#!/usr/bin/env bash
# Boot the image the way vast.ai does (its entrypoint, supervisor, Instance Portal,
# Caddy, provisioning) on a CPU-only CI runner, without the 63 GB of models, and check
# that every service answers and is wired to the others. Ends with a real generation
# through SwarmUI -> ComfyUI on the CPU, using the small SD 1.5 checkpoint that vast's
# ComfyUI image ships with.
#
# Usage: smoke-test.sh IMAGE [OUTPUT_DIR]
set -uo pipefail

IMAGE=${1:?usage: smoke-test.sh IMAGE [OUTPUT_DIR]}
OUT=${2:-$(mktemp -d)}
NAME=imagegen-smoke
TOKEN="ci-$(openssl rand -hex 16)"
mkdir -p "$OUT"
FAILURES=0

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
section() { printf '\n== %s\n' "$*"; }

# curl run inside the container, against its own loopback
icurl() { docker exec "$NAME" curl -s --max-time "${CURL_MAX_TIME:-30}" "$@"; }

# SwarmUI API call from inside the container: swarm ROUTE JSON
swarm() { icurl -X POST -H 'Content-Type: application/json' -d "$2" "http://127.0.0.1:17801/API/$1"; }

# json EXPR: read JSON on stdin, print a Python expression evaluated against it as `d`
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

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
    docker exec "$NAME" sh -c 'for f in /var/log/portal/*.log; do echo "----- $f"; tail -n 80 "$f"; done' || true
    echo "----- docker logs (tail)"
    docker logs --tail 200 "$NAME" 2>&1 || true
    docker logs "$NAME" > "$OUT/container.log" 2>&1 || true
}

section "start the container"
# A throwaway certificate, so the boot script finds a usable pair and never asks
# vast's console to sign one, while Caddy still serves real TLS.
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=localhost" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
    -keyout "$OUT/instance.key" -out "$OUT/instance.crt" 2>/dev/null
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker create --name "$NAME" --shm-size=2g \
    -e OPEN_BUTTON_TOKEN="$TOKEN" \
    -e IMAGEGEN_MODELS=none \
    -e COMFYUI_ARGS="--disable-auto-launch --enable-cors-header --port 18188 --cpu" \
    "$IMAGE" --no-update-portal --no-update-vast >/dev/null
docker cp "$OUT/instance.crt" "$NAME:/etc/instance.crt"
docker cp "$OUT/instance.key" "$NAME:/etc/instance.key"
docker start "$NAME" >/dev/null && pass "container started"

section "first boot and provisioning"
wait_until 900 "provisioning finished (/.provisioning removed)" \
    docker exec "$NAME" sh -c 'test ! -e /.provisioning'
if docker exec "$NAME" test -e /.provisioning_complete && ! docker exec "$NAME" test -e /.provisioning_failed; then
    pass "provisioner reported success"
else
    fail "provisioner did not report success"
fi
if docker logs "$NAME" 2>&1 | grep -q 'Provisioning instance with manifest from /opt/imagegen/provisioning/none.yaml'; then
    pass "IMAGEGEN_MODELS=none made the provisioner use none.yaml"
else
    fail "IMAGEGEN_MODELS=none did not select none.yaml"
fi
for set in all kroma chroma none; do
    if docker exec "$NAME" provisioner --dry-run "/opt/imagegen/provisioning/$set.yaml" > "$OUT/dry-run-$set.log" 2>&1; then
        pass "provisioner accepts $set.yaml ($(grep -c 'Would download' "$OUT/dry-run-$set.log") downloads planned)"
    else
        fail "provisioner rejects $set.yaml"; tail -n 30 "$OUT/dry-run-$set.log"
    fi
done
docker exec "$NAME" test -f /workspace/SwarmUI/Data/Settings.fds && pass "SwarmUI copied to /workspace with its settings" \
    || fail "SwarmUI settings missing from /workspace"

section "ComfyUI (127.0.0.1:18188)"
wait_until 600 "ComfyUI answers /system_stats" icurl -f http://127.0.0.1:18188/system_stats
icurl http://127.0.0.1:18188/object_info > "$OUT/object_info.json"
python3 - "$OUT/object_info.json" <<'EOF' && pass "SwarmUI's custom nodes loaded in ComfyUI, CLIPLoader knows krea2 and chroma" || fail "ComfyUI node check"
import json, sys
info = json.load(open(sys.argv[1]))
need = ["SwarmKSampler", "SwarmTextEncodeAdvanced", "SwarmAttnTokenWeights", "SwarmSaveImageWS",
        "SwarmLoraLoader", "SwarmRemBg", "SwarmYoloDetection", "SwarmSaveAnimationWS"]
missing = [n for n in need if n not in info]
types = info["CLIPLoader"]["input"]["required"]["type"][0]
missing += [f"CLIPLoader type {t}" for t in ("krea2", "chroma") if t not in types]
print("missing:", missing or "nothing")
sys.exit(1 if missing else 0)
EOF

