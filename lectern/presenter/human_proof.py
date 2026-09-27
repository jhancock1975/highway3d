"""Look at the built professor: stills, a viseme contact sheet, a talking test.

    blender -b lectern/presenter/professor.blend -P lectern/presenter/human_proof.py -- \
        --still OUT_DIR
    ... -- --sheet OUT_DIR
    ... -- --clip OUT_DIR --timeline .work/vo-XXXX.json [--wav .work/vo-XXXX.wav]

(BLENDER_USER_RESOURCES is not needed: the .blend is self-contained.)

The clip drives every face shape key from visemes.face(): the fifteen
visemes02 keys, jawOpen, blinks and brows, with a slow idle drift on the
neck and head so the hair and moustache are seen riding the skin. Frames are
rendered in EEVEE at 1080p and muxed with the narration.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys

import bpy
from mathutils import Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from lectern.presenter import visemes as V  # noqa: E402

FPS = 24


def body():
    return bpy.data.objects["Professor.body"]


def armature():
    return next(o for o in bpy.data.objects if o.type == "ARMATURE")


def head_point():
    arm = armature()
    b = arm.pose.bones["head"]
    h = arm.matrix_world @ b.head
    t = arm.matrix_world @ b.tail
    return h, t


def stage(shot="face", res=(1920, 1080)):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = FPS
    sc.eevee.taa_render_samples = 96
    sc.eevee.use_raytracing = True
    sc.eevee.use_shadows = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.film_transparent = False
    sc.render.hair_type = "STRIP"
    sc.render.hair_subdiv = 1

    for o in [o for o in bpy.data.objects if o.type in ("CAMERA", "LIGHT")]:
        bpy.data.objects.remove(o, do_unlink=True)

    h, t = head_point()
    face = h.lerp(t, 0.45) + Vector((0, -0.09, 0))
    cam_d = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    if shot == "face":
        cam_d.lens = 85
        target = face + Vector((0, 0, -0.05))
        cam.location = target + Vector((0.28, -1.25, 0.03))
    elif shot == "mouth":
        cam_d.lens = 85
        target = face + Vector((0, 0, -0.035))
        cam.location = target + Vector((0.12, -0.72, 0.0))
    else:  # full
        cam_d.lens = 50
        target = Vector((0, 0, 0.9))
        cam.location = Vector((0.9, -4.3, 1.1))
    d = target - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam_d.dof.use_dof = shot != "full"
    cam_d.dof.focus_distance = d.length
    cam_d.dof.aperture_fstop = 4.0
    sc.camera = cam

    def light(name, loc, energy, size, color, aim):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (aim - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        return lo

    light("key", face + Vector((-1.1, -1.4, 0.9)), 260, 1.4, (1.0, 0.9, 0.8), face)
    light("fill", face + Vector((1.4, -1.0, 0.1)), 70, 2.5, (0.85, 0.9, 1.0), face)
    light("rim", face + Vector((0.6, 1.3, 0.7)), 320, 0.8, (0.85, 0.92, 1.0), face)
    light("kick", face + Vector((-1.0, 1.0, 0.2)), 120, 0.8, (1.0, 0.85, 0.7), face)

    w = sc.world or bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs[0].default_value = (0.055, 0.06, 0.075, 1)
    bg.inputs[1].default_value = 1.0

    # a backdrop so the silhouette has something to read against
    if "backdrop" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 3.0, 2.0), rotation=(math.pi / 2, 0, 0))
        bd = bpy.context.active_object
        bd.name = "backdrop"
        m = bpy.data.materials.new("backdrop")
        m.use_nodes = True
        p = m.node_tree.nodes["Principled BSDF"]
        p.inputs["Base Color"].default_value = (0.16, 0.14, 0.13, 1)
        p.inputs["Roughness"].default_value = 0.9
        bd.data.materials.append(m)
    return cam


def keys():
    return body().data.shape_keys.key_blocks


def set_face(values):
    kb = keys()
    for k in list(V.KEYS) + ["jawOpen", "eyeBlinkLeft", "eyeBlinkRight", "browInnerUp",
                             "browOuterUpLeft", "browOuterUpRight"]:
        if k in kb:
            kb[k].value = values.get(k, 0.0)


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def do_still(out):
    for shot in ("face", "full"):
        stage(shot)
        set_face({})
        render(os.path.join(out, f"still_{shot}.png"))


SHEET = [("rest", {}),
         ("aa", {"viseme_aa": 1.0, "jawOpen": 0.55}),
         ("PP", {"viseme_PP": 1.0}),
         ("FF", {"viseme_FF": 1.0}),
         ("TH", {"viseme_TH": 1.0, "jawOpen": 0.1}),
         ("DD", {"viseme_DD": 1.0, "jawOpen": 0.12}),
         ("kk", {"viseme_kk": 1.0, "jawOpen": 0.16}),
         ("CH", {"viseme_CH": 1.0, "jawOpen": 0.08}),
         ("SS", {"viseme_SS": 1.0, "jawOpen": 0.04}),
         ("nn", {"viseme_nn": 1.0, "jawOpen": 0.12}),
         ("RR", {"viseme_RR": 1.0, "jawOpen": 0.12}),
         ("E", {"viseme_E": 1.0, "jawOpen": 0.28}),
         ("I", {"viseme_I": 1.0, "jawOpen": 0.14}),
         ("O", {"viseme_O": 1.0, "jawOpen": 0.4}),
         ("U", {"viseme_U": 1.0, "jawOpen": 0.12}),
         ("blink", {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0, "browInnerUp": 0.6})]


def do_sheet(out, shot="face"):
    stage(shot)
    paths = []
    for name, vals in SHEET:
        set_face(vals)
        p = os.path.join(out, f"sheet_{shot}_{name}.png")
        render(p)
        paths.append(p)
    # 4x4 tile at 1/4 size each -> one 1920x1080 sheet
    lst = os.path.join(out, f"sheet_{shot}.txt")
    inputs = []
    for p in paths:
        inputs += ["-i", p]
    n = len(paths)
    filt = "".join(f"[{i}:v]scale=480:270,drawbox=x=0:y=0:w=480:h=270:color=black@0:t=1[s{i}];" for i in range(n))
    filt = "".join(f"[{i}:v]scale=480:270[s{i}];" for i in range(n))
    layout = "|".join(f"{(i % 4) * 480}_{(i // 4) * 270}" for i in range(n))
    filt += "".join(f"[s{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={layout}"
    subprocess.check_call(["ffmpeg", "-loglevel", "error", "-y", *inputs,
                           "-filter_complex", filt, os.path.join(out, f"sheet_{shot}.png")])
    open(lst, "w").write("\n".join(f"{i}: {name}" for i, (name, _) in enumerate(SHEET)))


def idle_head(n):
    """A slow, small drift on neck and head: alive, not nodding."""
    arm = armature()
    out = []
    for f in range(n):
        t = f / FPS
        rx = 0.035 * noise.noise(Vector((t * 0.35, 1.3, 0)))
        rz = 0.06 * noise.noise(Vector((t * 0.25, 7.1, 0)))
        ry = 0.025 * noise.noise(Vector((t * 0.3, 3.7, 0)))
        out.append((rx, ry, rz))
    for f, (rx, ry, rz) in enumerate(out):
        for bn, s in (("neck01", 0.4), ("head", 0.6)):
            if bn not in arm.pose.bones:
                continue
            pb = arm.pose.bones[bn]
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (rx * s, ry * s, rz * s)
            pb.keyframe_insert("rotation_euler", frame=f + 1)


def do_clip(out, timeline_path, wav, shot, start, seconds):
    tl = json.load(open(timeline_path))
    face = V.face(tl, fps=FPS, jaw=1.0)
    n_all = len(face["viseme_PP"])
    f0 = int(start * FPS)
    f1 = min(n_all, f0 + int(seconds * FPS)) if seconds else n_all
    stage(shot)
    kb = keys()
    for k, vals in face.items():
        if k not in kb:
            continue
        for f in range(f0, f1):
            kb[k].value = vals[f]
            kb[k].keyframe_insert("value", frame=f - f0 + 1)
    # constant interpolation would snap; linear keeps the per-frame values exact
    act = body().data.shape_keys.animation_data.action
    for fc in _fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    idle_head(f1 - f0)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, f1 - f0
    frames = os.path.join(out, "frames")
    os.makedirs(frames, exist_ok=True)
    sc.render.filepath = os.path.join(frames, "f_")
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)
    # the per-frame truth for the frame-by-frame check
    with open(os.path.join(out, "track.json"), "w") as fh:
        json.dump({"start": start, "fps": FPS, "text": tl.get("text"),
                   "frames": [{k: face[k][f] for k in face} for f in range(f0, f1)]}, fh)
    mp4 = os.path.join(out, "talk_test.mp4")
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS),
           "-i", os.path.join(frames, "f_%04d.png")]
    if wav:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{(f1 - f0) / FPS:.3f}", "-i", wav]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16"]
    if wav:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd.append(mp4)
    subprocess.check_call(cmd)
    print("[proof] wrote", mp4)


def _fcurves(action):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--still")
    ap.add_argument("--sheet")
    ap.add_argument("--sheet-shot", default="face")
    ap.add_argument("--clip")
    ap.add_argument("--timeline")
    ap.add_argument("--wav")
    ap.add_argument("--shot", default="face")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=0.0)
    ap.add_argument("--samples", type=int, default=0)
    a = ap.parse_args(argv)
    for d in (a.still, a.sheet, a.clip):
        if d:
            os.makedirs(d, exist_ok=True)
    if a.still:
        do_still(a.still)
    if a.sheet:
        do_sheet(a.sheet, a.sheet_shot)
    if a.clip:
        do_clip(a.clip, a.timeline, a.wav, a.shot, a.start, a.seconds)


main()
