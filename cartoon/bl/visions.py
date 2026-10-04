"""The taste visions: what a formula tastes like, drawn as light.

Runs inside Blender on the prepared vision set (a dark void with Cinnamon
in it, eyes shut). Each vision is a function that builds its own glowing
things and animates them over the shot; Cinnamon's face is posed for the
taste -- bliss for the soup that settles, a scrunch for the one that burns,
a tear for the nothing.

Everything that carries writing carries it: the rings are numbered, the
jars are labelled with their primes, the wheel with its flavours.
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Vector

import fonts
from cartoon.bl import common as C, eyes as E

# roles in fonts.py: OFL fonts fetched on first use, never committed
FONT = "caslon"
MATH_FONT = "italic"
CENTER = Vector((0.0, 0.0, 1.2))


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def glow(name, rgb, strength=6.0, alpha=1.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED":
            nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    em.name = "emit"
    if alpha < 1.0:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs["Fac"].default_value = alpha
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
        m.surface_render_method = "BLENDED"
    else:
        nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def text(name, body, loc, size, mat, font=FONT, rot=(math.radians(90), 0, 0)):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = 0.004
    cu.font = bpy.data.fonts.load(fonts.path(font), check_existing=True)
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.rotation_euler = rot
    bpy.context.scene.collection.objects.link(ob)
    cu.materials.append(mat)
    return ob


def _link(ob):
    for c in ob.users_collection:
        c.objects.unlink(ob)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def torus(name, R, r, loc, mat, rot=(math.radians(90), 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=96, minor_segments=16,
                                     location=loc, rotation=rot)
    ob = _link(bpy.context.active_object)
    ob.name = name
    ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return ob


def sphere(name, r, loc, mat, seg=32):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=seg, ring_count=seg // 2)
    ob = _link(bpy.context.active_object)
    ob.name = name
    ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return ob


def box(name, size, loc, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = _link(bpy.context.active_object)
    ob.name = name
    ob.scale = size
    ob.data.materials.append(mat)
    return ob


def cyl(name, r, h, loc, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=40, location=loc, rotation=rot)
    ob = _link(bpy.context.active_object)
    ob.name = name
    ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return ob


def key_scale(ob, frames, fn):
    """Scale by fn(f) times the object's own scale (a box keeps its shape)."""
    base = Vector(ob.scale)
    for f in frames:
        s = max(1e-4, fn(f))
        ob.scale = base * s
        ob.keyframe_insert("scale", frame=f)


def key_loc(ob, frames, fn):
    for f in frames:
        ob.location = fn(f)
        ob.keyframe_insert("location", frame=f)


# ------------------------------------------------------------ Cinnamon

