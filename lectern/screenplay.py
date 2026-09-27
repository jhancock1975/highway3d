"""Render a lecture document as a script somebody can actually read.

    lectern/.mcpvenv/bin/python -m lectern.screenplay \
        --script scripts/relativity.yaml --out scripts/relativity.md

Generated from the document, never written beside it. The YAML is what
renders; a second copy kept by hand would disagree with it within a day,
which is the failure this project has already paid for once with its
demonstration lists. Edit the YAML, regenerate this, read this.

It shows what is said, how it is said, what is on screen while it is said,
and what he does with himself -- including the staging the renderer infers
rather than reads, so that what you review is what will actually be shot.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lectern import script as S  # noqa: E402

# How each delivery reads, in words rather than multipliers.
SAID = {
    "plain":  "",
    "open":   "opening up, slower",
    "build":  "pressing on, quicker",
    "aside":  "thrown away, quieter",
    "punch":  "slowed down, let to land",
    "weight": "lower, deliberate",
    "wry":    "dry",
}

WPM = 138.0


def seconds_of(text: str) -> float:
    return len(text.split()) / WPM * 60.0


def staging(seg: dict, secs: float) -> list[str]:
    """What is on screen, and what he does, including what is inferred."""
    kind = next(iter(seg["stage"]), "")
    body = seg["stage"].get(kind)
    out = []
    if kind == "card":
        out.append(f"TITLE CARD — {body.get('title','')}"
                   + (f" / {body['subtitle']}" if body.get("subtitle") else ""))
    elif kind == "board":
        out.append("BOARD — " + body.get("heading", ""))
        for it in body.get("items", []):
            out.append(f"    · {it}")
    elif kind == "note":
        out.append("BOARD — " + body.get("heading", ""))
        for ln in body.get("lines", []):
            out.append(f"    · {ln}")
    elif kind == "demo":
        out.append(f"DEMONSTRATION — {body}, staged beside him on a plinth")
    elif kind == "scene":
        out.append(f"CUTAWAY — {body}. He is not in frame; this is voice-over.")

    if kind in ("card", "board", "note"):
        if secs >= 12.0:
            out.append("    He crosses to the board, indicates two of the "
                       "lines, and comes back.")
        else:
            out.append("    He stays where he is; the shot is too short to "
                       "cross the room and back.")
    if seg.get("beat"):
        out.append(f"    Opening gesture: {seg['beat']}.")
    return out


def render(doc: dict) -> str:
    segs = S.segments(doc)
    total = sum(seconds_of(s["say"]) for s in segs)
    music = doc.get("music")
    lines = [f"# {doc['title']}", ""]
    lines.append(f"{len(doc['chapters'])} chapters · {len(segs)} segments · "
                 f"{S.word_count(doc)} words · about "
                 f"{S.estimate_minutes(doc):.0f} minutes")
    lines.append("")
    lines.append(f"**Presenter** {doc['presenter']} · "
                 f"**voice** {doc['voice']['preset']} at "
                 f"{doc['voice']['speed']}× · "
                 f"**music** " + (f"{music['mood']} at {music['level']}"
                                  if music else "none"))
    lines.append("")
    lines.append("Generated from `" + os.path.basename(doc.get("source", "")) +
                 "`. Edit the document, not this.")
    lines.append("")

    chapter = None
    for seg in segs:
        if seg["chapter"] != chapter:
            chapter = seg["chapter"]
            lines += ["", f"## {chapter + 1}. {seg['chapter_title']}", ""]
        secs = seconds_of(seg["say"])
        how = SAID.get(seg["delivery"], seg["delivery"])
        head = f"**{seg['index']}**  ·  ~{secs:.0f}s"
        if how:
            head += f"  ·  _{how}_"
        lines.append(head)
        lines.append("")
        lines.append("> " + seg["say"].replace("\n", " ").strip())
        lines.append("")
        for row in staging(seg, secs):
            lines.append("`" + row + "`" if not row.startswith("    ")
                         else "  " + row.strip())
        lines.append("")
    lines.append("")
    lines.append(f"_Total spoken: about {total / 60:.1f} minutes, before "
                 f"pauses and settle beats._")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    doc = S.load(a.script)
    text = render(doc)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(text)
        print(f"wrote {a.out} ({len(text.split())} words)")
    else:
        print(text)


if __name__ == "__main__":
    main()
