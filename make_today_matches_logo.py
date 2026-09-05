#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the modern marks for the four dashboard guides.

A channel's mark is how a viewer finds it in a list of two hundred, so
each one says its name in both languages and carries an emblem a viewer
can recognise at thumbnail size — a ball, a trophy, a broadcast wave, a
sun behind a cloud — on a deep gradient with a glow of its own colour.
Same layout, same family, four accents: a set that reads as a set.

    python make_today_matches_logo.py

Writes logos/today_matches.png, logos/other_sports.png,
logos/today_news.png and logos/today_weather.png — one 512×512
transparent PNG each, rounded like a modern app tile, ready for
TiviMate's icon slot.
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

# Each mark: the file, its Arabic name, its Latin caption, the top and
# bottom of the background gradient, and its accent colour.
MARKS = (
    ("logos/today_matches.png", "مباريات اليوم", "TODAY'S MATCHES",
     (14, 46, 38, 255), (5, 11, 9, 255), (58, 224, 138, 255)),
    ("logos/other_sports.png", "رياضات اليوم", "TODAY'S SPORTS",
     (34, 24, 8, 255), (10, 7, 3, 255), (255, 176, 46, 255)),
    ("logos/today_news.png", "أخبار اليوم", "TODAY'S NEWS",
     (14, 30, 56, 255), (4, 8, 16, 255), (86, 168, 255, 255)),
    ("logos/today_weather.png", "طقس اليوم", "TODAY'S WEATHER",
     (10, 46, 66, 255), (4, 10, 15, 255), (74, 224, 220, 255)),
)

AR_FONT = "fonts/Tajawal-ExtraBold.ttf"
EN_FONT = "fonts/Tajawal-Medium.ttf"

SCALE = 2                 # draw large, shrink at the end, so edges are smooth
SIZE = 512 * SCALE
RADIUS = 118 * SCALE      # the corner of a modern app tile
WHITE = (255, 255, 255, 255)

ARABIC = dict(direction="rtl", language="ar")


def refuse_without_shaping(name_ar: str) -> None:
    """Stop before drawing if the Arabic would not be shaped."""
    if not features.check("raqm"):
        sys.exit("Pillow has no Raqm, so Arabic would not be shaped. "
                 "Install libraqm and try again — do not commit the "
                 "output of a run without it.")
    font = ImageFont.truetype(AR_FONT, 40)
    if not all(font.getmask(letter).getbbox() for letter in name_ar if letter.strip()):
        sys.exit(f"{AR_FONT} does not carry every letter of {name_ar}.")


def fitted(path: str, text: str, width: int, ceiling: int, **kw) -> ImageFont.FreeTypeFont:
    """The largest size of `path` at which `text` still fits inside `width`."""
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = ceiling
    while size > 8:
        font = ImageFont.truetype(path, size)
        box = measure.textbbox((0, 0), text, font=font, **kw)
        if box[2] - box[0] <= width: 
            return font
        size -= 2
    return ImageFont.truetype(path, size)


# ── the emblems ─────────────────────────────────────────────────────────
# Line icons in white on a glow of the mark's accent: a ball, a cup, a
# broadcast wave, a sun behind a cloud. Drawn at the same stroke weight
# so they read as one family, and each is simple enough to survive a
# 64px thumbnail.

