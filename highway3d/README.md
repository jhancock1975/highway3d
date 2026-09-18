# toon-highway

Cartoonish-realistic highway-drive footage. Real 3D geometry, real lighting,
toon shading on top. Blender does the rasterising; everything in the scene is
generated from code, so curvature, traffic density and time of day are knobs
rather than assets.

```
python3 toon.py describe                              # every option, as JSON
python3 toon.py preview --out look.png --at 2,8,14    # contact sheet, ~1s/frame
python3 toon.py render  --out drive.mp4 --duration 20
```

`./setup.sh` installs Blender and ffmpeg if missing and fetches the CC0 car
models. `toon.py` runs on the system Python and shells out to Blender, so you
never invoke Blender directly.

## Why this exists

The earlier renderer (`../highway/highway.py`) rasterises in pure Python with a
painter's algorithm. Two things it cannot fix without becoming a real renderer:

- **Vehicles overlap wrongly.** Faces are sorted by average depth per object, so
  a car passing in the oncoming lane can be drawn over one that is nearer,
  which reads as cars being see-through.
- **Bodies are boxy.** They are extruded slabs, because anything better means
  shipping mesh data.

Both go away here. Blender uses a real depth buffer, so occlusion is exact, and
the vehicles are actual modelled meshes.

## What it draws

A curving, rolling dual carriageway: three lanes each way, grass median with a
jersey barrier, hard shoulders, guardrail, lighting masts, roadside planting and
rolling terrain out to the horizon. Traffic runs in both directions, every
vehicle at its own speed, so cars overtake and fall back around you. At dusk and
night the masts and vehicle lamps light up and the camera car throws real beams
down the road.

## Assets

