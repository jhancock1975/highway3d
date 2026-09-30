"""Blender-side helpers shared by every character and set.

Runs inside Blender only. Kept small on purpose: meshes from fields,
materials, and a look-development stage for checking a character.
"""

from __future__ import annotations

import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cartoon import sculpt as S  # noqa: E402


def log(*a):
    print("[cartoon]", *a, flush=True)


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                 bpy.data.armatures, bpy.data.cameras, bpy.data.lights,
                 bpy.data.images, bpy.data.node_groups):
        for b in list(coll):
            if b.users == 0:
                coll.remove(b)


def collection(name: str, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    p = parent or bpy.context.scene.collection
    if c.name not in [x.name for x in p.children]:
        p.children.link(c)
    return c


# ------------------------------------------------------------------ meshes

def mesh_from_field(name: str, field, lo, hi, voxel: float, coll=None,
                    project: bool = True, smooth: bool = True):
    """Sculpt -> mesh object, with the field's colour as a colour attribute
    `col` and its labels as an integer attribute `label` (names in the
    object's `labels` custom property)."""
    v, q = S.surface_nets(field, lo, hi, voxel)
    if project:
        v = S.project(field, v)
    col, lab = S.attributes(field, v)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", v.astype(np.float32).ravel())
    me.loops.add(q.size)
    me.loops.foreach_set("vertex_index", q.astype(np.int32).ravel())
    me.polygons.add(len(q))
    me.polygons.foreach_set("loop_start", (np.arange(len(q)) * 4).astype(np.int32))
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    if smooth:
        me.shade_smooth()
    a = me.color_attributes.new("col", "FLOAT_COLOR", "POINT")
    rgba = np.concatenate([col, np.ones((len(col), 1))], 1).astype(np.float32)
    a.data.foreach_set("color", rgba.ravel())
    names = sorted(set(lab.tolist()))
    li = me.attributes.new("label", "INT", "POINT")
    lookup = {n: i for i, n in enumerate(names)}
    li.data.foreach_set("value", np.array([lookup[x] for x in lab], dtype=np.int32))
    ob = bpy.data.objects.new(name, me)
    ob["labels"] = names
    (coll or bpy.context.scene.collection).objects.link(ob)
    log(f"{name}: {len(v)} verts, {len(q)} quads, labels {names}")
    return ob


def verts_np(ob) -> np.ndarray:
    me = ob.data
    v = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", v)
    return v.reshape(-1, 3).astype(float)


def labels_np(ob) -> np.ndarray:
    """Label names per vertex."""
    me = ob.data
    li = np.empty(len(me.vertices), np.int32)
    me.attributes["label"].data.foreach_get("value", li)
    names = list(ob["labels"])
    return np.array(names, dtype=object)[li]


def assign_by_label(ob, mapping: dict, default: int = 0):
    """Material index per face from the labels of its vertices (majority)."""
    lab = labels_np(ob)
    me = ob.data
    n = len(me.polygons)
    lstart = np.empty(n, np.int32)
    me.polygons.foreach_get("loop_start", lstart)
    vi = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", vi)
    quads = vi.reshape(-1, 4)
    idx = np.full(n, default, np.int32)
    for name, m in mapping.items():
        hit = (lab[quads] == name).sum(1) >= 3
        idx[hit] = m
    me.polygons.foreach_set("material_index", idx)


def subsurf(ob, view=1, render=2):
    m = ob.modifiers.new("subsurf", "SUBSURF")
    m.levels = view
    m.render_levels = render
    m.quality = 3
    return m


def add_shape_key(ob, name, disp: np.ndarray):
    """A shape key from per-vertex displacement."""
    if ob.data.shape_keys is None:
        ob.shape_key_add(name="Basis", from_mix=False)
    k = ob.shape_key_add(name=name, from_mix=False)
    base = verts_np(ob)
    k.data.foreach_set("co", (base + disp).astype(np.float32).ravel())
    k.slider_min = -1.0
    k.slider_max = 1.0
    return k


# --------------------------------------------------------------- materials

def _bsdf(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    return nt, nt.nodes["Principled BSDF"]


def mat_skin(name, sss_radius=(1.0, 0.45, 0.3), sss=0.18, rough=0.5,
             attr="col", sheen=0.0, coat=0.0, scale=0.0025):
    """Skin from the sculpt's colour attribute, with subsurface scattering."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt, p = _bsdf(m)
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_name = attr
    a.attribute_type = "GEOMETRY"
    nt.links.new(a.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    p.inputs["Subsurface Weight"].default_value = sss
    p.inputs["Subsurface Radius"].default_value = sss_radius
    p.inputs["Subsurface Scale"].default_value = scale
    p.inputs["Specular IOR Level"].default_value = 0.45
    if sheen:
        p.inputs["Sheen Weight"].default_value = sheen
        p.inputs["Sheen Roughness"].default_value = 0.4
    if coat:
        p.inputs["Coat Weight"].default_value = coat
        p.inputs["Coat Roughness"].default_value = 0.25
    return m


def mat_plain(name, rgb, rough=0.6, sheen=0.0, metal=0.0, sss=0.0, emit=None,
              emit_strength=0.0, coat=0.0, alpha=1.0, transmission=0.0, ior=1.45):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt, p = _bsdf(m)
    p.inputs["Base Color"].default_value = (*rgb, 1.0)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if sheen:
        p.inputs["Sheen Weight"].default_value = sheen
        p.inputs["Sheen Roughness"].default_value = 0.5
    if sss:
        p.inputs["Subsurface Weight"].default_value = sss
        p.inputs["Subsurface Scale"].default_value = 0.01
    if emit is not None:
        p.inputs["Emission Color"].default_value = (*emit, 1.0)
        p.inputs["Emission Strength"].default_value = emit_strength
    if coat:
        p.inputs["Coat Weight"].default_value = coat
        p.inputs["Coat Roughness"].default_value = 0.05
    if alpha < 1.0:
        p.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
    if transmission:
        p.inputs["Transmission Weight"].default_value = transmission
        p.inputs["IOR"].default_value = ior
    return m


def mat_attr(name, attr="col", rough=0.7, sheen=0.0, sss=0.0, coat=0.0):
    """Any surface whose colour comes from the sculpt (cloth, fur, horn)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt, p = _bsdf(m)
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_name = attr
    nt.links.new(a.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    if sheen:
        p.inputs["Sheen Weight"].default_value = sheen
        p.inputs["Sheen Roughness"].default_value = 0.5
    if sss:
        p.inputs["Subsurface Weight"].default_value = sss
        p.inputs["Subsurface Scale"].default_value = 0.01
    if coat:
        p.inputs["Coat Weight"].default_value = coat
        p.inputs["Coat Roughness"].default_value = 0.2
    return m


def mat_satin(name, attr="col", rough=0.28, aniso=0.6, spec=0.7):
    """Silk satin: a bright anisotropic sheen along the weave, dark in the
    folds. Colour from the sculpt."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt, p = _bsdf(m)
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_name = attr
    nt.links.new(a.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    p.inputs["Anisotropic"].default_value = aniso
    p.inputs["Specular IOR Level"].default_value = spec
    p.inputs["Sheen Weight"].default_value = 0.35
    p.inputs["Sheen Roughness"].default_value = 0.3
    return m


def mat_eye(name, iris=(0.25, 0.35, 0.45), iris_dark=(0.06, 0.08, 0.1),
            pupil=0.36, iris_size=0.55, cloudy=0.0, sclera=(0.93, 0.9, 0.86)):
    """A cartoon eye on a sphere whose front is local -Y.

    Iris and pupil are drawn by angle from the front pole, so the eye can
    turn by rotating the ball. A glossy coat gives the catchlights -- the
    single biggest difference between a live eye and a painted one.
    `cloudy` greys the iris and softens the pupil: Euler's cataract.
    """
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt, p = _bsdf(m)
    N = nt.nodes
    L = nt.links
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs[0])
    # angle from the -Y pole: r = sqrt(x^2+z^2) / |p| ~ sin(theta)
    vl = N.new("ShaderNodeVectorMath")
    vl.operation = "LENGTH"
    L.new(tc.outputs["Object"], vl.inputs[0])
    xz = N.new("ShaderNodeCombineXYZ")
    L.new(sep.outputs["X"], xz.inputs["X"])
    L.new(sep.outputs["Z"], xz.inputs["Z"])
    rl = N.new("ShaderNodeVectorMath")
    rl.operation = "LENGTH"
    L.new(xz.outputs[0], rl.inputs[0])
    r = N.new("ShaderNodeMath")
    r.operation = "DIVIDE"
    L.new(rl.outputs["Value"], r.inputs[0])
    L.new(vl.outputs["Value"], r.inputs[1])
    # back hemisphere is all sclera
    front = N.new("ShaderNodeMath")
    front.operation = "LESS_THAN"
    L.new(sep.outputs["Y"], front.inputs[0])
    front.inputs[1].default_value = 0.0
    rr = N.new("ShaderNodeMath")
    rr.operation = "MULTIPLY_ADD"   # r*front + (1-front)*1  -> r in front, 1 behind
    inv = N.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    L.new(front.outputs[0], inv.inputs[1])
    L.new(r.outputs[0], rr.inputs[0])
    L.new(front.outputs[0], rr.inputs[1])
    L.new(inv.outputs[0], rr.inputs[2])

    ramp = N.new("ShaderNodeValToRGB")
    L.new(rr.outputs[0], ramp.inputs["Fac"])
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    pu = pupil * iris_size
    soft = 0.02 + 0.05 * cloudy
    pupil_col = tuple(0.02 + 0.25 * cloudy for _ in range(3))
    cr.elements[0].position = 0.0
    cr.elements[0].color = (*pupil_col, 1)
    cr.elements[1].position = max(0.01, pu - soft)
    cr.elements[1].color = (*pupil_col, 1)
    def add(pos, rgb):
        e = cr.elements.new(pos)
        e.color = (*rgb, 1)
    mix = lambda a, b, t: tuple(x * (1 - t) + y * t for x, y in zip(a, b))
    grey = (0.62, 0.64, 0.66)
    add(pu + soft * 0.5, mix(iris_dark, grey, cloudy * 0.6))
    add(pu + (iris_size - pu) * 0.45, mix(iris, grey, cloudy * 0.55))
    add(iris_size - 0.05, mix(iris_dark, grey, cloudy * 0.4))
    add(iris_size - 0.012, (0.03, 0.03, 0.035))            # limbal ring
    add(iris_size + 0.015, sclera)
    add(0.98, tuple(c * 0.92 for c in sclera))
    L.new(ramp.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.35
    p.inputs["Coat Weight"].default_value = 1.0
    p.inputs["Coat Roughness"].default_value = 0.015 + 0.04 * cloudy
    p.inputs["Coat IOR"].default_value = 1.4
    p.inputs["Subsurface Weight"].default_value = 0.15
    p.inputs["Subsurface Scale"].default_value = 0.003
    return m


# ------------------------------------------------------------- look stage

def aim(ob, target):
    """Point -Z at target. The Euler angles are chosen nearest the object's
    current ones: a camera keyed while it turns through +-180 degrees of
    yaw otherwise gets keys on both sides of the wrap, the interpolation
    between them spins it round, and motion blur smears the spin over the
    whole frame (it did, for the whole of the dawn shot)."""
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler("XYZ", ob.rotation_euler)


def look_stage(target=(0, 0, 1.2), dist=1.2, lens=85, azim=-25, elev=4,
               res=(1280, 1280), engine="BLENDER_EEVEE", bg=(0.18, 0.17, 0.2)):
    """Camera and three lights around `target`, for judging a character."""
    sc = bpy.context.scene
    for o in [o for o in bpy.data.objects if o.type in ("CAMERA", "LIGHT") or o.name == "_backdrop"]:
        bpy.data.objects.remove(o, do_unlink=True)
    sc.render.engine = engine
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    if engine == "BLENDER_EEVEE":
        sc.eevee.taa_render_samples = 64
        sc.eevee.use_raytracing = True
    else:
        sc.cycles.samples = 128
        sc.cycles.use_denoising = True
    t = Vector(target)
    cd = bpy.data.cameras.new("_cam")
    cd.lens = lens
    cam = bpy.data.objects.new("_cam", cd)
    sc.collection.objects.link(cam)
    az, el = math.radians(azim), math.radians(elev)
    cam.location = t + Vector((math.sin(az) * dist * math.cos(el),
                               -math.cos(az) * dist * math.cos(el),
                               math.sin(el) * dist))
    aim(cam, t)
    sc.camera = cam

    def light(name, off, energy, size, color):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = t + Vector(off)
        aim(lo, t)

    s = dist / 1.2
    light("_key", (-1.0 * s, -1.2 * s, 0.9 * s), 90 * s * s, 1.0 * s, (1.0, 0.92, 0.82))
    light("_fill", (1.3 * s, -0.9 * s, 0.1 * s), 25 * s * s, 1.8 * s, (0.82, 0.88, 1.0))
    light("_rim", (0.7 * s, 1.2 * s, 0.8 * s), 140 * s * s, 0.6 * s, (0.9, 0.95, 1.0))
    w = sc.world or bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*bg, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.35
    return cam


def render_still(path, cam=None):
    sc = bpy.context.scene
    if cam is not None:
        sc.camera = cam
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log("still", path)