def draw_ball(pen: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
              stroke: int, accent) -> None:
    """A football: circle, centre pentagon, five seams to the rim."""
    pen.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE,
                width=stroke)
    import math
    pts = [(cx + int(r * 0.46 * math.cos(math.radians(90 + i * 72))),
            cy - int(r * 0.46 * math.sin(math.radians(90 + i * 72))))
           for i in range(5)]
    pen.polygon(pts, fill=accent)
    for i, (px, py) in enumerate(pts):
        a = math.radians(90 + i * 72)
        pen.line([px, py, cx + int(r * math.cos(a) * 0.92),
                  cy - int(r * math.sin(a) * 0.92)],
                 fill=WHITE, width=max(3, stroke // 2))


def draw_cup(pen: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
             stroke: int, accent) -> None:
    """A trophy: bowl, two handles, a stem, a base."""
    bowl = [cx - r // 2, cy - r, cx + r // 2, cy - r // 5]
    pen.rounded_rectangle(bowl, radius=r // 6, outline=WHITE, width=stroke)
    pen.arc([cx - r, cy - r, cx, cy + r // 5], 300, 90, fill=WHITE,
            width=max(3, stroke // 2))
    pen.arc([cx, cy - r, cx + r, cy + r // 5], 90, 240, fill=WHITE,
            width=max(3, stroke // 2))
    pen.line([cx, cy - r // 5, cx, cy + r // 3], fill=WHITE, width=stroke)
    pen.line([cx - r // 3, cy + r // 3, cx + r // 3, cy + r // 3],
             fill=WHITE, width=stroke)
    pen.rounded_rectangle([cx - r // 2, cy + r // 3, cx + r // 2,
                           cy + r // 3 + r // 6], radius=stroke,
                          outline=WHITE, width=stroke)
    pen.line([cx - r // 3, cy - r, cx + r // 3, cy - r], fill=accent,
             width=max(3, stroke // 2))


def draw_waves(pen: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
               stroke: int, accent) -> None:
    """A broadcast mark: a dot, and arcs either side of it."""
    dot = r // 7
    pen.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=accent)
    for i, spread in ((1, r // 3), (2, r * 2 // 3), (3, r)):
        box = [cx - spread, cy - spread, cx + spread, cy + spread]
        pen.arc(box, 315, 45, fill=WHITE, width=max(3, stroke // 2))
        pen.arc(box, 135, 225, fill=WHITE, width=max(3, stroke // 2))


def draw_sun_cloud(pen: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
                   stroke: int, accent) -> None:
    """A sun sitting behind a small cloud."""
    import math
    sun = r * 0.42
    sx, sy = cx + r // 3, cy - r // 3
    for i in range(8):
        a = math.radians(45 * i)
        pen.line([sx + int(sun * math.cos(a)), sy - int(sun * math.sin(a)),
                  sx + int((sun + r // 5) * math.cos(a)),
                  sy - int((sun + r // 5) * math.sin(a))],
                 fill=accent, width=max(3, stroke // 2))
    pen.ellipse([sx - sun, sy - sun, sx + sun, sy + sun], outline=WHITE,
                width=max(3, stroke // 2))
    pen.ellipse([cx - r, cy + r // 10, cx - r // 3, cy + r * 2 // 3],
                outline=WHITE, width=stroke)
    pen.ellipse([cx - r // 3, cy, cx + r // 4, cy + r * 3 // 5],
                outline=WHITE, width=stroke)
    pen.line([cx - r, cy + r * 2 // 3, cx + r // 4, cy + r * 2 // 3],
             fill=WHITE, width=stroke)


EMBLEMS = {
    "logos/today_matches.png": draw_ball,
    "logos/other_sports.png": draw_cup,
    "logos/today_news.png": draw_waves,
    "logos/today_weather.png": draw_sun_cloud,
}


# ── the mark ────────────────────────────────────────────────────────────

def draw(path: str, name_ar: str, name_en: str, top, bottom,
         accent) -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    # The background: a vertical gradient inside a rounded tile.
    for y in range(SIZE):
        share = y / (SIZE - 1)
        ink = tuple(int(top[i] + (bottom[i] - top[i]) * share)
                    for i in range(3)) + (255,)
        pen.line([(0, y), (SIZE - 1, y)], fill=ink)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1], radius=RADIUS, fill=255)
    image.putalpha(mask)

    # The glow: the emblem's colour, blurred, so the icon floats on it.
    cx, cy, r = SIZE // 2, 208 * SCALE, 96 * SCALE
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [cx - r * 2, cy - r * 2, cx + r * 2, cy + r * 2],
        fill=accent[:3] + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(52 * SCALE))
    image.alpha_composite(glow)

    pen = ImageDraw.Draw(image)
    EMBLEMS[path](pen, cx, cy, r, 8 * SCALE, accent)

    # The two names, inside the tile's width.
    inner = SIZE - 2 * 46 * SCALE
    middle = SIZE // 2
    arabic = fitted(AR_FONT, name_ar, inner, 96 * SCALE, **ARABIC)
    latin = fitted(EN_FONT, " ".join(name_en), int(inner * 0.92),
                   30 * SCALE)
    pen.text((middle, 436 * SCALE), name_ar, font=arabic, fill=WHITE,
             anchor="mm", **ARABIC)
    pen.text((middle, 500 * SCALE), " ".join(name_en), font=latin,
             fill=accent, anchor="mm")

    return image.resize((512, 512), Image.LANCZOS)


def main() -> None:
    for out, name_ar, name_en, top, bottom, accent in MARKS:
        refuse_without_shaping(name_ar)
        draw(out, name_ar, name_en, top, bottom, accent).save(out)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
