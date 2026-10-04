#!/usr/bin/env python3
"""Set Open WebUI up for the studio through its REST API. Runs on every boot.

Idempotent:
- creates or updates the studio_ui tool;
- points the tool servers at the four MCP servers;
- creates or updates the Studio Director model (the director prompt plus
  every tool, on top of the LLM vLLM serves);
- makes it the default for new chats.

Open WebUI keeps its settings in its database after the first boot, so this
writes them through the API rather than relying on environment variables.
It waits for Open WebUI to answer first. Stdlib only.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("OWUI_URL", "http://127.0.0.1:18081")
HERE = os.environ.get("STUDIO_OWUI_DIR", "/opt/studio-vast/owui")
LLM = os.environ.get("STUDIO_LLM_NAME", "studio-llm")
DIRECTOR = "studio-director"
# Added to every MCP port; tests on a machine already running these servers use 10000.
PORT_OFFSET = int(os.environ.get("STUDIO_MCP_PORT_OFFSET", "0"))
MCP = [("studio", "Studio", 8768, "Keyframes, animation, voices, music, cards and the edit"),
       ("cartoon", "Cartoon", 8769, "3D cartoons from a screenplay"),
       ("lectern", "Lectern", 8767, "Narrated lecture videos"),
       ("highway", "Highway", 8766, "Highway-driving footage")]


def call(method, path, body=None, token=None, timeout=60):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def wait_for_owui(limit=3600):
    began = time.time()
    while time.time() - began < limit:
        try:
            if call("GET", "/health", timeout=5)[0] == 200:
                return
        except OSError:
            pass
        time.sleep(3)
    sys.exit("studio: Open WebUI never answered; not configured")


def upsert(get_path, create_path, update_path, body, token):
    status, _ = call("GET", get_path, token=token)
    path = update_path if status == 200 else create_path
    status, reply = call("POST", path, body, token=token)
    if status != 200:
        raise RuntimeError(f"POST {path} answered HTTP {status}")
    return reply


def main():
    wait_for_owui()
    token = call("POST", "/api/v1/auths/signin", {"email": "", "password": ""})[1]["token"]
    with open(os.path.join(HERE, "studio_ui.py")) as fh:
        upsert("/api/v1/tools/id/studio_ui", "/api/v1/tools/create", "/api/v1/tools/id/studio_ui/update",
               {"id": "studio_ui", "name": "Studio", "content": fh.read(),
                "meta": {"description": "Live progress for studio jobs; pictures, clips and films in the chat."}},
               token)
    status, _ = call("POST", "/api/v1/configs/tool_servers", {"TOOL_SERVER_CONNECTIONS": [
        {"url": f"http://127.0.0.1:{port + PORT_OFFSET}/mcp", "path": "", "type": "mcp", "auth_type": "none", "key": "",
         "headers": None, "config": {"enable": True, "function_name_filter_list": "", "access_grants": []},
         "info": {"id": sid, "name": name, "description": about}} for sid, name, port, about in MCP]}, token)
    if status != 200:
        raise RuntimeError(f"tool servers: HTTP {status}")
    with open(os.path.join(HERE, "director.md")) as fh:
        system = fh.read()
    upsert(f"/api/v1/models/model?id={DIRECTOR}", "/api/v1/models/create", "/api/v1/models/model/update",
           {"id": DIRECTOR, "base_model_id": LLM, "name": "Studio Director",
            "meta": {"description": "Plans scenes and makes them: keyframes, animation, voices, music, the cut.",
                     "toolIds": ["studio_ui"] + [f"server:mcp:{sid}" for sid, *_ in MCP],
                     "capabilities": {"builtin_tools": False, "status_updates": True}},
            "params": {"system": system, "function_calling": "native", "temperature": 0.7,
                       "reasoning_effort": "low"},
            "access_grants": [], "is_active": True}, token)
    status, _ = call("POST", "/api/v1/configs/models", {"DEFAULT_MODELS": DIRECTOR, "DEFAULT_PINNED_MODELS": DIRECTOR,
                                                         "MODEL_ORDER_LIST": [DIRECTOR, LLM],
                                                         "DEFAULT_MODEL_METADATA": {}, "DEFAULT_MODEL_PARAMS": {}}, token)
    if status != 200:
        raise RuntimeError(f"default model: HTTP {status}")
    print("studio: Open WebUI configured (studio_ui, four MCP servers, studio-director as the default)", flush=True)


if __name__ == "__main__":
    for attempt in range(1, 6):
        try:
            main()
            break
        except Exception as e:
            print(f"studio: Open WebUI setup attempt {attempt} failed: {e}", flush=True)
            time.sleep(10 * attempt)
    else:
        sys.exit(1)
