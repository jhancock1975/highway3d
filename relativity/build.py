"""Assemble the lecture: narration, timing, frames, audio, video.

    python3 build.py --out lecture.mp4 [--limit 3] [--fps 30]

Timing is driven by the speech, not the other way round: each segment is
synthesised first, its real duration measured, and the picture laid out to fit.
Nothing has to be guessed or nudged into sync afterwards.

Panels are cached per quantised phase step, so a forty-thousand-frame render
draws a few thousand panels rather than one per frame.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import character
import content
import visuals

W, H = 1920, 1080
BG_TOP = (14, 18, 26)
BG_BOT = (24, 30, 42)
INK = (238, 243, 250)
DIM = (140, 156, 182)
ACCENT = (120, 190, 255)

SEG_PAUSE = 1.00          # silence between segments
CHAPTER_HOLD = 2.6        # extra time on the first segment of a chapter
PHASE_STEPS = 20          # panel cache resolution


# ------------------------------------------------------------------ narration

def synth_narration(segments, voice: str, work: str, speed: float) -> list:
    """One wav per segment; returns durations in seconds."""
    script = os.path.join(work, "_say.py")
    with open(script, "w") as fh:
        fh.write(
            "import sys, json, numpy as np, soundfile as sf\n"
            "from kokoro import KPipeline\n"
            "voice, speed, spec = sys.argv[1], float(sys.argv[2]), sys.argv[3]\n"
            "jobs = json.load(open(spec))\n"
            "pipe = KPipeline(lang_code='b' if voice[0]=='b' else 'a')\n"
            "out = []\n"
            "for path, text in jobs:\n"
            "    ch = [c[2] for c in pipe(text, voice=voice, speed=speed)]\n"
            "    a = np.concatenate(ch) if len(ch) > 1 else ch[0]\n"
            "    sf.write(path, a, 24000)\n"
            "    out.append(len(a)/24000)\n"
            "print(json.dumps(out))\n")
    jobs = [[os.path.join(work, f"vo{ i :03d}.wav"), s["text"]]
            for i, s in enumerate(segments)]
    spec = os.path.join(work, "_jobs.json")
    with open(spec, "w") as fh:
        json.dump(jobs, fh)
    venv = os.path.join(os.path.dirname(HERE), ".ttsvenv")
    env = dict(os.environ, VIRTUAL_ENV=venv)
    r = subprocess.run([os.path.join(venv, "bin", "python"), script,
                        voice, str(speed), spec],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError("narration failed:\n" + r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def concat_narration(segments, starts, durations, work, total) -> str:
    """Lay each segment's speech at its start time on one timeline."""
    sr = 24000
    track = np.zeros(int(total * sr) + sr)
    for i, (st, dur) in enumerate(zip(starts, durations)):
        p = os.path.join(work, f"vo{i:03d}.wav")
        with wave.open(p) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), "<i2")
        a = a.astype(np.float64) / 32768.0
        at = int(st * sr)
        end = min(len(track), at + len(a))
        track[at:end] += a[:end - at]
    out = os.path.join(work, "narration.wav")
    pcm = (np.clip(track, -1, 1) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return out


def lipsync(narration_path: str, fps: int, n_frames: int) -> np.ndarray:
    """Mouth openness per frame from the speech envelope."""
    with wave.open(narration_path) as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), "<i2")
    a = np.abs(a.astype(np.float64) / 32768.0)
    win = max(1, sr // fps)
    n = min(n_frames, len(a) // win)
    env = a[:n * win].reshape(n, win).mean(axis=1)
    if env.max() > 0:
        env = env / np.percentile(env, 97)
    env = np.clip(env * 1.45, 0.0, 1.0)
    # smooth a little so the jaw does not chatter between frames
    k = np.array([0.25, 0.5, 0.25])
    env = np.convolve(env, k, mode="same")
    out = np.zeros(n_frames)
    out[:len(env)] = env
    return out


# --------------------------------------------------------------------- canvas

def background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t)
                          for i in range(3)))
    d.line([(0, H - 96), (W, H - 96)], fill=(38, 46, 62), width=2)
    return img


def chapter_bar(base: Image.Image, title: str, frac: float) -> None:
    d = ImageDraw.Draw(base)
    d.text((56, H - 74), title, font=visuals.font(34), fill=DIM)
    d.rectangle([0, H - 6, int(W * frac), H], fill=ACCENT)


