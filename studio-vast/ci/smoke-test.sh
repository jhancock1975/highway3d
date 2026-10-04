#!/usr/bin/env bash
# Boot the studio image the way vast.ai does (its entrypoint, supervisor, Instance Portal, Caddy,
# provisioning) on a CPU-only CI runner, without the 125 GB of models, and check that every
# service answers and is wired to the others:
#   - ComfyUI has the nodes the studio's graphs use, and accepts both graphs;
#   - the four MCP servers list their tools;
#   - Blender renders EEVEE headless, Manim typesets with LaTeX, Kokoro speaks, GIMP draws,
#     ffmpeg has the filters the assembler uses, ACE-Step and vLLM import;
#   - the repo's test suites pass inside the image;
#   - Open WebUI is set up (the studio_ui tool, the four MCP servers, the director preset), and a
#     chat sent through its API reaches the studio's MCP server (a stand-in plays vLLM, which
#     needs a GPU and a model);
#   - Caddy fronts the apps with TLS and the token.
#
# Usage: smoke-test.sh IMAGE [OUTPUT_DIR]
set -uo pipefail

IMAGE=${1:?usage: smoke-test.sh IMAGE [OUTPUT_DIR]}
OUT=${2:-$(mktemp -d)}
NAME=studio-smoke
TOKEN="ci-$(openssl rand -hex 16)"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"
FAILURES=0

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
section() { printf '\n== %s\n' "$*"; }

# curl run inside the container, against its own loopback
icurl() { docker exec "$NAME" curl -s --max-time "${CURL_MAX_TIME:-30}" "$@"; }

# inside DESCRIPTION COMMAND...: run a shell command inside the container, PASS/FAIL on its exit status
inside() {
    local desc=$1
    shift
    if docker exec "$NAME" bash -c "$*" > "$OUT/last.log" 2>&1; then
        pass "$desc"
    else
        fail "$desc"
        tail -n 25 "$OUT/last.log"
    fi
}

# wait_until SECONDS DESCRIPTION COMMAND...
wait_until() {
    local limit=$1 desc=$2 start=$SECONDS
    shift 2
    until "$@" >/dev/null 2>&1; do
        if (( SECONDS - start > limit )); then
            fail "$desc (gave up after ${limit}s)"
            return 1
        fi
        if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]]; then
            fail "$desc (container stopped)"
            return 1
        fi
        sleep 5
    done
    pass "$desc ($((SECONDS - start))s)"
}

diagnostics() {
    section "diagnostics"
    docker exec "$NAME" supervisorctl status || true
    docker exec "$NAME" sh -c 'for f in /var/log/portal/*.log; do echo "----- $f"; tail -n 60 "$f"; done' || true
    echo "----- docker logs (tail)"
    docker logs --tail 200 "$NAME" 2>&1 || true
    docker logs "$NAME" > "$OUT/container.log" 2>&1 || true
}

section "start the container"
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=localhost" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
    -keyout "$OUT/instance.key" -out "$OUT/instance.crt" 2>/dev/null
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker create --name "$NAME" --shm-size=4g \
    -e OPEN_BUTTON_TOKEN="$TOKEN" \
    -e VAST_TCP_PORT_1111=1111 -e VAST_TCP_PORT_8081=8081 -e VAST_TCP_PORT_8188=8188 \
    -e STUDIO_MODELS=none \
    -e COMFYUI_ARGS="--disable-auto-launch --enable-cors-header --port 18188 --cpu" \
    "$IMAGE" --no-update-portal --no-update-vast >/dev/null
