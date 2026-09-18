"""Synthesise a soundtrack for a highway clip from its own traffic simulation.

    python3 audio.py --motion /tmp/motion.json --out /tmp/track.wav \
        [--narration /tmp/vo.wav]

Nothing here is sampled or downloaded: the bed is filtered noise and the
pass-bys are derived from the simulated positions, so every whoosh lines up
with a vehicle that actually passed, panned to the side it actually went and
Doppler-shifted by its actual closing speed. No licence to worry about and no
sync drift, because picture and sound come from the same numbers.

Only dependency is numpy.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import wave

import numpy as np

SR = 48000


# ----------------------------------------------------------------- utilities

def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    """Pink-ish noise via spectral shaping. Road roar is close to 1/f."""
    spec = rng.normal(size=n // 2 + 1) + 1j * rng.normal(size=n // 2 + 1)
    f = np.arange(len(spec))
    f[0] = 1
    spec /= np.sqrt(f)
    out = np.fft.irfft(spec, n)
    return out / (np.abs(out).max() + 1e-9)


def _onepole(x: np.ndarray, cutoff: float, kind: str = "low") -> np.ndarray:
    """Cheap one-pole filter; enough shaping for a noise bed."""
    a = math.exp(-2.0 * math.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1.0 - a) * x[i] + a * acc
        y[i] = acc
    return y if kind == "low" else x - y


def _fast_lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """FFT-domain low pass -- the sample loop above is too slow for minutes."""
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    spec *= 1.0 / (1.0 + (freqs / max(cutoff, 1.0)) ** 2)
    return np.fft.irfft(spec, n)


def _fast_bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    g = (1.0 / (1.0 + (freqs / max(hi, 1.0)) ** 4)) * \
        (1.0 - 1.0 / (1.0 + (freqs / max(lo, 1.0)) ** 4))
    return np.fft.irfft(spec * g, n)


# --------------------------------------------------------------------- layers

def ego_bed(motion: dict, rng) -> np.ndarray:
    """Tyre roar, wind and engine from the camera vehicle."""
    fps = motion["fps"]
    n = int(motion["duration"] * SR)
    t = np.arange(n) / SR

    v = np.array([m["v"] for m in motion["motion"]], dtype=float)
    v = np.interp(t, np.arange(len(v)) / fps, v)
    v = np.clip(v, 1.0, None)
    vn = v / max(motion["speed"], 1.0)

    # tyre roar: broadband, brightness and level rise with speed
    roar = _fast_bandpass(_pink(n, rng), 60.0, 3200.0) * (0.22 * vn ** 1.3)

    # wind: higher, hissier
    wind = _fast_bandpass(_pink(n, rng), 700.0, 9000.0) * (0.10 * vn ** 1.8)

    # engine: a few harmonics of a slowly wandering fundamental
    rpm = 34.0 * vn + 4.0 * np.sin(2 * math.pi * 0.07 * t)
    phase = 2 * math.pi * np.cumsum(rpm) / SR
    eng = np.zeros(n)
    for k, amp in ((1, 0.34), (2, 0.20), (3, 0.11), (4, 0.06), (6, 0.03)):
        eng += amp * np.sin(k * phase + k * 0.7)
    eng = _fast_lowpass(eng, 420.0) * 0.16 * (0.55 + 0.45 * vn)

    return roar + wind + eng


def passbys(motion: dict, rng) -> tuple[np.ndarray, np.ndarray]:
    """One Doppler-shifted whoosh per vehicle that actually comes close."""
    fps = motion["fps"]
    n = int(motion["duration"] * SR)
    left = np.zeros(n)
    right = np.zeros(n)

    # closest approach per car, from the simulated relative positions
    closest: dict[int, tuple[float, float, float]] = {}
    for f, m in enumerate(motion["motion"]):
        for idx, dz, dx in m["near"]:
            d = math.hypot(dz, dx)
            if idx not in closest or d < closest[idx][0]:
                closest[idx] = (d, f / fps, dx)

    speed = max(motion["speed"], 1.0)
    for idx, (dmin, t_at, dx) in closest.items():
        if dmin > 26.0:
            continue
        car = motion["cars"][idx]
        # closing speed: oncoming traffic passes far faster than an overtake
        rel_v = speed * (2.0 if car["oncoming"] else 0.30)
        rel_v = max(rel_v, 4.0)
        width = max(0.22, min(1.5, 34.0 / max(rel_v, 1.0)))
        i0 = int(max(0, (t_at - width * 2.2) * SR))
        i1 = int(min(n, (t_at + width * 2.2) * SR))
        if i1 - i0 < 128:
            continue
        seg = np.arange(i1 - i0) / SR - (t_at - i0 / SR)

        env = np.exp(-(seg / width) ** 2)
        near = 1.0 / (1.0 + (dmin / 7.0) ** 2)
        amp = 0.42 * near * (1.25 if car["length"] > 5.0 else 1.0)

        # Doppler: brighter approaching, darker receding
        shift = 1.0 + (rel_v / 340.0) * np.tanh(-seg / max(width, 1e-3)) * 2.0
        noise = _pink(i1 - i0, rng)
        body = _fast_bandpass(noise, 120.0, 2600.0)
        hiss = _fast_bandpass(noise, 1800.0, 9500.0)
        w = (body * 0.8 + hiss * 0.5 * np.clip(shift, 0.5, 1.6)) * env * amp

        # pan by which side it went, and how far out
        p = float(np.clip(dx / 7.5, -1.0, 1.0))
        gl = math.sqrt(0.5 * (1.0 - p))
        gr = math.sqrt(0.5 * (1.0 + p))
        left[i0:i1] += w * gl
        right[i0:i1] += w * gr

    return left, right


# ---------------------------------------------------------------------- mixing

def _read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
        width = w.getsampwidth()
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
    a = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    a /= float(np.iinfo(dtype).max)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return x
    n = int(len(x) * dst / src)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def _write_wav(path: str, left: np.ndarray, right: np.ndarray) -> None:
    peak = max(np.abs(left).max(), np.abs(right).max(), 1e-9)
    if peak > 0.97:
        left, right = left * (0.97 / peak), right * (0.97 / peak)
    inter = np.empty(len(left) * 2)
    inter[0::2] = left
    inter[1::2] = right
    pcm = (np.clip(inter, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def build(motion_path: str, out_path: str, narration: str | None = None,
          music: str | None = None, seed: int = 7,
          bed_gain: float = 1.0, vo_gain: float = 1.0,
          music_gain: float = 0.42) -> dict:
    with open(motion_path) as fh:
        motion = json.load(fh)
    rng = np.random.default_rng(seed)
    n = int(motion["duration"] * SR)

    bed = ego_bed(motion, rng) * bed_gain
    pl, pr = passbys(motion, rng)
    left = bed + pl
    right = bed + pr

    layers = ["ego bed", f"{int((np.abs(pl) > 1e-4).any()) and 'pass-bys' or 'pass-bys'}"]
    info = dict(duration=motion["duration"], cars=len(motion["cars"]))

    if music and os.path.exists(music):
        m, sr = _read_wav(music)
        m = _resample(m, sr, SR)
        m = np.resize(m, n) if len(m) < n else m[:n]
        left += m * music_gain
        right += m * music_gain
        layers.append("music")

    if narration and os.path.exists(narration):
        vo, sr = _read_wav(narration)
        vo = _resample(vo, sr, SR)
        if len(vo) < n:
            vo = np.concatenate([vo, np.zeros(n - len(vo))])
        else:
            vo = vo[:n]
        # duck the bed under speech so the voice stays intelligible
        env = _fast_lowpass(np.abs(vo), 6.0)
        env /= (env.max() + 1e-9)
        duck = 1.0 - 0.62 * np.clip(env * 2.2, 0.0, 1.0)
        left = left * duck + vo * vo_gain
        right = right * duck + vo * vo_gain
        layers.append("narration (ducked)")

    _write_wav(out_path, left, right)
    info.update(out=out_path, layers=layers,
                bytes=os.path.getsize(out_path))
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--motion", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--narration")
    ap.add_argument("--music")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--bed-gain", type=float, default=1.0)
    ap.add_argument("--music-gain", type=float, default=0.42)
    a = ap.parse_args()
    info = build(a.motion, a.out, a.narration, a.music, a.seed,
                 a.bed_gain, 1.0, a.music_gain)
    print(json.dumps(info))


if __name__ == "__main__":
    main()
