"""How a character feels on a line: in the voice, on the face, in the body.

Stdlib only. Three interpreters need this table -- `speak.py` under
`.ttsvenv` bends the voice with it, the Blender side poses the face with it,
and `script.py` checks documents against it under a venv with neither numpy
nor bpy -- and one table read by all three cannot disagree with itself.

Every mood is a few numbers, not a name the renderer has to interpret:

- voice: pitch, speed and level multipliers on top of the character's preset
- face:  smile (-1 frown .. 1 grin), brows (-1 knit .. 1 raised), lids
         (0 shut .. 1 wide; 0.8 is relaxed), squint (cheeks up)
- body:  energy (how big and how often gestures are) and lean (-1 back ..
         1 toward the other character)
"""

from __future__ import annotations

import hashlib

#               pitch  speed  level   smile brows  lids squint  energy lean
_T = {
    "neutral":     (1.00, 1.00, 1.00,   0.10, 0.00, 0.80, 0.00,   0.5,  0.0),
    "absorbed":    (0.97, 0.92, 0.72,   0.05, -0.25, 0.62, 0.10,  0.3, -0.1),
    "amused":      (1.03, 1.00, 1.00,   0.55, 0.20, 0.72, 0.35,   0.6,  0.1),
    "curious":     (1.04, 1.00, 1.00,   0.20, 0.45, 0.92, 0.00,   0.6,  0.4),
    "puzzled":     (1.02, 0.96, 0.98,  -0.05, 0.30, 0.85, 0.05,   0.4,  0.0),
    "eager":       (1.07, 1.08, 1.02,   0.60, 0.55, 0.96, 0.10,   0.9,  0.6),
    "dreamy":      (1.00, 0.90, 0.86,   0.45, 0.25, 0.35, 0.20,   0.4,  0.0),
    "delighted":   (1.08, 1.05, 1.06,   0.90, 0.65, 0.90, 0.45,   0.9,  0.4),
    "wry":         (0.98, 1.00, 0.90,   0.35, -0.10, 0.68, 0.25,  0.4,  0.0),
    "incredulous": (1.08, 1.00, 1.02,   0.10, 0.80, 1.00, 0.00,   0.8, -0.2),
    "proud":       (1.02, 0.97, 1.02,   0.60, 0.35, 0.70, 0.25,   0.7, -0.2),
    "thoughtful":  (0.97, 0.93, 0.95,   0.15, -0.20, 0.60, 0.10,  0.3,  0.0),
    "cheerful":    (1.05, 1.04, 1.02,   0.80, 0.40, 0.85, 0.35,   0.8,  0.2),
    "mischievous": (1.00, 0.97, 0.92,   0.55, 0.30, 0.62, 0.30,   0.6,  0.3),
    "alarmed":     (1.13, 1.12, 1.10,  -0.40, 0.90, 1.00, 0.00,   1.0, -0.5),
    "grumpy":      (0.94, 0.98, 0.98,  -0.45, -0.60, 0.62, 0.10,  0.5,  0.0),
    "teacherly":   (1.00, 0.97, 1.00,   0.30, 0.30, 0.80, 0.10,   0.6,  0.2),
    "awed":        (0.98, 0.90, 0.92,   0.25, 0.70, 1.00, 0.00,   0.4,  0.3),
    "excited":     (1.06, 1.06, 1.05,   0.75, 0.60, 0.95, 0.30,   1.0,  0.3),
    "amazed":      (1.10, 1.05, 1.06,   0.70, 0.90, 1.00, 0.20,   1.0,  0.2),
    "tender":      (0.97, 0.92, 0.86,   0.45, 0.20, 0.66, 0.25,   0.3,  0.3),
    "chef":        (1.00, 0.95, 1.00,   0.25, -0.15, 0.55, 0.15,  0.7,  0.2),
    "moved":       (0.96, 0.88, 0.76,   0.35, 0.55, 0.60, 0.20,   0.2,  0.2),
    "concerned":   (1.02, 0.97, 0.95,  -0.20, 0.60, 0.90, 0.00,   0.4,  0.4),
    "wistful":     (0.96, 0.90, 0.80,   0.20, 0.35, 0.50, 0.10,   0.2,  0.0),
    "content":     (0.98, 0.95, 0.95,   0.60, 0.15, 0.30, 0.35,   0.2, -0.2),
}

MOODS = tuple(_T)


def mood(name: str | None) -> dict:
    p, s, lv, sm, br, li, sq, en, le = _T.get(name or "neutral", _T["neutral"])
    return dict(pitch=p, speed=s, level=lv, smile=sm, brows=br, lids=li,
                squint=sq, energy=en, lean=le)


def voice(name: str | None, text: str = "") -> dict:
    """The voice half of a mood, with a small wobble stable per line.

    Two lines in the same mood must still not come out identical, or the
    speaker sounds like a machine hitting the same note. The wobble is keyed
    on the words, so it is the same every render and the cache holds.
    """
    m = mood(name)
    h = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
    return dict(pitch=m["pitch"] * (1.0 + ((h % 1000) / 1000.0 - 0.5) * 0.03),
                speed=m["speed"] * (1.0 + (((h >> 11) % 1000) / 1000.0 - 0.5) * 0.04),
                level=m["level"])