docker cp "$OUT/instance.crt" "$NAME:/etc/instance.crt"
docker cp "$OUT/instance.key" "$NAME:/etc/instance.key"
docker cp "$HERE" "$NAME:/ci"
# On vast the portal opens a public trycloudflare.com tunnel per app; not from CI.
docker cp "$NAME:/etc/supervisor/conf.d/tunnel_manager.conf" "$OUT/tunnel_manager.conf"
sed -i 's/^autostart=.*/autostart=false/' "$OUT/tunnel_manager.conf"
grep -q '^autostart=false' "$OUT/tunnel_manager.conf" || echo 'autostart=false' >> "$OUT/tunnel_manager.conf"
docker cp "$OUT/tunnel_manager.conf" "$NAME:/etc/supervisor/conf.d/tunnel_manager.conf"
docker start "$NAME" >/dev/null && pass "container started"

section "first boot and provisioning"
wait_until 900 "provisioning finished" docker exec "$NAME" sh -c \
    'test ! -e /.provisioning && { test -e /.provisioning_complete || test -e /.provisioning_failed; }'
if docker exec "$NAME" test -e /.provisioning_complete && ! docker exec "$NAME" test -e /.provisioning_failed; then
    pass "provisioner reported success"
else
    fail "provisioner did not report success"
fi
docker logs "$NAME" > "$OUT/boot.log" 2>&1
if grep -q "Traceback" "$OUT/boot.log" && grep -B2 -A8 "Traceback" "$OUT/boot.log" | grep -q "log-tee"; then
    fail "a supervisor program's log copier (log-tee) crashed at boot"; grep -A8 "Traceback" "$OUT/boot.log" | head -20
else
    pass "every program's log copier started"
fi
grep -q 'provisioning from /opt/studio-vast/provisioning/none.yaml' "$OUT/boot.log" \
    && pass "STUDIO_MODELS=none picked none.yaml" || fail "STUDIO_MODELS=none did not pick none.yaml"
for set in all none; do
    if docker exec "$NAME" provisioner --dry-run "/opt/studio-vast/provisioning/$set.yaml" > "$OUT/dry-run-$set.log" 2>&1; then
        pass "provisioner accepts $set.yaml"
    else
        fail "provisioner rejects $set.yaml"; tail -n 30 "$OUT/dry-run-$set.log"
    fi
done
inside "studio folders laid out, renders linked into the repo" \
    '. /opt/studio-vast/bin/studio-env.sh && test -d "$STUDIO_MEDIA" && test -d "$STUDIO_WORK" && test -s "$STUDIO_WEBUI/secret" && test "$(readlink /opt/highway3d/renders)" = "$STUDIO_RENDERS"'

section "ComfyUI (127.0.0.1:18188)"
wait_until 600 "ComfyUI answers /system_stats" icurl -f http://127.0.0.1:18188/system_stats
icurl http://127.0.0.1:18188/object_info > "$OUT/object_info.json"
python3 - "$OUT/object_info.json" <<'EOF' && pass "ComfyUI has every node the studio's graphs use" || fail "ComfyUI node check"
import json, sys
info = json.load(open(sys.argv[1]))
need = ["WanImageToVideo", "CreateVideo", "SaveVideo", "ModelSamplingAuraFlow", "T5TokenizerOptions",
        "EmptySD3LatentImage", "ModelSamplingSD3", "KSamplerAdvanced", "UNETLoader", "LoadImage"]
