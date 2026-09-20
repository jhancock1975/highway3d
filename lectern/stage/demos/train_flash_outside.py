"""The same flash, seen from the platform: the back wall runs into the light.

Identical carriage, identical lamp, identical event. The difference is that
the carriage is moving, so while the light crosses the gap the rear wall comes
forward to meet it and the front wall runs away. The light hits the back
first, and neither observer is mistaken.

This is the demonstration that has to be watched rather than described, which
is why the two fronts arrive at visibly different moments and the carriage
keeps moving underneath them.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, ball, cube, glow, key, label, matte

NAME = "train_flash_outside"
SUMMARY = ("The same flash seen from the platform: the carriage is moving, so "
           "the light reaches the rear wall before the front one.")

CAR_W = 0.66
CAR_H = 0.34
TRAVEL = 0.34          # how far the carriage moves across the shot
SPREAD = 0.70          # fraction of the shot the light takes to cross


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    shell = matte("demo.car", (0.30, 0.34, 0.42, 1.0), 0.55)
    trim = matte("demo.brass", PALETTE["brass"], 0.42)
    rail_mat = matte("demo.slate", PALETTE["slate"], 0.8)
    flash_mat = glow("demo.flash", (1.0, 0.94, 0.78), 22.0)
    front_mat = glow("demo.front", (0.70, 0.86, 1.0), 9.0)

    made = []
    start = origin + Vector((-TRAVEL / 2, 0, 0))

    made.append(cube("plat.rail", origin + Vector((0, 0, -CAR_H / 2 - 0.028)),
                     (CAR_W + TRAVEL + 0.16, 0.34, 0.014), rail_mat))

    floor = cube("ocar.floor", start + Vector((0, 0, -CAR_H / 2)),
                 (CAR_W, 0.30, 0.016), shell)
    roof = cube("ocar.roof", start + Vector((0, 0, CAR_H / 2)),
                (CAR_W, 0.30, 0.016), shell)
    walls = [cube(f"ocar.wall.{s}", start + Vector((s * CAR_W / 2, 0, 0)),
                  (0.018, 0.30, CAR_H), trim) for s in (-1, 1)]
    body = [floor, roof] + walls
    made += body

    sign = label("CAR 9", start + Vector((-CAR_W / 2 + 0.11, -0.152,
                                          CAR_H / 2 - 0.07)),
                 0.040, (0.86, 0.78, 0.52, 1.0), align="LEFT")
    made.append(sign)

    lamp = ball("ocar.lamp", 0.026, start, flash_mat)
    made.append(lamp)

    fronts = [ball(f"ocar.front.{s}", 0.019, start, front_mat, segments=16)
              for s in (-1, 1)]
    made += fronts

    def car_x(u):
        return start.x + TRAVEL * u

    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        x = car_x(u)
        for obj, dx, dz in ((floor, 0, -CAR_H / 2), (roof, 0, CAR_H / 2),
                            (walls[0], -CAR_W / 2, 0), (walls[1], CAR_W / 2, 0)):
            key(obj, f, location=(x + dx, origin.y, origin.z + dz))
        key(sign, f, location=(x - CAR_W / 2 + 0.11, origin.y - 0.152,
                               origin.z + CAR_H / 2 - 0.07))
        key(lamp, f, location=(start.x, origin.y, origin.z))
        key(lamp, f, scale=(1, 1, 1) if u < 0.10 else (0.55, 0.55, 0.55))

        # The light goes at the same speed in both directions from where the
        # flash happened -- which is a fixed point on the platform, not a
        # point on the train. That is the entire asymmetry.
        reach = min(1.0, u / SPREAD) * (CAR_W / 2 - 0.02)
        for front, s in zip(fronts, (-1, 1)):
            fx = start.x + s * reach
            wall_x = x + s * (CAR_W / 2 - 0.02)
            caught = (fx <= wall_x) if s < 0 else (fx >= wall_x)
            key(front, f, location=(fx, origin.y, origin.z))
            key(front, f, scale=(0.001, 0.001, 0.001) if caught else (1, 1, 1))

    return dict(objects=made, focus=origin, base=CAR_H / 2 + 0.05,
                width=CAR_W + TRAVEL + 0.24,
                caption="from the platform: the rear wall gets there first")
