"""Where things are in the study, as numbers anyone can read.

Pure Python: the timeline planner (no bpy) and the Blender set builder both
read these, so a camera aimed at "the slate" by the planner is aimed at the
slate the set actually built.
"""

from __future__ import annotations

import math

# Euler's chair, and his body's placement in it (body origin on the floor
# under the seat; see euler_shape.J)
CHAIR = (0.25, 0.85, 0.0)
CHAIR_YAW = -36.0
EULER = (0.25, 0.87, 0.0)
EULER_YAW = -36.0

# the slate on its easel
SLATE_ROOT = (-0.18, 1.065, 0.0)
SLATE_YAW = 48.6
SLATE_W, SLATE_H = 0.95, 0.72
SLATE_Z = 0.52                  # bottom edge of the writing surface
SLATE_TILT = -9.0               # leaning back, degrees

# the window (on the back wall, y = 3)
WIN_X, WIN_W, WIN_SILL, WIN_H = 0.55, 1.25, 0.85, 1.95
ROOM_D = 6.0


def _rz(v, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])


def _rx(v, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (v[0], v[1] * c - v[2] * s, v[1] * s + v[2] * c)


def board_point(u: float, v: float, lift: float = 0.0):
    """World position of a point on the slate's face: u, v in 0..1 from the
    bottom-left as you face it; `lift` metres out from the surface."""
    local = ((u - 0.5) * SLATE_W, -lift, v * SLATE_H)
    p = _rx(local, SLATE_TILT)
    p = (p[0], p[1], p[2] + SLATE_Z)
    p = _rz(p, SLATE_YAW)
    return (p[0] + SLATE_ROOT[0], p[1] + SLATE_ROOT[1], p[2] + SLATE_ROOT[2])


def board_normal():
    n = _rz(_rx((0, -1, 0), SLATE_TILT), SLATE_YAW)
    return n


def euler_point(local):
    """A point given in Euler's body coordinates, in the world."""
    p = _rz(local, EULER_YAW)
    return (p[0] + EULER[0], p[1] + EULER[1], p[2] + EULER[2])


# where each formula is written, as (u0, u1, v_centre, height) on the board
# Everything he writes sits where he can reach from his chair with his arm
# still bent -- within 0.40 m of his shoulder as it really is when he leans
# (it moves only 4-6 cm; his spine bends low). An earlier layout spread the
# formulas to 0.77 m, and his hand hung off the slate's edge, arm locked
# straight, while the chalk wrote on without it.
BOARD_LAYOUT = {
    "basel":    (0.42, 0.84, 0.72, 0.085),
    "harmonic": (0.42, 0.84, 0.59, 0.085),
    "product":  (0.40, 0.86, 0.43, 0.13),
    "exp":      (0.48, 0.60, 0.265, 0.09),
    "identity": (0.48, 0.84, 0.265, 0.09),
}

# older work, half rubbed out, on the part of the slate he cannot reach
# from his chair: it was written standing, some other day
GHOST_LAYOUT = {
    "ghost_formula": (0.1, 0.37, 0.84, 0.065),
    "ghost_poly":    (0.12, 0.33, 0.12, 0.065),
}
GHOSTS = {
    "ghost_formula": r"e^{ix} = \cos x + i \sin x",
    "ghost_poly":    r"V - E + F = 2",
}

# Cinnamon's marks (world, its body centre)
CINNAMON = {
    "outside": (WIN_X - 0.25, ROOM_D / 2 + 1.2, 1.7),
    "window": (WIN_X - 0.25, ROOM_D / 2 - 0.35, 1.6),
    "home": (-0.3, 0.16, 1.27),
    "close": (-0.14, 0.46, 0.92),
    "high": (-0.2, 0.28, 1.5),
}


def watch_spot():
    """Where Cinnamon hovers while Euler writes: up over the slate's top
    edge and a little behind it, peering down at the chalk -- facing the
    audience and well clear of the writing shot's lens. (Hovering over the
    front corner put the back of its head in the foreground of that shot;
    hovering just over the edge left it in the top of the frame for whole
    shots, cut off at the chin, its face behind the easel post. It goes up
    out of the shot and comes back down when he has finished.)"""
    p = board_point(0.55, 2.0, lift=-0.12)
    return (p[0], p[1], p[2])


def lick_spot(board: str):
    """Where Cinnamon hovers to lick a formula: out past the slate's left
    edge, well clear of Euler, and the tongue goes the rest of the way.

    In front of the formula's middle, where it used to hover, is where
    Euler sits -- 45 cm out from the slate's centre-right -- and it licked
    from inside his chest. From here the tongue crosses 60-70 cm of air to
    the chalk, which is the joke anyway."""
    u0, u1, v, h = BOARD_LAYOUT[board]
    p = board_point(max(0.05, u0 - 0.38), v + 0.08, lift=0.48)
    # never below his eyes: hovering level with a formula low on the slate
    # put its body between the camera and its own tongue
    return (p[0], p[1], max(p[2], HEAD_EULER[2] - 0.02))


HEAD_EULER = euler_point((0.0, -0.06, 1.16))

# his right shoulder while he leans to write, measured on the rig (body
# coordinates), and how far the chalk may be from it. The wrist reaches
# 0.485 m, but the chalk in his fist sits beside the line of the arm, not
# beyond it -- measured, it adds 2-3 cm -- so 0.40 keeps the elbow bent.
WRITING_SHOULDER = (-0.219, 0.01, 0.899)
CHALK_REACH = 0.40
