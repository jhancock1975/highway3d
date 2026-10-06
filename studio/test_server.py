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
os.environ["STUDIO_COMFY"] = "http://127.0.0.1:9"      # nothing listens: jobs fail fast
os.environ["STUDIO_PICTURES"] = "xai"
import anyio  # noqa: E402
from studio import mcp_server as S  # noqa: E402

TOOLS = {"studio_describe", "studio_import", "studio_speak", "studio_music", "studio_card",
         "studio_picture", "studio_assemble", "studio_status", "studio_list",
         "studio_animate", "studio_extend", "studio_compose"}


def call(name, **args):
    r = anyio.run(lambda: S.mcp.call_tool(name, args))
    return r.content[0].text


def test_every_tool_prefixed():
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


def test_os_errors_and_timeouts_read_as_sentences():
    import subprocess
    missing = FileNotFoundError(2, "No such file or directory", "/x/.ttsvenv/bin/python")
    assert S._sentence(missing) == "No such file or directory: /x/.ttsvenv/bin/python.", S._sentence(missing)
    assert S._sentence(OSError(28, "No space left on device")) == "No space left on device."
    slow = subprocess.TimeoutExpired(["tts", "--text", "a secret script"], 1800)
    assert S._sentence(slow) == "it took longer than 30 minutes and was stopped.", S._sentence(slow)


def test_bad_values_are_mended_not_refused():
    got = call("studio_music", mood="jazz", seconds=2)
    assert got.startswith("mood 'jazz' is not one of drive, open, night, so it is drive."), got
    assert "music-" in got, got


import json  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from studio import library  # noqa: E402


import contextlib  # noqa: E402
from studio import jobs as J  # noqa: E402


@contextlib.contextmanager
def apart():
    """A fresh library and job folder, so these tests leave the shared ones as the others expect."""
    saved = (library.MEDIA, J.WORK, os.environ["STUDIO_MEDIA"], os.environ["STUDIO_WORK"])
    library.MEDIA = os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
    J.WORK = os.environ["STUDIO_WORK"] = tempfile.mkdtemp(prefix="studio-work-")
    try:
        yield
    finally:
        library.MEDIA, J.WORK, os.environ["STUDIO_MEDIA"], os.environ["STUDIO_WORK"] = saved


def a_picture():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "f.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360",
                    "-frames:v", "1", p], check=True)
    return library.add(p, "pic")


def test_animate_refuses_what_is_not_a_picture():
    said = call("studio_animate", picture="clip-zzzz", prompt="x")
    assert "clip-zzzz" in said and "Not starting" in said, said


def test_animate_starts_a_job_that_reports_comfyui_missing():
    with apart():
        pic = a_picture()
        said = call("studio_animate", picture=pic["id"], prompt="she turns away", seconds=3)
        assert "job" in said and "watch_job" in said, said
        job = said.split(" as job ")[1].split(":")[0]
        for _ in range(60):
            status = call("studio_status", job=job)
            if "stopped" in status or "finished" in status:
                break
            time.sleep(0.5)
        assert "not answering" in status, status


def test_extend_refuses_a_picture():
    with apart():
        pic = a_picture()
        said = call("studio_extend", clip=pic["id"], prompt="x")
        assert "studio_animate" in said, said


def test_compose_refuses_an_empty_description():
    said = call("studio_compose", description="  ", seconds=20)
    assert "description" in said, said


def test_descriptions_mention_the_new_engines():
    tools = {t.name: t.description for t in anyio.run(S.mcp.list_tools)}
    assert "Wan" in tools["studio_animate"] and "5 seconds" in tools["studio_animate"]
    assert "last frame" in tools["studio_extend"]
    assert "ACE-Step" in tools["studio_compose"]



def test_picture_can_be_painted_from_an_earlier_one():
    listed = {t.name: t for t in anyio.run(S.mcp.list_tools)}
    params = listed["studio_picture"].input_schema["properties"]
    assert "from_picture" in params and "change" in params, sorted(params)
    assert "from_picture" in listed["studio_picture"].description

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
