# lectern

A narrated lecture, rendered from a document: a 3D presenter who speaks,
blinks and stages demonstrations, with notation on a chalkboard.

```bash
# check a lecture before spending hours on it
.ttsvenv/bin/python -c "from lectern import script as s; \
    d=s.load('lectures/relativity.yaml'); print(s.summary(d)); print(s.validate(d))"

# one shot, end to end
.ttsvenv/bin/python -m lectern.narrate --text "Time is not universal." --out .work/x
blender --background --factory-startup --python lectern/shot.py -- \
    --timeline .work/x.json --audio .work/x.wav --out renders/x.mp4 --engine eevee

# the whole thing -- .mcpvenv, not system python: build.py reads YAML
lectern/.mcpvenv/bin/python -m lectern.build --script lectures/relativity.yaml \
    --out renders/relativity.mp4 --quality draft

# for other agents
lectern/.mcpvenv/bin/python -m lectern.mcp_server --port 8767
```

## The lecture is a document, not a program

This replaces a 934-line `content.py` in which the script, the visual choices
and the drawing code were the same artifact — which is exactly why nothing
but that module could ever make a second lecture. Now the words and the
staging are `lectures/*.yaml` and the drawing lives here, where every lecture
can reach it.

```yaml
- say: "A moving rod is shorter along its motion, and only along it."
  beat: point
  stage: {demo: rod_contraction}
- say: "Which gives us the contraction formula."
  delivery: punch
  stage: {note: {heading: "Only along the motion", lines: ["L_x = L_{x,0}/\\gamma"]}}
```

Four stage kinds — `card`, `board`, `note`, `demo` — cover all 82 segments of
the relativity lecture. Camera work is not in the document: a caller should
not have to direct, and the planner picks a framing from the stage kind.

## Timing runs from the speech

Each segment is spoken first and its real duration measured; the picture is
then laid out to fit. Change a sentence and the video re-times itself, and
nothing has to be nudged into sync afterwards.

Kokoro hands back the phonemes it actually spoke, per-word timestamps and
per-phoneme durations alongside the audio, so the mouth is driven by a
measured timeline rather than by an amplitude envelope — which is why the
previous version gaped on loud vowels and stayed shut on quiet consonants
regardless of what was being said.

## The voice belongs to nobody

Three things, in this order, and the order is the point:

1. **Phonemise**, 2. **bend into the accent**, 3. **then synthesise**. The
   accent is a transform on the IPA (`w→v`, `θ→s`, `ð→z`, initial `s`+stop
   `→ʃ`, final devoicing), so the phoneme timeline driving the mouth is the
   accented one. His lips form a `v` when he says "vell" by construction.
   Proper nouns are protected: a charming "sink" for "think" is the point, an
   unintelligible "Michelson" is a bug.
2. **A blended speaker.** Voices are embedding vectors, so a weighted blend of
   three is a speaker none of them is.
3. **Pitch and formants moved apart.** No real throat does this — a bigger
   speaker has both a lower voice and a longer vocal tract — which is what
   puts the timbre somewhere no stock voice has been. Plus shimmer and gated
   breath noise for hoarseness.

Duration is preserved throughout, so the viseme track still lines up.

## Monotone was between the sentences, not inside them

Measured before changing anything, because the obvious fix would have been
the wrong one. Inside any single segment the pitch contour is fine: about
3.3 semitones of spread, which is ordinary speech. Across 24 consecutive
segments the baseline spanned **0.56 semitones** -- 156.9 Hz, sentence after
sentence, for twenty-three minutes. Every line was spoken at the same pitch,
the same rate and the same peak level, because every line went through the
same constants.

So the fix is not inside the synthesiser. `delivery.py` holds seven ways of
saying a line -- `open`, `build`, `plain`, `aside`, `punch`, `weight`, `wry`
-- as multipliers on pitch, rate and level, and the document marks which line
gets which. Unmarked lines are inferred: a chapter opens on `open`, its last
line lands on `weight`. Plus a wobble keyed on the words themselves, so two
lines marked the same way still differ and the narration cache stays valid.

Measured after: **2.43 semitones** across the same run of segments.

It lives in its own module rather than in `voice.py` because `script.py`
validates delivery names and runs under `.mcpvenv`, which has no numpy. The
alternative is the same table written twice, and this project has already
paid for that once -- see the demonstration lists, below.

## The hiss was the breath, not the shimmer

`hoarse` was one knob driving two effects. Shimmer -- cycle-to-cycle
amplitude jitter -- is what reads as a rough, elderly voice, and it costs
nothing in clarity. Breath noise is turbulence at the folds, and at 0.60 it
was measured **16 dB below the voice**, taking the harmonic-to-noise ratio to
9.9 dB. Below about 12 dB that stops being texture and becomes audible hiss.

Two things were wrong and only one was the level:

