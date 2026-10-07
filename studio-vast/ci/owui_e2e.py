#!/usr/bin/env python3
"""Check an Open WebUI set up by owui-setup.py, end to end, headless.

    python3 owui_e2e.py http://127.0.0.1:18081

Checks:
- the studio_ui tool and the four MCP tool servers are registered;
- the studio-director preset exists, is the default, and carries the director prompt;
- a chat sent through the API makes the LLM call the studio MCP server's
  studio_list, and the tool result lands in the saved chat.

Exits non-zero naming the first thing that is wrong. Stdlib only.
"""
import json
import sys
import time
import urllib.request
import uuid

BASE = sys.argv[1].rstrip("/")


def call(method, path, body=None, token=None, timeout=300):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def check(ok, what):
    print(("PASS  " if ok else "FAIL  ") + what)
    if not ok:
        sys.exit(1)


token = call("POST", "/api/v1/auths/signin", {"email": "", "password": ""})["token"]
tools = {t["id"] for t in call("GET", "/api/v1/tools/", token=token)}
check("studio_ui" in tools, f"studio_ui tool registered ({sorted(tools)})")
servers = call("GET", "/api/v1/configs/tool_servers", token=token)["TOOL_SERVER_CONNECTIONS"]
ids = sorted(s["info"]["id"] for s in servers)
check(ids == ["cartoon", "highway", "lectern", "studio"], f"four MCP tool servers ({ids})")
model = call("GET", "/api/v1/models/model?id=studio-director", token=token)
check(model and "director of a small film studio" in model["params"]["system"], "studio-director has the director prompt")
check(model and "Never depict a real, identifiable person in anything" in model["params"]["system"],
      "the director keeps real people out of everything it makes, as the spec says")
check(model and model["meta"]["capabilities"].get("vision") is True and "attaches a picture" in model["params"]["system"],
      "the director takes pictures the person attaches, and is told to match their style")
check(model and 'engine="grok"' in model["params"]["system"],
      "the director knows when to paint with Grok and when to stay with Chroma")
check(model and "character sheet" in model["params"]["system"] and "from_picture" in model["params"]["system"],
      "the director keeps characters the same by painting each new still from an earlier one")
check(model and "Every shot is real motion" in model["params"]["system"]
      and "never stand in for animation" in model["params"]["system"],
      "the director animates every shot instead of zooming or panning over stills")
check("server:mcp:studio" in model["meta"]["toolIds"] and "studio_ui" in model["meta"]["toolIds"],
      "studio-director carries studio_ui and the MCP servers")
defaults = call("GET", "/api/v1/configs/models", token=token)
check(defaults.get("DEFAULT_MODELS") == "studio-director", f"studio-director is the default ({defaults.get('DEFAULT_MODELS')})")
ui = (call("GET", "/api/v1/users/user/settings", token=token) or {}).get("ui") or {}
check(ui.get("iframeSandboxAllowSameOrigin") is True,
      "chat embeds may send vast's login cookie, so their pictures and videos load through Caddy")
check(ui.get("showChangelog") is False, "no What's New dialog over the first chat")

chat = call("POST", "/api/v1/chats/new", {"chat": {"title": "e2e", "models": ["studio-director"], "messages": [], "history": {"messages": {}, "currentId": None}}}, token=token)
user_id, reply_id = str(uuid.uuid4()), str(uuid.uuid4())
call("POST", "/api/chat/completions", {
    "model": "studio-director", "stream": True, "chat_id": chat["id"], "id": reply_id,
    "messages": [{"role": "user", "content": "What is in the studio library?"}],
    "tool_ids": model["meta"]["toolIds"],
    "user_message": {"id": user_id, "role": "user", "content": "What is in the studio library?",
                     "parentId": None, "childrenIds": []}}, token=token, timeout=600)
saved = ""
for _ in range(60):
    saved = json.dumps(call("GET", f"/api/v1/chats/{chat['id']}", token=token))
    if "library is empty" in saved or "is in the library" in saved:
        break
    time.sleep(2)
if not ("library is empty" in saved or "in the library" in saved):
    print(saved[:4000])
check("library is empty" in saved or "in the library" in saved,
      "the LLM called the studio MCP server's studio_list and its answer is in the chat")
print("All Open WebUI checks passed")
