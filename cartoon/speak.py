"""Say every line of a cartoon, and when each phoneme of it happened.

Runs under `.ttsvenv` (Kokoro, torch):

    .ttsvenv/bin/python -m cartoon.speak --script scripts/x.yaml --work .work/cartoon/x

For each line, `voice/<id>.wav` and `voice/<id>.json`; the JSON is the
timeline the mouth is animated from, measured, never guessed. Lines already
spoken are not spoken again: the id hashes the words, the voice and the mood.

The order inside a line is lectern's and the order is the point: phonemise,
bend into the accent, then synthesise, so the timeline driving the lips is
the accented one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from cartoon import moods, script, voices  # noqa: E402
from lectern import voice as V  # noqa: E402

_PIPES = {}

# Lighter than lectern's germanise, and chosen by what Whisper could still
# understand rather than by how German it sounds. With the full rule set
# Euler's key words went: "minus one" came back as "minus fun", "growth" as
# "gross", "squared" as "shkvet", and the closing line's "wet dog" as "vet
# doc". Turning the short a continental cost as much again ("that" heard as
# "zart", "bad" as "bard", "and" as "on"). So only "the" becomes "ze", which
# carries most of the accent on its own, and w turns to v only in words where
# nothing is lost by it.
SWISS = [
    (r"ð", "z"),              # the -> ze, that -> zat
]
SWISS_V = [(r"^w", "v")]      # very vell -- word-initial only
KEEP_W = {"one", "once", "wet", "we", "what", "whole", "who", "without",
          "where", "when", "which", "squares", "squared", "quarter", "way"}


def swiss(phonemes: str, words_plain: list[str] | None = None) -> str:
    out = []
    for i, w in enumerate(phonemes.split(" ")):
        plain = (words_plain[i] if words_plain and i < len(words_plain) else "").lower()
        plain = re.sub(r"[^a-z]", "", plain)
        if plain in voices.PROTECTED:
            out.append(w)
            continue
        for pat, rep in SWISS:
            w = re.sub(pat, rep, w)
        if plain and plain not in KEEP_W:
            for pat, rep in SWISS_V:
                w = re.sub(pat, rep, w)
        out.append(w)
    return " ".join(out)


def _pipe(lang):
    from kokoro import KPipeline
    if lang not in _PIPES:
        _PIPES[lang] = KPipeline(lang_code=lang)
    return _PIPES[lang]


def _blend(pipe, spec):
    packs = [(pipe.load_single_voice(n), w) for n, w in spec]
    total = sum(w for _, w in packs)
    return sum(p.float() * (w / total) for p, w in packs)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def say(text: str, preset: str, mood: str = "neutral", delivery: str | None = None) -> dict:
    """One line: audio at 24 kHz, the words with their phonemes and times."""
    cfg = voices.PRESETS[preset]
    m = moods.voice(mood, text)
    if delivery == "aside":
        m["level"] *= 0.8
        m["speed"] *= 0.96
    pipe = _pipe(cfg["lang"])
    vec = _blend(pipe, cfg["blend"])
    speed = cfg["speed"] * m["speed"]
    sr = 24000
    audio, words, t0 = [], [], 0.0
    for si, sent in enumerate(_sentences(text)):
        plain = list(pipe(sent, voice=cfg["blend"][0][0], speed=speed))
        phon = " ".join(r.phonemes for r in plain)
        ws = []
        for r in plain:
            for t in (r.tokens or []):
                if t.start_ts is None or t.end_ts is None:
                    continue
                ws.append(dict(text=t.text, phonemes=t.phonemes or "",
                               start=float(t.start_ts), end=float(t.end_ts)))
        if cfg["accent"] > 0:
            # rebuilt token by token, so each word's accent can see the word
            phon = ""
            for r in plain:
                for t in (r.tokens or []):
                    phon += swiss(t.phonemes or "", [t.text]) + (" " if t.whitespace else "")
            for w in ws:
                w["phonemes"] = swiss(w["phonemes"], [w["text"]])
            chunks = [r.audio.numpy() for r in pipe.generate_from_tokens(phon.strip(), voice=vec, speed=speed)]
        else:
            chunks = [r.audio.numpy() for r in pipe(sent, voice=vec, speed=speed)]
        a = np.concatenate(chunks)
        # Kokoro's timestamps come from the plain pass; the accented pass
        # can run a little longer or shorter, so stretch them to fit.
        plain_len = sum(len(r.audio) for r in plain) / sr
        k = (len(a) / sr) / plain_len if plain_len > 0 else 1.0
        for w in ws:
            words.append(dict(w, start=t0 + w["start"] * k, end=t0 + w["end"] * k))
        audio.append(a)
        t0 += len(a) / sr
        # a breath between sentences; longer after an ellipsis
        gap = 0.32 if sent.endswith("...") else 0.16
        audio.append(np.zeros(int(gap * sr), dtype=a.dtype))
        t0 += gap
    return dict(audio=np.concatenate(audio), sr=sr, words=words, cfg=cfg, mood=m)


def shape(audio, sr, cfg, m, work):
    """Pitch, formants, roughness, level. Returns audio, rate, time scale."""
    raw = os.path.join(work, "_raw.wav")
    shifted = os.path.join(work, "_pitch.wav")
    V.save(audio, sr, raw)
    V.pitch(raw, shifted, cfg["pitch"] * m["pitch"])
    a, sr2 = V.load(shifted)
    a = V.formants(a, sr2, cfg["formants"])
    a = V.hoarsen(a, sr2, cfg["hoarse"], cfg["breath"])
    a = V.tilt(a, sr2, presence=cfg["presence"], body=cfg["body"])
    peak = np.abs(a).max()
    if peak > 0:
        a = a / peak * 0.9
    a = a * m["level"]
    scale = (len(a) / sr2) / (len(audio) / sr)
    for p in (raw, shifted):
        if os.path.exists(p):
            os.remove(p)
    return a, sr2, scale


def speak_line(beat: dict, out_dir: str) -> dict:
    stem = os.path.join(out_dir, beat["id"])
    if os.path.exists(stem + ".json") and os.path.exists(stem + ".wav"):
        with open(stem + ".json") as fh:
            return json.load(fh)
    s = say(beat["text"], beat["voice"], beat["mood"], beat.get("delivery"))
    a, sr, k = shape(s["audio"], s["sr"], s["cfg"], s["mood"], out_dir)
    V.save(a, sr, stem + ".wav")
    tl = dict(id=beat["id"], who=beat["who"], text=beat["text"], voice=beat["voice"],
              mood=beat["mood"], duration=len(a) / sr,
              words=[dict(w, start=w["start"] * k, end=w["end"] * k) for w in s["words"]])
    with open(stem + ".json", "w") as fh:
        json.dump(tl, fh, indent=1)
    return tl


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--only", help="speak only beats whose id starts with this")
    a = ap.parse_args()
    doc = script.load(a.script)
    out = os.path.join(a.work, "voice")
    os.makedirs(out, exist_ok=True)
    total = 0.0
    for b in script.beats(doc):
        if not b["who"] or (a.only and not b["id"].startswith(a.only)):
            continue
        tl = speak_line(b, out)
        total += tl["duration"]
        print(f"{b['id']} {b['who']:9s} {tl['duration']:5.2f}s  {b['text'][:60]}", flush=True)
    print(f"total speech {total:.1f}s")


if __name__ == "__main__":
    main()
