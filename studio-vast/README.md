# studio-vast

A Docker image for renting one GPU on vast.ai and making short films by talking to a
director. You describe a scene in the browser; an uncensored LLM plans the shots, has an
uncensored image model paint keyframes for you to choose from, animates the chosen frames,
carries clips on into longer shots, voices the dialog, scores it, and cuts it all together.
Progress shows in the chat while renders run, and pictures, clips and the finished film
play inline.

Everything runs on the rented machine. Nothing calls back to a Mac, and no paid API is
involved. Every renderer in this repo is in the image too (studio, cartoon, lectern,
highway3d, highway, relativity), with the Linux builds of the tools they need.

Image: `ghcr.io/jhancock1975/studio-vast:latest`, public, built FROM vast's ComfyUI image
(`vastai/comfy:v0.38.0-cuda-12.9-py312`) so vast hosts already hold most of its layers.
Every build is also tagged with its 7-character commit; `:latest` only moves after a build
passes the checks described at the end.

## What runs

| Service | What it is | Address in the container | Instance Portal |
|---|---|---|---|
| **Studio Chat** | Open WebUI 0.11.4: the conversation, live progress, inline media | `127.0.0.1:18081` | port 8081 (the Open button goes here) |
| Director LLM | vLLM 0.30 serving `studio-llm` (OpenAI API, native tool calls) | `127.0.0.1:18000` | not exposed |
| ComfyUI | keyframes and animation | `127.0.0.1:18188` | port 8188 |
| studio MCP | pictures, animation, extension, voices, music, cards, the cut | `http://127.0.0.1:8768/mcp` | not exposed |
| cartoon MCP | 3D cartoons from a screenplay (Blender) | `http://127.0.0.1:8769/mcp` | not exposed |
| lectern MCP | narrated lecture videos (Blender, Manim) | `http://127.0.0.1:8767/mcp` | not exposed |
| highway3d MCP | highway-driving footage (Blender) | `http://127.0.0.1:8766/mcp` | not exposed |
| Jupyter | a terminal and file browser | `127.0.0.1:18080` | port 8080 |

Open WebUI's own sign-in is off; vast's Caddy fronts every port with TLS and the Open
button's token, so the token is the login. `owui-setup.py` configures Open WebUI through
its API on every boot: the `studio_ui` tool (live progress, inline media), the four MCP
servers as tool servers, and the **Studio Director** model, which is the default for new
chats. It also turns on the chat setting *iframe sandbox: allow same origin*: the media
`studio_ui` shows sits in a sandboxed frame, and without same-origin Chrome holds back
vast's login cookie from it, so Caddy refuses every picture and video.

## The models

| Role | Model | Download | Licence |
|---|---|---|---|
| Director | **Qwen3.8-27B abliterated** (`huihui-ai/Huihui-Qwen3.8-27B-abliterated`), quantised to FP8 by vLLM as it loads. Qwen3.8-27B (August 2026) is the strongest open model that fits beside the image and video models, and is strong at multi-step tool use; this build has its refusals removed. | 55.6 GB (bf16) | Apache-2.0 |
| Keyframes | **Chroma1-HD** (`lodestones/Chroma1-HD`) with its T5-XXL encoder and the FLUX VAE: 26 steps, CFG 3.8, as its author's reference workflow | 23.0 GB | Apache-2.0 |
| Animation | **Wan2.2-Remix NSFW image-to-video v3.0** (`FX-FeiHou/wan2.2-Remix`), both experts, with its recommended text encoder (`NSFW-API/NSFW-Wan-UMT5-XXL`) and the Wan 2.1 VAE. The four-step speed-up LoRAs are merged in: 8 steps, CFG 1, shift 8, 16 fps, up to 5 s a call | 35.6 GB | base Apache-2.0; the merge says "other" |
| Music | **ACE-Step 1.5** turbo (`ACE-Step/Ace-Step1.5`) | 10.1 GB | MIT |
| Voices | **Kokoro-82M** (`hexgrad/Kokoro-82M`), with the repo's own voice blends | 0.4 GB | Apache-2.0 |

About 125 GB in all, every file pinned to a commit and downloadable without a token. They
download on the first boot, so the first boot takes a while (15-20 minutes on a fast host);
a restart of the same instance keeps them. vast's provisioning fetches the ComfyUI models and
Kokoro (`ROOT/opt/studio-vast/provisioning/all.yaml`). At the same time, `studio-models`
(`ROOT/opt/supervisor-scripts/studio-models.sh`) fetches the director, then ACE-Step, so the
chat works as soon as the director is in, while Wan is still downloading. It runs each
download through `studio-fetch.py`, which starts a download again, from where it got to,
when it stalls: under 5 MB/s for three minutes.

What's legal: every one of these licences, and the law, forbids sexual content involving
minors and non-consensual sexual imagery of real people. The director's instructions
(`ROOT/opt/studio-vast/owui/director.md`) say so too: every character is an adult and is
shown as one, and no real, identifiable person is depicted at all, sexual or not: every
character is invented. Beyond that the director does not refuse adult subject matter.