- **The gate never closed.** Smoothed `|a|` normalised to its own maximum sits
  around a third of full scale right through connected speech, so noise scaled
  by it hisses continuously instead of breathing with the voice. It is now
  squared above a floor, so it tracks the loud parts only.
- **The drive was compression.** `tanh` at 1.54 squashes the loudness
  differences that carry emphasis, which was the other half of the monotone.

Now `hoarse=0.45, breath=0.10`, and HNR is 11.8 dB. Looking for the noise in
the silences finds nothing, by the way -- the gaps measured 63 dB below the
speech before any of this. It was never in the silence; it was riding on the
vowels.

## Notation writes itself onto the board

Manim typesets it; Blender maps the result onto the chalkboard as an image
sequence mixed into the board's own material. Mixed in, not composited over
the frame: the writing takes the room's key light, dims where the board is in
shadow, and stays behind him when he crosses in front of it.

`Tex`, not `MathTex`. The lecture's 89 lines mix prose with inline `$...$`,
and `MathTex` would try to typeset "holds in every inertial frame" as an
expression and fail on it.

LaTeX is TinyTeX in `~/Library/TinyTeX`, which installs without admin rights
-- only setting PATH wants a password, and nothing here needs it on PATH.
Manim lives in its own `.manimvenv` so it cannot contaminate the TTS or MCP
environments.

## Three interpreters, on purpose

| runs where | does |
| --- | --- |
| `.ttsvenv` | Kokoro and torch: speaking, and measuring when each phoneme happened |
| `lectern/.manimvenv` | Manim and TinyTeX: typesetting the board |
| Blender | the set, the presenter, the performance, the frames |
| `lectern/.mcpvenv` | orchestration and the MCP server |

None can import the others. Pretending otherwise is how a renderer ends up
shipping a gigabyte of ML dependencies in order to draw a chalkboard.

## He is a figure, not a bust

The presenter had no body animation, and could not have had any. `build_body`
joined the torso, the neck and both arms into one mesh, voxel-remeshed it and
baked it, so below the collar there was a single rigid transform with nothing
worth keyframing on it. He also stopped at z = -0.69 above a floor at -0.98 --
a bust on an invisible plinth, which worked only because every framing cropped
him at the chest.

He now has separate upper arms, forearms, hands, thighs, shins and shoes on a
joint chain of empties, and he reaches the floor. Empties rather than an
armature: nothing here is skinned, the parts are rigid, and a joint chain is a
transform the animation code keyframes directly with no rig to maintain.

Three things that each looked like a rigging problem and were not:

- **Origins belong at the joint.** A limb rotates about the end it hangs from.
  A mesh centred on itself swings its own shoulder through the torso the first
  time it is keyframed.
- **Segments must overrun their joints.** A capsule that stops dead on its own
  origin leaves a gap you can see through at every shoulder, elbow and knee,
  and that gap is the whole difference between a body and a doll assembled
  from parts.
- **Bake before parenting.** Converting an object applies its modifiers in
  world space, so doing it after the chain is built bakes the parent's
  rotation into the child's mesh.

`animate_body` runs three layers on deliberately different clocks, because a
figure whose every part turns over at one rate reads as a mechanism: breath at
about thirteen a minute on the torso, weight shifting foot to foot every eight
seconds or so on the root, and gestures on the arms. Gestures start on a word
and never on a timer -- a stroke that lands between syllables is a twitch, one
that lands on a stressed vowel is emphasis -- and each runs anticipation,
overshoot, settle, release, with the forearm two frames behind the upper arm
so the arm arrives as a limb rather than as one rigid piece.

## Painting a cardigan onto a remesh

The V-neck, the tie and the cardigan opening were three slabs floating in
front of the chest, and no amount of nudging fixes that: the torso is a voxel
remesh, its front is a curve nobody wrote down, and a straight ellipsoid laid
on it stands 14 mm proud at the sternum and pokes out through the waist below.
Measured, that is exactly what it did. They are now material assignments on
the torso's own faces, which cannot come unstuck from a surface they are part
of.

Two ways to get that wrong, both silent, both found by rendering it:

- **`poly.center` is in the mesh's own frame.** The torso's origin is wherever
  `_join` left it -- at the chest sphere, 0.356 m up -- so thresholds written
  as world z were all shifted by that much, and the shirt ran from the collar
  to the navel. Every face gets *a* material either way, so nothing complains.
- **A V-neck is wide at the collar.** The first inequality had it widest at
  the apex and closed to nothing by the collar: 382 faces out of 45,432,
  which rendered as a stray patch on the chest.

## What a frame costs

Measured on an M5 Max at 1080p, not estimated. Every one of these was found
by profiling something that looked fine:

| | per frame | a 24-minute lecture |
| --- | --- | --- |
| starting point | 8.8s | 6 days |
| enable the Metal GPU properly | 5.8s | 4 days |
| bake the modifier stack once | 5.3s | 3.5 days |
| denoise on the GPU, not the CPU | **1.23s** | **~12 hours** |
| Eevee draft, bust | 0.15s | ~1.5 hours |
| Eevee draft, whole figure with arms | 0.285s | ~3.5 hours |

