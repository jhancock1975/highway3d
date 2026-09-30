"""MCP server for cartoons: a dialogue between characters, made into a film.

    cartoon/.venv/bin/python -m cartoon.mcp_server --port 8769

An agent writes a document -- who says what, in what mood, doing what, with
what on the slate -- checks it, saves it, and asks for the film. The film is
a job (a final render is hours); cartoon_status says how far it has got.
Every answer is a sentence, because the caller is a model reading prose.
Tools are prefixed cartoon_ so they cannot collide with a client's own.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from typing import Annotated, Literal

import yaml
from pydantic import Field

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from forgiving import ForgivingServer  # noqa: E402
from cartoon import moods, script, vocab, voices  # noqa: E402

SCRIPTS = os.path.join(HERE, "scripts")
RENDERS = os.path.join(HERE, "renders")
WORK = os.path.join(HERE, ".work", "cartoon")
PY = os.path.join(HERE, "cartoon", ".venv", "bin", "python")

mcp = ForgivingServer(
    name="cartoon",
    title="Cartoon studio",
    version="1.0.0",
    instructions=(
        "Makes an animated cartoon from a written dialogue. cartoon_describe "
        "explains the document and lists the characters, moods, acts and "
        "visions it may use. cartoon_check reads a document and says what is "
        "wrong with it; cartoon_save files it under a name; cartoon_make "
        "renders it as a job, and cartoon_status says how it is going. "
        "cartoon_list shows the documents and finished films."
    ),
)

EXAMPLE = """title: The Flavor of Nothing
cast:
  euler:    {character: euler,    voice: euler}
  cinnamon: {character: cinnamon, voice: cinnamon}
boards:
  basel: '1 + \\\\tfrac{1}{4} + \\\\tfrac{1}{9} + \\\\cdots'
scenes:
  - scene: study
    time: night
    beats:
      - euler: "One. Plus a quarter. Plus a ninth."
        act: write
        board: {write: basel}
        mood: absorbed
      - do: window_opens
        seconds: 3.5
      - cinnamon: "Somebody in here is cooking numbers."
        act: sniff
        mood: curious
      - do: lick
        target: basel
        seconds: 2.4
      - do: vision
        vision: basel
        seconds: 6
