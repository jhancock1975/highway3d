"""Pictures for the studio: cards GIMP draws, and pictures xAI paints.

A card is text laid out on a plain ground -- title cards, lower thirds,
signs, end slates -- drawn by GIMP with no window open. Captions are drawn
the same way, by assemble.py, in one GIMP session with the rest of an
edit's text, because GIMP takes seconds to start and an edit can need
thirty captions.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

from studio import library, memory, xai
from studio.errors import last_line

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIMP = os.environ.get("STUDIO_GIMP",
                      "/Applications/GIMP.app/Contents/MacOS/gimp-console-3.2")
DRAW = os.path.join(HERE, "studio", "gimp_draw.py")
STYLES = ("dark", "light", "chalkboard", "sign")


def draw(jobs: list[dict]) -> None:
    """Draw every card and caption in `jobs`, in one GIMP session."""
    if not jobs:
        return
    refused = memory.refusal("gimp")
    if refused:
        raise MemoryError(refused)
    if not os.path.exists(GIMP):
        raise RuntimeError("GIMP is not installed here; brew install --cask gimp")
    fd, spec = tempfile.mkstemp(prefix="studio-draw-", suffix=".json")
    os.close(fd)
    try:
        with open(spec, "w") as fh:
            json.dump(jobs, fh)
        expr = f"STUDIO_JOBS = {spec!r}; exec(open({DRAW!r}).read())"
        r = subprocess.run([GIMP, "-i", "--batch-interpreter=python-fu-eval",
                            "-b", expr, "--quit"], capture_output=True,
                           text=True, timeout=900)
    finally:
        os.remove(spec)
    missing = [j["out"] for j in jobs if not os.path.exists(j["out"])]
    if missing:
        raise RuntimeError(f"GIMP drew {len(jobs) - len(missing)} of "
                           f"{len(jobs)} pictures: "
                           + last_line(r.stdout + "\n" + r.stderr))


def card(title: str, subtitle: str = "", style: str = "dark",
         width: int = 1920, height: int = 1080) -> dict:
    """A card drawn by GIMP, filed in the library."""
    if not title.strip():
        raise ValueError("a card needs a title")
    if style not in STYLES:
        raise ValueError(f"there is no style called {style}; the styles are "
                         f"{', '.join(STYLES)}")
    tmp = tempfile.mkdtemp(prefix="studio-card-")
    out = os.path.join(tmp, "card.png")
    draw([dict(kind="card", out=out, width=int(width), height=int(height),
               style=style, title=title, subtitle=subtitle)])
    note = library.add(out, "card", source=f"card: {style}", move=True,
                       title=title, subtitle=subtitle, style=style)
    os.rmdir(tmp)
    return note


def picture(prompt: str, aspect: str = "16:9", resolution: str = "2k",
            references=()) -> dict:
    """A picture from xAI, filed in the library."""
    if not prompt.strip():
        raise ValueError("a picture needs a prompt")
    if len(references) > 5:
        raise ValueError("xAI takes at most 5 reference pictures")
    paths = []
    for ref in references:
        note = library.resolve(ref)
        if note["kind"] != "image":
            raise ValueError(f"{ref} is {note['kind']}, and references must "
                             f"be pictures")
        paths.append(note["path"])
    data = xai.image(prompt, aspect, resolution, paths)
    fd, out = tempfile.mkstemp(prefix="studio-pic-", suffix=xai.extension(data))
    os.close(fd)
    with open(out, "wb") as fh:
        fh.write(data)
    return library.add(out, "pic", source=f"xai: {xai.MODEL}", move=True,
                       prompt=prompt, aspect=aspect, resolution=resolution,
                       references=list(references))