`cycles.devices` is empty until the preferences are refreshed, so setting
`scene.cycles.device = "GPU"` on a fresh `--factory-startup` silently renders
on the CPU. Remesh, subdivision and displacement are constant but were being
re-evaluated every frame, because the character is animated. And
OpenImageDenoise defaults to the CPU, where it was 4.7 of every 5.3 seconds —
the path tracing itself is about 0.6s.

## Shots are rendered in local time

A shot knows its own duration and nothing about where it sits. Timing is
speech-driven, so changing a sentence in chapter two shifts every start time
after it; a shot that knew its absolute position would be invalidated by an
edit three chapters away. Placement happens at assembly, which is cheap.
Everything is cached by a hash of its own inputs, so fixing a word re-renders
the shot that contains it and nothing else.

## For other agents

`mcp_server.py` speaks MCP over HTTP. It was written against a real client —
Cider, which ships no Python interpreter and connects as an MCP client — and
three of its properties come from that rather than from taste:

- **Rendering is a job.** `ToolServer.timeout` is 1200s; a final render is
  twelve hours. `lecture_render` starts it and returns; `lecture_status`
  reports.
- **A lecture can be built a few hundred tokens at a time**, because the
  caller may be a 27B model with a small budget. `lecture_define` takes the
  whole document for a client with room.
- **Answers are sentences and failures are words**, because a throw reads to
  that client as "no tool ran" and says nothing at all.

Every tool is prefixed `lecture_`: local names win a collision there, so a
name the client already uses would be silently dropped.

## On the presenter

A caricature assembled from primitives — the likeness is carried by the hair,
the moustache and the eyes, not by any attempt at a real face — and the voice
is synthetic and imitates nobody. A cartoon figure explaining real physics is
an ordinary teaching device. A photoreal synthetic person saying words they
never said is a different thing, and this deliberately is not that.

Hair is geometry rather than particles: real hair over 34,000 frames costs
days, and the recognition lives in the silhouette. It is a displaced mass with
shorter clumps standing out of it to break the outline — a displaced sphere
alone reads as cotton wool, because its silhouette stays convex, and bare
radiating spikes read as a sea urchin.


## Six bugs worth remembering

Each of these looked fine and was not, and each was found by looking at output
rather than trusting it.

**A declared width that was not the width.** Moving him clear of the board
introduced this one. Every demonstration reports a `width`, the framing used
it to decide what had to fit, and for most of them that was fine. Michelson's
interferometer rotates 88 degrees through the take: the declared width is the
footprint its plinth needs, not the space the plate sweeps, so the shot was
framed correctly on frame one and had the apparatus, the caption and a table
leg hanging off the right edge by the middle. Reported values describe what
something is for, not what it does. `staged_extent` samples the real
bounding box of every staged object every sixth frame and frames to the
union, which costs one depsgraph evaluation per sample against the two
hundred seconds the shot takes to draw.

**An `elif` that could never run.** Every demonstration segment also carries
notation, because the board deliberately keeps the chapter title up while a
demonstration plays. The staging read `if notation: ... elif demo: ...`, so
`notation` was always truthy and the demonstration branch had never executed
once. All twenty demonstrations rendered as an empty board with him talking
beside it -- he says "Galileo asks you to go below deck on a ship" over a
blank slate, for nineteen seconds. Nothing raises, nothing is missing from
the output, every frame renders, and it had survived every render of this
lecture. Found by pulling a frame out of a finished demonstration shot and
looking at it, which is the only thing that would have found it.

**Two hardcoded lists that disagreed.** `script.py` validated demonstration
names against one list and `demos/__init__.py` loaded them from another.
Three names were in the first and not the second, so `lecture_check` answered
"ready to render" and the job died thirty shots in -- and, because it had been
launched detached with no completion notification, left the machine idle for
six hours before anyone noticed. Both now read the modules off disk, so they
cannot disagree, and `preflight.py` stages everything the document names
before a single frame is drawn.

**`-shortest` on the mux.** Every shot renders a settle beat after the speech
so segments do not cut on the last syllable. `-shortest` truncated each one to
its speech track and threw all of them away -- two and a half hours of
rendering those frames, discarded at the final step, and 82 hard cuts in the
finished lecture. The picture is the master now, and the audio is padded to
meet it.

**A missing-texture magenta.** Notation sequences shorter than their shot made
the board turn bright pink two-thirds of the way through, because Blender
renders magenta past the end of an image sequence. Sequences are padded to the
shot length.

**A unit off by two.** `primitive_cube_add(size=1.0)` scaled by `w / 2` is
`w / 2` across, not `w`, which put every table top at half the width of its
own legs. The `cube` helper takes real dimensions now.
