#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw the news board: a headline, a line explaining it, and where from.

The fixtures boards draw a clock, a name and channel pills, and their row
is built around a match that has not started yet — green for coming, red
for played, a lit band for live. A bulletin has none of that. Every story
here has already happened, so "coming" and "played" mean nothing, and a
clock in match-green on all six rows would say something false at a
glance.

So this is its own drawing, and it shares the fixtures board's kit
rather than copying it: the same Tajawal faces, the same gradient ground
and outlined cards, the same shrink-before-clip, the same sweep of boards
past the end. What it does NOT take is the fixtures green — the bulletin
wears amber, so four boards in a row are four channels and not four
copies of one.

What a row says, in the order the eye reads it:

    the region, on the left, lit when the story is inside the hour —
    which is the one thing a reader scanning for Jordan is looking for
    THE HEADLINE, as large as fits without being cut
    one sentence explaining it, which is the "شرح بسيط" that was asked for
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

from epg_lib import arabic_count
from match_board import (
    ARABIC, H, MUTED, PAD, PANEL, PANEL_ALT, PILL, PILL_INK, RULE, W,
    WHITE, backdrop, clipped, date_chip, draw_text, norm_line, progress,
    rule, size_that_fits, width_of,
)

# THE BULLETIN'S OWN COLOUR. The fixtures wear their green and the other
# sports their violet; the news wears amber, which is the colour a
# breaking story has always been flagged in and reads against a night
# ground the way a desk lamp reads against a dark room.
NEWS_ACCENT = (245, 184, 82, 255)

# A fresh story is worth pointing at. Measured against the reader's own
# promise — "ساعة بساعة" — anything inside the hour is what a viewer
# turned the channel on for.
FRESH_MINUTES = 60

REGION_INK = (150, 176, 208, 255)

# The ground a fresh story stands on: the amber's own dark, the way the
# fixtures board's live row is the green's own dark. A story that just
# landed is the thing the channel is for, and it is found by the corner
# of the eye rather than read off the column.
FRESH_BG = (44, 35, 22, 255)

# The width the region gets on the left of a row. The hour that used to
# sit above it is gone, so the region has the whole column and the
# headline starts in the same place it always did.
REGION_COLUMN = 108


