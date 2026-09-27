"""A bad argument is mended and said, not refused. No server, no renders.

    lectern/.mcpvenv/bin/python test_forgiving.py

The case that found it: Cider's 27B asked lecture_make for quality "high",
which is not draft or final, and got a pydantic error instead of a video.
"""

import sys
from typing import Annotated, Literal

import anyio
from pydantic import Field

from forgiving import ForgivingServer

mcp = ForgivingServer(name="toy")


@mcp.tool()
def make(
    topic: Annotated[str, Field(description="What it is about.")],
    minutes: Annotated[float, Field(ge=0.5, le=15)] = 2.0,
    quality: Annotated[Literal["draft", "final"], Field()] = "draft",
    samples: Annotated[int, Field(ge=8, le=256)] = 64,
) -> str:
    return f"{topic}, {minutes:g} minutes, {quality}, {samples} samples."


def call(**arguments):
    r = anyio.run(lambda: mcp.call_tool("make", arguments))
    return r.content[0].text, r.is_error, r.structured_content


def test_good_call_untouched():
    text, bad, _ = call(topic="sky", minutes=1, quality="final")
    assert not bad and text == "sky, 1 minutes, final, 64 samples.", text


def test_unknown_choice_falls_back_and_says_so():
    text, bad, structured = call(topic="black holes", minutes=5, quality="high")
    assert not bad, text
    assert text.endswith("black holes, 5 minutes, draft, 64 samples."), text
    assert "quality 'high' is not one of draft, final, so it is draft." in text, text
    assert structured["result"] == text, structured


def test_out_of_range_is_clamped_and_said():
    text, bad, _ = call(topic="sky", minutes=20, samples=2)
    assert not bad, text
    assert text.endswith("sky, 15 minutes, draft, 8 samples."), text
    assert "minutes 20 is more than this tool allows, so it is 15" in text, text
    assert "samples 2 is less than this tool allows, so it is 8" in text, text


def test_wrong_type_with_a_default_falls_back():
    text, bad, _ = call(topic="sky", minutes="five")
    assert not bad, text
    assert text.endswith("sky, 2 minutes, draft, 64 samples."), text


def test_missing_required_is_one_sentence():
    text, bad, _ = call(minutes=3)
    assert bad
    assert text == "make did not run: it needs topic.", text


def test_lecture_make_high_quality():
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lectern import author, mcp_server as M
    seen = {}
    real = author.write, M._start, M._save
    author.write = lambda topic, minutes: {"title": topic, "chapters": []}
    M._save = lambda *a: None
    M._start = lambda lecture_id, doc, quality: seen.setdefault("q", quality) and "Started."
    M.S.summary, summary = (lambda doc: "0 segments"), M.S.summary
    try:
        r = anyio.run(lambda: M.mcp.call_tool("lecture_make", {
            "topic": "black holes", "minutes": 5, "quality": "high"}))
    finally:
        author.write, M._start, M._save = real
        M.S.summary = summary
    text = r.content[0].text
    assert not r.is_error, text
    assert seen["q"] == "draft", seen
    assert text.startswith("quality 'high' is not one of draft, final, so it is draft."), text


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
