"""The edit: what goes where, checked before anything renders.

An edit is JSON a model can write without computing a timecode. The video
track plays in order, so start times follow from lengths; overlays and
audio say when they begin. `normalise` turns an edit into a plan with every
time worked out and every asset found, and reports everything wrong with
it at once, in sentences. A problem found here costs nothing; the same
problem found by ffmpeg costs the whole render.
"""

from __future__ import annotations

import re

TRANSITION = 0.5
TRANSITIONS = ("cut", "dissolve", "fade")
FITS = ("cover", "contain")
MOVES = ("none", "push-in", "pull-out", "pan-left", "pan-right")
PLACES = ("full", "center", "top", "bottom", "top-left", "top-right",
          "bottom-left", "bottom-right")
STILL_SECONDS = 4.0
CHUNK = 7


def _s(x: float) -> str:
    """A time as a person writes it: 9, 9.5, 9.04."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def chunks(words: list[dict], at: float) -> list[dict]:
    """Speech's words in runs of up to seven, each shown while it is said.

    A run ends early at the end of a sentence, and at a comma once it has
    four words, so a caption breaks where the voice does. A short gap
    between runs is bridged, so captions do not flicker off and on.
    """
    runs, run = [], []
    for w in words:
        if not w["text"].strip():
            continue
        run.append(w)
        last = w["text"].rstrip("\"')”’")[-1:]
        if (len(run) >= CHUNK or (last and last in ".!?")
                or (last and last in ",;:" and len(run) >= 4)):
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    out = [dict(text=" ".join(w["text"] for w in r),
                at=round(at + r[0]["start"], 3), end=round(at + r[-1]["end"], 3))
           for r in runs]
    for a, b in zip(out, out[1:]):
        if b["at"] - a["end"] < 0.3:
            a["end"] = b["at"]
    for c in out:
        c["seconds"] = round(max(c.pop("end") - c["at"], 0.6), 3)
    return out


def normalise(edit: dict, lookup) -> tuple[dict, list[str]]:
    """A plan with every time and file worked out, and what is wrong."""
    problems: list[str] = []
    found: dict[str, dict | None] = {}

    def find(ref, where):
        if not isinstance(ref, str) or not ref.strip():
            problems.append(f"{where}: it needs an asset.")
            return None
        if ref not in found:
            try:
                found[ref] = lookup(ref)
            except (KeyError, ValueError) as e:
                problems.append(f"{where}: {e.args[0] if e.args else e}.")
                found[ref] = None
        return found[ref]

    def number(item, key, default, where, lo, hi):
        v = item.get(key, default)
        try:
            v = float(v)
        except (TypeError, ValueError):
            problems.append(f"{where}: {key} {v!r} is not a number.")
            return default
        if not lo <= v <= hi:
            problems.append(f"{where}: {key} {_s(v)} is outside {_s(lo)} "
                            f"to {_s(hi)}.")
            return default
        return v

    def choice(item, key, allowed, where):
        v = item.get(key, allowed[0])
        if v not in allowed:
            problems.append(f"{where}: {key} {v!r} is not one of "
                            f"{', '.join(allowed)}.")
            return allowed[0]
        return v

    def listed(key):
        items = edit.get(key) or []
        if not isinstance(items, list):
            problems.append(f"{key} must be a list.")
            return []
        return [{"asset": x} if isinstance(x, str) else x for x in items]

    # -- frame
    size = edit.get("size", "1920x1080")
    m = re.fullmatch(r"\s*(\d+)\s*[x×]\s*(\d+)\s*", str(size))
    w, h = (int(m[1]), int(m[2])) if m else (1920, 1080)
    if not m:
        problems.append(f"size {size!r} is not WIDTHxHEIGHT, like 1920x1080.")
    elif not (16 <= w <= 7680 and 16 <= h <= 4320):
        problems.append(f"size {w}x{h} is outside 16x16 to 7680x4320.")
        w, h = 1920, 1080
    # H.264 wants even sides, and one pixel is not worth a complaint.
    w, h = w - w % 2, h - h % 2
    fps = number(edit, "fps", 30.0, "the edit", 1, 120)
    name = re.sub(r"[^a-z0-9]+", "-", str(edit.get("name", "edit")).lower())
    name = name.strip("-")[:60] or "edit"

    # -- video, in order
    video: list[dict] = []
    t = 0.0
    for i, item in enumerate(listed("video"), 1):
        where = f"video item {i}"
        if not isinstance(item, dict):
            problems.append(f"{where}: it should be an object with an asset.")
            continue
        note = find(item.get("asset"), where)
        transition = choice(item, "transition", TRANSITIONS, where)
        fit = choice(item, "fit", FITS, where)
        move = choice(item, "move", MOVES, where)
        level = number(item, "level", 1.0, where, 0, 1)
        if note is None:
            continue
        if note["kind"] == "audio":
            problems.append(f"{where}: {note['id']} is sound, which goes in "
                            f"audio, not video.")
            continue
        start_in = 0.0
        if note["kind"] == "image":
            seconds = number(item, "seconds", STILL_SECONDS, where, 0.1, 3600)
        else:
            if move != "none":
                problems.append(f"{where}: move is for stills, and "
                                f"{note['id']} is video.")
                move = "none"
            length = note["seconds"]
            start_in = number(item, "from", 0.0, where, 0, 1e6)
            if start_in >= length:
                problems.append(f"{where}: {note['id']} is {_s(length)} "
                                f"seconds long, so from {_s(start_in)} is "
                                f"past its end.")
                continue
            seconds = number(item, "seconds", length - start_in, where, 0.1,
                             1e6)
            if start_in + seconds > length + 0.05:
                problems.append(f"{where}: {note['id']} is {_s(length)} "
                                f"seconds long, so {_s(seconds)} seconds from "
                                f"{_s(start_in)} runs past its end.")
                continue
        overlap = TRANSITION if video and transition != "cut" else 0.0
        if overlap and (seconds <= TRANSITION or
                        video[-1]["seconds"] <= TRANSITION):
            problems.append(f"{where}: its {transition} takes half a second, "
                            f"so it and the item before it must each be "
                            f"longer than that.")
            continue
        start = round(t - overlap, 3)
        video.append(dict(path=note["path"], id=note["id"], kind=note["kind"],
                          start=start, seconds=seconds, from_=start_in,
                          transition=transition, fit=fit, move=move,
                          level=level, sound=bool(note.get("sound"))))
        t = start + seconds

    # -- audio, placed by time
    audio: list[dict] = []
    for i, item in enumerate(listed("audio"), 1):
        where = f"audio item {i}"
        if not isinstance(item, dict):
            problems.append(f"{where}: it should be an object with an asset.")
            continue
        note = find(item.get("asset"), where)
        at = number(item, "at", 0.0, where, 0, 1e6)
        level = number(item, "level", 1.0, where, 0, 1)
        if note is None:
            continue
        if note["kind"] == "image":
            problems.append(f"{where}: {note['id']} is a picture, which has "
                            f"no sound.")
            continue
        if note["kind"] == "video" and not note.get("sound"):
            problems.append(f"{where}: {note['id']} is silent video, so there "
                            f"is no sound in it to use.")
            continue
        music = note["id"].startswith("music-")
        fade = number(item, "fade", 1.0 if music else 0.0, where, 0, 60)
        if video and at >= t:
            problems.append(f"{where}: it starts at {_s(at)}, after the edit "
                            f"ends at {_s(t)}.")
            continue
        audio.append(dict(path=note["path"], id=note["id"], at=at,
                          level=level, fade=fade,
                          duck=bool(item.get("duck", False)),
                          speech=bool(note.get("words")),
                          seconds=note["seconds"],
                          words=note.get("words") or []))

    if not edit.get("video") and not edit.get("audio"):
        problems.append("the edit has nothing in it: add video or audio.")
    total = t if video else max((a["at"] + a["seconds"] for a in audio),
                                default=0.0)

    # -- overlays and captions
    overlays: list[dict] = []
    captions: list[dict] = []
    for i, item in enumerate(listed("overlays"), 1):
        where = f"overlay {i}"
        if not isinstance(item, dict):
            problems.append(f"{where}: it should be an object with an asset.")
            continue
        if "captions" in item:
            note = find(item["captions"], "captions")
            if note is None:
                continue
            if not note.get("words"):
                what = ("music" if note["id"].startswith("music-")
                        else "a picture" if note["kind"] == "image"
                        else note["kind"] if note["kind"] == "video"
                        else "sound with no words")
                problems.append(f"captions: {note['id']} is {what}, not "
                                f"speech, so it has no words to show.")
                continue
            spoken = next((a for a in audio if a["id"] == note["id"]), None)
            if spoken is None:
                problems.append(f"captions: {note['id']} is not in audio, so "
                                f"there is no time to show its words at.")
                continue
            captions.extend(chunks(note["words"], spoken["at"]))
            continue
        note = find(item.get("asset"), where)
        at = number(item, "at", 0.0, where, 0, 1e6)
        place = choice(item, "place", PLACES, where)
        if note is None:
            continue
        if note["kind"] != "image":
            problems.append(f"{where}: overlays are pictures, and "
                            f"{note['id']} is {note['kind']}.")
            continue
        if video and at >= total:
            problems.append(f"{where}: it starts at {_s(at)}, after the edit "
                            f"ends at {_s(total)}.")
            continue
        seconds = number(item, "seconds", max(total - at, 0.1), where, 0.1,
                         1e6)
        overlays.append(dict(path=note["path"], id=note["id"], at=at,
                             seconds=seconds, place=place,
                             width=note["width"], height=note["height"]))

    for a in audio:
        a.pop("words")
    plan = dict(width=w, height=h, fps=fps, name=name,
                seconds=round(total, 3), audio_only=not video, video=video,
                overlays=overlays, captions=captions, audio=audio)
    return plan, problems
