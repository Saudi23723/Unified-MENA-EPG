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
# Outfit Bold, not the Arabic face the rest of the repo uses: every plate
# here is Latin ("HD 1 Ar", "MAX 1", "XTRA 1"), and Outfit's wider counters
# stay open when a television scales the icon down. A plate that ever needs
# Arabic would have to come back to fonts/Tajawal-*.ttf, which has it.
FONT_PATH = os.path.join("fonts", "Outfit-Bold.ttf")

SIZE = 512

# Where the wordmark and the plate sit, as fractions of the canvas. The
# plate is given the lower, wider part of the ball because its text is the
# information — which channel this is — while the wordmark only has to be
# recognisable as beIN.
MARK_HEIGHT = .30
MARK_TOP = .195
PLATE_CENTRE = .690
PLATE_INSET = .88      # keep the tab off the curve of the ball
PLATE_MAX_H = .26

# Extra space between the plate's letters, as a fraction of the font size.
# Outfit sets "HD 1 Ar" tight enough that the 1 and the A touch once the
# icon is scaled down, and two letters that merge cost more legibility than
# the width this spends.
PLATE_TRACKING = .05

# Where the wordmark sits on the one channel that carries no plate: the
# middle, because nothing is sharing the ball with it.
MARK_TOP_ALONE = .36

# The ball is shaded between these three, lit from the upper left, which
# is where the light sits in the photograph.
SHADOW = (58, 22, 92)
BODY = (92, 45, 145)
LIT = (140, 92, 200)
PLATE_INK = (74, 28, 116)

# Gold is not the purple ramp with the hue moved. Metal does not shade
# linearly: it runs dark, flares to a narrow bright band and falls away
# again, so it needs stops rather than two ends. A straight dark-to-light
# lerp in gold reads as plastic.
GOLD_STOPS = [(52, 32, 4), (120, 80, 14), (176, 128, 36),
              (236, 196, 96), (255, 243, 200), (214, 168, 66)]
GOLD_INK = (245, 214, 120)
GOLD_RING = (222, 184, 86)

# The wordmark goes DARK on gold, not white. White on light metal has
# almost no contrast, and at the 64px a set-top box actually draws a
# channel icon it collapses into a pale smudge — measured against four
# other treatments before this one was chosen. Purple on gold is both the
# legible pairing and the brand's own.
GOLD_MARK_INK = (58, 22, 92)

# How a channel is dressed.
PURPLE = "purple"      # the plain bubble
GOLD = "gold"          # the whole ball in metal
RINGED = "ringed"      # the plain bubble inside a gold band

