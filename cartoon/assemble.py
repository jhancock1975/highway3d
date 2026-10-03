"""Frames + soundtrack + title cards -> the finished mp4.

cartoon/.venv (Pillow for the cards). ffmpeg does the rest: the shots'
frames are already numbered in film order, so the picture is one image
sequence; cards are PNGs overlaid with fades where the document put them.
"""

from __future__ import annotations

import os
import subprocess

import fonts

# roles in fonts.py: OFL fonts fetched on first use, never committed
FONT_TITLE = "script"
FONT_CARD = "caslon"


def card(text, path, size=(1920, 1080), font=FONT_CARD, pt=84, y=0.78, sub=None, sub_pt=44):
    """White lettering with a soft shadow on transparent, like a storybook."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    f = ImageFont.truetype(fonts.path(font), pt)
    d = ImageDraw.Draw(img)
    ds = ImageDraw.Draw(shadow)
    tw = d.textlength(text, font=f)
    x, yy = (W - tw) / 2, H * y - pt / 2
    ds.text((x + 3, yy + 4), text, font=f, fill=(0, 0, 0, 200))
    d.text((x, yy), text, font=f, fill=(255, 248, 235, 255))
    if sub:
        fs = ImageFont.truetype(fonts.path(FONT_CARD), sub_pt)
        sw = d.textlength(sub, font=fs)
        ds.text(((W - sw) / 2 + 2, yy + pt * 1.35 + 3), sub, font=fs, fill=(0, 0, 0, 200))
        d.text(((W - sw) / 2, yy + pt * 1.35), sub, font=fs, fill=(255, 240, 220, 255))
    shadow = shadow.filter(ImageFilter.GaussianBlur(6))
    Image.alpha_composite(shadow, img).save(path)
    return path


def cards_for(film, work, size):
    """(png, start, end) for every card the document asked for, plus the
    film's title over its first seconds."""
    out = []
    os.makedirs(work, exist_ok=True)
    first = film["beats"][0]
    t_png = card(film["title"], os.path.join(work, "card_title.png"), size, FONT_TITLE, 120, 0.42)
    out.append((t_png, 0.4, min(first["end"], 4.4)))
    for b in film["beats"]:
        if b.get("card"):
            if b["do"] == "title":
                p = card(b["card"], os.path.join(work, "card_place.png"), size, FONT_CARD, 58, 0.84)
                out.append((p, first["end"] + 0.2, first["end"] + 4.0))
            else:
                p = card(b["card"], os.path.join(work, f"card_{b['index']}.png"), size, FONT_TITLE, 110, 0.8)
                out.append((p, b["end"] - 3.6, b["end"] + 1.5))
    return out


def assemble(film, frames_dir, audio, out, size=(1920, 1080), tail=2.0, crf=16):
    fps = film["fps"]
    work = os.path.join(os.path.dirname(os.path.abspath(out)), ".cards")
    cards = cards_for(film, work, size)
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-start_number", "0",
           "-i", os.path.join(frames_dir, "f_%05d.png")]
    for png, t0, t1 in cards:
        cmd += ["-loop", "1", "-t", f"{t1 + 0.1:.2f}", "-i", png]
    cmd += ["-i", audio]
    # hold the last frame for the tail, then fade to black
    dur = film["duration"] + tail
    chain = [f"[0:v]tpad=stop_mode=clone:stop_duration={tail},scale={size[0]}:{size[1]}[base]"]
    last = "base"
    for i, (png, t0, t1) in enumerate(cards, start=1):
        chain.append(f"[{i}:v]format=rgba,fade=t=in:st={t0:.2f}:d=0.8:alpha=1,"
                     f"fade=t=out:st={t1 - 0.8:.2f}:d=0.8:alpha=1[c{i}]")
        chain.append(f"[{last}][c{i}]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[v{i}]")
        last = f"v{i}"
    chain.append(f"[{last}]fade=t=in:st=0:d=1.2,fade=t=out:st={dur - 1.5:.2f}:d=1.5[vout]")
    a_idx = len(cards) + 1
    # -16 LUFS with a -1.5 dB true-peak ceiling: the mix came out at -17.8,
    # a touch quiet beside anything else a viewer plays
    chain.append(f"[{a_idx}:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
    cmd += ["-filter_complex", ";".join(chain), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "256k", "-t", f"{dur:.2f}", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("assembly failed: " + r.stderr[-800:])
    return out
