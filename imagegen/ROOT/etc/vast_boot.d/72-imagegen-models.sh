#!/bin/bash
# Sourced by vast's boot_default.sh just before 75-provisioning-manifest.sh runs the
# provisioner. Turns IMAGEGEN_MODELS into the manifest the provisioner should use:
#
#   all     Kroma v0.3 turbo and Chroma1-HD, with their text encoders and VAEs (default)
#   kroma   only the Kroma set
#   chroma  only the Chroma1-HD set
#   none    no model downloads
#
# An explicit PROVISIONING_MANIFEST always wins, so a template can still point at its
# own manifest. Provisioning runs once per instance; see the README for adding a model
# set later.

if [[ -z "${PROVISIONING_MANIFEST:-}" ]]; then
    _imagegen_set="${IMAGEGEN_MODELS:-all}"
    case "${_imagegen_set,,}" in
        all|kroma|chroma|none) _imagegen_set="${_imagegen_set,,}" ;;
        *)
            echo "IMAGEGEN_MODELS='${IMAGEGEN_MODELS}' is not one of all, kroma, chroma, none; using all"
            _imagegen_set=all
            ;;
    esac
    export PROVISIONING_MANIFEST="/opt/imagegen/provisioning/${_imagegen_set}.yaml"
    echo "Model set '${_imagegen_set}': provisioning from ${PROVISIONING_MANIFEST}"
    unset _imagegen_set
fi
