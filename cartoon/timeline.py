"""From a document and its measured speech to a film: when everything
happens, where everyone is, what is on the slate, and which camera sees it.

Pure Python (PyYAML through script.py), so it runs anywhere and the whole
plan can be checked before a frame is drawn. The output, film.json, is the
only thing the Blender side reads.

Timing runs from the speech: every line lasts as long as it was measured to
take, plus a breath either side; wordless beats last as long as the
document says. Nothing is nudged into sync afterwards.
"""

from __future__ import annotations

import json
import math
import os

from cartoon import script
from cartoon.sets import marks as MK

LEAD = 0.14          # seconds of breath before a line
TAIL = 0.32          # and after it
SLOW = {"moved": 0.45, "wistful": 0.5, "tender": 0.25, "awed": 0.3}   # let these land


def _voice(voice_dir, beat):
    with open(os.path.join(voice_dir, beat["id"] + ".json")) as fh:
        return json.load(fh)


# ------------------------------------------------------------------ timing

def lay_out(doc, voice_dir, fps=24):
    beats = script.beats(doc)
    t = 0.0
    for b in beats:
        b["start"] = t
        if b["who"]:
            v = _voice(voice_dir, b)
            lead = LEAD
            tail = TAIL + SLOW.get(b["mood"], 0.0)
            b["speech"] = dict(wav=os.path.join(voice_dir, b["id"] + ".wav"),
                               start=t + lead, duration=v["duration"],
                               words=[dict(w, start=w["start"] + t + lead, end=w["end"] + t + lead)
                                      for w in v["words"]])
            b["end"] = t + lead + v["duration"] + tail
        else:
            b["end"] = t + float(b["seconds"])
        # whole frames, so shots cut on frame boundaries
        b["end"] = round(b["end"] * fps) / fps
        t = b["end"]
    return beats


def scenes_of(beats):
    out = []
    for b in beats:
        if not out or out[-1]["index"] != b["scene_index"]:
            out.append(dict(index=b["scene_index"], scene=b["scene"], time=b["time"],
                            start=b["start"], end=b["end"]))
        out[-1]["end"] = b["end"]
    return out


# ------------------------------------------------------------------ slate

def board_events(beats):
    """What happens to the slate, in order: writes, licks, the slurp.

    Licks do not erase -- the chalk stays and the tongue leaves a wet streak
    that dries -- so a formula licked and then added to ("+ 1 = 0") is still
    the same formula. Only the slurp takes the board clean.
    """
    ev = []
    for b in beats:
        if b["board"]:
            if b["who"]:
                s = b["speech"]
                t0, t1 = s["start"] + 0.1, s["start"] + s["duration"] - 0.05
            else:
                t0, t1 = b["start"] + 0.35, b["end"] - 0.35
            ev.append(dict(kind="write", board=b["board"], t0=t0, t1=t1, beat=b["index"]))
        if b["do"] == "lick" and b["target"]:
            ev.append(dict(kind="lick", board=b["target"], t0=b["start"] + 0.45, t1=b["end"] - 0.35,
                           beat=b["index"]))
        if b["do"] == "slurp":
            ev.append(dict(kind="slurp", board=None, t0=b["start"] + 0.9, t1=b["end"] - 0.7, beat=b["index"]))
    return ev


# ---------------------------------------------------------------- blocking

