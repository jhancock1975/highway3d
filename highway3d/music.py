"""Generate a score for a clip. numpy only, nothing sampled or downloaded.

    python3 music.py --duration 20 --out music.wav --mood drive

Written rather than modelled, for the same reason the sound effects are: no
weights to fetch, no licence that follows the output, and the length is exact
so it never has to be looped or cut to fit the picture.

Four layers over a looping chord progression -- pad, bass, arpeggio and a soft
pulse -- voiced low and wide so a narration track sits on top of it.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import wave

import numpy as np

SR = 48000

# semitone offsets from the root, per chord, and the progression per mood
MOODS = {
    # minor, patient, documentary underscore
    "drive": dict(root=55.0, bpm=96.0,
                  prog=[(0, [0, 3, 7, 10]), (5, [0, 4, 7, 11]),
                        (8, [0, 4, 7, 11]), (3, [0, 4, 7, 11])],
                  arp=True, pulse=True, bright=0.55),
    # brighter, open fifths, more motion
    "open": dict(root=58.0, bpm=108.0,
                 prog=[(0, [0, 7, 12, 16]), (7, [0, 7, 12, 16]),
                       (5, [0, 7, 12, 16]), (3, [0, 7, 12, 14])],
                 arp=True, pulse=True, bright=0.72),
    # sparse, night-drive, almost no rhythm
    "night": dict(root=48.0, bpm=80.0,
                  prog=[(0, [0, 3, 7, 14]), (0, [0, 3, 7, 14]),
                        (10, [0, 4, 7, 14]), (8, [0, 3, 7, 14])],
                  arp=False, pulse=False, bright=0.38),
}


def _midi_hz(n: float) -> float:
    return 440.0 * (2.0 ** ((n - 69.0) / 12.0))


def _adsr(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    """Envelope in samples, sustain as a level."""
    A, D, R = int(a * SR), int(d * SR), int(r * SR)
    S = max(0, n - A - D - R)
    parts = [np.linspace(0, 1, A, endpoint=False) if A else np.empty(0),
             np.linspace(1, s, D, endpoint=False) if D else np.empty(0),
             np.full(S, s),
             np.linspace(s, 0, R) if R else np.empty(0)]
    env = np.concatenate(parts)
    return np.resize(env, n)


def _saw(freq: float, n: int, harmonics: int = 12) -> np.ndarray:
    """Additive saw: band-limited by construction, no aliasing."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k in range(1, harmonics + 1):
        if freq * k > SR * 0.45:
            break
        out += np.sin(2 * math.pi * freq * k * t) / k
    return out * (2.0 / math.pi)


def _lp(x: np.ndarray, cutoff: float) -> np.ndarray:
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    return np.fft.irfft(spec / (1.0 + (f / max(cutoff, 1.0)) ** 2), len(x))


def _place(buf: np.ndarray, sig: np.ndarray, at: int) -> None:
    end = min(len(buf), at + len(sig))
    if end > at:
        buf[at:end] += sig[:end - at]


def render(duration: float, mood: str = "drive", seed: int = 7,
           key_shift: float = 0.0) -> np.ndarray:
    cfg = MOODS[mood]
    rng = np.random.default_rng(seed)
    n = int(duration * SR)
    beat = 60.0 / cfg["bpm"]
    bar = beat * 4.0
    root = cfg["root"] + key_shift

    pad = np.zeros(n)
    bass = np.zeros(n)
    arp = np.zeros(n)
    pulse = np.zeros(n)

    bars = int(math.ceil(duration / bar)) + 1
    for b in range(bars):
        deg, chord = cfg["prog"][b % len(cfg["prog"])]
        at = int(b * bar * SR)
        if at >= n:
            break
        bar_n = int(bar * SR)

        # --- pad: whole-bar chord, slow attack, detuned pairs for width
        env = _adsr(bar_n, 0.45, 0.5, 0.75, 0.6)
        voice = np.zeros(bar_n)
        for iv in chord:
            f = _midi_hz(root + 12 + deg + iv)
            for det in (-0.09, 0.09):
                voice += _saw(f * (1.0 + det / 100.0), bar_n, 10)
        voice = _lp(voice / max(len(chord) * 2, 1),
                    420.0 + 900.0 * cfg["bright"])
        _place(pad, voice * env * 0.30, at)

        # --- bass: root on the beat, short and round
        for k in range(4):
            bat = at + int(k * beat * SR)
            if bat >= n:
                break
            ln = int(beat * SR * 0.92)
            f = _midi_hz(root - 12 + deg)
            sig = (_saw(f, ln, 6) * 0.6 + np.sin(
                2 * math.pi * f * np.arange(ln) / SR) * 0.4)
            e = _adsr(ln, 0.006, 0.12, 0.55 if k % 2 == 0 else 0.35, 0.18)
            _place(bass, _lp(sig, 260.0) * e * 0.34, bat)

        # --- arpeggio: eighth-note plucks climbing the chord
        if cfg["arp"]:
            for k in range(8):
                aat = at + int(k * beat * 0.5 * SR)
                if aat >= n:
                    break
                iv = chord[k % len(chord)]
                oct_up = 12 if k >= 4 else 0
                f = _midi_hz(root + 24 + deg + iv + oct_up)
                ln = int(beat * 0.5 * SR * 1.6)
                sig = np.sin(2 * math.pi * f * np.arange(ln) / SR)
                sig += 0.3 * np.sin(4 * math.pi * f * np.arange(ln) / SR)
                e = _adsr(ln, 0.004, 0.18, 0.0, 0.12)
                amp = 0.10 * (0.6 + 0.4 * rng.random())
                _place(arp, _lp(sig, 2600.0) * e * amp, aat)

        # --- pulse: soft kick and an airy offbeat, felt more than heard
        if cfg["pulse"]:
            for k in range(4):
                kat = at + int(k * beat * SR)
                if kat < n:
                    ln = int(0.16 * SR)
                    tt = np.arange(ln) / SR
                    f = 90.0 * np.exp(-tt * 26.0) + 42.0
                    sig = np.sin(2 * math.pi * np.cumsum(f) / SR)
                    _place(pulse, sig * _adsr(ln, 0.002, 0.10, 0.0, 0.05)
                           * 0.26, kat)
                hat = at + int((k + 0.5) * beat * SR)
                if hat < n:
                    ln = int(0.06 * SR)
                    h = rng.normal(size=ln)
                    h -= _lp(h, 5000.0)
                    _place(pulse, h * _adsr(ln, 0.001, 0.04, 0.0, 0.02)
                           * 0.05, hat)

    mix = pad + bass + arp + pulse
    mix = mix[:n]

    # ease in and out so it never starts or stops abruptly under picture
    fade = int(min(1.6, duration * 0.12) * SR)
    if fade > 0:
        mix[:fade] *= np.linspace(0, 1, fade)
        mix[-fade:] *= np.linspace(1, 0, fade)

    peak = np.abs(mix).max()
    return mix / peak * 0.72 if peak > 0 else mix


def write(path: str, mono: np.ndarray) -> None:
    pcm = (np.clip(mono, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mood", default="drive", choices=sorted(MOODS))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--key-shift", type=float, default=0.0)
    a = ap.parse_args()
    audio = render(a.duration, a.mood, a.seed, a.key_shift)
    write(a.out, audio)
    print(json.dumps(dict(ok=True, out=a.out, mood=a.mood,
                          duration=a.duration, bpm=MOODS[a.mood]["bpm"],
                          bytes=os.path.getsize(a.out))))


if __name__ == "__main__":
    main()
