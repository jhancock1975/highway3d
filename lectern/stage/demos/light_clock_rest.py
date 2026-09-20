"""A light clock standing still: one tick is one round trip, straight up.

The whole derivation of time dilation hangs off this object, so it is built
to be read rather than admired: two plainly parallel mirrors, a visible gap,
and a pulse whose path is the only thing moving. The companion demonstration
`light_clock_moving` is the same clock, translated, and the point is that the
two look identical from inside and completely different from outside.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, ball, cube, glow, key, label, matte, rod

NAME = "light_clock_rest"
SUMMARY = ("A light clock at rest: a pulse bouncing straight up and down "
           "between two mirrors. One round trip is one tick.")

GAP = 0.44
PLATE = 0.28


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    steel = matte("demo.steel", PALETTE["steel"], 0.35)
    frame_mat = matte("demo.slate", PALETTE["slate"], 0.7)
    beam = glow("demo.beam", (0.55, 0.80, 1.0), 9.0)
    pulse_mat = glow("demo.pulse", (0.85, 0.94, 1.0), 26.0)

    made = []
    bottom = origin + Vector((0, 0, -GAP / 2))
    top = origin + Vector((0, 0, GAP / 2))

    for tag, at in (("bottom", bottom), ("top", top)):
        m = cube(f"clock.{tag}", at, (PLATE, PLATE, 0.022), steel)
        made.append(m)

    # two posts, so it reads as one instrument rather than two floating slabs
    for side in (-1, 1):
        made.append(rod(f"clock.post.{side}", 0.005, GAP,
                        origin + Vector((side * PLATE * 0.46, 0, 0)),
                        frame_mat))

    # the beam: a thin column the pulse travels inside
    column = rod("clock.beam", 0.010, GAP * 0.98, origin, beam)
    column.hide_render = True
    made.append(column)

    pulse = ball("clock.pulse", 0.030, bottom + Vector((0, 0, 0.02)), pulse_mat)
    made.append(pulse)

    # Two full ticks across the shot, whatever the shot turns out to be: the
    # sentence sets the length, not the clock.
    ticks = 2.0
    lo = bottom.z + 0.024
    hi = top.z - 0.024
    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        # triangle wave: up, down, up, down
        saw = (u * ticks) % 1.0
        z = lo + (hi - lo) * (2 * saw if saw < 0.5 else 2 * (1 - saw))
        key(pulse, f, location=(origin.x, origin.y, z))

    return dict(objects=made, focus=origin, base=GAP / 2 + 0.014,
                width=(TRAVEL + PLATE + 0.26) if "TRAVEL" in globals() else PLATE + 0.60,
                caption="a clock that keeps time with light")
