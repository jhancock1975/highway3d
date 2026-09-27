"""MCP server for the studio: general audio and video tools.

    studio/.venv/bin/python -m studio.mcp_server --port 8768

Lectern makes lectures and highway makes highway drives. This makes the
pieces anything else is cut from -- speech, music, cards, pictures,
imported footage -- and cuts them together. A capable agent directs, one
small call at a time. Everything slow is a job, and every answer is a
sentence, because the caller is a model reading prose.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Annotated, Literal

from pydantic import Field

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from forgiving import ForgivingServer  # noqa: E402
from studio import (assemble, images, jobs, library, memory, music,  # noqa: E402
                    speech, timeline, xai)

RENDERS = os.environ.get("STUDIO_RENDERS", os.path.join(HERE, "renders"))

mcp = ForgivingServer(
    name="studio",
    title="Audio and video studio",
    version="1.0.0",
    instructions=(
        "Makes the pieces of a video and cuts them together. studio_speak, "
        "studio_music, studio_card and studio_picture make assets; "
        "studio_import brings in footage, pictures and sound by path or URL. "
        "Each returns an id. studio_assemble cuts ids together into an mp4 "
        "(or an m4a with no video) as a job, and studio_status says how it "
        "is going. studio_describe has the full edit format and an example."
    ),
)

EXAMPLE = {
    "size": "1920x1080", "fps": 30, "name": "pockterm-spot",
    "video": [{"asset": "card-1a2b", "seconds": 3},
              {"asset": "clip-9c01", "from": 12, "seconds": 6, "transition": "dissolve"},
              {"asset": "pic-44d0", "seconds": 5, "move": "push-in", "transition": "fade"}],
    "overlays": [{"asset": "card-7d3e", "at": 4, "seconds": 3, "place": "bottom"},
                 {"captions": "voice-3f2a"}],
    "audio": [{"asset": "voice-3f2a", "at": 0.5},
              {"asset": "music-77e1", "level": 0.15, "duck": True}],
}


def _sentence(e: BaseException) -> str:
    msg = str(e.args[0]) if getattr(e, "args", None) else str(e)
    return msg.rstrip(". ") + "."


def _wait(seconds: float) -> str:
    if seconds < 90:
        return f"about {max(5, round(seconds / 5) * 5):.0f} seconds"
    return f"about {round(seconds / 60):.0f} minutes"


@mcp.tool()
def studio_describe() -> str:
    """What the studio can make, and the edit format studio_assemble takes, with a worked example."""
    return "\n".join([
        "VOICES (studio_speak): am_michael and am_onyx (American men), af_heart and "
        "af_nova (American women), bm_george (British man), bf_emma (British woman), "
        "einstein (the lecture professor's German-accented voice).",
        f"MOODS (studio_music): {', '.join(music.MOODS)}.",
        f"CARD STYLES (studio_card): {', '.join(images.STYLES)}.",
        f"PICTURES (studio_picture, xAI {xai.MODEL}): aspect {', '.join(xai.ASPECTS)}; "
        f"resolution {', '.join(xai.RESOLUTIONS)}; up to 5 reference pictures.",
        "",
        "EDIT FORMAT (studio_assemble):",
        "  size WxH (default 1920x1080), fps (default 30), name.",
        "  video: a list played in order. Each item: asset (id or file path), seconds "
        "(stills default 4, clips run to their end), from (where in a clip to start), "
        f"transition ({', '.join(timeline.TRANSITIONS)}; 0.5 s), fit "
        f"({', '.join(timeline.FITS)}), move for stills ({', '.join(timeline.MOVES)}), "
        "level (the clip's own sound, 0 to 1).",
        f"  overlays: timed pictures {{asset, at, seconds, place: {', '.join(timeline.PLACES)}}}, "
        "or {captions: a speech id} to show its words as they are said.",
        "  audio: timed sound {asset, at, level 0 to 1, fade seconds, duck: true to dip "
        "under speech}. Music fades by default and is trimmed to the video.",
        "  With no video, the edit makes an m4a.",
        "",
        "EXAMPLE:",
        json.dumps(EXAMPLE, indent=1),
    ])


@mcp.tool()
def studio_import(
    source: Annotated[str, Field(description="A file path on this Mac, or an http(s) URL.")],
    name: Annotated[str, Field(description="A label for studio_list; edits still use the id.")] = "",
) -> str:
    """Bring a video, picture or sound into the library from a path on this Mac or a URL. Returns its id, what it is, and where the file is."""
    try:
        return library.said(library.import_(source, name)) + "."
    except Exception as e:
        return f"Nothing was imported: {_sentence(e)}"


@mcp.tool()
def studio_speak(
    text: Annotated[str, Field(description="What to say.")],
    voice: Annotated[Literal[speech.VOICES], Field(description="Who says it.")] = "am_michael",
    speed: Annotated[float, Field(ge=0.5, le=2.0, description="1 is natural pace.")] = 1.0,
) -> str:
    """Say text aloud and keep it as a sound, with every word's timing for captions. voice is am_michael (American man, the default), am_onyx (American man, deeper), af_heart or af_nova (American women), bm_george (British man), bf_emma (British woman) or einstein (the lecture professor's German-accented voice); speed is 0.5 to 2, 1 by default."""
    try:
        note = speech.speak(text, voice, speed)
    except Exception as e:
        return f"No speech was made: {_sentence(e)}"
    return f"{library.said(note)}. {len(note['words'])} words, timed for captions."


@mcp.tool()
def studio_music(
    mood: Annotated[Literal[music.MOODS], Field(description="The feel of the bed.")] = "drive",
    seconds: Annotated[float, Field(ge=1, le=600, description="How long.")] = 30.0,
) -> str:
    """Compose a music bed exactly as long as asked. mood is drive (patient, minor, the default), open (brighter, more motion) or night (sparse, almost no rhythm, best under speech); seconds is 1 to 600, 30 by default."""
    try:
        return library.said(music.compose(mood, seconds)) + "."
    except Exception as e:
        return f"No music was made: {_sentence(e)}"


@mcp.tool()
def studio_card(
    title: Annotated[str, Field(description="The main line.")],
    subtitle: Annotated[str, Field(description="A smaller second line.")] = "",
    style: Annotated[Literal[images.STYLES], Field(description="The look.")] = "dark",
    width: Annotated[int, Field(ge=64, le=7680)] = 1920,
    height: Annotated[int, Field(ge=64, le=4320)] = 1080,
) -> str:
    """Draw a text card with GIMP: title cards, lower thirds, signs, end slates. style is dark (the default), light, chalkboard or sign (a green highway sign); width and height default to 1920x1080 (a lower third might be 1600x200)."""
    try:
        return library.said(images.card(title, subtitle, style, width, height)) + "."
    except Exception as e:
        return f"No card was made: {_sentence(e)}"


@mcp.tool()
def studio_picture(
    prompt: Annotated[str, Field(description="What the picture shows.")],
    aspect: Annotated[Literal[xai.ASPECTS], Field(description="Shape of the picture.")] = "16:9",
    resolution: Annotated[Literal[xai.RESOLUTIONS], Field(description="Detail.")] = "2k",
    references: Annotated[list[str], Field(description="Up to 5 picture ids to work from.")] = [],
) -> str:
    """Paint a picture from a description with xAI's image model, paid from prepaid credit. aspect is 16:9 (the default), 9:16, 1:1, 4:3, 3:4, 3:2, 2:3, 21:9 or auto; resolution is 1k, 1.5k or 2k (the default); references are up to 5 picture ids to repaint or work from, such as a card laid out in GIMP."""
    try:
        return library.said(images.picture(prompt, aspect, resolution, references)) + "."
    except Exception as e:
        return f"No picture was made: {_sentence(e)}"


