# imagegen-vast

A Docker image for renting a GPU on vast.ai and generating images with uncensored
open-weight models from a browser. It is vast's own ComfyUI image with
[SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI) added on top as the friendly front
end. Both UIs use the same ComfyUI process, the same GPU and the same models folder.

No model weights are in the image. On first boot the instance downloads them from
Hugging Face (no token needed) into `/workspace/ComfyUI/models`.

Image: `ghcr.io/jhancock1975/imagegen-vast:latest` (every build is also tagged with its
7-character commit, e.g. `ghcr.io/jhancock1975/imagegen-vast:1a2b3c4`; use one of those to
pin a version).

## The models

| Model | What it is | Download | Licence |
|---|---|---|---|
| **Kroma v0.3 turbo** | lodestones' full fine-tune of Krea 2 (a 13B DiT). Krea 2 is currently the strongest open image model, but its base is censored; Kroma removes that. The Krea 2 Turbo distillation is merged in, so 8 steps is enough. | 34.77 GB (model 25.64 GB bf16, Qwen3-VL 4B text encoder 8.88 GB bf16, QwenImage VAE 0.25 GB) | Krea 2 Community License (see below) |
| **Chroma1-HD** | lodestones' 8.9B model based on FLUX.1-schnell, deliberately trained without safety alignment. Older and slower than Kroma (26 steps with real CFG), but mature, well understood and Apache-2.0. | 27.92 GB (model 17.80 GB bf16, T5-XXL encoder 9.79 GB fp16, FLUX VAE 0.34 GB) | Apache-2.0 |

Both are downloaded at full precision because the recommended GPU has room for it.
Total: 62.69 GB.

Sources (all pinned to a repo commit in the manifests):

- `lodestones/Kroma` → `kroma-v0.3-turbo.safetensors`
- `Comfy-Org/Krea-2` → `text_encoders/qwen3vl_4b_bf16.safetensors`, `vae/qwen_image_vae.safetensors`
  (Comfy-Org's ungated repackage; Krea's own repo needs a login)
- `lodestones/Chroma1-HD` → `Chroma1-HD.safetensors`
- `comfyanonymous/flux_text_encoders` → `t5xxl_fp16.safetensors`
- `Comfy-Org/Lumina_Image_2.0_Repackaged` → `split_files/vae/ae.safetensors` (the FLUX.1 VAE)

Four of these are saved under the names SwarmUI looks for
(`text_encoders/qwen3vl_4b.safetensors`, `text_encoders/t5xxl_enconly.safetensors`,
`vae/QwenImage/...`, `vae/Flux/ae.safetensors`), so SwarmUI uses them instead of quietly
downloading its own smaller fp8 copies the first time you generate.

### Licences

