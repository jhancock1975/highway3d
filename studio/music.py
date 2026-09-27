"""A music bed from a mood, exactly as long as asked.

Written, not modelled: the numpy composer in highway3d/music.py, through
lectern.score, which reads the moods off it rather than keeping a copy. No
weights, no licence that follows the output, and too little memory to be
worth guarding.
"""

from __future__ import annotations

import os
import tempfile

from lectern import score
from studio import library

MOODS = tuple(score.MOODS)


def compose(mood: str = "drive", seconds: float = 30.0) -> dict:
    """A bed of `seconds` in `mood`, filed in the library."""
    if mood not in MOODS:
        raise ValueError(f"there is no mood called {mood}; the moods are "
                         f"{', '.join(MOODS)}")
    fd, out = tempfile.mkstemp(prefix="studio-music-", suffix=".wav")
    os.close(fd)
    try:
        score.render(float(seconds), out, mood)
        return library.add(out, "music", source=f"music: {mood}", move=True,
                           mood=mood)
    finally:
        if os.path.exists(out):
            os.remove(out)
