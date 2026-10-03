"""A cartoon face rig computed from where the mouth and brows are.

Nobody paints weights or sculpts shape keys here: every one is a smooth
function of position around the landmarks the character's shape module
declares (mouth centre and width, jaw pivot, brow and cheek positions).
That is what lets a new character get a working face from its sculpt alone.

The mouth is sculpted a little open, with a slot through the lips into a
cavity. At rest `lips_close` brings the lips together; speech opens them
with the jaw bone and reshapes them with the rest of the keys:

  mouth_wide / mouth_narrow   corners out and back / lips pushed forward and in
  smile / frown               corners up and back / corners down
  upper_up / lower_down       show the upper / lower teeth
  lips_close / lips_press     lips meeting / pressed (m, b, p)
  lower_in                    lower lip up under the upper teeth (f, v)
  brow_up.L/R, brow_down.L/R, brow_inner  the brows
  cheek_up.L/R                the squint that comes with a real smile
"""

from __future__ import annotations

import math

import numpy as np

from cartoon.bl import common as C


def _ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _gauss(P, c, sig):
    d = P - np.asarray(c)
    if np.ndim(sig) == 0:
        return np.exp(-np.sum(d * d, 1) / (sig * sig))
    return np.exp(-np.sum((d / np.asarray(sig)) ** 2, 1))


def jaw_weights(P, mouth_c, half_w, smile_lift=0.0075, back_y=0.03, reach=None, radius=None):
    """How much of each vertex goes with the jaw.

    Sharp inside the mouth, where the split runs through the slot and so
    through empty space; soft beyond the corners, where it runs through
    cheek and has to stretch like cheek.
    """
    mx, my, mz = mouth_c
    u = np.clip((P[:, 0] - mx) / half_w, -1.4, 1.4)
    v = P[:, 2] - (mz + smile_lift * u * u)
    lat = np.maximum(0.0, np.abs(P[:, 0] - mx) - half_w * 0.95)
    band = 0.0012 + 0.55 * lat + 0.25 * np.maximum(0.0, (my - 0.01) - P[:, 1]) * 0
    w = _ss(-1.0, 1.0, -v / band)
    # the back of the head does not open
    w *= _ss(back_y, back_y - 0.05, P[:, 1])
    if reach is not None:
        # a creature that is all face below the mouth: the jaw is only the
        # muzzle, not the belly under it
        w *= _ss(-reach, -reach * 0.25, v)
        w *= _ss(half_w * 1.9, half_w * 1.2, np.abs(P[:, 0] - mx))
    if radius is not None:
        # or a soft round region round the lower lip: straight cut-offs at
        # the sides and below showed as edges -- a pale bib swinging down the
        # chest every time the mouth opened
        lo = np.array([mx, my, mz - 0.012])
        w *= _ss(radius, radius * 0.35, np.linalg.norm(P - lo, axis=1))
    return w


def mouth_keys(P, mouth_c, half_w, lip_upper, lip_lower, cheeks, smile_lift=0.0075):
    """Displacements (N,3) per shape key name, all in head-local metres.

    lip_upper / lip_lower are sculpt nodes (their distance fields weight the
    lips); cheeks is a list of cheek centres.
    """
    mx, my, mz = mouth_c
    rel = P - np.array(mouth_c)
    u = np.clip(rel[:, 0] / half_w, -1.6, 1.6)
    v = P[:, 2] - (mz + smile_lift * u * u)
    front = _ss(0.05, -0.01, rel[:, 1])                 # front of the face only
    near = _gauss(P, mouth_c, (half_w * 1.6, 0.05, 0.035)) * front
    wide_field = _gauss(P, mouth_c, (half_w * 2.2, 0.06, 0.05)) * front
    du = np.maximum(lip_upper.dist(P), 0.0)
    dl = np.maximum(lip_lower.dist(P), 0.0)
    w_up = np.exp(-(du / 0.007) ** 2) * front * (v > -0.002)
    w_lo = np.exp(-(dl / 0.007) ** 2) * front * (v < 0.002)
    corner = _ss(0.35, 1.0, np.abs(u)) * _gauss(P, mouth_c, (half_w * 1.9, 0.05, 0.03)) * front
    Z = np.zeros_like(P)
    K = {}

    d = Z.copy()
    d[:, 0] = 0.010 * u * wide_field * (1 - 0.3 * np.abs(u) / 1.6)
    d[:, 1] = 0.004 * np.abs(u) * wide_field
    K["mouth_wide"] = d

    d = Z.copy()
    d[:, 0] = -0.011 * np.clip(u, -1.2, 1.2) * near
    d[:, 1] = -0.009 * np.maximum(w_up, w_lo) - 0.004 * near
    d[:, 2] = 0.002 * np.sign(-v) * near * 0
    K["mouth_narrow"] = d

    d = Z.copy()
    d[:, 2] = 0.013 * corner
    d[:, 1] = 0.006 * corner
    d[:, 0] = 0.006 * np.sign(u) * corner
    for c in cheeks:
        g = _gauss(P, c, 0.03) * front
        d[:, 2] += 0.007 * g
        d[:, 1] += -0.002 * g
    K["smile"] = d

    d = Z.copy()
    d[:, 2] = -0.009 * corner
    d[:, 1] = 0.002 * corner
    K["frown"] = d

    d = Z.copy()
    d[:, 2] = 0.0045 * w_up
    d[:, 1] = -0.0015 * w_up
    K["upper_up"] = d

    d = Z.copy()
    d[:, 2] = -0.005 * w_lo
    d[:, 1] = -0.002 * w_lo
    K["lower_down"] = d

    # the slot is ~7 mm tall at the lips: each lip travels half of it
    close = 0.0036
    d = Z.copy()
    d[:, 2] = -close * w_up + close * w_lo
    K["lips_close"] = d

    d = Z.copy()
    d[:, 2] = -0.0012 * w_up + 0.0012 * w_lo
    d[:, 1] = 0.0025 * (w_up + w_lo)            # rolled in, pressed
    K["lips_press"] = d

    d = Z.copy()
    d[:, 2] = 0.006 * w_lo
    d[:, 1] = 0.004 * w_lo
    K["lower_in"] = d
    return K


