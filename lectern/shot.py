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
from lectern.stage import scenes  # noqa: E402
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


def board_lines(board, frames_dir, min_gap=14):
    """Where each line of chalk actually sits, in world space.

    Read off the rendered notation rather than predicted from the layout.
    Manim decides where the heading and each line land, the board is a plane
    with the result mapped across it, and anything that recomputed those
    positions here would be a second layout engine to keep in step with the
    first.

    Returns a list of (x, z) world points, topmost first: the heading, then
    each line.
    """
    import numpy as np

    have = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    if not have:
        return []
    img = bpy.data.images.load(os.path.join(frames_dir, have[-1]))
    try:
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        alpha = px.reshape(h, w, 4)[:, :, 3]
    finally:
        bpy.data.images.remove(img)

    # Blender samples images bottom-up, so row 0 of this array is the bottom
    # of the board. Keep it that way and convert at the end.
    ink = alpha > 0.15
    rows = ink.any(axis=1)
    bands = []
    start = None
    for i, on in enumerate(rows):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= 2:
                bands.append((start, i))
            start = None
    if start is not None:
        bands.append((start, len(rows)))

    merged = []
    for b in bands:
        if merged and b[0] - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], b[1])
        else:
            merged.append(list(b) if False else (b[0], b[1]))

    corners = [board.matrix_world @ Vector(c) for c in board.bound_box]
    x0 = min(c.x for c in corners); x1 = max(c.x for c in corners)
    z0 = min(c.z for c in corners); z1 = max(c.z for c in corners)

    out = []
    for lo, hi in merged:
        band = ink[lo:hi]
        cols = np.where(band.any(axis=0))[0]
        if not len(cols):
            continue
        u = (cols.min() + cols.max()) / 2.0 / w
        v = (lo + hi) / 2.0 / h
        out.append((x0 + u * (x1 - x0), z0 + v * (z1 - z0)))
    out.sort(key=lambda p: -p[1])          # topmost first
    return out


STEP_LENGTH = 0.30          # metres of ground covered per step
TURN = 0.95                 # radians he turns toward his line of travel