def draw_mark(pen, x: int, y: int, size: int, accent=NEWS_ACCENT) -> None:
    """The channel's own mark: a ring of bulletin bars.

    The fixtures mark is a countdown ring, because a fixtures board is
    about when to be back. A bulletin is about what just landed, and the
    glyph for that is the three bars of a wire feed — drawn in the
    channel's amber on the amber's own dark, so the four marks in a row
    of boards say four different channels.
    """
    ink = tuple(min(255, int(c * 0.28)) for c in accent[:3]) + (255,)
    pen.rounded_rectangle([x, y, x + size, y + size],
                          radius=size // 5, fill=ink, outline=accent, width=2)
    inset = size // 4
    inner = size - 2 * inset
    bar_h = max(4, size // 11)
    # Three bars, the middle one the widest and in the accent: the wire
    # feed as a shape, legible at television distance.
    spans = (0.56, 1.0, 0.78)
    fills = (WHITE, accent, WHITE)
    for which, (share, colour) in enumerate(zip(spans, fills)):
        centre = y + inset + inner * (which + 0.5) / 3
        wide = int(inner * share)
        left = x + size // 2 - wide // 2
        pen.rounded_rectangle(
            [left, int(centre - bar_h / 2), left + wide, int(centre + bar_h / 2)],
            radius=bar_h // 2, fill=colour)


def draw_board(stories: list[dict], now: datetime, viewer, *,
               title: str, subtitle: str, page: int = 1,
               pages: int = 1) -> Image.Image:
    """One page of the bulletin.

    THE PICTURE IS THE SAME PICTURE however much later it is drawn, as
    long as nothing it shows has changed — the rule the whole channel
    lives by. What it draws of the moment is the DATE and the freshness
    of each story, both of which move on the scale of the news itself
    and not on the scale of the build.
    """
    board = backdrop()
    pen = ImageDraw.Draw(board)
    accent = NEWS_ACCENT

    # ---- header ---------------------------------------------------------
    draw_mark(pen, PAD, PAD - 6, 76, accent)
    x = PAD + 76 + 24

    draw_text(pen, (x, PAD - 4), title, 46, WHITE)
    draw_text(pen, (x, PAD + 52), subtitle, 21, MUTED, thin=True)

    right = W - PAD
    # A DATE, NOT A CLOCK — the one thing on this board that may change
    # daily and never sooner. The minute the build ran was printed here
    # once, and it renamed every segment every pass, and a television
    # working through a cached playlist was handed 404s until the fault
    # was found. What a reader needs is not when the build ran; it is
    # how old the stories are, and every row says that by lighting its
    # region when the story is inside the hour.
    date_chip(pen, right, PAD - 6, f"{now.astimezone(viewer):%d.%m.%Y}")

    count = (arabic_count(len(stories), "خبر", "خبران", "أخبار", "خبر")
             if stories else "لا توجد أخبار")
    if pages > 1:
        count = f"{count} — {page}/{pages}"
    draw_text(pen, (right, PAD + 64), count, 21, accent, anchor="ra")

    top = PAD + 122
    rule(pen, top, accent)

    if not stories:
        draw_text(pen, (W // 2, H // 2), "لا توجد أخبار الآن", 32, MUTED,
                  anchor="mm")
        progress(pen, page, pages, accent)
        return board

    # ---- rows -----------------------------------------------------------
    room = H - top - PAD
    height = min(104, room // len(stories))
    y = top + 8

    for index, story in enumerate(stories):
        band = [PAD - 12, y, W - PAD + 12, y + height - 8]

        age = (now - story["start"]).total_seconds() / 60
        fresh = age <= FRESH_MINUTES

        # A STORY INSIDE THE HOUR IS THE CHANNEL'S WHOLE PROMISE, so it
        # stands on the amber's own ground with a lit edge on the
        # reading side — the same shape the fixtures board gives a match
        # that is on now, found by the corner of the eye and not read.
        if fresh:
            pen.rounded_rectangle(band, radius=12, fill=FRESH_BG,
                                  outline=accent, width=1)
            pen.rounded_rectangle([band[0] + 3, band[1] + 7,
                                   band[0] + 8, band[3] - 7],
                                  radius=2, fill=accent)
        else:
            fill = PANEL if index % 2 == 0 else PANEL_ALT
            pen.rounded_rectangle(band, radius=12, fill=fill,
                                  outline=RULE, width=1)

        middle = y + (height - 8) // 2

        # THE HOUR IS NOT DRAWN. "شيل الوقت بس يكون مخفي" — and it
        # earns its removal twice over. On a fixtures board a clock is
        # the point: it says when to be back. On a bulletin every story
        # has already happened, so a column of six times said nothing a
        # reader could act on and took the width the region needed.
        #
        # It is still READ, and that is the "مخفي" half: the hour orders
        # the page, decides what is fresh enough to point at, and is
        # what the reader refuses a story for not having. It is simply
        # not something the eye has to step over on its way to the
        # headline.
        #
        # What is left in that column is the region, which is what a
        # reader scanning for Jordan is actually looking for, lit when
        # the story is inside the hour.
        region = norm_line(story.get("region_name"))
        if region:
            at = size_that_fits(region, 21, 14, REGION_COLUMN - 12)
            draw_text(pen, (PAD + 4, middle), region, at,
                      accent if fresh else REGION_INK,
                      anchor="lm", thin=not fresh)

        head_x = PAD + REGION_COLUMN
        room_for_head = W - PAD - head_x - 12

        # THE SOURCE IS MEASURED FIRST, because the line under the
        # headline has to stop before it. It did not, and the summary
        # ran straight under the pill on every row long enough to reach
        # it — visible on the published board, where Jordan News
        # covered the end of its own story twice.
        outlet = norm_line(story.get("outlet"))
        pill_wide = 0
        if outlet:
            pill_wide = width_of(outlet, 16) + 34

        headline = norm_line(story["title"])
        size = size_that_fits(headline, 27, 19, room_for_head)
        draw_text(pen, (head_x, y + 10), headline, size, WHITE)

        # The explanation, which is the whole point of the second line.
        beneath = norm_line(story.get("summary"))
        if beneath and height >= 78:
            room_for_line = room_for_head - pill_wide - 16
            under = size_that_fits(beneath, 18, 15, room_for_line)
            beneath = clipped(beneath, under, room_for_line)
            draw_text(pen, (head_x, y + 12 + size + 8), beneath, under,
                      MUTED, thin=True)

        # And where it came from, so nothing on this board is
        # unattributed. The pill is outlined now, like every other card
        # on the redrawn boards.
        if outlet:
            at = 16
            wide = width_of(outlet, at)
            pill_y = y + height - 34
            pen.rounded_rectangle(
                [W - PAD - wide - 26, pill_y, W - PAD - 4, pill_y + 24],
                radius=12, fill=PILL, outline=RULE, width=1)
            draw_text(pen, (W - PAD - 15, pill_y + 12), outlet, at, PILL_INK,
                      anchor="rm")

        y += height

    progress(pen, page, pages, accent)
    return board
