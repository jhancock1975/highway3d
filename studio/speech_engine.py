"""Kokoro speech: text in, a wav and every word's timing out.

Runs under .ttsvenv, never the studio's own interpreter:

    .ttsvenv/bin/python studio/speech_engine.py --text "..." --voice af_heart \
        --speed 1 --out /tmp/stem

writes stem.wav and stem.json. Kokoro speaks long text in pieces and times
each word from the start of its own piece, so the lengths of the pieces
before it are added back here. Without that, every caption after the first
piece would come up early.

`einstein` goes through lectern.narrate, which accents the phonemes and
says the whole text in one breath. Kokoro refuses that past 510 phonemes,
about eighty words, and a line break restarted narrate's word times at
zero, so his text is said here in pieces of whole sentences and joined.
Kokoro and soundfile are imported where they are used, so the studio's own
interpreter can import `pieces` to test it.
"""

import argparse
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 24000
# Characters per piece for einstein: well under Kokoro's 510 phonemes once
# the accent has been applied.
PIECE = 240


def pieces(text: str, limit: int = PIECE) -> list[str]:
    """Text in runs said in one breath: whole sentences, under `limit` characters.

    A sentence too long on its own is broken after a comma if there is one
    in reach, and between words otherwise.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?;:])\s+|\s*\n+\s*",
                                             text.strip()) if s.strip()]
    out, run = [], ""
    for s in sentences:
        while len(s) > limit:
            cut = s.rfind(", ", 0, limit)
            cut = cut + 1 if cut > 0 else s.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            if run:
                out.append(run)
                run = ""
            out.append(s[:cut].strip())
            s = s[cut:].strip()
        if run and len(run) + 1 + len(s) > limit:
            out.append(run)
            run = s
        else:
            run = f"{run} {s}".strip()
    if run:
        out.append(run)
    return out


def plain(text: str, voice: str, speed: float):
    from kokoro import KPipeline

    # The voice's first letter is its accent: a for American, b for British.
    pipe = KPipeline(lang_code=voice[0], repo_id="hexgrad/Kokoro-82M")
    chunks, words, offset = [], [], 0.0
    for r in pipe(text, voice=voice, speed=speed):
        audio = r.audio.numpy()
        for t in (r.tokens or []):
            if t.start_ts is not None and t.end_ts is not None:
                words.append(dict(text=t.text, start=offset + float(t.start_ts),
                                  end=offset + float(t.end_ts)))
        chunks.append(audio)
        offset += len(audio) / SR
    return chunks, words, SR


def einstein(text: str, speed: float):
    import soundfile as sf

    sys.path.insert(0, ROOT)
    from lectern import narrate

    chunks, words, offset, rate = [], [], 0.0, SR
    with tempfile.TemporaryDirectory(prefix="studio-einstein-") as tmp:
        for i, piece in enumerate(pieces(text)):
            stem = os.path.join(tmp, f"piece{i:03d}")
            # 0.94 is lectern's own pace for him; `speed` scales it.
            timing = narrate.narrate(piece, stem, "einstein", 0.94 * speed)
            audio, rate = sf.read(stem + ".wav")
            words += [dict(text=w["text"], start=offset + w["start"],
                           end=offset + w["end"]) for w in timing["words"]]
            chunks.append(audio)
            offset += len(audio) / rate
    return chunks, words, rate


def main():
    import numpy as np
    import soundfile as sf

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", required=True, help="path stem, no extension")
    a = ap.parse_args()

    if a.voice == "einstein":
        chunks, words, rate = einstein(a.text, a.speed)
    else:
        chunks, words, rate = plain(a.text, a.voice, a.speed)
    wav = np.concatenate(chunks)
    sf.write(a.out + ".wav", wav, rate)
    with open(a.out + ".json", "w") as fh:
        json.dump(dict(seconds=len(wav) / rate, words=words), fh)
    print(json.dumps(dict(seconds=round(len(wav) / rate, 3), words=len(words))))


if __name__ == "__main__":
    main()
