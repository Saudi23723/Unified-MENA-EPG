#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نور — the theme for the board that carries revealed text.

The sports boards wear a cold blue because a fixture list is a table
and a table wants to read like one. Scripture is not a table, and the
same ground under it read as a spreadsheet with an ayah in it.

So: a warmer, deeper ground; a girih lattice under everything at the
edge of visibility, drawn rather than pasted so the same bytes come out
on every machine; gold rules where the sports boards use a hairline;
and a naskh face for the revealed text with Tajawal kept for the
chrome, because a geometric sans is the wrong voice for a mushaf and
the right one for a chip that says which day it is.

NOTHING LATIN. Arabic-Indic numerals throughout, the Hijri date beside
the Gregorian, and the weekday in words.
"""
from __future__ import annotations

import math
from datetime import date

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
PAD = 52

# ── the ground ────────────────────────────────────────────────────────
# A night that has a lamp in it rather than a screen that is off.
TOP = (14, 34, 34, 255)          # deep viridian, the top of the fall
INK = (6, 14, 16, 255)           # and the bottom
CARD = (17, 42, 41, 255)
CARD_ALT = (14, 35, 35, 255)
LATTICE = (34, 74, 68, 255)      # the girih, barely there

GOLD = (208, 170, 100, 255)
GOLD_DIM = (128, 104, 62, 255)
WHITE = (245, 241, 232, 255)     # warm, not the sports boards' blue-white
MUTED = (146, 168, 158, 255)
GREEN = (86, 190, 140, 255)

NASKH = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
NASKH_BOLD = "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"
SANS = "fonts/Tajawal-Bold.ttf"
SANS_MID = "fonts/Tajawal-Medium.ttf"
SANS_HEAVY = "fonts/Tajawal-ExtraBold.ttf"

_cache: dict = {}


def face(path: str, size: int):
    key = (path, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(path, size)
    return _cache[key]


# ── numbers and dates, in Arabic ──────────────────────────────────────
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def digits(value) -> str:
    """Latin numerals are not on this board."""
    return "".join(ARABIC_DIGITS[int(c)] if c.isdigit() else c
                   for c in str(value))


WEEKDAYS = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس",
            "الجمعة", "السبت", "الأحد")
HIJRI_MONTHS = ("محرَّم", "صفر", "ربيع الأول", "ربيع الآخر",
                "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان",
                "رمضان", "شوَّال", "ذو القعدة", "ذو الحجة")


def to_hijri(day: date) -> tuple[int, int, int]:
    """The tabular Islamic calendar — within a day of any almanac."""
    jd = day.toordinal() + 1721425
    n = jd - 1948440 + 10632
    j = (n - 1) // 10631
    n = n - 10631 * j + 354
    k = ((10985 - n) // 5316) * ((50 * n) // 17719) + \
        (n // 5670) * ((43 * n) // 15238)
    n = n - ((30 - k) // 15) * ((17719 * k) // 50) - \
        (k // 16) * ((15238 * k) // 43) + 29
    month = (24 * n) // 709
    dayn = n - (709 * month) // 24
    year = 30 * j + k - 30
    return year, month, dayn


def hijri_words(day: date) -> str:
    year, month, dayn = to_hijri(day)
    return f"{digits(dayn)} {HIJRI_MONTHS[month - 1]} {digits(year)} هـ"


def weekday_word(day: date) -> str:
    return WEEKDAYS[day.weekday()]


# ── text ──────────────────────────────────────────────────────────────
def text_width(pen, text, font) -> int:
    return int(pen.textbbox((0, 0), text, font=font)[2])


def write(pen, xy, text, font, fill, anchor="la"):
    pen.text(xy, text, font=font, fill=fill, anchor=anchor,
             direction="rtl", language="ar")


def wrap(pen, text, font, room) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if text_width(pen, trial, font) <= room:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


# ── the ground, drawn ─────────────────────────────────────────────────
def girih(pen) -> None:
    """An eight-fold star lattice, at the edge of being seen.

    A real sixteen-vertex star, not two squares laid over each other:
    the squares came out as a grid of squares, which is a window frame
    and not a mosque wall. Alternating long and short radii is what
    makes the points read as points.
    """
    step = 118
    outer, inner = step * 0.46, step * 0.19
    for row in range(-1, H // step + 2):
        for col in range(-1, W // step + 2):
            cx = col * step + (step // 2 if row % 2 else 0)
            cy = row * step
            points = []
            for n in range(16):
                turn = n * math.pi / 8 - math.pi / 2
                reach = outer if n % 2 == 0 else inner
                points.append((cx + reach * math.cos(turn),
                               cy + reach * math.sin(turn)))
            pen.polygon(points, outline=LATTICE[:3] + (34,))
            # the small lozenge that sits between four stars
            half = step / 2
            pen.polygon([(cx + half, cy), (cx + half + 9, cy + 9),
                         (cx + half, cy + 18), (cx + half - 9, cy + 9)],
                        outline=LATTICE[:3] + (22,))


def ground() -> Image.Image:
    board = Image.new("RGBA", (W, H))
    pen = ImageDraw.Draw(board)
    for y in range(H):
        share = y / (H - 1)
        # eased, so the light pools at the top rather than sliding evenly
        share = share * share * (3 - 2 * share)
        row = tuple(int(round(TOP[i] + (INK[i] - TOP[i]) * share))
                    for i in range(3)) + (255,)
        pen.line([(0, y), (W, y)], fill=row)

    lattice = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    girih(ImageDraw.Draw(lattice))
    board.alpha_composite(lattice)

    # A LAMP, NOT AN ARC. Stacked ellipses of flat alpha left a visible
    # edge where the stack ended — a grey band across the top right of
    # the board. A radial falloff computed per ring, fading to nothing,
    # has no last ring to show.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gpen = ImageDraw.Draw(glow)
    cx, cy, reach = W - 210, -60, 620
    for step in range(60, 0, -1):
        radius = reach * step / 60
        share = 1 - step / 60
        alpha = int(round(16 * share * share))
        if alpha <= 0:
            continue
        gpen.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     fill=GOLD[:3] + (alpha,))
    board.alpha_composite(glow)
    return board


# ── ornament ──────────────────────────────────────────────────────────
def gold_rule(pen, y: int, *, width: int = W - 2 * PAD) -> None:
    """A hairline that swells to a lozenge in the middle."""
    left, right = (W - width) // 2, (W + width) // 2
    pen.line([(left, y), (right, y)], fill=GOLD_DIM[:3] + (120,), width=1)
    mid = W // 2
    pen.polygon([(mid - 26, y), (mid, y - 5), (mid + 26, y), (mid, y + 5)],
                fill=GOLD)
    for side in (-1, 1):
        pen.polygon([(mid + side * 40, y), (mid + side * 48, y - 3),
                     (mid + side * 56, y), (mid + side * 48, y + 3)],
                    fill=GOLD_DIM)


def corner(pen, x: int, y: int, size: int, dx: int, dy: int) -> None:
    """A mushaf's corner bracket."""
    pen.line([(x, y + dy * size), (x, y), (x + dx * size, y)],
             fill=GOLD_DIM, width=2)
    pen.line([(x + dx * 10, y + dy * (size - 14)),
              (x + dx * 10, y + dy * 10),
              (x + dx * (size - 14), y + dy * 10)],
             fill=GOLD_DIM[:3] + (110,), width=1)


