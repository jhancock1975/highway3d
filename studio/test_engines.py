"""The studio's real engines, end to end. Minutes, not seconds.

    studio/.venv/bin/python studio/test_engines.py

Speaks, composes, draws, and cuts real edits, then checks each result with
ffprobe and pulls frames into studio/.work/check/ to be looked at. Run it
only when nothing heavy is running: it refuses to start otherwise.
"""

import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import assemble, images, library, memory, music, speech, timeline  # noqa: E402

CHECK = os.path.join(HERE, ".work", "check")
os.makedirs(CHECK, exist_ok=True)
SRC = tempfile.mkdtemp(prefix="studio-src-")
TIMES = {}


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def frame(video, t, name):
    p = os.path.join(CHECK, name)
    ffmpeg("-ss", f"{t}", "-i", video, "-frames:v", "1", p)
    return p


def timed(name, fn, *a):
    began = time.time()
    out = fn(*a)
    TIMES[name] = round(time.time() - began, 1)
    return out


def test_speech_plain():
    note = timed("speech", speech.speak, "Three in the morning. The server is down.", "am_michael")
    assert note["kind"] == "audio" and 1.0 < note["seconds"] < 8.0, note
    assert [w["text"] for w in note["words"]][:4] == ["Three", "in", "the", "morning."], note["words"][:4]


def test_speech_einstein():
    note = speech.speak("Time is not universal.", "einstein")
    assert len(note["words"]) >= 4, note["words"]


def test_long_speech_keeps_time():
    # Line breaks make Kokoro say it in several pieces, each timed from zero.
    text = "\n".join(["The terminal keeps tmux intact, draws htop as it should, and "
                      "never scrambles the borders of a pane."] * 5)
    note = speech.speak(text, "bf_emma")
    starts = [w["start"] for w in note["words"]]
    assert starts == sorted(starts), "word times went backwards between pieces"
    assert note["words"][-1]["end"] > 0.8 * note["seconds"], (note["words"][-1], note["seconds"])


def test_long_einstein_keeps_time():
    # lectern.narrate alone refused this (over 510 phonemes) and restarted
    # its word times at every line break.
    text = "\n".join(["Time is not universal, and every clock that moves runs "
                      "slow against the one you are holding."] * 6)
    note = speech.speak(text, "einstein")
    starts = [w["start"] for w in note["words"]]
    assert starts == sorted(starts), "einstein's word times went backwards"
    assert len(note["words"]) >= 95, len(note["words"])
    assert note["words"][-1]["end"] > 0.8 * note["seconds"], (note["words"][-1], note["seconds"])


def test_music():
    note = music.compose("night", 5)
    assert abs(note["seconds"] - 5) < 0.1, note


def test_cards():
    for style in images.STYLES:
        note = timed(f"card {style}", images.card, "Don't panic — it's café time",
                     "a terminal that does not mangle tmux", style, 1280, 720)
        assert (note["width"], note["height"]) == (1280, 720), note
        os.replace(note["path"], os.path.join(CHECK, f"card-{style}.png"))


def edit_assets():
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=3",
           "-f", "lavfi", "-i", "sine=frequency=330:duration=3", "-shortest",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.join(SRC, "portrait clip.mp4"))
    ffmpeg("-f", "lavfi", "-i", "mandelbrot=size=1600x900", "-frames:v", "1",
           os.path.join(SRC, "still.png"))
    return dict(
        card=images.card("Pockterm", "free, no account", "dark"),
        lower=images.card("tmux, intact", "", "light", 1600, 200),
        voice=speech.speak("Three in the morning. The server is down, and you "
                           "are not at your desk.", "am_michael"),
        bed=music.compose("drive", 12),
        clip=os.path.join(SRC, "portrait clip.mp4"),
        still=os.path.join(SRC, "still.png"))


def test_full_edit():
    a = edit_assets()
    edit = {
        "size": "1920x1080", "name": "engine-test",
        "video": [{"asset": a["card"]["id"], "seconds": 2},
                  {"asset": a["still"], "seconds": 3, "move": "push-in", "transition": "dissolve"},
                  {"asset": a["clip"], "fit": "contain", "transition": "fade", "level": 0.3}],
        "overlays": [{"asset": a["lower"]["id"], "at": 3, "seconds": 2, "place": "bottom"},
                     {"captions": a["voice"]["id"]}],
        "audio": [{"asset": a["voice"]["id"], "at": 0.3},
                  {"asset": a["bed"]["id"], "level": 0.2, "duck": True}],
    }
    plan, problems = timeline.normalise(edit, library.resolve)
    assert problems == [], problems
    out = os.path.join(CHECK, "engine-test.mp4")
    d = timed("assembly", assemble.run, plan, out)
    facts = library.probe(out)
    assert facts["kind"] == "video" and facts["sound"], facts
    assert (facts["width"], facts["height"]) == (1920, 1080), facts
    assert abs(facts["seconds"] - plan["seconds"]) < 0.15, (facts["seconds"], plan["seconds"])
    TIMES["assembly per second"] = round(d["took"] / plan["seconds"], 2)
    for t in (1.0, 1.75, 3.5, 5.5):
        print("  frame:", frame(out, t, f"frame-{t}.png"))


def test_audio_only_edit():
    voice = speech.speak("Audio on its own.", "af_heart")
    bed = music.compose("open", 4)
    plan, problems = timeline.normalise(
        {"name": "audio-test", "audio": [{"asset": voice["id"], "at": 0.5},
                                         {"asset": bed["id"], "level": 0.2, "duck": True}]},
        library.get)
    assert problems == [], problems
    out = os.path.join(CHECK, "audio-test.m4a")
    assemble.run(plan, out)
    assert library.probe(out)["kind"] == "audio"


def main():
    refused = memory.refusal("assembly")
    if refused:
        print("not running:", refused)
        sys.exit(2)
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print("times:", TIMES)
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
