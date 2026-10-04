"""ComfyUI on this machine, driven over its HTTP API.

The studio paints and animates through the ComfyUI that vast's image already
runs, at 127.0.0.1:18188 (STUDIO_COMFY overrides it). A job is one prompt
graph: queue it, follow it, and fetch what its output nodes wrote.

Step-by-step progress comes over ComfyUI's websocket when the
websocket-client package is installed. Without it, or if the socket drops,
the job is still followed by polling /history; it just reports no step counts.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

URL = os.environ.get("STUDIO_COMFY", "http://127.0.0.1:18188")


class ComfyError(RuntimeError):
    """ComfyUI refused a graph, a node failed running it, or ComfyUI is not there."""


def _summary(reply: dict) -> str:
    """One sentence from a /prompt refusal: which node, which input, why."""
    parts = []
    err = reply.get("error")
    if isinstance(err, dict) and err.get("message"):
        parts.append(err["message"].rstrip("."))
    for node, e in (reply.get("node_errors") or {}).items():
        for x in e.get("errors", []):
            parts.append(f"node {node} ({e.get('class_type', '?')}): {x.get('details') or x.get('message', '')}")
    return "; ".join(parts) or json.dumps(reply)[:300]


def _failure(status: dict) -> str:
    for kind, data in status.get("messages", []):
        if kind == "execution_error":
            return (f"{data.get('node_type', 'a node')} failed: "
                    f"{str(data.get('exception_message', '')).strip()}")
        if kind == "execution_interrupted":
            return "ComfyUI interrupted it"
    return "ComfyUI reported an error without saying why"


def progress_event(msg: dict, prompt_id: str, labels: dict):
    """(stage, percent) from one websocket message about our prompt, or None.

    `labels` maps node ids to what they do ("high-noise pass"), so a stage
    reads as words. The percent is -1.0 when there is no step count.
    """
    kind, data = msg.get("type"), msg.get("data") or {}
    if data.get("prompt_id") not in (None, prompt_id):
        return None
    node = data.get("node")
    if kind == "progress" and data.get("max"):
        stage = labels.get(str(node), f"node {node}")
        return f"{stage}, step {data['value']} of {data['max']}", 100.0 * data["value"] / data["max"]
    if kind == "executing" and node is not None:
        return labels.get(str(node), f"node {node}"), -1.0
    return None


class Comfy:
    def __init__(self, url: str = URL, opener=urllib.request.urlopen):
        self.url = url.rstrip("/")
        self.client_id = uuid.uuid4().hex
        self._open = opener

    # ---------------------------------------------------------------- http

    def _request(self, path: str, data: bytes | None = None, headers: dict | None = None,
                 timeout: float = 60) -> bytes:
        req = urllib.request.Request(self.url + path, data=data, headers=headers or {})
        try:
            with self._open(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                reply = json.loads(body)
            except ValueError:
                raise ComfyError(f"ComfyUI answered HTTP {e.code}: {body[:200]!r}") from None
            raise ComfyError(_summary(reply)) from None
        except (urllib.error.URLError, OSError) as e:
            raise ComfyError(f"ComfyUI is not answering at {self.url} ({e})") from None

    def _json(self, path: str, body: dict | None = None, timeout: float = 60) -> dict:
        data = None if body is None else json.dumps(body).encode()
        headers = {} if body is None else {"Content-Type": "application/json"}
        return json.loads(self._request(path, data, headers, timeout) or b"{}")

    # ------------------------------------------------------------- the API

    def upload(self, path: str) -> str:
        """Put a picture in ComfyUI's input folder; returns the name a LoadImage node takes."""
        ext = os.path.splitext(path)[1].lower() or ".png"
        name = f"studio-{uuid.uuid4().hex[:8]}{ext}"
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            payload = fh.read()
        b = uuid.uuid4().hex
        body = b"".join([
            f"--{b}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(), payload, b"\r\n",
            f"--{b}\r\n".encode(),
            b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
            f"--{b}--\r\n".encode(),
        ])
        reply = json.loads(self._request("/upload/image", body,
                                         {"Content-Type": f"multipart/form-data; boundary={b}"}))
        sub = reply.get("subfolder") or ""
        return f"{sub}/{reply['name']}" if sub else reply["name"]

    def queue(self, graph: dict) -> str:
        reply = self._json("/prompt", {"prompt": graph, "client_id": self.client_id})
        if reply.get("node_errors"):
            raise ComfyError(_summary(reply))
        return reply["prompt_id"]

    def history(self, prompt_id: str):
        """The finished record of a prompt, or None while it is queued or running."""
        return self._json(f"/history/{prompt_id}").get(prompt_id)

    def ahead(self, prompt_id: str):
        """How many prompts ComfyUI will run before this one; 0 once it is running; None if unknown."""
        q = self._json("/queue")
        running = q.get("queue_running", [])
        if any(item[1] == prompt_id for item in running):
            return 0
        pending = sorted(q.get("queue_pending", []), key=lambda item: item[0])
        for i, item in enumerate(pending):
            if item[1] == prompt_id:
                return len(running) + i
        return None

    def _socket(self):
        try:
            import websocket  # the websocket-client package
        except ImportError:
            return None
        url = self.url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        try:
            ws = websocket.create_connection(f"{url}/ws?clientId={self.client_id}", timeout=5)
            ws.settimeout(1.0)
            return ws
        except Exception:
            return None

    def run(self, graph: dict, on_progress=None, labels: dict | None = None,
            timeout: float = 3600, poll: float = 2.0) -> dict:
        """Queue a graph, follow it to its end, and return its outputs; ComfyError if it fails."""
        report = on_progress or (lambda stage, percent: None)
        labels = labels or {}
        ws = self._socket()          # before queueing, so no progress is missed
        try:
            prompt_id = self.queue(graph)
            deadline = time.time() + timeout
            checked = 0.0
            while time.time() < deadline:
                if ws is not None:
                    try:
                        raw = ws.recv()
                    except Exception as e:
                        if "Timeout" not in type(e).__name__:
                            ws = None          # closed: carry on by polling
                        raw = None
                    if isinstance(raw, str):
                        event = progress_event(json.loads(raw), prompt_id, labels)
                        if event:
                            report(*event)
                else:
                    time.sleep(poll)
                if time.time() - checked < poll:
                    continue
                checked = time.time()
                record = self.history(prompt_id)
                if record is not None:
                    status = record.get("status") or {}
                    if status.get("status_str") == "error" or status.get("completed") is False:
                        raise ComfyError(_failure(status))
                    return record.get("outputs") or {}
                waiting = self.ahead(prompt_id)
                if waiting:
                    report(f"waiting for ComfyUI: {waiting} job{'s' if waiting > 1 else ''} ahead", -1.0)
            raise ComfyError(f"gave up after {timeout / 60:.0f} minutes; ComfyUI is still working on it")
        finally:
            if ws is not None:
                ws.close()

    @staticmethod
    def files(outputs: dict) -> list:
        """Every file the output nodes wrote ({filename, subfolder, type}), in node order."""
        found = []
        for node in sorted(outputs, key=lambda k: int(k) if str(k).isdigit() else 0):
            for value in outputs[node].values():
                if isinstance(value, list):
                    found += [f for f in value if isinstance(f, dict) and "filename" in f]
        return found

    def download(self, f: dict, folder: str) -> str:
        q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                    "type": f.get("type", "output")})
        data = self._request(f"/view?{q}", timeout=600)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, os.path.basename(f["filename"]))
        with open(path, "wb") as fh:
            fh.write(data)
        return path
