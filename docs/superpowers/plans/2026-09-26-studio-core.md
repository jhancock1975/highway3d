# Studio Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `studio` MCP server on :8768 whose small tools (speak, music, card, picture, import, assemble, status, list, describe) let any agent make promos with real footage, voice-over explainers and audio on its own.

**Architecture:** A `studio/` package at the repo root. The server orchestrates, and each engine runs in its own interpreter: Kokoro under `.ttsvenv`, GIMP headless, ffmpeg as a subprocess, and the numpy composer (through `lectern.score`) in the studio's own venv. A media library files everything under short ids with JSON notes. An edit is checked into a plan by `timeline.py`, then rendered by one ffmpeg run in a background job.

**Tech Stack:** Python 3.12 (uv venv), MCP SDK 2.2.0, numpy, ffmpeg 9.0.1, GIMP 3.2.6, Kokoro 0.9.4, xAI images API.

**Spec:** `docs/superpowers/specs/2026-09-26-studio-core-design.md`

## Global Constraints

- `studio/.venv`: uv venv, Python 3.12, `mcp==2.2.0` (the version lectern and highway run), `numpy`.
- Server port 8768, bound to 127.0.0.1, built on `forgiving.ForgivingServer`.
- Every tool name starts `studio_`. Every tool description names its allowed values and defaults in its own text.
- Every failure a caller sees is a sentence. No traceback reaches a result.
- `XAI_API_KEY` is read from the environment only, and never written to a log, a note or a result.
- Memory guard: needs are speech 2 GB, gimp 1 GB, assembly 2 GB, plus 4 GB headroom.
- ffmpeg here has no `drawtext` or `subtitles`: all text is drawn by GIMP as pictures.
- No LaunchAgent. The server runs as a plain process.
- Do not modify anything under `lectern/` or `highway3d/`. Reuse them by import or subprocess.
- Tests are plain scripts with a `main()` that runs every `test_*` function, like `lectern/test_status.py`.
- Engine tests (Task 10) run only when nothing heavy is running: check `ps` for a 27B, Blender or a render first.
- Commit messages are one plain sentence, no prefix, no AI attribution trailers.

## Review Focus

1. **Portrait footage in a landscape edit** (a 1080x1920 phone recording in a 1920x1080 edit): `contain` letterboxes it and `cover` crops it, neither stretches it. Pinned in Task 10's edit.
2. **An mp3 with embedded cover art**: it is sound, not video. Pinned in Task 1 (`test_cover_art_is_still_sound`).
3. **Text with apostrophes, dashes and accents** on cards and captions ("Don't panic — it's café time"): it draws, because text reaches GIMP in a JSON file, never through a shell. Pinned in Task 10 (`test_cards`).
4. **Speech longer than one Kokoro piece**: word timings keep rising across pieces instead of restarting at zero. Pinned in Task 10 (`test_long_speech_keeps_time`).
5. **File paths with spaces**: import and assembly still work, because every command is an argument list. Pinned in Task 1 (`test_paths_with_spaces`).

---

## File Structure

```
forgiving.py              existing, shared: mends bad arguments (not modified)
studio/
  .gitignore              .venv/, media/, .work/
  __init__.py             empty
  README.md               starting the server; the tools; the edit format
  errors.py               last_line(): the line of engine output worth reporting
  library.py              media library: probe, add, get, resolve, import_, listing, said
  memory.py               available_gb(), refusal(task)
  jobs.py                 new(), start(), live(), status()
  timeline.py             normalise(edit, lookup) -> (plan, problems); chunks()
  assemble.py             command(plan, out), estimate(plan), run(plan, out), main()
  speech.py               words(), speak(text, voice, speed)
  speech_engine.py        runs under .ttsvenv: plain Kokoro voices -> wav + json
  music.py                compose(mood, seconds)
  xai.py                  image(...) -> bytes; extension(); Refused
  images.py               draw(jobs), card(...), picture(...)
  gimp_draw.py            runs inside GIMP: draws cards and captions from a job list
  mcp_server.py           the nine studio_ tools
  test_library.py test_memory.py test_jobs.py test_timeline.py
  test_assemble.py test_speech.py test_music.py test_xai.py test_server.py
  test_engines.py         real engines, end to end
```

Run any test with `studio/.venv/bin/python studio/test_<name>.py` from the repo root.

---

### Task 1: Package, venv, errors and the media library

**Files:**
- Create: `studio/.gitignore`, `studio/__init__.py`, `studio/errors.py`, `studio/library.py`
- Test: `studio/test_library.py`

**Interfaces:**
- Produces: `errors.last_line(text: str) -> str`; `library.MEDIA: str`; `library.probe(path) -> dict(kind, seconds, width, height, sound)`; `library.add(path, prefix="", source="", move=False, **extra) -> note`; `library.get(ref) -> note` (KeyError with a sentence); `library.resolve(ref) -> note` (id or absolute path); `library.import_(source, name="") -> note` (ValueError with a sentence); `library.listing(kind="") -> list[note]`; `library.said(note) -> str`. A note is a dict with at least `id, path, source, made, kind, seconds, width, height, sound`.

- [ ] **Step 1: Make the venv and the package skeleton**

```bash
uv venv studio/.venv --python 3.12
uv pip install --python studio/.venv/bin/python "mcp==2.2.0" numpy
```

**File: `studio/.gitignore`**
```
.venv/
media/
.work/
```

**File: `studio/__init__.py`**
```python
```

**File: `studio/errors.py`**
```python
"""The one line of an engine's output worth putting in front of a caller.

Engines are noisy. GIMP announces itself and complains about the display it
does not have, torch warns about the future, and the reason something
actually failed is usually the last line that is none of those.
"""

NOISE = ("CVDisplayLink", "GIMP is started", "Welcome to GIMP",
         "stray image", "batch command executed", "Warning", "warn(")


def last_line(text: str) -> str:
    """The last line of `text` that says something, or a stand-in."""
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line and not any(n in line for n in NOISE):
            return line
    return "it gave no reason"
```

- [ ] **Step 2: Write the failing test**

**File: `studio/test_library.py`**
```python
"""The media library, against small real files ffmpeg makes. No server.

    studio/.venv/bin/python studio/test_library.py
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import library as L  # noqa: E402

SRC = tempfile.mkdtemp(prefix="studio-src-")


def make(name, *args):
    """A small real file, from ffmpeg's built-in test sources."""
    p = os.path.join(SRC, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, p], check=True)
    return p


CLIP = make("clip.mp4", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest")
SILENT = make("silent.mov", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=30:duration=1")
STILL = make("still.png", "-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1")
TONE = make("tone.wav", "-f", "lavfi", "-i", "sine=frequency=220:duration=1.5")
COVERED = make("covered.mp3", "-i", TONE, "-i", STILL, "-map", "0", "-map", "1",
               "-c:a", "libmp3lame", "-c:v", "png", "-disposition:v", "attached_pic")
SPACED = make("my clip with spaces.mp4", "-f", "lavfi", "-i",
              "testsrc2=size=160x120:rate=30:duration=1")


def test_probe_tells_kinds_apart():
    c = L.probe(CLIP)
    assert (c["kind"], c["width"], c["height"], c["sound"]) == ("video", 320, 240, True), c
    assert abs(c["seconds"] - 2.0) < 0.1, c
    assert L.probe(SILENT)["sound"] is False
    s = L.probe(STILL)
    assert (s["kind"], s["width"], s["height"], s["seconds"]) == ("image", 640, 360, None), s
    t = L.probe(TONE)
    assert t["kind"] == "audio" and abs(t["seconds"] - 1.5) < 0.05, t


def test_cover_art_is_still_sound():
    assert L.probe(COVERED)["kind"] == "audio"


def test_import_names_by_kind():
    for path, prefix in ((CLIP, "clip-"), (STILL, "image-"), (TONE, "sound-")):
        note = L.import_(path)
        assert note["id"].startswith(prefix), note
        assert os.path.exists(note["path"]), note
        assert note["path"].startswith(L.MEDIA), note


def test_same_file_imported_once():
    assert L.import_(TONE)["id"] == L.import_(TONE)["id"]


def test_resolve_takes_ids_and_paths():
    note = L.import_(STILL)
    assert L.resolve(note["id"])["path"] == note["path"]
    assert L.resolve(STILL)["id"] == note["id"]


def test_paths_with_spaces():
    note = L.resolve(SPACED)
    assert note["kind"] == "video" and os.path.exists(note["path"]), note


def test_unknown_id_is_a_sentence():
    for ref in ("clip-0000", "../../etc/passwd"):
        try:
            L.get(ref)
        except KeyError as e:
            assert e.args[0] == f"there is no asset called {ref}", e
        else:
            raise AssertionError(f"{ref} was found")


def test_not_media_is_a_sentence():
    p = os.path.join(SRC, "notes.txt")
    with open(p, "w") as fh:
        fh.write("hello")
    try:
        L.import_(p)
    except ValueError as e:
        assert e.args[0] == "notes.txt is not a picture, video or sound that ffmpeg can read", e
    else:
        raise AssertionError("a text file was imported")


def test_missing_file_is_a_sentence():
    try:
        L.import_("/nowhere/at/all.mp4")
    except ValueError as e:
        assert e.args[0] == "there is no file at /nowhere/at/all.mp4", e
    else:
        raise AssertionError("a missing file was imported")


def test_listing_newest_first_and_by_kind():
    L.import_(CLIP)
    notes = L.listing()
    assert {n["kind"] for n in notes} >= {"video", "image", "audio"}
    assert all(n["kind"] == "image" for n in L.listing("image"))
    made = [n["made"] for n in notes]
    assert made == sorted(made, reverse=True)


def test_said_reads_as_a_line():
    note = L.import_(SILENT, name="demo")
    line = L.said(note)
    assert line == f"{note['id']} ('demo'): video, 1.0 seconds, 160x120, silent, at {note['path']}", line


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

- [ ] **Step 3: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_library.py`
Expected: `ModuleNotFoundError: No module named 'studio.library'`

- [ ] **Step 4: Write the library**

**File: `studio/library.py`**
```python
"""The media library: every file the studio makes or is handed, by id.

An id says where a file came from -- `voice-3f2a`, `clip-9c01` -- so a caller
holding one knows what it is without asking. Beside each file sits a JSON
note of what it is: kind, length, size, source, and for speech the word
timings captions are drawn from. The notes are the index, so there is no
database to fall out of step with the files.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.environ.get("STUDIO_MEDIA", os.path.join(HERE, "studio", "media"))

# ffprobe will read any text file as "tty", ANSI art, and call it video.
NOT_MEDIA = {"tty"}
# What ffprobe calls a single picture rather than a stream of them.
STILL_FORMATS = {"image2", "png_pipe", "jpeg_pipe", "webp_pipe", "bmp_pipe",
                 "tiff_pipe"}
# The prefix an imported file gets, by what it turns out to be.
IMPORTED = {"video": "clip", "image": "image", "audio": "sound"}


def probe(path: str) -> dict:
    """Kind, length and size of a media file, as ffprobe reads it."""
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                        "-show_streams", "-show_format", path],
                       capture_output=True, text=True)
    name = os.path.basename(path)
    if r.returncode != 0:
        raise ValueError(f"{name} is not a picture, video or sound that "
                         f"ffmpeg can read")
    info = json.loads(r.stdout or "{}")
    streams = info.get("streams", [])
    fmt = info.get("format", {})
    if fmt.get("format_name") in NOT_MEDIA:
        raise ValueError(f"{name} is not a picture, video or sound that "
                         f"ffmpeg can read")
    # An mp3's cover art is a video stream, and the file is still a sound.
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    sound = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video and fmt.get("format_name") in STILL_FORMATS:
        return dict(kind="image", seconds=None, width=video["width"],
                    height=video["height"], sound=False)
    seconds = round(float(fmt.get("duration") or 0.0), 3)
    if video:
        return dict(kind="video", seconds=seconds, width=video["width"],
                    height=video["height"], sound=sound is not None)
    if sound:
        return dict(kind="audio", seconds=seconds, width=None, height=None,
                    sound=True)
    raise ValueError(f"{name} has no picture or sound in it")


def _note_path(aid: str) -> str:
    return os.path.join(MEDIA, aid + ".json")


def _fresh(prefix: str) -> str:
    while True:
        aid = f"{prefix}-{uuid.uuid4().hex[:4]}"
        if not os.path.exists(_note_path(aid)):
            return aid


def add(path: str, prefix: str = "", source: str = "", move: bool = False,
        **extra) -> dict:
    """File `path` into the library under a new id, and return its note.

    With no prefix, the file's kind picks one, as for anything imported.
    """
    facts = probe(path)
    os.makedirs(MEDIA, exist_ok=True)
    aid = _fresh(prefix or IMPORTED[facts["kind"]])
    dest = os.path.join(MEDIA, aid + os.path.splitext(path)[1].lower())
    (shutil.move if move else shutil.copy2)(path, dest)
    note = dict(id=aid, path=dest, source=source, made=time.time(), **facts,
                **extra)
    with open(_note_path(aid), "w") as fh:
        json.dump(note, fh, indent=1)
    return note


def get(ref: str) -> dict:
    """The note for an id, or KeyError saying there is no such asset."""
    p = _note_path(ref)
    if "/" in ref or os.sep in ref or not os.path.exists(p):
        raise KeyError(f"there is no asset called {ref}")
    with open(p) as fh:
        return json.load(fh)


def resolve(ref: str) -> dict:
    """An id, or a path on this Mac, which is imported first."""
    path = os.path.expanduser(ref)
    if os.path.isabs(path):
        return import_(path)
    return get(ref)


def import_(source: str, name: str = "") -> dict:
    """A file on this Mac, or at an http(s) URL, filed into the library.

    A local file already imported, and unchanged since, is not filed twice:
    an edit that names the same path in three places gets one asset.
    """
    if source.startswith(("http://", "https://")):
        return _download(source, name)
    path = os.path.abspath(os.path.expanduser(source))
    if not os.path.isfile(path):
        raise ValueError(f"there is no file at {source}")
    st = os.stat(path)
    for note in listing():
        if (note.get("source") == path and note.get("size") == st.st_size
                and note.get("mtime") == st.st_mtime):
            return note
    return add(path, source=path, name=name or os.path.basename(path),
               size=st.st_size, mtime=st.st_mtime)


def _download(url: str, name: str) -> dict:
    tail = os.path.basename(urllib.parse.urlparse(url).path)
    os.makedirs(MEDIA, exist_ok=True)
    tmp = os.path.join(MEDIA, f".incoming-{uuid.uuid4().hex[:8]}"
                              f"{os.path.splitext(tail)[1][:8]}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, \
                open(tmp, "wb") as fh:
            shutil.copyfileobj(r, fh)
        return add(tmp, source=url, move=True, name=name or tail or url)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def listing(kind: str = "") -> list[dict]:
    """Every asset, newest first, only of `kind` if one is given."""
    if not os.path.isdir(MEDIA):
        return []
    notes = []
    for f in os.listdir(MEDIA):
        if f.endswith(".json"):
            with open(os.path.join(MEDIA, f)) as fh:
                notes.append(json.load(fh))
    return sorted((n for n in notes if not kind or n["kind"] == kind),
                  key=lambda n: n["made"], reverse=True)


def said(note: dict) -> str:
    """One line a model can read: the id, what it is, and where the file is."""
    if note["kind"] == "image":
        what = f"picture, {note['width']}x{note['height']}"
    elif note["kind"] == "video":
        what = (f"video, {note['seconds']:.1f} seconds, "
                f"{note['width']}x{note['height']}, "
                + ("with sound" if note["sound"] else "silent"))
    else:
        what = f"sound, {note['seconds']:.1f} seconds"
    label = f" ('{note['name']}')" if note.get("name") else ""
    return f"{note['id']}{label}: {what}, at {note['path']}"
```

