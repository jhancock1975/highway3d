"""Notation that writes itself onto the chalkboard.

Runs under `lectern/.manimvenv`, with TinyTeX on PATH. Produces a transparent
PNG sequence for one `note` stage, which `shot.py` maps onto the board as an
image-sequence texture -- so the notation lives in the room's lighting rather
than being pasted over the frame afterwards.

Manim rather than a static image because the brief asked for animated
notation and the old lecture cross-faded flat PNGs. An equation that draws
itself is the difference between reading a slide and watching someone work.

Lines carry inline maths in `$...$` and prose outside it, which is what the
lecture already had, so `Tex` is used rather than `MathTex`: the latter would
treat "holds in every inertial frame" as an expression and fail on it.

Timing comes from the speech, like everything else here: the writing is
stretched to the duration the sentence actually took.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIM = os.path.join(HERE, "lectern", ".manimvenv", "bin", "python")
TEXBIN = os.path.expanduser("~/Library/TinyTeX/bin/universal-darwin")

SCENE_TEMPLATE = '''from manim import *

class Board(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        heading = {heading!r}
        lines = {lines!r}
        hold = {hold!r}
        write = {write!r}

        items = []
        if heading:
            h = Tex(heading, color="#DCE6F2").scale(1.06)
            items.append(h)
        for text in lines:
            items.append(Tex(text, color="#EAF0FA").scale(0.94))

        group = VGroup(*items).arrange(DOWN, buff=0.42, aligned_edge=LEFT)
        group.move_to(ORIGIN)
        if heading:
            items[0].set_color("#8FC4F5")
            # a rule under the heading, the way a board actually gets used
            rule = Line(items[0].get_corner(DL), items[0].get_corner(DR),
                        color="#5C87B8", stroke_width=3)
            rule.shift(DOWN * 0.16)

        if heading:
            self.play(FadeIn(items[0], shift=DOWN * 0.12), run_time=0.45)
            self.play(Create(rule), run_time=0.30)
            body = items[1:]
        else:
            body = items

        for item in body:
            self.play(Write(item), run_time=write)
        self.wait(hold)
'''


def digest(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode())
    return h.hexdigest()[:16]


def render(spec: dict, duration: float, fps: int, work: str,
           width: int = 1280, height: int = 720) -> str:
    """Render one note. Returns a directory of numbered transparent PNGs."""
    heading = (spec or {}).get("heading", "") or ""
    lines = list((spec or {}).get("lines", []) or [])
    key = digest(heading, lines, round(duration, 2), fps, width, height)
    out_dir = os.path.join(work, f"note-{key}")
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        return out_dir

    # Split the sentence's real length between writing and holding: the board
    # should finish a little before he does, not at the same instant.
    n = max(1, len(lines))
    lead = 0.75 if heading else 0.0
    usable = max(0.8, duration * 0.78 - lead)
    write = max(0.30, min(1.6, usable / n))
    hold = max(0.2, duration - lead - write * n)

    scene_dir = os.path.join(work, f"scene-{key}")
    os.makedirs(scene_dir, exist_ok=True)
    scene_py = os.path.join(scene_dir, "board.py")
    with open(scene_py, "w") as fh:
        fh.write(SCENE_TEMPLATE.format(heading=heading, lines=lines,
                                       hold=hold, write=write))

    env = dict(os.environ, PATH=os.environ.get("PATH", "") + ":" + TEXBIN)
    r = subprocess.run(
        [MANIM, "-m", "manim", "render", "--format=png", "--transparent",
         "--fps", str(fps), "-r", f"{width},{height}",
         "--media_dir", scene_dir, scene_py, "Board"],
        capture_output=True, text=True, env=env, cwd=scene_dir)
    if r.returncode != 0:
        raise RuntimeError("notation failed: "
                           + (r.stderr or r.stdout).strip()[-500:])

    frames = None
    for root, _dirs, files in os.walk(scene_dir):
        if any(f.endswith(".png") for f in files):
            frames = root
            break
    if frames is None:
        raise RuntimeError("notation produced no frames")

    os.makedirs(out_dir, exist_ok=True)
    for i, name in enumerate(sorted(f for f in os.listdir(frames)
                                    if f.endswith(".png"))):
        shutil.move(os.path.join(frames, name),
                    os.path.join(out_dir, f"n{i:04d}.png"))
    shutil.rmtree(scene_dir, ignore_errors=True)
    return out_dir


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--heading", default="")
    ap.add_argument("--lines", required=True,
                    help="JSON list, or lines separated by ' | '")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--work", required=True)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    a = ap.parse_args()

    try:
        lines = json.loads(a.lines)
    except ValueError:
        lines = [x.strip() for x in a.lines.split("|") if x.strip()]

    out = render(dict(heading=a.heading, lines=lines), a.duration, a.fps,
                 a.work, a.width, a.height)
    print(json.dumps(dict(frames=out, count=len(os.listdir(out)))))


if __name__ == "__main__":
    main()
