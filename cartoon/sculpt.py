"""Characters sculpted as distance fields, meshed by surface nets.

numpy only, so it runs inside Blender as well as anywhere else.

A cartoon character is soft shapes melted into each other: a cheek that
swells out of a jaw, a nose that grows from a brow. Joining primitive meshes
and voxel-remeshing them -- what lectern's first presenter did -- leaves a
crease wherever two parts meet, and that crease is exactly what makes a
figure read as a doll assembled from parts. A signed distance field with a
smooth minimum has no creases to begin with: every union has a fillet whose
radius is a number in the code.

Each primitive also carries a colour and a label. Colours blend through the
same fillets, so a rosy cheek fades into the jaw rather than stopping at a
seam; labels (the nearest primitive wins) give the rig something to weight
by -- "this vertex is finger 2" -- without anyone painting anything.

Surface nets rather than marching cubes: quads come out directly, one vertex
per cell, which is what the rig and the subdivision surface want, and it is
forty lines of vectorised numpy instead of a 256-case table.
"""

from __future__ import annotations

import math

import numpy as np


# ------------------------------------------------------------ transforms

def rot(rx=0.0, ry=0.0, rz=0.0) -> np.ndarray:
    """XYZ Euler rotation in degrees, as a matrix (local -> world)."""
    rx, ry, rz = (math.radians(a) for a in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = (math.cos(rx), math.sin(rx), math.cos(ry),
                              math.sin(ry), math.cos(rz), math.sin(rz))
    X = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Z @ Y @ X


class Node:
    """A field: distance, colour and label at any set of points."""

    def eval(self, P: np.ndarray):
        raise NotImplementedError

    def dist(self, P):
        return self.eval(P)[0]

    # sugar
    def __or__(self, other):
        return Union([self, other], 0.0)


class Prim(Node):
    def __init__(self, center=(0, 0, 0), R=None, color=(0.8, 0.8, 0.8), label="", mirror=False):
        self.c = np.asarray(center, float)
        self.R = np.eye(3) if R is None else np.asarray(R, float)
        self.color = np.asarray(color, float)
        self.label = label
        self.mirror = mirror   # also exists reflected in x

    def _local(self, P):
        return (P - self.c) @ self.R          # world -> local (R orthonormal)

    def _d(self, Q):
        raise NotImplementedError

    def eval(self, P):
        if self.mirror:
            P = P.copy()
            P[:, 0] = np.abs(P[:, 0])
        d = self._d(self._local(P))
        return d, np.broadcast_to(self.color, (len(P), 3)), np.full(len(P), self.label, dtype=object)


class Sphere(Prim):
    def __init__(self, center, r, **kw):
        super().__init__(center, **kw)
        self.r = r

    def _d(self, Q):
        return np.linalg.norm(Q, axis=1) - self.r


class Ellipsoid(Prim):
    """Inigo Quilez's bound: exact on the axes, close enough between them."""

    def __init__(self, center, radii, **kw):
        super().__init__(center, **kw)
        self.r = np.asarray(radii, float)

    def _d(self, Q):
        k0 = np.linalg.norm(Q / self.r, axis=1)
        k1 = np.linalg.norm(Q / (self.r * self.r), axis=1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


class Capsule(Prim):
    """A round cone from a (radius ra) to b (radius rb), in world space."""

    def __init__(self, a, b, ra, rb=None, **kw):
        super().__init__((0, 0, 0), **kw)
        self.a = np.asarray(a, float)
        self.b = np.asarray(b, float)
        self.ra = ra
        self.rb = ra if rb is None else rb

    def _d(self, Q):
        # exact round-cone distance (iq)
        a, b, r1, r2 = self.a, self.b, self.ra, self.rb
        ba = b - a
        l2 = ba @ ba
        rr = r1 - r2
        a2 = l2 - rr * rr
        il2 = 1.0 / l2
        pa = Q - a
        y = pa @ ba
        z = y - l2
        xv = pa * l2 - np.outer(y, ba)
        x2 = np.einsum("ij,ij->i", xv, xv)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        out = np.empty(len(Q))
        m1 = np.sign(z) * a2 * z2 > k
        m2 = np.sign(y) * a2 * y2 < k
        m3 = ~(m1 | m2)
        out[m1] = np.sqrt(x2[m1] + z2[m1]) * il2 - r2
        out[m2] = np.sqrt(x2[m2] + y2[m2]) * il2 - r1
        out[m3] = (np.sqrt(x2[m3] * a2 * il2) + y[m3] * rr) * il2 - r1
        return out


class RoundBox(Prim):
    def __init__(self, center, half, r, **kw):
        super().__init__(center, **kw)
        self.h = np.asarray(half, float)
        self.r = r

    def _d(self, Q):
        q = np.abs(Q) - (self.h - self.r)
        return (np.linalg.norm(np.maximum(q, 0.0), axis=1)
                + np.minimum(np.max(q, axis=1), 0.0) - self.r)


class Torus(Prim):
    """Ring in the local XY plane."""

    def __init__(self, center, R_major, r_minor, **kw):
        super().__init__(center, **kw)
        self.Rm = R_major
        self.rm = r_minor

    def _d(self, Q):
        q = np.stack([np.linalg.norm(Q[:, :2], axis=1) - self.Rm, Q[:, 2]], axis=1)
        return np.linalg.norm(q, axis=1) - self.rm


class Tube(Prim):
    """A swept circle along a polyline, radius varying per point."""

    def __init__(self, points, radii, **kw):
        super().__init__((0, 0, 0), **kw)
        self.pts = np.asarray(points, float)
        self.rad = np.asarray(radii, float)

    def _d(self, Q):
        best = np.full(len(Q), np.inf)
        for i in range(len(self.pts) - 1):
            seg = Capsule(self.pts[i], self.pts[i + 1], self.rad[i], self.rad[i + 1])
            best = np.minimum(best, seg._d(Q))
        return best


# ---------------------------------------------------------------- blends

def _smin(d1, d2, k):
    """Polynomial smooth minimum; returns distance and the blend weight of d2."""
    if k <= 0:
        h = (d2 < d1).astype(float)
        return np.minimum(d1, d2), h
    h = np.clip(0.5 + 0.5 * (d1 - d2) / k, 0.0, 1.0)
    return d1 * (1 - h) + d2 * h - k * h * (1 - h), h


class Union(Node):
    def __init__(self, children, k=0.01):
        self.children = list(children)
        self.k = k

    def eval(self, P):
        d, c, lab = self.children[0].eval(P)
        c = np.array(c, float)
        for ch in self.children[1:]:
            d2, c2, l2 = ch.eval(P)
            k = getattr(ch, "blend", None)
            d_new, h = _smin(d, d2, self.k if k is None else k)
            c = c * (1 - h)[:, None] + np.asarray(c2) * h[:, None]
            lab = np.where(d2 < d, l2, lab)
            d = d_new
        return d, c, lab


class Subtract(Node):
    """a minus b, with a fillet of k. The cut surface takes b's colour."""

    def __init__(self, a, b, k=0.0, color_cut=True):
        self.a, self.b, self.k = a, b, k
        self.color_cut = color_cut

    def eval(self, P):
        da, ca, la = self.a.eval(P)
        db, cb, lb = self.b.eval(P)
        if self.k > 0:
            h = np.clip(0.5 - 0.5 * (da + db) / self.k, 0.0, 1.0)
            d = da * (1 - h) + (-db) * h + self.k * h * (1 - h)
        else:
            h = (-db > da).astype(float)
            d = np.maximum(da, -db)
        c = np.array(ca, float)
        lab = la
        if self.color_cut:
            c = c * (1 - h)[:, None] + np.asarray(cb) * h[:, None]
            lab = np.where(h > 0.5, lb, la)
        return d, c, lab


class Intersect(Node):
    def __init__(self, a, b, k=0.0):
        self.a, self.b, self.k = a, b, k

    def eval(self, P):
        da, ca, la = self.a.eval(P)
        db, _, _ = self.b.eval(P)
        if self.k > 0:
            h = np.clip(0.5 - 0.5 * (db - da) / self.k, 0.0, 1.0)
            d = db * (1 - h) + da * h + self.k * h * (1 - h)
        else:
            d = np.maximum(da, db)
        return d, ca, la


class Paint(Node):
    """Recolour a field inside a soft region without changing its shape.

    `region` is another field: where it is negative the colour is `color`,
    fading over `soft` metres. Freckles, a rosy nose, a painted stripe.
    """

    def __init__(self, base, region, color, soft=0.01, label=None):
        self.base, self.region = base, region
        self.color = np.asarray(color, float)
        self.soft = soft
        self.label = label

    def eval(self, P):
        d, c, lab = self.base.eval(P)
        dr = self.region.dist(P)
        w = np.clip(0.5 - dr / (2 * self.soft), 0.0, 1.0)
        w = w * w * (3 - 2 * w)
        c = np.asarray(c, float) * (1 - w)[:, None] + self.color * w[:, None]
        if self.label is not None:
            lab = np.where(w > 0.5, self.label, lab)
        return d, c, lab


class Warp(Node):
    """Evaluate a child in bent space: the child sees P - fn(P).

    A smile is a slot whose ends are lifted: warp z by the square of x and
    the same ellipsoid curves. Keep the bend gentle -- the distance is no
    longer exact, only close.
    """

    def __init__(self, base, fn):
        self.base, self.fn = base, fn

    def eval(self, P):
        return self.base.eval(P - self.fn(P))


class PaintFn(Node):
    """Recolour by any function of position returning a weight in [0, 1]:
    stripes, gradients, a weave."""

    def __init__(self, base, fn, color, label=None):
        self.base, self.fn = base, fn
        self.color = np.asarray(color, float)
        self.label = label

    def eval(self, P):
        d, c, lab = self.base.eval(P)
        w = np.clip(self.fn(P), 0.0, 1.0)
        c = np.asarray(c, float) * (1 - w)[:, None] + self.color * w[:, None]
        if self.label is not None:
            lab = np.where(w > 0.5, self.label, lab)
        return d, c, lab


class MirrorX(Node):
    """The child reflected through x = 0: a right hand from a left one."""

    def __init__(self, base):
        self.base = base

    def eval(self, P):
        Q = P.copy()
        Q[:, 0] = -Q[:, 0]
        return self.base.eval(Q)


class Displace(Node):
    """Add a function of position to the distance: folds, lumps, fur."""

    def __init__(self, base, fn):
        self.base, self.fn = base, fn

    def eval(self, P):
        d, c, lab = self.base.eval(P)
        return d + self.fn(P), c, lab


def blend(node, k):
    """Give one child its own fillet radius inside a Union."""
    node.blend = k
    return node


# ------------------------------------------------------------------ noise

def value_noise(P, scale, seed=0):
    """Smooth 3D value noise in [-1, 1]; cheap, deterministic, numpy only."""
    Q = P / scale
    i = np.floor(Q).astype(np.int64)
    f = Q - i
    u = f * f * (3 - 2 * f)

    def h(ix, iy, iz):
        n = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
        n = (n ^ (n >> 13)) * 1274126177
        return ((n & 0xFFFF) / 32767.5) - 1.0

    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = ((u[:, 0] if dx else 1 - u[:, 0]) *
                     (u[:, 1] if dy else 1 - u[:, 1]) *
                     (u[:, 2] if dz else 1 - u[:, 2]))
                out = out + w * h(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz)
    return out


def fbm(P, scale, octaves=3, seed=0):
    out, amp, s = 0.0, 1.0, scale
    for o in range(octaves):
        out = out + amp * value_noise(P, s, seed + o)
        amp *= 0.5
        s *= 0.5
    return out


# ------------------------------------------------------------ meshing

def surface_nets(node: Node, lo, hi, voxel: float, chunk: int = 400_000):
    """Mesh the zero level set of `node` inside the box [lo, hi].

    Returns (verts (N,3), quads (M,4)). One vertex per cell that the surface
    crosses, at the mean of the edge crossings; one quad per grid edge that
    the surface crosses, joining the four cells around it.
    """
    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)
    n = np.ceil((hi - lo) / voxel).astype(int) + 1
    xs = [lo[a] + np.arange(n[a]) * voxel for a in range(3)]
    G = np.stack(np.meshgrid(*xs, indexing="ij"), axis=-1).reshape(-1, 3)
    F = np.empty(len(G))
    for s in range(0, len(G), chunk):
        F[s:s + chunk] = node.dist(G[s:s + chunk])
    F = F.reshape(n)
    inside = F < 0

    # cells: corners at (i..i+1, j..j+1, k..k+1)
    nc = n - 1
    corners = [(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)]
    cnt = np.zeros(nc, dtype=np.int8)
    for a, b, c in corners:
        cnt += inside[a:a + nc[0], b:b + nc[1], c:c + nc[2]]
    active = (cnt > 0) & (cnt < 8)
    idx = -np.ones(nc, dtype=np.int64)
    ai = np.argwhere(active)
    idx[active] = np.arange(len(ai))

    # vertex = mean of crossings along the 12 cell edges
    acc = np.zeros((len(ai), 3))
    num = np.zeros(len(ai))
    edges = []
    for a, b, c in corners:
        for axis in range(3):
            d = [a, b, c]
            if d[axis] == 1:
                continue
            e = list(d)
            e[axis] = 1
            edges.append((tuple(d), tuple(e)))
    I, J, K = ai[:, 0], ai[:, 1], ai[:, 2]
    for d, e in edges:
        f0 = F[I + d[0], J + d[1], K + d[2]]
        f1 = F[I + e[0], J + e[1], K + e[2]]
        cross = (f0 < 0) != (f1 < 0)
        t = np.where(cross, f0 / np.where(f0 - f1 == 0, 1e-12, f0 - f1), 0.0)
        p0 = np.stack([I + d[0], J + d[1], K + d[2]], 1).astype(float)
        p1 = np.stack([I + e[0], J + e[1], K + e[2]], 1).astype(float)
        p = p0 + (p1 - p0) * t[:, None]
        acc += p * cross[:, None]
        num += cross
    verts = lo + acc / np.maximum(num, 1)[:, None] * voxel

    # quads: one per crossing grid edge, from the four cells sharing it
    quads = []
    for axis in range(3):
        o1, o2 = [(1, 2), (0, 2), (0, 1)][axis]
        sl0 = [slice(None)] * 3
        sl1 = [slice(None)] * 3
        sl0[axis] = slice(0, n[axis] - 1)
        sl1[axis] = slice(1, n[axis])
        e_in0 = inside[tuple(sl0)]
        e_in1 = inside[tuple(sl1)]
        cross = e_in0 != e_in1
        # the edge at grid point g along `axis` is shared by cells
        # g - (0|1 on o1) - (0|1 on o2); skip edges on the boundary
        g = np.argwhere(cross)
        ok = (g[:, o1] >= 1) & (g[:, o2] >= 1) & (g[:, o1] < n[o1] - 1) & (g[:, o2] < n[o2] - 1)
        g = g[ok]
        flip = e_in0[tuple(g.T)]

        def cell(du, dv):
            c = g.copy()
            c[:, o1] -= du
            c[:, o2] -= dv
            return idx[c[:, 0], c[:, 1], c[:, 2]]

        q = np.stack([cell(1, 1), cell(0, 1), cell(0, 0), cell(1, 0)], 1)
        q[flip] = q[flip][:, ::-1]
        if axis == 1:
            q = q[:, ::-1]
        quads.append(q)
    quads = np.concatenate(quads)
    quads = quads[(quads >= 0).all(1)][:, ::-1]     # outward normals
    return verts, np.ascontiguousarray(quads)


def attributes(node: Node, verts: np.ndarray, chunk=200_000):
    """Colour and label at each vertex (evaluated on the final surface)."""
    cols, labs = [], []
    for s in range(0, len(verts), chunk):
        _, c, lab = node.eval(verts[s:s + chunk])
        cols.append(np.asarray(c, float))
        labs.append(lab)
    return np.concatenate(cols), np.concatenate(labs)


def project(node: Node, verts: np.ndarray, iters=3, eps=1e-4):
    """Pull vertices onto the true zero set along the field gradient.

    Surface-nets vertices sit within a voxel of the surface; a couple of
    Newton steps put them on it, which is the difference between a smooth
    cheek and a faintly terraced one.
    """
    V = verts.copy()
    for _ in range(iters):
        d = node.dist(V)
        g = np.zeros_like(V)
        for a in range(3):
            o = np.zeros(3)
            o[a] = eps
            g[:, a] = (node.dist(V + o) - node.dist(V - o)) / (2 * eps)
        gn = np.maximum(np.linalg.norm(g, axis=1), 1e-9)
        V -= (d / gn / gn)[:, None] * g
    return V
