#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw the disasters channel's mark — a seismograph trace on the dashboard tile.

The tile, the glow and the two names are make_today_matches_logo.py's own
drawing, borrowed whole, so this channel sits in a player's list beside
the others and looks like one of them. Only the emblem is new: the trace
a seismometer draws when the ground moves, in the alert red the channel's
board wears, with a warning triangle above it.

    python make_world_disasters_logo.py

Writes logos/world_disasters.png — one 512x512 transparent PNG.
"""
from __future__ import annotations

from PIL import ImageDraw

import make_today_matches_logo as tile

OUT = "logos/world_disasters.png"
NAME_AR = "كوارث العالم"
NAME_EN = "WORLD DISASTERS"
TOP, BOTTOM = (58, 16, 14, 255), (12, 4, 4, 255)
ACCENT = (255, 92, 72, 255)


def draw_trace(pen: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
               stroke: int, accent) -> None:
    """A warning triangle, and a seismograph trace across its foot."""
    # The triangle, outlined in the accent.
    top = cy - r
    base = cy + r * 3 // 5
    half = r * 21 // 20
    pen.line([(cx, top), (cx + half, base), (cx - half, base), (cx, top)],
             fill=accent, width=stroke, joint="curve")
    # The exclamation inside it.
    pen.line([(cx, top + r * 2 // 5), (cx, base - r * 2 // 5)],
             fill=tile.WHITE, width=stroke)
    dot = stroke * 3 // 4
    pen.ellipse([cx - dot, base - r // 4 - dot, cx + dot, base - r // 4 + dot],
                fill=tile.WHITE)
    # The trace, running the width of the emblem beneath.
    line_y = base + r * 2 // 5
    left, right = cx - r * 3 // 2, cx + r * 3 // 2
    step = (right - left) / 12
    heights = (0, 0, 0.08, -0.12, 0.3, -0.42, 0.36, -0.2, 0.12, -0.05, 0, 0, 0)
    points = [(left + step * i, line_y - h * r) for i, h in enumerate(heights)]
    pen.line(points, fill=tile.WHITE, width=max(3, stroke * 2 // 3),
             joint="curve")


def main() -> None:
    tile.refuse_without_shaping(NAME_AR)
    tile.EMBLEMS[OUT] = draw_trace
    tile.draw(OUT, NAME_AR, NAME_EN, TOP, BOTTOM, ACCENT).save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
