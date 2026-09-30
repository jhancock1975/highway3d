"""Leonhard Euler at sixty-six, as a cartoon: the shapes, and nothing else.

numpy only (through cartoon.sculpt), so it can be meshed inside Blender and
tested outside it.

The design is taken from Emanuel Handmann's 1753 pastel -- the one everybody
knows -- pushed toward a caricature the way a studio would push it:

- the long face, long straight nose and knowing closed-mouth smile
- the right eye narrowed (lost in 1738), the left one blue; both a little
  clouded now, twenty years on (the cataract)
- the floppy satin cap, wound round and sagging to his left, its end
  hanging behind the ear
- the teal banyan -- the dressing gown learned men worked in -- with broad
  dark stripes and a white cravat
- pushed toward a cartoon: the head big against the body, the nose longer,
  the smile deeper, the cap floppier; and twenty years older than the
  pastel, so a softer jaw and a little more under the chin

Head coordinates are local to the head joint (the top of the neck): +z up,
-y forward (the way he faces), +x his left. Metres.
"""

from __future__ import annotations

from cartoon import sculpt as S
import numpy as np

from cartoon.sculpt import Capsule, Ellipsoid, Sphere, Union, Subtract, Paint, Warp, rot

SKIN = (0.64, 0.33, 0.22)
ROSY = (0.70, 0.26, 0.17)
LIP = (0.50, 0.19, 0.15)
MOUTH = (0.22, 0.04, 0.05)
BROW = (0.20, 0.16, 0.13)
HAIR = (0.26, 0.22, 0.19)
NOSE = (0.68, 0.30, 0.20)

HEAD_JOINT = (0.0, -0.02, 1.07)

EYE_R = 0.025
EYE_L_POS = (0.044, -0.080, 0.042)     # his left eye (+x)
EYE_SOCKET = EYE_R + 0.0045
EYE_TILT = 3.0

MOUTH_C = (0.0, -0.119, -0.056)
MOUTH_HALF_W = 0.031
JAW_PIVOT = (0.0, 0.0, 0.0)


SMILE_LIFT = 0.0075


def smile(P):
    """The corners lifted, the left a touch more: the portrait's smirk."""
    mx = MOUTH_C[0]
    o = np.zeros_like(P)
    u = np.clip((P[:, 0] - mx) / MOUTH_HALF_W, -1.3, 1.3)
    o[:, 2] = SMILE_LIFT * u * u + 0.0012 * u
    o[:, 1] = 0.004 * u * u          # corners tuck back into the cheeks
    return o


def lips():
    mx, my, mz = MOUTH_C
    up = Warp(Ellipsoid((mx, my - 0.003, mz + 0.0095), (0.034, 0.012, 0.0085),
                        color=LIP, label="lip_upper"), smile)
    lo = Warp(Ellipsoid((mx, my - 0.001, mz - 0.0105), (0.029, 0.013, 0.0105),
                        color=LIP, label="lip_lower"), smile)
    return up, lo


# face landmarks for the rig (head-local)
CHEEKS = [(0.057, -0.09, 0.012), (-0.057, -0.09, 0.012)]
BROW_L = (0.05, -0.1, 0.086)
BROW_R = (-0.05, -0.1, 0.086)
BROW_INNER_L = (0.018, -0.104, 0.08)
BROW_INNER_R = (-0.018, -0.104, 0.08)


