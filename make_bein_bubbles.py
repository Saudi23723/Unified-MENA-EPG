#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Print each beIN SPORTS Qatar channel's number onto beIN's own app icon.

The owner photographed his set-top box and could not read a single one of
these icons. Several designs were drawn here and rejected — a sized label
on the old bubble, a dark tile, a tile with a sweep, a rendered orb —
before he supplied beIN's own marks and said to use those, not versions of
them. logos/bein_tile.png is one of them unaltered: the official app icon,
purple with the white wordmark and its wave.

So this script composites. It adds one thing, the channel's number, and
touches nothing else in the artwork.

WHERE THE NUMBER GOES was measured, not guessed. Against a ruler the
lockup sits LOW in that icon — beIN spans y 250-395 and SPORTS 400-450 on
a 512 canvas — which leaves the whole upper half empty. The number goes
there. A first attempt placed it at .735 and landed it on the wordmark.

It is set in white with a soft drop shadow, and sized to the space rather
than to a fixed point size, so a bare "1" comes out larger than "XTRA 1"
without anyone choosing it.

The artwork is not this repository's to change; printing the numbers on it
is what fixes the eleven channels that were wearing another channel's
mark. beIN SPORTS 9 and AFC 4-6 showed an unnumbered brand logo, and XTRA
3-9 all showed the words "XTRA 1", because the upstream database has no
separate picture for any of them.

Türkiye is NOT touched. beIN SPORTS 1 in Istanbul is a different channel
showing different football from beIN SPORTS 1 in Doha; it has its own
bein_tr*.png copies of the flat mark.

Run it after adding a channel to bein_sports_qatar_epg.LOGO_KEYS:

    python make_bein_bubbles.py

It writes only the stems listed in SPECS, so it can touch neither another
broadcaster's logo nor bein_tile.png itself. fetch_logos.py does not list
these keys, for the same reason it does not list tabii: a run of it would
otherwise overwrite all forty with the pictures they came from.
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

OUT_DIR = "logos"
TILE = os.path.join(OUT_DIR, "bein_tile.png")
# Outfit Bold: a geometric face, closest of what is here to the rounded
# letterforms of the wordmark it sits above. Every label is Latin; one that
# ever needs Arabic has to come back to fonts/Tajawal-*.ttf.
FONT_PATH = os.path.join("fonts", "Outfit-Bold.ttf")

SIZE = 512

# The empty upper half of the icon. Measured against a ruler: the lockup
# runs from y 250 down, so everything above 240 is clear purple.
LABEL_CENTRE = .255
LABEL_MAX_W = .62
LABEL_MAX_H = .26
TRACKING = .02
SUPERSAMPLE = 3

INK = (255, 255, 255)
SHADOW = (20, 6, 44, 170)
SHADOW_OFFSET = .004
SHADOW_DROP = .006
SHADOW_BLUR = .005

# The icon is artwork, not flat colour, so PNG cannot compress it well.
# Reducing the RGB to a dithered palette while keeping the 8-bit alpha
# holds the rounded corners soft; saving as a palette PNG instead carries
# a single transparent index and jags them.
COLOURS = 256

SPECS = [
    ("bein_1", "1"),
    ("bein_2", "2"),
    ("bein_3", "3"),
    ("bein_4", "4"),
    ("bein_5", "5"),
    ("bein_6", "6"),
    ("bein_7", "7"),
    ("bein_8", "8"),
    ("bein_9", "9"),

    ("bein_xtra1", "XTRA 1"),
    ("bein_xtra2", "XTRA 2"),
    ("bein_xtra3", "XTRA 3"),
    ("bein_xtra4", "XTRA 4"),
    ("bein_xtra5", "XTRA 5"),
    ("bein_xtra6", "XTRA 6"),
    ("bein_xtra7", "XTRA 7"),
    ("bein_xtra8", "XTRA 8"),
    ("bein_xtra9", "XTRA 9"),

    ("bein_max1", "MAX 1"),
    ("bein_max2", "MAX 2"),
    ("bein_max3", "MAX 3"),
    ("bein_max4", "MAX 4"),
    ("bein_max5", "MAX 5"),
    ("bein_max6", "MAX 6"),

    ("bein_afc", "AFC"),
    ("bein_afc1", "AFC 1"),
    ("bein_afc2", "AFC 2"),
    ("bein_afc3", "AFC 3"),
    ("bein_afc4", "AFC 4"),
    ("bein_afc5", "AFC 5"),
    ("bein_afc6", "AFC 6"),

    ("bein_en1", "EN 1"),
    ("bein_en2", "EN 2"),

    ("bein_fr1", "FR 1"),
    ("bein_fr2", "FR 2"),

    ("bein_brand", ""),

    ("bein_4k", "4K"),

    ("bein_4khdr", "4K HDR"),

    ("bein_nba", "NBA"),

    ("bein_news", "NEWS"),
]


