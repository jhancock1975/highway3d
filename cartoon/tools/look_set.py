"""Build a set with the cast on their marks and render a few views.

    blender -b --factory-startup -P cartoon/tools/look_set.py -- --time night --out DIR
"""
import argparse, os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import bpy
from mathutils import Vector
from cartoon.bl import common as C, cast
from cartoon.sets import study

argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--time", default="night"); ap.add_argument("--out", required=True)
ap.add_argument("--engine", default="BLENDER_EEVEE"); ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--res", default="1280x720"); ap.add_argument("--no-cast", action="store_true")
a = ap.parse_args(argv)
os.makedirs(a.out, exist_ok=True)
C.clear_scene()
S = study.build(a.time)
m = S["marks"]
if not a.no_cast:
    eu = cast.load("euler"); cast.place(eu, m["euler"]["loc"], m["euler"]["yaw"])
    ci = cast.load("cinnamon"); cast.place(ci, m["cinnamon_home"], 30)
sc = bpy.context.scene
w = sc.world or bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.01, 0.012, 0.02, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
rx, ry = map(int, a.res.split("x"))
sc.render.resolution_x, sc.render.resolution_y = rx, ry
sc.render.engine = a.engine
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Medium High Contrast"
if a.engine == "CYCLES":
    sc.cycles.device = "GPU"; sc.cycles.samples = a.samples; sc.cycles.use_denoising = True
    import blender_gpu; blender_gpu.enable(bpy)
else:
    sc.eevee.taa_render_samples = a.samples; sc.eevee.use_raytracing = True
    sc.eevee.use_shadows = True
views = {
    "wide": ((1.4, -2.7, 1.6), (-0.1, 0.8, 1.0), 26),
    "two_shot": ((0.6, -1.6, 1.35), (-0.15, 0.5, 1.15), 40),
    "euler_ms": ((0.9, -0.7, 1.3), (0.2, 0.85, 1.15), 50),
    "reverse": ((0.9, 1.6, 1.5), (-0.4, 0.0, 1.1), 35),
}
for name, (loc, tgt, lens) in views.items():
    cd = bpy.data.cameras.new(name); cd.lens = lens
    cam = bpy.data.objects.new(name, cd); sc.collection.objects.link(cam)
    cam.location = loc; C.aim(cam, tgt)
    C.render_still(os.path.join(a.out, f"{a.time}_{name}.png"), cam)
