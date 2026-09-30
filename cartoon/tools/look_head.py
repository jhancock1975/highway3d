"""Mesh a character's head and render it from three sides, for judging.

    blender -b --factory-startup -P cartoon/tools/look_head.py -- --who euler --out DIR
"""

import argparse
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from cartoon.bl import common as C  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--who", default="euler")
ap.add_argument("--out", required=True)
ap.add_argument("--voxel", type=float, default=0.0025)
ap.add_argument("--engine", default="BLENDER_EEVEE")
a = ap.parse_args(argv)
os.makedirs(a.out, exist_ok=True)

C.clear_scene()
shape = importlib.import_module(f"cartoon.characters.{a.who}_shape")
head = C.mesh_from_field("head", shape.head(), *shape.HEAD_BOUNDS, a.voxel)
skin = C.mat_skin("skin")
mouth = C.mat_plain("mouth", (0.25, 0.05, 0.06), rough=0.4, sss=0.3)
head.data.materials.append(skin)
head.data.materials.append(mouth)
C.assign_by_label(head, {"mouth": 1})
C.subsurf(head, 1, 1)
if hasattr(shape, "cap"):
    cap = C.mesh_from_field("cap", shape.cap(), *shape.CAP_BOUNDS, a.voxel)
    cap.data.materials.append(C.mat_satin("satin"))
    C.subsurf(cap, 1, 1)
if hasattr(shape, "hair"):
    hr = C.mesh_from_field("hair", shape.hair(), *shape.HAIR_BOUNDS, a.voxel)
    hr.data.materials.append(C.mat_attr("hairmat", rough=0.55, sheen=0.8))
    C.subsurf(hr, 1, 1)
from cartoon.bl import eyes as E  # noqa: E402
eye = C.mat_eye("eye", iris=(0.22, 0.4, 0.62), iris_dark=(0.05, 0.1, 0.18), cloudy=0.22)
lid = E.lid_material("lid", shape.SKIN)
coll = bpy.context.scene.collection
for sx in (1, -1):
    e = E.build_eye(f"eye{sx}", (sx * shape.EYE_L_POS[0], *shape.EYE_L_POS[1:]), shape.EYE_R,
                    eye, lid, coll, tilt=-sx * getattr(shape, "EYE_TILT", 0.0))
    E.set_lids(e, 0.72 if sx == 1 else 0.36, 0.95 if sx == 1 else 0.7)

t = (0, -0.05, 0.0)
for name, az, el in (("front", 0, 2), ("three_quarter", -35, 6), ("side", -90, 0), ("low", -20, -12)):
    cam = C.look_stage(target=t, dist=0.95, lens=85, azim=az, elev=el, engine=a.engine,
                       res=(1000, 1000))
    C.render_still(os.path.join(a.out, f"{a.who}_{name}.png"), cam)