- [ ] **Step 5: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_library.py`
Expected: `11/11 passed`

- [ ] **Step 6: Commit**

```bash
git add studio/.gitignore studio/__init__.py studio/errors.py studio/library.py studio/test_library.py
git commit -m "Start the studio with a media library that files everything by id"
```

---

### Task 2: Memory guard

**Files:**
- Create: `studio/memory.py`
- Test: `studio/test_memory.py`

**Interfaces:**
- Produces: `memory.NEEDS_GB = {"speech": 2.0, "gimp": 1.0, "assembly": 2.0}`; `memory.HEADROOM_GB = 4.0`; `memory.available_gb(vm_stat_text=None) -> float`; `memory.refusal(task, available=None) -> str` ("" when there is room).

- [ ] **Step 1: Write the failing test**

**File: `studio/test_memory.py`**
```python
"""The memory guard's arithmetic, on vm_stat output. No engines.

    studio/.venv/bin/python studio/test_memory.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import memory as M  # noqa: E402

# 65536 + 131072 + 65536 pages of 16 KiB is exactly 4 GiB available.
SAMPLE = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               65536.
Pages active:                            800000.
Pages inactive:                          131072.
Pages speculative:                        65536.
Pages throttled:                              0.
Pages wired down:                        900000.
"""


def test_available_counts_free_inactive_and_speculative():
    assert M.available_gb(SAMPLE) == 4.0


def test_room_means_no_refusal():
    assert M.refusal("speech", 6.0) == ""
    assert M.refusal("assembly", 9.5) == ""


def test_no_room_is_a_sentence_with_the_numbers():
    got = M.refusal("speech", 5.0)
    assert got == ("The Mac has 5 GB available and speech needs about 2 GB "
                   "plus 4 GB of headroom; try again when the other work "
                   "finishes."), got
    assert "drawing needs about 1 GB" in M.refusal("gimp", 1.0)


def test_this_mac_reads():
    assert M.available_gb() > 0


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

- [ ] **Step 2: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_memory.py`
Expected: `ImportError: cannot import name 'memory'`

- [ ] **Step 3: Write the guard**

**File: `studio/memory.py`**
```python
"""Whether this Mac has room to start something heavy.

On 2026-09-26 this Mac took a watchdog panic from memory exhaustion: a
music-model trial, a resident 8B, Cider's 27B and Blender, all at once, with
0.25 GB free and nothing left to reclaim. So speech, drawing and assembly
each check first, and refuse with the numbers rather than add to a pile.

Available is what macOS can hand out without paging: free, inactive and
speculative pages. The needs are what each engine was measured to take,
and the headroom is for everything else on the machine.
"""

from __future__ import annotations

import re
import subprocess

NEEDS_GB = {"speech": 2.0, "gimp": 1.0, "assembly": 2.0}
HEADROOM_GB = 4.0
CALLED = {"speech": "speech", "gimp": "drawing", "assembly": "assembly"}


def available_gb(vm_stat_text: str | None = None) -> float:
    """Gigabytes macOS could hand out now, read from vm_stat."""
    text = vm_stat_text
    if text is None:
        text = subprocess.run(["vm_stat"], capture_output=True,
                              text=True).stdout
    page = int(re.search(r"page size of (\d+) bytes", text).group(1))

    def pages(label: str) -> int:
        m = re.search(rf"^{label}:\s+(\d+)\.", text, re.M)
        return int(m.group(1)) if m else 0

    free = (pages("Pages free") + pages("Pages inactive")
            + pages("Pages speculative"))
    return round(free * page / 2 ** 30, 2)


def refusal(task: str, available: float | None = None) -> str:
    """'' if there is room for `task`, else the sentence saying why not."""
    have = available_gb() if available is None else available
    need = NEEDS_GB[task]
    if have >= need + HEADROOM_GB:
        return ""
    return (f"The Mac has {have:.0f} GB available and {CALLED[task]} needs "
            f"about {need:g} GB plus {HEADROOM_GB:g} GB of headroom; try "
            f"again when the other work finishes.")
```

- [ ] **Step 4: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_memory.py`
Expected: `4/4 passed`

- [ ] **Step 5: Commit**

```bash
git add studio/memory.py studio/test_memory.py
git commit -m "Refuse heavy studio work when the Mac has no room for it"
```

---

### Task 3: Jobs

**Files:**
- Create: `studio/jobs.py`
- Test: `studio/test_jobs.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `jobs.WORK: str`; `jobs.new() -> str` (6 hex); `jobs.start(job, module, args, header) -> str` (log path; runs `python -m module *args --job job` detached); `jobs.live() -> set[str]`; `jobs.status(job="") -> str`. Log lines: `JOB {"name","out"}`, `PROGRESS {"stage","percent"}`, `DONE {"out","seconds","bytes","took"}`, `FAILED <reason>`.

- [ ] **Step 1: Write the failing test**

**File: `studio/test_jobs.py`**
```python
"""What studio_status says about jobs, live, finished and dead. No engines.

    studio/.venv/bin/python studio/test_jobs.py
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_WORK"] = tempfile.mkdtemp(prefix="studio-work-")
from studio import jobs as J  # noqa: E402

DONE = 'DONE {"out": "/r/spot.mp4", "seconds": 12.04, "bytes": 3400000, "took": 41.2}'
_age = [0]


def log(job, *lines, name="spot"):
    p = os.path.join(J.WORK, f"job-{job}.log")
    with open(p, "w") as fh:
        fh.write("JOB " + json.dumps(dict(name=name, out="/r/x.mp4")) + "\n")
        fh.write("\n".join(lines) + "\n")
    _age[0] += 10
    os.utime(p, (1e9 + _age[0], 1e9 + _age[0]))


def running(job):
    """A process that looks like a live studio job to ps."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                             "-m", "studio.assemble", "--job", job])


def clear():
    for f in os.listdir(J.WORK):
        os.remove(os.path.join(J.WORK, f))


def test_nothing_yet():
    clear()
    assert J.status() == "Nothing has been assembled on this server yet."


def test_finished_job():
    clear()
    log("aaaaaa", DONE)
    assert J.status() == ("Job aaaaaa ('spot'): finished: /r/spot.mp4, 12.0 "
                          "seconds long, 3.4 MB, took 41 seconds."), J.status()


def test_failed_job():
    clear()
    log("bbbbbb", "FAILED ffmpeg stopped: clip-9c01 has no video stream.")
    assert J.status("bbbbbb") == ("Job bbbbbb ('spot'): stopped: ffmpeg "
                                  "stopped: clip-9c01 has no video stream.")


def test_dead_job_says_so():
    clear()
    log("cccccc", 'PROGRESS {"stage": "encoding", "percent": 40}')
    got = J.status("cccccc")
    assert "stopped before it finished" in got and "40" not in got, got


def test_running_jobs_all_listed_with_progress():
    clear()
    procs = [running("dddddd"), running("eeeeee")]
    try:
        log("dddddd", 'PROGRESS {"stage": "encoding", "percent": 40}', name="one")
        log("eeeeee", 'PROGRESS {"stage": "drawing", "percent": 0}', name="two")
        log("ffffff", DONE, name="newest")
        got = J.status().splitlines()
        assert len(got) == 3, got
        assert got[0].startswith("Job ffffff ('newest'): finished"), got
        assert "Job dddddd ('one'): encoding, 40% done." in got, got
        assert "Job eeeeee ('two'): drawing, 0% done." in got, got
    finally:
        for p in procs:
            p.kill()
            p.wait()


def test_unknown_or_odd_job_ids():
    clear()
    for job in ("123456", "../../etc"):
        got = J.status(job)
        assert got.startswith(f"There is no job {job} on this server."), got


def test_start_writes_header_and_runs():
    clear()
    job = J.new()
    log_path = J.start(job, "json.tool", ["--help"], dict(name="probe", out="/r/p"))
    with open(log_path) as fh:
        first = fh.readline()
    assert first.startswith("JOB ") and json.loads(first[4:])["name"] == "probe", first


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

- [ ] **Step 2: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_jobs.py`
Expected: `ImportError: cannot import name 'jobs'`

- [ ] **Step 3: Write jobs**

**File: `studio/jobs.py`**
```python
"""Background jobs: start one, and say how it is going whenever asked.

The same shape lectern's renders use. A job's log opens with a JOB line
saying what it will make, then PROGRESS lines, then DONE or FAILED. A job
whose process has gone without writing either is said to have stopped,
rather than reported at its last progress line forever -- which is what a
render killed by the Mac going down used to look like.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.environ.get("STUDIO_WORK", os.path.join(HERE, "studio", ".work"))


def new() -> str:
    return uuid.uuid4().hex[:6]


def start(job: str, module: str, args: list[str], header: dict) -> str:
    """Run `python -m module *args --job job` detached. Returns its log."""
    os.makedirs(WORK, exist_ok=True)
    log = os.path.join(WORK, f"job-{job}.log")
    with open(log, "w") as fh:
        fh.write("JOB " + json.dumps(header) + "\n")
        fh.flush()
        subprocess.Popen([sys.executable, "-m", module, *args, "--job", job],
                         cwd=HERE, stdout=fh, stderr=subprocess.STDOUT,
                         start_new_session=True)
    return log


def live() -> set[str]:
    """Jobs whose process is still running, whichever server started them."""
    r = subprocess.run(["ps", "-axww", "-o", "args="], capture_output=True,
                       text=True)
    return set(re.findall(r"-m studio\.\w+ .*--job (\w+)", r.stdout))


def _read(log: str) -> tuple[dict, str]:
    with open(log) as fh:
        lines = [x.strip() for x in fh if x.strip()]
    head = {}
    if lines and lines[0].startswith("JOB "):
        try:
            head = json.loads(lines[0][4:])
        except ValueError:
            pass
    tail = next((x for x in reversed(lines)
                 if x.startswith(("PROGRESS", "DONE", "FAILED"))), "")
    return head, tail


def _report(job: str, log: str, running: set[str]) -> str:
    head, tail = _read(log)
    name = f"Job {job} ('{head['name']}')" if head.get("name") else f"Job {job}"
    if tail.startswith("DONE"):
        d = json.loads(tail[4:])
        return (f"{name}: finished: {d['out']}, {d['seconds']:.1f} seconds "
                f"long, {d['bytes'] / 1e6:.1f} MB, took {d['took']:.0f} "
                f"seconds.")
    if tail.startswith("FAILED"):
        return f"{name}: stopped: {tail[6:].strip()}"
    if job not in running:
        return (f"{name}: stopped before it finished, without saying why: its "
                f"process is no longer running, most likely because the "
                f"server or the Mac restarted under it. Assembling the same "
                f"edit again starts it over.")
    if tail.startswith("PROGRESS"):
        d = json.loads(tail[8:])
        done = f", {d['percent']:.0f}% done" if "percent" in d else ""
        return f"{name}: {d['stage']}{done}."
    return f"{name}: started, nothing reported yet."


def status(job: str = "") -> str:
    """How a job is going; with no job, the newest and any still running."""
    running = live()
    job = job.strip()
    if job:
        log = os.path.join(WORK, f"job-{job}.log")
        if not re.fullmatch(r"\w+", job) or not os.path.exists(log):
            return (f"There is no job {job} on this server. Ask without a job "
                    f"id to hear about the most recent one.")
        return _report(job, log, running)
    logs = sorted(glob.glob(os.path.join(WORK, "job-*.log")),
                  key=os.path.getmtime, reverse=True)
    if not logs:
        return "Nothing has been assembled on this server yet."

    def job_of(p: str) -> str:
        return os.path.basename(p)[len("job-"):-len(".log")]

    shown = logs[:1] + [p for p in logs[1:] if job_of(p) in running]
    return "\n".join(_report(job_of(p), p, running) for p in shown)
```

- [ ] **Step 4: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_jobs.py`
Expected: `7/7 passed`

- [ ] **Step 5: Commit**

```bash
git add studio/jobs.py studio/test_jobs.py
git commit -m "Run studio work as jobs that say how they are going"
```

---

### Task 4: The edit checker

**Files:**
- Create: `studio/timeline.py`
- Test: `studio/test_timeline.py`

**Interfaces:**
- Consumes: a `lookup(ref) -> note` callable (in production `library.resolve`); notes as in Task 1, speech notes carry `words: [{text, start, end}]`.
- Produces: `timeline.TRANSITION = 0.5`; `TRANSITIONS, FITS, MOVES, PLACES` tuples; `timeline.chunks(words, at) -> [{text, at, seconds}]`; `timeline.normalise(edit, lookup) -> (plan, problems)`. A plan is `dict(width, height, fps, name, seconds, audio_only, video=[{path, id, kind, start, seconds, from_, transition, fit, move, level, sound}], overlays=[{path, id, at, seconds, place, width, height}], captions=[{text, at, seconds}], audio=[{path, id, at, level, fade, duck, speech, seconds}])`.

- [ ] **Step 1: Write the failing test**

**File: `studio/test_timeline.py`**
```python
"""The edit checker: times worked out, and every mistake said. No engines.

    studio/.venv/bin/python studio/test_timeline.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import timeline as T  # noqa: E402

WORDS = [dict(text=t, start=s, end=e) for t, s, e in [
    ("Three", 0.0, 0.3), ("in", 0.3, 0.4), ("the", 0.4, 0.5),
    ("morning.", 0.5, 1.0), ("The", 1.2, 1.3), ("server", 1.3, 1.7),
    ("is", 1.7, 1.8), ("down,", 1.8, 2.2), ("and", 2.3, 2.4),
    ("you", 2.4, 2.5), ("are", 2.5, 2.6), ("not", 2.6, 2.8),
    ("at", 2.8, 2.9), ("your", 2.9, 3.0), ("desk.", 3.0, 3.5)]]

