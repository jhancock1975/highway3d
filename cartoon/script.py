"""A cartoon document: load it, check it, flatten it into beats.

Needs only PyYAML, so it runs under `.ttsvenv`, `cartoon/.venv` and
`lectern/.mcpvenv` alike. Blender never reads YAML: `build.py` hands it
the flattened beats as JSON.
"""

from __future__ import annotations

import hashlib
import json

import yaml

from cartoon import moods, vocab, voices


def load(path: str) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def _line(b: dict, cast: dict):
    for who in cast:
        if who in b:
            return who, str(b[who])
    return None, None


def validate(doc: dict) -> list[str]:
    """Everything wrong with a document, as sentences. Empty means fine."""
    bad = []
    cast = doc.get("cast") or {}
    if not cast:
        bad.append("there is no cast")
    for who, c in cast.items():
        if c.get("voice") not in voices.VOICES:
            bad.append(f"{who}'s voice {c.get('voice')!r} is not one of {', '.join(voices.VOICES)}")
    boards = doc.get("boards") or {}
    for si, sc in enumerate(doc.get("scenes") or []):
        name = sc.get("scene")
        if name not in vocab.SCENES:
            bad.append(f"scene {si + 1}: there is no set called {name!r}; "
                       f"the sets are {', '.join(vocab.SCENES)}")
        elif sc.get("time") not in vocab.SCENES[name]:
            bad.append(f"scene {si + 1}: {name} can be {', '.join(vocab.SCENES[name])}, "
                       f"not {sc.get('time')!r}")
        for bi, b in enumerate(sc.get("beats") or []):
            where = f"scene {si + 1} beat {bi + 1}"
            who, text = _line(b, cast)
            if who is None and "do" not in b:
                bad.append(f"{where}: neither a line nor a `do`")
                continue
            if who and not text.strip():
                bad.append(f"{where}: {who} says nothing")
            if "do" in b and b["do"] not in vocab.DOS:
                bad.append(f"{where}: `do: {b['do']}` is not one of {', '.join(vocab.DOS)}")
            if b.get("act") and b["act"] not in vocab.ACTS:
                bad.append(f"{where}: `act: {b['act']}` is not one of {', '.join(vocab.ACTS)}")
            if b.get("mood") and b["mood"] not in moods.MOODS:
                bad.append(f"{where}: `mood: {b['mood']}` is not one of {', '.join(moods.MOODS)}")
            if b.get("do") == "vision" and b.get("vision") not in vocab.VISIONS:
                bad.append(f"{where}: vision {b.get('vision')!r} is not one of {', '.join(vocab.VISIONS)}")
            for key in ("target",):
                if key in b and b[key] not in boards:
                    bad.append(f"{where}: {key} {b[key]!r} is not a board")
            wr = (b.get("board") or {}).get("write")
            if wr and wr not in boards:
                bad.append(f"{where}: board {wr!r} is not defined under `boards`")
            if who is None and not b.get("seconds"):
                bad.append(f"{where}: a `do` beat needs `seconds`")
    return bad


def beats(doc: dict) -> list[dict]:
    """Every beat in order, each carrying its scene and a stable id.

    The id hashes what the beat is, not where it is, so moving a line leaves
    its narration cached.
    """
    cast = doc.get("cast") or {}
    out = []
    for si, sc in enumerate(doc["scenes"]):
        for b in sc.get("beats") or []:
            who, text = _line(b, cast)
            beat = dict(scene=sc["scene"], time=sc["time"], scene_index=si,
                        who=who, text=text,
                        voice=(cast.get(who) or {}).get("voice") if who else None,
                        do=b.get("do"), act=b.get("act"),
                        mood=b.get("mood") or "neutral",
                        board=(b.get("board") or {}).get("write"),
                        target=b.get("target"), vision=b.get("vision"),
                        card=b.get("card"), seconds=b.get("seconds"),
                        delivery=b.get("delivery"))
            key = json.dumps({k: beat[k] for k in ("who", "text", "voice", "mood", "delivery", "do")},
                             sort_keys=True)
            beat["id"] = hashlib.sha256(key.encode()).hexdigest()[:10]
            out.append(beat)
    for i, b in enumerate(out):
        b["index"] = i
    return out


def summary(doc: dict) -> str:
    bs = beats(doc)
    lines = [b for b in bs if b["who"]]
    words = sum(len(b["text"].split()) for b in lines)
    silent = sum(float(b["seconds"] or 0) for b in bs if not b["who"])
    by = {}
    for b in lines:
        by[b["who"]] = by.get(b["who"], 0) + 1
    return (f"{doc.get('title')}: {len(bs)} beats, {len(lines)} lines "
            f"({', '.join(f'{k} {v}' for k, v in by.items())}), {words} words, "
            f"about {words / 2.4 + silent:.0f} s")
