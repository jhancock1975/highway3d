---
name: highway-video
description: Render a procedural highway-driving video or still frame - a first-person, chase or bumper-cam drive down a curving multi-lane highway with traffic, at day, golden hour, dusk or night. Use when asked for a highway/driving/road video, b-roll of cars on a motorway, or a looping drive background. No 3D application required.
---

# Highway video

`highway/highway.py` renders highway-drive footage with a self-contained
software 3D renderer. It needs `ffmpeg` on PATH for video; Python deps bootstrap
themselves into a venv on first run.

## Use it

1. Read the contract:

   ```bash
   python3 highway/highway.py describe
   ```

   This prints every option with its type, range, default and help text, plus
   worked examples. Trust it over anything remembered.

2. **Preview before rendering.** A still frame costs a fraction of a second; a
   clip costs seconds to minutes. Check framing, time of day and density first:

   ```bash
   python3 highway/highway.py preview --out /tmp/check.png --at 2,8,14 --look golden
   ```

   Then look at the PNG before committing to a render.

3. Render:

   ```bash
   python3 highway/highway.py render --out drive.mp4 --duration 20 --look day
   ```

Both commands print a single JSON object on stdout and exit non-zero with a
one-line stderr message on bad input.

## Mapping a request onto the options

| the user asks for | flags |
| --- | --- |
| "driving at night" | `--look night` |
| "sunset / golden hour" | `--look golden` or `--look dusk` |
| "following a car" | `--camera chase` |
| "fast, low, aggressive" | `--camera bumper --speed-kmh 150` |
| "busy motorway" / "empty road" | `--traffic 1.8` / `--traffic 0` |
| "straight desert highway" | `--curve 0 --hills 0 --trees 0` |
| "crisper, less blurry" | `--motion-blur 1` |
| "a different version of the same thing" | change `--seed` |
| longer or shorter | `--duration SECONDS` |

## Cost

Scales with `width × height × supersample² × fps × duration × motion_blur`.
720p60 for 20 seconds is roughly 12 seconds of wall clock on 16 cores. For a
quick draft use `--supersample 1 --motion-blur 1`; for a final pass leave the
defaults. Ask before rendering anything over about two minutes of footage.

## Don't

- Don't edit the renderer to change a look that an option already covers.
- Don't render at 4K "just in case" — it is 9× the cost of 720p.
