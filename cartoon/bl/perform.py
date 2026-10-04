"""The performance: every animated channel of both characters, computed
for the whole film from film.json, then baked for the frames a shot needs.

Computing the whole film every time is deliberate. A spring on an antenna,
a blink schedule, where a head was turning from -- all of them depend on
what came before, and a shot computed from its own first frame would start
every one of them cold and pop at the cut. It is a few seconds of numpy.

Layers, each on its own clock (a figure whose parts all move at one rate
reads as a mechanism):

- speech: visemes from the measured phonemes (lectern's dominance model),
  jaw on a bone, lips on shape keys
- mood: the face each line is played with, eased across beats; the
  listener mirrors some of the speaker
- life: blinks (on pauses), breathing, brows on stressed words, idle drift
- gaze: eyes lead, head follows. Euler is blind: he turns his face toward
  a voice and his eyes rest a little off it, which is both true and the
  saddest, funniest thing he does
- acts: what the document says a body does on a line
- Cinnamon's float: position from blocking with a manner (drift, zip,
  sniff), bob, bank, squash and stretch, antennae on springs, a tongue
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from cartoon import moods
from cartoon.bl import common as C, eyes as E
from cartoon.sets import marks as MK
from lectern.presenter import visemes as VIS

TAU = 2 * math.pi


# ------------------------------------------------------------------ utils

def ease(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def smooth_series(v, fps, tau):
    """Forward-backward exponential smoothing (zero lag)."""
    if tau <= 0:
        return v
    a = 1.0 - math.exp(-1.0 / (tau * fps))
    out = np.array(v, float)
    for i in range(1, len(out)):
        out[i] = out[i - 1] + a * (out[i] - out[i - 1])
    for i in range(len(out) - 2, -1, -1):
        out[i] = out[i + 1] + a * (out[i] - out[i + 1])
    return out


def lag_series(v, fps, tau):
    """One-way smoothing: follows with a lag, like a head after the eyes."""
    a = 1.0 - math.exp(-1.0 / (max(tau, 1e-3) * fps))
    out = np.array(v, float)
    for i in range(1, len(out)):
        out[i] = out[i - 1] + a * (out[i] - out[i - 1])
    return out


def noise1(n, fps, period, seed):
    """Smooth 1D noise in [-1, 1] with a characteristic period (seconds)."""
    rng = np.random.default_rng(seed)
    k = max(2, int(n / (period * fps)) + 3)
    pts = rng.uniform(-1, 1, k)
    x = np.arange(n) / (period * fps)
    i = np.floor(x).astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    return pts[i] * (1 - f) + pts[np.minimum(i + 1, k - 1)] * f


def pulse(t, t0, attack, hold, release):
    """0 -> 1 -> 0 envelope over time array t."""
    up = ease((t - t0) / max(attack, 1e-3))
    down = 1 - ease((t - (t0 + attack + hold)) / max(release, 1e-3))
    return np.minimum(up, down) * (t >= t0)


def quat_local(arm, bone, yaw=0.0, pitch=0.0, roll=0.0):
    """Pose quaternion turning `bone` by yaw (about armature Z), pitch
    (about X, + nods down) and roll (about Y, + tilts to its left), all in
    radians, relative to its rest orientation."""
    R = arm.data.bones[bone].matrix_local.to_3x3().normalized()
    q = (Quaternion((0, 0, 1), yaw) @ Quaternion((1, 0, 0), pitch) @ Quaternion((0, 1, 0), roll)).to_matrix()
    return (R.inverted() @ q @ R).to_quaternion()


def _two_taps(t, beat, words, depth):
    """Two deliberate taps timed to the word that matters, not a steady
    3 Hz patter for the whole line -- which read as a trembling hand."""
    ws = beat["speech"]["words"]
    hit = next((w for w in ws if w["text"].lower().strip(".,!?") in words), None)
    t_hit = hit["start"] if hit else beat["speech"]["start"] + 0.5 * beat["speech"]["duration"]
    out = np.zeros_like(t)
    for k in (0, 1):
        tc = t_hit + 0.32 * k
        out = np.maximum(out, np.exp(-((t - tc) / 0.06) ** 2))
    return depth * out


class Baker:
    """Collect per-frame values, then write them as linear keyframes."""

    def __init__(self, f0, f1):
        self.f0, self.f1 = f0, f1
        self.curves = []

    def add(self, idblock, path, values, index=-1, anim_owner=None):
        self.curves.append((idblock, path, index, np.asarray(values, float)))

    def bake(self):
        frames = np.arange(self.f0, self.f1 + 1, dtype=float)
        n = len(frames)
        for idb, path, index, vals in self.curves:
            v = vals[self.f0:self.f1 + 1]
            if len(v) < n:
                v = np.concatenate([v, np.full(n - len(v), v[-1] if len(v) else 0.0)])
            if idb.animation_data is None:
                idb.animation_data_create()
            if idb.animation_data.action is None:
                idb.animation_data.action = bpy.data.actions.new(idb.name + ".perf")
            act = idb.animation_data.action
            fc = act.fcurve_ensure_for_datablock(idb, path, index=max(index, 0))
            fc.keyframe_points.clear()
            fc.keyframe_points.add(n)
            co = np.empty(2 * n)
            co[0::2] = frames
            co[1::2] = v
            fc.keyframe_points.foreach_set("co", co)
            fc.keyframe_points.foreach_set("interpolation", np.full(n, 1, dtype=np.int32))  # LINEAR
            fc.update()


# ------------------------------------------------------------------ film

class Film:
    def __init__(self, film):
        self.f = film
        self.fps = film["fps"]
        self.n = film["frames"] + 1
        self.t = np.arange(self.n) / self.fps
        self.beats = film["beats"]

    def beat_at(self, t):
        for b in self.beats:
            if b["start"] <= t < b["end"]:
                return b
        return self.beats[-1]

    def beat_index_series(self):
        idx = np.zeros(self.n, int)
        for b in self.beats:
            f0, f1 = int(round(b["start"] * self.fps)), int(round(b["end"] * self.fps))
            idx[f0:f1 + 1] = b["index"]
        return idx

    def lines_of(self, who):
        return [b for b in self.beats if b["who"] == who]

    def speech_timeline(self, who):
        words = []
        for b in self.lines_of(who):
            words.extend(b["speech"]["words"])
        return dict(duration=self.t[-1] + 1.0, words=words)


# ---------------------------------------------------------------- mouths

def mouth_channels(film, who, jaw_scale=34.0, jaw_max=22.0):
    tl = film.speech_timeline(who)
    if not tl["words"]:
        z = np.zeros(film.n)
        return dict(jaw=z, keys={}), z
    w = VIS.weights(tl, fps=film.fps, jaw=1.0)
    n = min(film.n, len(w))
    get = lambda k: np.array([fr["weights"]["viseme_" + k] for fr in w[:n]] + [0.0] * (film.n - n))
    jaw_open = np.array([fr["jawOpen"] for fr in w[:n]] + [0.0] * (film.n - n))
    V = {k: get(k) for k in VIS.META}
    speaking = np.clip(1.0 - V["sil"] * 0 - (jaw_open < 0.005) * 0.0, 0, 1)
    active = np.clip(sum(V[k] for k in VIS.META if k not in ("sil",)) * 1.2, 0, 1)
    keys = {
        "mouth_wide": np.clip(V["E"] * 0.8 + V["I"] * 0.9 + V["SS"] * 0.35 + V["DD"] * 0.2, 0, 1),
        "mouth_narrow": np.clip(V["O"] * 0.7 + V["U"] * 1.0 + V["CH"] * 0.5 + V["RR"] * 0.45, 0, 1),
        "upper_up": np.clip(V["aa"] * 0.3 + V["E"] * 0.45 + V["I"] * 0.3 + V["FF"] * 0.35 + V["SS"] * 0.4
                            + V["TH"] * 0.25 + V["CH"] * 0.3, 0, 1),
        "lower_down": np.clip(V["aa"] * 0.45 + V["E"] * 0.3 + V["SS"] * 0.25 + V["CH"] * 0.35 + V["O"] * 0.2, 0, 1),
        "lower_in": np.clip(V["FF"] * 1.0 + V["TH"] * 0.3, 0, 1),
        "lips_press": np.clip(V["PP"], 0, 1),
    }
    closed = np.clip(1.0 - 4.0 * jaw_open - 1.2 * active * (1 - V["PP"]), 0.0, 1.0)
    keys["lips_close"] = np.maximum(closed, V["PP"])
    jaw = np.clip(jaw_open * jaw_scale, 0, jaw_max) * (1 - V["PP"])
    return dict(jaw=jaw, keys=keys), active


def mood_channels(film, who, other, empathy=0.45, tau=0.28):
    """Smile, brows, lids, squint, lean, energy per frame for `who`."""
    n = film.n
    ch = {k: np.zeros(n) for k in ("smile", "brows", "lids", "squint", "energy", "lean")}
    cur = moods.mood("neutral")
    for b in film.beats:
        f0, f1 = int(round(b["start"] * film.fps)), int(round(b["end"] * film.fps)) + 1
        if b["who"] == who:
            cur = moods.mood(b["mood"])
            m = cur
        elif b["who"] == other:
            sp = moods.mood(b["mood"])
            m = {k: cur[k] * (1 - empathy) + sp[k] * empathy for k in cur}
            m["lids"] = cur["lids"]
            m["energy"] = cur["energy"] * 0.5
        else:
            m = cur
        for k in ch:
            ch[k][f0:f1] = m[k]
    for k in ch:
        ch[k] = smooth_series(ch[k], film.fps, tau)
    return ch


# -------------------------------------------------------------- positions

def cinnamon_path(film):
    """Position (n,3) and facing mode per frame from the blocking keys."""
    K = film.f["blocking"]
    n, fps, t = film.n, film.fps, film.t
    pos = np.zeros((n, 3))
    face = np.empty(n, dtype=object)
    manner = np.empty(n, dtype=object)
    if not K:
        pos[:] = MK.CINNAMON["outside"]
        face[:] = "euler"
        return pos, face, manner
    keys = sorted(K, key=lambda k: k["t"])
    p_prev = np.array(keys[0]["pos"])
    pos[:] = p_prev
    face[:] = keys[0]["face"]
    manner[:] = "hold"
    for i, k in enumerate(keys):
        p1 = np.array(k["pos"])
        t1 = k["t"]
        dur = k.get("dur") or 0.0
        t0 = t1 - dur
        f0 = max(0, int(t0 * fps))
        f1 = min(n - 1, int(t1 * fps))
        if dur > 0 and f1 > f0:
            s = (t[f0:f1 + 1] - t0) / dur
            how = k["how"]
            if how == "zip":
                # anticipation back, fast middle, overshoot and settle
                e = np.where(s < 0.18, -0.08 * np.sin(np.pi * s / 0.18),
                             1.0 + 0.1 * np.sin(np.pi * np.clip((s - 0.18) / 0.82, 0, 1)) *
                             np.exp(-3 * np.clip((s - 0.18) / 0.82, 0, 1)) - (1 - ease((s - 0.18) / 0.72)))
                e = np.clip(e, -0.1, 1.12)
            else:
                e = ease(s)
            seg = p_prev[None, :] + (p1 - p_prev)[None, :] * e[:, None]
            if how == "sniff":
                d = p1 - p_prev
                side = np.array([-d[1], d[0], 0.0])
                side /= np.linalg.norm(side) + 1e-9
                seg += side[None, :] * (0.12 * np.sin(TAU * s * 2.2) * np.sin(np.pi * s))[:, None]
                seg[:, 2] += 0.05 * np.sin(TAU * s * 4.4) * np.sin(np.pi * s)
            pos[f0:f1 + 1] = seg
            manner[f0:f1 + 1] = how
        pos[f1:] = p1
        face[f0 if dur > 0 else f1:] = k["face"]
        p_prev = p1
    return pos, face, manner


# ------------------------------------------------------------------ gaze

def angles_to(src, dst, char_yaw_deg):
    """Yaw/pitch (radians) from src to dst, in a character's own frame
    (yaw + toward its left, pitch + up), given the character's yaw."""
    d = np.asarray(dst) - np.asarray(src)
    a = math.radians(-char_yaw_deg)
    c, s = math.cos(a), math.sin(a)
    dx = d[..., 0] * c - d[..., 1] * s
    dy = d[..., 0] * s + d[..., 1] * c
    yaw = np.arctan2(dx, -dy)
    pitch = np.arctan2(d[..., 2], np.hypot(dx, dy))
    return yaw, pitch


