"""Strands for the professor: the wild white hair, the brows and the walrus.

Imported by human.py inside Blender. Every strand is grown here in Python
rather than by the Essentials node groups because the shape is the whole
character -- Einstein's hair is not uniform fuzz, it is tufts that lift off
the crown and fan out at the sides, and the moustache is a drooping walrus
that hangs over the upper lip and past the corners of the mouth. That takes
per-region direction, length and clumping, which is easier to say in code.

Roots are sampled on the body's rest surface (area-weighted, masked by a
per-vertex region weight) and carry their UV, so a Deform Curves on Surface
modifier binds them to the skin: the hair rides the head bone and the
moustache rides the upper-lip shape keys.
"""

from __future__ import annotations

import math
import os
import random

import bpy
from mathutils import Vector, noise
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

UP = Vector((0.0, 0.0, 1.0))
DOWN = Vector((0.0, 0.0, -1.0))
BACK = Vector((0.0, 1.0, 0.0))     # MakeHuman faces -Y


def log(*a):
    print("[hair]", *a, flush=True)


# ---------------------------------------------------------------- surfaces

class Surface:
    """The body at rest: triangles with UVs, and a BVH to keep hair outside."""

    def __init__(self, body):
        me = body.data
        me.calc_loop_triangles()
        uv = me.uv_layers["UVMap"].data
        body_group = body.vertex_groups["body"].index
        in_body = [any(g.group == body_group and g.weight > 0.5 for g in v.groups)
                   for v in me.vertices]
        self.co = [v.co.copy() for v in me.vertices]
        self.normals = [v.normal.copy() for v in me.vertices]
        self.tris = []
        for t in me.loop_triangles:
            vs = tuple(t.vertices)
            if not all(in_body[i] for i in vs):
                continue
            self.tris.append((vs, tuple(uv[li].uv.copy() for li in t.loops), t.area))
        polys = [t[0] for t in self.tris]
        self.bvh = BVHTree.FromPolygons(self.co, polys, all_triangles=True)

    def sample(self, weight, count, rng):
        """`count` roots, area- and weight-proportional. weight: per vertex."""
        cand = []
        total = 0.0
        for vs, uvs, area in self.tris:
            w = sum(weight[i] for i in vs) / 3.0
            if w <= 0.01:
                continue
            total += area * w
            cand.append((total, vs, uvs, w))
        if not cand:
            return []
        out = []
        import bisect
        keys = [c[0] for c in cand]
        for _ in range(count):
            k = bisect.bisect_left(keys, rng.random() * total)
            _, vs, uvs, w = cand[min(k, len(cand) - 1)]
            a, b = rng.random(), rng.random()
            if a + b > 1:
                a, b = 1 - a, 1 - b
            c = 1 - a - b
            p = self.co[vs[0]] * a + self.co[vs[1]] * b + self.co[vs[2]] * c
            n = (self.normals[vs[0]] * a + self.normals[vs[1]] * b + self.normals[vs[2]] * c).normalized()
            uv = uvs[0] * a + uvs[1] * b + uvs[2] * c
            wt = weight[vs[0]] * a + weight[vs[1]] * b + weight[vs[2]] * c
            out.append((p, n, uv, wt))
        return out

    def push_out(self, p, offset):
        """Keep a point at least `offset` outside the skin."""
        hit = self.bvh.find_nearest(p)
        if hit[0] is None:
            return p
        loc, nrm, _, _ = hit
        d = (p - loc).dot(nrm)
        if d < offset:
            return p + nrm * (offset - d)
        return p


def group_weights(body, name):
    gi = body.vertex_groups[name].index
    w = [0.0] * len(body.data.vertices)
    for v in body.data.vertices:
        for g in v.groups:
            if g.group == gi:
                w[v.index] = g.weight
    return w


def proximity_weights(body, stencil, radius):
    """Weight body vertices by distance to another mesh (in world space)."""
    kd = KDTree(len(stencil.data.vertices))
    mw = stencil.matrix_world
    for i, v in enumerate(stencil.data.vertices):
        kd.insert(mw @ v.co, i)
    kd.balance()
    bw = body.matrix_world
    out = []
    for v in body.data.vertices:
        _, _, d = kd.find(bw @ v.co)
        out.append(max(0.0, 1.0 - d / radius) if d is not None else 0.0)
    return out


# ----------------------------------------------------------------- strands

def grow(root, direction, length, n, rng, *, gravity=0.0, wave=0.0,
         wave_freq=30.0, frizz=0.0, frizz_freq=160.0, surface=None,
         offset=0.0006, seed=0.0):
    """One strand as `n` points walking from the root."""
    seg = length / (n - 1)
    d = direction.normalized()
    p = root.copy()
    pts = [p.copy()]
    for k in range(1, n):
        t = k / (n - 1)
        q = p * wave_freq + Vector((seed, seed * 0.37, seed * 0.71))
        bend = noise.noise_vector(q) * wave * t
        fz = noise.noise_vector(p * frizz_freq + Vector((seed * 3.1, 0, 0))) * frizz * t * t
        d = (d + bend + fz + DOWN * gravity * t).normalized()
        p = p + d * seg
        if surface is not None:
            p = surface.push_out(p, offset * (1.0 + 2.0 * t))
        pts.append(p.copy())
    return pts


