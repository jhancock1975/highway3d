# SwarmUI in front of vast.ai's own ComfyUI image, for running Kroma v0.3 turbo and
# Chroma1-HD on a rented GPU. No model weights live in the image: the provisioning
# manifests in ROOT/opt/imagegen/provisioning fetch them on first boot.
#
# Building FROM vast's maintained ComfyUI image means vast hosts usually already hold
# its ~10 GB of layers, so an instance only has to pull the few layers added here.
ARG BASE_IMAGE=vastai/comfy:v0.38.0-cuda-12.9-py312

FROM ${BASE_IMAGE}

# SwarmUI master as of 2026-10-01. Krea 2 support landed in June 2026, Chroma long before.
ARG SWARMUI_REF=d9ecb52dfd4e147c4f2dc90440331e8dea4036a7
ARG SOURCE_URL=https://github.com/jhancock1975/highway3d

LABEL org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.title="imagegen-vast" \
      org.opencontainers.image.description="SwarmUI and ComfyUI for vast.ai, fetching Kroma v0.3 turbo and Chroma1-HD on first boot" \
      org.opencontainers.image.version="swarmui-${SWARMUI_REF}" \
      maintainer="jhancock1975"

# .NET SDKs for SwarmUI: 8.0, which this SwarmUI commit targets, and 10.0, which SwarmUI
# asks for at startup because upcoming versions move to it (its own Linux installer puts
# both in). The SDKs carry the ASP.NET runtimes SwarmUI needs, and keeping SDKs rather
# than bare runtimes lets SwarmUI rebuild itself after an update on a live instance.
ENV DOTNET_ROOT=/opt/dotnet \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_NOLOGO=1 \
    DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
RUN set -euo pipefail && \
    curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh && \
    bash /tmp/dotnet-install.sh --channel 10.0 --install-dir "${DOTNET_ROOT}" && \
    bash /tmp/dotnet-install.sh --channel 8.0 --install-dir "${DOTNET_ROOT}" && \
    ln -sf "${DOTNET_ROOT}/dotnet" /usr/local/bin/dotnet && \
    rm -f /tmp/dotnet-install.sh && \
    dotnet --list-sdks && \
    dotnet --list-runtimes

# SwarmUI, built now so the first boot does not spend minutes compiling. It goes into
# /opt/workspace-internal so it is copied to /workspace on first boot like ComfyUI is.
# Writing src/bin/last_build is what stops launch-linux.sh from rebuilding on start.
RUN set -euo pipefail && \
    git clone https://github.com/mcmonkeyprojects/SwarmUI /opt/workspace-internal/SwarmUI && \
    cd /opt/workspace-internal/SwarmUI && \
    git checkout --detach "${SWARMUI_REF}" && \
    dotnet build src/SwarmUI.csproj --configuration Release -o ./src/bin/live_release && \
    git rev-parse HEAD > src/bin/last_build && \
    rm -rf src/obj /root/.nuget /root/.local/share/NuGet /tmp/NuGetScratch* && \
    test -f src/bin/live_release/SwarmUI.dll

# SwarmUI drives ComfyUI through its own custom nodes (its sampler, its prompt encoder
# for Krea 2, its websocket image output...). With a "ComfyUI API By URL" backend they
# have to be installed into ComfyUI by hand, which is this step, along with the Python
# packages they import. The torch family is pinned to whatever the base image ships so
# nothing here can swap the CUDA build of torch out from under ComfyUI.
# ultralytics stays at the version SwarmUI itself pins (it avoids the compromised 8.3.41).
RUN set -euo pipefail && \
    apt-get update && \
    apt-get install -y --no-install-recommends libgl1 libglib2.0-0t64 && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    . /venv/main/bin/activate && \
    pip list --format=freeze 2>/dev/null | grep -E '^(torch|torchvision|torchaudio|torchcodec)==' | sort > /tmp/torch-pins.txt && \
    cat /tmp/torch-pins.txt && \
    uv pip install --no-cache-dir -c /tmp/torch-pins.txt \
        rembg onnxruntime dill "ultralytics==8.3.197" imageio-ffmpeg omegaconf \
        opencv-python-headless matplotlib && \
    pip list --format=freeze 2>/dev/null | grep -E '^(torch|torchvision|torchaudio|torchcodec)==' | sort | diff /tmp/torch-pins.txt - && \
    rm -f /tmp/torch-pins.txt && \
    python -c "import cv2, rembg, ultralytics, dill, imageio_ffmpeg, onnxruntime, av" && \
    for pack in SwarmComfyCommon SwarmComfyExtra; do \
        cp -r "/opt/workspace-internal/SwarmUI/src/BuiltinExtensions/ComfyUIBackend/ExtraNodes/${pack}" \
              /opt/workspace-internal/ComfyUI/custom_nodes/; \
    done && \
    cd /opt/workspace-internal/ComfyUI && \
    LD_PRELOAD=libtcmalloc_minimal.so.4 python main.py --cpu --listen 127.0.0.1 --port 11404 \
        --disable-auto-launch --quick-test-for-ci 2>&1 | tee /tmp/comfy-quick-test.log && \
    if grep -E 'IMPORT FAILED.*Swarm' /tmp/comfy-quick-test.log; then \
        echo "SwarmUI's ComfyUI nodes failed to import"; exit 1; \
    fi && \
    rm -f /tmp/comfy-quick-test.log

COPY ROOT/ /

# Pre-written SwarmUI settings (no installer wizard, models read from ComfyUI's folders,
# one backend pointing at the ComfyUI vast already runs), and the default manifest.
RUN set -euo pipefail && \
    chmod +x /opt/supervisor-scripts/swarmui.sh /opt/imagegen/bin/* && \
    mkdir -p /opt/workspace-internal/SwarmUI/Data && \
    cp /opt/imagegen/swarmui/Settings.fds /opt/imagegen/swarmui/Backends.fds \
       /opt/workspace-internal/SwarmUI/Data/ && \
    cp /opt/imagegen/provisioning/all.yaml /provisioning.yaml

# Instance Portal entries. External port != internal port, so Caddy fronts each app with
# TLS and the Open-button token; the apps themselves only listen on 127.0.0.1.
ENV PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:7801:17801:/:SwarmUI|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter" \
    OPEN_BUTTON_PORT=1111 \
    ENABLE_HTTPS=true \
    IMAGEGEN_MODELS=all \
    SWARMUI_ARGS="--launch_mode none --host 127.0.0.1 --port 17801"

EXPOSE 1111 7801 8188 8080

# vast's derivatives all finish with this; it guards against stale environments when
# a workspace volume is reused with a different image.
RUN env-hash > /.env_hash
