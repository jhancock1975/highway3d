#!/bin/bash
# One of the adult repo's MCP servers, on 127.0.0.1 only: Open WebUI calls them from inside the container.
# Take the server's name out of $1 first: the utils are sourced, so they see this script's
# arguments, and logging.sh reads $1 as its log path.
server=${1:?usage: studio-mcp.sh studio|cartoon|lectern|highway3d}
set --
utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. /opt/studio-vast/bin/studio-env.sh
cd "$STUDIO_ROOT"
PY=/opt/venvs/tools/bin/python
# With two or more GPUs, the jobs these servers start (ACE-Step, Blender) stay off vLLM's.
[ "${STUDIO_GPU_COUNT:-1}" -ge 2 ] 2>/dev/null && export CUDA_VISIBLE_DEVICES="$STUDIO_WORK_GPUS"
# exec, not pty: pty turned a crash into a clean exit.
case "$server" in
    studio)    exec "$PY" -m studio.mcp_server --host 127.0.0.1 --port 8768 ;;
    cartoon)   exec "$PY" -m cartoon.mcp_server --host 127.0.0.1 --port 8769 ;;
    lectern)   exec "$PY" -m lectern.mcp_server --host 127.0.0.1 --port 8767 ;;
    highway3d) exec "$PY" highway3d/mcp_server.py --host 127.0.0.1 --port 8766 ;;
    *) echo "studio-mcp.sh: unknown server '$server'"; exit 2 ;;
esac
