"""Panels and diagrams for the lecture.

Each visual is a function of a phase in 0..1, so it can animate across the
segment it belongs to. Everything is cached: a segment's panel is drawn once
per quantised phase step and then composited, which is what keeps a
forty-thousand-frame render cheap.

Math is set with matplotlib's mathtext, which renders LaTeX notation without a
TeX installation.
"""

from __future__ import annotations

import functools
import io
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PANEL_W, PANEL_H = 1180, 840

BG = (18, 22, 31)
INK = (238, 243, 250)
DIM = (150, 165, 190)
ACCENT = (120, 190, 255)
WARM = (255, 186, 110)
GREEN = (130, 222, 160)
RED = (255, 122, 122)
GRID = (44, 52, 68)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fonts  # noqa: E402  (OFL fonts fetched on first use, never committed)


@functools.lru_cache(maxsize=32)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(fonts.path("serif"), size)
    if bold:
        f.set_variation_by_axes([700])
    return f


@functools.lru_cache(maxsize=256)
def math_image(latex: str, size: int, colour: tuple) -> Image.Image:
    """Render one line of math to a transparent RGBA image."""
    fig = plt.figure(figsize=(12, 2.0), dpi=150)
    fig.patch.set_alpha(0.0)
    c = tuple(v / 255 for v in colour)
    fig.text(0.02, 0.5, latex, ha="left", va="center", fontsize=size, color=c)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight",
                pad_inches=0.06)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def _fade(img: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 1.0:
        return img
    a = img.getchannel("A").point(lambda v: int(v * max(0.0, alpha)))
    out = img.copy()
    out.putalpha(a)
    return out


def _blank() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (PANEL_W, PANEL_H), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _heading(d: ImageDraw.ImageDraw, text: str, y: int = 40) -> None:
    d.text((10, y), text, font=font(46, True), fill=INK)
    d.line([(12, y + 72), (12 + min(760, len(text) * 22), y + 72)],
           fill=ACCENT, width=3)


# --------------------------------------------------------------- plain panels

def panel_title(spec: dict, phase: float) -> Image.Image:
    img, d = _blank()
    a = min(1.0, phase * 3.0)
    main, sub = spec["main"], spec.get("sub", "")
    f1, f2 = font(92, True), font(44)
    w1 = d.textlength(main, font=f1)
    d.text(((PANEL_W - w1) / 2, 300), main, font=f1,
           fill=tuple(int(c * a) for c in INK))
    if sub:
        a2 = min(1.0, max(0.0, (phase - 0.2) * 3.0))
        w2 = d.textlength(sub, font=f2)
        d.text(((PANEL_W - w2) / 2, 420), sub, font=f2,
               fill=tuple(int(c * a2) for c in DIM))
    y = 500
    d.line([(PANEL_W / 2 - 180 * a, y), (PANEL_W / 2 + 180 * a, y)],
           fill=ACCENT, width=3)
    return img


def panel_bullets(spec: dict, phase: float) -> Image.Image:
    img, d = _blank()
    _heading(d, spec["heading"])
    items = spec["items"]
    for i, it in enumerate(items):
        t0 = 0.12 + i * 0.16
        a = min(1.0, max(0.0, (phase - t0) * 5.0))
        if a <= 0:
            continue
        y = 190 + i * 104
        d.ellipse([16, y + 20, 34, y + 38],
                  fill=tuple(int(c * a) for c in ACCENT))
        d.text((62, y), it, font=font(50),
               fill=tuple(int(c * a) for c in INK))
    return img


def panel_math(spec: dict, phase: float) -> Image.Image:
    img, d = _blank()
    _heading(d, spec.get("heading", ""))
    lines = spec["lines"]
    y = 190
    for i, ln in enumerate(lines):
        t0 = 0.10 + i * 0.17
        a = min(1.0, max(0.0, (phase - t0) * 5.0))
        if a <= 0:
            continue
        colour = INK if i == 0 else ACCENT
        m = math_image(ln, 40 if i == 0 else 34, colour)
        scale = min(1.0, (PANEL_W - 40) / m.width)
        if scale < 1.0:
            m = m.resize((int(m.width * scale), int(m.height * scale)),
                         Image.LANCZOS)
        img.alpha_composite(_fade(m, a), (20, y))
        y += m.height + 34
    return img


# ------------------------------------------------------------------ diagrams

def _axes(d, x0, y0, x1, y1, xlabel="", ylabel=""):
    d.line([(x0, y1), (x1, y1)], fill=DIM, width=3)
    d.line([(x0, y0), (x0, y1)], fill=DIM, width=3)
    if xlabel:
        d.text((x1 - 40, y1 + 14), xlabel, font=font(30), fill=DIM)
    if ylabel:
        d.text((x0 - 46, y0 - 10), ylabel, font=font(30), fill=DIM)


def _mpl_curve(fn, xlabel, ylabel, marker_x=None, title=""):
    fig = plt.figure(figsize=(9.2, 5.6), dpi=118)
    fig.patch.set_alpha(0.0)
    ax = fig.add_subplot(111)
    ax.set_facecolor((0, 0, 0, 0))
    xs, ys = fn()
    ax.plot(xs, ys, color="#78beff", linewidth=3.2)
    if marker_x is not None:
        i = int(np.clip(marker_x, 0, len(xs) - 1))
        ax.plot([xs[i]], [ys[i]], "o", color="#ffba6e", markersize=13)
    for sp in ax.spines.values():
        sp.set_color("#8a97ad")
    ax.tick_params(colors="#8a97ad", labelsize=13)
    ax.set_xlabel(xlabel, color="#c8d2e4", fontsize=17)
    ax.set_ylabel(ylabel, color="#c8d2e4", fontsize=17)
    if title:
        ax.set_title(title, color="#eef3fa", fontsize=19, pad=14)
    ax.grid(color="#2c3444", linewidth=0.9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def dg_gamma_curve(phase):
    img, d = _blank()
    _heading(d, "The Lorentz factor")
    n = 400
    k = int(np.clip(phase * n * 1.4, 4, n - 1))

    def fn():
        xs = np.linspace(0, 0.995, n)[:k]
        return xs, 1.0 / np.sqrt(1 - xs ** 2)
    img.alpha_composite(_mpl_curve(fn, "v / c", "gamma", marker_x=k - 1), (40, 170))
    return img


def dg_energy_curve(phase):
    img, d = _blank()
    _heading(d, "Energy runs away at c")
    n = 400
    k = int(np.clip(phase * n * 1.4, 4, n - 1))

    def fn():
        xs = np.linspace(0, 0.99, n)[:k]
        return xs, 1.0 / np.sqrt(1 - xs ** 2)
    img.alpha_composite(_mpl_curve(fn, "v / c", "E / mc^2", marker_x=k - 1), (40, 170))
    return img


def dg_doppler(phase):
    img, d = _blank()
    _heading(d, "Red shift and blue shift")
    n = 300
    k = int(np.clip(phase * n * 1.5, 4, n - 1))

    def fn():
        xs = np.linspace(-0.9, 0.9, n)[:k]
        return xs, np.sqrt((1 - xs) / (1 + xs))
    img.alpha_composite(
        _mpl_curve(fn, "v / c   (positive = receding)", "observed / source",
                   marker_x=k - 1), (40, 170))
    return img


def dg_light_cone(phase):
    img, d = _blank()
    _heading(d, "The light cone")
    cx, cy = PANEL_W // 2, 520
    r = int(300 * min(1.0, phase * 1.6))
    d.polygon([(cx, cy), (cx - r, cy - r), (cx + r, cy - r)],
              fill=(30, 50, 76), outline=ACCENT, width=3)
    d.polygon([(cx, cy), (cx - r, cy + r), (cx + r, cy + r)],
              fill=(46, 34, 40), outline=RED, width=3)
    d.line([(cx - 420, cy), (cx + 420, cy)], fill=GRID, width=2)
    d.line([(cx, cy - 340), (cx, cy + 320)], fill=GRID, width=2)
    d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=WARM)
    if phase > 0.45:
        d.text((cx + 26, cy - 300), "future", font=font(34), fill=ACCENT)
        d.text((cx + 26, cy + 250), "past", font=font(34), fill=RED)
        d.text((cx + 300, cy - 44), "elsewhere", font=font(30), fill=DIM)
        d.text((cx - 470, cy - 44), "elsewhere", font=font(30), fill=DIM)
    return img


def _road_car(d, x, y, w, h, colour, flip=False):
    d.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=colour)
    d.rounded_rectangle([x + w * 0.2, y - h * 0.5, x + w * 0.72, y + 2],
                        radius=8, fill=colour)
    for wx in (x + w * 0.22, x + w * 0.76):
        d.ellipse([wx - 13, y + h - 8, wx + 13, y + h + 18], fill=(30, 34, 42))