missing = [n for n in need if n not in info]
types = info["CLIPLoader"]["input"]["required"]["type"][0]
missing += [f"CLIPLoader type {t}" for t in ("wan", "chroma") if t not in types]
print("missing:", missing or "nothing")
sys.exit(1 if missing else 0)
EOF
# Both graphs, against placeholder model files: /prompt validates every input, then the run fails
# on the empty weights, which is fine.
docker exec "$NAME" /opt/venvs/tools/bin/python /ci/graphs.py placeholders /workspace/ComfyUI/models
docker exec "$NAME" bash -c 'mkdir -p /workspace/ComfyUI/input && ffmpeg -v error -y -f lavfi -i testsrc2=size=832x480 -frames:v 1 /workspace/ComfyUI/input/start.png'
for graph in chroma wan; do
    docker exec "$NAME" /opt/venvs/tools/bin/python /ci/graphs.py prompt "$graph" > "$OUT/graph-$graph.json"
    code=$(docker exec -i "$NAME" curl -s -o /tmp/prompt-reply.json -w '%{http_code}' -H 'Content-Type: application/json' \
           --data-binary @- http://127.0.0.1:18188/prompt < "$OUT/graph-$graph.json")
    if [[ "$code" == 200 ]] && docker exec "$NAME" grep -q prompt_id /tmp/prompt-reply.json; then
        pass "ComfyUI accepts the $graph graph"
    else
        fail "ComfyUI refused the $graph graph (HTTP $code)"; docker exec "$NAME" cat /tmp/prompt-reply.json; echo
    fi
done
icurl -X POST http://127.0.0.1:18188/interrupt >/dev/null
icurl -X POST -H 'Content-Type: application/json' -d '{"clear": true}' http://127.0.0.1:18188/queue >/dev/null
docker exec "$NAME" bash -c 'find /workspace/ComfyUI/models -size 0 -name "*.safetensors" -delete'

section "the adult repo's MCP servers"
T=/opt/venvs/tools/bin/python
wait_until 120 "studio MCP answers" docker exec "$NAME" $T /ci/mcp_list.py http://127.0.0.1:8768/mcp studio_list
inside "studio MCP has the new and old tools" \
    "$T /ci/mcp_list.py http://127.0.0.1:8768/mcp studio_picture studio_animate studio_extend studio_compose studio_speak studio_assemble studio_status"
inside "cartoon MCP lists its tools" "$T /ci/mcp_list.py http://127.0.0.1:8769/mcp cartoon_make cartoon_status"
inside "lectern MCP lists its tools" "$T /ci/mcp_list.py http://127.0.0.1:8767/mcp lecture_render lecture_status"
inside "highway3d MCP lists its tools" "$T /ci/mcp_list.py http://127.0.0.1:8766/mcp highway_render"

section "engines, on the CPU"
docker exec -i "$NAME" bash -c 'cat > /tmp/eevee.py' <<'EOF'
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_monkey_add()
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
cam.location, cam.rotation_euler = (0, -4, 0), (1.5708, 0, 0)
sc.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sc.collection.objects.link(sun)
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 64
sc.render.filepath = "/tmp/eevee.png"
bpy.ops.render.render(write_still=True)
print("EEVEE_OK")
EOF
inside "Blender renders EEVEE headless" 'blender -b --factory-startup --python /tmp/eevee.py 2>&1 | tail -5; test -s /tmp/eevee.png'
inside "blender_gpu picks the CPU on a GPU-less machine" \
    "blender -b --python-expr \"import sys; sys.path.insert(0, '/opt/highway3d'); import bpy, blender_gpu; print('GPU', blender_gpu.enable(bpy))\" 2>&1 | grep -x 'GPU CPU'"
docker exec -i "$NAME" bash -c 'mkdir -p /tmp/tex && cat > /tmp/tex/t.py' <<'EOF'
from manim import MathTex, Scene


class T(Scene):
    def construct(self):
        self.add(MathTex(r"\sum_{n=1}^\infty \frac{1}{n^2}=\frac{\pi^2}{6}"))
EOF
inside "Manim typesets with LaTeX" 'cd /tmp/tex && /opt/highway3d/lectern/.manimvenv/bin/manim -ql --format png -s t.py T && find /tmp/tex/media -name "*.png" | grep -q .'
inside "Kokoro speaks, GIMP draws, ffmpeg assembles (studio/test_engines.py)" \
    '. /opt/studio-vast/bin/studio-env.sh && cd /opt/highway3d && studio/.venv/bin/python studio/test_engines.py'
inside "ACE-Step imports in its venv, on the base image's torch" \
    '/opt/highway3d/lectern/.musicvenv/bin/python -c "import acestep.handler, acestep.inference, acestep.llm_inference, torch; print(torch.__version__)"'
inside "vLLM imports" '/opt/vllm/bin/python -c "import vllm; print(vllm.__version__)"'
inside "ffmpeg has the assembler's filters" \
    'f=$(ffmpeg -hide_banner -filters 2>/dev/null); for x in xfade zoompan sidechaincompress loudnorm; do echo "$f" | grep -qw "$x" || { echo "no $x"; exit 1; }; done'

section "the repo's test suites, inside the image"
for t in $(docker exec "$NAME" bash -c 'cd /opt/highway3d && ls studio/test_*.py | grep -v test_engines'); do
    inside "$t" "cd /opt/highway3d && studio/.venv/bin/python $t"
done
inside "cartoon/test_cartoon.py" 'cd /opt/highway3d && cartoon/.venv/bin/python cartoon/test_cartoon.py'
inside "test_forgiving.py" 'cd /opt/highway3d && lectern/.mcpvenv/bin/python test_forgiving.py'
inside "lectern/test_status.py" 'cd /opt/highway3d && lectern/.mcpvenv/bin/python lectern/test_status.py'
inside "test_blender_gpu.py" 'cd /opt/highway3d && python3 test_blender_gpu.py'
inside "the Open WebUI tool's tests" '/opt/openwebui/bin/python /opt/studio-vast/owui/test_studio_ui.py'

section "Open WebUI (127.0.0.1:18081)"
wait_until 900 "Open WebUI answers /health" icurl -f http://127.0.0.1:18081/health
wait_until 300 "owui-setup.py configured Open WebUI" docker exec "$NAME" grep -q "studio: Open WebUI configured" /var/log/portal/openwebui.log
# vLLM needs a GPU and a model; a stand-in answers on its port so the chat can run.
docker exec -d "$NAME" python3 /ci/fake_llm.py 18000 studio-llm
sleep 2
inside "a chat through Open WebUI's API reaches the studio MCP server" 'python3 /ci/owui_e2e.py http://127.0.0.1:18081'

section "Instance Portal and Caddy (TLS + token auth)"
wait_until 300 "Instance Portal answers on 127.0.0.1:11111" icurl -f http://127.0.0.1:11111/
for port in 1111 8081 8188; do
    wait_until 120 "Caddy serves HTTPS on :$port" icurl -k -o /dev/null https://127.0.0.1:$port/
    noauth=$(icurl -k -o /dev/null -w '%{http_code}' https://127.0.0.1:$port/)
    withauth=$(icurl -k -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" https://127.0.0.1:$port/)
    if [[ "$noauth" == 401 && "$withauth" =~ ^(200|302)$ ]]; then
        pass ":$port refuses anonymous requests ($noauth) and lets the token in ($withauth)"
    else
        fail ":$port anonymous=$noauth with-token=$withauth (want 401 and 200/302)"
    fi
done

section "services"
docker exec "$NAME" supervisorctl status | tee "$OUT/supervisor.txt"
for prog in comfyui openwebui caddy instance_portal studio-mcp-studio studio-mcp-cartoon studio-mcp-lectern studio-mcp-highway3d; do
    grep -qE "^${prog}[[:space:]]+RUNNING" "$OUT/supervisor.txt" && pass "supervisor: $prog RUNNING" \
        || fail "supervisor: $prog not RUNNING"
done
grep -qE "^vllm[[:space:]]+EXITED" "$OUT/supervisor.txt" && docker exec "$NAME" grep -q "vLLM not started" /var/log/portal/vllm.log \
    && pass "vllm exited cleanly with no model to serve" || fail "vllm did not exit cleanly without a model"

if (( FAILURES > 0 )); then
    diagnostics
    printf '\n%d check(s) failed\n' "$FAILURES"
    exit 1
fi
docker logs "$NAME" > "$OUT/container.log" 2>&1 || true
printf '\nAll checks passed\n'
