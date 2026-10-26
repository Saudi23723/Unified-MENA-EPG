#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the multi-sport games channel's mark — a medal on the dashboard tile.

The tile, the glow and the two names are make_today_matches_logo.py's own
drawing, borrowed whole, so this channel sits in a player's list beside
the four guides it was split from and looks like one of them. Only the
emblem is new: a medal on its ribbon, because the channel is the Games —
the Olympics, the Asian Games and the rest — and a medal is what all of
them are held for. No federation's rings or emblem are drawn.

    python make_multi_sport_logo.py

Writes logos/multi_sport.png — one 512x512 transparent PNG.
"""
from __future__ import annotations

from PIL import ImageDraw

import make_today_matches_logo as tile

OUT = "logos/multi_sport.png"
NAME_AR = "الألعاب الكبرى"
NAME_EN = "MULTI-SPORT GAMES"
TOP, BOTTOM = (40, 22, 52, 255), (9, 5, 13, 255)
ACCENT = (255, 196, 64, 255)


def draw_medal(pen: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
               stroke: int, accent) -> None:
    """A medal on a ribbon, with a star struck in its face."""
    disc_r = r * 7 // 10
    disc_cy = cy + r * 2 // 5
    # The ribbon: two bands meeting behind the medal.
    top = cy - r * 6 // 5
    for side in (-1, 1):
        outer = cx + side * r * 3 // 4
        inner = cx + side * r // 6
        pen.polygon([(outer, top), (outer - side * r // 3, top),
                     (inner - side * r // 8, disc_cy - disc_r // 2),
                     (inner + side * r // 5, disc_cy - disc_r // 3)],
                    fill=(200, 40, 70, 255) if side < 0 else (40, 90, 200, 255))
    # The medal itself, ringed.
    pen.ellipse([cx - disc_r, disc_cy - disc_r, cx + disc_r, disc_cy + disc_r],
                fill=accent)
    pen.ellipse([cx - disc_r, disc_cy - disc_r, cx + disc_r, disc_cy + disc_r],
                outline=tile.WHITE, width=stroke)
    # The star.
    import math
    points = []
    for n in range(10):
        angle = -math.pi / 2 + n * math.pi / 5
        radius = disc_r * (0.55 if n % 2 == 0 else 0.23)
        points.append((cx + radius * math.cos(angle),
                       disc_cy + radius * math.sin(angle)))
    pen.polygon(points, fill=tile.WHITE)


def main() -> None:
    tile.refuse_without_shaping(NAME_AR)
    tile.EMBLEMS[OUT] = draw_medal
    tile.draw(OUT, NAME_AR, NAME_EN, TOP, BOTTOM, ACCENT).save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
