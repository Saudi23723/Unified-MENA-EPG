#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw the day's matches as a board, for players that show programme art.

A guide file cannot lay anything out. It hands a player text, and the
player decides what that looks like — which is why the day's page reads as
a list of lines rather than the ruled, coloured board a viewer pictures.

There is exactly one opening: XMLTV lets a programme carry an <icon>, and
a player that shows programme artwork will put a picture on the screen at
full size. So the page is drawn as a picture, and the picture is the board.

Clock times only, deliberately. A countdown would change every build and
every build would commit a new copy of a hundred kilobytes; the times do
not change until the day's fixtures do, so the board is written a handful
of times a day. The live countdown stays in the title, which costs
nothing to rewrite. The board answers "what is on today", the title
answers "how long until the next one".
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

from epg_lib import arabic_count

from PIL import Image, ImageDraw, ImageFont, features

# Faces are looked up rather than named, because the machine that draws
# this is not the machine it was written on: a GitHub runner ships DejaVu
# and no Arabic face at all, and the first pass on one drew nothing but
# "cannot open resource". Each list is tried in order and the first file
# that exists wins, so installing a package is enough to change the answer
# and a missing one degrades to no board rather than to a broken build.
AR_FACES = (
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",   # no Arabic; a floor
)
EN_FACES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)
EN_THIN_FACES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)


def first_face(faces) -> str:
    for face in faces:
        if os.path.exists(face):
            return face
    raise FileNotFoundError(f"none of these fonts is installed: {faces}")


def has_arabic_face() -> bool:
    """Whether anything here can actually shape Arabic."""
    return (features.check("raqm")
            and os.path.exists(AR_FACES[0]))

W, H = 1280, 720
PAD = 48

INK = (10, 18, 30, 255)          # the ground
PANEL = (18, 29, 45, 255)        # a row's own shade, every other one
RULE = (35, 51, 74, 255)         # hairlines
WHITE = (243, 247, 252, 255)
MUTED = (139, 158, 184, 255)
ACCENT = (56, 214, 111, 255)     # the clock of a match still to come
OVER = (232, 93, 93, 255)        # and of one that has already been played
LIVE_BG = (18, 52, 38, 255)
PILL = (30, 45, 66, 255)
PILL_INK = (176, 199, 227, 255)
INK_TOP = (8, 16, 28, 255)
INK_BOTTOM = (16, 33, 52, 255)
SHEEN = (74, 130, 212, 180)
AURA = (40, 88, 170, 68)

ARABIC = re.compile(r"[؀-ۿݐ-ݿ]")


def font_for(text: str, size: int, *, thin: bool = False):
    """FreeSerif carries Arabic; DejaVu is the better face for Latin."""
    if ARABIC.search(text or ""):
        return ImageFont.truetype(first_face(AR_FACES), size)
    return ImageFont.truetype(
        first_face(EN_THIN_FACES if thin else EN_FACES), size)


def draw_text(pen, xy, text, size, fill, *, anchor="la", thin=False):
    """One run, laid out in its own script's direction."""
    text = text or ""
    font = font_for(text, size, thin=thin)
    if ARABIC.search(text):
        pen.text(xy, text, font=font, fill=fill, anchor=anchor,
                 direction="rtl", language="ar")
    else:
        pen.text(xy, text, font=font, fill=fill, anchor=anchor)


def width_of(text: str, size: int, *, thin=False) -> int:
    font = font_for(text or "", size, thin=thin)
    box = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text or "",
                                                            font=font)
    return box[2] - box[0]


def clipped(text: str, size: int, room: int, *, thin=False) -> str:
    """Cut a name to the room it has, with an ellipsis if it lost anything."""
    if width_of(text, size, thin=thin) <= room:
        return text
    cut = text
    while cut and width_of(cut + "…", size, thin=thin) > room:
        cut = cut[:-1]
    return (cut.rstrip() + "…") if cut else ""


