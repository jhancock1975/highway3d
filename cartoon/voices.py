"""Who sounds like what. Stdlib only, for the same reason as moods.py.

Each voice is a blend of Kokoro speakers -- a weighted mix of embedding
vectors is a speaker none of them is -- then an accent on the phonemes,
then pitch and formants moved apart, which no real throat does. Nobody's
voice is imitated; these are voices for cartoon characters.

- euler:    a big, warm, elderly man from Basel. The Swiss-German accent is
            lighter than lectern's einstein (0.55 against 0.8): vowels mostly
            English, w and th bent, final consonants devoiced.
- cinnamon: small and quick. Pitch up, formants up further than pitch, so it
            sounds like a small throat rather than a sped-up tape.
- fuss:     Euler's assistant, young, also from Basel, heard through a door.
"""

from __future__ import annotations

PRESETS = {
    "euler": dict(
        blend=[("am_santa", 0.45), ("bm_george", 0.35), ("bm_fable", 0.20)],
        lang="b", accent=0.55, speed=0.92,
        pitch=0.97, formants=0.93,
        hoarse=0.30, breath=0.06, presence=0.18, body=0.28,
    ),
    "cinnamon": dict(
        blend=[("af_sky", 0.45), ("am_puck", 0.35), ("af_bella", 0.20)],
        lang="a", accent=0.0, speed=1.02,
        pitch=1.16, formants=1.14,
        hoarse=0.0, breath=0.0, presence=0.30, body=0.0,
    ),
    "fuss": dict(
        blend=[("bm_lewis", 0.6), ("bm_daniel", 0.4)],
        lang="b", accent=0.45, speed=1.0,
        pitch=1.03, formants=1.0,
        hoarse=0.0, breath=0.0, presence=0.1, body=0.1,
    ),
}

# Names the accent must not touch: a charming "sink" for "think" is the
# point, an unintelligible "Euclid" is a bug.
PROTECTED = {"euler", "euclid", "fuss", "cinnamon", "leonhard", "herr",
             "pi", "e", "i"}

VOICES = tuple(PRESETS)