NOTES = {
    "card-1a2b": dict(id="card-1a2b", path="/m/card.png", kind="image", seconds=None, width=1920, height=1080, sound=False),
    "clip-9c01": dict(id="clip-9c01", path="/m/clip.mov", kind="video", seconds=9.0, width=1170, height=2532, sound=True),
    "pic-44d0": dict(id="pic-44d0", path="/m/pic.png", kind="image", seconds=None, width=1024, height=1024, sound=False),
    "card-7d3e": dict(id="card-7d3e", path="/m/lower.png", kind="image", seconds=None, width=1600, height=200, sound=False),
    "voice-3f2a": dict(id="voice-3f2a", path="/m/voice.wav", kind="audio", seconds=3.6, width=None, height=None, sound=True, words=WORDS),
    "music-77e1": dict(id="music-77e1", path="/m/music.wav", kind="audio", seconds=30.0, width=None, height=None, sound=True),
}


def lookup(ref):
    if ref not in NOTES:
        raise KeyError(f"there is no asset called {ref}")
    return NOTES[ref]


def good():
    return {
        "size": "1920x1080", "fps": 30, "name": "Pockterm Spot!",
        "video": [{"asset": "card-1a2b", "seconds": 3},
                  {"asset": "clip-9c01", "from": 2, "seconds": 6, "transition": "dissolve"},
                  {"asset": "pic-44d0", "seconds": 5, "move": "push-in", "transition": "fade"}],
        "overlays": [{"asset": "card-7d3e", "at": 4, "seconds": 3, "place": "bottom"},
                     {"captions": "voice-3f2a"}],
        "audio": [{"asset": "voice-3f2a", "at": 0.5},
                  {"asset": "music-77e1", "level": 0.15, "duck": True}],
    }


def test_good_edit_has_no_problems_and_times_add_up():
    plan, problems = T.normalise(good(), lookup)
    assert problems == [], problems
    starts = [v["start"] for v in plan["video"]]
    assert starts == [0.0, 2.5, 8.0], starts
    assert plan["seconds"] == 13.0, plan["seconds"]
    assert plan["name"] == "pockterm-spot"
    assert (plan["width"], plan["height"], plan["fps"]) == (1920, 1080, 30.0)
    assert plan["audio_only"] is False


def test_defaults():
    plan, problems = T.normalise({"video": ["pic-44d0", "clip-9c01"]}, lookup)
    assert problems == [], problems
    still, clip = plan["video"]
    assert (still["seconds"], still["transition"], still["fit"], still["move"]) == (4.0, "cut", "cover", "none")
    assert (clip["from_"], clip["seconds"]) == (0.0, 9.0)
    assert plan["seconds"] == 13.0 and plan["name"] == "edit"
    assert plan["audio"] == [] and plan["captions"] == []


def test_music_fades_by_default_speech_does_not():
    plan, _ = T.normalise(good(), lookup)
    voice, music = plan["audio"]
    assert (voice["fade"], voice["speech"], voice["duck"]) == (0.0, True, False)
    assert (music["fade"], music["speech"], music["duck"], music["level"]) == (1.0, False, True, 0.15)


def test_captions_follow_the_voice():
    plan, _ = T.normalise(good(), lookup)
    texts = [c["text"] for c in plan["captions"]]
    assert texts == ["Three in the morning.", "The server is down,", "and you are not at your desk."], texts
    first = plan["captions"][0]
    assert first["at"] == 0.5, first
    assert first["seconds"] == 1.2, first


def test_chunks_never_longer_than_seven_words():
    words = [dict(text=f"w{i}", start=i * 0.2, end=i * 0.2 + 0.15) for i in range(16)]
    sizes = [len(c["text"].split()) for c in T.chunks(words, 0.0)]
    assert sizes == [7, 7, 2], sizes


def test_chunks_survive_empty_and_bare_punctuation():
    words = [dict(text="", start=0, end=0.1), dict(text="Hi", start=0.1, end=0.3),
             dict(text="—", start=0.3, end=0.35), dict(text="there", start=0.35, end=0.6)]
    got = T.chunks(words, 1.0)
    assert [c["text"] for c in got] == ["Hi — there"], got
    assert got[0]["at"] == 1.1, got


def test_audio_only_edit():
    plan, problems = T.normalise({"audio": ["voice-3f2a", {"asset": "music-77e1", "at": 1}]}, lookup)
    assert problems == [], problems
    assert plan["audio_only"] is True and plan["seconds"] == 31.0, plan["seconds"]


def test_odd_sizes_become_even():
    plan, problems = T.normalise({"size": "1081x1921", "video": ["pic-44d0"]}, lookup)
    assert problems == [] and (plan["width"], plan["height"]) == (1080, 1920)


def said(edit):
    return T.normalise(edit, lookup)[1]


def test_problems_are_sentences():
    cases = [
        ({"video": [{"asset": "clip-9c01", "from": 12}]},
         "video item 1: clip-9c01 is 9 seconds long, so from 12 is past its end."),
        ({"video": [{"asset": "clip-9c01", "from": 2, "seconds": 8}]},
         "video item 1: clip-9c01 is 9 seconds long, so 8 seconds from 2 runs past its end."),
        ({"video": ["pic-44d0"], "overlays": [{"asset": "card-9999"}]},
         "overlay 1: there is no asset called card-9999."),
        ({"video": ["pic-44d0"], "overlays": [{"captions": "music-77e1"}], "audio": ["music-77e1"]},
         "captions: music-77e1 is music, not speech, so it has no words to show."),
        ({"video": ["pic-44d0"], "overlays": [{"captions": "voice-3f2a"}]},
         "captions: voice-3f2a is not in audio, so there is no time to show its words at."),
        ({"video": ["voice-3f2a"]},
         "video item 1: voice-3f2a is sound, which goes in audio, not video."),
        ({"video": [{"asset": "clip-9c01", "move": "push-in"}]},
         "video item 1: move is for stills, and clip-9c01 is video."),
        ({"video": [{"asset": "pic-44d0", "transition": "wipe"}]},
         "video item 1: transition 'wipe' is not one of cut, dissolve, fade."),
        ({"video": ["pic-44d0"], "audio": ["pic-44d0"]},
         "audio item 1: pic-44d0 is a picture, which has no sound."),
        ({"video": ["pic-44d0"], "overlays": [{"asset": "clip-9c01"}]},
         "overlay 1: overlays are pictures, and clip-9c01 is video."),
        ({"video": [{"asset": "pic-44d0", "seconds": 0.4},
                    {"asset": "card-1a2b", "transition": "dissolve"}]},
         "video item 2: its dissolve takes half a second, so it and the item before it must each be longer than that."),
        ({"video": ["pic-44d0"], "audio": [{"asset": "music-77e1", "at": 9}]},
         "audio item 1: it starts at 9, after the edit ends at 4."),
        ({"size": "big", "video": ["pic-44d0"]},
         "size 'big' is not WIDTHxHEIGHT, like 1920x1080."),
        ({"fps": "fast", "video": ["pic-44d0"]},
         "the edit: fps 'fast' is not a number."),
        ({}, "the edit has nothing in it: add video or audio."),
    ]
    for edit, want in cases:
        got = said(edit)
        assert want in got, (want, got)


def test_every_problem_reported_at_once():
    got = said({"video": [{"asset": "nope-0000"}, {"asset": "clip-9c01", "from": 99}],
                "audio": ["nada-1111"]})
    assert len(got) == 3, got


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

- [ ] **Step 2: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_timeline.py`
Expected: `ImportError: cannot import name 'timeline'`

- [ ] **Step 3: Write the checker**

**File: `studio/timeline.py`**
```python
"""The edit: what goes where, checked before anything renders.

An edit is JSON a model can write without computing a timecode. The video
track plays in order, so start times follow from lengths; overlays and
audio say when they begin. `normalise` turns an edit into a plan with every
time worked out and every asset found, and reports everything wrong with
it at once, in sentences. A problem found here costs nothing; the same
problem found by ffmpeg costs the whole render.
"""

from __future__ import annotations

import re

TRANSITION = 0.5
TRANSITIONS = ("cut", "dissolve", "fade")
FITS = ("cover", "contain")
MOVES = ("none", "push-in", "pull-out", "pan-left", "pan-right")
PLACES = ("full", "center", "top", "bottom", "top-left", "top-right",
          "bottom-left", "bottom-right")
STILL_SECONDS = 4.0
CHUNK = 7


def _s(x: float) -> str:
    """A time as a person writes it: 9, 9.5, 9.04."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def chunks(words: list[dict], at: float) -> list[dict]:
    """Speech's words in runs of up to seven, each shown while it is said.

    A run ends early at the end of a sentence, and at a comma once it has
    four words, so a caption breaks where the voice does. A short gap
    between runs is bridged, so captions do not flicker off and on.
    """
    runs, run = [], []
    for w in words:
        if not w["text"].strip():
            continue
        run.append(w)
        last = w["text"].rstrip("\"')”’")[-1:]
        if (len(run) >= CHUNK or (last and last in ".!?")
                or (last and last in ",;:" and len(run) >= 4)):
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    out = [dict(text=" ".join(w["text"] for w in r),
                at=round(at + r[0]["start"], 3), end=round(at + r[-1]["end"], 3))
           for r in runs]
    for a, b in zip(out, out[1:]):
        if b["at"] - a["end"] < 0.3:
            a["end"] = b["at"]
    for c in out:
        c["seconds"] = round(max(c.pop("end") - c["at"], 0.6), 3)
    return out


def normalise(edit: dict, lookup) -> tuple[dict, list[str]]:
    """A plan with every time and file worked out, and what is wrong."""
    problems: list[str] = []
    found: dict[str, dict | None] = {}

    def find(ref, where):
        if not isinstance(ref, str) or not ref.strip():
            problems.append(f"{where}: it needs an asset.")
            return None
        if ref not in found:
            try:
                found[ref] = lookup(ref)
            except (KeyError, ValueError) as e:
                problems.append(f"{where}: {e.args[0] if e.args else e}.")
                found[ref] = None
        return found[ref]

    def number(item, key, default, where, lo, hi):
        v = item.get(key, default)
        try:
            v = float(v)
        except (TypeError, ValueError):
            problems.append(f"{where}: {key} {v!r} is not a number.")
            return default
        if not lo <= v <= hi:
            problems.append(f"{where}: {key} {_s(v)} is outside {_s(lo)} "
                            f"to {_s(hi)}.")
            return default
        return v

    def choice(item, key, allowed, where):
        v = item.get(key, allowed[0])
        if v not in allowed:
            problems.append(f"{where}: {key} {v!r} is not one of "
                            f"{', '.join(allowed)}.")
            return allowed[0]
        return v

    def listed(key):
        items = edit.get(key) or []
        if not isinstance(items, list):
            problems.append(f"{key} must be a list.")
            return []
        return [{"asset": x} if isinstance(x, str) else x for x in items]

    # -- frame
    size = edit.get("size", "1920x1080")
    m = re.fullmatch(r"\s*(\d+)\s*[x×]\s*(\d+)\s*", str(size))
    w, h = (int(m[1]), int(m[2])) if m else (1920, 1080)
    if not m:
        problems.append(f"size {size!r} is not WIDTHxHEIGHT, like 1920x1080.")
    elif not (16 <= w <= 7680 and 16 <= h <= 4320):
        problems.append(f"size {w}x{h} is outside 16x16 to 7680x4320.")
        w, h = 1920, 1080
    # H.264 wants even sides, and one pixel is not worth a complaint.
    w, h = w - w % 2, h - h % 2
    fps = number(edit, "fps", 30.0, "the edit", 1, 120)
    name = re.sub(r"[^a-z0-9]+", "-", str(edit.get("name", "edit")).lower())
    name = name.strip("-")[:60] or "edit"

    # -- video, in order
    video: list[dict] = []
    t = 0.0
    for i, item in enumerate(listed("video"), 1):
        where = f"video item {i}"
        if not isinstance(item, dict):
            problems.append(f"{where}: it should be an object with an asset.")
            continue
        note = find(item.get("asset"), where)
        transition = choice(item, "transition", TRANSITIONS, where)
        fit = choice(item, "fit", FITS, where)
        move = choice(item, "move", MOVES, where)
        level = number(item, "level", 1.0, where, 0, 1)
        if note is None:
            continue
        if note["kind"] == "audio":
            problems.append(f"{where}: {note['id']} is sound, which goes in "
                            f"audio, not video.")
            continue
        start_in = 0.0
        if note["kind"] == "image":
            seconds = number(item, "seconds", STILL_SECONDS, where, 0.1, 3600)
        else:
            if move != "none":
                problems.append(f"{where}: move is for stills, and "
                                f"{note['id']} is video.")
                move = "none"
            length = note["seconds"]
            start_in = number(item, "from", 0.0, where, 0, 1e6)
            if start_in >= length:
                problems.append(f"{where}: {note['id']} is {_s(length)} "
                                f"seconds long, so from {_s(start_in)} is "
                                f"past its end.")
                continue
            seconds = number(item, "seconds", length - start_in, where, 0.1,
                             1e6)
            if start_in + seconds > length + 0.05:
                problems.append(f"{where}: {note['id']} is {_s(length)} "
                                f"seconds long, so {_s(seconds)} seconds from "
                                f"{_s(start_in)} runs past its end.")
                continue
        overlap = TRANSITION if video and transition != "cut" else 0.0
        if overlap and (seconds <= TRANSITION or
                        video[-1]["seconds"] <= TRANSITION):
            problems.append(f"{where}: its {transition} takes half a second, "
                            f"so it and the item before it must each be "
                            f"longer than that.")
            continue
        start = round(t - overlap, 3)
        video.append(dict(path=note["path"], id=note["id"], kind=note["kind"],
                          start=start, seconds=seconds, from_=start_in,
                          transition=transition, fit=fit, move=move,
                          level=level, sound=bool(note.get("sound"))))
        t = start + seconds

    # -- audio, placed by time
    audio: list[dict] = []
    for i, item in enumerate(listed("audio"), 1):
        where = f"audio item {i}"
        if not isinstance(item, dict):
            problems.append(f"{where}: it should be an object with an asset.")
            continue
        note = find(item.get("asset"), where)
        at = number(item, "at", 0.0, where, 0, 1e6)
        level = number(item, "level", 1.0, where, 0, 1)
        if note is None:
            continue
        if note["kind"] == "image":
            problems.append(f"{where}: {note['id']} is a picture, which has "
                            f"no sound.")
            continue
        if note["kind"] == "video" and not note.get("sound"):
            problems.append(f"{where}: {note['id']} is silent video, so there "
                            f"is no sound in it to use.")
            continue
        music = note["id"].startswith("music-")
        fade = number(item, "fade", 1.0 if music else 0.0, where, 0, 60)
        if video and at >= t:
            problems.append(f"{where}: it starts at {_s(at)}, after the edit "
                            f"ends at {_s(t)}.")
            continue
        audio.append(dict(path=note["path"], id=note["id"], at=at,
                          level=level, fade=fade,
                          duck=bool(item.get("duck", False)),
                          speech=bool(note.get("words")),
                          seconds=note["seconds"],
                          words=note.get("words") or []))

    if not edit.get("video") and not edit.get("audio"):
        problems.append("the edit has nothing in it: add video or audio.")
    total = t if video else max((a["at"] + a["seconds"] for a in audio),
                                default=0.0)

    # -- overlays and captions
    overlays: list[dict] = []
    captions: list[dict] = []
    for i, item in enumerate(listed("overlays"), 1):
        where = f"overlay {i}"
        if not isinstance(item, dict):
            problems.append(f"{where}: it should be an object with an asset.")
            continue
        if "captions" in item:
            note = find(item["captions"], "captions")
            if note is None:
                continue
            if not note.get("words"):
                what = ("music" if note["id"].startswith("music-")
                        else "a picture" if note["kind"] == "image"
                        else note["kind"] if note["kind"] == "video"
                        else "sound with no words")
                problems.append(f"captions: {note['id']} is {what}, not "
                                f"speech, so it has no words to show.")
                continue
            spoken = next((a for a in audio if a["id"] == note["id"]), None)
            if spoken is None:
                problems.append(f"captions: {note['id']} is not in audio, so "
                                f"there is no time to show its words at.")
                continue
            captions.extend(chunks(note["words"], spoken["at"]))
            continue
        note = find(item.get("asset"), where)
        at = number(item, "at", 0.0, where, 0, 1e6)
        place = choice(item, "place", PLACES, where)
        if note is None:
            continue
        if note["kind"] != "image":
            problems.append(f"{where}: overlays are pictures, and "
                            f"{note['id']} is {note['kind']}.")
            continue
        if video and at >= total:
            problems.append(f"{where}: it starts at {_s(at)}, after the edit "
                            f"ends at {_s(total)}.")
            continue
        seconds = number(item, "seconds", max(total - at, 0.1), where, 0.1,
                         1e6)
        overlays.append(dict(path=note["path"], id=note["id"], at=at,
                             seconds=seconds, place=place,
                             width=note["width"], height=note["height"]))

    for a in audio:
        a.pop("words")
    plan = dict(width=w, height=h, fps=fps, name=name,
                seconds=round(total, 3), audio_only=not video, video=video,
                overlays=overlays, captions=captions, audio=audio)
    return plan, problems
```

- [ ] **Step 4: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_timeline.py`
Expected: `11/11 passed`

- [ ] **Step 5: Commit**

```bash
git add studio/timeline.py studio/test_timeline.py
git commit -m "Check a studio edit before anything renders, and say what is wrong"
```

---

### Task 5: The ffmpeg command, and the assembly job

**Files:**
- Create: `studio/assemble.py`
- Test: `studio/test_assemble.py`

**Interfaces:**
- Consumes: a plan from `timeline.normalise` (Task 4), with each caption given a `path` before `command` is called; `images.draw(jobs)` (Task 8, imported lazily inside `run` so this task tests without it); `library.probe` (Task 1); `errors.last_line` (Task 1).
- Produces: `assemble.command(plan, out) -> list[str]`; `assemble.estimate(plan) -> float` seconds; `assemble.run(plan, out) -> dict(out, seconds, bytes, took)`; `assemble.CAPTION_HEIGHT = 0.14`; `python -m studio.assemble --plan P --out O --job J` prints `PROGRESS`/`DONE`/`FAILED` lines.

- [ ] **Step 1: Write the failing test**

**File: `studio/test_assemble.py`**
```python
"""The ffmpeg command an edit becomes. Strings only: no ffmpeg runs here.

    studio/.venv/bin/python studio/test_assemble.py

