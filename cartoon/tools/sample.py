"""Render one frame from each of several shots, for checking.

    cartoon/.venv/bin/python -m cartoon.tools.sample --film F --shots 1:360,3:650 --out DIR
"""
import argparse, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from cartoon import chalk, script

ap = argparse.ArgumentParser()
ap.add_argument("--film", required=True); ap.add_argument("--script", default="scripts/the-flavor-of-nothing.yaml")
ap.add_argument("--shots", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--res", default="1280x720"); ap.add_argument("--samples", default="32")
ap.add_argument("--engine", default="BLENDER_EEVEE")
a = ap.parse_args()
film = json.load(open(a.film))
work = os.path.dirname(os.path.abspath(a.film))
doc = script.load(a.script)
pngs = chalk.typeset(doc["boards"], os.path.join(work, "chalk"))
for spec in a.shots.split(","):
    sh, fr = map(int, spec.split(":"))
    shot = film["shots"][sh]
    key = "vision_void" if shot["setup"].startswith("vision_") else f"{shot['scene']}_{shot['time']}"
    sets = os.path.join(ROOT, ".work", "cartoon", "sets", f"{key}.blend")
    chalk.frames(film, pngs, fr, fr, os.path.join(work, "boards"), morning=shot["time"] == "morning")
    r = subprocess.run(["blender", "-b", sets, "-P", os.path.join(ROOT, "cartoon", "shot.py"), "--",
                        "--film", a.film, "--shot", str(sh), "--boards", os.path.join(work, "boards"),
                        "--out", a.out, "--frames", str(fr), "--res", a.res, "--samples", a.samples,
                        "--engine", a.engine], capture_output=True, text=True)
    err = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "Traceback" in l or "line " in l]
    print(sh, fr, "ok" if r.returncode == 0 and not err else "\n".join(err[-12:]), flush=True)
