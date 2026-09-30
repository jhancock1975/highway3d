"""Euler's study in St. Petersburg, 1773: the room, its dressing, its light.

Runs inside Blender. `build(time)` makes the set for "night" or "morning"
and returns its marks: named places the characters and cameras are put.

The room is what a professor of the Imperial Academy might have had on
Vasilyevsky Island: pale green plaster over panelled wainscot, a parquet
floor, a tall paned window onto the snowy street, a tiled stove in the
corner (every Petersburg room had one), bookcases of his own work, and the
big slate he wrote on in letters large enough to feel.

Props that exist as free CC0 models come from Poly Haven (cartoon/assets.py);
what does not -- the period books, the stove, the slate, the window -- is
built here. Everything that carries writing in life carries writing here:
the book spines have titles, the clock has numerals, the papers have lines.
"""

from __future__ import annotations

import math
import os
import random

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

from cartoon import assets
from cartoon.bl import common as C
from cartoon.sets import marks as MK

W, D, H = 6.0, MK.ROOM_D, 3.3    # room: x from -3 to 3, y from -3 to 3
WIN_X, WIN_W, WIN_SILL, WIN_H = MK.WIN_X, MK.WIN_W, MK.WIN_SILL, MK.WIN_H
FONT_BOOK = "/System/Library/Fonts/Supplemental/BigCaslon.ttf"

# Euler's own books, and what an eighteenth-century mathematician read.
TITLES = [
    "MECHANICA", "INTRODUCTIO", "CALC. DIFF.", "CALC. INTEGR.", "ALGEBRA",
    "DIOPTRICA", "OPUSCULA", "METHODUS", "THEORIA LUNAE", "SCIENTIA NAV.",
    "NOVI COMM.", "ACTA ERUD.", "EUCLIDES", "PRINCIPIA", "BERNOULLI", "LEIBNITZ",
    "AENEIS", "BIBLIA", "LETTRES", "TENTAMEN", "MUSICA", "ASTRONOMIA",
    "COMMENT. ACAD.", "INST. CALC.", "GEOMETRIA", "OPTICA", "HYDRAULICA",
    "BALLISTICA", "HARMONIA", "ARITHMETICA",
]


