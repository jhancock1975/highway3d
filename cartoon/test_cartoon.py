"""Checks that need no Blender and no render.

    cartoon/.venv/bin/python cartoon/test_cartoon.py

Each one is here because the thing it checks failed silently once, in
this project or in lectern next door: a hint accepted and animated by
nothing, a board placed out of an old man's reach, a mesh with a hole in
it, a gap between two shots.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

from cartoon import chalk, moods, script, sculpt, sound, timeline, vocab, voices  # noqa: E402
from cartoon.sets import marks as MK  # noqa: E402

DOC = os.path.join(HERE, "scripts", "the-flavor-of-nothing.yaml")
VOICE = os.path.join(HERE, ".work", "cartoon", "flavor", "voice")
FAILS = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f": {detail}"))
    if not ok:
        FAILS.append(name)


def test_document():
    doc = script.load(DOC)
    check("the film's document validates", script.validate(doc) == [], script.validate(doc))
    bad = dict(doc)
    bad["scenes"] = [dict(scene="study", time="night", beats=[{"euler": "hi", "act": "juggle", "mood": "sulky"},
                                                              {"do": "lick", "target": "nope", "seconds": 1}])]
    errs = " ".join(script.validate(bad))
    check("an unknown act is named in the error", "juggle" in errs and "write" in errs, errs)
    check("an unknown mood is named in the error", "sulky" in errs, errs)
    check("a lick at a board that does not exist is caught", "nope" in errs, errs)


def test_every_act_is_animated():
    """lectern once accepted `beat:` hints that nothing read. Every act the
    vocabulary allows must appear in the code that animates bodies."""
    src = ""
    for f in ("bl/perform.py", "timeline.py", "sound.py"):
        src += open(os.path.join(HERE, "cartoon", f)).read()
    missing = [a for a in vocab.ACTS if f'"{a}"' not in src]
    check("every act is animated somewhere", not missing, missing)
    missing = [d for d in vocab.DOS if f'"{d}"' not in src + open(os.path.join(HERE, "cartoon", "bl",
                                                                                   "exterior.py")).read()]
    check("every wordless beat is handled somewhere", not missing, missing)
    vis = open(os.path.join(HERE, "cartoon", "bl", "visions.py")).read()
    missing = [v for v in vocab.VISIONS if f'"{v}"' not in vis]
    check("every vision has a function", not missing, missing)


def test_timeline():
    if not os.path.isdir(VOICE):
        print("skip timeline (no narration yet)")
        return
    film = timeline.build(script.load(DOC), VOICE)
    shots = film["shots"]
    gaps = [(a["index"], b["index"]) for a, b in zip(shots, shots[1:]) if abs(a["end"] - b["start"]) > 1e-6]
    check("shots tile the film with no gaps", not gaps, gaps)
    check("the last shot ends where the film does", abs(shots[-1]["end"] - film["duration"]) < 1e-6)
    covered = sorted(set(i for s in shots for i in s["beats"]))
    check("every beat is seen in some shot (a long line may span two)", covered == list(range(len(film["beats"]))))
    known = set(film["setups"])
    odd = [s["setup"] for s in shots if s["setup"] not in known and not s["setup"].startswith(("vision_", "ext_"))]
    check("every shot's camera exists", not odd, odd)
    ts = [k["t"] for k in film["blocking"]]
    check("blocking keys are in time order", ts == sorted(ts))
    fps = film["fps"]
    whole = all(abs(b["end"] * fps - round(b["end"] * fps)) < 1e-6 for b in film["beats"])
    check("every beat ends on a whole frame", whole)
    # speech never overruns its beat
    over = [b["index"] for b in film["beats"] if b["who"] and
            b["speech"]["start"] + b["speech"]["duration"] > b["end"] + 1e-6]
    check("no line runs past the end of its beat", not over, over)


def test_reach():
    """Everything Euler writes must be reachable from his chair, leaning."""
    s = MK.euler_point((-0.195, 0.01, 0.935))
    c = MK.board_point(0.6, 0.5)
    d = [c[i] - s[i] for i in range(3)]
    n = math.sqrt(sum(x * x for x in d))
    lean = [s[i] + 0.25 * d[i] / n for i in range(3)]
    far = max(math.dist(MK.board_point(u, v), lean) for u0, u1, v, h in MK.BOARD_LAYOUT.values() for u in (u0, u1))
    check("every formula is within Euler's reach", far < 0.6, f"{far:.2f} m")


def test_sculpt():
    f = sculpt.Union([sculpt.Sphere((0, 0, 0), 0.1), sculpt.Ellipsoid((0.1, 0, 0), (0.06, 0.04, 0.03))], k=0.03)
    v, q = sculpt.surface_nets(f, (-0.2, -0.2, -0.2), (0.25, 0.2, 0.2), 0.005)
    edges = {}
    for a, b, c, d in q:
        for x, y in ((a, b), (b, c), (c, d), (d, a)):
            edges[(x, y)] = edges.get((x, y), 0) + 1
    holes = sum(1 for (x, y), k in edges.items() if k != 1 or edges.get((y, x)) != 1)
    check("surface nets make a closed surface", holes == 0, holes)
    P = v[q]
    nrm = np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 1])
    out = np.mean(np.einsum("ij,ij->i", nrm, P.mean(1) - [0.03, 0, 0]) > 0)
    check("its normals face outward", out > 0.99, out)


def test_board():
    film = dict(board=[dict(kind="write", board="basel", t0=0.0, t1=1.0),
                       dict(kind="lick", board="basel", t0=2.0, t1=3.0),
                       dict(kind="slurp", board=None, t0=5.0, t1=6.0)])
    pngs = {}
    work = os.path.join(HERE, ".work", "cartoon", "flavor", "chalk")
    have = [f for f in os.listdir(work)] if os.path.isdir(work) else []
    basel = next((os.path.join(work, f) for f in have if f.startswith("basel-") and f.endswith(".png")), None)
    if not basel:
        print("skip board (nothing typeset yet)")
        return
    b = chalk.Board(film, {"basel": basel}, MK.BOARD_LAYOUT)
    c0, _ = b.frame(-1.0)
    c1, _ = b.frame(1.5)
    c2, w2 = b.frame(2.6)
    c3, w3 = b.frame(6.5)
    check("the slate starts clean", c0.max() == 0)
    check("writing puts chalk on it", c1.max() > 0.5)
    check("a lick leaves it wet but keeps the chalk", w2.max() > 0.3 and c2.sum() > 0.9 * c1.sum())
    check("the slurp takes everything", c3.max() == 0 and w3.max() > 0.3)


def test_mix_length():
    if not os.path.isdir(VOICE):
        return
    film = timeline.build(script.load(DOC), VOICE)
    dia, duck = sound.dialogue(film)
    check("the dialogue bus covers the film", len(dia) >= int(film["duration"] * sound.SR))
    check("ducking is a 0..1 envelope", duck.min() >= -1e-6 and duck.max() <= 1 + 1e-6)


def test_tables_agree():
    check("every mood has all its numbers", all(len(moods.mood(m)) == 9 for m in moods.MOODS))
    check("every voice has a blend", all(voices.PRESETS[v]["blend"] for v in voices.VOICES))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"{len(FAILS)} failed" if FAILS else "all passed")
    sys.exit(1 if FAILS else 0)
