#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Formula 1 channel's logo, drawn rather than borrowed.

NOT THE SPORT'S OWN MARK. That one is a trademark and not this
project's to publish, so this is the channel's own: the chequered flag
every viewer already reads as motor racing, put on the dark ground the
rest of the service uses, with the speed streaks that say which
direction the thing is going.

Drawn at four times the size and brought down, because a chequer is
nothing but edges and edges are what scaling ruins.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

SIDE = 1024
OVER = 4
GROUND = (13, 17, 28, 255)
RED = (225, 6, 0, 255)
WHITE = (242, 246, 251, 255)
DARK = (30, 36, 50, 255)


def draw() -> Image.Image:
    big = SIDE * OVER
    art = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    pen = ImageDraw.Draw(art)

    pad = int(big * 0.055)
    radius = int(big * 0.20)
    pen.rounded_rectangle([pad, pad, big - pad, big - pad],
                          radius=radius, fill=GROUND)

    # EVERYTHING INSIDE IS CLIPPED TO THE TILE. The chequer is set on the
    # diagonal, and a rotated square does not respect a rounded corner —
    # drawn straight onto the art it hung off two sides of the logo. So
    # the marks go on their own layer and the tile's own shape is the
    # mask, which is the only way a corner stays a corner.
    inside = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    on_inside = ImageDraw.Draw(inside)
    shape = Image.new("L", (big, big), 0)
    ImageDraw.Draw(shape).rounded_rectangle(
        [pad, pad, big - pad, big - pad], radius=radius, fill=255)

    # THE STREAKS FIRST, because everything else sits on them. Three
    # bars running off the left edge, each shorter than the one above:
    # the shape a thing leaves behind it rather than a drawing of speed.
    top = int(big * 0.30)
    for index, (width, length) in enumerate(((0.052, 0.40),
                                             (0.052, 0.30),
                                             (0.052, 0.21))):
        y = top + int(index * big * 0.085)
        on_inside.rounded_rectangle(
            [int(big * 0.13), y, int(big * (0.13 + length)),
             y + int(big * width)],
            radius=int(big * width / 2), fill=RED)

    # THE CHEQUER, set on the diagonal so it reads as a flag rather than
    # a chessboard. Eight squares across, drawn into its own layer and
    # turned, so the rotation cannot soften the squares' own edges.
    cell = int(big * 0.062)
    across = 6
    flag = Image.new("RGBA", (cell * across, cell * across), (0, 0, 0, 0))
    on_flag = ImageDraw.Draw(flag)
    for row in range(across):
        for col in range(across):
            tone = WHITE if (row + col) % 2 == 0 else DARK
            on_flag.rectangle([col * cell, row * cell,
                               (col + 1) * cell, (row + 1) * cell], fill=tone)
    flag = flag.rotate(-18, resample=Image.BICUBIC, expand=True)
    inside.alpha_composite(flag, (int(big * 0.50), int(big * 0.22)))
    art.paste(inside, (0, 0), Image.composite(
        inside.getchannel("A"), Image.new("L", (big, big), 0), shape))

    # AND THE NAME, in the one place a logo can carry words: along the
    # foot, where it is read after the mark and not instead of it.
    from match_board import draw_text
    draw_text(pen, (big // 2, int(big * 0.80)), "FORMULA 1",
              int(big * 0.082), WHITE, anchor="mm", weight="heavy")
    pen.rounded_rectangle(
        [int(big * 0.35), int(big * 0.858), int(big * 0.65),
         int(big * 0.872)], radius=int(big * 0.007), fill=RED)
    return art.resize((SIDE, SIDE), Image.LANCZOS)


if __name__ == "__main__":
    import os
    os.makedirs("logos", exist_ok=True)
    art = draw()
    art.save("logos/f1.png", optimize=True)
    print(f"logos/f1.png {art.size} {os.path.getsize('logos/f1.png')//1024} KB")
