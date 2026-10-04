# studio-vast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A vast.ai container image in which an uncensored LLM, reached through a browser chat, directs an uncensored image model, Wan 2.2 image-to-video, Kokoro voices, ACE-Step music and every renderer in this repo to make films, with live progress and inline playback.

**Architecture:** The repo's existing `studio` MCP server becomes the hub. It gains local engines: Chroma1-HD keyframes and Wan2.2-Remix animation through ComfyUI, ACE-Step music, all filed in its one media library. Open WebUI is the chat. It talks to vLLM (Qwen3.8-27B abliterated), calls the four MCP servers (studio, cartoon, lectern, highway3d) as tool servers, and adds a small in-process tool for live job progress and inline media. Everything is baked into one image built FROM vast's ComfyUI image by GitHub Actions; models download on first boot.

**Tech Stack:** Python 3.12, MCP SDK 2.2.0 (streamable HTTP), ComfyUI v0.38.0 (vast base image), vLLM 0.30.0 (cu129 wheel), Open WebUI 0.11.4, Blender 5.2.2, GIMP 3.2.6 AppImage, Manim 0.21 + TeX Live, Kokoro 0.9.4, ACE-Step 1.5, ffmpeg 6.1, Docker Buildx, GitHub Actions, GHCR.

**Spec:** `docs/superpowers/specs/2026-10-04-studio-vast-design.md`

## Global Constraints

- Work on branch `studio-vast` in the worktree `/Users/john/git/highway3d-studio-vast`. Never touch `/Users/john/git/adult`'s working tree.
- Commit messages are one plain sentence in the repo's style ("Add ..., so ..."). No `feat:` prefixes. **No AI attribution of any kind:** no Co-Authored-By, no Claude-Session, no "Generated with".
- Never commit `.env`, its backups, keys or tokens. The vast.ai API key lives only in `/Users/john/git/vast-render/.env`.
- Python 3.12 for every venv in the image. Pin `mcp==2.2.0` wherever MCP is used; `forgiving.py` needs `mcp.server.mcpserver`.
- Every model URL is pinned to a commit: `/resolve/<sha>/` for files, `hf download --revision <sha>` for repos. No Hugging Face token is ever needed.
- Base image `vastai/comfy:v0.38.0-cuda-12.9-py312` (Ubuntu 24.04, `/venv/main` Python 3.12 with torch 2.10.0+cu128).
- Exact versions: vLLM 0.30.0 cu129 wheel, Open WebUI 0.11.4, Blender 5.2.2 (sha256 `84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168`), GIMP 3.2.6 AppImage (sha256 `79ea41bc9b06f78fda181849a9ca8e42d83f1124dedb756f4d52352e2465010f`), ACE-Step git `ca1e85fe9430179831e6bc6be790c332190a3866`.
- Ports:

  | Service | Address | Exposed? |
  |---|---|---|
  | vLLM | 127.0.0.1:18000 | no |
  | Open WebUI | 127.0.0.1:18081 | external 8081, "Studio Chat" |
  | ComfyUI | 18188 | external 8188 |
  | Jupyter | 18080 | external 8080 |
  | Instance Portal | 11111 | external 1111 |
  | MCP servers | 127.0.0.1:8766–8769 | no |

- Served LLM name `studio-llm`. Open WebUI model preset id `studio-director`. Python tool id `studio_ui`. MCP tool-server ids: `studio`, `cartoon`, `lectern`, `highway`. Open WebUI exposes MCP tools to the LLM as `<id>_<tool>`, for example `studio_studio_animate`.
- Tests follow the repo's style: plain `test_*` functions with `assert`, and a `main()` runner at the bottom that prints `ok`/`FAIL` and exits non-zero on failure. Tests run as scripts (`python path/test_x.py`), not under pytest.
- Local test interpreters on this Mac:
  - `/Users/john/git/adult/studio/.venv/bin/python` for studio tests
  - `/Users/john/git/adult/lectern/.mcpvenv/bin/python`
  - `/Users/john/git/adult/cartoon/.venv/bin/python`
  - the Open WebUI 0.11.4 venv at `/private/tmp/claude-501/-Users-john-git-vast-render/26778df9-debe-4b2b-98be-4efa3970339e/scratchpad/owui/.venv/bin/python`. Call it `$OWUI_PY` below.
- curl URL checks use `curl --connect-timeout 2 --max-time 5` (raise `--max-time` only for downloads).
- Renting GPUs is allowed once the user has added the auto-mode permission for `vast-studio.sh`. Destroy every instance you start as soon as its test is over, and check `vastai show instances` is empty.

## Review Focus

1. **Extending an imported clip whose size is not a Wan size** (a 320x240 phone clip with sound). Expect a longer clip at the nearest Wan size, not a crash. Tested in Task 4.
2. **A job whose process died** (instance restarted mid-render). `studio_status` and `watch_job` must say it stopped, not spin until the 60-minute limit. Tested in Tasks 4 and 7.
3. **Models missing or half-downloaded** (provisioning failed). ComfyUI refuses the graph, and the tool or job must say which file is missing in a sentence. Tested in Tasks 2 and 6.
4. **The wrong kind of id, or one that doesn't exist** (animate a clip, extend a picture, show `pic-zzzz`). Expect a sentence naming the problem and the right tool. Tested in Tasks 4, 6 and 7.
5. **A job queued behind other ComfyUI work.** Progress must say it is waiting, not sit at 0%. Tested in Task 2.

---

## File Structure

New or changed in the repo:

| Path | Responsibility |
|---|---|
| `blender_gpu.py` (new) | Pick Cycles' GPU back end (OptiX/CUDA/Metal…) on any machine |
| `test_blender_gpu.py` (new) | Its tests (pure, no Blender) |
| `cartoon/shot.py`, `cartoon/tools/look_set.py`, `lectern/shot.py`, `lectern/render.py` (modify) | Use `blender_gpu.enable` instead of hard-coded Metal |
| `cartoon/score.py` (modify) | ACE-Step on CUDA when there is one |
| `studio/memory.py`, `studio/test_memory.py` (modify) | Read `/proc/meminfo` on Linux |
| `studio/jobs.py`, `lectern/mcp_server.py` (modify) | Portable `ps`; jobs under another Python; asset id in DONE |
| `studio/test_library.py` (modify) | HEIC case only where `sips` exists |
| `studio/comfy.py` (new) | ComfyUI HTTP client: upload, queue, follow with progress, download |
| `studio/workflows.py` (new) | The two API graphs (Chroma1-HD t2i, Wan2.2-Remix i2v) and sizes |
| `studio/images.py` (modify) | `paint()`: keyframes from ComfyUI when `STUDIO_PICTURES=comfyui` |
| `studio/motion.py` (new) | Job module: animate a picture; extend a clip |
| `studio/compose.py` (new) | Job module: ACE-Step music from a description (runs under `lectern/.musicvenv`) |
| `studio/mcp_server.py` (modify) | New tools `studio_animate`, `studio_extend`, `studio_compose`; ComfyUI pictures |
| `studio/test_comfy.py`, `test_workflows.py`, `test_paint.py`, `test_motion.py`, `test_compose.py` (new); `studio/test_server.py`, `test_jobs.py` (modify) | Tests |
| `studio/README.md` (modify) | Document the new tools |
| `.dockerignore` (new) | Keep venvs, renders, .work and assets out of the build context |
| `studio-vast/Dockerfile` (new) | The image |
| `studio-vast/ROOT/...` (new) | Boot script, shared env, supervisor programs, provisioning manifests, Open WebUI tool, director prompt, setup script, vast capability and agent notes |
| `studio-vast/ci/{check-model-urls.py,smoke-test.sh,fake_llm.py,mcp_list.py,owui_e2e.py,owui-local-test.sh}` (new) | CI checks, plus a local Open WebUI integration test |
| `studio-vast/README.md` (new) | How it works and how to use it |
| `.github/workflows/studio-vast.yml` (new) | Build, push, smoke-test, tag `:latest` |

Outside the repo, in `/Users/john/git/vast-render` (not a git repo):

| Path | Responsibility |
|---|---|
| `vast-studio.sh` | Rent an RTX PRO 6000 and start the image |
| `acceptance.py` | Drive the director end to end on a rented GPU and check the film |
| `README.md` | Document both |

---

### Task 1: Make the repo's tools run on Linux

**Files:**
- Create: `blender_gpu.py`, `test_blender_gpu.py`
- Modify: `cartoon/shot.py:33-38` (`gpu_setup`), `cartoon/tools/look_set.py:35-37`, `lectern/shot.py:672-697` (`_enable_gpu`), `lectern/render.py` (`_enable_gpu`, same body), `cartoon/score.py:135` and its cleanup, `studio/memory.py`, `studio/test_memory.py`, `studio/jobs.py:43`, `lectern/mcp_server.py:425`, `studio/test_library.py:41-42,65-70`

**Interfaces:**
- Produces: `blender_gpu.PREFERENCE`, `blender_gpu.choose(found: dict[str, list[str]]) -> str | None`, `blender_gpu.enable(bpy) -> str` (a back end name or `"CPU"`); `studio.memory.MACHINE: str`; `studio.memory.available_gb(vm_stat_text=None, meminfo_text=None) -> float`.

- [ ] **Step 1: Write the failing tests**

`test_blender_gpu.py`:
```python
"""Which Cycles back end wins, on any machine. Pure: no Blender needed.

    python3 test_blender_gpu.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_gpu as G  # noqa: E402


class _Dev:
    def __init__(self, name, kind):
        self.name, self.type, self.use = name, kind, False


class _Prefs:
    """Cycles' add-on preferences, for a machine with the given back ends."""
    def __init__(self, available):
        self.available = available          # {kind: [device names]}
        self._kind = "NONE"
        self.devices = []

    @property
    def compute_device_type(self):
        return self._kind

    @compute_device_type.setter
    def compute_device_type(self, kind):
        if kind not in self.available:
            raise TypeError(f"enum '{kind}' not found")
        self._kind = kind

    def refresh_devices(self):
        self.devices = [_Dev(n, self._kind) for n in self.available[self._kind]] + [_Dev("CPU", "CPU")]


class _Bpy:
    def __init__(self, available):
        prefs = _Prefs(available)
        addon = type("A", (), {"preferences": prefs})()
        self.context = type("C", (), {"preferences": type("P", (), {"addons": {"cycles": addon}})()})()
        self.prefs = prefs


def test_nvidia_prefers_optix_over_cuda():
    assert G.choose({"OPTIX": ["RTX PRO 6000"], "CUDA": ["RTX PRO 6000"]}) == "OPTIX"


def test_cuda_when_optix_finds_nothing():
    assert G.choose({"OPTIX": [], "CUDA": ["A40"]}) == "CUDA"


def test_mac_metal():
    assert G.choose({"METAL": ["Apple M3 Max"]}) == "METAL"


def test_cpu_when_nothing_found():
    assert G.choose({}) is None and G.choose({"CUDA": []}) is None


def test_enable_on_linux_nvidia_turns_optix_devices_on():
    bpy = _Bpy({"OPTIX": ["RTX PRO 6000"], "CUDA": ["RTX PRO 6000"], "NONE": []})
    assert G.enable(bpy) == "OPTIX"
    assert bpy.prefs.compute_device_type == "OPTIX"
    assert [d.use for d in bpy.prefs.devices] == [True, False]   # the GPU yes, the CPU no


def test_enable_on_a_mac_turns_metal_on():
    bpy = _Bpy({"METAL": ["Apple M3 Max"], "NONE": []})
    assert G.enable(bpy) == "METAL"


def test_enable_without_a_gpu_says_cpu():
    assert G.enable(_Bpy({"NONE": []})) == "CPU"


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
```

Add to `studio/test_memory.py` (above its `main`):
```python
MEMINFO = """MemTotal:       65843916 kB
MemFree:         1234567 kB
MemAvailable:   41943040 kB
Buffers:          123456 kB
"""


def test_linux_reads_memavailable():
    assert M.available_gb(meminfo_text=MEMINFO) == 40.0


def test_this_machine_reports_memory():
    assert M.available_gb() > 0
```
In the same file, change the assertion at line 35 from the literal `"The Mac has 6 GB ..."` to the f-string `f"The {M.MACHINE} has 6 GB ..."`, keeping the rest of the expected sentence as it is.

- [ ] **Step 2: Run the tests to see them fail**

Run: `python3 test_blender_gpu.py; /Users/john/git/adult/studio/.venv/bin/python studio/test_memory.py`
Expected: `ModuleNotFoundError: No module named 'blender_gpu'`, then FAIL for `test_linux_reads_memavailable` (an unexpected keyword argument `meminfo_text`).

- [ ] **Step 3: Implement**

`blender_gpu.py`:
```python
"""Which GPU Cycles should render on, on whatever machine this is.

Imported inside Blender by cartoon/shot.py, cartoon/tools/look_set.py,
lectern/shot.py and lectern/render.py. Cycles names its back ends by vendor:
Metal on a Mac, OptiX or CUDA on an NVIDIA card. The first back end that
finds a device wins, so the same scripts render on the Mac and on a rented
Linux GPU instead of naming Metal and falling back to the CPU everywhere else.
"""

from __future__ import annotations

PREFERENCE = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")


def choose(found: dict) -> str | None:
    """The back end to use, given {back end: [device names]}; None for the CPU."""
    for kind in PREFERENCE:
        if found.get(kind):
            return kind
    return None


def _refresh(prefs) -> None:
    for attr in ("get_devices", "refresh_devices"):
        if hasattr(prefs, attr):
            getattr(prefs, attr)()


def enable(bpy) -> str:
    """Point Cycles at the best GPU and say which back end; "CPU" when there is none."""
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return "CPU"
    prefs = addon.preferences
    found = {}
    for kind in PREFERENCE:
        try:
            prefs.compute_device_type = kind
        except TypeError:            # this Blender has no such back end
            continue
        _refresh(prefs)
        found[kind] = [d.name for d in prefs.devices if d.type == kind]
    kind = choose(found)
    if kind is None:
        return "CPU"
    prefs.compute_device_type = kind
    _refresh(prefs)
    for d in prefs.devices:
        d.use = (d.type == kind)
    print(f"cycles device ({kind}):", ", ".join(found[kind]), flush=True)
    return kind
```

In `cartoon/shot.py`, replace the body of `gpu_setup()` (lines 34-38):
```python
def gpu_setup():
    import blender_gpu
    blender_gpu.enable(bpy)
```

In `cartoon/tools/look_set.py`, replace the three lines that set `"METAL"` and turn on every device (the two `prefs` lines and `for d in prefs.devices: d.use = True`) with:
```python
    import blender_gpu; blender_gpu.enable(bpy)
```

In both `lectern/shot.py` and `lectern/render.py`, replace `_enable_gpu`'s docstring first line and body (keep the explanatory paragraph about `cycles.devices` being empty):
```python
def _enable_gpu() -> str:
    """Turn the best GPU on (Metal on the Mac, OptiX or CUDA on NVIDIA), and say whether Cycles will use one.

    `cycles.devices` is empty until the preferences are refreshed, so setting
    `scene.cycles.device = "GPU"` on a fresh --factory-startup silently renders
    on the CPU instead: the first measurement here came out at 7s a frame,
    which over a 24-minute lecture is six days rather than one night.
    """
    try:
        import blender_gpu
        return "CPU" if blender_gpu.enable(bpy) == "CPU" else "GPU"
    except Exception as e:
        print("no GPU, falling back to CPU:", e, flush=True)
        return "CPU"
```

In `cartoon/score.py`, replace line 135 (`dev = "mps" if ... else "cpu"`) with:
```python
    if torch.cuda.is_available():
        dev = "cuda"
    elif torch.backends.mps.is_available():
        dev = "mps"
    else:
        dev = "cpu"
```
At the end of `generate()`, after `if dev == "mps": torch.mps.empty_cache()`, add:
```python
    elif dev == "cuda":
        torch.cuda.empty_cache()
```

In `studio/memory.py`:
- add `import sys`;
- add `MACHINE = "Mac" if sys.platform == "darwin" else "machine"` after `CALLED`;
- replace `available_gb` with the version below;
- in `refusal()`, change the message's start from `"The Mac has "` to `f"The {MACHINE} has "`.

```python
def available_gb(vm_stat_text: str | None = None,
                 meminfo_text: str | None = None) -> float:
    """Gigabytes the system could hand out now: vm_stat on a Mac,
    MemAvailable from /proc/meminfo on Linux."""
    if vm_stat_text is None and meminfo_text is None:
        if sys.platform == "darwin":
            vm_stat_text = subprocess.run(["vm_stat"], capture_output=True,
                                          text=True).stdout
        else:
            with open("/proc/meminfo") as fh:
                meminfo_text = fh.read()
    if meminfo_text is not None:
        kb = int(re.search(r"^MemAvailable:\s+(\d+) kB", meminfo_text,
                           re.M).group(1))
        return round(kb / 2 ** 20, 2)
    text = vm_stat_text
    page = int(re.search(r"page size of (\d+) bytes", text).group(1))

    def pages(label: str) -> int:
        m = re.search(rf"^{label}:\s+(\d+)\.", text, re.M)
        return int(m.group(1)) if m else 0

    free = (pages("Pages free") + pages("Pages inactive")
            + pages("Pages speculative"))
    return round(free * page / 2 ** 30, 2)
```

In `studio/jobs.py:43` and `lectern/mcp_server.py:425`, change `["ps", "-axww", "-o", "args="]` to `["ps", "-A", "-ww", "-o", "args="]`. That form means "every process, unlimited width" on both macOS and Linux procps.

In `studio/test_library.py`:
- add `import shutil` to the imports;
- replace line 42 (the `sips` call) with:
  ```python
  HAVE_SIPS = shutil.which("sips") is not None      # macOS only; Linux has no HEIC maker
  if HAVE_SIPS:
      subprocess.run(["sips", "-s", "format", "heic", STILL, "--out", HEIC], check=True, capture_output=True)
  ```
- make the first line of `test_iphone_photos_import_as_pictures` `if not HAVE_SIPS: return`.

- [ ] **Step 4: Run the tests to see them pass, and the existing suites still pass**

Run:
```bash
cd /Users/john/git/highway3d-studio-vast
python3 test_blender_gpu.py
S=/Users/john/git/adult/studio/.venv/bin/python
for t in memory jobs library; do $S studio/test_$t.py | tail -1; done
/Users/john/git/adult/lectern/.mcpvenv/bin/python lectern/test_status.py | tail -1
/Users/john/git/adult/cartoon/.venv/bin/python cartoon/test_cartoon.py | tail -1
blender -b --factory-startup --python-expr "import sys; sys.path.insert(0, '.'); import bpy, blender_gpu; print('GPU', blender_gpu.enable(bpy))" 2>&1 | grep -E '^GPU|cycles device'
```
Expected: every suite prints `N/N passed`, and the Blender line prints `cycles device (METAL): Apple ...` and then `GPU METAL`.

- [ ] **Step 5: Commit**

```bash
git add blender_gpu.py test_blender_gpu.py cartoon/shot.py cartoon/tools/look_set.py lectern/shot.py lectern/render.py cartoon/score.py studio/memory.py studio/test_memory.py studio/jobs.py lectern/mcp_server.py studio/test_library.py
git commit -m "Let the renderers run on Linux: pick Cycles' GPU back end by what the machine has instead of naming Metal, score on CUDA when there is one, read free memory from /proc/meminfo, list processes with flags both ps versions take, and make HEIC only where sips exists"
```

---

### Task 2: A ComfyUI client and the two graphs

**Files:**
- Create: `studio/comfy.py`, `studio/workflows.py`, `studio/test_comfy.py`, `studio/test_workflows.py`

**Interfaces:**
- Produces:
  - `comfy.URL: str` (env `STUDIO_COMFY`, default `http://127.0.0.1:18188`)
  - `comfy.ComfyError(RuntimeError)`
  - `comfy.progress_event(msg: dict, prompt_id: str, labels: dict) -> tuple[str, float] | None`. The percent is `-1.0` when there is no step count.
  - `class comfy.Comfy(url=URL, opener=urllib.request.urlopen)`, with methods:
    - `.upload(path) -> str`
    - `.queue(graph) -> str`
    - `.history(prompt_id) -> dict | None`
    - `.ahead(prompt_id) -> int | None`
    - `.run(graph, on_progress=None, labels=None, timeout=3600, poll=2.0) -> dict` (the outputs)
    - `Comfy.files(outputs) -> list[dict]` (static)
    - `.download(f: dict, folder: str) -> str`
  - `workflows.CHROMA`, `WAN`, `FPS = 16`, `CHROMA_SIZES`, `WAN_SIZES` (`{"draft": {...}, "final": {...}}`), `CHROMA_LABELS`, `WAN_LABELS`, `CHROMA_NEGATIVE`, `WAN_NEGATIVE`
  - `workflows.frames(seconds) -> int`
  - `workflows.nearest_aspect(width, height, table: dict) -> str`
  - `workflows.chroma_t2i(prompt, width, height, count=1, seed=0, negative="", prefix="studio/pic") -> dict`
  - `workflows.wan_i2v(image, prompt, width, height, length, seed=0, negative="", prefix="studio/clip") -> dict`

