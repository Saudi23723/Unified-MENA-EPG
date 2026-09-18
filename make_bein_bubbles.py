#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the forty beIN SPORTS Qatar channel marks, keyed by family.

The owner photographed his set-top box and could not read a single one of
these icons. Several designs were drawn here and rejected — a sized label
on the old bubble, a dark tile, a tile with a sweep, a rendered orb —
before he supplied beIN's own artwork and said to use that, not versions
of it. Both source files came from him unaltered:

    logos/bein_tile.png   the official app icon, purple, wordmark low
    logos/bein_mark.png   the beIN SPORT lockup alone, white on nothing

CHANNELS 1-9 WEAR THE APP ICON as it ships, with only the channel number
printed into the empty upper half. Nothing else in that artwork is
touched.

EVERY OTHER CHANNEL wears a two-tone plate: the same purple above, the
lockup below on a band whose colour names the family at a glance, so a
row of forty icons sorts itself before it is read.

    silver   the default
    red      XTRA 1-9
    gold     MAX, AFC, EN and FR

WHERE THE NUMBER GOES was measured, not guessed. Against a ruler the
lockup sits LOW in the app icon — beIN spans y 250-395 and SPORTS 400-450
on a 512 canvas — which leaves the whole upper half empty. The number goes
there. A first attempt placed it at .735 and landed it on the wordmark.
On the two-tone plate the band starts at .44, so the number centres at .22,
the middle of the purple.

It is set in white with a soft drop shadow, and sized to the space rather
than to a fixed point size, so a bare "1" comes out larger than "XTRA 1"
without anyone choosing it.

Printing the numbers is what fixes the eleven channels that were wearing
another channel's mark. beIN SPORTS 9 and AFC 4-6 showed an unnumbered
brand logo, and XTRA 3-9 all showed the words "XTRA 1", because the
upstream database has no separate picture for any of them.

Türkiye is NOT touched. beIN SPORTS 1 in Istanbul is a different channel
showing different football from beIN SPORTS 1 in Doha; it has its own
bein_tr*.png copies of the flat mark.

Run it after adding a channel to bein_sports_qatar_epg.LOGO_KEYS:

    python make_bein_bubbles.py

