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
_CRESTS: dict[tuple[str, int], object] = {}

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


def crest(name: str, box: int):
    """The club's crest at the size the row can hold, or None."""
    key = (name, box)
    if key in _CRESTS:
        return _CRESTS[key]
    image = None
    if team_badges is not None:
        try:
            found = team_badges.badge(name)
        except Exception:
            found = None
        if found is not None:
            found = found.copy()
            found.thumbnail((box, box), Image.LANCZOS)
            image = found
    _CRESTS[key] = image
    return image


def initials(name: str) -> str:
    words = [word for word in re.split(r"[\s.]+", name) if word]
    letters = "".join(word[0] for word in words if word[0].isalnum())
    return (letters[:2] or name[:2]).upper()


def draw_crest(board, pen, name, cx, cy, box):
    """A club's badge at (cx, cy), or its letters in its own colour."""
    image = crest(name, box)
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
            art = crest(name, 30)
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


def draw_board(day: date, events: list[dict], now: datetime, viewer,
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
    head = title.upper() if not ARABIC.search(title) else title
    draw_text(pen, (W // 2, 52), clipped(head, 40, 720, weight="heavy"), 40,
              WHITE, anchor="mm", weight="heavy")
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

    live_rows = [e for e in events
                 if e["start"] <= now < e["start"] + live_for]
    rest = [e for e in events if e not in live_rows]

    # ---- ON AIR, its own panel on the left ------------------------------
    col = PAD + 372                       # where the left column ends
    top = 140
    draw_text(pen, (PAD, top), "على الهواء الآن", 22, WHITE, anchor="lm",
              weight="mid")
    dot_x = PAD + width_of("على الهواء الآن", 22, weight="mid") + 18
    pen.ellipse([dot_x, top - 5, dot_x + 10, top + 5], fill=LIVE_TAG)
    draw_text(pen, (dot_x + 18, top + 1), "LIVE", 13, LIVE_RED, anchor="lm",
              weight="mid")

    y = top + 28
    if not live_rows:
        draw_text(pen, (PAD, y + 18), "لا يوجد بث مباشر الآن", 16, MUTED,
                  anchor="lm", thin=True)
    for event in live_rows[:4]:
        card_h = 92
        if y + card_h > foot:
            break
        card = [PAD, y, col - 28, y + card_h]
        pen.rounded_rectangle(card, radius=12, fill=LIVE_BG,
                              outline=LIVE_TAG, width=2)
        pen.rounded_rectangle([card[0], card[1] + 10, card[0] + 6,
                               card[3] - 10], radius=3, fill=LIVE_TAG)
        inner = card[0] + 20
        room = card[2] - inner - 16
        draw_text(pen, (inner, y + 24),
                  event["start"].astimezone(viewer).strftime("%H:%M"), 17,
                  LIVE_RED, anchor="lm", weight="heavy")
        comp = norm_line(event.get("competition"))
        if comp:
            draw_text(pen, (card[2] - 16, y + 24),
                      clipped(comp, 14, room - 90, weight="mid"), 14,
                      comp_colour(comp) + (255,), anchor="rm", weight="mid")
        name = size_that_fits(event["title"], 24, 16, room)
        draw_text(pen, (inner, y + 52), clipped(event["title"], name, room),
                  name, WHITE, anchor="lm", weight="mid")
        if event["channels"]:
            draw_text(pen, (inner, y + 76),
                      clipped("  ·  ".join(event["channels"][:3]), 14, room,
                              weight="mid"), 14, PILL_INK, anchor="lm",
                      weight="mid")
        y += card_h + 12

    pen.line([(col, top - 14), (col, foot)], fill=RULE, width=1)

    # ---- COMING, listed on the right ------------------------------------
    left = col + 30
    draw_text(pen, (left, top), "البث القادم", 22, WHITE, anchor="lm",
              weight="mid")
    draw_text(pen, (W - PAD, top), day_badge(day, now, viewer, weekday), 15,
              accent, anchor="rm", weight="mid")

    y = top + 28
    room = foot - y
    shown = rest
    height = max(40, min(64, room // max(1, len(shown))))
    if len(shown) * height > room:
        shown = rest[:max(1, room // 40)]
        height = room // len(shown)

    today = day == now.astimezone(viewer).date()
    coming = False
    for index, event in enumerate(shown):
        over = event["start"] + live_for <= now
        band = [left, y, W - PAD, y + height - 6]
        pen.rounded_rectangle(band, radius=8,
                              fill=OVER_BG if over else
                              (PANEL if index % 2 == 0 else PANEL_ALT))
        pen.rounded_rectangle([band[0], band[1] + 5, band[0] + 4,
                               band[3] - 5], radius=2,
                              fill=OVER_TAG if over else accent)
        middle = y + (height - 6) // 2
        ink = PILL_INK if over else WHITE

        draw_text(pen, (left + 18, middle),
                  event["start"].astimezone(viewer).strftime("%H:%M"), 19,
                  OVER_TAG if over else accent, anchor="lm", weight="heavy")
        text_x = left + 90
        tag = ""
        if over:
            tag = "انتهى"
        elif today and not coming:
            tag, coming = "التالي", True
        chan = "  ·  ".join(event["channels"][:3])
        chan_w = min(200, width_of(chan, 13, weight="mid")) if chan else 0
        if chan:
            draw_text(pen, (W - PAD - 16, middle),
                      clipped(chan, 13, 200, weight="mid"), 13,
                      MUTED if over else PILL_INK, anchor="rm", weight="mid")
        stop = W - PAD - 30 - chan_w
        if tag:
            wide = width_of(tag, 12, weight="mid") + 16
            pen.rounded_rectangle([stop - wide, middle - 10, stop,
                                   middle + 10], radius=10,
                                  fill=OVER_TAG if over else NEXT_TAG)
            draw_text(pen, (stop - wide // 2, middle), tag, 12, WHITE,
                      anchor="mm", weight="mid")
            stop -= wide + 12

        comp = norm_line(event.get("competition"))
        two = bool(comp) and height >= 50
        size = 19 if two else 20
        name_y = middle - 9 if two else middle
        space = stop - text_x - 14
        fitted = size_that_fits(event["title"], size, 14, space)
        draw_text(pen, (text_x, name_y),
                  clipped(event["title"], fitted, space), fitted, ink,
                  anchor="lm", weight="mid")
        if two:
            draw_text(pen, (text_x, middle + 12),
                      clipped(comp, 13, space, weight="mid"), 13,
                      comp_colour(comp) + (255,), anchor="lm", weight="mid")
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
