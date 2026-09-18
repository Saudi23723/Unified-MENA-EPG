#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the beIN SPORTS Qatar channel marks as the glossy bubble.

The repo owner photographed his set-top box and asked for the round purple
mark it shows. That mark is not a beIN asset: the public logo databases
carry only the flat wordmark, and the bubble comes from the icon packs
IPTV providers assemble themselves. His own box proves how those packs
age — four channels in a row on it wore the plate "HD 1 Ar", and a fifth
wore "HD 6 Ar".

So the bubble is drawn here instead of hunted for, over the official
wordmark this repository already holds. Drawing it is what fixes the
eleven channels that were wearing another channel's mark: beIN SPORTS 9
and AFC 4-6 showed an unnumbered brand logo, and XTRA 3-9 all showed the
words "XTRA 1", because the upstream database has no separate picture for
any of them. A drawn plate always says the channel it belongs to.

Türkiye is NOT drawn. beIN SPORTS 1 in Istanbul is a different channel
showing different football from beIN SPORTS 1 in Doha, and it used to
share these seven files; it now has its own bein_tr*.png copies of the
flat mark, so redrawing Doha leaves Istanbul alone.

Run it after adding a channel to bein_sports_qatar_epg.LOGO_KEYS:

    python make_bein_bubbles.py

It writes only the stems listed in SPECS, so it cannot touch a logo that
belongs to another broadcaster. fetch_logos.py no longer lists these keys
for the same reason it does not list tabii: a future run of it would
otherwise overwrite all forty with the pictures they came from.

The wordmark is read from logos/bein_wordmark.png, not from bein_brand.png,
because bein_brand is itself one of the forty this script overwrites — a
second run would otherwise draw a bubble on top of a bubble.
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = "logos"
WORDMARK = os.path.join(OUT_DIR, "bein_wordmark.png")
FONT_PATH = os.path.join("fonts", "Tajawal-Bold.ttf")

SIZE = 512

# The ball is shaded between these three, lit from the upper left, which
# is where the light sits in the photograph.
SHADOW = (58, 22, 92)
BODY = (92, 45, 145)
LIT = (140, 92, 200)
PLATE_INK = (74, 28, 116)

# (logo file stem, what its plate reads)
#
# The nine Arabic channels carry the box's own wording, "HD n Ar", because
# that is the set the owner was looking at. Every other family is named
# the way beIN names it, so a plate never has to be decoded.
SPECS = [
    ("bein_1", "HD 1 Ar"),
    ("bein_2", "HD 2 Ar"),
    ("bein_3", "HD 3 Ar"),
    ("bein_4", "HD 4 Ar"),
    ("bein_5", "HD 5 Ar"),
    ("bein_6", "HD 6 Ar"),
    ("bein_7", "HD 7 Ar"),
    ("bein_8", "HD 8 Ar"),
    ("bein_9", "HD 9 Ar"),

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

    ("bein_brand", "Ar"),
    ("bein_4k", "4K"),
    ("bein_4khdr", "4K HDR"),
    ("bein_nba", "NBA"),
    ("bein_news", "NEWS"),
]


def ball(size: int) -> Image.Image:
    """A lit sphere: Lambert term towards the light, plus a rim highlight.

    Drawn per pixel rather than as a canned radial gradient because a
    gradient centred on the disc reads as a flat ring; the terminator has
    to sit off centre for the shape to look round.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    r = size / 2.0
    lx, ly, lz = -0.45, -0.55, 0.70
    for y in range(size):
        for x in range(size):
            dx, dy = (x - r + .5) / r, (y - r + .5) / r
            d2 = dx * dx + dy * dy
            if d2 > 1.0:
                continue
            dz = math.sqrt(max(0.0, 1.0 - d2))
            lam = max(0.0, dx * lx + dy * ly + dz * lz) ** 1.25
            col = [SHADOW[i] + (LIT[i] - SHADOW[i]) * lam for i in range(3)]
            rim = d2 ** 6 * 0.55
            col = [min(255.0, c + (BODY[i] - c) * rim) for i, c in enumerate(col)]
            # Feather the last 3.5% of the radius so the edge is not jagged.
            alpha = 255 if d2 < .965 else int(255 * (1 - (d2 - .965) / .035))
            px[x, y] = (int(col[0]), int(col[1]), int(col[2]), max(0, alpha))
    return img


def gloss(size: int) -> Image.Image:
    """The specular cap across the top of the ball."""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse(
        [size * .10, size * .04, size * .90, size * .48], fill=150)
    mask = mask.filter(ImageFilter.GaussianBlur(size * .045))
    cap = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    cap.putalpha(mask)
    return cap


def wordmark(height: int) -> Image.Image:
    """bein_brand.png recoloured to solid white, keeping its own alpha.

    The file on disk is the purple gradient mark. Only its alpha carries
    the letterforms, so replacing the colour channels wholesale is exact,
    where a per-pixel recolour would leave the antialiasing purple.
    """
    src = Image.open(WORDMARK).convert("RGBA")
    src = src.resize((int(src.width * height / src.height), height), Image.LANCZOS)
    white = Image.new("RGBA", src.size, (255, 255, 255, 255))
    white.putalpha(src.getchannel("A"))
    return white


def plate(text: str, font: ImageFont.FreeTypeFont, size: int) -> Image.Image:
    """The white tab naming the channel."""
    height = int(size * .145)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    width = max(int(size * .30),
                probe.textbbox((0, 0), text, font=font)[2] + int(size * .085))
    tab = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(tab)
    d.rounded_rectangle([0, 0, width - 1, height - 1],
                        radius=height * .22, fill=(255, 255, 255, 240))
    box = d.textbbox((0, 0), text, font=font)
    d.text(((width - (box[2] - box[0])) / 2 - box[0],
            (height - (box[3] - box[1])) / 2 - box[1]),
           text, font=font, fill=PLATE_INK)
    return tab


def bubble(label: str, sphere: Image.Image, cap: Image.Image,
           mark: Image.Image, font: ImageFont.FreeTypeFont) -> Image.Image:
    img = sphere.copy()
    img.alpha_composite(cap)
    img.alpha_composite(mark, ((SIZE - mark.width) // 2, int(SIZE * .30)))
    tab = plate(label, font, SIZE)
    img.alpha_composite(tab, ((SIZE - tab.width) // 2, int(SIZE * .615)))
    # A long plate would otherwise hang over the edge of the ball.
    img.putalpha(Image.composite(img.getchannel("A"),
                                 Image.new("L", (SIZE, SIZE), 0),
                                 sphere.getchannel("A")))
    return img


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    sphere, cap = ball(SIZE), gloss(SIZE)
    font = ImageFont.truetype(FONT_PATH, int(SIZE * .095))

    mark = wordmark(int(SIZE * .30))
    if mark.width > SIZE * .66:
        mark = mark.resize(
            (int(SIZE * .66), int(mark.height * SIZE * .66 / mark.width)),
            Image.LANCZOS)

    for stem, label in SPECS:
        path = os.path.join(OUT_DIR, f"{stem}.png")
        bubble(label, sphere, cap, mark, font).save(path, "PNG", optimize=True)
        print(f"  {path:28} {label}")

    print(f"\ndrew {len(SPECS)} marks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
