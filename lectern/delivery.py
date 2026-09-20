"""How a line is said, as opposed to what it says.

Its own module, and deliberately stdlib-only, because two things that cannot
import each other both need it: `voice.py` runs under `.ttsvenv` with numpy
and torch behind it, and `script.py` validates documents under `.mcpvenv`
with neither. The alternative is the same table written out twice, which is
the bug this project has already paid for once -- a demonstration list in
`script.py` that disagreed with the one in `demos/__init__.py`, a document
that validated clean, and a render that died thirty shots in.

Every segment used to be spoken at the same pitch, the same rate and the same
peak level. Measured across 24 consecutive segments the baseline pitch spanned
0.56 semitones: 156.9 Hz, sentence after sentence, for twenty-three minutes.
Within any one sentence the contour is fine -- about 3.3 semitones of spread,
which is normal speech -- so the flatness was entirely between them. That is
what is heard as monotone, and no amount of work inside a sentence fixes it.

A lecturer does not deliver the setup, the joke and the conclusion the same
way. These are the ways; the document says which line gets which.
"""

from __future__ import annotations

import hashlib

DELIVERIES = {
    "plain":  dict(pitch=1.000, speed=1.00, level=1.00),
    # A chapter opens up and slows down: new subject, fresh breath.
    "open":   dict(pitch=1.050, speed=0.95, level=1.00),
    "build":  dict(pitch=1.020, speed=1.04, level=0.99),
    # Thrown away over the shoulder -- quicker, lower, and quieter, which is
    # what makes it read as an aside rather than as another sentence. 0.84
    # measured at only 1 dB under `plain` across the whole lecture, which is
    # about the threshold of being noticeable; a real aside drops three to
    # six.
    "aside":  dict(pitch=0.975, speed=1.08, level=0.62),
    # The line a joke lands on. Slow it down, keep it level, let it sit.
    "punch":  dict(pitch=0.985, speed=0.90, level=1.00),
    # The point he actually wants remembered.
    "weight": dict(pitch=0.940, speed=0.92, level=0.98),
    "wry":    dict(pitch=1.030, speed=0.99, level=0.80),
}

NAMES = tuple(DELIVERIES)


def delivery(name: str = "plain", text: str = "") -> dict:
    """Delivery parameters, plus a small wobble that is stable per line.

    Two segments marked the same way must still not come out identical: a
    speaker who hits the same note twice running is back to sounding like a
    machine. The wobble is keyed on the words themselves, so it is the same
    on every render and the narration cache stays valid.
    """
    d = dict(DELIVERIES.get(name or "plain", DELIVERIES["plain"]))
    h = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
    d["pitch"] *= 1.0 + ((h % 1000) / 1000.0 - 0.5) * 0.030
    d["speed"] *= 1.0 + (((h >> 11) % 1000) / 1000.0 - 0.5) * 0.045
    return d


def infer(seg: dict) -> str:
    """The delivery for a segment the document did not mark.

    Explicit wins. The inference covers only what is always true of a
    lecture: a chapter opens on a fresh breath, and its last line is the one
    meant to land.
    """
    if seg.get("delivery"):
        return seg["delivery"]
    if seg.get("first_in_chapter"):
        return "open"
    if seg.get("last_in_chapter"):
        return "weight"
    return "plain"


# ----------------------------------------------------------------- beats

# What he does with his hands while he says it. `beat` was accepted by the
# MCP server, written into the document and carried through the planner, and
# then read by nothing at all: an agent could ask for "points at the
# denominator", get a success message back, and watch him stand there. A
# free-text hint that no renderer understands is not a hint, it is a silent
# discard, and this server exists to be driven by other agents.
#
# So it is a closed set, checked by `script.validate` against this table and
# animated by `shot.animate_body` from the same one. An unknown beat is now
# an error with the list in it rather than a shrug.
BEATS = {
    "still":   None,        # hands stay down; idle motion only
    "beat":    "beat",      # a plain emphasis stroke
    "point":   "point",     # indicates the thing he is presenting
    "present": "present",   # opens a hand toward it
    "open":    "open",      # both-hands-open, "consider this"
    "count":   "count",     # hand up and held, for enumerating
}

BEAT_NAMES = tuple(BEATS)