- [ ] **Step 1: Write the failing tests**

`studio/test_workflows.py`:
```python
"""The ComfyUI graphs: wired up, and carrying what they were asked for. No ComfyUI.

    studio/.venv/bin/python studio/test_workflows.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import workflows as W  # noqa: E402


def links_resolve(graph):
    for nid, node in graph.items():
        for name, value in node["inputs"].items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                assert value[0] in graph, f"node {nid} input {name} points at missing node {value[0]}"


def test_chroma_is_wired_and_carries_the_request():
    g = W.chroma_t2i("a red fox in snow", 1344, 768, count=3, seed=42, negative="blurry")
    links_resolve(g)
    kinds = {n["class_type"] for n in g.values()}
    assert {"UNETLoader", "CLIPLoader", "T5TokenizerOptions", "ModelSamplingAuraFlow", "KSampler",
            "EmptySD3LatentImage", "VAEDecode", "SaveImage"} <= kinds, kinds
    by = {n["class_type"]: n["inputs"] for n in g.values()}
    assert by["EmptySD3LatentImage"] == {"width": 1344, "height": 768, "batch_size": 3}
    assert by["KSampler"]["seed"] == 42 and by["KSampler"]["steps"] == 26 and by["KSampler"]["cfg"] == 3.8
    assert by["KSampler"]["scheduler"] == "beta" and by["ModelSamplingAuraFlow"]["shift"] == 1.0
    texts = sorted(n["inputs"]["text"] for n in g.values() if n["class_type"] == "CLIPTextEncode")
    assert texts == ["a red fox in snow", "blurry"], texts
    assert by["UNETLoader"]["unet_name"] == "Chroma1-HD.safetensors"
    assert by["CLIPLoader"] == {"clip_name": "t5xxl_enconly.safetensors", "type": "chroma", "device": "default"}


def test_chroma_uses_the_standard_negative_when_none_given():
    g = W.chroma_t2i("x", 1024, 1024)
    assert W.CHROMA_NEGATIVE in [n["inputs"].get("text") for n in g.values()]


def test_wan_is_wired_and_splits_the_steps():
    g = W.wan_i2v("studio-1a2b.png", "she turns away", 832, 480, 81, seed=7)
    links_resolve(g)
    assert g["5"] == {"class_type": "LoadImage", "inputs": {"image": "studio-1a2b.png"}}
    w = g["8"]["inputs"]
    assert (w["width"], w["height"], w["length"], w["batch_size"]) == (832, 480, 81, 1)
    hi, lo = g["11"]["inputs"], g["12"]["inputs"]
    assert (hi["start_at_step"], hi["end_at_step"], lo["start_at_step"]) == (0, 4, 4)
    assert hi["noise_seed"] == lo["noise_seed"] == 7 and hi["cfg"] == lo["cfg"] == 1.0
    assert hi["add_noise"] == "enable" and lo["add_noise"] == "disable"
    assert g["9"]["inputs"]["shift"] == g["10"]["inputs"]["shift"] == 8.0
    assert g["1"]["inputs"]["unet_name"] == W.WAN["high"] and g["2"]["inputs"]["unet_name"] == W.WAN["low"]
    assert g["6"]["inputs"]["text"] == "she turns away" and g["7"]["inputs"]["text"] == W.WAN_NEGATIVE
    assert g["14"]["inputs"]["fps"] == 16.0
    assert g["15"]["class_type"] == "SaveVideo" and g["15"]["inputs"]["format"] == "mp4"


def test_frames_are_sixteen_a_second_plus_one_and_capped():
    assert W.frames(5) == 81 and W.frames(1) == 17
    assert W.frames(0.2) == 17 and W.frames(9) == 81


def test_nearest_aspect():
    sizes = W.WAN_SIZES["draft"]
    assert W.nearest_aspect(1344, 768, sizes) == "16:9"
    assert W.nearest_aspect(768, 1344, sizes) == "9:16"
    assert W.nearest_aspect(1000, 1010, sizes) == "1:1"
    assert W.nearest_aspect(320, 240, sizes) == "4:3"


def test_every_size_is_a_multiple_of_sixteen():
    for table in (W.CHROMA_SIZES, W.WAN_SIZES["draft"], W.WAN_SIZES["final"]):
        for w, h in table.values():
            assert w % 16 == 0 and h % 16 == 0, (w, h)


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
```

`studio/test_comfy.py`:
```python
"""The ComfyUI client, against a stand-in ComfyUI on a local port.

    studio/.venv/bin/python studio/test_comfy.py
"""
import json
import os
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import comfy as C  # noqa: E402

SEEN = {"uploads": [], "prompts": []}
POLLS = {"p1": 0}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/upload/image":
            name = re.search(rb'filename="([^"]+)"', body).group(1).decode()
            SEEN["uploads"].append((name, b"PNGBYTES" in body))
            return self._send(200, {"name": name, "subfolder": "", "type": "input"})
        if self.path == "/prompt":
            graph = json.loads(body)["prompt"]
            SEEN["prompts"].append(graph)
            if any(n["class_type"] == "Broken" for n in graph.values()):
                return self._send(400, {"error": {"type": "prompt_outputs_failed_validation",
                                                  "message": "Prompt outputs failed validation"},
                                        "node_errors": {"3": {"class_type": "UNETLoader", "errors": [
                                            {"message": "Value not in list",
                                             "details": "unet_name: 'Wan2.2_missing.safetensors' not in []"}]}}})
            pid = "p2" if any(n["class_type"] == "Fails" for n in graph.values()) else "p1"
            return self._send(200, {"prompt_id": pid, "number": 1, "node_errors": {}})
        self._send(404, {})

    def do_GET(self):
        if self.path == "/queue":
            running = [[1, "p1", {}, {}, []]] if POLLS["p1"] < 2 else []
            return self._send(200, {"queue_running": [[0, "other", {}, {}, []]], "queue_pending": running})
        if self.path == "/history/p1":
            POLLS["p1"] += 1
            if POLLS["p1"] < 3:
                return self._send(200, {})
            return self._send(200, {"p1": {"outputs": {"9": {"images": [
                {"filename": "a.png", "subfolder": "studio", "type": "output"}]}},
                "status": {"status_str": "success", "completed": True, "messages": []}}})
        if self.path == "/history/p2":
            return self._send(200, {"p2": {"outputs": {}, "status": {"status_str": "error", "completed": False,
                "messages": [["execution_error", {"node_type": "KSamplerAdvanced",
                                                  "exception_message": "CUDA out of memory"}]]}}})
        if self.path.startswith("/view?"):
            return self._send(200, b"IMAGEDATA", "image/png")
        self._send(404, {})


SERVER = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{SERVER.server_address[1]}"


def test_upload_sends_the_file_and_returns_its_name():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "frame.png")
    open(p, "wb").write(b"PNGBYTES")
    name = C.Comfy(URL).upload(p)
    assert name.endswith(".png") and SEEN["uploads"][-1] == (name, True), (name, SEEN["uploads"])


def test_refusal_names_the_node_and_the_missing_file():
    try:
        C.Comfy(URL).queue({"3": {"class_type": "Broken", "inputs": {}}})
    except C.ComfyError as e:
        assert "UNETLoader" in str(e) and "Wan2.2_missing.safetensors" in str(e), str(e)
    else:
        raise AssertionError("no error")


def test_run_waits_reports_waiting_and_returns_outputs():
    said = []
    out = C.Comfy(URL).run({"1": {"class_type": "Ok", "inputs": {}}},
                           on_progress=lambda s, p: said.append((s, p)), poll=0.05)
    files = C.Comfy.files(out)
    assert files == [{"filename": "a.png", "subfolder": "studio", "type": "output"}], files
    assert any("waiting for ComfyUI" in s for s, _ in said), said


def test_download_writes_the_file():
    d = tempfile.mkdtemp()
    path = C.Comfy(URL).download({"filename": "a.png", "subfolder": "studio", "type": "output"}, d)
    assert open(path, "rb").read() == b"IMAGEDATA" and path.endswith("a.png")


def test_a_failed_run_says_which_node_and_why():
    try:
        C.Comfy(URL).run({"1": {"class_type": "Fails", "inputs": {}}}, poll=0.05)
    except C.ComfyError as e:
        assert "KSamplerAdvanced" in str(e) and "out of memory" in str(e), str(e)
    else:
        raise AssertionError("no error")


def test_progress_events_read_as_words():
    labels = {"11": "high-noise pass"}
    msg = {"type": "progress", "data": {"value": 2, "max": 4, "prompt_id": "p1", "node": "11"}}
    assert C.progress_event(msg, "p1", labels) == ("high-noise pass, step 2 of 4", 50.0)
    assert C.progress_event(msg, "other", labels) is None
    ex = {"type": "executing", "data": {"node": "11", "prompt_id": "p1"}}
    assert C.progress_event(ex, "p1", labels) == ("high-noise pass", -1.0)
    assert C.progress_event({"type": "status", "data": {}}, "p1", labels) is None


def test_unreachable_comfyui_is_a_sentence():
    try:
        C.Comfy("http://127.0.0.1:9").queue({})
    except C.ComfyError as e:
        assert "not answering" in str(e), str(e)
    else:
        raise AssertionError("no error")


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `S=/Users/john/git/adult/studio/.venv/bin/python; $S studio/test_workflows.py; $S studio/test_comfy.py`
Expected: `ImportError: cannot import name 'workflows'` and `cannot import name 'comfy'`.

- [ ] **Step 3: Implement**

`studio/workflows.py`:
```python
"""The two ComfyUI graphs the studio runs, in ComfyUI's API format.

Both were checked against ComfyUI v0.38.0's /prompt validation and use only
core nodes, so nothing beyond vast's ComfyUI image is needed:

- keyframes: Chroma1-HD (Apache-2.0), as in its author's reference workflow
  (lodestones/Chroma1-HD@0e0c60ec): T5 tokenizer padding 0, AuraFlow shift 1,
  26 steps of euler/beta at CFG 3.8. Without the AuraFlow node ComfyUI falls
  back to Chroma's Flux-style shift of 1.15, a different schedule.
- animation: Wan2.2-Remix NSFW image-to-video v3.0 (FX-FeiHou/wan2.2-Remix),
  with the lightx2v four-step LoRAs already merged in, so none is added: 8
  steps split 4/4 between the high- and low-noise experts, CFG 1, shift 8,
  16 frames a second, saved as h264 at CRF 19 like the author's workflow.
"""

from __future__ import annotations

import math

CHROMA = dict(unet="Chroma1-HD.safetensors", clip="t5xxl_enconly.safetensors",
              vae="Flux/ae.safetensors")
WAN = dict(high="Wan2.2_Remix_NSFW_i2v_14b_high_lighting_fp8_e4m3fn_v3.0.safetensors",
           low="Wan2.2_Remix_NSFW_i2v_14b_low_lighting_fp8_e4m3fn_v3.0.safetensors",
           clip="nsfw_wan_umt5-xxl_fp8_scaled.safetensors",
           vae="wan_2.1_vae.safetensors")
FPS = 16
MAX_SECONDS = 5

CHROMA_NEGATIVE = (
    "This greyscale unfinished sketch has bad proportions, is featureless and disfigured. "
    "It is a blurry ugly mess and with excessive gaussian blur. It is riddled with watermarks "
    "and signatures. Everything is smudged with leaking colors and nonsensical orientation of "
    "objects. Messy and abstract image filled with artifacts disrupt the coherency of the overall "
    "composition. The image has extreme chromatic abberations and inconsistent lighting. Dull, "
    "monochrome colors and countless artistic errors.")
# Wan's own standard negative prompt, in the Chinese it was trained with.
WAN_NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，"
                "JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，"
                "形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")

# About a megapixel at each shape, every side a multiple of 16.
CHROMA_SIZES = {"1:1": (1024, 1024), "16:9": (1344, 768), "9:16": (768, 1344),
                "4:3": (1152, 896), "3:4": (896, 1152), "3:2": (1216, 832),
                "2:3": (832, 1216), "21:9": (1536, 640)}
# Wan 2.2 14B is trained at 480p and 720p.
WAN_SIZES = {
    "draft": {"16:9": (832, 480), "9:16": (480, 832), "1:1": (640, 640),
              "4:3": (736, 544), "3:4": (544, 736)},
    "final": {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (960, 960),
              "4:3": (1088, 832), "3:4": (832, 1088)},
}
CHROMA_LABELS = {"9": "painting", "10": "decoding the picture"}
WAN_LABELS = {"8": "preparing the start frame", "11": "high-noise pass",
              "12": "low-noise pass", "13": "decoding frames", "15": "writing the video"}


def frames(seconds: float) -> int:
    """Wan's frame count for a clip this long: 16 a second plus the start frame, 1 to 5 seconds."""
    s = max(1, min(MAX_SECONDS, round(float(seconds))))
    return FPS * s + 1


def nearest_aspect(width: int, height: int, table: dict) -> str:
    """The key of `table` whose shape is closest to width x height."""
    want = math.log(width / height)
    return min(table, key=lambda k: abs(math.log(table[k][0] / table[k][1]) - want))


def chroma_t2i(prompt: str, width: int, height: int, count: int = 1, seed: int = 0,
               negative: str = "", prefix: str = "studio/pic") -> dict:
    """Text to `count` pictures with Chroma1-HD."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": CHROMA["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CHROMA["clip"], "type": "chroma", "device": "default"}},
        "3": {"class_type": "T5TokenizerOptions", "inputs": {"clip": ["2", 0], "min_padding": 0, "min_length": 0}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": CHROMA["vae"]}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.0}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or CHROMA_NEGATIVE, "clip": ["3", 0]}},
        "8": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": count}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["5", 0], "seed": seed, "steps": 26, "cfg": 3.8,
                                                   "sampler_name": "euler", "scheduler": "beta",
                                                   "positive": ["6", 0], "negative": ["7", 0],
                                                   "latent_image": ["8", 0], "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": prefix}},
    }


def wan_i2v(image: str, prompt: str, width: int, height: int, length: int, seed: int = 0,
            negative: str = "", prefix: str = "studio/clip") -> dict:
    """A start frame (a name in ComfyUI's input folder) to `length` frames of video."""
    sampler = {"cfg": 1.0, "steps": 8, "sampler_name": "euler", "scheduler": "simple",
               "noise_seed": seed, "positive": ["8", 0], "negative": ["8", 1]}
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": WAN["high"], "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": WAN["low"], "weight_dtype": "fp8_e4m3fn"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": WAN["clip"], "type": "wan", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": WAN["vae"]}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or WAN_NEGATIVE, "clip": ["3", 0]}},
        "8": {"class_type": "WanImageToVideo", "inputs": {"positive": ["6", 0], "negative": ["7", 0], "vae": ["4", 0],
                                                          "start_image": ["5", 0], "width": width, "height": height,
                                                          "length": length, "batch_size": 1}},
        "9": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 8.0}},
        "11": {"class_type": "KSamplerAdvanced", "inputs": dict(sampler, model=["9", 0], add_noise="enable",
                                                                latent_image=["8", 2], start_at_step=0, end_at_step=4,
                                                                return_with_leftover_noise="enable")},
        "12": {"class_type": "KSamplerAdvanced", "inputs": dict(sampler, model=["10", 0], add_noise="disable",
                                                                latent_image=["11", 0], start_at_step=4,
                                                                end_at_step=10000,
                                                                return_with_leftover_noise="disable")},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": float(FPS), "bit_depth": "auto",
                                                       "color_space": "sRGB", "codec": "none"}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": prefix, "format": "mp4",
                                                     "format.codec": "h264", "format.codec.encoding": "re-encode",
                                                     "format.codec.encoding.crf": 19.0, "codec": "auto"}},
    }
```

`studio/comfy.py`:
```python
"""ComfyUI on this machine, driven over its HTTP API.

The studio paints and animates through the ComfyUI that vast's image already
runs, at 127.0.0.1:18188 (STUDIO_COMFY overrides it). A job is one prompt
graph: queue it, follow it, and fetch what its output nodes wrote.

Step-by-step progress comes over ComfyUI's websocket when the
websocket-client package is installed. Without it, or if the socket drops,
the job is still followed by polling /history; it just reports no step counts.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

URL = os.environ.get("STUDIO_COMFY", "http://127.0.0.1:18188")


class ComfyError(RuntimeError):
    """ComfyUI refused a graph, a node failed running it, or ComfyUI is not there."""


def _summary(reply: dict) -> str:
    """One sentence from a /prompt refusal: which node, which input, why."""
    parts = []
    err = reply.get("error")
    if isinstance(err, dict) and err.get("message"):
        parts.append(err["message"].rstrip("."))
    for node, e in (reply.get("node_errors") or {}).items():
        for x in e.get("errors", []):
            parts.append(f"node {node} ({e.get('class_type', '?')}): {x.get('details') or x.get('message', '')}")
    return "; ".join(parts) or json.dumps(reply)[:300]


def _failure(status: dict) -> str:
    for kind, data in status.get("messages", []):
        if kind == "execution_error":
            return (f"{data.get('node_type', 'a node')} failed: "
                    f"{str(data.get('exception_message', '')).strip()}")
        if kind == "execution_interrupted":
            return "ComfyUI interrupted it"
    return "ComfyUI reported an error without saying why"


def progress_event(msg: dict, prompt_id: str, labels: dict):
    """(stage, percent) from one websocket message about our prompt, or None.

    `labels` maps node ids to what they do ("high-noise pass"), so a stage
    reads as words. The percent is -1.0 when there is no step count.
    """
    kind, data = msg.get("type"), msg.get("data") or {}
    if data.get("prompt_id") not in (None, prompt_id):
        return None
    node = data.get("node")
    if kind == "progress" and data.get("max"):
        stage = labels.get(str(node), f"node {node}")
        return f"{stage}, step {data['value']} of {data['max']}", 100.0 * data["value"] / data["max"]
    if kind == "executing" and node is not None:
        return labels.get(str(node), f"node {node}"), -1.0
    return None


class Comfy:
    def __init__(self, url: str = URL, opener=urllib.request.urlopen):
        self.url = url.rstrip("/")
        self.client_id = uuid.uuid4().hex
        self._open = opener

    # ---------------------------------------------------------------- http

    def _request(self, path: str, data: bytes | None = None, headers: dict | None = None,
                 timeout: float = 60) -> bytes:
        req = urllib.request.Request(self.url + path, data=data, headers=headers or {})
        try:
            with self._open(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                reply = json.loads(body)
            except ValueError:
                raise ComfyError(f"ComfyUI answered HTTP {e.code}: {body[:200]!r}") from None
            raise ComfyError(_summary(reply)) from None
        except (urllib.error.URLError, OSError) as e:
            raise ComfyError(f"ComfyUI is not answering at {self.url} ({e})") from None

    def _json(self, path: str, body: dict | None = None, timeout: float = 60) -> dict:
        data = None if body is None else json.dumps(body).encode()
        headers = {} if body is None else {"Content-Type": "application/json"}
        return json.loads(self._request(path, data, headers, timeout) or b"{}")

    # ------------------------------------------------------------- the API

    def upload(self, path: str) -> str:
        """Put a picture in ComfyUI's input folder; returns the name a LoadImage node takes."""
        ext = os.path.splitext(path)[1].lower() or ".png"
        name = f"studio-{uuid.uuid4().hex[:8]}{ext}"
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            payload = fh.read()
        b = uuid.uuid4().hex
        body = b"".join([
            f"--{b}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(), payload, b"\r\n",
            f"--{b}\r\n".encode(),
            b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
            f"--{b}--\r\n".encode(),
        ])
        reply = json.loads(self._request("/upload/image", body,
                                         {"Content-Type": f"multipart/form-data; boundary={b}"}))
        sub = reply.get("subfolder") or ""
        return f"{sub}/{reply['name']}" if sub else reply["name"]

    def queue(self, graph: dict) -> str:
        reply = self._json("/prompt", {"prompt": graph, "client_id": self.client_id})
        if reply.get("node_errors"):
            raise ComfyError(_summary(reply))
        return reply["prompt_id"]

    def history(self, prompt_id: str):
        """The finished record of a prompt, or None while it is queued or running."""
        return self._json(f"/history/{prompt_id}").get(prompt_id)

    def ahead(self, prompt_id: str):
        """How many prompts ComfyUI will run before this one; 0 once it is running; None if unknown."""
        q = self._json("/queue")
        running = q.get("queue_running", [])
        if any(item[1] == prompt_id for item in running):
            return 0
        pending = sorted(q.get("queue_pending", []), key=lambda item: item[0])
        for i, item in enumerate(pending):
            if item[1] == prompt_id:
                return len(running) + i
        return None

    def _socket(self):
        try:
            import websocket  # the websocket-client package
        except ImportError:
            return None
        url = self.url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        try:
            ws = websocket.create_connection(f"{url}/ws?clientId={self.client_id}", timeout=5)
            ws.settimeout(1.0)
            return ws
        except Exception:
            return None

    def run(self, graph: dict, on_progress=None, labels: dict | None = None,
            timeout: float = 3600, poll: float = 2.0) -> dict:
        """Queue a graph, follow it to its end, and return its outputs; ComfyError if it fails."""
        report = on_progress or (lambda stage, percent: None)
        labels = labels or {}
        ws = self._socket()          # before queueing, so no progress is missed
        try:
            prompt_id = self.queue(graph)
            deadline = time.time() + timeout
            checked = 0.0
            while time.time() < deadline:
                if ws is not None:
                    try:
                        raw = ws.recv()
                    except Exception as e:
                        if "Timeout" not in type(e).__name__:
                            ws = None          # closed: carry on by polling
                        raw = None
                    if isinstance(raw, str):
                        event = progress_event(json.loads(raw), prompt_id, labels)
                        if event:
                            report(*event)
                else:
                    time.sleep(poll)
                if time.time() - checked < poll:
                    continue
                checked = time.time()
                record = self.history(prompt_id)
                if record is not None:
                    status = record.get("status") or {}
                    if status.get("status_str") == "error" or status.get("completed") is False:
                        raise ComfyError(_failure(status))
                    return record.get("outputs") or {}
                waiting = self.ahead(prompt_id)
                if waiting:
                    report(f"waiting for ComfyUI: {waiting} job{'s' if waiting > 1 else ''} ahead", -1.0)
            raise ComfyError(f"gave up after {timeout / 60:.0f} minutes; ComfyUI is still working on it")
        finally:
            if ws is not None:
                ws.close()

    @staticmethod
    def files(outputs: dict) -> list:
        """Every file the output nodes wrote ({filename, subfolder, type}), in node order."""
        found = []
        for node in sorted(outputs, key=lambda k: int(k) if str(k).isdigit() else 0):
            for value in outputs[node].values():
                if isinstance(value, list):
                    found += [f for f in value if isinstance(f, dict) and "filename" in f]
        return found

    def download(self, f: dict, folder: str) -> str:
        q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                    "type": f.get("type", "output")})
        data = self._request(f"/view?{q}", timeout=600)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, os.path.basename(f["filename"]))
        with open(path, "wb") as fh:
            fh.write(data)
        return path
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `S=/Users/john/git/adult/studio/.venv/bin/python; $S studio/test_workflows.py; $S studio/test_comfy.py`
Expected: `6/6 passed` and `7/7 passed`.