## The GPU and its memory

One RTX PRO 6000 (96 GB) by default. vLLM takes about 40 GB of it (the FP8 weights, a
64k-token context and its cache), and the rest is shared one job at a time by ComfyUI
(Chroma about 25 GB, Wan about 35-45 GB at 720p), ACE-Step (about 14 GB) and Blender. On a
bigger card vLLM still takes 40 GB (`gpu-plan.py` works the fraction out at boot and writes
it to `/etc/studio-gpus.env`). With two or more cards, vLLM has the first to itself and
ComfyUI, ACE-Step and Blender use the others. ComfyUI runs with
`--disable-smart-memory`, so it moves its models back to RAM when each picture or clip is
done and the next job finds the card free; reloading them costs a second or two. Without
that, Wan stayed on the card after a clip and ACE-Step ran out of memory loading.
`STUDIO_LLM_GB` changes vLLM's 40 GB, `VLLM_GPU_UTIL` sets its fraction outright, and
`VLLM_MAX_MODEL_LEN` its context.

## Launching

From `~/git/vast-render`:

```sh
./vast-studio.sh --wait
```

It rents the RTX PRO 6000 with the fastest download line (at least 5 Gbps; a first boot
is mostly downloads), 300 GB of disk, outside China, and waits until the director answers.
`--gpu h200` or `--gpu b200` rents a bigger card, `--gpus 2` two of them, `--min-down`
changes the 5 Gbps and `--cheapest` sorts by price instead. Open the instance with its Open button on
[cloud.vast.ai/instances](https://cloud.vast.ai/instances/). Destroy it with
`vastai destroy instance ID` when you are done; it bills until you do.

## A conversation

1. *"A woman in a red raincoat on a rain-soaked rooftop at night, the city behind her.
   Paint two keyframes for the opening shot."* The director paints two takes and shows
   them with their ids (`pic-3f2a`, `pic-9b10`).
2. *"Use pic-3f2a. Animate it: she turns toward the camera as the rain falls."* A job
   starts; a progress bar follows ComfyUI step by step; the 5-second clip (`clip-…`) plays
   in the chat.
3. *"Make that 15 seconds: she walks to the edge."* It extends the clip from its last
   frame, twice.
4. *"She says 'You came back.' Add slow synth music and cut it together with captions."*
   A Kokoro line, an ACE-Step cue, and `studio_assemble` puts them together; the film plays
   in the chat. Everything made stays in the library for the next shot.

## Changing a model

- Director: change its line in `ROOT/opt/supervisor-scripts/studio-models.sh` and
  `STUDIO_LLM_DIR` in `ROOT/opt/studio-vast/bin/studio-env.sh`; vLLM's flags are in
  `ROOT/opt/supervisor-scripts/vllm.sh`.
- Keyframes or animation: the downloads in `provisioning/all.yaml`, and the file names
  and settings in `studio/workflows.py` (the graphs the studio queues in ComfyUI).
- Music: `ACE_DIT` picks ACE-Step's model (`acestep-v15-xl-sft` on a bigger card).

## How it is built and tested

`.github/workflows/studio-vast.yml` runs on every push that touches the image or the
renderers:

1. `ci/check-model-urls.py` checks every model URL answers without a token, and every
   pinned repo is public and ungated.
2. `docker buildx build . -f studio-vast/Dockerfile` (the whole repo is the context),
   pushed as `:<commit>`.
3. `imagegen/ci/compare-layers.py` checks the base layers kept vast's digests.
4. `ci/smoke-test.sh` boots the image on the runner's CPU the way vast does, with
   `STUDIO_MODELS=none`, and checks that:
   - ComfyUI accepts both of the studio's graphs;
   - the four MCP servers list their tools;
   - Blender renders EEVEE headless, Manim typesets with LaTeX, Kokoro speaks, GIMP draws,
     and ffmpeg has the assembler's filters;
   - ACE-Step and vLLM import;
   - the repo's test suites pass inside the image;
   - Open WebUI is set up;
   - a chat sent through Open WebUI's API reaches the studio's MCP server, with a
     stand-in playing vLLM;
   - Caddy fronts every port with TLS and the token.
5. Only then, and only for a push to `main`, is `:latest` moved to the new build. A
   branch's build keeps just its commit tag.

On a rented GPU, `~/git/vast-render/acceptance.py INSTANCE_ID` plays the person's side of
the conversation above through Open WebUI's API, downloads the finished film, and checks
it has video and audible sound of a sensible length, writing a contact sheet of its
frames.

## Known limits

- No lip sync: voices are laid over the clips, not driven into the mouths.
- Wan makes at most 5 seconds a call; longer shots are built by extension, which can drift.
- No character consistency across separately painted keyframes yet (Qwen-Image-2.1's
  editing models would add it).
- Kroma v0.3 turbo, in `imagegen-vast`, is not here: its licence asks deployers to filter
  content.
