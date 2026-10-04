"""The media library, against small real files ffmpeg makes. No server.

    studio/.venv/bin/python studio/test_library.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import library as L  # noqa: E402

SRC = tempfile.mkdtemp(prefix="studio-src-")


def make(name, *args):
    """A small real file, from ffmpeg's built-in test sources."""
    p = os.path.join(SRC, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, p], check=True)
    return p


CLIP = make("clip.mp4", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest")
SILENT = make("silent.mov", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=30:duration=1")
STILL = make("still.png", "-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1")
TONE = make("tone.wav", "-f", "lavfi", "-i", "sine=frequency=220:duration=1.5")
COVERED = make("covered.mp3", "-i", TONE, "-i", STILL, "-map", "0", "-map", "1",
               "-c:a", "libmp3lame", "-c:v", "png", "-disposition:v", "attached_pic")
SPACED = make("my clip with spaces.mp4", "-f", "lavfi", "-i",
              "testsrc2=size=160x120:rate=30:duration=1")
# A screen recording whose sound runs on after the picture stops.
LONG_SOUND = make("long sound.mp4", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=30:duration=1",
                  "-f", "lavfi", "-i", "sine=frequency=440:duration=2")
# A phone clip stored landscape with a 90 degree display rotation.
ROTATED = make("rotated.mp4", "-display_rotation", "90", "-i", SILENT, "-c", "copy")
ONE_FRAME = make("one frame.mp4", "-f", "lavfi", "-i", "testsrc2=size=320x200", "-frames:v", "1")
HEIC = os.path.join(SRC, "photo.heic")
HAVE_SIPS = shutil.which("sips") is not None      # macOS only; Linux has no HEIC maker
if HAVE_SIPS:
    subprocess.run(["sips", "-s", "format", "heic", STILL, "--out", HEIC], check=True, capture_output=True)


def test_probe_tells_kinds_apart():
    c = L.probe(CLIP)
    assert (c["kind"], c["width"], c["height"], c["sound"]) == ("video", 320, 240, True), c
    assert abs(c["seconds"] - 2.0) < 0.1, c
    assert L.probe(SILENT)["sound"] is False
    s = L.probe(STILL)
    assert (s["kind"], s["width"], s["height"], s["seconds"]) == ("image", 640, 360, None), s
    t = L.probe(TONE)
    assert t["kind"] == "audio" and abs(t["seconds"] - 1.5) < 0.05, t


def test_a_clip_is_as_long_as_its_picture():
    assert abs(L.probe(LONG_SOUND)["seconds"] - 1.0) < 0.1, L.probe(LONG_SOUND)


def test_rotation_gives_the_upright_size():
    r = L.probe(ROTATED)
    assert (r["width"], r["height"]) == (120, 160), r


def test_iphone_photos_import_as_pictures():
    if not HAVE_SIPS:
        return
    note = L.import_(HEIC)
    assert note["id"].startswith("image-") and note["kind"] == "image", note
    assert (note["width"], note["height"]) == (640, 360), note
    assert note["path"].endswith(".png"), note


def test_a_one_frame_video_is_a_picture():
    note = L.import_(ONE_FRAME)
    assert note["kind"] == "image" and note["path"].endswith(".png"), note
    assert (note["width"], note["height"]) == (320, 200), note


def test_cover_art_is_still_sound():
    assert L.probe(COVERED)["kind"] == "audio"


def test_import_names_by_kind():
    for path, prefix in ((CLIP, "clip-"), (STILL, "image-"), (TONE, "sound-")):
        note = L.import_(path)
        assert note["id"].startswith(prefix), note
        assert os.path.exists(note["path"]), note
        assert note["path"].startswith(L.MEDIA), note


def test_same_file_imported_once():
    assert L.import_(TONE)["id"] == L.import_(TONE)["id"]


def test_resolve_takes_ids_and_paths():
    note = L.import_(STILL)
    assert L.resolve(note["id"])["path"] == note["path"]
    assert L.resolve(STILL)["id"] == note["id"]


def test_paths_with_spaces():
    note = L.resolve(SPACED)
    assert note["kind"] == "video" and os.path.exists(note["path"]), note


def test_unknown_id_is_a_sentence():
    for ref in ("clip-0000", "../../etc/passwd"):
        try:
            L.get(ref)
        except KeyError as e:
            assert e.args[0] == f"there is no asset called {ref}", e
        else:
            raise AssertionError(f"{ref} was found")


def test_not_media_is_a_sentence():
    p = os.path.join(SRC, "notes.txt")
    with open(p, "w") as fh:
        fh.write("hello")
    try:
        L.import_(p)
    except ValueError as e:
        assert e.args[0] == "notes.txt is not a picture, video or sound that ffmpeg can read", e
    else:
        raise AssertionError("a text file was imported")


def test_missing_file_is_a_sentence():
    try:
        L.import_("/nowhere/at/all.mp4")
    except ValueError as e:
        assert e.args[0] == "there is no file at /nowhere/at/all.mp4", e
    else:
        raise AssertionError("a missing file was imported")


def test_listing_newest_first_and_by_kind():
    L.import_(CLIP)
    notes = L.listing()
    assert {n["kind"] for n in notes} >= {"video", "image", "audio"}
    assert all(n["kind"] == "image" for n in L.listing("image"))
    made = [n["made"] for n in notes]
    assert made == sorted(made, reverse=True)


def test_said_reads_as_a_line():
    note = L.import_(SILENT, name="demo")
    line = L.said(note)
    assert line == f"{note['id']} ('demo'): video, 1.0 seconds, 160x120, silent, at {note['path']}", line


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
