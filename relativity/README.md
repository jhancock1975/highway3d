# relativity

A narrated lecture on special relativity: stylised presenter, animated LaTeX
notation, and diagrams, assembled from code.

```bash
python3 build.py --out lecture.mp4 --fps 30           # the whole thing
python3 build.py --out test.mp4 --limit 3             # first three segments
python3 content.py                                    # word count and runtime
python3 visuals.py                                    # contact sheet of diagrams
python3 character.py                                  # the mouth-shape sheet
```

Needs the `.ttsvenv` (Kokoro) and `highway/.venv` (numpy, Pillow, matplotlib)
from the parent directory, plus ffmpeg.

## On the presenter

The figure is a caricature drawn from primitives -- flat shapes, exaggerated
hair, no attempt at photographic likeness -- and the voice is a synthetic
narrator that does not imitate anyone. A cartoon figure explaining real physics
is an ordinary teaching device. A photoreal synthetic person saying words they
never said is a different thing, and this deliberately is not that.

## How it fits together

| file | does |
| --- | --- |
| `content.py` | the script: what is said, and what is on screen while it is said |
| `character.py` | the presenter, pre-rendered once per mouth openness |
| `visuals.py` | title, bullet, math and diagram panels, each a function of phase |
| `build.py` | narrates, times, composites, encodes |

Timing runs from the speech, not the other way round. Each segment is
synthesised first and its real duration measured, then the picture is laid out
to fit, so nothing has to be nudged into sync afterwards. Change a sentence and
the video re-times itself.

Two things that keep a 35,000-frame render cheap: panels are cached per
quantised phase step rather than drawn per frame, and frames are piped straight
into ffmpeg instead of written out, which would be about 16 GB of scratch.

Math is set with matplotlib's `mathtext`, which renders LaTeX notation with no
TeX installation.

## Physics covered

Galilean relativity and its transformation; Maxwell's constant `c` and the
ether; Michelson-Morley; the two postulates; relativity of simultaneity; the
light-clock derivation of time dilation; length contraction; the Lorentz
transformation; relativistic velocity addition; the invariant interval and the
light cone; mass-energy; the twin paradox; relativistic Doppler; momentum and
the ladder-barn paradox; proper time; a worked numerical example; muons and
satellite clocks; and the equivalence principle as the bridge to general
relativity.