| what | source | licence |
| --- | --- | --- |
| vehicles (50 models) | [Kenney Car Kit](https://kenney.nl/assets/car-kit) | CC0 |
| everything else | generated in `scene.py` | - |

Kenney's CC0 terms need no attribution, but crediting them is appreciated.
Nothing else is downloaded at render time; the scene has no other dependencies.

The kit's palette atlas (`colormap.png`) is what carries windscreens, lights,
grilles and bumpers. Do not replace vehicle materials with a flat colour -- you
lose every one of those details and the cars turn into blobs.

## How it works

| stage | what happens |
| --- | --- |
| geometry | The road is two functions of distance, `Road.x(s)` and `Road.z(s)`. Lane markings, barriers, planting, terrain and traffic are all placed by `(s, u)` -- distance along and lateral offset from the centreline -- so curvature and hills are a single knob each. |
| meshes | Ribbons, extruded slabs and low-poly blobs are written straight into `bpy` meshes. Trees and masts are merged into a handful of meshes rather than thousands of objects. |
| vehicles | Each GLB is imported once as a prototype, then instanced as linked duplicates that share mesh data. Every part keeps its transform relative to the car root, so wheels stay in their arches and can spin on their own axle. |
| rounding | Prototype meshes are bevelled and Catmull-Clark subdivided once, before instancing, so 14 models pay the cost rather than 120 vehicles. |
| shading | `Diffuse BSDF -> Shader to RGB -> banded ColorRamp`, multiplied by the base colour, plus a hard-edged specular and a fresnel rim. `Shader to RGB` is EEVEE-only; it is what makes toon shading possible over real lighting. |
| sky | Procedural multiple-scattering sky, with the sun lamp aimed to match. A photographic HDRI was tried first and looks wrong -- real trees on the horizon behind toy cars. |
| fog | Per-material, from `Camera Data -> View Distance`, mixed toward the horizon colour by `1 - exp(-max(0, d - start)/D)`, capped at `fog_max`. Cheaper than volumetrics and exact at any range. |
| animation | Transforms are baked to LINEAR keyframes on every frame so EEVEE has motion vectors for shutter blur. |
| output | PNG sequence out of Blender, muxed to H.264 by ffmpeg. |

## Haze is what makes cars look see-through

If vehicles look translucent, it is almost certainly the fog, not a depth bug.
Every material fades toward the horizon colour with distance, and when that
colour is bright and the density is high -- golden hour especially -- a car at
150 m gets washed far enough toward the sky that it reads as semi-transparent.

Three controls keep it honest, per look in `LOOKS`:

- `fog_start` -- metres before haze begins, so nearby traffic is never touched.
- `fog_density` -- `D = 1/density` is the e-folding distance.
- `fog_max` -- the hardest any surface may fade, so nothing fully dissolves.

Before blaming geometry, check it numerically. Render with
`scene.render.film_transparent = True` and look at the alpha channel: opaque
geometry is alpha 1.0, and partial alpha should appear only as thin
antialiased silhouette edges. If the vehicles come back solid, the problem is
in the shading, not the depth buffer.

Two things that are *not* the cause, both measured rather than assumed:

- **Motion blur.** Changing the shutter from 0.5 to off moved 421 pixels out of
  921,600 on a frame full of fast oncoming traffic. It is not what makes cars
  look transparent.
- **Material alpha.** A red cube in front of a green one renders pure red; no
  colour bleeds through.

## Rule: anything that carries writing in life carries writing here

Street signs get legends, vehicles get plates. A blank green gantry board reads
as an unfinished placeholder and is the first thing a viewer's eye lands on,
because real highways have nothing blank on them.

`text_mesh` builds a flat mesh from a FONT curve -- Blender's default font is
always present, so it works headless with no asset dependency.
`plate_prototypes` merges a code into a white backing so each plate is a single
mesh with two material slots, and those are instanced across the traffic rather
than built per vehicle. `sign_legends` puts a legend on every gantry.

Anchor plates to the body bounds measured *after* `proportion_prototypes` and
`round_prototypes` have run. Using the raw model extents buries them inside the
bodywork, which is silent -- the plate renders, you just never see it.

## Rule: solid objects never pass through solid objects

Vehicles are not placed by an analytic formula. Traffic is simulated once at
build time and the render samples that history, because any scheme that
computes each car's position independently will eventually drive one through
another -- a faster car in a lane will reach a slower one, and nothing in the
formula stops it.

`Traffic._simulate` integrates a safe-following rule per lane, then applies a
hard positional clamp: a follower may not enter its leader's tail no matter
what the dynamics wanted. The clamp is what makes the rule an invariant rather
than something that holds while the parameters happen to be kind.

Two things had to be got right for the dynamics not to fight the clamp:

- **Start at equilibrium.** Initial gaps are `length + MIN_GAP + v * REACT`.
  Spawning tighter than the following distance triggers a braking cascade at
  t=0 that the brakes cannot resolve, and cars pile into each other.
- **A follower cannot close a gap on a leader with the same desired speed.**
  The chase camera drifted to 48 m and stayed there, because once it fell
  behind during warm-up its target speed matched the lead's. The chase camera
  is therefore locked to the lead car rather than simulated.

Verify after any change to `Traffic`:

```bash
blender -b -P test_no_overlap.py -- --look day --camera chase --duration 20
```

It checks every pair in every lane on every frame and exits non-zero on
overlap.

## Vehicle gotchas that cost real time

Three of these produced complaints before they were found. All are baked into
`scene.py` now, but they generalise to any imported vehicle kit.

**The models face -Y.** Kenney's front wheels sit at negative Y, the rear
wheels at positive. Everything downstream drives along +Y, so a car placed at
the road heading with no correction is driving in reverse -- which is exactly
what it looks like. `MODEL_FLIP` turns each car to match. Check any new kit
with a bounding-box dump before trusting its axis.

**Never put a non-uniform scale on the car root.** Blender applies the parent
scale *after* the child's own rotation, so a spinning wheel under a root scaled
`(1.20, 1.72, 1.55)` is sheared into a wobbling ellipse. The stretch to a real
footprint is baked into the body meshes and the wheel *positions* by
`proportion_prototypes`, leaving the root uniform.

**Roll the wheels at distance / rolling radius.** Using the wheel diameter, or
any other wrong constant, makes the tyres visibly slip -- and combined with
stroboscopic aliasing at 60 fps it reads as the car rolling backwards.
`WHEEL_RADIUS` is derived from the model dimensions and the uniform root scale.

**Cars need a contact shadow to sit on the road.** Sun shadows alone are not
enough at high sun, and with the toon style the darkest band is bright enough
that the vehicle appears to hover. `contact_shadow_material` draws a soft
radial patch under each car; it is `BLENDED`, alpha-driven by distance from
the plane centre, and excluded from casting its own shadow.

## Two styles

`--style soft` (default) shades with a Principled BSDF under AgX: real
specular, real ambient, filmic highlight rolloff, plus depth of field. It is
the feature-animation look -- the stylisation lives in the shapes, not in the
shading.

`--style toon` is the original hard cel banding via Shader to RGB. Both run on
the same geometry and lighting rig; only the material builder differs.

The two need different light levels and they are not interchangeable. Soft uses
`soft_sun` / `soft_sky` per look (sun near 6, sky near 0.2) because a physical
sky at full strength floods the scene with blue ambient and turns tarmac pale.
Toon uses `sun_energy` / `sky_strength` and must stay under 1.0 for the reasons
in the calibration section below.

## Trees are instanced, not merged

The first version merged every tree into one giant mesh: cheap, but it capped
each canopy at a 7-segment blob and the silhouette read as faceted -- the note
in review was "too Minecraft-like". `tree_prototypes` now builds six properly
made trees (tapered trunk, two or three limbs, three to five overlapping
smooth-shaded canopy lobes) and `plant_trees` instances them with random
rotation and scale. Far more geometry per tree, same render cost.

## Night needs re-calibrating per style, not just scaling

AgX rolls the low end down hard, so the toon-era night levels render nearly
black in the soft style. Three things carry a night frame, and all three are
style-dependent:

- `soft_sky` -- 2.6 at night against 0.20 in daylight. The sky is the only
  ambient there is once the sun is below the horizon.
- The camera beam spots -- 24,000 W in soft against 2,600 in toon.
- Lamp and tail-light emitters -- roughly 3x, and the mast heads 55 against 22.

The trap: the tarmac is deliberately darkened to 0.55 albedo in the soft style
to stop daylight sky-wash turning it pale blue. At night that same darkening
swallows the headlights, so the beams land on nothing. `dark` is now keyed off
`look["headlights"]` -- 0.90 for the lit looks, 0.55 for the daylight ones.

If a night frame comes back black, check the albedo before reaching for more
light.

## Where quality actually comes from

Measured on this scene, not assumed. Two knobs that look like quality settings
do almost nothing here:

| change | pixels differing by >10, out of 921,600 |
| --- | --- |
| `--fidelity draft` -> `max` | **0** (max per-pixel delta: 7/765) |
| `--samples 64` -> `512` | **62** (0.01%) |
| `--samples 8` -> `512` | 3,932 (0.43%, all silhouette edges) |

The fidelity result is structural, not a fluke. Every material outputs
**Emission**, and EEVEE's raytraced GI, screen-space reflections and fast-GI
approximation do not affect emission output. Raising them buys nothing and
costs render time. `--samples` is converged by 64; it only ever affected
antialiasing on edges.

So do not reach for render settings. Quality here comes from:

1. **Resolution.** The one lever with no diminishing return. 4K costs about
   1.7 s/frame versus 0.6 at 1080p.
2. **Geometry.** `--round` on the vehicles, the road ribbon step (2.5 m), and
   how much roadside furniture exists.
3. **Scene richness.** Gantries, sign boards, guardrail posts and marker posts
   are what stop a highway reading as an empty ribbon, and they are the first
   thing that shows when resolution goes up.

## Rounding without dissolving the car

Plain Catmull-Clark on a low-poly body shrinks it and thins the window frames.
`round_prototypes` first walks the mesh with bmesh, measures each edge's
dihedral angle, and writes a `crease_edge` attribute of 0.75 on anything above
48 degrees. Subsurf then runs with `use_creases`, so the defining edges hold
their position while the gentle surfaces round off.

It is baked into the 14 prototype meshes before any car is instanced, so the
cost is paid once rather than 120 times.

## The one calibration that matters

The toon ramp takes the diffuse response and buckets it into bands. That only
works while lighting lands roughly in `0..1`. The view transform is **Standard**,
so materials are authored as final colour with no tonemapping to rescue
highlights.

Raise `sun_energy` or `sky_strength` and every band clamps to the brightest one:
the image goes flat and white, cars lose their shading, and it looks worse the
harder you push. The sun sits near 1.7 W for daylight and the sky near 0.11 for
exactly this reason. If you change either, re-render a still and check that the
shadowed side of a car is still visibly darker than its lit side.

Switching to AgX or Filmic has the same effect from the other direction: they
re-tonemap colours that are already final and flatten the bands out.

## Notes for automation

- Every command prints one JSON object on stdout; failures exit non-zero with a
  one-line message on stderr.
- `describe` is the machine-readable contract: names, types, ranges, defaults
  and examples.
- Preview before you render.
- Same `--seed` and same options reproduce the same clip exactly.
- Cost scales with `width x height x samples x fps x duration`, and roughly
  doubles with motion blur on.

## Sound

The soundtrack is generated from the traffic simulation, not sampled:

```bash
blender -b -P motion_dump.py -- --look day --camera chase --duration 20 \
    --motion-out /tmp/motion.json
python3 audio.py --motion /tmp/motion.json --out track.wav --narration vo.wav
ffmpeg -i clip.mp4 -i track.wav -map 0:v -map 1:a -c:v copy -c:a aac -shortest out.mp4
```

`motion_dump.py` writes, per frame, the camera's speed and every nearby
vehicle's position relative to it. `audio.py` turns that into road roar and
engine from the camera's own speed, plus one Doppler-shifted whoosh per vehicle
that actually passes, panned to the side it actually went. Narration is mixed
in with the bed ducked under it. Only dependency is numpy.

Two things this buys over a sample library: no licence to track, and sound that
cannot drift out of sync, because picture and audio come from the same numbers.
It also catches content bugs -- counting audible pass-bys is how the oncoming
traffic layout was found to be running dry after a few seconds.

### Narration

Kokoro-82M, Apache 2.0, 53 voices, about 6x realtime on an M-series Mac with no
GPU contention against Blender. `uv venv .ttsvenv && uv pip install --python
.ttsvenv/bin/python kokoro soundfile`. Its G2P shells out to `uv` for a spaCy
model on first run, so `VIRTUAL_ENV` must be set or that install fails.

### Music

`music.py` writes a score rather than generating one with a model: four layers
-- pad, bass, arpeggio and a soft pulse -- over a looping progression, in three
moods (`drive`, `open`, `night`). numpy only.

```bash
python3 music.py --duration 20 --out music.wav --mood drive
```

The reason to write it is the same as for the sound effects: no weights to
fetch, no licence that follows the output, and the length comes out exact so it
never has to be looped or cut to fit the picture.

### Mixing

`audio.py --music --narration` layers score, bed and voice, ducking the backing
under speech. Check the balance rather than trusting it: measure windowed peaks
during speech against the gaps. Narration wants to land around 1.8-2x the
backing; a mean over a per-sample mask will read close to 1.0 even when the
balance is right, because speech is full of gaps between syllables.

### Model-based music, if it is ever wanted

Licence matters more than quality here, because the weights' licence follows
the output:

| model | licence | note |
| --- | --- | --- |
| ACE-Step | Apache 2.0 | the permissive pick; vocals and instrumentals |
| Stable Audio Open | Stability Community | commercial under $1M revenue; CC0/CC-BY training data |
| YuE2-3B | CC BY-NC 4.0 | **rejected** -- see below |
| MusicGen | CC BY-NC 4.0 | **non-commercial**, even self-hosted |

YuE2-3B was evaluated and dropped, so it does not need re-litigating. It is a
lyrics-to-song model, so it cannot narrate at all; its CC BY-NC 4.0 licence
follows the output and rules out commercial use even self-hosted; and it is
CUDA-first, needing a 24 GB NVIDIA GPU, with only unofficial community MLX
ports for Apple Silicon. ACE-Step does the same job under Apache 2.0.

## MCP server

Other agents drive the renderer over MCP rather than shelling out to Python,
which is what `AGENTS.md` asks for.

```bash
.mcpvenv/bin/python mcp_server.py --port 8766      # streamable HTTP at /mcp
```

Three tools, named so they do not collide with other servers a client may have
mounted: `highway_describe`, `highway_preview`, `highway_render`. Every
argument that has a closed set is enumerated in the schema -- given only a
parameter name a model invents values and the call comes back a refusal, so the
enums earn their keystrokes.

The server shells out to `toon.py` rather than importing `scene.py`, so the CLI
stays the single source of truth: add an option there and it appears here.

`highway_render` estimates wall clock before starting and refuses a job that
would outrun a typical client timeout, with the numbers to reduce, rather than
running for an hour and being killed. Port 8765 is taken by another project on
this machine, hence 8766.

## Files

```
toon.py     CLI: describe / preview / render. Runs on system Python.
scene.py    Runs inside Blender. Builds the scene and renders it.
setup.sh    Installs Blender + ffmpeg, downloads the CC0 models, smoke-tests.
mcp_server.py   MCP front end over streamable HTTP. Needs .mcpvenv (uv venv + mcp).
test_no_overlap.py  Asserts the no-interpenetration rule across a whole clip.
```

## Examples

```bash
# default: daylight, driver's eye, 20s
python3 toon.py render --out drive.mp4

# golden hour, chasing a lead car
python3 toon.py render --out golden.mp4 --look golden --camera chase

# night run, heavy traffic, low camera
python3 toon.py render --out night.mp4 --look night --camera bumper --traffic 1.4

# comic-book treatment: ink outlines on the vehicles
python3 toon.py render --out ink.mp4 --outline 0.02

# empty straight road, crisp frames
python3 toon.py render --out empty.mp4 --traffic 0 --curve 0 --hills 0 \
    --trees 0 --motion-blur false
```
