"""The presenter's voice: accent, timbre, and the phoneme timeline.

Runs under `.ttsvenv`, not under Blender.

Three things happen here, and the order matters. The text is phonemised, the
phonemes are bent into an accent, and only then is anything synthesised -- so
the phoneme timeline that drives the mouth is the accented one. His lips form
a `v` when he says "vell" by construction rather than by correction. Doing
the accent any other way (a different model, or filtering the audio
afterwards) would leave the mouth animating phonemes that are no longer being
said.

The timbre is then shifted so the voice belongs to nobody: pitch and formants
move independently, which no real throat does and no stock voice has.
"""

from __future__ import annotations

import re
import subprocess
import wave

import numpy as np

# One table, two interpreters: see lectern/delivery.py.
from lectern.delivery import DELIVERIES, delivery  # noqa: F401

# ------------------------------------------------------------------- accent

# Kokoro's inventory is misaki's, not the IPA chart: diphthongs arrive as
# capitals (A, I, Q, O), so rules written against a textbook never fire.
RULES = [
    (r"w", "v", 0.20),            # very vell
    (r"θ", "s", 0.30),            # think -> sink
    (r"ð", "z", 0.30),            # this -> zis
    (r"\bs(?=[tpk])", "ʃ", 0.45),  # straight -> shtraight
    (r"æ", "ɛ", 0.55),
    (r"a(?![ɪʊ])", "ɑ", 0.60),
    (r"ʌ", "ɑ", 0.70),
    (r"ɜː", "ɛɐ", 0.75),
    (r"dʒ", "tʃ", 0.80),
]

DEVOICE = {"z": "s", "d": "t", "v": "f", "b": "p", "ɡ": "k", "g": "k"}
DIACRITICS = "ːˈˌ̩ᵊ"

# Words whose sense survives no mangling. A charming "sink" for "think" is the
# point; an unintelligible proper noun is a bug.
PROTECTED = {"michelson", "morley", "lorentz", "maxwell", "galileo", "newton",
             "minkowski", "doppler", "einstein"}


def germanise(phonemes: str, strength: float = 0.8,
              protect: set[str] | None = None) -> str:
    """English pronounced as a German speaker pronounces it."""
    protect = protect or set()
    out = []
    for word in phonemes.split(" "):
        if word.strip(DIACRITICS + ".,;:!?").lower() in protect:
            out.append(word)
            continue
        w = word
        for pattern, replacement, need in RULES:
            if strength >= need:
                w = re.sub(pattern, replacement, w)
        if strength >= 0.40:
            i = len(w) - 1
            while i >= 0 and (w[i] in DIACRITICS or not w[i].isalpha()):
                i -= 1
            if i >= 0 and w[i] in DEVOICE:
                w = w[:i] + DEVOICE[w[i]] + w[i + 1:]
        out.append(w)
    return " ".join(out)


# ------------------------------------------------------------------- timbre

def _smooth(x, n):
    n = max(1, int(n))
    return np.convolve(x, np.ones(n) / n, mode="same")


def _bandpass(x, sr, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, n=len(x))


def hoarsen(a, sr, amount=0.45, breath=0.10, seed=7):
    """Shimmer and turbulence -- what a rough voice actually measures as.

    Not distortion: a hoarse voice is one whose folds vibrate irregularly, so
    this is cycle-to-cycle amplitude jitter plus breath noise gated by the
    speech envelope.

    Shimmer and breath are separate knobs because only one of them was the
    complaint. Shimmer is what reads as a rough, elderly voice and costs
    nothing in clarity. Breath is turbulent noise, and the single `amount`
    this used to ship at put it 16 dB below the voice -- a sixth of the
    amplitude, riding on every vowel -- which took the harmonic-to-noise
    ratio down to 9.9 dB. Below about 12 dB that stops being texture and
    starts being audible hiss behind the speech.

    The gate is the other half of it. Smoothed |a| normalised to its own
    maximum does not come back down between words -- connected speech keeps
    it up around a third of full scale -- so noise scaled by it never lets
    go. Squaring it above a floor makes it track the loud parts only, which
    is where turbulence at the folds actually happens.
    """
    if amount <= 0 and breath <= 0:
        return a
    rng = np.random.default_rng(seed)
    env = _smooth(np.abs(a), sr * 0.012)
    env = env / (env.max() + 1e-9)
    gate = np.clip((env - 0.12) / 0.88, 0.0, 1.0) ** 2
    out = a
    if breath > 0:
        noise = _bandpass(rng.standard_normal(len(a)), sr, 1400, 4500)
        noise = noise / (np.abs(noise).max() + 1e-9)
        out = out + noise * gate * breath * 0.22
    if amount > 0:
        shimmer = 1.0 + amount * 0.30 * _smooth(rng.standard_normal(len(a)),
                                                sr * 0.005)
        # Drive, not compression. The old 1.0 + amount * 0.9 put 1.54 into a
        # tanh, which squashes exactly the loudness differences that carry
        # emphasis -- half of what was being heard as monotone.
        out = np.tanh(out * shimmer * (1.0 + amount * 0.25)) / (1.0 + amount * 0.12)
    peak = np.abs(out).max()
    return out / peak * 0.97 if peak > 0 else out


