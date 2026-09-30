"""Fetch the CC0 props and textures the sets are dressed with.

    python3 -m cartoon.assets                 # everything the sets name
    python3 -m cartoon.assets ArmChair_01     # one

Stdlib only. Everything comes from Poly Haven (polyhaven.com, CC0: no
attribution required, none claimed) through its public API, into
assets/polyhaven/<name>/, and every file is checked against the MD5 the
API publishes for it -- a changed upstream asset would change the film.
assets/ is gitignored, like the highway's HDRIs and cars.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "assets", "polyhaven")
API = "https://api.polyhaven.com"
UA = {"User-Agent": "cartoon-assets/1.0"}

# what the study and the city are dressed with
MODELS = [
    "ArmChair_01", "standing_chalkboard_01", "scandinavian_masonry_heater",
    "book_encyclopedia_set_01", "decorative_book_set_01", "wooden_bookshelf_worn",
    "brass_candleholders", "wooden_candlestick", "fancy_picture_frame_01",
    "vintage_grandfather_clock_01", "tea_set_01", "WoodenTable_01", "GothicCabinet_01",
    "vintage_cabinet_01", "treasure_chest", "Lantern_01", "brass_goblets",
    "wooden_display_shelves_01", "side_table_01",
]
TEXTURES = ["wood_floor_worn", "herringbone_parquet", "plastered_wall_04", "wood_planks",
            "castle_brick_07", "snow_02", "roof_tiles_14", "fabric_pattern_07",
            "painted_plaster_wall", "dark_wooden_planks", "rough_plaster_brick_04"]
HDRIS = ["moonless_golf", "kloppenheim_02", "satara_night"]


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _fetch(url, path, md5=None):
    if os.path.exists(path) and (md5 is None or hashlib.md5(open(path, "rb").read()).hexdigest() == md5):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = _get(url)
    if md5 and hashlib.md5(data).hexdigest() != md5:
        raise RuntimeError(f"md5 mismatch for {url}")
    with open(path + ".part", "wb") as fh:
        fh.write(data)
    os.replace(path + ".part", path)
    return True


def model(name, res="2k"):
    files = json.loads(_get(f"{API}/files/{name}"))
    b = files["blend"].get(res) or files["blend"]["1k"]
    blend = b["blend"]
    out = os.path.join(DEST, name)
    got = _fetch(blend["url"], os.path.join(out, os.path.basename(blend["url"])), blend.get("md5"))
    for rel, f in blend.get("include", {}).items():
        got |= _fetch(f["url"], os.path.join(out, rel), f.get("md5"))
    return os.path.join(out, os.path.basename(blend["url"])), got


def texture(name, res="2k"):
    files = json.loads(_get(f"{API}/files/{name}"))
    out = os.path.join(DEST, "textures", name)
    maps = {}
    for key in ("Diffuse", "nor_gl", "Rough", "Displacement", "AO", "arm"):
        if key in files:
            f = files[key].get(res) or files[key].get("1k")
            f = f.get("jpg") or f.get("png") or f.get("exr")
            p = os.path.join(out, os.path.basename(f["url"]))
            _fetch(f["url"], p, f.get("md5"))
            maps[key] = p
    return maps


def hdri(name, res="2k"):
    files = json.loads(_get(f"{API}/files/{name}"))
    f = files["hdri"][res]["hdr"]
    p = os.path.join(DEST, "hdri", os.path.basename(f["url"]))
    _fetch(f["url"], p, f.get("md5"))
    return p


def path_of(name):
    """The .blend of a fetched model, or None."""
    d = os.path.join(DEST, name)
    if not os.path.isdir(d):
        return None
    for f in os.listdir(d):
        if f.endswith(".blend"):
            return os.path.join(d, f)
    return None


def main():
    want = sys.argv[1:] or MODELS + TEXTURES + HDRIS
    for n in want:
        try:
            if n in TEXTURES:
                texture(n)
            elif n in HDRIS:
                hdri(n)
            else:
                model(n)
            print("ok", n, flush=True)
        except Exception as e:  # keep going; say which failed
            print("FAILED", n, e, flush=True)


if __name__ == "__main__":
    main()
