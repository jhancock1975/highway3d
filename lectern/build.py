"""Build a whole lecture: narrate, plan, render every shot, assemble.

    python3 -m lectern.build --script lectures/relativity.yaml \
        --out renders/relativity.mp4 --quality draft

Runs as a detached job, because a final render is about twelve hours and no
tool call may take that long. Progress goes to stdout as `PROGRESS {...}`
lines that `lecture_status` reads back; the job survives the session that
started it.

Three interpreters, on purpose. This one orchestrates; `.ttsvenv` holds
Kokoro and torch and does the speaking; Blender does the drawing. None of them
can import the others, and pretending otherwise is how a renderer ends up
shipping a gigabyte of ML dependencies to draw a chalkboard.

Everything is cached by a hash of its own inputs, and shots are rendered in
local time, so fixing a word in chapter two re-renders that shot and nothing
else -- even though every start time after it has moved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lectern import script as S  # noqa: E402
from lectern.delivery import DELIVERIES  # noqa: E402

TTSVENV = os.path.join(HERE, ".ttsvenv", "bin", "python")
MANIMVENV = os.path.join(HERE, "lectern", ".manimvenv", "bin", "python")
BLENDER = os.environ.get("LECTERN_BLENDER", "blender")

SHOT_FOR_STAGE = {"card": "note", "board": "note", "note": "note",
                  "demo": "demo", "scene": "scene"}


def digest(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode())
    return h.hexdigest()[:16]


def progress(stage: str, done: int, total: int, **extra) -> None:
    print("PROGRESS " + json.dumps(dict(stage=stage, done=done, total=total,
                                        **extra)), flush=True)


def preflight(doc, segments) -> None:
    """Stage everything the document names, before rendering any of it.

    Seconds, against the hours that a failure at shot thirty costs -- and a
    failure at shot thirty does not just waste the thirty, it leaves the
    machine doing nothing until somebody notices.
    """
    wanted = sorted({s["stage"]["demo"] for s in segments
                     if "demo" in s["stage"]})
    r = subprocess.run(
        [BLENDER, "--background", "--factory-startup", "--python",
         os.path.join(HERE, "lectern", "preflight.py"), "--",
         "--demos", ",".join(wanted), "--look", doc["look"]],
        cwd=HERE, capture_output=True, text=True)
    line = next((x for x in (r.stdout or "").splitlines()
                 if x.startswith("PREFLIGHT")), "")
    if not line:
        raise RuntimeError(
            "preflight did not report: " + (r.stderr or r.stdout)[-400:])
    report = json.loads(line[len("PREFLIGHT"):])
    if report["problems"]:
        raise RuntimeError("preflight found " + "; ".join(report["problems"][:6]))
    progress("preflight", report["demos"], report["demos"])


def narrate_all(doc, segments, work) -> list[dict]:
    """One wav and one phoneme timeline per segment, cached by what was said."""
    voice = doc["voice"]
    out = []
    for i, seg in enumerate(segments):
        # The delivery's *numbers*, not just its name. Keyed on the name
        # alone, editing the table silently reused audio synthesised with the
        # old values -- half the lecture at one setting and half at another,
        # with nothing reporting it. This is what CHARACTER_VERSION does for
        # the presenter, except that it needs no one to remember to bump it.
        key = digest(seg["say"], voice["preset"], voice["speed"],
                     seg["delivery"],
                     sorted(DELIVERIES[seg["delivery"]].items()))
        stem = os.path.join(work, f"vo-{key}")
        if not os.path.exists(stem + ".json"):
            r = subprocess.run(
                [TTSVENV, "-m", "lectern.narrate", "--text", seg["say"],
                 "--out", stem, "--preset", voice["preset"],
                 "--speed", str(voice["speed"]),
                 "--delivery", seg["delivery"]],
                cwd=HERE, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(
                    f"narration failed on segment {i}: "
                    f"{(r.stderr or r.stdout).strip()[-400:]}")
        with open(stem + ".json") as fh:
            timeline = json.load(fh)
        out.append(dict(seg=seg, stem=stem, timeline=timeline, key=key))
        progress("narrating", i + 1, len(segments))
    return out


def write_notation(doc, narrated, work) -> dict:
    """Render the chalkboard writing for every note, before any frames.

    Manim is its own interpreter with its own LaTeX, so this is a subprocess
    like narration is. Cached on the lines and the duration, so re-rendering a
    shot does not re-typeset what it already has.
    """
    out = {}
    notes = [n for n in narrated
             if next(iter(n["seg"]["stage"]), "") in
             ("note", "board", "card", "demo")]
    for i, n in enumerate(notes):
        kind = next(iter(n["seg"]["stage"]))
        spec = n["seg"]["stage"][kind]
        if kind == "board":
            # Written points are the same object as notation, without maths.
            spec = dict(heading=spec.get("heading", ""),
                        lines=list(spec.get("items", [])))
        elif kind == "demo":
            # During a demonstration the board keeps the chapter on it, the
            # way a real one does. A blank slab taking a third of the frame
            # reads as a set nobody finished dressing.
            spec = dict(heading=n["seg"]["chapter_title"], lines=[])
        elif kind == "card":
            # A chapter opening still goes on the board; an empty board
            # behind a title reads as a set nobody has dressed.
            spec = dict(heading=spec.get("title", ""),
                        lines=[spec.get("subtitle", "")]
                        if spec.get("subtitle") else [])
        tail = 2.4 if n["seg"]["first_in_chapter"] else 0.9
        duration = n["timeline"]["duration"] + tail
        r = subprocess.run(
            [MANIMVENV, "-m", "lectern.notation",
             "--heading", spec.get("heading", "") or "",
             "--lines", json.dumps(list(spec.get("lines", []))),
             "--duration", f"{duration:.3f}", "--fps", str(doc["fps"]),
             "--work", work],
            cwd=HERE, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(
                f"notation failed on segment {n['seg']['index']}: "
                f"{(r.stderr or r.stdout).strip()[-400:]}")
        out[n["seg"]["index"]] = json.loads(
            r.stdout.strip().splitlines()[-1])["frames"]
        progress("typesetting", i + 1, len(notes))
    return out


def render_shots(doc, narrated, work, quality, width, height,
                 notation=None) -> list[str]:
    """Every shot, in one Blender process.

    One launch, not eighty-two. Blender registers its bundle with the window
    server on every start -- as a Foreground app, even under --background --
    so launching it per shot put an icon in the Dock every couple of minutes
    for the length of the render. Batching also stops it paying the scene
    build cost once per shot.
    """
    engine = "cycles" if quality == "final" else "eevee"
    samples = 64 if quality == "final" else 48

    jobs, shots = [], []
    for n in narrated:
        stage_kind = next(iter(n["seg"]["stage"]), "card")
        shot_type = SHOT_FOR_STAGE.get(stage_kind, "mid")
        tail = 2.4 if n["seg"]["first_in_chapter"] else 0.9
        board = (notation or {}).get(n["seg"]["index"], "")
        # A beat only joins the key when the document actually asks for one,
        # so adding this did not invalidate every shot already rendered.
        beat = n["seg"].get("beat", "")
        key = digest(n["key"], stage_kind, shot_type, doc["look"],
                     doc["presenter"], engine, samples, width, height,
                     tail, os.path.basename(board), CHARACTER_VERSION,
                     *((beat,) if beat else ()))
        out = os.path.join(work, f"shot-{key}.mp4")
        shots.append(out)
        if os.path.exists(out):
            continue
        jobs.append(dict(
            timeline=n["stem"] + ".json", audio=n["stem"] + ".wav",
            out=out, shot=shot_type, look=doc["look"], tail=tail,
            demo=n["seg"]["stage"]["demo"] if stage_kind == "demo" else "",
            scene=n["seg"]["stage"]["scene"] if stage_kind == "scene" else "",
            beat=beat,
            notation=board,
            frames_dir=os.path.join(work, f"frames-{key}")))

    if jobs:
        spec = os.path.join(work, "jobs.json")
        with open(spec, "w") as fh:
            json.dump(jobs, fh)
        began = time.time()
        proc = subprocess.Popen(
            [BLENDER, "--background", "--factory-startup", "--python",
             os.path.join(HERE, "lectern", "shot.py"), "--",
             "--jobs", spec, "--engine", engine, "--samples", str(samples),
             "--width", str(width), "--height", str(height),
             "--fps", str(doc["fps"])],
            cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True)
        done = 0
        trailing = []
        for line in proc.stdout:
            line = line.rstrip()
            trailing.append(line)
            del trailing[:-40]
            if line.startswith("SHOT "):
                done += 1
                rate = (time.time() - began) / done
                progress("rendering", done, len(jobs),
                         eta_hours=round(rate * (len(jobs) - done) / 3600, 2))
        if proc.wait() != 0:
            raise RuntimeError("rendering failed: "
                               + "\n".join(trailing[-12:])[-600:])

    missing = [s for s in shots if not os.path.exists(s)]
    if missing:
        raise RuntimeError(f"{len(missing)} shot(s) never appeared, "
                           f"first: {os.path.basename(missing[0])}")
    return shots


# Bumped whenever the presenter or the set changes shape, so shots cached
# against an older look are rebuilt rather than silently reused. 7: the
# presenter gained articulated arms and legs, the camera framings opened up
# to hold a whole figure, and the body is animated. 8: the arms swing away
# from the body rather than into it. 9: he walks to the board and points at
# what is written on it.
CHARACTER_VERSION = 9


def assemble(shots, out, work, music=None) -> None:
    listing = os.path.join(work, "shots.txt")
    with open(listing, "w") as fh:
        for s in shots:
            fh.write(f"file '{os.path.abspath(s)}'\n")
    joined = out if not music else os.path.join(work, "_joined.mp4")
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", listing, "-c", "copy", "-movflags", "+faststart", joined],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"assembly failed: {r.stderr.strip()[-400:]}")
    if music:
        score_under(joined, out, work, music)


def duration_of(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def score_under(joined: str, out: str, work: str, music: dict) -> None:
    """Lay a written score under the finished lecture, ducked by the speech.

    The score is one continuous piece across the whole film rather than one
    per shot: music that restarts at every cut is worse than no music, and
    the shots are only cut apart because rendering is, not because the
    picture is.

    Ducking is `sidechaincompress` with the voice as the key, which is how
    it is done rather than by mixing at a level low enough to be safe. A bed
    quiet enough never to trouble the words is also quiet enough not to be
    there; ducked, it can sit up in the gaps and drop away under speech.
    """
    seconds = duration_of(joined)
    mood = music.get("mood", "night")
    level = float(music.get("level", 0.13))
    key = digest(mood, round(seconds, 2), music.get("seed", 11))
    wav = os.path.join(work, f"score-{key}.wav")
    if not os.path.exists(wav):
        r = subprocess.run(
            [TTSVENV, "-m", "lectern.score", "--duration", f"{seconds:.3f}",
             "--out", wav, "--mood", mood,
             "--seed", str(music.get("seed", 11))],
            cwd=HERE, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(
                "score failed: " + (r.stderr or r.stdout).strip()[-400:])
    chain = (f"[1:a]volume={level}[m];"
             f"[m][0:a]sidechaincompress=threshold=0.03:ratio=9:"
             f"attack=12:release=320[duck];"
             f"[duck][0:a]amix=inputs=2:normalize=0[mix]")
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", joined, "-i", wav,
         "-filter_complex", chain, "-map", "0:v", "-map", "[mix]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", out],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"scoring failed: {r.stderr.strip()[-400:]}")
    progress("scoring", 1, 1, mood=mood, level=level,
             minutes=round(seconds / 60, 2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--quality", default="draft", choices=("draft", "final"))
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--work", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--job", default="")
    ap.add_argument("--narrate-only", action="store_true",
                    help="speak every segment and stop. The narration cache is "
                         "keyed on the words and the voice alone, so it "
                         "survives every change to how things look.")
    a = ap.parse_args()

    began = time.time()
    try:
        doc = S.load(a.script)
        problems = S.validate(doc)
        if problems:
            raise RuntimeError("; ".join(problems[:6]))

        segments = S.segments(doc)
        if a.limit:
            segments = segments[:a.limit]
        work = a.work or os.path.join(HERE, ".work")
        os.makedirs(work, exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)

        preflight(doc, segments)
        narrated = narrate_all(doc, segments, work)
        speech = sum(n["timeline"]["duration"] for n in narrated)
        progress("narrated", len(narrated), len(narrated),
                 minutes=round(speech / 60, 2))

        if a.narrate_only:
            print("DONE " + json.dumps(dict(
                out="(narration only)", shots=0,
                minutes=round(speech / 60, 2), bytes=0,
                hours=round((time.time() - began) / 3600, 3),
                quality=a.quality)), flush=True)
            return

        notation = write_notation(doc, narrated, work)
        shots = render_shots(doc, narrated, work, a.quality, a.width, a.height,
                             notation)
        assemble(shots, a.out, work, doc.get("music"))

        hours = (time.time() - began) / 3600
        print("DONE " + json.dumps(dict(
            out=a.out, shots=len(shots), minutes=round(speech / 60, 2),
            bytes=os.path.getsize(a.out), hours=round(hours, 3),
            quality=a.quality)), flush=True)
    except Exception as e:
        print(f"FAILED {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