@mcp.tool()
def studio_assemble(
    edit: Annotated[dict | str, Field(
        description="The edit, as an object or JSON text: size, fps, name, video, "
                    "overlays, audio. studio_describe has the format and an example.")],
) -> str:
    """Cut clips, pictures, cards, captions, voice and music together into one mp4, or an m4a when there is no video. Starts a job and returns at once. video is a list played in order: {asset, seconds, from, transition: cut, dissolve or fade, fit: cover or contain, move for stills: none, push-in, pull-out, pan-left or pan-right}. overlays are timed pictures {asset, at, seconds, place} or {captions: a speech id}. audio is timed sound {asset, at, level 0 to 1, fade, duck}. Assets are ids or file paths."""
    if isinstance(edit, str):
        try:
            edit = json.loads(edit)
        except ValueError as e:
            return f"Not starting: the edit is not JSON ({e})."
    if not isinstance(edit, dict):
        return "Not starting: the edit must be an object."
    plan, problems = timeline.normalise(edit, library.resolve)
    if problems:
        return ("Not starting: the edit has problems.\n  "
                + "\n  ".join(problems[:15]))
    refused = memory.refusal("assembly")
    if refused:
        return f"Not starting: {refused}"
    job = jobs.new()
    out = os.path.join(RENDERS, f"{plan['name']}-{job}"
                       + (".m4a" if plan["audio_only"] else ".mp4"))
    os.makedirs(RENDERS, exist_ok=True)
    os.makedirs(jobs.WORK, exist_ok=True)
    plan_path = os.path.join(jobs.WORK, f"plan-{job}.json")
    with open(plan_path, "w") as fh:
        json.dump(plan, fh)
    jobs.start(job, "studio.assemble", ["--plan", plan_path, "--out", out],
               dict(name=plan["name"], out=out))
    what = ("sound" if plan["audio_only"]
            else f"{plan['width']}x{plan['height']} video")
    return (f"Started assembling '{plan['name']}' as job {job}: "
            f"{plan['seconds']:.1f} seconds of {what}, "
            f"{_wait(assemble.estimate(plan))}. It will be written to {out}. "
            f"Nothing announces when it finishes. studio_status says how it "
            f"is going whenever it is asked, with or without the job id.")


@mcp.tool()
def studio_status(
    job: Annotated[str, Field(description="The job id studio_assemble gave. "
                                          "Leave it out for the most recent.")] = "",
) -> str:
    """How an assembly is going, or how it finished. With no job id, the most recent one, and any others still running."""
    return jobs.status(job)


@mcp.tool()
def studio_list(
    kind: Annotated[Literal["", "video", "image", "audio"], Field(
        description="Only this kind; empty for everything.")] = "",
) -> str:
    """What is in the library, newest first: every id with what it is and where its file is. kind is video, image or audio, or empty (the default) for everything."""
    notes = library.listing(kind)
    if not notes:
        return "The library is empty." if not kind else f"There is no {kind} in the library."
    lines = [library.said(n) for n in notes[:50]]
    if len(notes) > 50:
        lines.append(f"...and {len(notes) - 50} older.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8768)
    ap.add_argument("--path", default="/mcp")
    a = ap.parse_args()
    print(f"studio MCP on http://{a.host}:{a.port}{a.path} -> {RENDERS}",
          flush=True)
    import anyio
    anyio.run(lambda: mcp.run_streamable_http_async(
        host=a.host, port=a.port, streamable_http_path=a.path))


if __name__ == "__main__":
    main()
