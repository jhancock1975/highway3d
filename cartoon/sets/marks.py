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
SLATE_ROOT = (-0.38, 0.78, 0.0)
SLATE_YAW = 62.0
SLATE_W, SLATE_H = 0.95, 0.72
SLATE_Z = 0.58                  # bottom edge of the writing surface
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
# Everything sits in the right-hand two thirds: he writes from his chair,
# leaning, and the left of the board is out of an old man's reach.
BOARD_LAYOUT = {
    "basel":    (0.40, 0.97, 0.85, 0.11),
    "harmonic": (0.40, 0.97, 0.66, 0.11),
    "product":  (0.26, 0.97, 0.43, 0.17),
    "exp":      (0.48, 0.68, 0.16, 0.12),
    "identity": (0.48, 0.97, 0.16, 0.12),
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
    corner, peeking down at the chalk -- out of the writing shot's way."""
    p = board_point(0.12, 1.12, lift=0.22)
    return (p[0], p[1], p[2])


def lick_spot(board: str):
    """Where Cinnamon hovers to lick a formula: in front of its middle."""
    u0, u1, v, h = BOARD_LAYOUT[board]
    p = board_point((u0 + u1) / 2, v, lift=0.38)
    return (p[0], p[1], p[2] - 0.04)


HEAD_EULER = euler_point((0.0, -0.06, 1.16))
