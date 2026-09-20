"""A laboratory, a toothed wheel, and a man timing a beam of light.

The measurement is Fizeau's: light goes out through a gap in a spinning
toothed wheel, travels to a distant mirror, and comes back. Spin the wheel
fast enough and the returning light meets a tooth instead of a gap and the
image blacks out. From the speed of the wheel and the distance to the
mirror, the speed of light falls out -- on a bench, with a crank and a
candle, decades before anyone could measure a nanosecond.

Built as a cutaway rather than as a demonstration on a plinth, because the
sentence it plays under is about somebody doing this, not about the
apparatus. He is not in the frame; the narration carries over it.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..demos import ball, cube, glow, key, label, matte, rod

NAME = "light_bench"
SUMMARY = ("A Victorian laboratory: a figure cranks a toothed wheel while a "
           "beam of light runs out to a distant mirror and back.")

BENCH_Y = 0.30        # the bench runs across in front of the wall
FIG_Y = 0.78          # he stands behind it, between bench and wall
WHEEL_X = -0.25
MIRROR_X = 1.30


def _room(made):
    """Dark boards, a dark wall, and nothing else competing for attention."""
    floor = matte("lab.floor", (0.050, 0.043, 0.038, 1.0), 0.94)
    wall = matte("lab.wall", (0.064, 0.058, 0.062, 1.0), 0.96)
    bpy.ops.mesh.primitive_plane_add(size=18, location=(0.4, 0, -0.98))
    o = bpy.context.object; o.name = "lab.floor"
    o.data.materials.append(floor); made.append(o)
    bpy.ops.mesh.primitive_plane_add(size=18, location=(0.4, 2.35, 2.0),
                                     rotation=(math.pi / 2, 0, 0))
    o = bpy.context.object; o.name = "lab.wall"
    o.data.materials.append(wall); made.append(o)


def _figure(made, x, seed=3):
    """A lab assistant, built plainly so he is not mistaken for the lecturer.

    Dark coat, dark hair, ordinary proportions. The presenter is a caricature
    with an enormous head and white hair precisely so he is recognisable at a
    glance; anybody else in this film has to be visibly not him, which means
    a normal head on a normal body and no silhouette worth remembering.
    """
    coat = matte("lab.coat", (0.115, 0.125, 0.150, 1.0), 0.88)
    skin = matte("lab.skin", (0.70, 0.50, 0.39, 1.0), 0.58)
    hair = matte("lab.hair", (0.085, 0.070, 0.062, 1.0), 0.80)
    shirt = matte("lab.shirt", (0.66, 0.67, 0.70, 1.0), 0.72)

    head = ball("fig.head", 0.098, (x, FIG_Y, -0.06), skin, 28)
    head.scale = (0.92, 1.0, 1.10)
    cap = ball("fig.hair", 0.104, (x, FIG_Y + 0.010, -0.035), hair, 24)
    cap.scale = (1.0, 1.0, 0.80)
    neck = ball("fig.neck", 0.042, (x, FIG_Y, -0.175), skin, 16)
    chest = ball("fig.chest", 0.150, (x, FIG_Y, -0.345), coat, 26)
    chest.scale = (1.20, 0.76, 1.05)
    waist = ball("fig.waist", 0.132, (x, FIG_Y, -0.560), coat, 24)
    waist.scale = (1.08, 0.76, 1.00)
    collar = ball("fig.collar", 0.052, (x, FIG_Y - 0.075, -0.205), shirt, 18)
    collar.scale = (1.30, 0.70, 0.60)
    parts = [head, cap, neck, chest, waist, collar]

    for side in (-1, 1):
        sh = ball(f"fig.sh{side}", 0.058, (x + side * 0.155, FIG_Y, -0.290),
                  coat, 18)
        upper = rod(f"fig.up{side}", 0.048, 0.20,
                    (x + side * 0.175, FIG_Y - 0.02, -0.400), coat)
        upper.rotation_euler = (0.0, side * 0.16, 0.0)
        parts += [sh, upper]

    # the near arm carries on down to the crank; the far one stops at the elbow
    fore = rod("fig.fore", 0.042, 0.22, (x + 0.245, FIG_Y - 0.175, -0.470),
               coat)
    fore.rotation_euler = (1.02, 0.0, 0.0)
    hand = ball("fig.hand", 0.044, (x + 0.265, FIG_Y - 0.335, -0.395), skin, 18)
    fore2 = rod("fig.fore2", 0.042, 0.18, (x - 0.215, FIG_Y, -0.545), coat)
    parts += [fore, hand, fore2]

    hips = ball("fig.hips", 0.135, (x, FIG_Y, -0.700), coat, 22)
    hips.scale = (1.10, 0.82, 0.70)
    parts.append(hips)
    for side in (-1, 1):
        leg = rod(f"fig.leg{side}", 0.055, 0.34,
                  (x + side * 0.072, FIG_Y, -0.930), coat)
        parts.append(leg)
        shoe = ball(f"fig.shoe{side}", 0.052,
                    (x + side * 0.072, FIG_Y - 0.030, -1.098), hair, 16)
        shoe.scale = (0.82, 1.45, 0.42)
        parts.append(shoe)

    made.extend(parts)
    return dict(head=head, hair=cap, hand=hand, arm=fore)


def build(n_frames: int, fps: int) -> dict:
    made: list = []
    _room(made)

    wood = matte("lab.wood", (0.20, 0.145, 0.105, 1.0), 0.72)
    brass = matte("lab.brass", (0.62, 0.48, 0.22, 1.0), 0.34)
    dark = matte("lab.iron", (0.10, 0.10, 0.11, 1.0), 0.52)

    # the bench: long, low, running away from camera-left to camera-right
    made.append(cube("bench.top", (0.52, BENCH_Y, -0.34),
                     (2.5, 0.52, 0.055), wood))
    for bx in (-0.58, 1.62):
        made.append(cube(f"bench.leg{bx:.0f}", (bx, BENCH_Y, -0.67),
                         (0.09, 0.50, 0.62), wood))

    # the lamp housing, the toothed wheel, and the distant mirror
    made.append(cube("lamp.box", (WHEEL_X - 0.40, BENCH_Y, -0.245),
                     (0.24, 0.20, 0.20), dark))
    lamp_glow = glow("lab.flame", (1.0, 0.82, 0.48), 26.0)
    made.append(ball("lamp.flame", 0.040,
                     (WHEEL_X - 0.28, BENCH_Y, -0.245), lamp_glow, 18))

    wheel = bpy.data.objects.new("wheel", None)
    bpy.context.scene.collection.objects.link(wheel)
    wheel.location = (WHEEL_X, BENCH_Y, -0.22)
    made.append(wheel)
    disc = bpy.ops.mesh.primitive_cylinder_add(
        radius=0.145, depth=0.018, location=(WHEEL_X, BENCH_Y, -0.22),
        rotation=(0, math.pi / 2, 0), vertices=48)
    d = bpy.context.object; d.name = "wheel.disc"
    d.data.materials.append(brass); made.append(d)
    d.parent = wheel
    d.matrix_parent_inverse = wheel.matrix_world.inverted()
    for i in range(12):
        a = i * math.pi / 6.0
        t = cube(f"wheel.tooth{i}",
                 (WHEEL_X, BENCH_Y + 0.175 * math.cos(a),
                  -0.22 + 0.175 * math.sin(a)),
                 (0.022, 0.055, 0.055), brass)
        t.rotation_euler = (a, 0, 0)
        t.parent = wheel
        t.matrix_parent_inverse = wheel.matrix_world.inverted()
        made.append(t)

    made.append(cube("mirror.post", (MIRROR_X, BENCH_Y, -0.62),
                     (0.07, 0.07, 0.50), dark))
    mirror = cube("mirror.face", (MIRROR_X, BENCH_Y, -0.22),
                  (0.03, 0.26, 0.26), matte("lab.silver", (0.72, 0.75, 0.78, 1.0), 0.08))
    made.append(mirror)

    fig = _figure(made, WHEEL_X - 1.02)

    # the pulse: out to the mirror and back, over and over
    pulse_mat = glow("lab.pulse", (1.0, 0.93, 0.70), 30.0)
    pulse = ball("lab.pulse", 0.030, (WHEEL_X, BENCH_Y, -0.22),
                 pulse_mat, 16)
    made.append(pulse)

    trips = max(2, int(round(n_frames / fps / 1.6)))
    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        s = (u * trips) % 1.0
        # out on the first half, back on the second
        travel = s * 2.0 if s < 0.5 else (1.0 - s) * 2.0
        px = WHEEL_X + (MIRROR_X - WHEEL_X) * travel
        key(pulse, f, location=(px, BENCH_Y, -0.22))
        key(wheel, f, rotation=(u * trips * 2.4 * math.pi, 0, 0))
        # he leans in a little as the wheel comes up to speed
        key(fig["head"], f,
            location=(WHEEL_X - 1.02, FIG_Y - 0.02 * math.sin(u * 3.1),
                      -0.06 + 0.006 * math.sin(u * 6.2)))

    label("timing a beam against a spinning wheel",
          (0.45, BENCH_Y - 0.36, -0.92), size=0.075)

    # a warm working light over the bench, and a cold one from the window side
    d = bpy.data.lights.new("lab.key", "AREA")
    d.energy, d.size, d.color = 180.0, 1.6, (1.0, 0.88, 0.70)
    o = bpy.data.objects.new("lab.key", d)
    o.location = (0.10, BENCH_Y - 1.2, 1.5)
    o.rotation_euler = (math.radians(52), 0, math.radians(-14))
    bpy.context.scene.collection.objects.link(o); made.append(o)
    d2 = bpy.data.lights.new("lab.rim", "AREA")
    d2.energy, d2.size, d2.color = 90.0, 2.2, (0.62, 0.74, 1.0)
    o2 = bpy.data.objects.new("lab.rim", d2)
    o2.location = (2.4, BENCH_Y + 1.4, 1.2)
    o2.rotation_euler = (math.radians(-64), 0, math.radians(38))
    bpy.context.scene.collection.objects.link(o2); made.append(o2)

    return dict(objects=made,
                camera=dict(location=(0.30, -3.45, -0.12), lens=34,
                            target=(0.30, BENCH_Y, -0.46)),
                caption=SUMMARY)
