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