def dg_galileo_ship(phase):
    img, d = _blank()
    _heading(d, "Galileo's ship")
    # sea
    for i in range(6):
        yy = 560 + i * 26
        off = math.sin(phase * math.tau + i) * 14
        d.line([(0, yy + off), (PANEL_W, yy - off)], fill=GRID, width=3)
    hull_x = 180 + 120 * math.sin(phase * math.tau * 0.5)
    d.polygon([(hull_x, 520), (hull_x + 560, 520), (hull_x + 500, 600),
               (hull_x + 60, 600)], fill=COAT_HULL)
    d.rectangle([hull_x + 120, 330, hull_x + 440, 520], fill=(44, 54, 72),
                outline=DIM, width=3)
    d.text((hull_x + 150, 360), "cabin below deck", font=font(32), fill=DIM)
    # a drop falling straight down inside the cabin
    dy = (phase * 2.0 % 1.0)
    d.ellipse([hull_x + 280, 400 + dy * 90, hull_x + 296, 416 + dy * 90],
              fill=ACCENT)
    d.text((10, 640), "Nothing inside reveals the motion", font=font(40),
           fill=INK)
    return img


COAT_HULL = (92, 72, 58)


def dg_michelson(phase):
    img, d = _blank()
    _heading(d, "Michelson and Morley")
    cx, cy = 470, 470
    d.line([(160, cy), (cx, cy)], fill=WARM, width=5)
    d.line([(cx, cy), (820, cy)], fill=ACCENT, width=4)
    d.line([(cx, cy), (cx, 210)], fill=ACCENT, width=4)
    d.rectangle([cx - 14, cy - 14, cx + 14, cy + 14], fill=DIM)
    d.rectangle([810, cy - 46, 826, cy + 46], fill=INK)
    d.rectangle([cx - 46, 200, cx + 46, 216], fill=INK)
    p = (phase * 1.6) % 1.0
    d.ellipse([160 + p * (cx - 160) - 9, cy - 9, 160 + p * (cx - 160) + 9,
               cy + 9], fill=WARM)
    d.text((10, 640), "Expected a shift. Found none.", font=font(42), fill=INK)
    d.text((10, 706), "No ether wind, at any orientation", font=font(34),
           fill=DIM)
    return img