- **Kroma** is a derivative of Krea 2, so the
  [Krea 2 Community License](https://huggingface.co/Comfy-Org/Krea-2/blob/main/LICENSE.pdf)
  applies. The Kroma model card body says "MIT", but its licence metadata says
  `krea-2-community-license`, and the card itself says the fine-tune grants no rights to
  the Krea 2 base weights; treat the Krea licence as the one that binds. (The card text
  also still describes v0.2; v0.3 files were added later without a card update.) Two
  terms worth knowing: commercial use is only allowed if your total annual revenue is
  under US$1M, and section 4.2 asks anyone deploying the model to put "reasonable and
  appropriate" content filters in front of it. This image adds no filter.
- **Chroma1-HD**, the T5-XXL encoder and the FLUX VAE are Apache-2.0. The Krea 2 text
  encoder and VAE come from the Krea 2 repackage and fall under the Krea licence too
  (Qwen3-VL and the QwenImage VAE are themselves Apache-2.0).
- SwarmUI is MIT, ComfyUI is GPL-3.0, vast's base image has its own licence.

What's legal: every one of these licences (and the law) forbids sexual content involving
minors and non-consensual sexual imagery of real people.

## Launching on vast.ai

Create a template (Templates → New) with:

| Field | Value |
|---|---|
| Image Path:Tag | `ghcr.io/jhancock1975/imagegen-vast:latest` |
| Launch mode | **Jupyter-python notebook + SSH** (tick "Use direct HTTPS"). This is how vast runs its own ComfyUI template. |
| On-start script | `entrypoint.sh` |
| Docker options | `-p 1111:1111 -p 7801:7801 -p 8188:8188 -p 8080:8080` |
| Disk space | **150 GB** |

Environment variables (add them in the template's env section, or append each as
`-e NAME=value` to the Docker options):

| Variable | Value | Why |
|---|---|---|
| `PORTAL_CONFIG` | `localhost:1111:11111:/:Instance Portal\|localhost:7801:17801:/:SwarmUI\|localhost:8188:18188:/:ComfyUI\|localhost:8080:18080:/:Jupyter` | Which apps the Instance Portal and its proxy serve. Already the image default; setting it in the template makes it visible and editable. |
| `OPEN_BUTTON_PORT` | `1111` | The Open button lands on the Instance Portal. |
| `OPEN_BUTTON_TOKEN` | `1` | Tells vast to generate the login token the Open button uses. |
| `IMAGEGEN_MODELS` | `all` | `all`, `kroma`, `chroma` or `none`. Picks what is downloaded on first boot. |
| `JUPYTER_DIR` | `/` | Same as vast's ComfyUI template. |

Optional: `ENABLE_HTTPS` is `true` in the image; set it to `false` only if you want plain
HTTP. `HF_TOKEN` is not needed. `PROVISIONING_DOWNLOADS` adds your own files on first
boot, e.g. a LoRA:
`https://huggingface.co/org/repo/resolve/main/x.safetensors|/workspace/ComfyUI/models/loras/x.safetensors`
(separate several with `;`).

Leave authentication on (it is on by default). Each app's port is served by vast's Caddy
proxy with TLS, and only the Open button's cookie, a `Bearer` token or the
`vastai` / token basic-auth login gets through. The apps themselves only listen on
127.0.0.1. vast's portal also opens a trycloudflare.com link per app (listed in the
portal's Tunnels tab); those go through the same login.

### Which machine to rent

- **GPU: one 48 GB card** — RTX A6000, A40, L40S or RTX 6000 Ada. Kroma at full bf16
  precision needs about 26 GB of VRAM for its weights plus room to work; 48 GB runs it
  without compromises and Chroma1-HD comfortably.
- **Disk: 150 GB.** The image unpacks to roughly 30 GB, the models are 63 GB, and
  downloads briefly need scratch space; the rest is room for outputs.
- **CUDA: max CUDA 12.8 or newer** in vast's filters (the image is built on CUDA 12.9,
  PyTorch 2.10).
- **RAM: 64 GB or more** system memory, since ComfyUI parks the text encoders in RAM
  between generations. Fast download speed (500 Mbps+) shortens first boot a lot.

**Smaller cards.** On a 32 GB RTX 5090, Kroma's 25.6 GB of bf16 weights leave too little
headroom, so load it in fp8 instead: in SwarmUI's Generate tab, open the "Kroma turbo"
preset's parameters (Advanced Sampling → Preferred DType) and set it to FP8 e4m3fn, or
just untick it (SwarmUI then picks fp8 for Krea 2 on its own). That halves Kroma to about
13 GB at a small cost in fine detail. Chroma1-HD (17.8 GB) fits a 32 GB card as is. On
24 GB cards (RTX 4090/3090) use fp8 for both. Same downloads and disk either way.

### First boot

1. vast pulls the image. When the host already has vast's ComfyUI image cached (common),
   only the ~1.2 GB of layers added here download; otherwise about 12 GB.
2. The provisioner downloads the models (62.7 GB with `IMAGEGEN_MODELS=all`, three files
   at a time). Expect roughly 10 minutes on a fast (1 Gbps+) host and 20-30 minutes on a
   500 Mbps one; about half that for `kroma` or `chroma` alone.
3. ComfyUI and SwarmUI start once the downloads finish. Until then the Instance Portal is
   up, and its **Logs** tab (`provisioning.log`) shows the download progress.

Everything lives under `/workspace`, so stopping and restarting the instance keeps the
models, settings and images. Provisioning only runs once per instance.

## Using it

Click **Open** on the instance card. That logs you in and shows the Instance Portal; click
**SwarmUI** there (or ComfyUI for the node editor). You can also go straight to the
public address vast maps to port 7801.

With `ENABLE_HTTPS=true` the browser will warn about the certificate unless you have
installed vast's certificate once (see vast's "Instance Portal" / Jupyter certificate
docs); accepting the warning also works.

In SwarmUI's **Generate** tab, pick a model in the Models list. Each model has a preset
linked to it that switches on when you select the model:

