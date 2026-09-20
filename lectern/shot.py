"""Render one shot: set, presenter, performance, frames, audio, mp4.

Runs inside Blender:

    blender --background --factory-startup --python lectern/shot.py -- \
        --timeline work/seg000.json --audio work/seg000.wav \
        --out renders/shot000.mp4 --engine eevee

A shot knows its own duration and nothing about where it sits in the
lecture. That is deliberate: timing is speech-driven, so changing a sentence
early on shifts every start time after it, and a shot that knew its absolute
position would be invalidated by an edit three chapters away. Placement
happens at assembly, which is cheap; rendering is not.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lectern.delivery import BEATS  # noqa: E402
from lectern.presenter import character, visemes  # noqa: E402
from lectern.stage import demos  # noqa: E402
from lectern.stage import set as stage  # noqa: E402


# ---------------------------------------------------------------- animation

def animate_mouth(parts, track, fps):
    """Keyframe the mouth cavity from the viseme track."""
    mouth = next(o for o in parts["all"] if o.name == "mouth")
    bx, by, bz = mouth.scale
    base_z = mouth.location.z
    for f in track:
        frame = f["frame"] + 1
        mouth.scale = (bx * f["wide"] * (0.72 + 0.28 * f["round"]),
                       by,
                       bz * (0.28 + 1.05 * f["open"]))
        # the jaw drops as the mouth opens, so it does not grow upward
        mouth.location.z = base_z - character.HEAD_R * 0.085 * f["open"]
        mouth.keyframe_insert("scale", frame=frame)
        mouth.keyframe_insert("location", frame=frame)


def animate_blinks(parts, n_frames, fps, seed=11, words=None):
    """Blinks, biased toward the gaps between sentences.

    A character who never blinks is the single loudest tell that nothing is
    alive behind the face, and it costs four keyframes each.
    """
    rng = random.Random(seed)
    eyes = [o for o in parts["all"] if o.name.startswith(("eye.", "iris."))]
    base = {o.name: tuple(o.scale) for o in eyes}

    moments = []
    t = rng.uniform(0.6, 2.0)
    while t < n_frames / fps:
        moments.append(t)
        t += rng.uniform(1.9, 4.6)
    # one just after each sentence ends, which is where people actually blink
    for w in (words or []):
        if w["text"].strip() in {".", "?", "!"}:
            moments.append(w["end"] + rng.uniform(0.02, 0.14))

    for o in eyes:
        bx, by, bz = base[o.name]
        o.scale = (bx, by, bz)
        o.keyframe_insert("scale", frame=1)
    for t in sorted(moments):
        mid = int(t * fps) + 1
        if mid < 2 or mid > n_frames - 2:
            continue
        for o in eyes:
            bx, by, bz = base[o.name]
            for frame, k in ((mid - 2, 1.0), (mid, 0.06), (mid + 2, 1.0)):
                o.scale = (bx, by, bz * k)
                o.keyframe_insert("scale", frame=frame)


def animate_head(parts, n_frames, fps, seed=3, words=None, look_at=None):
    """Idle sway, plus a small settle on each stressed word.

    Not a performance -- that comes from the beat library later -- but enough
    that he is not a photograph with a moving mouth.
    """
    rng = random.Random(seed)
    root = parts["root"]
    phase = [rng.uniform(0, 6.28) for _ in range(6)]

    accents = set()
    for w in (words or []):
        if len(w["text"].strip()) > 4:
            accents.add(round(w["start"], 2))

    for frame in range(1, n_frames + 1):
        t = (frame - 1) / fps
        rx = (0.030 * math.sin(t * 0.7 + phase[0])
              + 0.014 * math.sin(t * 1.9 + phase[1]))
        ry = (0.026 * math.sin(t * 0.5 + phase[2])
              + 0.011 * math.sin(t * 1.3 + phase[3]))
        rz = (0.020 * math.sin(t * 0.9 + phase[4])
              + 0.009 * math.sin(t * 2.3 + phase[5]))
        nod = 0.0
        for a in accents:
            d = t - a
            if 0.0 <= d < 0.26:
                nod -= 0.030 * math.sin(d / 0.26 * math.pi)
        # Turned toward whatever he is presenting, most of the time, with a
        # glance back to camera on the stressed words. A presenter who stares
        # down the lens while a demonstration runs beside him reads as a
        # newsreader, not a teacher.
        toward = 0.0
        if look_at is not None:
            toward = -0.34 * math.atan2(look_at.x + 0.66, 1.6)
            glance = 0.0
            for a_ in accents:
                d = t - a_
                if 0.0 <= d < 0.55:
                    glance = max(glance, math.sin(d / 0.55 * math.pi))
            toward *= (1.0 - 0.75 * glance)
        root.rotation_euler = (rx + nod, ry, rz + toward)
        root.location = (0.0, 0.0, 0.004 * math.sin(t * 1.15 + phase[0]))
        root.keyframe_insert("rotation_euler", frame=frame)
        root.keyframe_insert("location", frame=frame)


def staged_extent(objects, n_frames, step=6):
    """How wide the demonstration actually gets, in world x, over the take.

    Not the width it declares. Every demonstration reports a `width`, and
    that number is the footprint its plinth needs -- it is not the space the
    thing sweeps once it starts moving. Michelson's interferometer rotates
    88 degrees through the shot; framed to its declared width it is correct
    on frame one and hanging off the right of the frame by the middle.

    So this samples the real bounding box across the animation, which costs
    a depsgraph evaluation every sixth frame against the two hundred seconds
    the shot takes to render.
    """
    scene = bpy.context.scene
    lo, hi = 1e9, -1e9
    for f in range(1, max(2, n_frames) + 1, step):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for o in objects:
            if not hasattr(o, "bound_box") or o.type == "EMPTY":
                continue
            ob = o.evaluated_get(dg)
            for corner in ob.bound_box:
                x = (ob.matrix_world @ Vector(corner)).x
                lo = min(lo, x)
                hi = max(hi, x)
    scene.frame_set(1)
    return (lo, hi) if hi > lo else (None, None)


def animate_body(parts, n_frames, fps, seed=17, words=None, focus=None,
                 beat=""):
    """Breath, weight and gesture -- the half of the performance that was
    missing.

    There used to be no body animation here at all, and there could not have
    been: the torso, the neck and both arms were joined into a single mesh
    and voxel-remeshed before the bake, so below the head there was exactly
    one transform and nothing on it worth a keyframe. A presenter who holds
    perfectly still from the collar down for twenty-three minutes reads as a
    photograph someone has animated the mouth of, which is what it was.

    Three layers, deliberately on different clocks, because a figure whose
    every part turns over at the same rate reads as a mechanism:

    - breath, at about thirteen a minute, on the torso itself;
    - weight, shifting foot to foot every eight seconds or so, on the root;
    - gesture, on the arms, landing on words rather than on a timer.
    """
    rng = random.Random(seed)
    body = parts["body_root"]
    torso = parts["torso"]
    arms = parts["arms"]

    rest = {side: (tuple(a["shoulder"].rotation_euler), (0.22, 0.0, 0.0))
            for side, a in arms.items()}
    for side, a in arms.items():
        a["elbow"].rotation_euler = rest[side][1]

    # The hand he presents with is the one on the side the thing is on.
    near = "L"
    if focus is not None:
        near = "R" if (focus.x - parts["stand"].location.x) < 0 else "L"
    far = "R" if near == "L" else "L"

    tx, ty, tz = torso.scale
    ph = [rng.uniform(0, 6.28) for _ in range(5)]
    breath_hz = rng.uniform(0.20, 0.25)
    shift_hz = rng.uniform(0.09, 0.14)

    for frame in range(1, n_frames + 1):
        t = (frame - 1) / fps
        b = math.sin(2 * math.pi * breath_hz * t + ph[0])
        # Chest, not belly: the depth moves most, the width a little, the
        # height least. Scaling all three equally makes him inflate.
        torso.scale = (tx * (1 + 0.009 * b), ty * (1 + 0.017 * b),
                       tz * (1 + 0.006 * b))
        torso.keyframe_insert("scale", frame=frame)

        s = math.sin(2 * math.pi * shift_hz * t + ph[1])
        s2 = math.sin(2 * math.pi * shift_hz * 0.63 * t + ph[2])
        body.location = (0.018 * s, 0.0,
                         -0.004 * abs(s) + 0.003 * b)
        body.rotation_euler = (0.010 * b, 0.013 * s2, -0.022 * s)
        body.keyframe_insert("location", frame=frame)
        body.keyframe_insert("rotation_euler", frame=frame)

    def key(joint, t, rot, lag=0):
        f = int(t * fps) + 1 + lag
        if 1 <= f <= n_frames:
            joint.rotation_euler = rot
            joint.keyframe_insert("rotation_euler", frame=f)

    for side, a in arms.items():
        key(a["shoulder"], 0.0, rest[side][0])
        key(a["elbow"], 0.0, rest[side][1])

    # Gestures start on a word, never on a clock: a stroke that lands between
    # syllables looks like a twitch, and one that lands on a stressed vowel
    # looks like emphasis, which is the entire difference.
    spoken = [w["start"] for w in (words or [])
              if len(w["text"].strip()) > 3]
    last_end = n_frames / fps - 1.1
    moments, t = [], rng.uniform(0.7, 1.5)
    while t < last_end:
        nxt = next((w for w in spoken if w >= t), None)
        if nxt is None or nxt > last_end:
            break
        moments.append(nxt)
        t = nxt + rng.uniform(2.4, 4.6)

    KINDS = ("beat", "beat", "beat", "present", "open", "count")
    # The document gets the opening gesture; the rest are chosen here. That
    # is the whole of what `beat` does, and it is now the only thing it
    # claims to do.
    opening = BEATS.get(beat, "present") if beat else "present"
    if opening is None:
        moments = []
    for i, t0 in enumerate(moments):
        kind = KINDS[rng.randrange(len(KINDS))] if i else opening
        use = near if kind in ("present", "open") else (
            near if rng.random() < 0.6 else far)
        a = arms[use]
        sgn = a["sign"]
        sh0, el0 = rest[use]

        if kind == "beat":
            sh = (sh0[0] - 0.30, sh0[1], sh0[2])
            el = (el0[0] + 0.55, 0.0, sgn * 0.10)
        elif kind == "present":
            sh = (sh0[0] - 0.52, sh0[1] + sgn * 0.30, sh0[2] - sgn * 0.16)
            el = (el0[0] + 0.34, 0.0, sgn * 0.26)
        elif kind == "point":
            # Arm further out and the elbow nearly straight: a point reads as
            # a line from the shoulder to the thing, and a bent elbow breaks
            # the line.
            sh = (sh0[0] - 0.74, sh0[1] + sgn * 0.22, sh0[2] - sgn * 0.20)
            el = (el0[0] - 0.14, 0.0, sgn * 0.06)
        elif kind == "open":
            sh = (sh0[0] - 0.38, sh0[1] + sgn * 0.44, sh0[2])
            el = (el0[0] + 0.30, 0.0, sgn * 0.34)
        else:                                       # count: hand up, held
            sh = (sh0[0] - 0.66, sh0[1], sh0[2])
            el = (el0[0] + 0.95, 0.0, sgn * 0.05)

        def blend(r0, r1, k):
            return tuple(x + (y - x) * k for x, y in zip(r0, r1))

        hold = rng.uniform(0.55, 1.05)
        # anticipation, stroke past the pose, settle back onto it, release --
        # and the forearm two frames behind the upper arm throughout, so the
        # arm arrives as a limb rather than as one rigid piece.
        key(a["shoulder"], t0 - 0.16, blend(sh0, sh, -0.18))
        key(a["elbow"], t0 - 0.16, blend(el0, el, -0.18), lag=2)
        key(a["shoulder"], t0 + 0.16, blend(sh0, sh, 1.10))
        key(a["elbow"], t0 + 0.16, blend(el0, el, 1.14), lag=2)
        key(a["shoulder"], t0 + 0.30, sh)
        key(a["elbow"], t0 + 0.30, el, lag=2)
        key(a["shoulder"], t0 + 0.30 + hold, sh)
        key(a["elbow"], t0 + 0.30 + hold, el, lag=2)
        key(a["shoulder"], t0 + 0.30 + hold + 0.55, sh0)
        key(a["elbow"], t0 + 0.30 + hold + 0.55, el0, lag=3)


def _fcurves(action):
    """Every f-curve in an action, on either Action API.

    Blender 4.4 replaced `action.fcurves` with slotted actions -- layers,
    strips, channelbags -- and 5.x dropped the old attribute entirely.
    """
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                yield from bag.fcurves


def ease_interpolation():
    """Bezier, not linear. Linear keys are what make cheap animation read
    as cheap: everything arrives at a constant speed and stops dead."""
    for action in bpy.data.actions:
        for fc in _fcurves(action):
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"


# ------------------------------------------------------------------- render

def _enable_gpu() -> str:
    """Turn the Metal GPU on, and say which device Cycles will actually use.

    `cycles.devices` is empty until the preferences are refreshed, so setting
    `scene.cycles.device = "GPU"` on a fresh --factory-startup silently renders
    on the CPU instead: the first measurement here came out at 7s a frame,
    which over a 24-minute lecture is six days rather than one night.
    """
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return "CPU"
    prefs = addon.preferences
    try:
        prefs.compute_device_type = "METAL"
        for attr in ("get_devices", "refresh_devices"):
            if hasattr(prefs, attr):
                getattr(prefs, attr)()
        gpus = [d for d in prefs.devices if d.type == "METAL"]
        if not gpus:
            return "CPU"
        for d in prefs.devices:
            d.use = (d.type == "METAL")
        print("cycles device:", ", ".join(d.name for d in gpus), flush=True)
        return "GPU"
    except Exception as e:
        print("no GPU, falling back to CPU:", e, flush=True)
        return "CPU"


def configure(engine, width, height, samples, fps, n_frames, view="punchy",
              bounces=4, denoise=True, fast_gi=False,
              denoise_quality="BALANCED"):
    scene = bpy.context.scene
    r = scene.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, 100
    r.fps = fps
    scene.frame_start, scene.frame_end = 1, n_frames

    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = denoise
        # OpenImageDenoise defaults to the CPU, and at 1080p that was 4.7 of
        # every 5.3 seconds a frame -- the path tracing itself is about 0.6s.
        # On the GPU the same pass is nearly free.
        if denoise:
            if hasattr(scene.cycles, "denoising_use_gpu"):
                scene.cycles.denoising_use_gpu = True
            scene.cycles.denoising_quality = denoise_quality
            scene.cycles.denoising_prefilter = "FAST"
        # A lit interior with three soft area lights does not need twelve
        # bounces; past about four, nothing in this set changes and every
        # frame pays for it.
        scene.cycles.max_bounces = bounces
        scene.cycles.diffuse_bounces = bounces
        scene.cycles.glossy_bounces = min(bounces, 3)
        scene.cycles.transmission_bounces = min(bounces, 2)
        scene.cycles.volume_bounces = 0
        scene.cycles.use_fast_gi = fast_gi
        scene.cycles.device = _enable_gpu()
    else:
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = max(16, samples // 4)
        for flag in ("use_raytracing", "use_shadows", "use_gtao"):
            if hasattr(scene.eevee, flag):
                setattr(scene.eevee, flag, True)

    if view == "punchy":
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Punchy"
    elif view == "standard":
        scene.view_settings.view_transform = "Standard"
    else:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"


def render_one(job: dict, opt) -> dict:
    """Build, animate and encode one shot in the current Blender process."""
    began = time.time()
    with open(job["timeline"]) as fh:
        timeline = json.load(fh)

    track = visemes.track(timeline, fps=opt.fps)
    # A beat at the end, mouth closed: cutting on the last syllable of every
    # sentence reads as an edit made by a machine, which it is.
    rest = visemes.VISEMES["REST"]
    for _ in range(int(round(job.get("tail", 0.0) * opt.fps))):
        track.append(dict(frame=len(track), viseme="REST",
                          open=rest[0], wide=rest[1], round=rest[2]))
    n_frames = len(track)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    configure(opt.engine, opt.width, opt.height, opt.samples, opt.fps,
              n_frames, opt.view, bounces=opt.bounces,
              denoise=not opt.no_denoise, fast_gi=opt.fast_gi)

    scene_parts = stage.build(job.get("look", "study"))
    parts = character.build()

    focus = None
    notation = job.get("notation", "")
    demo = job.get("demo", "")
    # Chalk first, and independently of where he stands. These used to be one
    # if/elif, and every demonstration segment also carries notation -- the
    # board keeps the chapter title up during a demonstration, deliberately --
    # so `notation` was always truthy and the `elif demo:` branch had never
    # run. All twenty demonstrations in this lecture rendered as an empty
    # board with him talking beside it: he says "Galileo asks you to go below
    # deck on a ship" over a blank slate. Nothing errors, so it survived
    # every render.
    if notation:
        have = sorted(f for f in os.listdir(notation) if f.endswith(".png"))
        last = os.path.join(notation, have[-1])
        # Blender renders a magenta "missing texture" past the end of an image
        # sequence, so a board that finishes writing before he finishes
        # talking would turn bright pink for the rest of the take.
        for i in range(len(have), n_frames + 2):
            shutil.copyfile(last, os.path.join(notation, f"n{i:04d}.png"))
        count = len([f for f in os.listdir(notation) if f.endswith(".png")])
        stage.chalk(scene_parts["board"], notation, count)

    demo_fit = 0.0
    demo_target = None
    if demo:
        # Far enough left that he clears the writing on the board behind him.
        # Measured rather than nudged: the notation image puts its ink between
        # 0.271 and 0.728 of the board's width, and the board is 1.62 m wide
        # centred at x = -0.62, so the text occupies x = -0.991 .. -0.250.
        # He used to stand at -0.66 and cover -0.940 .. -0.380 of it -- very
        # nearly all of it, in all twenty demonstration shots.
        parts["stand"].location = (-1.45, 0.20, 0.0)
        where = Vector((0.62, 0.34, -0.02))
        staged = demos.build(demo, origin=tuple(where),
                             n_frames=n_frames, fps=opt.fps)
        furniture = demos.plinth(where, staged.get("base", 0.25),
                                 width=staged.get("width", 1.15),
                                 caption=staged.get("caption", "")) or []
        demos.demo_light(where)
        focus = staged["focus"]
        # Frame what is actually on stage, rather than the midpoint of two
        # points. REACH is his half-width with an arm extended in a gesture,
        # which is what decides the edge of the frame, not his shoulders.
        REACH = 0.44
        lo, hi = staged_extent(list(staged.get("objects", [])) + list(furniture),
                               n_frames)
        if lo is None:
            lo = where.x - staged.get("width", 1.15) / 2.0
            hi = where.x + staged.get("width", 1.15) / 2.0
        left = min(parts["stand"].location.x - REACH, lo)
        right = hi
        demo_target = ((left + right) / 2.0, 0.0, -0.20)
        demo_fit = (right - left) / 2.0
    elif notation:
        # He stands to the right of his own board and turns to it, the way
        # anybody writing on one does.
        parts["stand"].location = (0.52, 0.16, 0.0)
        focus = Vector((-0.62, 1.20, 0.26))

    # Aim between him and the thing he is presenting, not at either.
    # z well below his eyeline: he is a whole figure now rather than a bust,
    # and aiming at 0.06 put his feet out of frame and half the shot on the
    # wall above his hair.
    if demo_target is not None:
        target = demo_target
    elif focus is None:
        target = (0.0, 0.0, -0.26)
    else:
        target = ((parts["stand"].location.x + focus.x) * 0.5, 0.0, -0.20)
    stage.camera(job.get("shot", "mid"), target=target, fit=demo_fit)

    words = timeline.get("words", [])
    animate_mouth(parts, track, opt.fps)
    animate_blinks(parts, n_frames, opt.fps, words=words)
    animate_head(parts, n_frames, opt.fps, words=words, look_at=focus)
    animate_body(parts, n_frames, opt.fps, words=words, focus=focus,
                 beat=job.get("beat", ""))
    ease_interpolation()

    frames_dir = job.get("frames_dir") or os.path.join(
        os.path.dirname(job["out"]) or ".", "_frames")
    if os.path.isdir(frames_dir):
        shutil.rmtree(frames_dir, ignore_errors=True)
    os.makedirs(frames_dir, exist_ok=True)
    scene = bpy.context.scene
    scene.render.filepath = os.path.join(frames_dir, "f")
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)
    drawn = time.time() - began

    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-framerate", str(opt.fps), "-i", os.path.join(frames_dir, "f%04d.png"),
        "-i", job["audio"],
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        # No -shortest: the speech track is shorter than the shot by exactly
        # the settle beat, and -shortest threw every rendered tail frame away.
        # The picture is the master; the audio is padded to meet it.
        "-af", "apad", "-movflags", "+faststart",
        "-t", f"{n_frames / opt.fps:.4f}", job["out"]], check=True)
    shutil.rmtree(frames_dir, ignore_errors=True)

    return dict(out=job["out"], frames=n_frames, fps=opt.fps,
                seconds=round(timeline["duration"], 3), engine=opt.engine,
                render_seconds=round(drawn, 1),
                per_frame=round(drawn / max(1, n_frames), 3),
                bytes=os.path.getsize(job["out"]))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    # One Blender for many shots. Launching it per shot registered the bundle
    # with the window server every time -- it checks in as a Foreground app
    # even under --background -- so the Dock flashed once every couple of
    # minutes for the length of the render. It also paid the scene build cost
    # eighty-two times.
    ap.add_argument("--jobs", default="",
                    help="JSON file: a list of shots to render in this process")
    ap.add_argument("--timeline", default="")
    ap.add_argument("--audio", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--shot", default="mid")
    ap.add_argument("--look", default="study")
    ap.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    ap.add_argument("--view", default="punchy")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--frames-dir", default="")
    ap.add_argument("--bounces", type=int, default=4)
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--fast-gi", action="store_true")
    ap.add_argument("--tail", type=float, default=0.0)
    ap.add_argument("--demo", default="")
    ap.add_argument("--notation", default="")
    a = ap.parse_args(argv)

    if a.jobs:
        with open(a.jobs) as fh:
            jobs = json.load(fh)
        for i, job in enumerate(jobs):
            res = render_one(job, a)
            print("SHOT " + json.dumps(dict(res, index=i, of=len(jobs))),
                  flush=True)
        return

    job = dict(timeline=a.timeline, audio=a.audio, out=a.out, shot=a.shot,
               look=a.look, demo=a.demo, notation=a.notation, tail=a.tail,
               frames_dir=a.frames_dir)
    print(json.dumps(render_one(job, a)))


if __name__ == "__main__":
    main()
