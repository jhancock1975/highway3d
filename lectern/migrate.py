"""Turn the old lecture from a program into a document.

    .ttsvenv/bin/python -m lectern.migrate relativity/content.py \
        lectures/relativity.yaml

A one-time import. `relativity/content.py` held the script, the visual
choices and the code that drew them in a single 934-line module, which is
exactly why nothing but that module could ever make a second lecture. The
words and the staging come out here as data; the drawing stays behind in
`lectern`, where every lecture can reach it.

Nothing about the writing changes. The 3,285 words that come out are the
3,285 words that went in.
"""

from __future__ import annotations

import argparse
import os
import sys

import yaml


def convert_visual(v: dict) -> dict:
    """Old visual dict -> new stage directive."""
    kind = v["kind"]
    if kind == "title":
        return {"card": {"title": v["main"], "subtitle": v.get("sub", "")}}
    if kind == "bullets":
        return {"board": {"heading": v.get("heading", ""),
                          "items": list(v["items"])}}
    if kind == "math":
        return {"note": {"heading": v.get("heading", ""),
                         "lines": list(v["lines"])}}
    if kind == "diagram":
        return {"demo": v["name"]}
    raise ValueError(f"unknown visual kind: {kind}")


def convert(content_module) -> dict:
    segments = content_module.all_segments()
    chapters: list[dict] = []
    for seg in segments:
        if seg["first_in_chapter"] or not chapters:
            chapters.append({"title": seg["chapter_title"], "segments": []})
        chapters[-1]["segments"].append({
            "say": seg["text"],
            "stage": convert_visual(seg["visual"]),
        })
    return {
        "title": "Special Relativity",
        "presenter": "einstein",
        "voice": {"preset": "einstein", "speed": 0.94},
        "look": "study",
        "fps": 24,
        "chapters": chapters,
    }


class _Dumper(yaml.SafeDumper):
    """Block scalars for the prose, so a paragraph reads as a paragraph."""


def _str_presenter(dumper, data):
    style = "|" if len(data) > 90 else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_presenter)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("content", help="path to the old content.py")
    ap.add_argument("out", help="path to write the lecture document")
    a = ap.parse_args()

    src = os.path.dirname(os.path.abspath(a.content))
    sys.path.insert(0, src)
    import content  # noqa: E402

    doc = convert(content)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w") as fh:
        yaml.dump(doc, fh, Dumper=_Dumper, sort_keys=False,
                  allow_unicode=True, width=78)

    n_seg = sum(len(c["segments"]) for c in doc["chapters"])
    words = sum(len(s["say"].split()) for c in doc["chapters"]
                for s in c["segments"])
    kinds: dict[str, int] = {}
    for c in doc["chapters"]:
        for s in c["segments"]:
            k = next(iter(s["stage"]))
            kinds[k] = kinds.get(k, 0) + 1
    print(f"{len(doc['chapters'])} chapters, {n_seg} segments, {words} words")
    print("stage kinds:", ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
