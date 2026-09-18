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

import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

OUT_DIR = "logos"
ORB = os.path.join(OUT_DIR, "bein_orb.png")
# Big Shoulders Bold, condensed. It is here for a measured reason: capped at
# the wordmark's own letter height, a normal-width face lets "XTRA 1" reach
# only 74px while a bare "1" reaches 110, so the long names shrink to half
# the short ones and the roster stops looking like one set. Condensed, every
# label reaches 99-110. Twenty-nine of the forty carry a name rather than a
# bare number, so that is the majority.
FONT_PATH = os.path.join("fonts", "BigShoulders-Bold.ttf")

SIZE = 512

# The number is never taller than the beIN lettering above it. 110px on this
# 512 canvas, measured off the artwork against a ruler — the ascender at
# y=148, the baseline at y=258.
BEIN_CAP = 110 / 512

BAND_GAP = .045        # clear of the band's lower edge
RIM_KEEP = .90         # how close to the rim the type may come
TRACKING = .02
SUPERSAMPLE = 3        # the type is drawn big and brought down

INK = (255, 254, 252)
# The number is cut the way the beIN wordmark is cut: lit from the upper
# left, shadowed to the lower right. Flat white sat ON the picture; this
# sits IN it.
EMBOSS_LIGHT = (255, 248, 230, 150)
EMBOSS_DARK = (34, 10, 62, 215)
EMBOSS_OFFSET = .016   # of the type size, across
EMBOSS_DROP = .022     # and down
DROP_SHADOW = (12, 3, 30, 170)
SHADOW_BLUR = .010
SHADOW_SHIFT = .003
SHADOW_DROP = .009

# Reading the band's lower edge off the orb. It is sampled only at the two
# sides, where the band is clear of the beIN lettering, and a line is fitted
# through those samples.
BAND_LEVEL = 200
BAND_MIN_RUN = .08
SIDE_SHARE = .22       # how much of each side is sampled

# The orb is a render, not flat art, so PNG cannot compress it: in full
# colour the roster came to 11.3 MB. Saving as a palette PNG carries only
# one transparent index, which jagged the rim; reducing just the RGB and
# keeping the 8-bit alpha holds the soft edge.
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


def band_line(orb: Image.Image) -> tuple[float, float]:
    """The band's lower edge, as a line y = slope*x + intercept.

    The band is tilted, so the number cannot simply be placed at a fixed
    height: it would foul the band on one side and float on the other. The
    edge is sampled only at the two sides, where no lettering interrupts
    the white, and a line is fitted through those samples.
    """
    px = orb.load()
    size = orb.width
    need = size * BAND_MIN_RUN
    pts = []
    for x in range(size):
        if not (x < size * SIDE_SHARE or x > size * (1 - SIDE_SHARE)):
            continue
        column = [y for y in range(size) if px[x, y][3] >= 150]
        if not column:
            continue
        run = last = None
        found = None
        for y in range(column[0], column[-1] + 1):
            p = px[x, y]
            if p[0] > BAND_LEVEL and p[1] > BAND_LEVEL - 5 and p[2] > BAND_LEVEL:
                if run is None:
                    run = y
                last = y
            elif run is not None:
                if last - run >= need:
                    found = last
                run = None
        if run is not None and last - run >= need:
            found = last
        if found is not None:
            pts.append((x, found))
    if len(pts) < 40:
        raise SystemExit("could not find the band's lower edge on the orb")
    n = len(pts)
    sx = sum(x for x, _ in pts); sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts); sxy = sum(x * y for x, y in pts)
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return slope, (sy - slope * sx) / n


def place(width: float, height: float, slope: float, inter: float):
    """Where the number's box goes, or None if it will not fit.

    It is CENTRED in the clear purple rather than tucked under the band:
    hugging the band put the type high on the ball and left a gap beneath
    it. The space runs from the band's lowest corner down to where the
    box's own corners would leave the rim.
    """
    x0, x1 = (SIZE - width) / 2, (SIZE + width) / 2
    radius = SIZE / 2.0 * RIM_KEEP
    top = max(slope * x0 + inter, slope * x1 + inter) + SIZE * BAND_GAP
    reach = radius * radius - (width / 2.0) ** 2
    if reach <= 0:
        return None
    bottom = SIZE / 2.0 + math.sqrt(reach)
    if bottom - top < height:
        return None
    return top + (bottom - top - height) / 2.0


def largest_fit(text: str, slope: float, inter: float):
    """The biggest face that clears the band, the rim, and beIN's own height."""
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for px in range(int(SIZE * .70), 8, -1):
        font = ImageFont.truetype(FONT_PATH, px)
        track = px * TRACKING
        width = (sum(probe.textlength(c, font=font) for c in text)
                 + track * (len(text) - 1))
        box = probe.textbbox((0, 0), text, font=font)
        height = box[3] - box[1]
        if height > SIZE * BEIN_CAP:
            continue
        top = place(width, height, slope, inter)
        if top is not None:
            return px, track, top
    raise SystemExit(f"no size fits {text!r} on the orb")


def label_on(img: Image.Image, text: str, slope: float, inter: float) -> None:
    """Print the channel's number, cut into the surface rather than onto it."""
    px, track, top = largest_fit(text, slope, inter)
    big = SIZE * SUPERSAMPLE
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = ImageFont.truetype(FONT_PATH, px * SUPERSAMPLE)
    step = track * SUPERSAMPLE
    box = draw.textbbox((0, 0), text, font=font)
    run = (sum(draw.textlength(c, font=font) for c in text)
           + step * (len(text) - 1))
    x0 = (big - run) / 2
    y0 = top * SUPERSAMPLE - box[1]
    size = px * SUPERSAMPLE
    for dx, dy, colour in ((-size * EMBOSS_OFFSET, -size * EMBOSS_DROP, EMBOSS_LIGHT),
                           (size * EMBOSS_OFFSET, size * EMBOSS_DROP, EMBOSS_DARK)):
        x = x0
        for ch in text:
            draw.text((x + dx, y0 + dy), ch, font=font, fill=colour)
            x += draw.textlength(ch, font=font) + step
    x = x0
    for ch in text:
        draw.text((x, y0), ch, font=font, fill=INK)
        x += draw.textlength(ch, font=font) + step
    flat = layer.resize((SIZE, SIZE), Image.LANCZOS)

    shade = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shade.paste(Image.new("RGBA", (SIZE, SIZE), DROP_SHADOW), (0, 0), flat)
    img.alpha_composite(
        shade.filter(ImageFilter.GaussianBlur(SIZE * SHADOW_BLUR))
             .transform((SIZE, SIZE), Image.AFFINE,
                        (1, 0, -SIZE * SHADOW_SHIFT, 0, 1, -SIZE * SHADOW_DROP)))
    img.alpha_composite(flat)


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
    alpha = orb.getchannel("A")
    slope, inter = band_line(orb)

    tallest = 0
    for stem, label in SPECS:
        path = os.path.join(OUT_DIR, f"{stem}.png")
        img = orb.copy()
        if label:
            px, _, _ = largest_fit(label, slope, inter)
            tallest = max(tallest, px)
            label_on(img, label, slope, inter)
            img.putalpha(ImageChops.darker(img.getchannel("A"), alpha))
        save(img, path)
        print(f"  {path:28} {label or '(orb as supplied)'}")

    print(f"\nprinted {len(SPECS)} marks  ·  band edge y = {slope:.4f}x + "
          f"{inter:.1f}  ·  largest face {tallest}px, capped at "
          f"{int(SIZE * BEIN_CAP)}px of letter height")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
