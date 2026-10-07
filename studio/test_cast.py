"""The cast: each character's fixed description and best still, kept for every picture of them.

    studio/.venv/bin/python studio/test_cast.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
os.environ["STUDIO_WORK"] = tempfile.mkdtemp(prefix="studio-work-")
from studio import cast, library  # noqa: E402

SRC = tempfile.mkdtemp(prefix="studio-src-")


def picture(name="face.png"):
    path = os.path.join(SRC, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360",
                    "-frames:v", "1", path], check=True)
    return library.add(path, "pic")


MARA = "a woman of 30, tall, olive skin, long black hair in a braid, a scar over her left eyebrow, red leather jacket"


def test_a_character_is_kept_with_their_still():
    pic = picture()
    cast.save("Mara", MARA, pic["id"])
    m = cast.members(["mara"])[0]                       # names are not case-sensitive
    assert m == {"name": "Mara", "description": MARA, "picture": pic["id"]}, m


def test_their_description_leads_every_prompt_word_for_word():
    cast.save("Jon", "a man of 40, broad, shaved head, grey beard, navy wool coat")
    got = cast.prompt(["Mara", "Jon"], "they argue in a rain-soaked alley at night")
    assert got.startswith(f"Mara: {MARA}. Jon: a man of 40, broad, shaved head, grey beard, navy wool coat. "), got
    assert got.endswith("they argue in a rain-soaked alley at night"), got


def test_their_stills_come_back_in_order():
    pic = picture("jon.png")
    cast.save("Jon", "a man of 40, broad, shaved head, grey beard, navy wool coat", pic["id"])
    assert cast.pictures(["Jon", "Mara"]) == [pic["id"], cast.members(["Mara"])[0]["picture"]]


def test_an_unknown_name_says_who_is_in_the_cast():
    try:
        cast.members(["Lena"])
    except ValueError as e:
        assert "Lena" in str(e) and "Mara" in str(e) and "Jon" in str(e), str(e)
    else:
        raise AssertionError("no error for an unknown character")


def test_only_a_picture_can_be_a_characters_still():
    tone = os.path.join(SRC, "tone.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", tone], check=True)
    sound = library.add(tone, "voice")
    try:
        cast.save("Mara", MARA, sound["id"])
    except ValueError as e:
        assert sound["id"] in str(e), str(e)
    else:
        raise AssertionError("a sound was accepted as a still")


def test_the_cast_outlives_the_process():
    r = subprocess.run([sys.executable, "-c", "from studio import cast; print(sorted(m['name'] for m in cast.load().values()))"],
                       cwd=os.path.dirname(HERE), capture_output=True, text=True, env=dict(os.environ))
    assert r.stdout.strip() == "['Jon', 'Mara']", r.stdout + r.stderr


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    order = ["test_a_character_is_kept_with_their_still", "test_their_description_leads_every_prompt_word_for_word",
             "test_their_stills_come_back_in_order", "test_an_unknown_name_says_who_is_in_the_cast",
             "test_only_a_picture_can_be_a_characters_still", "test_the_cast_outlives_the_process"]
    tests = sorted(tests, key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)
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