def pose_cinnamon(f0, f1, fps, mood):
    """Eyes shut, floating, the face of the taste."""
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE" and o.get("character") == "cinnamon"), None)
    if arm is None:
        return
    body = bpy.data.objects[arm["head_mesh"]]
    kb = body.data.shape_keys.key_blocks
    faces = {
        "bliss": dict(smile=0.9, lips_close=1.0, **{"cheek_up.L": 0.8, "cheek_up.R": 0.8, "brow_up.L": 0.3, "brow_up.R": 0.3},
                      nostril_flare=0.3),
        "burn": dict(frown=0.7, mouth_wide=0.6, lips_close=0.0, upper_up=0.8, lower_down=0.8, nose_scrunch=0.8,
                     **{"brow_down.L": 1.0, "brow_down.R": 1.0}),
        "wonder": dict(smile=0.4, lips_close=0.3, mouth_narrow=0.6, **{"brow_up.L": 1.0, "brow_up.R": 1.0}),
        "moved": dict(smile=0.35, lips_close=1.0, brow_inner=1.0, **{"cheek_up.L": 0.4, "cheek_up.R": 0.4}),
    }
    face = faces[mood]
    for k in kb[1:]:
        k.value = face.get(k.name, 0.0)
        k.keyframe_insert("value", frame=f0)
    for s, e in arm["eyes"].items():
        lu = bpy.data.objects[e["lid_up"]]
        ll = bpy.data.objects[e["lid_lo"]]
        shut = 0.0
        lu.rotation_euler = (-math.radians(-8 + 58 * shut), 0, 0)
        ll.rotation_euler = (math.radians(3 + 17 * 0.2), 0, 0)
        lu.keyframe_insert("rotation_euler", frame=f0)
        ll.keyframe_insert("rotation_euler", frame=f0)
    arm.location = CENTER
    arm.rotation_euler = (0, 0, 0)
    for f in range(f0, f1 + 1, 2):
        t = f / fps
        arm.location = CENTER + Vector((0, 0, 0.03 * math.sin(t * 2.2)))
        arm.rotation_euler = (0.05 * math.sin(t * 1.3), 0.04 * math.sin(t * 1.7), 0.15 * math.sin(t * 0.6))
        arm.keyframe_insert("location", frame=f)
        arm.keyframe_insert("rotation_euler", frame=f)
    if mood == "burn":
        # shaking, faster and faster
        for f in range(f0, f1 + 1):
            t = (f - f0) / fps
            arm.location = CENTER + Vector((0.01 * t * math.sin(f * 2.3), 0, 0.01 * t * math.sin(f * 3.1)))
            arm.keyframe_insert("location", frame=f)
    return arm


