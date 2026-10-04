#!/bin/bash
# vLLM serving the director (Qwen3.8-27B abliterated, quantised to FP8 as it loads) on
# 127.0.0.1:18000 for Open WebUI and lectern's author. Takes 42% of the GPU, leaving about
# 55 GB for ComfyUI, Blender and ACE-Step. Exits cleanly when no model was downloaded
# (STUDIO_MODELS=none).
utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. /opt/studio-vast/bin/studio-env.sh

while [ -f "/.provisioning" ]; do
    echo "$PROC_NAME startup paused until instance provisioning has completed (/.provisioning present)"
    sleep 5
done
if [ ! -f "$STUDIO_LLM_DIR/.complete" ]; then
    echo "No director model at $STUDIO_LLM_DIR (STUDIO_MODELS=none, or its download failed); vLLM not started."
    sleep 6
    exit 0
fi
export VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
pty /opt/vllm/bin/vllm serve "$STUDIO_LLM_DIR" --served-model-name "$STUDIO_LLM_NAME" \
    --host 127.0.0.1 --port 18000 \
    --quantization fp8 --kv-cache-dtype fp8 --max-model-len "${VLLM_MAX_MODEL_LEN:-65536}" --max-num-seqs 8 \
    --gpu-memory-utilization "${VLLM_GPU_UTIL:-0.42}" --language-model-only \
    --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 \
    --speculative-config '{"method":"mtp","num_speculative_tokens":3}' ${VLLM_EXTRA_ARGS:-}
