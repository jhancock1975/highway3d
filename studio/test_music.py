"""Music beds, composed for real: numpy only, a few seconds.

    studio/.venv/bin/python studio/test_music.py
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
from studio import music as M  # noqa: E402


def test_moods_come_from_the_composer():
    assert M.MOODS == ("drive", "open", "night"), M.MOODS


def test_exact_length_in_the_library():
    note = M.compose("night", 3.0)
    assert note["id"].startswith("music-") and note["kind"] == "audio", note
    assert abs(note["seconds"] - 3.0) < 0.05, note
    assert note["mood"] == "night" and os.path.exists(note["path"])


def test_unknown_mood_is_a_sentence():
    try:
        M.compose("jazz", 3)
    except ValueError as e:
        assert e.args[0] == "there is no mood called jazz; the moods are drive, open, night", e
    else:
        raise AssertionError("jazz was composed")


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