Task 10 renders real edits; this pins what the command asks for, so a
change that drops the ducking or shifts a transition shows up in a second.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import assemble as A  # noqa: E402


def still(path, seconds, start, move="none", transition="cut", fit="cover"):
    return dict(path=path, id="x", kind="image", start=start, seconds=seconds,
                from_=0.0, transition=transition, fit=fit, move=move, level=1.0, sound=False)


def plan(**over):
    p = dict(width=1920, height=1080, fps=30.0, name="t", seconds=13.0, audio_only=False,
             video=[still("/m/card.png", 3, 0.0),
                    dict(path="/m/clip.mov", id="clip", kind="video", start=2.5, seconds=6,
                         from_=2.0, transition="dissolve", fit="contain", move="none",
                         level=1.0, sound=True),
                    still("/m/pic.png", 5, 8.0, move="push-in", transition="fade")],
             overlays=[dict(path="/m/lower.png", id="o", at=4.0, seconds=3.0, place="bottom",
                            width=1600, height=200)],
             captions=[dict(text="Three in the morning.", at=0.5, seconds=1.2, path="/c/0.png")],
             audio=[dict(path="/m/voice.wav", id="v", at=0.5, level=1.0, fade=0.0, duck=False,
                         speech=True, seconds=3.6),
                    dict(path="/m/music.wav", id="m", at=0.0, level=0.15, fade=1.0, duck=True,
                         speech=False, seconds=30.0)])
    p.update(over)
    return p


def graph(args):
    return args[args.index("-filter_complex") + 1]


def test_video_trims_and_fits():
    args = A.command(plan(), "/r/out.mp4")
    i = args.index("/m/clip.mov")
    assert args[i - 5:i] == ["-ss", "2.000", "-t", "6.000", "-i"], args[i - 5:i]
    g = graph(args)
    assert "force_original_aspect_ratio=decrease,pad=1920:1080" in g  # contain
    assert "force_original_aspect_ratio=increase,crop=1920:1080" in g  # cover


def test_transitions():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "xfade=transition=dissolve:duration=0.5:offset=2.500" in g, g
    assert "xfade=transition=fadeblack:duration=0.5:offset=8.000" in g, g
    cut = plan()
    cut["video"][1]["transition"] = "cut"
    assert "concat=n=2:v=1:a=0" in graph(A.command(cut, "/r/out.mp4"))


def test_push_in_moves_over_every_frame():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "zoompan=z=1+0.12*(on/149)" in g and ":d=150:s=1920x1080" in g, g


def test_overlays_and_captions_are_timed():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "setpts=PTS-STARTPTS+4.000/TB" in g and "setpts=PTS-STARTPTS+0.500/TB" in g, g
    assert g.count("overlay=x=") == 2 and "eof_action=pass" in g, g


def test_music_ducks_under_speech():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "sidechaincompress" in g and "asplit=2" in g, g
    assert "adelay=500:all=1" in g, g


def test_clip_sound_is_placed_at_its_start():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "adelay=2500:all=1[va1]" in g, g


def test_silence_when_there_is_no_audio():
    p = plan(audio=[], captions=[])
    p["video"][1]["sound"] = False
    args = A.command(p, "/r/out.mp4")
    assert "anullsrc=r=48000:cl=stereo" in args, args


def test_audio_only_makes_m4a():
    p = plan(audio_only=True, video=[], overlays=[], captions=[], seconds=30.0)
    args = A.command(p, "/r/out.m4a")
    assert "[vout]" not in " ".join(args) and args[-1] == "/r/out.m4a", args
    assert args[args.index("-c:a") + 1] == "aac"


def test_output_is_h264_aac_and_exact_length():
    args = A.command(plan(), "/r/out.mp4")
    for flag, value in (("-c:v", "libx264"), ("-pix_fmt", "yuv420p"), ("-c:a", "aac"), ("-t", "13.000")):
        last = len(args) - 1 - args[::-1].index(flag)  # inputs have their own -t
        assert args[last + 1] == value, (flag, args)


def test_estimate_grows_with_length_and_size():
    small = A.estimate(plan(seconds=10.0, width=1280, height=720))
    big = A.estimate(plan(seconds=60.0))
    assert 0 < small < big, (small, big)


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

- [ ] **Step 2: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_assemble.py`
Expected: `ImportError: cannot import name 'assemble'`

- [ ] **Step 3: Write assembly**

**File: `studio/assemble.py`**
```python
"""Turn a checked edit into one ffmpeg run, as a background job.

    studio/.venv/bin/python -m studio.assemble --plan plan.json --out x.mp4 --job 5a1c

Text is drawn first: every caption the edit needs, in one GIMP session.
Then one ffmpeg command does the rest -- trims, fits, moves on stills,
transitions, overlays, the audio mix with ducking -- so there is a single
encode and no generation loss between steps.

This ffmpeg has no drawtext or subtitles filter, which is why text arrives
as pictures.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from studio import library  # noqa: E402
from studio.errors import last_line  # noqa: E402
from studio.timeline import TRANSITION  # noqa: E402

ZOOM = 0.12            # how far push-in, pull-out and the pans travel
SR = 48000
CAPTION_HEIGHT = 0.14  # of the frame's height
# Seconds of work per second of 1080p30 edit, measured on this Mac (Task 10).
RATE = 1.0


def _fit(fit: str, w: int, h: int) -> str:
    if fit == "contain":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


def _zoom(move: str, frames: int) -> str:
    """zoompan's z, x and y for a move spread over `frames` frames."""
    p = f"(on/{max(frames - 1, 1)})"
    y = "y=ih/2-(ih/zoom/2)"
    if move == "push-in":
        return f"z=1+{ZOOM}*{p}:x=iw/2-(iw/zoom/2):{y}"
    if move == "pull-out":
        return f"z=1+{ZOOM}*(1-{p}):x=iw/2-(iw/zoom/2):{y}"
    span = "(iw-iw/zoom)"
    if move == "pan-left":
        return f"z={1 + ZOOM}:x={span}*(1-{p}):{y}"
    return f"z={1 + ZOOM}:x={span}*{p}:{y}"


def _size(place: str, w: int, h: int, W: int, H: int) -> tuple[int, int]:
    """An overlay's drawn size: full fills the frame, the rest fit inside."""
    k = min(W / w, H / h) if place == "full" else min(1.0, W / w, H / h)
    return max(2, round(w * k) // 2 * 2), max(2, round(h * k) // 2 * 2)


def _place(place: str, w: int, h: int, W: int, H: int) -> tuple[int, int]:
    m = round(0.04 * H)
    cx, cy = (W - w) // 2, (H - h) // 2
    return {"full": (cx, cy), "center": (cx, cy), "top": (cx, m),
            "bottom": (cx, H - h - m), "top-left": (m, m),
            "top-right": (W - w - m, m), "bottom-left": (m, H - h - m),
            "bottom-right": (W - w - m, H - h - m)}[place]


def _sound(level: float) -> str:
    return (f"aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS,volume={level:g}")


def command(plan: dict, out: str) -> list[str]:
    """The one ffmpeg command that renders `plan` to `out`."""
    W, H, fps, T = plan["width"], plan["height"], plan["fps"], plan["seconds"]
    args = ["ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1"]
    graph: list[str] = []
    count = 0

    def source(path: str, *opts: str) -> int:
        nonlocal count
        args.extend([*opts, "-i", path])
        count += 1
        return count - 1

    mix: list[tuple[str, bool, bool]] = []  # (label, speech, ducked)
    if not plan["audio_only"]:
        tail = f"fps={fps:g},setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS"
        for i, v in enumerate(plan["video"]):
            frames = max(1, round(v["seconds"] * fps))
            if v["kind"] == "image" and v["move"] != "none":
                k = source(v["path"])
                graph.append(f"[{k}:v]{_fit(v['fit'], 2 * W, 2 * H)},"
                             f"zoompan={_zoom(v['move'], frames)}:d={frames}"
                             f":s={W}x{H}:fps={fps:g},{tail}[v{i}]")
            elif v["kind"] == "image":
                k = source(v["path"], "-loop", "1", "-framerate", f"{fps:g}",
                           "-t", f"{v['seconds']:.3f}")
                graph.append(f"[{k}:v]{_fit(v['fit'], W, H)},{tail}[v{i}]")
            else:
                k = source(v["path"], "-ss", f"{v['from_']:.3f}",
                           "-t", f"{v['seconds']:.3f}")
                graph.append(f"[{k}:v]{_fit(v['fit'], W, H)},{tail}[v{i}]")
                if v["sound"] and v["level"] > 0:
                    graph.append(f"[{k}:a]{_sound(v['level'])},"
                                 f"adelay={round(v['start'] * 1000)}:all=1"
                                 f"[va{i}]")
                    mix.append((f"va{i}", False, False))

        acc = "v0"
        if plan["video"][0]["transition"] != "cut":
            graph.append(f"[v0]fade=t=in:d={TRANSITION}[v0in]")
            acc = "v0in"
        for i, v in enumerate(plan["video"][1:], 1):
            if v["transition"] == "cut":
                graph.append(f"[{acc}][v{i}]concat=n=2:v=1:a=0[c{i}]")
            else:
                kind = "dissolve" if v["transition"] == "dissolve" else "fadeblack"
                graph.append(f"[{acc}][v{i}]xfade=transition={kind}"
                             f":duration={TRANSITION}:offset={v['start']:.3f}"
                             f"[c{i}]")
            acc = f"c{i}"

        ch = round(H * CAPTION_HEIGHT)
        layers = [(o["path"], o["at"], o["seconds"], o["place"], o["width"],
                   o["height"]) for o in plan["overlays"]]
        layers += [(c["path"], c["at"], c["seconds"], "bottom", W, ch)
                   for c in plan["captions"]]
        for j, (path, at, secs, place, w, h) in enumerate(layers):
            if at >= T:
                continue
            secs = min(secs, T - at)
            k = source(path, "-loop", "1", "-framerate", f"{fps:g}",
                       "-t", f"{secs:.3f}")
            dw, dh = _size(place, w, h, W, H)
            x, y = _place(place, dw, dh, W, H)
            graph.append(f"[{k}:v]scale={dw}:{dh},format=rgba,"
                         f"setpts=PTS-STARTPTS+{at:.3f}/TB[o{j}]")
            graph.append(f"[{acc}][o{j}]overlay=x={x}:y={y}:eof_action=pass"
                         f"[w{j}]")
            acc = f"w{j}"
        graph.append(f"[{acc}]trim=duration={T:.3f},format=yuv420p[vout]")

    for m, a in enumerate(plan["audio"]):
        if a["at"] >= T:
            continue
        length = min(a["seconds"], T - a["at"])
        k = source(a["path"])
        chain = f"[{k}:a]atrim=end={length:.3f},{_sound(a['level'])}"
        if a["fade"] > 0:
            f = min(a["fade"], length / 2)
            chain += (f",afade=t=in:d={f:.3f}"
                      f",afade=t=out:st={length - f:.3f}:d={f:.3f}")
        chain += f",adelay={round(a['at'] * 1000)}:all=1"
        graph.append(chain + f"[a{m}]")
        mix.append((f"a{m}", a["speech"], a["duck"]))

    speech = [x for x, s, d in mix if s]
    ducked = [x for x, s, d in mix if d and not s]
    final = [x for x, s, d in mix if not s and not d]
    if speech and ducked:
        graph.append("".join(f"[{x}]" for x in speech)
                     + f"amix=inputs={len(speech)}:normalize=0:duration=longest,"
                     + f"asplit={len(ducked) + 1}"
                     + "".join(f"[sc{i}]" for i in range(len(ducked) + 1)))
        final.append("sc0")
        for i, x in enumerate(ducked, 1):
            graph.append(f"[{x}][sc{i}]sidechaincompress=threshold=0.02"
                         f":ratio=8:attack=20:release=400[dk{i}]")
            final.append(f"dk{i}")
    else:
        final += speech + ducked
    if final:
        graph.append("".join(f"[{x}]" for x in final)
                     + f"amix=inputs={len(final)}:normalize=0:duration=longest,"
                     + f"apad=whole_dur={T:.3f},atrim=end={T:.3f},"
                     + "alimiter=limit=0.95[aout]")
    else:
        k = source(f"anullsrc=r={SR}:cl=stereo", "-f", "lavfi",
                   "-t", f"{T:.3f}")
        graph.append(f"[{k}:a]anull[aout]")

    args += ["-filter_complex", ";".join(graph)]
    if plan["audio_only"]:
        return args + ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
                       "-t", f"{T:.3f}", out]
    return args + ["-map", "[vout]", "-map", "[aout]", "-c:v", "libx264",
                   "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-r", f"{fps:g}", "-c:a", "aac", "-b:a", "192k",
                   "-movflags", "+faststart", "-t", f"{T:.3f}", out]