def head():
    """The head surface, mouth open a little (the rig closes it)."""
    mx, my, mz = MOUTH_C
    lip_up, lip_lo = lips()

    parts = [
        Ellipsoid((0, 0.012, 0.07), (0.098, 0.11, 0.112), color=SKIN, label="skull"),
        # a long oval face
        Ellipsoid((0, -0.015, -0.03), (0.09, 0.088, 0.108), color=SKIN, label="face"),
        # cheekbones and the pads either side of the smile
        S.blend(Ellipsoid((0.057, -0.072, 0.012), (0.04, 0.034, 0.03), color=ROSY,
                          label="cheek", mirror=True), 0.025),
        S.blend(Ellipsoid((0.039, -0.094, -0.036), (0.026, 0.027, 0.027), color=SKIN,
                          label="cheek_pad", mirror=True), 0.02),
        # jowls, softened by twenty years; a chin with a little under it
        S.blend(Ellipsoid((0.052, -0.04, -0.08), (0.04, 0.046, 0.044), color=SKIN,
                          label="jowl", mirror=True), 0.03),
        S.blend(Ellipsoid((0, -0.088, -0.108), (0.037, 0.032, 0.028), color=SKIN,
                          label="chin"), 0.02),
        S.blend(Ellipsoid((0, -0.045, -0.128), (0.058, 0.055, 0.024), color=SKIN,
                          label="chin2"), 0.025),
        S.blend(Ellipsoid((0, -0.093, -0.058), (0.045, 0.036, 0.034), color=SKIN,
                          label="muzzle"), 0.025),
        # brow ridge, and the little furrow of concentration above the nose
        S.blend(Ellipsoid((0, -0.074, 0.083), (0.086, 0.028, 0.024), color=SKIN,
                          label="brow"), 0.028),
        # bags under the eyes
        S.blend(Ellipsoid((0.044, -0.096, 0.012), (0.021, 0.009, 0.007), R=rot(0, 8, 0),
                          color=SKIN, label="bag", mirror=True), 0.009),
        # the nose: long and straight, a firm tip, the wings
        S.blend(Capsule((0, -0.096, 0.072), (0, -0.146, 0.0), 0.0105, 0.0165,
                        color=SKIN, label="nose"), 0.014),
        S.blend(Sphere((0, -0.151, -0.005), 0.021, color=NOSE, label="nose"), 0.012),
        S.blend(Ellipsoid((0.019, -0.13, -0.012), (0.014, 0.015, 0.012), color=NOSE,
                          label="nose", mirror=True), 0.009),
        # ears
        S.blend(Ellipsoid((0.099, 0.004, 0.012), (0.017, 0.03, 0.045), R=rot(0, -10, -14),
                          color=NOSE, label="ear", mirror=True), 0.01),
        # lips: closed and smiling
        S.blend(lip_up, 0.006),
        S.blend(lip_lo, 0.006),
    ]
    face = Union(parts, k=0.02)

    # brows: arched, raised, brown going grey; half the expression
    brows = S.Union([
        Ellipsoid((0.042, -0.1, 0.087), (0.03, 0.01, 0.0075), R=rot(0, 14, 6),
                  color=BROW, label="brows", mirror=True),
        Ellipsoid((0.07, -0.088, 0.082), (0.019, 0.01, 0.0065), R=rot(0, -26, 14),
                  color=BROW, label="brows", mirror=True),
    ], k=0.01)
    brows = S.Displace(brows, lambda P: 0.0011 * S.fbm(P, 0.004, 2, seed=3))
    face = Union([face, S.blend(brows, 0.004)], k=0.004)

    # smile lines, deep: he smiles a great deal
    for sx in (1, -1):
        crease = Warp(Capsule((sx * 0.026, -0.131, -0.012), (sx * 0.044, -0.116, -0.072),
                              0.0021, 0.0015, color=SKIN, label="crease"),
                      lambda P, sx=sx: np.stack([sx * 0.004 * np.sin((P[:, 2] + 0.012) * 40),
                                                 0 * P[:, 0], 0 * P[:, 0]], 1))
        face = Subtract(face, crease, k=0.006, color_cut=False)
    # crow's feet
    for sx in (1, -1):
        for i, dz in enumerate((-0.006, 0.002, 0.01)):
            cf = Capsule((sx * 0.072, -0.07, 0.042 + dz), (sx * 0.084, -0.058, 0.04 + dz * 1.6),
                         0.0011, 0.0008, color=SKIN, label="crease")
            face = Subtract(face, cf, k=0.003, color_cut=False)

    nost = Ellipsoid((0.011, -0.155, -0.021), (0.0055, 0.0075, 0.004), R=rot(-25, 0, 20),
                     color=(0.3, 0.1, 0.08), label="nostril", mirror=True)
    face = Subtract(face, nost, k=0.0035)

    sock = Sphere(EYE_L_POS, EYE_SOCKET, color=SKIN, label="socket", mirror=True)
    face = Subtract(face, sock, k=0.006, color_cut=False)

    slot = Warp(Ellipsoid((mx, my + 0.016, mz), (MOUTH_HALF_W + 0.002, 0.03, 0.0034),
                          color=MOUTH, label="mouth"), smile)
    bag = Ellipsoid((mx, my + 0.042, mz - 0.004), (0.027, 0.028, 0.02), color=MOUTH, label="mouth")
    face = Subtract(face, Union([slot, bag], k=0.011), k=0.003)

    spots = S.Displace(Sphere((0.08, -0.05, 0.085), 0.02, mirror=True),
                       lambda P: 0.014 * S.value_noise(P, 0.004, 9))
    face = Paint(face, spots, (0.55, 0.27, 0.17), soft=0.004)
    return face


