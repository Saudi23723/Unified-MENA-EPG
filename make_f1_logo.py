#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the Formula 1 channel's mark — a chequered flag on the dashboard tile.

The tile, the glow and the two names are make_today_matches_logo.py's own
drawing, borrowed whole, so this channel sits in a player's list beside
the guides around it and looks like one of them. Only the emblem is new:
the chequered flag, which every race ends under. No series logo is drawn.

    python make_f1_logo.py

Writes logos/f1.png — one 512x512 transparent PNG.
"""
from __future__ import annotations

from PIL import ImageDraw

import make_today_matches_logo as tile

OUT = "logos/f1.png"
NAME_AR = "الفورمولا 1"
NAME_EN = "FORMULA 1"
TOP, BOTTOM = (58, 10, 14, 255), (14, 3, 5, 255)
ACCENT = (232, 0, 45, 255)


def draw_flag(pen: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
              stroke: int, accent) -> None:
    """A chequered flag on its pole, five squares by four."""
    cols, rows = 5, 4
    cell = (r * 2) // cols
    left = cx - cell * cols // 2 + stroke
    top = cy - cell * rows // 2 - stroke
    # The pole, in the channel's red.
    pen.rectangle([left - stroke * 2, top - stroke,
                   left - stroke // 2, top + cell * rows + r // 2],
                  fill=accent)
    for row in range(rows):
        for col in range(cols):
            colour = tile.WHITE if (row + col) % 2 == 0 else (16, 16, 20, 255)
            x = left + col * cell
            # A gentle wave: each column sits a little lower than the last.
            y = top + row * cell + (col % 2) * (cell // 6)
            pen.rectangle([x, y, x + cell, y + cell], fill=colour)
    pen.rectangle([left, top, left + cell * cols, top + cell * rows + cell // 6],
                  outline=tile.WHITE, width=max(2, stroke // 2))


def main() -> None:
    tile.refuse_without_shaping(NAME_AR)
    tile.EMBLEMS[OUT] = draw_flag
    tile.draw(OUT, NAME_AR, NAME_EN, TOP, BOTTOM, ACCENT).save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