- [ ] **Step 5: Validate both graphs against a real ComfyUI v0.38.0 on this Mac's CPU**

A research subagent already set up a CPU ComfyUI v0.38.0 with placeholder model files at `/private/tmp/claude-501/-Users-john-git-vast-render/26778df9-debe-4b2b-98be-4efa3970339e/scratchpad/serving/`.
1. Start it: `cd $SCRATCH/serving/comfyui-src && ../comfy-venv/bin/python main.py --cpu --base-directory ../comfy-base --port 18388` in the background.
2. Copy a PNG into `../comfy-base/input/start.png`.
3. POST each graph with `studio.workflows`. Use `S` for the studio venv's Python and run from the worktree:

```bash
$S - <<'EOF'
import json, sys, urllib.request
sys.path.insert(0, ".")
from studio import workflows as W
for g in (W.chroma_t2i("a fox", 1024, 1024, count=2, seed=1), W.wan_i2v("start.png", "turns", 832, 480, 81, seed=1)):
    req = urllib.request.Request("http://127.0.0.1:18388/prompt", data=json.dumps({"prompt": g}).encode(), headers={"Content-Type": "application/json"})
    print(urllib.request.urlopen(req).read()[:200])
EOF
```
Expected: two replies with a `prompt_id` and empty `node_errors`. Execution itself then fails on the placeholder weights, which is fine. Stop ComfyUI afterwards. If the scratch setup is gone, skip this step: Task 10's smoke test does the same check inside the image.

- [ ] **Step 6: Commit**

```bash
git add studio/comfy.py studio/workflows.py studio/test_comfy.py studio/test_workflows.py
git commit -m "Add a ComfyUI client to the studio, and the Chroma1-HD keyframe and Wan2.2-Remix image-to-video graphs it runs, checked against ComfyUI v0.38's validation"
```

---

### Task 3: Keyframes from ComfyUI in the studio library

**Files:**
- Modify: `studio/images.py`
- Create: `studio/test_paint.py`

**Interfaces:**
- Consumes: `comfy.Comfy` (`.run`, `.files`, `.download`), `workflows.chroma_t2i`, `workflows.CHROMA_SIZES`, `workflows.CHROMA_LABELS`, `library.add`.
- Produces: `images.PICTURES: str` (env `STUDIO_PICTURES`, `"xai"` by default, `"comfyui"` in the image) and `images.paint(prompt, aspect="16:9", count=1, negative="", seed=-1, client=None) -> list[dict]` (library notes, prefix `pic`).

- [ ] **Step 1: Write the failing test** — `studio/test_paint.py`:
```python
"""Keyframes from ComfyUI, filed in the library. A stand-in client; no ComfyUI.

    studio/.venv/bin/python studio/test_paint.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import images, library  # noqa: E402


class FakeClient:
    def __init__(self):
        self.graphs = []

    def run(self, graph, on_progress=None, labels=None, **kw):
        self.graphs.append(graph)
        n = graph["8"]["inputs"]["batch_size"]
        return {"11": {"images": [{"filename": f"pic_{i}.png", "subfolder": "studio", "type": "output"}
                                  for i in range(n)]}}

    @staticmethod
    def files(outputs):
        return outputs["11"]["images"]

    def download(self, f, folder):
        g = self.graphs[-1]["8"]["inputs"]
        path = os.path.join(folder, f["filename"])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=size={g['width']}x{g['height']}", "-frames:v", "1", path], check=True)
        return path


def test_two_keyframes_land_in_the_library_as_pictures():
    c = FakeClient()
    notes = images.paint("a lighthouse at dusk", aspect="16:9", count=2, seed=5, client=c)
    assert [n["id"][:4] for n in notes] == ["pic-", "pic-"], notes
    assert all(n["kind"] == "image" and (n["width"], n["height"]) == (1344, 768) for n in notes)
    assert all(os.path.exists(n["path"]) and n["prompt"] == "a lighthouse at dusk" for n in notes)
    assert c.graphs[-1]["9"]["inputs"]["seed"] == 5
    assert {n["id"] for n in library.listing("image")} >= {n["id"] for n in notes}


def test_a_random_seed_when_none_is_given():
    c = FakeClient()
    images.paint("x", client=c)
    assert c.graphs[-1]["9"]["inputs"]["seed"] >= 0


def test_count_is_one_to_four():
    for bad in (0, 5):
        try:
            images.paint("x", count=bad, client=FakeClient())
        except ValueError as e:
            assert "1 to 4" in str(e)
        else:
            raise AssertionError(f"count {bad} accepted")


def test_empty_prompt_is_refused():
    try:
        images.paint("  ", client=FakeClient())
    except ValueError as e:
        assert "prompt" in str(e)
    else:
        raise AssertionError("empty prompt accepted")


def test_unknown_aspect_falls_back_to_square():
    c = FakeClient()
    notes = images.paint("x", aspect="auto", client=c)
    assert (notes[0]["width"], notes[0]["height"]) == (1024, 1024)


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `$S studio/test_paint.py`. Expected: `AttributeError: module 'studio.images' has no attribute 'paint'`.

- [ ] **Step 3: Implement** in `studio/images.py`:
- change the module docstring's first line to `"""Pictures for the studio: cards GIMP draws, and pictures painted by Chroma1-HD on this machine's ComfyUI or by xAI."""`;
- change `from studio import library, memory, xai` to `from studio import comfy, library, memory, workflows, xai`;
- add `import random`, `import shutil`;
- add after `STYLES`:
```python
# Where pictures come from: "comfyui" (Chroma1-HD on this machine, the
# vast.ai image's setting) or "xai" (xAI's paid API, the Mac's setting).
PICTURES = os.environ.get("STUDIO_PICTURES", "xai")
```
and append:
```python
def paint(prompt: str, aspect: str = "16:9", count: int = 1, negative: str = "",
          seed: int = -1, client=None) -> list[dict]:
    """Keyframes from Chroma1-HD on this machine's ComfyUI, filed in the library as pic- ids."""
    if not prompt.strip():
        raise ValueError("a picture needs a prompt")
    count = int(count)
    if not 1 <= count <= 4:
        raise ValueError("pictures come 1 to 4 at a time")
    width, height = workflows.CHROMA_SIZES.get(aspect, workflows.CHROMA_SIZES["1:1"])
    seed = random.randrange(2 ** 31) if seed is None or int(seed) < 0 else int(seed)
    client = client or comfy.Comfy()
    graph = workflows.chroma_t2i(prompt, width, height, count=count, seed=seed, negative=negative)
    outputs = client.run(graph, labels=workflows.CHROMA_LABELS)
    tmp = tempfile.mkdtemp(prefix="studio-paint-")
    try:
        notes = [library.add(client.download(f, tmp), "pic", source="comfyui: Chroma1-HD", move=True,
                             prompt=prompt, aspect=aspect, seed=seed, take=i, negative=negative)
                 for i, f in enumerate(client.files(outputs))]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not notes:
        raise RuntimeError("ComfyUI finished without writing a picture")
    return notes
```

- [ ] **Step 4: Run it and the existing image tests to see them pass**

Run: `$S studio/test_paint.py; $S studio/test_xai.py; $S studio/test_server.py`
Expected: `5/5 passed`; the other two pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add studio/images.py studio/test_paint.py
git commit -m "Paint the studio's pictures with Chroma1-HD on this machine's ComfyUI when STUDIO_PICTURES=comfyui, one to four keyframes at a time, filed in the library like every other picture"
```

---

### Task 4: Animate a picture and extend a clip, as jobs

**Files:**
- Create: `studio/motion.py`, `studio/test_motion.py`
- Modify: `studio/jobs.py` (`start()` takes `python`; `_report()` names the asset), `studio/test_jobs.py`

**Interfaces:**
- Consumes: `comfy.Comfy`, `workflows.wan_i2v/frames/nearest_aspect/WAN_SIZES/WAN_LABELS/FPS`, `library.get/add`.
- Produces:
  - `motion.progress(stage, percent=-1.0)`, which prints a `PROGRESS` line;
  - `motion.last_frame(video, out) -> str`;
  - `motion.join(first, second, out, width, height) -> str`;
  - `motion.animate(picture, prompt, seconds=5, quality="draft", seed=-1, negative="", client=None) -> dict`;
  - `motion.extend(clip, prompt, seconds=5, quality="draft", seed=-1, negative="", client=None) -> dict`;
  - the CLI `python -m studio.motion {animate --picture ID | extend --clip ID} --prompt P --seconds N --quality Q --seed S --job J`, which prints `DONE {"out","seconds","bytes","took","asset"}`;
  - `jobs.start(job, module, args, header, python=None)`.

- [ ] **Step 1: Write the failing tests**

`studio/test_motion.py`:
```python
"""Animating pictures and extending clips. A stand-in ComfyUI that 'renders' with
ffmpeg's test pattern, so the joins, sizes and library notes are real.

    studio/.venv/bin/python studio/test_motion.py
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import library, motion  # noqa: E402

SRC = tempfile.mkdtemp(prefix="studio-src-")


def make(name, *args):
    path = os.path.join(SRC, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, path], check=True)
    return path


PIC = library.add(make("frame.png", "-f", "lavfi", "-i", "testsrc2=size=1344x768", "-frames:v", "1"), "pic")
PHONE = library.add(make("phone.mp4", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
                         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest"), "clip")


class FakeClient:
    def __init__(self):
        self.graphs, self.uploads = [], []

    def upload(self, path):
        self.uploads.append(path)
        return "studio-start.png"

    def run(self, graph, on_progress=None, labels=None, **kw):
        self.graphs.append(graph)
        if on_progress:
            on_progress("high-noise pass, step 2 of 4", 50.0)
        return {"15": {"images": [{"filename": "clip_00001_.mp4", "subfolder": "studio", "type": "output"}]}}

    @staticmethod
    def files(outputs):
        return outputs["15"]["images"]

    def download(self, f, folder):
        w = self.graphs[-1]["8"]["inputs"]
        n = w["length"]
        path = os.path.join(folder, f"seg{len(self.graphs)}.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=size={w['width']}x{w['height']}:rate=16", "-frames:v", str(n),
                        "-pix_fmt", "yuv420p", path], check=True)
        return path


def quiet(fn, *a, **k):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **k)
    return r, out.getvalue()


def test_animate_makes_a_clip_at_the_pictures_shape():
    c = FakeClient()
    note, said = quiet(motion.animate, PIC["id"], "she turns away", seconds=5, seed=3, client=c)
    assert note["id"].startswith("clip-") and note["kind"] == "video", note
    assert (note["width"], note["height"]) == (832, 480), note
    assert abs(note["seconds"] - 81 / 16) < 0.1, note["seconds"]
    assert note["picture"] == PIC["id"] and note["prompt"] == "she turns away"
    assert c.uploads == [PIC["path"]]
    assert 'PROGRESS {"stage": "high-noise pass, step 2 of 4", "percent": 50.0}' in said, said


def test_final_quality_is_720p():
    note, _ = quiet(motion.animate, PIC["id"], "x", seconds=1, quality="final", client=FakeClient())
    assert (note["width"], note["height"]) == (1280, 720)


def test_extend_carries_a_clip_on_without_repeating_the_join_frame():
    first, _ = quiet(motion.animate, PIC["id"], "a", seconds=5, client=FakeClient())
    c = FakeClient()
    longer, _ = quiet(motion.extend, first["id"], "she walks to the door", seconds=5, client=c)
    assert longer["id"].startswith("clip-") and longer["extends"] == first["id"], longer
    assert abs(longer["seconds"] - (81 + 80) / 16) < 0.1, longer["seconds"]
    assert c.uploads and c.uploads[0].endswith(".png")


def test_extending_an_odd_sized_phone_clip_lands_on_a_wan_size():
    longer, _ = quiet(motion.extend, PHONE["id"], "the camera pans left", seconds=2, client=FakeClient())
    assert (longer["width"], longer["height"]) == (736, 544), longer
    assert abs(longer["seconds"] - (2.0 + 32 / 16)) < 0.15, longer["seconds"]


def test_only_pictures_animate_and_only_clips_extend():
    for fn, ref, word in ((motion.animate, PHONE["id"], "studio_extend"),
                          (motion.extend, PIC["id"], "studio_animate")):
        try:
            fn(ref, "x", client=FakeClient())
        except ValueError as e:
            assert word in str(e), str(e)
        else:
            raise AssertionError(f"{fn.__name__} took {ref}")


def test_a_missing_id_is_a_sentence():
    try:
        motion.animate("pic-zzzz", "x", client=FakeClient())
    except KeyError as e:
        assert "pic-zzzz" in str(e)
    else:
        raise AssertionError("missing id accepted")


def test_the_job_says_failed_with_a_reason():
    r = subprocess.run([sys.executable, "-m", "studio.motion", "animate", "--picture", "pic-zzzz",
                        "--prompt", "x", "--job", "t1"], cwd=ROOT, capture_output=True, text=True,
                       env=dict(os.environ))
    assert r.returncode == 1 and r.stdout.strip().splitlines()[-1].startswith("FAILED"), r.stdout + r.stderr
    assert "pic-zzzz" in r.stdout


def test_last_frame_is_a_picture_of_the_clips_size():
    out = os.path.join(SRC, "last.png")
    motion.last_frame(PHONE["path"], out)
    assert library.probe(out)["kind"] == "image" and library.probe(out)["width"] == 320


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
```

Add to `studio/test_jobs.py` (above `main`):
```python
def test_a_finished_job_names_what_it_made():
    job = "aa11bb"
    log = os.path.join(J.WORK, f"job-{job}.log")
    with open(log, "w") as fh:
        fh.write('JOB {"name": "animate pic-1a2b"}\n')
        fh.write('DONE {"out": "/m/clip-9c01.mp4", "seconds": 5.1, "bytes": 2000000, "took": 70, "asset": "clip-9c01"}\n')
    said = J.status(job)
    assert "clip-9c01" in said and "finished" in said, said
```
This test assumes `test_jobs.py` imports `studio.jobs as J` and points `STUDIO_WORK` at a temp dir. If it uses other names, adapt the two names to match the file.

- [ ] **Step 2: Run the tests to see them fail**

Run: `$S studio/test_motion.py; $S studio/test_jobs.py`
Expected: `cannot import name 'motion'`, and a FAIL for `test_a_finished_job_names_what_it_made`, because the report does not mention `clip-9c01`.

- [ ] **Step 3: Implement**

In `studio/jobs.py`:
- change `start` to:
```python
def start(job: str, module: str, args: list[str], header: dict,
          python: str | None = None) -> str:
    """Run `python -m module *args --job job` detached, under `python` (this
    server's own interpreter unless given). Returns its log."""
    os.makedirs(WORK, exist_ok=True)
    log = os.path.join(WORK, f"job-{job}.log")
    with open(log, "w") as fh:
        fh.write("JOB " + json.dumps(header) + "\n")
        fh.flush()
        subprocess.Popen([python or sys.executable, "-m", module, *args, "--job", job],
                         cwd=HERE, stdout=fh, stderr=subprocess.STDOUT,
                         start_new_session=True)
    return log
```
- in `_report`, replace the DONE branch with:
```python
    if tail.startswith("DONE"):
        d = json.loads(tail[4:])
        what = f"{d['asset']} ({d['out']})" if d.get("asset") else d["out"]
        return (f"{name}: finished: {what}, {d['seconds']:.1f} seconds "
                f"long, {d['bytes'] / 1e6:.1f} MB, took {d['took']:.0f} "
                f"seconds.")
```
- in the "stopped before it finished" message, change "most likely because the server or the Mac restarted under it. Assembling the same edit again starts it over." to "most likely because the machine restarted under it. Starting the same work again starts it over."