def walk(parts, t0, t1, x0, x1, fps, n_frames, seed=5):
    """Move him from x0 to x1 on his own legs, without the feet sliding.

    The root follows the feet, not the other way round. Swinging pendulum
    legs under a root that translates on its own schedule cannot hold a foot
    still: the two only agree instantaneously, and measured over a 0.62 m
    walk the planted foot dragged 600 mm of it. So each frame plants the
    stance foot, evaluates where the rig actually puts it, and slides the
    root by whatever is left over. That makes a still foot an invariant
    rather than something the numbers happen to produce.

    He also turns to face his line of travel. The legs swing about their own
    X, which carries the feet along his Y, so a figure that walks sideways
    without turning is moonwalking -- and a partial turn cannot be made
    slip-free at all, because then his stride axis and his travel are
    different directions.
    """
    stand = parts["stand"]
    legs = parts["legs"]
    arms = parts["arms"]
    dist = abs(x1 - x0)
    dur = max(1e-3, t1 - t0)
    if dist < 1e-3:
        return
    steps = max(1, int(round(dist / STEP_LENGTH)))
    stride = dist / steps
    # One sine cycle is two footfalls, one per leg, so the cycle rate is
    # half the step rate. Counting them as the same thing walked him twice
    # as far as asked -- 1.43 m for a 0.62 m journey -- with the feet
    # planted perfectly the whole way, because the root was faithfully
    # following a gait that was simply doing too much.
    freq = (steps / 2.0) / dur
    f0, f1 = int(t0 * fps) + 1, int(t1 * fps) + 1

    hip_z = legs["L"]["hip"].matrix_world.translation.z
    shoe0 = legs["L"]["shoe"]
    sole = min((shoe0.matrix_world @ v.co).z for v in shoe0.data.vertices)
    leg_len = max(0.05, hip_z - sole)
    theta = math.asin(min(0.85, stride / (2.0 * leg_len)))

    face = math.copysign(math.pi / 2.0, x1 - x0)

    # Turn in place, stride, turn back. Turning while striding rotates the
    # planted foot about the root, and the correction then translates to
    # compensate, which quietly adds distance -- measured at 0.77 m for a
    # 0.62 m journey. Separated, the two never interact.
    turn_t = min(0.42, dur * 0.18)
    s0, s1 = t0 + turn_t, t1 - turn_t
    stride_dur = max(1e-3, s1 - s0)
    freq = (steps / 2.0) / stride_dur

    def foot_x(side):
        shoe = legs[side]["shoe"]
        pts = [shoe.matrix_world @ v.co for v in shoe.data.vertices]
        return sum(p.x for p in pts) / len(pts)

    def set_legs(ph, moving, th):
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            a = -th * math.sin(ph) * sgn if moving else 0.0
            legs[side]["hip"].rotation_euler = (a, 0.0, 0.0)
            legs[side]["knee"].rotation_euler = (max(0.0, -1.4 * a), 0.0, 0.0)
            sh0 = (0.06, -(1.0 if side == "L" else -1.0) * 0.20, 0.0)
            arms[side]["shoulder"].rotation_euler = (sh0[0] - 0.68 * a,
                                                     sh0[1], sh0[2])

    # One dry pass to see how far this gait actually carries him, then the
    # real one with the swing scaled to land on the mark. The arithmetic
    # says a stance run advances him 2*L*sin(theta) and two of them make a
    # cycle, but the hand-over between them absorbs a little more, and the
    # measured overshoot was 0.14 m in 0.62. Measuring it costs one extra
    # pass of a loop that is already cheap; predicting it costs a snap at
    # the end of every walk, which is the one thing the eye always catches.
    def sweep(th, commit):
        x = x0
        planted_side = planted_x = None
        for frame in range(max(1, f0), min(n_frames, f1) + 1):
            t = (frame - 1) / fps
            if t < s0:
                turn, ph, moving = (t - t0) / max(1e-3, turn_t), 0.0, False
            elif t > s1:
                turn, ph, moving = (t1 - t) / max(1e-3, turn_t), 0.0, False
            else:
                turn, moving = 1.0, True
                ph = 2.0 * math.pi * freq * (t - s0)
            turn = min(1.0, max(0.0, turn))
            turn = turn * turn * (3.0 - 2.0 * turn)
            set_legs(ph, moving, th)
            stand.rotation_euler = (0.0, 0.0, face * turn)
            stand.location = (x, stand.location.y, 0.0)
            bpy.context.view_layer.update()
            if moving:
                stance = "L" if math.cos(ph) < 0.0 else "R"
                if stance != planted_side:
                    planted_side, planted_x = stance, foot_x(stance)
                else:
                    x += planted_x - foot_x(stance)
                    stand.location = (x, stand.location.y, 0.0)
                    bpy.context.view_layer.update()
            else:
                planted_side = None
            if commit:
                body = parts["body_root"]
                body.location = (body.location.x, body.location.y,
                                 0.016 * abs(math.sin(ph)) if moving else 0.0)
                stand.keyframe_insert("location", frame=frame)
                stand.keyframe_insert("rotation_euler", frame=frame)
                body.keyframe_insert("location", frame=frame)
                for side in ("L", "R"):
                    legs[side]["hip"].keyframe_insert("rotation_euler",
                                                      frame=frame)
                    legs[side]["knee"].keyframe_insert("rotation_euler",
                                                       frame=frame)
                    arms[side]["shoulder"].keyframe_insert("rotation_euler",
                                                           frame=frame)
        return x

    reached = sweep(theta, False)
    got = abs(reached - x0)
    if got > 1e-4:
        theta = math.asin(min(0.85, math.sin(theta) * dist / got))
    x = sweep(theta, True)

    # The gait decides how far he got; land him where he was asked to be.
    stand.location = (x1, stand.location.y, 0.0)
    stand.rotation_euler = (0.0, 0.0, 0.0)
    stand.keyframe_insert("location", frame=min(n_frames, f1))
    stand.keyframe_insert("rotation_euler", frame=min(n_frames, f1))
    return dict(steps=steps, stride=stride, theta=theta, freq=freq,
                stride_window=(s0, s1), arrived=x, asked=x1)


