#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reframe Alwan's mark so it reads at the size a TV gives it.

The owner supplied logos/alwan_src.png himself, and it is kept exactly as
he sent it — this script never writes to it. But as an icon it was the
weakest of the set, for two reasons that were measured rather than felt:

  THE MARK WAS SMALL INSIDE ITS FRAME. Against the 512 canvas the artwork
  spans x 81-431 and y 178-335, so it fills 69% of the width and 31% of
  the height and the rest is black padding. At the 72px a set-top box
  gives an icon that is a black square with a green smudge in it.

  THE SQUARE WAS CUT HARD. Not one pixel of its alpha was between 0 and
  255, so it had neither rounded corners nor a softened edge, while every
  tile beside it — ball_sports, today_matches, f1, other_sports — is a
  rounded tile of radius 118. It was the only sharp square in the row.

So the mark is lifted off its ground, enlarged to fill the tile, and set
back on black with that same corner. Nothing about the artwork itself is
redrawn: the ground is (1, 1, 1), so a pixel's brightness IS its coverage,
and lifting it to alpha keeps the green circles and the white lettering
with the soft edges they were drawn with.

    python make_alwan_logo.py

Writes logos/alwan.png, the file update_alwan_epg.py points every channel
at. fetch_logos.py does not list this key, so a run of it cannot reach
either file.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

SRC = "logos/alwan_src.png"
OUT = "logos/alwan.png"

SIZE = 512
SUPERSAMPLE = 3                # the corner is a curve; draw big, shrink
RADIUS = 118                   # what ball_sports and today_matches use

# The artwork's own box inside the supplied canvas, measured not guessed.
MARK_BOX = (81, 178, 432, 336)

# Its ground is (1, 1, 1). Everything under FLOOR is ground; everything
# over FLOOR + RAMP is solid mark; between them is the edge the artwork
# was drawn with, and that is what keeps the circles from stairstepping.
FLOOR = 8
RAMP = 60

GROUND = (8, 8, 10)
PAD = .075                     # air between the mark and the tile's edge
COLOURS = 256


def tile_mask() -> Image.Image:
    """The rounded square, drawn at SUPERSAMPLE so its corner is smooth."""
    big = SIZE * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big - 1, big - 1], radius=RADIUS * SUPERSAMPLE, fill=255)
    return mask.resize((SIZE, SIZE), Image.LANCZOS)


def lift(src: Image.Image) -> Image.Image:
    """The mark alone, its brightness read back as its alpha."""
    crop = src.crop(MARK_BOX).convert("RGB")
    alpha = crop.convert("L").point(
        lambda v: 0 if v < FLOOR else min(255, int((v - FLOOR) * 255 / RAMP)))
    mark = crop.convert("RGBA")
    mark.putalpha(alpha)
    return mark


def save(img: Image.Image, path: str) -> None:
    """Palette the colour, keep the 8-bit alpha, as the beIN set does."""
    alpha = img.getchannel("A")
    flat = img.convert("RGB").quantize(
        colors=COLOURS, method=Image.FASTOCTREE,
        dither=Image.FLOYDSTEINBERG).convert("RGB").convert("RGBA")
    flat.putalpha(alpha)
    flat.save(path, "PNG", optimize=True)


def main() -> int:
    src = Image.open(SRC).convert("RGBA")
    if src.size != (SIZE, SIZE):
        src = src.resize((SIZE, SIZE), Image.LANCZOS)
    mark = lift(src)

    width = int(SIZE * (1 - 2 * PAD))
    height = round(mark.height * width / mark.width)
    img = Image.new("RGBA", (SIZE, SIZE), GROUND + (255,))
    img.alpha_composite(mark.resize((width, height), Image.LANCZOS),
                        ((SIZE - width) // 2, (SIZE - height) // 2))
    img.putalpha(tile_mask())
    save(img, OUT)

    print(f"  {OUT}  mark {width}x{height} on a {RADIUS}px corner  ·  "
          f"was {MARK_BOX[2] - MARK_BOX[0]}x{MARK_BOX[3] - MARK_BOX[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
