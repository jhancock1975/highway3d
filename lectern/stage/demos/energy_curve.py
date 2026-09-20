"""The energy needed to go faster, which runs away before c does.

Deliberately the same axes as `gamma_curve` so the two read as the same fact
seen twice: the barrier is not that c is forbidden, it is that arriving there
costs everything there is. The rest energy sits on the axis as a marked
floor, because mc-squared being the value at zero speed is most of the point.
"""

from __future__ import annotations

import math

from mathutils import Vector

from . import PALETTE, cube, glow, label, plot_axes, plot_curve

NAME = "energy_curve"
SUMMARY = ("Total energy against speed: finite at rest, and rising without "
           "bound as the speed approaches c.")

W, H = 0.66, 0.46
YMAX = 4.0


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    base = origin + Vector((-W / 2, 0, -H / 2))
    curve_mat = glow("demo.energy", (1.0, 0.74, 0.40), 5.0)
    floor_mat = glow("demo.rest", (0.60, 0.90, 0.70), 2.6)
    wall_mat = glow("demo.wall", (1.0, 0.46, 0.38), 3.0)

    made = plot_axes(base, W, H, "speed", "energy",
                     ticks=((0.0, "0"), (0.5, "0.5c"), (1.0, "c")))
    made.append(cube("energy.rest", base + Vector((W / 2, 0, H / YMAX)),
                     (W, 0.005, 0.005), floor_mat))
    made.append(label("mc^2 at rest",
                      base + Vector((W * 0.30, -0.01, H / YMAX + 0.016)),
                      0.026, (0.68, 1.0, 0.80, 1.0)))
    made.append(cube("energy.asymptote", base + Vector((W, 0, H / 2)),
                     (0.006, 0.006, H), wall_mat))
    made += plot_curve("energy", base, W, H,
                       lambda u: 1.0 / math.sqrt(max(1e-4, 1.0 - (u * 0.985) ** 2)),
                       n_frames, curve_mat, points=40, ymax=YMAX)
    return dict(objects=made, focus=origin, base=H / 2 + 0.06,
                width=W + 0.42,
                caption="not forbidden -- just infinitely expensive")
