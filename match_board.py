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

import math
import os
import re
from datetime import date, datetime, timedelta

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
# The clock well in the header, left of the date chip. The encoder paints
# the live digits inside it, so the geometry is a constant both files read
# rather than something one of them measures.
CLOCK_W = 132
CLOCK_H = 44
CLOCK_BOX = [W - PAD - 214 - CLOCK_W, PAD - 6,
             W - PAD - 214, PAD - 6 + CLOCK_H]

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
NEXT_TAG = (23, 133, 116, 255)   # the التالي pill: the coming green, white letters
PILL = (31, 47, 72, 255)
CHANNEL_BAR = (23, 78, 166, 255)   # the lit bar that names the broadcaster
CHANNEL_EDGE = (64, 132, 224, 255)
PILL_INK = (186, 207, 233, 255)

# THE COMPETITION'S OWN COLOUR. A board carries a league, a cup, a
# friendly and a practice session in the same column, and they all read
# the same. Each competition is given a colour of its own — chosen from
# its name, so the same competition is always the same colour on every
# board and the picture stays byte-stable — and the second line of a row
# wears it as a chip. A viewer looking for the league sees a colour
# before they read a word.
COMP_TAGS = (
    (56, 130, 246), (168, 85, 247), (245, 158, 11), (16, 185, 129),
    (236, 72, 153), (20, 184, 166), (248, 113, 113), (129, 140, 248),
)


# THE COMPETITIONS A READER LOOKS FOR FIRST wear a colour of their own
# rather than one drawn from their name, asked for in those words. Three
# families, and not one of them is red — red belongs to the live mark, and
# a league wearing it would argue with the indicator beside it.
#
#   gold      the ones watched for: boxing, MMA, F1, the Premier League,
#             the Champions League and UEFA's competitions, La Liga
#   sky       NBA and NFL
#   mint      WNBA and MLB
#
# Everything else keeps the colour its own name gives it.
COMP_FAMILIES = (
    (re.compile(
        r"boxing|\bmma\b|\bufc\b|bellator|\bpfl\b|contender series|"
        r"formula\s*1|\bf1\b|grand prix|"
        r"premier league|\bepl\b|champions league|europa|uefa|"
        r"conference league|nations league|super cup|la\s*liga|laliga|"
        r"ملاكمة|فنون قتالية|فورمولا|دوري أبطال أوروبا|"
        r"الدوري الإنجليزي|الدوري الإسباني|الدوري الأوروبي", re.I),
     (250, 204, 21)),
    (re.compile(r"\bnba\b|\bnfl\b|national football league", re.I),
     (56, 189, 248)),
    (re.compile(r"\bwnba\b|\bmlb\b|world series|major league baseball",
                re.I),
     (52, 211, 153)),
)


def comp_colour(name: str):
    """A competition's colour: its family's, or the one its name gives it."""
    text = name or ""
    for pattern, colour in COMP_FAMILIES:
        if pattern.search(text):
            return colour
    total = sum(ord(ch) for ch in text)
    return COMP_TAGS[total % len(COMP_TAGS)]


def dim(colour, share: float = 0.22):
    """The same colour, dark enough to sit a bright word on."""
    return tuple(int(round(c * share)) for c in colour[:3]) + (255,)


def readable(colour, share: float = 0.55):
    """The same colour, lifted far enough toward white to be READ.

    A competition's family colour is chosen to tell one competition from
    another at a glance, and on a light ground it does that well. On this
    board's navy panels a saturated blue or green at 13px is a smudge —
    photographed off a television across a room, the competition line
    under each fixture could not be made out at all, which is the one
    line that says WHICH tournament a viewer is looking at.

    So the hue is kept, because the hue is the whole point of it, and the
    colour is mixed toward white until it clears the panel behind it.
    """
    return tuple(int(round(c + (255 - c) * share))
                 for c in colour[:3]) + (255,)


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


# WHICH DAY THIS BOARD IS, AND IT IS NOT A FOOTNOTE. The reel turns
# through four pages of today and as many again of tomorrow, and the
# only thing saying which was 15px of accent text in the far right
# corner — "غداً · الأربعاء", set smaller than a channel name. It is now
# a chip in the middle of the heading line, set half again as large, and
# it carries a colour of its own for each day so a viewer glancing up
# has the answer before the words are read.
#
# None of the three is a colour a pill already owns: the red is مباشر,
# the green التالي and the slate انتهى, so the day cannot be mistaken
# for the state of a row.
A_DAY_COLOUR = {
    0: (245, 158, 11, 255),      # اليوم — amber
    1: (56, 189, 248, 255),      # غداً — sky
    2: (167, 139, 250, 255),     # بعد غد — violet
}
ANOTHER_DAY = (129, 140, 168, 255)
DAY_INK = (9, 15, 26, 255)       # dark letters, because the chip is bright


