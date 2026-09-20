"""Two worldlines between the same two events, and only one of them turns.

The asymmetry is the whole resolution of the paradox, and it is geometric: the
stay-at-home draws a straight line up the time axis, the traveller draws a bent
one. Bending costs proper time. Drawing both on the same axes, from the same
start to the same end, is what makes "but isn't it symmetric?" answer itself --
one of these paths has a corner in it and the other does not.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, ball, cube, glow, key, label, matte

NAME = "twin_paths"
SUMMARY = ("Two worldlines between the same departure and the same reunion: "
           "one straight, one bent. Only the traveller turns around.")

W = 0.54               # axis width
H = 0.52               # axis height (time)
DOTS = 22


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    axis_mat = matte("demo.slate", PALETTE["slate"], 0.75)
    stay_mat = glow("demo.stay", (0.55, 0.80, 1.00), 5.0)
    trip_mat = glow("demo.trip", (1.00, 0.62, 0.34), 5.5)
    event_mat = glow("demo.event", (1.0, 0.95, 0.80), 16.0)

    made = []
    base = origin + Vector((0, 0, -H / 2))

    made.append(cube("twin.axis.t", origin, (0.008, 0.008, H), axis_mat))
    made.append(cube("twin.axis.x", base, (W, 0.008, 0.008), axis_mat))
    made.append(label("time", origin + Vector((-0.075, -0.01, H / 2 - 0.02)),
                      0.032, (0.70, 0.74, 0.82, 1.0)))
    made.append(label("space", base + Vector((W / 2 - 0.05, -0.01, -0.052)),
                      0.032, (0.70, 0.74, 0.82, 1.0)))

    depart = base
    reunite = origin + Vector((0, 0, H / 2))
    turn = Vector((origin.x + W * 0.40, origin.y, origin.z))

    for name, at in (("depart", depart), ("reunite", reunite)):
        made.append(ball(f"twin.{name}", 0.020, at, event_mat, segments=18))
    made.append(label("depart", depart + Vector((-0.12, -0.01, -0.03)), 0.028))
    made.append(label("reunite", reunite + Vector((-0.12, -0.01, 0.02)), 0.028))

    def on_stay(u):
        return depart.lerp(reunite, u)

    def on_trip(u):
        return depart.lerp(turn, u * 2) if u < 0.5 \
            else turn.lerp(reunite, (u - 0.5) * 2)

    # Both worldlines draw themselves at once, so the eye follows two clocks
    # running rather than reading a finished diagram.
    for label_, fn, mat in (("stay", on_stay, stay_mat),
                            ("trip", on_trip, trip_mat)):
        for i in range(DOTS):
            u = (i + 0.5) / DOTS
            p = fn(u)
            d = ball(f"twin.{label_}.{i:02d}", 0.0115,
                     (p.x, p.y - 0.012, p.z), mat, segments=12)
            made.append(d)
            appear = max(1, int(u * n_frames * 0.92))
            key(d, 1, scale=(0.001, 0.001, 0.001))
            key(d, max(1, appear - 1), scale=(0.001, 0.001, 0.001))
            key(d, min(n_frames, appear + 2), scale=(1.0, 1.0, 1.0))

    made.append(label("stays", on_stay(0.55) + Vector((-0.10, -0.02, 0)), 0.030,
                      (0.62, 0.84, 1.0, 1.0)))
    made.append(label("travels", turn + Vector((0.10, -0.02, 0.0)), 0.030,
                      (1.0, 0.70, 0.45, 1.0)))

    return dict(objects=made, focus=origin, base=H / 2 + 0.06,
                width=W + 0.40,
                caption="only one of them turns around")
