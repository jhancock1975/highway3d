"""Cutaway scenes: the thing itself, instead of a man describing it.

Runs inside Blender. One module per scene, discovered from the directory
exactly as the demonstrations are -- a hardcoded list here disagreed with
the one in `script.py` once already, and the renderer died thirty shots into
a job because of it.

A scene is not a demonstration. A demonstration is staged beside him, on a
plinth, while he stands there and works it. A scene replaces him: it has its
own room, its own light and its own camera, he is not in the frame at all,
and the narration becomes voice-over. Twenty seconds of a man saying that
somebody measured the speed of light on a bench is worse television than
twenty seconds of somebody measuring the speed of light on a bench.

Each scene exposes:

    NAME, SUMMARY, build(n_frames, fps) -> dict

`build` makes everything including the room, keyframes it across the whole
shot, and returns where the camera goes. It is handed the real frame count
because timing is speech-driven: the scene is cut to the sentence, never the
sentence to the scene.
"""

from __future__ import annotations

import importlib
import os

_loaded: dict = {}


def modules() -> tuple:
    here = os.path.dirname(os.path.abspath(__file__))
    return tuple(sorted(f[:-3] for f in os.listdir(here)
                        if f.endswith(".py") and not f.startswith("_")))


def registry() -> dict:
    if not _loaded:
        for name in modules():
            _loaded[name] = importlib.import_module(f"{__name__}.{name}")
    return _loaded


def names() -> list[str]:
    return sorted(registry())


def catalogue() -> list[dict]:
    """What each scene is, for a caller choosing between them."""
    return [dict(name=n, summary=getattr(m, "SUMMARY", ""))
            for n, m in sorted(registry().items())]


def build(name: str, n_frames: int = 48, fps: int = 24) -> dict:
    mods = registry()
    if name not in mods:
        raise KeyError(
            f"no scene called '{name}'; known: {', '.join(names())}")
    return mods[name].build(n_frames, fps)
