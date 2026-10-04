#!/bin/bash
# Open WebUI on 127.0.0.1:18081, fronted by Caddy as "Studio Chat" (external 8081). Single user:
# Caddy's Open-button token is the login, so Open WebUI's own sign-in is off. owui-setup.py
# configures the tools and the director through the API once Open WebUI answers.
utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. "${utils}/exit_portal.sh" "Studio Chat"
. /opt/studio-vast/bin/studio-env.sh

mkdir -p "$DATA_DIR" "$STUDIO_MEDIA" "$STUDIO_RENDERS"
export WEBUI_SECRET_KEY="$(cat "$STUDIO_WEBUI/secret")"
export WEBUI_AUTH=False ENABLE_OLLAMA_API=False OFFLINE_MODE=True \
       OPENAI_API_BASE_URL=http://127.0.0.1:18000/v1 OPENAI_API_KEY=local \
       DEFAULT_MODELS=studio-director ENABLE_TAGS_GENERATION=False ENABLE_FOLLOW_UP_GENERATION=False \
       STUDIO_WORK STATIC_DIR
/usr/bin/python3 /opt/studio-vast/bin/owui-setup.py &
cd "$DATA_DIR"
# exec, not pty: pty turned a crash into a clean exit, and supervisor only restarts unexpected ones.
exec /opt/openwebui/bin/open-webui serve --host 127.0.0.1 --port 18081