| Model | Preset | Steps | CFG | Sigma shift | Other |
|---|---|---|---|---|---|
| `kroma-v0.3-turbo` | Kroma turbo | 8 | 1 | 1.15 | Preferred DType: Default (16-bit), otherwise SwarmUI would load it in fp8 |
| `Chroma1-HD` | Chroma1-HD | 26 | 3.8 | 1 | euler sampler, beta scheduler (SwarmUI's own Chroma defaults) |

Kroma's model card allows 8-12 steps and CFG 1.0-1.5. Chroma likes long, descriptive
prompts and a negative prompt, e.g. "low quality, blurry, deformed, watermark". Both are
trained around 1024×1024; Chroma1-HD also did extra training at 1152×1152.

Images are saved in `/workspace/SwarmUI/Output/local/raw/<date>/` (and ComfyUI's own in
`/workspace/ComfyUI/output`). Jupyter's file browser can download them.

**Adding a model set later.** If you started with `kroma` and want Chroma too, open a
terminal (Jupyter → New → Terminal, or SSH) and run
`provisioner /opt/imagegen/provisioning/chroma.yaml`, then refresh the model list in
SwarmUI. Any other model can simply be dropped into the matching folder under
`/workspace/ComfyUI/models`.

**Restarting a service:** `supervisorctl restart swarmui` or `supervisorctl restart comfyui`.

## How it is put together

- `Dockerfile` — `FROM vastai/comfy:v0.38.0-cuda-12.9-py312` (ComfyUI v0.38.0, which has
  native Krea 2 support). Adds the .NET 8 and 10 SDKs, SwarmUI at commit `d9ecb52` (built at image
  build time), SwarmUI's ComfyUI nodes (`SwarmComfyCommon`, `SwarmComfyExtra`) and their
  Python packages. Nothing in the base image is modified, so its layers keep vast's
  digests and vast hosts that have them cached skip them.
- `ROOT/opt/imagegen/swarmui/` — SwarmUI's `Settings.fds` (installer already done, models
  read from ComfyUI's folders, listens on 127.0.0.1:17801, output under `/workspace`) and
  `Backends.fds` (one "ComfyUI API By URL" backend at http://127.0.0.1:18188).
- `ROOT/opt/supervisor-scripts/swarmui.sh` and `ROOT/etc/supervisor/conf.d/swarmui.conf` —
  the SwarmUI service, following vast's pattern (waits for provisioning, logs to the
  portal). `ROOT/opt/imagegen/bin/swarmui-defaults.py` adds the per-model presets on first
  boot.
- `ROOT/opt/imagegen/provisioning/*.yaml` — vast provisioning manifests, one per model set.
  `ROOT/etc/vast_boot.d/72-imagegen-models.sh` picks one from `IMAGEGEN_MODELS`;
  `all.yaml` is also baked in as `/provisioning.yaml`.
- `ROOT/etc/vast_agents/imagegen.md` — notes for AI agents working on the instance,
  including how to generate through SwarmUI's HTTP API.

To update SwarmUI or the base image, change `SWARMUI_REF` or `BASE_IMAGE` in the
Dockerfile and push.

### What CI checks

`.github/workflows/imagegen.yml` runs on every push that touches `imagegen/`:

1. HEAD-requests every model URL with no token and fails unless each ends in a 200 with a
   real file size; checks the manifests agree with each other.
2. Builds the image and pushes it as `:<short sha>`, then checks the base layers kept vast's
   digests.
3. Boots it on the CPU runner the way vast does (entrypoint, supervisor, Instance Portal,
   Caddy with TLS, provisioning with `IMAGEGEN_MODELS=none`, ComfyUI with `--cpu`; only the
   portal's public quick tunnels are switched off) and checks:
   ComfyUI answers on 18188 with SwarmUI's nodes loaded and Krea 2 / Chroma support;
   SwarmUI answers on 17801 with no install wizard; SwarmUI's API reports its ComfyUI
   backend as running; the per-model presets exist and are linked; Caddy refuses anonymous
   requests and lets the token through on 1111, 7801 and 8188; every manifest passes the
   provisioner's dry run; and a real image is generated through SwarmUI → ComfyUI on the CPU
   with the small SD 1.5 checkpoint vast's image ships with.
4. Only then moves `:latest` to the new build.

What CI cannot check is a real Kroma or Chroma generation, which needs a GPU.