It writes only the stems listed in SPECS, so it can touch neither another
broadcaster's logo nor either source file. fetch_logos.py does not list
these keys, for the same reason it does not list tabii: a run of it would
otherwise overwrite all forty with the pictures they came from.
"""

from __future__ import annotations

import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

OUT_DIR = "logos"
TILE = os.path.join(OUT_DIR, "bein_tile.png")
MARK = os.path.join(OUT_DIR, "bein_mark.png")
# Outfit Bold: a geometric face, closest of what is here to the rounded
# letterforms of the wordmark it sits above. Every label is Latin; one that
# ever needs Arabic has to come back to fonts/Tajawal-*.ttf.
FONT_PATH = os.path.join("fonts", "Outfit-Bold.ttf")

SIZE = 512

# The empty purple. On the app icon the lockup runs from y 250 down, so
# everything above 240 is clear; on the plate the band starts at SPLIT.
TILE_CENTRE = .255
PLATE_CENTRE = .22
LABEL_MAX_W = .62
LABEL_MAX_H = .26
TRACKING = .02
SUPERSAMPLE = 3

INK = (255, 255, 255)
SHADOW = (20, 6, 44, 170)
SHADOW_OFFSET = .004
SHADOW_DROP = .006
SHADOW_BLUR = .005

# The plate. Purple is read off the app icon so the two halves of the set
# sit together — it is the flat (79, 24, 129) the icon's top half is
# filled with, sampled, not chosen — and the corner is measured off it
# too: on a 512 canvas its opaque box runs x 2-509 and its left edge
# goes straight at y 69, which is a radius of 67. A plate drawn rounder
# than that reads as a different app sitting in the same row.
PURPLE = (79, 24, 129)
SILVER, SILVER_INK = (196, 198, 206), (34, 34, 42)
GOLD, GOLD_INK = (212, 170, 84), (44, 28, 6)
RED, RED_INK = (176, 32, 44), (255, 255, 255)
SPLIT = .44
CORNER = 67 / 512
MARK_WIDTH = .72
MARK_TOP = .52

# The icon is artwork, not flat colour, so PNG cannot compress it well.
# Reducing the RGB to a dithered palette while keeping the 8-bit alpha
# holds the rounded corners soft; saving as a palette PNG instead carries
# a single transparent index and jags them.
COLOURS = 256

# 1-9 keep beIN's own icon. So does the unnumbered brand mark: a plate
# with no number on it would be the lockup twice over.
AS_SUPPLIED = {f"bein_{n}" for n in range(1, 10)} | {"bein_brand"}

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

GOLD_FAMILIES = ("bein_max", "bein_afc", "bein_en", "bein_fr")


def family(stem: str):
    """The band colour, the ink the lockup takes on it, and its name."""
    if stem.startswith("bein_xtra"):
        return RED, RED_INK, "red"
    if stem.startswith(GOLD_FAMILIES):
        return GOLD, GOLD_INK, "gold"
    return SILVER, SILVER_INK, "silver"


def plate_mask() -> Image.Image:
    """The rounded square the plate is cut to, drawn big and shrunk.

    ImageDraw does not antialias, and a corner stepped in whole pixels is
    the one thing on a 72px icon the eye catches. Drawing it at
    SUPERSAMPLE and scaling down gives the same soft rim the app icon has.
    """
    big = SIZE * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big - 1, big - 1], radius=int(big * CORNER), fill=255)
    return mask.resize((SIZE, SIZE), Image.LANCZOS)


MASK = plate_mask()


def plate(lower, ink, mark: Image.Image) -> Image.Image:
    """Purple above, the family's colour below, the lockup sitting on it."""
    img = Image.new("RGBA", (SIZE, SIZE), PURPLE + (255,))
    ImageDraw.Draw(img).rectangle(
        [0, int(SIZE * SPLIT), SIZE, SIZE], fill=lower + (255,))

    width = int(SIZE * MARK_WIDTH)
    art = mark.resize((width, round(mark.height * width / mark.width)),
                      Image.LANCZOS)
    tint = Image.new("RGBA", art.size, ink + (255,))
    tint.putalpha(art.getchannel("A"))
    img.alpha_composite(tint, ((SIZE - width) // 2, int(SIZE * MARK_TOP)))
    img.putalpha(MASK)
    return img


def largest_fit(text: str):
    """The biggest face whose tracked text fits the clear purple."""
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


def label_on(img: Image.Image, text: str, centre: float) -> int:
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
    y0 = big * centre - (box[3] - box[1]) / 2 - box[1]
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
    tile_alpha = tile.getchannel("A")
    mark = Image.open(MARK).convert("RGBA")

    sizes = []
    tally = {}
    for stem, label in SPECS:
        path = os.path.join(OUT_DIR, f"{stem}.png")
        if stem in AS_SUPPLIED:
            img, mask, centre, dress = tile.copy(), tile_alpha, TILE_CENTRE, "icon"
        else:
            lower, ink, dress = family(stem)
            img, mask, centre = plate(lower, ink, mark), MASK, PLATE_CENTRE
        tally[dress] = tally.get(dress, 0) + 1
        if label:
            sizes.append(label_on(img, label, centre))
            img.putalpha(ImageChops.darker(img.getchannel("A"), mask))
        save(img, path)
        print(f"  {path:28} {dress:7} {label or '(icon as supplied)'}")

    spread = "  ".join(f"{n}× {k}" for k, n in sorted(tally.items()))
    print(f"\ndrew {len(SPECS)} beIN marks  ·  {spread}  ·  "
          f"face {min(sizes)}-{max(sizes)}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
