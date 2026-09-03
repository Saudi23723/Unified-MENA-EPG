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
    ACCENT, ARABIC, H, INK, MUTED, PAD, PANEL, PILL, PILL_INK, W, WHITE,
    clipped, draw_text, norm_line, size_that_fits,
    width_of,
)

# A fresh story is worth pointing at. Measured against the reader's own
# promise — "ساعة بساعة" — anything inside the hour is what a viewer
# turned the channel on for.
FRESH_MINUTES = 60

REGION_INK = (150, 176, 208, 255)

# The width the region gets on the left of a row. It was 108 with a clock
# above the region and the region shrunk to 16px underneath it; the clock
# is gone, so the region has the whole column and the headline starts in
# the same place it always did.
REGION_COLUMN = 108


# ARABIC IS DRAWN SMALLER THAN LATIN AT THE SAME NOMINAL SIZE, and on a
# board read from across a room that is the difference between a
# headline and a smudge. Reported in as many words: "العربي مش واضح
# منيح".
#
# It is not a rendering fault to correct — it is what the two faces are.
# FreeSerif is the only face on the build image that shapes Arabic, and
# its cap height at 27px sits well below DejaVu's; measured on this
# board, an Arabic headline needs about a fifth more to read as the same
# size as the English one beside it.
#
# So Arabic gets that fifth. Everything else about the row is unchanged,
# and the shrink-to-fit below still has the last word, so a long Arabic
# headline gives the size back rather than running off the board.
ARABIC_LIFT = 1.22


def for_script(text: str, size: int) -> int:
    """The size this text needs to LOOK like `size` on this board."""
    return int(round(size * ARABIC_LIFT)) if ARABIC.search(text or "") else size


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
    # NO CLOCK IS DRAWN HERE, AND THAT IS NOT A STYLE CHOICE. IT TOOK THE
    # CHANNEL OFF THE AIR.
    #
    # This printed the minute the build ran — "آخر تحديث 12:20" — so the
    # picture's BYTES changed on every pass. A segment is named after the
    # hash of its board, so every pass renamed all six segments and swept
    # the ones before them. Measured on what was published:
    #
    #     20:04  news renamed      20:10  news renamed
    #     20:07  news renamed      20:13  news renamed
    #
    # — every three minutes, while the two fixtures boards went hours
    # without changing. raw.githubusercontent serves the playlist with a
    # five-minute cache, so a television was still working through a
    # playlist whose segments had been deleted two passes ago:
    #
    #     An error occurred: code 404      photographed at 13:09 PT,
    #                                      which is 20:09 UTC
    #
    # The fixtures boards have known this since they were written — they
    # carry kickoff times and no countdown precisely so that they change
    # when the football changes and not when the clock ticks — and this
    # board was drawn without the rule.
    #
    # A DATE IS SAFE AND A MINUTE IS NOT, because a date changes once a
    # day. What the reader needs is not when the build ran; it is how old
    # the stories are, and every row already says that by lighting its
    # region when the story is inside the hour.
    draw_text(pen, (right, PAD - 2),
              now.astimezone(viewer).strftime("%d.%m.%Y"), 30, WHITE,
              anchor="ra")
    draw_text(pen, (right, PAD + 40),
              f"نشرة اليوم · {page}/{pages}" if pages > 1 else "نشرة اليوم",
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

        age = (now - story["start"]).total_seconds() / 60
        fresh = age <= FRESH_MINUTES

        # THE HOUR IS NOT DRAWN ANY MORE. "شيل الوقت بس يكون مخفي" — and
        # it earns its removal twice over. On a fixtures board a clock is
        # the point: it says when to be back. On a bulletin every story
        # has already happened, so a column of six times said nothing a
        # reader could act on and took the width the region needed.
        #
        # It is still READ, and that is the "مخفي" half: the hour orders
        # the page, decides what is fresh enough to point at, and is what
        # the reader refuses a story for not having. It is simply not
        # something the eye has to step over on its way to the headline.
        #
        # What is left in that column is the region, which is what a
        # reader scanning for Jordan is actually looking for, at the size
        # the clock used to take and lit when the story is inside the
        # hour.
        region = story.get("region_name", "")
        if region:
            at = size_that_fits(region, for_script(region, 21),
                                for_script(region, 14), REGION_COLUMN - 12)
            draw_text(pen, (PAD + 4, y + (height - 8) // 2), region, at,
                      ACCENT if fresh else REGION_INK,
                      anchor="lm", thin=not fresh)

        head_x = PAD + REGION_COLUMN
        room_for_head = W - PAD - head_x - 12

        # THE SOURCE IS MEASURED FIRST, because the line under the
        # headline has to stop before it. It did not, and the summary ran
        # straight under the pill on every row long enough to reach it —
        # visible on the published board, where Jordan News covered the
        # end of its own story twice.
        outlet = norm_line(story.get("outlet"))
        pill_wide = 0
        if outlet:
            pill_wide = width_of(outlet, for_script(outlet, 16)) + 34

        headline = norm_line(story["title"])
        size = size_that_fits(headline, for_script(headline, 27),
                              for_script(headline, 19), room_for_head)
        draw_text(pen, (head_x, y + 10), headline, size, WHITE)

        # The explanation, which is the whole point of the second line.
        beneath = norm_line(story.get("summary"))
        if beneath and height >= 78:
            room_for_line = room_for_head - pill_wide - 16
            under = size_that_fits(beneath, for_script(beneath, 18),
                                   for_script(beneath, 15), room_for_line)
            beneath = clipped(beneath, under, room_for_line)
            draw_text(pen, (head_x, y + 12 + size + 8), beneath, under,
                      MUTED, thin=True)

        # And where it came from, so nothing on this board is unattributed.
        if outlet:
            at = for_script(outlet, 16)
            wide = width_of(outlet, at)
            pill_y = y + height - 34
            pen.rounded_rectangle(
                [W - PAD - wide - 26, pill_y, W - PAD - 4, pill_y + 24],
                radius=12, fill=PILL)
            draw_text(pen, (W - PAD - 15, pill_y + 12), outlet, at, PILL_INK,
                      anchor="rm")

        y += height

    return board
