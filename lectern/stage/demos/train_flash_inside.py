"""A flash at the middle of a carriage, seen from inside it.

From in here the two walls are equally far away and nothing is moving, so the
light arrives at both ends together. That is the easy half, and it has to be
shown first and shown plainly, because the whole force of
`train_flash_outside` is that the identical event looks different from the
platform -- and nobody is doing anything wrong.

The carriage carries its number on the side. A blank vehicle reads as a
placeholder.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, ball, cube, glow, key, label, matte

NAME = "train_flash_inside"
SUMMARY = ("A lamp flashes at the centre of a carriage, seen by a passenger: "
           "the light reaches both ends at the same moment.")

CAR_W = 0.78
CAR_H = 0.34
ARRIVE = 0.62          # fraction of the shot at which the light lands


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    shell = matte("demo.car", (0.30, 0.34, 0.42, 1.0), 0.55)
    trim = matte("demo.brass", PALETTE["brass"], 0.42)
    flash_mat = glow("demo.flash", (1.0, 0.94, 0.78), 22.0)
    front_mat = glow("demo.front", (0.70, 0.86, 1.0), 9.0)

    made = []
    made.append(cube("car.floor", origin + Vector((0, 0, -CAR_H / 2)),
                     (CAR_W, 0.30, 0.016), shell))
    made.append(cube("car.roof", origin + Vector((0, 0, CAR_H / 2)),
                     (CAR_W, 0.30, 0.016), shell))
    walls = []
    for side in (-1, 1):
        w = cube(f"car.wall.{side}", origin + Vector((side * CAR_W / 2, 0, 0)),
                 (0.018, 0.30, CAR_H), trim)
        walls.append(w)
        made.append(w)
    made.append(label("CAR 9", origin + Vector((-CAR_W / 2 + 0.11, -0.152,
                                                CAR_H / 2 - 0.07)),
                      0.040, (0.86, 0.78, 0.52, 1.0), align="LEFT"))

    lamp = ball("car.lamp", 0.026, origin, flash_mat)
    made.append(lamp)
    made.append(label("lamp", origin + Vector((0, -0.02, -0.062)), 0.028))

    fronts = [ball(f"car.front.{s}", 0.019, origin, front_mat, segments=16)
              for s in (-1, 1)]
    made += fronts

    # Both fronts leave together and arrive together. Nothing else happens,
    # which is the point.
    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        reach = min(1.0, u / ARRIVE)
        for front, s in zip(fronts, (-1, 1)):
            key(front, f,
                location=(origin.x + s * reach * (CAR_W / 2 - 0.02),
                          origin.y, origin.z))
            key(front, f, scale=(1, 1, 1) if u < ARRIVE + 0.06
                else (0.001, 0.001, 0.001))
        key(lamp, f, scale=(1, 1, 1) if u < 0.10
            else (0.55, 0.55, 0.55))

    return dict(objects=made, focus=origin, base=CAR_H / 2 + 0.02,
                width=CAR_W + 0.22,
                caption="from inside: both ends at once")