def camera(f0, f1, dist=2.4, lens=40, height=0.0):
    cd = bpy.data.cameras.new("shot")
    cd.lens = lens
    cam = bpy.data.objects.new("shot", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    for f, k in ((f0, 0.0), (f1, 1.0)):
        cam.location = CENTER + Vector((0.3 - 0.1 * k, -dist + 0.35 * k, 0.15 + height))
        C.aim(cam, CENTER + Vector((0, 0, 0.1)))
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    return cam


# ------------------------------------------------------------ the visions

def basel(f0, f1, fps):
    """Rings of flavour, each a quarter, a ninth, a sixteenth of the first,
    arriving faster and smaller until they settle into one warm glow."""
    pose_cinnamon(f0, f1, fps, "bliss")
    n = 12
    T = (f1 - f0) / fps
    cols = [(1.0, 0.45, 0.12), (1.0, 0.6, 0.18), (1.0, 0.72, 0.25), (1.0, 0.82, 0.4)]
    rings = []
    for k in range(1, n + 1):
        m = glow(f"v.basel{k}", cols[min(k - 1, 3)], 1.6 + k * 0.15)
        R = 1.25 / math.sqrt(k)                 # area goes as 1/k^2... radius as 1/k
        R = 0.35 + 1.1 / k
        ring = torus(f"v.ring{k}", R, 0.006 + 0.012 / k, CENTER + Vector((0, 0.4, 0.05)), m)
        t_on = 0.25 + 2.4 * (1 - 1.0 / k)
        f_on = f0 + int(t_on * fps)
        key_scale(ring, [f0, f_on, f_on + 6, f_on + 12, f1],
                  lambda f, f_on=f_on: 0.0 if f < f_on else (1.3 if f < f_on + 6 else 1.0))
        rings.append(ring)
        if k <= 4:
            # slashed, all four: no font here has a one-ninth glyph, and a
            # missing glyph renders as nothing
            # the sum building in a column at the right as each ring
            # arrives -- on the rings themselves, which mostly run past the
            # frame, the labels were specks at its edge
            lab = ["1", "+ 1/4", "+ 1/9", "+ 1/16"][k - 1]
            tx = text(f"v.basel_lab{k}", lab, CENTER + Vector((0.56, -0.1, 0.4 - 0.16 * (k - 1))), 0.11,
                      glow("v.lab", (1, 0.9, 0.7), 4.0), font=FONT)
            # nothing until its ring arrives: keyed only at the start and at
            # the ring, it grew from nothing over the whole wait
            key_scale(tx, [f0, f_on - 1, f_on, f_on + 4, f1],
                      lambda f, f_on=f_on: 0.0 if f < f_on else (1.15 if f < f_on + 4 else 1.0))
    # the settled glow and its name
    core = sphere("v.basel_core", 0.3, CENTER + Vector((0, 0.45, 0.05)), glow("v.core", (1.0, 0.75, 0.4), 1.0, 0.3))
    f_set = f0 + int(3.2 * fps)
    key_scale(core, [f0, f_set, f_set + 20, f1], lambda f: 0.0 if f < f_set else (1.0 if f > f_set + 15 else 0.6))
    # the sum's answer, under the column -- where the camera sees it: at
    # 0.72 up it was above the frame in every cut
    tx = text("v.basel_name", "= π²/6", CENTER + Vector((0.56, -0.15, 0.4 - 0.16 * 4 - 0.04)), 0.14,
              glow("v.name", (1, 0.95, 0.8), 6.0), font=MATH_FONT)
    key_scale(tx, [f0, f_set + 9, f_set + 10, f_set + 16, f1],
              lambda f: 0.0 if f < f_set + 10 else (1.2 if f < f_set + 16 else 1.0))
    camera(f0, f1)


def harmonic(f0, f1, fps):
    """A staircase of flavour: each step smaller, and yet it keeps climbing,
    greener to hotter to burning, off the top of the frame."""
    pose_cinnamon(f0, f1, fps, "burn")
    n = 40
    x0 = -1.3
    z = 0.4
    for k in range(1, n + 1):
        h = 0.32 / k ** 0.35
        w = 0.07
        heat = min(1.0, k / 25)
        col = (0.3 + 0.7 * heat, 0.9 - 0.7 * heat, 0.2 - 0.15 * heat)
        m = glow(f"v.step{k}", col, 1.5 + 3 * heat)
        b = box(f"v.step{k}", (w, 0.06, h), (x0 + k * 0.066, 0.6, z + h / 2), m)
        z += h * 0.55
        f_on = f0 + int((0.2 + 4.2 * math.sqrt(k / n)) * fps)
        key_scale(b, [f0, f_on, f_on + 4, f1], lambda f, f_on=f_on: 0.0 if f < f_on else 1.0)
    tx = text("v.harm_sum", "1 + ½ + ⅓ + ¼ + …", CENTER + Vector((0, -0.2, -0.75)), 0.13,
              glow("v.hsum", (1, 0.85, 0.6), 4.0))
    key_scale(tx, [f0, f0 + 6, f1], lambda f: 0.0 if f < f0 + 6 else 1.0)
    # upright, as infinity always is in mathematics (and the italic has none)
    inf = text("v.harm_inf", "∞", CENTER + Vector((0.95, -0.1, 0.75)), 0.35, glow("v.inf", (1, 0.25, 0.1), 9.0),
               font=FONT)
    f_inf = f1 - int(1.3 * fps)
    key_scale(inf, [f0, f_inf, f_inf + 6, f1], lambda f: 0.0 if f < f_inf else (1.4 if f < f_inf + 6 else 1.0))
    # sparks
    rng = np.random.default_rng(3)
    for i in range(40):
        s = sphere(f"v.spark{i}", 0.01, CENTER, glow("v.spark", (1, 0.5, 0.15), 12.0), seg=8)
        t0 = rng.uniform(1.5, 4.5)
        d = Vector((rng.uniform(-1, 1), rng.uniform(-0.3, 0.3), rng.uniform(0.2, 1)))
        fs = f0 + int(t0 * fps)
        key_loc(s, range(f0, f1 + 1, 3), lambda f, d=d, fs=fs: CENTER + Vector((0, 0.3, 0.6)) +
                d * (0 if f < fs else (f - fs) / fps * 0.9))
        key_scale(s, [f0, fs, fs + 10, fs + 20], lambda f, fs=fs: 0.0 if f < fs or f > fs + 18 else 1.0)
    camera(f0, f1, dist=2.8, lens=35)


def product(f0, f1, fps):
    """The pages of a cookbook -- every number's recipe -- fly up and fold
    themselves into a rack of spice jars, one per prime, going on for ever."""
    pose_cinnamon(f0, f1, fps, "wonder")
    rng = np.random.default_rng(7)
    page_m = glow("v.page", (1.0, 0.95, 0.85), 1.6)
    ink = glow("v.ink", (0.3, 0.2, 0.1), 0.5)
    primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43]
    jar_cols = [(0.95, 0.9, 0.9), (0.9, 0.85, 0.3), (0.95, 0.5, 0.6), (0.6, 0.3, 0.9), (0.3, 0.85, 0.5),
                (1.0, 0.55, 0.2), (0.4, 0.7, 1.0)]
    T = (f1 - f0) / fps
    for i in range(36):
        p = box(f"v.pagep{i}", (0.16, 0.002, 0.22), CENTER, page_m)
        a = rng.uniform(0, 2 * math.pi)
        r0 = rng.uniform(0.3, 0.6)
        j = i % len(primes)
        target = _jar_pos(j)

        def at(f, a=a, r0=r0, target=target, i=i):
            t = (f - f0) / fps
            k = ease((t - 2.0 - 0.02 * i) / 1.6)
            swirl = CENTER + Vector((math.cos(a + t * 2.5) * (r0 + t * 0.25), 0.3 + 0.2 * math.sin(a * 2),
                                     -0.3 + t * 0.35 + 0.1 * math.sin(a + t * 3)))
            return swirl.lerp(target, k)
        key_loc(p, range(f0, f1 + 1, 2), at)
        key_scale(p, [f0, f0 + int(0.2 * fps) + i, f0 + int((3.6 + 0.02 * i) * fps), f1],
                  lambda f, i=i: 0.0 if f < f0 + int(0.2 * fps) + i else (1.0 if f < f0 + int((3.6 + 0.02 * i) * fps) else 0.0))
        for f in range(f0, f1 + 1, 4):
            p.rotation_euler = (math.sin(f * 0.13 + i) * 1.2, math.cos(f * 0.1 + i) * 0.8, f * 0.05 + i)
            p.keyframe_insert("rotation_euler", frame=f)
    for j, pr in enumerate(primes):
        pos = _jar_pos(j)
        col = jar_cols[j % len(jar_cols)]
        jm = glow(f"v.jar{j}", col, 3.0, 0.85)
        jar = cyl(f"v.jar{j}", 0.065, 0.16, pos, jm)
        lid = cyl(f"v.lid{j}", 0.07, 0.03, pos + Vector((0, 0, 0.095)), glow("v.lid", (0.9, 0.7, 0.35), 4.0))
        lab = text(f"v.jarlab{j}", str(pr), pos + Vector((0, -0.07, 0.0)), 0.06, glow("v.jarlab", (1, 1, 1), 6.0))
        f_on = f0 + int((3.0 + 0.12 * j) * fps)
        for ob in (jar, lid, lab):
            key_scale(ob, [f0, f_on, f_on + 5, f1], lambda f, f_on=f_on: 0.0 if f < f_on else (1.2 if f < f_on + 5 else 1.0))
    tx = text("v.prod_eq", "every number  =  only the primes", CENTER + Vector((0, -0.4, -0.85)), 0.09,
              glow("v.peq", (1, 0.9, 0.7), 4.0))
    key_scale(tx, [f0, f0 + int(4.2 * fps), f1], lambda f: 0.0 if f < f0 + int(4.2 * fps) else 1.0)
    camera(f0, f1, dist=2.9, lens=35)


