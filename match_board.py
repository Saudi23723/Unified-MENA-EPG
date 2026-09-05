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

THE 2026 REDRAW
===============
The boards were FreeSerif-on-flat-navy, which read as a terminal rather
than as a channel. They are drawn again on the same skeleton — the same
rows, the same shrink-before-clip, the same byte-for-byte stability —
with a face that was made for screens like this one and a ground that
has some depth to it:

    Tajawal, committed under fonts/, is the face. It is a modern
    bilingual sans (OFL, Boutros International) that shapes Arabic with
    raqm the same as it sets Latin, so one family serves the whole board
    and the two scripts finally look like they were designed together.
    The system faces stay in the lookup as the floor under it, because a
    machine without the repo's fonts/ still has to draw something.

    The ground is a slow gradient instead of a flat ink, the rows are
    outlined cards instead of bare bands, and each channel carries its
    own accent colour so four boards in a row are four channels and not
    four copies of one. NOTHING ABOUT THE CONTENT MOVED: same strings,
    same sources, same date-and-no-clock rule, same clipping, and the
    picture is still identical from one build to the next unless the
    day itself changed.
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
# that exists wins, so the repo's own fonts/ is the face and the system
# packages are the floor under it.
#
# Tajawal first because it is the redraw's face: one family, Arabic and
# Latin, four weights. FreeSerif and DejaVu stay behind it so a checkout
# without fonts/ degrades to the old look rather than to no board.
AR_FACES = (
    "fonts/Tajawal-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",   # no Arabic; a floor
)
EN_FACES = (
    "fonts/Tajawal-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)
EN_THIN_FACES = (
    "fonts/Tajawal-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)
# The display weights: temperature figures and channel titles set in the
# ExtraBold, and the quieter labels in the Medium.
HEAVY_FACES = (
    "fonts/Tajawal-ExtraBold.ttf",
    "fonts/Tajawal-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
MID_FACES = (
    "fonts/Tajawal-Medium.ttf",
    "fonts/Tajawal-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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

# THE GROUND AND THE CARDS ON IT. The redraw keeps the palette's names —
# other boards import them by name — and moves their values: a deeper
# ink, a bluer panel, a rule bright enough to outline a card with.
INK = (7, 13, 24, 255)           # the bottom of the gradient
TOP = (16, 27, 44, 255)          # and the top of it
PANEL = (17, 29, 46, 255)        # a card's own shade
PANEL_ALT = (22, 35, 55, 255)    # and its neighbour's
RULE = (44, 64, 92, 255)         # outlines and hairlines
WHITE = (242, 246, 251, 255)
MUTED = (142, 161, 188, 255)
ACCENT = (52, 211, 153, 255)     # the clock of a match still to come
OVER = (239, 93, 93, 255)        # and of one that has already been played
LIVE_BG = (74, 18, 24, 255)      # the band a match on now sits in: red, and meant
LIVE_RED = (255, 105, 97, 255)   # the clock of the row that is on the air
LIVE_TAG = (224, 49, 49, 255)    # the مباشر pill: solid red, white letters
OVER_TAG = (108, 124, 148, 255)  # the انتهى pill: slate, white letters
OVER_BG = (24, 33, 47, 255)      # the band a finished match sits in: grey, not green
PILL = (31, 47, 72, 255)
PILL_INK = (186, 207, 233, 255)

ARABIC = re.compile(r"[\u0600-\u06ff\u0750-\u077f]")


def font_for(text: str, size: int, *, thin: bool = False, weight: str = ""):
    """Tajawal for everything, at the weight the line asked for.

    `thin` is kept because half this repo's drawing calls use it; the
    named weights are the redraw's — "heavy" for the figures a board is
    watched for and "mid" for the labels beside them.
    """
    if weight == "heavy":
        return ImageFont.truetype(first_face(HEAVY_FACES), size)
    if weight in ("mid", "medium"):
        return ImageFont.truetype(first_face(MID_FACES), size)
    if ARABIC.search(text or ""):
        return ImageFont.truetype(first_face(AR_FACES), size)
    return ImageFont.truetype(
        first_face(EN_THIN_FACES if thin else EN_FACES), size)


# LETTERS THE FACE CANNOT WRITE, written the way the reader says them.
#
# Tajawal is the board's face, and it has no Turkish ş, ğ, İ, Ş or Ğ —
# measured on the committed fonts, and then photographed by a reader:
# "look how Beşiktaş looks bad", and it did, every s in it a hollow box
# where the face gives up. The GUIDE carries the true spelling and always
# will; this is the picture's problem, so it is mended in the picture:
# the five letters the face cannot draw are drawn as the nearest ones it
# can — s, S, g, G, I — and Beşiktaş reads the way it is said. ı ç ü ö
# and their capitals are all present in the face and left exactly alone.
THE_LETTERS_THE_FACE_LACKS = str.maketrans({
    "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G", "İ": "I",
})


def as_the_face_writes_it(text: str) -> str:
    """The text with every letter the face lacks in the nearest one it has."""
    return (text or "").translate(THE_LETTERS_THE_FACE_LACKS)


# THE READER'S NAME, small, in the top right corner of every board.
# Asked for by name and by position: "write my name S.Saudi on every
# channel on the 4 channels always to be showed on top right corner in
# small text". Every board this repository draws — the fixtures, the
# other sports, the news, the weather — carries it, drawn rather than
# stamped on the video, so it is part of the picture the moment the
# board is drawn and not a layer any encoder could lose.
SIGNATURE = "S.Saudi"


def draw_signature(pen) -> None:
    """The reader's mark: small, muted, top right, on every board."""
    draw_text(pen, (W - PAD, 20), SIGNATURE, 15, MUTED,
              anchor="ra", thin=True)


def draw_text(pen, xy, text, size, fill, *, anchor="la", thin=False,
              weight: str = ""):
    """One run, laid out in its own script's direction."""
    text = as_the_face_writes_it(text)
    font = font_for(text, size, thin=thin, weight=weight)
    if ARABIC.search(text):
        pen.text(xy, text, font=font, fill=fill, anchor=anchor,
                 direction="rtl", language="ar")
    else:
        pen.text(xy, text, font=font, fill=fill, anchor=anchor)


def width_of(text: str, size: int, *, thin=False, weight: str = "") -> int:
    font = font_for(text or "", size, thin=thin, weight=weight)
    box = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text or "",
                                                            font=font)
    return box[2] - box[0]


def clipped(text: str, size: int, room: int, *, thin=False,
            weight: str = "") -> str:
    """Cut a name to the room it has, with an ellipsis if it lost anything."""
    if width_of(text, size, thin=thin, weight=weight) <= room:
        return text
    cut = text
    while cut and width_of(cut + "…", size, thin=thin, weight=weight) > room:
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


# ------------------------------------------------------------------ ground

def backdrop() -> Image.Image:
    """The ground every board stands on: a slow fall from blue to ink.

    A flat ink read as a terminal; a gradient this shallow reads as a
    screen with a light on it. It is drawn a row at a time so the same
    ground comes out byte for byte on every machine that draws it —
    which is the rule the whole board lives by, and a blur would break.
    """
    board = Image.new("RGBA", (W, H))
    pen = ImageDraw.Draw(board)
    for y in range(H):
        share = y / (H - 1)
        row = tuple(
            int(round(TOP[i] + (INK[i] - TOP[i]) * share)) for i in range(3)
        ) + (255,)
        pen.line([(0, y), (W, y)], fill=row)
    return board


def rule(pen, y: int, accent) -> None:
    """A hairline with a short focus of the channel's colour in its middle."""
    pen.line([(PAD, y), (W - PAD, y)], fill=RULE, width=2)
    pen.rounded_rectangle([W // 2 - 64, y - 1, W // 2 + 64, y + 3],
                          radius=2, fill=accent)


def progress(pen, page: int, pages: int, accent, *, y: int | None = None) -> None:
    """Where this board sits in the reel, said in dots instead of digits.

    The page number is already in the header; the dots are for the corner
    of the eye, which is the one reading a board from across a room.
    Nothing time-dependent is drawn — page and pages are the whole input.
    """
    if pages <= 1:
        return
    y = H - 26 if y is None else y
    gap, dot = 26, 5
    left = (W - (pages * gap - (gap - dot * 2))) // 2
    for which in range(pages):
        cx = left + which * gap + dot
        fill = accent if which == page - 1 else RULE
        pen.ellipse([cx - dot, y - dot, cx + dot, y + dot], fill=fill)


def date_chip(pen, right: int, y: int, text: str) -> int:
    """The date as a right-aligned chip; returns the chip's left edge."""
    wide = width_of(text, 24) + 40
    pen.rounded_rectangle([right - wide, y, right, y + 44],
                          radius=14, fill=PANEL, outline=RULE, width=1)
    draw_text(pen, (right - 20, y + 22), text, 24, WHITE, anchor="rm")
    return right - wide


def draw_mark(pen, x: int, y: int, size: int, accent=ACCENT) -> None:
    """The channel's mark, drawn rather than shrunk.

    The redraw's mark is a filled square in the channel's colour with
    the countdown ring inside it — bolder at television distance than
    the outline it was, and still the same badge the logo wears.
    """
    ink = tuple(min(255, int(c * 0.28)) for c in accent[:3]) + (255,)
    pen.rounded_rectangle([x, y, x + size, y + size],
                          radius=size // 5, fill=ink, outline=accent, width=2)
    inset = size // 4
    ring = [x + inset, y + inset, x + size - inset, y + size - inset]
    pen.ellipse(ring, outline=WHITE, width=max(3, size // 14))
    pen.arc(ring, start=-90, end=170, fill=accent, width=max(3, size // 14))
    pen.ellipse([x + size // 2 - 4, y + size // 2 - 4,
                 x + size // 2 + 4, y + size // 2 + 4], fill=WHITE)


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
               page: int = 1, pages: int = 1, accent=None) -> Image.Image:
    """The whole board: header, then a card for each match.

    `events` are dicts with start / title / channels, already filtered and
    in order. `live_for` is how long a match counts as under way.
    `accent` is the channel's own colour — the football wears the green
    and the other sports their violet, and a caller that passes nothing
    gets the green this board has always worn.
    """
    accent = accent or ACCENT
    board = backdrop()
    pen = ImageDraw.Draw(board)

    # ---- header ---------------------------------------------------------
    draw_mark(pen, PAD, PAD - 6, 76, accent)
    x = PAD + 76 + 24

    draw_text(pen, (x, PAD - 4), title, 46, WHITE)
    draw_text(pen, (x, PAD + 52), subtitle, 21, MUTED, thin=True)

    right = W - PAD
    date_chip(pen, right, PAD - 6, f"{day:%d.%m.%Y}")
    draw_signature(pen)

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
    badge_size = 26
    wide = width_of(badge, badge_size) + 60
    middle_x = W // 2
    pen.rounded_rectangle(
        [middle_x - wide // 2, PAD + 46, middle_x + wide // 2, PAD + 92],
        radius=23, fill=PANEL, outline=RULE, width=1)
    draw_text(pen, (middle_x, PAD + 69), badge, badge_size, accent,
              anchor="mm")
    count = (arabic_count(len(events), "مباراة", "مبارياتان", "مباريات",
                          "مباراة") if events else "لا توجد مباراة")
    # A day too long for one screen is drawn over several, and a viewer
    # watching them go past should be told which of them this is.
    if pages > 1:
        count = f"{count} — {page}/{pages}"
    draw_text(pen, (right, PAD + 64), count, 21, accent, anchor="ra")

    top = PAD + 122
    rule(pen, top, accent)

    if not events:
        draw_text(pen, (W // 2, H // 2), "لا توجد مباراة معلنة اليوم",
                  32, MUTED, anchor="mm")
        progress(pen, page, pages, accent)
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
    y = top + 8
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
            # ON THE AIR, AND IT LOOKS LIKE IT. A viewer looking at the
            # board in bed, at arm's length, in the dark, asked why a
            # match being played right now looked exactly like one that
            # starts at nine. It did: the live band was a green so close
            # to the panel either side of it that the only difference was
            # a hairline a pixel wide, and the clock stayed green — the
            # colour of "not started yet".
            #
            # So the band is red now, in the one shade a television
            # viewer already knows means "on the air", with a red
            # مباشر pill beside the clock and the clock itself red. Red
            # was already the board's word for "over"; it stays there as
            # a muted letter and comes here as a lit room, so "over" is
            # read and "on now" is seen.
            pen.rounded_rectangle(band, radius=12, fill=LIVE_BG,
                                  outline=LIVE_TAG, width=2)
            # A thick lit edge on the reading side — six times the
            # hairline it was — so the eye lands on the row that is on
            # before it reads a word on it.
            pen.rounded_rectangle([band[0] + 3, band[1] + 7,
                                   band[0] + 11, band[3] - 7],
                                  radius=3, fill=LIVE_TAG)
        elif over:
            # FINISHED, AND IT LOOKS LIKE IT TOO. The live row got a red
            # room; the finished one gets the opposite of that: a grey
            # band dimmer than the panels around it, so an evening board
            # full of played matches reads as "already been" at a glance
            # and the green rows are the ones the eye goes to. The clock
            # keeps its red — "over" stays red as it always was — but
            # the row itself steps back, and the انتهى pill below says
            # what the colour is saying.
            pen.rounded_rectangle(band, radius=12, fill=OVER_BG,
                                  outline=OVER_TAG, width=1)
            pen.rounded_rectangle([band[0] + 3, band[1] + 7,
                                   band[0] + 11, band[3] - 7],
                                  radius=3, fill=OVER_TAG)
        else:
            fill = PANEL if index % 2 == 0 else PANEL_ALT
            pen.rounded_rectangle(band, radius=12, fill=fill,
                                  outline=RULE, width=1)

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
        # 14 is the floor for the competition line, measured against the
        # smallest phone a viewer checks a board on: 13px MUTED thin read
        # as a smudge at arm's length and the viewer could not tell the
        # league from the cup, which is the one thing the line exists to
        # say. Two points of size cost nothing the name needs and the
        # line is legible wherever the clock beside it is.
        under = max(14, size - 7)
        head_y = middle - (under // 2) - 2 if two else middle
        sub_y = middle + (size // 2) + 2

        clock = event["start"].astimezone(viewer).strftime("%H:%M")
        draw_text(pen, (time_x, middle), clock, size,
                  LIVE_RED if live else (OVER if over else accent),
                  anchor="rm")

        if live:
            # AND THE ROW SAYS SO IN A WORD. The band is caught by the
            # eye; the pill is read. مباشر — "on the air" — in white on
            # solid red, on the reading side of the name, because the
            # viewer who asked for this asked it from bed in the dark:
            # "which one is on now?" is answered at a glance by a colour
            # and confirmed in a word.
            tag_px = max(13, min(16, size - 8))
            tag_w = width_of("مباشر", tag_px, weight="mid") + 22
            pen.rounded_rectangle(
                [name_x, head_y - tag_px - 5, name_x + tag_w,
                 head_y + tag_px + 5],
                radius=tag_px + 5, fill=LIVE_TAG)
            draw_text(pen, (name_x + tag_w // 2, head_y), "مباشر",
                      tag_px, WHITE, anchor="mm", weight="mid")
            head = name_x + tag_w + 14
        elif over:
            # THE FINISHED PILL, THE SAME SHAPE AS THE LIVE ONE. Red and
            # a word is how the board says "on the air"; slate and a word
            # is how it says "finished". انتهى sits where مباشر sits, so
            # a viewer scanning the reading side finds the same shape in
            # the same place and only the colour and the word change —
            # the reading side of the board keeps one language.
            tag_px = max(13, min(16, size - 8))
            tag_w = width_of("انتهى", tag_px, weight="mid") + 22
            pen.rounded_rectangle(
                [name_x, head_y - tag_px - 5, name_x + tag_w,
                 head_y + tag_px + 5],
                radius=tag_px + 5, fill=OVER_TAG)
            draw_text(pen, (name_x + tag_w // 2, head_y), "انتهى",
                      tag_px, WHITE, anchor="mm", weight="mid")
            head = name_x + tag_w + 14
        else:
            head = name_x

        # The channels sit on whichever line has room for them: beside
        # the name when there is only one, and under it when there are
        # two — which is the whole point of two.
        pill_y = sub_y if two else middle
        # SAME SIZE ON EVERY ROW, TWO LINES OR ONE. The size used to be
        # taken from the line the pills sat on, and a single-line row
        # had a larger font than a two-line one, so its pills were
        # larger too — Fox Nation measured 35px tall against DAZN's 22
        # beside it on the same board, and a viewer read the larger pill
        # as a louder channel. Every row's pills are drawn at the
        # two-line row's ceiling now, whichever line they sit on, so
        # the board has one size of channel and not two.
        pill_size = max(15, min(16, (under if two else size - 8) - 2))
        channel_x = W - PAD
        for channel in reversed(event["channels"][:3]):
            label = clipped(channel, pill_size, 280, thin=True)
            wide = width_of(label, pill_size, thin=True) + 26
            pen.rounded_rectangle(
                [channel_x - wide, pill_y - pill_size, channel_x,
                 pill_y + pill_size],
                radius=(pill_size + 4), fill=PILL, outline=RULE, width=1)
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
            # THE COMPETITION IS THE FIRST THING A VIEWER LOOKS FOR after
            # the two names — league, cup or friendly decides whether
            # they turn over at all — so it is drawn to be read, not to
            # sit quietly under the name: an accent dot to lead the eye,
            # the mid weight, and PILL_INK, which holds its own against
            # the white above it instead of fading to a whisper like
            # MUTED did. The dot is the same accent the board already
            # marks "look here" with, so it reads as part of the board's
            # language rather than a new thing.
            pen.ellipse([head, sub_y - 4, head + 8, sub_y + 4],
                        fill=accent)
            draw_text(pen, (head + 18, sub_y),
                      clipped(beneath, under, channel_x - head - 38,
                              weight="mid"),
                      under, PILL_INK, anchor="lm", weight="mid")
        y += height

    left_out = len(events) - len(rows)
    if left_out > 0:
        draw_text(pen, (W - PAD, H - PAD + 8), f"+{left_out} مباراة أخرى",
                  20, MUTED, anchor="rs")
    progress(pen, page, pages, accent)
    return board