def size_that_fits(text: str, size: int, floor: int, room: int) -> int:
    """The largest size at or under `size` that fits, never below `floor`.

    A name cut short is a name that says nothing. "US Open Men's &
    Women's Singles 3rd Round and Women's Doubles 1st Round" came out as
    "US Open…", which is every tennis row on the board and tells a
    viewer which of them apart from none. Two or three points smaller and
    the whole of it fits.

    The floor is the line underneath it, because a name smaller than its
    own subtitle reads as a mistake rather than as a fit. Below that the
    caller clips, and what is left is a name longer than a whole board,
    where something has to give.
    """
    while size > floor and width_of(text or "", size) > room:
        size -= 1
    return size


def forget_boards_past(prefix: str, kept: int, folder: str = "boards") -> int:
    """Delete this screen's boards numbered at or beyond `kept`.

    NOTHING EVER DELETED A BOARD, and at midnight that shows.

    A build writes board 0 upwards for the days it has. When a day ends
    the window rolls: yesterday is gone, a new day arrives at the far
    end, and the count can fall — a quiet day needs one board where a
    busy one needed three. The boards the new build did not write stayed
    on disk from the old one, and the reel picks up every board it finds.
    So a day that was over went on playing, in a slot the new build no
    longer knew about, until some later day happened to be busy enough to
    overwrite it.

    That is the whole of "at midnight, delete the day's page": a board
    numbered past the end of this build is not a page any more.
    """
    if not os.path.isdir(folder):
        return 0
    gone = 0
    for name in sorted(os.listdir(folder)):
        if not (name.startswith(prefix) and name.endswith(".png")):
            continue
        number = re.search(r"_(\d+)\.png$", name)
        if number and int(number.group(1)) >= kept:
            os.remove(os.path.join(folder, name))
            gone += 1
    return gone


