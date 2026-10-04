"""Render one shot of a film, or prepare the set a shot is rendered in.

    # once per scene and time of day: the set with the cast in it
    blender -b --factory-startup -P cartoon/shot.py -- --prepare study:night --out .work/cartoon/sets/study_night.blend

    # a shot, opened from its prepared set
    blender -b .work/cartoon/sets/study_night.blend -P cartoon/shot.py -- \
        --film .work/cartoon/flavor/film.json --shot 5 --boards .work/cartoon/flavor/boards --out DIR

Frames come out as numbered PNGs in DIR (global frame numbers), so a crash
costs only the frame it happened on and assembly can start anywhere.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from cartoon.bl import cast, common as C  # noqa: E402
from cartoon.sets import marks as MK  # noqa: E402


def gpu_setup():
    import blender_gpu
    blender_gpu.enable(bpy)


def render_settings(engine, res, samples, fps=24):
    sc = bpy.context.scene
    # The sculpts are already dense (2-4 mm voxels). Subdividing them again
    # at render cost 15 of every 16 seconds a frame took and changed nothing
    # visible even in a close-up; only the thin eyelid shells need it.
    for o in bpy.data.objects:
        for m in o.modifiers:
            if m.type == "SUBSURF" and "lid" not in o.name:
                m.render_levels = 0
    sc.render.fps = fps
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.compression = 30
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.4
    if engine == "CYCLES":
        sc.render.engine = "CYCLES"
        gpu_setup()
        sc.cycles.device = "GPU"
        sc.cycles.samples = samples
        sc.cycles.use_adaptive_sampling = True
        sc.cycles.adaptive_threshold = 0.02
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
        sc.cycles.denoising_use_gpu = True
        sc.cycles.max_bounces = 8
        sc.cycles.caustics_reflective = False
        sc.cycles.caustics_refractive = False
        sc.render.use_persistent_data = True
    else:
        sc.render.engine = "BLENDER_EEVEE"
        sc.eevee.taa_render_samples = samples
        sc.eevee.use_raytracing = True
        sc.eevee.ray_tracing_options.resolution_scale = "1"
        sc.eevee.use_shadows = True
        sc.eevee.shadow_ray_count = 2
        sc.eevee.use_volumetric_shadows = True
        sc.eevee.fast_gi_method = "GLOBAL_ILLUMINATION"
        sc.eevee.shadow_pool_size = "1024"
        _tame_shadows()


def _tame_shadows():
    """Only lights that shape the picture cast shadows.

    EEVEE's virtual shadow maps come out of one fixed pool, and five candle
    flames, the moon, the fills and two antenna tips overflowed it (2375 of
    2048 pages): frames took 40 s and shadows went missing. The candelabra
    casts through one of its flames; fills and glows cast none.
    """
    for o in bpy.data.objects:
        if o.type != "LIGHT":
            continue
        n = o.name
        L = o.data
        if n.startswith("candle") and n != "candle0":
            L.use_shadow = False
        elif any(k in n for k in ("fill", "bounce", "rim", "glow", "stove", "cinnamon.key", "sky")):
            L.use_shadow = False
        if L.use_shadow:
            L.shadow_maximum_resolution = 0.002 if n in ("moon", "sun", "euler_key") else 0.004


def prepare(scene_time, out):
    scene, time = scene_time.split(":")
    C.clear_scene()
    if scene == "study":
        from cartoon.sets import study
        S = study.build(time)
        eu = cast.load("euler")
        cast.place(eu, MK.EULER, MK.EULER_YAW)
        _chalk(eu)
        if time == "night":
            ci = cast.load("cinnamon")
            cast.place(ci, MK.CINNAMON["outside"], 0)
            _antenna_glow(ci)
            _cinnamon_key(ci)
            _scent_puff()
            from cartoon.sets import petersburg
            ship = petersburg.build_ship(bpy.context.scene.collection)
            ship.scale = (0.8, 0.8, 0.8)
            ship.location = (0, 0, -30)
    elif scene == "petersburg":
        from cartoon.sets import petersburg
        petersburg.build(time)
    elif scene == "vision":
        from cartoon.sets import vision
        vision.build()
    if scene != "vision":
        w = bpy.context.scene.world or bpy.data.worlds.new("w")
        bpy.context.scene.world = w
        w.use_nodes = True
        bg = w.node_tree.nodes["Background"]
        bg.inputs[0].default_value = (0.012, 0.014, 0.024, 1) if time in ("night",) else (0.4, 0.45, 0.55, 1)
        bg.inputs[1].default_value = 1.0 if time == "night" else 0.4
    bpy.context.scene["scene_time"] = scene_time
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    C.log("prepared", scene_time, out)


def _chalk(arm):
    """A stick of chalk in Euler's right hand, shown only while he writes."""
    bpy.ops.mesh.primitive_cylinder_add(radius=0.0055, depth=0.065, vertices=12)
    ch = bpy.context.active_object
    ch.name = "euler.chalk"
    for c in ch.users_collection:
        c.objects.unlink(ch)
    arm.users_collection[0].objects.link(ch)
    ch.data.materials.append(bpy.data.materials.get("st.chalk") or C.mat_plain("st.chalk", (0.9, 0.9, 0.88), rough=0.95))
    ch.parent = arm
    ch.parent_type = "BONE"
    ch.parent_bone = "f_index_2.R"
    # in the bone's frame: across the finger tips, pointing out of the fist
    ch.location = (0.0, 0.0, -0.012)
    ch.rotation_euler = (math.radians(90), 0, math.radians(20))
    ch.hide_render = True


