"""The score: a cue per stretch of story, generated, then laid end to end
to the film's own timings with crossfades.

    .ttsvenv/bin/python -m cartoon.score --film film.json --out music.wav

Runs under `.ttsvenv` (torch, transformers) with MusicGen-medium, locally.
It is a heavy model on this 36 GB Mac: run it on its own, never while a
render or another model is running (see the 2026-09-26 panic), and the
model is dropped as soon as the cues are written.

Each cue is generated a little longer than it is needed and trimmed, and
cues are cached by prompt and length, so re-timing the film re-generates
only what moved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import numpy as np

SR_OUT = 48000

STYLE = ("animated feature film score, orchestral, warm, delicate, "
         "recorded in a small hall, no vocals, no drums")

# (start beat predicate, mood prompt). A cue runs from the first beat that
# matches to the next cue's start.
CUES = [
    ("scene:petersburg:night", "a hushed snowy night, celesta and harp twinkle over soft sustained strings, "
                               "a little mystery, something magical arriving, 6/8"),
    ("scene:study:night", "a quiet candlelit study late at night, gentle pizzicato strings and a curious clarinet, "
                          "playful and tender, sparse"),
    ("vision:basel", "wonder, shimmering harp glissandi and celesta, warm strings swelling and settling on a "
                     "radiant major chord"),
    ("after:vision:basel", "light comic chamber music, bassoon and pizzicato, a friendly conversation, sparse"),
    ("vision:harmonic", "comic rising tension, strings climbing a chromatic staircase faster and faster, "
                        "a muted trumpet squeal, playful alarm"),
    ("after:vision:harmonic", "a gentle playful waltz for oboe, flute and pizzicato strings, warm, clean, sparse"),
    ("vision:product", "a magical revelation, full strings and french horns rising, glockenspiel sparkles, "
                       "triumphant but gentle"),
    ("after:vision:product", "excited and warm, strings and flute, a sense of discovery, light"),
    ("vision:wheel", "a swirling dreamy waltz, harp and celesta going round and round, strings rising "
                     "halfway and pausing on a question"),
    ("after:vision:wheel", "gentle and thoughtful, solo piano with soft strings, quiet"),
    ("vision:nothing", "near silence, a single sustained high violin note, then a soft bell, ethereal and still"),
    ("after:vision:nothing", "tender and moving, solo cello and piano, slow, heartfelt, the most beautiful moment"),
    ("do:ship_toots", "bittersweet farewell, woodwinds and strings, whimsical and warm, a little sad"),
    ("scene:study:morning", "a bright gentle morning, solo flute and harp, sunlight, content"),
    ("scene:petersburg:dawn", "a joyful soaring finale, full orchestra, strings and horns, warm triumphant theme, "
                              "ending on a big bright chord"),
]


# some cues want to sit lower than the rest
GAIN = {"near silence": 0.35, "a hushed snowy night": 0.8}


def _gain(prompt):
    return next((g for k, g in GAIN.items() if prompt.startswith(k)), 1.0)


def cue_times(film):
    """(start, end, prompt) per cue, from the beats."""
    beats = film["beats"]
    starts = []
    for pred, prompt in CUES:
        kind, *rest = pred.split(":")
        t = None
        for i, b in enumerate(beats):
            if kind == "scene" and b["scene"] == rest[0] and b["time"] == rest[1]:
                t = b["start"]
            elif kind == "vision" and b["do"] == "vision" and b["vision"] == rest[0]:
                t = b["start"]
            elif kind == "after" and b["do"] == "vision" and b["vision"] == rest[1] and i + 1 < len(beats):
                t = beats[i + 1]["start"]
            elif kind == "do" and b["do"] == rest[0]:
                t = b["start"]
            if t is not None:
                break
        if t is not None:
            starts.append((t, prompt))
    starts.sort()
    out = []
    for i, (t, p) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else film["duration"] + 2.0
        out.append((t, end, p))
    return out


def generate(cues, cache):
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration
    os.makedirs(cache, exist_ok=True)
    todo = []
    for t0, t1, p in cues:
        length = min(29.0, (t1 - t0) + 2.0)
        key = hashlib.sha256(f"{p}|{length:.1f}".encode()).hexdigest()[:12]
        path = os.path.join(cache, f"cue-{key}.npy")
        todo.append((t0, t1, p, length, path))
    need = [x for x in todo if not os.path.exists(x[4])]
    if need:
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        proc = AutoProcessor.from_pretrained("facebook/musicgen-medium")
        model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-medium",
                                                                 torch_dtype=torch.float32).to(dev)
        sr = model.config.audio_encoder.sampling_rate
        fr = model.config.audio_encoder.frame_rate
        for t0, t1, p, length, path in need:
            inputs = proc(text=[f"{p}. {STYLE}"], padding=True, return_tensors="pt").to(dev)
            with torch.no_grad():
                audio = model.generate(**inputs, do_sample=True, guidance_scale=3.5,
                                       max_new_tokens=int(length * fr) + 4)
            a = audio[0, 0].detach().cpu().float().numpy()
            np.save(path, np.stack([a, np.full_like(a, sr)])[:1].ravel() if False else a)
            with open(path + ".sr", "w") as fh:
                fh.write(str(sr))
            print(f"cue {t0:7.2f}-{t1:7.2f} ({length:4.1f}s): {p[:60]}", flush=True)
        del model
        if dev == "mps":
            torch.mps.empty_cache()
    return todo


def assemble(todo, duration, out):
    import soundfile as sf
    n = int((duration + 3) * SR_OUT)
    bus = np.zeros(n)
    fade = int(1.2 * SR_OUT)
    for t0, t1, p, length, path in todo:
        a = np.load(path)
        sr = int(open(path + ".sr").read())
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * SR_OUT / sr)), np.arange(len(a)), a)
        a = a / (np.abs(a).max() + 1e-9) * 0.8 * _gain(p)
        need = int((t1 - t0) * SR_OUT) + fade
        if len(a) < need:
            # loop the cue's middle with a crossfade until it is long enough
            loop = a[int(0.1 * len(a)):]
            while len(a) < need:
                x = min(fade, len(loop), len(a))
                ramp = np.linspace(0, 1, x)
                a = np.concatenate([a[:-x], a[-x:] * (1 - ramp) + loop[:x] * ramp, loop[x:]])
        a = a[:need]
        env = np.ones(len(a))
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        i = max(0, int(t0 * SR_OUT) - fade // 2)
        j = min(n, i + len(a))
        bus[i:j] += (a * env)[: j - i]
    sf.write(out, bus / (np.abs(bus).max() + 1e-9) * 0.85, SR_OUT, subtype="PCM_24")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    film = json.load(open(a.film))
    cues = cue_times(film)
    todo = generate(cues, os.path.join(os.path.dirname(os.path.abspath(a.out)), "cues"))
    print(assemble(todo, film["duration"], a.out))


if __name__ == "__main__":
    main()
