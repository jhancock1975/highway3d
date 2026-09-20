"""Muons reaching the ground, which by rights they should not.

The one place in the lecture where the arithmetic is checked against
something measured rather than imagined, so it is staged as an altitude
column with a real scale on it: created high up, a lifetime that gets them
only part of the way, and the ones that arrive anyway.

Two streams fall side by side -- what Newton predicts and what happens -- and
the difference between where they stop is the whole result.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, ball, cube, glow, key, label, matte

NAME = "muon"
SUMMARY = ("Muons made high in the atmosphere reaching the ground: without "
           "time dilation almost none would arrive, and they do.")

COLUMN = 0.56
STREAM = 7


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    air = matte("demo.air", (0.38, 0.46, 0.60, 1.0), 0.8)
    ground_mat = matte("demo.ground", (0.24, 0.20, 0.15, 1.0), 0.85)
    dead_mat = glow("demo.dead", (0.85, 0.36, 0.30), 3.0)
    live_mat = glow("demo.live", (0.55, 0.92, 0.70), 6.0)

    made = []
    top_z = origin.z + COLUMN / 2
    ground_z = origin.z - COLUMN / 2

    # No box: a solid slab of "atmosphere" hid the muons it was meant to
    # contain. Two thin guide rails give the column without filling it.
    for gx in (-0.23, 0.23):
        made.append(cube(f"muon.rail.{gx}", origin + Vector((gx, 0.02, 0)),
                         (0.006, 0.006, COLUMN), air))
    made.append(cube("muon.ground", origin + Vector((0, 0, ground_z - origin.z - 0.012)),
                     (0.62, 0.20, 0.022), ground_mat))
    made.append(label("15 km", origin + Vector((-0.30, -0.03, COLUMN / 2 - 0.02)),
                      0.030, (0.72, 0.78, 0.88, 1.0), align="LEFT"))
    made.append(label("sea level", origin + Vector((-0.30, -0.03, -COLUMN / 2 + 0.01)),
                      0.030, (0.72, 0.78, 0.88, 1.0), align="LEFT"))

    # Newton's muons: they expire about a fifth of the way down.
    dead_stop = top_z - COLUMN * 0.22
    dead = [ball(f"muon.dead.{i}", 0.014,
                 origin + Vector((-0.12, 0, top_z)), dead_mat, segments=12)
            for i in range(STREAM)]
    live = [ball(f"muon.live.{i}", 0.014,
                 origin + Vector((0.12, 0, top_z)), live_mat, segments=12)
            for i in range(STREAM)]
    made += dead + live
    made.append(label("as Newton has it",
                      origin + Vector((-0.12, -0.03, COLUMN / 2 + 0.045)), 0.026,
                      (1.0, 0.62, 0.56, 1.0)))
    made.append(label("as they arrive",
                      origin + Vector((0.12, -0.03, COLUMN / 2 + 0.045)), 0.026,
                      (0.66, 1.0, 0.80, 1.0)))

    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        for i in range(STREAM):
            phase = (u * 1.7 + i / STREAM) % 1.0
            z_dead = top_z - (top_z - dead_stop) * min(1.0, phase * 2.4)
            key(dead[i], f, location=(origin.x - 0.12, origin.y, z_dead))
            key(dead[i], f, scale=(1, 1, 1) if phase < 0.42
                else (0.001, 0.001, 0.001))
            z_live = top_z - (top_z - ground_z - 0.02) * phase
            key(live[i], f, location=(origin.x + 0.12, origin.y, z_live))
            key(live[i], f, scale=(1, 1, 1) if phase < 0.99
                else (0.001, 0.001, 0.001))

    return dict(objects=made, focus=origin, base=COLUMN / 2 + 0.02,
                width=0.86,
                caption="they arrive, and that is the measurement")
