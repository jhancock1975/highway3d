"""The ffmpeg command an edit becomes. Strings only: no ffmpeg runs here.

    studio/.venv/bin/python studio/test_assemble.py

Task 10 renders real edits; this pins what the command asks for, so a
change that drops the ducking or shifts a transition shows up in a second.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import assemble as A  # noqa: E402


def still(path, seconds, start, move="none", transition="cut", fit="cover"):
    return dict(path=path, id="x", kind="image", start=start, seconds=seconds,
                from_=0.0, transition=transition, fit=fit, move=move, level=1.0, sound=False)


def plan(**over):
    p = dict(width=1920, height=1080, fps=30.0, name="t", seconds=13.0, audio_only=False,
             video=[still("/m/card.png", 3, 0.0),
                    dict(path="/m/clip.mov", id="clip", kind="video", start=2.5, seconds=6,
                         from_=2.0, transition="dissolve", fit="contain", move="none",
                         level=1.0, sound=True),
                    still("/m/pic.png", 5, 8.0, move="push-in", transition="fade")],
             overlays=[dict(path="/m/lower.png", id="o", at=4.0, seconds=3.0, place="bottom",
                            width=1600, height=200)],
             captions=[dict(text="Three in the morning.", at=0.5, seconds=1.2, path="/c/0.png")],
             audio=[dict(path="/m/voice.wav", id="v", at=0.5, level=1.0, fade=0.0, duck=False,
                         speech=True, seconds=3.6),
                    dict(path="/m/music.wav", id="m", at=0.0, level=0.15, fade=1.0, duck=True,
                         speech=False, seconds=30.0)])
    p.update(over)
    return p


def graph(args):
    return args[args.index("-filter_complex") + 1]


def test_video_trims_and_fits():
    args = A.command(plan(), "/r/out.mp4")
    i = args.index("/m/clip.mov")
    assert args[i - 5:i] == ["-ss", "2.000", "-t", "6.000", "-i"], args[i - 5:i]
    g = graph(args)
    assert "force_original_aspect_ratio=decrease,pad=1920:1080" in g  # contain
    assert "force_original_aspect_ratio=increase,crop=1920:1080" in g  # cover


def test_transitions():
    g = graph(A.command(plan(), "/r/out.mp4"))
    # xfade's own "dissolve" is a pixel dither; an editor's dissolve is its "fade"
    assert "xfade=transition=fade:duration=0.5:offset=2.500" in g, g
    assert "xfade=transition=fadeblack:duration=0.5:offset=8.000" in g, g
    cut = plan()
    cut["video"][1]["transition"] = "cut"
    assert "concat=n=2:v=1:a=0" in graph(A.command(cut, "/r/out.mp4"))


def test_push_in_moves_over_every_frame():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "zoompan=z=1+0.12*(on/149)" in g and ":d=150:s=1920x1080" in g, g


def test_overlays_and_captions_are_timed():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "setpts=PTS-STARTPTS+4.000/TB" in g and "setpts=PTS-STARTPTS+0.500/TB" in g, g
    assert g.count("overlay=x=") == 2 and "eof_action=pass" in g, g


def test_music_ducks_under_speech():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "sidechaincompress" in g and "asplit=2" in g, g
    assert "anullsrc=r=48000:cl=stereo,atrim=duration=0.500" in g, g


def test_ducked_music_outlasts_the_speech():
    # sidechaincompress ends with the shorter input, so a voice that stops
    # early stopped the music with it: the speech bus runs the whole edit.
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "apad=whole_dur=13.000,asplit=2" in g, g


def test_sound_is_placed_after_silence_not_delayed():
    # adelay in a graph with video let a clip's sound start at 0 and dropped
    # the voice entirely; silence joined on with concat is exact.
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "adelay" not in g, g
    assert "concat=n=2:v=0:a=1[a0]" in g, g


def test_clip_sound_is_placed_at_its_start():
    g = graph(A.command(plan(), "/r/out.mp4"))
    assert "atrim=duration=2.500" in g and "concat=n=2:v=0:a=1[va1]" in g, g



def test_silence_when_there_is_no_audio():
    p = plan(audio=[], captions=[])
    p["video"][1]["sound"] = False
    args = A.command(p, "/r/out.mp4")
    assert "anullsrc=r=48000:cl=stereo" in args, args


def test_audio_only_makes_m4a():
    p = plan(audio_only=True, video=[], overlays=[], captions=[], seconds=30.0)
    args = A.command(p, "/r/out.m4a")
    assert "[vout]" not in " ".join(args) and args[-1] == "/r/out.m4a", args
    assert args[args.index("-c:a") + 1] == "aac"


def test_output_is_h264_aac_and_exact_length():
    args = A.command(plan(), "/r/out.mp4")
    for flag, value in (("-c:v", "libx264"), ("-pix_fmt", "yuv420p"), ("-c:a", "aac"), ("-t", "13.000")):
        last = len(args) - 1 - args[::-1].index(flag)  # inputs have their own -t
        assert args[last + 1] == value, (flag, args)


def test_estimate_grows_with_length_and_size():
    small = A.estimate(plan(seconds=10.0, width=1280, height=720))
    big = A.estimate(plan(seconds=60.0))
    assert 0 < small < big, (small, big)


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