`studio/motion.py`:
```python
"""Moving pictures: a keyframe animated into a clip, and a clip carried on.

    python -m studio.motion animate --picture pic-3f2a --prompt "she turns away" --seconds 5 --job 1a2b3c
    python -m studio.motion extend --clip clip-9c01 --prompt "she walks to the door" --seconds 5 --job 1a2b3c

Both run as studio jobs: after the JOB line come PROGRESS lines while
ComfyUI works, then DONE with the new clip's id, or FAILED saying why. The
model is Wan2.2-Remix image-to-video (see workflows.py); a call makes at most
five seconds.

A clip is extended by animating its last frame and joining the two, without
the new part's first frame, which repeats the old one's last. Both parts are
brought to the same Wan size, so an imported clip of any shape can be carried
on; Wan's clips are silent, so the result is too.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

from studio import comfy, library, workflows
from studio.errors import last_line


def progress(stage: str, percent: float = -1.0) -> None:
    d = {"stage": stage}
    if percent >= 0:
        d["percent"] = round(percent, 1)
    print("PROGRESS " + json.dumps(d), flush=True)


def _ffmpeg(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + last_line(r.stderr))


def last_frame(video: str, out: str) -> str:
    """The clip's very last frame, as a picture (every decoded frame overwrites the last)."""
    _ffmpeg("-sseof", "-1", "-i", video, "-update", "1", "-fps_mode", "passthrough", out)
    if not os.path.exists(out):
        raise RuntimeError(f"no last frame could be read from {video}")
    return out


def join(first: str, second: str, out: str, width: int, height: int) -> str:
    """`first` then `second` without its first frame, both at width x height and 16 fps."""
    fit = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
           f"crop={width}:{height},fps={workflows.FPS},setsar=1")
    _ffmpeg("-i", first, "-i", second, "-filter_complex",
            f"[0:v]{fit}[a];[1:v]trim=start_frame=1,setpts=PTS-STARTPTS,{fit}[b];"
            f"[a][b]concat=n=2:v=1:a=0,format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-preset", "medium", out)
    return out


def _size(note: dict, quality: str) -> tuple[int, int]:
    sizes = workflows.WAN_SIZES[quality]
    return sizes[workflows.nearest_aspect(note["width"], note["height"], sizes)]


def _seed(seed) -> int:
    return random.randrange(2 ** 31) if seed is None or int(seed) < 0 else int(seed)


def _render(client, image: str, prompt: str, width: int, height: int, seconds: float,
            seed: int, negative: str, folder: str) -> str:
    progress("sending the start frame to ComfyUI")
    name = client.upload(image)
    graph = workflows.wan_i2v(name, prompt, width, height, workflows.frames(seconds),
                              seed=seed, negative=negative)
    outputs = client.run(graph, on_progress=progress, labels=workflows.WAN_LABELS)
    videos = [f for f in client.files(outputs)
              if f["filename"].lower().endswith((".mp4", ".webm", ".mov"))]
    if not videos:
        raise RuntimeError("ComfyUI finished without writing a video")
    return client.download(videos[0], folder)


def animate(picture: str, prompt: str, seconds: float = 5, quality: str = "draft",
            seed: int = -1, negative: str = "", client=None) -> dict:
    """A picture from the library, animated into a clip that is filed beside it."""
    note = library.get(picture)
    if note["kind"] != "image":
        raise ValueError(f"{picture} is a {note['kind']}, and only a picture can be animated; "
                         f"carry a clip on with studio_extend")
    width, height = _size(note, quality)
    seed = _seed(seed)
    tmp = tempfile.mkdtemp(prefix="studio-anim-")
    try:
        clip = _render(client or comfy.Comfy(), note["path"], prompt, width, height,
                       seconds, seed, negative, tmp)
        return library.add(clip, "clip", source=f"wan2.2-remix i2v from {picture}", move=True,
                           prompt=prompt, picture=picture, quality=quality, seed=seed)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extend(clip: str, prompt: str, seconds: float = 5, quality: str = "draft",
           seed: int = -1, negative: str = "", client=None) -> dict:
    """A clip carried on from its last frame, filed as a new, longer clip."""
    note = library.get(clip)
    if note["kind"] != "video":
        raise ValueError(f"{clip} is a {note['kind']}, and only a clip can be extended; "
                         f"animate a picture with studio_animate")
    width, height = _size(note, quality)
    seed = _seed(seed)
    tmp = tempfile.mkdtemp(prefix="studio-ext-")
    try:
        progress("taking the clip's last frame")
        start = last_frame(note["path"], os.path.join(tmp, "last.png"))
        more = _render(client or comfy.Comfy(), start, prompt, width, height,
                       seconds, seed, negative, tmp)
        progress("joining the new part on")
        out = join(note["path"], more, os.path.join(tmp, "extended.mp4"), width, height)
        return library.add(out, "clip", source=f"wan2.2-remix i2v extending {clip}", move=True,
                           prompt=prompt, extends=clip, quality=quality, seed=seed)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("animate", "extend"))
    ap.add_argument("--picture", default="")
    ap.add_argument("--clip", default="")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--seconds", type=float, default=5)
    ap.add_argument("--quality", choices=("draft", "final"), default="draft")
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--negative", default="")
    ap.add_argument("--job", default="")
    a = ap.parse_args()
    began = time.time()
    try:
        if a.action == "animate":
            note = animate(a.picture, a.prompt, a.seconds, a.quality, a.seed, a.negative)
        else:
            note = extend(a.clip, a.prompt, a.seconds, a.quality, a.seed, a.negative)
    except Exception as e:
        msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        print("FAILED " + (str(msg).strip() or type(e).__name__), flush=True)
        sys.exit(1)
    print("DONE " + json.dumps(dict(out=note["path"], seconds=note["seconds"],
                                    bytes=os.path.getsize(note["path"]),
                                    took=time.time() - began, asset=note["id"])), flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `$S studio/test_motion.py; $S studio/test_jobs.py; $S studio/test_assemble.py`
Expected: `8/8 passed`, and the jobs and assemble suites all pass.

- [ ] **Step 5: Commit**

```bash
git add studio/motion.py studio/test_motion.py studio/jobs.py studio/test_jobs.py
git commit -m "Animate library pictures into clips with Wan2.2-Remix and carry clips on from their last frame, as studio jobs that report ComfyUI's progress and name the clip they made"
```

---

### Task 5: Music from a description with ACE-Step

**Files:**
- Create: `studio/compose.py`, `studio/test_compose.py`

**Interfaces:**
- Consumes: `library.add`; ACE-Step's `acestep.handler.AceStepHandler`, `acestep.inference.{GenerationConfig, GenerationParams, generate_music}` and `acestep.llm_inference.LLMHandler`, the same API cartoon/score.py uses.
- Produces:
  - `compose.ACE_HOME`, `compose.MIN_SECONDS = 10.0`, `compose.MAX_SECONDS = 600.0`
  - `compose.params(description, seconds, lyrics="", seed=-1) -> dict`
  - `compose.device(torch) -> str`
  - `compose.compose(description, seconds, lyrics="", seed=-1, folder=None) -> tuple[str, dict]`
  - the CLI `python -m studio.compose --description D --seconds N [--lyrics L] [--seed S] --job J`, which prints `DONE {..., "asset": "music-xxxx"}`
  - `compose.PYTHON`, the path to `lectern/.musicvenv/bin/python`

- [ ] **Step 1: Write the failing test** — `studio/test_compose.py`:
```python
"""ACE-Step music, with ACE-Step and torch stood in for, so it runs anywhere.

    studio/.venv/bin/python studio/test_compose.py
"""
import os
import sys
import tempfile
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import compose  # noqa: E402

CALLS = {}


def fake_modules(cuda=True):
    torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: cuda, empty_cache=lambda: None),
                                  backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)))

    class Handler:
        def initialize_service(self, project_root, config_path, device):
            CALLS["dit"] = (project_root, config_path, device)
            return "ok", True

    class LLM:
        def initialize(self, checkpoint_dir, lm_model_path, backend, device):
            CALLS["lm"] = (checkpoint_dir, lm_model_path, backend, device)
            return "ok", True

    class Tensor:
        def __init__(self, a):
            self.a = a

        def detach(self):
            return self

        def cpu(self):
            return self

        def float(self):
            return self

        def numpy(self):
            return self.a

    def generate_music(dit, lm, params, config, save_dir=None):
        CALLS["params"] = params
        audio = np.zeros((2, int(params.duration * 48000)), dtype=np.float32)
        return types.SimpleNamespace(success=True, error="", audios=[{"tensor": Tensor(audio), "sample_rate": 48000}])

    inference = types.SimpleNamespace(GenerationParams=lambda **k: types.SimpleNamespace(**k),
                                      GenerationConfig=lambda **k: types.SimpleNamespace(**k),
                                      generate_music=generate_music)
    sys.modules.update({"torch": torch, "acestep": types.ModuleType("acestep"),
                        "acestep.handler": types.SimpleNamespace(AceStepHandler=Handler),
                        "acestep.inference": inference,
                        "acestep.llm_inference": types.SimpleNamespace(LLMHandler=LLM)})
    return torch


def test_length_is_kept_between_ten_seconds_and_ten_minutes():
    assert compose.params("piano", 5)["duration"] == 10.0
    assert compose.params("piano", 900)["duration"] == 600.0
    assert compose.params("piano", 42.26)["duration"] == 42.3


def test_instrumental_unless_lyrics_are_given():
    p = compose.params("sad piano", 30)
    assert p["instrumental"] is True and p["lyrics"] == "[Instrumental]"
    s = compose.params("torch song", 30, lyrics="[verse]\nYou came back")
    assert s["instrumental"] is False and s["lyrics"].startswith("[verse]")


def test_turbo_settings_and_a_given_seed():
    p = compose.params("x", 20, seed=7)
    assert (p["inference_steps"], p["shift"], p["seed"]) == (8, 3.0, 7)
    assert compose.params("x", 20)["seed"] >= 0


def test_device_prefers_cuda():
    assert compose.device(fake_modules(cuda=True)) == "cuda"
    assert compose.device(fake_modules(cuda=False)) == "cpu"


def test_compose_writes_a_wav_of_the_asked_length():
    fake_modules(cuda=True)
    path, p = compose.compose("melancholy synth, rain", 12, seed=3, folder=tempfile.mkdtemp())
    import soundfile as sf
    info = sf.info(path)
    assert abs(info.duration - 12.0) < 0.01 and info.channels == 2, info
    assert CALLS["dit"][2] == "cuda" and CALLS["lm"][2] == "pt"
    assert CALLS["params"].caption == "melancholy synth, rain"


def test_empty_description_is_refused():
    try:
        compose.params("  ", 30)
    except ValueError as e:
        assert "description" in str(e)
    else:
        raise AssertionError("empty description accepted")


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
```
`soundfile` must be in the studio venv. If it is missing locally, run this test with `/Users/john/git/adult/cartoon/.venv/bin/python`, which has numpy and soundfile.

- [ ] **Step 2: Run it to see it fail** — `$S studio/test_compose.py` → `cannot import name 'compose'`.

- [ ] **Step 3: Implement** — `studio/compose.py`:
```python
"""Music from a description, by ACE-Step 1.5 on this machine's GPU.

    lectern/.musicvenv/bin/python -m studio.compose --description "slow sad piano, rain on glass" --seconds 40 --job 1a2b3c

Runs under lectern/.musicvenv, where ACE-Step is installed. ACE-Step is MIT
licensed; its authors trained it on licensed and public-domain music and say
its output may be used commercially. It uses the turbo model (8 steps,
guidance baked in), as cartoon/score.py does. A cue is instrumental unless
lyrics are given, and 10 seconds to 10 minutes long. ACE_HOME holds
checkpoints/ (acestep-v15-turbo, acestep-5Hz-lm-1.7B, Qwen3-Embedding-0.6B,
vae). The cue is filed in the library as a music- id.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(HERE, "lectern", ".musicvenv", "bin", "python")
ACE_HOME = os.environ.get("ACE_HOME", os.path.expanduser("~/.cache/ace-step"))
DIT = os.environ.get("ACE_DIT", "acestep-v15-turbo")
LM = "acestep-5Hz-lm-1.7B"
TURBO = "turbo" in DIT
MIN_SECONDS, MAX_SECONDS = 10.0, 600.0


def progress(stage: str) -> None:
    print("PROGRESS " + json.dumps({"stage": stage}), flush=True)


def params(description: str, seconds: float, lyrics: str = "", seed: int = -1) -> dict:
    """ACE-Step's generation settings, as plain values."""
    if not description.strip():
        raise ValueError("music needs a description: instruments, mood, tempo, style")
    sung = bool(lyrics.strip())
    return dict(caption=description.strip(),
                lyrics=lyrics.strip() if sung else "[Instrumental]",
                instrumental=not sung,
                duration=round(max(MIN_SECONDS, min(MAX_SECONDS, float(seconds))), 1),
                inference_steps=8 if TURBO else 50, guidance_scale=7.0,
                shift=3.0 if TURBO else 1.0,
                seed=random.randrange(2_000_000_000) if seed is None or int(seed) < 0 else int(seed))


