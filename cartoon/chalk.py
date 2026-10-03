"""What is on the slate, frame by frame.

Two steps, in two interpreters:

1. `typeset(boards, work)` runs Manim (lectern/.manimvenv, TinyTeX) once per
   formula and keeps a white-on-transparent PNG of each.
2. `frames(film, f0, f1, out)` composes the slate for every frame of a shot
   under cartoon/.venv (numpy + Pillow): each formula at its place in
   marks.BOARD_LAYOUT, revealed left to right while it is being written,
   with chalk grain; a wet streak where the tongue went, drying over a few
   seconds; and the slurp, which takes everything.

The PNG's alpha is the chalk and its red channel is the wet -- the slate
material reads them separately (alpha_mode CHANNEL_PACKED), so the room's
light falls on both.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIM = os.path.join(HERE, "lectern", ".manimvenv", "bin", "python")
TEXBIN = os.path.expanduser("~/Library/TinyTeX/bin/universal-darwin")

# board texture resolution; the slate is 0.95 x 0.72 m
BW, BH = 2048, 1552

SCENE = '''from manim import *
config.frame_width = 16
class F(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        t = MathTex(r"""{tex}""", color=WHITE)
        t.set_stroke(WHITE, width=1.2)
        t.scale_to_fit_height({h})
        self.add(t)
'''


def typeset(boards: dict, work: str) -> dict:
    """{name: png path} for every formula, rendered once and cached."""
    out = {}
    work = os.path.abspath(work)
    os.makedirs(work, exist_ok=True)
    env = dict(os.environ, PATH=os.environ.get("PATH", "") + ":" + TEXBIN)
    for name, tex in boards.items():
        key = hashlib.sha256(tex.encode()).hexdigest()[:12]
        png = os.path.join(work, f"{name}-{key}.png")
        if not os.path.exists(png):
            d = os.path.join(work, f"scene-{name}-{key}")
            os.makedirs(d, exist_ok=True)
            py = os.path.join(d, "f.py")
            with open(py, "w") as fh:
                fh.write(SCENE.format(tex=tex, h=1.6 if "prod" not in tex else 2.6))
            r = subprocess.run([MANIM, "-m", "manim", "render", "-s", "--format=png", "--transparent",
                                "-r", "3200,1800", "--media_dir", d, py, "F"],
                               capture_output=True, text=True, env=env, cwd=d)
            if r.returncode != 0:
                raise RuntimeError(f"typesetting {name} failed: " + (r.stderr or r.stdout)[-600:])
            found = None
            for root, _, files in os.walk(d):
                for f in files:
                    if f.endswith(".png"):
                        found = os.path.join(root, f)
            _crop(found, png)
        out[name] = png
    return out


def _crop(src, dst):
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    im.crop(bbox).save(dst)


# ------------------------------------------------------------- composing

def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class Board:
    """Composes slate frames. Build once per shot; call frame(t)."""

    def __init__(self, film, pngs, layout):
        import numpy as np
        from PIL import Image
        self.np = np
        self.events = film["board"]
        self.layout = layout
        self.glyph = {}
        rng = np.random.default_rng(5)
        # chalk grain: dusty, broken strokes
        g = rng.random((BH, BW)).astype(np.float32)
        g = 0.55 + 0.45 * g
        self.grain = g
        for name, p in pngs.items():
            u0, u1, v, h = layout[name]
            im = Image.open(p)
            a = np.asarray(im.getchannel("A"), np.float32) / 255.0
            # fit into the layout box, keeping aspect
            box_w = (u1 - u0) * BW
            box_h = h * BH
            s = min(box_w / a.shape[1], box_h / a.shape[0])
            w, hh = max(1, int(a.shape[1] * s)), max(1, int(a.shape[0] * s))
            a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((w, hh), Image.LANCZOS),
                           np.float32) / 255.0
            x0 = int(u0 * BW)
            y0 = int((1 - v) * BH - hh / 2)
            self.glyph[name] = (a, x0, y0)

    def ghosts(self, pngs, layout):
        """Older work, faint and half rubbed out, gone with the slurp."""
        import numpy as np
        from PIL import Image
        self.ghost = []
        rng = np.random.default_rng(9)
        for name, p in pngs.items():
            if name not in layout:
                continue
            u0, u1, v, h = layout[name]
            im = Image.open(p)
            a = np.asarray(im.getchannel("A"), np.float32) / 255.0
            box_w, box_h = (u1 - u0) * BW, h * BH
            sc = min(box_w / a.shape[1], box_h / a.shape[0])
            w, hh = max(1, int(a.shape[1] * sc)), max(1, int(a.shape[0] * sc))
            a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((w, hh), Image.LANCZOS),
                           np.float32) / 255.0
            # rubbed: faint, patchy, smeared sideways
            smear = np.clip(rng.random(a.shape) * 1.4, 0, 1)
            a = a * 0.32 * smear
            a = np.maximum(a, np.roll(a, 6, axis=1) * 0.6)
            self.ghost.append((a, int(u0 * BW), int((1 - v) * BH - hh / 2)))

    def _state(self, t):
        """(visible formulas with reveal fraction, wet streaks, wiped)."""
        vis = {}
        wet = []
        wiped_at = None
        for e in self.events:
            if e["t0"] > t:
                continue
            if e["kind"] == "write":
                frac = _smooth((t - e["t0"]) / max(0.01, e["t1"] - e["t0"]))
                start = 0.0
                if e["board"] == "identity" and "exp" in vis:
                    # "+ 1 = 0" goes on after the e^{i pi} already there
                    u0e, u1e, _, _ = self.layout["exp"]
                    u0, u1, _, _ = self.layout["identity"]
                    start = (u1e - u0) / (u1 - u0)
                    del vis["exp"]
                vis[e["board"]] = start + (1 - start) * frac
            elif e["kind"] == "lick":
                wet.append(e)
            elif e["kind"] == "slurp":
                wiped_at = e
        return vis, wet, wiped_at

    def frame(self, t):
        np = self.np
        chalk = np.zeros((BH, BW), np.float32)
        wetm = np.zeros((BH, BW), np.float32)
        vis, wet, slurp = self._state(t)
        for name, frac in vis.items():
            a, x0, y0 = self.glyph[name]
            h, w = a.shape
            cut = int(w * frac)
            if cut <= 0:
                continue
            part = a[:, :cut].copy()
            # a soft leading edge where the chalk is still going on
            edge = min(cut, 24)
            part[:, cut - edge:] *= np.linspace(1, 0.3, edge)[None, :]
            ys, xs = slice(max(0, y0), min(BH, y0 + h)), slice(max(0, x0), min(BW, x0 + cut))
            chalk[ys, xs] = np.maximum(chalk[ys, xs], part[: ys.stop - ys.start, : xs.stop - xs.start])
        chalk *= self.grain
        for a, x0, y0 in getattr(self, "ghost", []):
            h, w = a.shape
            ys, xs = slice(max(0, y0), min(BH, y0 + h)), slice(max(0, x0), min(BW, x0 + w))
            chalk[ys, xs] = np.maximum(chalk[ys, xs], a[: ys.stop - ys.start, : xs.stop - xs.start])
        # wet streaks: a band along the formula the tongue swept, drying out
        for e in wet:
            u0, u1, v, h = self.layout[e["board"]]
            u1 = min(u1, e.get("u_end", u1))
            prog = _smooth((t - e["t0"]) / max(0.01, e["t1"] - e["t0"]))
            dry = max(0.0, 1.0 - max(0.0, t - e["t1"]) / 6.0)
            if dry <= 0:
                continue
            x_end = int((u0 + (u1 - u0) * min(1.0, prog * 1.15)) * BW)
            yc = int((1 - v) * BH)
            band = int(h * BH * 0.55)
            xx = np.arange(int(u0 * BW), max(int(u0 * BW) + 1, x_end))
            wob = (np.sin(xx / 37.0) * band * 0.12).astype(int)
            for i, x in enumerate(xx[::2]):
                y = yc + wob[2 * i] if 2 * i < len(wob) else yc
                y0, y1 = max(0, y - band // 2), min(BH, y + band // 2)
                col = np.linspace(-1, 1, y1 - y0)
                wetm[y0:y1, x:x + 2] = np.maximum(wetm[y0:y1, x:x + 2], (1 - col ** 2)[:, None] * dry * 0.9)
        # the slurp: a great wet swathe crossing the board, taking the chalk
        if slurp is not None:
            prog = _smooth((t - slurp["t0"]) / max(0.01, slurp["t1"] - slurp["t0"]))
            dry = max(0.0, 1.0 - max(0.0, t - slurp["t1"]) / 20.0)
            xline = int(prog * 1.2 * BW)
            yy, xx = np.mgrid[0:BH, 0:BW]
            front = xx + (yy - BH / 2) * 0.25 < xline
            chalk[front] = 0.0
            wetm[front] = np.maximum(wetm[front], 0.85 * dry)
        return chalk, wetm

    def save(self, t, path):
        from PIL import Image
        np = self.np
        chalk, wetm = self.frame(t)
        rgba = np.zeros((BH, BW, 4), np.uint8)
        rgba[..., 0] = (wetm * 255).astype(np.uint8)
        rgba[..., 3] = (np.clip(chalk, 0, 1) * 255).astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(path, compress_level=1)


def frames(film, pngs, f0, f1, out_dir, morning=False):
    """Slate PNGs for global frames f0..f1 into out_dir/board_#####.png.
    Frames where nothing changes are written once and hard-linked."""
    from cartoon.sets import marks as MK
    os.makedirs(out_dir, exist_ok=True)
    b = Board(film, {k: v for k, v in pngs.items() if k in MK.BOARD_LAYOUT}, MK.BOARD_LAYOUT)
    b.ghosts(pngs, MK.GHOST_LAYOUT)
    fps = film["fps"]
    last_key, last_path = None, None
    for f in range(f0, f1 + 1):
        t = f / fps
        if morning:
            t = 1e9          # the morning after: whatever the night left
        path = os.path.join(out_dir, f"board_{f:05d}.png")
        vis, wet, slurp = b._state(t)
        key = json.dumps([sorted((k, round(v, 3)) for k, v in vis.items()),
                          [(e["board"], round(min(1, max(0, (t - e["t0"]) / 6)), 2)) for e in wet
                           if t - e["t1"] < 6.5],
                          None if slurp is None else round(min(1.0, (t - slurp["t0"]) / 20), 2)])
        if os.path.exists(path):
            last_key, last_path = key, path
            continue
        if key == last_key and last_path:
            os.link(last_path, path)
        else:
            b.save(t, path)
            last_key, last_path = key, path
    return out_dir
