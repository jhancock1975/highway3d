# The studio: an uncensored director LLM (vLLM) that you chat with in Open WebUI, painting with
# Chroma1-HD and animating with Wan2.2-Remix through ComfyUI, and voicing, scoring and cutting
# with the renderers in this repo (studio, cartoon, lectern, highway3d), which all run in here.
# Built FROM vast's maintained ComfyUI image, so vast hosts already hold most of its layers.
# No model weights are in the image: studio-vast/ROOT/opt/studio-vast/provisioning fetches
# them on first boot.
#
# Build context: the repository root.
#   docker buildx build . -f studio-vast/Dockerfile
ARG BASE_IMAGE=vastai/comfy:v0.38.0-cuda-12.9-py312
FROM ${BASE_IMAGE}

ARG SOURCE_URL=https://github.com/jhancock1975/highway3d
LABEL org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.title="studio-vast" \
      org.opencontainers.image.description="An uncensored film studio you talk to: vLLM + Open WebUI directing ComfyUI (Chroma1-HD, Wan2.2-Remix), Kokoro, ACE-Step, Blender and ffmpeg" \
      maintainer="jhancock1975"

# Blender's USD library needs libSM/libICE, which vast's base lacks; libXt/libOpenGL are for its
# GLSL MaterialX libraries. TeX for Manim's notation: everything lectern and cartoon typeset with,
# except doublestroke, which comes from CTAN (193 KB rather than texlive-fonts-extra's 1.7 GB).
# The EGL vendor file lets Blender's headless EEVEE find NVIDIA's EGL instead of falling back
# to Mesa's software renderer. CTAN's own redirector picks a random mirror, and some of those
# have broken certificates, so doublestroke comes from a fixed list of mirrors, checked by hash.
ARG DOUBLESTROKE_SHA256=6131360ec181ff62a2fba00fb8ad0bc0dda1c628b94f304db1a7617bde35949a
RUN set -euo pipefail && \
    apt-get update && \
    apt-get install -y --no-install-recommends libsm6 libice6 libxt6t64 libopengl0 xz-utils unzip \
        texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
        texlive-science tipa dvisvgm libcairo2-dev libpango1.0-dev pkg-config && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    for m in https://mirrors.mit.edu/CTAN https://ctan.math.illinois.edu https://ftp.fau.de/ctan \
             https://mirror.las.iastate.edu/tex-archive; do \
        curl -fsSL --retry 3 "$m/install/fonts/doublestroke.tds.zip" -o /tmp/doublestroke.zip && \
        echo "${DOUBLESTROKE_SHA256}  /tmp/doublestroke.zip" | sha256sum -c - && break; \
        rm -f /tmp/doublestroke.zip; \
    done && test -s /tmp/doublestroke.zip && \
    mkdir -p /usr/local/share/texmf && unzip -q /tmp/doublestroke.zip -d /usr/local/share/texmf && \
    rm /tmp/doublestroke.zip && mktexlsr && kpsewhich dsfont.sty && \
    mkdir -p /usr/share/glvnd/egl_vendor.d && \
    printf '{"file_format_version" : "1.0.0","ICD": {"library_path": "libEGL_nvidia.so.0"}}\n' \
        > /usr/share/glvnd/egl_vendor.d/10_nvidia.json

# Blender 5.2 LTS, which the renderers are tested on (EEVEE Next is "BLENDER_EEVEE" from 5.0).
ARG BLENDER_URL=https://download.blender.org/release/Blender5.2/blender-5.2.2-linux-x64.tar.xz
ARG BLENDER_SHA256=84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168
RUN set -euo pipefail && \
    curl -fsSL "${BLENDER_URL}" -o /tmp/blender.tar.xz && \
    echo "${BLENDER_SHA256}  /tmp/blender.tar.xz" | sha256sum -c - && \
    mkdir -p /opt/blender && tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 && \
    rm /tmp/blender.tar.xz && ln -sf /opt/blender/blender /usr/local/bin/blender && \
    blender -b --factory-startup --python-expr "import bpy; print('BLENDER_OK', bpy.app.version_string)" \
        | grep BLENDER_OK

