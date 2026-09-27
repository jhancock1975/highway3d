"""The studio's tools, called in-process the way a client calls them.

    studio/.venv/bin/python studio/test_server.py

Nothing heavy runs: no speech, no GIMP, no ffmpeg job. Those are Task 10.
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
os.environ["STUDIO_WORK"] = tempfile.mkdtemp(prefix="studio-work-")
os.environ.pop("XAI_API_KEY", None)
import anyio  # noqa: E402
from studio import mcp_server as S  # noqa: E402

TOOLS = {"studio_describe", "studio_import", "studio_speak", "studio_music", "studio_card",
         "studio_picture", "studio_assemble", "studio_status", "studio_list"}


def call(name, **args):
    r = anyio.run(lambda: S.mcp.call_tool(name, args))
    return r.content[0].text


def test_nine_tools_every_one_prefixed():
    names = {t.name for t in anyio.run(S.mcp.list_tools)}
    assert names == TOOLS, names


def test_descriptions_name_their_values():
    tools = {t.name: t.description for t in anyio.run(S.mcp.list_tools)}
    assert "am_michael" in tools["studio_speak"] and "einstein" in tools["studio_speak"]
    assert all(m in tools["studio_music"] for m in ("drive", "open", "night"))
    assert "dark" in tools["studio_card"] and "chalkboard" in tools["studio_card"]
    assert "16:9" in tools["studio_picture"] and "2k" in tools["studio_picture"]
    assert "dissolve" in tools["studio_assemble"] and "push-in" in tools["studio_assemble"]


def test_describe_has_the_catalogue_and_an_example():
    got = call("studio_describe")
    for word in ("am_michael", "night", "chalkboard", "16:9", '"video"', "captions"):
        assert word in got, word


def test_nothing_of_a_kind_and_no_jobs():
    assert call("studio_list", kind="video") == "There is no video in the library."
    assert call("studio_status") == "Nothing has been assembled on this server yet."


def test_bad_edit_is_refused_with_its_problems():
    got = call("studio_assemble", edit={"video": [{"asset": "clip-0000"}]})
    assert got.startswith("Not starting: the edit has problems."), got
    assert "there is no asset called clip-0000" in got, got


def test_edit_as_json_text():
    got = call("studio_assemble", edit='{"video": ["clip-0000"]}')
    assert "there is no asset called clip-0000" in got, got
    got = call("studio_assemble", edit="{not json")
    assert got.startswith("Not starting: the edit is not JSON"), got


def test_import_failure_is_a_sentence():
    got = call("studio_import", source="/nowhere/at/all.mp4")
    assert got == "Nothing was imported: there is no file at /nowhere/at/all.mp4.", got


def test_picture_without_a_key_is_a_sentence():
    got = call("studio_picture", prompt="a fox")
    assert got == ("No picture was made: No xAI key is set; put XAI_API_KEY in the "
                   "environment the studio server runs in."), got


def test_bad_values_are_mended_not_refused():
    got = call("studio_music", mood="jazz", seconds=2)
    assert got.startswith("mood 'jazz' is not one of drive, open, night, so it is drive."), got
    assert "music-" in got, got


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
