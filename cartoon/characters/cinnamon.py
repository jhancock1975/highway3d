"""Build Cinnamon in Blender: meshes, materials, rig, face, tongue.

    blender -b --factory-startup -P cartoon/characters/cinnamon.py -- --out .work/cartoon/assets/cinnamon.blend

The animation interface is the same shape as Euler's, plus what an alien
has that he does not:

  root body head jaw                      FK; root scale is squash/stretch
  ik.hand.L / ik.hand.R                   hands
  f_<f1..f3>_<1,2>.L/R                    fingers
  ant_<1..4>.L/R                          antennae (driven by a spring sim)
  cinnamon.tongue                         a curve: its points and
                                          bevel_factor_end are the lick
  body mesh shape keys                    bl/face.py, plus nostril_flare
  (no eyes: the brows, the nose and the antennae carry the expression)
"""

from __future__ import annotations

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from cartoon import sculpt as S  # noqa: E402
from cartoon.bl import common as C, eyes as E, face as F, rig as R  # noqa: E402
from cartoon.characters import cinnamon_shape as X  # noqa: E402

NAME = "cinnamon"
TONGUE_POINTS = 14


def antenna_matrix(side):
    sx = 1 if side == ".L" else -1
    b = X.ANTENNA_BASE_L
    M = Matrix.Translation((sx * b[0], b[1], b[2]))
    if side == ".R":
        M = M @ Matrix.Scale(-1, 4, (1, 0, 0))
    return M


def bones():
    j = {k: Vector(v) for k, v in X.J.items()}
    B = [
        dict(name="root", head=j["root"], tail=j["body"]),
        dict(name="body", head=j["body"], tail=j["head"], parent="root", connect=True),
        dict(name="head", head=j["head"], tail=j["head_top"], parent="body", connect=True),
        dict(name="jaw", head=Vector(X.JAW_PIVOT), tail=Vector((0, -0.15, -0.05)), parent="head",
             roll_to=(0, 0, -1)),
    ]
    for s, sx in ((".L", 1), (".R", -1)):
        B += [
            dict(name="arm" + s, head=j["arm" + s], tail=j["forearm" + s], parent="body"),
            dict(name="forearm" + s, head=j["forearm" + s], tail=j["hand" + s], parent="arm" + s, connect=True),
            dict(name="hand" + s, head=j["hand" + s], tail=j["hand_end" + s], parent="forearm" + s,
                 connect=True, roll_to=(0, 0, 1)),
            dict(name="foot" + s, head=j["foot" + s], tail=j["foot_end" + s], parent="root"),
        ]
        for name in X.FINGER_OFFSETS:
            pts = X.finger_points(sx, name)
            B.append(dict(name=f"f_{name}_1{s}", head=pts[0], tail=pts[1], parent="hand" + s, roll_to=(0, 0, 1)))
            B.append(dict(name=f"f_{name}_2{s}", head=pts[1], tail=pts[2], parent=f"f_{name}_1{s}",
                          connect=True, roll_to=(0, 0, 1)))
        M = antenna_matrix(s)
        ap = [M @ Vector(p) for p in X.antenna_points()]
        for i in range(4):
            B.append(dict(name=f"ant_{i + 1}{s}", head=ap[i], tail=ap[i + 1],
                          parent=(f"ant_{i}{s}" if i else "head"), connect=bool(i)))
    return B


