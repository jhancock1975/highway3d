"""A cartoon from a document, end to end.

    cartoon/.venv/bin/python -m cartoon.build --script scripts/the-flavor-of-nothing.yaml \
        --out renders/the-flavor-of-nothing.mp4

Steps, each cached so a rerun does only what changed:

  1. speak      every line, measured (Kokoro, .ttsvenv)
  2. time       film.json: timing, blocking, slate events, shots
  3. score      ACE-Step cues (lectern/.musicvenv) -- before any render, never during one
  4. typeset    the slate's formulas (Manim, lectern/.manimvenv)
  5. prepare    characters and sets, as .blend files
  6. render     every shot, frame by frame (Blender); frames already on disk
                are kept, so a stopped build resumes where it stopped
  7. mix        dialogue, synthesised foley, score ducked under speech
  8. assemble   frames + mix + title cards -> mp4

Progress is written to <work>/status.json as it goes, for anyone -- an MCP
client, a person -- who wants to know how far it has got.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import fonts  # noqa: E402
from cartoon import assemble, chalk, script, sound, timeline  # noqa: E402

TTS = os.path.join(ROOT, ".ttsvenv", "bin", "python")
MUSIC = os.path.join(ROOT, "lectern", ".musicvenv", "bin", "python")   # ACE-Step 1.5
BLENDER = os.environ.get("BLENDER", "blender")
ASSETS = os.path.join(ROOT, ".work", "cartoon", "assets")
SETS = os.path.join(ROOT, ".work", "cartoon", "sets")

SET_SOURCES = {
    "study": ["cartoon/sets/study.py", "cartoon/sets/marks.py"],
    "petersburg": ["cartoon/sets/petersburg.py"],
    "vision": ["cartoon/sets/vision.py"],
}
CHAR_SOURCES = {
    "euler": ["cartoon/characters/euler.py", "cartoon/characters/euler_shape.py", "cartoon/bl/face.py",
              "cartoon/bl/eyes.py", "cartoon/bl/rig.py", "cartoon/sculpt.py", "cartoon/bl/common.py"],
    "cinnamon": ["cartoon/characters/cinnamon.py", "cartoon/characters/cinnamon_shape.py", "cartoon/bl/face.py",
                 "cartoon/bl/eyes.py", "cartoon/bl/rig.py", "cartoon/sculpt.py", "cartoon/bl/common.py"],
}


class Status:
    def __init__(self, work):
        self.path = os.path.join(work, "status.json")
        self.s = dict(started=time.time(), step="start", done=[], shots_total=0, shots_done=0,
                      frames_total=0, frames_done=0, error=None, out=None)

    def set(self, **kw):
        self.s.update(kw)
        self.s["updated"] = time.time()
        with open(self.path + ".tmp", "w") as fh:
            json.dump(self.s, fh, indent=1)
        os.replace(self.path + ".tmp", self.path)

    def log(self, msg):
        print(f"[build] {msg}", flush=True)


def _stale(target, sources):
    if not os.path.exists(target):
        return True
    t = os.path.getmtime(target)
    return any(os.path.getmtime(os.path.join(ROOT, s)) > t for s in sources)


def _run(cmd, log=None, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if log:
        with open(log, "a") as fh:
            fh.write(r.stdout[-20000:] + r.stderr[-20000:])
    if r.returncode != 0:
        tail = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()][-15:]
        raise RuntimeError(f"{os.path.basename(cmd[0])} failed:\n" + "\n".join(tail))
    return r


def prepare(film, st, log):
    os.makedirs(ASSETS, exist_ok=True)
    for c, src in CHAR_SOURCES.items():
        out = os.path.join(ASSETS, f"{c}.blend")
        if _stale(out, src):
            st.log(f"building {c}")
            _run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(ROOT, "cartoon", "characters", f"{c}.py"),
                  "--", "--out", out], log)
    needed = set()
    for s in film["shots"]:
        needed.add("vision:void" if s["setup"].startswith("vision_") else f"{s['scene']}:{s['time']}")
    for key in sorted(needed):
        scene, t = key.split(":")
        out = os.path.join(SETS, f"{scene}_{t}.blend")
        src = SET_SOURCES[scene] + ["cartoon/shot.py"] + sum(CHAR_SOURCES.values(), [])
        if _stale(out, src) or any(os.path.getmtime(os.path.join(ASSETS, f"{c}.blend")) > os.path.getmtime(out)
                                   for c in CHAR_SOURCES if os.path.exists(out)):
            st.log(f"preparing {key}")
            _run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(ROOT, "cartoon", "shot.py"), "--",
                  "--prepare", key, "--out", out], log)


def set_for(shot):
    key = "vision_void" if shot["setup"].startswith("vision_") else f"{shot['scene']}_{shot['time']}"
    return os.path.join(SETS, f"{key}.blend")


def render(film, pngs, work, frames, st, log, engine, samples, res, only=None):
    fps = film["fps"]
    boards = os.path.join(work, "boards")
    shots = film["shots"] if only is None else [film["shots"][i] for i in only]
    total = sum(int(round(s["end"] * fps)) - int(round(s["start"] * fps)) for s in shots)
    st.set(step="render", shots_total=len(shots), frames_total=total)
    done_frames = 0
    for k, s in enumerate(shots):
        f0 = int(round(s["start"] * fps))
        f1 = int(round(s["end"] * fps)) - 1
        have = sum(os.path.exists(os.path.join(frames, f"f_{f:05d}.png")) for f in range(f0, f1 + 1))
        if have < f1 - f0 + 1:
            if s["scene"] == "study" and not s["setup"].startswith("vision_"):
                chalk.frames(film, pngs, f0, f1, boards, morning=s["time"] == "morning")
            st.log(f"shot {s['index']} {s['setup']} frames {f0}-{f1} ({have} already)")
            t = time.time()
            _run([BLENDER, "-b", set_for(s), "-P", os.path.join(ROOT, "cartoon", "shot.py"), "--",
                  "--film", os.path.join(work, "film.json"), "--shot", str(s["index"]), "--boards", boards,
                  "--chalk", os.path.join(work, "chalk"), "--out", frames, "--engine", engine,
                  "--samples", str(samples), "--res", res], log)
            st.log(f"  {(time.time() - t) / max(1, f1 - f0 + 1 - have):.1f}s a frame")
        done_frames += f1 - f0 + 1
        st.set(shots_done=k + 1, frames_done=done_frames, current_shot=s["index"])


def build(script_path, out, work=None, engine="BLENDER_EEVEE", samples=96, res="1920x1080",
          music=True, only=None, assemble_only=False):
    doc = script.load(script_path)
    bad = script.validate(doc)
    if bad:
        raise ValueError("the document has problems:\n" + "\n".join(bad))
    name = os.path.splitext(os.path.basename(script_path))[0]
    work = work or os.path.join(ROOT, ".work", "cartoon", name)
    os.makedirs(work, exist_ok=True)
    log = os.path.join(work, "build.log")
    st = Status(work)
    try:
        fonts.fetch_all()
        st.set(step="speak")
        st.log("speaking")
        _run([TTS, "-m", "cartoon.speak", "--script", script_path, "--work", work], log, cwd=ROOT)
        st.set(step="time")
        film = timeline.build(doc, os.path.join(work, "voice"))
        with open(os.path.join(work, "film.json"), "w") as fh:
            json.dump(film, fh, indent=1)
        st.log(f"{film['duration']:.1f}s, {len(film['shots'])} shots")
        music_wav = os.path.join(work, "music.wav")
        if music and not os.path.exists(music_wav):
            st.set(step="score")
            # ACE-Step must not load beside a render (the 2026-09-26 panic)
            while subprocess.run(["pgrep", "-x", "blender"], capture_output=True).returncode == 0:
                st.set(step="score (waiting for other renders to finish)")
                time.sleep(60)
            st.set(step="score")
            st.log("scoring (ACE-Step; nothing else runs meanwhile)")
            _run([MUSIC, "-m", "cartoon.score", "--film", os.path.join(work, "film.json"), "--out", music_wav],
                 log, cwd=ROOT)
        st.set(step="typeset")
        from cartoon.sets import marks as MK
        pngs = chalk.typeset(dict(doc.get("boards") or {}, **MK.GHOSTS), os.path.join(work, "chalk"))
        frames = os.path.join(work, "frames")
        os.makedirs(frames, exist_ok=True)
        if not assemble_only:
            st.set(step="prepare")
            prepare(film, st, log)
            render(film, pngs, work, frames, st, log, engine, samples, res, only)
        st.set(step="mix")
        mix = sound.mix(film, music_wav if os.path.exists(music_wav) else None, os.path.join(work, "mix.wav"))
        st.set(step="assemble")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        rx, ry = map(int, res.split("x"))
        assemble.assemble(film, frames, mix, out, size=(rx, ry))
        st.set(step="done", out=os.path.abspath(out))
        st.log(f"wrote {out}")
        return out
    except Exception as e:
        st.set(step="failed", error=str(e))
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work")
    ap.add_argument("--engine", default="BLENDER_EEVEE", choices=("BLENDER_EEVEE", "CYCLES"))
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--res", default="1920x1080")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--shots", help="only these shot numbers, e.g. 3,7,12")
    ap.add_argument("--assemble-only", action="store_true")
    a = ap.parse_args()
    only = [int(x) for x in a.shots.split(",")] if a.shots else None
    build(a.script, a.out, a.work, a.engine, a.samples, a.res, not a.no_music, only, a.assemble_only)


if __name__ == "__main__":
    main()