def clump(strands, roots, guides, guide_roots, amount, shape=1.2):
    """Pull each strand's tip toward its nearest guide: tufts, not fuzz."""
    kd = KDTree(len(guide_roots))
    for i, r in enumerate(guide_roots):
        kd.insert(r, i)
    kd.balance()
    out = []
    for pts, r in zip(strands, roots):
        _, gi, _ = kd.find(r)
        g = guides[gi]
        gr = guide_roots[gi]
        n = len(pts)
        new = []
        for k, p in enumerate(pts):
            t = k / (n - 1)
            gk = g[min(k, len(g) - 1)]
            target = gk + (r - gr) * (1.0 - t)
            f = amount * (t ** shape)
            new.append(p.lerp(target, f))
        out.append(new)
    return out


# ----------------------------------------------------------- the three looks

def head_hair(surf, body, rng):
    w = group_weights(body, "scalp")
    scalp = [surf.co[i] for i, x in enumerate(w) if x > 0.3]
    c = sum(scalp, Vector()) / len(scalp)
    c.z -= 0.03
    roots = surf.sample(w, 42000, rng)
    guides_roots = surf.sample(w, 520, random.Random(rng.random()))

    def shape(p, n, s, long=1.0):
        radial = (p - c).normalized()
        front = max(0.0, -radial.y)                      # hairline over the face
        side = abs(radial.x)
        d = n * 0.55 + radial * 0.45 + UP * 0.25 + BACK * (0.55 * front)
        d += Vector((rng.gauss(0, 0.28), rng.gauss(0, 0.28), rng.gauss(0, 0.22)))
        L = rng.uniform(0.050, 0.095) * (1.0 + 0.55 * side) * (1.0 - 0.35 * front) * long
        return grow(p, d, L, 16, rng, gravity=0.10 + 0.25 * (1 - radial.z),
                    wave=0.55, wave_freq=26.0, frizz=0.35, frizz_freq=140.0,
                    surface=surf, offset=0.002, seed=s)

    guides = [shape(p, n, i * 1.37, long=1.08) for i, (p, n, uv, wt) in enumerate(guides_roots)]
    strands = [shape(p, n, rng.random() * 100) for (p, n, uv, wt) in roots]
    strands = clump(strands, [r[0] for r in roots], guides, [g[0] for g in guides_roots], 0.62)
    # a few escaped wisps: the halo that makes the silhouette read as his
    for (p, n, uv, wt), i in zip(roots[:1800], range(1800)):
        radial = (p - c).normalized()
        d = radial * 0.8 + n * 0.3 + UP * 0.2
        strands[i] = grow(p, d, rng.uniform(0.08, 0.14), 16, rng, gravity=0.05,
                          wave=0.9, wave_freq=20.0, frizz=0.5, surface=surf,
                          offset=0.002, seed=rng.random() * 100)
    return roots, strands, (0.00016, 0.00005)


def brow_hair(surf, body, brows, rng):
    w = proximity_weights(body, brows, 0.007)
    roots = surf.sample(w, 2600, rng)
    mid_x = 0.0
    strands = []
    for p, n, uv, wt in roots:
        side = 1.0 if p.x > mid_x else -1.0
        out_x = Vector((side, 0.0, 0.0))
        tang = (out_x - n * out_x.dot(n)).normalized()
        outer = min(1.0, abs(p.x) / 0.05)
        d = tang * 0.75 + UP * 0.25 + n * 0.45 + Vector((0, 0, -0.35 * outer))
        d += Vector((rng.gauss(0, 0.3), rng.gauss(0, 0.2), rng.gauss(0, 0.3)))
        L = rng.uniform(0.008, 0.016) * (1.0 + 0.9 * outer)
        if rng.random() < 0.06:
            L *= 2.0          # the wild ones
        strands.append(grow(p, d, L, 7, rng, gravity=0.15, wave=0.4, wave_freq=60.0,
                            frizz=0.3, surface=surf, offset=0.0008,
                            seed=rng.random() * 100))
    return roots, strands, (0.00012, 0.00005)


def moustache_hair(surf, body, stencil, rng):
    w = proximity_weights(body, stencil, 0.006)
    roots = surf.sample(w, 9000, rng)
    xs = [r[0].x for r in roots]
    half = max(max(xs), -min(xs), 1e-3)
    strands = []
    for p, n, uv, wt in roots:
        side = 1.0 if p.x >= 0 else -1.0
        u = min(1.0, abs(p.x) / half)                     # 0 centre, 1 corner
        d = DOWN * 1.0 + n * (0.55 - 0.2 * u) + Vector((side * 0.35 * u, 0, 0))
        d += Vector((rng.gauss(0, 0.12), rng.gauss(0, 0.08), rng.gauss(0, 0.1)))
        # a walrus: short over the philtrum, long and heavy past the corners
        L = rng.uniform(0.016, 0.022) + 0.024 * u * u
        strands.append(grow(p, d, L, 10, rng, gravity=0.35 + 0.3 * u, wave=0.25,
                            wave_freq=70.0, frizz=0.12, surface=surf, offset=0.0025,
                            seed=rng.random() * 100))
    return roots, strands, (0.00018, 0.00007)


