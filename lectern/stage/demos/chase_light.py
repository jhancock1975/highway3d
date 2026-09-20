"""Chasing a light beam, and never gaining on it.

A runner accelerates from rest to most of c, and the pulse ahead keeps exactly
the same lead the whole way. Everyday intuition says the gap should close; the
demonstration is that it does not, and the speed readout beside the runner is
what makes the failure specific rather than vague.

The readout carries real numbers. A dial with no figures on it is decoration.
"""

from __future__ import annotations

from mathutils import Vector

from . import PALETTE, ball, cube, glow, key, label, matte

NAME = "chase_light"
SUMMARY = ("Accelerate as hard as you like toward a light pulse: it still "
           "outruns you by exactly c, and the gap never closes.")

TRACK = 1.00
GAP = 0.34


def build(origin: Vector, n_frames: int, fps: int) -> dict:
    rail = matte("demo.slate", PALETTE["slate"], 0.8)
    runner_mat = matte("demo.warm", PALETTE["warm"], 0.45)
    pulse_mat = glow("demo.pulse", (0.85, 0.94, 1.0), 26.0)
    gap_mat = glow("demo.gapline", (0.45, 0.72, 1.0), 2.2)

    made = []
    left = origin.x - TRACK / 2
    made.append(cube("chase.rail", origin + Vector((0, 0, -0.055)),
                     (TRACK, 0.26, 0.030), rail))

    runner = cube("chase.runner", origin, (0.110, 0.110, 0.150), runner_mat)
    pulse = ball("chase.pulse", 0.046, origin, pulse_mat)
    made += [runner, pulse]

    bar = cube("chase.gapbar", origin + Vector((0, 0, 0.135)),
               (GAP, 0.014, 0.012), gap_mat)
    made.append(bar)
    made.append(label("the gap never closes",
                      origin + Vector((0, -0.02, 0.175)), 0.034,
                      (0.68, 0.84, 1.0, 1.0)))

    speed = label("0.00 c", origin + Vector((0, -0.05, -0.135)), 0.044,
                  (1.0, 0.78, 0.58, 1.0))
    made.append(speed)

    # The runner eases up toward c and never reaches it; the pulse keeps its
    # lead exactly, which is the only thing the eye has to check.
    for f in range(1, n_frames + 1):
        u = (f - 1) / max(1, n_frames - 1)
        v = 0.94 * (1.0 - pow(1.0 - u, 2.2))
        x = left + (TRACK - GAP) * (u * 0.82)
        key(runner, f, location=(x, origin.y, origin.z))
        key(pulse, f, location=(x + GAP, origin.y, origin.z))
        key(bar, f, location=(x + GAP / 2, origin.y, origin.z + 0.135))
        key(speed, f, location=(x, origin.y - 0.05, origin.z - 0.135))

    # The readout is redrawn in steps rather than per frame: text data cannot
    # be keyframed, so each figure is its own object, shown for its stretch.
    made_speed = []
    for i in range(6):
        u0, u1 = i / 6, (i + 1) / 6
        v = 0.94 * (1.0 - pow(1.0 - (u0 + u1) / 2, 2.2))
        t = label(f"{v:.2f} c", origin + Vector((0, -0.05, -0.135)), 0.044,
                  (1.0, 0.78, 0.58, 1.0))
        made_speed.append(t)
        made.append(t)
        for f in range(1, n_frames + 1):
            u = (f - 1) / max(1, n_frames - 1)
            x = left + (TRACK - GAP) * (u * 0.82)
            on = u0 <= u < u1
            key(t, f, location=(x, origin.y - 0.05, origin.z - 0.135))
            key(t, f, scale=(1, 1, 1) if on else (0.001, 0.001, 0.001))
    # the placeholder readout is replaced by the stepped ones
    for f in (1, n_frames):
        key(speed, f, scale=(0.001, 0.001, 0.001))

    return dict(objects=made, focus=origin, base=0.075,
                width=TRACK + 0.24,
                caption="however hard you run, it leaves at c")
