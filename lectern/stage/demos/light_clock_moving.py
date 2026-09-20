"""The same clock, moving: the pulse traces a zigzag, so a tick takes longer.

The whole of time dilation is the difference between this picture and
`light_clock_rest`, so the two are deliberately the same object with the same
gap and the same plates. Only the path changes -- and it changes because the
pulse has to chase a mirror that has moved on.

The diagonal is drawn as it happens rather than stated afterwards: the point
lands when you watch the path get longer while the speed does not.
"""

from __future__ import annotations

import math

from mathutils import Vector

from . import PALETTE, ball, cube, glow, key, label, matte, rod

NAME = "light_clock_moving"
SUMMARY = ("The same light clock, moving past you: the pulse travels a "
           "longer, diagonal path, so its tick takes longer than yours.")

GAP = 0.44
PLATE = 0.28
TRAVEL = 0.86          # how far it crosses the stage over the shot
TRAIL = 26             # segments of drawn path


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    steel = matte("demo.steel", PALETTE["steel"], 0.35)
    frame_mat = matte("demo.slate", PALETTE["slate"], 0.7)
    pulse_mat = glow("demo.pulse", (0.85, 0.94, 1.0), 26.0)
    path_mat = glow("demo.path", (0.40, 0.70, 1.0), 3.4)

    made = []
    start = origin + Vector((-TRAVEL / 2, 0, 0))

    plates = []
    for tag, dz in (("bottom", -GAP / 2), ("top", GAP / 2)):
        m = cube(f"mclock.{tag}", start + Vector((0, 0, dz)),
                 (PLATE, PLATE, 0.022), steel)
        plates.append(m)
        made.append(m)
    posts = [rod(f"mclock.post.{s}", 0.005, GAP,
                 start + Vector((s * PLATE * 0.46, 0, 0)), frame_mat)
             for s in (-1, 1)]
    made += posts

    pulse = ball("mclock.pulse", 0.030, start, pulse_mat)
    made.append(pulse)

    ticks = 2.0
    lo, hi = -GAP / 2 + 0.024, GAP / 2 - 0.024

    def at(u: float):
        """Where the clock and its pulse are, at fraction u through the shot."""
        x = start.x + TRAVEL * u
        saw = (u * ticks) % 1.0
        z = origin.z + lo + (hi - lo) * (2 * saw if saw < 0.5 else 2 * (1 - saw))
        return x, z

    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        x, z = at(u)
        for m, dz in zip(plates, (-GAP / 2, GAP / 2)):
            key(m, f, location=(x, origin.y, origin.z + dz))
        for p, s in zip(posts, (-1, 1)):
            key(p, f, location=(x + s * PLATE * 0.46, origin.y, origin.z))
        key(pulse, f, location=(x, origin.y, z))

    # The path it actually took, laid down behind it as a dotted diagonal.
    # Drawn segment by segment, each appearing as the pulse reaches it, so the
    # zigzag accumulates rather than being there from the first frame.
    for i in range(TRAIL):
        u = (i + 0.5) / TRAIL
        x, z = at(u)
        dot = ball(f"mclock.trail.{i:02d}", 0.011,
                   (x, origin.y + 0.012, z), path_mat, segments=12)
        made.append(dot)
        appear = max(1, int(u * n_frames))
        key(dot, 1, scale=(0.001, 0.001, 0.001))
        key(dot, max(1, appear - 1), scale=(0.001, 0.001, 0.001))
        key(dot, min(n_frames, appear + 1), scale=(1.0, 1.0, 1.0))

    return dict(objects=made, focus=origin, base=GAP / 2 + 0.014,
                width=(TRAVEL + PLATE + 0.26) if "TRAVEL" in globals() else PLATE + 0.60,
                caption="the pulse has further to go, at the same speed")