def device(torch) -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def compose(description: str, seconds: float, lyrics: str = "", seed: int = -1,
            folder: str | None = None) -> tuple[str, dict]:
    """Generate the cue and write it as a WAV; returns (path, settings)."""
    import soundfile as sf
    import torch
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    p = params(description, seconds, lyrics, seed)
    folder = folder or tempfile.mkdtemp(prefix="studio-music-")
    dev = device(torch)
    progress(f"loading ACE-Step on the {dev.upper()}")
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=ACE_HOME, config_path=DIT, device=dev)
    if not ok:
        raise RuntimeError(f"ACE-Step's music model did not load: {msg}")
    lm = LLMHandler()
    msg, ok = lm.initialize(checkpoint_dir=os.path.join(ACE_HOME, "checkpoints"), lm_model_path=LM,
                            backend="mlx" if dev == "mps" else "pt", device=dev)
    if not ok:
        raise RuntimeError(f"ACE-Step's planner did not load: {msg}")
    progress(f"composing {p['duration']:.0f} seconds")
    r = generate_music(dit, lm, GenerationParams(**p),
                       GenerationConfig(batch_size=1, use_random_seed=False, seeds=[p["seed"]],
                                        audio_format="wav"),
                       save_dir=os.path.join(folder, "ace-out"))
    if not r.success:
        raise RuntimeError(f"ACE-Step failed: {r.error}")
    a = r.audios[0]["tensor"].detach().cpu().float().numpy()
    path = os.path.join(folder, "music.wav")
    sf.write(path, a.T if a.ndim == 2 else a, int(r.audios[0]["sample_rate"]))
    del dit, lm
    if dev == "cuda":
        torch.cuda.empty_cache()
    return path, p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--description", required=True)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--lyrics", default="")
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--job", default="")
    a = ap.parse_args()
    began = time.time()
    folder = tempfile.mkdtemp(prefix="studio-music-")
    try:
        path, p = compose(a.description, a.seconds, a.lyrics, a.seed, folder)
        sys.path.insert(0, HERE)
        from studio import library
        note = library.add(path, "music", source=f"ace-step 1.5 ({DIT})", move=True,
                           description=p["caption"], lyrics=p["lyrics"], seed=p["seed"])
    except Exception as e:
        print("FAILED " + (str(e).strip() or type(e).__name__), flush=True)
        sys.exit(1)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    print("DONE " + json.dumps(dict(out=note["path"], seconds=note["seconds"],
                                    bytes=os.path.getsize(note["path"]),
                                    took=time.time() - began, asset=note["id"])), flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it to see it pass** — `$S studio/test_compose.py` (or the cartoon venv) → `6/6 passed`.

- [ ] **Step 5: Commit**

```bash
git add studio/compose.py studio/test_compose.py
git commit -m "Compose music cues from a description with ACE-Step 1.5 on the GPU, as a studio job run under the ACE-Step venv, filed in the library like the procedural beds"
```

---

### Task 6: The studio MCP server's new tools

**Files:**
- Modify: `studio/mcp_server.py`, `studio/test_server.py`, `studio/README.md`

**Interfaces:**
- Consumes: `images.PICTURES`, `images.paint`, `motion` (CLI through `jobs.start`), `compose.PYTHON`, `compose.MIN_SECONDS/MAX_SECONDS`, `jobs.new/start/status`, `library.get/said`.
- Produces three new MCP tools:
  - `studio_animate(picture, prompt, seconds=5, quality="draft", seed=-1)`
  - `studio_extend(clip, prompt, seconds=5, quality="draft", seed=-1)`
  - `studio_compose(description, seconds=30, lyrics="", seed=-1)`

  `studio_picture` paints with ComfyUI when `PICTURES == "comfyui"` and gains `count`, `negative` and `seed`. Every start message ends with the job id and suggests `watch_job`.

- [ ] **Step 1: Write the failing tests** — in `studio/test_server.py`:
- add `os.environ["STUDIO_COMFY"] = "http://127.0.0.1:9"` (unreachable) and `os.environ["STUDIO_PICTURES"] = "xai"` next to the other environment lines at the top;
- extend `TOOLS` with `"studio_animate", "studio_extend", "studio_compose"`;
- rename `test_nine_tools_every_one_prefixed` to `test_every_tool_prefixed`;
- add:
```python
import json  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from studio import library  # noqa: E402


def a_picture():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "f.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360",
                    "-frames:v", "1", p], check=True)
    return library.add(p, "pic")


def test_animate_refuses_what_is_not_a_picture():
    said = call("studio_animate", picture="clip-zzzz", prompt="x")
    assert "clip-zzzz" in said and "Not starting" in said, said


def test_animate_starts_a_job_that_reports_comfyui_missing():
    pic = a_picture()
    said = call("studio_animate", picture=pic["id"], prompt="she turns away", seconds=3)
    assert "job" in said and "watch_job" in said, said
    job = said.split(" as job ")[1].split(":")[0]
    for _ in range(60):
        status = call("studio_status", job=job)
        if "stopped" in status or "finished" in status:
            break
        time.sleep(0.5)
    assert "not answering" in status, status


def test_extend_refuses_a_picture():
    pic = a_picture()
    said = call("studio_extend", clip=pic["id"], prompt="x")
    assert "studio_animate" in said, said


def test_compose_refuses_an_empty_description():
    said = call("studio_compose", description="  ", seconds=20)
    assert "description" in said, said


def test_descriptions_mention_the_new_engines():
    tools = {t.name: t.description for t in anyio.run(S.mcp.list_tools)}
    assert "Wan" in tools["studio_animate"] and "5 seconds" in tools["studio_animate"]
    assert "last frame" in tools["studio_extend"]
    assert "ACE-Step" in tools["studio_compose"]
```

- [ ] **Step 2: Run them to see them fail** — `$S studio/test_server.py` → FAILs for the new tests (unknown tools).

- [ ] **Step 3: Implement** in `studio/mcp_server.py`:
- import `compose` alongside the other studio modules (`from studio import ..., compose`). `compose` only imports ACE-Step inside its functions, so importing it here is light.
- replace `studio_picture` with:
```python
@mcp.tool()
def studio_picture(
    prompt: Annotated[str, Field(description="What the picture shows: subject, setting, light, lens, style.")],
    aspect: Annotated[Literal[xai.ASPECTS], Field(description="Shape of the picture.")] = "16:9",
    resolution: Annotated[Literal[xai.RESOLUTIONS], Field(description="Detail, for xAI pictures only.")] = "2k",
    references: Annotated[list[str], Field(description="Up to 5 picture ids to work from (xAI only).")] = [],
    count: Annotated[int, Field(ge=1, le=4, description="How many takes to paint at once, 1 to 4.")] = 1,
    negative: Annotated[str, Field(description="What to keep out of the picture (Chroma only).")] = "",
    seed: Annotated[int, Field(description="-1 for new random takes; a number repeats a take.")] = -1,
) -> str:
    """Paint pictures from a description, filed in the library as pic- ids. On a machine with STUDIO_PICTURES=comfyui (the vast.ai studio) they come from Chroma1-HD, an uncensored open model, 1 to 4 takes at a time, about a megapixel each; elsewhere from xAI's image model, paid from prepaid credit, one at a time with up to 5 reference pictures. aspect is 16:9 (the default), 9:16, 1:1, 4:3, 3:4, 3:2, 2:3, 21:9 or auto; resolution is 1k, 1.5k or 2k (the default). Keyframes made here can be animated with studio_animate."""
    try:
        if images.PICTURES == "comfyui":
            if references:
                return "No picture was made: reference pictures need xAI; Chroma paints from the description alone."
            notes = images.paint(prompt, aspect, count, negative, seed)
            return "\n".join(library.said(n) for n in notes) + "\nShow them with show; animate one with studio_animate."
        return library.said(images.picture(prompt, aspect, resolution, references)) + "."
    except Exception as e:
        return f"No picture was made: {_sentence(e)}"
```
- add after `studio_assemble`:
```python
def _need(ref: str, kind: str, tool: str) -> str:
    """'' if ref is a library asset of this kind, else why not, as a sentence."""
    try:
        note = library.get(ref.strip())
    except KeyError as e:
        return f"Not starting: {_sentence(e)}"
    if note["kind"] != kind:
        return f"Not starting: {ref} is a {note['kind']}, not a {'picture' if kind == 'image' else 'clip'}; use {tool}."
    return ""


@mcp.tool()
def studio_animate(
    picture: Annotated[str, Field(description="The picture's id, such as pic-3f2a.")],
    prompt: Annotated[str, Field(description="What moves and how: the action, then the camera.")],
    seconds: Annotated[int, Field(ge=1, le=5, description="Length, 1 to 5 seconds.")] = 5,
    quality: Annotated[Literal["draft", "final"], Field(description="draft is 480p and quicker; final is 720p.")] = "draft",
    seed: Annotated[int, Field(description="-1 for a new random take; a number repeats one.")] = -1,
) -> str:
    """Animate a picture from the library into a silent clip of up to 5 seconds at 16 frames a second, with Wan 2.2 image-to-video (the uncensored Remix merge). Starts a job and returns at once with its id; follow it with watch_job in the chat, or studio_status. The clip is filed as a clip- id; studio_extend carries it on."""
    refused = _need(picture, "image", "studio_extend to carry a clip on")
    if refused:
        return refused
    job = jobs.new()
    jobs.start(job, "studio.motion", ["animate", "--picture", picture.strip(), "--prompt", prompt,
                                      "--seconds", str(seconds), "--quality", quality, "--seed", str(seed)],
               dict(name=f"animate {picture.strip()}"))
    return (f"Started animating {picture.strip()} as job {job}: {seconds} seconds at {quality} quality, "
            f"usually a minute or two (the first run of a session also loads the models). "
            f"Call watch_job with {job} to show its progress and the clip.")


@mcp.tool()
def studio_extend(
    clip: Annotated[str, Field(description="The clip's id, such as clip-9c01.")],
    prompt: Annotated[str, Field(description="What happens next: the action, then the camera.")],
    seconds: Annotated[int, Field(ge=1, le=5, description="How much to add, 1 to 5 seconds.")] = 5,
    quality: Annotated[Literal["draft", "final"], Field(description="draft is 480p; final is 720p.")] = "draft",
    seed: Annotated[int, Field(description="-1 for a new random take.")] = -1,
) -> str:
    """Carry a clip on: animate its last frame for up to 5 more seconds and join the two into one longer clip, filed as a new clip- id (the original stays). Repeat to build long shots. Starts a job and returns at once; follow it with watch_job."""
    refused = _need(clip, "video", "studio_animate to start from a picture")
    if refused:
        return refused
    job = jobs.new()
    jobs.start(job, "studio.motion", ["extend", "--clip", clip.strip(), "--prompt", prompt,
                                      "--seconds", str(seconds), "--quality", quality, "--seed", str(seed)],
               dict(name=f"extend {clip.strip()}"))
    return (f"Started extending {clip.strip()} by {seconds} seconds as job {job}. "
            f"Call watch_job with {job} to show its progress and the longer clip.")


@mcp.tool()
def studio_compose(
    description: Annotated[str, Field(description="The music: instruments, mood, tempo, genre.")],
    seconds: Annotated[float, Field(ge=10, le=600, description="Length, 10 to 600 seconds.")] = 30,
    lyrics: Annotated[str, Field(description="Words to sing, with [verse]/[chorus] tags; empty for instrumental.")] = "",
    seed: Annotated[int, Field(description="-1 for a new random take.")] = -1,
) -> str:
    """Compose a music cue from a description with ACE-Step 1.5, instrumental unless lyrics are given, 10 seconds to 10 minutes. Starts a job and returns at once; follow it with watch_job. The cue is filed as a music- id for studio_assemble. For a quick procedural bed from a mood instead, use studio_music."""
    try:
        compose.params(description, seconds, lyrics, seed)
    except ValueError as e:
        return f"Not starting: {_sentence(e)}"
    job = jobs.new()
    args = ["--description", description, "--seconds", str(seconds), "--seed", str(seed)]
    if lyrics.strip():
        args += ["--lyrics", lyrics]
    jobs.start(job, "studio.compose", args, dict(name="compose music"), python=compose.PYTHON)
    return (f"Started composing {seconds:.0f} seconds of music as job {job}; about a minute. "
            f"Call watch_job with {job} to show its progress and play the cue.")
```
- change `studio_status`'s docstring to: `"""How a job is going, or how it finished: an animation, an extension, a composed cue or an assembly. With no job id, the most recent one, and any others still running."""`, and its field description to `"The job id a studio tool gave. Leave it out for the most recent."`.
- in `studio_describe`, after the PICTURES line, add:
```python
        "ANIMATION (studio_animate, studio_extend): Wan 2.2 image-to-video, 1-5 seconds a call at 16 fps, "
        "draft 480p or final 720p; studio_extend carries a clip on from its last frame. Both are jobs.",
        "COMPOSED MUSIC (studio_compose): ACE-Step 1.5 from a description, 10-600 seconds, instrumental "
        "unless lyrics are given; a job.",
```
  Keep `describe`'s output a list of lines joined as it already is. If `describe` builds a single string some other way, put these two sentences in that same structure.
- in `studio/README.md`'s tool table, add rows for `studio_animate`, `studio_extend` and `studio_compose`, and change the `studio_picture` row to "a picture from Chroma1-HD on this machine's ComfyUI (`STUDIO_PICTURES=comfyui`) or xAI".

- [ ] **Step 4: Run all the studio suites to see them pass**

Run: `for t in server memory jobs timeline assemble music xai library speech comfy workflows paint motion compose; do $S studio/test_$t.py | tail -1; done`
Expected: every line shows `N/N passed`.

- [ ] **Step 5: Commit**

```bash
git add studio/mcp_server.py studio/test_server.py studio/README.md
git commit -m "Give the studio MCP server tools to animate pictures, extend clips and compose music, as jobs watch_job can follow, and paint pictures with Chroma1-HD when the machine has ComfyUI"
```

---

### Task 7: The Open WebUI tool for progress and inline media

**Files:**
- Create: `studio-vast/ROOT/opt/studio-vast/owui/studio_ui.py`, `studio-vast/ROOT/opt/studio-vast/owui/test_studio_ui.py`

**Interfaces:**
- Consumes: studio job logs in `STUDIO_WORK` (`JOB` / `PROGRESS {"stage","percent"?}` / `DONE {"out",...,"asset"?}` / `FAILED reason`), library notes `<id>.json` in `<STATIC_DIR>/studio/media`, and films in `<STATIC_DIR>/studio/renders`.
- Produces the Open WebUI tool module `studio_ui`, with:
  - `class Tools` and `Tools.Valves(work_dir, static_dir, poll_seconds, max_minutes)`
  - `async show(items: str, __event_emitter__=None)`
  - `async watch_job(job: str, __event_emitter__=None)`

  Both return `(HTMLResponse, str)` or a plain `str`. The module-level `_alive(job) -> bool` can be monkeypatched in tests.

- [ ] **Step 1: Write the failing test** — `test_studio_ui.py`:
```python
"""The studio_ui Open WebUI tool, without Open WebUI: needs only fastapi and pydantic.

    $OWUI_PY studio-vast/ROOT/opt/studio-vast/owui/test_studio_ui.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import studio_ui as U  # noqa: E402

STATIC = tempfile.mkdtemp(prefix="owui-static-")
WORK = tempfile.mkdtemp(prefix="studio-work-")
MEDIA = os.path.join(STATIC, "studio", "media")
RENDERS = os.path.join(STATIC, "studio", "renders")
os.makedirs(MEDIA)
os.makedirs(RENDERS)


def note(aid, kind, ext, **extra):
    path = os.path.join(MEDIA, aid + ext)
    open(path, "wb").write(b"x")
    n = dict(id=aid, path=path, kind=kind, width=832, height=480, seconds=5.06, sound=False, **extra)
    json.dump(n, open(os.path.join(MEDIA, aid + ".json"), "w"))
    return n


note("pic-1a2b", "image", ".png")
note("clip-9c01", "video", ".mp4")
open(os.path.join(RENDERS, "rooftop-aa11bb.mp4"), "wb").write(b"x")
json.dump(dict(id="pic-evil", path="/etc/passwd", kind="image", width=1, height=1),
          open(os.path.join(MEDIA, "pic-evil.json"), "w"))


def tools():
    t = U.Tools()
    t.valves.static_dir, t.valves.work_dir, t.valves.poll_seconds = STATIC, WORK, 0.05
    return t


class Events(list):
    async def __call__(self, event):
        self.append(event)


def run(coro):
    return asyncio.run(coro)


def test_show_puts_pictures_clips_and_films_in_the_chat():
    page, text = run(tools().show("pic-1a2b, clip-9c01 rooftop-aa11bb.mp4"))
    body = page.body.decode()
    assert '<img src="/static/studio/media/pic-1a2b.png"' in body, body
    assert '<video src="/static/studio/media/clip-9c01.mp4"' in body
    assert '<video src="/static/studio/renders/rooftop-aa11bb.mp4"' in body
    assert page.headers["content-disposition"] == "inline"
    assert "pic-1a2b" in text and "clip-9c01" in text and "rooftop-aa11bb.mp4" in text


def test_show_says_what_it_could_not_find():
    said = run(tools().show("pic-zzzz"))
    assert isinstance(said, str) and "pic-zzzz" in said and "not in the library" in said, said


def test_show_never_serves_files_outside_the_static_folder():
    said = run(tools().show("pic-evil"))
    assert isinstance(said, str) and "pic-evil" in said, said


def write_log(job, *lines):
    with open(os.path.join(WORK, f"job-{job}.log"), "w") as fh:
        fh.write('JOB {"name": "animate pic-1a2b"}\n' + "".join(x + "\n" for x in lines))


def test_watch_shows_progress_live_then_the_clip():
    U._alive = lambda job: True
    write_log("w1", 'PROGRESS {"stage": "high-noise pass, step 2 of 4", "percent": 50.0}')

    def finish():
        time.sleep(0.3)
        with open(os.path.join(WORK, "job-w1.log"), "a") as fh:
            fh.write('DONE {"out": "%s", "seconds": 5.06, "bytes": 1, "took": 9, "asset": "clip-9c01"}\n'
                     % os.path.join(MEDIA, "clip-9c01.mp4"))
    threading.Thread(target=finish).start()
    ev = Events()
    page, text = run(tools().watch_job("w1", __event_emitter__=ev))
    assert any(e["type"] == "status" and "high-noise pass" in e["data"]["description"]
               and "50%" in e["data"]["description"] for e in ev), ev
    assert any(e["type"] == "embeds" for e in ev)
    assert ev[-1]["type"] == "embeds" and ev[-1]["data"] == {"embeds": [], "replace": True}, ev[-1]
    assert "clip-9c01" in page.body.decode() and "clip-9c01" in text


def test_watch_reports_a_failure():
    U._alive = lambda job: True
    write_log("w2", "FAILED ComfyUI is not answering at http://127.0.0.1:18188")
    said = run(tools().watch_job("w2", __event_emitter__=Events()))
    assert "failed" in said and "not answering" in said, said


def test_watch_notices_a_job_whose_process_died():
    U._alive = lambda job: False
    write_log("w3", 'PROGRESS {"stage": "low-noise pass, step 1 of 4", "percent": 25.0}')
    old = time.time() - 60
    os.utime(os.path.join(WORK, "job-w3.log"), (old, old))
    said = run(tools().watch_job("w3", __event_emitter__=Events()))
    assert "stopped" in said, said


def test_watch_an_unknown_job():
    said = run(tools().watch_job("nope42", __event_emitter__=Events()))
    assert "no studio job" in said, said


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it to see it fail** — `$OWUI_PY studio-vast/ROOT/opt/studio-vast/owui/test_studio_ui.py` → `ModuleNotFoundError: No module named 'studio_ui'`.

- [ ] **Step 3: Implement** — `studio_ui.py`:
```python
"""
title: Studio
author: jhancock1975
description: Follows studio jobs with live progress, and shows pictures, clips, sound and finished films in the chat.
version: 1.0.0
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import subprocess
import time
import urllib.parse

from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ID = re.compile(r"^[a-z]+-[0-9a-z]{4}$")
VIDEO = (".mp4", ".webm", ".mov", ".mkv")
IMAGE = (".png", ".jpg", ".jpeg", ".webp")
STYLE = (
    "<style>body{margin:0;background:#151515;color:#ddd;font:14px system-ui,sans-serif}"
    ".grid{display:flex;flex-wrap:wrap;gap:10px;padding:8px}figure{margin:0}"
    "figure img,figure video{max-width:min(100%,640px);max-height:480px;border-radius:6px;display:block}"
    "figcaption{padding:4px 2px;color:#aaa}figcaption b{color:#fff}"
    ".bar{height:10px;background:#333;border-radius:5px;overflow:hidden;margin:8px}"
    ".bar div{height:100%;background:#4c8bf5;transition:width .5s}.stage{padding:4px 8px}</style>"
)
GRACE = 10  # seconds a job's process gets to appear after its log is written


def _alive(job: str) -> bool:
    """Whether a studio job's process is still running on this machine."""
    r = subprocess.run(["ps", "-A", "-ww", "-o", "args="], capture_output=True, text=True)
    return f"--job {job}" in r.stdout


def _read(log: str):
    with open(log) as fh:
        lines = [x.strip() for x in fh if x.strip()]
    head = {}
    if lines and lines[0].startswith("JOB "):
        try:
            head = json.loads(lines[0][4:])
        except ValueError:
            pass
    tail = next((x for x in reversed(lines) if x.startswith(("PROGRESS", "DONE", "FAILED"))), "")
    return head, tail


def _kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return "video" if ext in VIDEO else "image" if ext in IMAGE else "audio"


def _describe(n: dict) -> str:
    kind = n.get("kind") or _kind(n["path"])
    if kind == "image" and n.get("width"):
        return f"picture, {n['width']}x{n['height']}"
    if kind == "video" and n.get("seconds"):
        return f"clip, {n['seconds']:.1f} s" + (f", {n['width']}x{n['height']}" if n.get("width") else "")
    if kind == "audio" and n.get("seconds"):
        return f"sound, {n['seconds']:.1f} s"
    return kind


async def _noop(event):
    return None


class Tools:
    class Valves(BaseModel):
        work_dir: str = Field(default=os.environ.get("STUDIO_WORK", "/workspace/studio/work"),
                              description="Where studio jobs write their logs.")
        static_dir: str = Field(default=os.environ.get("STATIC_DIR", "/workspace/studio-webui/static"),
                                description="Open WebUI's static folder; the library and renders are in studio/.")
        poll_seconds: float = Field(default=2.0, description="How often a watched job is checked.")
        max_minutes: int = Field(default=60, description="How long watch_job follows one job.")

    def __init__(self):
        self.valves = self.Valves()

    # ----------------------------------------------------------- helpers

    def _media(self) -> str:
        return os.path.join(self.valves.static_dir, "studio", "media")

    def _renders(self) -> str:
        return os.path.join(self.valves.static_dir, "studio", "renders")

    def _url(self, path: str):
        """The /static URL of a file under the static folder; None for anything outside it."""
        root = os.path.realpath(self.valves.static_dir)
        real = os.path.realpath(path)
        if not real.startswith(root + os.sep) or not os.path.isfile(real):
            return None
        rel = os.path.relpath(real, root)
        return "/static/" + "/".join(urllib.parse.quote(p) for p in rel.split(os.sep))

    def _find(self, ref: str):
        ref = ref.strip().strip(",;")
        if ID.match(ref):
            p = os.path.join(self._media(), ref + ".json")
            if os.path.exists(p):
                with open(p) as fh:
                    return json.load(fh)
            return None
        name = os.path.basename(ref)
        for folder in (self._renders(), self._media()):
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                return {"id": name, "path": p, "kind": _kind(p)}
        return None

    def _figure(self, n: dict) -> str:
        url = html.escape(self._url(n["path"]) or "")
        kind = n.get("kind") or _kind(n["path"])
        if kind == "image":
            media = f'<img src="{url}" alt="{html.escape(n["id"])}">'
        elif kind == "video":
            media = f'<video src="{url}" controls loop playsinline preload="metadata"></video>'
        else:
            media = f'<audio src="{url}" controls preload="metadata"></audio>'
        return (f"<figure>{media}<figcaption><b>{html.escape(n['id'])}</b> "
                f"{html.escape(_describe(n))}</figcaption></figure>")

    @staticmethod
    def _page(body: str) -> HTMLResponse:
        return HTMLResponse(content=f"<!doctype html><html><head><meta charset='utf-8'>{STYLE}</head>"
                                    f"<body>{body}</body></html>",
                            headers={"Content-Disposition": "inline"})

    @staticmethod
    def _bar(name: str, stage: str, percent) -> str:
        width = f"{percent:.0f}%" if percent is not None else "100%"
        shade = "" if percent is not None else ";opacity:.35"
        return (f"<!doctype html><html><head><meta charset='utf-8'>{STYLE}</head><body>"
                f"<div class='stage'><b>{html.escape(name)}</b>: {html.escape(stage)}"
                f"{f' ({percent:.0f}%)' if percent is not None else ''}</div>"
                f"<div class='bar'><div style='width:{width}{shade}'></div></div></body></html>")

    # ------------------------------------------------------------- tools

    async def show(self, items: str, __event_emitter__=None):
        """
        Show pictures, clips, sounds or finished films in the chat, side by side with their ids, so they can be looked at and chosen from.
        :param items: Asset ids such as pic-3f2a, clip-9c01, voice-1a2b or music-77e1, or the file names of finished films, separated by commas or spaces.
        """
        found, missing = [], []
        for ref in [r for r in re.split(r"[,\s]+", items or "") if r]:
            n = self._find(ref)
            if n and self._url(n["path"]):
                found.append(n)
            else:
                missing.append(ref)
        if not found:
            names = ", ".join(missing) or "nothing was named"
            return f"Nothing to show: {names} {'is' if len(missing) == 1 else 'are'} not in the library or the finished films."
        body = "<div class='grid'>" + "".join(self._figure(n) for n in found) + "</div>"
        text = "Shown in the chat: " + "; ".join(f"{n['id']} ({_describe(n)})" for n in found)
        if missing:
            text += f". Not found: {', '.join(missing)}."
        return (self._page(body), text)

    async def watch_job(self, job: str, __event_emitter__=None):
        """
        Follow a studio job (an animation, extension, composed music or assembly) and show its progress live in the chat until it finishes, then show what it made. Call it right after a studio tool says it started a job.
        :param job: The job id the studio tool gave, such as 1a2b3c.
        """
        emit = __event_emitter__ or _noop
        job = (job or "").strip()
        log = os.path.join(self.valves.work_dir, f"job-{job}.log")
        if not re.fullmatch(r"\w+", job) or not os.path.exists(log):
            return f"There is no studio job {job}; studio_status lists the recent ones."
        began, last = time.time(), None
        name = f"Job {job}"
        try:
            while time.time() - began < self.valves.max_minutes * 60:
                head, tail = _read(log)
                name = head.get("name") or name
                if tail.startswith("DONE"):
                    d = json.loads(tail[4:])
                    await emit({"type": "status", "data": {"description": f"{name}: finished", "done": True}})
                    n = self._find(d["asset"]) if d.get("asset") else self._find(d.get("out", ""))
                    if n and self._url(n["path"]):
                        return (self._page("<div class='grid'>" + self._figure(n) + "</div>"),
                                f"Job {job} finished: {n['id']} ({_describe(n)}), shown in the chat.")
                    return f"Job {job} finished: {d.get('out')}."
                if tail.startswith("FAILED"):
                    await emit({"type": "status", "data": {"description": f"{name}: failed", "done": True}})
                    return f"Job {job} failed: {tail[6:].strip()}"
                if not _alive(job) and time.time() - os.path.getmtime(log) > GRACE:
                    await emit({"type": "status", "data": {"description": f"{name}: stopped", "done": True}})
                    return (f"Job {job} stopped before it finished: its process is gone, most likely "
                            f"because the machine restarted. Starting the same work again starts it over.")
                stage, percent = "started", None
                if tail.startswith("PROGRESS"):
                    d = json.loads(tail[8:])
                    stage, percent = d.get("stage", stage), d.get("percent")
                if (stage, percent) != last:
                    last = (stage, percent)
                    pct = f" ({percent:.0f}%)" if percent is not None else ""
                    await emit({"type": "status", "data": {"description": f"{name}: {stage}{pct}", "done": False}})
                    await emit({"type": "embeds", "data": {"embeds": [self._bar(name, stage, percent)],
                                                            "replace": True}})
                await asyncio.sleep(self.valves.poll_seconds)
            return (f"Job {job} is still running after {self.valves.max_minutes} minutes; "
                    f"call watch_job again to keep following it.")
        finally:
            await emit({"type": "embeds", "data": {"embeds": [], "replace": True}})
```

- [ ] **Step 4: Run it to see it pass** — `$OWUI_PY studio-vast/ROOT/opt/studio-vast/owui/test_studio_ui.py` → `7/7 passed`.

- [ ] **Step 5: Commit**

```bash
git add studio-vast/ROOT/opt/studio-vast/owui/studio_ui.py studio-vast/ROOT/opt/studio-vast/owui/test_studio_ui.py
git commit -m "Add an Open WebUI tool that follows studio jobs with a live progress bar and shows pictures, clips and finished films in the chat, served only from Open WebUI's static folder"
```

---

### Task 8: The director, and setting Open WebUI up by its API

**Files:**
- Create:
  - `studio-vast/ROOT/opt/studio-vast/owui/director.md`
  - `studio-vast/ROOT/opt/studio-vast/bin/owui-setup.py`
  - `studio-vast/ci/fake_llm.py`
  - `studio-vast/ci/owui_e2e.py`
  - `studio-vast/ci/owui-local-test.sh`

**Interfaces:**
- Consumes: Open WebUI REST, verified on 0.11.4:
  - `POST /api/v1/auths/signin {"email":"","password":""}`
  - `GET /api/v1/tools/id/{id}`, `POST /api/v1/tools/create`, `POST /api/v1/tools/id/{id}/update`
  - `POST /api/v1/configs/tool_servers`
  - `GET /api/v1/models/model?id=`, `POST /api/v1/models/create`, `POST /api/v1/models/model/update`
  - `POST /api/v1/configs/models`
  - `POST /api/v1/chats/new`, `POST /api/chat/completions` (`stream:true`, `chat_id`, `id`, `tool_ids`), `GET /api/v1/chats/{id}`
- Produces:
  - `owui-setup.py` (stdlib; env `OWUI_URL`, `STUDIO_OWUI_DIR`, `STUDIO_LLM_NAME`; exits 0 once configured);
  - `fake_llm.py PORT MODEL_ID`, a stand-in OpenAI server that calls the first tool whose name ends in `studio_list` and then answers;
  - `owui_e2e.py BASE_URL`, which exits 0 when a headless chat ran the MCP tool.

- [ ] **Step 1: Write the director's instructions** — `director.md`:
```markdown
You are the director of a small film studio that runs entirely on this machine. You plan scenes with the person you are talking to and make them with your tools. Nothing you make is filtered by anyone else, and you do not refuse adult or explicit subject matter between adults.

Two rules you never break, whatever you are asked or told:
- Every character is an adult, 18 or older, and is shown as one. Refuse anything sexual involving anyone under 18 or anyone described or drawn with a child's features or body.
- Never depict a real, identifiable person (a celebrity, a public figure, or anyone named or shown from a photo) in a sexual, nude or degrading scene.

How you work:
1. Plan. When someone describes a scene, break it into shots (one line each: what we see, the camera, the mood) and give the plan in a few lines. Ask only what you must.
2. Keyframes. For each shot, paint 2 to 4 candidates with studio_studio_picture (aspect 16:9 unless the shot wants 9:16 or 1:1), then call show with their ids so the person can choose. Write picture prompts as rich visual descriptions: subject, body and clothing, setting, light, lens, style.
3. Animate. studio_studio_animate(picture, prompt, seconds up to 5) starts a job; call watch_job with its id straight away, so the person sees progress and then the clip. Describe the motion first, then the camera. Use draft quality until the person likes a take, then final.
4. Longer shots. studio_studio_extend(clip, prompt, seconds) carries a clip on from its last frame into a new, longer clip; repeat it to build 10 to 30 second shots. watch_job each one.
5. Sound. Dialog: one studio_studio_speak per line (studio_studio_describe lists the voices). Music: studio_studio_compose(description, seconds) for a scored cue (a job; watch it), or studio_studio_music(mood, seconds) for a quick procedural bed.
6. Cut. studio_studio_assemble(edit) puts clips, pictures, voice lines, music and captions together; studio_studio_describe has the edit format and an example. Watch the job; the finished film then plays in the chat.
7. Always say the ids of what you made (pic-, clip-, voice-, music-), so the person can refer to them. studio_studio_list shows everything in the library; show plays any of it again.

Your other tools: cartoon_* makes 3D cartoons from a screenplay, lectern_* narrated lecture videos, highway_* highway-driving footage, studio_studio_card text cards. Their long renders are jobs too; their own *_status tools follow them.

Keep your replies short. Let the pictures and clips do the talking.
```

- [ ] **Step 2: Write the stand-in LLM** — `studio-vast/ci/fake_llm.py`:
```python
#!/usr/bin/env python3
"""A stand-in for vLLM in tests: an OpenAI-compatible server that calls one tool, then answers.

    python3 fake_llm.py PORT MODEL_ID

On a request with tools, where the last message is the user's, it calls the
first tool whose name ends in "studio_list" (streamed the way vLLM streams
tool calls). After the tool's result comes back, it answers in words,
quoting the result. Stdlib only.
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, MODEL = int(sys.argv[1]), sys.argv[2]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            return self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "test"}]})
        self._json(404, {})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = req.get("messages", [])
        tools = [t["function"]["name"] for t in req.get("tools") or []]
        wanted = next((n for n in tools if n.endswith("studio_list")), None)
        if wanted and msgs and msgs[-1].get("role") == "user":
            chunks = [{"role": "assistant", "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                                            "function": {"name": wanted, "arguments": ""}}]},
                      {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}]
            finish = "tool_calls"
        else:
            result = next((m.get("content") for m in reversed(msgs) if m.get("role") == "tool"), "")
            chunks = [{"role": "assistant", "content": f"The studio says: {result}"}]
            finish = "stop"
        if not req.get("stream"):
            msg = {"role": "assistant", "content": chunks[0].get("content")}
            if finish == "tool_calls":
                msg["tool_calls"] = [{"id": "call_1", "type": "function", "function": {"name": wanted, "arguments": "{}"}}]
            return self._json(200, {"id": "x", "object": "chat.completion", "model": MODEL, "created": int(time.time()),
                                    "choices": [{"index": 0, "message": msg, "finish_reason": finish}]})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for delta in chunks + [{}]:
            body = {"id": "x", "object": "chat.completion.chunk", "model": MODEL, "created": int(time.time()),
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None if delta else finish}]}
            self.wfile.write(f"data: {json.dumps(body)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
```

- [ ] **Step 3: Write the end-to-end checker** — `studio-vast/ci/owui_e2e.py`:
```python
#!/usr/bin/env python3
"""Check an Open WebUI set up by owui-setup.py, end to end, headless.

    python3 owui_e2e.py http://127.0.0.1:18081

Checks:
- the studio_ui tool and the four MCP tool servers are registered;
- the studio-director preset exists, is the default, and carries the director prompt;
- a chat sent through the API makes the LLM call the studio MCP server's
  studio_list, and the tool result lands in the saved chat.

Exits non-zero naming the first thing that is wrong. Stdlib only.
"""
import json
import sys
import time
import urllib.request
import uuid

BASE = sys.argv[1].rstrip("/")


def call(method, path, body=None, token=None, timeout=300):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def check(ok, what):
    print(("PASS  " if ok else "FAIL  ") + what)
    if not ok:
        sys.exit(1)


token = call("POST", "/api/v1/auths/signin", {"email": "", "password": ""})["token"]
tools = {t["id"] for t in call("GET", "/api/v1/tools/", token=token)}
check("studio_ui" in tools, f"studio_ui tool registered ({sorted(tools)})")
servers = call("GET", "/api/v1/configs/tool_servers", token=token)["TOOL_SERVER_CONNECTIONS"]
ids = sorted(s["info"]["id"] for s in servers)
check(ids == ["cartoon", "highway", "lectern", "studio"], f"four MCP tool servers ({ids})")
model = call("GET", "/api/v1/models/model?id=studio-director", token=token)
check(model and "director of a small film studio" in model["params"]["system"], "studio-director has the director prompt")
check("server:mcp:studio" in model["meta"]["toolIds"] and "studio_ui" in model["meta"]["toolIds"],
      "studio-director carries studio_ui and the MCP servers")
defaults = call("GET", "/api/v1/configs/models", token=token)
check(defaults.get("DEFAULT_MODELS") == "studio-director", f"studio-director is the default ({defaults.get('DEFAULT_MODELS')})")

chat = call("POST", "/api/v1/chats/new", {"chat": {"title": "e2e", "models": ["studio-director"], "messages": [], "history": {"messages": {}, "currentId": None}}}, token=token)
user_id, reply_id = str(uuid.uuid4()), str(uuid.uuid4())
call("POST", "/api/chat/completions", {
    "model": "studio-director", "stream": True, "chat_id": chat["id"], "id": reply_id,
    "messages": [{"role": "user", "content": "What is in the studio library?"}],
    "tool_ids": model["meta"]["toolIds"],
    "user_message": {"id": user_id, "role": "user", "content": "What is in the studio library?",
                     "parentId": None, "childrenIds": []}}, token=token, timeout=600)
saved = ""
for _ in range(60):
    saved = json.dumps(call("GET", f"/api/v1/chats/{chat['id']}", token=token))
    if "library is empty" in saved or "is in the library" in saved:
        break
    time.sleep(2)
check("library is empty" in saved or "in the library" in saved,
      "the LLM called the studio MCP server's studio_list and its answer is in the chat")
print("All Open WebUI checks passed")
```

- [ ] **Step 4: Write the setup script** — `studio-vast/ROOT/opt/studio-vast/bin/owui-setup.py`:
```python
#!/usr/bin/env python3
"""Set Open WebUI up for the studio through its REST API. Runs on every boot.

Idempotent:
- creates or updates the studio_ui tool;
- points the tool servers at the four MCP servers;
- creates or updates the Studio Director model (the director prompt plus
  every tool, on top of the LLM vLLM serves);
- makes it the default for new chats.

Open WebUI keeps its settings in its database after the first boot, so this
writes them through the API rather than relying on environment variables.
It waits for Open WebUI to answer first. Stdlib only.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("OWUI_URL", "http://127.0.0.1:18081")
HERE = os.environ.get("STUDIO_OWUI_DIR", "/opt/studio-vast/owui")
LLM = os.environ.get("STUDIO_LLM_NAME", "studio-llm")
DIRECTOR = "studio-director"
MCP = [("studio", "Studio", 8768, "Keyframes, animation, voices, music, cards and the edit"),
       ("cartoon", "Cartoon", 8769, "3D cartoons from a screenplay"),
       ("lectern", "Lectern", 8767, "Narrated lecture videos"),
       ("highway", "Highway", 8766, "Highway-driving footage")]


def call(method, path, body=None, token=None, timeout=60):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def wait_for_owui(limit=3600):
    began = time.time()
    while time.time() - began < limit:
        try:
            if call("GET", "/health", timeout=5)[0] == 200:
                return
        except OSError:
            pass
        time.sleep(3)
    sys.exit("studio: Open WebUI never answered; not configured")


def upsert(get_path, create_path, update_path, body, token):
    status, _ = call("GET", get_path, token=token)
    path = update_path if status == 200 else create_path
    status, reply = call("POST", path, body, token=token)
    if status != 200:
        raise RuntimeError(f"POST {path} answered HTTP {status}")
    return reply


def main():
    wait_for_owui()
    token = call("POST", "/api/v1/auths/signin", {"email": "", "password": ""})[1]["token"]
    with open(os.path.join(HERE, "studio_ui.py")) as fh:
        upsert("/api/v1/tools/id/studio_ui", "/api/v1/tools/create", "/api/v1/tools/id/studio_ui/update",
               {"id": "studio_ui", "name": "Studio", "content": fh.read(),
                "meta": {"description": "Live progress for studio jobs; pictures, clips and films in the chat."}},
               token)
    status, _ = call("POST", "/api/v1/configs/tool_servers", {"TOOL_SERVER_CONNECTIONS": [
        {"url": f"http://127.0.0.1:{port}/mcp", "path": "", "type": "mcp", "auth_type": "none", "key": "",
         "headers": None, "config": {"enable": True, "function_name_filter_list": "", "access_grants": []},
         "info": {"id": sid, "name": name, "description": about}} for sid, name, port, about in MCP]}, token)
    if status != 200:
        raise RuntimeError(f"tool servers: HTTP {status}")
    with open(os.path.join(HERE, "director.md")) as fh:
        system = fh.read()
    upsert(f"/api/v1/models/model?id={DIRECTOR}", "/api/v1/models/create", "/api/v1/models/model/update",
           {"id": DIRECTOR, "base_model_id": LLM, "name": "Studio Director",
            "meta": {"description": "Plans scenes and makes them: keyframes, animation, voices, music, the cut.",
                     "toolIds": ["studio_ui"] + [f"server:mcp:{sid}" for sid, *_ in MCP],
                     "capabilities": {"builtin_tools": False, "status_updates": True}},
            "params": {"system": system, "function_calling": "native", "temperature": 0.7,
                       "reasoning_effort": "low"},
            "access_grants": [], "is_active": True}, token)
    status, _ = call("POST", "/api/v1/configs/models", {"DEFAULT_MODELS": DIRECTOR, "DEFAULT_PINNED_MODELS": DIRECTOR,
                                                         "MODEL_ORDER_LIST": [DIRECTOR, LLM],
                                                         "DEFAULT_MODEL_METADATA": {}, "DEFAULT_MODEL_PARAMS": {}}, token)
    if status != 200:
        raise RuntimeError(f"default model: HTTP {status}")
    print("studio: Open WebUI configured (studio_ui, four MCP servers, studio-director as the default)", flush=True)


if __name__ == "__main__":
    for attempt in range(1, 6):
        try:
            main()
            break
        except Exception as e:
            print(f"studio: Open WebUI setup attempt {attempt} failed: {e}", flush=True)
            time.sleep(10 * attempt)
    else:
        sys.exit(1)
```
If `POST /api/v1/models/create` refuses a base model that no backend lists yet, which happens while vLLM is still loading, make `main()` first wait until `GET /api/models` lists `LLM`, polling every 15 s for up to 3 hours. Then create the preset. Find out which case applies in Step 6.

- [ ] **Step 5: Write the local integration test** — `studio-vast/ci/owui-local-test.sh`:
```bash
#!/usr/bin/env bash
# Run Open WebUI 0.11.4 on this Mac with the real studio MCP server and a stand-in LLM, set
# it up with owui-setup.py, and check it end to end with owui_e2e.py. Everything is stopped
# afterwards.
#   owui-local-test.sh OWUI_PYTHON STUDIO_PYTHON
set -euo pipefail
OWUI_PY=${1:?usage: owui-local-test.sh OWUI_PYTHON STUDIO_PYTHON}
STUDIO_PY=${2:?usage: owui-local-test.sh OWUI_PYTHON STUDIO_PYTHON}
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
T=$(mktemp -d)
trap 'kill $(jobs -p) 2>/dev/null || true; wait 2>/dev/null || true' EXIT
python3 "$HERE/fake_llm.py" 18990 studio-llm &
(cd "$REPO" && STUDIO_MEDIA="$T/static/studio/media" STUDIO_WORK="$T/work" "$STUDIO_PY" -m studio.mcp_server --host 127.0.0.1 --port 8768 > "$T/mcp.log" 2>&1) &
OWUI_BIN="$(dirname "$OWUI_PY")/open-webui"
(cd "$T" && DATA_DIR="$T/data" STATIC_DIR="$T/static" WEBUI_SECRET_KEY=test WEBUI_AUTH=False ENABLE_OLLAMA_API=False \
  OPENAI_API_BASE_URL=http://127.0.0.1:18990/v1 OPENAI_API_KEY=local OFFLINE_MODE=True \
  ENABLE_TITLE_GENERATION=False ENABLE_TAGS_GENERATION=False ENABLE_FOLLOW_UP_GENERATION=False \
  "$OWUI_BIN" serve --host 127.0.0.1 --port 18981 > "$T/owui.log" 2>&1) &
OWUI_URL=http://127.0.0.1:18981 STUDIO_OWUI_DIR="$REPO/studio-vast/ROOT/opt/studio-vast/owui" STUDIO_LLM_NAME=studio-llm \
  python3 "$REPO/studio-vast/ROOT/opt/studio-vast/bin/owui-setup.py"
python3 "$HERE/owui_e2e.py" http://127.0.0.1:18981
```
This test registers only the studio MCP server. The other three tool servers point at ports nothing listens on, which Open WebUI tolerates; `owui_e2e.py` only checks their registration.

- [ ] **Step 6: Run the local integration test until it passes**

Run: `bash studio-vast/ci/owui-local-test.sh "$OWUI_PY" /Users/john/git/adult/studio/.venv/bin/python`
Expected: six `PASS` lines and `All Open WebUI checks passed`. The first start takes about 80 s.

If any endpoint shape differs from the code (check `$T/owui.log`), fix `owui-setup.py` and `owui_e2e.py` against the scratch install's source in `site-packages/open_webui/routers/`.

- [ ] **Step 7: Commit**

```bash
git add studio-vast/ROOT/opt/studio-vast/owui/director.md studio-vast/ROOT/opt/studio-vast/bin/owui-setup.py studio-vast/ci/fake_llm.py studio-vast/ci/owui_e2e.py studio-vast/ci/owui-local-test.sh
git commit -m "Set Open WebUI up for the studio through its API on every boot, with a director prompt that plans shots, paints keyframes and animates them but keeps every character an adult and real people out of it, and a headless end-to-end check against a stand-in LLM"
```

---

### Task 9: The image

**Files:**
- Create:
  - `.dockerignore`
  - `studio-vast/Dockerfile`
  - `studio-vast/ROOT/opt/studio-vast/bin/studio-env.sh`
  - `studio-vast/ROOT/etc/vast_boot.d/71-studio.sh`
  - `studio-vast/ROOT/etc/supervisor/conf.d/studio.conf`
  - `studio-vast/ROOT/opt/supervisor-scripts/{vllm.sh,openwebui.sh,studio-mcp.sh}`
  - `studio-vast/ROOT/opt/studio-vast/provisioning/{all.yaml,none.yaml}`
  - `studio-vast/ROOT/etc/vast_capabilities.d/61-studio.yaml`
  - `studio-vast/ROOT/etc/vast_agents/studio.md`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - Install paths:

    | Path | What |
    |---|---|
    | `/opt/highway3d` | the repo |
    | `/opt/venvs/tools` | the venv the MCP servers and tools share, linked as `studio/.venv`, `cartoon/.venv`, `lectern/.mcpvenv`, `highway3d/.mcpvenv`, `highway/.venv` |
    | `/opt/highway3d/.ttsvenv`, `/opt/highway3d/lectern/.musicvenv` | system-site venvs on `/venv/main`'s torch |
    | `/opt/highway3d/lectern/.manimvenv` | Manim |
    | `/opt/vllm`, `/opt/openwebui` | vLLM and Open WebUI |
    | `/opt/blender` (and `/usr/local/bin/blender`) | Blender |
    | `/opt/gimp/AppRun-console` | GIMP's console launcher |

  - Environment from `studio-env.sh`: `STUDIO_*`, `DATA_DIR`, `STATIC_DIR`, `ACE_HOME`, `STUDIO_LLM_DIR`, `LECTERN_*`, `HIGHWAY_OUT_DIR`.
  - Supervisor programs: `vllm`, `openwebui`, `studio-mcp-studio`, `studio-mcp-cartoon`, `studio-mcp-lectern`, `studio-mcp-highway3d`.
  - `STUDIO_MODELS` env (`all` | `none`).

- [ ] **Step 1: Write `.dockerignore`** (repo root; the build context is the whole repo):
```
.git
.github
.claude
.cache
.superpowers
.work
.ttsvenv
renders
assets
docs
imagegen
**/.venv
**/.mcpvenv
**/.manimvenv
**/.musicvenv
**/__pycache__
**/*.mp4
**/*.wav
studio/media
studio/.work
.env
.env.*
*~
```

- [ ] **Step 2: Write `studio-env.sh`**:
```bash
# Paths and settings every studio program shares. Sourced, never run.
export STUDIO_ROOT=/opt/highway3d
export STUDIO_WEBUI=${WORKSPACE:-/workspace}/studio-webui
export DATA_DIR=$STUDIO_WEBUI/data
export STATIC_DIR=$STUDIO_WEBUI/static
export STUDIO_MEDIA=$STATIC_DIR/studio/media
export STUDIO_RENDERS=$STATIC_DIR/studio/renders
export LECTERN_RENDERS=$STUDIO_RENDERS
export HIGHWAY_OUT_DIR=$STUDIO_RENDERS
export STUDIO_WORK=${WORKSPACE:-/workspace}/studio/work
export STUDIO_PICTURES=comfyui
export STUDIO_COMFY=http://127.0.0.1:18188
export STUDIO_GIMP=/opt/gimp/AppRun-console
export BLENDER=/usr/local/bin/blender
export LECTERN_BLENDER=/usr/local/bin/blender
export ACE_HOME=${WORKSPACE:-/workspace}/models/ace-step
export STUDIO_LLM_DIR=${WORKSPACE:-/workspace}/models/llm/qwen3.8-27b-abliterated
export STUDIO_LLM_NAME=studio-llm
export STUDIO_OWUI_DIR=/opt/studio-vast/owui
export LECTERN_LLM_URL=http://127.0.0.1:18000/v1
export LECTERN_LLM_MODEL=studio-llm
export LECTERN_LLM_KEY=local
```

- [ ] **Step 3: Write the boot script** — `71-studio.sh`:
```bash
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
```

- [ ] **Step 4: Write the supervisor programs** — `studio.conf`. It holds six `[program:...]` blocks with these common lines:
```
environment=PROC_NAME="%(program_name)s"
autostart=true
startsecs=0
stopasgroup=true
killasgroup=true
stopsignal=TERM
stopwaitsecs=20
stdout_logfile=/dev/stdout
redirect_stderr=true
stdout_events_enabled=true
stdout_logfile_maxbytes=0
stdout_logfile_backups=0
```
The program-specific lines:

| Program | `command` | Restart |
|---|---|---|
| `vllm` | `/opt/supervisor-scripts/vllm.sh` | `autorestart=unexpected`, `exitcodes=0`, `stopwaitsecs=60` |
| `openwebui` | `/opt/supervisor-scripts/openwebui.sh` | `autorestart=unexpected`, `exitcodes=0` |
| `studio-mcp-studio` | `/opt/supervisor-scripts/studio-mcp.sh studio` | `autorestart=true` |
| `studio-mcp-cartoon` | `… studio-mcp.sh cartoon` | `autorestart=true` |
| `studio-mcp-lectern` | `… studio-mcp.sh lectern` | `autorestart=true` |
| `studio-mcp-highway3d` | `… studio-mcp.sh highway3d` | `autorestart=true` |

`vllm.sh`:
```bash
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
```

`openwebui.sh`:
```bash
#!/bin/bash
# Open WebUI on 127.0.0.1:18081, fronted by Caddy as "Studio Chat" (external 8081). Single user:
# Caddy's Open-button token is the login, so Open WebUI's own sign-in is off. owui-setup.py
# configures the tools and the director through the API once Open WebUI answers.
utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. "${utils}/exit_portal.sh" "Studio Chat"
. /opt/studio-vast/bin/studio-env.sh

mkdir -p "$DATA_DIR" "$STUDIO_MEDIA" "$STUDIO_RENDERS"
export WEBUI_SECRET_KEY="$(cat "$STUDIO_WEBUI/secret")"
export WEBUI_AUTH=False ENABLE_OLLAMA_API=False OFFLINE_MODE=True \
       OPENAI_API_BASE_URL=http://127.0.0.1:18000/v1 OPENAI_API_KEY=local \
       DEFAULT_MODELS=studio-director ENABLE_TAGS_GENERATION=False ENABLE_FOLLOW_UP_GENERATION=False \
       STUDIO_WORK STATIC_DIR
/usr/bin/python3 /opt/studio-vast/bin/owui-setup.py &
cd "$DATA_DIR"
pty /opt/openwebui/bin/open-webui serve --host 127.0.0.1 --port 18081
```

`studio-mcp.sh`:
```bash
#!/bin/bash
# One of the adult repo's MCP servers, on 127.0.0.1 only: Open WebUI calls them from inside the container.
utils=/opt/supervisor-scripts/utils
. "${utils}/logging.sh"
. "${utils}/cleanup_generic.sh"
. "${utils}/environment.sh"
. /opt/studio-vast/bin/studio-env.sh
cd "$STUDIO_ROOT"
PY=/opt/venvs/tools/bin/python
case "$1" in
    studio)    pty "$PY" -m studio.mcp_server --host 127.0.0.1 --port 8768 ;;
    cartoon)   pty "$PY" -m cartoon.mcp_server --host 127.0.0.1 --port 8769 ;;
    lectern)   pty "$PY" -m lectern.mcp_server --host 127.0.0.1 --port 8767 ;;
    highway3d) pty "$PY" highway3d/mcp_server.py --host 127.0.0.1 --port 8766 ;;
    *) echo "studio-mcp.sh: unknown server '$1'"; exit 2 ;;
