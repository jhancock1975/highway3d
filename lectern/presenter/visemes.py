"""Phonemes in, mouth shapes out.

Pure Python -- no bpy -- so it can be tested without launching Blender.

The input is the timeline `narrate.py` measured, which carries the accented
phonemes actually spoken and the real time each word occupied. Phonemes are
laid out inside their word, mapped onto a small set of mouth shapes, and then
smoothed, because a mouth that snapped between shapes on phoneme boundaries
would chatter: real articulation overlaps, and the shape of a sound is
already forming during the one before it.

Nine shapes rather than forty. Past about this many the extra fidelity is
invisible at 24 fps on a cartoon face, and every one of them is a shape
somebody has to be able to look at and recognise.
"""

from __future__ import annotations

# Kokoro speaks misaki's inventory: diphthongs arrive as capitals.
VISEMES = {
    #        open  wide  round
    "REST": (0.06, 1.00, 1.00),
    "AI":   (0.88, 1.16, 0.94),   # ɑ a I æ ɛ  -- jaw down
    "E":    (0.42, 1.32, 0.84),   # i ɪ iː e A -- spread
    "O":    (0.70, 0.82, 1.16),   # ɒ ɔ Q o Y  -- rounded
    "U":    (0.34, 0.62, 1.28),   # u uː ʊ     -- pursed
    "MBP":  (0.00, 1.02, 1.00),   # m b p      -- shut
    "FV":   (0.13, 1.06, 0.94),   # f v        -- lip to teeth
    "L":    (0.46, 1.00, 1.00),   # l ɹ r      -- tongue visible
    "S":    (0.22, 1.10, 0.96),   # everything else voiced through a gap
}

PHONEME_TO_VISEME = {}
for _group, _chars in {
    # misaki writes eɪ as A and aɪ as I (misaki/espeak.py: 'e^ɪ':'A',
    # 'a^ɪ':'I', 'a^ʊ':'W', 'ɔ^ɪ':'Y', 'o^ʊ':'O', 'ə^ʊ':'Q'), so "day" is
    # spread and "high" opens the jaw -- not the other way round.
    "AI": "ɑaIæɛʌɐW",
    "E":  "iɪeA",
    "O":  "ɒɔoQY",
    "U":  "uʊ",
    "MBP": "mbp",
    "FV": "fv",
    "L":  "lɹrɾ",
    "S":  "szʃʒtdnkɡghjʧʤθðŋ",
}.items():
    for _c in _chars:
        PHONEME_TO_VISEME[_c] = _group

SKIP = set("ˈˌːˑ̩ᵊ ")
PAUSE = set(".,;:!?\"'()")


def phoneme_units(phonemes: str) -> list[str]:
    """Split a phoneme string into units, dropping stress and length marks."""
    out = []
    for ch in phonemes:
        if ch in SKIP:
            continue
        if ch in PAUSE:
            out.append(".")
            continue
        out.append(ch)
    return out


def viseme_of(unit: str) -> str:
    if unit == ".":
        return "REST"
    return PHONEME_TO_VISEME.get(unit, "S")


def track(timeline: dict, fps: int = 24, smoothing: float = 0.045) -> list[dict]:
    """A mouth shape per frame for the whole segment.

    `smoothing` is the coarticulation time constant in seconds: how long the
    mouth takes to reach a shape it is heading for. Too small and the jaw
    chatters; too large and he mumbles.
    """
    duration = timeline["duration"]
    n = max(1, int(round(duration * fps)))

    # lay phonemes out inside the word that measured them
    events = []
    for w in timeline["words"]:
        units = [u for u in phoneme_units(w["phonemes"]) if u != "."]
        if not units:
            events.append((w["start"], "REST"))
            continue
        span = max(1e-4, w["end"] - w["start"]) / len(units)
        for i, u in enumerate(units):
            events.append((w["start"] + i * span, viseme_of(u)))
    events.sort(key=lambda e: e[0])

    # sample to frames, holding the last shape, resting past the end of speech
    target = []
    j = 0
    for f in range(n):
        t = f / fps
        while j + 1 < len(events) and events[j + 1][0] <= t:
            j += 1
        if not events or t < events[0][0]:
            target.append("REST")
        else:
            target.append(events[j][1])

    # smooth toward the target rather than snapping to it
    alpha = 1.0 - pow(0.001, 1.0 / max(1.0, smoothing * fps))
    cur = list(VISEMES["REST"])
    out = []
    for f in range(n):
        goal = VISEMES[target[f]]
        cur = [c + (g - c) * alpha for c, g in zip(cur, goal)]
        out.append(dict(frame=f, viseme=target[f],
                        open=round(cur[0], 4), wide=round(cur[1], 4),
                        round=round(cur[2], 4)))
    return out


