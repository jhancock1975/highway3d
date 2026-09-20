"""Approaching light comes in bluer, receding light redder, and by how much.

Two curves on one pair of axes, because the asymmetry is the interesting part:
the shift toward you grows without limit while the shift away saturates
toward zero. Drawn in the colours they describe, which is the one place in
this lecture where the palette is carrying information rather than taste.
"""

from __future__ import annotations

import math

from mathutils import Vector

from . import PALETTE, cube, glow, label, plot_axes, plot_curve

NAME = "doppler"
SUMMARY = ("The relativistic Doppler shift: light from an approaching source "
           "is blued without limit, light from a receding one reddened toward "
           "nothing.")

W, H = 0.66, 0.46
YMAX = 4.0


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    base = origin + Vector((-W / 2, 0, -H / 2))
    blue = glow("demo.blue", (0.42, 0.62, 1.0), 5.0)
    red = glow("demo.red", (1.0, 0.36, 0.30), 4.4)
    unity = glow("demo.unity", (0.75, 0.78, 0.84), 2.0)

    made = plot_axes(base, W, H, "speed", "frequency",
                     ticks=((0.0, "0"), (0.5, "0.5c"), (1.0, "c")))
    made.append(cube("dop.unity", base + Vector((W / 2, 0, H / YMAX)),
                     (W, 0.005, 0.005), unity))
    made.append(label("unshifted",
                      base + Vector((W * 0.22, -0.01, H / YMAX + 0.014)),
                      0.024, (0.78, 0.80, 0.86, 1.0)))

    def approach(u):
        b = u * 0.97
        return math.sqrt((1 + b) / max(1e-4, 1 - b))

    def recede(u):
        b = u * 0.97
        return math.sqrt(max(1e-4, (1 - b) / (1 + b)))

    made += plot_curve("dop.blue", base, W, H, approach, n_frames, blue,
                       points=38, ymax=YMAX)
    made += plot_curve("dop.red", base, W, H, recede, n_frames, red,
                       points=38, ymax=YMAX)
    made.append(label("coming toward you",
                      base + Vector((W * 0.58, -0.01, H * 0.80)), 0.026,
                      (0.60, 0.76, 1.0, 1.0)))
    made.append(label("going away",
                      base + Vector((W * 0.62, -0.01, 0.022)), 0.026,
                      (1.0, 0.56, 0.50, 1.0)))
    return dict(objects=made, focus=origin, base=H / 2 + 0.06,
                width=W + 0.42,
                caption="bluer coming, redder going")