def dg_chase_light(phase):
    img, d = _blank()
    _heading(d, "Chasing a beam")
    y1, y2 = 300, 470
    p = (phase * 1.2) % 1.0
    d.line([(20, y1 + 40), (PANEL_W - 20, y1 + 40)], fill=GRID, width=2)
    d.line([(20, y2 + 40), (PANEL_W - 20, y2 + 40)], fill=GRID, width=2)
    _road_car(d, 60 + p * 300, y1, 130, 52, ACCENT)
    d.text((60, y1 - 78), "you, at 0.9c", font=font(32), fill=DIM)
    bx = 60 + p * 980
    d.ellipse([bx, y1 + 4, bx + 26, y1 + 30], fill=WARM)
    d.text((10, y2 - 78), "the beam, measured by you", font=font(32), fill=DIM)
    d.text((10, 620), "still recedes at c, not 0.1c", font=font(46), fill=INK)
    return img


def _train(d, x, y, w, h, flash=None):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14,
                        fill=(46, 56, 76), outline=DIM, width=3)
    for wx in (x + w * 0.18, x + w * 0.5, x + w * 0.82):
        d.ellipse([wx - 16, y + h - 10, wx + 16, y + h + 22], fill=(28, 32, 40))
    d.ellipse([x + w / 2 - 11, y + h / 2 - 11, x + w / 2 + 11, y + h / 2 + 11],
              fill=WARM)


def dg_train_flash_inside(phase):
    img, d = _blank()
    _heading(d, "In the carriage")
    x, y, w, h = 150, 360, 880, 180
    _train(d, x, y, w, h)
    p = min(1.0, (phase * 1.7) % 1.0)
    cx = x + w / 2
    reach = p * (w / 2 - 20)
    d.line([(cx, y + h / 2), (cx - reach, y + h / 2)], fill=ACCENT, width=6)
    d.line([(cx, y + h / 2), (cx + reach, y + h / 2)], fill=ACCENT, width=6)
    if p > 0.97:
        for sx in (x + 14, x + w - 14):
            d.ellipse([sx - 16, y + h / 2 - 16, sx + 16, y + h / 2 + 16],
                      fill=GREEN)
    d.text((10, 640), "Both walls are reached together", font=font(44),
           fill=INK)
    return img