def build(coll=None, voxel=0.0028):
    coll = coll or C.collection(NAME)
    body = C.mesh_from_field(NAME + ".body", X.body(), *X.BODY_BOUNDS, voxel, coll)
    skin = C.mat_skin("cinnamon.skin", sss=0.2, sss_radius=(1.0, 0.45, 0.25), rough=0.55, sheen=0.12, scale=0.0025)
    body.data.materials.append(skin)
    body.data.materials.append(C.mat_plain("cinnamon.mouth", (0.2, 0.025, 0.05), rough=0.4, sss=0.3))
    body.data.materials.append(C.mat_skin("cinnamon.nose", sss=0.25, rough=0.35, coat=0.3, scale=0.0025))
    C.assign_by_label(body, {"mouth": 1, "nose": 2})

    ants = {}
    for s in (".L", ".R"):
        a = C.mesh_from_field(NAME + ".antenna" + s, X.antenna(), *X.ANTENNA_BOUNDS, 0.0012, coll)
        a.matrix_world = antenna_matrix(s)
        if s == ".R":
            # bake the mirror so normals are right and the object is unscaled
            a.data.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
            a.data.flip_normals()
            a.matrix_world = Matrix.Translation(antenna_matrix(".R").translation)
        am = C.mat_attr("cinnamon.antenna", rough=0.5, sheen=0.3, sss=0.15)
        glow = C.mat_plain("cinnamon.glow", X.GLOW, rough=0.3, emit=X.GLOW, emit_strength=1.2)
        a.data.materials.append(am)
        a.data.materials.append(glow)
        C.assign_by_label(a, {"tip": 1})
        ants[s] = a

    # no eyes: it has never needed them
    eyes = {}

    arm = R.armature(NAME + ".rig", bones(), coll)
    keep = {b["name"] for b in bones() if not b["name"].startswith("ant_") and b["name"] != "jaw"
            and not b["name"].startswith("f_")}
    R.skin_auto(body, arm, keep=keep)
    # jaw, and fingers by segment, on top of the heat weights
    P = C.verts_np(body)
    lab = C.labels_np(body)
    wj = F.jaw_weights(P, X.MOUTH_C, X.MOUTH_HALF_W, X.SMILE_LIFT, back_y=0.0, reach=0.1)
    wj[lab == "hand"] = 0
    _blend_group(body, "jaw", wj, take_from=["head", "body"])
    for s, sx in ((".L", 1), (".R", -1)):
        for name in X.FINGER_OFFSETS:
            m = lab == name
            pts = X.finger_points(sx, name)
            sw = R.segment_weights(P[m], pts, [f"f_{name}_1{s}", f"f_{name}_2{s}"], before="hand" + s, blend=0.3)
            for g in list(body.vertex_groups):
                idx = np.nonzero(m)[0]
                for i in idx:
                    try:
                        g.remove([int(i)])
                    except RuntimeError:
                        pass
            for b, w in sw.items():
                vg = body.vertex_groups.get(b) or body.vertex_groups.new(name=b)
                for i, wi in zip(np.nonzero(m)[0], w):
                    if wi > 1e-4:
                        vg.add([int(i)], float(wi), "REPLACE")
    # antennae
    for s, a in ants.items():
        Pw = np.array([a.matrix_world @ Vector(v) for v in C.verts_np(a)])
        M = antenna_matrix(s)
        ap = [np.array(M @ Vector(p)) for p in X.antenna_points()]
        sw = R.segment_weights(Pw, ap, [f"ant_{i + 1}{s}" for i in range(4)], before="head", blend=0.35)
        mw = a.matrix_world.copy()
        R.skin_groups(a, arm, sw)
        a.matrix_world = mw
        a.matrix_parent_inverse = arm.matrix_world.inverted()

    for s, sx in ((".L", 1), (".R", -1)):
        hb = arm.data.bones["hand" + s]
        tgt = R.empty(f"{NAME}.ik.hand{s}", Vector(X.J["hand" + s]), coll, 0.03, "CUBE")
        tgt.rotation_mode = "QUATERNION"
        tgt.rotation_quaternion = (arm.matrix_world @ hb.matrix_local).to_quaternion()
        pole = R.empty(f"{NAME}.pole.forearm{s}", Vector(X.J["forearm" + s]) + Vector((sx * 0.2, 0.2, 0.0)),
                       coll, 0.03, "PLAIN_AXES")
        R.ik(arm, "forearm" + s, tgt, pole, chain=2)
        cr = arm.pose.bones["hand" + s].constraints.new("COPY_ROTATION")
        cr.target = tgt
        tgt.parent = arm
        pole.parent = arm
        tgt["rest_location"] = list(tgt.location)
        tgt["rest_rotation"] = list(tgt.rotation_quaternion)
    from cartoon.characters.euler import _pick_pole_angles
    _pick_pole_angles(arm)

    # face
    lip_up, lip_lo = X.lips()
    keys = F.mouth_keys(P, X.MOUTH_C, X.MOUTH_HALF_W, lip_up, lip_lo, X.CHEEKS, X.SMILE_LIFT)
    keys.update(F.brow_keys(P, X.BROW_L, X.BROW_R, X.CHEEKS[0], X.CHEEKS[1],
                            X.BROW_INNER_L, X.BROW_INNER_R, sig=0.035))
    # scale the mouth keys up: this mouth is twice Euler's. And with no eyes
    # the brows carry the face, so they travel further too
    for k in ("mouth_wide", "mouth_narrow", "smile", "frown"):
        keys[k] = keys[k] * 1.6
    for k in [k for k in keys if k.startswith(("brow_", "cheek_"))]:
        keys[k] = keys[k] * 1.5
    keys["nostril_flare"] = _nostril_flare(P)
    keys["nose_scrunch"] = _nose_scrunch(P)
    F.add_keys(body, keys)
    body.data.shape_keys.key_blocks["lips_close"].value = 1.0

    tongue = build_tongue(coll)
    R.attach(tongue, arm, "jaw")

    for o in (body,):
        C.subsurf(o, 1, 2)
    for o in ants.values():
        C.subsurf(o, 0, 1)

    arm["character"] = NAME
    arm["head_mesh"] = body.name
    arm["eyes"] = {}
    arm["lids_rest"] = {}
    arm["tongue"] = tongue.name
    arm["face_offset"] = (0, -0.1, -0.005)
    return dict(rig=arm, body=body, eyes=eyes, antennae=ants, tongue=tongue, coll=coll)


