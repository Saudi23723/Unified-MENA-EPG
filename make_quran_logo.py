#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The channel's logo, drawn in its own theme rather than fetched.

Same reasoning as the other make_*_logo files here: a picture this
repository draws is a picture nobody outside can take away, and it
comes out byte for byte the same on every machine that draws it.
"""
import math

from PIL import Image, ImageDraw

from nur_theme import GOLD, GOLD_DIM, INK, TOP, WHITE, face, SANS_HEAVY

SIZE = 512


def main() -> None:
    logo = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    pen = ImageDraw.Draw(logo)
    pen.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=96, fill=TOP)
    for y in range(SIZE):
        share = (y / (SIZE - 1)) ** 1.4
        row = tuple(int(round(TOP[i] + (INK[i] - TOP[i]) * share))
                    for i in range(3)) + (255,)
        pen.line([(60, y), (SIZE - 60, y)], fill=row)
    pen.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=96,
                          outline=GOLD_DIM, width=6)

    # The eight-point star the boards' lattice is made of, once, large.
    cx = cy = SIZE // 2
    outer, inner = SIZE * 0.34, SIZE * 0.145
    points = []
    for n in range(16):
        turn = n * math.pi / 8 - math.pi / 2
        reach = outer if n % 2 == 0 else inner
        points.append((cx + reach * math.cos(turn),
                       cy + reach * math.sin(turn)))
    pen.polygon(points, outline=GOLD, width=7)

    pen.text((cx, cy + 6), "و", font=face(SANS_HEAVY, 150), fill=WHITE,
             anchor="mm", direction="rtl", language="ar")
    logo.save("logos/today_quran.png")
    print("  drew logos/today_quran.png")


if __name__ == "__main__":
    main()
