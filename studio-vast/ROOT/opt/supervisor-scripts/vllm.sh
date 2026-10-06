#!/bin/bash
# vLLM serving the director (Qwen3.8-27B abliterated, quantised to FP8 as it loads) on
# 127.0.0.1:18000 for Open WebUI and lectern's author. Takes about 40 GB of a single GPU (the
# share gpu-plan.py works out, VLLM_GPU_UTIL), or GPU 0 to itself when there are more. Exits
# cleanly when there is no model (STUDIO_MODELS=none, or its download gave up).
utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. /opt/studio-vast/bin/studio-env.sh

# The director downloads in studio-models, beside the rest of provisioning; start as soon as it's in.
if [[ "${STUDIO_MODELS:-all}" == none ]]; then
    echo "No director model (STUDIO_MODELS=none); vLLM not started."
    sleep 6
    exit 0
fi
while [ ! -f "$STUDIO_LLM_DIR/.complete" ]; do
    if [ -f "$STUDIO_LLM_DIR/.failed" ]; then
        echo "The director's model did not download ($(cat "$STUDIO_LLM_DIR/.failed")); vLLM not started. See /var/log/portal/studio-models.log."
        sleep 6
        exit 0
    fi
    echo "$PROC_NAME waiting for the director's model to download (/var/log/portal/studio-models.log)"
    sleep 15
done
# With two or more GPUs, vLLM has GPU 0 to itself (gpu-plan.py).
[ "${STUDIO_GPU_COUNT:-1}" -ge 2 ] 2>/dev/null && export CUDA_VISIBLE_DEVICES="$STUDIO_LLM_GPU"
export VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1 PYTHONUNBUFFERED=1
# No pty wrapper: it reported a crashed vLLM as a clean exit, so supervisor never restarted it.
/opt/vllm/bin/vllm serve "$STUDIO_LLM_DIR" --served-model-name "$STUDIO_LLM_NAME" \
    --host 127.0.0.1 --port 18000 \
    --quantization fp8 --kv-cache-dtype fp8 --max-model-len "${VLLM_MAX_MODEL_LEN:-65536}" --max-num-seqs 8 \
    --gpu-memory-utilization "${VLLM_GPU_UTIL:-0.42}" --language-model-only \
    --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 \
    --speculative-config '{"method":"mtp","num_speculative_tokens":3}' ${VLLM_EXTRA_ARGS:-}
exit $?
