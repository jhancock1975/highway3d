"""A stylised lecturer, drawn with primitives.

Deliberately a caricature -- flat shapes, exaggerated hair and moustache, no
attempt at photographic likeness. A cartoon figure explaining real physics is a
normal teaching device; a photoreal synthetic person saying words they never
said is a different thing, and not what this draws.

Mouth shapes are pre-rendered once per openness level and composited per
frame, so a long video does not redraw the face forty thousand times.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

SKIN = (232, 196, 168)
SKIN_SHADE = (206, 168, 141)
HAIR = (238, 238, 240)
HAIR_SHADE = (205, 208, 215)
BROW = (226, 226, 230)
COAT = (74, 82, 100)
COAT_DARK = (58, 65, 80)
SHIRT = (226, 230, 238)
MOUTH_DARK = (92, 48, 48)
TONGUE = (176, 96, 96)

W, H = 620, 760          # character canvas


def _ellipse(d, cx, cy, rx, ry, fill, outline=None, width=0):
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill,
              outline=outline, width=width)


def _hair_tuft(d, cx, cy, rx, ry, angle, fill):
    """One lock of hair: a rotated ellipse approximated by a polygon."""
    pts = []
    for i in range(24):
        a = math.tau * i / 24
        x = rx * math.cos(a)
        y = ry * math.sin(a)
        ca, sa = math.cos(angle), math.sin(angle)
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    d.polygon(pts, fill=fill)


def _draw_body(d):
    # shoulders and jacket
    d.polygon([(90, H), (150, 560), (300, 520), (470, 560), (530, H)],
              fill=COAT)
    d.polygon([(255, 540), (310, 520), (365, 540), (355, H), (265, H)],
              fill=SHIRT)
    d.polygon([(150, 560), (255, 540), (265, H), (140, H)], fill=COAT_DARK)
    d.polygon([(470, 560), (365, 540), (355, H), (480, H)], fill=COAT_DARK)
    # collar
    d.polygon([(255, 540), (310, 585), (365, 540), (310, 556)], fill=COAT_DARK)


def _draw_hair_back(d):
    for cx, cy, rx, ry, ang in [
        (150, 300, 96, 56, -0.55), (470, 300, 96, 56, 0.55),
        (128, 372, 84, 46, -0.15), (492, 372, 84, 46, 0.15),
        (170, 232, 84, 46, -0.95), (450, 232, 84, 46, 0.95),
        (232, 176, 82, 44, -1.25), (388, 176, 82, 44, 1.25),
        (310, 158, 96, 46, 0.0),
    ]:
        _hair_tuft(d, cx, cy, rx, ry, ang, HAIR_SHADE)


def _draw_hair_front(d):
    for cx, cy, rx, ry, ang in [
        (166, 286, 78, 44, -0.5), (454, 286, 78, 44, 0.5),
        (150, 344, 68, 38, -0.1), (470, 344, 68, 38, 0.1),
        (196, 222, 70, 38, -0.9), (424, 222, 70, 38, 0.9),
        (256, 178, 68, 36, -1.2), (364, 178, 68, 36, 1.2),
        (310, 168, 80, 38, 0.0),
    ]:
        _hair_tuft(d, cx, cy, rx, ry, ang, HAIR)


def _draw_face(d):
    _ellipse(d, 310, 330, 132, 156, SKIN)               # head
    _ellipse(d, 310, 258, 126, 92, SKIN)                # forehead
    # cheeks
    _ellipse(d, 246, 384, 34, 24, SKIN_SHADE)
    _ellipse(d, 374, 384, 34, 24, SKIN_SHADE)
    # eyes
    for ex in (262, 358):
        _ellipse(d, ex, 316, 27, 19, (250, 250, 250))
        _ellipse(d, ex + 2, 318, 12, 12, (62, 52, 46))
        _ellipse(d, ex + 5, 314, 4, 4, (255, 255, 255))
    # heavy brows
    d.polygon([(228, 286), (300, 276), (300, 290), (230, 300)], fill=BROW)
    d.polygon([(392, 286), (320, 276), (320, 290), (390, 300)], fill=BROW)
    # nose
    d.polygon([(310, 326), (296, 384), (324, 384)], fill=SKIN_SHADE)
    _ellipse(d, 310, 386, 18, 12, SKIN)
    # eye bags, for age
    d.arc([236, 322, 288, 352], 20, 160, fill=SKIN_SHADE, width=3)
    d.arc([332, 322, 384, 352], 20, 160, fill=SKIN_SHADE, width=3)


def _draw_moustache(d, drop=0):
    y = 412 + drop
    _hair_tuft(d, 272, y, 46, 21, 0.20, HAIR)
    _hair_tuft(d, 348, y, 46, 21, -0.20, HAIR)
    _hair_tuft(d, 310, y - 4, 30, 17, 0.0, HAIR)


def _draw_mouth(d, openness: float):
    """openness 0..1 -- closed lips through to a wide open vowel."""
    cy = 452
    w = 34 + 14 * openness
    h = 3 + 34 * openness
    if openness < 0.06:
        d.line([(310 - w, cy), (310 + w, cy)], fill=MOUTH_DARK, width=6)
        return
    d.ellipse([310 - w, cy - h * 0.45, 310 + w, cy + h], fill=MOUTH_DARK)
    if openness > 0.35:
        d.ellipse([310 - w * 0.55, cy + h * 0.18, 310 + w * 0.55, cy + h * 0.92],
                  fill=TONGUE)
    # lower lip catches light
    d.arc([310 - w, cy + h * 0.2, 310 + w, cy + h * 1.5], 0, 180,
          fill=SKIN_SHADE, width=5)


def render_head(openness: float, scale: float = 1.0) -> Image.Image:
    """One RGBA frame of the character at a given mouth openness."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _draw_body(d)
    _draw_hair_back(d)
    _draw_face(d)
    _draw_hair_front(d)
    # jaw drops slightly with the mouth
    _draw_moustache(d, drop=int(6 * openness))
    _draw_mouth(d, openness)
    if scale != 1.0:
        img = img.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
    return img


def mouth_frames(levels: int = 10, scale: float = 1.0) -> list[Image.Image]:
    """Pre-render the whole mouth range once."""
    return [render_head(i / (levels - 1), scale) for i in range(levels)]


if __name__ == "__main__":
    sheet = Image.new("RGBA", (W * 5, H), (18, 22, 31, 255))
    for i, o in enumerate([0.0, 0.25, 0.5, 0.75, 1.0]):
        sheet.paste(render_head(o), (W * i, 0), render_head(o))
    sheet.convert("RGB").resize((W * 5 // 2, H // 2), Image.LANCZOS).save(
        "/tmp/character_sheet.png")
    print("/tmp/character_sheet.png")