def blocking(beats, events):
    """Cinnamon's path as keyframes: (time, position, facing, how).

    `how` is the manner of the move -- "drift" for a lazy float, "zip" for
    a fast one with anticipation and overshoot, "sniff" for a meandering
    nose-first wander along a scent trail.
    """
    K = []
    pos = None
    lick_of = {e["beat"]: e for e in events if e["kind"] in ("lick", "slurp")}

    def go(t, where, how="drift", face="euler", dur=None):
        nonlocal pos
        p = MK.CINNAMON[where] if isinstance(where, str) else where
        K.append(dict(t=t, pos=list(p), face=face, how=how, dur=dur))
        pos = p

    for b in beats:
        if b["scene"] != "study":
            continue
        if b["time"] == "morning":
            continue
        t0, t1 = b["start"], b["end"]
        if pos is None:
            go(t0, "outside", face="window")
        if b["do"] == "window_opens":
            go(t0 + 1.2, "outside", face="window")
            go(t1 - 0.2, "window", how="drift", face="slate", dur=t1 - 0.2 - (t0 + 1.2))
        elif b["who"] == "cinnamon" and b["act"] == "sniff" and pos == MK.CINNAMON["window"]:
            go(t0 + 0.2, "window", face="slate")
            go(t1 - 0.4, "home", how="sniff", face="slate", dur=t1 - 0.6 - t0)
        elif b["do"] in ("lick", "slurp"):
            e = lick_of[b["index"]]
            spot = MK.lick_spot(e["board"] or "product")
            if b["do"] == "slurp":
                spot = MK.lick_spot("product")
                spot = (spot[0] + 0.1, spot[1] - 0.1, spot[2] + 0.05)
            go(t0, pos, face="board")
            go(t0 + 0.5, spot, how="zip", face="board", dur=0.5)
            go(t1, spot, face="board")
        elif (b["who"] == "euler" and b["act"] == "write" or b["do"] == "write") and pos is not None \
                and tuple(pos) not in (tuple(MK.CINNAMON["outside"]), tuple(MK.CINNAMON["window"])):
            # it floats up to peek over the slate at what he is writing
            go(t0, pos, face="euler")
            go(t0 + 1.0, MK.watch_spot(), how="drift", face="board", dur=1.0)
        elif b["act"] == "touch_hand":
            go(t0, pos, face="euler")
            go(t0 + 0.9, "close", how="drift", face="euler", dur=0.9)
        elif b["act"] == "exit":
            go(t0, pos, face="window")
            go(t0 + 0.6, "window", how="zip", face="window", dur=0.6)
            go(t1, "outside", how="zip", face="window", dur=t1 - t0 - 0.6)
        elif b["who"] == "cinnamon" and b["act"] == "spin":
            go(t0, pos)
            go(t0 + 0.6, "high", how="drift", face="euler", dur=0.6)
        elif b["do"] == "ship_toots":
            go(t0, pos, face="window")
        elif b["do"] == "vision":
            pass
        else:
            # after a lick or a spin, come back to where the conversation is;
            # otherwise just turn to him
            home = MK.CINNAMON["home"]
            if pos is not None and tuple(pos) not in (tuple(home), tuple(MK.CINNAMON["close"])) \
                    and tuple(pos) != tuple(MK.CINNAMON["outside"]) and tuple(pos) != tuple(MK.CINNAMON["window"]):
                go(t0, pos)
                go(t0 + 0.9, "home", how="drift", face="euler", dur=0.9)
            elif pos is not None and tuple(pos) != tuple(MK.CINNAMON["outside"]):
                go(t0 + 0.15, pos, face="euler")
    return K


# ------------------------------------------------------------------ cameras

def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _add(a, b, k=1.0):
    return [x + y * k for x, y in zip(a, b)]


def _rot2(v, deg):
    a = math.radians(deg)
    return [v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a), v[2]]


EULER_HEAD = list(MK.euler_point((0.0, -0.06, 1.2)))
EULER_CHEST = list(MK.euler_point((0.0, -0.05, 0.95)))


def _single(subject, other, dist, lens, side=1, off_deg=22, height=0.0, look_down=0.0):
    """A camera on `subject` from roughly where `other` is, swung off the
    line by off_deg toward the side all cameras live on."""
    d = _unit([other[0] - subject[0], other[1] - subject[1], 0])
    d = _rot2(d, side * off_deg)
    loc = _add(subject, d, dist)
    loc[2] = subject[2] + height
    tgt = list(subject)
    tgt[2] -= look_down
    return dict(loc=loc, target=tgt, lens=lens)


def _write_cam():
    """In front of him and a little to his left -- on the audience's side of
    the line -- with the slate raking away at frame left as he turns to it."""
    head = MK.euler_point((0, -0.06, 1.2))
    f = MK._rz((0, -1, 0), MK.EULER_YAW)
    left = MK._rz((1, 0, 0), MK.EULER_YAW)
    bp = MK.board_point(0.7, 0.6)
    loc = [head[i] + f[i] * 1.2 + left[i] * 0.6 for i in range(3)]
    loc[2] = head[2] + 0.1
    tgt = [(head[i] * 0.55 + bp[i] * 0.45) for i in range(3)]
    return dict(loc=loc, target=tgt, lens=30)