HEAD_BOUNDS = ((-0.14, -0.19, -0.17), (0.14, 0.14, 0.2))

TOOTH = (0.86, 0.82, 0.72)
GUM = (0.55, 0.18, 0.17)
TONGUE = (0.62, 0.2, 0.2)


def teeth(upper=True):
    """A row of small rounded teeth on an arc behind the lips. He is
    sixty-six in 1773: one is missing on the lower row."""
    import math
    mx, my, mz = MOUTH_C
    parts = []
    n = 8
    rad = 0.026
    cy = my + 0.012 + rad
    zc = mz + (0.0032 if upper else -0.0042)
    for i in range(n):
        a = math.radians(-58 + 116 * (i + 0.5) / n)
        if not upper and i == 5:
            continue
        x, y = mx + rad * math.sin(a), cy - rad * math.cos(a)
        w = 0.0042 if abs(i - (n - 1) / 2) < 1.2 else 0.0036
        parts.append(S.RoundBox((x, y, zc), (w, 0.0028, 0.0042), 0.0016,
                                R=rot(0, 0, math.degrees(a)), color=TOOTH, label="tooth"))
    gum = S.Torus((mx, cy, zc + (0.004 if upper else -0.004)), rad, 0.0035,
                  color=GUM, label="gum")
    return Union(parts + [S.blend(gum, 0.002)], k=0.0015)


def tongue():
    mx, my, mz = MOUTH_C
    return Ellipsoid((mx, my + 0.04, mz - 0.011), (0.02, 0.028, 0.008), color=TONGUE, label="tongue")


TEETH_BOUNDS = ((-0.05, -0.15, -0.09), (0.05, -0.05, -0.02))


def hair():
    """Brown-grey hair below the cap: a shell that hugs the skull behind the
    ears and round the nape, cut into rounded locks by |sin| grooves (sharp
    valleys between soft locks, as with the satin), with a wavy lower edge
    where it curls against the collar."""
    shell = Ellipsoid((0, 0.016, 0.055), (0.106, 0.118, 0.112), color=HAIR, label="hair")
    over_ears = Ellipsoid((0.086, 0.0, 0.035), (0.03, 0.05, 0.05), color=HAIR,
                          label="hair", mirror=True)
    mass = Union([shell, over_ears], k=0.02)

    def locks(P):
        ang = np.arctan2(P[:, 0], P[:, 1])
        w = np.sin(ang * 22 + 25 * P[:, 2] + 0.7 * S.value_noise(P, 0.03, 7))
        return 0.0022 * (np.abs(w) - 0.6) + 0.0008 * S.fbm(P, 0.015, 2, seed=8)
    mass = S.Displace(mass, locks)

    # only a band: below the cap, above the collar, behind the face
    def lower(P):
        ang = np.arctan2(P[:, 0], P[:, 1])
        return -0.012 * np.abs(np.sin(ang * 11))       # curls at the bottom edge
    below = Warp(S.RoundBox((0, 0.0, -0.12), (0.2, 0.2, 0.09), 0.01), lambda P: np.stack(
        [0 * P[:, 0], 0 * P[:, 0], -lower(P)], 1))
    mass = Subtract(mass, below, k=0.012, color_cut=False)
    front = S.RoundBox((0, -0.13, 0.0), (0.2, 0.105, 0.3), 0.01, R=rot(0, 0, 0))
    mass = Subtract(mass, front, k=0.015, color_cut=False)
    ear = Ellipsoid((0.099, 0.004, 0.012), (0.022, 0.034, 0.049), R=rot(0, -10, -14), mirror=True)
    return Subtract(mass, ear, k=0.006, color_cut=False)


HAIR_BOUNDS = ((-0.14, -0.1, -0.12), (0.14, 0.16, 0.16))

CAP = (0.40, 0.41, 0.43)
CAP2 = (0.30, 0.32, 0.36)