def draw_day_chip(pen, day: date, now: datetime, viewer, weekday: str,
                  y: int, *, clear_of: int) -> None:
    """The day, as a chip in the middle of the line it sits on."""
    words = day_badge(day, now, viewer, weekday)
    away = (day - now.astimezone(viewer).date()).days
    tone = A_DAY_COLOUR.get(away, ANOTHER_DAY)
    size, high = 22, 36
    wide = width_of(words, size, weight="heavy") + 44
    x = max(clear_of, (W - wide) // 2)
    x = min(x, W - PAD - wide)
    pen.rounded_rectangle([x, y - high // 2, x + wide, y + high // 2],
                          radius=high // 2, fill=tone)
    draw_text(pen, (x + wide // 2, y + 1), words, size, DAY_INK,
              anchor="mm", weight="heavy")


def day_badge(day: date, now: datetime, viewer, weekday: str) -> str:
    """Which of the three days this board is, said in words.

    No digits: the date is already set on the right, and a number inside
    Arabic is the one thing that can come out reversed.
    """
    away = (day - now.astimezone(viewer).date()).days
    relative = RELATIVE_DAY.get(away, "")
    return f"{relative} · {weekday}" if relative else weekday


# ---- crests ------------------------------------------------------------
# A MATCH IS TWO CLUBS, SO THE ROW SHOWS TWO CLUBS. The board used to
# print "Real Madrid CF - FC Internazionale Milano" as one run of text,
# and a viewer across a room read a grey line rather than a fixture.
# Each side now carries its crest, the two are set either side of a VS,
# and a club whose crest cannot be found wears a lettered disc in a
# colour taken from its own name — never a hole where a badge should be.
try:
    import team_badges
except Exception:                                # pragma: no cover
    team_badges = None

SPLIT = re.compile(r"\s+(?:vs\.?|VS\.?|[-–—x×])\s+")
_CRESTS: dict[tuple[str, str, int], object] = {}

# THE SECOND CHANNEL IS NOT ALL FIXTURES, and drawing it as if it were
# is worse than drawing nothing: "Italian Grand Prix - Practice 2" was
# set as a match between a Grand Prix and a practice session, each with
# a lettered disc for a crest, VS between them. Some of its rows ARE two
# competitors — "Ruiz vs Knyba", "Lakers - Celtics" — so the answer is
# not to switch the mirror off, it is to ask whether each SIDE is the
# name of a competitor at all. A session, a round, a discipline or a
# tournament stage is not, and a side carrying one of these words is
# refused; both sides must pass before a row is set as a fixture.
NOT_A_SIDE = re.compile(
    r"\b(practice|qualifying|qualification|sprint|race|grand\s*prix|gp|"
    r"free\s*practice|fp\d|q\d|round|rd|stage|leg|heat|session|"
    r"final|finals|semi[- ]?finals?|quarter[- ]?finals?|"
    r"singles|doubles|mixed|men'?s|women'?s|day\s*\d|"
    r"championship|tournament|cup|open|classic|masters|series|"
    r"سباق|تجارب|تصفيات|الجولة|الدور|نهائي|بطولة|فردي|زوجي)\b", re.I)


def looks_like_a_side(name: str) -> bool:
    """Whether one half of a split title is plausibly a competitor."""
    if len(name) < 2 or len(name) > 34:
        return False
    if NOT_A_SIDE.search(name):
        return False
    # A SIDE THAT STILL HOLDS A SEPARATOR IS NOT ONE NAME. The title is
    # split once, so a title carrying two separators leaves the second
    # inside the right-hand side — and that side is then drawn as a
    # single competitor, crest and all. Photographed off the television:
    #
    #     Berisha            VS      Pasley - Meta Apex
    #
    # Meta Apex is the hall the card is fought in, not half of the man's
    # name. Nothing here needs to know that: a competitor is one name,
    # and one name does not contain a fixture's own "v" or dash. Such a
    # row falls back to its whole title, centred, which is what it is.
    if SPLIT.search(name):
        return False
    # A competitor is named in a word or three, not a sentence.
    return len(name.split()) <= 4


# What a broadcaster puts in FRONT of a fight — "Live Boxing Ruiz vs
# Knyba", "UFC 300: Jones vs Miocic". The lead belongs to the event, not
# to the man on the left of it, and left on his name it made the row
# read as a club called "Live Boxing Ruiz".
LEAD = re.compile(
    r"^\s*(?:[^:]{2,40}:\s*|(?:live\s+)?(?:boxing|mma|ufc|wwe|tennis|"
    r"basketball|nba|nfl|mlb|nhl|f1|formula\s*1|"
    r"ملاكمة|نزال|تنس|كرة\s*سلة)\s+)+", re.I)


def trim_lead(name: str) -> str:
    """A competitor's name with the broadcaster's billing taken off."""
    cut = LEAD.sub("", name or "").strip(" .-–—:")
    return cut or (name or "").strip()


# A TITLE THAT IS AN EVENT, NOT A FIXTURE. A race, a tour, a stage, a
# memorial, a named meeting or a season week is ONE thing happening,
# and the dash inside its name is punctuation rather than a fixture's
# "v". "2026 Giro della Toscana - Memorial Alfredo Martini" was drawn
# as a club called Giro playing a club called Memorial. Any of these
# words anywhere in the title, or a four-digit year, and the row is an
# event: one name, centred, no crests and no VS.
NOT_A_FIXTURE = re.compile(
    r"\b(giro|tour|vuelta|rally|rallye|marathon|memorial|trophy|"
    r"grand\s*prix|classica|classic|cycling|criterium|etape|"
    r"open|masters|championships?|tournament|series|festival|"
    r"stage|round|session|practice|qualifying|sprint|heat|"
    r"week\s*\d|season|preview|primetime|show|special|"
    r"سباق|طواف|مرحلة|بطولة|جولة)\b"
    r"|\b(?:19|20)\d{2}\b", re.I)


def split_sides(title: str):
    """The two sides of a fixture, or nothing if it is not one."""
    if NOT_A_FIXTURE.search(title or ""):
        return None
    parts = SPLIT.split(title or "", maxsplit=1)
    if len(parts) != 2:
        return None
    home, away = (trim_lead(part) for part in parts)
    if not home or not away:
        return None
    if not (looks_like_a_side(home) and looks_like_a_side(away)):
        return None
    return home, away


def crest(name: str, box: int, context: str = ""):
    """The club's crest at the size the row can hold, or None."""
    key = (name, context, box)
    if key in _CRESTS:
        return _CRESTS[key]
    image = None
    if team_badges is not None:
        try:
            found = team_badges.badge(name, context=context)
        except Exception:
            found = None
        if found is not None:
            found = found.copy()
            found.thumbnail((box, box), Image.LANCZOS)
            image = found
    _CRESTS[key] = image
    return image


# THE TWO EMPTY BOXES WHERE A FLAG SHOULD BE. A flag emoji is not a
# glyph — it is two regional-indicator letters a font is expected to
# join — and none of the faces this board can reach carries either of
# them. The Turkish channel's masthead therefore read "▯▯ TURKISH PPV"
# on the television. No font this build can install will fix that, so
# the flag is DRAWN rather than typed, and a country with no drawing has
# its emoji dropped instead of printed as boxes.
A_FLAG = re.compile("[\U0001F1E6-\U0001F1FF]{2}")

TURKISH_RED = (227, 10, 23, 255)


def flag_code(pair: str) -> str:
    """"🇹🇷" -> "TR". The pair is two letters written in another block."""
    return "".join(chr(ord(letter) - 0x1F1E6 + ord("A")) for letter in pair)


def flag_art(code: str, height: int):
    """A country's flag drawn at this height, or None for one not drawn.

    Turkey's is built to its own law rather than by eye: Flag Law No.
    2893 fixes every measure as a fraction of the hoist — the crescent's
    outer circle centred at 0.5 of it and half of it across, the inner
    circle at 0.5625 and 0.4 across, the star's circle at 0.815 and a
    quarter across — and the star turns one point toward the crescent.
    Drawn at four times the size and brought back down, because a
    crescent is two circles subtracting and their edge is the whole
    shape.
    """
    if code != "TR" or height < 8:
        return None
    over = 4
    tall = height * over
    wide = int(round(tall * 1.5))
    art = Image.new("RGBA", (wide, tall), TURKISH_RED)
    pen = ImageDraw.Draw(art)

    def circle(at: float, across: float, fill) -> None:
        radius = across * tall / 2
        middle = at * tall
        pen.ellipse([middle - radius, tall / 2 - radius,
                     middle + radius, tall / 2 + radius], fill=fill)

    circle(0.5, 0.5, WHITE)
    circle(0.5625, 0.4, TURKISH_RED)

    middle, radius = 0.815 * tall, 0.125 * tall
    star = []
    for step in range(10):
        angle = math.pi + step * math.pi / 5
        # the notch of a five-pointed star, sin(18°) / sin(126°)
        reach = radius if step % 2 == 0 else radius * 0.38197
        star.append((middle + reach * math.cos(angle),
                     tall / 2 + reach * math.sin(angle)))
    pen.polygon(star, fill=WHITE)
    return art.resize((wide // over, tall // over), Image.LANCZOS)


def a_masthead(title: str, height: int):
    """The channel name as it is drawn, and the flag drawn beside it."""
    art = None
    found = A_FLAG.search(title)
    if found:
        art = flag_art(flag_code(found.group(0)), height)
        title = A_FLAG.sub("", title).strip()
    return title, art


def initials(name: str) -> str:
    words = [word for word in re.split(r"[\s.]+", name) if word]
    letters = "".join(word[0] for word in words if word[0].isalnum())
    return (letters[:2] or name[:2]).upper()


def draw_crest(board, pen, name, cx, cy, box, context=""):
    """A club's badge at (cx, cy), or its letters in its own colour."""
    image = crest(name, box, context=context)
    if image is not None:
        board.alpha_composite(image, (cx - image.width // 2,
                                      cy - image.height // 2))
        return
    tone = comp_colour(name) + (255,)
    half = box // 2
    pen.ellipse([cx - half, cy - half, cx + half, cy + half],
                fill=dim(tone, 0.30), outline=tone, width=2)
    draw_text(pen, (cx, cy), initials(name), max(12, box // 2 - 2), tone,
              anchor="mm", weight="heavy")


CHANNEL_ZONE = 300


def without_repeats(events: list[dict]) -> list[dict]:
    """One match drawn once, whichever script each page wrote it in.

    An Arabic federation page and an English listing describe the same
    fixture — الوحدات - الفيصلي and "Al Wehdat - Al Faisaly" — and when
    the two pages round the kickoff differently, both reach the board and
    sit one under the other. The guide's own cross-script club test
    settles it here, at the last moment before ink: same two clubs
    inside ninety minutes is one match, the first spelling stays, and
    the second hands over any channel the first did not have so nothing
    a viewer could watch is lost with it.
    """
    try:
        from epg_lib import club_skeleton, same_club
    except Exception:                            # pragma: no cover
        return events

    def bones(name: str) -> str:
        # THE VOWELS ARE WHERE THE TWO SPELLINGS DISAGREE, and only
        # there: "Al Faisaly" reduces to fasala and الفيصلي to fasla,
        # one letter apart and refused, while the consonants — f s l —
        # are identical because they are what the Arabic actually
        # writes. Comparing the bones catches the pair the strict test
        # drops, and it is only ever asked after BOTH sides have been
        # paired, at one kickoff, so two clubs sharing consonants
        # cannot collide unless they somehow play the same opponent at
        # the same minute.
        return re.sub(r"[aeiou]", "", club_skeleton(name) or "")

    def pair(one: str, two: str) -> bool:
        if same_club(one, two):
            return True
        left, right = bones(one), bones(two)
        return len(left) >= 3 and left == right
    window = timedelta(minutes=90)
    kept: list[dict] = []
    for event in events:
        sides = split_sides(event.get("title", ""))
        twin = None
        if sides:
            for already in kept:
                other = split_sides(already.get("title", ""))
                if not other:
                    continue
                if abs(already["start"] - event["start"]) > window:
                    continue
                straight = pair(sides[0], other[0]) and pair(sides[1],
                                                             other[1])
                reversed_ = pair(sides[0], other[1]) and pair(sides[1],
                                                              other[0])
                if straight or reversed_:
                    twin = already
                    break
        if twin is None:
            kept.append(event)
        else:
            for channel in event.get("channels", []):
                if channel not in twin["channels"]:
                    twin["channels"].append(channel)
    return kept


def _crest_strip(board, pen, events, y: int, accent) -> None:
    """The band of crests along the foot, the way a channel's info screen
    signs itself off with the competitions it carries."""
    seen, marks = set(), []
    for event in events:
        sides = split_sides(event["title"])
        for name in (sides or ()):
            key = name.lower()
            if key in seen:
                continue
            art = crest(name, 30, context=event.get("competition", ""))
            if art is not None:
                seen.add(key)
                marks.append(art)
        if len(marks) >= 12:
            break
    if not marks:
        return
    gap = 46
    left = (W - (len(marks) * gap - (gap - 30))) // 2
    faint = Image.new("RGBA", board.size, (0, 0, 0, 0))
    for index, art in enumerate(marks):
        faint.paste(art, (left + index * gap, y), art)
    board.alpha_composite(Image.blend(Image.new("RGBA", board.size,
                                                (0, 0, 0, 0)), faint, 0.75))


def _span_for(event, live_for):
    """How long THIS row is on the air.

    `live_for` may be a plain duration, as it always was, or a function of
    the row — which is how a sport's own length reaches the drawing.
    """
    try:
        return live_for(event) if callable(live_for) else live_for
    except Exception:                                          # noqa: BLE001
        return live_for


def _is_live(event, now, live_for) -> bool:
    return event["start"] <= now < event["start"] + _span_for(event, live_for)


def _is_over(event, now, live_for) -> bool:
    return event["start"] + _span_for(event, live_for) <= now


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
    events = without_repeats([dict(event) for event in events])
    board = backdrop()
    pen = ImageDraw.Draw(board)

    # ---- header ---------------------------------------------------------
    draw_mark(pen, PAD, PAD - 6, 76, accent)
    x = PAD + 76 + 24

    head, badge = a_masthead(title, 34)
    if badge:
        board.alpha_composite(badge, (x, PAD + 18 - badge.height // 2))
        x += badge.width + 16
    draw_text(pen, (x, PAD - 4), head, 46, WHITE)
    # THE DAY CHIP SITS ON THIS LINE TOO, in the middle of the board, so
    # the subtitle is given the room the chip leaves it and no more. It
    # was drawn at full length underneath and the chip was drawn on top
    # of it: on the board on air, "الدوري الأمريكي للسلة والقدم
    # الأمريكية" reached the middle of the screen and the chip covered
    # its first word. Cut with an ellipsis is a subtitle a viewer can
    # read the start of; painted over is one they cannot read at all.
    chip_words = day_badge(day, now, viewer, weekday)
    chip_wide = width_of(chip_words, 26) + 60
    draw_text(pen, (x, PAD + 52),
              clipped(subtitle, 21, (W - chip_wide) // 2 - x - 24,
                      thin=True), 21, MUTED, thin=True)

    right = W - PAD
    date_chip(pen, right, PAD - 6, f"{day:%d.%m.%Y}")
    # THE CLOCK. A board is a still picture, so the digits are painted on
    # frame by frame by the encoder (match_screen_video) and tick while
    # the channel is playing. All that is drawn here is the well they sit
    # in, at CLOCK_BOX - the one geometry both files agree on.
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
    badge = chip_words
    badge_size = 26
    wide = chip_wide
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

    # A THIN DAY SHOULD NOT LEAVE HALF A SCREEN EMPTY. The row height
    # was fixed, so five matches sat in the top third of the board and
    # the bottom two thirds were bare ground — on a television, across a
    # room, that reads as a broken page. The rows grow into the room
    # they have, up to a ceiling that keeps a card looking like a card,
    # and whatever is still spare is split above and below so the block
    # sits in the middle of the board rather than hanging from its top.
    if len(rows) * height < room:
        # 130 RATHER THAN 96. This channel's quiet nights are most of its
        # nights — one, two, three games — and a 96px card in 502px of
        # room read off a television as one row adrift in black ground,
        # which is the fault the other board was rebuilt for. A row may
        # now grow half again as far, and the type inside it grows with
        # it rather than staying at the size a 55px row already reached.
        height = min(130, room // len(rows))
    # Whatever room is still spare is spread as air between the cards
    # rather than left in one dead block at the foot of the screen, so a
    # three-match day breathes down the whole board instead of stopping
    # a third of the way and leaving the rest bare.
    spare = max(0, room - len(rows) * height)
    lead = min(40, spare // (len(rows) + 1))
    spare -= lead * (len(rows) + 1)

    time_x, name_x = PAD + 128, PAD + 168
    y = top + 8 + lead + spare // 2

    # THE STATUS SLOT. One line for مباشر, التالي and انتهى — asked for
    # outright, twice, in the same breath: "التالي و المباشر مش على نفس
    # الخط" and "make them a bit smaller to make it fit inside the lines".
    # The old pill sat before the name only on live and finished rows, so
    # a live row's name started some ninety pixels right of its
    # neighbours', and the pill itself stood taller than the band it sat
    # in — on a two-line row the name line sits above centre, so the pill
    # rode up and poked through the row's own outline. One slot on every
    # row, the same width on every row, is the only shape in which
    # "on the air" and "next" can be read on the same line at all.
    tag_px = max(11, min(13, height - 30)) if height >= 42 else 11
    # The same width for all three words — the widest of them sets it —
    # so a مباشر pill and a التالي pill occupy exactly the same box and
    # the name behind them starts on exactly the same pixel.
    slot_w = max(width_of(word, tag_px, weight="mid")
                 for word in ("مباشر", "انتهى", "التالي")) + 18
    slot_x = name_x
    # The pill rides at the name line's height on a two-line row and the
    # row's middle on a one-line one — never above the band's top edge,
    # whatever the row's height: a pill that pokes out of the line is the
    # thing that was asked to stop.
    slot_half = min(tag_px + 5, (height - 6) // 2 - 2)
    today = day == now.astimezone(viewer).date()
    coming_seen = False

    for index, event in enumerate(rows):
        live = _is_live(event, now, live_for)
        # OVER, AND SAID SO IN RED. Asked for outright. A board carries
        # the whole day, so by the evening most of it has been played —
        # and every one of those rows was printing its clock in the same
        # green as the match that has not started yet. Green is the
        # colour this board uses for "coming"; a match that is finished
        # is not coming, and a viewer scanning for what is next was being
        # made to read every line to find out.
        over = _is_over(event, now, live_for)
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
        # THE CAPS WERE REACHED AT A 55px ROW, so every row from there to
        # the ceiling was drawn at one size — a card that grew with
        # letters that did not. Past 80px the larger caps apply; below it
        # nothing moves, so a full page is drawn exactly as it was. Held
        # by a hash: an eight-row page renders to the same bytes.
        tall_row = height >= 80
        size = (max(17, min(31 if tall_row else 25, height - 30)) if two
                else max(19, min(36 if tall_row else 28, height - 26)))
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
        # THE CLOCK IS THE COLUMN A BOARD IS SCANNED DOWN, so it is set
        # in the display weight and separated from the names by a
        # hairline: the eye runs down the times first and crosses to a
        # name only when one of them is the time it wanted.
        # THE KICKOFF IS A KEY, NOT A CAPTION. On a television board the
        # time is the one thing read from across a room, so it is set in
        # its own outlined tablet at the head of the row — a shape the
        # eye finds without reading, the way a departures board is read
        # by the column of times and not the column of destinations.
        clock_ink = LIVE_RED if live else (OVER if over else accent)
        clock_px = max(17, min(29 if tall_row else 23, height - 32))
        tab_h = min(clock_px + 16, height - 16)
        tab = [PAD + 4, middle - tab_h // 2, time_x + 22, middle + tab_h // 2]
        pen.rounded_rectangle(tab, radius=9, fill=dim(clock_ink),
                              outline=clock_ink, width=2)
        draw_text(pen, ((tab[0] + tab[2]) // 2, middle), clock, clock_px,
                  clock_ink, anchor="mm", weight="heavy")

        # THREE WORDS, ONE SLOT, ONE SIZE. The pill is drawn in the slot
        # every row carries, at the slot's fixed width: مباشر red for the
        # row on the air, التالي teal for the next kickoff on today's
        # board, انتهى slate for the finished one — and nothing drawn at
        # all for a plain upcoming row on a future day, where "next" is
        # every row and would say nothing. The word sits at the name
        # line's height on a two-line row and the row's middle on a
        # one-line one, and the box it sits in never stands taller than
        # the band around it — the pill that rode out of the row line was
        # the thing asked out of the picture.
        word, fill = "", LIVE_TAG
        # The pill sits at the name line's height where that is inside
        # the band, and at the band's own centre otherwise — a pill
        # centred on a line that sits near the band's edge is a pill
        # that pokes out of the row, which is the thing asked to stop.
        slot_y = min(max(head_y, y + 3 + slot_half),
                     y + height - 6 - 3 - slot_half)
        if live:
            word, fill = "مباشر", LIVE_TAG
        elif over:
            word, fill = "انتهى", OVER_TAG
        elif today and not coming_seen:
            # THE NEXT KICKOFF, SAID SO. The red room says "on now";
            # everything else on today's board is either finished or
            # waiting, and the waiting row a viewer is actually after is
            # the next one to kick off. It wears the coming green the
            # board has always used for a clock still to come, in the
            # same slot and the same size as the red word, so "which one
            # is next?" and "which one is on?" are answered on one line
            # by the same shape. Only the first upcoming row wears it —
            # a second التالي would be a second promise this board
            # cannot keep.
            word, fill = "التالي", NEXT_TAG
            coming_seen = True
        if word:
            pen.rounded_rectangle(
                [slot_x, slot_y - slot_half, slot_x + slot_w,
                 slot_y + slot_half],
                radius=slot_half, fill=fill)
            draw_text(pen, (slot_x + slot_w // 2, slot_y), word,
                      tag_px, WHITE, anchor="mm", weight="mid")
        # On a future day's board nothing is live or over and only one
        # row would wear التالي; leaving the slot empty on every row
        # would waste the widest word's width of name room, so the name
        # takes the slot's x on the days it is never used.
        head = slot_x + slot_w + 14 if (word or today) else name_x

        # THE CHANNELS BESIDE THE NAME, NOT UNDER IT. They used to drop
        # to the competition line on any row tall enough for two lines,
        # and a viewer photographing the board asked outright for them
        # back beside the name: the pills name where the game is
        # watched, which is the question the name asks, and a line of
        # channels under a match reads as a second event rather than an
        # answer. They sit at the row's middle now — the name's level on
        # a two-line row and the whole row on a one-line one — and the
        # competition keeps the second line to itself.
        pill_y = middle
        # SAME SIZE ON EVERY ROW, TWO LINES OR ONE. The size used to be
        # taken from the line the pills sat on, and a single-line row
        # had a larger font than a two-line one, so its pills were
        # larger too — Fox Nation measured 35px tall against DAZN's 22
        # beside it on the same board, and a viewer read the larger pill
        # as a louder channel. Every row's pills are drawn at the
        # two-line row's ceiling now, whichever line they sit on, so
        # the board has one size of channel and not two.
        pill_size = max(15, min(16, (under if two else size - 8) - 2))
        # The pill's half is capped to the band, as the status slot's
        # is — a channel pill that pokes out of the row line is the
        # same complaint the status pill earned.
        pill_half = min(pill_size, (height - 6) // 2 - 2)
        # THE CHANNELS KEEP A COLUMN OF THEIR OWN, always the same
        # width, so the VS down the middle of the board lands in one
        # straight line on every row instead of drifting with however
        # many channels a match happens to carry. Nothing is dropped:
        # every channel still shows, each one simply cut to its share
        # of the column when a match is on three of them at once.
        # WHERE TO WATCH IT IS ONE ANSWER, SO IT IS ONE BAR. Three
        # little grey lozenges of different widths made the right-hand
        # side of the board look like spare change; a broadcaster on a
        # real sports channel gets a lit bar the width of the column,
        # the same on every row, carrying every channel the match is on.
        # Nothing is dropped — two or three names share the bar.
        channel_x = W - PAD - CHANNEL_ZONE
        if shown_any := event["channels"][:3]:
            bar = [channel_x, middle - (pill_half + 4), W - PAD,
                   middle + (pill_half + 4)]
            pen.rounded_rectangle(bar, radius=8, fill=CHANNEL_BAR,
                                  outline=CHANNEL_EDGE, width=2)
            joined = clipped("  ·  ".join(shown_any), pill_size,
                             CHANNEL_ZONE - 24, weight="mid")
            draw_text(pen, ((bar[0] + bar[2]) // 2, middle), joined,
                      pill_size, WHITE, anchor="mm", weight="mid")

        # THE NAME STOPS WHERE THE CHANNELS BEGIN, on every row. When
        # the pills sat under the name it could run edge to edge, and
        # the events that needed the room were the ones that got it.
        # With the pills beside the name again — where a viewer asked
        # for them — the name gives way, and "US Open Men's & Women's
        # Singles 3rd Round and Women's Doubles 1st Round" is clipped
        # rather than written over its own channels. It shrinks first
        # and clips only past its own floor, as below.
        room_for_name = channel_x - head - 24

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
        # THE FIXTURE, DRAWN AS A FIXTURE. Where the row is tall enough
        # and the title really is two sides, it is set as crest, club,
        # VS, crest, club — the shape a viewer already reads on every
        # sports channel there is. Where it is not (a race, a session, a
        # one-name event, or a row squeezed thin by a full day) the
        # title is written as it always was.
        sides = split_sides(event["title"]) if height >= 52 else None
        drawn = False
        chip_left, chip_stop = head, channel_x - 60
        if sides:
            home, away = sides
            # A FIXTURE IS A MIRROR, AND THE BOARD IS SET LIKE ONE. The
            # home club runs out from the left with its crest first; the
            # away club runs back in from the right with its crest last;
            # VS holds the centre line, in the same place on every row,
            # so the eye reads straight down the middle of the board
            # instead of hunting for where one fixture ends. Each side
            # gets exactly half the span minus the VS gutter, so the two
            # can never meet in the middle whatever the names are.
            left_edge, right_edge = head, W - PAD - CHANNEL_ZONE - 24
            centre = (left_edge + right_edge) // 2
            crest_y = (head_y + middle) // 2 if two else middle
            # A CREST IS THE FASTEST THING ON THE ROW TO READ — a viewer
            # knows the arrowhead before they read "Kansas City" — so on
            # a row with the room it is not left at the size a 62px row
            # allows. The two bounds below still hold it inside the band.
            box = min(60 if tall_row else 44, 2 * (crest_y - y - 6),
                      2 * (y + height - 6 - crest_y))
            # AND IT BELONGS ON THE NAME'S OWN LINE, beside the التالي or
            # مباشر pill, which is already drawn there. It sat seven
            # pixels below both — measured, not guessed — so a row read
            # as a badge that had not lined up with its own words.
            #
            # It is raised to that line as far as it can go WITHOUT
            # shrinking: the size is settled first, and the crest then
            # takes the highest place that size still fits inside the
            # band. On a 130px row that is the name's line exactly. On a
            # 62px one the crest is already as high as it can sit, so
            # nothing moves and a full page is drawn as it was.
            crest_y = max(head_y, y + 6 + box // 2)
            gap, gutter = 12, 34
            side_room = centre - gutter - left_edge - box - gap
            fitted = size
            while fitted > 15 and max(width_of(home, fitted),
                                      width_of(away, fitted)) > side_room:
                fitted -= 1
            if box >= 22 and side_room > 60:
                # A played match steps back in grey; red is kept
                # for the clock, where it means "over" already.
                ink = PILL_INK if over else WHITE
                home_txt = clipped(home, fitted, side_room)
                away_txt = clipped(away, fitted, side_room)
                draw_crest(board, pen, home, left_edge + box // 2,
                           crest_y, box, event.get("competition", ""))
                chip_left = left_edge + box + gap
                draw_text(pen, (chip_left, head_y), home_txt, fitted, ink,
                          anchor="lm")
                draw_text(pen, (centre, head_y), "VS", max(14, fitted - 5),
                          LIVE_TAG if live else MUTED, anchor="mm",
                          weight="heavy")
                draw_crest(board, pen, away, right_edge - box // 2,
                           crest_y, box, event.get("competition", ""))
                draw_text(pen, (right_edge - box - gap, head_y), away_txt,
                          fitted, ink, anchor="rm")
                chip_stop = centre - gutter
                drawn = True
        if not drawn:
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
            #
            # The line still stops where the pills' lowest edge hangs,
            # because the pills sit at the row's middle now and their
            # bottom band crosses this line's height on the right — the
            # dot leads the eye from the left and the text never runs
            # under a channel.
            # The competition wears its own colour as a chip, so four
            # leagues on one board are four colours and not four grey
            # lines. The colour comes from the competition's name, so it
            # never changes between builds and the board stays byte for
            # byte the same unless the day did.
            tone = comp_colour(beneath) + (255,)
            label = clipped(beneath, under, max(60, chip_stop - chip_left),
                            weight="mid")
            # THE COMPETITION WHISPERS. It was a filled colour chip, and
            # a board with eight of them read as a bag of sweets; the
            # row's own furniture — the time tablet and the broadcaster
            # bar — carries the colour now, and the league is simply set
            # quietly under the home club, where a viewer looks only
            # when they want it.
            draw_text(pen, (chip_left, sub_y), label, under, tone,
                      anchor="lm", weight="mid")
        y += height + lead

    left_out = len(events) - len(rows)
    if left_out > 0:
        draw_text(pen, (W - PAD, H - PAD + 8), f"+{left_out} مباراة أخرى",
                  20, MUTED, anchor="rs")
    progress(pen, page, pages, accent)
    return board


def draw_board_info(day: date, events: list[dict], now: datetime, viewer,
               live_for, *, title: str, subtitle: str, weekday: str,
               page: int = 1, pages: int = 1, accent=None) -> Image.Image:
    """The whole board, laid out the way a broadcaster's info channel is.

    THE 2026 INFO-SCREEN REDRAW. A list of eight identical boxes is a
    spreadsheet; the screens a viewer actually recognises — beIN CONNECT
    INFO, S SPORT+ INFO — are built the other way round: the channel's
    name set large across the top, what is ON AIR right now in its own
    panel on the reading side, what is COMING listed beside it, and the
    competitions signed along the foot. That is this board now.
    """
    accent = accent or ACCENT
    events = without_repeats([dict(event) for event in events])
    board = backdrop()
    pen = ImageDraw.Draw(board)

    # ---- masthead -------------------------------------------------------
    draw_mark(pen, PAD, 30, 54, accent)
    head, badge = a_masthead(title, 30)
    head = head.upper() if not ARABIC.search(head) else head
    beside = badge.width + 16 if badge else 0
    head = clipped(head, 40, 720 - beside, weight="heavy")
    span = width_of(head, 40, weight="heavy") + beside
    x = (W - span) // 2
    if badge:
        board.alpha_composite(badge, (x, 52 - badge.height // 2))
        x += beside
    draw_text(pen, (x, 52), head, 40, WHITE, anchor="lm", weight="heavy")
    if subtitle:
        draw_text(pen, (W // 2, 84), clipped(subtitle, 17, 760, thin=True),
                  17, MUTED, anchor="mm", thin=True)
    stamp = f"{weekday} · {day:%d.%m.%Y}"
    draw_text(pen, (W - PAD, 46), stamp, 20, WHITE, anchor="rm", weight="mid")
    count = (arabic_count(len(events), "مباراة", "مبارياتان", "مباريات",
                          "مباراة") if events else "لا توجد مباراة")
    if pages > 1:
        count = f"{count} · {page}/{pages}"
    draw_text(pen, (W - PAD, 72), count, 14, MUTED, anchor="rm", thin=True)
    pen.line([(PAD, 112), (W - PAD, 112)], fill=RULE, width=1)
    pen.rounded_rectangle([PAD, 110, PAD + 150, 114], radius=2, fill=accent)

    foot = H - 104
    if not events:
        draw_text(pen, (W // 2, H // 2), "لا توجد مباراة معلنة اليوم",
                  30, MUTED, anchor="mm")
        progress(pen, page, pages, accent, y=H - 26)
        return board

    live_rows = [e for e in events if _is_live(e, now, live_for)]
    rest = [e for e in events if e not in live_rows]

    # ---- ON AIR, its own panel on the left ------------------------------
    # THE COLUMN IS ONLY WORTH ITS WIDTH WHEN SOMETHING IS IN IT. On a
    # channel whose night has not started, this held 372px of empty panel
    # against a list of three rows crushed into what was left — reported
    # off the television as "too small". With nothing on air the left
    # column keeps just enough to say so, and the list takes the rest.
    #
    # AND A NIGHT WHERE EVERYTHING IS ON AT ONCE. The panel drew four
    # cards and stopped: with eight simultaneous matches the heading
    # counted eight, four were drawn nowhere at all, and the COMING
    # column sat empty across two thirds of the screen. So the panel is
    # sized from what it has to hold — it takes the whole width in two
    # lanes when nothing is coming — and a card that still does not fit
    # falls into the list beside it rather than off the board.
    top = 140
    foot_of_panel = foot - (top + 28)
    STEP = 12
    GUTTER = 24

    def cards_that_fit(height: int) -> int:
        """How many cards of this height one lane of the panel holds."""
        return max(1, (foot_of_panel + STEP) // (height + STEP))

    lanes = (2 if live_rows and not rest
             and len(live_rows) > cards_that_fit(92) else 1)
    tall = lanes == 1 and len(live_rows) <= 2
    card_h = 148 if tall else 92
    per_lane = cards_that_fit(card_h)
    if lanes == 2:
        # five on air reads as 3 + 2, not as a full lane and a stray
        per_lane = min(per_lane, -(-len(live_rows) // lanes))

    spill = live_rows[per_lane * lanes:]
    live_rows = live_rows[:per_lane * lanes]
    if spill:
        rest = sorted(rest + spill, key=lambda e: e["start"])

    # WHEN NOTHING IS ON AIR, THE COLUMN IS NOT WORTH A COLUMN. It kept
    # 196px and a heading of its own purely to say it was empty, and the
    # list read the whole night in what was left — reported off the
    # television as small twice over. On a quiet board the note moves
    # onto the heading line and the list takes the full width.
    quiet = not live_rows
    col = PAD + (372 if live_rows else 0)
    if lanes == 2:
        col = W - PAD
    span = (col - PAD) - (28 if lanes == 1 else 0)
    lane_w = (span - GUTTER * (lanes - 1)) // lanes
    heading_ends = PAD
    if not quiet:
        draw_text(pen, (PAD, top), "على الهواء الآن", 22, WHITE, anchor="lm",
                  weight="mid")
        dot_x = PAD + width_of("على الهواء الآن", 22, weight="mid") + 18
        pen.ellipse([dot_x, top - 5, dot_x + 10, top + 5], fill=LIVE_TAG)
        draw_text(pen, (dot_x + 18, top + 1), "LIVE", 13, LIVE_RED,
                  anchor="lm", weight="mid")
        heading_ends = dot_x + 18 + width_of("LIVE", 13, weight="mid")

    y = top + 28
    # THE LIVE CARD IS THE POINT OF THE BOARD, so it is not the smallest
    # thing on it. Once the coming rows were allowed to grow, a fixture
    # actually ON AIR sat in a 92px card beside 118px rows — the one row
    # a viewer is looking for, drawn smaller than the ones they are not.
    # With one or two live it takes the room the column has.
    for index, event in enumerate(live_rows):
        lane, slot = divmod(index, per_lane)
        x = PAD + lane * (lane_w + GUTTER)
        y = top + 28 + slot * (card_h + STEP)
        card = [x, y, x + lane_w, y + card_h]
        pen.rounded_rectangle(card, radius=12, fill=LIVE_BG,
                              outline=LIVE_TAG, width=2)
        pen.rounded_rectangle([card[0], card[1] + 10, card[0] + 6,
                               card[3] - 10], radius=3, fill=LIVE_TAG)
        inner = card[0] + 20
        room = card[2] - inner - 16
        clock_y = y + (30 if tall else 24)
        draw_text(pen, (inner, clock_y),
                  event["start"].astimezone(viewer).strftime("%H:%M"),
                  24 if tall else 17, LIVE_RED, anchor="lm", weight="heavy")
        # THE WORD ITSELF, on the card, in the language the board is in.
        # The header says LIVE once for the whole column; a viewer
        # scanning a card wants it on the card.
        if tall:
            word = "مباشر"
            wide = width_of(word, 15, weight="mid") + 26
            pill = [card[2] - 16 - wide, clock_y - 14, card[2] - 16,
                    clock_y + 14]
            pen.rounded_rectangle(pill, radius=14, fill=LIVE_TAG)
            draw_text(pen, ((pill[0] + pill[2]) // 2, clock_y), word, 15,
                      WHITE, anchor="mm", weight="mid")
        name = size_that_fits(event["title"], 30 if tall else 24,
                              16, room)
        draw_text(pen, (inner, y + (72 if tall else 52)),
                  clipped(event["title"], name, room),
                  name, WHITE, anchor="lm", weight="mid")
        comp = norm_line(event.get("competition"))
        if comp:
            if tall:
                # its own line, not squeezed beside the clock
                draw_text(pen, (inner, y + 102),
                          clipped(comp, 17, room, weight="mid"), 17,
                          readable(comp_colour(comp)), anchor="lm",
                          weight="mid")
            else:
                draw_text(pen, (card[2] - 16, y + 24),
                          clipped(comp, 15, room - 90, weight="mid"), 15,
                          readable(comp_colour(comp)), anchor="rm",
                          weight="mid")
        if event["channels"]:
            draw_text(pen, (inner, y + (128 if tall else 76)),
                      clipped("  ·  ".join(event["channels"][:3]),
                              16 if tall else 14, room, weight="mid"),
                      16 if tall else 14, PILL_INK, anchor="lm",
                      weight="mid")

    if lanes == 2:
        draw_day_chip(pen, day, now, viewer, weekday, top,
                      clear_of=heading_ends + 30)
        # the panel is the board; there is no list to rule off from
        progress(pen, page, pages, accent, y=H - 14)
        pen.line([(PAD, foot + 34), (W - PAD, foot + 34)], fill=RULE,
                 width=1)
        _crest_strip(board, pen, events, foot + 44, accent)
        draw_text(pen, (W - PAD, H - 10), SIGNATURE, 13, RULE, anchor="rs",
                  thin=True)
        return board

    if not quiet:
        pen.line([(col, top - 14), (col, foot)], fill=RULE, width=1)

    # ---- COMING, listed on the right ------------------------------------
    left = col + (0 if quiet else 30)
    draw_text(pen, (left, top), "البث القادم", 22, WHITE, anchor="lm",
              weight="mid")
    heading_ends = left + width_of("البث القادم", 22, weight="mid")
    if quiet:
        note = heading_ends + 20
        pen.ellipse([note, top - 5, note + 10, top + 5], fill=RULE)
        draw_text(pen, (note + 18, top + 1), "لا يوجد بث مباشر الآن", 15,
                  MUTED, anchor="lm", thin=True)
        heading_ends = note + 18 + width_of("لا يوجد بث مباشر الآن", 15,
                                            thin=True)
    draw_day_chip(pen, day, now, viewer, weekday, top,
                  clear_of=heading_ends + 30)

    y = top + 28
    room = foot - y
    shown = rest
    # A BOARD IS NOT A BAND ACROSS THE TOP. The ceiling here was 64px, so
    # three rows filled a fifth of the screen and left the rest black —
    # photographed and reported as exactly that. A row may now grow to
    # 118px, which is what a nearly empty night needs and what gives the
    # title, the competition, the channels and the مباشر pill room to sit
    # apart instead of on top of one another.
    height = max(40, min(118, room // max(1, len(shown))))
    if len(shown) * height > room:
        shown = rest[:max(1, room // 40)]
        height = room // len(shown)

    # TYPE THAT GROWS WITH THE ROW, not two sizes with a cliff between
    # them. The cliff sat at 78px, and a full page of eight puts a row
    # at 56 — so every size on a full board fell to the small step and
    # stayed there: 20px fixtures and 13px channels, read across a room
    # off a television and reported as small twice. Each size is now
    # taken from the row's own height and clamped at both ends, so a row
    # is always as large as the room it actually has.
    def fits(share: float, least: int, most: int) -> int:
        return max(least, min(most, int(height * share)))

    clock_size = fits(0.34, 20, 28)
    name_size = fits(0.40, 22, 34)
    comp_size = fits(0.26, 16, 22)
    chan_size = fits(0.24, 15, 18)
    tag_size = fits(0.22, 13, 16)

    # A SHORT NIGHT SITS IN THE MIDDLE, not in a band under the heading
    # with the rest of the screen black beneath it. Whatever the rows do
    # not use is split above and below them, so three fixtures read as a
    # board that was laid out for three rather than as a board that lost
    # its other five.
    spare = room - len(shown) * height
    if spare > 0:
        y += spare // 2

    today = day == now.astimezone(viewer).date()
    coming = False
    for index, event in enumerate(shown):
        over = _is_over(event, now, live_for)
        # A ROW THAT SPILLED OUT OF A FULL PANEL IS STILL ON AIR, and a
        # list that told a viewer it was "next" would be lying about the
        # one thing this board exists to say.
        on_air = not over and event["start"] <= now
        band = [left, y, W - PAD, y + height - 6]
        pen.rounded_rectangle(band, radius=8,
                              fill=LIVE_BG if on_air else
                              (OVER_BG if over else
                               (PANEL if index % 2 == 0 else PANEL_ALT)))
        pen.rounded_rectangle([band[0], band[1] + 5, band[0] + 4,
                               band[3] - 5], radius=2,
                              fill=LIVE_TAG if on_air else
                              (OVER_TAG if over else accent))
        middle = y + (height - 6) // 2
        ink = PILL_INK if over else WHITE

        clock = event["start"].astimezone(viewer).strftime("%H:%M")
        draw_text(pen, (left + 18, middle), clock, clock_size,
                  LIVE_RED if on_air else
                  (OVER_TAG if over else accent), anchor="lm",
                  weight="heavy")
        # the fixture starts clear of the clock, whatever size it took
        text_x = left + 18 + width_of("00:00", clock_size,
                                      weight="heavy") + 26
        tag = ""
        if over:
            tag = "انتهى"
        elif on_air:
            tag = "مباشر"
        elif today and not coming:
            tag, coming = "التالي", True
        chan = "  ·  ".join(event["channels"][:3])
        chan_room = 340 if height >= 66 else 260
        chan_w = (min(chan_room, width_of(chan, chan_size, weight="mid"))
                  if chan else 0)
        if chan:
            draw_text(pen, (W - PAD - 16, middle),
                      clipped(chan, chan_size, chan_room, weight="mid"),
                      chan_size, MUTED if over else PILL_INK,
                      anchor="rm", weight="mid")
        stop = W - PAD - 30 - chan_w
        if tag:
            half = tag_size // 2 + 6
            wide = width_of(tag, tag_size, weight="mid") + tag_size + 8
            pen.rounded_rectangle([stop - wide, middle - half, stop,
                                   middle + half], radius=half,
                                  fill=LIVE_TAG if on_air else
                                  (OVER_TAG if over else NEXT_TAG))
            draw_text(pen, (stop - wide // 2, middle), tag, tag_size, WHITE,
                      anchor="mm", weight="mid")
            stop -= wide + 12

        comp = norm_line(event.get("competition"))
        two = bool(comp) and height >= name_size + comp_size + 12
        # the two lines are centred as one block, so the pair sits on
        # the row's middle however large either of them grew
        block = name_size + 4 + comp_size
        name_y = (middle - block // 2 + name_size // 2) if two else middle
        space = stop - text_x - 14
        fitted = size_that_fits(event["title"], name_size, 14, space)
        draw_text(pen, (text_x, name_y),
                  clipped(event["title"], fitted, space), fitted, ink,
                  anchor="lm", weight="mid")
        if two:
            draw_text(pen, (text_x, middle + block // 2 - comp_size // 2),
                      clipped(comp, comp_size, space, weight="mid"),
                      comp_size, readable(comp_colour(comp)),
                      anchor="lm", weight="mid")
        y += height

    left_out = len(rest) - len(shown)
    if left_out > 0:
        draw_text(pen, (W - PAD, foot + 16), f"+{left_out} أخرى", 14, MUTED,
                  anchor="rm", thin=True)

    # ---- the sign-off band ----------------------------------------------
    pen.line([(PAD, foot + 34), (W - PAD, foot + 34)], fill=RULE, width=1)
    _crest_strip(board, pen, events, foot + 44, accent)
    draw_text(pen, (W - PAD, H - 10), SIGNATURE, 13, RULE, anchor="rs",
              thin=True)
    progress(pen, page, pages, accent, y=H - 14)
    return board
