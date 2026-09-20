"""Phonemes in, mouth shapes out.

Pure Python -- no bpy -- so it can be tested without launching Blender.

The input is the timeline `narrate.py` measured, which carries the accented
phonemes actually spoken and the real time each word occupied. Phonemes are
laid out inside their word, mapped onto a small set of mouth shapes, and then
smoothed, because a mouth that snapped between shapes on phoneme boundaries
would chatter: real articulation overlaps, and the shape of a sound is
already forming during the one before it.

Nine shapes rather than forty. Past about this many the extra fidelity is
invisible at 24 fps on a cartoon face, and every one of them is a shape
somebody has to be able to look at and recognise.
"""

from __future__ import annotations

# Kokoro speaks misaki's inventory: diphthongs arrive as capitals.
VISEMES = {
    #        open  wide  round
    "REST": (0.06, 1.00, 1.00),
    "AI":   (0.88, 1.16, 0.94),   # ɑ a A æ ɛ  -- jaw down
    "E":    (0.42, 1.32, 0.84),   # i ɪ iː e   -- spread
    "O":    (0.70, 0.82, 1.16),   # ɒ ɔ Q o    -- rounded
    "U":    (0.34, 0.62, 1.28),   # u uː ʊ W   -- pursed
    "MBP":  (0.00, 1.02, 1.00),   # m b p      -- shut
    "FV":   (0.13, 1.06, 0.94),   # f v        -- lip to teeth
    "L":    (0.46, 1.00, 1.00),   # l ɹ r      -- tongue visible
    "S":    (0.22, 1.10, 0.96),   # everything else voiced through a gap
}

PHONEME_TO_VISEME = {}
for _group, _chars in {
    "AI": "ɑaAæɛʌ",
    "E":  "iɪeI",
    "O":  "ɒɔoQ",
    "U":  "uʊWY",
    "MBP": "mbp",
    "FV": "fv",
    "L":  "lɹrɾ",
    "S":  "szʃʒtdnkɡghjʧʤθðŋ",
}.items():
    for _c in _chars:
        PHONEME_TO_VISEME[_c] = _group

SKIP = set("ˈˌːˑ̩ᵊ ")
PAUSE = set(".,;:!?\"'()")


def phoneme_units(phonemes: str) -> list[str]:
    """Split a phoneme string into units, dropping stress and length marks."""
    out = []
    for ch in phonemes:
        if ch in SKIP:
            continue
        if ch in PAUSE:
            out.append(".")
            continue
        out.append(ch)
    return out


def viseme_of(unit: str) -> str:
    if unit == ".":
        return "REST"
    return PHONEME_TO_VISEME.get(unit, "S")


def track(timeline: dict, fps: int = 24, smoothing: float = 0.045) -> list[dict]:
    """A mouth shape per frame for the whole segment.

    `smoothing` is the coarticulation time constant in seconds: how long the
    mouth takes to reach a shape it is heading for. Too small and the jaw
    chatters; too large and he mumbles.
    """
    duration = timeline["duration"]
    n = max(1, int(round(duration * fps)))

    # lay phonemes out inside the word that measured them
    events = []
    for w in timeline["words"]:
        units = [u for u in phoneme_units(w["phonemes"]) if u != "."]
        if not units:
            events.append((w["start"], "REST"))
            continue
        span = max(1e-4, w["end"] - w["start"]) / len(units)
        for i, u in enumerate(units):
            events.append((w["start"] + i * span, viseme_of(u)))
    events.sort(key=lambda e: e[0])

    # sample to frames, holding the last shape, resting past the end of speech
    target = []
    j = 0
    for f in range(n):
        t = f / fps
        while j + 1 < len(events) and events[j + 1][0] <= t:
            j += 1
        if not events or t < events[0][0]:
            target.append("REST")
        else:
            target.append(events[j][1])

    # smooth toward the target rather than snapping to it
    alpha = 1.0 - pow(0.001, 1.0 / max(1.0, smoothing * fps))
    cur = list(VISEMES["REST"])
    out = []
    for f in range(n):
        goal = VISEMES[target[f]]
        cur = [c + (g - c) * alpha for c, g in zip(cur, goal)]
        out.append(dict(frame=f, viseme=target[f],
                        open=round(cur[0], 4), wide=round(cur[1], 4),
                        round=round(cur[2], 4)))
    return out
