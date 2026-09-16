---
name: toon-highway
description: Render a cartoonish-realistic highway-driving video or still frame - real 3D geometry and real lighting, shaded with toon bands. First-person, bumper or chase camera, at day, golden hour, dusk or night. Use when asked for a highway/driving/road video, b-roll of cars on a motorway, stylised or cartoon driving footage, or a looping drive background.
---

# Toon highway video

`highway3d/toon.py` renders highway footage by building a scene in Blender and
shading it with a toon ramp laid over physically-lit geometry. Cars are real
CC0 models, so silhouettes and occlusion are correct; the stylisation is in the
shading, not in the shapes.

There is an older pure-Python renderer at `highway/highway.py`. It is faster to
start but draws with a painter's algorithm, so vehicles overlap incorrectly and
the bodies are boxy. **Prefer this one** unless someone explicitly wants the
old look or Blender is unavailable.

## Use it

1. Read the contract:

   ```bash
   python3 highway3d/toon.py describe
   ```

   Every option with its type, range, default and help text, plus worked
   examples. Trust it over anything remembered.

2. **Preview before rendering.** A still costs about a second; a clip costs
   minutes.

   ```bash
   python3 highway3d/toon.py preview --out /tmp/check.png --at 2,8,14 --look golden
   ```

   Then look at the PNG before committing to a render.

3. Render:

   ```bash
   python3 highway3d/toon.py render --out drive.mp4 --duration 20 --look day
   ```

Both commands print a single JSON object on stdout and exit non-zero with a
one-line message on stderr.

## First run on a new machine

```bash
./highway3d/setup.sh
```

Installs Blender and ffmpeg via Homebrew if missing, downloads the CC0 Kenney
Car Kit into `assets/`, and renders a tiny frame to prove the pipeline works.

## Mapping a request onto the options

| the user asks for | flags |
| --- | --- |
| "driving at night" | `--look night` |
| "sunset / golden hour" | `--look golden` or `--look dusk` |
| "following a car" | `--camera chase` |
| "fast, low, aggressive" | `--camera bumper --speed 42` |
| "busy motorway" / "empty road" | `--traffic 1.8` / `--traffic 0` |
| "straight desert highway" | `--curve 0 --hills 0 --trees 0` |
| "more cartoony" / "comic book" | `--style toon --outline 0.02` |
| "Pixar / Disney / feature-animation look" | `--style soft` (the default) |
| "cars look like they are floating" | contact shadows - already on; check `_contact` is running |
| "cars look like they are going backwards" | wheel roll rate or `MODEL_FLIP`; see README |
| "shallower / deeper focus" | `--dof 2.0` blurs more, `--dof 0` is all sharp |
| night frame comes back nearly black | check tarmac albedo (`dark`) before adding light - see README |
| "crisper, less blurry" | `--motion-blur false`, or lower `--shutter` |
| "cars look see-through / washed out" | lower `fog_density` or raise `fog_start` in `LOOKS` - not a depth bug |
| "rounder / softer cars" | `--round 1.5` (0 = raw faceted models) |
| "a different version of the same thing" | change `--seed` |
| longer or shorter | `--duration SECONDS` |

## Don't chase quality through render settings

Measured on this scene: `--fidelity draft` vs `max` changes **zero** pixels by
more than 10/765, and `--samples` is converged by 64. Every material outputs
Emission, which EEVEE's raytracing and GI passes do not touch, so those knobs
are inert here.

Quality comes from `--width/--height` (4K is the real lever), `--round`, and
how much roadside furniture the scene has. Spend time there.

## Cost

Scales with `width x height x samples x fps x duration`, and roughly doubles
with motion blur on. A 20-second 1080p60 clip is about six minutes on an
M-series GPU; a still is about a second. For a quick draft use
`--samples 16 --motion-blur false`. Ask before rendering more than about two
minutes of footage.

## Two styles

`--style soft` (default) is Principled BSDF under AgX with depth of field --
the feature-animation look, stylisation carried by the shapes. `--style toon`
is hard cel banding via Shader to RGB. They need different light levels
(`soft_sun`/`soft_sky` vs `sun_energy`/`sky_strength`) and are not
interchangeable; see the README before touching either.

## How the look works

Read `highway3d/README.md` before changing the shading. The short version:
every material is `Diffuse BSDF -> Shader to RGB -> banded ColorRamp`, which is
EEVEE-only, plus a sharp specular, a fresnel rim and per-material distance fog.
Output is emission, authored as **final colour** under a Standard view
transform.

## If someone reports see-through vehicles

It is the haze, not the depth buffer. Every material fades toward the horizon
colour with distance; a bright, dense fog makes mid-distance cars read as
translucent. Lower `fog_density`, raise `fog_start`, or lower `fog_max` for
that look in `scene.py`.

Verify before changing anything: render with `film_transparent = True` and
check the alpha channel. Opaque geometry is alpha 1.0, and partial alpha
should only appear on thin antialiased edges. Motion blur and material alpha
have both been measured and ruled out.

## Don't

- Don't raise `sun_energy` or `sky_strength` in `scene.py` without re-checking a
  still. The ramp expects lighting under 1.0; past that every band clamps to the
  brightest one and the image goes flat white.
- Don't switch the view transform to AgX or Filmic. It re-tonemaps colours that
  are already final and flattens the bands.
- Don't edit the scene to change something an option already covers.
- Don't render at 4K "just in case" - it is 4x the cost of 1080p.
