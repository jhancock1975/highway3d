"""Speak a script, and say exactly when each phoneme happened.

Runs under `.ttsvenv` (Kokoro, torch, soundfile), never under Blender:

    .ttsvenv/bin/python -m lectern.narrate --text "..." --out work/seg000

writes `seg000.wav` and `seg000.json`. The JSON is the whole point -- the
audio is only half of what narration produces, and the other half is the
timeline the mouth is animated from.

Timing runs from the speech, not the other way round. Nothing downstream
guesses how long a line takes; it is measured here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lectern import voice as V  # noqa: E402


def _blend(pipeline, spec):
    packs = [(pipeline.load_single_voice(name), w) for name, w in spec]
    total = sum(w for _, w in packs)
    return sum(pack.float() * (w / total) for pack, w in packs)


def speak(text: str, preset: str = "einstein", speed: float = 0.94,
          lang: str = "b") -> dict:
    """Synthesise one segment and return audio plus its phoneme timeline."""
    from kokoro import KPipeline

    cfg = V.PRESETS[preset]
    pipe = KPipeline(lang_code=lang)

    # 1. phonemise, 2. bend into the accent, 3. only then synthesise
    plain = list(pipe(text, voice=cfg["blend"][0][0], speed=speed))
    phonemes = " ".join(r.phonemes for r in plain)
    words = []
    for r in plain:
        for t in (r.tokens or []):
            if t.start_ts is None or t.end_ts is None:
                continue
            words.append(dict(text=t.text, phonemes=t.phonemes or "",
                              start=float(t.start_ts), end=float(t.end_ts)))

    accented = V.germanise(phonemes, cfg["strength"], V.PROTECTED)
    # Per word too: the audio is accented, so a viseme track built from the
    # plain phonemes would animate sounds that are no longer being made.
    for w in words:
        w["phonemes"] = V.germanise(w["phonemes"], cfg["strength"], V.PROTECTED)
    voice_vec = _blend(pipe, cfg["blend"])
    chunks = [r.audio.numpy() for r in
              pipe.generate_from_tokens(accented, voice=voice_vec, speed=speed)]
    audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    return dict(audio=audio, sr=24000, words=words,
                phonemes=phonemes, accented=accented, cfg=cfg)


def shape(audio, sr, cfg, work: str, delivery=None) -> tuple:
    """Pitch, formants, hoarseness. Returns audio and the timing scale factor."""
    d = delivery or dict(pitch=1.0, speed=1.0, level=1.0)
    raw = os.path.join(work, "_raw.wav")
    shifted = os.path.join(work, "_pitch.wav")
    V.save(audio, sr, raw)
    V.pitch(raw, shifted, cfg["pitch"] * d["pitch"])
    a, sr2 = V.load(shifted)
    a = V.formants(a, sr2, cfg["formants"])
    a = V.hoarsen(a, sr2, cfg["hoarse"], cfg.get("breath", 0.10))
    a = V.tilt(a, sr2, presence=cfg["presence"], body=cfg["body"])
    # Level last, and after the normalising stages rather than before them.
    # Both hoarsen and tilt finish on a peak normalise, so a segment meant to
    # be an aside came back out at exactly the same loudness as the line it
    # was an aside to -- the dynamics were being flattened at the very end of
    # the chain, which no amount of pitch variation upstream can recover.
    a = a * d["level"]
    # WSOLA lands within a few ms rather than exactly; the timeline is scaled
    # by what actually came out so the mouth cannot drift over a long segment.
    scale = (len(a) / sr2) / (len(audio) / sr)
    for p in (raw, shifted):
        if os.path.exists(p):
            os.remove(p)
    return a, sr2, scale


def narrate(text: str, out_stem: str, preset: str = "einstein",
            speed: float = 0.94, delivery: str = "plain") -> dict:
    work = os.path.dirname(os.path.abspath(out_stem)) or "."
    os.makedirs(work, exist_ok=True)

    d = V.delivery(delivery, text)
    spoken = speak(text, preset, speed * d["speed"])
    audio, sr, scale = shape(spoken["audio"], spoken["sr"], spoken["cfg"],
                             work, d)
    V.save(audio, sr, out_stem + ".wav")

    timeline = dict(
        text=text,
        duration=len(audio) / sr,
        preset=preset,
        delivery=delivery,
        phonemes=spoken["phonemes"],
        accented=spoken["accented"],
        words=[dict(w, start=w["start"] * scale, end=w["end"] * scale)
               for w in spoken["words"]],
    )
    with open(out_stem + ".json", "w") as fh:
        json.dump(timeline, fh, indent=1)
    return timeline


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True, help="path stem, no extension")
    ap.add_argument("--preset", default="einstein")
    ap.add_argument("--speed", type=float, default=0.94)
    ap.add_argument("--delivery", default="plain",
                    choices=tuple(V.DELIVERIES),
                    help="how the line is said, not what is said")
    a = ap.parse_args()
    t = narrate(a.text, a.out, a.preset, a.speed, a.delivery)
    print(json.dumps(dict(duration=round(t["duration"], 3),
                          words=len(t["words"]), out=a.out + ".wav")))


if __name__ == "__main__":
    main()