# GIMP 3.2 draws the studio's cards and captions. Ubuntu 24.04 only has 2.10, so the official
# AppImage is unpacked, with a console copy of its AppRun. Its programs must start from the
# AppDir, because their loader path is relative to it.
ARG GIMP_URL=https://download.gimp.org/gimp/v3.2/linux/GIMP-3.2.6-x86_64.AppImage
ARG GIMP_SHA256=79ea41bc9b06f78fda181849a9ca8e42d83f1124dedb756f4d52352e2465010f
RUN set -euo pipefail && \
    curl -fsSL "${GIMP_URL}" -o /tmp/gimp.AppImage && \
    echo "${GIMP_SHA256}  /tmp/gimp.AppImage" | sha256sum -c - && \
    chmod +x /tmp/gimp.AppImage && cd /opt && /tmp/gimp.AppImage --appimage-extract >/dev/null && \
    mv squashfs-root gimp && rm /tmp/gimp.AppImage && \
    sed 's#exec "$APPDIR"/usr/bin/org.gimp.GIMP.Stable#exec "$APPDIR"/usr/bin/gimp-console-3.2#' \
        gimp/AppRun > gimp/AppRun-console && \
    chmod +x gimp/AppRun-console && grep -q gimp-console-3.2 gimp/AppRun-console && \
    /opt/gimp/AppRun-console --version

# vLLM 0.30 for the director, in its own venv with its own torch. The cu129 build: PyPI's
# default is CUDA 13, which needs a newer driver than many vast hosts run. sm_120 (Blackwell)
# is in the build.
RUN set -euo pipefail && \
    uv venv --python /usr/bin/python3.12 /opt/vllm && \
    VIRTUAL_ENV=/opt/vllm uv pip install --no-cache --torch-backend cu129 \
        "https://github.com/vllm-project/vllm/releases/download/v0.30.0/vllm-0.30.0%2Bcu129-cp38-abi3-manylinux_2_28_x86_64.whl" && \
    /opt/vllm/bin/python -c "import vllm, torch; print('VLLM_OK', vllm.__version__, torch.__version__)"

# Open WebUI 0.11.4 for the chat. CPU torch is enough for its own embeddings, which are not
# used here.
RUN set -euo pipefail && \
    uv venv --python /usr/bin/python3.12 /opt/openwebui && \
    VIRTUAL_ENV=/opt/openwebui uv pip install --no-cache --torch-backend cpu "open-webui==0.11.4" && \
    /opt/openwebui/bin/python -c "import open_webui; print('OWUI_OK')"

