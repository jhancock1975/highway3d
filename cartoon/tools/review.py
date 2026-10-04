"""Render a few frames from every shot and lay them out on labelled sheets,
so every shot is looked at before a long render -- not just the ones that
happen to get sampled.

    cartoon/.venv/bin/python -m cartoon.tools.review --film F --out DIR [--per 3] [--res 640x360]
"""
import argparse, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import fonts
from cartoon import chalk, script
from cartoon.sets import marks as MK

ap = argparse.ArgumentParser()
ap.add_argument("--film", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--script", default="scripts/the-flavor-of-nothing.yaml")
ap.add_argument("--per", type=int, default=3); ap.add_argument("--res", default="640x360")
ap.add_argument("--samples", default="12"); ap.add_argument("--shots", help="only these shot indices, e.g. 3,7")
a = ap.parse_args()
film = json.load(open(a.film))
work = os.path.dirname(os.path.abspath(a.film))
doc = script.load(a.script)
pngs = chalk.typeset(dict(doc["boards"], **MK.GHOSTS), os.path.join(work, "chalk"))
os.makedirs(a.out, exist_ok=True)
fps = film["fps"]
only = {int(x) for x in a.shots.split(",")} if a.shots else None
picked = []
for i, shot in enumerate(film["shots"]):
    if only is not None and i not in only:
        continue
    f0, f1 = int(round(shot["start"] * fps)), int(round(shot["end"] * fps)) - 1
    # a tenth in from each end, and evenly between
    lo, hi = f0 + (f1 - f0) // 10, f1 - (f1 - f0) // 10
    step = max(1, (hi - lo) // max(1, a.per - 1))
    frames = list(range(lo, hi + 1, step))[: a.per]
    key = "vision_void" if shot["setup"].startswith("vision_") else f"{shot['scene']}_{shot['time']}"
    sets = os.path.join(ROOT, ".work", "cartoon", "sets", f"{key}.blend")
    chalk.frames(film, pngs, lo, hi, os.path.join(work, "boards"), morning=shot["time"] == "morning")
    r = subprocess.run(["blender", "-b", sets, "-P", os.path.join(ROOT, "cartoon", "shot.py"), "--",
                        "--film", a.film, "--shot", str(i), "--boards", os.path.join(work, "boards"),
                        "--out", a.out, "--frames", f"{lo}:{hi}", "--step", str(step),
                        "--res", a.res, "--samples", a.samples], capture_output=True, text=True)
    ok = r.returncode == 0 and all(os.path.exists(os.path.join(a.out, f"f_{f:05d}.png")) for f in frames)
    print(f"shot {i:2d} {shot['setup']:14s} {frames} {'ok' if ok else 'FAILED'}", flush=True)
    if not ok:
        print("\n".join([l for l in (r.stdout + r.stderr).splitlines() if "Error" in l][-5:]))
    picked.append((i, shot["setup"], frames))

# sheets of eight shots, one row per shot, labelled (Pillow: this ffmpeg has no drawtext)
from PIL import Image, ImageDraw, ImageFont
font = ImageFont.truetype(fonts.path("caslon"), 24)
for n in range(0, len(picked), 8):
    rows = []
    for i, setup, frames in picked[n:n + 8]:
        ims = [Image.open(os.path.join(a.out, f"f_{f:05d}.png")).convert("RGB") for f in frames
               if os.path.exists(os.path.join(a.out, f"f_{f:05d}.png"))]
        if not ims:
            continue
        w, h = ims[0].size
        row = Image.new("RGB", (w * a.per, h), (20, 20, 20))
        for k, im in enumerate(ims):
            row.paste(im, (k * w, 0))
        d = ImageDraw.Draw(row)
        d.rectangle((0, 0, 260, 36), fill=(0, 0, 0))
        d.text((10, 5), f"{i}  {setup}", font=font, fill=(255, 255, 255))
        rows.append(row)
    sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    path = os.path.join(a.out, f"sheet_{n // 8:02d}.png")
    sheet.save(path)
    print("sheet", path)
