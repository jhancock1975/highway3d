"""Where a lick is seen from, and how far along its formula the tongue goes.

Pure Python, math only. Three places need the answer and must agree: the
timeline draws the wet streak on the slate before anything is animated,
Blender aims the tongue, and Blender places the camera. Computed in one
place, a streak cannot glisten on chalk the tongue never reached.

Cinnamon licks from out past the slate's left edge, face to face with Euler
at his eye level. The formulas are within his reach, half a metre from his
head, but seen from the audience's side their far ends are behind it -- and
a tongue sweeping on to them read on screen as a tongue running into his
mouth. So the camera swings round to the angle that shows the most chalk and
tongue past both of them, and the tongue stops while its tip is still well
clear of his face on screen.
"""

from __future__ import annotations

import math

from cartoon.sets import marks as MK

LENS = 32.0
HEAD_R = 0.17          # his head with the cap and hair
NOSE_AHEAD, NOSE_R = 0.14, 0.05
CHEST_R = 0.20
CINNAMON_R = 0.23      # its belly and arms, seen from behind
MARGIN = 0.06          # screen tangents between the tip and his face, ~100 px
# His head, as it sits on the head bone (not HEAD_EULER, the point everyone
# looks at, which is 5 cm further forward), and his nose straight ahead of
# it. Checked against the rendered silhouette at mid-lick for all five
# licks: within 0.5-2.7 hundredths of a screen tangent, always on the
# cautious side.
HEAD_CENTRE = (0.0, -0.01, 1.15)


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _add(a, b):
    return [a[i] + b[i] for i in range(3)]


def _mul(a, s):
    return [x * s for x in a]


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a) or 1e-9
    return [x / n for x in a]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _lerp(a, b, t):
    return [a[i] + (b[i] - a[i]) * t for i in range(3)]


def _span(board, kind):
    if kind == "slurp":
        return 0.1, 1.0, 0.5
    u0, u1, v, _ = MK.BOARD_LAYOUT[board]
    return u0, u1, v


def where(board, kind="lick"):
    """Cinnamon's body centre while it licks."""
    p = MK.lick_spot(board or "product")
    return [p[0], p[1], p[2] + 0.05]


class _View:
    def __init__(self, loc, target):
        self.loc = loc
        self.f = _unit(_sub(target, loc))
        self.r = _unit(_cross(self.f, [0.0, 0.0, 1.0]))
        self.u = _cross(self.r, self.f)

    def depth(self, p):
        return _dot(_sub(p, self.loc), self.f)

    def x(self, p):
        return _dot(_sub(p, self.loc), self.r) / self.depth(p)

    def screen(self, p):
        w = _sub(p, self.loc)
        z = _dot(w, self.f)
        return _dot(w, self.r) / z, _dot(w, self.u) / z


def _blocked(loc, p, a, b, r):
    """Does the sight line loc -> p pass within r of segment ab?"""
    w = _sub(p, loc)
    ww = _dot(w, w)
    for k in range(10):
        q = _lerp(a, b, k / 9)
        s = min(0.98, max(0.0, _dot(_sub(q, loc), w) / ww))
        if _norm(_sub(_add(loc, _mul(w, s)), q)) < r:
            return True
    return False


