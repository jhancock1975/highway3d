#!/bin/bash
# The studio's own model downloads, started at boot beside vast's provisioning rather than after
# it: the director first, since the chat needs it before anything else, then ACE-Step. Each one
# is restarted when it stalls (studio-fetch.py). vLLM waits for the director's .complete.
utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. /opt/studio-vast/bin/studio-env.sh

if [[ "${STUDIO_MODELS:-all}" == none ]]; then
    echo "STUDIO_MODELS=none: no studio model downloads."
    sleep 6     # let the log copier pick the line up before this exits, as vllm.sh does
    exit 0
fi
FETCH=/opt/studio-vast/bin/studio-fetch.py
/usr/bin/python3 "$FETCH" huihui-ai/Huihui-Qwen3.8-27B-abliterated 739e3c5b89849f6c238ce1e5b70008612ae42cdd \
    "$STUDIO_LLM_DIR"
llm=$?
/usr/bin/python3 "$FETCH" ACE-Step/Ace-Step1.5 19671f406d603126926c1b7e2adc169acbcade22 "$ACE_HOME/checkpoints"
ace=$?
exit $(( llm || ace ))
