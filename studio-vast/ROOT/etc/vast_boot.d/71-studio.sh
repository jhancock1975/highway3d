#!/bin/bash
# Sourced by vast's boot_default.sh before 75-provisioning-manifest.sh. It picks the model
# manifest from STUDIO_MODELS and lays out the studio's folders. Sourced, so never `exit`.
#
#   all   the director LLM, Chroma1-HD, Wan2.2-Remix i2v, ACE-Step and Kokoro (default)
#   none  no model downloads (CI)
#
# An explicit PROVISIONING_MANIFEST still wins.
if [[ -z "${PROVISIONING_MANIFEST:-}" ]]; then
    _studio_set="${STUDIO_MODELS:-all}"
    case "${_studio_set,,}" in
        all|none) _studio_set="${_studio_set,,}" ;;
        *) echo "STUDIO_MODELS='${STUDIO_MODELS}' is not all or none; using all"; _studio_set=all ;;
    esac
    export PROVISIONING_MANIFEST="/opt/studio-vast/provisioning/${_studio_set}.yaml"
    echo "Studio model set '${_studio_set}': provisioning from ${PROVISIONING_MANIFEST}"
    unset _studio_set
fi
. /opt/studio-vast/bin/studio-env.sh
mkdir -p "$STUDIO_MEDIA" "$STUDIO_RENDERS" "$STUDIO_WORK" "$DATA_DIR" "$ACE_HOME/checkpoints" \
         "$(dirname "$STUDIO_LLM_DIR")"
# cartoon writes its films to renders/ in the repo
ln -sfn "$STUDIO_RENDERS" "$STUDIO_ROOT/renders"
[[ -s "$STUDIO_WEBUI/secret" ]] || (umask 077 && openssl rand -hex 32 > "$STUDIO_WEBUI/secret")