def _jar_pos(j):
    """A shelf curving away into the dark: jars get smaller with distance."""
    a = -0.9 + j * 0.2
    return CENTER + Vector((1.1 * math.sin(a) * (1 + j * 0.08), 0.5 + j * 0.35, -0.55 + 0.02 * j))


def wheel(f0, f1, fps):
    """The flavour wheel. e is bread rising; i turns it; round it goes,
    sweet, sour, bitter, and at pi, halfway round, the opposite of one."""
    pose_cinnamon(f0, f1, fps, "wonder")
    R = 1.0
    c = CENTER + Vector((0, 0.7, 0.05))
    sectors = [("SWEET", (1.0, 0.45, 0.65)), ("SOUR", (0.75, 0.95, 0.3)),
               ("BITTER", (0.25, 0.55, 0.5)), ("SALT", (0.7, 0.85, 1.0))]
    for i, (name, col) in enumerate(sectors):
        a0 = math.radians(-45 + 90 * i)
        verts = [(0, 0, 0)] + [(R * math.cos(a0 + math.radians(90) * s / 24), 0, R * math.sin(a0 + math.radians(90) * s / 24))
                               for s in range(25)]
        faces = [(0, s + 1, s + 2) for s in range(24)]
        me = bpy.data.meshes.new(f"v.sector{i}")
        me.from_pydata(verts, [], faces)
        ob = bpy.data.objects.new(f"v.sector{i}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = c + Vector((0, 0.01 * i, 0))
        me.materials.append(glow(f"v.sec{i}", col, 1.3, 0.55))
        am = a0 + math.radians(45)
        text(f"v.seclab{i}", name, c + Vector((0.72 * R * math.cos(am), -0.02, 0.72 * R * math.sin(am))), 0.08,
             glow("v.seclabm", (1, 1, 1), 3.0))
    text("v.one", "1", c + Vector((R * 1.12, -0.02, 0)), 0.14, glow("v.onem", (1, 1, 0.9), 6.0), font=MATH_FONT)
    minus = text("v.minus", "−1", c + Vector((-R * 1.18, -0.02, 0)), 0.14, glow("v.minusm", (1, 0.85, 0.5), 8.0),
                 font=MATH_FONT)
    # the comet: rising bread, golden, going round from 1 to -1
    comet = sphere("v.comet", 0.06, c, glow("v.cometm", (1.0, 0.75, 0.35), 12.0))
    T = (f1 - f0) / fps
    trail = []
    for k in range(14):
        trail.append(sphere(f"v.trail{k}", 0.05 * (1 - k / 16), c, glow("v.trailm", (1.0, 0.7, 0.3), 6.0 * (1 - k / 14)), seg=12))

    def ang(f):
        t = (f - f0) / fps
        return math.pi * ease((t - 0.6) / (T - 1.8))
    key_loc(comet, range(f0, f1 + 1, 1), lambda f: c + Vector((R * 0.92 * math.cos(ang(f)), -0.05, R * 0.92 * math.sin(ang(f)))))
    for k, s in enumerate(trail):
        key_loc(s, range(f0, f1 + 1, 1), lambda f, k=k: c + Vector((R * 0.92 * math.cos(ang(max(f0, f - 2 * (k + 1)))), -0.04,
                                                                      R * 0.92 * math.sin(ang(max(f0, f - 2 * (k + 1)))))))
    f_end = f1 - int(1.0 * fps)
    key_scale(minus, [f0, f_end, f_end + 5, f1], lambda f: 0.6 if f < f_end else (1.5 if f < f_end + 5 else 1.2))
    camera(f0, f1, dist=3.0, lens=33)


def nothing(f0, f1, fps):
    """Every colour of the night drains inward into one clear drop, the
    light goes, and there is only the drop: perfectly, deliciously nothing.
    And a tear."""
    pose_cinnamon(f0, f1, fps, "moved")
    rng = np.random.default_rng(11)
    cols = [(1, 0.45, 0.12), (1, 0.8, 0.4), (0.3, 0.9, 0.4), (1, 0.3, 0.1), (0.95, 0.5, 0.6), (0.6, 0.3, 0.9),
            (0.4, 0.7, 1.0)]
    c = CENTER + Vector((0, -0.42, 0.32))       # in front of its face
    T = (f1 - f0) / fps
    for i in range(70):
        col = cols[i % len(cols)]
        s = sphere(f"v.mote{i}", 0.025, c, glow(f"v.mote{i % 7}", col, 8.0), seg=10)
        a = rng.uniform(0, 2 * math.pi)
        r0 = rng.uniform(0.6, 1.6)
        z0 = rng.uniform(-0.6, 0.6)

        def at(f, a=a, r0=r0, z0=z0):
            t = (f - f0) / fps
            k = ease(t / 2.8)
            r = r0 * (1 - k)
            return c + Vector((r * math.cos(a + t * 3), 0.2 * math.sin(a), z0 * (1 - k) + r * 0.3 * math.sin(a + t * 3)))
        key_loc(s, range(f0, f1 + 1, 2), at)
        key_scale(s, [f0, f0 + int(2.6 * fps), f0 + int(2.9 * fps), f1], lambda f: 1.0 if f < f0 + int(2.6 * fps) else 0.0)
    drop_m = bpy.data.materials.new("v.drop")
    drop_m.use_nodes = True
    p = drop_m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.95, 0.98, 1.0, 1)
    p.inputs["Roughness"].default_value = 0.0
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["IOR"].default_value = 1.33
    p.inputs["Emission Color"].default_value = (0.8, 0.9, 1.0, 1)
    p.inputs["Emission Strength"].default_value = 0.4
    drop = sphere("v.drop", 0.05, c, drop_m, seg=48)
    drop.scale = (1, 1, 1.25)
    f_drop = f0 + int(2.7 * fps)
    key_scale(drop, [f0, f_drop, f_drop + 8, f1], lambda f: 0.0 if f < f_drop else (1.15 if f < f_drop + 8 else 1.0))
    # a soft light in the drop, the only light left
    ld = bpy.data.lights.new("v.drop_light", "POINT")
    ld.energy = 4.0
    ld.color = (0.85, 0.92, 1.0)
    lo = bpy.data.objects.new("v.drop_light", ld)
    lo.location = c
    bpy.context.scene.collection.objects.link(lo)
    for f, e in ((f0, 0.0), (f_drop, 0.0), (f_drop + 10, 5.0), (f1, 5.0)):
        ld.energy = e
        ld.keyframe_insert("energy", frame=f)
    # dim everything else as the colours go
    for o in bpy.data.objects:
        if o.type == "LIGHT" and o.name.startswith("vision."):
            L = o.data
            base = L.energy
            for f, k in ((f0, 1.0), (f0 + int(2.4 * fps), 1.0), (f0 + int(3.0 * fps), 0.25), (f1, 0.25)):
                L.energy = base * k
                L.keyframe_insert("energy", frame=f)
    # the tear: a small drop that rolls down its cheek
    tear = sphere("v.tear", 0.012, CENTER, drop_m, seg=16)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.get("character") == "cinnamon")
    f_t = f0 + int(3.6 * fps)
    key_loc(tear, range(f0, f1 + 1, 2), lambda f: arm.location + Vector((0.07, -0.13, 0.1 - 0.12 * ease((f - f_t) / (1.6 * fps)))))
    key_scale(tear, [f0, f_t, f_t + 4, f1], lambda f: 0.0 if f < f_t else 1.0)
    camera(f0, f1, dist=2.0, lens=45)


VISIONS = {"basel": basel, "harmonic": harmonic, "product": product, "wheel": wheel, "nothing": nothing}


def animate(name, film, shot, f0, f1):
    VISIONS[name](f0, f1, film["fps"])