def estimate(plan: dict) -> float:
    """Seconds this will take, from the speed measured on this Mac."""
    px = plan["width"] * plan["height"] / (1920 * 1080)
    frames = plan["fps"] / 30.0
    draw = 6 + 0.2 * len(plan["captions"]) if plan["captions"] else 0
    return 3 + draw + plan["seconds"] * RATE * (px * frames if not plan["audio_only"] else 0.05)


def _say(stage: str, percent: float) -> None:
    print("PROGRESS " + json.dumps(dict(stage=stage, percent=round(percent))),
          flush=True)


def run(plan: dict, out: str) -> dict:
    """Draw the text, run ffmpeg, and report progress on stdout."""
    began = time.time()
    if plan["captions"]:
        from studio import images
        _say("drawing captions", 0)
        tmp = tempfile.mkdtemp(prefix="studio-captions-")
        jobs = []
        for i, c in enumerate(plan["captions"]):
            c["path"] = os.path.join(tmp, f"caption-{i:03d}.png")
            jobs.append(dict(kind="caption", out=c["path"], text=c["text"],
                             width=plan["width"],
                             height=round(plan["height"] * CAPTION_HEIGHT)))
        images.draw(jobs)
    _say("encoding", 0)
    p = subprocess.Popen(command(plan, out), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    shown = -5.0
    for line in p.stdout:
        if line.startswith("out_time_us="):
            try:
                done = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                continue
            percent = min(99.0, 100.0 * done / max(plan["seconds"], 0.001))
            if percent - shown >= 5:
                _say("encoding", percent)
                shown = percent
    err = p.stderr.read()
    p.wait()
    if p.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("ffmpeg stopped: " + last_line(err))
    return dict(out=out, seconds=library.probe(out)["seconds"],
                bytes=os.path.getsize(out), took=round(time.time() - began, 1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--job", default="")
    a = ap.parse_args()
    try:
        with open(a.plan) as fh:
            plan = json.load(fh)
        print("DONE " + json.dumps(run(plan, a.out)), flush=True)
    except Exception as e:
        print(f"FAILED {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_assemble.py`
Expected: `10/10 passed`

- [ ] **Step 5: Commit**

```bash
git add studio/assemble.py studio/test_assemble.py
git commit -m "Render a studio edit as one ffmpeg command, run as a job"
```

---

### Task 6: Speech

**Files:**
- Create: `studio/speech.py`, `studio/speech_engine.py`
- Test: `studio/test_speech.py`

**Interfaces:**
- Consumes: `library.add` (Task 1), `memory.refusal` (Task 2), `errors.last_line` (Task 1); `lectern.narrate` CLI (`--text --out --speed`, writes stem.wav and stem.json with `words`).
- Produces: `speech.VOICES` (tuple of 7); `speech.words(raw) -> [{text, start, end}]`; `speech.speak(text, voice="am_michael", speed=1.0) -> note` with prefix `voice`, extra `text, voice, words`.

- [ ] **Step 1: Write the failing test**

**File: `studio/test_speech.py`**
```python
"""Speech's word handling, without speaking. Task 10 speaks for real.

    studio/.venv/bin/python studio/test_speech.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import speech as S  # noqa: E402


def test_punctuation_joins_the_word_before():
    raw = [dict(text="Hello", start=0.0, end=0.4), dict(text=",", start=0.4, end=0.4),
           dict(text="world", start=0.5, end=0.9), dict(text=".", start=0.9, end=0.9)]
    assert S.words(raw) == [dict(text="Hello,", start=0.0, end=0.4),
                            dict(text="world.", start=0.5, end=0.9)]


def test_blank_tokens_are_dropped_and_times_rounded():
    raw = [dict(text=" ", start=0, end=0), dict(text="Hi", start=0.123456, end=0.4567)]
    assert S.words(raw) == [dict(text="Hi", start=0.123, end=0.457)]


def test_unknown_voice_is_a_sentence():
    try:
        S.speak("hello", voice="morgan")
    except ValueError as e:
        assert e.args[0].startswith("there is no voice called morgan; the voices are am_michael"), e
    else:
        raise AssertionError("an unknown voice spoke")


def test_nothing_to_say():
    try:
        S.speak("   ")
    except ValueError as e:
        assert e.args[0] == "there is nothing to say"
    else:
        raise AssertionError("silence was spoken")


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

- [ ] **Step 2: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_speech.py`
Expected: `ImportError: cannot import name 'speech'`

- [ ] **Step 3: Write speech and its engine**

**File: `studio/speech_engine.py`**
```python
"""Plain Kokoro speech: text in, a wav and every word's timing out.

Runs under .ttsvenv, never the studio's own interpreter:

    .ttsvenv/bin/python studio/speech_engine.py --text "..." --voice af_heart \
        --speed 1 --out /tmp/stem

writes stem.wav and stem.json. Kokoro speaks long text in pieces and times
each word from the start of its own piece, so the lengths of the pieces
before it are added back here. Without that, every caption after the first
piece would come up early.
"""

import argparse
import json

import numpy as np
import soundfile as sf
from kokoro import KPipeline

SR = 24000


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", required=True, help="path stem, no extension")
    a = ap.parse_args()

    # The voice's first letter is its accent: a for American, b for British.
    pipe = KPipeline(lang_code=a.voice[0], repo_id="hexgrad/Kokoro-82M")
    pieces, words, offset = [], [], 0.0
    for r in pipe(a.text, voice=a.voice, speed=a.speed):
        audio = r.audio.numpy()
        for t in (r.tokens or []):
            if t.start_ts is not None and t.end_ts is not None:
                words.append(dict(text=t.text, start=offset + float(t.start_ts),
                                  end=offset + float(t.end_ts)))
        pieces.append(audio)
        offset += len(audio) / SR
    wav = np.concatenate(pieces)
    sf.write(a.out + ".wav", wav, SR)
    with open(a.out + ".json", "w") as fh:
        json.dump(dict(seconds=len(wav) / SR, words=words), fh)
    print(json.dumps(dict(seconds=round(len(wav) / SR, 3), words=len(words))))


if __name__ == "__main__":
    main()
```

**File: `studio/speech.py`**
```python
"""Speech from text, with the time every word is said.

Kokoro does the speaking, under `.ttsvenv`, because torch and Kokoro live
there and nowhere else. The six plain voices go through speech_engine.py;
`einstein` is lectern's blended, accented voice and goes through
lectern.narrate, which already times every word. Either way the words come
back with a start and an end, and captions are drawn from them.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile

from studio import library, memory
from studio.errors import last_line

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS = os.environ.get("STUDIO_TTS", os.path.join(HERE, ".ttsvenv", "bin", "python"))
ENGINE = os.path.join(HERE, "studio", "speech_engine.py")
VOICES = ("am_michael", "am_onyx", "af_heart", "af_nova", "bm_george",
          "bf_emma", "einstein")


def words(raw: list[dict]) -> list[dict]:
    """Kokoro's tokens as words: punctuation joins the word before it."""
    out: list[dict] = []
    for t in raw:
        text = t["text"].strip()
        if not text:
            continue
        if out and not re.search(r"\w", text):
            out[-1]["text"] += text
            continue
        out.append(dict(text=text, start=round(float(t["start"]), 3),
                        end=round(float(t["end"]), 3)))
    return out


def speak(text: str, voice: str = "am_michael", speed: float = 1.0) -> dict:
    """Say `text` in `voice`, and file it in the library with its words."""
    if not text.strip():
        raise ValueError("there is nothing to say")
    if voice not in VOICES:
        raise ValueError(f"there is no voice called {voice}; the voices are "
                         f"{', '.join(VOICES)}")
    refused = memory.refusal("speech")
    if refused:
        raise MemoryError(refused)
    with tempfile.TemporaryDirectory(prefix="studio-speech-") as tmp:
        stem = os.path.join(tmp, "speech")
        if voice == "einstein":
            # 0.94 is lectern's own pace for him; `speed` scales it.
            cmd = [TTS, "-m", "lectern.narrate", "--text", text, "--out", stem,
                   "--speed", f"{0.94 * speed:.3f}"]
        else:
            cmd = [TTS, ENGINE, "--text", text, "--voice", voice,
                   "--speed", f"{speed:.3f}", "--out", stem]
        r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                           timeout=1800)
        if r.returncode != 0 or not os.path.exists(stem + ".wav"):
            raise RuntimeError("speech stopped: "
                               + last_line(r.stderr or r.stdout))
        with open(stem + ".json") as fh:
            timing = json.load(fh)
        return library.add(stem + ".wav", "voice", source=f"speech: {voice}",
                           move=True, text=text, voice=voice,
                           words=words(timing["words"]))
```

- [ ] **Step 4: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_speech.py`
Expected: `4/4 passed`

- [ ] **Step 5: Commit**

```bash
git add studio/speech.py studio/speech_engine.py studio/test_speech.py
git commit -m "Speak text in any of seven voices, keeping every word's timing"
```

---

### Task 7: Music

**Files:**
- Create: `studio/music.py`
- Test: `studio/test_music.py`

**Interfaces:**
- Consumes: `lectern.score.render(duration, out, mood)` and `lectern.score.MOODS`; `library.add` (Task 1).
- Produces: `music.MOODS` (tuple); `music.compose(mood="drive", seconds=30.0) -> note` with prefix `music`, extra `mood`.

- [ ] **Step 1: Write the failing test**

**File: `studio/test_music.py`**
```python
"""Music beds, composed for real: numpy only, a few seconds.

    studio/.venv/bin/python studio/test_music.py
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import music as M  # noqa: E402


def test_moods_come_from_the_composer():
    assert M.MOODS == ("drive", "open", "night"), M.MOODS


def test_exact_length_in_the_library():
    note = M.compose("night", 3.0)
    assert note["id"].startswith("music-") and note["kind"] == "audio", note
    assert abs(note["seconds"] - 3.0) < 0.05, note
    assert note["mood"] == "night" and os.path.exists(note["path"])


def test_unknown_mood_is_a_sentence():
    try:
        M.compose("jazz", 3)
    except ValueError as e:
        assert e.args[0] == "there is no mood called jazz; the moods are drive, open, night", e
    else:
        raise AssertionError("jazz was composed")


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

- [ ] **Step 2: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_music.py`
Expected: `ImportError: cannot import name 'music'`

- [ ] **Step 3: Write music**

**File: `studio/music.py`**
```python
"""A music bed from a mood, exactly as long as asked.

Written, not modelled: the numpy composer in highway3d/music.py, through
lectern.score, which reads the moods off it rather than keeping a copy. No
weights, no licence that follows the output, and too little memory to be
worth guarding.
"""

from __future__ import annotations

import os
import tempfile

from lectern import score
from studio import library

MOODS = tuple(score.MOODS)


def compose(mood: str = "drive", seconds: float = 30.0) -> dict:
    """A bed of `seconds` in `mood`, filed in the library."""
    if mood not in MOODS:
        raise ValueError(f"there is no mood called {mood}; the moods are "
                         f"{', '.join(MOODS)}")
    fd, out = tempfile.mkstemp(prefix="studio-music-", suffix=".wav")
    os.close(fd)
    try:
        score.render(float(seconds), out, mood)
        return library.add(out, "music", source=f"music: {mood}", move=True,
                           mood=mood)
    finally:
        if os.path.exists(out):
            os.remove(out)
```

- [ ] **Step 4: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_music.py`
Expected: `3/3 passed`

- [ ] **Step 5: Commit**

```bash
git add studio/music.py studio/test_music.py
git commit -m "Compose music beds for the studio from the existing composer"
```

---

### Task 8: Cards, captions and pictures

**Files:**
- Create: `studio/xai.py`, `studio/images.py`, `studio/gimp_draw.py`
- Test: `studio/test_xai.py`

**Interfaces:**
- Consumes: `library.add`, `library.resolve` (Task 1); `memory.refusal` (Task 2); `errors.last_line` (Task 1).
- Produces: `xai.MODEL`, `xai.ASPECTS`, `xai.RESOLUTIONS`, `xai.Refused`, `xai.extension(data) -> str`, `xai.image(prompt, aspect, resolution, references=(), key=None, opener=urlopen) -> bytes`; `images.STYLES = ("dark", "light", "chalkboard", "sign")`; `images.draw(jobs)`; `images.card(title, subtitle="", style="dark", width=1920, height=1080) -> note` (prefix `card`); `images.picture(prompt, aspect="16:9", resolution="2k", references=()) -> note` (prefix `pic`). Draw jobs: `{"kind": "card", out, width, height, style, title, subtitle}` or `{"kind": "caption", out, width, height, text}`.

- [ ] **Step 1: Write the failing test**

**File: `studio/test_xai.py`**
```python
"""The xAI client against a fake server: requests, replies and every failure.

    studio/.venv/bin/python studio/test_xai.py

No credit is spent here. Task 10 makes one real picture once a key exists.
"""

import base64
import io
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import xai as X  # noqa: E402

KEY = "xai-secret-never-shown"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake(status=200, body=None, sent=None):
    def opener(req, timeout=0):
        if sent is not None:
            sent.append((req.full_url, json.loads(req.data), dict(req.header_items())))
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "no", {},
                                         io.BytesIO(json.dumps(body).encode()))
        return Reply(json.dumps(body).encode())
    return opener


OK = {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}


def test_no_key_is_a_sentence():
    try:
        X.image("a fox", key="")
    except X.Refused as e:
        assert str(e) == "No xAI key is set; put XAI_API_KEY in the environment the studio server runs in."
    else:
        raise AssertionError("no key, and yet a picture")


def test_generation_request_shape():
    sent = []
    data = X.image("a fox", "9:16", "1k", key=KEY, opener=fake(body=OK, sent=sent))
    assert data == PNG
    url, body, headers = sent[0]
    assert url.endswith("/images/generations"), url
    assert body == dict(model=X.MODEL, prompt="a fox", n=1, aspect_ratio="9:16",
                        resolution="1k", response_format="b64_json"), body
    assert headers["Authorization"] == f"Bearer {KEY}"


def test_references_use_the_edits_endpoint():
    ref = os.path.join(tempfile.mkdtemp(), "layout.png")
    with open(ref, "wb") as fh:
        fh.write(PNG)
    sent = []
    X.image("repaint this", references=[ref], key=KEY, opener=fake(body=OK, sent=sent))
    url, body, _ = sent[0]
    assert url.endswith("/images/edits"), url
    assert body["images"][0]["type"] == "image_url"
    assert body["images"][0]["url"].startswith("data:image/png;base64,")


def test_failures_say_which_kind():
    cases = [
        (402, {"error": "Payment required"}, "The xAI credits are used up; add more at console.x.ai."),
        (403, {"error": "Your team has run out of credits"}, "The xAI credits are used up; add more at console.x.ai."),
        (401, {"error": "Incorrect API key provided"}, "xAI refused the key (HTTP 401): Incorrect API key provided"),
        (400, {"error": "Generated image rejected by content moderation"},
         "xAI refused the prompt: Generated image rejected by content moderation"),
        (500, {"error": "boom"}, "xAI answered HTTP 500: boom"),
    ]
    for status, body, want in cases:
        try:
            X.image("a fox", key=KEY, opener=fake(status, body))
        except X.Refused as e:
            assert str(e) == want, (status, str(e))
            assert KEY not in str(e)
        else:
            raise AssertionError(f"HTTP {status} made a picture")


def test_reply_without_a_picture():
    try:
        X.image("a fox", key=KEY, opener=fake(body={"data": []}))
    except X.Refused as e:
        assert str(e) == "xAI answered without a picture in the reply."
    else:
        raise AssertionError("an empty reply made a picture")


def test_extension_from_bytes():
    assert X.extension(PNG) == ".png"
    assert X.extension(b"\xff\xd8\xff\xe0") == ".jpg"
    assert X.extension(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp"


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

- [ ] **Step 2: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_xai.py`
Expected: `ImportError: cannot import name 'xai'`

- [ ] **Step 3: Write the xAI client**

**File: `studio/xai.py`**
```python
"""Pictures from xAI's image model, paid for from prepaid credit.

Reads XAI_API_KEY from the environment and nowhere else, and never writes
it anywhere: not to a log, a note or a result. Every failure is a sentence
that says which kind it is, because "the credits are used up" and "that
prompt was refused" call for different things from whoever asked.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("STUDIO_XAI_URL", "https://api.x.ai/v1")
MODEL = "grok-imagine-image-2.0"
ASPECTS = ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "auto")
RESOLUTIONS = ("1k", "1.5k", "2k")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"}


class Refused(Exception):
    """xAI did not make the picture; the message says why, in a sentence."""


def extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def _data_uri(path: str) -> str:
    with open(path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode()
    mime = MIME.get(os.path.splitext(path)[1].lower(), "image/png")
    return f"data:{mime};base64,{encoded}"


def _why(code: int, text: str) -> str:
    try:
        message = json.loads(text).get("error", text)
    except (ValueError, AttributeError):
        message = text
    if isinstance(message, dict):
        message = message.get("message", json.dumps(message))
    message = " ".join(str(message).split())[:300]
    low = message.lower()
    if code == 402 or any(w in low for w in ("credit", "balance",
                                             "spending limit", "insufficient")):
        return "The xAI credits are used up; add more at console.x.ai."
    if code == 401 or (code == 403 and ("key" in low or "auth" in low)):
        return f"xAI refused the key (HTTP {code}): {message}"
    if code == 400 and any(w in low for w in ("policy", "moderation", "safety",
                                              "not allowed")):
        return f"xAI refused the prompt: {message}"
    return f"xAI answered HTTP {code}: {message}"


def image(prompt: str, aspect: str = "16:9", resolution: str = "2k",
          references=(), key: str | None = None,
          opener=urllib.request.urlopen) -> bytes:
    """One picture's bytes, or Refused with a sentence saying why not."""
    key = os.environ.get("XAI_API_KEY", "") if key is None else key
    if not key:
        raise Refused("No xAI key is set; put XAI_API_KEY in the environment "
                      "the studio server runs in.")
    body = dict(model=MODEL, prompt=prompt, n=1, aspect_ratio=aspect,
                resolution=resolution, response_format="b64_json")
    path = "/images/generations"
    if references:
        body["images"] = [dict(type="image_url", url=_data_uri(p))
                          for p in references]
        path = "/images/edits"
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with opener(req, timeout=300) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        raise Refused(_why(e.code, e.read().decode(errors="replace"))) from None
    except (urllib.error.URLError, OSError) as e:
        raise Refused(f"Could not reach xAI: {getattr(e, 'reason', e)}.") from None
    try:
        return base64.b64decode(reply["data"][0]["b64_json"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise Refused("xAI answered without a picture in the reply.") from None
```

- [ ] **Step 4: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_xai.py`
Expected: `6/6 passed`

- [ ] **Step 5: Write the GIMP drawing script and images**

**File: `studio/gimp_draw.py`**
```python
"""Runs inside GIMP. Draws every card and caption a job list asks for.

    gimp-console-3.2 -i --batch-interpreter=python-fu-eval \
        -b "STUDIO_JOBS = '/path/jobs.json'; exec(open('studio/gimp_draw.py').read())" --quit

Each job is {"kind": "card" | "caption", "out", "width", "height", ...}.
Cards take a style, a title and a subtitle. Captions take one chunk of
speech and are drawn on a transparent ground, so they can be laid over the
picture. Text arrives in the JSON file, never through a shell, so quotes,
dashes and accents draw as written.
"""

import json

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, Gio  # noqa: E402

STYLES = {
    "dark": dict(ground="#15181d", title="#f4f1ea", sub="#aeb6c2",
                 fonts=("Sans-serif Bold", "Sans-serif"), grime=0.0),
    "light": dict(ground="#f3efe6", title="#1b1d22", sub="#5a6170",
                  fonts=("Sans-serif Bold", "Sans-serif"), grime=0.0),
    "chalkboard": dict(ground="#243129", title="#f1efe4", sub="#cfd8cf",
                       fonts=("Chalkduster", "Chalkboard SE"), grime=18.0),
    "sign": dict(ground="#00694a", title="#ffffff", sub="#ffffff",
                 fonts=("Sans-serif Bold", "Sans-serif Bold"), grime=14.0,
                 border="#ffffff"),
}


def font(name):
    return Gimp.Font.get_by_name(name) or Gimp.Font.get_by_name("Sans-serif")


def new_layer(img, name, opacity=100.0, mode=Gimp.LayerMode.NORMAL):
    lay = Gimp.Layer.new(img, name, img.get_width(), img.get_height(),
                         Gimp.ImageType.RGBA_IMAGE, opacity, mode)
    img.insert_layer(lay, None, 0)
    return lay


def select(img, inset=0, radius=0):
    w, h = img.get_width() - 2 * inset, img.get_height() - 2 * inset
    if radius:
        img.select_round_rectangle(Gimp.ChannelOps.REPLACE, inset, inset, w,
                                   h, radius, radius)
    else:
        img.select_rectangle(Gimp.ChannelOps.REPLACE, inset, inset, w, h)


def fill(img, lay, colour, inset=0, radius=0):
    select(img, inset, radius)
    Gimp.context_set_foreground(Gegl.Color.new(colour))
    lay.edit_fill(Gimp.FillType.FOREGROUND)
    Gimp.Selection.none(img)


def text(img, words, size, face, colour, widest):
    """A text layer no wider than `widest`, the type shrunk until it fits."""
    Gimp.context_set_foreground(Gegl.Color.new(colour))
    while True:
        t = Gimp.text_font(img, None, 0, 0, words, 0, True, size, face)
        if t.get_width() <= widest or size <= 12:
            return t
        img.remove_layer(t)
        size = int(size * 0.9)


def save(img, out):
    img.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(out),
                   None)
    img.delete()


def card(job):
    W, H, s = job["width"], job["height"], STYLES[job["style"]]
    img = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
    ground = new_layer(img, "ground")
    r = int(min(W, H) * 0.05)
    if s.get("border"):
        fill(img, ground, s["border"], 0, r)
        fill(img, ground, s["ground"], int(min(W, H) * 0.02), int(r * 0.75))
    else:
        fill(img, ground, s["ground"])
    if s["grime"]:
        grime = new_layer(img, "grime", s["grime"], Gimp.LayerMode.OVERLAY)
        grime.append_filter(Gimp.DrawableFilter.new(grime, "gegl:perlin-noise",
                                                    "grime"))
        grime.merge_filters()
        if s.get("border"):
            # keep the weathering off the rounded corners
            select(img, 0, r)
            Gimp.Selection.invert(img)
            grime.edit_clear()
            Gimp.Selection.none(img)
    widest = int(W * 0.86)
    title = text(img, job["title"], int(H * 0.13), font(s["fonts"][0]),
                 s["title"], widest)
    sub = None
    if job.get("subtitle"):
        sub = text(img, job["subtitle"], int(H * 0.055), font(s["fonts"][1]),
                   s["sub"], widest)
    gap = int(H * 0.03)
    block = title.get_height() + (gap + sub.get_height() if sub else 0)
    y = (H - block) // 2
    title.set_offsets((W - title.get_width()) // 2, y)
    if sub:
        sub.set_offsets((W - sub.get_width()) // 2, y + title.get_height() + gap)
    save(img, job["out"])


def caption(job):
    W, H = job["width"], job["height"]
    img = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
    band = new_layer(img, "band", 62.0)
    t = text(img, job["text"], int(H * 0.36), font("Sans-serif Bold"),
             "#ffffff", int(W * 0.9))
    pad_x, pad_y = int(H * 0.25), int(H * 0.12)
    bw, bh = t.get_width() + 2 * pad_x, t.get_height() + 2 * pad_y
    img.select_round_rectangle(Gimp.ChannelOps.REPLACE, (W - bw) // 2,
                               (H - bh) // 2, bw, bh, pad_y, pad_y)
    Gimp.context_set_foreground(Gegl.Color.new("#000000"))
    band.edit_fill(Gimp.FillType.FOREGROUND)
    Gimp.Selection.none(img)
    t.set_offsets((W - t.get_width()) // 2, (H - t.get_height()) // 2)
    save(img, job["out"])


with open(STUDIO_JOBS) as _fh:  # noqa: F821 -- set by the -b expression
    for _job in json.load(_fh):
        try:
            (card if _job["kind"] == "card" else caption)(_job)
        except Exception as _e:  # one bad job must not lose the rest
            print(f"could not draw {_job.get('out')}: {_e}")
```

**File: `studio/images.py`**
```python
"""Pictures for the studio: cards GIMP draws, and pictures xAI paints.

A card is text laid out on a plain ground -- title cards, lower thirds,
signs, end slates -- drawn by GIMP with no window open. Captions are drawn
the same way, by assemble.py, in one GIMP session with the rest of an
edit's text, because GIMP takes seconds to start and an edit can need
thirty captions.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

from studio import library, memory, xai
from studio.errors import last_line

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIMP = os.environ.get("STUDIO_GIMP",
                      "/Applications/GIMP.app/Contents/MacOS/gimp-console-3.2")
DRAW = os.path.join(HERE, "studio", "gimp_draw.py")
STYLES = ("dark", "light", "chalkboard", "sign")


def draw(jobs: list[dict]) -> None:
    """Draw every card and caption in `jobs`, in one GIMP session."""
    if not jobs:
        return
    refused = memory.refusal("gimp")
    if refused:
        raise MemoryError(refused)
    if not os.path.exists(GIMP):
        raise RuntimeError("GIMP is not installed here; brew install --cask gimp")
    fd, spec = tempfile.mkstemp(prefix="studio-draw-", suffix=".json")
    os.close(fd)
    try:
        with open(spec, "w") as fh:
            json.dump(jobs, fh)
        expr = f"STUDIO_JOBS = {spec!r}; exec(open({DRAW!r}).read())"
        r = subprocess.run([GIMP, "-i", "--batch-interpreter=python-fu-eval",
                            "-b", expr, "--quit"], capture_output=True,
                           text=True, timeout=900)
    finally:
        os.remove(spec)
    missing = [j["out"] for j in jobs if not os.path.exists(j["out"])]
    if missing:
        raise RuntimeError(f"GIMP drew {len(jobs) - len(missing)} of "
                           f"{len(jobs)} pictures: "
                           + last_line(r.stdout + "\n" + r.stderr))


def card(title: str, subtitle: str = "", style: str = "dark",
         width: int = 1920, height: int = 1080) -> dict:
    """A card drawn by GIMP, filed in the library."""
    if not title.strip():
        raise ValueError("a card needs a title")
    if style not in STYLES:
        raise ValueError(f"there is no style called {style}; the styles are "
                         f"{', '.join(STYLES)}")
    tmp = tempfile.mkdtemp(prefix="studio-card-")
    out = os.path.join(tmp, "card.png")
    draw([dict(kind="card", out=out, width=int(width), height=int(height),
               style=style, title=title, subtitle=subtitle)])
    note = library.add(out, "card", source=f"card: {style}", move=True,
                       title=title, subtitle=subtitle, style=style)
    os.rmdir(tmp)
    return note


def picture(prompt: str, aspect: str = "16:9", resolution: str = "2k",
            references=()) -> dict:
    """A picture from xAI, filed in the library."""
    if not prompt.strip():
        raise ValueError("a picture needs a prompt")
    if len(references) > 5:
        raise ValueError("xAI takes at most 5 reference pictures")
    paths = []
    for ref in references:
        note = library.resolve(ref)
        if note["kind"] != "image":
            raise ValueError(f"{ref} is {note['kind']}, and references must "
                             f"be pictures")
        paths.append(note["path"])
    data = xai.image(prompt, aspect, resolution, paths)
    fd, out = tempfile.mkstemp(prefix="studio-pic-", suffix=xai.extension(data))
    os.close(fd)
    with open(out, "wb") as fh:
        fh.write(data)
    return library.add(out, "pic", source=f"xai: {xai.MODEL}", move=True,
                       prompt=prompt, aspect=aspect, resolution=resolution,
                       references=list(references))
```

- [ ] **Step 6: Draw one card for real, and look at it**

Run:
```bash
studio/.venv/bin/python -c "
import os, tempfile; os.environ['STUDIO_MEDIA'] = tempfile.mkdtemp()
import sys; sys.path.insert(0, '.')
from studio import images
n = images.card('Pockterm', 'a terminal that does not mangle tmux', 'sign', 1280, 720)
print(n['path'], n['width'], n['height'])"
```
Expected: a path ending `.png` and `1280 720`. Open the PNG with the Read tool and check the text is centred and legible.

- [ ] **Step 7: Commit**

```bash
git add studio/xai.py studio/images.py studio/gimp_draw.py studio/test_xai.py
git commit -m "Draw cards and captions in GIMP and paint pictures with xAI"
```

---

### Task 9: The MCP server and README

**Files:**
- Create: `studio/mcp_server.py`, `studio/README.md`
- Test: `studio/test_server.py`

**Interfaces:**
- Consumes: everything above: `library`, `memory`, `jobs`, `timeline`, `assemble`, `speech`, `music`, `images`, `xai`; `forgiving.ForgivingServer`.
- Produces: tools `studio_describe`, `studio_import`, `studio_speak`, `studio_music`, `studio_card`, `studio_picture`, `studio_assemble`, `studio_status`, `studio_list`; `python -m studio.mcp_server --port 8768`.

- [ ] **Step 1: Write the failing test**

**File: `studio/test_server.py`**
```python
"""The studio's tools, called in-process the way a client calls them.

    studio/.venv/bin/python studio/test_server.py

Nothing heavy runs: no speech, no GIMP, no ffmpeg job. Those are Task 10.
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
os.environ["STUDIO_WORK"] = tempfile.mkdtemp(prefix="studio-work-")
os.environ.pop("XAI_API_KEY", None)
import anyio  # noqa: E402
from studio import mcp_server as S  # noqa: E402

TOOLS = {"studio_describe", "studio_import", "studio_speak", "studio_music", "studio_card",
         "studio_picture", "studio_assemble", "studio_status", "studio_list"}


def call(name, **args):
    r = anyio.run(lambda: S.mcp.call_tool(name, args))
    return r.content[0].text


def test_nine_tools_every_one_prefixed():
    names = {t.name for t in anyio.run(S.mcp.list_tools)}
    assert names == TOOLS, names


def test_descriptions_name_their_values():
    tools = {t.name: t.description for t in anyio.run(S.mcp.list_tools)}
    assert "am_michael" in tools["studio_speak"] and "einstein" in tools["studio_speak"]
    assert "drive, open or night" in tools["studio_music"]
    assert "dark" in tools["studio_card"] and "chalkboard" in tools["studio_card"]
    assert "16:9" in tools["studio_picture"] and "2k" in tools["studio_picture"]
    assert "dissolve" in tools["studio_assemble"] and "push-in" in tools["studio_assemble"]


def test_describe_has_the_catalogue_and_an_example():
    got = call("studio_describe")
    for word in ("am_michael", "night", "chalkboard", "16:9", '"video"', "captions"):
        assert word in got, word


def test_nothing_of_a_kind_and_no_jobs():
    assert call("studio_list", kind="video") == "There is no video in the library."
    assert call("studio_status") == "Nothing has been assembled on this server yet."


def test_bad_edit_is_refused_with_its_problems():
    got = call("studio_assemble", edit={"video": [{"asset": "clip-0000"}]})
    assert got.startswith("Not starting: the edit has problems."), got
    assert "there is no asset called clip-0000" in got, got


def test_edit_as_json_text():
    got = call("studio_assemble", edit='{"video": ["clip-0000"]}')
    assert "there is no asset called clip-0000" in got, got
    got = call("studio_assemble", edit="{not json")
    assert got.startswith("Not starting: the edit is not JSON"), got


def test_import_failure_is_a_sentence():
    got = call("studio_import", source="/nowhere/at/all.mp4")
    assert got == "Nothing was imported: there is no file at /nowhere/at/all.mp4.", got


def test_picture_without_a_key_is_a_sentence():
    got = call("studio_picture", prompt="a fox")
    assert got == ("No picture was made: No xAI key is set; put XAI_API_KEY in the "
                   "environment the studio server runs in."), got


def test_bad_values_are_mended_not_refused():
    got = call("studio_music", mood="jazz", seconds=2)
    assert got.startswith("mood 'jazz' is not one of drive, open, night, so it is drive."), got
    assert "music-" in got, got


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

- [ ] **Step 2: Run it and see it fail**

Run: `studio/.venv/bin/python studio/test_server.py`
Expected: `ImportError: cannot import name 'mcp_server'`

- [ ] **Step 3: Write the server**

**File: `studio/mcp_server.py`**
```python
"""MCP server for the studio: general audio and video tools.

    studio/.venv/bin/python -m studio.mcp_server --port 8768

Lectern makes lectures and highway makes highway drives. This makes the
pieces anything else is cut from -- speech, music, cards, pictures,
imported footage -- and cuts them together. A capable agent directs, one
small call at a time. Everything slow is a job, and every answer is a
sentence, because the caller is a model reading prose.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Annotated, Literal

from pydantic import Field

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from forgiving import ForgivingServer  # noqa: E402
from studio import (assemble, images, jobs, library, memory, music,  # noqa: E402
                    speech, timeline, xai)

RENDERS = os.environ.get("STUDIO_RENDERS", os.path.join(HERE, "renders"))

mcp = ForgivingServer(
    name="studio",
    title="Audio and video studio",
    version="1.0.0",
    instructions=(
        "Makes the pieces of a video and cuts them together. studio_speak, "
        "studio_music, studio_card and studio_picture make assets; "
        "studio_import brings in footage, pictures and sound by path or URL. "
        "Each returns an id. studio_assemble cuts ids together into an mp4 "
        "(or an m4a with no video) as a job, and studio_status says how it "
        "is going. studio_describe has the full edit format and an example."
    ),
)

EXAMPLE = {
    "size": "1920x1080", "fps": 30, "name": "pockterm-spot",
    "video": [{"asset": "card-1a2b", "seconds": 3},
              {"asset": "clip-9c01", "from": 12, "seconds": 6, "transition": "dissolve"},
              {"asset": "pic-44d0", "seconds": 5, "move": "push-in", "transition": "fade"}],
    "overlays": [{"asset": "card-7d3e", "at": 4, "seconds": 3, "place": "bottom"},
                 {"captions": "voice-3f2a"}],
    "audio": [{"asset": "voice-3f2a", "at": 0.5},
              {"asset": "music-77e1", "level": 0.15, "duck": True}],
}


def _sentence(e: BaseException) -> str:
    msg = str(e.args[0]) if getattr(e, "args", None) else str(e)
    return msg.rstrip(". ") + "."


def _wait(seconds: float) -> str:
    if seconds < 90:
        return f"about {max(5, round(seconds / 5) * 5):.0f} seconds"
    return f"about {round(seconds / 60):.0f} minutes"


@mcp.tool()
def studio_describe() -> str:
    """What the studio can make, and the edit format studio_assemble takes, with a worked example."""
    return "\n".join([
        "VOICES (studio_speak): am_michael and am_onyx (American men), af_heart and "
        "af_nova (American women), bm_george (British man), bf_emma (British woman), "
        "einstein (the lecture professor's German-accented voice).",
        f"MOODS (studio_music): {', '.join(music.MOODS)}.",
        f"CARD STYLES (studio_card): {', '.join(images.STYLES)}.",
        f"PICTURES (studio_picture, xAI {xai.MODEL}): aspect {', '.join(xai.ASPECTS)}; "
        f"resolution {', '.join(xai.RESOLUTIONS)}; up to 5 reference pictures.",
        "",
        "EDIT FORMAT (studio_assemble):",
        "  size WxH (default 1920x1080), fps (default 30), name.",
        "  video: a list played in order. Each item: asset (id or file path), seconds "
        "(stills default 4, clips run to their end), from (where in a clip to start), "
        f"transition ({', '.join(timeline.TRANSITIONS)}; 0.5 s), fit "
        f"({', '.join(timeline.FITS)}), move for stills ({', '.join(timeline.MOVES)}), "
        "level (the clip's own sound, 0 to 1).",
        f"  overlays: timed pictures {{asset, at, seconds, place: {', '.join(timeline.PLACES)}}}, "
        "or {captions: a speech id} to show its words as they are said.",
        "  audio: timed sound {asset, at, level 0 to 1, fade seconds, duck: true to dip "
        "under speech}. Music fades by default and is trimmed to the video.",
        "  With no video, the edit makes an m4a.",
        "",
        "EXAMPLE:",
        json.dumps(EXAMPLE, indent=1),
    ])


@mcp.tool()
def studio_import(
    source: Annotated[str, Field(description="A file path on this Mac, or an http(s) URL.")],
    name: Annotated[str, Field(description="A label for studio_list; edits still use the id.")] = "",
) -> str:
    """Bring a video, picture or sound into the library from a path on this Mac or a URL. Returns its id, what it is, and where the file is."""
    try:
        return library.said(library.import_(source, name)) + "."
    except Exception as e:
        return f"Nothing was imported: {_sentence(e)}"


@mcp.tool()
def studio_speak(
    text: Annotated[str, Field(description="What to say.")],
    voice: Annotated[Literal[speech.VOICES], Field(description="Who says it.")] = "am_michael",
    speed: Annotated[float, Field(ge=0.5, le=2.0, description="1 is natural pace.")] = 1.0,
) -> str:
    """Say text aloud and keep it as a sound, with every word's timing for captions. voice is am_michael (American man, the default), am_onyx (American man, deeper), af_heart or af_nova (American women), bm_george (British man), bf_emma (British woman) or einstein (the lecture professor's German-accented voice); speed is 0.5 to 2, 1 by default."""
    try:
        note = speech.speak(text, voice, speed)
    except Exception as e:
        return f"No speech was made: {_sentence(e)}"
    return f"{library.said(note)}. {len(note['words'])} words, timed for captions."


@mcp.tool()
def studio_music(
    mood: Annotated[Literal[music.MOODS], Field(description="The feel of the bed.")] = "drive",
    seconds: Annotated[float, Field(ge=1, le=600, description="How long.")] = 30.0,
) -> str:
    """Compose a music bed exactly as long as asked. mood is drive (patient, minor, the default), open (brighter, more motion) or night (sparse, almost no rhythm, best under speech); seconds is 1 to 600, 30 by default."""
    try:
        return library.said(music.compose(mood, seconds)) + "."
    except Exception as e:
        return f"No music was made: {_sentence(e)}"


@mcp.tool()
def studio_card(
    title: Annotated[str, Field(description="The main line.")],
    subtitle: Annotated[str, Field(description="A smaller second line.")] = "",
    style: Annotated[Literal[images.STYLES], Field(description="The look.")] = "dark",
    width: Annotated[int, Field(ge=64, le=7680)] = 1920,
    height: Annotated[int, Field(ge=64, le=4320)] = 1080,
) -> str:
    """Draw a text card with GIMP: title cards, lower thirds, signs, end slates. style is dark (the default), light, chalkboard or sign (a green highway sign); width and height default to 1920x1080 (a lower third might be 1600x200)."""
    try:
        return library.said(images.card(title, subtitle, style, width, height)) + "."
    except Exception as e:
        return f"No card was made: {_sentence(e)}"


@mcp.tool()
def studio_picture(
    prompt: Annotated[str, Field(description="What the picture shows.")],
    aspect: Annotated[Literal[xai.ASPECTS], Field(description="Shape of the picture.")] = "16:9",
    resolution: Annotated[Literal[xai.RESOLUTIONS], Field(description="Detail.")] = "2k",
    references: Annotated[list[str], Field(description="Up to 5 picture ids to work from.")] = [],
) -> str:
    """Paint a picture from a description with xAI's image model, paid from prepaid credit. aspect is 16:9 (the default), 9:16, 1:1, 4:3, 3:4, 3:2, 2:3, 21:9 or auto; resolution is 1k, 1.5k or 2k (the default); references are up to 5 picture ids to repaint or work from, such as a card laid out in GIMP."""
    try:
        return library.said(images.picture(prompt, aspect, resolution, references)) + "."
    except Exception as e:
        return f"No picture was made: {_sentence(e)}"


@mcp.tool()
def studio_assemble(
    edit: Annotated[dict | str, Field(
        description="The edit, as an object or JSON text: size, fps, name, video, "
                    "overlays, audio. studio_describe has the format and an example.")],
) -> str:
    """Cut clips, pictures, cards, captions, voice and music together into one mp4, or an m4a when there is no video. Starts a job and returns at once. video is a list played in order: {asset, seconds, from, transition: cut, dissolve or fade, fit: cover or contain, move for stills: none, push-in, pull-out, pan-left or pan-right}. overlays are timed pictures {asset, at, seconds, place} or {captions: a speech id}. audio is timed sound {asset, at, level 0 to 1, fade, duck}. Assets are ids or file paths."""
    if isinstance(edit, str):
        try:
            edit = json.loads(edit)
        except ValueError as e:
            return f"Not starting: the edit is not JSON ({e})."
    if not isinstance(edit, dict):
        return "Not starting: the edit must be an object."
    plan, problems = timeline.normalise(edit, library.resolve)
    if problems:
        return ("Not starting: the edit has problems.\n  "
                + "\n  ".join(problems[:15]))
    refused = memory.refusal("assembly")
    if refused:
        return f"Not starting: {refused}"
    job = jobs.new()
    out = os.path.join(RENDERS, f"{plan['name']}-{job}"
                       + (".m4a" if plan["audio_only"] else ".mp4"))
    os.makedirs(RENDERS, exist_ok=True)
    os.makedirs(jobs.WORK, exist_ok=True)
    plan_path = os.path.join(jobs.WORK, f"plan-{job}.json")
    with open(plan_path, "w") as fh:
        json.dump(plan, fh)
    jobs.start(job, "studio.assemble", ["--plan", plan_path, "--out", out],
               dict(name=plan["name"], out=out))
    what = ("sound" if plan["audio_only"]
            else f"{plan['width']}x{plan['height']} video")
    return (f"Started assembling '{plan['name']}' as job {job}: "
            f"{plan['seconds']:.1f} seconds of {what}, "
            f"{_wait(assemble.estimate(plan))}. It will be written to {out}. "
            f"Nothing announces when it finishes. studio_status says how it "
            f"is going whenever it is asked, with or without the job id.")


@mcp.tool()
def studio_status(
    job: Annotated[str, Field(description="The job id studio_assemble gave. "
                                          "Leave it out for the most recent.")] = "",
) -> str:
    """How an assembly is going, or how it finished. With no job id, the most recent one, and any others still running."""
    return jobs.status(job)


@mcp.tool()
def studio_list(
    kind: Annotated[Literal["", "video", "image", "audio"], Field(
        description="Only this kind; empty for everything.")] = "",
) -> str:
    """What is in the library, newest first: every id with what it is and where its file is. kind is video, image or audio, or empty (the default) for everything."""
    notes = library.listing(kind)
    if not notes:
        return "The library is empty." if not kind else f"There is no {kind} in the library."
    lines = [library.said(n) for n in notes[:50]]
    if len(notes) > 50:
        lines.append(f"...and {len(notes) - 50} older.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8768)
    ap.add_argument("--path", default="/mcp")
    a = ap.parse_args()
    print(f"studio MCP on http://{a.host}:{a.port}{a.path} -> {RENDERS}",
          flush=True)
    import anyio
    anyio.run(lambda: mcp.run_streamable_http_async(
        host=a.host, port=a.port, streamable_http_path=a.path))


if __name__ == "__main__":
    main()
```

**File: `studio/README.md`**
````markdown
# studio

General audio and video tools over MCP. Lectern makes lectures and highway
makes highway drives; the studio makes the pieces anything else is cut
from, and cuts them together.

```bash
studio/.venv/bin/python -m studio.mcp_server --port 8768   # streamable HTTP at /mcp
```

It runs as a plain process, not a LaunchAgent, until the stack is judged
stable. Log it with `>> ~/Library/Logs/studio-mcp.log 2>&1`.

## Tools

| Tool | Does |
|---|---|
| `studio_describe` | the voices, moods, card styles, and the edit format with an example |
| `studio_import` | brings in a video, picture or sound from a path or URL |
| `studio_speak` | text to speech, with word timings for captions |
| `studio_music` | a music bed from a mood, exactly as long as asked |
| `studio_card` | a text card drawn by GIMP |
| `studio_picture` | a picture from xAI (needs `XAI_API_KEY`; prepaid credit) |
| `studio_assemble` | cuts it all into an mp4 (or m4a), as a job |
| `studio_status` | how a job is going; no id means the newest |
| `studio_list` | what is in the library |

Every asset has an id saying where it came from: `voice-`, `music-`,
`card-`, `pic-`, and for imports `clip-`, `image-`, `sound-`. Files live in
`studio/media/` beside a JSON note each; finished edits go to `renders/`.

## The edit

```json
{
  "size": "1920x1080", "fps": 30, "name": "pockterm-spot",
  "video": [
    {"asset": "card-1a2b", "seconds": 3},
    {"asset": "clip-9c01", "from": 12, "seconds": 6, "transition": "dissolve"},
    {"asset": "pic-44d0", "seconds": 5, "move": "push-in", "transition": "fade"}
  ],
  "overlays": [
    {"asset": "card-7d3e", "at": 4, "seconds": 3, "place": "bottom"},
    {"captions": "voice-3f2a"}
  ],
  "audio": [
    {"asset": "voice-3f2a", "at": 0.5},
    {"asset": "music-77e1", "level": 0.15, "duck": true}
  ]
}
```

The video track plays in order, so nobody computes a timecode. The design
is in `docs/superpowers/specs/2026-09-26-studio-core-design.md`.

## Engines

| Work | Engine |
|---|---|
| speech | Kokoro, under `.ttsvenv` (`studio/speech_engine.py`, or `lectern.narrate` for einstein) |
| music | `highway3d/music.py` through `lectern.score` |
| cards and captions | GIMP 3.2, headless (`studio/gimp_draw.py`) |
| pictures | xAI `grok-imagine-image-2.0` |
| assembly | ffmpeg; this build has no drawtext, so text arrives as pictures |

Before starting speech, drawing or assembly, the studio checks the Mac has
the memory for it plus 4 GB, and says so if it does not.

## Tests

```bash
for t in library memory jobs timeline assemble speech music xai server; do
  studio/.venv/bin/python studio/test_$t.py | tail -1
done
studio/.venv/bin/python studio/test_engines.py   # real engines; only when the Mac is quiet
```
````

- [ ] **Step 4: Run it and see it pass**

Run: `studio/.venv/bin/python studio/test_server.py`
Expected: `9/9 passed`

- [ ] **Step 5: Commit**

```bash
git add studio/mcp_server.py studio/README.md studio/test_server.py
git commit -m "Serve the studio's nine tools over MCP on port 8768"
```

---

### Task 10: The real engines, end to end

**Files:**
- Create: `studio/test_engines.py`
- Modify: `studio/assemble.py` (`RATE`) and `studio/memory.py` (`NEEDS_GB`) from the measurements

**Interfaces:**
- Consumes: every module above.

- [ ] **Step 1: Check the Mac is quiet**

Run: `ps -axo rss=,args= | sort -rn | head -5; vm_stat | head -5`
Expected: no 27B, Blender or render in the top five; if there is one, wait.

- [ ] **Step 2: Write the engine test**

**File: `studio/test_engines.py`**
```python
"""The studio's real engines, end to end. Minutes, not seconds.

    studio/.venv/bin/python studio/test_engines.py

Speaks, composes, draws, and cuts real edits, then checks each result with
ffprobe and pulls frames into studio/.work/check/ to be looked at. Run it
only when nothing heavy is running: it refuses to start otherwise.
"""

import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import assemble, images, library, memory, music, speech, timeline  # noqa: E402

CHECK = os.path.join(HERE, ".work", "check")
os.makedirs(CHECK, exist_ok=True)
SRC = tempfile.mkdtemp(prefix="studio-src-")
TIMES = {}


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def frame(video, t, name):
    p = os.path.join(CHECK, name)
    ffmpeg("-ss", f"{t}", "-i", video, "-frames:v", "1", p)
    return p


def timed(name, fn, *a):
    began = time.time()
    out = fn(*a)
    TIMES[name] = round(time.time() - began, 1)
    return out


def test_speech_plain():
    note = timed("speech", speech.speak, "Three in the morning. The server is down.", "am_michael")
    assert note["kind"] == "audio" and 1.0 < note["seconds"] < 8.0, note
    assert [w["text"] for w in note["words"]][:4] == ["Three", "in", "the", "morning."], note["words"][:4]


def test_speech_einstein():
    note = speech.speak("Time is not universal.", "einstein")
    assert len(note["words"]) >= 4, note["words"]


def test_long_speech_keeps_time():
    text = " ".join(["The terminal keeps tmux intact, draws htop as it should, and "
                     "never scrambles the borders of a pane."] * 5)
    note = speech.speak(text, "bf_emma")
    starts = [w["start"] for w in note["words"]]
    assert starts == sorted(starts), "word times went backwards between pieces"
    assert note["words"][-1]["end"] > 0.8 * note["seconds"], (note["words"][-1], note["seconds"])


def test_music():
    note = music.compose("night", 5)
    assert abs(note["seconds"] - 5) < 0.1, note


def test_cards():
    for style in images.STYLES:
        note = timed(f"card {style}", images.card, "Don't panic — it's café time",
                     "a terminal that does not mangle tmux", style, 1280, 720)
        assert (note["width"], note["height"]) == (1280, 720), note
        os.replace(note["path"], os.path.join(CHECK, f"card-{style}.png"))


def edit_assets():
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=3",
           "-f", "lavfi", "-i", "sine=frequency=330:duration=3", "-shortest",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.join(SRC, "portrait clip.mp4"))
    ffmpeg("-f", "lavfi", "-i", "mandelbrot=size=1600x900", "-frames:v", "1",
           os.path.join(SRC, "still.png"))
    return dict(
        card=images.card("Pockterm", "free, no account", "dark"),
        lower=images.card("tmux, intact", "", "light", 1600, 200),
        voice=speech.speak("Three in the morning. The server is down, and you "
                           "are not at your desk.", "am_michael"),
        bed=music.compose("drive", 12),
        clip=os.path.join(SRC, "portrait clip.mp4"),
        still=os.path.join(SRC, "still.png"))


def test_full_edit():
    a = edit_assets()
    edit = {
        "size": "1920x1080", "name": "engine-test",
        "video": [{"asset": a["card"]["id"], "seconds": 2},
                  {"asset": a["still"], "seconds": 3, "move": "push-in", "transition": "dissolve"},
                  {"asset": a["clip"], "fit": "contain", "transition": "fade", "level": 0.3}],
        "overlays": [{"asset": a["lower"]["id"], "at": 3, "seconds": 2, "place": "bottom"},
                     {"captions": a["voice"]["id"]}],
        "audio": [{"asset": a["voice"]["id"], "at": 0.3},
                  {"asset": a["bed"]["id"], "level": 0.2, "duck": True}],
    }
    plan, problems = timeline.normalise(edit, library.resolve)
    assert problems == [], problems
    out = os.path.join(CHECK, "engine-test.mp4")
    d = timed("assembly", assemble.run, plan, out)
    facts = library.probe(out)
    assert facts["kind"] == "video" and facts["sound"], facts
    assert (facts["width"], facts["height"]) == (1920, 1080), facts
    assert abs(facts["seconds"] - plan["seconds"]) < 0.15, (facts["seconds"], plan["seconds"])
    TIMES["assembly per second"] = round(d["took"] / plan["seconds"], 2)
    for t in (1.0, 1.75, 3.5, 5.5):
        print("  frame:", frame(out, t, f"frame-{t}.png"))


def test_audio_only_edit():
    voice = speech.speak("Audio on its own.", "af_heart")
    bed = music.compose("open", 4)
    plan, problems = timeline.normalise(
        {"name": "audio-test", "audio": [{"asset": voice["id"], "at": 0.5},
                                         {"asset": bed["id"], "level": 0.2, "duck": True}]},
        library.get)
    assert problems == [], problems
    out = os.path.join(CHECK, "audio-test.m4a")
    assemble.run(plan, out)
    assert library.probe(out)["kind"] == "audio"


def main():
    refused = memory.refusal("assembly")
    if refused:
        print("not running:", refused)
        sys.exit(2)
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print("times:", TIMES)
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it, then look at every frame and card it wrote**

Run: `studio/.venv/bin/python studio/test_engines.py`
Expected: `7/7 passed`, a `times:` line, and frame paths. Open each PNG in `studio/.work/check/` with the Read tool:
- `card-*.png`: text centred, legible, accents and the apostrophe drawn, no text past the edges.
- `frame-1.0.png`: the dark card with a caption strip at the bottom.
- `frame-1.75.png`: mid-dissolve from the card into the Mandelbrot still.
- `frame-3.5.png`: the still, pushed in a little, with the light lower third.
- `frame-5.5.png`: the portrait test pattern pillarboxed between black bars, not stretched.
Listen to `engine-test.mp4` by checking the audio levels instead:
`ffmpeg -i studio/.work/check/engine-test.mp4 -af volumedetect -f null - 2>&1 | grep -e mean_volume -e max_volume`
Expected: max_volume at or below -0.1 dB (the limiter), mean_volume between -35 and -12 dB.

- [ ] **Step 4: Calibrate from the measurements**

Set `RATE` in `studio/assemble.py` to the measured `assembly per second` (rounded up to one decimal), and update its comment with the date and the measurement. If `ps` during the run showed any engine above its `NEEDS_GB` figure, raise that figure in `studio/memory.py` and say so in the comment.

- [ ] **Step 5: Rerun the fast tests**

Run: `for t in library memory jobs timeline assemble speech music xai server; do studio/.venv/bin/python studio/test_$t.py | tail -1; done`
Expected: every line `N/N passed`.

- [ ] **Step 6: Commit**

```bash
git add studio/test_engines.py studio/assemble.py studio/memory.py
git commit -m "Test the studio's engines end to end and time assembly from real runs"
```

---

### Task 11: Run the server and check it over HTTP

**Files:**
- none created; the server runs as a plain process.

- [ ] **Step 1: Start it**

```bash
cd "$(git rev-parse --show-toplevel)" && PYTHONUNBUFFERED=1 nohup studio/.venv/bin/python -m studio.mcp_server --port 8768 >> ~/Library/Logs/studio-mcp.log 2>&1 &
sleep 4; lsof -nP -iTCP:8768 -sTCP:LISTEN
```
Expected: one Python process listening on 127.0.0.1:8768.

- [ ] **Step 2: Call it over streamable HTTP as a client would**

```bash
lectern/.mcpvenv/bin/python - <<'EOF'
import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with streamable_http_client("http://127.0.0.1:8768/mcp") as st:
        async with ClientSession(st[0], st[1]) as s:
            await s.initialize()
            print(sorted(t.name for t in (await s.list_tools()).tools))
            for name, args in [("studio_status", {}), ("studio_list", {"kind": "audio"}),
                               ("studio_music", {"mood": "night", "seconds": 3}),
                               ("studio_picture", {"prompt": "a fox"}),
                               ("studio_assemble", {"edit": {"video": ["clip-0000"]}})]:
                r = await s.call_tool(name, args)
                print(name, "->", r.content[0].text[:200])
anyio.run(main)
EOF
```
Expected: the nine tool names; status and list answer; music returns a `music-` id; picture says no xAI key is set (or makes a picture if the key exists); assemble says the edit has problems.

- [ ] **Step 3: Assemble one real edit over HTTP and follow it with studio_status**

Use the music id from Step 2 in `{"name": "http-check", "audio": ["<music id>"]}`, call `studio_assemble`, then call `studio_status` with no job until it reports `finished`. Expected: an `.m4a` in `renders/`.

- [ ] **Step 4: Commit anything the run changed**

If nothing changed, skip. Otherwise commit with a one-sentence message.
