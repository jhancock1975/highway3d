"""A rod, shortened along its motion and only along it.

Two rods, one still and one moving, with the moving one visibly shorter along
x and visibly the same across it. The comparison is the demonstration: a
single shrinking rod invites the question "shorter than what?", and the answer
has to be on screen at the same time.

The rule markings matter more than they look. A smooth bar that changes length
is ambiguous -- it could be moving toward you -- and the ticks sliding closer
together are what make it read as contraction rather than perspective.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, cube, key, label, matte

NAME = "rod_contraction"
SUMMARY = ("Two identical rods, one at rest and one moving: the moving one is "
           "shorter along its motion, and exactly the same across it.")

REST_LEN = 0.66
TICKS = 8
GAMMA = 1.60          # the contraction actually drawn, v = 0.78c


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    still_mat = matte("demo.pale", PALETTE["pale"], 0.55)
    moving_mat = matte("demo.cool", PALETTE["cool"], 0.45)
    tick_mat = matte("demo.slate", PALETTE["slate"], 0.8)

    made = []
    rows = (("rest", 0.15, still_mat, 1.0, "at rest"),
            ("moving", 0.02, moving_mat, 1.0 / GAMMA, "moving at 0.78c"))

    moving_parts = []
    for tag, dz, mat, _, caption in rows:
        at = origin + Vector((0, 0, dz))
        bar = cube(f"rod.{tag}", at, (REST_LEN, 0.055, 0.045), mat)
        made.append(bar)
        ticks = []
        for i in range(TICKS + 1):
            u = i / TICKS - 0.5
            t = cube(f"rod.{tag}.tick{i}",
                     at + Vector((u * REST_LEN, -0.030, 0)),
                     (0.006, 0.004, 0.045), tick_mat)
            ticks.append((t, u))
            made.append(t)
        made.append(label(caption, at + Vector((0, -0.05, 0.048)), 0.034,
                          (0.80, 0.84, 0.92, 1.0)))
        if tag == "moving":
            moving_parts = [(bar, 0.0)] + ticks

    # The contraction arrives over the first third and then holds, so there is
    # something to look at rather than a state that was always true.
    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        ease = min(1.0, u / 0.34)
        ease = ease * ease * (3 - 2 * ease)
        factor = 1.0 - (1.0 - 1.0 / GAMMA) * ease
        for obj, offset in moving_parts:
            if offset == 0.0 and obj.name.endswith("moving"):
                key(obj, f, scale=(REST_LEN * factor, 0.055, 0.045))
            else:
                key(obj, f, location=(origin.x + offset * REST_LEN * factor,
                                      origin.y - 0.030, origin.z + 0.02))

    return dict(objects=made, focus=origin, base=0.02,
                width=REST_LEN + 0.30,
                caption="shorter along the motion, unchanged across it")