def dg_train_flash_outside(phase):
    img, d = _blank()
    _heading(d, "From the embankment")
    p = (phase * 1.7) % 1.0
    x = 120 + p * 210
    y, w, h = 360, 800, 180
    _train(d, x, y, w, h)
    cx0 = 120 + w / 2
    reach = p * 430
    d.line([(cx0, y + h / 2), (cx0 - reach, y + h / 2)], fill=ACCENT, width=6)
    d.line([(cx0, y + h / 2), (cx0 + reach, y + h / 2)], fill=ACCENT, width=6)
    if p > 0.42:
        d.ellipse([x - 16, y + h / 2 - 16, x + 16, y + h / 2 + 16], fill=GREEN)
        d.text((x - 60, y + h + 40), "hit first", font=font(30), fill=GREEN)
    if p > 0.86:
        sx = x + w
        d.ellipse([sx - 16, y + h / 2 - 16, sx + 16, y + h / 2 + 16], fill=RED)
        d.text((sx - 50, y + h + 40), "hit later", font=font(30), fill=RED)
    d.text((10, 660), "The back wall is reached first", font=font(44), fill=INK)
    return img


def _clock_box(d, x, y, w, h):
    d.rectangle([x, y, x + w, y + h], outline=DIM, width=3)
    d.rectangle([x, y - 10, x + w, y], fill=INK)
    d.rectangle([x, y + h, x + w, y + h + 10], fill=INK)


def dg_light_clock_rest(phase):
    img, d = _blank()
    _heading(d, "A light clock at rest")
    x, y, w, h = 480, 240, 200, 340
    _clock_box(d, x, y, w, h)
    p = (phase * 2.0) % 1.0
    yy = y + (h * (1 - abs(2 * p - 1)))
    d.line([(x + w / 2, y), (x + w / 2, y + h)], fill=(50, 66, 92), width=3)
    d.ellipse([x + w / 2 - 12, yy - 12, x + w / 2 + 12, yy + 12], fill=WARM)
    d.text((x + w + 40, y + 140), "L", font=font(48), fill=ACCENT)
    d.text((10, 640), "One tick = 2L / c", font=font(46), fill=INK)
    return img


def dg_light_clock_moving(phase):
    img, d = _blank()
    _heading(d, "The same clock, moving")
    p = (phase * 1.4) % 1.0
    x = 180 + p * 620
    y, w, h = 240, 190, 330
    _clock_box(d, x, y, w, h)
    up = p * 2 if p < 0.5 else (1 - p) * 2
    yy = y + h * (1 - up)
    x0 = 180 + (p - up * 0.5) * 620
    d.line([(x0 + w / 2, y + h), (x + w / 2, yy)], fill=ACCENT, width=5)
    d.ellipse([x + w / 2 - 12, yy - 12, x + w / 2 + 12, yy + 12], fill=WARM)
    d.line([(180, y + h + 60), (800 + w, y + h + 60)], fill=GRID, width=2)
    d.text((10, 660), "Longer path, same c, so a longer tick",
           font=font(42), fill=INK)
    return img


def dg_rod_contraction(phase):
    img, d = _blank()
    _heading(d, "A moving rod measures shorter")
    v = 0.2 + 0.75 * (0.5 - 0.5 * math.cos(phase * math.tau))
    g = 1.0 / math.sqrt(1 - v * v)
    full = 760
    d.rectangle([160, 300, 160 + full, 356], fill=(60, 72, 96), outline=DIM,
                width=3)
    d.text((160, 246), "rest length  L0", font=font(34), fill=DIM)
    L = full / g
    d.rectangle([160, 470, 160 + L, 526], fill=(46, 92, 132), outline=ACCENT,
                width=3)
    d.text((160, 416), f"measured at v = {v:0.2f}c", font=font(34), fill=ACCENT)
    d.text((10, 640), f"L = L0 / gamma     gamma = {g:0.2f}", font=font(44),
           fill=INK)
    return img


