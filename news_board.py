#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw the news board: a headline, a line explaining it, and where from.

The fixtures boards draw a clock, a name and channel pills, and their
row is built around a match that has not started yet — green for coming,
red for played, a lit band for live. A bulletin has none of that. Every
story here has already happened, so "coming" and "played" mean nothing,
and a clock in match-green on all six rows would say something false at
a glance.

So this is its own drawing, and it shares the fixtures board's
primitives rather than copying them: the same faces, the same colours,
the same shrink-before-clip, the same sweep of boards past the end.

What a row says, in the order the eye reads it:

    the hour it was published, muted, because it is context and not a
    countdown
    THE HEADLINE, as large as fits without being cut
    one sentence explaining it, which is the "شرح بسيط" that was asked
    for
    the newsroom, in a pill, because a headline without its source is
    an assertion

The headline keeps its own language. The sources are a mix of Arabic and
English by design and nothing here translates: a translation this
repository invented would be words no newsroom published, which is the
one thing every guide here refuses to do.
"""
from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from match_board import (
    ACCENT, H, INK, MUTED, PAD, PANEL, PILL, PILL_INK, W, WHITE,
    draw_text, font_for, norm_line, size_that_fits,
)

# A fresh story is worth pointing at. Measured against the reader's own
# promise — "ساعة بساعة" — anything inside the hour is what a viewer
# turned the channel on for.
FRESH_MINUTES = 60

REGION_INK = (150, 176, 208, 255)


def draw_mark(pen, x: int, y: int, size: int) -> None:
    """The channel's own mark: a ring with a bulletin bar across it."""
    pen.rounded_rectangle([x, y, x + size, y + size], radius=size // 4,
                          fill=PANEL)
    pad = size // 5
    pen.ellipse([x + pad, y + pad, x + size - pad, y + size - pad],
                outline=ACCENT, width=max(3, size // 12))
    bar = size // 2
    pen.rounded_rectangle(
        [x + pad, y + bar - size // 14, x + size - pad, y + bar + size // 14],
        radius=size // 20, fill=ACCENT)


def draw_board(stories: list[dict], now: datetime, viewer, *,
               title: str, subtitle: str, page: int = 1,
               pages: int = 1) -> Image.Image:
    """One page of the bulletin."""
    board = Image.new("RGBA", (W, H), INK)
    pen = ImageDraw.Draw(board)

    draw_mark(pen, PAD, PAD - 4, 72)
    x = PAD + 72 + 22
    draw_text(pen, (x, PAD - 2), title, 40, WHITE)
    draw_text(pen, (x, PAD + 46), subtitle, 21, MUTED, thin=True)

    right = W - PAD
    # THE HOUR THIS WAS BUILT, not the date. A newspaper carries a date
    # because it is printed once a day; this is rebuilt every few
    # minutes, and the thing a reader needs to know is how old what they
    # are looking at is.
    draw_text(pen, (right, PAD - 2),
              now.astimezone(viewer).strftime("%H:%M"), 30, WHITE,
              anchor="ra")
    draw_text(pen, (right, PAD + 40),
              f"آخر تحديث · {page}/{pages}" if pages > 1 else "آخر تحديث",
              19, MUTED, anchor="ra", thin=True)

    top = PAD + 92
    pen.line([PAD, top, W - PAD, top], fill=(35, 51, 74, 255), width=2)

    if not stories:
        draw_text(pen, (W // 2, H // 2), "لا توجد أخبار الآن", 32, MUTED,
                  anchor="mm")
        return board

    room = H - top - PAD
    height = min(104, room // len(stories))
    y = top + 8

    for index, story in enumerate(stories):
        band = [PAD - 12, y, W - PAD + 12, y + height - 8]
        if index % 2 == 0:
            pen.rounded_rectangle(band, radius=12, fill=PANEL)

        published = story["start"].astimezone(viewer)
        age = (now - story["start"]).total_seconds() / 60
        fresh = age <= FRESH_MINUTES

        # The hour, and the region beneath it: a reader scanning for
        # Jordan should find it without reading a headline first.
        draw_text(pen, (PAD + 4, y + 14), published.strftime("%H:%M"), 23,
                  ACCENT if fresh else MUTED)
        draw_text(pen, (PAD + 4, y + 44), story.get("region_name", ""), 16,
                  REGION_INK, thin=True)

        head_x = PAD + 108
        room_for_head = W - PAD - head_x - 12

        headline = norm_line(story["title"])
        size = size_that_fits(headline, 27, 19, room_for_head)
        draw_text(pen, (head_x, y + 10), headline, size, WHITE)

        # The explanation, which is the whole point of the second line.
        beneath = norm_line(story.get("summary"))
        if beneath and height >= 78:
            under = size_that_fits(beneath, 17, 14, room_for_head - 150)
            draw_text(pen, (head_x, y + 12 + size + 8), beneath, under,
                      MUTED, thin=True)

        # And where it came from, so nothing on this board is unattributed.
        outlet = norm_line(story.get("outlet"))
        if outlet:
            font = font_for(outlet, 16)
            wide = pen.textlength(outlet, font=font)
            pill_y = y + height - 34
            pen.rounded_rectangle(
                [W - PAD - wide - 26, pill_y, W - PAD - 4, pill_y + 24],
                radius=12, fill=PILL)
            draw_text(pen, (W - PAD - 15, pill_y + 12), outlet, 16, PILL_INK,
                      anchor="rm")

        y += height

    return board