esac
```
Check that each of the four servers' argparse accepts `--host`, `--port` and `--path` by grepping for `add_argument("--host"` in their `mcp_server.py`. If one lacks `--host`, leave the flag out: they all default to 127.0.0.1.

- [ ] **Step 5: Write the provisioning manifests**

`none.yaml`:
```yaml
# No model downloads (CI). The ComfyUI extension stays so workflow discovery still runs.
version: 1
extensions:
  - module: provisioner_comfyui
    config:
      comfyui_dir: "${WORKSPACE:-/workspace}/ComfyUI"
```

`all.yaml`:
```yaml
# Everything the studio runs, about 125 GB, all pinned to commits and downloadable without a token:
#   ComfyUI   Chroma1-HD + T5-XXL fp8 + Flux VAE (23 GB); Wan2.2-Remix NSFW i2v v3.0 high + low,
#             the NSFW UMT5 text encoder and the Wan 2.1 VAE (35.6 GB)
#   music     ACE-Step 1.5 checkpoints (9.4 GB)
#   voices    Kokoro-82M (0.3 GB), into the Hugging Face cache Kokoro reads
#   director  Qwen3.8-27B abliterated, BF16 (55.6 GB; vLLM quantises it to FP8 as it loads)
# Repos are fetched with `hf download --revision` in post_commands, because the provisioner
# cannot pin a whole repo. Plain paths only: ${...} would be expanded when the manifest loads.
version: 1
settings:
  concurrency: {hf_downloads: 4, wget_downloads: 4}
extensions:
  - module: provisioner_comfyui
    config:
      comfyui_dir: "${WORKSPACE:-/workspace}/ComfyUI"
downloads:
  - url: https://huggingface.co/lodestones/Chroma1-HD/resolve/0e0c60ece1e82b17cb7f77342d765ba5024c40c0/Chroma1-HD.safetensors
    dest: "${WORKSPACE:-/workspace}/ComfyUI/models/diffusion_models/Chroma1-HD.safetensors"
  - url: https://huggingface.co/mcmonkey/google_t5-v1_1-xxl_encoderonly/resolve/b13e9156c8ea5d48d245929610e7e4ea366c9620/t5xxl_fp8_e4m3fn.safetensors
    dest: "${WORKSPACE:-/workspace}/ComfyUI/models/text_encoders/t5xxl_enconly.safetensors"
  - url: https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/5b072540ef86570fecb8249c505f23d5bdeb88cd/split_files/vae/ae.safetensors
    dest: "${WORKSPACE:-/workspace}/ComfyUI/models/vae/Flux/ae.safetensors"
  - url: https://huggingface.co/FX-FeiHou/wan2.2-Remix/resolve/4369125a0f1157c6b8768df18b7e81bacd5fdc1f/NSFW/Wan2.2_Remix_NSFW_i2v_14b_high_lighting_fp8_e4m3fn_v3.0.safetensors
    dest: "${WORKSPACE:-/workspace}/ComfyUI/models/diffusion_models/Wan2.2_Remix_NSFW_i2v_14b_high_lighting_fp8_e4m3fn_v3.0.safetensors"
  - url: https://huggingface.co/FX-FeiHou/wan2.2-Remix/resolve/4369125a0f1157c6b8768df18b7e81bacd5fdc1f/NSFW/Wan2.2_Remix_NSFW_i2v_14b_low_lighting_fp8_e4m3fn_v3.0.safetensors
    dest: "${WORKSPACE:-/workspace}/ComfyUI/models/diffusion_models/Wan2.2_Remix_NSFW_i2v_14b_low_lighting_fp8_e4m3fn_v3.0.safetensors"
  - url: https://huggingface.co/NSFW-API/NSFW-Wan-UMT5-XXL/resolve/9202c70dd998d183f3dd58276d06689eeab9a174/nsfw_wan_umt5-xxl_fp8_scaled.safetensors
    dest: "${WORKSPACE:-/workspace}/ComfyUI/models/text_encoders/nsfw_wan_umt5-xxl_fp8_scaled.safetensors"
  - url: https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/ee6f4a40737a995bf5818954cfce6d59443b0f04/split_files/vae/wan_2.1_vae.safetensors
    dest: "${WORKSPACE:-/workspace}/ComfyUI/models/vae/wan_2.1_vae.safetensors"
post_commands:
  - hf download hexgrad/Kokoro-82M --revision f3ff3571791e39611d31c381e3a41a3af07b4987
  - hf download ACE-Step/Ace-Step1.5 --revision 19671f406d603126926c1b7e2adc169acbcade22 --local-dir /workspace/models/ace-step/checkpoints
  - hf download huihui-ai/Huihui-Qwen3.8-27B-abliterated --revision 739e3c5b89849f6c238ce1e5b70008612ae42cdd --local-dir /workspace/models/llm/qwen3.8-27b-abliterated && touch /workspace/models/llm/qwen3.8-27b-abliterated/.complete
```

- [ ] **Step 6: Write the capability and agent notes**

`61-studio.yaml`:
```yaml
# studio-vast: image identity (overrides the ComfyUI derivative's block)
image:
  name: Studio (uncensored director LLM, Chroma1-HD, Wan2.2-Remix, Kokoro, ACE-Step, Blender)
  readme: https://github.com/jhancock1975/highway3d/tree/studio-vast/studio-vast
  preinstalled: PyTorch + ComfyUI + vLLM + Open WebUI + Blender 5.2 + GIMP 3.2 + Manim/LaTeX + Kokoro + ACE-Step
```

`studio.md`: a short note for agents working on the instance. It lists:
- the services, with their internal addresses and portal ports (the Ports constraint above);
- the four MCP endpoints, `http://127.0.0.1:8766-8769/mcp`;
- where the library and renders live (`$STUDIO_MEDIA`, `$STUDIO_RENDERS`);
- how to call vLLM, as a curl to `http://127.0.0.1:18000/v1/chat/completions` with model `studio-llm`;
- how to tail a studio job (`$STUDIO_WORK/job-<id>.log`).

Write it as plain Markdown, like `imagegen/ROOT/etc/vast_agents/imagegen.md`.

- [ ] **Step 7: Write the Dockerfile** — `studio-vast/Dockerfile`:
```dockerfile
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
# to Mesa's software renderer.
RUN set -euo pipefail && \
    apt-get update && \
    apt-get install -y --no-install-recommends libsm6 libice6 libxt6t64 libopengl0 xz-utils unzip \
        texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
        texlive-science tipa dvisvgm libcairo2-dev libpango1.0-dev pkg-config && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://mirrors.ctan.org/install/fonts/doublestroke.tds.zip -o /tmp/doublestroke.zip && \
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

COPY . /opt/highway3d
COPY studio-vast/ROOT/ /

# The venvs the repo's tools expect, by the names its code uses:
#  - one shared venv for the MCP servers and the plain tools, linked under each tool's name;
#  - .ttsvenv (Kokoro) and lectern/.musicvenv (ACE-Step) on top of /venv/main's CUDA torch,
#    which is pinned so nothing replaces it;
#  - lectern/.manimvenv for Manim.
RUN set -euo pipefail && cd /opt/highway3d && \
    uv venv --python /usr/bin/python3.12 /opt/venvs/tools && \
    VIRTUAL_ENV=/opt/venvs/tools uv pip install --no-cache "mcp==2.2.0" numpy pillow pyyaml soundfile \
        fonttools scipy scikit-image imageio matplotlib websocket-client anyio uvicorn && \
    for d in studio/.venv cartoon/.venv lectern/.mcpvenv highway3d/.mcpvenv highway/.venv; do \
        ln -sfn /opt/venvs/tools "/opt/highway3d/$d"; done && \
    /venv/main/bin/python -m pip list --format=freeze 2>/dev/null \
        | grep -E '^(torch|torchvision|torchaudio)==' | sort > /tmp/torch-pins.txt && cat /tmp/torch-pins.txt && \
    uv venv --python /venv/main/bin/python --system-site-packages .ttsvenv && \
    VIRTUAL_ENV=/opt/highway3d/.ttsvenv uv pip install --no-cache -c /tmp/torch-pins.txt \
        "kokoro==0.9.4" "misaki[en]==0.9.4" soundfile pyyaml \
        "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl" && \
    .ttsvenv/bin/python -c "import kokoro, spacy, torch; spacy.load('en_core_web_sm'); print('TTS_OK', torch.__version__)" && \
    uv venv --python /venv/main/bin/python --system-site-packages lectern/.musicvenv && \
    VIRTUAL_ENV=/opt/highway3d/lectern/.musicvenv uv pip install --no-cache -c /tmp/torch-pins.txt \
        "git+https://github.com/ACE-Step/ACE-Step-1.5@ca1e85fe9430179831e6bc6be790c332190a3866" soundfile && \
    lectern/.musicvenv/bin/python -c "import acestep.handler, acestep.inference, acestep.llm_inference, torch; print('ACE_OK', torch.__version__)" && \
    uv venv --python /usr/bin/python3.12 lectern/.manimvenv && \
    VIRTUAL_ENV=/opt/highway3d/lectern/.manimvenv uv pip install --no-cache "manim==0.21.0" numpy pillow scipy pyyaml && \
    lectern/.manimvenv/bin/python -c "import manim; print('MANIM_OK', manim.__version__)" && \
    rm -f /tmp/torch-pins.txt

# Fonts, the Kenney cars and the Poly Haven assets the renderers fetch on first use, fetched now.
RUN set -euo pipefail && cd /opt/highway3d && \
    /opt/venvs/tools/bin/python fonts.py && \
    /opt/venvs/tools/bin/python -m cartoon.assets && \
    bash highway3d/setup.sh

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
```
Notes for the implementer:
- `highway3d/setup.sh` only calls Homebrew when blender or ffmpeg is missing; both are present by then.
- If ACE-Step's pyproject names a torch that the constraint rejects, read its `pyproject.toml` at that commit and pin to match the base image's torch. Do not let a second torch install. Check with `ls lectern/.musicvenv/lib/python3.12/site-packages | grep -c '^torch'` → 0.
- `pip list` in `/venv/main` must print `torch==2.10.0+cu128`. If it prints nothing, use `uv pip freeze --python /venv/main/bin/python`.

- [ ] **Step 8: Check that the shell scripts parse, and commit**

Run: `for f in studio-vast/ROOT/opt/supervisor-scripts/*.sh studio-vast/ROOT/etc/vast_boot.d/71-studio.sh studio-vast/ROOT/opt/studio-vast/bin/studio-env.sh; do bash -n "$f" && echo "ok $f"; done; python3 -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]; print('yaml ok')" studio-vast/ROOT/opt/studio-vast/provisioning/*.yaml`
Expected: `ok` for every script and `yaml ok`. If PyYAML is missing, use `/Users/john/git/adult/lectern/.mcpvenv/bin/python`.

```bash
git add .dockerignore studio-vast/Dockerfile studio-vast/ROOT
git commit -m "Add the studio-vast image: vast's ComfyUI image plus vLLM, Open WebUI, Blender 5.2, GIMP 3.2, Manim with TeX, Kokoro and ACE-Step, every renderer in this repo with its MCP server, and a manifest that fetches the director, Chroma1-HD, Wan2.2-Remix, ACE-Step and Kokoro on first boot"
```

---

### Task 10: CI: build, push, smoke-test on the runner

**Files:**
- Create: `.github/workflows/studio-vast.yml`, `studio-vast/ci/check-model-urls.py`, `studio-vast/ci/mcp_list.py`, `studio-vast/ci/smoke-test.sh`

**Interfaces:**
- Consumes: the image from Task 9; `imagegen/ci/compare-layers.py` (already on this branch, reused as is); `fake_llm.py` and `owui_e2e.py` from Task 8.
- Produces: `ghcr.io/jhancock1975/studio-vast:<sha>` and `:latest`. `:latest` moves only after the smoke test passes.

- [ ] **Step 1: Write `check-model-urls.py`**:
```python
#!/usr/bin/env python3
"""Check the studio's provisioning manifests without downloading anything.

- every download URL answers a token-less HEAD with 200, through Hugging Face's redirects,
  and reports a size;
- every destination is under /workspace, and no two share one;
- every `hf download REPO --revision SHA` in post_commands names a public, ungated repo at a
  commit that exists;
- none.yaml downloads nothing.

    check-model-urls.py PROVISIONING_DIR
"""
import json
import os
import re
import subprocess
import sys

import yaml


def head(url):
    env = {k: v for k, v in os.environ.items() if k not in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")}
    out = subprocess.run(["curl", "--connect-timeout", "10", "--max-time", "60", "-sIL", url],
                         capture_output=True, text=True, env=env).stdout
    statuses, length = [], None
    for line in out.splitlines():
        low = line.lower()
        if low.startswith("http/"):
            statuses.append(int(line.split()[1]))
            length = None
        elif low.startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    return statuses, length


def api(path):
    out = subprocess.run(["curl", "--connect-timeout", "10", "--max-time", "60", "-s",
                          f"https://huggingface.co/api/models/{path}"], capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except ValueError:
        return {}


def main(folder):
    bad = 0
    total = 0
    for name in sorted(os.listdir(folder)):
        m = yaml.safe_load(open(os.path.join(folder, name)))
        downloads, posts = m.get("downloads") or [], m.get("post_commands") or []
        print(f"== {name}: {len(downloads)} downloads, {len(posts)} post commands")
        if name == "none.yaml" and (downloads or posts):
            print("FAIL  none.yaml must download nothing")
            bad += 1
        dests = [d["dest"] for d in downloads]
        if len(dests) != len(set(dests)):
            print("FAIL  two downloads share a destination")
            bad += 1
        for d in downloads:
            if not d["dest"].startswith("${WORKSPACE:-/workspace}/"):
                print(f"FAIL  {d['dest']} is not under /workspace")
                bad += 1
            statuses, length = head(d["url"])
            if statuses and statuses[-1] == 200 and length:
                total += length
                print(f"ok    {length / 1e9:6.2f} GB  {d['url'].split('/resolve/')[0].split('huggingface.co/')[1]}  {os.path.basename(d['dest'])}")
            else:
                print(f"FAIL  {d['url']} answered {statuses}")
                bad += 1
        for cmd in posts:
            for repo, rev in re.findall(r"hf download (\S+) --revision ([0-9a-f]{40})", cmd):
                info = api(f"{repo}/revision/{rev}")
                if info.get("sha") == rev and not info.get("gated") and not info.get("private"):
                    size = sum(s.get("size", 0) or 0 for s in api(f"{repo}?blobs=true").get("siblings", []))
                    total += size
                    print(f"ok    {size / 1e9:6.2f} GB  {repo}@{rev[:8]} (public, not gated)")
                else:
                    print(f"FAIL  {repo}@{rev} is missing, gated or private")
                    bad += 1
    print(f"\ntotal about {total / 1e9:.1f} GB; {bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 2: Run it locally** — `/Users/john/git/adult/lectern/.mcpvenv/bin/python studio-vast/ci/check-model-urls.py studio-vast/ROOT/opt/studio-vast/provisioning`
Expected: every line `ok`, about 125 GB in total, `0 problem(s)`.

- [ ] **Step 3: Write `mcp_list.py`**, which runs inside the container under `/opt/venvs/tools`:
```python
#!/usr/bin/env python3
"""List an MCP server's tools over streamable HTTP; exit 1 if any expected tool is missing.

    mcp_list.py URL TOOL [TOOL ...]
"""
import sys

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main(url, want):
    async with streamable_http_client(url) as (read, write, *_):
        async with ClientSession(read, write) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
    missing = sorted(set(want) - names)
    print(f"{url}: {len(names)} tools" + (f"; missing {missing}" if missing else ""))
    sys.exit(1 if missing else 0)


anyio.run(main, sys.argv[1], sys.argv[2:])
```
Run it on the Mac against a studio MCP server started from the worktree: `/Users/john/git/adult/studio/.venv/bin/python -m studio.mcp_server --port 18768 &`, then `$S studio-vast/ci/mcp_list.py http://127.0.0.1:18768/mcp studio_animate studio_extend studio_compose`. That should print `14 tools`. If `streamable_http_client`'s signature differs in mcp 2.2.0, copy the connection code from `/Users/john/git/vast-render/mcp_client.py`, which already talks to these servers. Kill the server afterwards.

- [ ] **Step 4: Write `smoke-test.sh`**

It follows `imagegen/ci/smoke-test.sh` in full: the same `pass`/`fail`/`section`/`icurl`/`wait_until`/`diagnostics` helpers, the same certificate and tunnel-manager handling, and container name `studio-smoke`. The differences:
- **`docker create`:**
  - env: `-e STUDIO_MODELS=none`, `-e OPEN_BUTTON_TOKEN="$TOKEN"`, `-e VAST_TCP_PORT_1111=1111 -e VAST_TCP_PORT_8081=8081 -e VAST_TCP_PORT_8188=8188`, and `-e COMFYUI_ARGS="--disable-auto-launch --enable-cors-header --port 18188 --cpu"`;
  - `--shm-size=4g`;
  - copy `studio-vast/ci/` into the container at `/ci`: `docker cp studio-vast/ci "$NAME:/ci"`, before `docker start`.
- **Sections and checks**, in this order:
  1. *Provisioning:*
     - `wait_until 900` for provisioning;
     - the boot log contains `provisioning from /opt/studio-vast/provisioning/none.yaml`;
     - `provisioner --dry-run` accepts `all.yaml` and `none.yaml`.
  2. *ComfyUI:*
     - `/system_stats` answers;
     - `/object_info` has `WanImageToVideo`, `CreateVideo`, `SaveVideo`, `ModelSamplingAuraFlow`, `T5TokenizerOptions`, `EmptySD3LatentImage`, `ModelSamplingSD3` and `KSamplerAdvanced`, and `CLIPLoader` types include `wan` and `chroma`;
     - **graph validation:**
       - create empty placeholder files for every model name in `workflows.CHROMA` and `workflows.WAN` under `/workspace/ComfyUI/models/{diffusion_models,text_encoders,vae}` (with `vae/Flux/`), and copy a PNG to `/workspace/ComfyUI/input/start.png`;
       - POST `workflows.chroma_t2i(...)` and `workflows.wan_i2v("start.png", ...)` to `/prompt`, printed by `docker exec ... /opt/venvs/tools/bin/python -c "import json,sys; sys.path.insert(0,'/opt/highway3d'); from studio import workflows as W; print(json.dumps({'prompt': W.chroma_t2i('a fox', 512, 512)}))"`; expect HTTP 200 with a `prompt_id`;
       - then `POST /interrupt`, `POST /queue {"clear": true}` and remove the placeholders.
  3. *MCP servers:* `mcp_list.py` passes for each:
     - `http://127.0.0.1:8768/mcp` with `studio_picture studio_animate studio_extend studio_compose studio_speak studio_assemble`;
     - `8769` with `cartoon_make cartoon_status`;
     - `8767` with `lecture_render lecture_status`;
     - `8766` with `highway_render`.
  4. *Engines on the CPU*, each a `docker exec` with a PASS/FAIL line:
     - `blender -b --factory-startup --python-expr "<cube, EEVEE (BLENDER_EEVEE), 64x64, render.render(write_still=True) to /tmp/eevee.png>"`, then `test -s /tmp/eevee.png`;
     - `blender -b --python-expr "import sys; sys.path.insert(0,'/opt/highway3d'); import bpy, blender_gpu; print('GPU', blender_gpu.enable(bpy))"`, which prints `GPU CPU`;
     - Manim: write a `MathTex` scene of `\sum_{n=1}^\infty \frac{1}{n^2}=\frac{\pi^2}{6}` to `/tmp/t.py` and run `cd /tmp && /opt/highway3d/lectern/.manimvenv/bin/manim -ql --format png -s t.py T`; a PNG appears under `/tmp/media`;
     - `cd /opt/highway3d && studio/.venv/bin/python studio/test_engines.py`, which runs Kokoro, GIMP and ffmpeg for real (Kokoro downloads its weights from Hugging Face here);
     - `lectern/.musicvenv/bin/python -c "import acestep.handler"`;
     - `/opt/vllm/bin/python -c "import vllm"`;
     - ffmpeg has `xfade`, `zoompan`, `sidechaincompress` and `loudnorm`.
  5. *Test suites inside the image:*
     - `cd /opt/highway3d`, then every `studio/test_*.py` except `test_engines.py` (done above) under `studio/.venv/bin/python`;
     - `cartoon/test_cartoon.py` under `cartoon/.venv/bin/python`;
     - `test_forgiving.py` and `lectern/test_status.py` under `lectern/.mcpvenv/bin/python`;
     - `python3 test_blender_gpu.py`;
     - `/opt/openwebui/bin/python /opt/studio-vast/owui/test_studio_ui.py`.
  6. *Open WebUI:*
     - `wait_until 900` for `icurl -f http://127.0.0.1:18081/health`;
     - start the stand-in LLM inside the container on vLLM's port (vLLM is not running with `none`): `docker exec -d "$NAME" python3 /ci/fake_llm.py 18000 studio-llm`;
     - run `docker exec "$NAME" python3 /ci/owui_e2e.py http://127.0.0.1:18081`, which must pass. It proves Open WebUI → MCP → studio works inside the image.
  7. *Caddy:* for ports 1111, 8081 and 8188, anonymous requests get 401 and the token gets 200 or 302 (as in imagegen).
  8. *Services:*
     - `supervisorctl status` shows `comfyui`, `openwebui`, `caddy`, `instance_portal` and the four `studio-mcp-*` programs RUNNING;
     - `vllm` is EXITED, and its log says `vLLM not started`.

Write it as complete bash, copying the helper functions verbatim from `imagegen/ci/smoke-test.sh`. Write each check as a `PASS`/`FAIL` line that increments `FAILURES`, and end with the same summary and `diagnostics` call.

- [ ] **Step 5: Write the workflow** — `.github/workflows/studio-vast.yml`. Copy `imagegen.yml` with these changes:
- `name: studio-vast`.
- Trigger `paths`:
  - `studio-vast/**`, `studio/**`, `cartoon/**`, `lectern/**`, `highway3d/**`, `highway/**`, `relativity/**`, `scripts/**`
  - `fonts.py`, `forgiving.py`, `blender_gpu.py`, `.dockerignore`, `.github/workflows/studio-vast.yml`
- `concurrency.group: studio-vast-${{ github.ref }}`.
- `env.IMAGE: ghcr.io/${{ github.repository_owner }}/studio-vast`.
- Job `model-urls` runs `studio-vast/ci/check-model-urls.py studio-vast/ROOT/opt/studio-vast/provisioning`.
- Job `image`:
  - `timeout-minutes: 300`;
  - the same free-disk step, with an extra `sudo swapoff -a && sudo rm -f /mnt/swapfile || true`;
  - build with `docker buildx build . -f studio-vast/Dockerfile ...`, with the same labels and cache flags;
  - compare layers with `base=$(grep -m1 '^ARG BASE_IMAGE=' studio-vast/Dockerfile | cut -d= -f2)` and `python3 imagegen/ci/compare-layers.py "$base" "$IMAGE:<sha>"`;
  - smoke test with `bash studio-vast/ci/smoke-test.sh "$IMAGE:<sha>" smoke-out`;
  - artifacts and the `:latest` step as before.

- [ ] **Step 6: Push and run it until green**

```bash
git add .github/workflows/studio-vast.yml studio-vast/ci
git commit -m "Build the studio-vast image in GitHub Actions, check its model URLs, and boot it on the runner's CPU to check every service, engine and test suite, including a headless chat through Open WebUI to the studio's MCP server, before moving :latest"
git push -u origin studio-vast
gh run watch --repo jhancock1975/highway3d $(gh run list --repo jhancock1975/highway3d --workflow studio-vast.yml --branch studio-vast --limit 1 --json databaseId --jq '.[0].databaseId')
```
Expected: both jobs succeed, and the summary lists `ghcr.io/jhancock1975/studio-vast:<sha>` and `:latest`.

On failure:
1. Download the `smoke-test-output` artifact (`gh run download`) and read `container.log` and the FAIL lines.
2. Fix the cause in the Dockerfile, scripts or code, commit with a sentence saying what was wrong, and push again. Use `superpowers:systematic-debugging` for anything not obvious.
3. Likely trouble spots: the runner's disk (watch the `df` output; if the build runs out, move the vLLM install to first boot); the vLLM wheel URL; ACE-Step's torch pin; GIMP's AppImage on 24.04; Blender's software EGL for EEVEE.

- [ ] **Step 7: Make the GHCR package public** (once, after the first push): `gh api -X PATCH /user/packages/container/studio-vast -f visibility=public`. If that endpoint refuses (visibility may only change in the web UI), open `https://github.com/users/jhancock1975/packages/container/studio-vast/settings` in Chrome and set it to Public under "Danger Zone". Ask the user before clicking the confirm button, because it publishes the package. Confirm with `curl --connect-timeout 2 --max-time 5 -s -o /dev/null -w '%{http_code}' https://ghcr.io/v2/jhancock1975/studio-vast/manifests/latest -H "Authorization: Bearer $(curl -s 'https://ghcr.io/token?scope=repository:jhancock1975/studio-vast:pull' | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')" -H 'Accept: application/vnd.oci.image.index.v1+json'` → `200`.

---

### Task 11: The launch script

**Files (outside the repo, in `/Users/john/git/vast-render`):**
- Create: `vast-studio.sh`
- Modify: `README.md`

**Interfaces:**
- Consumes: `VAST_API_KEY` and `STUDIO_WEB_PASSWORD` (created if missing) from `.env`; the image `ghcr.io/jhancock1975/studio-vast:latest`.
- Produces: `./vast-studio.sh [--wait] [OFFER_ID]`. It logs to `logs/` and prints `created instance <id>`. With `--wait`, it also prints `chat ready: https://<ip>:<port>`. It never prints the password.

- [ ] **Step 1: Write the script**, based on `vast-uncensored-model.sh`:
```bash
#!/usr/bin/env bash
# Rent an RTX PRO 6000 (96 GB) on vast.ai and start the studio on it: an uncensored director you
# chat with at "Studio Chat", painting, animating, voicing and scoring films on the same machine.
#   ./vast-studio.sh                 cheapest matching offer
#   ./vast-studio.sh OFFER_ID        a specific offer from the search
#   ./vast-studio.sh --wait [ID]     also wait until the chat answers (first boot downloads ~125 GB)
set -euo pipefail

cd "$(dirname "$0")"
set -a; . ./.env; set +a

mkdir -p logs
LOG_FILE="$PWD/logs/vast-studio-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "logging to $LOG_FILE"

WAIT=0
if [ "${1:-}" = "--wait" ]; then WAIT=1; shift; fi

# A password for the instance's web apps besides vast's Open button, so scripts can reach the
# chat too (?token=...). Kept in .env, which git ignores; never printed.
if [ -z "${STUDIO_WEB_PASSWORD:-}" ]; then
  STUDIO_WEB_PASSWORD=$(openssl rand -hex 16)
  printf '\nSTUDIO_WEB_PASSWORD=%s\n' "$STUDIO_WEB_PASSWORD" >> .env
  echo "made a web password for the studio and saved it in .env as STUDIO_WEB_PASSWORD"
fi

# One RTX PRO 6000 with room for ~125 GB of models, RAM for vLLM and Blender, and a fast line.
# Hosts in China stall pulling from ghcr.io and Hugging Face.
QUERY='num_gpus=1 gpu_name in [RTX_PRO_6000_WS,RTX_PRO_6000_S,RTX_PRO_6000_Max-Q] gpu_ram>=90 disk_space>=300 cpu_ram>=96 cuda_vers>=12.9 reliability>0.98 verified=true rentable=true direct_port_count>=8 inet_down>=1000 geolocation!=CN'
OFFERS=$(vastai --api-key "$VAST_API_KEY" search offers "$QUERY" -o 'dph' --raw)

echo "cheapest offers:"
echo "$OFFERS" | jq -r '.[:8][] | "  \(.id)  \(.gpu_name)  $\(.dph_total * 1000 | round / 1000)/hr  \(.geolocation)  \(.inet_down|floor) Mbps"'

OFFER_ID="${1:-$(echo "$OFFERS" | jq -r '.[0].id // empty')}"
if [ -z "$OFFER_ID" ]; then
  echo "no offers match the search, nothing rented" >&2
  exit 1
fi
echo "renting offer $OFFER_ID"

RESULT=$(vastai --api-key "$VAST_API_KEY" create instance "$OFFER_ID" \
  --image ghcr.io/jhancock1975/studio-vast:latest \
  --disk 300 --jupyter --direct \
  --env "-p 1111:1111 -p 8081:8081 -p 8188:8188 -p 8080:8080 -e OPEN_BUTTON_PORT=8081 -e OPEN_BUTTON_TOKEN=1 -e STUDIO_MODELS=all -e WEB_PASSWORD=$STUDIO_WEB_PASSWORD" \
  --onstart-cmd 'entrypoint.sh' --label studio --raw)

# the CLI exits 0 even when the API rejects the request, so check the reply
INSTANCE_ID=$(echo "$RESULT" | jq -r '.new_contract // empty' 2>/dev/null || true)
if [ -z "$INSTANCE_ID" ]; then
  echo "create instance failed for offer $OFFER_ID${RESULT:+: $RESULT}" >&2
  exit 1
fi
echo "created instance $INSTANCE_ID"
echo "open it:    the Open button on https://cloud.vast.ai/instances/ (goes straight to Studio Chat)"
echo "destroy it: vastai destroy instance $INSTANCE_ID"
[ "$WAIT" = 1 ] || exit 0

echo "waiting for the chat (the first boot downloads about 125 GB of models)..."
for _ in $(seq 1 240); do
  J=$(vastai --api-key "$VAST_API_KEY" show instance "$INSTANCE_ID" --raw 2>/dev/null || echo '{}')
  IP=$(echo "$J" | jq -r '.public_ipaddr // empty')
  PORT=$(echo "$J" | jq -r '.ports["8081/tcp"][0].HostPort // empty' 2>/dev/null)
  STATE=$(echo "$J" | jq -r '.actual_status // "?"')
  if [ -n "$IP" ] && [ -n "$PORT" ]; then
    CODE=$(curl --connect-timeout 2 --max-time 5 -k -s -o /dev/null -w '%{http_code}' \
           "https://$IP:$PORT/api/models?token=$STUDIO_WEB_PASSWORD" || true)
    if [ "$CODE" = 200 ] || [ "$CODE" = 401 ]; then
      echo "chat ready: https://$IP:$PORT  (log in with the Open button, or add ?token=\$STUDIO_WEB_PASSWORD)"
      exit 0
    fi
  fi
  echo "  $(date +%H:%M:%S) $STATE ${IP:+$IP:$PORT}"
  sleep 30
done
echo "the chat did not answer within two hours; check the instance's logs on cloud.vast.ai" >&2
exit 1
```
`401` from Open WebUI's own API means Caddy let the request through and Open WebUI answered, so it counts as ready.

- [ ] **Step 2: Test the script's logic with a stand-in `vastai`** (no rental). Reuse the earlier stand-in pattern: a fake `vastai` early on `PATH` that passes `search offers` to the real CLI and answers `create instance` with `{"success": true, "new_contract": 12345678}`. Then run `PATH=fakebin:$PATH ./vast-studio.sh`. Expected:
- the offers list shows only RTX PRO 6000 cards and no hosts in China;
- `created instance 12345678`;
- `.env` gains `STUDIO_WEB_PASSWORD`, and the log does not contain its value (`grep -c` → 0).

If the search returns nothing, check `vastai search offers 'gpu_name=RTX_PRO_6000_WS' --raw | jq length` and fix the query's GPU names. Delete the stand-in's log afterwards.

- [ ] **Step 3: Document it** — add a `## vast-studio.sh` section to `README.md` covering:
- what it rents, and why each search filter is there;
- the `--wait` flag;
- `STUDIO_WEB_PASSWORD` in `.env`;
- the Open button;
- how to destroy the instance.

No commit: `vast-render` is not a git repository.

---

### Task 12: End-to-end on a rented RTX PRO 6000

**Files (outside the repo, in `/Users/john/git/vast-render`):**
- Create: `acceptance.py`; outputs go to `acceptance-out/`, added to `.gitignore`

**Interfaces:**
- Consumes: a running instance from `vast-studio.sh`, and Open WebUI's API through Caddy (`?token=$STUDIO_WEB_PASSWORD` on every request plus Open WebUI's Bearer token).
- Produces: `acceptance.py INSTANCE_ID`, which exits 0 only when the film checks pass, and writes a contact sheet `acceptance-out/<id>-frames.png` and `acceptance-out/<id>.mp4`.

