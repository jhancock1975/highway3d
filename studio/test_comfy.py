"""The ComfyUI client, against a stand-in ComfyUI on a local port.

    studio/.venv/bin/python studio/test_comfy.py
"""
import json
import os
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import comfy as C  # noqa: E402

SEEN = {"uploads": [], "prompts": []}
POLLS = {"p1": 0}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/upload/image":
            name = re.search(rb'filename="([^"]+)"', body).group(1).decode()
            SEEN["uploads"].append((name, b"PNGBYTES" in body))
            return self._send(200, {"name": name, "subfolder": "", "type": "input"})
        if self.path == "/prompt":
            graph = json.loads(body)["prompt"]
            SEEN["prompts"].append(graph)
            if any(n["class_type"] == "Broken" for n in graph.values()):
                return self._send(400, {"error": {"type": "prompt_outputs_failed_validation",
                                                  "message": "Prompt outputs failed validation"},
                                        "node_errors": {"3": {"class_type": "UNETLoader", "errors": [
                                            {"message": "Value not in list",
                                             "details": "unet_name: 'Wan2.2_missing.safetensors' not in []"}]}}})
            pid = "p2" if any(n["class_type"] == "Fails" for n in graph.values()) else "p1"
            return self._send(200, {"prompt_id": pid, "number": 1, "node_errors": {}})
        self._send(404, {})

    def do_GET(self):
        if self.path == "/queue":
            running = [[1, "p1", {}, {}, []]] if POLLS["p1"] < 2 else []
            return self._send(200, {"queue_running": [[0, "other", {}, {}, []]], "queue_pending": running})
        if self.path == "/history/p1":
            POLLS["p1"] += 1
            if POLLS["p1"] < 3:
                return self._send(200, {})
            return self._send(200, {"p1": {"outputs": {"9": {"images": [
                {"filename": "a.png", "subfolder": "studio", "type": "output"}]}},
                "status": {"status_str": "success", "completed": True, "messages": []}}})
        if self.path == "/history/p2":
            return self._send(200, {"p2": {"outputs": {}, "status": {"status_str": "error", "completed": False,
                "messages": [["execution_error", {"node_type": "KSamplerAdvanced",
                                                  "exception_message": "CUDA out of memory"}]]}}})
        if self.path.startswith("/view?"):
            return self._send(200, b"IMAGEDATA", "image/png")
        self._send(404, {})


SERVER = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{SERVER.server_address[1]}"


def test_upload_sends_the_file_and_returns_its_name():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "frame.png")
    open(p, "wb").write(b"PNGBYTES")
    name = C.Comfy(URL).upload(p)
    assert name.endswith(".png") and SEEN["uploads"][-1] == (name, True), (name, SEEN["uploads"])


def test_refusal_names_the_node_and_the_missing_file():
    try:
        C.Comfy(URL).queue({"3": {"class_type": "Broken", "inputs": {}}})
    except C.ComfyError as e:
        assert "UNETLoader" in str(e) and "Wan2.2_missing.safetensors" in str(e), str(e)
    else:
        raise AssertionError("no error")


def test_run_waits_reports_waiting_and_returns_outputs():
    said = []
    out = C.Comfy(URL).run({"1": {"class_type": "Ok", "inputs": {}}},
                           on_progress=lambda s, p: said.append((s, p)), poll=0.05)
    files = C.Comfy.files(out)
    assert files == [{"filename": "a.png", "subfolder": "studio", "type": "output"}], files
    assert any("waiting for ComfyUI" in s for s, _ in said), said


def test_download_writes_the_file():
    d = tempfile.mkdtemp()
    path = C.Comfy(URL).download({"filename": "a.png", "subfolder": "studio", "type": "output"}, d)
    assert open(path, "rb").read() == b"IMAGEDATA" and path.endswith("a.png")


def test_a_failed_run_says_which_node_and_why():
    try:
        C.Comfy(URL).run({"1": {"class_type": "Fails", "inputs": {}}}, poll=0.05)
    except C.ComfyError as e:
        assert "KSamplerAdvanced" in str(e) and "out of memory" in str(e), str(e)
    else:
        raise AssertionError("no error")


def test_progress_events_read_as_words():
    labels = {"11": "high-noise pass"}
    msg = {"type": "progress", "data": {"value": 2, "max": 4, "prompt_id": "p1", "node": "11"}}
    assert C.progress_event(msg, "p1", labels) == ("high-noise pass, step 2 of 4", 50.0)
    assert C.progress_event(msg, "other", labels) is None
    ex = {"type": "executing", "data": {"node": "11", "prompt_id": "p1"}}
    assert C.progress_event(ex, "p1", labels) == ("high-noise pass", -1.0)
    assert C.progress_event({"type": "status", "data": {}}, "p1", labels) is None


def test_unreachable_comfyui_is_a_sentence():
    try:
        C.Comfy("http://127.0.0.1:9").queue({})
    except C.ComfyError as e:
        assert "not answering" in str(e), str(e)
    else:
        raise AssertionError("no error")



def test_a_node_error_over_several_lines_reads_as_one():
    said = C._failure({"messages": [["execution_error", {
        "node_type": "UNETLoader",
        "exception_message": "Error while deserializing header: MetadataIncompleteBuffer\n"
                             "File path: /workspace/models/x.safetensors\n\nThe safetensors file is corrupt."}]]})
    assert "\n" not in said and "File path: /workspace/models/x.safetensors" in said, said


def test_busy_counts_the_running_and_waiting_prompts():
    expected = 1 + (1 if POLLS["p1"] < 2 else 0)
    assert C.Comfy(URL).pending() == expected


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
