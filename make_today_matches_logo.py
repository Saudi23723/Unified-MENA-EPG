#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the marks for the two dashboard guides.

The guide is not a broadcaster, so there is no artwork to fetch: it is a
strip of the day's football with a countdown on each fixture. The mark says
that and nothing else — the channel's own name inside a ring drawn as a
countdown part-way run down.

Unlike make_filler_logos.py, this one does set Arabic type. It can, because
it refuses to run unless Pillow was built with Raqm and the font actually
carries the letters; without shaping the words would come out as
disconnected back-to-front glyphs, which is exactly why the filler marks
stay in Latin. Better to fail loudly here than to publish a broken mark.

    python make_today_matches_logo.py

It writes logos/today_matches.png and logos/other_sports.png.

TWO MARKS, because there are two channels. They shared one file until a
reader looked at their guide and saw the same picture twice — a logo is
how a channel is found in a list, so two channels wearing one is two
channels a viewer cannot tell apart. Same shape, so they read as a pair;
different name and different colour, so they are not each other.
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw, ImageFont, features

# Each mark: the file, its Arabic name, its Latin one, and its four
# colours — the ground, the part of the ring still to come, the part
# already run down, and the Latin line. The shape and the layout are
# shared, so the two read as a pair; nothing else is, so they are not
# each other at a glance in a channel list.
MARKS = (
    ("logos/today_matches.png", "مباريات اليوم",
     "T O D A Y ' S   M A T C H E S",
     (11, 43, 36, 255), (30, 76, 65, 255),
     (56, 214, 111, 255), (143, 231, 180, 255)),
    ("logos/other_sports.png", "رياضات اليوم",
     "T O D A Y ' S   S P O R T S",
     (28, 22, 46, 255), (58, 48, 86, 255),
     (245, 158, 11, 255), (253, 214, 138, 255)),
)

# FreeSerif is the one font on the build image that carries Arabic.
AR_FONT = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
EN_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

SCALE = 4                 # draw large, shrink at the end, so edges are smooth
SIZE = 512 * SCALE

WHITE = (255, 255, 255, 255)

ARABIC = dict(direction="rtl", language="ar")


def refuse_without_shaping(name_ar: str) -> None:
    """Stop before drawing if the Arabic would come out malformed."""
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


def draw(name_ar: str, name_en: str, ground, track, lit,
         accent) -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    pen.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1],
                          radius=80 * SCALE, fill=ground)

    # The ring is a countdown caught part-way: lit from the top round to
    # the lower left, dark for what is left.
    pad, width = 46 * SCALE, 22 * SCALE
    ring = [pad, pad, SIZE - 1 - pad, SIZE - 1 - pad]
    pen.ellipse(ring, outline=track, width=width)
    pen.arc(ring, start=-90, end=170, fill=lit, width=width)

    # Both lines sit inside the ring, so neither may be wider than it.
    inner = SIZE - 2 * (pad + width) - 24 * SCALE
    middle = SIZE // 2

    arabic = fitted(AR_FONT, name_ar, inner, 130 * SCALE, **ARABIC)
    latin = fitted(EN_FONT, name_en, int(inner * 0.78), 34 * SCALE)

    pen.text((middle, 224 * SCALE), name_ar, font=arabic, fill=WHITE,
             anchor="mm", **ARABIC)
    pen.text((middle, 322 * SCALE), name_en, font=latin, fill=accent,
             anchor="mm")

    return image.resize((512, 512), Image.LANCZOS)


def main() -> None:
    for out, name_ar, name_en, ground, track, lit, accent in MARKS:
        refuse_without_shaping(name_ar)
        draw(name_ar, name_en, ground, track, lit, accent).save(out)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
