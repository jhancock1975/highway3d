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
eyes and no brows: a nose far too big for its face is how it finds its way,
moth antennae that glow when it smells are how it looks round, and a small,
soft, smiling mouth with one buck tooth holds a tongue long enough to lick a
slate across a desk. The nose, the antennae, the cheeks and the mouth carry
every expression -- and when it tells a blind man "neither have I", it means
it.

Its mouth opens by a shape, not a jaw bone (`face.open_key`). A jaw hinged
behind a face that is all muzzle swung the chin back into the body as it
opened: a sunken pouch with a sharp rim under the mouth. And only its arms
follow its arm bones (`rig.limbs_only`): bone heat had given its chest a
share of them, every gesture opened a seam down its front, and the mouth's
rosy inside showed through. Its two hands share the finger labels, and from
the first sculpt its left fingers were weighted to its right hand's bones: when one
hand moved, a needle of skin stretched from the other. A test now fails the
build if any vertex follows a bone on the far side. And it bends through its
whole body when it nods (`_bean_bends`): bone heat had given it a neck it
does not have, a hinge just under the chin that folded into a V on every
tilt of the head.

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

## Hands that do not shake

Measured as the gap between each hand's path and a 7-frame smoothing of it,
before the fixes: 18 mm of jitter on Euler's free hand in ordinary dialogue,
a 241 mm jump at the end of each formula, a 3 Hz patter of temple taps for
the length of a line. Each was a rule written as if more motion meant more
life: a beat gesture on every stressed word, up in four frames; a laugh as a
4.5 Hz bounce of the hands; a chalk correction that switched on at a
threshold. Now beats are few, slow and small, the laugh is in his chest, taps
are two and timed to the word, and every chalk correction eases in and out
with the writing: 2 mm of jitter in dialogue.

## Nobody inside anybody

Cinnamon's marks are places in the room, and a lick spot was "in front of
the formula" -- which is where Euler sits, 45 cm out from the slate's
centre-right. Through every lick of the first three cuts it licked from
inside his chest. Now it licks from out past the slate's left edge, face to
face with him at his eye level, and the tongue crosses 60-70 cm of air past
his nose to the chalk, bowing round his head (`_round_euler`). The lick
camera finds, per lick, the angle from the audience's side that shows the
most chalk and tongue past both of them. From there the far end of every
formula is behind his head, and a tongue sweeping on to it read as a tongue
running into his mouth, so each lick stops while the tip is still well clear
of his face on screen -- and the wet streak on the slate stops with it,
because both come from one function (`sets/lick.py`), checked against his
rendered silhouette. The slurp, which has to take the whole board, gets its
own camera, raking along the slate from its left, searched together with
where Cinnamon hovers (over the slate's top edge) so that none of the chalk
is hidden behind either of them. Behind all of it, `space_pass`
pushes Cinnamon out of capsules round Euler's bones on any frame it comes
too close and logs what it had to do; a test fails if a lick spot comes
within reach of him again.

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
| `cartoon/.venv` | documents, timeline, slate frames, mix, assembly, MCP; fonttools for the tests |
| `.ttsvenv` | Kokoro speech; MusicGen score |
| `lectern/.manimvenv` | typesetting the slate's formulas |
| Blender | sculpting, rigging, sets, performance, frames |

## Fonts

Every font is under the SIL Open Font License, fetched on first use by
`fonts.py` at the repo's root from a pinned commit of the Google Fonts
repository, checked against git's hash of the file, and cached in
`.work/fonts` -- none is committed. Pinyon Script for the title and chapter
cards, Libre Caslon Display for the place card, the book spines and the
visions' labels, STIX Two for their mathematics, and Old Standard for the
Petersburg signs, which needs Cyrillic. They replaced macOS system fonts
named by path, which exist on no other system. A character a font has no
glyph for renders as nothing, so a test checks every string the film draws
against the font it is drawn in.

## Assets

Props and textures are Poly Haven's (CC0), fetched and checksummed by
`assets.py` into `assets/polyhaven/`. What Poly Haven does not have -- books
with Euler's titles on their spines, a Petersburg tiled stove, the slate,
the window, the whole street outside -- is built in `sets/`. Everything that
carries writing in life carries it here: spines, a bakery sign, a house
number, the jars in the visions.
