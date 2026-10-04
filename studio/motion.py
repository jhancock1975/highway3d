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