def aim_arm_at(arm, target, torso, sgn):
    """Point the whole arm at a world position, elbow nearly straight.

    A point is a line from the shoulder to the thing. Working out the two
    joint angles that produce that line by hand is how you get an arm that
    indicates a spot near the thing; asking for the direction and letting
    `to_track_quat` solve it is exact, and it stays exact when the figure
    moves or the board's writing lands somewhere else.
    """
    shoulder = arm["shoulder"]
    world = shoulder.matrix_world.translation
    direction = (Vector(target) - world).normalized()
    parent = shoulder.parent
    if parent is not None:
        direction = parent.matrix_world.to_3x3().inverted() @ direction
    rot = direction.to_track_quat("-Z", "Y").to_euler()
    el = (0.04, 0.0, 0.0)
    return clear_of_torso(arm, torso, (rot.x, rot.y, rot.z), el, sgn)


def pierce_depth(obj, torso) -> float:
    """How far the deepest vertex of `obj` sits inside `torso`, in metres."""
    inv = torso.matrix_world.inverted()
    worst = 0.0
    for v in obj.data.vertices:
        local = inv @ (obj.matrix_world @ v.co)
        ok, loc, nor, _ = torso.closest_point_on_mesh(local)
        if not ok:
            continue
        d = local - loc
        if d.dot(nor) < 0.0:               # on the inside of the surface
            worst = max(worst, d.length)
    return worst


def clear_of_torso(arm, torso, sh, el, sgn, step=0.06, tries=12):
    """Swing the arm out until the hand and forearm are outside the body.

    A clamp, not a tuned constant, for the reason the traffic simulation in
    the highway renderer has one: a set of angles that happens to clear today
    is not an invariant, and this particular failure is silent. The hand
    renders inside the cardigan, every frame encodes, every check passes,
    and it is only ever caught by somebody watching the film.

    Measured before it was fixed: `present`, which is the opening gesture of
    every shot, put the hand 37 mm and the forearm 61 mm inside the torso.
    `open` was 75 mm and 99 mm.
    """
    for _ in range(tries):
        arm["shoulder"].rotation_euler = sh
        arm["elbow"].rotation_euler = el
        bpy.context.view_layer.update()
        deep = max(pierce_depth(arm["hand"], torso),
                   pierce_depth(arm["fore"], torso))
        if deep <= 0.002:
            return sh, el
        sh = (sh[0], sh[1] - sgn * step, sh[2])
    return sh, el


def animate_body(parts, n_frames, fps, seed=17, words=None, focus=None,
                 beat="", board=None):
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

    torso_mesh = parts["torso"]
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
    # While he is at the board the arms are busy pointing, so no gesture is
    # scheduled inside that window; two performances driving the same two
    # joints would simply overwrite one another's keyframes.
    busy = board["window"] if board else None
    moments, t = [], rng.uniform(0.7, 1.5)
    while t < last_end:
        nxt = next((w for w in spoken if w >= t), None)
        if nxt is None or nxt > last_end:
            break
        if not (busy and busy[0] - 0.8 <= nxt <= busy[1] + 0.8):
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

        # Minus sgn, not plus: this is the direction away from the body.
        if kind == "beat":
            sh = (sh0[0] - 0.30, sh0[1], sh0[2])
            el = (el0[0] + 0.55, 0.0, sgn * 0.10)
        elif kind == "present":
            sh = (sh0[0] - 0.52, sh0[1] - sgn * 0.30, sh0[2] - sgn * 0.16)
            el = (el0[0] + 0.34, 0.0, sgn * 0.26)
        elif kind == "point":
            # Arm further out and the elbow nearly straight: a point reads as
            # a line from the shoulder to the thing, and a bent elbow breaks
            # the line.
            sh = (sh0[0] - 0.74, sh0[1] - sgn * 0.22, sh0[2] - sgn * 0.20)
            el = (el0[0] - 0.14, 0.0, sgn * 0.06)
        elif kind == "open":
            sh = (sh0[0] - 0.38, sh0[1] - sgn * 0.44, sh0[2])
            el = (el0[0] + 0.30, 0.0, sgn * 0.34)
        else:                                       # count: hand up, held
            sh = (sh0[0] - 0.66, sh0[1], sh0[2])
            el = (el0[0] + 0.95, 0.0, sgn * 0.05)
        sh, el = clear_of_torso(a, torso_mesh, sh, el, sgn)

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

    if board:
        perform_at_board(parts, board, fps, n_frames, torso_mesh)