# The venvs the repo's tools expect, by the names its code uses. They are built before the
# repo is copied in, so a change to the code does not rebuild them (the build context leaves
# every venv out, so the copy keeps these):
#  - one shared venv for the MCP servers and the plain tools, linked under each tool's name;
#  - .ttsvenv (Kokoro) and lectern/.musicvenv (ACE-Step) on top of /venv/main's CUDA torch,
#    which is pinned so nothing replaces it. The pin (torch==2.10.0+cu128) only resolves with
#    PyTorch's own index in reach; PyPI has no +cu128 builds. transformers and huggingface_hub
#    are pinned to the Mac's working Kokoro venv: left free, huggingface_hub 2.x drags
#    transformers back to 4.12, whose tokenizers needs Rust to build. torchcodec must match
#    torch's release (0.10 for 2.10).
#  - lectern/.manimvenv: manimpango has no Linux wheel for Python 3.12 and builds from source
#    against the pango/cairo headers installed above. ACE-Step is installed from a checkout because its
#    nano-vllm dependency is a folder inside its own repo;
#  - lectern/.manimvenv for Manim.
RUN set -euo pipefail && mkdir -p /opt/highway3d/studio /opt/highway3d/cartoon /opt/highway3d/lectern \
        /opt/highway3d/highway3d /opt/highway3d/highway && cd /opt/highway3d && \
    uv venv --python /usr/bin/python3.12 /opt/venvs/tools && \
    VIRTUAL_ENV=/opt/venvs/tools uv pip install --no-cache "mcp==2.2.0" numpy pillow pyyaml soundfile \
        fonttools scipy scikit-image imageio matplotlib websocket-client anyio uvicorn && \
    for d in studio/.venv cartoon/.venv lectern/.mcpvenv highway3d/.mcpvenv highway/.venv; do \
        ln -sfn /opt/venvs/tools "/opt/highway3d/$d"; done && \
    /venv/main/bin/python -m pip list --format=freeze 2>/dev/null \
        | grep -E '^(torch|torchvision|torchaudio)==' | sort > /tmp/torch-pins.txt && cat /tmp/torch-pins.txt && \
    uv venv --python /venv/main/bin/python --system-site-packages .ttsvenv && \
    VIRTUAL_ENV=/opt/highway3d/.ttsvenv uv pip install --no-cache -c /tmp/torch-pins.txt \
        --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match \
        "kokoro==0.9.4" "misaki[en]==0.9.4" "transformers==5.17.0" "huggingface_hub==1.32.0" soundfile pyyaml \
        "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl" && \
    .ttsvenv/bin/python -c "import kokoro, spacy, torch; spacy.load('en_core_web_sm'); print('TTS_OK', torch.__version__)" && \
    git clone --quiet https://github.com/ACE-Step/ACE-Step-1.5 /opt/ace-step && \
    git -C /opt/ace-step checkout --quiet --detach ca1e85fe9430179831e6bc6be790c332190a3866 && \
    uv venv --python /venv/main/bin/python --system-site-packages lectern/.musicvenv && \
    VIRTUAL_ENV=/opt/highway3d/lectern/.musicvenv uv pip install --no-cache -c /tmp/torch-pins.txt \
        --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match \
        /opt/ace-step/acestep/third_parts/nano-vllm /opt/ace-step "torchcodec==0.10.0" soundfile && \
    lectern/.musicvenv/bin/python -c "import acestep.handler, acestep.inference, acestep.llm_inference, torch; print('ACE_OK', torch.__version__)" && \
    uv venv --python /usr/bin/python3.12 lectern/.manimvenv && \
    VIRTUAL_ENV=/opt/highway3d/lectern/.manimvenv uv pip install --no-cache "manim==0.21.0" "manimpango==0.6.1" numpy pillow scipy pyyaml && \
    lectern/.manimvenv/bin/python -c "import manim; print('MANIM_OK', manim.__version__)" && \
    rm -f /tmp/torch-pins.txt

COPY . /opt/highway3d
COPY studio-vast/ROOT/ /

# Fonts, the Kenney cars and the Poly Haven assets the renderers fetch on first use, fetched now.
# (highway3d/setup.sh does the cars too, but ends with a Blender render, which is the smoke test's job.)
RUN set -euo pipefail && cd /opt/highway3d && \
    /opt/venvs/tools/bin/python fonts.py && \
    /opt/venvs/tools/bin/python -m cartoon.assets && \
    mkdir -p assets/cars/kenney && \
    url=$(curl -fsS --max-time 30 https://kenney.nl/assets/car-kit | grep -oiE 'https?://[^"]*kenney_car-kit\.zip' | head -1) && \
    curl -fsSL --max-time 300 -o /tmp/kenney.zip "$url" && unzip -oq /tmp/kenney.zip -d assets/cars/kenney && rm /tmp/kenney.zip && \
    test "$(find assets/cars/kenney -iname '*.glb' | wc -l)" -ge 20

RUN set -euo pipefail && \
    chmod +x /opt/supervisor-scripts/vllm.sh /opt/supervisor-scripts/openwebui.sh \
             /opt/supervisor-scripts/studio-mcp.sh /opt/studio-vast/bin/owui-setup.py && \
    cp /opt/studio-vast/provisioning/all.yaml /provisioning.yaml

# Instance Portal entries. External port != internal port, so Caddy fronts each app with TLS and
# the Open-button token; the apps listen only on 127.0.0.1. The Open button goes straight to the chat.
ENV PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8081:18081:/:Studio Chat|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter" \
    OPEN_BUTTON_PORT=8081 \
    ENABLE_HTTPS=true \
    STUDIO_MODELS=all

EXPOSE 1111 8081 8188 8080

# vast's derivatives all end with this; it guards against stale environments when a workspace
# volume is reused with a different image.
RUN env-hash > /.env_hash