def _spans(px, y: int, size: int):
    """Where the orb starts and ends on one row, or None off the sphere."""
    xs = [x for x in range(size) if px[x, y][3] > 150]
    return (xs[0], xs[-1]) if len(xs) >= 60 else None


def largest_fit(text: str):
    """The biggest face whose tracked text fits the clear upper half."""
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    font = track = None
    for px in range(int(SIZE * .90), 8, -1):
        font = ImageFont.truetype(FONT_PATH, px)
        track = px * TRACKING
        width = (sum(probe.textlength(c, font=font) for c in text)
                 + track * (len(text) - 1))
        box = probe.textbbox((0, 0), text, font=font)
        if width <= SIZE * LABEL_MAX_W and (box[3] - box[1]) <= SIZE * LABEL_MAX_H:
            return px, track
    return px, track


def label_on(img: Image.Image, text: str) -> int:
    """Print the channel's number, with a shadow so it lifts off the purple."""
    px, track = largest_fit(text)
    big = SIZE * SUPERSAMPLE
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = ImageFont.truetype(FONT_PATH, px * SUPERSAMPLE)
    step = track * SUPERSAMPLE
    box = draw.textbbox((0, 0), text, font=font)
    run = (sum(draw.textlength(c, font=font) for c in text)
           + step * (len(text) - 1))
    x0 = (big - run) / 2
    y0 = big * LABEL_CENTRE - (box[3] - box[1]) / 2 - box[1]
    x = x0
    for ch in text:
        draw.text((x, y0), ch, font=font, fill=INK)
        x += draw.textlength(ch, font=font) + step
    flat = layer.resize((SIZE, SIZE), Image.LANCZOS)

    shade = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shade.paste(Image.new("RGBA", (SIZE, SIZE), SHADOW), (0, 0), flat)
    img.alpha_composite(
        shade.filter(ImageFilter.GaussianBlur(SIZE * SHADOW_BLUR))
             .transform((SIZE, SIZE), Image.AFFINE,
                        (1, 0, -SIZE * SHADOW_OFFSET, 0, 1, -SIZE * SHADOW_DROP)))
    img.alpha_composite(flat)
    return px


def save(img: Image.Image, path: str) -> None:
    """Write the mark with its palette reduced but its alpha untouched."""
    alpha = img.getchannel("A")
    flat = img.convert("RGB").quantize(
        colors=COLOURS, method=Image.FASTOCTREE,
        dither=Image.FLOYDSTEINBERG).convert("RGB").convert("RGBA")
    flat.putalpha(alpha)
    flat.save(path, "PNG", optimize=True)


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    tile = Image.open(TILE).convert("RGBA")
    if tile.size != (SIZE, SIZE):
        tile = tile.resize((SIZE, SIZE), Image.LANCZOS)
    alpha = tile.getchannel("A")

    sizes = []
    for stem, label in SPECS:
        path = os.path.join(OUT_DIR, f"{stem}.png")
        img = tile.copy()
        if label:
            sizes.append(label_on(img, label))
            img.putalpha(ImageChops.darker(img.getchannel("A"), alpha))
        save(img, path)
        print(f"  {path:28} {label or '(icon as supplied)'}")

    print(f"\nprinted {len(SPECS)} numbers on beIN's app icon  ·  "
          f"face {min(sizes)}-{max(sizes)}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
