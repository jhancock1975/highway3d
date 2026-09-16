#!/usr/bin/env python3
"""Cartoonish-realistic highway video renderer.

Front end for scene.py, which builds and renders the scene inside Blender.
Nothing here needs Blender's Python -- this runs on the system interpreter and
shells out, so it behaves like any other CLI tool.

    python3 toon.py describe                             # options, as JSON
    python3 toon.py preview --out look.png --at 2,8,14   # contact sheet
    python3 toon.py render  --out drive.mp4 --duration 20

Every command prints one JSON object on stdout and exits non-zero with a
one-line message on stderr.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(HERE, "scene.py")
ASSETS = os.path.abspath(os.path.join(HERE, "..", "assets"))

LOOKS = ["day", "golden", "dusk", "night"]
FIDELITY = ["draft", "high", "max"]
STYLES = ["soft", "toon"]
CAMERAS = ["driver", "bumper", "chase"]

OPTIONS = [
    ("out", "path", "drive.mp4", "Output file. .mp4 for render, .png for preview.", None),
    ("look", "str", "day", "Time of day. Sets sun angle, sky, haze; dusk/night light the lamps and headlights.", LOOKS),
    ("camera", "str", "driver", "driver = eye height; bumper = low and fast; chase = behind a lead car.", CAMERAS),
    ("width", "int", 1920, "Frame width in pixels.", (256, 3840)),
    ("height", "int", 1080, "Frame height in pixels.", (144, 2160)),
    ("fps", "int", 60, "Frames per second.", (12, 120)),
    ("duration", "float", 20.0, "Clip length in seconds.", (0.5, 600.0)),
    ("seed", "int", 7, "Changes traffic layout, roadside planting and road shape.", (0, 2 ** 31 - 1)),
    ("speed", "float", 31.0, "Camera speed in m/s (31 = 112 km/h). Traffic scales with it.", (5.0, 70.0)),
    ("traffic", "float", 1.0, "Vehicle density multiplier. 0 = empty road.", (0.0, 3.0)),
    ("lane", "int", 2, "Which lane the camera travels in, 1 = nearest the median.", (1, 3)),
    ("trees", "float", 1.0, "Roadside planting density.", (0.0, 3.0)),
    ("curve", "float", 1.0, "Horizontal curvature. 0 = dead straight.", (0.0, 3.0)),
    ("hills", "float", 1.0, "Vertical undulation. 0 = flat.", (0.0, 3.0)),
    ("lens", "float", 36.0, "Camera focal length in mm. Lower is wider.", (14.0, 85.0)),
    ("samples", "int", 48, "EEVEE samples per frame. More kills sampling noise in shadows and GI.", (1, 1024)),
    ("fidelity", "str", "high", "Render fidelity. draft = half-res tracing and cheap shadows; high = full-res tracing; max = full-res tracing at full trace quality, 4-ray/16-step shadows and no fast-GI approximation.", ["draft", "high", "max"]),
    ("motion_blur", "bool", True, "Shutter blur. Off is crisper and slightly faster.", None),
    ("shutter", "float", 0.22, "Shutter angle as a fraction of the frame. Above about 0.3 EEVEE's post-process blur smears fast oncoming traffic into semi-transparency.", (0.02, 1.0)),
    ("mb_steps", "int", 12, "Motion blur time samples. Low values ghost instead of smearing.", (2, 32)),
    ("round", "float", 1.0, "Rounds the vehicle bodies: bevelled creases, plus Catmull-Clark above 0.5. 0 = the raw faceted models, 1.5+ adds a second subdivision.", (0.0, 2.0)),
    ("style", "str", "soft", "soft = physically-lit rounded forms with filmic tonemapping (feature-animation look); toon = hard cel bands over the same geometry.", ["soft", "toon"]),
    ("dof", "float", 4.0, "Depth of field f-stop; lower blurs the background more. 0 = everything sharp.", (0.0, 32.0)),
    ("clouds", "float", 1.0, "Cumulus density on the sky dome. 0 = clear sky; higher breaks the cover into smaller, more numerous clouds.", (0.0, 4.0)),
    ("outline", "float", 0.0, "Inverted-hull ink outline on vehicles, in metres. 0 = off, 0.02 is a visible line.", (0.0, 0.1)),
    ("quality", "int", 16, "x264 CRF for the muxed video. Lower is better and bigger.", (0, 51)),
]


def describe():
    return {
        "name": "toon-highway",
        "summary": "Render a cartoonish-realistic highway-drive video: stylised "
                   "toon shading laid over real 3D geometry and real lighting.",
        "commands": {
            "describe": "Print this document as JSON.",
            "preview": "Render one frame, or a contact sheet, to a PNG. Cheap - "
                       "use it to check settings before rendering.",
            "render": "Render the clip to an H.264 .mp4.",
        },
        "extra_args": {
            "--at": "preview only: comma-separated timestamps in seconds, e.g. 2,8,14",
        },
        "options": [
            {
                "name": n, "flag": "--" + n.replace("_", "-"), "type": t,
                "default": d, "help": h,
                **({"choices": rng} if isinstance(rng, list) else {}),
                **({"min": rng[0], "max": rng[1]} if isinstance(rng, tuple) else {}),
            }
            for (n, t, d, h, rng) in OPTIONS
        ],
        "requires": {
            "blender": ">=4.2 on PATH (tested on 5.2 LTS); EEVEE, so a GPU helps",
            "ffmpeg": "render only",
            "assets": ASSETS + " (CC0: Kenney Car Kit). Run setup.sh to fetch.",
        },
        "output": "Every command prints a single JSON object on stdout. Exit "
                  "code 0 on success, non-zero with a message on stderr.",
        "notes": [
            "Cost scales with width*height*samples*fps*duration, and roughly "
            "doubles with motion_blur on.",
            "Same seed plus same options reproduces the same clip exactly.",
            "Traffic in the camera's own lane holds station ahead and never "
            "passes through the viewpoint.",
            "Preview first: a still is about a second, a 20s 1080p60 clip is "
            "about six minutes on an M-series GPU.",
            "The look is authored as final colour with a Standard view "
            "transform, so lighting is deliberately kept under 1.0. If you "
            "raise sun_energy in scene.py, the toon bands will clamp and the "
            "image goes flat white.",
        ],
        "examples": [
            "python3 toon.py preview --out /tmp/check.png --at 1,6,12 --look golden",
            "python3 toon.py render --out drive.mp4 --duration 20",
            "python3 toon.py render --out night.mp4 --look night --camera bumper --traffic 1.4",
            "python3 toon.py render --out ink.mp4 --outline 0.02 --look day",
        ],
    }


def fail(msg):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(1)


def need(tool):
    p = shutil.which(tool)
    if not p:
        fail(f"{tool} not found on PATH. See setup.sh.")
    return p


def scene_args(a):
    out = []
    for (n, t, d, _h, _r) in OPTIONS:
        if n in ("out", "quality"):
            continue
        v = getattr(a, n)
        out += ["--" + n, ("true" if v else "false") if t == "bool" else str(v)]
    return out


def run_blender(a, extra, quiet=True):
    cmd = [need("blender"), "-b", "-P", SCENE, "--"] + scene_args(a) + extra
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tail = "\n".join(r.stdout.strip().splitlines()[-12:])
        fail(f"blender failed ({r.returncode}):\n{tail}\n{r.stderr.strip()[-400:]}")
    return r


def cmd_preview(a):
    if not os.path.exists(os.path.join(ASSETS, "cars")):
        fail(f"assets missing at {ASSETS}; run setup.sh first")
    times = [float(x) for x in a.at.split(",") if x.strip()]
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix="toon_prev_")
    try:
        shots = []
        for i, t in enumerate(times):
            p = os.path.join(tmp, f"s{i}.png")
            r = run_blender(a, ["--still", str(t), "--out", p])
            if not os.path.exists(p):
                tail = "\n".join(r.stdout.strip().splitlines()[-14:])
                fail(f"blender wrote no frame for t={t}:\n{tail}")
            shots.append(p)
        if len(shots) == 1:
            shutil.copyfile(shots[0], a.out)
        else:
            ff = need("ffmpeg")
            ins = []
            for p in shots:
                ins += ["-i", p]
            n = len(shots)
            filt = "".join(f"[{i}]" for i in range(n)) + f"hstack={n}"
            r = subprocess.run([ff, "-v", "error", *ins, "-filter_complex",
                                filt, "-y", a.out], capture_output=True, text=True)
            if r.returncode != 0:
                fail("ffmpeg stitch failed: " + r.stderr.strip()[-300:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": True, "command": "preview", "out": a.out, "at": times,
            "seconds": round(time.time() - t0, 2)}


def cmd_render(a):
    if not os.path.exists(os.path.join(ASSETS, "cars")):
        fail(f"assets missing at {ASSETS}; run setup.sh first")
    ff = need("ffmpeg")
    frames = int(a.duration * a.fps)
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix="toon_seq_")
    try:
        run_blender(a, ["--start", "0", "--end", str(frames - 1),
                        "--out", os.path.join(tmp, "f_")])
        got = sorted(x for x in os.listdir(tmp) if x.endswith(".png"))
        if len(got) < frames:
            fail(f"blender wrote {len(got)} of {frames} frames")
        r = subprocess.run([ff, "-v", "error", "-framerate", str(a.fps),
                            "-i", os.path.join(tmp, "f_%04d.png"),
                            "-c:v", "libx264", "-crf", str(a.quality),
                            "-preset", "slow", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", "-y", a.out],
                           capture_output=True, text=True)
        if r.returncode != 0:
            fail("ffmpeg mux failed: " + r.stderr.strip()[-300:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": True, "command": "render", "out": a.out, "frames": frames,
            "fps": a.fps, "duration": a.duration, "width": a.width,
            "height": a.height, "look": a.look, "camera": a.camera,
            "bytes": os.path.getsize(a.out),
            "render_seconds": round(time.time() - t0, 2)}


def main():
    ap = argparse.ArgumentParser(add_help=True, description=__doc__)
    ap.add_argument("command", choices=["describe", "preview", "render"])
    ap.add_argument("--at", default="2,8,14")
    for (n, t, d, h, rng) in OPTIONS:
        flag = "--" + n.replace("_", "-")
        if t == "bool":
            ap.add_argument(flag, dest=n, default=d,
                            type=lambda s: str(s).lower() in ("1", "true", "yes", "on"),
                            help=h)
        else:
            ap.add_argument(flag, dest=n, default=d,
                            type={"int": int, "float": float}.get(t, str), help=h)
    a = ap.parse_args()

    if a.command == "describe":
        print(json.dumps(describe(), indent=2))
        return
    if a.look not in LOOKS:
        fail(f"--look must be one of {LOOKS}")
    if a.camera not in CAMERAS:
        fail(f"--camera must be one of {CAMERAS}")
    if a.fidelity not in FIDELITY:
        fail(f"--fidelity must be one of {FIDELITY}")
    if a.style not in STYLES:
        fail(f"--style must be one of {STYLES}")
    if a.command == "preview":
        if a.out.endswith(".mp4"):
            a.out = "preview.png"
        print(json.dumps(cmd_preview(a)))
    else:
        print(json.dumps(cmd_render(a)))


if __name__ == "__main__":
    main()