class Performer:
    def __init__(self, film_json, rigs: dict, f0: int, f1: int):
        self.film = Film(film_json)
        self.rigs = rigs
        self.f0, self.f1 = f0, f1
        self.bk = Baker(f0, f1)
        self.cpos, self.cface, self.cmanner = cinnamon_path(self.film)
        self.cyaw = np.zeros(self.film.n)

    # ------------------------------------------------------------ common
    def _face(self, who, arm, mouth, mood, extra=None):
        film = self.film
        head = bpy.data.objects[arm["head_mesh"]]
        kb = head.data.shape_keys
        keys = {k: np.array(v) for k, v in mouth["keys"].items()}
        smile = mood["smile"] + float(arm.get("smile_base", 0.0))
        if "lips_close" in keys:
            pp = keys.get("lips_press", 0)
            keys["lips_close"] = np.maximum(np.minimum(keys["lips_close"], float(arm.get("lips_rest", 1.0))), pp)
        if "lower_down" in keys:
            keys["lower_down"] = np.clip(keys["lower_down"] * float(arm.get("lower_down_gain", 1.0)), 0, 1.2)
        keys["smile"] = keys.get("smile", 0) + np.clip(smile, 0, 1) * 0.85
        keys["frown"] = keys.get("frown", 0) + np.clip(-smile, 0, 1) * 0.85
        tl = film.speech_timeline(who)
        br = VIS.brows(tl, fps=film.fps, seed=3 if who == "euler" else 7) if tl["words"] else None
        b_up = np.clip(mood["brows"], 0, 1) * 0.9
        b_dn = np.clip(-mood["brows"], 0, 1) * 0.9
        if br is not None:
            m = min(film.n, len(br["browInnerUp"]))
            emph = np.zeros(film.n)
            emph[:m] = br["browInnerUp"][:m]
            b_up = np.clip(b_up + emph * 0.9, 0, 1.2)
        for s in ("L", "R"):
            keys[f"brow_up.{s}"] = b_up
            keys[f"brow_down.{s}"] = b_dn
            keys[f"cheek_up.{s}"] = np.clip(mood["squint"] + np.clip(smile, 0, 1) * 0.3, 0, 1)
        keys["brow_inner"] = np.clip(-mood["smile"] * 0.4 + np.clip(mood["brows"], 0, 1) * 0.3 * (mood["smile"] < 0.3), 0, 1)
        if extra:
            for k, v in extra.items():
                keys[k] = keys.get(k, 0) + v
        for name, v in keys.items():
            if name in kb.key_blocks:
                self.bk.add(kb, f'key_blocks["{name}"].value', np.clip(np.broadcast_to(v, (film.n,)), -0.2, 1.3))
        self.bk.add(arm, 'pose.bones["jaw"].rotation_quaternion', None)  # placeholder, replaced below
        self.bk.curves.pop()
        jaw = np.radians(mouth["jaw"])
        if arm.get("open_by_key") and "mouth_open" in kb.key_blocks:
            opening = np.clip(np.asarray(mouth["jaw"]) / float(arm.get("jaw_max", 12.0)), 0.0, 1.2)
            self.bk.add(kb, 'key_blocks["mouth_open"].value', opening)
            jaw = np.zeros_like(jaw)
        qs = [quat_local(arm, "jaw", 0, j, 0) for j in jaw[self.f0:self.f1 + 1]]
        self._bake_quats(arm, "jaw", qs)

    def _bake_quats(self, arm, bone, qs):
        """qs covers f0..f1 only."""
        pad = [Quaternion()] * self.f0
        allq = pad + list(qs)
        for i, comp in enumerate("wxyz"):
            v = np.array([getattr(q, comp) for q in allq])
            self.bk.add(arm, f'pose.bones["{bone}"].rotation_quaternion', v, index=i)

    def _bake_ypr(self, arm, bone, yaw, pitch, roll):
        rng = range(self.f0, self.f1 + 1)
        qs = [quat_local(arm, bone, yaw[f], pitch[f], roll[f]) for f in rng]
        self._bake_quats(arm, bone, qs)

    def _eyes(self, arm, look_yaw, look_pitch, up_open, lo_open):
        eyes = arm["eyes"]
        for s, e in eyes.items():
            ball = bpy.data.objects[e["ball"]]
            lu = bpy.data.objects[e["lid_up"]]
            ll = bpy.data.objects[e["lid_lo"]]
            ru, rl = arm["lids_rest"][s]
            u = up_open * (ru / 0.72 if arm["character"] == "euler" else 1.0)
            u = np.clip(u, 0, 1.15)
            lo = np.clip(lo_open * rl, 0, 1)
            up_ang = -np.radians(-8 + 58 * u) - 0.6 * look_pitch
            lo_ang = np.radians(3 + 17 * lo) - 0.3 * look_pitch
            self.bk.add(lu, "rotation_euler", up_ang, index=0)
            self.bk.add(ll, "rotation_euler", lo_ang, index=0)
            self.bk.add(ball, "rotation_euler", -look_pitch, index=0)
            self.bk.add(ball, "rotation_euler", look_yaw, index=2)

    # ------------------------------------------------------------ Euler
    def euler(self):
        arm = self.rigs.get("euler")
        if arm is None:
            return
        film = self.film
        n, fps, t = film.n, film.fps, film.t
        mouth, talking = mouth_channels(film, "euler", jaw_scale=24, jaw_max=13)
        mood = mood_channels(film, "euler", "cinnamon")
        bidx = film.beat_index_series()
        beats = film.beats

        # --- where he looks: toward the voice, a little off (he is blind)
        head_w = np.array(MK.HEAD_EULER)
        cin_head = self.cpos + np.array([0, 0, 0.12])
        target = cin_head.copy()
        writing = np.zeros(n)
        write_pt = np.zeros((n, 3))
        for e in film.f["board"]:
            if e["kind"] != "write":
                continue
            f0, f1 = int(e["t0"] * fps), int(e["t1"] * fps)
            u0, u1, v, h = MK.BOARD_LAYOUT[e["board"]]
            if e["board"] == "identity":
                u0 = MK.BOARD_LAYOUT["exp"][1]
            for f in range(max(0, f0 - int(0.6 * fps)), min(n, f1 + int(0.5 * fps))):
                s = np.clip((f - f0) / max(1, f1 - f0), 0, 1)
                u = u0 + (u1 - u0) * s
                # the chalk bobs up and down along the line: writing
                wob = 0.08 * h * math.sin(TAU * (f / fps) * 3.1) * (0 < s < 1)
                write_pt[f] = MK.board_point(u, v + wob / MK.SLATE_H * 0.0 + wob, lift=0.0)
                writing[f] = max(writing[f], pulse(np.array([f / fps]), e["t0"] - 0.6, 0.55, e["t1"] - e["t0"] + 0.05, 0.5)[0])
        # before Cinnamon comes in, and while writing, he faces the slate
        outside = self.cpos[:, 1] > MK.ROOM_D / 2 - 0.1
        board_look = np.array(MK.board_point(0.7, 0.55))
        target[outside] = board_look
        target = target * (1 - writing[:, None]) + write_pt * writing[:, None]
        # listening for a sound at the window
        for b in beats:
            if b["who"] == "euler" and b["act"] == "listen":
                # he takes the noise for his assistant at the door
                f0, f1 = int(b["start"] * fps), int(b["end"] * fps)
                target[f0:f1] = np.array([-2.9, -1.8, 1.5])
            if b["scene"] == "study" and b["time"] == "morning":
                f0, f1 = int(b["start"] * fps), int(b["end"] * fps)
                target[f0:f1] = np.array([-2.9, -1.8, 1.4]) if b["who"] != "euler" else np.array([-1.5, -1.0, 1.3])
        yaw, pitch = angles_to(head_w, target, MK.EULER_YAW)
        blind = 1.0 - writing * 0.6
        yaw = yaw + np.radians(11) * blind + np.radians(4) * noise1(n, fps, 3.5, 11) * blind
        pitch = pitch + np.radians(5) * blind + np.radians(2.5) * noise1(n, fps, 4.0, 12)
        g_yaw = lag_series(yaw, fps, 0.12)
        g_pitch = lag_series(pitch, fps, 0.12)
        # a real neck turns about 70 degrees; a cartoon head that turns more
        # than about 40 shows the audience the back of its skull
        h_yaw = lag_series(np.clip(g_yaw * 0.8, -0.7, 0.7), fps, 0.28)
        h_pitch = lag_series(np.clip(g_pitch * 0.7, -0.5, 0.5), fps, 0.3)
        e_yaw = np.clip(g_yaw - h_yaw, -0.45, 0.45) * 0.7
        e_pitch = np.clip(g_pitch - h_pitch, -0.3, 0.3) * 0.7
        # nods on stressed words while he talks
        nod = np.zeros(n)
        for b in film.lines_of("euler"):
            for w in b["speech"]["words"]:
                if "ˈ" in w.get("phonemes", "") and w["end"] - w["start"] > 0.22:
                    nod += pulse(t, w["start"] - 0.08, 0.1, 0.05, 0.3) * 0.06 * (0.6 + 0.8 * mood["energy"])
        # turn_to_voice: the double take -- a snap round toward the voice,
        # brows up, a little lean in, then settling
        take = np.zeros(n)
        for b in beats:
            if b["who"] == "euler" and b["act"] == "turn_to_voice":
                take = np.maximum(take, pulse(t, b["start"] - 0.1, 0.18, 0.5, 0.9))
        nod -= take * 0.08
        mood["brows"] = mood["brows"] + take * 0.8
        mood["lean"] = mood["lean"] + take * 0.5
        roll = np.radians(3) * noise1(n, fps, 5.0, 13) + np.radians(2) * mood["brows"]
        for b in beats:
            if b["who"] == "euler" and b["act"] == "listen":
                roll += pulse(t, b["start"], 0.5, b["end"] - b["start"] - 1.0, 0.5) * np.radians(10)
            if b["who"] == "euler" and b["act"] == "laugh":
                # head back, a slow rock: a big man's laugh, not a vibration
                shake = pulse(t, b["start"], 0.2, 1.2, 0.8)
                nod -= shake * (0.1 + 0.035 * np.sin(TAU * 2.2 * t))
        breath = np.sin(TAU * t / 4.3)
        lean = mood["lean"] * 0.1
        for b in beats:
            if b["who"] == "euler" and b["act"] == "lean_in":
                lean += pulse(t, b["start"], 0.5, b["end"] - b["start"] - 0.8, 0.6) * 0.14
            if b["who"] == "euler" and b["act"] == "laugh":
                w = pulse(t, b["start"], 0.25, 1.4, 0.9)
                lean -= w * (0.06 + 0.03 * np.sin(TAU * 2.2 * t))
        spine_yaw = writing * np.radians(-22)
        spine_pitch = lean + writing * 0.26 + 0.012 * breath
        spine_roll = writing * np.radians(-12)
        self._bake_ypr(arm, "spine", spine_yaw * 0.5, spine_pitch * 0.6, spine_roll * 0.5)
        self._bake_ypr(arm, "chest", spine_yaw * 0.5, spine_pitch * 0.4 + 0.01 * breath, spine_roll * 0.5)
        hy = h_yaw - spine_yaw
        hp = -(h_pitch) + nod - spine_pitch * 0.7
        self._bake_ypr(arm, "neck", hy * 0.35, hp * 0.35, roll * 0.3)
        self._bake_ypr(arm, "head", hy * 0.65, hp * 0.65, roll * 0.7)

        # --- blinks, lids
        bl = np.array(VIS.blinks(t[-1] + 1, fps, 15.0, seed=5, timeline=film.speech_timeline("euler"))[:n])
        up_open = np.clip(mood["lids"] / 0.8, 0, 1.3) * (1 - bl)
        lo_open = np.clip(1.0 - mood["squint"] * 0.6, 0.3, 1.0) * (1 - bl * 0.6)
        self._eyes(arm, e_yaw, e_pitch, up_open, lo_open)
        self._face("euler", arm, mouth, mood)

        # --- hands: right writes and gestures, left rests and beats
        self._writing = writing
        self._write_pt = write_pt
        self._euler_arm = arm
        self._euler_hands(arm, writing, write_pt, mood, talking)

    def _to_arm_local(self, p, loc, yaw_deg):
        a = math.radians(-yaw_deg)
        d = np.asarray(p) - np.asarray(loc)
        c, s = math.cos(a), math.sin(a)
        return np.stack([d[..., 0] * c - d[..., 1] * s, d[..., 0] * s + d[..., 1] * c, d[..., 2]], -1)

    def _euler_hands(self, arm, writing, write_pt, mood, talking):
        film = self.film
        n, fps, t = film.n, film.fps, film.t
        for side in (".L", ".R"):
            tg = bpy.data.objects[f"{arm['character']}.ik.hand{side}"]
            rest = np.array(tg["rest_location"])
            rq = Quaternion(tg["rest_rotation"])
            P = np.tile(rest, (n, 1))
            rot_off = np.zeros((n, 3))    # extra rotation (x, y, z) radians in armature axes
            if side == ".R":
                wl = self._to_arm_local(write_pt, MK.EULER, MK.EULER_YAW)
                # the hand sits a few centimetres off the board: the chalk
                # tip is what touches
                wl = wl + np.array([0.035, 0.03, -0.02])
                P = P * (1 - writing[:, None]) + wl * writing[:, None]
                rot_off[:, 0] += writing * np.radians(-55)
                rot_off[:, 2] += writing * np.radians(40)
            # acts
            for b in film.beats:
                if b["who"] != "euler" or not b["act"]:
                    continue
                t0, t1 = b["start"], b["end"]
                a = b["act"]
                if side == ".R" and a == "tap_temple":
                    temple = np.array(MK.euler_point((-0.09, -0.06, 1.2)))
                    tl = self._to_arm_local(temple, MK.EULER, MK.EULER_YAW) + np.array([-0.02, -0.03, -0.03])
                    w = pulse(t, t0 + 0.4, 0.75, t1 - t0 - 2.0, 0.85)
                    tap = _two_taps(t, b, ("head", "mind", "think"), 0.012) * w
                    P = P * (1 - w[:, None]) + (tl + np.array([0, 0, tap.mean() * 0]))[None, :] * w[:, None]
                    P[:, 0] -= tap
                    rot_off[:, 0] += w * np.radians(-80)
                elif side == ".R" and a == "realise":
                    up = rest + np.array([0.05, -0.12, 0.32])
                    w = pulse(t, t0 + 0.3, 0.35, t1 - t0 - 1.0, 0.5)
                    P = P * (1 - w[:, None]) + up[None, :] * w[:, None]
                    rot_off[:, 0] += w * np.radians(-75)
                elif side == ".R" and a == "turn_hand":
                    up = rest + np.array([0.02, -0.14, 0.22])
                    w = pulse(t, t0 + 0.2, 0.4, t1 - t0 - 0.9, 0.5)
                    P = P * (1 - w[:, None]) + up[None, :] * w[:, None]
                    turn = ease((t - t0 - 0.9) / 1.0) * w
                    rot_off[:, 1] += turn * np.radians(-90) + w * np.radians(-40)
                elif side == ".R" and a == "tap_board":
                    bp = self._to_arm_local(np.array(MK.board_point(0.75, 0.43)), MK.EULER, MK.EULER_YAW)
                    w = pulse(t, t0 + 0.2, 0.5, t1 - t0 - 1.1, 0.5)
                    tap = _two_taps(t, b, ("year", "seventeen", "thirty"), 0.016) * w
                    P = P * (1 - w[:, None]) + (bp + np.array([0.04, 0.04, 0.0]))[None, :] * w[:, None]
                    P[:, 0] += tap
                    rot_off[:, 0] += w * np.radians(-50)
                elif a == "laugh":
                    # the laugh is in his chest (see euler()); the hands only
                    # settle onto his belly, they do not bounce -- a 4.5 Hz
                    # bounce here read as shaking hands
                    w = pulse(t, t0 + 0.1, 0.4, t1 - t0 - 1.0, 0.6)
                    P = P + np.array([0.04 if side == ".R" else -0.04, 0.05, 0.03])[None, :] * w[:, None]
                elif side == ".L" and a in ("lean_in", "sniff"):
                    w = pulse(t, t0 + 0.2, 0.4, t1 - t0 - 0.9, 0.5)
                    P = P + np.array([-0.03, -0.1, 0.12])[None, :] * w[:, None]
            # beats: the free (left) hand lifts on the words that matter --
            # few, slow and small. Every stressed word, up in four frames and
            # down again, read as a nervous twitch, a shake for no reason.
            if side == ".L":
                beat = np.zeros(n)
                last = -10.0
                for b in film.lines_of("euler"):
                    if b["act"] in ("write", "tap_temple", "laugh"):
                        continue
                    for wd in b["speech"]["words"]:
                        if "ˈ" in wd.get("phonemes", "") and wd["end"] - wd["start"] > 0.3 \
                                and wd["start"] - last > 1.6:
                            beat = np.maximum(beat, pulse(t, wd["start"] - 0.35, 0.4, 0.2, 0.9))
                            last = wd["start"]
                beat = smooth_series(beat * (0.25 + 0.6 * mood["energy"]), fps, 0.08)
                P = P + np.array([-0.015, -0.045, 0.06])[None, :] * beat[:, None]
                rot_off[:, 0] += beat * np.radians(-18)
            # a little life even at rest
            P = P + np.array([0.004, 0.004, 0.006])[None, :] * np.stack(
                [noise1(n, fps, 3.0, 20 + i + (0 if side == ".L" else 5)) for i in range(3)], 1)
            for i in range(3):
                self.bk.add(tg, "location", P[:, i], index=i)
            qs = []
            for f in range(n):
                rx, ry, rz = rot_off[f]
                q = Quaternion((0, 0, 1), rz) @ Quaternion((0, 1, 0), ry) @ Quaternion((1, 0, 0), rx) @ rq
                qs.append(q)
            for i, comp in enumerate("wxyz"):
                self.bk.add(tg, "rotation_quaternion", np.array([getattr(q, comp) for q in qs]), index=i)
        # fingers: curl around the chalk while writing, point for realise
        self._fingers(arm, ".R", {"hold": writing})
        acts = {}
        for b in film.beats:
            if b["who"] == "euler" and b["act"] in ("realise", "tap_temple"):
                acts.setdefault("point", np.zeros(n))
                acts["point"] = np.maximum(acts["point"], pulse(t, b["start"] + 0.3, 0.3, b["end"] - b["start"] - 1.0, 0.4))
        if acts:
            self._fingers(arm, ".R", acts, add=True)
        # chalk visibility
        ch = bpy.data.objects.get("euler.chalk")
        if ch is not None:
            vis = (writing > 0.2).astype(float)
            self.bk.add(ch, "hide_render", 1.0 - vis)
            self.bk.add(ch, "hide_viewport", 1.0 - vis)

    def _fingers(self, arm, side, poses: dict, add=False):
        """Curl each finger by pose weights. Poses: hold (around chalk),
        point (index straight, others curled), fist, open, count_k."""
        film = self.film
        n = film.n
        names = [b.name for b in arm.data.bones if b.name.startswith("f_") and b.name.endswith(side)]
        if not hasattr(self, "_finger_acc"):
            self._finger_acc = {}
        for bn in names:
            finger = bn.split("_")[1]
            seg = int(bn.split("_")[2][0])
            curl = self._finger_acc.get(bn, np.zeros(n))
            for pose, w in poses.items():
                if pose == "hold":
                    c = {"thumb": 0.5, "index": 0.9, "middle": 1.1, "ring": 1.3, "pinky": 1.4}.get(finger, 1.0)
                elif pose == "point":
                    c = {"thumb": 0.6, "index": -0.1, "middle": 1.5, "ring": 1.6, "pinky": 1.6}.get(finger, 1.2)
                elif pose == "fist":
                    c = 1.5
                elif pose == "open":
                    c = -0.2
                elif pose.startswith("count_"):
                    k = int(pose.split("_")[1])
                    order = ["f1", "f2", "f3", "index", "middle", "ring", "pinky", "thumb"]
                    c = -0.1 if (finger in order and order.index(finger) < k) else 1.4
                elif pose == "pinch":
                    c = {"thumb": 0.9, "index": 0.9, "f1": 1.0, "f2": 0.4, "f3": 0.3}.get(finger, 0.3)
                else:
                    c = 0.0
                curl = curl + np.asarray(w) * c * 0.7
            self._finger_acc[bn] = curl
        for bn in names:
            curl = self._finger_acc[bn]
            rng = range(self.f0, self.f1 + 1)
            # curl bends toward the palm: about the bone's local X
            qs = [Quaternion((1, 0, 0), -float(curl[f])) for f in rng]
            # overwrite any earlier bake of this bone
            self.bk.curves = [c for c in self.bk.curves if not (c[0] == arm and c[1] == f'pose.bones["{bn}"].rotation_quaternion')]
            self._bake_quats(arm, bn, qs)

    # ------------------------------------------------------------ Cinnamon
    def cinnamon(self):
        arm = self.rigs.get("cinnamon")
        if arm is None:
            return
        film = self.film
        n, fps, t = film.n, film.fps, film.t
        mouth, talking = mouth_channels(film, "cinnamon", jaw_scale=float(arm.get("jaw_scale", 34)),
                                        jaw_max=float(arm.get("jaw_max", 20)))
        mood = mood_channels(film, "cinnamon", "euler", empathy=0.35, tau=0.22)
        pos = self.cpos.copy()
        # hover: a slow bob and a slower sway, bigger when excited
        bob = 0.022 * np.sin(TAU * t / 1.7) + 0.008 * np.sin(TAU * t / 0.63 + 1.0)
        pos[:, 2] += bob * (0.7 + 0.6 * mood["energy"])
        pos[:, 0] += 0.01 * noise1(n, fps, 2.5, 31)
        pos[:, 1] += 0.01 * noise1(n, fps, 2.7, 32)
        # hops on stressed words
        hop = np.zeros(n)
        for b in film.lines_of("cinnamon"):
            for w in b["speech"]["words"]:
                if "ˈ" in w.get("phonemes", "") and w["end"] - w["start"] > 0.2:
                    hop = np.maximum(hop, pulse(t, w["start"] - 0.1, 0.12, 0.05, 0.3))
        hop *= 0.3 + 0.9 * mood["energy"]
        pos[:, 2] += 0.025 * hop
        # facing
        head_e = np.array(MK.HEAD_EULER)
        tgt = np.tile(head_e, (n, 1))
        for i in range(n):
            f = self.cface[i]
            if f == "board":
                tgt[i] = MK.board_point(0.65, 0.5)
            elif f == "window":
                tgt[i] = (MK.WIN_X, MK.ROOM_D / 2 + 2, 1.6)
            elif f == "slate":
                tgt[i] = MK.board_point(0.6, 0.7)
        d = tgt - pos
        yaw = np.unwrap(np.arctan2(d[:, 0], -d[:, 1]))
        # While it licks, it turns part of the way toward the camera that
        # watches the lick, so its mouth is seen and the tongue leaves it in
        # plain view before curving on to the chalk. Squarely facing the
        # board, the camera had its back, and the tongue seemed to come out
        # from under its belly.
        from cartoon.sets import lick as LK
        cheat = np.zeros(n)
        cam_yaw = np.zeros(n)
        for b in film.beats:
            if b["do"] not in ("lick", "slurp"):
                continue
            cam = LK.slurp_camera() if b["do"] == "slurp" else \
                LK.camera(film.f["setups"]["two"], b.get("target") or "product")
            env = np.clip(np.minimum((t - b["start"]) / 0.5, (b["end"] - t) / 0.5), 0, 1)
            k = env > cheat
            dc = np.array(cam["loc"])[None, :] - pos[k]
            cam_yaw[k] = np.arctan2(dc[:, 0], -dc[:, 1])
            cheat[k] = env[k]
        turn = np.angle(np.exp(1j * (cam_yaw - yaw)))
        yaw = yaw + smooth_series(0.5 * turn * cheat, fps, 0.12)
        # while moving fast, face the way it is going
        vel = np.gradient(pos, axis=0) * fps
        speed = np.linalg.norm(vel[:, :2], axis=1)
        travel = np.unwrap(np.arctan2(vel[:, 0], -vel[:, 1]))
        # only a real dash turns it to face where it is going; on a lazy
        # drift home it keeps facing Euler (not the back of its head to us)
        mix = np.clip((speed - 1.2) / 0.8, 0, 1)
        # bring travel angle into yaw's branch before mixing
        travel = yaw + np.angle(np.exp(1j * (travel - yaw)))
        yaw = yaw * (1 - mix) + travel * mix
        # spins
        for b in film.beats:
            if b["who"] == "cinnamon" and b["act"] == "spin":
                s = ease((t - b["start"] - 0.5) / min(2.0, b["end"] - b["start"] - 0.6))
                yaw = yaw + TAU * s
        yaw = lag_series(yaw, fps, 0.18)
        self.cyaw = yaw
        acc = np.gradient(vel, axis=0) * fps
        # bank into turns, pitch into acceleration
        side_acc = acc[:, 0] * np.cos(yaw) + acc[:, 1] * np.sin(yaw)
        fwd_acc = -acc[:, 0] * np.sin(yaw) + acc[:, 1] * np.cos(yaw)
        roll = np.clip(smooth_series(-side_acc * 0.03, fps, 0.12), -0.22, 0.22)
        pitch = np.clip(smooth_series(fwd_acc * 0.025, fps, 0.14), -0.18, 0.18)
        # look down at what it licks: level, from above the slate, the tongue
        # took the straight way to the chalk -- down through its own body --
        # and showed only where it came out, under the belly or by a hand
        look = np.zeros(n)
        for b in film.beats:
            if b["do"] not in ("lick", "slurp"):
                continue
            if b["do"] == "slurp":
                aim = np.array(MK.board_point(0.55, 0.5))
            else:
                u0, u1, v, h = MK.BOARD_LAYOUT[b.get("target") or "product"]
                aim = np.array(MK.board_point((u0 + u1) / 2, v))
            env = np.clip(np.minimum((t - b["start"]) / 0.4, (b["end"] - t) / 0.4), 0, 1)
            k = env > 0
            d = aim - pos[k]
            down = np.arctan2(-d[:, 2], np.linalg.norm(d[:, :2], axis=1))
            look[k] = np.maximum(look[k], env[k] * np.clip(down * 0.7, 0.0, 0.65))
        pitch = pitch + smooth_series(look, fps, 0.1)
        for i in range(3):
            self.bk.add(arm, "location", pos[:, i], index=i)
        arm.rotation_mode = "XYZ"
        self.bk.add(arm, "rotation_euler", pitch, index=0)
        self.bk.add(arm, "rotation_euler", roll, index=1)
        self.bk.add(arm, "rotation_euler", yaw, index=2)
        # squash and stretch on the root bone, volume kept
        vz = np.gradient(pos[:, 2]) * fps
        stretch = 1.0 + np.clip(lag_series(speed * 0.08 + np.abs(vz) * 0.25, fps, 0.06), 0, 0.25) \
            + 0.012 * np.sin(TAU * t / 3.1) + 0.06 * hop
        land = np.clip(-np.gradient(speed) * fps * 0.03, 0, 0.18)
        sz = stretch - lag_series(land, fps, 0.05)
        sxy = 1.0 / np.sqrt(np.maximum(sz, 0.5))
        self.bk.add(arm, 'pose.bones["root"].scale', sxy, index=0)
        self.bk.add(arm, 'pose.bones["root"].scale', sz, index=1)
        self.bk.add(arm, 'pose.bones["root"].scale', sxy, index=2)

        # head: tilt, nods, looks
        tilt = np.radians(4) * noise1(n, fps, 3.0, 33)
        for b in film.beats:
            if b["who"] == "cinnamon" and b["act"] == "tilt":
                tilt += pulse(t, b["start"], 0.4, b["end"] - b["start"] - 0.8, 0.5) * np.radians(22)
        nod = np.zeros(n)
        for b in film.lines_of("cinnamon"):
            for w in b["speech"]["words"]:
                if "ˈ" in w.get("phonemes", ""):
                    nod += pulse(t, w["start"] - 0.06, 0.08, 0.04, 0.25) * 0.07
        sniff = np.zeros(n)
        taste = np.zeros(n)
        for b in film.beats:
            if b["who"] == "cinnamon" and b["act"] == "sniff":
                sniff = np.maximum(sniff, pulse(t, b["start"], 0.2, b["end"] - b["start"] - 0.4, 0.3))
            if b["do"] in ("lick", "slurp"):
                taste = np.maximum(taste, pulse(t, b["start"] + 0.3, 0.2, b["end"] - b["start"] - 0.5, 0.3))
            if b["who"] == "cinnamon" and b["act"] in ("savour",):
                taste = np.maximum(taste, pulse(t, b["start"], 0.3, b["end"] - b["start"] - 0.5, 0.4) * 0.8)
        sniff_bob = sniff * 0.08 * np.maximum(0, np.sin(TAU * 3.2 * t))
        # gentler than a creature with a neck: the whole bean bends with it
        self._bake_ypr(arm, "head", np.zeros(n), (-(nod + sniff_bob) + 0.1 * mood["lean"]) * 0.7, tilt * 0.7)
        self._bake_ypr(arm, "body", np.zeros(n), -0.05 * mood["lean"] + 0.03 * hop, 0.4 * tilt)

        # eyes: on Euler, on the slate while licking, shut while tasting
        head_pos = pos + np.array([0, 0, 0.13])
        eyaw, epitch = angles_to(head_pos, tgt, 0.0)
        eyaw = np.angle(np.exp(1j * (eyaw - yaw)))
        eyaw = lag_series(np.clip(eyaw, -0.5, 0.5), fps, 0.05)
        epitch = lag_series(np.clip(epitch - pitch, -0.4, 0.4), fps, 0.05)
        bl = np.array(VIS.blinks(t[-1] + 1, fps, 11.0, seed=8, timeline=film.speech_timeline("cinnamon"))[:n])
        shut = np.clip(taste + (mood["lids"] < 0.4) * 0.0, 0, 1)
        up_open = np.clip(mood["lids"] / 0.85, 0, 1.25) * (1 - bl) * (1 - shut * 0.95)
        lo_open = np.clip(1.0 - mood["squint"] * 0.5, 0.3, 1) * (1 - bl * 0.6) * (1 - shut * 0.6)
        self._eyes(arm, eyaw, epitch, up_open, lo_open)
        flare = np.clip(sniff * (0.5 + 0.5 * np.maximum(0, np.sin(TAU * 3.2 * t))) + taste * 0.4
                        + 0.15 * np.maximum(0, np.sin(TAU * t / 2.3)) ** 8, 0, 1)
        # the mouth opens whenever the tongue is out -- licks, the slurp, the
        # fanning -- or the tongue would come out through closed lips
        tongue_out = np.zeros(n)
        for b in film.beats:
            if b["do"] in ("lick", "slurp"):
                tongue_out = np.maximum(tongue_out, pulse(t, b["start"] + 0.3, 0.25, b["end"] - b["start"] - 0.7, 0.3))
            if b["who"] == "cinnamon" and b["act"] == "fan_tongue":
                tongue_out = np.maximum(tongue_out, pulse(t, b["start"] + 0.1, 0.25, b["end"] - b["start"] - 0.5, 0.3))
        self._face("cinnamon", arm, mouth, mood, extra={"nostril_flare": flare,
                                                        "nose_scrunch": sniff * 0.3,
                                                        "mouth_open": tongue_out * 0.75,
                                                        "lips_close": -tongue_out * 1.2})
        self._cinnamon_arms(arm, mood, talking, pos, yaw)
        self._antennae(arm, pos, yaw, mood, sniff, taste)
        self._tongue(arm, pos, yaw)

    def _cinnamon_arms(self, arm, mood, talking, pos, yaw):
        film = self.film
        n, fps, t = film.n, film.fps, film.t
        for side, sx in ((".L", 1), (".R", -1)):
            tg = bpy.data.objects[f"{arm['character']}.ik.hand{side}"]
            rest = np.array(tg["rest_location"])
            rq = Quaternion(tg["rest_rotation"])
            P = np.tile(rest, (n, 1))
            rot = np.zeros((n, 3))
            # floating paddle
            P[:, 2] += 0.012 * np.sin(TAU * t / 1.7 + 0.8 + sx * 0.3)
            P[:, 0] += sx * 0.008 * np.sin(TAU * t / 1.1 + sx)
            poses = {}
            for b in film.beats:
                if b["do"] in ("lick", "slurp"):
                    # hands back at its sides while it licks: in front, the
                    # near one hid its mouth, and the tongue seemed to come
                    # out from behind its hand
                    w = pulse(t, b["start"], 0.3, max(0.1, b["end"] - b["start"] - 0.6), 0.3)
                    P = P + np.array([sx * 0.05, 0.085, -0.03])[None, :] * w[:, None]
                    continue
                if not b["act"] or b["who"] != "cinnamon":
                    continue
                t0, t1, a = b["start"], b["end"], b["act"]
                w = pulse(t, t0 + 0.1, 0.3, max(0.1, t1 - t0 - 0.8), 0.4)
                if a == "shrug":
                    w = pulse(t, t0 + 0.1, 0.25, 0.5, 0.4)
                    P = P + np.array([sx * 0.07, -0.02, 0.1])[None, :] * w[:, None]
                    rot[:, 1] += sx * w * np.radians(40)
                    poses["open"] = np.maximum(poses.get("open", 0), w)
                elif a == "count" and side == ".R":
                    P = P + np.array([-0.02, -0.08, 0.14])[None, :] * w[:, None]
                    rot[:, 0] += w * np.radians(-70)
                    words = [wd for wd in b["speech"]["words"] if wd["text"].lower().strip(".,!?") in
                             ("two", "three", "five", "seven")]
                    for k, wd in enumerate(words[:3]):
                        poses[f"count_{k + 1}"] = np.maximum(poses.get(f"count_{k + 1}", 0),
                                                             pulse(t, wd["start"] - 0.1, 0.1, 0.9, 0.15) * w)
                elif a == "fan_tongue" and side == ".L":
                    fan = np.sin(TAU * 4.0 * t)
                    P = P + np.array([-0.08 + 0.02 * 0, -0.1, 0.13])[None, :] * w[:, None]
                    P[:, 0] += 0.035 * fan * w
                    rot[:, 1] += fan * w * np.radians(30)
                    poses["open"] = np.maximum(poses.get("open", 0), w)
                elif a == "pinch" and side == ".R":
                    P = P + np.array([0.0, -0.1, 0.16])[None, :] * w[:, None]
                    rot[:, 0] += w * np.radians(-60)
                    poses["pinch"] = np.maximum(poses.get("pinch", 0), w)
                    P[:, 2] += 0.01 * np.sin(TAU * 5 * t) * w
                elif a == "gasp":
                    w = pulse(t, t0, 0.15, t1 - t0 - 0.6, 0.4)
                    P = P + np.array([-sx * 0.05, -0.06, 0.16])[None, :] * w[:, None]
                    poses["open"] = np.maximum(poses.get("open", 0), w)
                elif a in ("spin", "exit"):
                    P = P + np.array([sx * 0.1, 0.02, 0.08])[None, :] * w[:, None]
                    poses["open"] = np.maximum(poses.get("open", 0), w)
                elif a == "puff":
                    P = P + np.array([-sx * 0.04, -0.03, -0.02])[None, :] * w[:, None]
                elif a == "touch_hand" and side == ".R":
                    # reach for Euler's right hand on the armrest
                    eh = np.array(MK.euler_point((-0.2, -0.33, 0.69)))
                    local = self._cinn_local(eh, pos, yaw)
                    w = pulse(t, t0 + 0.8, 0.6, t1 - t0 - 1.0, 0.8)
                    P = P * (1 - w[:, None]) + local * w[:, None]
                    poses["open"] = np.maximum(poses.get("open", 0), w * 0.6)
                elif a == "savour":
                    P = P + np.array([-sx * 0.03, -0.05, 0.06])[None, :] * w[:, None]
                elif a == "sniff":
                    P = P + np.array([-sx * 0.02, -0.04, 0.03])[None, :] * w[:, None]
            # talking hands: small lifts on stress
            beat = np.zeros(n)
            for b in film.lines_of("cinnamon"):
                if b["act"] in ("count", "fan_tongue", "pinch", "touch_hand"):
                    continue
                last = -10.0
                for wd in b["speech"]["words"]:
                    if "ˈ" in wd.get("phonemes", "") and wd["end"] - wd["start"] > 0.22 and wd["start"] - last > 1.0:
                        beat = np.maximum(beat, pulse(t, wd["start"] - 0.25, 0.3, 0.15, 0.6))
                        last = wd["start"]
            beat = smooth_series(beat, fps, 0.06)
            P = P + np.array([sx * 0.02, -0.04, 0.06])[None, :] * (beat * (0.35 + 0.7 * mood["energy"]))[:, None]
            for i in range(3):
                self.bk.add(tg, "location", P[:, i], index=i)
            qs = [Quaternion((0, 0, 1), rot[f, 2]) @ Quaternion((0, 1, 0), rot[f, 1]) @
                  Quaternion((1, 0, 0), rot[f, 0]) @ rq for f in range(n)]
            for i, comp in enumerate("wxyz"):
                self.bk.add(tg, "rotation_quaternion", np.array([getattr(q, comp) for q in qs]), index=i)
            if poses:
                self._fingers(arm, side, poses)

    def _cinn_local(self, p, pos, yaw):
        """World point -> Cinnamon armature-local, per frame (ignores its
        small pitch and roll)."""
        d = np.asarray(p)[None, :] - pos
        c, s = np.cos(-yaw), np.sin(-yaw)
        return np.stack([d[:, 0] * c - d[:, 1] * s, d[:, 0] * s + d[:, 1] * c, d[:, 2]], 1)

    def _antennae(self, arm, pos, yaw, mood, sniff, taste):
        """Each antenna a chain of damped springs driven by the head's
        acceleration: lag on starts, overshoot on stops. Excitement perks
        them up, sadness droops them, a sniff sets them quivering."""
        film = self.film
        n, fps, t = film.n, film.fps, film.t
        acc = np.gradient(np.gradient(pos, axis=0), axis=0) * fps * fps
        c, s = np.cos(-yaw), np.sin(-yaw)
        ax = acc[:, 0] * c - acc[:, 1] * s
        ay = acc[:, 0] * s + acc[:, 1] * c
        az = acc[:, 2]
        spin = np.gradient(yaw) * fps
        perk = np.clip(mood["energy"] - 0.5, -0.5, 0.5) * 0.5 - np.clip(-mood["smile"], 0, 1) * 0.3
        for side, sx in ((".L", 1), (".R", -1)):
            for seg in range(1, 5):
                bn = f"ant_{seg}{side}"
                k = 40.0 + 10 * seg
                damp = 5.0
                # forcing: inertia (lag behind acceleration), centrifugal on spins
                fx = -(ax * 0.08) * seg * 0.5 + sx * spin * spin * 0.004
                fy = -(ay * 0.08 + az * 0.05) * seg * 0.5
                x = np.zeros(n)
                y = np.zeros(n)
                vx = vy = 0.0
                dt = 1.0 / fps
                sub = 4
                for f in range(1, n):
                    for _ in range(sub):
                        axx = -k * x[f - 1] - damp * vx + fx[f]
                        ayy = -k * y[f - 1] - damp * vy + fy[f]
                        vx += axx * dt / sub
                        vy += ayy * dt / sub
                        x[f - 1] += vx * dt / sub
                        y[f - 1] += vy * dt / sub
                    x[f], y[f] = x[f - 1], y[f - 1]
                quiver = (sniff * 0.06 + taste * 0.03) * np.sin(TAU * (9 + seg) * t + seg + sx)
                pitch = np.clip(y, -0.6, 0.6) - perk * 0.25 + quiver
                yawa = np.clip(x, -0.6, 0.6) + sx * 0.02 * np.sin(TAU * t / 2.9 + seg)
                self._bake_ypr(arm, bn, yawa * 0.6, pitch, yawa * 0.3)

    def _tongue(self, arm, pos, yaw):
        """Licks. The tongue is a curve attached to the jaw; its points are
        keyed in the jaw's frame, which is only known once the rest of the
        animation is in, so this runs frame by frame through the depsgraph
        -- only for the frames with a tongue out."""
        tongue = bpy.data.objects.get(arm.get("tongue", ""))
        if tongue is None:
            return
        film = self.film
        fps, t = film.fps, film.t
        self._tongue_jobs = []
        for b in film.beats:
            kind = None
            if b["do"] in ("lick", "slurp"):
                kind = b["do"]
            elif b["who"] == "cinnamon" and b["act"] == "fan_tongue":
                kind = "fan"
            if not kind:
                continue
            f0, f1 = int(b["start"] * fps), int(b["end"] * fps)
            if f1 < self.f0 or f0 > self.f1:
                continue
            self._tongue_jobs.append((kind, b, f0, f1))
        self._tongue_obj = tongue

    def _round_body(self, pts, clear=0.012, iterations=6):
        """Keep the tongue outside Cinnamon's own body, past the lips.

        Each point that would be inside the bean is pushed out to its
        surface, then the tongue is relaxed along its length so the push
        leaves no kink; the root in the mouth and the tip on the chalk stay
        where they are."""
        cin = self.rigs.get("cinnamon")
        if cin is None:
            return pts
        mw = cin.matrix_world
        spheres = [(np.array(mw @ Vector(c)), r) for c, r in self.CINNAMON_BODY[:2]]
        P = np.array(pts, float)
        k = len(P)
        start = 2               # the first points are in the mouth, where they belong
        for _ in range(iterations):
            for i in range(start, k - 1):
                for c, r in spheres:
                    d = P[i] - c
                    n_ = np.linalg.norm(d)
                    if n_ < r + clear:
                        P[i] = c + d / max(n_, 1e-6) * (r + clear)
            Q = P.copy()
            Q[start:k - 1] = 0.5 * P[start:k - 1] + 0.25 * (P[start - 1:k - 2] + P[start + 1:k])
            P = Q
        return [p for p in P]

    def _round_euler(self, pts, clear=0.03, iterations=4):
        """Bow the tongue round Euler's head and arms, ends fixed.

        The formulas are within his reach, so a tongue from across the
        slate passes right by his nose; a straight one went through it.
        Each round finds the point that is deepest inside him and bows the
        whole tongue out by enough to clear it, the most in the middle and
        none at the mouth or the chalk.
        """
        eu = getattr(self, "_euler_arm", None)
        if eu is None:
            return pts
        pw = eu.matrix_world
        caps = [(np.array(pw @ getattr(eu.pose.bones[a], ae)), np.array(pw @ getattr(eu.pose.bones[b], be)), r)
                for a, ae, b, be, r in self.EULER_BODY]
        P = np.array(pts, float)
        k = len(P)
        bow = np.sin(np.pi * np.arange(k) / (k - 1))
        for _ in range(iterations):
            worst, at, dirn = 0.0, 0, None
            for i in range(1, k - 1):
                for a, b, r in caps:
                    ab = b - a
                    t = np.clip(np.dot(P[i] - a, ab) / max(np.dot(ab, ab), 1e-9), 0, 1)
                    q = a + t * ab
                    d = np.linalg.norm(P[i] - q)
                    deficit = r + clear - d
                    if deficit > worst:
                        worst, at, dirn = deficit, i, (P[i] - q) / max(d, 1e-6)
            if worst <= 1e-4:
                break
            P += np.outer(bow / max(bow[at], 0.2), dirn * worst)
        return [p for p in P]

    def tongue_pass(self):
        """Call after bake(): keys the tongue's points for lick frames."""
        if not getattr(self, "_tongue_jobs", None):
            return
        tongue = self._tongue_obj
        from cartoon.characters.cinnamon import tongue_rest, TONGUE_POINTS
        sc = bpy.context.scene
        film = self.film
        fps = film.fps
        rest = np.array(tongue_rest())
        sp = tongue.data.splines[0]
        cu = tongue.data
        if cu.animation_data is None:
            cu.animation_data_create()
        if cu.animation_data.action is None:
            cu.animation_data.action = bpy.data.actions.new("tongue.perf")
        act = cu.animation_data.action
        frames_done = {}
        # how far along each lick goes was settled with the slate's wet
        # streak (sets/lick.py, via the timeline's slate events)
        reach_of = {e["beat"]: e.get("u_end", 1.0) for e in film.f.get("board", []) if e["kind"] == "lick"}
        for kind, b, f0, f1 in self._tongue_jobs:
            board = b.get("target") or "product"
            u_end = reach_of.get(b["index"], 1.0)
            for f in range(max(f0, self.f0), min(f1, self.f1) + 1):
                sc.frame_set(f)
                M = tongue.matrix_world.copy()
                Mi = M.inverted()
                mouth_w = np.array(M @ Vector(rest[-1]))
                s = (f - f0) / max(1, f1 - f0)
                if kind in ("lick", "slurp"):
                    u0, u1, v, h = MK.BOARD_LAYOUT[board]
                    if kind == "slurp":
                        u0, u1, v = 0.1, 1.0, 0.5
                    u1 = min(u1, u_end)
                    if s < 0.22:
                        out = ease(s / 0.22)
                        u = u0
                    elif s < 0.78:
                        out = 1.0
                        u = u0 + (u1 - u0) * ease((s - 0.22) / 0.56)
                    else:
                        out = 1 - ease((s - 0.78) / 0.22)
                        u = u1
                    vv = v + (0.35 * math.sin(TAU * s * 3) if kind == "slurp" else 0.0)
                    tip = np.array(MK.board_point(u, vv, lift=0.004))
                else:
                    out = 0.8 * pulse(np.array([s]), 0.0, 0.15, 0.7, 0.15)[0]
                    fwd = np.array(M.to_3x3() @ Vector((0, -1, 0)))
                    # hanging out of the mouth in front of the chin, flapping
                    tip = mouth_w + fwd * 0.11 + np.array([0, 0, -0.05]) \
                        + np.array([0.012 * math.sin(TAU * 4 * f / fps), 0, 0])
                # out through the lips, then on to the tip: a quadratic Bezier
                # from inside the mouth, through a point just in front of the
                # lips. A straight line from inside the mouth to a tip below it
                # came out through the chin.
                from cartoon.characters.cinnamon_shape import MOUTH_C
                mx, my, mz = MOUTH_C
                # out of the mouth forward before it turns for the chalk: a
                # control point well in front of the lips, so the tongue is
                # seen leaving the mouth rather than appearing out of its body
                ahead = 0.09 if kind in ("lick", "slurp") else 0.03
                lips = np.array(M @ Vector((mx, my - ahead, mz - 0.006)))
                pts = []
                nrm = np.array(MK.board_normal())
                for i in range(TONGUE_POINTS):
                    a = i / (TONGUE_POINTS - 1)
                    q = (1 - a) ** 2 * mouth_w + 2 * (1 - a) * a * lips + a ** 2 * tip
                    if kind in ("lick", "slurp"):
                        q = q + nrm * 0.01 * math.sin(math.pi * a) * out
                    rw = np.array(M @ Vector(rest[i]))
                    pts.append(rw * (1 - out) + q * out)
                if kind in ("lick", "slurp"):
                    pts = self._round_body(self._round_euler(pts))
                for i, p in enumerate(pts):
                    lp = Mi @ Vector(p)
                    frames_done.setdefault(i, []).append((f, lp))
        for i, lst in frames_done.items():
            for comp in range(3):
                fc = act.fcurve_ensure_for_datablock(cu, f"splines[0].points[{i}].co", index=comp)
                fc.keyframe_points.clear()
                # rest before and after, so the tongue is home between licks
                keys = [(self.f0 - 1, rest[i][comp])] + [(f, lp[comp]) for f, lp in lst] + [(self.f1 + 1, rest[i][comp])]
                # rest key right before each lick starts and after it ends
                fc.keyframe_points.add(len(keys))
                co = np.array([x for k in keys for x in k], float)
                fc.keyframe_points.foreach_set("co", co)
                fc.update()

    # ------------------------------------------------------------ the room
    def props(self):
        """The window that opens, the ship waiting outside it, the puff of
        scent that is Cinnamon's name."""
        film = self.film
        n, fps, t = film.n, film.fps, film.t
        sash = bpy.data.objects.get("sash_left")
        if sash is not None:
            ang = np.zeros(n)
            for b in film.beats:
                if b["do"] == "window_opens" and b["time"] == "night":
                    s = np.clip((t - b["start"] - 0.4) / 1.4, 0, 1)
                    # swings in, overshoots a touch, settles
                    swing = ease(s) + 0.08 * np.sin(np.pi * s) * (s < 1)
                    ang = np.maximum(ang, swing * (t >= b["start"]))
                    ang[t > b["end"]] = 1.0
            self.bk.add(sash, "rotation_euler", -np.radians(78) * ang, index=2)
        ship = bpy.data.objects.get("ship")
        if ship is not None and self.rigs.get("cinnamon") is not None:
            vis = np.zeros(n)
            for b in film.beats:
                if b["do"] == "window_opens" and b["time"] == "night":
                    vis[t >= b["start"]] = 1.0
            base = np.array([MK.WIN_X + 0.9, MK.ROOM_D / 2 + 1.6, 1.1])
            for i, off in enumerate((0.0, 0.0, 0.0)):
                pass
            bob = 0.05 * np.sin(TAU * t / 2.2)
            self.bk.add(ship, "location", np.full(n, base[0]), index=0)
            self.bk.add(ship, "location", np.full(n, base[1]), index=1)
            self.bk.add(ship, "location", base[2] + bob - 30 * (1 - vis), index=2)
            self.bk.add(ship, "rotation_euler", t * 0.8, index=2)
        # the puff: a little cloud of glowing scent drifting to Euler's nose
        puffs = [o for o in bpy.data.objects if o.name.startswith("scent.")]
        if puffs:
            for b in film.beats:
                if not (b["who"] == "cinnamon" and b["act"] == "puff"):
                    continue
                t0 = b["end"] - 0.9
                src = self.cpos[int(t0 * fps)] + np.array([0, 0, 0.02])
                dst = np.array(MK.HEAD_EULER) + np.array([0, -0.05, -0.02])
                for i, o in enumerate(puffs):
                    rng = np.random.default_rng(i)
                    jit = rng.normal(0, 0.04, 3)
                    delay = 0.04 * i
                    s = np.clip((t - t0 - delay) / 2.2, 0, 1)
                    path = src[None, :] * (1 - ease(s))[:, None] + dst[None, :] * ease(s)[:, None]
                    path = path + jit[None, :] * np.sin(np.pi * s)[:, None] * 2.0
                    path[:, 2] += 0.05 * np.sin(TAU * s * 1.5 + i)
                    size = np.sin(np.pi * np.clip(s * 1.1, 0, 1)) * (0.05 + 0.03 * rng.random()) * (s > 0)
                    for k in range(3):
                        self.bk.add(o, "location", path[:, k], index=k)
                        self.bk.add(o, "scale", np.maximum(size, 1e-4), index=k)

    # Euler as capsules on his bones: (from bone, from end, to bone, to end,
    # radius). Generous: his cap and hair stand off his skull, and his
    # waistcoat off his ribs.
    EULER_BODY = (
        ("root", "head", "neck", "head", 0.20),
        ("head", "head", "head", "tail", 0.17),
        ("upper_arm.L", "head", "upper_arm.L", "tail", 0.075),
        ("upper_arm.R", "head", "upper_arm.R", "tail", 0.075),
        ("forearm.L", "head", "forearm.L", "tail", 0.065),
        ("forearm.R", "head", "forearm.R", "tail", 0.065),
    )
    # Cinnamon as spheres in its own frame: lower bean, upper bean, nose
    CINNAMON_BODY = (((0.0, 0.0, -0.07), 0.16), ((0.0, -0.02, 0.09), 0.16), ((0.0, -0.15, 0.06), 0.07))

    def space_pass(self, iterations=3, margin=0.02):
        """Keep Cinnamon out of Euler.

        Its marks are places in the room, and a lick spot is wherever the
        formula is -- 38 cm out from the slate, which is where Euler sits,
        and through every lick of the first three cuts its body was inside
        his chest with his chin poking through it. The lick spots have moved
        (marks.lick_spot); this is what catches the next one. Every frame it
        comes near him, it is pushed out of capsules round his bones, and
        the push is smoothed in time so it drifts clear rather than popping.
        Runs before the tongue is aimed, which then reaches from wherever it
        ends up.
        """
        cin = self.rigs.get("cinnamon")
        eu = getattr(self, "_euler_arm", None)
        if cin is None or eu is None or cin.animation_data is None:
            return
        act = cin.animation_data.action
        floc = [act.fcurve_ensure_for_datablock(cin, "location", index=i) for i in range(3)]
        sc = bpy.context.scene
        # frames worth testing: where its planned path comes within reach of
        # him at rest, with room for how far he leans
        rest = eu.matrix_world
        bones = eu.data.bones
        caps0 = [(np.array(rest @ getattr(bones[a], "head_local" if ae == "head" else "tail_local")),
                  np.array(rest @ getattr(bones[b], "head_local" if be == "head" else "tail_local")), r)
                 for a, ae, b, be, r in self.EULER_BODY]

        def seg_dist(c, a, b):
            ab = b - a
            t = np.clip(np.dot(c - a, ab) / max(np.dot(ab, ab), 1e-9), 0.0, 1.0)
            q = a + t * ab
            return np.linalg.norm(c - q), q

        frames = []
        for f in range(self.f0, self.f1 + 1):
            c = self.cpos[f]
            if min(seg_dist(c, a, b)[0] - r for a, b, r in caps0) < 0.16 + 0.35:
                frames.append(f)
        if not frames:
            return
        key = lambda f: f - self.f0
        n = self.f1 - self.f0 + 1
        # hide the meshes while stepping frames: only the bones are needed
        hidden = [o for o in sc.objects if o.type == "MESH" and not o.hide_viewport]
        for o in hidden:
            o.hide_viewport = True

        def sample():
            push = np.zeros((n, 3))
            worst = 0.0
            for f in frames:
                sc.frame_set(f)
                mw = cin.matrix_world
                pw = eu.matrix_world
                caps = [(np.array(pw @ getattr(eu.pose.bones[a], ae)), np.array(pw @ getattr(eu.pose.bones[b], be)), r)
                        for a, ae, b, be, r in self.EULER_BODY]
                best = np.zeros(3)
                for lc, rc in self.CINNAMON_BODY:
                    c = np.array(mw @ Vector(lc))
                    for a, b, r in caps:
                        d, q = seg_dist(c, a, b)
                        need = r + rc + margin
                        if d < need:
                            v = (c - q) / max(d, 1e-6) * (need - d)
                            if np.linalg.norm(v) > np.linalg.norm(best):
                                best = v
                # nor through the slate: its spheres stay in front of the face
                for lc, rc in self.CINNAMON_BODY:
                    c = np.array(mw @ Vector(lc)) + best
                    rel = c - slate_o
                    u, v, d = rel @ slate_u, rel @ slate_v, rel @ slate_n
                    if -0.1 < u < MK.SLATE_W + 0.1 and -0.1 < v < MK.SLATE_H + 0.15 and -0.4 < d < rc + margin:
                        best = best + slate_n * (rc + margin - d)
                push[key(f)] = best
                worst = max(worst, float(np.linalg.norm(best)))
            return push, worst

        slate_o = np.array(MK.board_point(0.0, 0.0))
        slate_u = np.array(MK.board_point(1.0, 0.0)) - slate_o
        slate_u /= np.linalg.norm(slate_u)
        slate_v = np.array(MK.board_point(0.0, 1.0)) - slate_o
        slate_v /= np.linalg.norm(slate_v)
        slate_n = np.array(MK.board_normal())
        total = np.zeros((n, 3))
        moved = 0
        try:
            for it in range(iterations):
                push, worst = sample()
                if worst < 1e-4:
                    break
                # spread each push over a third of a second either side, so it
                # starts to drift clear before it would touch him
                sm = np.stack([smooth_series(push[:, i], self.film.fps, 0.12) for i in range(3)], 1)
                peak = np.linalg.norm(push, axis=1).max()
                speak = np.linalg.norm(sm, axis=1).max()
                if speak > 1e-9:
                    sm *= min(3.0, peak / speak)
                total += sm
                for i in range(3):
                    for k in range(n):
                        floc[i].keyframe_points[k].co[1] += sm[k, i]
                    floc[i].update()
                moved = int((np.linalg.norm(total, axis=1) > 0.002).sum())
            _, left = sample()
        finally:
            for o in hidden:
                o.hide_viewport = False
        # the cameras that follow it frame where it is, not where it was meant to be
        self.cpos[self.f0:self.f1 + 1] += total
        C.log(f"Cinnamon clear of Euler: {moved} frames moved, largest move "
              f"{np.linalg.norm(total, axis=1).max() * 100:.1f} cm, worst overlap left {left * 1000:.1f} mm")

    def chalk_pass(self, iterations=3):
        """Put the chalk's tip where the writing is, from in front of the slate.

        The IK target is the wrist, and the chalk sits in the fist beside the
        line of the arm. Two things have to be steered, in this order:

        1. which way the chalk points. Steering only the tip onto the text
           let the hand reach *through* the slate -- measured, 95% of it sat
           up to 14 cm behind the writing surface with the chalk poking out
           of the front, which reads as a transparent hand. So first the
           hand is turned until the chalk points into the slate the way a
           pen points into paper, the fist in front of it;
        2. where the tip is: then the target moves by the tip's miss.

        Every correction is scaled by the writing weight (which eases in and
        out), so nothing switches on at a threshold -- an earlier version
        did, and the hand jumped 24 cm at the end of each formula -- and the
        result is lightly smoothed in time so per-frame corrections cannot
        add a shake of their own.
        """
        writing = getattr(self, "_writing", None)
        if writing is None:
            return
        frames = [f for f in range(self.f0, self.f1 + 1) if writing[f] > 0.01]
        chalk = bpy.data.objects.get("euler.chalk")
        if not frames or chalk is None:
            return
        on = [f for f in frames if writing[f] > 0.98]
        arm = self._euler_arm
        tg = bpy.data.objects["euler.ik.hand.R"]
        act = tg.animation_data.action
        floc = [act.fcurve_ensure_for_datablock(tg, "location", index=i) for i in range(3)]
        frot = [act.fcurve_ensure_for_datablock(tg, "rotation_quaternion", index=i) for i in range(4)]
        sc = bpy.context.scene
        R_arm = arm.matrix_world.to_quaternion()
        R_inv = R_arm.inverted()
        nrm = Vector(MK.board_normal())
        up = (Vector(MK.board_point(0.5, 1.0)) - Vector(MK.board_point(0.5, 0.0))).normalized()
        away = (Vector(MK.board_point(0.0, 0.5)) - Vector(MK.board_point(1.0, 0.5))).normalized()
        # into the slate, tipped a little up and away from him: a pen's angle
        want_dir = (-nrm + up * 0.3 + away * 0.25).normalized()
        a_ = math.radians(-MK.EULER_YAW)
        c, s_ = math.cos(a_), math.sin(a_)

        def key(f):
            return f - self.f0

        def get_loc(f):
            return Vector([floc[i].keyframe_points[key(f)].co[1] for i in range(3)])

        def get_rot(f):
            return Quaternion([frot[i].keyframe_points[key(f)].co[1] for i in range(4)])

        def set_loc(f, v):
            for i in range(3):
                floc[i].keyframe_points[key(f)].co[1] = v[i]

        def set_rot(f, q):
            for i in range(4):
                frot[i].keyframe_points[key(f)].co[1] = q[i]

        def update():
            for fc in floc + frot:
                fc.update()

        def ends():
            tip = chalk.matrix_world @ Vector((0, 0, -0.0325))
            butt = chalk.matrix_world @ Vector((0, 0, 0.0325))
            return tip, butt

        hand_pb = arm.pose.bones["hand.R"]
        # which way up the hand is, once the chalk points into the slate: the
        # fingers rise from a low wrist toward the board, leaning away from
        # him, the back of the hand up and out -- a pen held against a wall
        fingers_want = (up * 0.8 + away * 0.6).normalized()

        def roll_to_upright(q, d_hand):
            """Turn about the chalk's own axis until the fingers point the way
            a hand writing on a wall points them. Aiming only the chalk left
            the hand free to spin round it, and it hung from the wrist
            knuckles-down, which read as an upside-down hand."""
            ax = want_dir
            cur = q @ d_hand
            cur_p = (cur - ax * cur.dot(ax))
            want_p = (fingers_want - ax * fingers_want.dot(ax))
            if cur_p.length < 1e-4 or want_p.length < 1e-4:
                return q
            cur_p.normalize()
            want_p.normalize()
            ang = math.atan2(ax.dot(cur_p.cross(want_p)), cur_p.dot(want_p))
            return Quaternion(ax, ang) @ q

        for it in range(iterations):
            # 1. aim the chalk, then stand the hand upright about it
            for f in frames:
                sc.frame_set(f)
                tip, butt = ends()
                d = (tip - butt).normalized()
                mw = arm.matrix_world
                d_hand = (mw @ hand_pb.tail - mw @ hand_pb.head).normalized()
                q = roll_to_upright(d.rotation_difference(want_dir), d_hand)
                q = Quaternion().slerp(q, float(writing[f]))
                set_rot(f, (R_inv @ q @ R_arm @ get_rot(f)).normalized())
            update()
            # 2. put the tip on the text
            for f in frames:
                sc.frame_set(f)
                tip, _ = ends()
                want = Vector(self._write_pt[f]) + nrm * 0.003
                d = (want - tip) * float(writing[f])
                local = Vector((d.x * c - d.y * s_, d.x * s_ + d.y * c, d.z))
                set_loc(f, get_loc(f) + local)
            update()
        # 3. smooth in time over the writing stretch (5-frame window)
        locs = {f: get_loc(f) for f in frames}
        rots = {f: get_rot(f) for f in frames}
        for f in frames:
            nb = [g for g in range(f - 2, f + 3) if g in locs]
            set_loc(f, sum((locs[g] for g in nb), Vector()) / len(nb))
            q = rots[f].copy()
            for g in nb:
                if g != f:
                    q = q.slerp(rots[g], 1.0 / len(nb))
            set_rot(f, q.normalized())
        update()
        # measure: where the tip is, and whether any of the hand is behind
        # the slate's face
        hand = bpy.data.objects.get("euler.hand.R")
        o = Vector(MK.board_point(0.5, 0.5))
        miss = 0.0
        behind = 0.0
        for f in on[::6]:
            sc.frame_set(f)
            tip, _ = ends()
            miss = max(miss, (Vector(self._write_pt[f]) + nrm * 0.003 - tip).length)
            if hand is not None:
                dg = bpy.context.evaluated_depsgraph_get()
                ev = hand.evaluated_get(dg)
                me = ev.to_mesh()
                mw = hand.matrix_world
                co = np.empty(len(me.vertices) * 3)
                me.vertices.foreach_get("co", co)
                co = co.reshape(-1, 3)[::7]
                M = np.array(mw)
                wc = co @ M[:3, :3].T + M[:3, 3]
                deep = float(((wc - np.array(o)) @ np.array(nrm)).min())
                ev.to_mesh_clear()
                behind = min(behind, deep)
        ups = []
        for f in on[::6]:
            sc.frame_set(f)
            mw = arm.matrix_world
            ups.append((mw @ hand_pb.tail - mw @ hand_pb.head).normalized().dot(up))
        C.log(f"chalk on the slate: {len(on)} frames touching, worst miss {miss * 1000:.1f} mm, "
              f"deepest hand point {behind * 1000:.1f} mm behind the slate, "
              f"fingers rising {min(ups, default=0):+.2f}..{max(ups, default=0):+.2f} (up is +1)")

    # ------------------------------------------------------------ run
    def run(self):
        self.euler()
        self.cinnamon()
        self.props()
        self.bk.bake()
        self.space_pass()
        self.tongue_pass()
        self.chalk_pass()
