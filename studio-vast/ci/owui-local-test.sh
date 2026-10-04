#!/usr/bin/env bash
# Run Open WebUI 0.11.4 on this Mac with the real studio MCP server and a stand-in LLM, set
# it up with owui-setup.py, and check it end to end with owui_e2e.py. Everything is stopped
# afterwards.
#   owui-local-test.sh OWUI_PYTHON STUDIO_PYTHON
set -euo pipefail
OWUI_PY=${1:?usage: owui-local-test.sh OWUI_PYTHON STUDIO_PYTHON}
STUDIO_PY=${2:?usage: owui-local-test.sh OWUI_PYTHON STUDIO_PYTHON}
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
T=$(mktemp -d)
echo "work folder: $T"
trap 'kill $(jobs -p) 2>/dev/null || true; wait 2>/dev/null || true' EXIT
python3 "$HERE/fake_llm.py" 18990 studio-llm &
(cd "$REPO" && STUDIO_MEDIA="$T/static/studio/media" STUDIO_WORK="$T/work" "$STUDIO_PY" -m studio.mcp_server --host 127.0.0.1 --port 18768 > "$T/mcp.log" 2>&1) &
OWUI_BIN="$(dirname "$OWUI_PY")/open-webui"
(cd "$T" && DATA_DIR="$T/data" STATIC_DIR="$T/static" WEBUI_SECRET_KEY=test WEBUI_AUTH=False ENABLE_OLLAMA_API=False \
  OPENAI_API_BASE_URL=http://127.0.0.1:18990/v1 OPENAI_API_KEY=local OFFLINE_MODE=True \
  ENABLE_TITLE_GENERATION=False ENABLE_TAGS_GENERATION=False ENABLE_FOLLOW_UP_GENERATION=False \
  "$OWUI_BIN" serve --host 127.0.0.1 --port 18981 > "$T/owui.log" 2>&1) &
OWUI_URL=http://127.0.0.1:18981 STUDIO_MCP_PORT_OFFSET=10000 STUDIO_OWUI_DIR="$REPO/studio-vast/ROOT/opt/studio-vast/owui" STUDIO_LLM_NAME=studio-llm \
  python3 "$REPO/studio-vast/ROOT/opt/studio-vast/bin/owui-setup.py"
python3 "$HERE/owui_e2e.py" http://127.0.0.1:18981