# ---------------------------------------------------------------- visemes02
#
# The human presenter (presenter/human.py) carries the fifteen Meta/Oculus
# viseme shape keys from MakeHuman's visemes02 pack, sculpted on a real face
# with the teeth and tongue following. Those want weights, not the three
# numbers above, so this is a second, finer track over the same timeline.
#
# Coarticulation is a dominance blend (Cohen & Massaro): every speech segment
# pulls the mouth toward its shape with a strength that falls off either side
# of it, and each frame is the normalised mix of every pull still reaching it.
# Lips and teeth consonants pull hard and briefly, so a /p/ still shuts the
# mouth between two open vowels; vowels pull softly and long, so their shapes
# bleed across the consonants around them the way real speech does.

META = ("sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR",
        "aa", "E", "I", "O", "U")
KEYS = tuple("viseme_" + v for v in META)

_META_OF = {}
for _v, _chars in {
    "PP": "mbp",
    "FF": "fv",
    "TH": "θð",
    "DD": "tdɾ",
    "kk": "kɡgŋxh",
    "CH": "ʃʒʧʤ",
    "SS": "sz",
    "nn": "nl",
    "RR": "ɹrʁ",
    "aa": "ɑaæʌɐəᵊ",
    "E":  "ɛeɜɝ",
    "I":  "iɪj",
    "O":  "ɒɔo",
    "U":  "uʊwy",
}.items():
    for _c in _chars:
        _META_OF[_c] = _v

# misaki's diphthongs, split in time: (shape, share of the segment)
DIPHTHONGS = {
    "A": (("E", 0.55), ("I", 0.45)),    # eɪ  day
    "I": (("aa", 0.55), ("I", 0.45)),   # aɪ  high
    "O": (("O", 0.55), ("U", 0.45)),    # oʊ  go
    "Q": (("aa", 0.40), ("U", 0.60)),   # əʊ  go (British)
    "W": (("aa", 0.55), ("U", 0.45)),   # aʊ  now
    "Y": (("O", 0.55), ("I", 0.45)),    # ɔɪ  boy
}

VOWELS = set("ɑaæʌɐəᵊɛeɜɝiɪɒɔouʊy") | set(DIPHTHONGS)
WEAK = set("əᵊɐ")                         # reduced vowels barely move the jaw
STOPS = set("pbtdkgɡʧʤ")

# how far the jaw drops on top of each shape (ARKit jawOpen), before `jaw`
JAW = {"sil": 0.0, "PP": 0.0, "FF": 0.02, "TH": 0.10, "DD": 0.12,
       "kk": 0.16, "CH": 0.08, "SS": 0.04, "nn": 0.12, "RR": 0.12,
       "aa": 0.55, "E": 0.28, "I": 0.14, "O": 0.40, "U": 0.12}

# dominance: (strength, fall-off time constant in seconds)
_DOM = {"PP": (3.0, 0.025), "FF": (2.5, 0.025), "TH": (1.8, 0.030),
        "sil": (1.0, 0.070)}
_DOM_CONS = (1.3, 0.035)
_DOM_VOWEL = (1.0, 0.060)


