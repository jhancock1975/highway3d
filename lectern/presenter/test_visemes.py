"""Pure-python checks on the mouth track. No Blender.

    python3 lectern/presenter/test_visemes.py

Each test is a thing a viewer would notice: lips that never meet on "m",
an "f" with no teeth on the lip, a mouth that keeps talking through a pause,
a face that never blinks or blinks like a strobe.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from lectern.presenter import visemes as V  # noqa: E402

FPS = 24


def tl(words, duration=None, lead=0.3):
    """A timeline from (text, phonemes, seconds) triples, laid end to end."""
    t = lead
    out = []
    for text, ph, d in words:
        out.append(dict(text=text, phonemes=ph, start=t, end=t + d))
        t += d
    return dict(duration=duration or t + 0.5, words=out)


def frames_of(track, key, lo, hi):
    return [fr["weights"][key] for fr in track if lo <= fr["frame"] / FPS < hi]


def test_track_api_unchanged():
    t = V.track(tl([("mama", "mˈɑmə", 0.5)]), fps=FPS)
    assert set(t[0]) == {"frame", "viseme", "open", "wide", "round"}
    assert len(t) == round(t[-1]["frame"]) + 1


def test_misaki_diphthongs():
    # misaki/espeak.py: 'e^ɪ':'A', 'a^ɪ':'I'. "day" spreads, "high" opens.
    assert V.viseme_of("A") == "E"
    assert V.viseme_of("I") == "AI"
    assert [s["shape"] for s in V.segments("dˈA")] == ["DD", "E", "I"]
    assert [s["shape"] for s in V.segments("hˈI")] == ["kk", "aa", "I"]
    assert [s["shape"] for s in V.segments("nˈW")] == ["nn", "aa", "U"]
    assert [s["shape"] for s in V.segments("bˈY")] == ["PP", "O", "I"]


def test_diphthong_moves_through_time():
    w = V.weights(tl([("high", "hˈI", 0.6)]), fps=FPS)
    seg = [fr for fr in w if 0.3 <= fr["frame"] / FPS < 0.9]
    first = max(seg[: len(seg) // 2], key=lambda fr: fr["weights"]["viseme_aa"])
    last = max(seg[len(seg) // 2:], key=lambda fr: fr["weights"]["viseme_I"])
    assert first["frame"] < last["frame"]
    assert first["weights"]["viseme_aa"] > first["weights"]["viseme_I"]
    assert last["weights"]["viseme_I"] > last["weights"]["viseme_aa"]


def test_lips_close_fully_on_bilabials():
    # a fast "p" between open vowels, shorter than a frame
    t = tl([("apa", "ɑpˈɑ", 0.30), ("mob", "mˈɒb", 0.35), ("bee", "bˈi", 0.3)])
    w = V.weights(t, fps=FPS)
    for word in t["words"]:
        pp = frames_of(w, "viseme_PP", word["start"], word["end"])
        assert max(pp) == 1.0, (word["text"], pp)
    shut = [fr for fr in w if fr["weights"]["viseme_PP"] == 1.0]
    assert all(fr["jawOpen"] == 0.0 for fr in shut)
    assert all(sum(fr["weights"].values()) <= 1.0 + 1e-6 for fr in shut)


def test_real_timeline_every_bilabial_closes():
    files = sorted(glob.glob(os.path.join(HERE, "..", "..", ".work", "vo-*.json")))
    if not files:
        return
    checked = 0
    for fn in files[:40]:
        d = json.load(open(fn))
        if "words" not in d:
            continue
        w = V.weights(d, fps=FPS)
        for e in V.speech_events(d):
            if e["shape"] != "PP":
                continue
            lo = int(e["s"] * FPS) - 1
            hi = int(e["e"] * FPS) + 2
            vals = [fr["weights"]["viseme_PP"] for fr in w[max(0, lo):hi]]
            assert 1.0 in vals, (fn, e)
            checked += 1
    assert checked > 50


def test_teeth_on_lip_for_f_and_v():
    t = tl([("off", "ˈɒf", 0.35), ("vivid", "vˈɪvɪd", 0.5)])
    w = V.weights(t, fps=FPS)
    for word in t["words"]:
        ff = frames_of(w, "viseme_FF", word["start"], word["end"])
        assert max(ff) >= 0.9, (word["text"], ff)


def test_rounding_on_o_and_u():
    t = tl([("oo", "ˈuː", 0.5), ("law", "lˈɔː", 0.5)])
    w = V.weights(t, fps=FPS)
    mid_u = w[int((0.3 + 0.25) * FPS)]
    mid_o = w[int((0.8 + 0.3) * FPS)]
    assert mid_u["viseme"] == "U", mid_u
    assert mid_o["viseme"] == "O", mid_o
    assert mid_o["jawOpen"] > mid_u["jawOpen"]


def test_jaw_drops_on_open_vowels_not_on_closures():
    w = V.weights(tl([("father", "fˈɑːzɐ", 0.6)]), fps=FPS, jaw=1.0)
    aa = max(fr["jawOpen"] for fr in w)
    assert aa > 0.3
    w2 = V.weights(tl([("father", "fˈɑːzɐ", 0.6)]), fps=FPS, jaw=2.0)
    assert max(fr["jawOpen"] for fr in w2) > aa * 1.9


def test_rests_in_silence_and_bounds():
    t = tl([("one", "wˈʌn", 0.4)], duration=3.0, lead=0.5)
    w = V.weights(t, fps=FPS)
    assert len(w) == 72
    for fr in w:
        s = sum(fr["weights"].values())
        assert 0.0 <= s <= 1.0 + 1e-6
        assert all(0.0 <= v <= 1.0 for v in fr["weights"].values())
    # well after the word the mouth has let go
    assert sum(w[int(2.5 * FPS)]["weights"].values()) < 0.05
    assert w[int(2.5 * FPS)]["jawOpen"] < 0.02
    assert sum(w[0]["weights"].values()) < 0.05


def test_blinks_at_human_rate_and_speed():
    track = V.blinks(120.0, FPS, per_minute=17.0, seed=3)
    starts = V.blink_times(track, FPS)
    per_min = len(starts) / 2.0
    assert 13 <= per_min <= 21, per_min
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert min(gaps) >= 1.2
    # each blink: frames with the lid more than a tenth closed
    runs, cur = [], 0
    for x in track:
        if x > 0.1:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    ms = [1000.0 * r / FPS for r in runs]
    assert all(80 <= m <= 250 for m in ms), ms
    assert max(track) == 1.0


def test_brows_move_but_not_constantly():
    words = [("Absolutely", "ˌæbsəlˈuːtli", 0.8), ("not", "nˈɒt", 0.3)] * 8
    t = tl(words, lead=0.2)
    b = V.brows(t, FPS)
    inner = b["browInnerUp"]
    assert max(inner) > 0.3
    up = sum(1 for x in inner if x > 0.05) / len(inner)
    assert 0.05 < up < 0.7, up


def test_face_keys():
    f = V.face(tl([("mama", "mˈɑmə", 0.5)]), fps=FPS)
    for k in V.KEYS + ("jawOpen", "eyeBlinkLeft", "eyeBlinkRight", "browInnerUp"):
        assert k in f
    n = len(f["viseme_PP"])
    assert all(len(v) == n for v in f.values())


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
