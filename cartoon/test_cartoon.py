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
    """Everything Euler writes must be reachable from his chair -- measured
    from where his shoulder really is when he leans, which is only 6 cm from
    where it rests. The first check assumed 25 and passed while his hand
    hung off the slate's edge."""
    s = MK.euler_point(MK.WRITING_SHOULDER)
    far = max(math.dist(MK.board_point(u, v), s) for u0, u1, v, h in MK.BOARD_LAYOUT.values()
              for u in (u0, (u0 + u1) / 2, u1))
    check("every formula is within Euler's measured reach", far <= MK.CHALK_REACH, f"{far:.2f} m")


def test_cinnamon_clear_of_euler():
    """Cinnamon licked every formula from inside Euler's chest, in every cut
    until the fourth: a lick spot in front of a formula's middle is where he
    sits. Each lick spot must clear his head and his body by both sizes."""
    head = np.array(MK.HEAD_EULER)
    chest0, chest1 = np.array(MK.euler_point((0, 0, 0.55))), np.array(MK.euler_point((0, -0.02, 0.98)))

    def to_seg(p, a, b):
        t = np.clip(np.dot(p - a, b - a) / np.dot(b - a, b - a), 0, 1)
        return np.linalg.norm(p - (a + t * (b - a)))
    worst = min(min(np.linalg.norm(np.array(MK.lick_spot(b)) - head) - (0.17 + 0.16),
                    to_seg(np.array(MK.lick_spot(b)), chest0, chest1) - (0.20 + 0.16))
                for b in MK.BOARD_LAYOUT)
    check("every lick spot clears Euler", worst > 0.02, f"{worst * 100:.1f} cm")


def test_watch_spot_out_of_the_writing_shot():
    """Hovering just over the slate left Cinnamon cut off at the chin in the
    top of every writing shot. Its whole body must be outside that frame."""
    cam = timeline._write_cam()
    loc, tgt = np.array(cam["loc"], float), np.array(cam["target"], float)
    fwd = (tgt - loc) / np.linalg.norm(tgt - loc)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    hw = 18.0 / cam["lens"]
    hh = hw * 9 / 16
    lo, hi = np.array([-0.233, -0.205, -0.238]), np.array([0.233, 0.14, 0.407])
    g = np.stack(np.meshgrid(*[np.linspace(lo[i], hi[i], 7) for i in range(3)]), -1).reshape(-1, 3)
    d = g + np.array(MK.watch_spot()) - loc
    z = d @ fwd
    inside = (z > 0) & (np.abs((d @ right) / z) < hw) & (np.abs((d @ up) / z) < hh)
    check("Cinnamon's watch spot is out of the writing shot", not inside.any(), f"{inside.mean():.0%} in frame")


def test_licks_seen_and_stopped_short():
    """From the audience's side the far end of every formula is behind
    Euler's head, and a tongue sweeping on to it read as a tongue running
    into his mouth. Each lick stops short of his face on screen -- but still
    licks some of the formula -- and the slurp has a camera that sees all of
    the slate past him."""
    from cartoon.sets import lick as LK
    two = timeline.setups()["two"]
    frac = {}
    for b, (u0, u1, v, h) in MK.BOARD_LAYOUT.items():
        frac[b] = (LK.reach(two, b) - u0) / (u1 - u0)
    check("every lick licks some of its formula and stops short of his face",
          all(0.12 <= x < 1.0 for x in frac.values()) and max(frac.values()) > 0.2,
          ", ".join(f"{k} {x:.0%}" for k, x in frac.items()))
    try:
        cam = LK.slurp_camera()
        ok = True
    except RuntimeError as e:
        cam, ok = str(e), False
    check("the slurp has a camera that sees the whole slate past Euler", ok, cam)