def frame(pen, box, *, ornate=False) -> None:
    """A card. The ornate one is for revealed text only."""
    left, top, right, bottom = box
    pen.rounded_rectangle(box, radius=18, fill=CARD,
                          outline=GOLD_DIM[:3] + (90,), width=1)
    if not ornate:
        return
    for x, dx in ((left + 14, 1), (right - 14, -1)):
        for y, dy in ((top + 14, 1), (bottom - 14, -1)):
            corner(pen, x, y, 46, dx, dy)


def pill(pen, right: int, y: int, text, font, *,
         fill=None, ink=None, height=40) -> int:
    """A chip, laid out from its RIGHT edge because the board reads that way."""
    wide = text_width(pen, text, font) + 38
    pen.rounded_rectangle([right - wide, y, right, y + height],
                          radius=height // 2, fill=fill or CARD_ALT,
                          outline=GOLD_DIM[:3] + (110,), width=1)
    write(pen, (right - wide // 2, y + height // 2), text, font,
          ink or GOLD, anchor="mm")
    return right - wide


def pill_left(pen, left: int, y: int, text, font, *,
              fill=None, ink=None, height=40) -> int:
    """The same chip anchored by its LEFT edge.

    A column of right-anchored chips of different widths has a ragged
    left edge, which on a list of five is the only thing the eye sees.
    """
    wide = text_width(pen, text, font) + 38
    pen.rounded_rectangle([left, y, left + wide, y + height],
                          radius=height // 2, fill=fill or CARD_ALT,
                          outline=GOLD_DIM[:3] + (110,), width=1)
    write(pen, (left + wide // 2, y + height // 2), text, font,
          ink or GOLD, anchor="mm")
    return left + wide


def masthead(board, pen, title, subtitle, day, right_note="") -> int:
    """The channel's name, its day, and the two dates. All Arabic."""
    right = W - PAD
    write(pen, (right, PAD + 2), title, face(SANS_HEAVY, 52), WHITE,
          anchor="ra")
    write(pen, (right, PAD + 66), subtitle, face(SANS_MID, 22), MUTED,
          anchor="ra")

    # The dates sit on the left, the direction the eye leaves the line.
    left = PAD
    write(pen, (left, PAD + 6), hijri_words(day), face(SANS, 26), GOLD,
          anchor="la")
    gregorian = digits(f"{day.day:02d}.{day.month:02d}.{day.year}")
    write(pen, (left, PAD + 44), f"{weekday_word(day)} · {gregorian}",
          face(SANS_MID, 21), MUTED, anchor="la")
    if right_note:
        write(pen, (left, PAD + 76), right_note, face(SANS_MID, 20),
              GOLD_DIM, anchor="la")

    top = PAD + 116
    gold_rule(pen, top)
    return top + 26


def dots(pen, page: int, pages: int) -> None:
    if pages <= 1:
        return
    y = H - 28
    gap = 30
    left = (W - (pages - 1) * gap) // 2
    for which in range(pages):
        cx = left + which * gap
        if which == page - 1:
            pen.polygon([(cx - 7, y), (cx, y - 7), (cx + 7, y), (cx, y + 7)],
                        fill=GOLD)
        else:
            pen.ellipse([cx - 3, y - 3, cx + 3, y + 3], fill=GOLD_DIM)