# ---------------------------------------------------------------- objects

def hair_material(name, base, variance):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    h = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
    h.parametrization = "COLOR"
    info = nt.nodes.new("ShaderNodeHairInfo")
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (*base, 1.0)
    mix.inputs["B"].default_value = (*variance, 1.0)
    nt.links.new(info.outputs["Random"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], h.inputs["Color"])
    h.inputs["Roughness"].default_value = 0.32
    h.inputs["Radial Roughness"].default_value = 0.55
    h.inputs["Coat"].default_value = 0.15
    nt.links.new(h.outputs[0], out.inputs[0])
    return mat


def deform_tree():
    ng = bpy.data.node_groups.get("ProfessorHairDeform")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("ProfessorHairDeform", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    dn = ng.nodes.new("GeometryNodeDeformCurvesOnSurface")
    ng.links.new(gi.outputs[0], dn.inputs[0])
    ng.links.new(dn.outputs[0], go.inputs[0])
    return ng


def make_curves(name, body, roots, strands, radius, material):
    cd = bpy.data.hair_curves.new(name)
    sizes = [len(s) for s in strands]
    cd.add_curves(sizes)
    flat = [c for s in strands for p in s for c in p]
    cd.attributes["position"].data.foreach_set("vector", flat)
    r0, r1 = radius
    rad = []
    for s in strands:
        n = len(s)
        rad.extend(r0 + (r1 - r0) * (k / (n - 1)) for k in range(n))
    ra = cd.attributes.get("radius") or cd.attributes.new("radius", "FLOAT", "POINT")
    ra.data.foreach_set("value", rad)
    uva = cd.attributes.new("surface_uv_coordinate", "FLOAT2", "CURVE")
    uva.data.foreach_set("vector", [c for r in roots for c in (r[2].x, r[2].y)])
    cd.surface = body
    cd.surface_uv_map = "UVMap"
    cd.materials.append(material)
    ob = bpy.data.objects.new(name, cd)
    for col in body.users_collection:
        col.objects.link(ob)
    ob.parent = body
    ob.matrix_parent_inverse = body.matrix_world.inverted()
    mod = ob.modifiers.new("Surface Deform", "NODES")
    mod.node_group = deform_tree()
    log(name, len(strands), "strands", sum(sizes), "points")
    return ob


def _stencil(body, mhclo_name):
    import importlib
    svc = importlib.import_module("bl_ext.user_default.mpfb.services")
    path = svc.AssetService.find_asset_absolute_path(mhclo_name, asset_subdir="clothes")
    ob = svc.HumanService.add_mhclo_asset(path, body, asset_type="Clothes", subdiv_levels=0,
                                           material_type="NONE", set_up_rigging=False,
                                           interpolate_weights=False, import_subrig=False,
                                           import_weights=False)
    return ob


def _discard_stencil(body, ob, mhclo_name):
    stem = "Delete." + os.path.splitext(mhclo_name)[0]
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    vg = body.vertex_groups.get(stem)
    if vg:
        body.vertex_groups.remove(vg)
    for m in list(body.modifiers):
        if m.type == "MASK" and m.vertex_group == stem:
            body.modifiers.remove(m)


def grow_all(body, kids, seed=11):
    rng = random.Random(seed)
    body.add_rest_position_attribute = True
    surf = Surface(body)

    white = hair_material("ProfessorHair", (0.86, 0.85, 0.82), (0.64, 0.62, 0.59))
    roots, strands, rad = head_hair(surf, body, rng)
    make_curves("Professor.hair", body, roots, strands, rad, white)

    brows = next(o for o in kids if "eyebrow" in o.name)
    roots, strands, rad = brow_hair(surf, body, brows, rng)
    make_curves("Professor.brows", body, roots, strands, rad, white)
    # the card brows stay underneath as density, in the same white
    for m in brows.data.materials:
        _tint(m, (0.8, 0.79, 0.76))

    stencil_name = "rehmanpolanski_moustache_viking.mhclo"
    st = _stencil(body, stencil_name)
    roots, strands, rad = moustache_hair(surf, body, st, rng)
    _discard_stencil(body, st, stencil_name)
    tache = hair_material("ProfessorMoustache", (0.82, 0.79, 0.72), (0.66, 0.62, 0.54))
    make_curves("Professor.moustache", body, roots, strands, rad, tache)

    sc = bpy.context.scene
    sc.render.hair_type = "STRIP"
    sc.render.hair_subdiv = 1


def _tint(mat, rgb):
    if not mat or not mat.node_tree:
        return
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            for link in list(n.inputs["Base Color"].links):
                mat.node_tree.links.remove(link)
            n.inputs["Base Color"].default_value = (*rgb, 1.0)
