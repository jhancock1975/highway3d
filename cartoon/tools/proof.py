"""Put a built character through its paces: a full figure and a sheet of
faces, so a rig can be judged by looking rather than by trusting it.

    blender -b .work/cartoon/assets/euler.blend -P cartoon/tools/proof.py -- --out DIR
"""

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import bpy  # noqa: E402
from mathutils import Quaternion, Vector  # noqa: E402

from cartoon.bl import common as C, eyes as E, rig as R  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--engine", default="BLENDER_EEVEE")
ap.add_argument("--only", default="")
a = ap.parse_args(argv)
os.makedirs(a.out, exist_ok=True)

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
who = arm["character"]
head = bpy.data.objects[arm["head_mesh"]]
kb = head.data.shape_keys.key_blocks
eyes = {s: {k: bpy.data.objects[v] if isinstance(v, str) and v in bpy.data.objects else v
            for k, v in e.items()} for s, e in arm["eyes"].items()}
rest_lids = arm["lids_rest"]


def reset():
    for k in kb[1:]:
        k.value = 0.0
    kb["lips_close"].value = 1.0
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    for s, e in eyes.items():
        E.set_lids(e, *rest_lids[s])
        E.set_look(e, 0, 0)
    for s in (".L", ".R"):
        t = bpy.data.objects.get(f"{who}.ik.hand{s}")
        if t:
            t.location = t["rest_location"]
            t.rotation_quaternion = t["rest_rotation"]


def jaw(deg):
    arm.pose.bones["jaw"].rotation_quaternion = R.world_rot(arm, "jaw", (1, 0, 0), deg)


def lids(up, lo=None):
    for s, e in eyes.items():
        ru, rl = rest_lids[s]
        E.set_lids(e, up * ru / 0.72, (lo if lo is not None else rl))


POSES = {
    "neutral": {},
    "aa": dict(jaw=16, keys=dict(lips_close=0.0, upper_up=0.3, lower_down=0.4)),
    "ee": dict(jaw=5, keys=dict(lips_close=0.1, mouth_wide=0.8, upper_up=0.5, lower_down=0.4)),
    "oo": dict(jaw=7, keys=dict(lips_close=0.2, mouth_narrow=1.0)),
    "mbp": dict(keys=dict(lips_press=1.0)),
    "ff": dict(jaw=3, keys=dict(lips_close=0.0, lower_in=1.0, upper_up=0.4)),
    "laugh": dict(jaw=14, keys=dict(lips_close=0.0, smile=1.0, upper_up=0.6, lower_down=0.5,
                                    **{"cheek_up.L": 1.0, "cheek_up.R": 1.0}), lids=0.45),
    "surprise": dict(jaw=10, keys=dict(lips_close=0.3, mouth_narrow=0.5, **{"brow_up.L": 1.0, "brow_up.R": 1.0}),
                     lids=1.0),
    "worried": dict(keys=dict(frown=0.6, brow_inner=1.0)),
    "grumpy": dict(keys=dict(frown=0.8, **{"brow_down.L": 1.0, "brow_down.R": 1.0}), lids=0.6),
    "blink": dict(lids=0.0, lo=0.0),
    "look_left": dict(look=(0.45, 0.1), head=(0, 0, 25)),
}


def pose(p):
    reset()
    if "jaw" in p:
        jaw(p["jaw"])
    for k, v in p.get("keys", {}).items():
        kb[k].value = v
    if "lids" in p:
        lids(p["lids"], p.get("lo"))
    if "look" in p:
        for e in eyes.values():
            E.set_look(e, *p["look"])
    if "head" in p:
        rx, ry, rz = p["head"]
        arm.pose.bones["head"].rotation_quaternion = R.world_rot(arm, "head", (0, 0, 1), rz)
    bpy.context.view_layer.update()


hp = arm.matrix_world @ arm.data.bones["head"].head_local
face_t = hp + Vector(arm.get("face_offset", (0, -0.07, 0.07)))
for name, p in POSES.items():
    if a.only and name not in a.only.split(","):
        continue
    pose(p)
    cam = C.look_stage(target=face_t, dist=0.85, lens=85, azim=-22, elev=4, engine=a.engine, res=(700, 700))
    C.render_still(os.path.join(a.out, f"{who}_face_{name}.png"), cam)

# full figure, and one with the right hand raised as if to write
if not a.only or "body" in a.only:
    reset()
    import numpy as np
    pts = np.array([list(o.matrix_world @ Vector(c)) for o in bpy.data.objects
                    if o.type == "MESH" and not o.hide_render for c in o.bound_box])
    lo, hi = pts.min(0), pts.max(0)
    ctr = (lo + hi) / 2
    size = float(max(hi - lo))
    cam = C.look_stage(target=tuple(ctr), dist=size * 2.6, lens=50, azim=-30, elev=8,
                       engine=a.engine, res=(900, 1100))
    C.render_still(os.path.join(a.out, f"{who}_body.png"), cam)
    t = bpy.data.objects[f"{who}.ik.hand.R"]
    t.location = Vector(t["rest_location"]) + Vector((-0.12, -0.12, 0.42)) * (size / 1.2)
    q = Quaternion((1, 0, 0), math.radians(-70))
    t.rotation_quaternion = q @ Quaternion(t["rest_rotation"])
    arm.pose.bones["head"].rotation_quaternion = R.world_rot(arm, "head", (0, 0, 1), -20)
    for n in ("index", "middle", "ring", "pinky"):
        for i in (1, 2, 3):
            pb = arm.pose.bones.get(f"f_{n}_{i}.R")
            if pb and n != "index":
                pb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(-55))
    bpy.context.view_layer.update()
    C.render_still(os.path.join(a.out, f"{who}_body_reach.png"), cam)