def _cinnamon_key(arm):
    """A soft warm key that travels with Cinnamon, above and in front."""
    ld = bpy.data.lights.new("cinnamon.key", "AREA")
    ld.energy = 2.6
    ld.size = 0.6
    ld.color = (1.0, 0.78, 0.55)
    lo = bpy.data.objects.new("cinnamon.key", ld)
    arm.users_collection[0].objects.link(lo)
    lo.parent = arm
    lo.location = (0.35, -0.75, 0.55)
    C.aim(lo, (0, 0, 0.1))


def _scent_puff(n=14):
    """Little glowing blobs of scent, parked out of sight until a puff."""
    m = bpy.data.materials.new("scent")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (1.0, 0.62, 0.3, 1)
    p.inputs["Emission Color"].default_value = (1.0, 0.55, 0.25, 1)
    p.inputs["Emission Strength"].default_value = 2.5
    p.inputs["Alpha"].default_value = 0.35
    p.inputs["Roughness"].default_value = 0.8
    m.surface_render_method = "BLENDED"
    for i in range(n):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=16, ring_count=8, location=(0, 0, -20))
        o = bpy.context.active_object
        o.name = f"scent.{i:02d}"
        o.scale = (1e-4, 1e-4, 1e-4)
        o.data.materials.append(m)
        o.visible_shadow = False
        bpy.ops.object.shade_smooth()


def _antenna_glow(arm):
    """Tiny lavender lights at the antenna tips: the room sees it."""
    for s in (".L", ".R"):
        ld = bpy.data.lights.new("cinnamon.glow" + s, "POINT")
        ld.energy = 0.6
        ld.color = (0.55, 0.45, 1.0)
        ld.shadow_soft_size = 0.02
        lo = bpy.data.objects.new("cinnamon.glow" + s, ld)
        arm.users_collection[0].objects.link(lo)
        lo.parent = arm
        lo.parent_type = "BONE"
        lo.parent_bone = "ant_4" + s
        lo.location = (0, 0.05, 0)


def rigs():
    out = {}
    for o in bpy.data.objects:
        if o.type == "ARMATURE" and "character" in o:
            out[o["character"]] = o
    return out


