#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A mark for every playlist channel that has none.

The owner's second playlist shows a plain "TV" tile wherever neither the
provider nor any source gives a logo (5 October 2026: Ligue 1+, the Shoof
and Shahid loops, the local stations no guide carries). Each of those gets
a tile drawn here: the channel's own name on a rounded tile in the
dashboard marks' style, the colour chosen by its category, the category
written small underneath — so a channel always reads as itself.

The tiles are published beside the playlist guide on its own branch
(att-epg, replaced whole each run), not on main, so a thousand images do
not pile up in the repository's history. The same name always draws the
same bytes, so a rebuild changes nothing it does not have to.
"""

from __future__ import annotations

import hashlib
import io
import os
import re

from PIL import Image, ImageDraw, ImageFont, features

OUT_DIR = "logos_gen"
BASE_URL = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
            "att-epg/" + OUT_DIR + "/")
SIZE, SCALE = 256, 2
FONT_AR = "fonts/Tajawal-ExtraBold.ttf"
FONT_EN = "fonts/Tajawal-Bold.ttf"
FONT_CAP = "fonts/Tajawal-Medium.ttf"
ARABIC = re.compile(r"[؀-ۿ]")

# (top, bottom, accent) per family of category; anything else by hash.
PALETTES = [
    ((20, 40, 78), (6, 12, 26), (96, 170, 255)),     # blue
    ((70, 16, 24), (22, 5, 8), (255, 96, 110)),      # red
    ((14, 52, 40), (4, 16, 12), (70, 220, 150)),     # green
    ((60, 40, 10), (18, 12, 3), (255, 186, 70)),     # amber
    ((48, 22, 70), (14, 6, 22), (190, 130, 255)),    # violet
    ((10, 50, 62), (3, 15, 19), (80, 220, 230)),     # teal
]


def palette(category: str):
    digest = int(hashlib.md5((category or "").encode()).hexdigest(), 16)
    return PALETTES[digest % len(PALETTES)]


def url_for(name: str, category: str) -> str:
    return BASE_URL + key(name, category) + ".png"


def key(name: str, category: str) -> str:
    return hashlib.md5(f"{category}\t{name}".encode()).hexdigest()[:12]


def _fit(draw, text: str, font_path: str, box_w: int, box_h: int, rtl: bool):
    """The largest font, in up to three lines, that fits the box."""
    words = text.split()
    for size in range(96 * SCALE // 2, 14 * SCALE, -2 * SCALE):
        font = ImageFont.truetype(font_path, size)
        kw = dict(direction="rtl", language="ar") if rtl else {}
        lines, line = [], ""
        for word in words:
            trial = (line + " " + word).strip()
            if draw.textlength(trial, font=font, **kw) <= box_w:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        height = len(lines) * size * 1.15
        if len(lines) <= 3 and height <= box_h and all(
                draw.textlength(l, font=font, **kw) <= box_w for l in lines):
            return font, lines, kw
    font = ImageFont.truetype(font_path, 14 * SCALE)
    return font, [text[:24]], dict(direction="rtl", language="ar") if rtl else {}


def draw(name: str, category: str) -> bytes:
    S = SIZE * SCALE
    top, bottom, accent = palette(category)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    column = Image.new("RGBA", (1, S))
    for y in range(S):
        t = y / (S - 1)
        column.putpixel((0, y), tuple(round(top[i] + (bottom[i] - top[i]) * t)
                                      for i in range(3)) + (255,))
    grad = column.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), 58 * SCALE, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # An accent bar, the dashboard marks' signature.
    d.rounded_rectangle((S // 2 - 34 * SCALE, 30 * SCALE, S // 2 + 34 * SCALE, 38 * SCALE),
                        4 * SCALE, fill=accent + (255,))
    rtl = bool(ARABIC.search(name)) and features.check("raqm")
    text = name if (rtl or not ARABIC.search(name)) else category or name
    font, lines, kw = _fit(d, text, FONT_AR if rtl else FONT_EN,
                           S - 36 * SCALE, 150 * SCALE, rtl)
    size = font.size
    y0 = 128 * SCALE - len(lines) * size * 1.15 / 2 + size * 0.55
    for i, line in enumerate(lines):
        d.text((S // 2, y0 + i * size * 1.15), line, font=font, fill=(255, 255, 255, 255),
               anchor="mm", **kw)
    if category:
        cap = ImageFont.truetype(FONT_CAP, 16 * SCALE)
        label = re.sub(r"\s+", " ", category.strip()).upper()[:26]
        if not ARABIC.search(label):
            d.text((S // 2, 226 * SCALE), label, font=cap, fill=accent + (255,), anchor="mm")
    out = io.BytesIO()
    # A palette of 64 colours: a fifth of the bytes, and a tile of flat
    # colour and text loses nothing a television can show.
    small = img.resize((SIZE, SIZE), Image.LANCZOS)
    small.quantize(colors=64, method=Image.Quantize.FASTOCTREE).save(out, format="PNG",
                                                                       optimize=True)
    return out.getvalue()


def make(name: str, category: str) -> str:
    """Write the tile for this channel (once) and return its published URL."""
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, key(name, category) + ".png")
    if not os.path.exists(path):
        with open(path, "wb") as handle:
            handle.write(draw(name, category))
    return url_for(name, category)
