"""Gamma against speed: flat for everything you have ever seen, then a wall.

The shape is the argument. Nearly all the way across the graph gamma is
indistinguishable from one, which is why nobody noticed any of this for three
hundred years, and then it goes vertical. Both halves have to be visible at
once, so the curve is drawn left to right and the asymptote is standing there
before it arrives.
"""

from __future__ import annotations

import math

from mathutils import Vector

from . import PALETTE, glow, matte, plot_axes, plot_curve, cube, label

NAME = "gamma_curve"
SUMMARY = ("The Lorentz factor against speed: flat and unremarkable until "
           "about 0.8c, then rising without limit.")

W, H = 0.66, 0.46
YMAX = 4.0


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    base = origin + Vector((-W / 2, 0, -H / 2))
    curve_mat = glow("demo.gamma", (0.55, 0.84, 1.0), 5.0)
    wall_mat = glow("demo.wall", (1.0, 0.46, 0.38), 3.0)

    made = plot_axes(base, W, H, "speed", "gamma",
                     ticks=((0.0, "0"), (0.5, "0.5c"), (1.0, "c")))
    made.append(cube("gamma.asymptote", base + Vector((W, 0, H / 2)),
                     (0.006, 0.006, H), wall_mat))
    made.append(label("nothing gets here",
                      base + Vector((W - 0.02, -0.01, H + 0.03)), 0.026,
                      (1.0, 0.62, 0.55, 1.0)))
    made += plot_curve("gamma", base, W, H,
                       lambda u: 1.0 / math.sqrt(max(1e-4, 1.0 - (u * 0.985) ** 2)),
                       n_frames, curve_mat, points=40, ymax=YMAX)
    made.append(label("1", base + Vector((-0.032, -0.01, H / YMAX - 0.012)),
                      0.024, (0.66, 0.70, 0.78, 1.0)))
    return dict(objects=made, focus=origin, base=H / 2 + 0.06,
                width=W + 0.42,
                caption="flat for everything you know, then a wall")