def set_board(boards_dir, f0):
    face = bpy.data.objects.get("slate.face")
    if face is None or not boards_dir:
        return
    first = os.path.join(os.path.abspath(boards_dir), f"board_{f0:05d}.png")
    if not os.path.exists(first):
        have = sorted(f for f in os.listdir(boards_dir) if f.startswith("board_"))
        later = [f for f in have if int(f[6:11]) >= f0]
        if not later:
            C.log("no board frames from", f0)
            return
        first = os.path.join(os.path.abspath(boards_dir), later[0])
    m = face.active_material
    node = m.node_tree.nodes["writing"]
    img = bpy.data.images.load(first)
    img.source = "SEQUENCE"
    img.alpha_mode = "CHANNEL_PACKED"
    img.colorspace_settings.name = "Non-Color"
    node.image = img
    iu = node.image_user
    iu.frame_start = 1
    iu.frame_offset = 0
    iu.frame_duration = 100000
    iu.use_auto_refresh = True
    # wet: the red channel darkens the slate and makes it shine
    nt = m.node_tree
    if "wet_sep" not in nt.nodes:
        p = nt.nodes["Principled BSDF"]
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        sep.name = "wet_sep"
        nt.links.new(node.outputs["Color"], sep.inputs["Color"])
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        base_link = p.inputs["Base Color"].links[0]
        src = base_link.from_socket
        nt.links.new(sep.outputs["Red"], mul.inputs["Factor"])
        nt.links.new(src, mul.inputs["A"])
        mul.inputs["B"].default_value = (0.45, 0.47, 0.5, 1)
        nt.links.new(mul.outputs["Result"], p.inputs["Base Color"])
        r_link = p.inputs["Roughness"].links[0].from_socket
        rm = nt.nodes.new("ShaderNodeMix")
        rm.data_type = "FLOAT"
        nt.links.new(sep.outputs["Red"], rm.inputs["Factor"])
        nt.links.new(r_link, rm.inputs["A"])
        rm.inputs["B"].default_value = 0.15
        nt.links.new(rm.outputs["Result"], p.inputs["Roughness"])


def _lick_camera(film, shot, P, f0, f1):
    """See sets/lick.py: the same camera the slate's wet streak and the
    tongue's reach were worked out for."""
    from cartoon.sets import lick as LK
    b = next((film["beats"][i] for i in shot["beats"] if film["beats"][i].get("target")), None)
    board = b["target"] if b else "product"
    cam = LK.camera(film["setups"]["two"], board)
    C.log(f"lick camera: {cam['deg']} degrees round from the two-shot, {cam['seen']:.0%} of the chalk and tongue in view")
    return dict(loc=cam["loc"], target=cam["target"], lens=cam["lens"])