def dg_twin_paths(phase):
    img, d = _blank()
    _heading(d, "Two paths through spacetime")
    x0, ybot, ytop = 300, 640, 210
    d.line([(x0, ybot), (x0, ytop)], fill=ACCENT, width=6)
    d.text((x0 - 150, 400), "stays", font=font(34), fill=ACCENT)
    apex = (760, 420)
    d.line([(x0, ybot), apex], fill=WARM, width=6)
    d.line([apex, (x0, ytop)], fill=WARM, width=6)
    d.text((apex[0] + 20, apex[1] - 20), "turns around", font=font(32),
           fill=WARM)
    p = (phase * 1.3) % 1.0
    if p < 0.5:
        t = p * 2
        px, py = x0 + (apex[0] - x0) * t, ybot + (apex[1] - ybot) * t
    else:
        t = (p - 0.5) * 2
        px, py = apex[0] + (x0 - apex[0]) * t, apex[1] + (ytop - apex[1]) * t
    d.ellipse([px - 11, py - 11, px + 11, py + 11], fill=GREEN)
    d.text((10, 690), "10 years pass here, 6 on the journey", font=font(40),
           fill=INK)
    return img


def dg_ladder_barn(phase):
    img, d = _blank()
    _heading(d, "The ladder and the barn")
    d.rectangle([420, 300, 760, 470], outline=DIM, width=4)
    d.text((420, 250), "barn", font=font(32), fill=DIM)
    p = (phase * 1.1) % 1.0
    lx = 60 + p * 780
    d.rectangle([lx, 360, lx + 300, 392], fill=WARM)
    for s in (420, 760):
        shut = 0.36 < p < 0.62
        d.line([(s, 300), (s, 470)], fill=GREEN if shut else GRID,
               width=8 if shut else 3)
    d.text((10, 560), "Barn frame: the ladder fits, both doors shut",
           font=font(38), fill=INK)
    d.text((10, 626), "Ladder frame: the doors shut at different times",
           font=font(38), fill=DIM)
    return img


def dg_muon(phase):
    img, d = _blank()
    _heading(d, "Muons reach the ground")
    d.line([(120, 250), (PANEL_W - 120, 250)], fill=GRID, width=3)
    d.text((PANEL_W - 430, 200), "15 km up", font=font(32), fill=DIM)
    d.line([(120, 640), (PANEL_W - 120, 640)], fill=GREEN, width=5)
    d.text((120, 660), "sea level", font=font(32), fill=GREEN)
    for i in range(5):
        p = ((phase * 1.4) + i * 0.2) % 1.0
        y = 250 + p * 390
        x = 220 + i * 170
        d.ellipse([x - 10, y - 10, x + 10, y + 10], fill=WARM)
        d.line([(x, y - 34), (x, y - 10)], fill=(120, 90, 50), width=3)
    d.text((10, 706), "Should decay in 660 m. They arrive.", font=font(42),
           fill=INK)
    return img


DIAGRAMS = {
    "galileo_ship": dg_galileo_ship,
    "michelson": dg_michelson,
    "chase_light": dg_chase_light,
    "train_flash_inside": dg_train_flash_inside,
    "train_flash_outside": dg_train_flash_outside,
    "light_clock_rest": dg_light_clock_rest,
    "light_clock_moving": dg_light_clock_moving,
    "gamma_curve": dg_gamma_curve,
    "rod_contraction": dg_rod_contraction,
    "light_cone": dg_light_cone,
    "energy_curve": dg_energy_curve,
    "muon": dg_muon,
    "twin_paths": dg_twin_paths,
    "doppler": dg_doppler,
    "ladder_barn": dg_ladder_barn,
}


def render_panel(spec: dict, phase: float) -> Image.Image:
    kind = spec["kind"]
    if kind == "title":
        return panel_title(spec, phase)
    if kind == "bullets":
        return panel_bullets(spec, phase)
    if kind == "math":
        return panel_math(spec, phase)
    if kind == "diagram":
        fn = DIAGRAMS.get(spec["name"])
        if fn is None:
            return panel_title(dict(main=spec["name"], sub=""), phase)
        return fn(phase)
    raise ValueError(f"unknown visual kind {kind!r}")


if __name__ == "__main__":
    names = list(DIAGRAMS)
    cols, rows = 4, 4
    sheet = Image.new("RGB", (PANEL_W // 2 * cols, PANEL_H // 2 * rows), BG)
    for i, n in enumerate(names):
        p = render_panel(dict(kind="diagram", name=n), 0.62)
        p = p.resize((PANEL_W // 2, PANEL_H // 2), Image.LANCZOS)
        sheet.paste(p, ((i % cols) * PANEL_W // 2, (i // cols) * PANEL_H // 2), p)
    sheet.save("/tmp/diagram_sheet.png")
    print("/tmp/diagram_sheet.png", len(names), "diagrams")