def _box(name, size, loc, mat, coll, bevel=0.0, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = rot
    coll.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    if bevel:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
        m.limit_method = "ANGLE"
    return ob


def _cyl(name, r, depth, loc, mat, coll, verts=32, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=verts, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    for c in ob.users_collection:
        c.objects.unlink(ob)
    coll.objects.link(ob)
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def _text(name, body, loc, rot, size, mat, coll, font=FONT_BOOK, extrude=0.0006, align="CENTER"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    cu.align_y = "CENTER"
    if font and os.path.exists(font):
        cu.font = bpy.data.fonts.load(font, check_existing=True)
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.rotation_euler = rot
    coll.objects.link(ob)
    cu.materials.append(mat)
    return ob


def _textured(name, tex, scale=1.0, tint=None, rough_mult=1.0, bump=0.4):
    """A material from a fetched Poly Haven texture set, box-mapped."""
    maps = assets.texture(tex)
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def img(path, non_color=False):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            n.image.colorspace_settings.name = "Non-Color"
        n.projection = "BOX"
        n.projection_blend = 0.25
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n
    if "Diffuse" in maps:
        d = img(maps["Diffuse"])
        col = d.outputs["Color"]
        if tint is not None:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            nt.links.new(col, mix.inputs["A"])
            mix.inputs["B"].default_value = (*tint, 1)
            col = mix.outputs["Result"]
        nt.links.new(col, p.inputs["Base Color"])
    if "Rough" in maps:
        r = img(maps["Rough"], True)
        mm = nt.nodes.new("ShaderNodeMath")
        mm.operation = "MULTIPLY"
        mm.inputs[1].default_value = rough_mult
        nt.links.new(r.outputs["Color"], mm.inputs[0])
        nt.links.new(mm.outputs[0], p.inputs["Roughness"])
    if "nor_gl" in maps:
        n = img(maps["nor_gl"], True)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = bump
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    return m


def _append(name, coll, loc=(0, 0, 0), rot_z=0.0, scale=1.0, drop=None):
    p = assets.path_of(name)
    if not p:
        raise RuntimeError(f"{name} is not fetched: run python3 -m cartoon.assets")
    with bpy.data.libraries.load(p, link=False) as (src, dst):
        dst.objects = src.objects
    obs = [o for o in dst.objects if o is not None and not o.name.startswith("wdg")
           and not o.name.startswith("Sphere_stash")]
    if drop:
        obs = [o for o in obs if not any(d in o.name for d in drop)]
    root = bpy.data.objects.new(name + ".root", None)
    coll.objects.link(root)
    for o in obs:
        coll.objects.link(o)
        if o.parent is None:
            o.parent = root
    root.location = loc
    root.rotation_euler = (0, 0, math.radians(rot_z))
    root.scale = (scale, scale, scale)
    return root, obs


# ------------------------------------------------------------------ room

def room(coll, mats):
    floor = _box("floor", (W, D, 0.02), (0, 0, -0.01), mats["floor"], coll)
    ceil = _box("ceiling", (W, D, 0.02), (0, 0, H + 0.01), mats["ceiling"], coll)
    walls = []
    # back wall (+y) with the window cut out: built as four pieces
    wx0, wx1 = WIN_X - WIN_W / 2, WIN_X + WIN_W / 2
    wz0, wz1 = WIN_SILL, WIN_SILL + WIN_H
    t = 0.12
    y = D / 2 + t / 2
    walls.append(_box("wall_back_l", (wx0 + W / 2, t, H), ((wx0 - W / 2) / 2, y, H / 2), mats["wall"], coll))
    walls.append(_box("wall_back_r", (W / 2 - wx1, t, H), ((wx1 + W / 2) / 2, y, H / 2), mats["wall"], coll))
    walls.append(_box("wall_back_b", (WIN_W, t, wz0), (WIN_X, y, wz0 / 2), mats["wall"], coll))
    walls.append(_box("wall_back_t", (WIN_W, t, H - wz1), (WIN_X, y, (H + wz1) / 2), mats["wall"], coll))
    walls.append(_box("wall_left", (t, D, H), (-W / 2 - t / 2, 0, H / 2), mats["wall"], coll))
    walls.append(_box("wall_right", (t, D, H), (W / 2 + t / 2, 0, H / 2), mats["wall"], coll))
    walls.append(_box("wall_front", (W, t, H), (0, -D / 2 - t / 2, H / 2), mats["wall"], coll))

    # wainscot: panelled wood to the dado rail, on every wall
    dado = 0.95
    for name, a, b, fixed, axis in (("back", -W / 2, W / 2, D / 2, "x"), ("front", -W / 2, W / 2, -D / 2, "x"),
                                    ("left", -D / 2, D / 2, -W / 2, "y"), ("right", -D / 2, D / 2, W / 2, "y")):
        inward = -1 if fixed > 0 else 1
        segs = []
        if name == "back":
            segs = [(a, wx0), (wx1, b)]
            # under the window
            segs.append((wx0, wx1))
        else:
            segs = [(a, b)]
        for s0, s1 in segs:
            top = dado if not (name == "back" and s0 == wx0) else wz0
            length = s1 - s0
            mid = (s0 + s1) / 2
            if axis == "x":
                _box(f"wainscot_{name}_{mid:.1f}", (length, 0.025, top), (mid, fixed + inward * 0.0125, top / 2),
                     mats["panel"], coll)
                _box(f"dado_{name}_{mid:.1f}", (length, 0.05, 0.045), (mid, fixed + inward * 0.025, top), mats["trim"], coll, 0.008)
                _box(f"skirting_{name}_{mid:.1f}", (length, 0.04, 0.14), (mid, fixed + inward * 0.02, 0.07), mats["trim"], coll, 0.006)
                n = max(1, int(length / 0.62))
                for i in range(n):
                    px = s0 + (i + 0.5) * length / n
                    _box(f"panel_{name}_{px:.2f}", (length / n - 0.12, 0.018, top - 0.34),
                         (px, fixed + inward * 0.03, 0.14 + (top - 0.34) / 2 + 0.03), mats["panel"], coll, 0.012)
            else:
                _box(f"wainscot_{name}", (0.025, length, top), (fixed + inward * 0.0125, mid, top / 2), mats["panel"], coll)
                _box(f"dado_{name}", (0.05, length, 0.045), (fixed + inward * 0.025, mid, top), mats["trim"], coll, 0.008)
                _box(f"skirting_{name}", (0.04, length, 0.14), (fixed + inward * 0.02, mid, 0.07), mats["trim"], coll, 0.006)
                n = max(1, int(length / 0.62))
                for i in range(n):
                    py = s0 + (i + 0.5) * length / n
                    _box(f"panel_{name}_{py:.2f}", (0.018, length / n - 0.12, top - 0.34),
                         (fixed + inward * 0.03, py, 0.14 + (top - 0.34) / 2 + 0.03), mats["panel"], coll, 0.012)
        # cornice
        if axis == "x":
            _box(f"cornice_{name}", (b - a, 0.09, 0.1), ((a + b) / 2, fixed + inward * 0.045, H - 0.05), mats["trim"], coll, 0.02)
        else:
            _box(f"cornice_{name}", (0.09, b - a, 0.1), (fixed + inward * 0.045, (a + b) / 2, H - 0.05), mats["trim"], coll, 0.02)
    # ceiling beams
    for i in range(5):
        _box(f"beam_{i}", (0.16, D, 0.2), (-2.4 + i * 1.2, 0, H - 0.1), mats["beam"], coll, 0.01)
    return floor


def door(coll, mats, y=-1.8):
    """The study door on the left wall, panelled, with a brass knob: the one
    Fuss knocks on in the morning."""
    x = -W / 2 + 0.03
    wood = mats["case"]
    trim = mats["trim"]
    _box("door.frame_l", (0.08, 0.12, 2.3), (x, y - 0.56, 1.15), trim, coll, 0.01)
    _box("door.frame_r", (0.08, 0.12, 2.3), (x, y + 0.56, 1.15), trim, coll, 0.01)
    _box("door.frame_t", (0.08, 1.2, 0.12), (x, y, 2.33), trim, coll, 0.01)
    _box("door.leaf", (0.05, 1.02, 2.22), (x + 0.02, y, 1.11), wood, coll, 0.006)
    for zc, h in ((0.55, 0.75), (1.55, 0.95)):
        for dy in (-0.24, 0.24):
            _box(f"door.panel{zc}{dy}", (0.02, 0.38, h), (x + 0.05, y + dy, zc), wood, coll, 0.015)
    k = _cyl("door.knob", 0.03, 0.05, (x + 0.08, y + 0.4, 1.0), mats["brass"], coll, 24, rot=(0, math.pi / 2, 0))
    _cyl("door.rose", 0.045, 0.01, (x + 0.055, y + 0.4, 1.0), mats["brass"], coll, 24, rot=(0, math.pi / 2, 0))
    for zc in (0.35, 1.9):
        _box(f"door.hinge{zc}", (0.02, 0.1, 0.12), (x + 0.05, y - 0.5, zc), mats["iron"], coll)
    return k


def window(coll, mats):
    """A tall sash window of small panes, with a deep sill and curtains."""
    wx0, wx1 = WIN_X - WIN_W / 2, WIN_X + WIN_W / 2
    y = D / 2
    z0, z1 = WIN_SILL, WIN_SILL + WIN_H
    fr = mats["trim"]
    # jambs and head, deep reveals
    _box("win_jamb_l", (0.08, 0.2, WIN_H), (wx0 + 0.04, y + 0.02, (z0 + z1) / 2), fr, coll, 0.01)
    _box("win_jamb_r", (0.08, 0.2, WIN_H), (wx1 - 0.04, y + 0.02, (z0 + z1) / 2), fr, coll, 0.01)
    _box("win_head", (WIN_W, 0.2, 0.09), (WIN_X, y + 0.02, z1 - 0.045), fr, coll, 0.01)
    _box("win_sill", (WIN_W + 0.16, 0.3, 0.05), (WIN_X, y - 0.04, z0), fr, coll, 0.012)
    # the sash: 3 x 5 panes. The left half is hinged so it can swing open.
    sash_l = bpy.data.objects.new("sash_left", None)
    sash_l.location = (wx0 + 0.08, y + 0.05, z0 + 0.03)
    coll.objects.link(sash_l)
    sash_r = bpy.data.objects.new("sash_right", None)
    sash_r.location = (wx1 - 0.08, y + 0.05, z0 + 0.03)
    coll.objects.link(sash_r)
    half = (WIN_W - 0.16) / 2
    hh = WIN_H - 0.12
    glass = mats["glass"]
    for side, root, sgn in (("l", sash_l, 1), ("r", sash_r, -1)):
        cx = sgn * half / 2
        for i in range(3):
            xx = sgn * i * half / 2
            o = _box(f"mullion_v_{side}{i}", (0.03, 0.04, hh), (xx if i else 0, 0, hh / 2), fr, coll, 0.004)
            o.parent = root
        o = _box(f"mullion_v_{side}_edge", (0.03, 0.04, hh), (sgn * half, 0, hh / 2), fr, coll, 0.004)
        o.parent = root
        for j in range(6):
            o = _box(f"mullion_h_{side}{j}", (half, 0.04, 0.028), (cx, 0, j * hh / 5), fr, coll, 0.004)
            o.parent = root
        g = _box(f"glass_{side}", (half, 0.006, hh), (cx, 0, hh / 2), glass, coll)
        g.parent = root
    # curtains: heavy drapes gathered to each side
    for side, x in (("l", wx0 - 0.18), ("r", wx1 + 0.18)):
        _curtain(f"curtain_{side}", (x, y - 0.12, 0), coll, mats["curtain"])
    _cyl("curtain_rod", 0.018, WIN_W + 1.0, (WIN_X, y - 0.14, z1 + 0.18), mats["brass"], coll, rot=(0, math.pi / 2, 0))
    return sash_l, sash_r


def _curtain(name, loc, coll, mat):
    """A drape as a pleated sheet: sin folds in plan, gathered at the top."""
    nx, nz = 48, 40
    width, height = 0.5, WIN_SILL + WIN_H + 0.25
    V, F = [], []
    for j in range(nz):
        z = height * j / (nz - 1)
        gather = 0.55 + 0.45 * (1 - j / (nz - 1)) ** 0.5
        for i in range(nx):
            u = i / (nx - 1)
            x = (u - 0.5) * width * gather
            yy = 0.045 * math.sin(u * 2 * math.pi * 5.5) * (0.6 + 0.4 * gather)
            V.append((x, yy, z))
    for j in range(nz - 1):
        for i in range(nx - 1):
            a = j * nx + i
            F.append((a, a + 1, a + nx + 1, a + nx))
    me = bpy.data.meshes.new(name)
    me.from_pydata(V, [], F)
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    coll.objects.link(ob)
    me.materials.append(mat)
    s = ob.modifiers.new("solid", "SOLIDIFY")
    s.thickness = 0.012
    C.subsurf(ob, 1, 1)
    return ob


# -------------------------------------------------------------- dressing

def bookcase(name, loc, width, coll, mats, rot_z=0.0, seed=0, titled=0.5):
    """A tall bookcase full of leather-bound books with gilt spines."""
    rng = random.Random(seed)
    root = bpy.data.objects.new(name, None)
    root.location = loc
    root.rotation_euler = (0, 0, math.radians(rot_z))
    coll.objects.link(root)
    depth, height, t = 0.34, 2.3, 0.035
    wood = mats["case"]
    parts = [
        _box(name + ".side_l", (t, depth, height), (-width / 2 + t / 2, 0, height / 2), wood, coll, 0.004),
        _box(name + ".side_r", (t, depth, height), (width / 2 - t / 2, 0, height / 2), wood, coll, 0.004),
        _box(name + ".back", (width, 0.015, height), (0, depth / 2 - 0.008, height / 2), wood, coll),
        _box(name + ".crown", (width + 0.08, depth + 0.05, 0.07), (0, -0.02, height + 0.035), wood, coll, 0.012),
        _box(name + ".plinth", (width + 0.04, depth + 0.03, 0.1), (0, -0.01, 0.05), wood, coll, 0.008),
    ]
    shelves = [0.1, 0.52, 0.94, 1.36, 1.78, 2.2]
    for z in shelves:
        parts.append(_box(f"{name}.shelf{z:.2f}", (width - 2 * t, depth - 0.02, 0.025), (0, -0.005, z), wood, coll, 0.003))
    leathers = [mats[k] for k in ("leather_red", "leather_brown", "leather_green", "leather_tan", "leather_black")]
    for si, z in enumerate(shelves[:-1]):
        x = -width / 2 + t + 0.01
        gap = shelves[si + 1] - z - 0.03
        while x < width / 2 - t - 0.04:
            if rng.random() < 0.04:           # a gap, a leaning book
                x += 0.06
                continue
            bw = rng.uniform(0.028, 0.06)
            bh = min(gap - 0.02, rng.uniform(0.24, 0.36))
            bd = rng.uniform(0.2, 0.26)
            m = rng.choice(leathers)
            b = _box(f"{name}.book{si}_{x:.3f}", (bw, bd, bh), (x + bw / 2, -depth / 2 + bd / 2 + 0.03, z + 0.0125 + bh / 2),
                     m, coll, 0.004)
            parts.append(b)
            # gilt bands across the spine
            for bz in (0.12, 0.88):
                parts.append(_box(f"{name}.band{si}_{x:.3f}_{bz}", (bw * 0.98, 0.002, 0.006),
                                  (x + bw / 2, -depth / 2 + 0.03 - 0.001, z + 0.0125 + bh * bz), mats["gilt"], coll))
            if bw > 0.034 and rng.random() < titled:
                title = rng.choice(TITLES)
                size = min(bw * 0.55, 0.022)
                tx = _text(f"{name}.title{si}_{x:.3f}", title,
                           (x + bw / 2, -depth / 2 + 0.03 - 0.0015, z + 0.0125 + bh * 0.52),
                           (math.pi / 2, math.pi / 2, 0), size, mats["gilt"], coll)
                tx.data.body = title if len(title) * size * 0.62 < bh * 0.7 else title[: max(3, int(bh * 0.7 / (size * 0.62)))]
                tx.rotation_euler = (math.radians(90), 0, 0)
                tx.rotation_euler.rotate(Euler((0, math.radians(-90), 0)))
                parts.append(tx)
            x += bw + rng.uniform(0.0, 0.004)
    for p in parts:
        p.parent = root
    return root


def stove(loc, coll, mats, rot_z=0.0):
    """A Petersburg tiled stove: white Delft-style tiles with blue motifs,
    a cornice, and a small iron door whose crack of fire is a light."""
    root = bpy.data.objects.new("stove", None)
    root.location = loc
    root.rotation_euler = (0, 0, math.radians(rot_z))
    coll.objects.link(root)
    tile = mats["tile"]
    parts = [
        _box("stove.base", (1.0, 0.8, 0.2), (0, 0, 0.1), mats["trim"], coll, 0.02),
        _box("stove.body", (0.9, 0.7, 2.2), (0, 0, 1.3), tile, coll, 0.01),
        _box("stove.band", (0.96, 0.76, 0.08), (0, 0, 1.1), tile, coll, 0.02),
        _box("stove.cornice", (1.02, 0.82, 0.12), (0, 0, 2.44), tile, coll, 0.03),
        _box("stove.crown", (0.8, 0.6, 0.18), (0, 0, 2.59), tile, coll, 0.04),
        _box("stove.door", (0.3, 0.02, 0.24), (0, -0.355, 0.55), mats["iron"], coll, 0.01),
    ]
    glow = _box("stove.glow", (0.24, 0.012, 0.03), (0, -0.362, 0.43), mats["fire"], coll)
    parts.append(glow)
    for p in parts:
        p.parent = root
    return root, glow


def slate(loc, coll, mats, rot_z=0.0):
    """The big slate on a sturdy easel. Its face is a plane named
    `slate.face` whose material takes an image sequence: the writing."""
    root = bpy.data.objects.new("slate", None)
    root.location = loc
    root.rotation_euler = (0, 0, math.radians(rot_z))
    coll.objects.link(root)
    wood = mats["case"]
    bw, bh = MK.SLATE_W, MK.SLATE_H
    tilt = math.radians(MK.SLATE_TILT)
    board = bpy.data.objects.new("slate.board", None)
    board.location = (0, 0, MK.SLATE_Z)
    board.rotation_euler = (tilt, 0, 0)
    coll.objects.link(board)
    board.parent = root
    parts = []
    for name, size, off in (("top", (bw + 0.08, 0.05, 0.05), (0, 0, bh + 0.025)),
                            ("bottom", (bw + 0.08, 0.05, 0.05), (0, 0, -0.025)),
                            ("left", (0.05, 0.05, bh), (-bw / 2 - 0.025, 0, bh / 2)),
                            ("right", (0.05, 0.05, bh), (bw / 2 + 0.025, 0, bh / 2))):
        o = _box("slate.frame_" + name, size, off, wood, coll, 0.008)
        o.parent = board
    o = _box("slate.back", (bw, 0.02, bh), (0, 0.012, bh / 2), mats["slate"], coll)
    o.parent = board
    # the writing surface: a plane facing -y with UVs 0..1
    me = bpy.data.meshes.new("slate.face")
    me.from_pydata([(-bw / 2, 0, 0), (bw / 2, 0, 0), (bw / 2, 0, bh), (-bw / 2, 0, bh)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, (u, v) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[li].uv = (u, v)
    face = bpy.data.objects.new("slate.face", me)
    face.location = (0, 0.0005 - 0.001, 0)
    coll.objects.link(face)
    face.parent = board
    face["size"] = (bw, bh)
    me.materials.append(mats["slate_face"])
    # chalk ledge with chalk and a rag
    o = _box("slate.ledge", (bw, 0.08, 0.02), (0, -0.04, -0.06), wood, coll, 0.004)
    o.parent = board
    for i, x in enumerate((-0.3, -0.26, 0.35)):
        c = _cyl(f"slate.chalk{i}", 0.006, 0.06, (x, -0.05, -0.045), mats["chalk"], coll, 12, rot=(0, math.pi / 2, 0.2 * i))
        c.parent = board
    # easel legs
    for sx in (-1, 1):
        o = _box(f"slate.leg{sx}", (0.05, 0.05, 1.75), (sx * (bw / 2 - 0.05), 0.02, 0.86), wood, coll, 0.006)
        o.rotation_euler = (tilt, 0, sx * math.radians(-3))
        o.parent = root
    o = _box("slate.leg_back", (0.05, 0.05, 1.7), (0, 0.42, 0.8), wood, coll, 0.006)
    o.rotation_euler = (math.radians(22), 0, 0)
    o.parent = root
    o = _box("slate.crossbar", (bw, 0.04, 0.04), (0, 0.1, 0.45), wood, coll, 0.006)
    o.parent = root
    return root, face


def desk_dressing(desk_top, coll, mats):
    """Papers with lines of writing, an inkwell, a quill, spectacles he no
    longer uses, and a stack of his letters."""
    x0, y0, z = desk_top
    rng = random.Random(3)
    objs = []
    for i in range(6):
        p = _box(f"paper{i}", (0.21, 0.297, 0.0008),
                 (x0 + rng.uniform(-0.2, 0.2), y0 + rng.uniform(-0.12, 0.12), z + 0.0005 + i * 0.0009),
                 mats["paper"], coll, rot=(0, 0, rng.uniform(-0.6, 0.6)))
        objs.append(p)
    ink = _cyl("inkwell", 0.03, 0.05, (x0 + 0.22, y0 + 0.16, z + 0.025), mats["glass_dark"], coll, 24)
    quill = _box("quill", (0.006, 0.28, 0.02), (x0 + 0.2, y0 + 0.1, z + 0.11), mats["feather"], coll, 0.003,
                 rot=(math.radians(55), 0, math.radians(20)))
    return objs


# ------------------------------------------------------------------ lights

def _point(name, loc, energy, color, radius, coll):
    ld = bpy.data.lights.new(name, "POINT")
    ld.energy = energy
    ld.color = color
    ld.shadow_soft_size = radius
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    coll.objects.link(lo)
    return lo


def _area(name, loc, target, energy, color, size, coll, shape="RECTANGLE", size_y=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.color = color
    ld.shape = shape
    ld.size = size
    if size_y:
        ld.size_y = size_y
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    coll.objects.link(lo)
    C.aim(lo, target)
    return lo


def lights(time, coll, marks):
    L = {}
    if time == "night":
        # candles on the side table: the key
        for i, p in enumerate(marks["candle_flames"]):
            L[f"candle{i}"] = _point(f"candle{i}", p, 9.0, (1.0, 0.62, 0.3), 0.012, coll)
        # the stove's crack of fire
        L["stove"] = _area("stove_fire", marks["stove_fire"], Vector(marks["stove_fire"]) + Vector((0.5, -1, -0.2)),
                           40.0, (1.0, 0.4, 0.12), 0.25, coll)
        # moonlight through the window, cool and hard enough to cast the panes
        L["moon"] = _area("moon", (WIN_X + 0.8, D / 2 + 2.5, WIN_SILL + 2.4), (WIN_X - 0.5, 0.0, 0.4),
                          260.0, (0.55, 0.68, 1.0), 0.6, coll)
        # a soft cold fill bouncing off the snow outside
        L["snow_bounce"] = _area("snow_bounce", (WIN_X, D / 2 - 0.1, WIN_SILL + 0.3), (WIN_X, 0, 1.5),
                                 18.0, (0.6, 0.72, 1.0), 1.2, coll, size_y=0.3)
        # warm fill from the candles' direction, larger, dim
        L["warm_fill"] = _area("warm_fill", (2.0, -1.5, 2.2), (0, 0.6, 1.0), 45.0, (1.0, 0.7, 0.45), 2.0, coll)
        # the lighter's cheat: a soft warm key on Euler's face from the
        # candles' side and in front, so his face models instead of going to
        # silhouette whenever the camera is on the far side of the flames
        head = MK.euler_point((0, -0.06, 1.2))
        f = MK._rz((0, -1, 0), MK.EULER_YAW)
        left = MK._rz((1, 0, 0), MK.EULER_YAW)
        key = [head[i] + f[i] * 0.8 + left[i] * 0.7 for i in range(3)]
        key[2] += 0.5
        L["euler_key"] = _area("euler_key", key, head, 16.0, (1.0, 0.72, 0.48), 0.5, coll)
        rim = [head[i] - f[i] * 0.9 - left[i] * 0.6 for i in range(3)]
        rim[2] += 0.6
        L["euler_rim"] = _area("euler_rim", rim, head, 14.0, (0.65, 0.75, 1.0), 0.3, coll)
    else:
        L["sun"] = _area("sun", (WIN_X + 1.2, D / 2 + 3.5, WIN_SILL + 3.2), (WIN_X - 0.8, -0.5, 0.2),
                         1400.0, (1.0, 0.86, 0.68), 0.8, coll)
        L["sky_fill"] = _area("sky_fill", (WIN_X, D / 2 - 0.05, WIN_SILL + 1.0), (WIN_X, 0, 1.0),
                              160.0, (0.78, 0.86, 1.0), 1.2, coll, size_y=1.8)
        L["room_fill"] = _area("room_fill", (1.5, -2.2, 2.6), (0, 0.5, 1.0), 120.0, (1.0, 0.95, 0.9), 3.0, coll)
    return L


def exterior(time, coll, mats):
    """What the window looks out on: the snowy street, the houses opposite
    with their lit windows, the sky."""
    y0 = D / 2 + 3.5
    rng = random.Random(7)
    _box("street_snow", (30, 14, 0.1), (0, D / 2 + 6, -0.6), mats["snow"], coll)
    x = -10.0
    i = 0
    while x < 10:
        w = rng.uniform(4.5, 7.0)
        h = rng.uniform(5.5, 8.0)
        col = rng.choice(["facade_yellow", "facade_green", "facade_pink", "facade_blue"])
        _box(f"house{i}", (w - 0.1, 3, h), (x + w / 2, y0 + 1.5, h / 2 - 0.6), mats[col], coll)
        _box(f"roof{i}", (w, 3.4, 0.35), (x + w / 2, y0 + 1.5, h - 0.45), mats["snow"], coll)
        for fz in (1.0, 3.2, 5.2):
            if fz > h - 1.2:
                continue
            nx = int(w / 1.3)
            for k in range(nx):
                wx = x + (k + 0.5) * w / nx
                lit = rng.random() < (0.35 if time == "night" else 0.0)
                m = mats["window_lit"] if lit else mats["window_dark"]
                _box(f"hw{i}_{fz}_{k}", (0.6, 0.05, 1.1), (wx, y0 - 0.02, fz), m, coll)
                _box(f"hws{i}_{fz}_{k}", (0.75, 0.2, 0.06), (wx, y0 - 0.08, fz - 0.58), mats["snow"], coll)
        x += w
        i += 1
    # the sky: a big dome of gradient with stars at night
    bpy.ops.mesh.primitive_uv_sphere_add(radius=60, location=(0, 0, 0), segments=48, ring_count=24)
    sky = bpy.context.active_object
    sky.name = "sky"
    for c in sky.users_collection:
        c.objects.unlink(sky)
    coll.objects.link(sky)
    sky.data.materials.append(mats["sky"])
    sky.visible_shadow = False
    return sky


# ---------------------------------------------------------------- materials

def materials(time):
    M = {}
    M["floor"] = _textured("st.floor", "herringbone_parquet", scale=0.6, tint=(0.75, 0.55, 0.4), bump=0.3)
    M["wall"] = _textured("st.wall", "plastered_wall_04", scale=0.5, tint=(0.62, 0.72, 0.6), bump=0.2)
    M["ceiling"] = C.mat_plain("st.ceiling", (0.7, 0.68, 0.62), rough=0.9)
    M["panel"] = _textured("st.panel", "dark_wooden_planks", scale=0.8, tint=(0.8, 0.62, 0.45), bump=0.2)
    M["trim"] = C.mat_plain("st.trim", (0.72, 0.7, 0.62), rough=0.45)
    M["beam"] = _textured("st.beam", "wood_planks", scale=0.8, tint=(0.5, 0.36, 0.25), bump=0.3)
    M["case"] = _textured("st.case", "dark_wooden_planks", scale=1.2, tint=(0.75, 0.5, 0.35), bump=0.15)
    M["glass"] = C.mat_plain("st.glass", (0.85, 0.9, 0.95), rough=0.05, transmission=1.0, ior=1.45, alpha=0.25)
    M["glass_dark"] = C.mat_plain("st.glass_dark", (0.02, 0.03, 0.05), rough=0.1, coat=1.0)
    M["curtain"] = C.mat_plain("st.curtain", (0.25, 0.05, 0.06), rough=0.7, sheen=0.8)
    M["brass"] = C.mat_plain("st.brass", (0.8, 0.6, 0.3), rough=0.25, metal=1.0)
    M["gilt"] = C.mat_plain("st.gilt", (0.85, 0.62, 0.25), rough=0.3, metal=1.0)
    M["iron"] = C.mat_plain("st.iron", (0.05, 0.05, 0.05), rough=0.5, metal=0.8)
    M["fire"] = C.mat_plain("st.fire", (1, 0.4, 0.1), emit=(1.0, 0.35, 0.08), emit_strength=30.0)
    M["slate"] = C.mat_plain("st.slate", (0.035, 0.04, 0.045), rough=0.8)
    M["chalk"] = C.mat_plain("st.chalk", (0.9, 0.9, 0.88), rough=0.95)
    M["paper"] = C.mat_plain("st.paper", (0.82, 0.76, 0.62), rough=0.9, sss=0.1)
    M["feather"] = C.mat_plain("st.feather", (0.85, 0.83, 0.78), rough=0.6, sheen=1.0)
    for name, rgb in (("leather_red", (0.26, 0.04, 0.03)), ("leather_brown", (0.18, 0.08, 0.035)),
                      ("leather_green", (0.04, 0.1, 0.05)), ("leather_tan", (0.35, 0.18, 0.08)),
                      ("leather_black", (0.03, 0.025, 0.02))):
        M[name] = C.mat_plain("st." + name, rgb, rough=0.55, sheen=0.2)
    M["tile"] = _tile_material()
    M["snow"] = C.mat_plain("st.snow", (0.85, 0.88, 0.95), rough=0.6, sss=0.3)
    for name, rgb in (("facade_yellow", (0.7, 0.5, 0.18)), ("facade_green", (0.3, 0.5, 0.35)),
                      ("facade_pink", (0.7, 0.4, 0.35)), ("facade_blue", (0.35, 0.45, 0.6))):
        M[name] = C.mat_plain("st." + name, rgb, rough=0.85)
    M["window_lit"] = C.mat_plain("st.window_lit", (1, 0.7, 0.35), emit=(1.0, 0.6, 0.25), emit_strength=4.0)
    M["window_dark"] = C.mat_plain("st.window_dark", (0.03, 0.04, 0.06), rough=0.1)
    M["sky"] = _sky_material(time)
    M["slate_face"] = slate_material()
    return M


def _tile_material():
    """White glazed tiles with a blue motif, from a procedural grid."""
    m = bpy.data.materials.new("st.tile")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.0
    br.inputs["Scale"].default_value = 5.5
    br.inputs["Mortar Size"].default_value = 0.01
    br.inputs["Color1"].default_value = (0.86, 0.85, 0.8, 1)
    br.inputs["Color2"].default_value = (0.82, 0.82, 0.78, 1)
    br.inputs["Mortar"].default_value = (0.5, 0.48, 0.44, 1)
    br.inputs["Brick Width"].default_value = 0.5
    br.inputs["Row Height"].default_value = 0.5
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    # blue motif: a wave texture ring per tile
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (11, 11, 11)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    fr = nt.nodes.new("ShaderNodeVectorMath")
    fr.operation = "FRACTION"
    nt.links.new(mp.outputs["Vector"], fr.inputs[0])
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = (0.5, 0.5, 0.5)
    nt.links.new(fr.outputs["Vector"], sub.inputs[0])
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    nt.links.new(sub.outputs["Vector"], ln.inputs[0])
    ring = nt.nodes.new("ShaderNodeValToRGB")
    ring.color_ramp.elements[0].position = 0.28
    ring.color_ramp.elements[0].color = (0.08, 0.16, 0.5, 1)
    ring.color_ramp.elements[1].position = 0.33
    ring.color_ramp.elements[1].color = (1, 1, 1, 1)
    e = ring.color_ramp.elements.new(0.18)
    e.color = (1, 1, 1, 1)
    e = ring.color_ramp.elements.new(0.22)
    e.color = (0.1, 0.2, 0.55, 1)
    nt.links.new(ln.outputs["Value"], ring.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(br.outputs["Color"], mix.inputs["A"])
    nt.links.new(ring.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.18
    p.inputs["Coat Weight"].default_value = 0.6
    return m


def _sky_material(time):
    m = bpy.data.materials.new("st.sky")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED":
            nt.nodes.remove(n)
    out = nt.nodes["Material Output"]
    em = nt.nodes.new("ShaderNodeEmission")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nrm = nt.nodes.new("ShaderNodeVectorMath")
    nrm.operation = "NORMALIZE"
    nt.links.new(tc.outputs["Object"], nrm.inputs[0])
    nt.links.new(nrm.outputs["Vector"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    cr = ramp.color_ramp
    if time == "night":
        cr.elements[0].color = (0.05, 0.07, 0.14, 1)
        cr.elements[1].position = 0.5
        cr.elements[1].color = (0.005, 0.008, 0.03, 1)
        strength = 1.0
    else:
        cr.elements[0].color = (0.95, 0.75, 0.55, 1)
        cr.elements[1].position = 0.45
        cr.elements[1].color = (0.35, 0.55, 0.9, 1)
        strength = 2.5
    col = ramp.outputs["Color"]
    if time == "night":
        # stars: sparse bright points from a Voronoi
        vo = nt.nodes.new("ShaderNodeTexVoronoi")
        vo.inputs["Scale"].default_value = 180
        nt.links.new(nrm.outputs["Vector"], vo.inputs["Vector"])
        st = nt.nodes.new("ShaderNodeMath")
        st.operation = "LESS_THAN"
        st.inputs[1].default_value = 0.035
        nt.links.new(vo.outputs["Distance"], st.inputs[0])
        up = nt.nodes.new("ShaderNodeMath")
        up.operation = "GREATER_THAN"
        up.inputs[1].default_value = 0.1
        nt.links.new(sep.outputs["Z"], up.inputs[0])
        both = nt.nodes.new("ShaderNodeMath")
        both.operation = "MULTIPLY"
        nt.links.new(st.outputs[0], both.inputs[0])
        nt.links.new(up.outputs[0], both.inputs[1])
        add = nt.nodes.new("ShaderNodeMix")
        add.data_type = "RGBA"
        add.blend_type = "ADD"
        nt.links.new(both.outputs[0], add.inputs["Factor"])
        nt.links.new(col, add.inputs["A"])
        add.inputs["B"].default_value = (2.5, 2.5, 2.8, 1)
        col = add.outputs["Result"]
    nt.links.new(col, em.inputs["Color"])
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def slate_material():
    """Slate with the writing on it: an image (sequence) of chalk over the
    stone, mixed into the surface so the room's light falls on the chalk."""
    m = bpy.data.materials.new("st.slate_face")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = "writing"
    tex.interpolation = "Cubic"
    # a generated colour survives a save; hand-set pixels do not, and an
    # opaque placeholder reads as a slate covered in chalk
    blank = bpy.data.images.get("slate_blank") or bpy.data.images.new("slate_blank", 4, 4, alpha=True)
    blank.generated_color = (0.0, 0.0, 0.0, 0.0)
    tex.image = blank
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 60
    base = nt.nodes.new("ShaderNodeValToRGB")
    base.color_ramp.elements[0].color = (0.03, 0.035, 0.04, 1)
    base.color_ramp.elements[1].color = (0.06, 0.065, 0.07, 1)
    nt.links.new(noise.outputs["Fac"], base.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(base.outputs["Color"], mix.inputs["A"])
    mix.inputs["B"].default_value = (0.85, 0.86, 0.84, 1)
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(tex.outputs["Alpha"], rough.inputs["Value"])
    rough.inputs["To Min"].default_value = 0.55
    rough.inputs["To Max"].default_value = 0.95
    nt.links.new(rough.outputs["Result"], p.inputs["Roughness"])
    return m


# ------------------------------------------------------------------ build

def build(time="night", coll=None):
    coll = coll or C.collection("study")
    mats = materials(time)
    room(coll, mats)
    sash_l, sash_r = window(coll, mats)
    door(coll, mats)
    marks = {}

    # Euler's corner: the chair turned a little toward the slate
    _append("ArmChair_01", coll, MK.CHAIR, MK.CHAIR_YAW)
    marks["euler"] = dict(loc=MK.EULER, yaw=MK.EULER_YAW)

    slate_root, slate_face = slate(MK.SLATE_ROOT, coll, mats, rot_z=MK.SLATE_YAW)
    marks["slate_face"] = slate_face.name

    # side table with the candelabra, books, tea
    _append("WoodenTable_01", coll, (1.25, 0.95, 0), 90, drop=None)
    table_top_z = 0.55
    root, obs = _append("brass_candleholders", coll, (1.3, 0.95, table_top_z), -90)
    # keep only the big candelabra
    for o in obs:
        if not o.name.endswith("_03") and "candleholder" in o.name:
            bpy.data.objects.remove(o, do_unlink=True)
    marks["candle_flames"] = _flame_points(coll)
    desk_dressing((1.2, 0.8, table_top_z), coll, mats)
    _append("tea_set_01", coll, (1.25, 1.35, table_top_z), 90, scale=0.6)

    # bookcases along the back wall either side of the window, and one on the left
    bookcase("case_back_l", (-1.1, D / 2 - 0.2, 0), 1.3, coll, mats, seed=1)
    bookcase("case_back_ll", (-2.4, D / 2 - 0.2, 0), 1.1, coll, mats, seed=2)
    bookcase("case_left", (-W / 2 + 0.2, 0.9, 0), 1.3, coll, mats, rot_z=90, seed=3)
    st, glow = stove((2.35, D / 2 - 0.55, 0), coll, mats, rot_z=0)
    marks["stove_fire"] = tuple(st.location + Vector((0, -0.4, 0.45)))
    # Poly Haven models face -y: on the left wall (-x) they turn +90 to face
    # the room, on the right wall -90. The first dressing had these the wrong
    # way round and the clock showed the room its back -- no dial, no numerals.
    _append("vintage_grandfather_clock_01", coll, (-W / 2 + 0.3, -0.45, 0), 90)
    _append("vintage_cabinet_01", coll, (W / 2 - 0.35, -0.2, 0), -90)
    _append("fancy_picture_frame_01", coll, (W / 2 - 0.03, -0.2, 2.45), -90, scale=1.6)
    _append("treasure_chest", coll, (1.5, D / 2 - 0.45, 0), 0, scale=0.8)
    _append("brass_goblets", coll, (W / 2 - 0.35, -0.5, 1.02), -90, scale=0.7)
    for i, x in enumerate((-0.4, 0.9)):
        _append("wooden_candlestick", coll, (x, D / 2 - 0.12, WIN_SILL + 0.03), 0)

    exterior(time, coll, mats)
    L = lights(time, coll, marks)

    # marks for Cinnamon and the cameras (world positions)
    marks.update({
        "cinnamon_home": MK.CINNAMON["home"],
        "sash_left": sash_l.name,
        "sash_right": sash_r.name,
        "door": (-W / 2 + 0.05, -1.8, 1.0),
        "stove_glow": glow.name,
    })
    return dict(marks=marks, lights=L, coll=coll)


def _flame_points(coll):
    """Put a flame on every candle of the candelabra; return their tips."""
    cands = [o for o in coll.objects if "candleholder_03" in o.name]
    pts = []
    if not cands:
        return pts
    ob = cands[0]
    bpy.context.view_layer.update()
    mw = ob.matrix_world
    V = np.array([list(mw @ v.co) for v in ob.data.vertices])
    # candle tops: the highest vertices clustered in xy
    top = V[V[:, 2] > V[:, 2].max() - 0.12]
    clusters = []
    for p in top[np.argsort(-top[:, 2])]:
        if all(np.linalg.norm(p[:2] - c[:2]) > 0.03 for c in clusters):
            clusters.append(p)
        if len(clusters) >= 5:
            break
    mat = bpy.data.materials.get("st.flame") or C.mat_plain("st.flame", (1, 0.7, 0.3), emit=(1.0, 0.62, 0.22),
                                                             emit_strength=40.0)
    for i, c in enumerate(clusters):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.008, location=(c[0], c[1], c[2] + 0.018), segments=16, ring_count=8)
        f = bpy.context.active_object
        f.name = f"flame{i}"
        f.scale = (0.8, 0.8, 2.2)
        for cc in f.users_collection:
            cc.objects.unlink(f)
        coll.objects.link(f)
        f.data.materials.append(mat)
        f.visible_shadow = False
        pts.append((c[0], c[1], c[2] + 0.03))
    return pts