def camera(setup, f0, f1, film, P=None, shot=None):
    import numpy as np
    sc = bpy.context.scene
    s = film["setups"].get(setup)
    if s is None:
        s = dict(loc=[1.25, -1.05, 1.38], target=[0.02, 0.55, 1.15], lens=32)
    if s.get("track") == "lick" and P is not None:
        s = _lick_camera(film, shot, P, f0, f1)
    cd = bpy.data.cameras.new("shot")
    cd.lens = s["lens"]
    cd.sensor_width = 36
    cam = bpy.data.objects.new("shot", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    loc0 = Vector(s["loc"])
    tgt = Vector(s["target"])
    n = max(1, f1 - f0)
    track = s.get("track")
    if track in ("cinnamon", "both") and P is not None:
        # follow the subject, softly: an operator, not a rig
        from cartoon.bl.perform import lag_series
        cp = np.array(P.cpos)
        if track == "both":
            eh = np.array(MK.HEAD_EULER)
            subj = (cp + eh) / 2
            ref = (np.array(MK.CINNAMON["home"]) + eh) / 2
        else:
            subj = cp + np.array([0, 0, 0.06])
            ref = np.array(s.get("mark", s["target"]))
        pre = max(0, f0 - 48)
        seg = np.array([lag_series(subj[pre:f1 + 1, i], film["fps"], 0.35) for i in range(3)]).T
        k = s.get("follow", 0.8)
        # Cinnamon's top (antennae and all) and bottom, and Euler's head:
        # the frame keeps all of them. Following the midpoint alone, when
        # Cinnamon rose to its high mark after the spin, cut its head off at
        # the top of the frame; tilting up alone then lost Euler at the bottom.
        lagged = np.array([lag_series(cp[pre:f1 + 1, i], film["fps"], 0.35) for i in range(3)]).T
        raw = cp[pre:f1 + 1]
        half_v = math.atan(18.0 / s["lens"] * 9 / 16) - 0.05
        eh = Vector(MK.HEAD_EULER)
        for f in range(f0, f1 + 1, 2):
            off = (seg[f - pre] - ref) * k
            push = (tgt - loc0) * 0.04 * ((f - f0) / n)
            cam.location = loc0 + Vector(off) * (0.7 if track == "both" else 1.0) + push
            aim_at = tgt + Vector(off)
            if track == "both":
                c_now = [Vector(lagged[f - pre]), Vector(raw[f - pre])]
                pts = [c + Vector((0, 0, 0.42)) for c in c_now] + [c + Vector((0, 0, -0.26)) for c in c_now] + \
                      [eh + Vector((0, 0, 0.2)), eh + Vector((0, 0, -0.16))]
                for _ in range(3):
                    fwd = (aim_at - cam.location).normalized()
                    hz = Vector((fwd.x, fwd.y, 0)).normalized()
                    pitch0 = math.atan2(fwd.z, Vector((fwd.x, fwd.y, 0)).length)
                    angs = []
                    for p_ in pts:
                        w = p_ - cam.location
                        angs.append(math.atan2(w.z, max(1e-6, w.dot(hz))))
                    lo, hi = min(angs), max(angs)
                    if hi - lo > 2 * half_v:
                        # both cannot fit: step back along the view until they do
                        cam.location = cam.location - fwd * (aim_at - cam.location).length * 0.12
                        continue
                    want = min(max(pitch0, hi - half_v), lo + half_v)
                    if abs(want - pitch0) < 1e-3:
                        break
                    d = (aim_at - cam.location)
                    flat = Vector((d.x, d.y, 0)).length
                    aim_at = Vector((aim_at.x, aim_at.y, cam.location.z + flat * math.tan(want)))
            C.aim(cam, aim_at)
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
    else:
        # a slow push-in over the shot, so no frame is quite still
        for f in (f0, f1):
            k = (f - f0) / n
            cam.location = loc0 + (tgt - loc0) * 0.045 * k
            C.aim(cam, tgt)
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
    cd.dof.use_dof = True
    cd.dof.focus_distance = (tgt - loc0).length
    cd.dof.aperture_fstop = 2.8 if s["lens"] >= 50 else 4.0
    return cam


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare")
    ap.add_argument("--film")
    ap.add_argument("--shot", type=int)
    ap.add_argument("--boards")
    ap.add_argument("--chalk", help="typeset formulas (for the sky-writing)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default="BLENDER_EEVEE")
    ap.add_argument("--res", default="1920x1080")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--frames", help="only these frames, e.g. 1200:1210 or 1205")
    ap.add_argument("--save-blend", action="store_true")
    ap.add_argument("--step", type=int, default=1, help="render every Nth frame (for review sheets)")
    a = ap.parse_args(argv)
    if a.prepare:
        prepare(a.prepare, a.out)
        return
    with open(a.film) as fh:
        film = json.load(fh)
    shot = film["shots"][a.shot]
    fps = film["fps"]
    f0 = int(round(shot["start"] * fps))
    f1 = int(round(shot["end"] * fps)) - 1
    if shot["setup"].startswith("vision_"):
        from cartoon.bl import visions
        visions.animate(shot["setup"][len("vision_"):], film, shot, f0, f1)
    elif shot["scene"] == "petersburg":
        from cartoon.bl import exterior
        if shot["time"] == "night":
            exterior.night(film, shot, f0, f1)
        else:
            chalk_dir = a.chalk or os.path.join(os.path.dirname(os.path.abspath(a.film)), "chalk")
            png = next(os.path.join(chalk_dir, f) for f in sorted(os.listdir(chalk_dir))
                       if f.startswith("identity-") and f.endswith(".png"))
            exterior.dawn(film, shot, f0, f1, png)
    else:
        from cartoon.bl.perform import Performer
        R = rigs()
        set_board(a.boards, f0)
        P = Performer(film, R, f0, f1)
        P.run()
        camera(shot["setup"], f0, f1, film, P, shot)
    rx, ry = map(int, a.res.split("x"))
    render_settings(a.engine, (rx, ry), a.samples, fps)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = f0, f1
    if a.frames:
        if ":" in a.frames:
            x, y = a.frames.split(":")
            sc.frame_start, sc.frame_end = int(x), int(y)
        else:
            sc.frame_start = sc.frame_end = int(a.frames)
    sc.frame_step = max(1, a.step)
    os.makedirs(a.out, exist_ok=True)
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.abspath(a.out), f"shot{a.shot:03d}.blend"))
    sc.render.filepath = os.path.join(os.path.abspath(a.out), "f_#####")
    sc.render.use_overwrite = False
    sc.render.use_placeholder = True
    bpy.ops.render.render(animation=True)
    C.log(f"shot {a.shot} frames {sc.frame_start}-{sc.frame_end} done")


if __name__ == "__main__":
    main()
