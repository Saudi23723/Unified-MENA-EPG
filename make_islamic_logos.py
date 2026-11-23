#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the marks for the playlist's azkar and sunnah channels.

The same tile, gradient, fonts and gold as the Quran mark
(make_quran_logo.py), with an emblem of their own: a string of prayer
beads for أذكار الصباح, a mosque's dome and minaret for السنة النبوية.

    python make_islamic_logos.py

Writes logos/azkar.png and logos/sunnah.png, 512×512 transparent PNGs.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import make_quran_logo as q

S = q.SCALE


def glow(img: Image.Image, box) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=(226, 186, 106, 70))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(40 * S)))


def beads(img: Image.Image) -> None:
    """A ring of prayer beads with its tassel."""
    cx, cy, r = q.SIZE // 2, 170 * S, 88 * S
    glow(img, (cx - 150 * S, cy - 130 * S, cx + 150 * S, cy + 150 * S))
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=q.GOLD_DEEP, width=4 * S)
    count, bead = 33, 11 * S
    for i in range(count):
        a = math.pi / 2 + 2 * math.pi * i / count
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        d.ellipse((x - bead, y - bead, x + bead, y + bead), fill=q.GOLD)
    # The tassel hangs from the bottom bead.
    top = cy + r + bead
    d.rectangle((cx - 5 * S, top, cx + 5 * S, top + 22 * S), fill=q.GOLD_DEEP)
    d.polygon([(cx - 18 * S, top + 22 * S), (cx + 18 * S, top + 22 * S),
               (cx + 10 * S, top + 50 * S), (cx - 10 * S, top + 50 * S)], fill=q.GOLD)


def mosque(img: Image.Image) -> None:
    """A dome on its drum, a minaret beside it, a crescent above."""
    cx, base = q.SIZE // 2, 300 * S
    glow(img, (cx - 160 * S, 60 * S, cx + 160 * S, base + 20 * S))
    d = ImageDraw.Draw(img)
    # The hall and the dome.
    d.rectangle((cx - 110 * S, base - 70 * S, cx + 70 * S, base), fill=q.GOLD)
    d.pieslice((cx - 85 * S, base - 170 * S, cx + 45 * S, base - 40 * S), 180, 360, fill=q.GOLD)
    d.rectangle((cx - 85 * S, base - 106 * S, cx + 45 * S, base - 70 * S), fill=q.GOLD)  # the drum
    d.rectangle((cx - 30 * S, base - 45 * S, cx - 10 * S, base), fill=q.GOLD_DEEP)  # the door
    # The minaret.
    d.rectangle((cx + 90 * S, base - 200 * S, cx + 120 * S, base), fill=q.GOLD)
    d.polygon([(cx + 85 * S, base - 200 * S), (cx + 125 * S, base - 200 * S),
               (cx + 105 * S, base - 245 * S)], fill=q.GOLD)
    d.rectangle((cx + 82 * S, base - 150 * S, cx + 128 * S, base - 140 * S), fill=q.GOLD_DEEP)
    # The crescent over the dome.
    mx, my, mr = cx - 20 * S, base - 196 * S, 20 * S
    d.ellipse((mx - mr, my - mr, mx + mr, my + mr), fill=q.GOLD)
    d.ellipse((mx - mr + 9 * S, my - mr - 4 * S, mx + mr + 9 * S, my + mr - 4 * S), fill=q.TOP)


def draw(out: str, name_ar: str, name_en: str, emblem) -> None:
    img = q.tile()
    emblem(img)
    d = ImageDraw.Draw(img)
    ar = ImageFont.truetype(q.AR_FONT, 74 * S)
    en = ImageFont.truetype(q.EN_FONT, 40 * S)
    d.text((q.SIZE // 2, 388 * S), name_ar, font=ar, fill=q.WHITE, anchor="mm",
           direction="rtl", language="ar")
    d.text((q.SIZE // 2, 458 * S), name_en, font=en, fill=q.GOLD, anchor="mm")
    img.resize((512, 512), Image.LANCZOS).save(out, optimize=True)
    print(f"wrote {out}")


def main() -> int:
    q.refuse_without_shaping()
    draw("logos/azkar.png", "أذكار الصباح", "MORNING ADHKAR", beads)
    draw("logos/sunnah.png", "السنة النبوية", "PROPHETIC SUNNAH", mosque)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