def cap():
    """The floppy satin cap: wound round the brow, a loose crown sagging to
    his left, its end hanging down behind the left ear."""
    band = S.Torus((0, 0.006, 0.098), 0.103, 0.017, R=rot(-14, 4, 0), color=CAP2, label="cap")
    band2 = S.Torus((0.004, 0.01, 0.118), 0.103, 0.017, R=rot(-6, -6, 0), color=CAP, label="cap")
    crown = Ellipsoid((0.028, 0.018, 0.158), (0.122, 0.118, 0.07), R=rot(0, 16, 0),
                      color=CAP, label="cap")
    droop = Ellipsoid((0.105, 0.03, 0.12), (0.05, 0.085, 0.05), R=rot(0, 35, 0),
                      color=CAP, label="cap")
    # the hanging end, a flattened ribbon
    tail = Union([
        Ellipsoid((0.107, 0.045, 0.07), (0.016, 0.03, 0.05), R=rot(8, 12, 0), color=CAP2, label="cap"),
        Ellipsoid((0.114, 0.055, 0.0), (0.013, 0.027, 0.045), R=rot(14, 6, 0), color=CAP2, label="cap"),
    ], k=0.02)
    # a lining that covers the whole skull, so nothing shows between band
    # and crown whichever way the crown sags
    lining = Ellipsoid((0, 0.013, 0.083), (0.104, 0.116, 0.118), color=CAP2, label="cap")
    c = Union([lining, band, S.blend(band2, 0.006), crown, droop, tail], k=0.018)

    def folds(P):
        # satin creases: sharp valleys, soft ridges, wound round the head
        ang = np.arctan2(P[:, 0] - 0.02, -P[:, 1])
        w = np.sin(ang * 4 + P[:, 2] * 38 + 0.8 * S.value_noise(P, 0.06, 5))
        return 0.004 * (np.abs(w) - 0.6) + 0.0005 * S.fbm(P, 0.03, 2, seed=11)
    c = S.Displace(c, folds)
    # but never down over the face
    cut = S.RoundBox((0, -0.12, -0.03), (0.2, 0.1, 0.1), 0.02, R=rot(-16, 0, 0))
    return Subtract(c, cut, k=0.01, color_cut=False)


CAP_BOUNDS = ((-0.15, -0.15, -0.06), (0.19, 0.17, 0.26))


# ------------------------------------------------------------------ body
#
# Body coordinates: origin on the floor under the middle of the seat, +z up,
# -y the way he faces. He is built sitting, because he never stands up in
# this film, and a figure sculpted in the pose it spends its life in has no
# knees or hips to fold badly.

ROBE = (0.035, 0.20, 0.25)          # the portrait's teal-blue silk
STRIPE = (0.045, 0.075, 0.095)      # the dark slate stripes
TRIM = (0.020, 0.022, 0.026)        # satin edging at the opening and collar
CRAVAT = (0.80, 0.79, 0.76)
STOCKING = (0.62, 0.60, 0.55)
SHOE = (0.025, 0.02, 0.018)
BUCKLE = (0.55, 0.45, 0.25)

SEAT_Z = 0.46

# joints, in body coordinates; the rig is built from these, the sculpt is
# built around them, so the two cannot disagree
J = {
    "hips":       (0.0, 0.03, 0.56),
    "spine":      (0.0, 0.02, 0.70),
    "chest":      (0.0, 0.00, 0.86),
    "neck":       (0.0, -0.005, 0.99),
    "head":       (0.0, -0.01, 1.05),
    "shoulder.L": (0.075, 0.0, 0.965),
    "upper_arm.L": (0.195, 0.01, 0.935),
    "forearm.L":  (0.245, -0.05, 0.715),
    "hand.L":     (0.19, -0.29, 0.665),
    "hand_end.L": (0.18, -0.39, 0.655),
    "thigh.L":    (0.105, -0.01, 0.53),
    "shin.L":     (0.125, -0.40, 0.54),
    "foot.L":     (0.135, -0.43, 0.10),
    "toe.L":      (0.14, -0.55, 0.04),
}
for _k, _v in list(J.items()):
    if _k.endswith(".L"):
        J[_k[:-2] + ".R"] = (-_v[0], _v[1], _v[2])

# where the head sculpt's origin sits in body coordinates: the neck enters
# the head at head-local (0, 0.012, -0.095)
HEAD_ORIGIN = (J["head"][0], J["head"][1] - 0.012, J["head"][2] + 0.095)


def _robe_colour(P):
    """Broad diagonal stripes, as in the portrait, plus the dark edging down
    the front opening."""
    u = P[:, 0] * 0.8 + P[:, 2] * 0.35 + 0.03 * np.sin(P[:, 1] * 20)
    s = np.abs(np.sin(u * np.pi / 0.075))
    # soft-edged, about a third of the width: silk stripes, not a convict's
    return np.clip((s - 0.78) / 0.08, 0.0, 1.0)