def setups():
    """Named camera setups for the study. All keep to one side of the line
    between Euler and Cinnamon's home, so screen direction never flips:
    Euler looks screen-left, Cinnamon screen-right."""
    home = list(MK.CINNAMON["home"])
    close = list(MK.CINNAMON["close"])
    bp = list(MK.board_point(0.62, 0.5))
    bn = list(MK.board_normal())
    S = {
        "wide": dict(loc=[1.95, -2.1, 1.7], target=[-0.1, 0.65, 1.05], lens=24, track="both", follow=0.3),
        "two": dict(loc=[1.25, -1.05, 1.38], target=[0.02, 0.55, 1.15], lens=32, track="both", follow=0.75),
        "two_tight": dict(loc=[0.95, -0.55, 1.32], target=[0.02, 0.55, 1.17], lens=40, track="both", follow=0.75),
        # side: +1 for Euler, -1 for Cinnamon keeps both singles on the
        # audience's side of the line between them (the side "two" is on)
        "euler_mcu": _single(EULER_HEAD, home, 1.05, 45, side=1, off_deg=42, height=0.02, look_down=0.05),
        "euler_cu": _single(EULER_HEAD, home, 0.95, 55, side=1, off_deg=36, height=0.03, look_down=0.03),
        "cinn_mcu": _single([home[0], home[1], home[2] + 0.02], EULER_HEAD, 1.15, 50, side=-1, off_deg=30,
                            height=-0.02),
        "cinn_cu": _single([home[0], home[1], home[2] + 0.04], EULER_HEAD, 0.9, 55, side=-1, off_deg=26),
        "close_two": dict(loc=[0.75, -0.45, 1.05], target=[0.0, 0.55, 0.95], lens=45),
        "slate": dict(loc=_add(bp, bn, 1.05), target=bp, lens=38),
        "lick": dict(loc=[0, 0, 0], target=[0, 0, 0], lens=30, track="lick"),
        # from beside the slate, looking back at him as he writes: his face,
        # the chalk hand in the foreground, the board raking away at left
        "euler_write": _write_cam(),
        "window": dict(loc=[1.2, -0.3, 1.35], target=[MK.WIN_X - 0.2, MK.ROOM_D / 2, 1.55], lens=30),
        "door": dict(loc=[1.6, 0.6, 1.4], target=[-2.9, -1.8, 1.2], lens=28),
    }
    # the morning after: the room in daylight, the door Fuss knocks on
    S["morning_wide"] = dict(S["wide"])
    S["morning_wide"].pop("track", None)
    S["morning_door"] = dict(loc=[0.9, 0.2, 1.35], target=[-2.95, -1.8, 1.25], lens=24)
    S["morning_euler"] = dict(S["euler_cu"])
    S["cinn_close"] = _single([close[0], close[1], close[2] + 0.06], EULER_HEAD, 0.9, 55, side=-1, off_deg=35)
    # singles on Cinnamon follow it: it floats, and it is not always on its mark
    for k in ("cinn_mcu", "cinn_cu", "cinn_close"):
        S[k]["track"] = "cinnamon"
        S[k]["mark"] = list(home) if k != "cinn_close" else list(close)
        S[k]["follow"] = 0.85
    return S


EMOTIONAL = {"moved", "tender", "wistful", "awed", "concerned", "content"}


_BLOCK = []

LONG_LINE = 7.5
REACTION = {"euler_mcu": "cinn_mcu", "euler_cu": "cinn_cu", "cinn_mcu": "euler_mcu", "cinn_cu": "euler_cu",
            "two": "two_tight", "two_tight": "two"}


def _mid_line_cut(b, setup, fps=24):
    """A long line cuts once, at the sentence end nearest its middle, to the
    listener's face (or from one two-shot to the other). An editor would;
    twelve seconds on one angle is where attention goes to die."""
    if not b["who"] or setup not in REACTION or b["end"] - b["start"] < LONG_LINE:
        return None
    words = b["speech"]["words"]
    mid = (b["start"] + b["end"]) / 2
    ends = [w["end"] for w in words if w["text"].strip()[-1:] in ".!?" and b["start"] + 2.0 < w["end"] < b["end"] - 2.0]
    if not ends:
        return None
    t = min(ends, key=lambda e: abs(e - mid)) + 0.12
    react = REACTION[setup]
    if react.startswith("cinn"):
        # only cut to Cinnamon's face if it is in the conversation: at the
        # window it is a speck in a two-shot, not a close-up
        p = _cinnamon_at(t)
        if p is not None and math.dist(p, MK.CINNAMON["home"]) > 0.8:
            react = "window" if p[1] > MK.ROOM_D / 2 - 0.8 else "two"
    return round(t * fps) / fps, react


def _cinnamon_at(t):
    keys = sorted(_BLOCK, key=lambda k: k["t"])
    if not keys:
        return None
    p = keys[0]["pos"]
    for k in keys:
        if k["t"] <= t:
            p = k["pos"]
    return p


