#!/bin/bash
# SwarmUI, using the ComfyUI that vast's image already runs (127.0.0.1:18188) as its
# only backend, so both UIs share one ComfyUI, one GPU and one models folder.

utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. "${utils}/exit_portal.sh" "SwarmUI"

while [ -f "/.provisioning" ]; do
    echo "$PROC_NAME startup paused until instance provisioning has completed (/.provisioning present)"
    sleep 5
done

SWARMUI_DIR="${WORKSPACE:-/workspace}/SwarmUI"
COMFYUI_URL="http://127.0.0.1:18188"

export DOTNET_ROOT="${DOTNET_ROOT:-/opt/dotnet}"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
# SwarmUI shells out to git; the workspace copy is owned by whoever copied it.
export GIT_CONFIG_GLOBAL=/tmp/temporary-git-config
git config --file "$GIT_CONFIG_GLOBAL" --add safe.directory '*'

# Give ComfyUI up to five minutes to come up first so the backend connects on the first
# try. This is a courtesy, not a dependency: the backend is allowed to idle, so SwarmUI
# reconnects by itself whenever ComfyUI (re)appears.
for _ in $(seq 1 60); do
    curl -fs -o /dev/null --max-time 5 "${COMFYUI_URL}/system_stats" && break
    echo "Waiting for ComfyUI at ${COMFYUI_URL} before starting SwarmUI..."
    sleep 5
done

# Per-model presets go in once SwarmUI answers (first boot only).
/venv/main/bin/python /opt/imagegen/bin/swarmui-defaults.py &

cd "${SWARMUI_DIR}"
pty ./launch-linux.sh ${SWARMUI_ARGS:---launch_mode none --host 127.0.0.1 --port 17801}
