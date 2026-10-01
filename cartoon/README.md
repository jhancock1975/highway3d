# cartoon

An animated short from a written dialogue: characters sculpted and rigged
from code, voices synthesised, faces driven by the phonemes actually spoken,
a set dressed with free CC0 props, a score, foley, and a camera plan -- all
from one YAML document.

The first film is **The Flavor of Nothing**: St. Petersburg, 1773, and a
nearly blind Leonhard Euler is visited by a small alien who does mathematics
by smell and taste. `scripts/the-flavor-of-nothing.yaml`.

```bash
# the whole film (speech, score, sets, every shot, mix, mp4) -- hours
cartoon/.venv/bin/python -m cartoon.build --script scripts/the-flavor-of-nothing.yaml \
    --out renders/the-flavor-of-nothing.mp4

# a few shots at draft size, to look at
cartoon/.venv/bin/python -m cartoon.build --script scripts/the-flavor-of-nothing.yaml \
    --out renders/draft.mp4 --res 960x540 --samples 24 --shots 3,7,12

# one frame from each of several shots
cartoon/.venv/bin/python -m cartoon.tools.sample --film .work/cartoon/the-flavor-of-nothing/film.json \
    --shots 3:650,7:1195 --out /tmp/look

# for other agents
cartoon/.venv/bin/python -m cartoon.mcp_server --port 8769
cartoon/.venv/bin/python cartoon/test_cartoon.py
```

## The document

```yaml
cast:
  euler:    {character: euler,    voice: euler}
  cinnamon: {character: cinnamon, voice: cinnamon}
boards:
  basel: '1 + \tfrac{1}{4} + \tfrac{1}{9} + \cdots'
scenes:
  - scene: study
    time: night
    beats:
      - euler: "One. Plus a quarter. Plus a ninth."
        act: write
        board: {write: basel}
        mood: absorbed
      - do: lick
        target: basel
        seconds: 2.4
```

A beat is a line (who says it, with an `act`, a `mood`, what goes on the
slate) or a wordless `do:` with a length. Every name a document may use is
in `vocab.py` and `moods.py`, and `test_cartoon.py` fails if one of them is
accepted but animated by nothing -- lectern once took `beat:` hints, wrote
them into its documents and read them nowhere, and an agent asking for "points
at the denominator" got a success message and a presenter standing still.

Nobody directs. `timeline.py` times every beat from the speech, blocks where
Cinnamon floats, schedules the slate, and picks a camera per beat by rules
(the speaker is seen; the lines that matter are close; a two-shot comes round
often enough that nobody loses the room), keeping every camera on one side of
the line between the two so screen direction never flips.

## Characters are sculpted, not downloaded

`sculpt.py` is a signed-distance-field modeller in forty lines of numpy
plus a surface-nets mesher. A cartoon is soft shapes melted into each other,
and a smooth minimum gives every join a fillet whose radius is a number in
the code; joining primitive meshes and remeshing -- lectern's first
presenter -- leaves a crease at every join, and that crease is what makes a
figure read as a doll. Each primitive carries a colour, which blends through
the same fillets (a rosy cheek fades into the jaw), and a label, which the
rig weights by: "this vertex is the ring finger" with nobody painting
anything.

