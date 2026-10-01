"""Cinnamon: an alien who does mathematics by smell and taste. The shapes.

numpy only, through cartoon.sculpt.

Euler names it after what it smells of, so it is the colour of the spice:
warm cinnamon-brown with a cream belly, freckled, and -- because it is a
cartoon -- a cinnamon-roll swirl on its back. Everything else follows from
how it thinks:

- no eyes at all. It has never needed them: the nose, far too big for its
  face, with nostrils that flare, is how it finds its way, and the feathery
  antennae, glowing at the tips when it smells, are how it looks round. So
  when it tells a blind man "neither have I", it means it
- a wide frog's mouth, because the tongue that lives in it is long enough
  to lick a slate from across a desk
- brows on a soft ridge where eyes would be: with no eyes, the brows, the
  nose, the antennae and the mouth carry every expression
- a round bean of a body that floats, squashes and stretches, with stubby
  three-fingered arms and little feet that never quite touch anything

Local coordinates: origin at the body's centre, +z up, -y the way it faces.
"""

from __future__ import annotations

import math

import numpy as np

from cartoon import sculpt as S
from cartoon.sculpt import Capsule, Ellipsoid, Sphere, Union, Subtract, Paint, Warp, rot

BODY = (0.46, 0.16, 0.055)       # cinnamon
BELLY = (0.72, 0.48, 0.26)       # cream
FRECKLE = (0.26, 0.07, 0.025)
SWIRL = (0.30, 0.085, 0.03)
NOSE = (0.72, 0.22, 0.26)        # a warm rosy pink
LIP = (0.40, 0.10, 0.06)
MOUTH = (0.22, 0.03, 0.06)
BLUSH = (0.66, 0.18, 0.12)
BROW = (0.12, 0.03, 0.012)
ANTENNA = (0.72, 0.42, 0.14)
GLOW = (0.45, 0.3, 1.0)           # lavender, at the antenna tips


MOUTH_C = (0.0, -0.163, -0.014)
MOUTH_HALF_W = 0.066
SMILE_LIFT = 0.012
JAW_PIVOT = (0.0, -0.02, 0.0)

CHEEKS = [(0.088, -0.118, 0.05), (-0.088, -0.118, 0.05)]
BROW_L = (0.058, -0.128, 0.158)
BROW_R = (-0.058, -0.128, 0.158)
BROW_INNER_L = (0.028, -0.134, 0.152)
BROW_INNER_R = (-0.028, -0.134, 0.152)

NOSE_C = (0.0, -0.168, 0.078)
NOSTRIL_L = (0.02, -0.19, 0.064)


def smile(P):
    mx = MOUTH_C[0]
    o = np.zeros_like(P)
    u = np.clip((P[:, 0] - mx) / MOUTH_HALF_W, -1.3, 1.3)
    o[:, 2] = SMILE_LIFT * u * u
    o[:, 1] = 0.02 * u * u          # the corners wrap round the face
    return o


def lips():
    mx, my, mz = MOUTH_C
    up = Warp(Ellipsoid((mx, my - 0.002, mz + 0.008), (0.07, 0.012, 0.008), color=LIP,
                        label="lip_upper"), smile)
    lo = Warp(Ellipsoid((mx, my - 0.001, mz - 0.009), (0.064, 0.013, 0.009), color=LIP,
                        label="lip_lower"), smile)
    return up, lo


