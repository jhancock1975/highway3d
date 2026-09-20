"""Background music for a lecture, written rather than modelled.

    .ttsvenv/bin/python -m lectern.score --duration 1620 --out score.wav

The score itself is `highway3d/music.py`, unchanged: four layers -- pad,
bass, arpeggio and a soft pulse -- over a looping progression, numpy only.
It was written for the traffic films and it does exactly this job, so it is
loaded from there rather than copied. Copying it would give this project a
second score generator to keep in step with the first, which is the mistake
the demonstration lists already made once.

It is loaded by path because `highway3d/` is a directory of scripts and not
an importable package, and making it one would change how every one of its
own entry points is run.

The mood belongs to the document. A lecture is not a car chase: `night` is
sparse and nearly rhythmless, which is what sits under speech without
competing with it, and it is the default for that reason.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC = os.path.join(HERE, "highway3d", "music.py")


def moods() -> tuple:
    """The moods that exist, read off `music.py` without importing it.

    Parsed rather than imported because `script.py` validates documents
    under an interpreter with no numpy, and music.py needs numpy at import.
    The same reason `_known_demos` lists a directory: one source of truth,
    reachable from both sides.
    """
    try:
        with open(MUSIC) as fh:
            tree = ast.parse(fh.read())
    except OSError:
        return ()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "MOODS":
                return tuple(k.value for k in node.value.keys
                             if isinstance(k, ast.Constant))
    return ()


MOODS = moods()


def _music():
    spec = importlib.util.spec_from_file_location("hw_music", MUSIC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render(duration: float, out: str, mood: str = "night", seed: int = 11):
    """One score, exactly `duration` long, so nothing has to be looped or cut."""
    m = _music()
    if mood not in MOODS:
        raise ValueError(f"no mood called '{mood}'; have: {', '.join(MOODS)}")
    audio = m.render(duration, mood=mood, seed=seed)
    m.write(out, audio)
    return dict(out=out, duration=duration, mood=mood, sr=m.SR)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mood", default="night", choices=MOODS or None)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    import json
    print(json.dumps(render(a.duration, a.out, a.mood, a.seed)))


if __name__ == "__main__":
    main()