def segments(phonemes: str) -> list[dict]:
    """One word's phonemes as speech segments.

    Each carries its mouth shape, a relative duration and an amplitude: stress
    marks promote the vowel after them, length marks stretch the one before,
    reduced vowels are quiet and quick. Diphthongs become two segments.
    """
    out = []
    stress = 0.0
    for ch in phonemes:
        if ch == "ˈ":
            stress = 1.0
            continue
        if ch == "ˌ":
            stress = max(stress, 0.6)
            continue
        if ch in "ːˑ":
            if out:
                out[-1]["dur"] *= 1.5
            continue
        if ch in PAUSE:
            out.append(dict(shape="sil", dur=1.5, amp=0.0, unit="."))
            continue
        if ch in SKIP and ch != "ᵊ":
            continue
        if ch in DIPHTHONGS:
            amp = 0.8 + 0.2 * stress
            for shape, share in DIPHTHONGS[ch]:
                out.append(dict(shape=shape, dur=2.4 * share, amp=amp, unit=ch))
            stress = 0.0
            continue
        shape = _META_OF.get(ch, "DD")
        if ch in VOWELS:
            if ch in WEAK:
                amp, dur = 0.55, 0.8
            else:
                amp, dur = 0.75 + 0.25 * stress, 1.7
            stress = 0.0
        else:
            amp, dur = 1.0, (0.9 if ch in STOPS else 1.0)
        out.append(dict(shape=shape, dur=dur, amp=amp, unit=ch))
    return out


def speech_events(timeline: dict, gap: float = 0.06) -> list[dict]:
    """Segments laid out in time inside the word that measured them.

    Silence becomes explicit `sil` events so the mouth relaxes in pauses
    instead of holding the last shape.
    """
    ev = []
    t_prev = 0.0
    for w in timeline["words"]:
        s, e = float(w["start"]), float(w["end"])
        if s - t_prev > gap:
            ev.append(dict(shape="sil", amp=0.0, s=t_prev, e=s, unit="."))
        segs = [g for g in segments(w["phonemes"]) if g["unit"] != "."]
        if not segs:
            t_prev = max(t_prev, e)
            continue
        total = sum(g["dur"] for g in segs)
        t = s
        for g in segs:
            d = (e - s) * g["dur"] / total
            ev.append(dict(shape=g["shape"], amp=g["amp"], s=t, e=t + d, unit=g["unit"]))
            t += d
        t_prev = max(t_prev, e)
    end = float(timeline["duration"])
    if end > t_prev:
        ev.append(dict(shape="sil", amp=0.0, s=t_prev, e=end + 1.0, unit="."))
    if not ev or ev[0]["s"] > 0:
        ev.insert(0, dict(shape="sil", amp=0.0, s=-1.0,
                          e=ev[0]["s"] if ev else end, unit="."))
    return ev


def _dominance(ev: dict, t: float) -> float:
    shape = ev["shape"]
    if shape in _DOM:
        strength, tau = _DOM[shape]
    elif shape in ("aa", "E", "I", "O", "U"):
        strength, tau = _DOM_VOWEL
    else:
        strength, tau = _DOM_CONS
    c = 0.5 * (ev["s"] + ev["e"])
    core = 0.35 * (ev["e"] - ev["s"])
    d = max(0.0, abs(t - c) - core)
    return strength * pow(2.718281828, -d / tau)


