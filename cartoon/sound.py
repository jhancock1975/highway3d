"""The soundtrack: dialogue where the film put it, foley synthesised from
what happens, the score under it, ducked when anyone speaks.

numpy + soundfile, under cartoon/.venv.

Every effect here is made, not downloaded: a sniff is band-passed noise in
three quick breaths, a lick is noise through a sweeping formant with a wet
pop at the end, chalk is gritty noise bursts on the rhythm of the writing,
the ship is a chord that bends. That keeps the whole film reproducible from
the repository and free of anyone's licence terms.
"""

from __future__ import annotations

import json
import math
import os

import numpy as np

SR = 48000


# ------------------------------------------------------------------ helpers

def _t(sec):
    return np.arange(int(sec * SR)) / SR


def _env(n, a=0.01, r=0.1):
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _bp(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, n=len(x))


def _lp(x, fc):
    a = math.exp(-2 * math.pi * fc / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def _norm(x, peak=0.9):
    m = np.abs(x).max()
    return x / m * peak if m > 0 else x


RNG = np.random.default_rng(1773)


def noise(sec):
    return RNG.standard_normal(int(sec * SR))


# ------------------------------------------------------------------ foley

def sniff(n=3, gap=0.16):
    out = []
    for i in range(n):
        d = 0.11 + 0.03 * RNG.random()
        x = _bp(noise(d), 1800, 6500) * _env(int(d * SR), 0.02, 0.06)
        x *= np.linspace(0.6, 1.0, len(x))
        out.append(x)
        out.append(np.zeros(int(gap * SR)))
    return _norm(np.concatenate(out), 0.6)


def lick(sec=1.2):
    """A wet, stretchy lick: noise through a formant that sweeps, a few
    saliva clicks, and a pop as the tongue leaves."""
    t = _t(sec)
    n = noise(sec)
    f = 700 + 900 * np.sin(np.pi * t / sec)
    out = np.zeros_like(n)
    # crude time-varying bandpass: sum of a few fixed bands weighted by f
    for fc in (500, 800, 1200, 1800, 2600):
        band = _bp(n, fc * 0.8, fc * 1.25)
        w = np.exp(-((f - fc) / 350.0) ** 2)
        out += band * w
    out *= _env(len(out), 0.05, 0.2) * (0.6 + 0.4 * np.sin(2 * np.pi * 7 * t) ** 2)
    for k in range(6):
        i = int(RNG.uniform(0.1, 0.9) * len(out))
        click = np.exp(-np.arange(400) / 60.0) * np.sin(2 * np.pi * 2500 * np.arange(400) / SR)
        out[i:i + 400] += click * 0.4
    pop = np.exp(-_t(0.06) / 0.012) * np.sin(2 * np.pi * (300 + 900 * _t(0.06) / 0.06) * _t(0.06))
    out = np.concatenate([out, pop * 1.2])
    return _norm(out, 0.55)


def chalk(sec, strokes_per_sec=5.0):
    """Chalk on slate: gritty bursts, each a short scrape, some squeaking."""
    out = np.zeros(int(sec * SR))
    t = 0.0
    while t < sec - 0.1:
        d = RNG.uniform(0.05, 0.16)
        i = int(t * SR)
        x = _bp(noise(d), 2500, 9000) * _env(int(d * SR), 0.005, 0.03)
        grit = (RNG.random(len(x)) < 0.02) * RNG.standard_normal(len(x)) * 3
        x = x + _bp(grit, 1500, 7000)
        if RNG.random() < 0.08:
            sq = np.sin(2 * np.pi * RNG.uniform(1800, 2600) * _t(d)) * _env(int(d * SR), 0.01, 0.03) * 0.3
            x = x + sq
        out[i:i + len(x)] += x[: len(out) - i]
        t += d + RNG.uniform(0.02, 1.0 / strokes_per_sec)
    return _norm(out, 0.35)


def knock(n=3):
    out = []
    for i in range(n):
        d = 0.25
        t = _t(d)
        thud = np.sin(2 * np.pi * 95 * t) * np.exp(-t / 0.03) + 0.5 * _bp(noise(d), 200, 1500) * np.exp(-t / 0.01)
        out.append(thud)
        out.append(np.zeros(int(0.12 * SR)))
    return _norm(np.concatenate(out), 0.8)


def creak(sec=1.3):
    t = _t(sec)
    f0 = 180 + 140 * np.sin(np.pi * t / sec) + 30 * np.sin(2 * np.pi * 3 * t)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    x = np.sign(np.sin(ph)) * 0.3 + np.sin(ph * 2.01) * 0.2
    x = _bp(x * (1 + 0.5 * (RNG.random(len(x)) - 0.5)), 250, 3000)
    return _norm(x * _env(len(x), 0.1, 0.3), 0.4)


def wind(sec, strength=1.0):
    n = noise(sec)
    lf = _lp(RNG.standard_normal(int(sec * 50) + 2), 0.5)
    g = np.interp(np.arange(len(n)) / SR * 50, np.arange(len(lf)), lf)
    g = 0.5 + 0.5 * (g - g.min()) / (np.ptp(g) + 1e-9)
    x = _bp(n, 150, 1200) * g * strength
    return _norm(x, 0.25 * strength)


def fire_and_clock(sec):
    """Room tone for the study at night: the stove's crackle and the
    grandfather clock, once a second."""
    out = _bp(noise(sec), 60, 400) * 0.05
    t = 0.0
    while t < sec:
        i = int(t * SR)
        if RNG.random() < 0.6:
            c = np.exp(-np.arange(600) / 80.0) * RNG.standard_normal(600)
            out[i:i + 600] += _bp(c, 800, 5000)[: len(out) - i] * RNG.uniform(0.1, 0.4)
        t += RNG.exponential(0.25)
    for k in range(int(sec)):
        i = int(k * SR)
        tick = np.exp(-np.arange(900) / 120.0) * np.sin(2 * np.pi * (2400 if k % 2 else 1900) * np.arange(900) / SR)
        out[i:i + 900] += tick[: len(out) - i] * 0.18
    return _norm(out, 0.3)


def sparkle(sec=1.6, up=True):
    """Magic: bell partials in a quick glissando."""
    out = np.zeros(int(sec * SR))
    notes = [523.25, 659.25, 783.99, 1046.5, 1318.5, 1568.0, 2093.0]
    if not up:
        notes = notes[::-1]
    for i, f in enumerate(notes):
        start = int(i * 0.08 * SR)
        t = _t(sec - i * 0.08)
        tone = sum(a * np.sin(2 * np.pi * f * m * t) for m, a in ((1, 1), (2.76, 0.4), (5.4, 0.2)))
        tone *= np.exp(-t / 0.5)
        out[start:start + len(tone)] += tone[: len(out) - start]
    return _norm(out, 0.35)


def chime():
    t = _t(3.0)
    f = 880.0
    x = sum(a * np.sin(2 * np.pi * f * m * t) for m, a in ((1, 1), (2.0, 0.5), (3.0, 0.25), (4.2, 0.15)))
    return _norm(x * np.exp(-t / 1.1), 0.4)


def ship_hum(sec, descend=True):
    t = _t(sec)
    bend = (1 - t / sec) if descend else t / sec
    f = 110 * (1 + 0.25 * bend)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.5 * np.sin(1.5 * ph) + 0.3 * np.sin(2.02 * ph)
    x *= 1 + 0.3 * np.sin(2 * np.pi * 6 * t)
    x += 0.3 * _bp(noise(sec), 300, 2500) * (np.sin(np.pi * t / sec) ** 2)
    return _norm(x * _env(len(x), 0.8, 0.8), 0.4)


def toot():
    """The pepper-mill ship's horn: two cheerful notes."""
    out = []
    for f, d in ((587.3, 0.18), (880.0, 0.32)):
        t = _t(d)
        x = np.sign(np.sin(2 * np.pi * f * t)) * 0.4 + np.sin(2 * np.pi * f * t) * 0.6
        x = _bp(x, 300, 4000) * _env(len(t), 0.01, 0.05)
        out += [x, np.zeros(int(0.05 * SR))]
    return _norm(np.concatenate(out), 0.5)


def whoosh(sec=0.6):
    t = _t(sec)
    x = _bp(noise(sec), 300, 3000) * np.sin(np.pi * t / sec) ** 2
    return _norm(x, 0.4)


def puff():
    w, s = whoosh(0.5), sparkle(1.0)
    out = s * 0.5
    out[: len(w)] += w * 0.6
    return _norm(out, 0.4)


def thump():
    t = _t(0.4)
    return _norm(np.sin(2 * np.pi * 60 * t) * np.exp(-t / 0.08) + 0.3 * _bp(noise(0.4), 100, 800) * np.exp(-t / 0.05), 0.6)


# ------------------------------------------------------------------ mixing

def _place(bus, clip, t, gain=1.0):
    i = int(t * SR)
    if i >= len(bus):
        return
    j = min(len(bus), i + len(clip))
    bus[i:j] += clip[: j - i] * gain


def _load(path):
    import soundfile as sf
    a, sr = sf.read(path, dtype="float64")
    if a.ndim > 1:
        a = a.mean(1)
    if sr != SR:
        n = int(len(a) * SR / sr)
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)
    return a