def perform_at_board(parts, board, fps, n_frames, torso):
    """Walk to the board, indicate two of the lines on it, and come back.

    He used to deliver a whole lecture rooted to one spot. A presenter who
    never approaches the thing he is talking about is reading aloud near a
    chalkboard rather than teaching from one.

    Which lines he points at comes from `board_lines`, which reads them off
    the rendered notation. Nothing here knows how Manim lays a board out,
    and nothing here should.
    """
    lines = board["lines"]
    if not lines:
        return
    t0, t1 = board["window"]
    home, near = board["home_x"], board["near_x"]
    arms = parts["arms"]
    # The arm nearer the board does the pointing; the board is to his left
    # in every framing that has one.
    side = "R" if near > lines[0][0] else "L"
    arm = arms[side]
    sgn = arm["sign"]
    rest_sh = tuple(arm["shoulder"].rotation_euler)
    rest_el = (0.22, 0.0, 0.0)

    out_t = (t0, t0 + 1.1)
    back_t = (t1 - 1.1, t1)
    walk(parts, out_t[0], out_t[1], home, near, fps, n_frames)

    span = back_t[0] - out_t[1]
    picks = [lines[0], lines[min(len(lines) - 1, 2)]] if len(lines) > 1 \
        else [lines[0]]
    hold = span / max(1, len(picks))
    for i, (lx, lz) in enumerate(picks):
        a0 = out_t[1] + i * hold
        sh, el = aim_arm_at(arm, (lx, 1.30, lz), torso, sgn)
        for t, pose in ((a0 + 0.02, (rest_sh, rest_el)),
                        (a0 + 0.34, (sh, el)),
                        (a0 + hold - 0.30, (sh, el))):
            f = int(t * fps) + 1
            if 1 <= f <= n_frames:
                arm["shoulder"].rotation_euler = pose[0]
                arm["elbow"].rotation_euler = pose[1]
                arm["shoulder"].keyframe_insert("rotation_euler", frame=f)
                arm["elbow"].keyframe_insert("rotation_euler", frame=f)
    f = int((back_t[0] - 0.15) * fps) + 1
    if 1 <= f <= n_frames:
        arm["shoulder"].rotation_euler = rest_sh
        arm["elbow"].rotation_euler = rest_el
        arm["shoulder"].keyframe_insert("rotation_euler", frame=f)
        arm["elbow"].keyframe_insert("rotation_euler", frame=f)

    walk(parts, back_t[0], back_t[1], near, home, fps, n_frames)



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

    cutaway = job.get("scene", "")
    if cutaway:
        # A scene replaces him. No study, no presenter, no chalkboard: it
        # brings its own room and its own camera, and the narration that
        # would have been delivered to camera becomes voice-over.
        staged = scenes.build(cutaway, n_frames=n_frames, fps=opt.fps)
        cam = staged["camera"]
        stage.camera_at(cam["location"], cam["lens"], cam["target"])
        return _finish(job, opt, n_frames, began, timeline)

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
    board_plan = None
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
        # Long enough to be worth crossing the room for. Under about twelve
        # seconds he would arrive, point once and set off back, which reads
        # as pacing rather than as teaching.
        seconds = n_frames / opt.fps
        if seconds >= 12.0:
            lines = board_lines(scene_parts["board"], notation)
            if lines:
                board_plan = dict(lines=lines, home_x=0.52, near_x=0.22,
                                  window=(seconds * 0.24, seconds * 0.82))

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
                 beat=job.get("beat", ""), board=board_plan)
    ease_interpolation()

    return _finish(job, opt, n_frames, began, timeline)


def _finish(job, opt, n_frames, began, timeline):
    """Render the frames and mux them with the segment's audio.

    Shared by the lecture-room path and the cutaway path: a scene is a
    different picture, not a different kind of file.
    """
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