# (logo file stem, what its plate reads, how it is dressed)
#
# The nine Arabic channels carry the BARE number, which is how beIN names
# them: they are the default, and everything else is a named variant. It
# started as "HD 1 Ar" after the owner's set-top box, and the suffix was
# dropped because it said nothing the icon did not already say — the
# English feeds carry their own "EN 1", so a bare number can only be the
# Arabic channel, and no other plate in the roster is a bare number. The
# room that bought goes to the digit, which is what a reader is looking
# for. Every other family is named the way beIN names it.
#
# An EMPTY label means no plate at all, and only the unnumbered brand
# channel takes it. A plate reading "Ar" there claimed a distinction that
# does not exist; having no plate is itself the distinction, and it is the
# one channel that has no number or sub-name to print.
#
# The dress is what tells the families apart in a long channel list, and
# it is deliberately coarse: gold for the nine Arabic channels and the two
# 4K feeds, a gold band for MAX, and the plain bubble for everything else.
# Marking more than that would mark nothing — a list where every icon is
# gold distinguishes no channel from another.
SPECS = [
    ("bein_1", "1", GOLD),
    ("bein_2", "2", GOLD),
    ("bein_3", "3", GOLD),
    ("bein_4", "4", GOLD),
    ("bein_5", "5", GOLD),
    ("bein_6", "6", GOLD),
    ("bein_7", "7", GOLD),
    ("bein_8", "8", GOLD),
    ("bein_9", "9", GOLD),

    ("bein_xtra1", "XTRA 1", PURPLE),
    ("bein_xtra2", "XTRA 2", PURPLE),
    ("bein_xtra3", "XTRA 3", PURPLE),
    ("bein_xtra4", "XTRA 4", PURPLE),
    ("bein_xtra5", "XTRA 5", PURPLE),
    ("bein_xtra6", "XTRA 6", PURPLE),
    ("bein_xtra7", "XTRA 7", PURPLE),
    ("bein_xtra8", "XTRA 8", PURPLE),
    ("bein_xtra9", "XTRA 9", PURPLE),

    ("bein_max1", "MAX 1", RINGED),
    ("bein_max2", "MAX 2", RINGED),
    ("bein_max3", "MAX 3", RINGED),
    ("bein_max4", "MAX 4", RINGED),
    ("bein_max5", "MAX 5", RINGED),
    ("bein_max6", "MAX 6", RINGED),

    ("bein_afc", "AFC", PURPLE),
    ("bein_afc1", "AFC 1", PURPLE),
    ("bein_afc2", "AFC 2", PURPLE),
    ("bein_afc3", "AFC 3", PURPLE),
    ("bein_afc4", "AFC 4", PURPLE),
    ("bein_afc5", "AFC 5", PURPLE),
    ("bein_afc6", "AFC 6", PURPLE),

    ("bein_en1", "EN 1", PURPLE),
    ("bein_en2", "EN 2", PURPLE),
    ("bein_fr1", "FR 1", PURPLE),
    ("bein_fr2", "FR 2", PURPLE),

    ("bein_brand", "", GOLD),
    ("bein_4k", "4K", GOLD),
    ("bein_4khdr", "4K HDR", GOLD),
    ("bein_nba", "NBA", PURPLE),
    ("bein_news", "NEWS", PURPLE),
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


def metal_ball(size: int, stops: list[tuple[int, int, int]],
               gamma: float = 1.05) -> Image.Image:
    """Shade a sphere through a list of colour stops rather than two ends.

    Same geometry as ball(); only the mapping from the light term to a
    colour differs. See GOLD_STOPS for why metal needs the extra stops.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    r = size / 2.0
    lx, ly, lz = -0.45, -0.55, 0.70
    last = len(stops) - 1
    for y in range(size):
        for x in range(size):
            dx, dy = (x - r + .5) / r, (y - r + .5) / r
            d2 = dx * dx + dy * dy
            if d2 > 1.0:
                continue
            dz = math.sqrt(max(0.0, 1.0 - d2))
            t = min(0.99999, max(0.0, dx * lx + dy * ly + dz * lz) ** gamma) * last
            i = int(t)
            frac = t - i
            a, b = stops[i], stops[i + 1]
            col = [a[k] + (b[k] - a[k]) * frac for k in range(3)]
            alpha = 255 if d2 < .965 else int(255 * (1 - (d2 - .965) / .035))
            px[x, y] = (int(col[0]), int(col[1]), int(col[2]), max(0, alpha))
    return img


def band(size: int, width_frac: float = .055) -> Image.Image:
    """The gold band that marks a MAX channel.

    A band rather than a tinted plate or wordmark: at icon size only a
    change to the OUTLINE carries. Anything inside the disc is too small
    to see.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    w = size * width_frac
    ImageDraw.Draw(img).ellipse(
        [w / 2, w / 2, size - 1 - w / 2, size - 1 - w / 2],
        outline=GOLD_RING + (255,), width=int(w))
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


def wordmark(height: int, ink: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """bein_wordmark.png recoloured to a solid ink, keeping its own alpha.

    The file on disk is the purple gradient mark. Only its alpha carries
    the letterforms, so replacing the colour channels wholesale is exact,
    where a per-pixel recolour would leave the antialiasing purple.
    """
    src = Image.open(WORDMARK).convert("RGBA")
    src = src.resize((int(src.width * height / src.height), height), Image.LANCZOS)
    flat = Image.new("RGBA", src.size, ink + (255,))
    flat.putalpha(src.getchannel("A"))
    return flat


def chord(centre_frac: float, size: int) -> float:
    """How wide the ball is at a given height, in pixels."""
    r = size / 2.0
    dy = centre_frac * size - r
    return 2 * math.sqrt(max(0.0, r * r - dy * dy))


def tracked(draw: ImageDraw.ImageDraw, text: str,
            font: ImageFont.FreeTypeFont, track: float) -> float:
    """Width of the text once the letters are spaced apart."""
    return sum(draw.textlength(c, font=font) for c in text) + track * (len(text) - 1)


def plate(text: str, size: int,
          fill: tuple[int, int, int] = (255, 255, 255),
          ink: tuple[int, int, int] = PLATE_INK,
          opacity: int = 240) -> Image.Image:
    """The tab naming the channel, set as large as the ball will allow.

    The font is NOT a fixed size. A plate sized for the canvas is unreadable
    on a television: at 48px on this 512px canvas the label came out SIX
    pixels tall once a set-top box scaled the icon down to its channel list,
    which is where the owner photographed it and could not read it.

    So the size is chosen per label instead — the widest the ball is at the
    plate's height, less an inset to stay inside the curve, then the largest
    font whose text fits that. A short label like "4K" gets a bigger face
    than "4K HDR" automatically, and every plate is as legible as its own
    text allows.
    """
    usable = chord(PLATE_CENTRE, size) * PLATE_INSET
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for px in range(int(size * .34), 10, -1):
        font = ImageFont.truetype(FONT_PATH, px)
        track = px * PLATE_TRACKING
        box = probe.textbbox((0, 0), text, font=font)
        text_w = tracked(probe, text, font, track)
        width = text_w + px * .34 * 2
        height = (box[3] - box[1]) + px * .30 * 2
        if width <= usable and height <= size * PLATE_MAX_H:
            break
    width, height = int(width), int(height)
    tab = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(tab)
    d.rounded_rectangle([0, 0, width - 1, height - 1],
                        radius=height * .24, fill=fill + (opacity,))
    x = (width - text_w) / 2
    y = (height - (box[3] - box[1])) / 2 - box[1]
    for ch in text:
        d.text((x, y), ch, font=font, fill=ink)
        x += d.textlength(ch, font=font) + track
    return tab


def bubble(label: str, sphere: Image.Image, cap: Image.Image,
           mark: Image.Image, tab: Image.Image | None,
           ring: Image.Image | None = None) -> Image.Image:
    img = sphere.copy()
    img.alpha_composite(cap)
    if ring is not None:
        img.alpha_composite(ring)
    top = MARK_TOP if tab is not None else MARK_TOP_ALONE
    img.alpha_composite(mark, ((SIZE - mark.width) // 2, int(SIZE * top)))
    if tab is not None:
        img.alpha_composite(tab, ((SIZE - tab.width) // 2,
                                  int(SIZE * PLATE_CENTRE - tab.height / 2)))
    # A long plate would otherwise hang over the edge of the ball.
    img.putalpha(Image.composite(img.getchannel("A"),
                                 Image.new("L", (SIZE, SIZE), 0),
                                 sphere.getchannel("A")))
    return img


def fit(mark: Image.Image) -> Image.Image:
    """Keep the wordmark inside the ball's usable width."""
    if mark.width <= SIZE * .66:
        return mark
    return mark.resize((int(SIZE * .66), int(mark.height * SIZE * .66 / mark.width)),
                       Image.LANCZOS)


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    cap = gloss(SIZE)

    # Both spheres and the band are drawn once and shared; only the plate
    # differs per channel.
    purple_ball = ball(SIZE)
    gold_ball = metal_ball(SIZE, GOLD_STOPS)
    ring = band(SIZE)

    white_mark = fit(wordmark(int(SIZE * MARK_HEIGHT)))
    dark_mark = fit(wordmark(int(SIZE * MARK_HEIGHT), GOLD_MARK_INK))

    drawn = {PURPLE: 0, GOLD: 0, RINGED: 0}
    for stem, label, style in SPECS:
        if style == GOLD:
            sphere, mark, ring_arg = gold_ball, dark_mark, None
            tab = plate(label, SIZE, fill=GOLD_MARK_INK, ink=GOLD_INK,
                        opacity=245) if label else None
        elif style == RINGED:
            sphere, mark, ring_arg = purple_ball, white_mark, ring
            tab = plate(label, SIZE) if label else None
        else:
            sphere, mark, ring_arg = purple_ball, white_mark, None
            tab = plate(label, SIZE) if label else None

        path = os.path.join(OUT_DIR, f"{stem}.png")
        bubble(label, sphere, cap, mark, tab, ring_arg).save(
            path, "PNG", optimize=True)
        drawn[style] += 1
        print(f"  {path:28} {label or '(no plate)':10} {style}")

    print(f"\ndrew {len(SPECS)} marks: "
          f"{drawn[GOLD]} gold, {drawn[RINGED]} ringed, {drawn[PURPLE]} plain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
