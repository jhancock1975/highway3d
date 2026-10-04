"""The score: a cue per stretch of story, generated, then laid end to end
to the film's own timings with crossfades.

    lectern/.musicvenv/bin/python -m cartoon.score --film film.json --out music.wav

Generated locally by ACE-Step 1.5 (MIT; its authors trained it on licensed
and public-domain music and say outright that what it makes may be used
commercially). It replaced MusicGen, whose weights are CC-BY-NC and whose
output nobody could vouch for. The turbo model, as ACE-Step itself runs on
Macs: the XL one holds 20 GB of weights in full precision, and turbo alone
already peaked at a 35 GB footprint on this 36 GB machine with a quarter of
memory left free. Set ACE_DIT=acestep-v15-xl-sft on a bigger machine.
Each cue is made at its full length --
up to ten minutes, where MusicGen stopped at thirty seconds and long
stretches had to be looped -- in stereo, from a seed fixed by its prompt, so
the same film always gets the same score.

It is heavy on this 36 GB Mac: run it on its own, never while a render or
another model is running (ACE-Step was one of the four in the 2026-09-26
panic), and the models are dropped as soon as the cues are written. Cues
are cached by model, prompt, length and seed, so re-timing the film
re-generates only what moved.
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


ACE_HOME = os.environ.get("ACE_HOME", os.path.expanduser("~/.cache/ace-step"))
DIT = os.environ.get("ACE_DIT", "acestep-v15-turbo")
LM = "acestep-5Hz-lm-1.7B"
TURBO = "turbo" in DIT       # distilled: 8 steps, guidance baked in, timesteps shifted


def _seed(prompt):
    return int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16) % 2_000_000_000


def generate_plan(cues, cache):
    """(start, end, prompt, length, cache path) per cue."""
    os.makedirs(cache, exist_ok=True)
    todo = []
    for t0, t1, p in cues:
        # made a little long for the crossfades, and never under ACE-Step's ten seconds
        length = round(max(10.0, min(600.0, (t1 - t0) + 2.5)), 1)
        key = hashlib.sha256(f"{DIT}|{LM}|{p}|{length:.1f}|{_seed(p)}".encode()).hexdigest()[:12]
        todo.append((t0, t1, p, length, os.path.join(cache, f"ace-{key}.npy")))
    return todo


def generate(cues, cache):
    todo = generate_plan(cues, cache)
    need = [x for x in todo if not os.path.exists(x[4])]
    if not need:
        return todo
    import torch
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler
    if torch.cuda.is_available():
        dev = "cuda"
    elif torch.backends.mps.is_available():
        dev = "mps"
    else:
        dev = "cpu"
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=ACE_HOME, config_path=DIT, device=dev)
    if not ok:
        raise RuntimeError(f"ACE-Step DiT: {msg}")
    # Decoding a long cue in the default 512-frame windows took this Mac from
    # 74% of memory free to 3% in under five seconds; the smallest window
    # the decoder allows, and no MLX buffer cache, keep the peak down.
    dit.mlx_vae_chunk_size = 192
    try:
        import mlx.core as mx
        mx.set_cache_limit(0)
    except (ImportError, AttributeError):
        mx = None
    lm = LLMHandler()
    msg, ok = lm.initialize(checkpoint_dir=os.path.join(ACE_HOME, "checkpoints"), lm_model_path=LM,
                            backend="mlx" if dev == "mps" else "pt", device=dev)
    if not ok:
        raise RuntimeError(f"ACE-Step LM: {msg}")
    for t0, t1, p, length, path in need:
        params = GenerationParams(caption=f"{p}. {STYLE}", lyrics="[Instrumental]", instrumental=True,
                                  duration=length, inference_steps=8 if TURBO else 50, guidance_scale=7.0,
                                  shift=3.0 if TURBO else 1.0, seed=_seed(p))
        config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[_seed(p)], audio_format="wav")
        r = generate_music(dit, lm, params, config, save_dir=os.path.join(cache, "ace-out"))
        if not r.success:
            raise RuntimeError(f"ACE-Step failed on {p[:40]!r}: {r.error}")
        a = r.audios[0]["tensor"].detach().cpu().float().numpy()        # (channels, samples)
        np.save(path, a.T if a.ndim == 2 else a)
        with open(path + ".sr", "w") as fh:
            fh.write(str(int(r.audios[0]["sample_rate"])))
        print(f"cue {t0:7.2f}-{t1:7.2f} ({length:5.1f}s): {p[:60]}", flush=True)
        if mx is not None:
            mx.clear_cache()
    del dit, lm
    if dev == "mps":
        torch.mps.empty_cache()
    elif dev == "cuda":
        torch.cuda.empty_cache()
    return todo


def _stereo(a):
    a = np.asarray(a, float)
    return np.stack([a, a], 1) if a.ndim == 1 else a[:, :2]


def assemble(todo, duration, out):
    import soundfile as sf
    n = int((duration + 3) * SR_OUT)
    bus = np.zeros((n, 2))
    fade = int(1.2 * SR_OUT)
    for t0, t1, p, length, path in todo:
        a = _stereo(np.load(path))
        sr = int(open(path + ".sr").read())
        if sr != SR_OUT:
            m = int(len(a) * SR_OUT / sr)
            a = np.stack([np.interp(np.linspace(0, len(a) - 1, m), np.arange(len(a)), a[:, c]) for c in (0, 1)], 1)
        # matched by loudness rather than by peak, so a quiet cue next to a
        # loud one is quiet because it was asked to be, not by accident
        rms = np.sqrt(np.mean(a ** 2)) + 1e-9
        a = a * (0.12 / rms) * _gain(p)
        a = a / max(1.0, np.abs(a).max() / 0.9)
        need = int((t1 - t0) * SR_OUT) + fade
        if len(a) < need:
            # only if the model came up short: loop the cue's middle with a crossfade
            loop = a[int(0.1 * len(a)):]
            while len(a) < need:
                x = min(fade, len(loop), len(a))
                ramp = np.linspace(0, 1, x)[:, None]
                a = np.concatenate([a[:-x], a[-x:] * (1 - ramp) + loop[:x] * ramp, loop[x:]])
        a = a[:need]
        env = np.ones(len(a))
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        i = max(0, int(t0 * SR_OUT) - fade // 2)
        j = min(n, i + len(a))
        bus[i:j] += (a * env[:, None])[: j - i]
    sf.write(out, bus / (np.abs(bus).max() + 1e-9) * 0.85, SR_OUT, subtype="PCM_24")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", type=int, help="generate just this cue (used internally)")
    a = ap.parse_args()
    film = json.load(open(a.film))
    cues = cue_times(film)
    cache = os.path.join(os.path.dirname(os.path.abspath(a.out)), "cues")
    if a.only is not None:
        generate([cues[a.only]], cache)
        return
    # one process per cue, so memory starts clean for each: one process for
    # all of them crept down to 16% free between cues before the decode spike
    import subprocess
    for k, (t0, t1, p, length, path) in enumerate(generate_plan(cues, cache)):
        if not os.path.exists(path):
            subprocess.run([sys.executable, "-m", "cartoon.score", "--film", a.film, "--out", a.out,
                            "--only", str(k)], check=True)
    print(assemble(generate_plan(cues, cache), film["duration"], a.out))


if __name__ == "__main__":
    main()
