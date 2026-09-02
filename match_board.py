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
ACCENT = (56, 214, 111, 255)     # the clock, and the mark on a live row
LIVE_BG = (18, 52, 38, 255)
PILL = (30, 45, 66, 255)
PILL_INK = (176, 199, 227, 255)

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


def draw_board(day: date, events: list[dict], now: datetime, viewer,
               live_for, *, title: str, subtitle: str,
               weekday: str) -> Image.Image:
    """The whole board: header, then a ruled row for each match.

    `events` are dicts with start / title / channels, already filtered and
    in order. `live_for` is how long a match counts as under way.
    """
    board = Image.new("RGBA", (W, H), INK)
    pen = ImageDraw.Draw(board)

    # ---- header ---------------------------------------------------------
    draw_mark(pen, PAD, PAD - 4, 72)
    x = PAD + 72 + 22

    draw_text(pen, (x, PAD - 2), title, 40, WHITE)
    draw_text(pen, (x, PAD + 46), subtitle, 21, MUTED, thin=True)

    right = W - PAD
    draw_text(pen, (right, PAD - 2), f"{day:%d.%m.%Y}", 27, WHITE, anchor="ra")
    draw_text(pen, (right, PAD + 36), weekday, 21, MUTED, anchor="ra")
    count = (arabic_count(len(events), "مباراة", "مباراتان", "مباريات",
                          "مباراة") if events else "لا توجد مباراة")
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
        band = [PAD - 12, y, W - PAD + 12, y + height - 6]
        if live:
            pen.rounded_rectangle(band, radius=10, fill=LIVE_BG)
        elif index % 2 == 0:
            pen.rounded_rectangle(band, radius=10, fill=PANEL)

        middle = y + (height - 6) // 2
        size = max(19, min(28, height - 26))

        clock = event["start"].astimezone(viewer).strftime("%H:%M")
        draw_text(pen, (time_x, middle), clock, size, ACCENT, anchor="rm")

        # Channels sit on the right, so the name gets whatever is left.
        channel_x = W - PAD
        pill_size = max(15, size - 6)
        for channel in reversed(event["channels"][:2]):
            label = clipped(channel, pill_size, 230, thin=True)
            wide = width_of(label, pill_size, thin=True) + 26
            pen.rounded_rectangle(
                [channel_x - wide, middle - pill_size, channel_x,
                 middle + pill_size],
                radius=(pill_size + 4), fill=PILL)
            draw_text(pen, (channel_x - wide // 2, middle), label,
                      pill_size, PILL_INK, anchor="mm", thin=True)
            channel_x -= wide + 10

        if live:
            pen.ellipse([name_x, middle - 6, name_x + 12, middle + 6],
                        fill=ACCENT)
            head = name_x + 24
        else:
            head = name_x
        draw_text(pen, (head, middle),
                  clipped(event["title"], size, channel_x - head - 24, ),
                  size, WHITE, anchor="lm")
        y += height

    left_out = len(events) - len(rows)
    if left_out > 0:
        draw_text(pen, (W - PAD, H - PAD + 8), f"+{left_out} مباراة أخرى",
                  20, MUTED, anchor="rs")
    return board