def norm_line(value) -> str:
    """One line of text, or nothing. A competition may be missing."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def paint_background(board: Image.Image) -> None:
    """A darker top and a softer lower half, so the board reads like a screen."""
    pen = ImageDraw.Draw(board, "RGBA")
    for y in range(H):
        mix = y / max(H - 1, 1)
        colour = tuple(
            int(top + (bottom - top) * mix)
            for top, bottom in zip(INK_TOP[:3], INK_BOTTOM[:3]))
        pen.line([(0, y), (W, y)], fill=colour + (255,), width=1)
    pen.ellipse([W - 420, -180, W + 120, 260], fill=AURA)
    pen.rounded_rectangle([PAD - 18, PAD - 18, W - PAD + 18, PAD + 86],
                          radius=28, fill=(11, 20, 34, 214),
                          outline=SHEEN, width=2)
    pen.line([(PAD + 20, PAD + 84), (W - PAD - 20, PAD + 84)],
             fill=SHEEN, width=3)


def draw_mark(pen, x: int, y: int, size: int) -> None:
    """The channel's mark, drawn rather than shrunk.

    The published logo carries the channel's name inside its ring, which
    is legible at 512 pixels and mush at seventy. So the badge here is the
    ring alone — the same countdown caught part-way, the same green — and
    the name is set beside it at a size that can be read.
    """
    pen.rounded_rectangle([x, y, x + size, y + size],
                          radius=size // 5, fill=PANEL)
    inset = size // 6
    ring = [x + inset, y + inset, x + size - inset, y + size - inset]
    pen.ellipse(ring, outline=RULE, width=max(3, size // 12))
    pen.arc(ring, start=-90, end=170, fill=ACCENT, width=max(3, size // 12))


# اليوم, غداً, بعد غد — and nothing beyond that, because the guide is
# only ever drawn three days out and a fourth word would be a guess.
RELATIVE_DAY = {0: "اليوم", 1: "غداً", 2: "بعد غد"}


def day_badge(day: date, now: datetime, viewer, weekday: str) -> str:
    """Which of the three days this board is, said in words.

    No digits: the date is already set on the right, and a number inside
    Arabic is the one thing that can come out reversed.
    """
    away = (day - now.astimezone(viewer).date()).days
    relative = RELATIVE_DAY.get(away, "")
    return f"{relative} · {weekday}" if relative else weekday


def draw_board(day: date, events: list[dict], now: datetime, viewer,
               live_for, *, title: str, subtitle: str, weekday: str,
               page: int = 1, pages: int = 1) -> Image.Image:
    """The whole board: header, then a ruled row for each match.

    `events` are dicts with start / title / channels, already filtered and
    in order. `live_for` is how long a match counts as under way.
    """
    board = Image.new("RGBA", (W, H), INK)
    paint_background(board)
    pen = ImageDraw.Draw(board)

    # ---- header ---------------------------------------------------------
    draw_mark(pen, PAD, PAD - 4, 72)
    x = PAD + 72 + 22

    draw_text(pen, (x, PAD - 2), title, 40, WHITE)
    draw_text(pen, (x, PAD + 46), subtitle, 21, MUTED, thin=True)

    right = W - PAD
    draw_text(pen, (right, PAD - 2), f"{day:%d.%m.%Y}", 27, WHITE, anchor="ra")

    # WHICH day this board is, in the middle where it cannot be missed.
    #
    # The name of the channel is "مباريات اليوم", and it was set in 40px
    # across the top of every board — including tomorrow's and the day
    # after's. So the largest words on a Friday board said "today", and
    # the only thing that disagreed was a 21px muted weekday in a corner.
    # A viewer watching three boards go past could not tell which was
    # which, and the one thing they were told outright was wrong.
    #
    # The relative word is the one that answers it — اليوم, غداً, بعد غد
    # — and the weekday is what it means. No digits in this badge: the
    # date is already set on the right, and a number inside Arabic is the
    # one thing that can come out reversed.
    badge = day_badge(day, now, viewer, weekday)
    badge_size = 27
    wide = width_of(badge, badge_size) + 56
    middle_x = W // 2
    pen.rounded_rectangle(
        [middle_x - wide // 2, PAD - 6, middle_x + wide // 2, PAD + 40],
        radius=23, fill=PANEL)
    draw_text(pen, (middle_x, PAD + 17), badge, badge_size, ACCENT,
              anchor="mm")
    count = (arabic_count(len(events), "مباراة", "مباراتان", "مباريات",
                          "مباراة") if events else "لا توجد مباراة")
    # A day too long for one screen is drawn over several, and a viewer
    # watching them go past should be told which of them this is.
    if pages > 1:
        count = f"{count} — {page}/{pages}"
    draw_text(pen, (right, PAD + 66), count, 21, ACCENT, anchor="ra")

    top = PAD + 106
    pen.line([(PAD, top), (W - PAD, top)], fill=RULE, width=2)

    if not events:
        draw_text(pen, (W // 2, H // 2), "لا توجد مباراة معلنة اليوم",
                  32, MUTED, anchor="mm")
        return board

    # ---- rows -----------------------------------------------------------
    room = H - top - PAD
    rows = events
    height = 62
    if len(rows) * height > room:
        height = max(38, room // len(rows))
        if height < 38:                     # more than fits: show what does
            rows = events[:max(1, (room - 40) // 38)]
            height = 38

    time_x, name_x = PAD + 128, PAD + 168
    y = top + 6
    for index, event in enumerate(rows):
        live = event["start"] <= now < event["start"] + live_for
        # OVER, AND SAID SO IN RED. Asked for outright. A board carries
        # the whole day, so by the evening most of it has been played —
        # and every one of those rows was printing its clock in the same
        # green as the match that has not started yet. Green is the
        # colour this board uses for "coming"; a match that is finished
        # is not coming, and a viewer scanning for what is next was being
        # made to read every line to find out.
        over = event["start"] + live_for <= now
        band = [PAD - 12, y, W - PAD + 12, y + height - 6]
        if live:
            pen.rounded_rectangle(band, radius=10, fill=LIVE_BG)
        elif index % 2 == 0:
            pen.rounded_rectangle(band, radius=10, fill=PANEL)

        middle = y + (height - 6) // 2

        # TWO LINES WHERE THERE IS ROOM FOR TWO, and the second one is
        # the competition.
        #
        # A row said "Fenerbahce - Besiktas · beIN 6" and left out the one
        # thing that tells a viewer what they are looking at — whether
        # that is the league, the cup, or a pre-season friendly. On the
        # second board it matters more, not less: "Live Boxing Ruiz vs
        # Knyba" says nothing about whether it is a title fight, and
        # "Practice 1" says nothing about which championship.
        #
        # The name gives up a little size to make room, which is the
        # trade asked for outright — a slightly smaller line that says
        # more beats a large one that says half of it.
        #
        # 42 is where it stops, and it is measured rather than chosen: a
        # 42px row leaves a 36px band, and a 17px name over a 13px
        # competition needs 31 of it. Below that the two lines start
        # touching, and two lines that touch are worse than one that
        # does not — so a day too full for both keeps the single centred
        # name, which is the thing a viewer came for.
        beneath = norm_line(event.get("competition"))
        two = bool(beneath) and height >= 42
        size = (max(17, min(25, height - 30)) if two
                else max(19, min(28, height - 26)))
        under = max(13, size - 7)
        head_y = middle - (under // 2) - 2 if two else middle
        sub_y = middle + (size // 2) + 2

        clock = event["start"].astimezone(viewer).strftime("%H:%M")
        draw_text(pen, (time_x, middle), clock, size,
                  OVER if over else ACCENT, anchor="rm")

        if live:
            pen.ellipse([name_x, head_y - 6, name_x + 12, head_y + 6],
                        fill=ACCENT)
            head = name_x + 24
        else:
            head = name_x

        # The channels sit on whichever line has room for them: beside
        # the name when there is only one, and under it when there are
        # two — which is the whole point of two.
        pill_y = sub_y if two else middle
        pill_size = max(15, (under if two else size) - 2)
        channel_x = W - PAD
        for channel in reversed(event["channels"][:3]):
            label = clipped(channel, pill_size, 280, thin=True)
            wide = width_of(label, pill_size, thin=True) + 26
            pen.rounded_rectangle(
                [channel_x - wide, pill_y - pill_size, channel_x,
                 pill_y + pill_size],
                radius=(pill_size + 4), fill=PILL)
            draw_text(pen, (channel_x - wide // 2, pill_y), label,
                      pill_size, PILL_INK, anchor="mm", thin=True)
            channel_x -= wide + 10

        # THE NAME GETS THE WHOLE LINE. It used to end where the channel
        # pills began, which on a busy row was less than half the board —
        # "US Open Men's & Women's Singles 3rd Round and Women's Doubles
        # 1st Round" came out as "US Open…" and said nothing at all.
        #
        # With the pills moved down, nothing is beside the name any more,
        # so it runs edge to edge and the events that actually need the
        # room are the ones that get it. It is still clipped if it is
        # longer than a whole board, because something has to give — but
        # that is now a genuinely enormous name rather than an ordinary
        # one competing with three channel pills.
        room_for_name = (W - PAD - head) if two else (channel_x - head - 24)

        # SHRINK BEFORE CUTTING. A name cut short is a name that says
        # nothing — "US Open Men's & Women's Singles 3rd Round and
        # Women's Doubles 1st Round" became "US Open…", which is every
        # tennis row on the board and tells a viewer which of them apart
        # from none. Two or three points smaller and the whole of it
        # fits, and a viewer can read the whole of it.
        #
        # It only goes down as far as the competition line under it,
        # because a name smaller than its own subtitle reads as a
        # mistake. Past that, and only past that, it is clipped — and
        # what is left over is a name longer than a whole board, where
        # something has to give.
        fitted = size_that_fits(event["title"], size,
                                under if two else max(15, size - 6),
                                room_for_name)
        draw_text(pen, (head, head_y),
                  clipped(event["title"], fitted, room_for_name),
                  fitted, WHITE, anchor="lm")

        if two:
            # And the competition takes what the pills left on their line.
            draw_text(pen, (head, sub_y),
                      clipped(beneath, under, channel_x - head - 20,
                              thin=True),
                      under, MUTED, anchor="lm", thin=True)
        y += height

    left_out = len(events) - len(rows)
    if left_out > 0:
        draw_text(pen, (W - PAD, H - PAD + 8), f"+{left_out} مباراة أخرى",
                  20, MUTED, anchor="rs")
    return board