"""


def _sentence(e: BaseException) -> str:
    s = str(e).strip() or e.__class__.__name__
    return s[0].upper() + s[1:] if s else s


def _path(name: str) -> str:
    name = os.path.basename(name.strip())
    if not name.endswith(".yaml"):
        name += ".yaml"
    return os.path.join(SCRIPTS, name)


@mcp.tool()
def cartoon_describe() -> str:
    """The document format, with an example, and every name a document may use: characters and voices, scenes, moods, acts, wordless beats and visions."""
    lines = [
        "A cartoon document is YAML. `cast` maps each speaker to a character and a voice; `boards` names the "
        "formulas that can be written on the slate (LaTeX); `scenes` is a list, each with `scene`, `time` and "
        "`beats`. A beat is either a line (`<speaker>: \"words\"`, optionally `act`, `mood`, `board: {write: "
        "<board>}`, `delivery: aside`) or a wordless `do:` with `seconds` (and `target` for a lick, `vision` "
        "for a vision, `card` for a title card).",
        "Timing comes from the speech: every line lasts as long as it is measured to take. Cameras are chosen "
        "by the planner; nobody has to direct.",
        f"Voices: {', '.join(voices.VOICES)}. Characters on screen: euler, cinnamon.",
        "Scenes: " + "; ".join(f"{k} ({' or '.join(v)})" for k, v in vocab.SCENES.items()) + ".",
        f"Moods: {', '.join(moods.MOODS)}.",
        "Acts (what a speaker's body does on its line): " + "; ".join(f"{k} -- {v}" for k, v in vocab.ACTS.items()) + ".",
        "Wordless beats: " + "; ".join(f"{k} -- {v}" for k, v in vocab.DOS.items()) + ".",
        "Visions: " + "; ".join(f"{k} -- {v}" for k, v in vocab.VISIONS.items()) + ".",
        "Example:\n" + EXAMPLE,
    ]
    return "\n\n".join(lines)


@mcp.tool()
def cartoon_check(
    document: Annotated[str, Field(description="The document as YAML text, or the name of a saved one.")],
) -> str:
    """Read a document and say what is wrong with it, or, if nothing is, how long it will run and who says how much."""
    try:
        if "\n" not in document and os.path.exists(_path(document)):
            doc = script.load(_path(document))
        else:
            doc = yaml.safe_load(document)
        if not isinstance(doc, dict):
            return "That is not a document: it should be YAML with cast, boards and scenes."
        bad = script.validate(doc)
        if bad:
            return "It needs fixing: " + " ".join(b[0].upper() + b[1:] + "." for b in bad)
        return "It is ready. " + script.summary(doc) + "."
    except Exception as e:
        return "It could not be read: " + _sentence(e)


@mcp.tool()
def cartoon_save(
    name: Annotated[str, Field(description="A short file name, like the-flavor-of-nothing.")],
    document: Annotated[str, Field(description="The document as YAML text.")],
) -> str:
    """Check a document and, if it is sound, save it under a name in scripts/ so cartoon_make can render it."""
    try:
        doc = yaml.safe_load(document)
        bad = script.validate(doc) if isinstance(doc, dict) else ["it is not YAML with cast, boards and scenes"]
        if bad:
            return "Not saved, it needs fixing: " + " ".join(b[0].upper() + b[1:] + "." for b in bad)
        p = _path(name)
        with open(p, "w") as fh:
            fh.write(document)
        return f"Saved as {os.path.basename(p)}. " + script.summary(doc) + "."
    except Exception as e:
        return "It could not be saved: " + _sentence(e)


@mcp.tool()
def cartoon_make(
    name: Annotated[str, Field(description="The name of a saved document.")],
    quality: Annotated[Literal["draft", "final"], Field(
        description="draft is 960x540 and quick to look at; final is 1920x1080 and takes hours.")] = "draft",
) -> str:
    """Render a saved document into a film, as a job. Returns at once; cartoon_status says how it is going."""
    p = _path(name)
    if not os.path.exists(p):
        return f"There is no document called {os.path.basename(p)}; cartoon_list shows what there is."
    doc = script.load(p)
    bad = script.validate(doc)
    if bad:
        return "It cannot be made yet: " + " ".join(b[0].upper() + b[1:] + "." for b in bad)
    stem = os.path.splitext(os.path.basename(p))[0]
    work = os.path.join(WORK, stem + ("-draft" if quality == "draft" else ""))
    # One film at a time. Two renders side by side are slower than one after
    # the other, and a second build's music model loading beside a render is
    # how this Mac ran out of memory on 2026-09-26.
    for st in glob.glob(os.path.join(WORK, "*", "status.json")):
        s = json.load(open(st))
        if s.get("step") not in ("done", "failed") and time.time() - s.get("updated", 0) < 1800:
            other = os.path.basename(os.path.dirname(st))
            return (f"{other} is being made right now ({s.get('step')}), and films are made one at a time; "
                    f"cartoon_status says how far it has got. Ask again when it is done.")
    os.makedirs(work, exist_ok=True)
    out = os.path.join(RENDERS, f"{stem}{'-draft' if quality == 'draft' else ''}.mp4")
    args = [PY, "-m", "cartoon.build", "--script", p, "--out", out, "--work", work]
    args += (["--res", "960x540", "--samples", "24"] if quality == "draft" else ["--res", "1920x1080", "--samples", "96"])
    log = open(os.path.join(work, "job.log"), "a")
    subprocess.Popen(args, cwd=HERE, stdout=log, stderr=log, start_new_session=True)
    return (f"Started making {stem} ({quality}). It will be written to {out}. "
            f"cartoon_status with name {stem} says how it is going.")


@mcp.tool()
def cartoon_status(
    name: Annotated[str, Field(description="The document's name. Leave it out for the most recent job.")] = "",
) -> str:
    """How a film is coming along: which step it is on, how many shots and frames are done, and where it was written when finished."""
    paths = glob.glob(os.path.join(WORK, "*", "status.json"))
    if name:
        stem = os.path.splitext(os.path.basename(name))[0]
        paths = [p for p in paths if os.path.basename(os.path.dirname(p)) in (stem, stem + "-draft")]
    if not paths:
        return "Nothing is being made." if not name else f"Nothing has been made of {name} yet."
    p = max(paths, key=os.path.getmtime)
    s = json.load(open(p))
    who = os.path.basename(os.path.dirname(p))
    step = s.get("step")
    if step == "done":
        return f"{who} is finished: {s.get('out')}."
    if step == "failed":
        return f"{who} stopped: {s.get('error')}"
    if step == "render":
        fd, ft = s.get("frames_done", 0), max(1, s.get("frames_total", 1))
        el = time.time() - s.get("started", time.time())
        return (f"{who} is rendering: shot {s.get('shots_done', 0)} of {s.get('shots_total', 0)}, "
                f"{fd} of {ft} frames ({100 * fd / ft:.0f}%), {el / 3600:.1f} hours in.")
    return f"{who} is at the {step} step."


@mcp.tool()
def cartoon_list() -> str:
    """The saved documents and the finished films."""
    docs = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(SCRIPTS, "*.yaml"))
                  if _is_cartoon(p))
    films = sorted(os.path.basename(p) for p in glob.glob(os.path.join(RENDERS, "*.mp4")))
    films = [f for f in films if any(f.startswith(d) for d in docs)]
    out = [f"Documents: {', '.join(docs) if docs else 'none'}."]
    out.append(f"Films: {', '.join(films) if films else 'none yet'}.")
    return " ".join(out)


def _is_cartoon(p):
    try:
        d = script.load(p)
        return isinstance(d, dict) and "cast" in d and "scenes" in d
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8769)
    ap.add_argument("--path", default="/mcp")
    a = ap.parse_args()
    print(f"cartoon MCP on http://{a.host}:{a.port}{a.path}", flush=True)
    import anyio
    anyio.run(lambda: mcp.run_streamable_http_async(host=a.host, port=a.port, streamable_http_path=a.path))


if __name__ == "__main__":
    main()
