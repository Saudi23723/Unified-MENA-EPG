#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the placeholder marks for the filler channels.

These channels have no published schedule and no broadcaster artwork this
project can fetch, so each gets a plain generated mark instead: its short
name in white on its own colour, inside a thin ring so it still reads as a
channel bug when a player shrinks it to a corner icon.

They are deliberately *not* the broadcasters' logos. A placeholder channel
wearing a real channel's branding would claim to be something it is not,
and the whole point of the filler is that it never does that.

Latin text only. Arabic needs shaping and bidi to render correctly, and a
mark with disconnected back-to-front letters would look broken; the Arabic
name lives in the guide's <display-name>, which players render properly.

Run it after adding a row to CHANNELS in filler_epg.py:

    python make_filler_logos.py

It only writes files whose name appears in SPECS, so it can never touch a
real broadcaster logo already in logos/.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = "logos"
SIZE = 400
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# (logo file stem, short Latin label, background colour)
# Pairs of the same series share a hue so they read as siblings, and differ
# in shade so they are never mistaken for each other.
SPECS = [
    ("maraya",       "MARAYA",    (26, 42, 74)),
    ("alkabeerawi",  "AL KABEER", (74, 30, 34)),
    ("aflam",        "AFLAM",     (30, 58, 46)),
    ("ayla5",        "AYLA 5",    (52, 34, 78)),
    ("ayla6",        "AYLA 6",    (72, 48, 104)),
    ("fusoul1",      "FUSOUL 1",  (20, 54, 70)),
    ("fusoul2",      "FUSOUL 2",  (32, 78, 96)),
    ("dayaa1",       "DAYAA 1",   (78, 52, 24)),
    ("dayaa2",       "DAYAA 2",   (104, 72, 34)),
    ("mudeer1",      "MUDEER 1",  (60, 26, 52)),
    ("mudeer2",      "MUDEER 2",  (86, 40, 74)),
    ("alkhibra",     "AL KHIBRA", (34, 62, 62)),
    ("bibasata",     "BIBASATA",  (68, 40, 40)),
    ("alwaq",        "AL WAQ",    (40, 46, 84)),
    ("altawareed",   "TAWAREED",  (44, 66, 40)),
]

SUBTITLE = "24/7"


def draw(stem: str, label: str, background: tuple[int, int, int]) -> str:
    image = Image.new("RGBA", (SIZE, SIZE), background + (255,))
    pen = ImageDraw.Draw(image)
    pen.ellipse([14, 14, SIZE - 14, SIZE - 14],
                outline=(255, 255, 255, 70), width=5)

    # Shrink until the label fits the ring rather than the square, so a long
    # name like AL KHIBRA never touches the edge.
    size = 78
    while size > 20:
        font = ImageFont.truetype(FONT_PATH, size)
        box = pen.textbbox((0, 0), label, font=font)
        if box[2] - box[0] <= SIZE - 110:
            break
        size -= 3

    font = ImageFont.truetype(FONT_PATH, size)
    box = pen.textbbox((0, 0), label, font=font)
    pen.text(((SIZE - (box[2] - box[0])) / 2 - box[0],
              (SIZE - (box[3] - box[1])) / 2 - box[1]),
             label, font=font, fill=(255, 255, 255, 255))

    small = ImageFont.truetype(FONT_PATH, 28)
    sbox = pen.textbbox((0, 0), SUBTITLE, font=small)
    pen.text(((SIZE - (sbox[2] - sbox[0])) / 2 - sbox[0], SIZE - 96),
             SUBTITLE, font=small, fill=(255, 255, 255, 150))

    path = os.path.join(OUT_DIR, f"{stem}.png")
    image.save(path)
    return path


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    for stem, label, background in SPECS:
        path = draw(stem, label, background)
        print(f"  {path:<28} {label}")
    print(f"{len(SPECS)} filler marks written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