def foley(film):
    """Every effect, placed from the film's beats and board events."""
    dur = film["duration"] + 3
    bus = np.zeros(int(dur * SR))
    amb = np.zeros_like(bus)
    for sc in film["scenes"]:
        n = sc["end"] - sc["start"]
        if sc["scene"] == "petersburg":
            _place(amb, wind(n, 1.0 if sc["time"] == "night" else 0.5), sc["start"], 0.6)
        else:
            _place(amb, fire_and_clock(n) if sc["time"] == "night" else wind(n, 0.2) * 0.4, sc["start"], 0.5)
    for b in film["beats"]:
        d = b["do"]
        t0, t1 = b["start"], b["end"]
        if d == "ship_descends":
            _place(bus, ship_hum(t1 - t0), t0, 0.5)
            _place(bus, thump(), t1 - 0.9, 0.6)
        elif d == "window_opens":
            _place(bus, creak(), t0 + 0.3, 0.6)
            _place(bus, wind(2.5, 0.8), t0 + 0.6, 0.5)
            _place(bus, sniff(2), t1 - 1.0, 0.5)
        elif d == "lick":
            _place(bus, lick(max(0.8, t1 - t0 - 0.7)), t0 + 0.45, 0.8)
        elif d == "slurp":
            _place(bus, lick(t1 - t0 - 1.2) * 1.2, t0 + 0.8, 0.9)
            _place(bus, lick(0.8), t0 + 1.2, 0.5)
        elif d == "vision":
            _place(bus, sparkle(1.6, up=True), t0, 0.6)
            if b["vision"] == "nothing":
                _place(bus, chime(), t0 + 3.5, 0.7)
            else:
                _place(bus, sparkle(1.2, up=False), t1 - 1.0, 0.4)
        elif d == "ship_toots":
            _place(bus, toot(), t0 + 0.6, 0.7)
        elif d == "knock":
            _place(bus, knock(3), t0 + 0.4, 0.8)
        elif d == "skywriting":
            _place(bus, ship_hum(t1 - t0, descend=False), t0, 0.35)
        if b["who"] == "cinnamon" and b["act"] == "sniff":
            _place(bus, sniff(3), b["start"] + 0.1, 0.6)
        if b["who"] == "euler" and b["act"] == "sniff":
            _place(bus, sniff(2), b["start"] + 0.05, 0.4)
        if b["who"] == "cinnamon" and b["act"] == "puff":
            _place(bus, puff(), b["end"] - 0.8, 0.6)
        if b["who"] == "cinnamon" and b["act"] in ("exit", "spin"):
            _place(bus, whoosh(0.7), b["start"] + 0.4, 0.5)
        if b["who"] == "cinnamon" and b["act"] == "exit":
            _place(bus, ship_hum(4.0, descend=False), b["end"], 0.3)
    for e in film["board"]:
        if e["kind"] == "write":
            _place(bus, chalk(e["t1"] - e["t0"]), e["t0"], 0.55)
    return bus, amb


