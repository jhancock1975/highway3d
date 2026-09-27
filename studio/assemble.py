"""Turn a checked edit into one ffmpeg run, as a background job.

    studio/.venv/bin/python -m studio.assemble --plan plan.json --out x.mp4 --job 5a1c

Text is drawn first: every caption the edit needs, in one GIMP session.
Then one ffmpeg command does the rest -- trims, fits, moves on stills,
transitions, overlays, the audio mix with ducking -- so there is a single
encode and no generation loss between steps.

This ffmpeg has no drawtext or subtitles filter, which is why text arrives
as pictures.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from studio import library  # noqa: E402
from studio.errors import last_line  # noqa: E402
from studio.timeline import TRANSITION  # noqa: E402

ZOOM = 0.12            # how far push-in, pull-out and the pans travel
SR = 48000
CAPTION_HEIGHT = 0.14  # of the frame's height
# Seconds of work per second of 1080p30 edit, measured on this Mac (Task 10).
RATE = 1.0


def _fit(fit: str, w: int, h: int) -> str:
    if fit == "contain":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


def _zoom(move: str, frames: int) -> str:
    """zoompan's z, x and y for a move spread over `frames` frames."""
    p = f"(on/{max(frames - 1, 1)})"
    y = "y=ih/2-(ih/zoom/2)"
    if move == "push-in":
        return f"z=1+{ZOOM}*{p}:x=iw/2-(iw/zoom/2):{y}"
    if move == "pull-out":
        return f"z=1+{ZOOM}*(1-{p}):x=iw/2-(iw/zoom/2):{y}"
    span = "(iw-iw/zoom)"
    if move == "pan-left":
        return f"z={1 + ZOOM}:x={span}*(1-{p}):{y}"
    return f"z={1 + ZOOM}:x={span}*{p}:{y}"


def _size(place: str, w: int, h: int, W: int, H: int) -> tuple[int, int]:
    """An overlay's drawn size: full fills the frame, the rest fit inside."""
    k = min(W / w, H / h) if place == "full" else min(1.0, W / w, H / h)
    return max(2, round(w * k) // 2 * 2), max(2, round(h * k) // 2 * 2)


def _place(place: str, w: int, h: int, W: int, H: int) -> tuple[int, int]:
    m = round(0.04 * H)
    cx, cy = (W - w) // 2, (H - h) // 2
    return {"full": (cx, cy), "center": (cx, cy), "top": (cx, m),
            "bottom": (cx, H - h - m), "top-left": (m, m),
            "top-right": (W - w - m, m), "bottom-left": (m, H - h - m),
            "bottom-right": (W - w - m, H - h - m)}[place]


def _sound(level: float) -> str:
    return (f"aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS,volume={level:g}")


def _placed(chain: str, at: float, label: str) -> list[str]:
    """`chain` starting `at` seconds in, after exact silence.

    adelay is the obvious filter, and in a graph that also carries video it
    let a clip's sound start at 0 and dropped the voice from the mix
    altogether. Silence joined on with concat is exact to the sample.
    """
    if at <= 0:
        return [f"{chain}[{label}]"]
    return [f"{chain}[{label}x]",
            f"anullsrc=r={SR}:cl=stereo,atrim=duration={at:.3f},"
            f"aformat=sample_fmts=fltp[{label}s]",
            f"[{label}s][{label}x]concat=n=2:v=0:a=1[{label}]"]


def command(plan: dict, out: str) -> list[str]:
    """The one ffmpeg command that renders `plan` to `out`."""
    W, H, fps, T = plan["width"], plan["height"], plan["fps"], plan["seconds"]
    args = ["ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1"]
    graph: list[str] = []
    count = 0

    def source(path: str, *opts: str) -> int:
        nonlocal count
        args.extend([*opts, "-i", path])
        count += 1
        return count - 1

    mix: list[tuple[str, bool, bool]] = []  # (label, speech, ducked)
    if not plan["audio_only"]:
        tail = f"fps={fps:g},setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS"
        for i, v in enumerate(plan["video"]):
            frames = max(1, round(v["seconds"] * fps))
            if v["kind"] == "image" and v["move"] != "none":
                k = source(v["path"])
                graph.append(f"[{k}:v]{_fit(v['fit'], 2 * W, 2 * H)},"
                             f"zoompan={_zoom(v['move'], frames)}:d={frames}"
                             f":s={W}x{H}:fps={fps:g},{tail}[v{i}]")
            elif v["kind"] == "image":
                k = source(v["path"], "-loop", "1", "-framerate", f"{fps:g}",
                           "-t", f"{v['seconds']:.3f}")
                graph.append(f"[{k}:v]{_fit(v['fit'], W, H)},{tail}[v{i}]")
            else:
                k = source(v["path"], "-ss", f"{v['from_']:.3f}",
                           "-t", f"{v['seconds']:.3f}")
                graph.append(f"[{k}:v]{_fit(v['fit'], W, H)},{tail}[v{i}]")
                if v["sound"] and v["level"] > 0:
                    graph.extend(_placed(f"[{k}:a]{_sound(v['level'])}",
                                         v["start"], f"va{i}"))
                    mix.append((f"va{i}", False, False))

        acc = "v0"
        if plan["video"][0]["transition"] != "cut":
            graph.append(f"[v0]fade=t=in:d={TRANSITION}[v0in]")
            acc = "v0in"
        for i, v in enumerate(plan["video"][1:], 1):
            if v["transition"] == "cut":
                graph.append(f"[{acc}][v{i}]concat=n=2:v=1:a=0[c{i}]")
            else:
                # xfade's "dissolve" is a pixel dither; a dissolve is its "fade".
                kind = "fade" if v["transition"] == "dissolve" else "fadeblack"
                graph.append(f"[{acc}][v{i}]xfade=transition={kind}"
                             f":duration={TRANSITION}:offset={v['start']:.3f}"
                             f"[c{i}]")
            acc = f"c{i}"

        ch = round(H * CAPTION_HEIGHT)
        layers = [(o["path"], o["at"], o["seconds"], o["place"], o["width"],
                   o["height"]) for o in plan["overlays"]]
        layers += [(c["path"], c["at"], c["seconds"], "bottom", W, ch)
                   for c in plan["captions"]]
        for j, (path, at, secs, place, w, h) in enumerate(layers):
            if at >= T:
                continue
            secs = min(secs, T - at)
            k = source(path, "-loop", "1", "-framerate", f"{fps:g}",
                       "-t", f"{secs:.3f}")
            dw, dh = _size(place, w, h, W, H)
            x, y = _place(place, dw, dh, W, H)
            graph.append(f"[{k}:v]scale={dw}:{dh},format=rgba,"
                         f"setpts=PTS-STARTPTS+{at:.3f}/TB[o{j}]")
            graph.append(f"[{acc}][o{j}]overlay=x={x}:y={y}:eof_action=pass"
                         f"[w{j}]")
            acc = f"w{j}"
        graph.append(f"[{acc}]trim=duration={T:.3f},format=yuv420p[vout]")

    for m, a in enumerate(plan["audio"]):
        if a["at"] >= T:
            continue
        length = min(a["seconds"], T - a["at"])
        k = source(a["path"])
        chain = f"[{k}:a]atrim=end={length:.3f},{_sound(a['level'])}"
        if a["fade"] > 0:
            f = min(a["fade"], length / 2)
            chain += (f",afade=t=in:d={f:.3f}"
                      f",afade=t=out:st={length - f:.3f}:d={f:.3f}")
        graph.extend(_placed(chain, a["at"], f"a{m}"))
        mix.append((f"a{m}", a["speech"], a["duck"]))

    speech = [x for x, s, d in mix if s]
    ducked = [x for x, s, d in mix if d and not s]
    final = [x for x, s, d in mix if not s and not d]
    if speech and ducked:
        graph.append("".join(f"[{x}]" for x in speech)
                     + f"amix=inputs={len(speech)}:normalize=0:duration=longest,"
                     # sidechaincompress stops with its shorter input
                     + f"apad=whole_dur={T:.3f},asplit={len(ducked) + 1}"
                     + "".join(f"[sc{i}]" for i in range(len(ducked) + 1)))
        final.append("sc0")
        for i, x in enumerate(ducked, 1):
            graph.append(f"[{x}][sc{i}]sidechaincompress=threshold=0.02"
                         f":ratio=8:attack=20:release=400[dk{i}]")
            final.append(f"dk{i}")
    else:
        final += speech + ducked
    if final:
        graph.append("".join(f"[{x}]" for x in final)
                     + f"amix=inputs={len(final)}:normalize=0:duration=longest,"
                     + f"apad=whole_dur={T:.3f},atrim=end={T:.3f},"
                     + "alimiter=limit=0.95[aout]")
    else:
        k = source(f"anullsrc=r={SR}:cl=stereo", "-f", "lavfi",
                   "-t", f"{T:.3f}")
        graph.append(f"[{k}:a]anull[aout]")

    args += ["-filter_complex", ";".join(graph)]
    if plan["audio_only"]:
        return args + ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
                       "-t", f"{T:.3f}", out]
    return args + ["-map", "[vout]", "-map", "[aout]", "-c:v", "libx264",
                   "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-r", f"{fps:g}", "-c:a", "aac", "-b:a", "192k",
                   "-movflags", "+faststart", "-t", f"{T:.3f}", out]


