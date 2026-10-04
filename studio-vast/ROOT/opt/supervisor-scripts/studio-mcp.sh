#!/bin/bash
# One of the adult repo's MCP servers, on 127.0.0.1 only: Open WebUI calls them from inside the container.
utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. /opt/studio-vast/bin/studio-env.sh
cd "$STUDIO_ROOT"
PY=/opt/venvs/tools/bin/python
case "$1" in
    studio)    pty "$PY" -m studio.mcp_server --host 127.0.0.1 --port 8768 ;;
    cartoon)   pty "$PY" -m cartoon.mcp_server --host 127.0.0.1 --port 8769 ;;
    lectern)   pty "$PY" -m lectern.mcp_server --host 127.0.0.1 --port 8767 ;;
    highway3d) pty "$PY" highway3d/mcp_server.py --host 127.0.0.1 --port 8766 ;;
    *) echo "studio-mcp.sh: unknown server '$1'"; exit 2 ;;
esac