def weights(timeline: dict, fps: int = 24, jaw: float = 1.0,
            closure_frames: int = 1) -> list[dict]:
    """Per-frame weights for the visemes02 shape keys plus ARKit jawOpen.

    Returns one dict per frame::

        {"frame": f, "viseme": dominant shape,
         "weights": {"viseme_PP": 1.0, ...}, "jawOpen": 0.0}

    Weights sum to at most 1. `jaw` scales the jawOpen boost that makes the
    mouth read at cartoon distance. Every bilabial is guaranteed at least
    `closure_frames` frames of full closure (viseme_PP == 1.0, jaw shut), and
    every f/v at least one frame of lip-on-teeth: at 24 fps a /p/ is often
    shorter than a frame, and a mouth that never visibly closes on it reads
    as a dub.
    """
    ev = speech_events(timeline)
    n = max(1, int(round(float(timeline["duration"]) * fps)))
    out = []
    j0 = 0
    for f in range(n):
        t = f / fps
        while j0 < len(ev) and ev[j0]["e"] < t - 0.5:
            j0 += 1
        acc = {k: 0.0 for k in META}
        total = 0.0
        j = j0
        while j < len(ev) and ev[j]["s"] <= t + 0.5:
            d = _dominance(ev[j], t)
            total += d
            acc[ev[j]["shape"]] += d * ev[j]["amp"]
            j += 1
        w = {k: (acc[k] / total if total > 0 else 0.0) for k in META}
        w["sil"] = 0.0
        out.append(w)

    # hard contacts: lips shut on m/b/p, lower lip on the teeth for f/v
    for e_ in ev:
        if e_["shape"] not in ("PP", "FF"):
            continue
        c = 0.5 * (e_["s"] + e_["e"])
        frames = {min(n - 1, max(0, int(round(c * fps))))}
        f = int(e_["s"] * fps + 0.999)
        while f / fps < e_["e"] and f < n:
            frames.add(f)
            f += 1
        if e_["shape"] == "PP":
            frames = sorted(frames, key=lambda x: abs(x / fps - c))[:max(closure_frames, 1)] \
                if len(frames) > closure_frames else frames
            for f in frames:
                out[f] = {k: 0.0 for k in META}
                out[f]["PP"] = 1.0
        else:
            f = min(frames, key=lambda x: abs(x / fps - c))
            w = out[f]
            if w["PP"] < 1.0 and w["FF"] < 0.9:
                rest = sum(v for k, v in w.items() if k != "FF")
                scale = (0.1 / rest) if rest > 0.1 else 1.0
                for k in w:
                    w[k] = w[k] * scale if k != "FF" else 0.0
                w["FF"] = 0.9

    res = []
    for f, w in enumerate(out):
        j_open = 0.0 if w["PP"] >= 1.0 else jaw * sum(w[k] * JAW[k] for k in META)
        dom = max(META, key=lambda k: w[k]) if max(w.values()) > 0.05 else "sil"
        res.append(dict(frame=f, viseme=dom,
                        weights={"viseme_" + k: round(w[k], 4) for k in META},
                        jawOpen=round(j_open, 4)))
    return res


# -------------------------------------------------------------- the rest of
# the face. A mouth alone on a still face reads as a ventriloquist's dummy.

def _rng(seed):
    # small deterministic LCG so the track is reproducible without numpy
    state = [seed * 2654435761 % 4294967296 or 1]

    def r():
        state[0] = (1664525 * state[0] + 1013904223) % 4294967296
        return state[0] / 4294967296.0
    return r


def blinks(duration: float, fps: int = 24, per_minute: float = 17.0,
           seed: int = 1, timeline: dict | None = None) -> list[float]:
    """Per-frame eyelid closure (ARKit eyeBlinkLeft/Right), 0..1.

    People blink 15-20 times a minute while talking, each blink 150-200 ms:
    a fast close, a moment shut, a slower open. Intervals are irregular.
    Given a timeline, blinks prefer to land on pauses between phrases,
    which is where speakers actually blink.
    """
    r = _rng(seed)
    n = max(1, int(round(duration * fps)))
    mean = 60.0 / per_minute
    pauses = []
    if timeline:
        ws = timeline["words"]
        for a, b in zip(ws, ws[1:]):
            if b["start"] - a["end"] > 0.12:
                pauses.append(0.5 * (a["end"] + b["start"]))
    times = []
    t = 0.4 + r() * mean * 0.8
    while t < duration - 0.25:
        near = [p for p in pauses if abs(p - t) < 0.6]
        if near:
            t = min(near, key=lambda p: abs(p - t))
        times.append(t)
        # gamma-ish spacing: sum of two uniforms, never under 1.2 s
        t += max(1.2, mean * (0.45 + 0.55 * (r() + r())))
    v = [0.0] * n
    for t0 in times:
        close = 0.06 + 0.02 * r()
        hold = 0.02 + 0.02 * r()
        open_ = 0.08 + 0.03 * r()
        for f in range(max(0, int((t0 - 0.02) * fps)), min(n, int((t0 + close + hold + open_) * fps) + 2)):
            dt = f / fps - t0
            if dt < 0:
                x = 0.0
            elif dt < close:
                x = dt / close
            elif dt < close + hold:
                x = 1.0
            elif dt < close + hold + open_:
                x = 1.0 - (dt - close - hold) / open_
            else:
                x = 0.0
            v[f] = max(v[f], x * x * (3 - 2 * x))
        # make sure the lid actually reaches the bottom on some frame
        fc = min(n - 1, int(round((t0 + close + 0.5 * hold) * fps)))
        v[fc] = 1.0
    return v


