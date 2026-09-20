"""The light cone: what an event can reach, and what can reach it.

Two cones meeting at a point, drawn as rings rather than as solid surfaces, so
you can see through the future into the past and read the elsewhere between
them. A solid cone hides exactly the region that has to be understood.

The three regions are named in the scene. An unlabelled double cone is a
shape; a labelled one is an argument about causality.
"""

from __future__ import annotations

import math

from mathutils import Vector

from . import PALETTE, ball, cube, glow, key, label, matte

NAME = "light_cone"
SUMMARY = ("The light cone of an event: future above, past below, and the "
           "elsewhere that no signal can reach.")

H = 0.30               # half-height
R = 0.30               # radius at the rim
RINGS = 7
SEGS = 22


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    axis_mat = matte("demo.slate", PALETTE["slate"], 0.78)
    future_mat = glow("demo.future", (0.52, 0.80, 1.00), 3.6)
    past_mat = glow("demo.past", (1.00, 0.60, 0.40), 3.2)
    here_mat = glow("demo.here", (1.0, 0.96, 0.82), 20.0)

    made = []
    made.append(cube("cone.axis", origin, (0.006, 0.006, H * 2 + 0.10),
                     axis_mat))
    made.append(ball("cone.event", 0.022, origin, here_mat, segments=18))
    made.append(label("here, now", origin + Vector((0.055, -0.02, 0.0)), 0.028))
    made.append(label("future", origin + Vector((0, -0.02, H + 0.045)), 0.032,
                      (0.66, 0.86, 1.0, 1.0)))
    made.append(label("past", origin + Vector((0, -0.02, -H - 0.070)), 0.032,
                      (1.0, 0.70, 0.52, 1.0)))
    made.append(label("elsewhere", origin + Vector((R + 0.10, -0.02, 0.0)),
                      0.030, (0.76, 0.76, 0.80, 1.0)))

    dots = []
    for half, mat, sign in (("fut", future_mat, 1), ("past", past_mat, -1)):
        for ring in range(1, RINGS + 1):
            t = ring / RINGS
            z = origin.z + sign * H * t
            r = R * t
            for k in range(SEGS):
                a = 2 * math.pi * k / SEGS
                d = ball(f"cone.{half}.{ring}.{k}", 0.0075,
                         (origin.x + r * math.cos(a),
                          origin.y + r * math.sin(a) * 0.32, z),
                         mat, segments=8)
                dots.append((d, t))
                made.append(d)

    # The cones open outward from the event rather than being there already:
    # the growth is what says "at the speed of light", and a static pair of
    # cones says only "two cones".
    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        for d, t in dots:
            on = t <= max(0.02, u * 1.12)
            key(d, f, scale=(1, 1, 1) if on else (0.001, 0.001, 0.001))

    return dict(objects=made, focus=origin, base=H + 0.09,
                width=R * 2 + 0.52,
                caption="inside the cone is reachable; outside it is not")