def dialogue(film):
    bus = np.zeros(int((film["duration"] + 3) * SR))
    env = np.zeros_like(bus)
    for b in film["beats"]:
        if not b["who"]:
            continue
        a = _load(b["speech"]["wav"])
        g = 0.62 if b["who"] == "fuss" else 1.0
        if b["who"] == "fuss":
            a = _bp(a, 250, 3500)       # through a door
        _place(bus, a, b["speech"]["start"], g)
        _place(env, np.ones(len(a)), b["speech"]["start"] - 0.25, 1.0)
        _place(env, np.ones(int(0.5 * SR)), b["speech"]["start"] + len(a) / SR, 1.0)
    env = np.clip(env, 0, 1)
    # smooth the ducking envelope so the music breathes rather than pumps
    k = int(0.3 * SR)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    return bus, env


def mix(film, music_path, out_path):
    import soundfile as sf
    dia, duck = dialogue(film)
    fx, amb = foley(film)
    n = len(dia)
    mus = np.zeros(n)
    if music_path and os.path.exists(music_path):
        m = _load(music_path)
        mus[: min(n, len(m))] = m[:n]
    music_gain = 0.30 * (1 - 0.72 * duck)
    out = dia * 0.95 + fx * 0.55 + amb * 0.35 + mus * music_gain
    # gentle limiter
    peak = np.abs(out).max()
    if peak > 0.98:
        out = np.tanh(out / peak * 1.4) / math.tanh(1.4) * 0.98
    stereo = np.stack([out, out], 1)
    # a little width for the music and ambience
    stereo[:, 0] += (mus * music_gain * 0.1 + amb * 0.05)
    stereo[:, 1] -= (mus * music_gain * 0.1 + amb * 0.05)
    sf.write(out_path, np.clip(stereo, -1, 1), SR, subtype="PCM_24")
    return out_path


if __name__ == "__main__":
    import sys
    film = json.load(open(sys.argv[1]))
    print(mix(film, sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3] if len(sys.argv) > 3 else "mix.wav"))