def body():
    """The seated figure in the banyan, without head or hands."""
    j = {k: np.array(v) for k, v in J.items()}
    robe = []
    robe += [
        Ellipsoid((0, 0.03, 0.56), (0.19, 0.17, 0.12), color=ROBE, label="robe"),
        Ellipsoid((0, -0.035, 0.70), (0.205, 0.19, 0.19), color=ROBE, label="robe"),   # belly
        Ellipsoid((0, 0.0, 0.86), (0.2, 0.14, 0.15), color=ROBE, label="robe"),        # chest
        Ellipsoid((0.155, 0.01, 0.93), (0.075, 0.075, 0.06), color=ROBE, label="robe", mirror=True),
    ]
    for s in (".L", ".R"):
        # sleeves: wide and soft, widening to a turned-back cuff
        robe.append(Capsule(j["upper_arm" + s], j["forearm" + s], 0.058, 0.052, color=ROBE, label="sleeve"))
        robe.append(Capsule(j["forearm" + s], j["hand" + s] + (j["forearm" + s] - j["hand" + s]) * 0.08,
                            0.052, 0.062, color=ROBE, label="sleeve"))
        # thighs under the skirts of the robe
        robe.append(Capsule(j["thigh" + s], j["shin" + s], 0.092, 0.075, color=ROBE, label="robe"))
    # the skirts falling over the knees and between them
    robe.append(S.blend(RoundBox_((0, -0.3, 0.44), (0.19, 0.12, 0.1), 0.06, color=ROBE, label="robe"), 0.06))
    robe.append(S.blend(Ellipsoid((0, -0.43, 0.36), (0.2, 0.05, 0.14), color=ROBE, label="robe"), 0.05))
    body = Union(robe, k=0.04)
    body = S.PaintFn(body, _robe_colour, STRIPE, label="robe")
    # dark satin edging down the opening and round the cuffs
    edge = lambda P: np.clip(1.0 - np.abs(P[:, 0] - 0.012 * np.sin(P[:, 2] * 8)) / 0.016, 0, 1) \
        * (P[:, 1] < -0.05) * (P[:, 2] > 0.5)
    body = S.PaintFn(body, lambda P: (edge(P) > 0.5).astype(float), TRIM, label="robe")
    for s in (".L", ".R"):
        cuff = Capsule(j["hand" + s] + (j["forearm" + s] - j["hand" + s]) * 0.12,
                       j["hand" + s] + (j["forearm" + s] - j["hand" + s]) * 0.0, 0.07, 0.07)
        body = Paint(body, cuff, TRIM, soft=0.004)

    # shawl collar of the banyan round the neck, dark satin
    collar = S.Torus((0, 0.005, 0.975), 0.088, 0.024, R=rot(-18, 0, 0), color=TRIM, label="collar")
    body = Union([body, S.blend(collar, 0.015)], k=0.015)
    # neck and the cravat's ruffles at the throat
    neck = Capsule((0, 0.0, 0.93), j["head"] + (0, 0.0, 0.03), 0.056, 0.052,
                   color=(0.64, 0.33, 0.22), label="neck")
    cravat = [Ellipsoid((0, -0.07, 0.975), (0.05, 0.04, 0.04), color=CRAVAT, label="cravat")]
    rng = np.random.default_rng(12)
    for i in range(7):
        z = 0.99 - i * 0.022
        cravat.append(Ellipsoid((0.01 * rng.standard_normal(), -0.085 - 0.004 * i, z),
                                (0.036 - 0.002 * i, 0.02, 0.014), R=rot(15 * rng.standard_normal(), 0, 20 * rng.standard_normal()),
                                color=CRAVAT, label="cravat"))
    cr = Union(cravat, k=0.008)
    cr = S.Displace(cr, lambda P: 0.002 * np.sin(P[:, 0] * 180 + P[:, 2] * 90))
    body = Union([body, S.blend(neck, 0.02), S.blend(cr, 0.006)], k=0.02)
    # buttons down the front, as in the portrait
    for i in range(5):
        z = 0.88 - i * 0.075
        yb = -0.14 - 0.06 * np.exp(-((z - 0.7) / 0.1) ** 2) - 0.02
        body = Union([body, S.blend(Sphere((0.025, yb + 0.012, z), 0.011, color=TRIM, label="button"), 0.003)], k=0.003)

    # legs below the robe: stockings and buckled shoes
    legs = []
    for s in (".L", ".R"):
        legs.append(Capsule(j["shin" + s] + (0, -0.02, -0.08), j["foot" + s], 0.05, 0.036,
                            color=STOCKING, label="stocking"))
        sx = 1 if s == ".L" else -1
        legs.append(S.blend(Ellipsoid((sx * 0.138, -0.47, 0.05), (0.048, 0.1, 0.045),
                                      color=SHOE, label="shoe"), 0.02))
        legs.append(S.blend(S.RoundBox((sx * 0.14, -0.52, 0.085), (0.025, 0.006, 0.018), 0.004,
                                       R=rot(-30, 0, 0), color=BUCKLE, label="buckle"), 0.002))
        legs.append(S.blend(Ellipsoid((sx * 0.137, -0.44, 0.012), (0.05, 0.11, 0.014),
                                      color=(0.05, 0.035, 0.03), label="shoe"), 0.01))   # sole & heel
    body = Union([body] + legs, k=0.025)
    return body