def test_every_glyph_drawn_exists():
    """A character its font has no glyph for renders as nothing. Moving off
    the macOS fonts, the bakery sign's Cyrillic, the visions' pi, infinity
    and one-ninth would all have vanished without a word. Every string the
    film draws -- book spines, signs, the visions' labels, the cards -- must
    be covered by the font it is drawn in."""
    import ast
    import urllib.error
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        check("every glyph drawn exists (needs fonttools)", False, "uv pip install fonttools")
        return
    import fonts
    try:
        cmaps = {role: set(TTFont(fonts.path(role)).getBestCmap()) for role in fonts.FONTS}
    except (urllib.error.URLError, OSError) as e:
        print(f"skip glyphs (fonts not fetched: {e})")
        return

    def module(path):
        return ast.parse(open(os.path.join(HERE, path)).read())

    def constants(tree):
        """NAME = "role" assignments at module level."""
        return {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)
                and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}

    drawn = []          # (where, text, role)
    for path, call, default in (("cartoon/sets/study.py", "_text", "FONT_BOOK"),
                                ("cartoon/sets/petersburg.py", "_text", "FONT_BOOK"),
                                ("cartoon/bl/visions.py", "text", "FONT")):
        tree = module(path)
        roles = dict(constants(module("cartoon/sets/study.py")), **constants(tree))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == call and len(n.args) > 1:
                kw = next((k.value.id for k in n.keywords if k.arg == "font" and isinstance(k.value, ast.Name)), default)
                if isinstance(n.args[1], ast.Constant):
                    drawn.append((path, n.args[1].value, roles[kw]))
            # labels picked from literal lists (the Basel rings, the wheel's sectors, book titles)
            if isinstance(n, (ast.List, ast.Tuple)):
                for e in n.elts:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str) and not e.value.startswith("v."):
                        drawn.append((path, e.value, roles[default]))
    doc = script.load(DOC)
    drawn.append(("title card", doc["title"], "script"))
    for sc in doc["scenes"]:
        for b in sc.get("beats") or []:
            if b.get("card"):
                drawn += [("card", b["card"], "script"), ("card", b["card"], "caslon")]
    missing = sorted({(w, t, r, c) for w, t, r in drawn for c in t if not c.isspace() and ord(c) not in cmaps[r]})
    check("every glyph the film draws exists in its font", not missing,
          "; ".join(f"{t!r} in {r} ({w}) lacks {c!r}" for w, t, r, c in missing[:6]))


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


def test_no_cross_side_weights():
    """Built characters: nothing on one side follows the other side's bones.
    Cinnamon's left fingers once followed its right hand (shared labels)."""
    import subprocess, json as _j
    blend = os.path.join(HERE, ".work", "cartoon", "assets", "cinnamon.blend")
    if not os.path.exists(blend):
        print("skip cross-side weights (no built character)")
        return
    code = (
        "import bpy, json\n"
        "ob = bpy.data.objects['cinnamon.body']\n"
        "names = {g.index: g.name for g in ob.vertex_groups}\n"
        "bad = 0\n"
        "for v in ob.data.vertices:\n"
        "    x = v.co.x\n"
        "    for g in v.groups:\n"
        "        n = names[g.group]\n"
        "        if g.weight > 0.05 and abs(x) > 0.08 and ((x > 0 and n.endswith('.R')) or (x < 0 and n.endswith('.L'))):\n"
        "            bad += 1\n"
        "print('CROSS', bad)\n")
    r = subprocess.run(["blender", "-b", blend, "--python-expr", code], capture_output=True, text=True)
    line = [l for l in r.stdout.splitlines() if l.startswith("CROSS")]
    n = int(line[0].split()[1]) if line else -1
    check("no vertex follows a bone on the other side", n == 0, n)


def test_tables_agree():
    check("every mood has all its numbers", all(len(moods.mood(m)) == 9 for m in moods.MOODS))
    check("every voice has a blend", all(voices.PRESETS[v]["blend"] for v in voices.VOICES))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"{len(FAILS)} failed" if FAILS else "all passed")
    sys.exit(1 if FAILS else 0)