def build(args) -> dict:
    segments = content.all_segments()
    if args.limit:
        segments = segments[:args.limit]

    work = args.work or os.path.join(HERE, ".work")
    os.makedirs(work, exist_ok=True)
    print(f"[1/5] narrating {len(segments)} segments", flush=True)
    durations = synth_narration(segments, args.voice, work, args.speed)

    starts, t = [], 0.4
    for i, seg in enumerate(segments):
        if seg["first_in_chapter"] and i > 0:
            t += CHAPTER_HOLD
        starts.append(t)
        t += durations[i] + SEG_PAUSE
    total = t + 1.6
    n_frames = int(total * args.fps)
    print(f"      speech {sum(durations)/60:.1f} min, "
          f"total {total/60:.1f} min, {n_frames} frames", flush=True)

    narration = concat_narration(segments, starts, durations, work, total)
    mouth = lipsync(narration, args.fps, n_frames)

    print("[2/5] caching panels", flush=True)
    panel_cache = {}
    for i, seg in enumerate(segments):
        for k in range(PHASE_STEPS):
            p = visuals.render_panel(seg["visual"], k / (PHASE_STEPS - 1))
            panel_cache[(i, k)] = p
        if (i + 1) % 10 == 0:
            print(f"      {i+1}/{len(segments)}", flush=True)

    print("[3/5] pre-rendering mouth shapes", flush=True)
    heads = character.mouth_frames(levels=10, scale=1.16)

    print("[4/5] building audio", flush=True)
    music = os.path.join(work, "music.wav")
    subprocess.run([sys.executable,
                    os.path.join(os.path.dirname(HERE), "highway3d", "music.py"),
                    "--duration", str(total), "--out", music,
                    "--mood", "night"], check=True, capture_output=True)
    mix = os.path.join(work, "mix.wav")
    _mix(narration, music, mix, total)

    print("[5/5] compositing and encoding", flush=True)
    # frames go straight down a pipe: 41k PNGs would be ~16 GB of scratch
    enc = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-framerate", str(args.fps), "-i", "pipe:0",
        "-i", mix,
        "-c:v", "libx264", "-crf", "19", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest", args.out],
        stdin=subprocess.PIPE)
    base = background()
    seg_of = np.zeros(n_frames, dtype=int)
    phase_of = np.zeros(n_frames)
    for i, (st, dur) in enumerate(zip(starts, durations)):
        a = int(st * args.fps)
        b = int((st + dur + SEG_PAUSE) * args.fps)
        b = min(b, n_frames)
        seg_of[a:b] = i
        if b > a:
            phase_of[a:b] = np.linspace(0, 1, b - a)
    if n_frames:
        seg_of[int((starts[-1] + durations[-1] + SEG_PAUSE) * args.fps):] = \
            len(segments) - 1

    head_x, head_y = 24, H - int(character.H * 1.16) - 96
    for f in range(n_frames):
        img = base.copy()
        i = int(seg_of[f])
        k = int(round(phase_of[f] * (PHASE_STEPS - 1)))
        img.paste(panel_cache[(i, k)], (735, 118), panel_cache[(i, k)])
        h = heads[int(round(mouth[f] * (len(heads) - 1)))]
        img.paste(h, (head_x, head_y), h)
        chapter_bar(img, segments[i]["chapter_title"], (f + 1) / n_frames)
        enc.stdin.write(img.tobytes())
        if (f + 1) % 1800 == 0:
            print(f"      {f+1}/{n_frames} "
                  f"({100.0*(f+1)/n_frames:.0f}%)", flush=True)

    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("encoding failed")

    return dict(ok=True, out=args.out, minutes=round(total / 60, 2),
                segments=len(segments), frames=n_frames,
                bytes=os.path.getsize(args.out))


def _mix(narration: str, music: str, out: str, total: float) -> None:
    sr = 48000
    n = int(total * sr)

    def load(p):
        with wave.open(p) as w:
            rate = w.getframerate()
            ch = w.getnchannels()
            a = np.frombuffer(w.readframes(w.getnframes()), "<i2")
        a = a.astype(np.float64) / 32768.0
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        if rate != sr:
            a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * sr / rate)),
                          np.arange(len(a)), a)
        return np.resize(a, n) if len(a) < n else a[:n]

    vo = load(narration)
    mu = load(music)
    # duck the score hard under speech: this is a lecture, not a trailer
    env = np.abs(vo)
    k = int(sr * 0.25)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    env /= (env.max() + 1e-9)
    duck = 1.0 - 0.82 * np.clip(env * 3.0, 0, 1)
    mix = vo * 2.5 + mu * 0.26 * duck
    peak = np.abs(mix).max()
    mix = mix / peak * 0.92 if peak > 0 else mix
    st = np.empty(n * 2)
    st[0::2] = mix
    st[1::2] = mix
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(st, -1, 1) * 32767).astype("<i2").tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--voice", default="bm_george")
    ap.add_argument("--speed", type=float, default=0.94)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--work", default="")
    a = ap.parse_args()
    print(json.dumps(build(a)))


if __name__ == "__main__":
    main()