def body():
    """Everything but the antennae and the tongue. (It has no eyes.)"""
    mx, my, mz = MOUTH_C
    lip_up, lip_lo = lips()
    parts = [
        # the bean: a big round head melting into a rounder belly
        Ellipsoid((0, 0.0, 0.1), (0.15, 0.135, 0.14), color=BODY, label="skin"),
        Ellipsoid((0, -0.01, -0.06), (0.165, 0.15, 0.15), color=BODY, label="skin"),
        S.blend(Ellipsoid((0, -0.02, -0.17), (0.1, 0.09, 0.06), color=BODY, label="skin"), 0.06),
        # cheeks, full and blushing
        S.blend(Ellipsoid((0.085, -0.1, 0.045), (0.05, 0.045, 0.04), color=BLUSH,
                          label="cheek", mirror=True), 0.035),
        # a muzzle for the wide mouth
        S.blend(Ellipsoid((0, -0.128, -0.016), (0.094, 0.052, 0.048), color=BODY, label="muzzle"), 0.04),
        # a soft ridge where eyes would be, and the brows on it: with no
        # eyes they carry the expression, so they are bigger and bolder
        S.blend(Ellipsoid((0, -0.1, 0.145), (0.1, 0.035, 0.04), color=BODY, label="ridge"), 0.04),
        S.blend(Ellipsoid((0.058, -0.139, 0.158), (0.043, 0.019, 0.015), R=rot(0, -14, 8),
                          color=BROW, label="brows", mirror=True), 0.007),
        # the nose: the most important thing on it
        S.blend(Capsule((0, -0.122, 0.13), (0, -0.162, 0.09), 0.017, 0.028, color=NOSE, label="nose"), 0.02),
        S.blend(Sphere(NOSE_C, 0.04, color=NOSE, label="nose"), 0.015),
        S.blend(Ellipsoid((0.033, -0.163, 0.062), (0.022, 0.022, 0.018), color=NOSE,
                          label="nose", mirror=True), 0.012),
        S.blend(lip_up, 0.006),
        S.blend(lip_lo, 0.006),
    ]
    for s in (1, -1):
        # stubby arms, reaching forward a little, three fat fingers each
        sh = np.array((s * 0.14, -0.02, -0.02))
        el = np.array((s * 0.19, -0.06, -0.08))
        wr = np.array((s * 0.2, -0.12, -0.11))
        parts.append(S.blend(Capsule(sh, el, 0.034, 0.028, color=BODY, label="arm"), 0.03))
        parts.append(S.blend(Capsule(el, wr, 0.028, 0.026, color=BODY, label="arm"), 0.015))
        parts.append(S.blend(Sphere(wr + np.array((0, -0.012, -0.004)), 0.03, color=BODY, label="hand"), 0.012))
        for name, (dx, dz) in FINGER_OFFSETS.items():
            pts = finger_points(s, name)
            parts.append(S.blend(S.Tube(pts, [0.0125, 0.0115, 0.0095], color=BODY, label=f"{name}"), 0.008))
        # little feet
        parts.append(S.blend(Ellipsoid((s * 0.065, -0.05, -0.205), (0.04, 0.05, 0.03),
                                       color=BODY, label="foot"), 0.03))
    b = Union(parts, k=0.03)

    # cream belly and face-front
    belly = Ellipsoid((0, -0.13, -0.1), (0.11, 0.08, 0.11))
    b = Paint(b, belly, BELLY, soft=0.02, label="belly")
    # freckles over the cheeks and nose bridge, and all down the back
    fr = lambda P: np.clip((S.value_noise(P, 0.0055, 31) - 0.7) / 0.05, 0, 1) * (
        (np.abs(P[:, 0]) > 0.05) * (P[:, 1] < -0.08) * (np.abs(P[:, 2] - 0.08) < 0.05)
        + (P[:, 1] > 0.04) * 1.0)
    b = S.PaintFn(b, fr, FRECKLE)
    # the cinnamon-roll swirl on its back
    def swirl(P):
        x, z = P[:, 0], P[:, 2] - 0.0
        r = np.sqrt(x * x + z * z)
        th = np.arctan2(z, x)
        arm_ = np.sin(2 * np.pi * r / 0.035 - th)
        return np.clip((arm_ - 0.55) / 0.2, 0, 1) * (P[:, 1] > 0.05) * (r < 0.13)
    b = S.PaintFn(b, swirl, SWIRL)

    # nostrils: big, and they flare
    nost = Ellipsoid(NOSTRIL_L, (0.011, 0.014, 0.008), R=rot(-30, 0, 25),
                     color=(0.25, 0.05, 0.06), label="nostril", mirror=True)
    b = Subtract(b, nost, k=0.005)
    slot = Warp(Ellipsoid((mx, my + 0.02, mz), (MOUTH_HALF_W + 0.003, 0.04, 0.0038),
                          color=MOUTH, label="mouth"), smile)
    bag = Ellipsoid((mx, my + 0.06, mz - 0.01), (0.055, 0.045, 0.03), color=MOUTH, label="mouth")
    b = Subtract(b, Union([slot, bag], k=0.015), k=0.0035)
    return b


