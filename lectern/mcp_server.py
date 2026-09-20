"""MCP server in front of the lecture renderer.

    lectern/.mcpvenv/bin/python -m lectern.mcp_server --port 8767

Written against a specific client rather than in the abstract. Cider ships no
Python interpreter and does not run one, so the boundary is a process
boundary: this runs where it was built and speaks MCP over HTTP, and Cider
connects as a client. Three things follow from reading its `ToolServers.swift`,
and they shape every tool below.

**Twenty minutes is the ceiling.** `ToolServer.timeout` defaults to 1200s and
sets both the request and the resource timeout. A full lecture is about twelve
hours of Cycles. So rendering is a job: `lecture_render` starts it and returns
at once, and `lecture_status` is asked afterwards. Nothing here blocks on
anything long.

**The caller may be a small model.** Cider runs a 27B on-device with a couple
of thousand tokens to think in. Handing it one argument containing eighty-two
segments is not an interface it can use, so a lecture can be built a few
hundred tokens at a time. A client with room to spare passes the whole
document in one call instead.

**Answers are sentences.** A result reaches the model as prose through its
`notePreamble`, and a failure comes back as words rather than a throw, because
a throw reads to that client as "no tool ran" and says nothing at all.

Every name is prefixed `lecture_`: local names win a collision there, so a
tool called something Cider already uses would simply be ignored.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from typing import Annotated, Literal

from pydantic import Field

from mcp.server.mcpserver import MCPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lectern import script as S  # noqa: E402

LECTURES = os.environ.get("LECTERN_DIR", os.path.join(HERE, "lectures"))
RENDERS = os.environ.get("LECTERN_RENDERS", os.path.join(HERE, "renders"))
WORK = os.environ.get("LECTERN_WORK", os.path.join(HERE, ".work"))

PRESENTERS = {
    "einstein": "A caricature of Einstein: wild white hair, walrus moustache, "
                "cardigan. Speaks English with a German accent in a voice "
                "blended from several so it belongs to nobody.",
}
LOOKS = {
    "study": "A warm panelled room with a chalkboard. Key light from the "
             "left, cool rim from behind.",
    "void":  "Cold empty space with a single rim light. For when the "
             "demonstration should be the only thing present.",
}

mcp = MCPServer(
    name="lectern",
    title="Narrated lecture renderer",
    version="1.0.0",
    instructions=(
        "Renders narrated lecture videos: a 3D presenter who speaks, gestures "
        "and stages physical demonstrations, with animated notation on a "
        "chalkboard. Call lecture_describe first for the catalogue of "
        "presenters, demonstrations and looks. Build a lecture with "
        "lecture_new and lecture_add, or hand over a whole document with "
        "lecture_define. Rendering is a background job: lecture_render starts "
        "it and returns immediately, and lecture_status reports progress."
    ),
)

_jobs: dict[str, dict] = {}


def _path(lecture_id: str) -> str:
    safe = "".join(c for c in lecture_id if c.isalnum() or c in "-_")
    return os.path.join(LECTURES, f"{safe}.yaml")


def _load(lecture_id: str) -> dict:
    p = _path(lecture_id)
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"There is no lecture called '{lecture_id}'. "
            f"Existing ones: {', '.join(_list_ids()) or 'none yet'}.")
    return S.load(p)


def _save(lecture_id: str, doc: dict) -> None:
    import yaml
    os.makedirs(LECTURES, exist_ok=True)
    body = {k: v for k, v in doc.items() if k != "source"}
    with open(_path(lecture_id), "w") as fh:
        yaml.safe_dump(body, fh, sort_keys=False, allow_unicode=True, width=78)


def _list_ids() -> list[str]:
    if not os.path.isdir(LECTURES):
        return []
    return sorted(f[:-5] for f in os.listdir(LECTURES) if f.endswith(".yaml"))


@mcp.tool()
def lecture_describe() -> str:
    """What this renderer can stage: presenters, demonstrations, looks.

    Call this before writing a lecture. The demonstrations are the ones the
    renderer knows how to build; asking for anything else is refused at
    validation rather than discovered mid-render.
    """
    lines = ["PRESENTERS"]
    for name, why in PRESENTERS.items():
        lines.append(f"  {name}: {why}")
    lines.append("")
    lines.append("LOOKS")
    for name, why in LOOKS.items():
        lines.append(f"  {name}: {why}")
    lines.append("")
    lines.append("STAGE DIRECTIONS (one per segment)")
    lines.append("  card  {title, subtitle}  -- a chapter title")
    lines.append("  board {heading, items}   -- written points on the board")
    lines.append("  note  {heading, lines}   -- notation, written on and morphed")
    lines.append("  demo  <name>             -- a staged demonstration, below")
    lines.append("")
    lines.append("DEMONSTRATIONS")
    for d in S.KNOWN_DEMOS:
        lines.append(f"  {d}")
    lines.append("")
    lines.append(f"EXISTING LECTURES: {', '.join(_list_ids()) or 'none yet'}")
    return "\n".join(lines)


@mcp.tool()
def lecture_new(
    title: Annotated[str, Field(description="What the lecture is called.")],
    lecture_id: Annotated[str, Field(
        description="Short handle to refer to it later, e.g. 'relativity'. "
                    "Letters, digits, dashes.")],
    presenter: Annotated[Literal["einstein"], Field(
        description="Who delivers it.")] = "einstein",
    look: Annotated[Literal["study", "void"], Field(
        description="The set and its lighting.")] = "study",
) -> str:
    """Start an empty lecture. Add segments to it with lecture_add."""
    if lecture_id in _list_ids():
        return (f"A lecture called '{lecture_id}' already exists. Pick another "
                f"handle, or add to that one with lecture_add.")
    doc = S.normalise(dict(title=title, presenter=presenter, look=look,
                           chapters=[]))
    _save(lecture_id, doc)
    return (f"Started '{title}' as '{lecture_id}', {presenter} presenting in "
            f"the {look}. It has no segments yet.")


@mcp.tool()
def lecture_add(
    lecture_id: Annotated[str, Field(description="Which lecture to add to.")],
    say: Annotated[str, Field(
        description="What the presenter says. One or two sentences works "
                    "best; the picture is timed to fit the speech.")],
    chapter: Annotated[str, Field(
        description="Chapter title. Reusing the previous one continues that "
                    "chapter; a new one starts a new chapter.")] = "",
    demo: Annotated[str, Field(
        description="A demonstration to stage while this is said. See "
                    "lecture_describe. Leave empty for none.")] = "",
    note: Annotated[str, Field(
        description="Notation to write on the chalkboard, one expression per "
                    "line, separated by ' | '. Leave empty for none.")] = "",
    points: Annotated[str, Field(
        description="Written points for the board, separated by ' | '. "
                    "Leave empty for none.")] = "",
    heading: Annotated[str, Field(
        description="Heading over the note or the points.")] = "",
    beat: Annotated[str, Field(
        description="What he does with his hands as the segment opens. One "
                    "of: still, beat, point, present, open, count. Leave "
                    "empty for the default, which is present.")] = "",
) -> str:
    """Add one segment. Give exactly one of demo, note or points."""
    try:
        doc = _load(lecture_id)
    except FileNotFoundError as e:
        return str(e)

    given = [k for k, v in (("demo", demo), ("note", note),
                            ("points", points)) if v.strip()]
    if len(given) > 1:
        return (f"Give one of demo, note or points, not {len(given)} "
                f"({', '.join(given)}). A segment shows one thing.")
    if demo.strip():
        if demo.strip() not in S.KNOWN_DEMOS:
            return (f"There is no demonstration called '{demo.strip()}'. "
                    f"Call lecture_describe for the catalogue.")
        stage = {"demo": demo.strip()}
    elif note.strip():
        stage = {"note": {"heading": heading,
                          "lines": [x.strip() for x in note.split("|")
                                    if x.strip()]}}
    elif points.strip():
        stage = {"board": {"heading": heading,
                           "items": [x.strip() for x in points.split("|")
                                     if x.strip()]}}
    else:
        stage = {"card": {"title": heading or doc["title"], "subtitle": ""}}

    title = chapter.strip() or (doc["chapters"][-1]["title"]
                                if doc["chapters"] else "Opening")
    if not doc["chapters"] or doc["chapters"][-1]["title"] != title:
        doc["chapters"].append({"title": title, "segments": []})
    seg = {"say": say}
    if beat.strip():
        if beat.strip() not in S.BEAT_NAMES:
            return (f"There is no beat called '{beat.strip()}'. Use one of: "
                    f"{', '.join(S.BEAT_NAMES)}.")
        seg["beat"] = beat.strip()
    seg["stage"] = stage
    doc["chapters"][-1]["segments"].append(seg)
    _save(lecture_id, doc)

    n = len(S.segments(doc))
    return (f"Added segment {n} to '{doc['title']}' under '{title}'. "
            f"{S.word_count(doc)} words so far, about "
            f"{S.estimate_minutes(doc):.1f} minutes.")


@mcp.tool()
def lecture_define(
    lecture_id: Annotated[str, Field(description="Handle for the lecture.")],
    document: Annotated[str, Field(
        description="The whole lecture as a YAML or JSON document: title, "
                    "presenter, look, and chapters, each with segments "
                    "carrying 'say' and 'stage'. Replaces anything already "
                    "under this handle.")],
) -> str:
    """Hand over a complete lecture in one call, rather than a segment at a time."""
    import yaml
    try:
        doc = S.normalise(yaml.safe_load(document))
    except Exception as e:
        return f"That document could not be read: {e}"
    problems = S.validate(doc)
    if problems:
        return ("The document has problems, so nothing was saved:\n  "
                + "\n  ".join(problems[:12]))
    _save(lecture_id, doc)
    return f"Saved '{lecture_id}'. {S.summary(doc)}"


@mcp.tool()
def lecture_check(
    lecture_id: Annotated[str, Field(description="Which lecture to check.")],
) -> str:
    """Check a lecture is renderable, in seconds rather than hours.

    Worth doing before every render. A single bad stage direction otherwise
    surfaces partway through a twelve-hour job.
    """
    try:
        doc = _load(lecture_id)
    except FileNotFoundError as e:
        return str(e)
    problems = S.validate(doc)
    if problems:
        return (f"{S.summary(doc)}\n\n{len(problems)} problem(s):\n  "
                + "\n  ".join(problems[:20]))
    return f"{S.summary(doc)}\n\nNo problems. Ready to render."


@mcp.tool()
def lecture_render(
    lecture_id: Annotated[str, Field(description="Which lecture to render.")],
    quality: Annotated[Literal["draft", "final"], Field(
        description="draft renders in Eevee in minutes and is for checking "
                    "blocking and timing. final renders in Cycles and takes "
                    "hours -- about twelve for a 24-minute lecture.")] = "draft",
    width: Annotated[int, Field(ge=640, le=3840)] = 1920,
    height: Annotated[int, Field(ge=360, le=2160)] = 1080,
) -> str:
    """Start rendering. Returns at once with a job to ask about later.

    This never waits for the render: a full lecture is far longer than any
    tool call is allowed to take. Ask lecture_status how it is going.
    """
    try:
        doc = _load(lecture_id)
    except FileNotFoundError as e:
        return str(e)
    problems = S.validate(doc)
    if problems:
        return ("Not starting: the lecture has problems that would surface "
                "hours in.\n  " + "\n  ".join(problems[:10]))

    os.makedirs(RENDERS, exist_ok=True)
    job = uuid.uuid4().hex[:6]
    out = os.path.join(RENDERS, f"{lecture_id}-{quality}-{job}.mp4")
    log = os.path.join(WORK, f"job-{job}.log")
    os.makedirs(WORK, exist_ok=True)

    cmd = [sys.executable, "-m", "lectern.build",
           "--script", _path(lecture_id), "--out", out,
           "--quality", quality, "--width", str(width), "--height", str(height),
           "--job", job]
    with open(log, "w") as fh:
        proc = subprocess.Popen(cmd, cwd=HERE, stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)
    _jobs[job] = dict(pid=proc.pid, out=out, log=log, started=time.time(),
                      lecture=lecture_id, quality=quality)

    minutes = S.estimate_minutes(doc)
    hours = minutes * 60 * 24 * (1.25 if quality == "final" else 0.06) / 3600
    return (f"Started rendering '{doc['title']}' at {quality} quality as job "
            f"{job}. About {len(S.segments(doc))} shots, roughly "
            f"{hours:.1f} hours. Ask lecture_status about job {job}; nothing "
            f"is lost if this session ends.")


@mcp.tool()
def lecture_status(
    job: Annotated[str, Field(description="The job id lecture_render gave you.")],
) -> str:
    """How a render is going, or how it finished."""
    info = _jobs.get(job)
    log = info["log"] if info else os.path.join(WORK, f"job-{job}.log")
    if not os.path.exists(log):
        return (f"There is no job {job} on this server. Jobs started before "
                f"it was last restarted are not remembered.")

    tail = ""
    with open(log) as fh:
        lines = [x.strip() for x in fh.readlines() if x.strip()]
    for line in reversed(lines):
        if line.startswith("PROGRESS") or line.startswith("DONE") or \
           line.startswith("FAILED"):
            tail = line
            break

    if tail.startswith("DONE"):
        try:
            d = json.loads(tail[4:])
            return (f"Finished: {d['out']}, {d['minutes']:.1f} minutes, "
                    f"{d['shots']} shots, {d['bytes'] / 1e6:.0f} MB, "
                    f"took {d['hours']:.1f} hours.")
        except Exception:
            return f"Finished. {tail}"
    if tail.startswith("FAILED"):
        return f"That render stopped: {tail[6:].strip()}"
    if tail.startswith("PROGRESS"):
        try:
            d = json.loads(tail[8:])
            left = d.get("eta_hours")
            eta = f", about {left:.1f} hours to go" if left else ""
            return (f"{d['stage']}: {d['done']} of {d['total']}{eta}.")
        except Exception:
            return tail
    return (f"Job {job} has started but not reported yet "
            f"({len(lines)} lines of log).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--path", default="/mcp")
    a = ap.parse_args()
    for d in (LECTURES, RENDERS, WORK):
        os.makedirs(d, exist_ok=True)
    print(f"lectern MCP on http://{a.host}:{a.port}{a.path} -> {RENDERS}",
          flush=True)
    import anyio
    anyio.run(lambda: mcp.run_streamable_http_async(
        host=a.host, port=a.port, streamable_http_path=a.path))


if __name__ == "__main__":
    main()
