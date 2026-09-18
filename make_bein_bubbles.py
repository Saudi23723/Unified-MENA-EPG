#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the beIN SPORTS Qatar channel marks as a dark tile.

The repo owner photographed his set-top box and could not read a single
one of these icons. That photograph is what this file is answering, and
answering it twice over: first the label was sized to the art, then the
art itself was replaced.

WHY NOT THE GLOSSY BUBBLE. These were a lit sphere with a highlight, the
mark his box happens to ship. That style prices legibility for gloss: a
sphere fills 79% of the square it is given and narrows sharply towards the
bottom, which is exactly where the channel's own name has to go, and its
highlight spends contrast on light that carries no information. Measured
at 72px — the size a television actually gives a channel icon — the tile
below reads at a glance where the bubble had to be squinted at.

WHY DARK. The colour does not fill the tile any more; it rides the edge.
White on a dark field beats purple on purple, and a dark icon sits inside
a set-top box's own dark interface instead of being pasted on top of it.
The base is NOT neutral black, though: it is beIN's purple held down to
icon luminance, so all forty still read as one brand rather than as forty
dark squares.

WHAT THE EDGE MEANS, and it is deliberately coarse, because marking more
than this would mark nothing:

    gold edge                  beIN SPORTS 1-9, 4K, 4K HDR, the brand feed
    purple edge, gold ring     beIN SPORTS MAX 1-6
    purple edge                XTRA, AFC, EN, FR, NBA, NEWS

The edge glows inward before it is drawn. That is not decoration: the
bloom lifts the field just inside the border, which separates the icon
from whatever dark background sits behind it, while the centre — where
the text is — stays at the darkest point.

None of this is a beIN asset. The public logo databases carry only the
flat wordmark, so the tile is drawn here over the official wordmark this
repository already holds. Drawing it is what fixes the eleven channels
that were wearing another channel's mark: beIN SPORTS 9 and AFC 4-6
showed an unnumbered brand logo, and XTRA 3-9 all showed the words
"XTRA 1", because the upstream database has no separate picture for any
of them. A drawn label always says the channel it belongs to.

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
second run would otherwise draw a tile on top of a tile.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = "logos"
WORDMARK = os.path.join(OUT_DIR, "bein_wordmark.png")
# Outfit Bold, not the Arabic face the rest of the repo uses: every label
# here is Latin ("1", "MAX 1", "XTRA 1"), and Outfit's wider counters stay
# open when a television scales the icon down. A label that ever needs
# Arabic would have to come back to fonts/Tajawal-*.ttf, which has it.
FONT_PATH = os.path.join("fonts", "Outfit-Bold.ttf")

SIZE = 512
CORNER = .26           # the tile's own corner, as a fraction of its side

# The field. NOT neutral black: this is beIN's purple held down to icon
# luminance, top lighter than bottom. The hue is what keeps forty of these
# reading as one brand instead of forty dark squares, and the darkness is
# what lets white text sit on it at full contrast.
FIELD_TOP = (58, 34, 84)
FIELD_BOTTOM = (24, 12, 38)

# The edge carries the family. Both are lifted well clear of the field so
# they survive being scaled down to a channel list.
EDGE_GOLD = (232, 193, 106)
EDGE_PURPLE = (150, 92, 214)
# MAX keeps a gold ring inside its purple edge — the same thing its gold
# band said on the old bubble, said the same way: purple for beIN, gold
# for premium, and MAX is both.
RING_GOLD = EDGE_GOLD

EDGE_INSET = .035      # how far the edge sits in from the tile
EDGE_WIDTH = .030
EDGE_RADIUS = .22
BLOOM_WIDTH = .050     # the same edge, wider and blurred, laid down first
BLOOM_ALPHA = 210
BLOOM_BLUR = .075
RING_INSET = .105
RING_WIDTH = .016
RING_RADIUS = .18

INK = (247, 245, 251)  # everything printed on the field

# The wordmark shares the tile with the label, so it is given a size that
# reads without crowding the thing a viewer is actually looking for. On
# the one channel with no label it takes the middle of the tile instead.
MARK_HEIGHT = .19
MARK_TOP = .175
MARK_MAX_W = .62
MARK_HEIGHT_ALONE = .30
MARK_TOP_ALONE = .355
MARK_MAX_W_ALONE = .70

# The label is not set at a fixed size. A fixed size is what made the old
# icons unreadable: at 48px on this 512px canvas the text stood six pixels
# tall once a set-top box scaled the icon down. Instead the largest face
# that fits the box below is chosen per label, so "4K" comes out bigger
# than "4K HDR" without anyone choosing it.
LABEL_CENTRE = .655
LABEL_MAX_W = .70
LABEL_MAX_H = .37
LABEL_TRACKING = .02   # Outfit sets "4K HDR" tight enough to merge at size

# How a channel is dressed.
PURPLE = "purple"      # the plain tile
GOLD = "gold"          # a gold edge
RINGED = "ringed"      # a purple edge with a gold ring inside it

# (logo file stem, what its label reads, how it is dressed)
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
# An EMPTY label means no label at all, and only the unnumbered brand
# channel takes it. One reading "Ar" there claimed a distinction that
# does not exist; carrying none is itself the distinction, and it is the
# one channel that has no number or sub-name to print.
#
# The dress is what tells the families apart in a long channel list, and
# it is deliberately coarse: a gold edge for the nine Arabic channels and
# the two 4K feeds, a gold ring inside a purple edge for MAX, and the
# plain tile for everything else.
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


