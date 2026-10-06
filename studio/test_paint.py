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
        self.uploads = []

    def upload(self, path):
        self.uploads.append(path)
        return "studio-start.png"

    def pending(self):
        return self.busy

    def run(self, graph, on_progress=None, labels=None, **kw):
        self.graphs.append(graph)
        latent = graph["8"]["inputs"]
        repeat = next((x["inputs"]["amount"] for x in graph.values() if x["class_type"] == "RepeatLatentBatch"), 1)
        n = latent.get("batch_size", repeat)
        return {"11": {"images": [{"filename": f"pic_{i}.png", "subfolder": "studio", "type": "output"}
                                  for i in range(n)]}}

    @staticmethod
    def files(outputs):
        return outputs["11"]["images"]

    def download(self, f, folder):
        graph = self.graphs[-1]
        scale = next((x["inputs"] for x in graph.values() if x["class_type"] == "ImageScale"), None)
        g = scale or graph["8"]["inputs"]          # the size: the scaled start picture, or the empty latent
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



def test_a_new_still_can_start_from_an_earlier_one():
    c = FakeClient()
    first = images.paint("a woman with short red hair and a green coat", "16:9", 1, seed=1, client=c)[0]
    later = images.paint("the same woman, now on a rooftop at night", "16:9", 1, seed=2, client=c,
                         from_picture=first["id"], change=0.5)[0]
    assert c.uploads == [first["path"]], c.uploads
    g = c.graphs[-1]
    samp = next(n for n in g.values() if n["class_type"] == "KSampler")
    assert samp["inputs"]["denoise"] == 0.5 and any(n["class_type"] == "VAEEncode" for n in g.values())
    assert later["from_picture"] == first["id"] and later["change"] == 0.5, later


def test_only_a_picture_can_be_painted_from():
    c = FakeClient()
    tone = os.path.join(tempfile.mkdtemp(), "tone.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", tone], check=True)
    sound = library.add(tone, "voice")
    for bad in ("pic-zzzz", sound["id"]):
        try:
            images.paint("x", "16:9", 1, client=c, from_picture=bad)
        except (KeyError, ValueError) as e:
            assert bad in str(e), str(e)
        else:
            raise AssertionError(f"painted from {bad}")
    assert c.graphs == [] and c.uploads == []


def test_change_is_kept_between_a_touch_and_almost_new():
    c = FakeClient()
    first = images.paint("a man in a grey suit", "16:9", 1, client=c)[0]
    for change in (0.0, 1.5):
        try:
            images.paint("x", "16:9", 1, client=c, from_picture=first["id"], change=change)
        except ValueError as e:
            assert "change" in str(e), str(e)
        else:
            raise AssertionError(f"accepted change={change}")


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
