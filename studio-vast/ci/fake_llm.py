#!/usr/bin/env python3
"""A stand-in for vLLM in tests: an OpenAI-compatible server that calls one tool, then answers.

    python3 fake_llm.py PORT MODEL_ID

On a request with tools, where the last message is the user's, it calls the
first tool whose name ends in "studio_list" (streamed the way vLLM streams
tool calls). After the tool's result comes back, it answers in words,
quoting the result. Stdlib only.
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, MODEL = int(sys.argv[1]), sys.argv[2]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            return self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "test"}]})
        self._json(404, {})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = req.get("messages", [])
        tools = [t["function"]["name"] for t in req.get("tools") or []]
        wanted = next((n for n in tools if n.endswith("studio_list")), None)
        if wanted and msgs and msgs[-1].get("role") == "user":
            chunks = [{"role": "assistant", "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                                            "function": {"name": wanted, "arguments": ""}}]},
                      {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}]
            finish = "tool_calls"
        else:
            result = next((m.get("content") for m in reversed(msgs) if m.get("role") == "tool"), "")
            chunks = [{"role": "assistant", "content": f"The studio says: {result}"}]
            finish = "stop"
        if not req.get("stream"):
            msg = {"role": "assistant", "content": chunks[0].get("content")}
            if finish == "tool_calls":
                msg["tool_calls"] = [{"id": "call_1", "type": "function", "function": {"name": wanted, "arguments": "{}"}}]
            return self._json(200, {"id": "x", "object": "chat.completion", "model": MODEL, "created": int(time.time()),
                                    "choices": [{"index": 0, "message": msg, "finish_reason": finish}]})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for delta in chunks + [{}]:
            body = {"id": "x", "object": "chat.completion.chunk", "model": MODEL, "created": int(time.time()),
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None if delta else finish}]}
            self.wfile.write(f"data: {json.dumps(body)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
