"""Assert the presenter's hands never enter his body.

    blender -b -P lectern/test_no_pierce.py -- --frames 480

Runs the real animation over a whole shot's worth of frames and measures,
on every sampled frame, how far each hand and forearm sits inside the
torso mesh. Exits non-zero on any penetration.

This exists because the failure is silent. `present` -- the gesture every
shot opens on -- put the hand 37 mm and the forearm 61 mm inside the
cardigan, and `open` put them 75 mm and 99 mm in. Every frame rendered,
every shot encoded, every duration reconciled, and the only thing that
ever reported it was somebody watching the film.

The cause was a sign: positive Y rotation swings the left arm, which sits
at +x, toward -x -- straight into the torso. Every "outward" rotation in
the gesture library had it backwards.
"""

from __future__ import annotations

import argparse
import os
import sys

import bpy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lectern import shot as S  # noqa: E402
from lectern.presenter import character  # noqa: E402


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=480)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--step", type=int, default=4)
    ap.add_argument("--tolerance", type=float, default=0.002)
    a = ap.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    parts = character.build()

    # words at a plausible rate, so gestures fire the way they do in a shot
    words = [dict(text=f"word{i}", start=i * 0.42, end=i * 0.42 + 0.36)
             for i in range(int(a.frames / a.fps / 0.42) + 1)]
    S.animate_body(parts, a.frames, a.fps, words=words, focus=None)
    S.ease_interpolation()

    torso = parts["torso"]
    worst, worst_frame, worst_part = 0.0, 0, ""
    scene = bpy.context.scene
    for f in range(1, a.frames + 1, a.step):
        scene.frame_set(f)
        for side, arm in parts["arms"].items():
            for key in ("hand", "fore"):
                d = S.pierce_depth(arm[key], torso)
                if d > worst:
                    worst, worst_frame, worst_part = d, f, f"{key}.{side}"

    ok = worst <= a.tolerance
    print(f"PIERCE {{\"worst_mm\": {worst * 1000:.1f}, \"frame\": {worst_frame}, "
          f"\"part\": \"{worst_part}\", \"frames\": {a.frames}, "
          f"\"ok\": {str(ok).lower()}}}")
    if not ok:
        print(f"FAIL {worst_part} is {worst * 1000:.1f} mm inside the torso "
              f"on frame {worst_frame}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
