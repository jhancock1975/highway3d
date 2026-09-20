"""A ladder too long for the barn, fitting inside it anyway.

Staged from the barn's point of view, because that is the frame in which the
paradox looks like a contradiction: the ladder is contracted, both doors shut
with it inside, and nothing has been broken. The resolution is that "both
doors shut at once" is a claim about simultaneity, and the ladder's own frame
disagrees about it -- which the caption says and the next segment develops.

Both doors carry their labels. A barn with two identical blank panels leaves
the viewer counting which is which.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, cube, key, label, matte

NAME = "ladder_barn"
SUMMARY = ("A ladder longer than the barn, contracted enough to fit with both "
           "doors shut at once -- in the barn's frame.")

BARN_W = 0.56
BARN_H = 0.30
LADDER = 0.76          # rest length, plainly longer than the barn
GAMMA = 1.55


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    barn_mat = matte("demo.barn", (0.36, 0.20, 0.17, 1.0), 0.78)
    door_mat = matte("demo.brass", PALETTE["brass"], 0.45)
    ladder_mat = matte("demo.pale", PALETTE["pale"], 0.5)

    made = []
    made.append(cube("barn.roof", origin + Vector((0, 0, BARN_H / 2)),
                     (BARN_W, 0.30, 0.020), barn_mat))
    made.append(cube("barn.floor", origin + Vector((0, 0, -BARN_H / 2)),
                     (BARN_W + 0.16, 0.30, 0.018), barn_mat))

    doors = []
    for side, name in ((-1, "in"), (1, "out")):
        d = cube(f"barn.door.{name}",
                 origin + Vector((side * BARN_W / 2, 0, BARN_H / 2 - 0.02)),
                 (0.018, 0.28, BARN_H * 0.92), door_mat)
        doors.append((d, side))
        made.append(d)
    made.append(label("front door",
                      origin + Vector((-BARN_W / 2, -0.155, BARN_H / 2 + 0.035)),
                      0.026))
    made.append(label("back door",
                      origin + Vector((BARN_W / 2, -0.155, BARN_H / 2 + 0.035)),
                      0.026))

    ladder = cube("barn.ladder", origin + Vector((-0.42, 0, -BARN_H / 2 + 0.06)),
                  (LADDER, 0.05, 0.035), ladder_mat)
    made.append(ladder)
    rungs = []
    for i in range(6):
        u = (i + 0.5) / 6 - 0.5
        r = cube(f"barn.rung.{i}",
                 origin + Vector((-0.42 + u * LADDER, -0.03,
                                  -BARN_H / 2 + 0.06)),
                 (0.008, 0.008, 0.045), door_mat)
        rungs.append((r, u))
        made.append(r)

    shut = 0.58        # when both doors are closed, briefly
    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        length = LADDER / GAMMA
        x = -0.42 + (0.42 + 0.0) * min(1.0, u / shut)
        key(ladder, f, location=(origin.x + x, origin.y,
                                 origin.z - BARN_H / 2 + 0.06),
            scale=(length, 0.05, 0.035))
        for r, off in rungs:
            key(r, f, location=(origin.x + x + off * length, origin.y - 0.03,
                                origin.z - BARN_H / 2 + 0.06))
        # Both doors close for a moment, with it inside. In the barn's frame.
        closed = shut <= u < shut + 0.20
        for d, side in doors:
            z = origin.z + (0.0 if closed else BARN_H / 2 - 0.02)
            key(d, f, location=(origin.x + side * BARN_W / 2, origin.y, z))

    return dict(objects=made, focus=origin, base=BARN_H / 2 + 0.02,
                width=BARN_W + 0.50,
                caption="both doors shut at once -- in the barn's frame")
