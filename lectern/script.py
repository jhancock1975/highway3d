"""The lecture document: load it, check it, and say what is wrong.

A lecture is data. This module is the only thing that knows its shape, so a
malformed document is caught here in milliseconds rather than twenty minutes
into a render -- the lesson the old `test_content.py` learned the hard way,
when one unsupported LaTeX command killed a 35,000-frame job.

Nothing here imports bpy, so validation runs without launching Blender.
"""

from __future__ import annotations

import os

from lectern.delivery import (BEAT_NAMES, NAMES as DELIVERY_NAMES,
                              infer as infer_delivery)

# Re-exported so the MCP server checks against the same table the
# renderer animates from, rather than a copy of it.
__all__ = ["BEAT_NAMES", "DELIVERY_NAMES"]

STAGE_KINDS = ("card", "board", "note", "demo")

def _known_demos() -> tuple:
    """The demonstrations that actually exist, read off disk.

    Not a hardcoded list. A hardcoded one said `gamma_curve` was fine, the
    document asked for it, `lecture_check` answered "ready to render", and the
    job then died thirty shots in -- which is the exact failure this module
    exists to prevent. The modules on disk are the truth; asking them costs a
    directory listing and needs no bpy, so validation still runs outside
    Blender.
    """
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "stage", "demos")
    try:
        return tuple(sorted(f[:-3] for f in os.listdir(here)
                            if f.endswith(".py") and not f.startswith("_")))
    except OSError:
        return ()


KNOWN_DEMOS = _known_demos()

DEFAULTS = dict(presenter="einstein", look="study", fps=24,
                voice=dict(preset="einstein", speed=0.94))


class ScriptError(ValueError):
    """A document that cannot be rendered, with the reason in words."""


def load(path: str) -> dict:
    import yaml
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        raise ScriptError(f"{path} is not a lecture document")
    doc.setdefault("source", os.path.abspath(path))
    return normalise(doc)


def normalise(doc: dict) -> dict:
    out = dict(DEFAULTS)
    out.update(doc)
    out["voice"] = dict(DEFAULTS["voice"], **(doc.get("voice") or {}))
    chapters = out.get("chapters") or []
    for c in chapters:
        c.setdefault("segments", [])
    out["chapters"] = chapters
    return out


def segments(doc: dict) -> list[dict]:
    """Flatten to a list, each carrying where it came from."""
    flat = []
    for ci, chapter in enumerate(doc["chapters"]):
        n = len(chapter["segments"])
        for si, seg in enumerate(chapter["segments"]):
            out = dict(
                index=len(flat),
                chapter=ci,
                chapter_title=chapter.get("title", ""),
                first_in_chapter=(si == 0),
                last_in_chapter=(si == n - 1),
                say=seg["say"],
                stage=seg.get("stage") or {},
                beat=seg.get("beat", ""),
                delivery=seg.get("delivery", ""),
            )
            # Resolved here rather than at the point of synthesis, so that
            # what the cache is keyed on and what is spoken are the same
            # string and cannot drift apart.
            out["delivery"] = infer_delivery(out)
            flat.append(out)
    return flat


def validate(doc: dict, demos=None) -> list[str]:
    """Every problem in the document, as sentences. Empty means renderable."""
    demos = tuple(demos or KNOWN_DEMOS)
    problems = []

    if not doc.get("title"):
        problems.append("The lecture has no title.")
    if not doc.get("chapters"):
        problems.append("The lecture has no chapters.")

    for i, seg in enumerate(segments(doc)):
        where = f"segment {i} (chapter {seg['chapter'] + 1})"
        if not str(seg["say"]).strip():
            problems.append(f"{where} has nothing to say.")
        if seg["beat"] and seg["beat"] not in BEAT_NAMES:
            problems.append(
                f"{where} asks for the beat '{seg['beat']}', which is not one "
                f"this renderer knows. Use one of: {', '.join(BEAT_NAMES)}.")
        if seg["delivery"] not in DELIVERY_NAMES:
            problems.append(
                f"{where} asks to be said '{seg['delivery']}', which is not a "
                f"delivery. Use one of: {', '.join(DELIVERY_NAMES)}.")
        stage = seg["stage"]
        if not stage:
            problems.append(f"{where} has no stage direction.")
            continue
        if len(stage) > 1:
            problems.append(
                f"{where} has {len(stage)} stage directions "
                f"({', '.join(sorted(stage))}); it may have one.")
            continue
        kind = next(iter(stage))
        if kind not in STAGE_KINDS:
            problems.append(
                f"{where} asks for '{kind}', which is not a stage kind. "
                f"Use one of: {', '.join(STAGE_KINDS)}.")
            continue
        body = stage[kind]
        if kind == "demo":
            if body not in demos:
                problems.append(
                    f"{where} asks for the demonstration '{body}', which does "
                    f"not exist. Call lecture_describe for the catalogue.")
        elif kind == "note":
            if not (body or {}).get("lines"):
                problems.append(f"{where} is a note with no lines.")
        elif kind == "board":
            if not (body or {}).get("items"):
                problems.append(f"{where} is a board with no items.")
        elif kind == "card":
            if not (body or {}).get("title"):
                problems.append(f"{where} is a card with no title.")
    return problems


def word_count(doc: dict) -> int:
    return sum(len(s["say"].split()) for s in segments(doc))


def estimate_minutes(doc: dict, wpm: float = 138.0) -> float:
    """Rough runtime before anything is synthesised.

    Only an estimate: the real timing is measured from the speech itself, and
    this voice runs slower than plain narration because of the accent.
    """
    n = len(segments(doc))
    speech = word_count(doc) / wpm
    pauses = n * 1.0 / 60.0
    holds = len(doc["chapters"]) * 2.6 / 60.0
    return speech + pauses + holds


def summary(doc: dict) -> str:
    kinds: dict[str, int] = {}
    for s in segments(doc):
        for k in s["stage"]:
            kinds[k] = kinds.get(k, 0) + 1
    parts = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))
    return (f"'{doc['title']}', {len(doc['chapters'])} chapters, "
            f"{len(segments(doc))} segments, {word_count(doc)} words, "
            f"about {estimate_minutes(doc):.0f} minutes. Staging: {parts}.")
