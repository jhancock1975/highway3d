"""Build Euler in Blender: meshes, materials, rig, face. Saves a .blend.

    blender -b --factory-startup -P cartoon/characters/euler.py -- --out .work/cartoon/assets/euler.blend

Everything is generated from euler_shape.py; nothing is downloaded or
painted. What comes out is one collection, `euler`, with an armature
`euler.rig` whose bones and IK targets are the whole animation interface:

  root spine chest neck head jaw           FK, quaternions
  ik.hand.L / ik.hand.R                    hand position and orientation
  f_<finger>_<1..3>.L/R, thumb_<1,2>.L/R   finger curls
  head mesh shape keys                     see bl/face.py
  <side>.lid_up / lid_lo / ball            eyes (bl/eyes.py)
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
from cartoon.characters import euler_shape as X  # noqa: E402

NAME = "euler"
FINGER_NAMES = list(X.FINGERS)


def hand_matrix(side: str) -> Matrix:
    """Hand-local -> body: -Y along the forearm, +Z kept near world up."""
    j = X.J
    d = (Vector(j["hand" + side]) - Vector(j["forearm" + side])).normalized()
    y = -d
    up = Vector((0, 0, 1))
    z = (up - y * up.dot(y)).normalized()
    x = y.cross(z)
    M = Matrix((x, y, z)).transposed().to_4x4()
    M.translation = Vector(j["hand" + side])
    return M


def finger_joints(side):
    """World positions of each finger's joints: {name: [k, j1, j2, tip]}."""
    M = hand_matrix(side)
    sx = 1 if side == ".L" else -1
    out = {}
    for name, (kn, ln, r) in X.FINGERS.items():
        splay = {"index": -4, "middle": 0, "ring": 4, "pinky": 9}[name]
        pts = X.finger_points(kn, ln, X.REST_CURL, splay)
        out[name] = [M @ Vector((sx * p[0], p[1], p[2])) for p in pts]
    t0, t1, t2, _ = X.THUMB
    out["thumb"] = [M @ Vector((sx * p[0], p[1], p[2])) for p in (t0, t1, t2)]
    tip = np.array(t2) + (np.array(t2) - np.array(t1)) * 0.45
    out["thumb"].append(M @ Vector((sx * tip[0], tip[1], tip[2])))
    return out


def bones():
    j = {k: Vector(v) for k, v in X.J.items()}
    ho = Vector(X.HEAD_ORIGIN)
    B = [
        dict(name="root", head=j["hips"], tail=j["spine"]),
        dict(name="spine", head=j["spine"], tail=j["chest"], parent="root", connect=True),
        dict(name="chest", head=j["chest"], tail=j["neck"], parent="spine", connect=True),
        dict(name="neck", head=j["neck"], tail=j["head"], parent="chest", connect=True),
        dict(name="head", head=j["head"], tail=j["head"] + Vector((0, 0, 0.22)), parent="neck", connect=True),
        dict(name="jaw", head=ho + Vector(X.JAW_PIVOT), tail=ho + Vector((0, -0.09, -0.1)),
             parent="head", roll_to=(0, 0, -1)),
    ]
    for s in (".L", ".R"):
        B += [
            dict(name="shoulder" + s, head=j["shoulder" + s], tail=j["upper_arm" + s], parent="chest"),
            dict(name="upper_arm" + s, head=j["upper_arm" + s], tail=j["forearm" + s],
                 parent="shoulder" + s, connect=True),
            dict(name="forearm" + s, head=j["forearm" + s], tail=j["hand" + s],
                 parent="upper_arm" + s, connect=True),
            dict(name="hand" + s, head=j["hand" + s], tail=j["hand_end" + s],
                 parent="forearm" + s, connect=True, roll_to=(0, 0, 1)),
            dict(name="thigh" + s, head=j["thigh" + s], tail=j["shin" + s], parent="root"),
            dict(name="shin" + s, head=j["shin" + s], tail=j["foot" + s], parent="thigh" + s, connect=True),
            dict(name="foot" + s, head=j["foot" + s], tail=j["toe" + s], parent="shin" + s, connect=True),
        ]
        fj = finger_joints(s)
        for name, pts in fj.items():
            n = 2 if name == "thumb" else 3
            if name == "thumb":
                pts = pts[1:] if len(pts) > 3 else pts
            for i in range(len(pts) - 1):
                B.append(dict(name=f"f_{name}_{i + 1}{s}", head=pts[i], tail=pts[i + 1],
                              parent=(f"f_{name}_{i}{s}" if i else "hand" + s),
                              connect=bool(i), roll_to=(0, 0, 1)))
    return B


BODY_BONES = {"root", "spine", "chest", "neck", "head"} | {
    b + s for b in ("shoulder", "upper_arm", "forearm", "thigh", "shin", "foot") for s in (".L", ".R")}


