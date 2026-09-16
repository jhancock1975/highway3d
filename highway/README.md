# highway

Procedural highway-drive video renderer. No Blender, no game engine, no model
files — a few hundred lines of software rasterisation on top of Pillow, piped
straight into ffmpeg.

```
python3 highway.py describe                           # every option, as JSON
python3 highway.py preview --out look.png --at 2,8,14  # contact sheet, ~0.5s/frame
python3 highway.py render  --out drive.mp4 --duration 20
```

`render` needs `ffmpeg` on PATH. Pillow and numpy are installed into `.venv`
beside the script on first run and the process re-execs into it, so the only
prerequisite is Python 3.9+.

## What it draws

A first-person (or chase, or bumper-height) drive down a curving, rolling dual
carriageway: three lanes each way, jersey barrier and oncoming traffic on one
side, guardrail, light masts and planting on the other, and a few dozen vehicles
each running its own speed so they overtake and fall back around you.

## How it works

| stage | what happens |
| --- | --- |
| geometry | The road is two functions of distance, `road_x(z)` and `road_y(z)`. Everything — lane markings, barriers, trees, traffic — is placed relative to those, so curvature and hills are a single knob each. |
| projection | Perspective projection with Sutherland–Hodgman clipping against the near plane, plus camera yaw (look-ahead), pitch (road gradient) and roll (banking into corners). |
| shading | Newell face normals, then flat shading from a directional sun, a hemisphere sky term and a ground-bounce term. Flat per face on purpose: the lighting is physical, the surfaces stay animated. |
| shadows | Object silhouettes are projected onto the road along the sun vector, convex-hulled, draped over the terrain height, and composited as one alpha layer under the upright geometry. |
| headlights | At dusk and night a smooth cone term (distance × lateral falloff) multiplies every near surface, so the light pool has no geometry and therefore no hard edges. |
| depth sort | Painter's algorithm. Near-coplanar surfaces (ground, median, tarmac, wear, markings) are drawn as separate passes, because equal depths in one sorted list interleave into stripes. |
| output | Motion-blur sub-samples are averaged, then saturation, contrast, vignette, bloom and grain are applied, and raw RGB goes down a pipe to `ffmpeg`. Nothing touches the disk in between. |

## Notes for automation

- Every command prints one JSON object on stdout; failures exit non-zero with a
  one-line message on stderr.
- `describe` is the machine-readable contract: option names, types, ranges,
  defaults and examples.
- Preview before you render. A preview frame is a fraction of a second; a
  20-second 720p60 clip is about 12 seconds on 16 cores.
- Cost scales with `width × height × supersample² × fps × duration × motion_blur`.
- Same `--seed` and same options reproduce the same clip exactly.

## Examples

```bash
# default: daylight, driver's eye, 20s
python3 highway.py render --out drive.mp4

# golden hour, long shadows, chasing a lead car
python3 highway.py render --out golden.mp4 --look golden --camera chase

# night run, heavy traffic, low camera
python3 highway.py render --out night.mp4 --look night --camera bumper --traffic 1.6

# empty straight road, crisp frames, flat colours
python3 highway.py render --out empty.mp4 --traffic 0 --curve 0 --hills 0 \
    --motion-blur 1 --detail 0
```
