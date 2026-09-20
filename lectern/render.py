"""Render a shot, or a still to check one before committing to a shot.

Runs inside Blender:

    blender --background --factory-startup --python lectern/render.py -- \
        --out /tmp/look.png --shot mid --engine eevee

Two engines on purpose. Eevee is for looking at blocking, timing and
silhouette in seconds; Cycles is for the take you keep. At 24 fps a
twenty-four minute lecture is about 34,000 frames, so the difference between
them is an hour and a day and a half.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lectern.presenter import character  # noqa: E402
from lectern.stage import set as stage  # noqa: E402


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _enable_gpu() -> str:
    """Turn the Metal GPU on, and say which device Cycles will actually use.

    `cycles.devices` is empty until the preferences are refreshed, so setting
    `scene.cycles.device = "GPU"` on a fresh --factory-startup silently renders
    on the CPU instead: the first measurement here came out at 7s a frame,
    which over a 24-minute lecture is six days rather than one night.
    """
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return "CPU"
    prefs = addon.preferences
    try:
        prefs.compute_device_type = "METAL"
        for attr in ("get_devices", "refresh_devices"):
            if hasattr(prefs, attr):
                getattr(prefs, attr)()
        gpus = [d for d in prefs.devices if d.type == "METAL"]
        if not gpus:
            return "CPU"
        for d in prefs.devices:
            d.use = (d.type == "METAL")
        print("cycles device:", ", ".join(d.name for d in gpus), flush=True)
        return "GPU"
    except Exception as e:
        print("no GPU, falling back to CPU:", e, flush=True)
        return "CPU"


def configure(engine: str, width: int, height: int, samples: int,
              view: str = "standard"):
    scene = bpy.context.scene
    r = scene.render
    r.resolution_x = width
    r.resolution_y = height
    r.resolution_percentage = 100
    r.film_transparent = False
    r.fps = 24

    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.device = _enable_gpu()
    else:
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = max(16, samples // 4)
        for flag in ("use_raytracing", "use_shadows", "use_gtao"):
            if hasattr(scene.eevee, flag):
                setattr(scene.eevee, flag, True)

    if view == "standard":
        # Saturated and punchy, which is what a drawn look wants. AgX is built
        # to tame real camera highlights; on flat cartoon albedos it just
        # greys everything down.
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    elif view == "punchy":
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Punchy"
    else:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"


def build_scene(look: str, shot: str):
    stage.build(look)
    parts = character.build()
    stage.camera(shot, target=(0.0, 0.0, -0.02))
    return parts


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--shot", default="mid")
    ap.add_argument("--look", default="study")
    ap.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--view", default="standard",
                    choices=("standard", "punchy", "agx"))
    a = ap.parse_args(argv)

    began = time.time()
    clear()
    configure(a.engine, a.width, a.height, a.samples, a.view)
    build_scene(a.look, a.shot)

    bpy.context.scene.render.filepath = a.out
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print(f"RENDERED {a.out} in {time.time() - began:.1f}s "
          f"({a.engine}, {a.width}x{a.height})")


if __name__ == "__main__":
    main()