def blink_times(track: list[float], fps: int = 24) -> list[float]:
    """Start times of the blinks in a blinks() track (for tests and logs)."""
    out = []
    was = False
    for f, x in enumerate(track):
        shut = x > 0.9
        if shut and not was:
            out.append(f / fps)
        was = shut
    return out


def brows(timeline: dict, fps: int = 24, seed: int = 2) -> dict[str, list[float]]:
    """Brow lifts on emphasis (ARKit browInnerUp, browOuterUpLeft/Right).

    A stressed, long word lifts the brows, the lift leads the word slightly
    and settles over half a second. Not every one -- that would read as
    permanent surprise -- at most one lift every two seconds.
    """
    r = _rng(seed)
    n = max(1, int(round(float(timeline["duration"]) * fps)))
    inner = [0.0] * n
    outer_l = [0.0] * n
    outer_r = [0.0] * n
    last = -10.0
    for w in timeline["words"]:
        dur = w["end"] - w["start"]
        if "ˈ" not in w["phonemes"] or dur < 0.28 or w["start"] - last < 2.0:
            continue
        if r() < 0.35:
            continue
        last = w["start"]
        amp = 0.35 + 0.3 * r()
        skew = 0.8 + 0.4 * r()
        t0 = w["start"] - 0.08
        for f in range(max(0, int(t0 * fps)), min(n, int((w["end"] + 0.7) * fps))):
            dt = f / fps - t0
            if dt < 0.15:
                x = dt / 0.15
            elif dt < 0.15 + dur:
                x = 1.0
            else:
                x = max(0.0, 1.0 - (dt - 0.15 - dur) / 0.5)
            x = x * x * (3 - 2 * x) * amp
            inner[f] = max(inner[f], x)
            outer_l[f] = max(outer_l[f], 0.6 * x * skew)
            outer_r[f] = max(outer_r[f], 0.6 * x / skew)
    return {"browInnerUp": inner, "browOuterUpLeft": outer_l,
            "browOuterUpRight": outer_r}


def face(timeline: dict, fps: int = 24, jaw: float = 1.0,
         blinks_per_minute: float = 17.0, seed: int = 1) -> dict[str, list[float]]:
    """Every animated face shape key for a segment, as per-frame value lists.

    Keys are shape key names on the MPFB professor: the fifteen viseme_*
    keys, jawOpen, eyeBlinkLeft/Right and the brow keys.
    """
    w = weights(timeline, fps=fps, jaw=jaw)
    n = len(w)
    out = {k: [fr["weights"][k] for fr in w] for k in KEYS}
    out["jawOpen"] = [fr["jawOpen"] for fr in w]
    b = blinks(float(timeline["duration"]), fps, blinks_per_minute, seed, timeline)
    out["eyeBlinkLeft"] = b[:n]
    out["eyeBlinkRight"] = b[:n]
    for k, v in brows(timeline, fps, seed + 1).items():
        out[k] = v[:n]
    return out