def RoundBox_(center, half, r, **kw):
    return S.RoundBox(center, half, r, **kw)


BODY_BOUNDS = ((-0.36, -0.64, -0.02), (0.36, 0.26, 1.12))


# ------------------------------------------------------------------ hands
#
# A left hand in hand-local coordinates: the wrist joint at the origin, the
# fingers reaching along -y (forward, the way the forearm rests), the palm
# facing -z (down), the thumb toward -x (the body's midline). The right hand
# is its mirror. Five fingers: he is a person, not a mouse.

FINGERS = {
    #          knuckle (x, y, z)          length  radius
    "index":  ((-0.024, -0.082, 0.004), 0.072, 0.0102),
    "middle": ((-0.007, -0.088, 0.005), 0.080, 0.0105),
    "ring":   ((0.010, -0.085, 0.004), 0.074, 0.0100),
    "pinky":  ((0.025, -0.077, 0.001), 0.058, 0.0090),
}
THUMB = ((-0.032, -0.03, -0.006), (-0.052, -0.07, -0.012), (-0.056, -0.098, -0.014), 0.0115)
REST_CURL = 12.0     # degrees per joint in the sculpted pose: relaxed, not flat


def finger_points(knuckle, length, curl_deg=REST_CURL, splay=0.0):
    """Three joints and a tip for a finger curling down (toward -z)."""
    import math
    k = np.array(knuckle, float)
    segs = (0.45, 0.32, 0.23)
    pts = [k]
    ang = 0.0
    for sfrac in segs:
        ang += math.radians(curl_deg)
        d = np.array([math.sin(math.radians(splay)) * math.cos(ang),
                      -math.cos(math.radians(splay)) * math.cos(ang), -math.sin(ang)])
        pts.append(pts[-1] + d * length * sfrac)
    return pts


def hand():
    palm = Union([
        S.RoundBox((0.0, -0.045, 0.0), (0.036, 0.045, 0.014), 0.012, color=SKIN, label="palm"),
        Ellipsoid((-0.02, -0.035, -0.008), (0.022, 0.03, 0.016), color=SKIN, label="palm"),   # thumb pad
        Capsule((0, 0.02, 0.0), (0, -0.01, 0.0), 0.024, 0.028, color=SKIN, label="wrist"),
    ], k=0.015)
    parts = [palm]
    for name, (kn, ln, r) in FINGERS.items():
        splay = {"index": -4, "middle": 0, "ring": 4, "pinky": 9}[name]
        pts = finger_points(kn, ln, REST_CURL, splay)
        radii = [r * 1.05, r, r * 0.93, r * 0.8]
        parts.append(S.blend(S.Tube(pts, radii, color=SKIN, label=name), 0.008))
        # knuckle shading
    t0, t1, t2, tr = THUMB
    parts.append(S.blend(S.Tube([t0, t1, t2], [tr * 1.25, tr, tr * 0.85], color=SKIN, label="thumb"), 0.012))
    h = Union(parts, k=0.008)
    # fingernails: a touch pinker and glossier where the nail is
    for name, (kn, ln, r) in FINGERS.items():
        splay = {"index": -4, "middle": 0, "ring": 4, "pinky": 9}[name]
        tip = finger_points(kn, ln, REST_CURL, splay)[-1]
        nail = Ellipsoid(tip + np.array([0, 0.004, r * 0.75]), (r * 0.7, r * 1.1, r * 0.5))
        h = Paint(h, nail, (0.72, 0.42, 0.34), soft=0.002)   # keeps its finger's label, so it bends with it
    return h


HAND_BOUNDS = ((-0.085, -0.19, -0.06), (0.06, 0.05, 0.04))
