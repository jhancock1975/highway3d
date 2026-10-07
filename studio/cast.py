"""The cast: each character's fixed description and the still that shows them best.

A character described afresh in every prompt, and painted from nothing every time, comes out a
different person in each shot. So a character is cast once, with the words that describe them
and the picture that shows them best, and every picture or animation that names them is given
those same words, word for word, and starts from that same picture. Kept in
$STUDIO_WORK/cast.json, so it lasts as long as the library does. Names are not case-sensitive.
"""

from __future__ import annotations

import json
import os

from studio import library

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path() -> str:
    return os.path.join(os.environ.get("STUDIO_WORK") or os.path.join(HERE, "studio", ".work"), "cast.json")


def load() -> dict:
    try:
        with open(_path()) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save(name: str, description: str, picture: str | None = None) -> dict:
    """Cast a character, or recast one: their description, and the still that shows them best."""
    name, description = (name or "").strip(), " ".join((description or "").split())
    if not name or not description:
        raise ValueError("a character needs a name and a description")
    if picture:
        note = library.get(picture.strip())
        if note["kind"] != "image":
            raise ValueError(f"{picture} is a {note['kind']}; a character's still must be a picture")
        picture = note["id"]
    everyone = load()
    member = {"name": name, "description": description.rstrip("."), "picture": picture or None}
    if not picture and name.lower() in everyone:
        member["picture"] = everyone[name.lower()].get("picture")      # keep their still when only the words change
    everyone[name.lower()] = member
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    with open(_path(), "w") as fh:
        json.dump(everyone, fh, indent=1)
    return member


def members(names) -> list[dict]:
    """The named characters, in the order named; a name not in the cast is an error that lists it."""
    everyone, out, missing = load(), [], []
    for n in names or []:
        m = everyone.get(str(n).strip().lower())
        (out.append(m) if m else missing.append(str(n).strip()))
    if missing:
        who = ", ".join(m["name"] for m in everyone.values()) or "nobody yet"
        raise ValueError(f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not in the cast "
                         f"(the cast: {who}); cast them first with studio_cast")
    return out


def prompt(names, text: str) -> str:
    """`text`, led by each named character's description, word for word."""
    lead = " ".join(f"{m['name']}: {m['description']}." for m in members(names))
    return f"{lead} {text}".strip() if lead else text


def pictures(names) -> list[str]:
    """The stills of the named characters who have one, in the order named."""
    return [m["picture"] for m in members(names) if m.get("picture")]


def said(member: dict) -> str:
    still = f" ({member['picture']})" if member.get("picture") else " (no still yet)"
    return f"{member['name']}{still}: {member['description']}"
