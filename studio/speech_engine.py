"""Plain Kokoro speech: text in, a wav and every word's timing out.

Runs under .ttsvenv, never the studio's own interpreter:

    .ttsvenv/bin/python studio/speech_engine.py --text "..." --voice af_heart \
        --speed 1 --out /tmp/stem

writes stem.wav and stem.json. Kokoro speaks long text in pieces and times
each word from the start of its own piece, so the lengths of the pieces
before it are added back here. Without that, every caption after the first
piece would come up early.
"""

import argparse
import json

import numpy as np
import soundfile as sf
from kokoro import KPipeline

SR = 24000


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", required=True, help="path stem, no extension")
    a = ap.parse_args()

    # The voice's first letter is its accent: a for American, b for British.
    pipe = KPipeline(lang_code=a.voice[0], repo_id="hexgrad/Kokoro-82M")
    pieces, words, offset = [], [], 0.0
    for r in pipe(a.text, voice=a.voice, speed=a.speed):
        audio = r.audio.numpy()
        for t in (r.tokens or []):
            if t.start_ts is not None and t.end_ts is not None:
                words.append(dict(text=t.text, start=offset + float(t.start_ts),
                                  end=offset + float(t.end_ts)))
        pieces.append(audio)
        offset += len(audio) / SR
    wav = np.concatenate(pieces)
    sf.write(a.out + ".wav", wav, SR)
    with open(a.out + ".json", "w") as fh:
        json.dump(dict(seconds=len(wav) / SR, words=words), fh)
    print(json.dumps(dict(seconds=round(len(wav) / SR, 3), words=len(words))))


if __name__ == "__main__":
    main()
