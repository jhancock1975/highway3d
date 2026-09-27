"""Speech from text, with the time every word is said.

Kokoro does the speaking, under `.ttsvenv`, because torch and Kokoro live
there and nowhere else, through speech_engine.py. `einstein` is lectern's
blended, accented voice; the engine says his text through lectern.narrate
a few sentences at a time, because narrate says a text in one breath and
Kokoro refuses a long one. Either way the words come back with a start and
an end, and captions are drawn from them.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile

from studio import library, memory
from studio.errors import last_line

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS = os.environ.get("STUDIO_TTS", os.path.join(HERE, ".ttsvenv", "bin", "python"))
ENGINE = os.path.join(HERE, "studio", "speech_engine.py")
VOICES = ("am_michael", "am_onyx", "af_heart", "af_nova", "bm_george",
          "bf_emma", "einstein")


def words(raw: list[dict]) -> list[dict]:
    """Kokoro's tokens as words: punctuation joins the word before it."""
    out: list[dict] = []
    for t in raw:
        text = t["text"].strip()
        if not text:
            continue
        if out and not re.search(r"\w", text):
            out[-1]["text"] += text
            continue
        out.append(dict(text=text, start=round(float(t["start"]), 3),
                        end=round(float(t["end"]), 3)))
    return out


def speak(text: str, voice: str = "am_michael", speed: float = 1.0) -> dict:
    """Say `text` in `voice`, and file it in the library with its words."""
    if not text.strip():
        raise ValueError("there is nothing to say")
    if voice not in VOICES:
        raise ValueError(f"there is no voice called {voice}; the voices are "
                         f"{', '.join(VOICES)}")
    refused = memory.refusal("speech")
    if refused:
        raise MemoryError(refused)
    with tempfile.TemporaryDirectory(prefix="studio-speech-") as tmp:
        stem = os.path.join(tmp, "speech")
        cmd = [TTS, ENGINE, "--text", text, "--voice", voice,
               "--speed", f"{speed:.3f}", "--out", stem]
        r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                           timeout=1800)
        if r.returncode != 0 or not os.path.exists(stem + ".wav"):
            raise RuntimeError("speech stopped: "
                               + last_line(r.stderr or r.stdout))
        with open(stem + ".json") as fh:
            timing = json.load(fh)
        return library.add(stem + ".wav", "voice", source=f"speech: {voice}",
                           move=True, text=text, voice=voice,
                           words=words(timing["words"]))