- [ ] **Step 1: Write `acceptance.py`** (stdlib + ffmpeg/ffprobe on the Mac):
```python
#!/usr/bin/env python3
"""Drive the studio's director end to end on a rented instance, and check the film it makes.

    ./acceptance.py INSTANCE_ID

It talks to Open WebUI through vast's Caddy (?token= with STUDIO_WEB_PASSWORD from .env) and
plays the person's side of a short conversation:
  1. two keyframes, 2. animate one, 3. extend it, 4. a voice line, composed music, and the cut.
After each turn it checks the director made what was asked (pic-, clip-, voice-, music-
ids, and a film in the renders). Then it downloads the film and checks it has video and
audible sound of a plausible length, and writes a contact sheet of six frames to
acceptance-out/ for a person (or Claude) to look at.
"""
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = dict(line.strip().split("=", 1) for line in open(os.path.join(HERE, ".env"))
           if "=" in line and not line.startswith("#"))
CTX = ssl._create_unverified_context()      # the instance's own certificate
OUT = os.path.join(HERE, "acceptance-out")


def instance(iid):
    r = subprocess.run(["vastai", "--api-key", ENV["VAST_API_KEY"], "show", "instance", str(iid), "--raw"],
                       capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    return j["public_ipaddr"], j["ports"]["8081/tcp"][0]["HostPort"]


class Chat:
    def __init__(self, base):
        self.base, self.token = base, None
        self.token = self.call("POST", "/api/v1/auths/signin", {"email": "", "password": ""})["token"]

    def call(self, method, path, body=None, timeout=120, raw=False):
        sep = "&" if "?" in path else "?"
        url = f"{self.base}{path}{sep}token={urllib.parse.quote(ENV['STUDIO_WEB_PASSWORD'])}"
        req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            data = r.read()
        return data if raw else (json.loads(data) if data else None)


def ids(text, prefix):
    return list(dict.fromkeys(re.findall(rf"\b{prefix}-[0-9a-z]{{4}}\b", text)))


def main(iid):
    os.makedirs(OUT, exist_ok=True)
    ip, port = instance(iid)
    chat = Chat(f"https://{ip}:{port}")
    print(f"studio at https://{ip}:{port}; waiting for the director's model...")
    for _ in range(240):
        models = [m["id"] for m in chat.call("GET", "/api/models").get("data", [])]
        if "studio-director" in models and "studio-llm" in models:
            break
        time.sleep(30)
    else:
        sys.exit("FAIL: studio-llm never appeared (is vLLM up? see the instance's logs)")
    preset = chat.call("GET", "/api/v1/models/model?id=studio-director")
    c = chat.call("POST", "/api/v1/chats/new", {"chat": {"title": "acceptance", "models": ["studio-director"],
                                                       "messages": [], "history": {"messages": {}, "currentId": None}}})
    history = []

    def turn(text, expect):
        user_id, reply_id = str(uuid.uuid4()), str(uuid.uuid4())
        history.append({"role": "user", "content": text})
        print(f"\n> {text}")
        chat.call("POST", "/api/chat/completions", {
            "model": "studio-director", "stream": True, "chat_id": c["id"], "id": reply_id, "messages": history,
            "tool_ids": preset["meta"]["toolIds"],
            "user_message": {"id": user_id, "role": "user", "content": text, "parentId": None, "childrenIds": []}},
            timeout=3600)
        saved = json.dumps(chat.call("GET", f"/api/v1/chats/{c['id']}"))
        reply = next((m.get("content", "") for m in reversed(
            chat.call("GET", f"/api/v1/chats/{c['id']}")["chat"].get("messages", [])) if m.get("role") == "assistant"), "")
        history.append({"role": "assistant", "content": reply})
        print(reply[:800])
        got = expect(saved)
        if not got:
            open(os.path.join(OUT, f"{iid}-chat.json"), "w").write(saved)
            sys.exit(f"FAIL: that turn did not make what was asked; the chat is in acceptance-out/{iid}-chat.json")
        return got

    pics = turn("A woman in a red raincoat on a rain-soaked neon-lit rooftop at night, the city behind her. "
                "Paint two 16:9 keyframes for the opening shot and show them.", lambda s: ids(s, "pic"))
    clip = turn(f"Animate {pics[0]}: she turns toward the camera as the rain falls, slow push-in. "
                "5 seconds, draft quality. Watch the job.", lambda s: ids(s, "clip"))[-1]
    longer = turn(f"Extend {clip} by 5 seconds: she walks toward the camera. Watch the job.",
                  lambda s: [x for x in ids(s, "clip") if x != clip])[-1]
    film = turn(f"Make one voice line, 'You came back.', in voice af_heart. Compose 20 seconds of melancholy synth "
                f"music with studio_compose and watch it. Then assemble {longer} with the voice at 2 seconds, the "
                f"music under everything, and captions on, name it rooftop, watch the job and show me the film.",
                lambda s: re.findall(r"rooftop-[0-9a-f]{6}\.mp4", s))[-1]

    path = os.path.join(OUT, f"{iid}.mp4")
    open(path, "wb").write(chat.call("GET", f"/static/studio/renders/{film}", raw=True, timeout=600))
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                                      capture_output=True, text=True, check=True).stdout)
    kinds = {s["codec_type"] for s in probe["streams"]}
    seconds = float(probe["format"]["duration"])
    vol = subprocess.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    mean = float(re.search(r"mean_volume: (-?[\d.]+) dB", vol).group(1))
    sheet = os.path.join(OUT, f"{iid}-frames.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf",
                    f"fps=6/{max(seconds, 1):.2f},scale=480:-2,tile=3x2", "-frames:v", "1", sheet], check=True)
    ok = {"video and audio streams": {"video", "audio"} <= kinds,
          "at least 9 seconds long": seconds >= 9,
          "audible sound (mean above -45 dB)": mean > -45}
    for what, good in ok.items():
        print(("PASS  " if good else "FAIL  ") + what)
    print(f"film: {path} ({seconds:.1f} s, mean volume {mean:.1f} dB); frames: {sheet}")
    sys.exit(0 if all(ok.values()) else 1)


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 2: Rent, run, look, destroy**
1. `./vast-studio.sh --wait` (permission permitting). Note the instance id.
2. Run `./acceptance.py <id>` in the background and watch its output.
3. Open the contact sheet with the Read tool and look at it: the frames must show the scene that was asked for, not noise or black.
4. Open Studio Chat in Chrome in a new tab group via the Open button on `cloud.vast.ai/instances`. Check that the acceptance chat is there, that the film plays inline, and that `show` displays pictures. Take a screenshot.
5. Also check from the instance's logs (`vastai logs <id>`) that:
   - vLLM loaded with FP8 and the qwen3_xml tool parser;
   - EEVEE uses the NVIDIA renderer, not llvmpipe. Run `cartoon_make` on `scripts/the-flavor-of-nothing.yaml` at draft quality through the chat, watch it for 2 minutes, then cancel it.
6. **Destroy the instance**: `vastai destroy instance <id> -y`. Then `vastai show instances --raw | jq length` → `0`.

- [ ] **Step 3: Fix what failed and repeat**

For every failure:
1. Use `superpowers:systematic-debugging`, reading the instance logs through `vastai logs <id>` or the Jupyter terminal via the portal.
2. Fix it in the repo with a test where one is possible, and commit.
3. Wait for CI to rebuild `:latest`.
4. Re-run Step 2.

Rent at most one instance at a time and destroy it before waiting on CI. Model downloads take most of a boot, so batch fixes rather than re-renting per small change.

- [ ] **Step 4: Record what passed**: add `acceptance-out/` to `/Users/john/git/vast-render/.gitignore`. Keep the final contact sheet and film for the user.

---

### Task 13: Documentation and handover

**Files:**
- Create: `studio-vast/README.md`
- Modify: `studio/README.md` (if not already complete), and `/Users/john/git/vast-render/README.md` (acceptance section)

- [ ] **Step 1: Write `studio-vast/README.md`** in the style of `imagegen/README.md`. Cover:
- what the image is;
- the services table (the Ports constraint above);
- the models, with sizes, licences and pinned sources (from `all.yaml`);
- the VRAM budget on 96 GB: vLLM 42%, about 40 GB; ComfyUI time-shares the rest;
- first-boot time and disk (about 125 GB and 300 GB);
- how to launch (`vast-studio.sh`);
- a short tour of a conversation;
- the content rules in the director prompt;
- how to change the LLM, image or video model (the manifest + `studio-env.sh` + `workflows.py`);
- how CI builds and tests it;
- known limits: no lip sync; 5 s per animation call; no character consistency yet.

- [ ] **Step 2: Commit and push**

```bash
git add studio-vast/README.md studio/README.md
git commit -m "Document the studio-vast image: what runs in it, the models and their sources, the VRAM budget, launching it, a tour of a conversation, the director's rules, and how CI tests it"
git push
```

- [ ] **Step 3: Finish the branch** with `superpowers:finishing-a-development-branch`. Offer the user a pull request from `studio-vast` into `main`, with the PR body written in their voice and with no AI attribution. Leave the worktree in place unless they say otherwise.