Euler is drawn from Handmann's 1753 pastel -- the long nose, the knowing
smile, the right eye narrowed, the floppy satin cap, the teal striped banyan
-- twenty years older. Cinnamon is a floating cinnamon-brown bean with no
eyes at all: a nose far too big for its face is how it finds its way, moth
antennae that glow when it smells are how it looks round, and a frog's mouth
holds a tongue long enough to lick a slate across a desk. With no eyes, its
brows (bolder than Euler's, on a soft ridge where eyes would be), nose,
antennae and mouth carry every expression -- and when it tells a blind man
"neither have I", it means it.

Euler's sleeves are separate pieces weighted only to his arms. Fused to the
robe, as they were first sculpted, raising an arm to write dragged the robe's
flank up with it into a fin of skin under the armpit.

The face rig (`bl/face.py`) is computed from where the mouth and brows are:
jaw weights sharp inside the mouth (the split runs through empty space) and
soft beyond its corners (where it has to stretch like cheek), and every
shape key a smooth displacement field around a landmark. A new character
gets a working face from its sculpt alone. Eyes are balls with separate lid
shells (`bl/eyes.py`); the lid's real edge and its shadow on the ball are
most of what makes an eye read as alive.

## The performance

`bl/perform.py` computes every channel for the whole film every time and
bakes only the shot's frames. Springs on the antennae, the blink schedule,
where a head was turning from -- all depend on what came before, and a shot
computed from its own first frame would start them cold and pop at the cut.

Layers on separate clocks: visemes from the measured phonemes (lectern's
dominance model); the mood each line is played with, eased across beats,
the listener mirroring part of the speaker; blinks on pauses, breathing,
brows on stressed words; gaze with the eyes leading and the head following.
Euler is blind: he turns his face toward a voice and his eyes rest a little
off it. Cinnamon floats: position from the blocking with a manner (drift,
zip with anticipation and overshoot, a nose-first sniffing wander), bob,
banking into turns, squash and stretch that keeps its volume.

## Where the chalk goes

The hand is on an IK target, but the chalk sits in the fist beside the line
of the arm, so aiming the wrist at the writing leaves the chalk wherever the
geometry puts it. After the rest of the performance is keyed, `chalk_pass`
measures the chalk's tip on every writing frame and moves the target by the
miss, three times over: the tip lands within 6 mm of the text being written.

That only works if the text is within reach, and the first layout was not:
it assumed leaning moved his shoulder 25 cm toward the slate, when on the rig
it moves 4-6 cm (his spine bends low). Formulas sat up to 0.77 m away, his
arm locked straight, and his hand hung off the slate's edge while the chalk
wrote on without it. The slate is now placed, and the formulas laid out, so
everything he writes is within 0.40 m of his shoulder as measured in the
writing pose, and `test_cartoon.py` checks that against the measured number.
The far side of the slate carries older work, half rubbed out, that he could
only have written standing.

## What a frame costs

Measured on an M5 Max, EEVEE at 1920x1080:

| | per frame |
| --- | --- |
| first render | 43 s |
| shadow pool overflowing (2375 of 2048 pages) fixed | 19 s |
| subdivision off at render | **2.9 s** |

Two findings, both found by profiling rather than guessing. Five candle
flames, the moon, the fills and two antenna tips all casting shadows
overflowed EEVEE's virtual shadow pool: frames were slow *and* missing
shadows. Only lights that shape the picture cast now. And the sculpts are
already dense (2-4 mm voxels), so subdividing them again cost 15 of every
16 seconds a frame took and changed nothing visible even in a close-up:
render levels are 0, except on the thin eyelid shells.

## Sound

Voices are Kokoro blends with pitch and formants moved apart (lectern's
chain), each checked for intelligibility with Whisper rather than by ear:
Euler's full German accent took "minus one" to "minus fun", "growth" to
"gross" and his closing "wet dog" to "vet doc", so his Swiss accent keeps
only "ze" for "the" and a soft w. Word error: Euler 7%, Cinnamon 4%, most of
what is left Whisper writing "1737" in digits.

Foley is synthesised (`sound.py`): sniffs, licks, chalk, the clock and the
stove, the ship's hum and toot. The score is MusicGen-medium, one cue per
stretch of story, generated locally and laid to the film's timings
(`score.py`); it must run on its own, never beside a render (see the memory
note of 2026-09-26). The mix ducks the score under every line.

## Three interpreters, plus one

| runs where | does |
| --- | --- |
| `cartoon/.venv` | documents, timeline, slate frames, mix, assembly, MCP |
| `.ttsvenv` | Kokoro speech; MusicGen score |
| `lectern/.manimvenv` | typesetting the slate's formulas |
| Blender | sculpting, rigging, sets, performance, frames |

## Assets

Props and textures are Poly Haven's (CC0), fetched and checksummed by
`assets.py` into `assets/polyhaven/`. What Poly Haven does not have -- books
with Euler's titles on their spines, a Petersburg tiled stove, the slate,
the window, the whole street outside -- is built in `sets/`. Everything that
carries writing in life carries it here: spines, a bakery sign, a house
number, the jars in the visions.