def camera(two: dict, board: str, kind: str = "lick"):
    """The lick shot's camera: dict(loc, target, lens, deg, seen).

    `two` is the two-shot setup, whose direction it starts from so screen
    direction holds: Cinnamon screen-left, Euler screen-right.
    """
    cp = where(board, kind)
    u0, u1, v = _span(board, kind)
    bp = list(MK.board_point((u0 + u1) / 2, v))
    m = _lerp(cp, bp, 0.6)
    d0 = _unit(_sub(two["loc"], two["target"]))
    dist = 0.9 + 1.2 * _norm(_sub(bp, cp))
    head = list(MK.HEAD_EULER)
    mouth = list(MK.euler_point((0.0, -0.18, 1.10)))
    t0, t1 = list(MK.euler_point((0, 0, 0.55))), list(MK.euler_point((0, -0.02, 0.98)))
    chalk = [list(MK.board_point(u0 + (u1 - u0) * k / 14, v, lift=0.004)) for k in range(15)]
    face = _unit(_sub(list(MK.board_point(0.65, 0.5)), cp))
    lips = _add(cp, _mul(face, 0.17))
    tongue = [_lerp(lips, bp, 0.1 + 0.1 * k) for k in range(9)]
    best = None
    for deg in range(-20, 1, 5):
        a = math.radians(deg)
        d = [d0[0] * math.cos(a) - d0[1] * math.sin(a), d0[0] * math.sin(a) + d0[1] * math.cos(a), d0[2]]
        loc = _add(_add(m, _mul(d, dist)), [0, 0, 0.06])

        def clear(p):
            return not (_blocked(loc, p, head, head, HEAD_R - 0.01) or _blocked(loc, p, t0, t1, CHEST_R)
                        or _blocked(loc, p, _add(cp, [0, 0, -0.14]), _add(cp, [0, 0, 0.04]), CINNAMON_R))
        seen = 0.5 * sum(map(clear, chalk)) / len(chalk) + 0.5 * sum(map(clear, tongue)) / len(tongue)
        view = _View(loc, m)
        ms = view.screen(mouth)
        gap = min(math.dist(view.screen(p), ms) for p in chalk)
        # past ~250 px (0.15) a gap reads as clear of his lips; then only what is seen counts
        score = seen + 0.8 * min(gap, 0.15)
        if best is None or score > best[0]:
            best = (score, dict(loc=loc, target=m, lens=LENS, deg=deg, seen=seen))
    return best[1]


def reach(two: dict, board: str, kind: str = "lick") -> float:
    """How far along the formula (in slate u) the tongue goes, seen from the
    lick camera: on until its tip comes within MARGIN of his head or nose on
    screen, or would go behind his chest."""
    u0, u1, v = _span(board, kind)
    if kind == "slurp":
        # the slurp is seen in the slate insert, without him: all of it
        return u1
    cam = camera(two, board, kind)
    view = _View(cam["loc"], cam["target"])
    head = list(MK.euler_point(HEAD_CENTRE))
    nose = _add(head, _mul(list(MK._rz((0, -1, 0), MK.EULER_YAW)), NOSE_AHEAD))
    face = [(view.screen(c), r / view.depth(c)) for c, r in ((head, HEAD_R), (nose, NOSE_R))]
    c0, c1 = list(MK.euler_point((0, 0, 0.55))), list(MK.euler_point((0, -0.02, 0.98)))
    a, b = view.screen(c0), view.screen(c1)
    chest_r = CHEST_R / view.depth(_lerp(c0, c1, 0.5))

    def clear(p):
        x, y = view.screen(p)
        if any(math.hypot(x - cx, y - cy) - r < MARGIN for (cx, cy), r in face):
            return False
        abx, aby = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((x - a[0]) * abx + (y - a[1]) * aby) / (abx * abx + aby * aby)))
        return math.hypot(x - a[0] - t * abx, y - a[1] - t * aby) - chest_r >= 0.02
    out = u0
    for k in range(41):
        u = u0 + (u1 - u0) * k / 40
        if not clear(list(MK.board_point(u, v))):
            break
        out = u
    return max(out, u0 + 0.12 * (u1 - u0))


# where Cinnamon may hover for the slurp, as (u, v, lift) on the slate
SLURP_SPOTS = ((0.5, 1.3, 0.3), (0.3, 1.3, 0.3), (0.7, 1.35, 0.25), (0.15, 1.2, 0.4), (-0.2, 0.9, 0.4),
               (0.05, 0.62, 0.55))


def slurp_where():
    """Cinnamon's body centre for the slurp (chosen with its camera)."""
    return list(_slurp()["spot"])


def slurp_camera():
    c = _slurp()
    return dict(loc=c["loc"], target=c["target"], lens=c["lens"], deg=c["deg"], dist=c["dist"])


_SLURP = None


