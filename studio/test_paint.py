"""Keyframes from ComfyUI, filed in the library. A stand-in client; no ComfyUI.

    studio/.venv/bin/python studio/test_paint.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import images, library  # noqa: E402


class FakeClient:
    def __init__(self):
        self.graphs = []
        self.busy = 0

    def pending(self):
        return self.busy

    def run(self, graph, on_progress=None, labels=None, **kw):
        self.graphs.append(graph)
        n = graph["8"]["inputs"]["batch_size"]
        return {"11": {"images": [{"filename": f"pic_{i}.png", "subfolder": "studio", "type": "output"}
                                  for i in range(n)]}}

    @staticmethod
    def files(outputs):
        return outputs["11"]["images"]

    def download(self, f, folder):
        g = self.graphs[-1]["8"]["inputs"]
        path = os.path.join(folder, f["filename"])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=size={g['width']}x{g['height']}", "-frames:v", "1", path], check=True)
        return path


def test_two_keyframes_land_in_the_library_as_pictures():
    c = FakeClient()
    notes = images.paint("a lighthouse at dusk", aspect="16:9", count=2, seed=5, client=c)
    assert [n["id"][:4] for n in notes] == ["pic-", "pic-"], notes
    assert all(n["kind"] == "image" and (n["width"], n["height"]) == (1344, 768) for n in notes)
    assert all(os.path.exists(n["path"]) and n["prompt"] == "a lighthouse at dusk" for n in notes)
    assert c.graphs[-1]["9"]["inputs"]["seed"] == 5
    assert {n["id"] for n in library.listing("image")} >= {n["id"] for n in notes}


def test_a_random_seed_when_none_is_given():
    c = FakeClient()
    images.paint("x", client=c)
    assert c.graphs[-1]["9"]["inputs"]["seed"] >= 0


def test_count_is_one_to_four():
    for bad in (0, 5):
        try:
            images.paint("x", count=bad, client=FakeClient())
        except ValueError as e:
            assert "1 to 4" in str(e)
        else:
            raise AssertionError(f"count {bad} accepted")


def test_empty_prompt_is_refused():
    try:
        images.paint("  ", client=FakeClient())
    except ValueError as e:
        assert "prompt" in str(e)
    else:
        raise AssertionError("empty prompt accepted")


def test_unknown_aspect_falls_back_to_square():
    c = FakeClient()
    notes = images.paint("x", aspect="auto", client=c)
    assert (notes[0]["width"], notes[0]["height"]) == (1024, 1024)



def test_a_busy_comfyui_is_refused_at_once():
    c = FakeClient()
    c.busy = 2
    try:
        images.paint("a lighthouse", "16:9", 1, client=c)
    except RuntimeError as e:
        assert "busy" in str(e) and "2" in str(e), str(e)
    else:
        raise AssertionError("painted while ComfyUI was busy")
    assert c.graphs == [], "the graph was queued anyway"


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
