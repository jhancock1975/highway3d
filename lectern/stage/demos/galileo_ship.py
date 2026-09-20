"""Galileo's ship: below deck, nothing tells you whether you are moving.

The oldest idea in the lecture and the one that has to land first, because
every strange thing later is this principle refusing to be given up. So it is
staged as a cabin with the things Galileo actually listed -- a bowl with a
fish, a bottle dripping into a jar -- behaving in exactly the ordinary way
while the ship sails.

The drips fall straight down. That is the whole demonstration, and it only
works if you can see the hull moving at the same time.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, ball, cube, key, label, matte

NAME = "galileo_ship"
SUMMARY = ("Below deck on a smoothly sailing ship: drips fall straight down "
           "and nothing inside the cabin reveals the motion.")

HULL_W = 0.80
HULL_H = 0.34
TRAVEL = 0.30
DRIPS = 5


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    hull_mat = matte("demo.hull", (0.26, 0.19, 0.14, 1.0), 0.72)
    sea_mat = matte("demo.sea", (0.10, 0.22, 0.30, 1.0), 0.35)
    glass = matte("demo.glass", (0.62, 0.76, 0.82, 1.0), 0.18)
    water = matte("demo.water", (0.30, 0.56, 0.68, 1.0), 0.25)
    fish_mat = matte("demo.fish", (0.82, 0.48, 0.24, 1.0), 0.5)

    made = []
    start = origin + Vector((-TRAVEL / 2, 0, 0))
    made.append(cube("ship.sea", origin + Vector((0, 0, -HULL_H / 2 - 0.03)),
                     (HULL_W + TRAVEL + 0.30, 0.40, 0.020), sea_mat))

    hull = [cube("ship.floor", start + Vector((0, 0, -HULL_H / 2)),
                 (HULL_W, 0.30, 0.018), hull_mat),
            cube("ship.roof", start + Vector((0, 0, HULL_H / 2)),
                 (HULL_W, 0.30, 0.018), hull_mat)]
    for s in (-1, 1):
        hull.append(cube(f"ship.wall.{s}",
                         start + Vector((s * HULL_W / 2, 0, 0)),
                         (0.018, 0.30, HULL_H), hull_mat))
    made += hull

    sign = label("BELOW DECK",
                 start + Vector((-HULL_W / 2 + 0.08, -0.152, HULL_H / 2 - 0.06)),
                 0.034, (0.84, 0.74, 0.54, 1.0), align="LEFT")
    made.append(sign)

    bowl = ball("ship.bowl", 0.055, start + Vector((-0.20, 0, -HULL_H / 2 + 0.07)),
                glass)
    fish = ball("ship.fish", 0.018,
                start + Vector((-0.20, 0, -HULL_H / 2 + 0.07)), fish_mat,
                segments=14)
    bottle = cube("ship.bottle", start + Vector((0.20, 0, HULL_H / 2 - 0.09)),
                  (0.045, 0.045, 0.10), glass)
    jar = cube("ship.jar", start + Vector((0.20, 0, -HULL_H / 2 + 0.05)),
               (0.075, 0.075, 0.07), glass)
    made += [bowl, fish, bottle, jar]

    drips = [ball(f"ship.drip.{i}", 0.010, start, water, segments=10)
             for i in range(DRIPS)]
    made += drips

    def hull_x(u):
        return start.x + TRAVEL * u

    top = origin.z + HULL_H / 2 - 0.15
    bottom = origin.z - HULL_H / 2 + 0.08

    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        dx = hull_x(u) - start.x
        for obj, ox, oz in ((hull[0], 0, -HULL_H / 2), (hull[1], 0, HULL_H / 2),
                            (hull[2], -HULL_W / 2, 0), (hull[3], HULL_W / 2, 0)):
            key(obj, f, location=(start.x + dx + ox, origin.y, origin.z + oz))
        key(sign, f, location=(start.x + dx - HULL_W / 2 + 0.08,
                               origin.y - 0.152, origin.z + HULL_H / 2 - 0.06))
        for obj, ox, oz in ((bowl, -0.20, -HULL_H / 2 + 0.07),
                            (fish, -0.20, -HULL_H / 2 + 0.07),
                            (bottle, 0.20, HULL_H / 2 - 0.09),
                            (jar, 0.20, -HULL_H / 2 + 0.05)):
            wobble = 0.006 if obj is fish else 0.0
            key(obj, f, location=(start.x + dx + ox, origin.y,
                                  origin.z + oz + wobble * (1 if f % 7 < 4 else -1)))
        # Straight down, in the cabin's own frame. Nothing leans.
        for i, drip in enumerate(drips):
            phase = (u * 2.4 + i / DRIPS) % 1.0
            key(drip, f, location=(start.x + dx + 0.20, origin.y,
                                   top - (top - bottom) * phase))

    return dict(objects=made, focus=origin, base=HULL_H / 2 + 0.05,
                width=HULL_W + TRAVEL + 0.30,
                caption="nothing in here tells you the ship is moving")