def open_key(P, mouth_c, half_w, smile_lift=0.0075, drop=0.02, sigma=0.04):
    """Open the mouth by lowering the lower lip and chin, not by hinging a jaw.

    For a creature whose face is all muzzle, a jaw bone turning about a pivot
    behind the face swings the chin *back* into the body as it opens: a
    sunken pouch with a sharp U-shaped rim under the mouth. This moves the
    lower half straight down (and a hair forward), fading as a Gaussian in
    every direction, so there is nothing to fold. The split between the lips
    is sharp only inside the mouth, where it runs through empty space.
    """
    mx, my, mz = mouth_c
    u = np.clip((P[:, 0] - mx) / half_w, -1.4, 1.4)
    v = P[:, 2] - (mz + smile_lift * u * u)
    lat = np.maximum(0.0, np.abs(P[:, 0] - mx) - half_w * 0.95)
    band = 0.0012 + 0.6 * lat
    # sharp between the lips; but anything clearly below the mouth line is
    # simply "lower", whatever its x -- otherwise a mouth-wide column moved
    # with hard side edges and showed as a pale strip down the chest
    lower = np.maximum(_ss(-1.0, 1.0, -v / band), _ss(-0.003, -0.018, v))
    lo = np.array([mx, my, mz - 0.01])
    g = np.exp(-np.sum(((P - lo) / np.array((sigma * 1.4, sigma * 1.6, sigma))) ** 2, 1))
    w = lower * g
    d = np.zeros_like(P)
    d[:, 2] = -drop * w
    d[:, 1] = -0.003 * w
    return {"mouth_open": d}


def brow_keys(P, brow_l, brow_r, cheek_l, cheek_r, inner_l, inner_r, sig=0.03):
    """Brow and cheek keys. brow_* are brow centres; inner_* the inner ends."""
    K = {}
    front = _ss(0.05, -0.02, P[:, 1])
    for side, bc, cc, ic in (("L", brow_l, cheek_l, inner_l), ("R", brow_r, cheek_r, inner_r)):
        g = _gauss(P, bc, (sig * 1.3, 0.04, sig)) * front
        d = np.zeros_like(P)
        d[:, 2] = 0.014 * g
        d[:, 1] = -0.003 * g
        K[f"brow_up.{side}"] = d
        gi = _gauss(P, ic, (sig * 0.8, 0.04, sig * 0.9)) * front
        d = np.zeros_like(P)
        d[:, 2] = -0.008 * g - 0.006 * gi
        d[:, 0] = -np.sign(bc[0]) * 0.006 * gi
        d[:, 1] = -0.004 * gi
        K[f"brow_down.{side}"] = d
        g = _gauss(P, cc, 0.028) * front
        d = np.zeros_like(P)
        d[:, 2] = 0.006 * g
        d[:, 1] = -0.002 * g
        K[f"cheek_up.{side}"] = d
    gi = (_gauss(P, inner_l, (0.022, 0.04, 0.025)) + _gauss(P, inner_r, (0.022, 0.04, 0.025))) * front
    d = np.zeros_like(P)
    d[:, 2] = 0.012 * gi
    K["brow_inner"] = d
    return K


def add_keys(ob, keys: dict, local_offset=(0, 0, 0)):
    for name, disp in keys.items():
        C.add_shape_key(ob, name, disp)
    C.log(f"{ob.name}: shape keys {', '.join(keys)}")