def body_materials(ob):
    mats = [
        C.mat_satin("euler.robe", rough=0.42, aniso=0.35, spec=0.45),
        C.mat_skin("euler.skin"),
        C.mat_attr("euler.cravat", rough=0.75, sheen=0.5),
        C.mat_attr("euler.stocking", rough=0.8, sheen=0.7),
        C.mat_attr("euler.shoe", rough=0.28, coat=0.6),
        C.mat_plain("euler.buckle", (0.8, 0.62, 0.3), rough=0.25, metal=1.0),
    ]
    for m in mats:
        ob.data.materials.append(m)
    C.assign_by_label(ob, {"neck": 1, "cravat": 2, "stocking": 3, "shoe": 4, "buckle": 5})


def build(coll=None, voxel_head=0.0022, voxel_body=0.004):
    coll = coll or C.collection(NAME)
    ho = Vector(X.HEAD_ORIGIN)

    # ---- meshes
    body = C.mesh_from_field(NAME + ".body", X.body(), *X.BODY_BOUNDS, voxel_body, coll)
    body_materials(body)

    head = C.mesh_from_field(NAME + ".head", X.head(), *X.HEAD_BOUNDS, voxel_head, coll)
    head.location = ho
    head.data.materials.append(C.mat_skin("euler.skin"))
    head.data.materials.append(C.mat_plain("euler.mouth", (0.2, 0.035, 0.04), rough=0.45, sss=0.3))
    C.assign_by_label(head, {"mouth": 1})

    hair = C.mesh_from_field(NAME + ".hair", X.hair(), *X.HAIR_BOUNDS, voxel_head, coll)
    hair.location = ho
    hair.data.materials.append(C.mat_attr("euler.hair", rough=0.5, sheen=0.9))
    cap = C.mesh_from_field(NAME + ".cap", X.cap(), *X.CAP_BOUNDS, voxel_head, coll)
    cap.location = ho
    cap.data.materials.append(C.mat_satin("euler.cap", rough=0.45, aniso=0.5, spec=0.4))

    tooth = C.mat_attr("euler.teeth", rough=0.25, sss=0.2, coat=0.3)
    t_up = C.mesh_from_field(NAME + ".teeth_up", X.teeth(True), *X.TEETH_BOUNDS, 0.0012, coll)
    t_lo = C.mesh_from_field(NAME + ".teeth_lo", X.teeth(False), *X.TEETH_BOUNDS, 0.0012, coll)
    tg = C.mesh_from_field(NAME + ".tongue", X.tongue(), *X.TEETH_BOUNDS, 0.0015, coll)
    for o in (t_up, t_lo):
        o.location = ho
        o.data.materials.append(tooth)
    tg.location = ho
    tg.data.materials.append(C.mat_attr("euler.tongue", rough=0.3, sss=0.4, coat=0.5))

    hands = {}
    for s in (".L", ".R"):
        fld = X.hand() if s == ".L" else S.MirrorX(X.hand())
        h = C.mesh_from_field(NAME + ".hand" + s, fld, *(
            X.HAND_BOUNDS if s == ".L" else ((-X.HAND_BOUNDS[1][0], X.HAND_BOUNDS[0][1], X.HAND_BOUNDS[0][2]),
                                             (-X.HAND_BOUNDS[0][0], X.HAND_BOUNDS[1][1], X.HAND_BOUNDS[1][2]))),
            0.0016, coll)
        h.matrix_world = hand_matrix(s)
        h.data.materials.append(C.mat_skin("euler.skin"))
        hands[s] = h

    # ---- eyes
    eye_mat = C.mat_eye("euler.eye", iris=(0.22, 0.4, 0.62), iris_dark=(0.05, 0.1, 0.18), cloudy=0.22)
    lid_mat = E.lid_material("euler.lid", X.SKIN)
    eyes = {}
    for s, sx in ((".L", 1), (".R", -1)):
        c = ho + Vector((sx * X.EYE_L_POS[0], X.EYE_L_POS[1], X.EYE_L_POS[2]))
        eyes[s] = E.build_eye(NAME + s, c, X.EYE_R, eye_mat, lid_mat, coll, tilt=-sx * X.EYE_TILT)

    # ---- rig
    arm = R.armature(NAME + ".rig", bones(), coll)
    # body: bone heat, body bones only
    R.skin_auto(body, arm, keep=BODY_BONES)
    # head: head and jaw by the face rig's function
    P = C.verts_np(head)
    wj = F.jaw_weights(P, X.MOUTH_C, X.MOUTH_HALF_W, X.SMILE_LIFT)
    R.skin_groups(head, arm, {"head": 1.0 - wj, "jaw": wj})
    head.matrix_parent_inverse = arm.matrix_world.inverted()
    # hands: fingers by segment, the rest to the hand bone
    for s, h in hands.items():
        Pw = np.array([h.matrix_world @ Vector(v) for v in C.verts_np(h)])
        lab = C.labels_np(h)
        fj = finger_joints(s)
        W = {"hand" + s: np.ones(len(Pw))}
        for name in FINGER_NAMES + ["thumb"]:
            m = lab == name
            if not m.any():
                continue
            pts = fj[name] if name != "thumb" else fj[name][1:]
            bn = [f"f_{name}_{i + 1}{s}" for i in range(len(pts) - 1)]
            sw = R.segment_weights(Pw[m], [np.array(p) for p in pts], bn, before="hand" + s, blend=0.25)
            for b, w in sw.items():
                if b not in W:
                    W[b] = np.zeros(len(Pw))
                W[b][m] = w
            W["hand" + s][m] = sw["hand" + s]
        mw = h.matrix_world.copy()
        R.skin_groups(h, arm, W)
        h.matrix_world = mw
        h.matrix_parent_inverse = arm.matrix_world.inverted() @ Matrix.Identity(4)
    # rigid children
    for o in (hair, cap, t_up):
        R.attach(o, arm, "head")
    for o in (t_lo, tg):
        R.attach(o, arm, "jaw")
    for s, e in eyes.items():
        R.attach(e["root"], arm, "head")

    # IK on the arms
    for s in (".L", ".R"):
        sx = 1 if s == ".L" else -1
        hb = arm.data.bones["hand" + s]
        tgt = R.empty(f"{NAME}.ik.hand{s}", Vector(X.J["hand" + s]), coll, 0.04, "CUBE")
        tgt.rotation_mode = "QUATERNION"
        tgt.rotation_quaternion = (arm.matrix_world @ hb.matrix_local).to_quaternion()
        el = Vector(X.J["forearm" + s])
        pole = R.empty(f"{NAME}.pole.forearm{s}", el + Vector((sx * 0.25, 0.3, -0.05)), coll, 0.03, "PLAIN_AXES")
        R.ik(arm, "forearm" + s, tgt, pole, chain=2)
        cr = arm.pose.bones["hand" + s].constraints.new("COPY_ROTATION")
        cr.target = tgt
        cr.mix_mode = "REPLACE"
        tgt.parent = arm
        pole.parent = arm
        tgt["rest_location"] = list(tgt.location)
        tgt["rest_rotation"] = list(tgt.rotation_quaternion)
    _pick_pole_angles(arm)

    # ---- face keys
    lip_up, lip_lo = X.lips()
    keys = F.mouth_keys(P, X.MOUTH_C, X.MOUTH_HALF_W, lip_up, lip_lo, X.CHEEKS, X.SMILE_LIFT)
    keys.update(F.brow_keys(P, X.BROW_L, X.BROW_R, X.CHEEKS[0], X.CHEEKS[1],
                            X.BROW_INNER_L, X.BROW_INNER_R))
    F.add_keys(head, keys)
    head.data.shape_keys.key_blocks["lips_close"].value = 1.0

    for o in (body, head, hair, cap, hands[".L"], hands[".R"]):
        C.subsurf(o, 1, 2)
    for o in (t_up, t_lo, tg):
        C.subsurf(o, 0, 1)

    # rest-state lids
    E.set_lids(eyes[".L"], 0.72, 0.95)
    E.set_lids(eyes[".R"], 0.36, 0.7)

    arm["character"] = NAME
    arm["head_mesh"] = head.name
    arm["eyes"] = {s: {k: (v.name if hasattr(v, "name") else v) for k, v in e.items()}
                   for s, e in eyes.items()}
    arm["lids_rest"] = {".L": [0.72, 0.95], ".R": [0.36, 0.7]}
    return dict(rig=arm, head=head, body=body, hands=hands, eyes=eyes, cap=cap, hair=hair,
                coll=coll)


