"""The interferometer that found nothing, which was the discovery.

A splitter, two arms, two mirrors, and a fringe pattern at the detector. The
apparatus rotates through the shot and the fringes stay put -- that null
result is the demonstration, and it needs the fringes visible and steady
rather than a caption saying they did not move.

The arms are labelled, because the whole design is about comparing two paths
and an unlabelled cross is just a cross.
"""

from __future__ import annotations

import math

from mathutils import Vector

import bpy

from . import PALETTE, ball, cube, glow, key, label, matte

NAME = "michelson"
SUMMARY = ("The Michelson-Morley interferometer: two perpendicular arms, "
           "rotated through the ether, and fringes that refuse to shift.")

ARM = 0.30
FRINGES = 7


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    bench = matte("demo.slate", PALETTE["slate"], 0.8)
    mirror = matte("demo.steel", PALETTE["steel"], 0.22)
    split_mat = matte("demo.glass2", (0.55, 0.70, 0.78, 1.0), 0.18)
    beam_mat = glow("demo.beam2", (0.55, 0.82, 1.0), 4.5)
    fringe_mat = glow("demo.fringe", (0.80, 0.90, 1.0), 6.0)

    made = []
    plate = cube("mm.bench", origin + Vector((0, 0, -0.035)),
                 (ARM * 2 + 0.16, ARM * 2 + 0.16, 0.014), bench)
    made.append(plate)

    split = cube("mm.splitter", origin, (0.050, 0.010, 0.050), split_mat)
    split.rotation_euler = (0, 0, math.radians(45))
    made.append(split)

    arms = []
    for name, off in (("x", Vector((ARM, 0, 0))), ("y", Vector((0, ARM, 0)))):
        m = cube(f"mm.mirror.{name}", origin + off, (0.014, 0.090, 0.070)
                 if name == "x" else (0.090, 0.014, 0.070), mirror)
        b = cube(f"mm.beam.{name}", origin + off / 2,
                 (ARM, 0.006, 0.006) if name == "x" else (0.006, ARM, 0.006),
                 beam_mat)
        arms += [m, b]
        made += [m, b]
    made.append(label("arm 1", origin + Vector((ARM * 0.62, -0.06, 0.052)),
                      0.026))
    made.append(label("arm 2", origin + Vector((-0.10, ARM * 0.5, 0.052)),
                      0.026))

    # The detector, and the fringes that are supposed to shift and do not.
    det = cube("mm.detector", origin + Vector((0, -ARM, 0)),
               (0.130, 0.014, 0.090), bench)
    made.append(det)
    made.append(label("detector", origin + Vector((0, -ARM - 0.02, -0.075)),
                      0.026))
    bars = []
    for i in range(FRINGES):
        u = (i - (FRINGES - 1) / 2) / FRINGES
        b = cube(f"mm.fringe.{i}",
                 origin + Vector((u * 0.11, -ARM - 0.010, 0.0)),
                 (0.007, 0.004, 0.060), fringe_mat)
        bars.append(b)
        made.append(b)

    # Rotated as one instrument, about the bench's own centre. Turning each
    # part about its own origin would spin the mirrors on the spot and leave
    # the arms where they were.
    pivot = bpy.data.objects.new("mm.pivot", None)
    pivot.location = origin
    bpy.context.scene.collection.objects.link(pivot)
    for obj in [plate, split] + arms + bars + [det]:
        obj.parent = pivot
        obj.matrix_parent_inverse = pivot.matrix_world.inverted()

    # Tipped up to face the room. Lying flat on a bench is how it really sat,
    # and from a seat in the audience that is an edge-on sliver.
    tilt = math.radians(66.0)
    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        key(pivot, f, rotation=(tilt, 0, math.radians(88.0) * u))
        # The apparatus turns and the fringes ride with it -- but they never
        # shift along the detector, which is the null result itself.

    return dict(objects=made, focus=origin, base=0.02,
                width=ARM * 2 + 0.40,
                caption="rotate it all you like: the fringes do not move")
