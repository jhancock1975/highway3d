"""Thumbnail every fetched Poly Haven model with its size.

    blender -b --factory-startup -P cartoon/tools/props_sheet.py -- --out DIR
"""
import os, sys, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import bpy
from mathutils import Vector
from cartoon import assets
from cartoon.bl import common as C

argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args(argv)
os.makedirs(a.out, exist_ok=True)
for name in assets.MODELS:
    C.clear_scene()
    p = assets.path_of(name)
    with bpy.data.libraries.load(p, link=False) as (src, dst):
        dst.objects = src.objects
    obs = [o for o in dst.objects if o is not None]
    for o in obs:
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in obs if o.type == "MESH" for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    size = hi - lo
    print(f"[size] {name}: {size.x:.2f} x {size.y:.2f} x {size.z:.2f}  min z {lo.z:.2f}  objs {[o.name for o in obs][:6]}", flush=True)
    ctr = (lo + hi) / 2
    cam = C.look_stage(target=tuple(ctr), dist=max(size) * 2.4, lens=50, azim=-30, elev=15, res=(400, 400))
    C.render_still(os.path.join(a.out, f"{name}.png"), cam)