def _gradient(size: int, top: tuple[int, int, int],
              bottom: tuple[int, int, int]) -> Image.Image:
    """A vertical ramp, one row computed then stretched across."""
    strip = Image.new("RGB", (1, size))
    px = strip.load()
    for y in range(size):
        t = y / (size - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return strip.resize((size, size), Image.NEAREST).convert("RGBA")


def tile_mask(size: int, radius: float = CORNER) -> Image.Image:
    """The tile's silhouette, used both to cut it out and to clip onto it."""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius), fill=255)
    return mask


def field(size: int) -> Image.Image:
    """The tile itself, before anything is drawn on it.

    A film of noise used to go on here, to stop the gradient banding on a
    cheap panel. It was removed after measuring: the ramp is shallow
    enough not to band without it, the three versions were
    indistinguishable at full size, and the noise was costing 148 KB of
    every 187 KB icon — PNG cannot compress it. The forty now weigh 1.6 MB
    where the glossy bubbles weighed 4.6 MB.
    """
    base = _gradient(size, FIELD_TOP, FIELD_BOTTOM)
    base.putalpha(tile_mask(size))
    return base


def outline(size: int, colour: tuple[int, int, int], inset: float,
            width: float, radius: float, alpha: int = 255) -> Image.Image:
    """A rounded rectangle stroke on its own transparent layer."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        [size * inset, size * inset, size - size * inset, size - size * inset],
        radius=size * radius, outline=colour + (alpha,), width=int(size * width))
    return layer


def onto(img: Image.Image, layer: Image.Image, mask: Image.Image) -> None:
    """Composite a layer but let nothing of it spill past the tile."""
    img.alpha_composite(Image.composite(
        layer, Image.new("RGBA", img.size, (0, 0, 0, 0)), mask))


def edge(img: Image.Image, colour: tuple[int, int, int],
         mask: Image.Image) -> None:
    """The family's edge: a blurred copy first, then the crisp stroke.

    The bloom is not decoration. It lifts the field just inside the border,
    which is what separates the icon from a dark background behind it,
    while the centre stays at its darkest under the text.
    """
    size = img.width
    onto(img, outline(size, colour, EDGE_INSET, BLOOM_WIDTH, EDGE_RADIUS,
                      BLOOM_ALPHA).filter(
                          ImageFilter.GaussianBlur(size * BLOOM_BLUR)), mask)
    onto(img, outline(size, colour, EDGE_INSET, EDGE_WIDTH, EDGE_RADIUS), mask)


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


def fit(mark: Image.Image, max_w: float) -> Image.Image:
    """Hold the wordmark inside its share of the tile."""
    if mark.width <= SIZE * max_w:
        return mark
    return mark.resize((int(SIZE * max_w),
                        int(mark.height * SIZE * max_w / mark.width)),
                       Image.LANCZOS)


def largest_fit(draw: ImageDraw.ImageDraw, text: str,
                max_w: float, max_h: float):
    """The biggest face whose tracked text still fits the box."""
    for px in range(int(SIZE * .80), 8, -1):
        font = ImageFont.truetype(FONT_PATH, px)
        track = px * LABEL_TRACKING
        width = (sum(draw.textlength(c, font=font) for c in text)
                 + track * (len(text) - 1))
        box = draw.textbbox((0, 0), text, font=font)
        if width <= max_w and (box[3] - box[1]) <= max_h:
            return font, track, width, box
    return font, track, width, box


def label_on(img: Image.Image, text: str) -> None:
    """Print the channel's own name, as large as the tile allows."""
    draw = ImageDraw.Draw(img)
    font, track, width, box = largest_fit(
        draw, text, SIZE * LABEL_MAX_W, SIZE * LABEL_MAX_H)
    x = (SIZE - width) / 2
    y = SIZE * LABEL_CENTRE - (box[3] - box[1]) / 2 - box[1]
    for ch in text:
        draw.text((x, y), ch, font=font, fill=INK)
        x += draw.textlength(ch, font=font) + track


def mark(label: str, style: str, base: Image.Image,
         mask: Image.Image) -> Image.Image:
    """One finished channel icon."""
    img = base.copy()
    edge(img, EDGE_GOLD if style == GOLD else EDGE_PURPLE, mask)
    if style == RINGED:
        onto(img, outline(SIZE, RING_GOLD, RING_INSET, RING_WIDTH,
                          RING_RADIUS), mask)
    if label:
        word = fit(wordmark(int(SIZE * MARK_HEIGHT), INK), MARK_MAX_W)
        img.alpha_composite(word, ((SIZE - word.width) // 2,
                                   int(SIZE * MARK_TOP)))
        label_on(img, label)
    else:
        word = fit(wordmark(int(SIZE * MARK_HEIGHT_ALONE), INK),
                   MARK_MAX_W_ALONE)
        img.alpha_composite(word, ((SIZE - word.width) // 2,
                                   int(SIZE * MARK_TOP_ALONE)))
    return img


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    # The field and the silhouette are identical on all forty, so they are
    # built once; only the edge and the text differ per channel.
    base = field(SIZE)
    mask = tile_mask(SIZE)

    drawn = {PURPLE: 0, GOLD: 0, RINGED: 0}
    for stem, label, style in SPECS:
        path = os.path.join(OUT_DIR, f"{stem}.png")
        mark(label, style, base, mask).save(path, "PNG", optimize=True)
        drawn[style] += 1
        print(f"  {path:28} {label or '(no label)':10} {style}")

    print(f"\ndrew {len(SPECS)} marks: "
          f"{drawn[GOLD]} gold, {drawn[RINGED]} ringed, {drawn[PURPLE]} plain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