def estimate(plan: dict) -> float:
    """Seconds this will take, from the speed measured on this Mac."""
    px = plan["width"] * plan["height"] / (1920 * 1080)
    frames = plan["fps"] / 30.0
    draw = 6 + 0.2 * len(plan["captions"]) if plan["captions"] else 0
    return 3 + draw + plan["seconds"] * RATE * (px * frames if not plan["audio_only"] else 0.05)


def _say(stage: str, percent: float) -> None:
    print("PROGRESS " + json.dumps(dict(stage=stage, percent=round(percent))),
          flush=True)


def run(plan: dict, out: str) -> dict:
    """Draw the text, run ffmpeg, and report progress on stdout."""
    began = time.time()
    if plan["captions"]:
        from studio import images
        _say("drawing captions", 0)
        tmp = tempfile.mkdtemp(prefix="studio-captions-")
        jobs = []
        for i, c in enumerate(plan["captions"]):
            c["path"] = os.path.join(tmp, f"caption-{i:03d}.png")
            jobs.append(dict(kind="caption", out=c["path"], text=c["text"],
                             width=plan["width"],
                             height=round(plan["height"] * CAPTION_HEIGHT)))
        images.draw(jobs)
    _say("encoding", 0)
    p = subprocess.Popen(command(plan, out), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    shown = -5.0
    for line in p.stdout:
        if line.startswith("out_time_us="):
            try:
                done = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                continue
            percent = min(99.0, 100.0 * done / max(plan["seconds"], 0.001))
            if percent - shown >= 5:
                _say("encoding", percent)
                shown = percent
    err = p.stderr.read()
    p.wait()
    if p.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("ffmpeg stopped: " + last_line(err))
    return dict(out=out, seconds=library.probe(out)["seconds"],
                bytes=os.path.getsize(out), took=round(time.time() - began, 1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--job", default="")
    a = ap.parse_args()
    try:
        with open(a.plan) as fh:
            plan = json.load(fh)
        print("DONE " + json.dumps(run(plan, a.out)), flush=True)
    except Exception as e:
        print(f"FAILED {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
