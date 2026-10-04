"""Animating pictures and extending clips. A stand-in ComfyUI that 'renders' with
ffmpeg's test pattern, so the joins, sizes and library notes are real.

    studio/.venv/bin/python studio/test_motion.py
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import library, motion  # noqa: E402

SRC = tempfile.mkdtemp(prefix="studio-src-")


def make(name, *args):
    path = os.path.join(SRC, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, path], check=True)
    return path


PIC = library.add(make("frame.png", "-f", "lavfi", "-i", "testsrc2=size=1344x768", "-frames:v", "1"), "pic")
PHONE = library.add(make("phone.mp4", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
                         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest"), "clip")


class FakeClient:
    def __init__(self):
        self.graphs, self.uploads = [], []

    def upload(self, path):
        self.uploads.append(path)
        return "studio-start.png"

    def run(self, graph, on_progress=None, labels=None, **kw):
        self.graphs.append(graph)
        if on_progress:
            on_progress("high-noise pass, step 2 of 4", 50.0)
        return {"15": {"images": [{"filename": "clip_00001_.mp4", "subfolder": "studio", "type": "output"}]}}

    @staticmethod
    def files(outputs):
        return outputs["15"]["images"]

    def download(self, f, folder):
        w = self.graphs[-1]["8"]["inputs"]
        n = w["length"]
        path = os.path.join(folder, f"seg{len(self.graphs)}.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=size={w['width']}x{w['height']}:rate=16", "-frames:v", str(n),
                        "-pix_fmt", "yuv420p", path], check=True)
        return path


def quiet(fn, *a, **k):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **k)
    return r, out.getvalue()


def test_animate_makes_a_clip_at_the_pictures_shape():
    c = FakeClient()
    note, said = quiet(motion.animate, PIC["id"], "she turns away", seconds=5, seed=3, client=c)
    assert note["id"].startswith("clip-") and note["kind"] == "video", note
    assert (note["width"], note["height"]) == (832, 480), note
    assert abs(note["seconds"] - 81 / 16) < 0.1, note["seconds"]
    assert note["picture"] == PIC["id"] and note["prompt"] == "she turns away"
    assert c.uploads == [PIC["path"]]
    assert 'PROGRESS {"stage": "high-noise pass, step 2 of 4", "percent": 50.0}' in said, said


def test_final_quality_is_720p():
    note, _ = quiet(motion.animate, PIC["id"], "x", seconds=1, quality="final", client=FakeClient())
    assert (note["width"], note["height"]) == (1280, 720)


def test_extend_carries_a_clip_on_without_repeating_the_join_frame():
    first, _ = quiet(motion.animate, PIC["id"], "a", seconds=5, client=FakeClient())
    c = FakeClient()
    longer, _ = quiet(motion.extend, first["id"], "she walks to the door", seconds=5, client=c)
    assert longer["id"].startswith("clip-") and longer["extends"] == first["id"], longer
    assert abs(longer["seconds"] - (81 + 80) / 16) < 0.1, longer["seconds"]
    assert c.uploads and c.uploads[0].endswith(".png")


def test_extending_an_odd_sized_phone_clip_lands_on_a_wan_size():
    longer, _ = quiet(motion.extend, PHONE["id"], "the camera pans left", seconds=2, client=FakeClient())
    assert (longer["width"], longer["height"]) == (736, 544), longer
    assert abs(longer["seconds"] - (2.0 + 32 / 16)) < 0.15, longer["seconds"]


def test_only_pictures_animate_and_only_clips_extend():
    for fn, ref, word in ((motion.animate, PHONE["id"], "studio_extend"),
                          (motion.extend, PIC["id"], "studio_animate")):
        try:
            fn(ref, "x", client=FakeClient())
        except ValueError as e:
            assert word in str(e), str(e)
        else:
            raise AssertionError(f"{fn.__name__} took {ref}")


def test_a_missing_id_is_a_sentence():
    try:
        motion.animate("pic-zzzz", "x", client=FakeClient())
    except KeyError as e:
        assert "pic-zzzz" in str(e)
    else:
        raise AssertionError("missing id accepted")


def test_the_job_says_failed_with_a_reason():
    r = subprocess.run([sys.executable, "-m", "studio.motion", "animate", "--picture", "pic-zzzz",
                        "--prompt", "x", "--job", "t1"], cwd=ROOT, capture_output=True, text=True,
                       env=dict(os.environ))
    assert r.returncode == 1 and r.stdout.strip().splitlines()[-1].startswith("FAILED"), r.stdout + r.stderr
    assert "pic-zzzz" in r.stdout


def test_last_frame_is_a_picture_of_the_clips_size():
    out = os.path.join(SRC, "last.png")
    motion.last_frame(PHONE["path"], out)
    assert library.probe(out)["kind"] == "image" and library.probe(out)["width"] == 320


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