BODY_BOUNDS = ((-0.28, -0.26, -0.26), (0.28, 0.2, 0.3))

# fingers: offsets from the hand ball (x toward the midline, z)
FINGER_OFFSETS = {"f1": (-0.016, 0.006), "f2": (0.0, 0.0), "f3": (0.016, -0.004)}


def finger_points(s, name):
    dx, dz = FINGER_OFFSETS[name]
    wr = np.array((s * 0.2, -0.132, -0.114))
    base = wr + np.array((-s * dx * 1.0, -0.018, dz))
    mid = base + np.array((-s * dx * 0.3, -0.022, -0.006))
    tip = mid + np.array((-s * dx * 0.2, -0.016, -0.012))
    return [base, mid, tip]


def antenna(side=1):
    """A feathery antenna, moth-style: a curved stalk with barbs down both
    sides, and a glowing bead at the tip. Built in its own frame: base at
    the origin, reaching up +z and out +x (mirrored for the right)."""
    pts = antenna_points()
    stalk = S.Tube(pts, [0.009, 0.007, 0.0055, 0.0045, 0.004], color=ANTENNA, label="stalk")
    parts = [stalk]
    # barbs: little flat feathers along both sides, longest in the middle
    n = 16
    for i in range(n):
        t = 0.12 + 0.8 * i / (n - 1)
        p, d = _along(pts, t)
        side_v = np.cross(d, np.array((0, 1, 0)))
        side_v /= np.linalg.norm(side_v) + 1e-9
        ln = 0.022 * math.sin(math.pi * (t - 0.05)) + 0.006
        for sgn in (1, -1):
            c = p + side_v * sgn * ln * 0.55 + d * 0.004
            parts.append(Ellipsoid(c, (ln * 0.55, 0.0025, 0.0045),
                                   R=_frame(side_v * sgn, d), color=ANTENNA, label="barb"))
    parts.append(S.blend(Sphere(pts[-1] + np.array((0.004, 0, 0.008)), 0.014, color=GLOW, label="tip"), 0.004))
    return Union(parts, k=0.003)


def antenna_points():
    return [np.array(p, float) for p in
            ((0, 0, 0), (0.012, 0, 0.05), (0.035, -0.006, 0.1), (0.07, -0.014, 0.14), (0.11, -0.02, 0.16))]


ANTENNA_BOUNDS = ((-0.05, -0.06, -0.03), (0.16, 0.04, 0.2))
ANTENNA_BASE_L = (0.052, -0.012, 0.225)


def _along(pts, t):
    seg = np.array([np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1)])
    L = seg.sum()
    s = t * L
    for i, l in enumerate(seg):
        if s <= l or i == len(seg) - 1:
            f = s / l
            d = (pts[i + 1] - pts[i]) / l
            return pts[i] + (pts[i + 1] - pts[i]) * f, d
        s -= l


def _frame(xv, zv):
    """Rotation whose local x is xv and local z is (roughly) zv."""
    x = xv / np.linalg.norm(xv)
    z = zv - x * (zv @ x)
    z /= np.linalg.norm(z) + 1e-9
    y = np.cross(z, x)
    return np.stack([x, y, z], 1)


# the joints the rig is built from
J = {
    "root": (0.0, 0.0, -0.2),
    "body": (0.0, 0.0, -0.06),
    "head": (0.0, 0.0, 0.08),
    "head_top": (0.0, 0.0, 0.24),
    "arm.L": (0.14, -0.02, -0.02),
    "forearm.L": (0.19, -0.06, -0.08),
    "hand.L": (0.2, -0.12, -0.11),
    "hand_end.L": (0.2, -0.15, -0.118),
    "foot.L": (0.065, -0.03, -0.18),
    "foot_end.L": (0.065, -0.1, -0.21),
}
for _k, _v in list(J.items()):
    if _k.endswith(".L"):
        J[_k[:-2] + ".R"] = (-_v[0], _v[1], _v[2])