def _pick_pole_angles(arm):
    """The IK pole angle that leaves each arm where it was sculpted.

    It depends on the bones' rolls, and guessing it wrong swings the elbow
    out through the body at frame one. So try the four candidates and keep
    the one whose solved elbow lands nearest the rest elbow.
    """
    dg = bpy.context.evaluated_depsgraph_get()
    for s in (".L", ".R"):
        c = arm.pose.bones["forearm" + s].constraints["IK"]
        rest = arm.matrix_world @ arm.data.bones["forearm" + s].head_local
        best, best_d = 0.0, 1e9
        for a in (0.0, 90.0, -90.0, 180.0):
            c.pole_angle = math.radians(a)
            bpy.context.view_layer.update()
            got = arm.matrix_world @ arm.pose.bones["forearm" + s].head
            d = (got - rest).length
            if d < best_d:
                best, best_d = a, d
        # refine
        for a in np.linspace(best - 45, best + 45, 31):
            c.pole_angle = math.radians(a)
            bpy.context.view_layer.update()
            got = arm.matrix_world @ arm.pose.bones["forearm" + s].head
            d = (got - rest).length
            if d < best_d:
                best, best_d = a, d
        c.pole_angle = math.radians(best)
        C.log(f"pole angle {s}: {best:.1f} deg (elbow off by {best_d * 1000:.1f} mm)")


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
