#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Print each beIN SPORTS Qatar channel's number onto the supplied orb.

The owner photographed his set-top box and could not read a single one of
these icons. Four designs were drawn here and rejected — a sized label on
the old bubble, a dark tile, a tile with a sweep, a plain sphere — before
he supplied the orb he actually wanted: a rendered purple sphere with a
white band carrying the beIN wordmark, and nothing under it. This script
does the last step only. It is a compositor, not a renderer.

logos/bein_orb.png is that orb with its background removed. The circle was
found by walking rays out from the centre and taking the median radius at
which the rim's brightness steps, then kept a few pixels inside so no
background came with it; the cut was checked against black, white and
purple before being committed.

The channel's number goes in the empty purple below the band, with a soft
drop shadow so it sits on the surface rather than floating over it. An
earlier version of the artwork carried the word SPORTS there and had to be
painted out; four ways of finding that word failed, because the band and
the word are both white and the beIN lettering inside the band breaks any
run test. None of that is needed now — the space is already clear, which
is the whole reason this orb replaced it.

ALL FORTY SHARE ONE ORB. The families are no longer dressed apart; the
supplied artwork has one colourway, and the number is the only thing that
differs, which is why it is set as large as the space allows.

The orb is not a beIN asset; the public logo databases carry only the flat
wordmark. Printing the numbers here is what fixes the eleven channels that
were wearing another channel's mark: beIN SPORTS 9 and AFC 4-6 showed an
unnumbered brand logo, and XTRA 3-9 all showed the words "XTRA 1", because
the upstream database has no separate picture for any of them.

Türkiye is NOT touched. beIN SPORTS 1 in Istanbul is a different channel
showing different football from beIN SPORTS 1 in Doha; it has its own
bein_tr*.png copies of the flat mark.

Run it after adding a channel to bein_sports_qatar_epg.LOGO_KEYS:

    python make_bein_bubbles.py

It writes only the stems listed in SPECS, so it can touch neither another
broadcaster's logo nor bein_orb.png itself. fetch_logos.py does not list
these keys, for the same reason it does not list tabii: a run of it would
otherwise overwrite all forty with the pictures they came from.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = "logos"
ORB = os.path.join(OUT_DIR, "bein_orb.png")
# Outfit Bold: every label here is Latin ("1", "MAX 1", "XTRA 1"), and its
# wider counters stay open when a television scales the icon down. A label
# that ever needs Arabic has to come back to fonts/Tajawal-*.ttf.
FONT_PATH = os.path.join("fonts", "Outfit-Bold.ttf")

SIZE = 512

# Where the number sits: the clear purple under the white band. The band's
# lower edge is tilted, so the centre is placed below its lowest point.
LABEL_CENTRE = .745
LABEL_MAX_W = .60
LABEL_MAX_H = .20
TRACKING = .03

INK = (253, 252, 255)
SHADOW = (18, 6, 40, 205)
SHADOW_OFFSET = .005   # across, as a fraction of the canvas
SHADOW_DROP = .007     # and down
SHADOW_BLUR = .005

# The orb is a render, not flat art, so PNG cannot compress it: in full
# colour it weighs 283 KB a file, over 11 MB for the roster. The RGB is
# reduced to a dithered palette and the alpha kept intact — saving as a
# palette PNG instead carries only one transparent index, which jagged the
# rim when it was tried.
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


def largest_fit(draw: ImageDraw.ImageDraw, text: str):
    """The biggest face whose tracked text fits the space under the band."""
    for px in range(int(SIZE * .36), 8, -1):
        font = ImageFont.truetype(FONT_PATH, px)
        track = px * TRACKING
        width = (sum(draw.textlength(c, font=font) for c in text)
                 + track * (len(text) - 1))
        box = draw.textbbox((0, 0), text, font=font)
        if width <= SIZE * LABEL_MAX_W and (box[3] - box[1]) <= SIZE * LABEL_MAX_H:
            return font, track, width, box
    return font, track, width, box


def label_on(img: Image.Image, text: str) -> None:
    """Print the channel's number, with a shadow so it sits on the surface."""
    draw = ImageDraw.Draw(img)
    font, track, width, box = largest_fit(draw, text)
    x0 = (SIZE - width) / 2
    y = SIZE * LABEL_CENTRE - (box[3] - box[1]) / 2 - box[1]

    shade = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    x = x0
    for ch in text:
        sd.text((x + SIZE * SHADOW_OFFSET, y + SIZE * SHADOW_DROP),
                ch, font=font, fill=SHADOW)
        x += sd.textlength(ch, font=font) + track
    img.alpha_composite(shade.filter(ImageFilter.GaussianBlur(SIZE * SHADOW_BLUR)))

    x = x0
    for ch in text:
        draw.text((x, y), ch, font=font, fill=INK)
        x += draw.textlength(ch, font=font) + track


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
    orb = Image.open(ORB).convert("RGBA")
    if orb.size != (SIZE, SIZE):
        orb = orb.resize((SIZE, SIZE), Image.LANCZOS)

    for stem, label in SPECS:
        path = os.path.join(OUT_DIR, f"{stem}.png")
        img = orb.copy()
        if label:
            label_on(img, label)
        save(img, path)
        print(f"  {path:28} {label or '(orb as supplied)'}")

    print(f"\nprinted {len(SPECS)} marks on the orb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
