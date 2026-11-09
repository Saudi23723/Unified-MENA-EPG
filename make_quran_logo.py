#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the mark for the playlist's Quran channels.

The Islamic group of the owner's second playlist is a hundred and thirty
channels, most of them one reciter each, and the playlist gives none of
them a picture. They share one mark: an open mushaf on its stand in gold
on a deep green tile, its name in Arabic over HOLY QURAN — the same
rounded tile, fonts and layout as the dashboard's own marks.

    python make_quran_logo.py

Writes logos/quran.png, a 512×512 transparent PNG.
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

OUT = "logos/quran.png"
NAME_AR = "القرآن الكريم"
NAME_EN = "HOLY QURAN"
TOP, BOTTOM = (10, 58, 40, 255), (3, 18, 12, 255)
GOLD = (226, 186, 106, 255)
GOLD_DEEP = (176, 134, 62, 255)
WHITE = (255, 255, 255, 255)

AR_FONT = "fonts/Tajawal-ExtraBold.ttf"
EN_FONT = "fonts/Tajawal-Medium.ttf"
SCALE = 2
SIZE = 512 * SCALE
RADIUS = 118 * SCALE


def refuse_without_shaping() -> None:
    if not features.check("raqm"):
        sys.exit("Pillow has no Raqm, so Arabic would not be shaped — "
                 "do not commit the output of a run without it.")


def tile() -> Image.Image:
    grad = Image.new("RGBA", (SIZE, SIZE))
    px = grad.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        row = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(4))
        for x in range(SIZE):
            px[x, y] = row
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), RADIUS, fill=255)
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def emblem(img: Image.Image) -> None:
    """An open mushaf resting on a crossed stand, with a soft glow."""
    s = SCALE
    cx, top = SIZE // 2, 92 * s
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - 150 * s, top - 10 * s, cx + 150 * s, top + 250 * s),
                                 fill=(226, 186, 106, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40 * s)))
    d = ImageDraw.Draw(img)
    # The stand (rahl): two crossed boards under the book.
    d.polygon([(cx - 122 * s, top + 236 * s), (cx - 96 * s, top + 236 * s),
               (cx + 40 * s, top + 150 * s), (cx + 14 * s, top + 150 * s)], fill=GOLD_DEEP)
    d.polygon([(cx + 122 * s, top + 236 * s), (cx + 96 * s, top + 236 * s),
               (cx - 40 * s, top + 150 * s), (cx - 14 * s, top + 150 * s)], fill=GOLD_DEEP)
    # The two open pages, each a gold leaf with a cream page inside.
    left = [(cx - 6 * s, top + 40 * s), (cx - 150 * s, top + 8 * s),
            (cx - 150 * s, top + 150 * s), (cx - 6 * s, top + 182 * s)]
    right = [(cx + 6 * s, top + 40 * s), (cx + 150 * s, top + 8 * s),
             (cx + 150 * s, top + 150 * s), (cx + 6 * s, top + 182 * s)]
    d.polygon(left, fill=GOLD)
    d.polygon(right, fill=GOLD)
    inset = 14 * s
    d.polygon([(cx - 6 * s - 0, top + 40 * s + inset), (cx - 150 * s + inset, top + 8 * s + inset),
               (cx - 150 * s + inset, top + 150 * s - inset // 2), (cx - 6 * s, top + 182 * s - inset)],
              fill=(250, 240, 214, 255))
    d.polygon([(cx + 6 * s + 0, top + 40 * s + inset), (cx + 150 * s - inset, top + 8 * s + inset),
               (cx + 150 * s - inset, top + 150 * s - inset // 2), (cx + 6 * s, top + 182 * s - inset)],
              fill=(250, 240, 214, 255))
    # Lines of text on each page.
    for i in range(5):
        y = top + (52 + i * 22) * s
        d.line([(cx - 128 * s, y - 14 * s + i * 1), (cx - 26 * s, y + 6 * s)], fill=GOLD_DEEP, width=5 * s)
        d.line([(cx + 26 * s, y + 6 * s), (cx + 128 * s, y - 14 * s + i * 1)], fill=GOLD_DEEP, width=5 * s)
    # The spine.
    d.line([(cx, top + 34 * s), (cx, top + 186 * s)], fill=GOLD_DEEP, width=6 * s)


def words(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    ar = ImageFont.truetype(AR_FONT, 74 * SCALE)
    en = ImageFont.truetype(EN_FONT, 40 * SCALE)
    d.text((SIZE // 2, 388 * SCALE), NAME_AR, font=ar, fill=WHITE, anchor="mm",
           direction="rtl", language="ar")
    d.text((SIZE // 2, 458 * SCALE), NAME_EN, font=en, fill=GOLD, anchor="mm")


def main() -> int:
    refuse_without_shaping()
    img = tile()
    emblem(img)
    words(img)
    img.resize((512, 512), Image.LANCZOS).save(OUT, optimize=True)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
