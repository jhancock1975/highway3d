# studio-vast: an uncensored film studio you talk to, on one vast.ai GPU

## What it is

A container image for vast.ai. You rent one GPU, open a chat page in the
browser, describe a scene, and an uncensored LLM directs the work: it has an
uncensored image model paint keyframes, shows them to you to pick from,
animates the chosen frames into clips, chains clips into longer scenes, and
cuts them together with spoken dialog and music. Progress shows in the chat
while renders run, and finished pictures and videos play inline.

Everything runs on the rented machine. Nothing calls back to the Mac, and no
paid API is involved.

## Decisions (agreed 2026-10-04)

- **Hardware:** one RTX PRO 6000, 96 GB VRAM (vast lists it at about
  $1.00-1.10/hr). The whole stack must fit in 96 GB; the hard ceiling is 128 GB.
- **Where it lives:** branch `studio-vast` of jhancock1975/highway3d, which is
  the `~/git/adult` repo. The image is built by GitHub Actions, pushed to
  GHCR as `ghcr.io/jhancock1975/studio-vast` (public), on top of vast's
  ComfyUI image (`vastai/comfy:v0.38.0-cuda-12.9-py312`), the same way
  `imagegen-vast` is, so vast hosts already hold most of its layers. SwarmUI
  is not needed and is left out.
- **All of the adult repo's tools are in the image, not called remotely:**
  cartoon, lectern, studio, highway3d (with their four MCP servers on ports
  8769, 8767, 8768, 8766), highway, relativity, fonts.py and forgiving.py,
  with every venv they need rebuilt for Linux, Blender 5.2, Manim and LaTeX,
  Kokoro, ACE-Step 1.5, GIMP 3.2 and ffmpeg.
- **Two uncensored models, one directing the other:**
  - the director, an LLM: Qwen3.8-27B abliterated
    (`huihui-ai/Huihui-Qwen3.8-27B-abliterated`, Apache-2.0, not gated),
    served by vLLM with native tool calling;
  - the painter: Chroma1-HD (Apache-2.0) through ComfyUI, for keyframes.
- **Animation:** Wan2.2-Remix NSFW image-to-video v3.0 through ComfyUI, with
  its recommended text encoder (`NSFW-API/NSFW-Wan-UMT5-XXL`). A clip is
  extended by animating its last frame and joining the two.
- **Dialog and music:** Kokoro voices (studio_speak) and ACE-Step 1.5 music
  from a description, both from the adult repo; ffmpeg assembly by
  studio_assemble.
- **Browser interface:** Open WebUI v0.11.4, reached from vast's Instance
  Portal like ComfyUI. It talks to vLLM, uses the four MCP servers as tool
  servers, and adds a small set of its own Python tools for what MCP cannot
  do in the chat: live progress while a job runs, and showing pictures and
  videos inline.
- **One media library:** the studio library (ids like `pic-`, `clip-`,
  `voice-`, `music-`) holds every keyframe, clip, voice line and music cue,
  so anything one tool makes, another can use by id.
- **Content rule built into the director's instructions:** every character
  is an adult, and no real, identifiable person is depicted. The director
  refuses anything else.

## The conversation it supports

1. "A rainy rooftop at night, two lovers arguing..." -- the director proposes
   shots and paints 2-4 candidate keyframes per shot, shown as a gallery with
   their ids.
2. "Use pic-3f2a for the first shot, but make her hair red" -- it repaints or
   keeps the chosen frame.
3. "Animate it, she turns away" -- a 5 s clip renders with live progress and
   plays in the chat.
4. "Make that 15 seconds" -- it extends the clip from its last frame, twice.
5. "Add their dialog and some sad piano" -- Kokoro lines, an ACE-Step cue,
   cut together with the clips by studio_assemble, captions optional, and
   the finished film plays in the chat.

## Out of scope for the first version

- Character consistency across separately painted keyframes (Qwen-Image-2.1
  edit models) -- a later addition.
- Lip sync between dialog and mouths.
- Multi-GPU layouts.
- Kroma v0.3 turbo (its licence obliges deployers to filter content).

## Success criteria

- CI builds the image, and a CPU smoke test on the runner shows every
  service starting and answering: ComfyUI, Open WebUI with its tools and the
  four MCP tool servers registered, the four MCP servers listing their tools,
  Blender rendering a frame headless, Kokoro speaking a line, Manim
  typesetting a formula, ffmpeg's filters present.
- On a rented RTX PRO 6000, the scripted acceptance run drives the director
  through Open WebUI's API from a scene description to a finished mp4 with
  keyframes, an animated and extended clip, a voice line and music, and the
  result is checked by looking at its frames and listening to its audio
  track.
- The launch script in ~/git/vast-render rents the machine and prints how to
  open the chat.
