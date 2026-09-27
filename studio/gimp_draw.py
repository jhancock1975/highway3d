"""Runs inside GIMP. Draws every card and caption a job list asks for.

    gimp-console-3.2 -i --batch-interpreter=python-fu-eval \
        -b "STUDIO_JOBS = '/path/jobs.json'; exec(open('studio/gimp_draw.py').read())" --quit

Each job is {"kind": "card" | "caption", "out", "width", "height", ...}.
Cards take a style, a title and a subtitle. Captions take one chunk of
speech and are drawn on a transparent ground, so they can be laid over the
picture. Text arrives in the JSON file, never through a shell, so quotes,
dashes and accents draw as written.
"""

import json

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, Gio  # noqa: E402

STYLES = {
    "dark": dict(ground="#15181d", title="#f4f1ea", sub="#aeb6c2",
                 fonts=("Sans-serif Bold", "Sans-serif"), grime=0.0),
    "light": dict(ground="#f3efe6", title="#1b1d22", sub="#5a6170",
                  fonts=("Sans-serif Bold", "Sans-serif"), grime=0.0),
    "chalkboard": dict(ground="#243129", title="#f1efe4", sub="#cfd8cf",
                       fonts=("Chalkduster", "Chalkboard SE"), grime=18.0),
    "sign": dict(ground="#00694a", title="#ffffff", sub="#ffffff",
                 fonts=("Sans-serif Bold", "Sans-serif Bold"), grime=14.0,
                 border="#ffffff"),
}


def font(name):
    """GIMP names most fonts with their style: "Chalkduster Regular"."""
    for candidate in (name, name + " Regular"):
        found = Gimp.Font.get_by_name(candidate)
        if found:
            return found
    return Gimp.Font.get_by_name("Sans-serif")


def new_layer(img, name, opacity=100.0, mode=Gimp.LayerMode.NORMAL):
    lay = Gimp.Layer.new(img, name, img.get_width(), img.get_height(),
                         Gimp.ImageType.RGBA_IMAGE, opacity, mode)
    img.insert_layer(lay, None, 0)
    return lay


def select(img, inset=0, radius=0):
    w, h = img.get_width() - 2 * inset, img.get_height() - 2 * inset
    if radius:
        img.select_round_rectangle(Gimp.ChannelOps.REPLACE, inset, inset, w,
                                   h, radius, radius)
    else:
        img.select_rectangle(Gimp.ChannelOps.REPLACE, inset, inset, w, h)


def fill(img, lay, colour, inset=0, radius=0):
    select(img, inset, radius)
    Gimp.context_set_foreground(Gegl.Color.new(colour))
    lay.edit_fill(Gimp.FillType.FOREGROUND)
    Gimp.Selection.none(img)


def text(img, words, size, face, colour, widest):
    """A text layer no wider than `widest`, the type shrunk until it fits."""
    Gimp.context_set_foreground(Gegl.Color.new(colour))
    while True:
        t = Gimp.text_font(img, None, 0, 0, words, 0, True, size, face)
        if t.get_width() <= widest or size <= 12:
            return t
        img.remove_layer(t)
        size = int(size * 0.9)


def save(img, out):
    img.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(out),
                   None)
    img.delete()


def card(job):
    W, H, s = job["width"], job["height"], STYLES[job["style"]]
    img = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
    ground = new_layer(img, "ground")
    r = int(min(W, H) * 0.05)
    if s.get("border"):
        fill(img, ground, s["border"], 0, r)
        fill(img, ground, s["ground"], int(min(W, H) * 0.02), int(r * 0.75))
    else:
        fill(img, ground, s["ground"])
    if s["grime"]:
        grime = new_layer(img, "grime", s["grime"], Gimp.LayerMode.OVERLAY)
        grime.append_filter(Gimp.DrawableFilter.new(grime, "gegl:perlin-noise",
                                                    "grime"))
        grime.merge_filters()
        if s.get("border"):
            # keep the weathering off the rounded corners
            select(img, 0, r)
            Gimp.Selection.invert(img)
            grime.edit_clear()
            Gimp.Selection.none(img)
    widest = int(W * 0.86)
    # Type sized for a full frame of this width, but never over half the
    # height: a 1600x200 lower third sized from its height alone lettered
    # "tmux, intact" 26 pixels tall.
    size = int(min(0.13 * max(H, W * 9 / 16), 0.5 * H))
    title = text(img, job["title"], size, font(s["fonts"][0]), s["title"],
                 widest)
    sub = None
    if job.get("subtitle"):
        sub = text(img, job["subtitle"], int(size * 0.42), font(s["fonts"][1]),
                   s["sub"], widest)
    gap = int(size * 0.2)
    block = title.get_height() + (gap + sub.get_height() if sub else 0)
    y = (H - block) // 2
    title.set_offsets((W - title.get_width()) // 2, y)
    if sub:
        sub.set_offsets((W - sub.get_width()) // 2, y + title.get_height() + gap)
    save(img, job["out"])


def caption(job):
    W, H = job["width"], job["height"]
    img = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
    band = new_layer(img, "band", 62.0)
    t = text(img, job["text"], int(H * 0.36), font("Sans-serif Bold"),
             "#ffffff", int(W * 0.9))
    pad_x, pad_y = int(H * 0.25), int(H * 0.12)
    bw, bh = t.get_width() + 2 * pad_x, t.get_height() + 2 * pad_y
    img.select_round_rectangle(Gimp.ChannelOps.REPLACE, (W - bw) // 2,
                               (H - bh) // 2, bw, bh, pad_y, pad_y)
    Gimp.context_set_foreground(Gegl.Color.new("#000000"))
    band.edit_fill(Gimp.FillType.FOREGROUND)
    Gimp.Selection.none(img)
    t.set_offsets((W - t.get_width()) // 2, (H - t.get_height()) // 2)
    save(img, job["out"])


with open(STUDIO_JOBS) as _fh:  # noqa: F821 -- set by the -b expression
    for _job in json.load(_fh):
        try:
            (card if _job["kind"] == "card" else caption)(_job)
        except Exception as _e:  # one bad job must not lose the rest
            print(f"could not draw {_job.get('out')}: {_e}")