def _stft(a, n_fft, hop):
    win = np.hanning(n_fft + 1)[:-1]
    x = np.concatenate([np.zeros(n_fft), a, np.zeros(2 * n_fft)])
    frames = 1 + (len(x) - n_fft) // hop
    S = np.empty((frames, n_fft // 2 + 1), dtype=complex)
    for i in range(frames):
        S[i] = np.fft.rfft(x[i * hop: i * hop + n_fft] * win)
    return S


def _istft(S, n_fft, hop, n):
    win = np.hanning(n_fft + 1)[:-1]
    out = np.zeros((S.shape[0] - 1) * hop + n_fft)
    wsum = np.zeros_like(out)
    for i in range(S.shape[0]):
        out[i * hop: i * hop + n_fft] += np.fft.irfft(S[i], n=n_fft) * win
        wsum[i * hop: i * hop + n_fft] += win ** 2
    out /= np.maximum(wsum, 1e-8)
    return out[n_fft: n_fft + n]


def formants(a, sr, ratio, n_fft=1024, hop=256, smooth_bins=28):
    """Move the resonances without moving the pitch.

    This is what makes the voice nobody's. Pitch and formants normally travel
    together -- a larger speaker has both a lower voice and a longer vocal
    tract -- so moving them apart puts the timbre somewhere no throat goes.
    Duration is untouched, so the phoneme timeline still lines up.
    """
    if abs(ratio - 1.0) < 1e-3:
        return a
    S = _stft(a, n_fft, hop)
    mag, phase = np.abs(S), np.angle(S)
    idx = np.arange(mag.shape[1])
    kern = np.ones(smooth_bins) / smooth_bins
    out = np.empty_like(mag)
    for i in range(mag.shape[0]):
        logm = np.log(mag[i] + 1e-9)
        env = np.convolve(logm, kern, mode="same")
        warped = np.interp(idx / ratio, idx, env, left=env[0], right=env[-1])
        out[i] = np.exp(logm - env + warped)
    return _istft(out * np.exp(1j * phase), n_fft, hop, len(a))


def pitch(src: str, dst: str, ratio: float) -> None:
    """Shift pitch through ffmpeg's WSOLA and put the duration back."""
    if abs(ratio - 1.0) < 1e-3:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, dst], check=True)
        return
    with wave.open(src) as w:
        sr = w.getframerate()
    af = f"asetrate={int(sr * ratio)},atempo={1.0 / ratio:.6f},aresample={sr}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", af, dst],
                   check=True)


def tilt(a, sr, presence=0.0, body=0.0):
    if presence == 0.0 and body == 0.0:
        return a
    X = np.fft.rfft(a)
    f = np.fft.rfftfreq(len(a), 1.0 / sr)
    g = np.ones_like(f)
    if presence:
        g *= 1.0 + presence * np.exp(-((f - 3000.0) / 1600.0) ** 2)
    if body:
        g *= 1.0 + body * np.exp(-((f - 200.0) / 180.0) ** 2)
    out = np.fft.irfft(X * g, n=len(a))
    peak = np.abs(out).max()
    return out / peak * 0.97 if peak > 0 else out


def load(path):
    with wave.open(path) as w:
        sr, n = w.getframerate(), w.getnframes()
        a = np.frombuffer(w.readframes(n), "<i2").astype(np.float64) / 32768.0
    return a, sr


def save(a, sr, path):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())


# ------------------------------------------------------------------- presets

PRESETS = {
    # The one chosen by ear from the candidates: a blended speaker nobody
    # ships, lifted and roughened.
    "einstein": dict(
        blend=[("bm_george", 0.5), ("am_michael", 0.3), ("bf_emma", 0.2)],
        accent="german", strength=0.8,
        pitch=1.12, formants=0.90,
        # `hoarse` was 0.60 and drove both the shimmer and the breath noise.
        # The roughness is worth keeping; the noise it dragged in with it was
        # measured at -16 dB relative to the voice and was plainly audible.
        hoarse=0.45, breath=0.10,
        presence=0.25, body=0.15,
    ),
}