def _blend_group(ob, name, w, take_from):
    """Add group `name` with weights w, scaling the others down to make room."""
    vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    others = [ob.vertex_groups[g] for g in take_from if g in ob.vertex_groups]
    for i in np.nonzero(w > 1e-4)[0]:
        v = ob.data.vertices[int(i)]
        for g in v.groups:
            if ob.vertex_groups[g.group] in others:
                g.weight *= (1.0 - w[i])
        vg.add([int(i)], float(w[i]), "REPLACE")


def _nostril_flare(P):
    d = np.zeros_like(P)
    for sx in (1, -1):
        c = np.array((sx * X.NOSTRIL_L[0], X.NOSTRIL_L[1], X.NOSTRIL_L[2]))
        rel = P - c
        g = np.exp(-np.sum((rel / np.array((0.022, 0.02, 0.018))) ** 2, 1))
        rn = rel / (np.linalg.norm(rel, axis=1)[:, None] + 1e-9)
        d += 0.007 * g[:, None] * rn * np.array((1.3, 0.4, 0.8))
    return d


def _nose_scrunch(P):
    rel = P - np.array(X.NOSE_C)
    g = np.exp(-np.sum((rel / np.array((0.06, 0.06, 0.05))) ** 2, 1))
    d = np.zeros_like(P)
    d[:, 2] = 0.01 * g
    d[:, 1] = 0.006 * g
    return d


def build_tongue(coll):
    """A long pink tongue: a curve with a flat oval bevel and a round tip.

    At rest its points are coiled in the mouth and bevel_factor_end is
    small, so only a stub exists; a lick moves the points out along the
    path to the slate and runs bevel_factor_end up to 1.
    """
    prof = bpy.data.curves.new(NAME + ".tongue_profile", "CURVE")
    prof.dimensions = "2D"
    sp = prof.splines.new("NURBS")
    n = 12
    sp.points.add(n - 1)
    for i in range(n):
        a = 2 * math.pi * i / n
        sp.points[i].co = (0.019 * math.cos(a), 0.011 * math.sin(a) + 0.002 * math.cos(a) ** 2, 0, 1)
    sp.use_cyclic_u = True
    po = bpy.data.objects.new(NAME + ".tongue_profile", prof)
    coll.objects.link(po)
    po.hide_render = True
    po.hide_viewport = True

    cu = bpy.data.curves.new(NAME + ".tongue", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_mode = "OBJECT"
    cu.bevel_object = po
    cu.use_fill_caps = True
    cu.resolution_u = 6
    cu.twist_mode = "MINIMUM"
    s = cu.splines.new("POLY")
    s.points.add(TONGUE_POINTS - 1)
    for i, p in enumerate(tongue_rest()):
        s.points[i].co = (*p, 1)
    # taper to a rounder tip
    for i in range(TONGUE_POINTS):
        t = i / (TONGUE_POINTS - 1)
        s.points[i].radius = 1.0 - 0.35 * t ** 2
    ob = bpy.data.objects.new(NAME + ".tongue", cu)
    coll.objects.link(ob)
    m = C.mat_plain("cinnamon.tongue", (0.75, 0.16, 0.28), rough=0.25, sss=0.4, coat=0.8)
    cu.materials.append(m)
    cu.bevel_factor_end = 1.0
    return ob


def tongue_rest():
    """Coiled in the mouth: a short arc along the floor of the cavity."""
    mx, my, mz = X.MOUTH_C
    pts = []
    for i in range(TONGUE_POINTS):
        t = i / (TONGUE_POINTS - 1)
        pts.append((mx, my + 0.075 - 0.07 * t, mz - 0.02 + 0.006 * math.sin(math.pi * t)))
    return pts


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    C.clear_scene()
    build()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    C.log("saved", a.out)


if __name__ == "__main__":
    main()
