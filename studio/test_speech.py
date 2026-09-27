"""Speech's word handling, without speaking. Task 10 speaks for real.

    studio/.venv/bin/python studio/test_speech.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import speech as S  # noqa: E402


def test_punctuation_joins_the_word_before():
    raw = [dict(text="Hello", start=0.0, end=0.4), dict(text=",", start=0.4, end=0.4),
           dict(text="world", start=0.5, end=0.9), dict(text=".", start=0.9, end=0.9)]
    assert S.words(raw) == [dict(text="Hello,", start=0.0, end=0.4),
                            dict(text="world.", start=0.5, end=0.9)]


def test_blank_tokens_are_dropped_and_times_rounded():
    raw = [dict(text=" ", start=0, end=0), dict(text="Hi", start=0.123456, end=0.4567)]
    assert S.words(raw) == [dict(text="Hi", start=0.123, end=0.457)]


def test_unknown_voice_is_a_sentence():
    try:
        S.speak("hello", voice="morgan")
    except ValueError as e:
        assert e.args[0].startswith("there is no voice called morgan; the voices are am_michael"), e
    else:
        raise AssertionError("an unknown voice spoke")


def test_nothing_to_say():
    try:
        S.speak("   ")
    except ValueError as e:
        assert e.args[0] == "there is nothing to say"
    else:
        raise AssertionError("silence was spoken")


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