section "SwarmUI (127.0.0.1:17801)"
wait_until 600 "SwarmUI answers HTTP" icurl -f http://127.0.0.1:17801/
code=$(icurl -o /dev/null -w '%{http_code}' http://127.0.0.1:17801/Text2Image)
[[ "$code" == 200 ]] && pass "Generate page served directly, no install wizard (HTTP $code)" \
    || fail "Generate page returned HTTP $code (302 would mean the install wizard)"

backend_running() {
    local sid
    sid=$(swarm GetNewSession '{}' | json 'd["session_id"]') || return 1
    swarm ListBackends "{\"session_id\": \"$sid\"}" > "$OUT/backends.json"
    json 'all(b["type"] == "comfyui_api" and b["status"] == "running" for b in d.values()) and len(d) == 1' \
        < "$OUT/backends.json" | grep -qx True
}
wait_until 300 "SwarmUI reports its ComfyUI backend (http://127.0.0.1:18188) as running" backend_running
python3 -c "import json; [print('      backend', k, b['type'], b['status'], b['settings'].get('Address')) for k, b in json.load(open('$OUT/backends.json')).items()]" || true

presets_linked() {
    local sid
    sid=$(swarm GetNewSession '{}' | json 'd["session_id"]') || return 1
    swarm GetMyUserData "{\"session_id\": \"$sid\"}" > "$OUT/userdata.json"
    python3 - "$OUT/userdata.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
titles = {p["title"] for p in d.get("presets", [])}
links = d.get("model_preset_links", {}).get("Stable-Diffusion", {})
ok = {"Kroma turbo", "Chroma1-HD"} <= titles \
    and links.get("kroma-v0.3-turbo") == ["Kroma turbo"] and links.get("Chroma1-HD") == ["Chroma1-HD"]
sys.exit(0 if ok else 1)
EOF
}
wait_until 300 "per-model presets added and linked (Kroma turbo, Chroma1-HD)" presets_linked

section "Instance Portal and Caddy (TLS + token auth)"
wait_until 300 "Instance Portal answers on 127.0.0.1:11111" icurl -f http://127.0.0.1:11111/
for port in 1111 7801 8188; do
    wait_until 120 "Caddy serves HTTPS on :$port" icurl -k -o /dev/null https://127.0.0.1:$port/
    noauth=$(icurl -k -o /dev/null -w '%{http_code}' https://127.0.0.1:$port/)
    withauth=$(icurl -k -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" https://127.0.0.1:$port/)
    if [[ "$noauth" == 401 && "$withauth" =~ ^(200|302)$ ]]; then
        pass ":$port refuses anonymous requests ($noauth) and lets the token in ($withauth)"
    else
        fail ":$port anonymous=$noauth with-token=$withauth (want 401 and 200/302)"
    fi
done
code=$(icurl -k -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" https://127.0.0.1:7801/Text2Image)
[[ "$code" == 200 ]] && pass "SwarmUI's Generate page through Caddy (HTTP $code)" || fail "SwarmUI through Caddy returned HTTP $code"
code=$(icurl -k -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" https://127.0.0.1:8188/system_stats)
[[ "$code" == 200 ]] && pass "ComfyUI's API through Caddy (HTTP $code)" || fail "ComfyUI through Caddy returned HTTP $code"

section "Python environment"
if docker exec "$NAME" /venv/main/bin/python -c "import torch, cv2, rembg, ultralytics, dill, imageio_ffmpeg, onnxruntime; print('torch', torch.__version__)"; then
    pass "SwarmUI node dependencies import alongside the base image's torch"
else
    fail "Python imports"
fi

section "end-to-end generation on the CPU (SwarmUI -> ComfyUI, SD 1.5)"
sid=$(swarm GetNewSession '{}' | json 'd["session_id"]')
model=$(swarm ListModels "{\"session_id\": \"$sid\", \"path\": \"\", \"depth\": 3}" \
    | json 'next(f["name"] for f in d["files"] if "v1-5" in f["name"])' 2>/dev/null)
if [[ -z "$model" ]]; then
    fail "SwarmUI does not list the SD 1.5 checkpoint from ComfyUI's checkpoints folder"
else
    pass "SwarmUI lists $model from ComfyUI's models folder"
    start=$SECONDS
    CURL_MAX_TIME=1500 swarm GenerateText2Image "{\"session_id\": \"$sid\", \"images\": 1,
        \"prompt\": \"a red apple on a wooden table, photo\", \"negativeprompt\": \"blurry\",
        \"model\": \"$model\", \"width\": 256, \"height\": 256, \"steps\": 8, \"cfgscale\": 7, \"seed\": 42}" \
        > "$OUT/generate.json"
    cat "$OUT/generate.json"; echo
    img=$(json 'd["images"][0]' < "$OUT/generate.json" 2>/dev/null)
    if [[ -n "$img" && "$img" != data:* ]]; then
        # fetch the result the way a browser would: through Caddy, with the token
        docker exec "$NAME" curl -sk --max-time 60 -H "Authorization: Bearer $TOKEN" \
            -o /tmp/smoke.png "https://127.0.0.1:7801/$img"
        docker cp "$NAME:/tmp/smoke.png" "$OUT/smoke.png" >/dev/null 2>&1
    fi
    if [[ -s "$OUT/smoke.png" ]] && head -c 8 "$OUT/smoke.png" | od -An -tx1 | grep -q '89 50 4e 47 0d 0a 1a 0a'; then
        pass "generated a PNG through SwarmUI's ComfyUI backend in $((SECONDS - start))s ($(stat -c %s "$OUT/smoke.png") bytes)"
    else
        fail "no image came back from GenerateText2Image"
    fi
fi

section "services"
docker exec "$NAME" supervisorctl status | tee "$OUT/supervisor.txt"
for prog in comfyui swarmui caddy instance_portal; do
    grep -qE "^${prog}[[:space:]]+RUNNING" "$OUT/supervisor.txt" && pass "supervisor: $prog RUNNING" \
        || fail "supervisor: $prog not RUNNING"
done

if (( FAILURES > 0 )); then
    diagnostics
    printf '\n%d check(s) failed\n' "$FAILURES"
    exit 1
fi
docker logs "$NAME" > "$OUT/container.log" 2>&1 || true
printf '\nAll checks passed\n'