def _slurp():
    """The slurp, one enormous lick that takes the whole slate clean, raking
    along the board from its left: from 30 degrees or less off the board's
    face, Euler -- 45 cm out from it -- is never between the camera and any
    of the chalk, and the tongue can be seen across the whole of it.

    Searched, not placed, together with where Cinnamon hovers: the pair
    that holds all four corners of the slate and Cinnamon, hides none of the
    chalk behind either of them, keeps his head clear of every line from its
    mouth to the board on screen, and is as square-on as that allows.
    """
    global _SLURP
    if _SLURP is not None:
        return _SLURP
    centre = list(MK.board_point(0.5, 0.5))
    n = list(MK.board_normal())
    left = _unit(_sub(list(MK.board_point(0.0, 0.5)), list(MK.board_point(1.0, 0.5))))
    corners = [list(MK.board_point(u, v)) for u in (0.0, 1.0) for v in (0.0, 1.0)]
    head = list(MK.euler_point(HEAD_CENTRE))
    c0, c1 = list(MK.euler_point((0, 0, 0.55))), list(MK.euler_point((0, -0.02, 0.98)))
    sweep = [list(MK.board_point(0.1 + 0.9 * i / 8, v)) for i in range(9) for v in (0.15, 0.5, 0.85)]
    def works(cp, loc, aim, lens):
        hw = 18.0 / lens
        hh = hw * 9 / 16
        view = _View(loc, aim)
        # the whole slate, and the whole of Cinnamon, antennae and all
        pts = corners + [cp, _add(cp, [0, 0, 0.40]), _add(cp, [0, 0, -0.27])]
        if any(view.depth(p) <= 0.2 for p in pts):
            return False
        if any(abs(view.screen(p)[0]) > hw * 0.95 or abs(view.screen(p)[1]) > hh * 0.95 for p in pts):
            return False
        if CINNAMON_R / view.depth(cp) > 0.35 * hh:         # not filling the frame
            return False
        # none of the chalk behind him or behind Cinnamon
        for p in sweep:
            if _blocked(loc, p, head, head, HEAD_R) or _blocked(loc, p, c0, c1, CHEST_R) \
                    or _blocked(loc, p, _add(cp, [0, 0, -0.14]), _add(cp, [0, 0, 0.04]), CINNAMON_R):
                return False
        # his head clear, on screen, of every line from its mouth to the chalk in front of him
        lips = view.screen(_add(cp, _mul(_unit(_sub(centre, cp)), 0.17)))
        hx, hy = view.screen(head)
        hr = HEAD_R / view.depth(head)
        for p in sweep:
            if view.depth(head) > view.depth(p):
                continue
            bx, by = view.screen(p)
            abx, aby = bx - lips[0], by - lips[1]
            t = max(0.0, min(1.0, ((hx - lips[0]) * abx + (hy - lips[1]) * aby) / (abx * abx + aby * aby)))
            if math.hypot(hx - lips[0] - t * abx, hy - lips[1] - t * aby) - hr < MARGIN:
                return False
        return True

    best = None
    for spot in SLURP_SPOTS:
        cp = list(MK.board_point(*spot))
        if _norm(_sub(cp, head)) < HEAD_R + 0.16 + 0.05:
            continue
        for deg in range(14, 46, 2):
            a = math.radians(deg)
            d = _unit(_add(_mul(n, math.sin(a)), _mul(left, math.cos(a))))
            for dist in (1.6, 1.9, 2.2, 2.5, 2.8):
                for lift in (0.15, 0.35, 0.55, 0.75):
                    loc = _add(_add(centre, _mul(d, dist)), [0, 0, lift])
                    for up in (0.0, 0.2, 0.35):
                        aim = _lerp(centre, cp, up)
                        for lens in (28.0, 24.0):
                            # as square-on, as close and as long a lens as allowed
                            score = deg - 4.0 * dist + 0.2 * lens
                            if (best is None or score > best[0]) and works(cp, loc, aim, lens):
                                best = (score, dict(loc=loc, target=aim, lens=lens, deg=deg, dist=dist, spot=cp))
    if best is None:
        raise RuntimeError("no camera sees the whole slurp past Euler")
    _SLURP = best[1]
    return _SLURP
