"""The edit checker: times worked out, and every mistake said. No engines.

    studio/.venv/bin/python studio/test_timeline.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import timeline as T  # noqa: E402

WORDS = [dict(text=t, start=s, end=e) for t, s, e in [
    ("Three", 0.0, 0.3), ("in", 0.3, 0.4), ("the", 0.4, 0.5),
    ("morning.", 0.5, 1.0), ("The", 1.2, 1.3), ("server", 1.3, 1.7),
    ("is", 1.7, 1.8), ("down,", 1.8, 2.2), ("and", 2.3, 2.4),
    ("you", 2.4, 2.5), ("are", 2.5, 2.6), ("not", 2.6, 2.8),
    ("at", 2.8, 2.9), ("your", 2.9, 3.0), ("desk.", 3.0, 3.5)]]

NOTES = {
    "card-1a2b": dict(id="card-1a2b", path="/m/card.png", kind="image", seconds=None, width=1920, height=1080, sound=False),
    "clip-9c01": dict(id="clip-9c01", path="/m/clip.mov", kind="video", seconds=9.0, width=1170, height=2532, sound=True),
    "pic-44d0": dict(id="pic-44d0", path="/m/pic.png", kind="image", seconds=None, width=1024, height=1024, sound=False),
    "card-7d3e": dict(id="card-7d3e", path="/m/lower.png", kind="image", seconds=None, width=1600, height=200, sound=False),
    "voice-3f2a": dict(id="voice-3f2a", path="/m/voice.wav", kind="audio", seconds=3.6, width=None, height=None, sound=True, words=WORDS),
    "music-77e1": dict(id="music-77e1", path="/m/music.wav", kind="audio", seconds=30.0, width=None, height=None, sound=True),
}


def lookup(ref):
    if ref not in NOTES:
        raise KeyError(f"there is no asset called {ref}")
    return NOTES[ref]


def good():
    return {
        "size": "1920x1080", "fps": 30, "name": "Pockterm Spot!",
        "video": [{"asset": "card-1a2b", "seconds": 3},
                  {"asset": "clip-9c01", "from": 2, "seconds": 6, "transition": "dissolve"},
                  {"asset": "pic-44d0", "seconds": 5, "move": "push-in", "transition": "fade"}],
        "overlays": [{"asset": "card-7d3e", "at": 4, "seconds": 3, "place": "bottom"},
                     {"captions": "voice-3f2a"}],
        "audio": [{"asset": "voice-3f2a", "at": 0.5},
                  {"asset": "music-77e1", "level": 0.15, "duck": True}],
    }


def test_good_edit_has_no_problems_and_times_add_up():
    plan, problems = T.normalise(good(), lookup)
    assert problems == [], problems
    starts = [v["start"] for v in plan["video"]]
    assert starts == [0.0, 2.5, 8.0], starts
    assert plan["seconds"] == 13.0, plan["seconds"]
    assert plan["name"] == "pockterm-spot"
    assert (plan["width"], plan["height"], plan["fps"]) == (1920, 1080, 30.0)
    assert plan["audio_only"] is False


def test_defaults():
    plan, problems = T.normalise({"video": ["pic-44d0", "clip-9c01"]}, lookup)
    assert problems == [], problems
    still, clip = plan["video"]
    assert (still["seconds"], still["transition"], still["fit"], still["move"]) == (4.0, "cut", "cover", "none")
    assert (clip["from_"], clip["seconds"]) == (0.0, 9.0)
    assert plan["seconds"] == 13.0 and plan["name"] == "edit"
    assert plan["audio"] == [] and plan["captions"] == []


def test_music_fades_by_default_speech_does_not():
    plan, _ = T.normalise(good(), lookup)
    voice, music = plan["audio"]
    assert (voice["fade"], voice["speech"], voice["duck"]) == (0.0, True, False)
    assert (music["fade"], music["speech"], music["duck"], music["level"]) == (1.0, False, True, 0.15)


def test_captions_follow_the_voice():
    plan, _ = T.normalise(good(), lookup)
    texts = [c["text"] for c in plan["captions"]]
    assert texts == ["Three in the morning.", "The server is down,", "and you are not at your desk."], texts
    first = plan["captions"][0]
    assert first["at"] == 0.5, first
    assert first["seconds"] == 1.2, first


def test_chunks_never_longer_than_seven_words():
    words = [dict(text=f"w{i}", start=i * 0.2, end=i * 0.2 + 0.15) for i in range(16)]
    sizes = [len(c["text"].split()) for c in T.chunks(words, 0.0)]
    assert sizes == [7, 7, 2], sizes


def test_chunks_survive_empty_and_bare_punctuation():
    words = [dict(text="", start=0, end=0.1), dict(text="Hi", start=0.1, end=0.3),
             dict(text="—", start=0.3, end=0.35), dict(text="there", start=0.35, end=0.6)]
    got = T.chunks(words, 1.0)
    assert [c["text"] for c in got] == ["Hi — there"], got
    assert got[0]["at"] == 1.1, got


def test_audio_only_edit():
    plan, problems = T.normalise({"audio": ["voice-3f2a", {"asset": "music-77e1", "at": 1}]}, lookup)
    assert problems == [], problems
    assert plan["audio_only"] is True and plan["seconds"] == 31.0, plan["seconds"]


def test_odd_sizes_become_even():
    plan, problems = T.normalise({"size": "1081x1921", "video": ["pic-44d0"]}, lookup)
    assert problems == [] and (plan["width"], plan["height"]) == (1080, 1920)


def said(edit):
    return T.normalise(edit, lookup)[1]


def test_problems_are_sentences():
    cases = [
        ({"video": [{"asset": "clip-9c01", "from": 12}]},
         "video item 1: clip-9c01 is 9 seconds long, so from 12 is past its end."),
        ({"video": [{"asset": "clip-9c01", "from": 2, "seconds": 8}]},
         "video item 1: clip-9c01 is 9 seconds long, so 8 seconds from 2 runs past its end."),
        ({"video": ["pic-44d0"], "overlays": [{"asset": "card-9999"}]},
         "overlay 1: there is no asset called card-9999."),
        ({"video": ["pic-44d0"], "overlays": [{"captions": "music-77e1"}], "audio": ["music-77e1"]},
         "captions: music-77e1 is music, not speech, so it has no words to show."),
        ({"video": ["pic-44d0"], "overlays": [{"captions": "voice-3f2a"}]},
         "captions: voice-3f2a is not in audio, so there is no time to show its words at."),
        ({"video": ["voice-3f2a"]},
         "video item 1: voice-3f2a is sound, which goes in audio, not video."),
        ({"video": [{"asset": "clip-9c01", "move": "push-in"}]},
         "video item 1: move is for stills, and clip-9c01 is video."),
        ({"video": [{"asset": "pic-44d0", "transition": "wipe"}]},
         "video item 1: transition 'wipe' is not one of cut, dissolve, fade."),
        ({"video": ["pic-44d0"], "audio": ["pic-44d0"]},
         "audio item 1: pic-44d0 is a picture, which has no sound."),
        ({"video": ["pic-44d0"], "overlays": [{"asset": "clip-9c01"}]},
         "overlay 1: overlays are pictures, and clip-9c01 is video."),
        ({"video": [{"asset": "pic-44d0", "seconds": 0.4},
                    {"asset": "card-1a2b", "transition": "dissolve"}]},
         "video item 2: its dissolve takes half a second, so it and the item before it must each be longer than that."),
        ({"video": ["pic-44d0"], "audio": [{"asset": "music-77e1", "at": 9}]},
         "audio item 1: it starts at 9, after the edit ends at 4."),
        ({"size": "big", "video": ["pic-44d0"]},
         "size 'big' is not WIDTHxHEIGHT, like 1920x1080."),
        ({"fps": "fast", "video": ["pic-44d0"]},
         "the edit: fps 'fast' is not a number."),
        ({}, "the edit has nothing in it: add video or audio."),
    ]
    for edit, want in cases:
        got = said(edit)
        assert want in got, (want, got)


def test_every_problem_reported_at_once():
    got = said({"video": [{"asset": "nope-0000"}, {"asset": "clip-9c01", "from": 99}],
                "audio": ["nada-1111"]})
    assert len(got) == 3, got


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