def plan_shots(beats, scenes):
    """One camera setup per beat, then consecutive beats that share a setup
    merge into a shot. Rules, not taste -- but rules written by watching:
    the speaker is seen, the lines that matter are close, the action is
    seen from where it reads, and a two-shot comes round often enough that
    the audience never loses where everyone is."""
    last_single = {"euler": 0, "cinnamon": 0}
    plan = []
    n_line = 0
    for i, b in enumerate(beats):
        if b["scene"] == "petersburg":
            setup = "ext_" + b["time"]
        elif b["time"] == "morning":
            setup = "morning_wide" if b["do"] == "knock" else ("morning_door" if b["who"] == "fuss"
                                                                else "morning_euler")
        elif b["do"] == "vision":
            setup = "vision_" + b["vision"]
        elif b["do"] == "window_opens" or b["do"] == "ship_toots":
            setup = "window"
        elif b["do"] == "lick":
            setup = "lick"
        elif b["do"] == "write":
            setup = "slate"
        elif b["do"] == "slurp":
            setup = "lick"
        elif b["who"] == "euler":
            n_line += 1
            if b["act"] == "write":
                setup = "euler_write"
            elif b["mood"] in EMOTIONAL:
                setup = "euler_cu"
            elif b["act"] in ("laugh", "lean_in") or n_line % 4 == 0:
                setup = "two"
            else:
                setup = "euler_mcu"
        elif b["who"] == "cinnamon":
            n_line += 1
            if b["act"] == "touch_hand":
                setup = "close_two"
            elif b["act"] in ("exit", "spin", "puff"):
                setup = "two" if b["act"] != "exit" else "window"
            elif b["mood"] in EMOTIONAL:
                setup = "cinn_cu"
            elif b["act"] == "sniff" and any(k["t"] > b["start"] and k["t"] <= b["end"] and (k.get("dur") or 0) > 2.0
                                             for k in _BLOCK):
                setup = "wide"
            elif n_line % 5 == 0:
                setup = "two_tight"
            else:
                setup = "cinn_mcu"
        else:
            setup = "two"
        # after a touch, stay close for the rest of the moment
        if b["who"] and i > 0 and plan and plan[-1]["setup"] == "close_two" and b["mood"] in EMOTIONAL:
            setup = "close_two"
        plan.append(dict(beat=i, setup=setup))
    shots = []
    for p in plan:
        b = beats[p["beat"]]
        parts = [(b["start"], b["end"], p["setup"])]
        cut = _mid_line_cut(b, p["setup"])
        if cut:
            parts = [(b["start"], cut[0], p["setup"]), (cut[0], b["end"], cut[1])]
        for s0, s1, setup in parts:
            if shots and shots[-1]["setup"] == setup and shots[-1]["scene_index"] == b["scene_index"]:
                shots[-1]["end"] = s1
                if p["beat"] not in shots[-1]["beats"]:
                    shots[-1]["beats"].append(p["beat"])
            else:
                shots.append(dict(setup=setup, scene=b["scene"], time=b["time"], scene_index=b["scene_index"],
                                  start=s0, end=s1, beats=[p["beat"]]))
    # the opening line gets an establishing wide before it cuts in
    for i, s in enumerate(shots):
        s["index"] = i
    return shots


def build(doc, voice_dir, fps=24):
    beats = lay_out(doc, voice_dir, fps)
    sc = scenes_of(beats)
    ev = board_events(beats)
    film = dict(title=doc.get("title"), fps=fps, duration=beats[-1]["end"],
                frames=int(round(beats[-1]["end"] * fps)),
                beats=beats, scenes=sc, board=ev, blocking=blocking(beats, ev),
                boards=doc.get("boards") or {},
                setups=setups(), shots=None)
    _BLOCK[:] = film["blocking"]
    film["shots"] = plan_shots(beats, sc)
    return film


def summary(film):
    lines = [f"{film['title']}: {film['duration']:.1f}s, {film['frames']} frames, {len(film['shots'])} shots"]
    for s in film["shots"]:
        lines.append(f"  {s['index']:3d} {s['setup']:14s} {s['start']:7.2f}-{s['end']:7.2f} "
                     f"({s['end'] - s['start']:5.2f}s) beats {s['beats'][0]}-{s['beats'][-1]}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    doc = script.load(sys.argv[1])
    f = build(doc, sys.argv[2])
    print(summary(f))
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w") as fh:
            json.dump(f, fh, indent=1)
