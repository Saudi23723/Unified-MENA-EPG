#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Formula 1 board — three boards, because a race weekend is 3 days in 7.

THE PROBLEM THIS CHANNEL HAS AND NO OTHER ONE DOES. Every other screen
here carries fixtures: there is always another match tomorrow. Formula 1
runs twenty-four weekends a year, so a channel built the way the others
are would be a black screen from Monday to Thursday — which is most of
its life.

So it is not one board with rows in it. It is THREE, and which one is
drawn is decided by the clock rather than by a setting:

    LIVE      a session is running now — the order, the flags, the
              track temperature, the tyres, the radio
    WEEKEND   the cars are at a circuit but not on it — the next
              session counting down, the last one's result
    BETWEEN   no circuit at all, five days out of seven — the
              championship, the next Grand Prix and every session it
              has, the last race's podium

The third is the one that makes the channel work, and it is the one a
board full of fixtures could never have drawn.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from match_board import (ARABIC, H, MUTED, PAD, PANEL, PANEL_ALT, RULE, W,
                         WHITE, backdrop, clipped, draw_text, width_of)

F1_RED = (225, 6, 0, 255)
F1_DARK = (15, 18, 26, 255)
GREEN_FLAG = (34, 197, 94, 255)
YELLOW_FLAG = (250, 204, 21, 255)
RED_FLAG = (225, 6, 0, 255)
CHEQUER = (240, 244, 250, 255)
INK = (9, 12, 20, 255)

# EVERY TEAM IN ITS OWN COLOUR, because a viewer who follows the sport
# reads the colour before the name — a teal bar IS Mercedes on a
# television across a room, and three letters are not.
TEAM_COLOUR = {
    "Mercedes": (0, 215, 182, 255),
    "Ferrari": (232, 0, 45, 255),
    "Red Bull": (54, 113, 198, 255),
    "McLaren": (255, 128, 0, 255),
    "Aston Martin": (34, 153, 113, 255),
    "Alpine F1 Team": (0, 147, 204, 255),
    "Alpine": (0, 147, 204, 255),
    "Williams": (100, 196, 255, 255),
    "RB F1 Team": (102, 146, 255, 255),
    "Racing Bulls": (102, 146, 255, 255),
    "Sauber": (82, 226, 82, 255),
    "Kick Sauber": (82, 226, 82, 255),
    "Audi": (82, 226, 82, 255),
    "Haas F1 Team": (182, 186, 189, 255),
    "Haas": (182, 186, 189, 255),
    "Cadillac": (200, 168, 90, 255),
}
TYRE_COLOUR = {"SOFT": (225, 6, 0, 255), "MEDIUM": (250, 204, 21, 255),
               "HARD": (240, 244, 250, 255),
               "INTERMEDIATE": (34, 197, 94, 255),
               "WET": (54, 113, 198, 255)}
FLAG_COLOUR = {"GREEN": GREEN_FLAG, "CLEAR": GREEN_FLAG,
               "YELLOW": YELLOW_FLAG, "DOUBLE YELLOW": YELLOW_FLAG,
               "RED": RED_FLAG, "CHEQUERED": CHEQUER}


# THE SKY, in the WMO codes Open-Meteo answers with, said in the same
# short English the rest of this page's labels use. A code that is not
# in here is not guessed at — the band simply does not name the sky.
WMO_EN = {
    0: "CLEAR", 1: "MOSTLY CLEAR", 2: "PARTLY CLOUDY", 3: "OVERCAST",
    45: "FOG", 48: "FREEZING FOG",
    51: "LIGHT DRIZZLE", 53: "DRIZZLE", 55: "HEAVY DRIZZLE",
    56: "FREEZING DRIZZLE", 57: "FREEZING DRIZZLE",
    61: "LIGHT RAIN", 63: "RAIN", 65: "HEAVY RAIN",
    66: "FREEZING RAIN", 67: "FREEZING RAIN",
    71: "LIGHT SNOW", 73: "SNOW", 75: "HEAVY SNOW", 77: "SNOW GRAINS",
    80: "SHOWERS", 81: "SHOWERS", 82: "VIOLENT SHOWERS",
    85: "SNOW SHOWERS", 86: "HEAVY SNOW SHOWERS",
    95: "THUNDERSTORM", 96: "THUNDERSTORM, HAIL", 99: "THUNDERSTORM, HAIL",
}
# WET IS THE ONE THING ON THIS BAND THAT CHANGES A RACE, so it is the
# one thing that gets a colour. Everything else is read, not spotted.
WET_CODES = tuple(range(51, 68)) + tuple(range(80, 100))
DRY_SKY = (120, 145, 190, 255)
WET_SKY = (54, 113, 198, 255)


def sky_words(code) -> str:
    try:
        return WMO_EN.get(int(code), "")
    except (TypeError, ValueError):
        return ""


def sky_is_wet(weather: dict) -> bool:
    """Rain that is falling, or rain that is more likely than not."""
    try:
        if int(weather.get("code")) in WET_CODES:
            return True
    except (TypeError, ValueError):
        pass
    return (float(weather.get("rain_mm") or 0) > 0
            or float(weather.get("rain_chance") or 0) >= 50)


def team_colour(name: str):
    for known, tone in TEAM_COLOUR.items():
        if known.lower() in (name or "").lower():
            return tone
    return MUTED


def _masthead(board, pen, title: str, subtitle: str, right: str, chip: str,
              chip_tone) -> None:
    """The band every one of the three boards wears."""
    # THE CHEQUER. Drawn rather than typed — there is no font here with a
    # chequered flag in it, and the one mark that says motor racing
    # without a word is worth eight squares of arithmetic.
    for row in range(2):
        for col in range(4):
            if (row + col) % 2 == 0:
                x, y = PAD + col * 13, 34 + row * 13
                pen.rectangle([x, y, x + 12, y + 12], fill=WHITE)
            else:
                x, y = PAD + col * 13, 34 + row * 13
                pen.rectangle([x, y, x + 12, y + 12], fill=(40, 46, 60, 255))
    draw_text(pen, (PAD + 66, 41), title, 34, WHITE, anchor="lm",
              weight="heavy")
    draw_text(pen, (PAD + 66, 68), subtitle, 15, MUTED, anchor="lm",
              thin=True)
    draw_text(pen, (W - PAD, 41), right, 19, WHITE, anchor="rm",
              weight="mid")
    if chip:
        wide = width_of(chip, 17, weight="heavy") + 34
        pen.rounded_rectangle([W - PAD - wide, 58, W - PAD, 88], radius=15,
                              fill=chip_tone)
        draw_text(pen, (W - PAD - wide // 2, 73), chip, 17, INK,
                  anchor="mm", weight="heavy")
    pen.line([(PAD, 104), (W - PAD, 104)], fill=RULE, width=1)
    pen.rounded_rectangle([PAD, 102, PAD + 190, 106], radius=2, fill=F1_RED)


def _panel(pen, box, heading: str) -> int:
    pen.rounded_rectangle(box, radius=14, fill=PANEL, outline=RULE, width=1)
    draw_text(pen, (box[0] + 20, box[1] + 24), heading, 16, MUTED,
              anchor="lm", weight="mid")
    return box[1] + 48


def _driver_row(pen, x, y, wide, pos, code, team, right, tall=34,
                shade=None, lead=False):
    """One driver: a colour bar for the team, the code, the number."""
    pen.rounded_rectangle([x, y, x + wide, y + tall], radius=7,
                          fill=shade or PANEL_ALT)
    tone = team_colour(team)
    pen.rounded_rectangle([x + 4, y + 5, x + 10, y + tall - 5], radius=3,
                          fill=tone)
    draw_text(pen, (x + 26, y + tall // 2), str(pos), 18,
              WHITE if not lead else F1_RED, anchor="lm", weight="heavy")
    draw_text(pen, (x + 58, y + tall // 2), code, 20, WHITE, anchor="lm",
              weight="heavy")
    draw_text(pen, (x + 112, y + tall // 2),
              clipped(team, 15, wide - 230, weight="mid"), 15, _lift(tone),
              anchor="lm", weight="mid")
    draw_text(pen, (x + wide - 16, y + tall // 2), right, 18, WHITE,
              anchor="rm", weight="heavy")



def draw_track(board, pen, points, box, rotation=0, tone=None, width=5):
    """The circuit's own shape, drawn from its coordinates.

    NOT A DOWNLOADED PICTURE. The service behind the meetings feed hands
    over a track as a list of points, so the outline is drawn here in the
    board's own colours at the board's own weight — it scales to whatever
    box it is given, it carries no white background to knock out, and it
    costs one line of geometry rather than an image fetch on every pass.
    """
    import math
    angle = math.radians(rotation)
    turned = [(x * math.cos(angle) - y * math.sin(angle),
               x * math.sin(angle) + y * math.cos(angle)) for x, y in points]
    xs = [p[0] for p in turned]
    ys = [p[1] for p in turned]
    span_x, span_y = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
    wide, tall = box[2] - box[0], box[3] - box[1]
    scale = min(wide / span_x, tall / span_y) * 0.88
    off_x = box[0] + (wide - span_x * scale) / 2 - min(xs) * scale
    off_y = box[1] + (tall - span_y * scale) / 2 - min(ys) * scale
    line = [(off_x + x * scale, off_y + y * scale) for x, y in turned]
    pen.line(line + [line[0]], fill=tone or RULE, width=width, joint="curve")
    return line


def _dim(tone, share: float = 0.22):
    """A team's colour at the weight a bar behind text can carry."""
    return (int(tone[0] * share), int(tone[1] * share),
            int(tone[2] * share), 255)


def _lift(tone, share: float = 0.55):
    """A team's colour bright enough to READ on a bar of that colour.

    THIS IS WHY THE TEAM NAMES WERE NOT LEGIBLE. Every championship row
    drew the team's name in the team's own colour on top of a bar that
    was the same colour at 28 per cent — Ferrari red on dark Ferrari
    red, Red Bull blue on dark Red Bull blue. The two are related by a
    multiplication, so the contrast between them is fixed and low no
    matter which team it is, and on a television across a room the name
    disappeared into its own bar.

    Mixing the colour towards white instead keeps a Ferrari row red and
    a McLaren row orange — the colour is still doing its job of naming
    the team before the letters are read — while putting the text far
    enough from the bar behind it to be read at all.
    """
    return (int(tone[0] + (255 - tone[0]) * share),
            int(tone[1] + (255 - tone[1]) * share),
            int(tone[2] + (255 - tone[2]) * share), 255)


def _hex(code: str):
    code = (code or "").lstrip("#")
    if len(code) != 6:
        return MUTED
    return (int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16), 255)


def _clock(pen, x, y, label, value, tone=WHITE, big=30):
    draw_text(pen, (x, y), label, 13, MUTED, anchor="lm", thin=True)
    draw_text(pen, (x, y + 28), value, big, tone, anchor="lm", weight="heavy")


def _bar_row(pen, box, y, tone, share, pos, code, team, right, note="",
             tall=26, room=150):
    """One championship row: a bar as long as the points it stands for.

    THE BAR IS DIMMER AND THE TEXT IS BRIGHTER than they were. A bar at
    28 per cent of the team's colour with the team's name written on it
    in the full colour is the one pairing on this board that cannot be
    read; the bar carries 22 per cent now and the name is lifted towards
    white, so the colour still names the team and the letters still read.
    """
    wide = box[2] - box[0] - 40
    half = tall // 2
    pen.rounded_rectangle([box[0] + 20, y - half,
                           box[0] + 20 + int(wide * share), y + half],
                          radius=6, fill=_dim(tone, 0.22))
    pen.rounded_rectangle([box[0] + 20, y - half, box[0] + 26, y + half],
                          radius=3, fill=tone)
    draw_text(pen, (box[0] + 38, y + 1), pos, 16, WHITE, anchor="lm",
              weight="mid")
    draw_text(pen, (box[0] + 66, y + 1), code, 19, WHITE, anchor="lm",
              weight="heavy")
    # THE SECOND COLUMN STARTS AFTER THE FIRST ONE ENDS. A fixed offset
    # assumed a three-letter driver code and the constructors' page
    # writes "Aston Martin" into the same slot, so the name and the
    # nationality were printed on top of each other.
    after = box[0] + 66 + width_of(code, 19, weight="heavy") + 18
    if team:
        draw_text(pen, (after, y + 1),
                  clipped(team, 15, max(40, room), weight="mid"), 15,
                  _lift(tone), anchor="lm", weight="mid")
    if note:
        draw_text(pen, (box[2] - 88, y + 1), note, 14, (150, 164, 190, 255),
                  anchor="rm", weight="mid")
    draw_text(pen, (box[2] - 20, y + 1), right, 18, WHITE, anchor="rm",
              weight="heavy")


def _lap(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:06.3f}"


def _session_rows(pen, box, y, sessions, viewer):
    for name, when in sessions:
        local = when.astimezone(viewer)
        race = name == "RACE"
        pen.rounded_rectangle([box[0] + 18, y - 15, box[2] - 18, y + 17],
                              radius=7,
                              fill=(38, 18, 20, 255) if race else PANEL_ALT)
        pen.rounded_rectangle([box[0] + 22, y - 10, box[0] + 27, y + 12],
                              radius=3, fill=F1_RED if race else RULE)
        draw_text(pen, (box[0] + 42, y + 1), name, 16,
                  WHITE if race else MUTED, anchor="lm", weight="heavy")
        draw_text(pen, (box[0] + 178, y + 1), f"{local:%a %d %b}", 15, MUTED,
                  anchor="lm", weight="mid")
        draw_text(pen, (box[2] - 30, y + 1), f"{local:%H:%M}", 18, WHITE,
                  anchor="rm", weight="heavy")
        y += 36
    return y


def countdown(now, when) -> str:
    gap = when - now
    if gap.total_seconds() <= 0:
        return "UNDER WAY"
    days, rest = gap.days, gap.seconds
    if days:
        return f"IN {days}D {rest // 3600}H"
    if rest >= 3600:
        return f"IN {rest // 3600}H {(rest % 3600) // 60}M"
    return f"IN {rest // 60}M"


def draw_live(now, state) -> Image.Image:
    """A session is on. The order, the circuit, the track, the lap."""
    board = backdrop()
    pen = ImageDraw.Draw(board)
    flag = (state.get("flag") or "GREEN").upper()
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · على الحلبة الآن",
              f"{state['circuit'].upper()} · {state['country'].upper()}",
              flag, FLAG_COLOUR.get(flag, GREEN_FLAG))

    left = [PAD, 122, PAD + 610, H - 116]
    head = state["session"].upper()
    if state.get("lap"):
        head = f"{head}  ·  LAP {state['lap']}/{state.get('laps', '?')}"
    y = _panel(pen, left, head)
    for index, row in enumerate(state.get("order", [])[:9], start=1):
        tone = _hex(row.get("colour"))
        _driver_row(pen, left[0] + 14, y, left[2] - left[0] - 28, str(index),
                    row["code"], row.get("team", ""), row["gap"], tall=36,
                    lead=index == 1,
                    shade=(38, 18, 20, 255) if index == 1 else None)
        pen.rounded_rectangle([left[0] + 18, y + 5, left[0] + 24, y + 31],
                              radius=3, fill=tone)
        y += 42

    track = [PAD + 634, 122, W - PAD - 234, 386]
    pen.rounded_rectangle(track, radius=14, fill=PANEL, outline=RULE, width=1)
    draw_text(pen, (track[0] + 20, track[1] + 24), "CIRCUIT", 16, MUTED,
              anchor="lm", weight="mid")
    if state.get("shape"):
        draw_track(board, pen, state["shape"],
                   [track[0] + 30, track[1] + 44, track[2] - 30,
                    track[3] - 16], rotation=state.get("rotation", 0),
                   tone=(90, 110, 150, 255), width=6)
    if state.get("corners"):
        draw_text(pen, (track[2] - 18, track[1] + 24),
                  f"{state['corners']} corners", 13, MUTED, anchor="rm",
                  thin=True)

    air = [W - PAD - 214, 122, W - PAD, 386]
    y = _panel(pen, air, "TRACK")
    weather = state.get("weather") or {}
    _clock(pen, air[0] + 20, y, "TRACK",
           f"{weather.get('track_temperature', 0):.0f}°", F1_RED, big=34)
    _clock(pen, air[0] + 20, y + 78, "AIR",
           f"{weather.get('air_temperature', 0):.0f}°", WHITE, big=28)
    wet = bool(weather.get("rainfall"))
    _clock(pen, air[0] + 120, y + 78, "RAIN", "YES" if wet else "NO",
           RED_FLAG if wet else GREEN_FLAG, big=28)
    draw_text(pen, (air[0] + 20, y + 156),
              f"humidity {weather.get('humidity', 0):.0f}%", 14, MUTED,
              anchor="lm", thin=True)
    draw_text(pen, (air[0] + 20, y + 178),
              f"wind {weather.get('wind_speed', 0):.1f} m/s", 14, MUTED,
              anchor="lm", thin=True)

    box = [PAD + 634, 404, W - PAD, H - 116]
    y = _panel(pen, box, "FASTEST LAP")
    best = state.get("fastest")
    if best:
        tone = _hex(best.get("colour"))
        draw_text(pen, (box[0] + 20, y + 10), best["code"], 26, tone,
                  anchor="lm", weight="heavy")
        draw_text(pen, (box[0] + 96, y + 10), _lap(best["time"]), 30, WHITE,
                  anchor="lm", weight="heavy")
        draw_text(pen, (box[2] - 20, y + 10), f"lap {best['lap']}", 15, MUTED,
                  anchor="rm", thin=True)
        x = box[0] + 20
        for number, part in enumerate(best.get("sectors") or (), start=1):
            pen.rounded_rectangle([x, y + 38, x + 112, y + 70], radius=7,
                                  fill=PANEL_ALT)
            draw_text(pen, (x + 12, y + 54), f"S{number}", 13, MUTED,
                      anchor="lm", weight="mid")
            draw_text(pen, (x + 100, y + 54), f"{part:.3f}", 17, WHITE,
                      anchor="rm", weight="heavy")
            x += 122
        if best.get("trap"):
            draw_text(pen, (box[2] - 20, y + 54), f"trap {best['trap']} km/h",
                      14, MUTED, anchor="rm", thin=True)
    pen.line([(box[0] + 20, y + 96), (box[2] - 20, y + 96)], fill=RULE,
             width=1)
    top = state.get("top_speed")
    if top:
        draw_text(pen, (box[0] + 20, y + 118), "TOP SPEED", 13, MUTED,
                  anchor="lm", thin=True)
        draw_text(pen, (box[0] + 20, y + 146), f"{top['kph']} km/h", 24,
                  _hex(top.get("colour")), anchor="lm", weight="heavy")
        draw_text(pen, (box[0] + 186, y + 146), top["code"], 18, WHITE,
                  anchor="lm", weight="mid")
    pits = state.get("pits")
    if pits:
        draw_text(pen, (box[0] + 320, y + 118), "PIT STOPS", 13, MUTED,
                  anchor="lm", thin=True)
        draw_text(pen, (box[0] + 320, y + 146), str(pits["count"]), 24, WHITE,
                  anchor="lm", weight="heavy")
        if pits.get("best"):
            draw_text(pen, (box[0] + 374, y + 146),
                      f"fastest {pits['best']} {pits['s']}s", 15, MUTED,
                      anchor="lm", weight="mid")
    _foot(pen, now)
    return board


def _foot(pen, now) -> None:
    pen.line([(PAD, H - 96), (W - PAD, H - 96)], fill=RULE, width=1)
    draw_text(pen, (W - PAD, H - 14), "S.Saudi", 13, RULE, anchor="rs",
              thin=True)


def _fact(pen, x, y, label, value, tone=WHITE, size=26):
    draw_text(pen, (x, y), label, 14, MUTED, anchor="lm", thin=True)
    draw_text(pen, (x, y + 30), value, size, tone, anchor="lm",
              weight="heavy")


def draw_facts(pen, box, facts) -> None:
    """What is true of this circuit, in one band of numbers.

    NONE OF IT IS FETCHED FOR THIS PANEL. The corner count falls out of
    the shape the board already draws, the type is a field in the
    meetings feed, and the history is the same calendar this channel
    already reads, asked about one circuit instead of one season.

    A FACT THAT IS MISSING IS LEFT OUT, not guessed and not zeroed: a
    board that says "0 corners" is worse than one that says nothing
    about corners. The numbers that survive are spread across whatever
    width they have, so three of them and five of them both look laid
    out rather than left over.
    """
    y = _panel(pen, box, "TRACK")
    told = []
    if facts.get("last_winner"):
        told.append(f"last won by {facts['last_winner']}")
    most = facts.get("most_wins")
    if most:
        told.append(f"{most[0]} {most[1]}×")
    if told:
        draw_text(pen, (box[2] - 20, box[1] + 24), "  ·  ".join(told), 14,
                  F1_RED, anchor="rm", weight="mid")

    numbers = []
    if facts.get("corners"):
        numbers.append(("CORNERS", str(facts["corners"]), F1_RED))
    if facts.get("laps"):
        numbers.append(("RACE LAPS", str(facts["laps"]), WHITE))
    if facts.get("held"):
        numbers.append(("HELD", str(facts["held"]), WHITE))
    if facts.get("first"):
        numbers.append(("SINCE", str(facts["first"]), WHITE))
    if facts.get("type"):
        numbers.append(("CIRCUIT", facts["type"].upper()[:9], MUTED))
    if not numbers:
        return
    room = box[2] - box[0] - 44
    step = room // len(numbers)
    for index, (label, value, tone) in enumerate(numbers):
        x = box[0] + 22 + index * step
        draw_text(pen, (x, y + 6), label, 14, MUTED, anchor="lm", thin=True)
        draw_text(pen, (x, y + 36), value, 28 if len(value) < 5 else 20,
                  tone, anchor="lm", weight="heavy")


def draw_weather(pen, box, weather) -> None:
    """The weather at the circuit, in one band under its outline.

    WHY IT IS ON THIS PAGE AND NOT ONLY THE LIVE ONE. The live board's
    weather comes off the trackside sensors, which is the better number
    and only exists while a session is running. This channel is on air
    the whole week; for five days of it the circuit had no weather on
    the screen at all. This band is a forecast at the circuit's own
    coordinates, so the track page always has one.

    IT NEVER CLAIMS TO BE THE SENSOR. The ground figure is labelled
    SURFACE, not TRACK — the live panel keeps TRACK for the measured
    one, and a viewer comparing the two pages is never told the same
    word means two different things.

    A READING THAT DID NOT COME BACK IS LEFT OUT. Four figures spread
    across the band and six spread across it both look laid out; a
    "0°" where a number is missing looks like weather.
    """
    if not weather or weather.get("air_c") is None:
        return
    wet = sky_is_wet(weather)
    tone = WET_SKY if wet else DRY_SKY
    pen.rounded_rectangle(box, radius=10, fill=PANEL_ALT)
    pen.rounded_rectangle([box[0], box[1], box[0] + 5, box[3]], radius=2,
                          fill=tone)

    said = sky_words(weather.get("code"))
    draw_text(pen, (box[0] + 22, box[1] + 20), "TRACK WEATHER", 13, MUTED,
              anchor="lm", thin=True)
    if said:
        draw_text(pen, (box[0] + 150, box[1] + 20), said, 15, tone,
                  anchor="lm", weight="heavy")
    # WHERE, AND WHAT TIME IT IS THERE. A viewer reading 11° for
    # Melbourne is owed the 23:30 that explains it.
    when = (weather.get("observed") or "")[11:16]
    right = " · ".join(one for one in (weather.get("where"), when) if one)
    if right:
        draw_text(pen, (box[2] - 20, box[1] + 20),
                  clipped(right, 14, box[2] - box[0] - 340, thin=True), 14,
                  MUTED, anchor="rm", thin=True)

    numbers = []
    air = weather.get("air_c")
    numbers.append(("AIR", f"{air:.0f}\u00b0", WHITE))
    if weather.get("surface_c") is not None:
        numbers.append(("SURFACE", f"{weather['surface_c']:.0f}\u00b0",
                        F1_RED))
    if weather.get("feels_c") is not None:
        numbers.append(("FEELS", f"{weather['feels_c']:.0f}\u00b0", MUTED))
    if weather.get("rain_chance") is not None:
        numbers.append(("RAIN CHANCE", f"{weather['rain_chance']:.0f}%",
                        tone))
    if weather.get("humidity") is not None:
        numbers.append(("HUMIDITY", f"{weather['humidity']:.0f}%", WHITE))
    if weather.get("wind_kmh") is not None:
        numbers.append(("WIND", f"{weather['wind_kmh']:.0f}", WHITE))

    room = box[2] - box[0] - 44
    step = room // len(numbers)
    y = box[1] + 46
    for index, (label, value, ink) in enumerate(numbers):
        x = box[0] + 22 + index * step
        draw_text(pen, (x, y), label, 12, MUTED, anchor="lm", thin=True)
        draw_text(pen, (x, y + 26), value, 26, ink, anchor="lm",
                  weight="heavy")
        if label == "WIND":
            draw_text(pen, (x + width_of(value, 26) + 6, y + 32), "km/h",
                      12, MUTED, anchor="lm", thin=True)


def page_track(now, state) -> Image.Image:
    """THE CIRCUIT, on a page of its own and nothing else on it.

    Cramming the corners and the history into a band under the
    championship was losing them. A circuit gets the whole screen: its
    own shape drawn large from its own coordinates, and every fact
    around it in type a television can read.
    """
    board = backdrop()
    pen = ImageDraw.Draw(board)
    nxt = state.get("next") or {}
    facts = state.get("facts") or {}
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · الحلبة",
              f"ROUND {nxt.get('round', '')} · "
              f"{(nxt.get('country') or '').upper()}",
              "THE TRACK", (90, 110, 150, 255))

    left = [PAD, 122, PAD + 700, H - 116]
    pen.rounded_rectangle(left, radius=14, fill=PANEL, outline=RULE, width=1)
    draw_text(pen, (left[0] + 24, left[1] + 30), nxt.get("circuit", ""), 30,
              WHITE, anchor="lm", weight="heavy")
    draw_text(pen, (left[0] + 24, left[1] + 62),
              f"{nxt.get('locality', '')}, {nxt.get('country', '')}", 17,
              F1_RED, anchor="lm", weight="mid")
    # THE WEATHER TAKES THE FOOT OF THIS PANEL, and the outline gives up
    # exactly that much room rather than being drawn over. A pass with
    # no weather back gives the whole panel to the circuit again, so a
    # source that did not answer costs a band, not a smaller track.
    sky = state.get("weather") or {}
    band = [left[0] + 20, left[3] - 108, left[2] - 20, left[3] - 20]
    floor = (band[1] - 12) if sky.get("air_c") is not None else left[3] - 24
    if state.get("shape"):
        draw_track(board, pen, state["shape"],
                   [left[0] + 40, left[1] + 92, left[2] - 40, floor],
                   rotation=state.get("rotation", 0),
                   tone=(120, 145, 190, 255), width=8)
    draw_weather(pen, band, sky)

    right = [PAD + 724, 122, W - PAD, H - 116]
    y = _panel(pen, right, "THE FACTS")
    rows = []
    if facts.get("corners"):
        rows.append(("CORNERS", str(facts["corners"]), F1_RED))
    if facts.get("laps"):
        rows.append(("RACE LAPS", str(facts["laps"]), WHITE))
    if facts.get("type"):
        rows.append(("CIRCUIT", facts["type"].upper(), WHITE))
    if facts.get("held"):
        rows.append(("GRANDS PRIX HELD", str(facts["held"]), WHITE))
    if facts.get("first"):
        rows.append(("FIRST HELD", str(facts["first"]), WHITE))
    if facts.get("last_winner"):
        rows.append(("LAST WON BY",
                     f"{facts['last_winner']} "
                     f"{facts.get('last_winner_year', '')}".strip(), WHITE))
    most = facts.get("most_wins")
    if most:
        rows.append(("MOST WINS HERE", f"{most[0]}  {most[1]}×", F1_RED))
    if not rows:
        draw_text(pen, ((right[0] + right[2]) // 2, (right[1] + right[3]) // 2),
                  "لا توجد معلومات عن الحلبة", 18, MUTED, anchor="mm",
                  thin=True)
        _foot(pen, now)
        return board
    step = max(48, min(74, (right[3] - y - 20) // len(rows)))
    for label, value, tone in rows:
        pen.rounded_rectangle([right[0] + 16, y - 14, right[2] - 16,
                               y + step - 24], radius=8, fill=PANEL_ALT)
        draw_text(pen, (right[0] + 30, y + 2), label, 14, MUTED, anchor="lm",
                  thin=True)
        draw_text(pen, (right[2] - 30, y + 2), value,
                  26 if len(value) < 8 else 20, tone, anchor="rm",
                  weight="heavy")
        y += step
    _foot(pen, now)
    return board


def _columns(count, top, foot, least=32, most=52, most_cols=4):
    """How to lay `count` rows into a box: how many columns, how tall.

    THE COLUMN COUNT CANNOT BE DECIDED BEFORE THE ROW HEIGHT. Fixing the
    step first and dividing gave twenty drivers three columns of seven
    and left the bottom third of the panel empty — the page looked
    padded and every row was narrower than it needed to be.

    So it asks the other way round: the FEWEST columns whose rows are
    still tall enough to read, and then the rows grow to fill the height
    they actually have. Twenty drivers become two columns of ten that
    reach the foot of the panel, not three of seven that stop halfway.
    """
    room = max(1, foot - top)
    for columns in range(1, most_cols + 1):
        per = -(-count // columns)
        step = room // max(1, per)
        if step >= least or columns == most_cols:
            return columns, per, max(least, min(most, step))
    return 1, count, least


def _title_band(pen, box, state, table) -> None:
    """How the championship stands, as two numbers and a verdict."""
    if len(table) < 2:
        return
    gap = int(table[0]["points"]) - int(table[1]["points"])
    rounds_left = int(state["rounds"]) - int(state["round"])
    # 25 for a win, 18 for second, and a point for the fastest lap is
    # not on offer any more — so the most a driver can still take from
    # here is 25 a round, and the sprints are what this cannot know.
    left_pts = rounds_left * 25
    settled = gap > left_pts
    line = box[3] - 52
    pen.line([(box[0] + 20, line), (box[2] - 20, line)], fill=RULE, width=1)
    draw_text(pen, (box[0] + 20, line + 26),
              f"{table[0]['code']} leads by {gap}", 19,
              _lift(_hex(table[0].get("colour")), 0.35), anchor="lm",
              weight="heavy")
    draw_text(pen, (box[0] + 240, line + 26),
              f"{left_pts} still available over {rounds_left} rounds", 16,
              (160, 176, 202, 255), anchor="lm", weight="mid")
    draw_text(pen, (box[2] - 20, line + 26),
              "DECIDED" if settled else "STILL OPEN", 18,
              F1_RED if settled else GREEN_FLAG, anchor="rm", weight="heavy")


def page_championship(now, state) -> Image.Image:
    """EVERY DRIVER IN THE CHAMPIONSHIP, in two columns.

    Ten was never the championship, it was as many as one column had
    room for — and the source hands over all twenty-odd in the same
    answer. Two columns side by side hold the whole table at a size a
    television reads, so nobody is dropped for being eleventh.
    """
    board = backdrop()
    pen = ImageDraw.Draw(board)
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · ترتيب السائقين",
              f"ROUND {state.get('round', '')} OF {state.get('rounds', '')}",
              "DRIVERS", F1_RED)

    table = state.get("drivers") or []
    box = [PAD, 122, W - PAD, H - 116]
    _panel(pen, box, "DRIVERS' CHAMPIONSHIP")
    if not table:
        draw_text(pen, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2),
                  "لا يوجد ترتيب بعد", 20, MUTED, anchor="mm", thin=True)
        _foot(pen, now)
        return board

    lead = float(table[0]["points"]) or 1
    # AS MANY ROWS AS THE COLUMN HOLDS, then the second column, then a
    # third if a season ever runs more entries than two columns take.
    top, foot = box[1] + 58, box[3] - 66
    columns, per, step = _columns(len(table), top, foot, least=34, most=46)
    wide = (box[2] - box[0] - 24) // columns
    for index, line in enumerate(table):
        column, seat = divmod(index, per)
        cell = [box[0] + 12 + column * wide, 0,
                box[0] + 12 + (column + 1) * wide - 12, 0]
        _bar_row(pen, cell, top + seat * step + step // 2,
                 _hex(line.get("colour")),
                 float(line["points"]) / lead, line["pos"], line["code"],
                 line["team"], line["points"],
                 f"{line['wins']}W" if int(line["wins"] or 0) else "",
                 tall=min(30, step - 6), room=wide - 300)
    _title_band(pen, box, state, table)
    _foot(pen, now)
    return board


def page_constructors(now, state) -> Image.Image:
    """EVERY CONSTRUCTOR, not the first six — and what each has won."""
    board = backdrop()
    pen = ImageDraw.Draw(board)
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · ترتيب الفرق",
              f"ROUND {state.get('round', '')} OF {state.get('rounds', '')}",
              "CONSTRUCTORS", (90, 110, 150, 255))

    teams = state.get("teams") or []
    box = [PAD, 122, W - PAD, H - 116]
    _panel(pen, box, "CONSTRUCTORS' CHAMPIONSHIP")
    if not teams:
        draw_text(pen, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2),
                  "لا يوجد ترتيب للفرق بعد", 20, MUTED, anchor="mm",
                  thin=True)
        _foot(pen, now)
        return board

    top = float(teams[0]["points"]) or 1
    y = box[1] + 62
    step = max(38, min(56, (box[3] - 40 - y) // max(1, len(teams))))
    for line in teams:
        tone = team_colour(line["name"])
        _bar_row(pen, box, y, tone, float(line["points"]) / top,
                 line["pos"], line["name"][:24], line.get("nationality", ""),
                 line["points"],
                 (f"{line.get('wins', '0')} win"
                  + ("s" if int(line.get("wins") or 0) != 1 else ""))
                 if int(line.get("wins") or 0) else "",
                 tall=min(34, step - 8), room=200)
        y += step
    _foot(pen, now)
    return board


def page_last(now, state) -> Image.Image:
    """THE LAST RACE, CLASSIFIED IN FULL — gap, laps, points, and why
    a car that is not on the list is not on it.

    Six rows of code and team were all this channel kept of a Grand
    Prix. The same answer carries every finisher, the gap each was
    beaten by, the status of anyone who did not finish, the laps they
    completed and the points they took — so all of it is on the board.
    """
    board = backdrop()
    pen = ImageDraw.Draw(board)
    last = state.get("last") or {}
    rows = last.get("top") or []
    where = (last.get("at") or "").upper()
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · نتيجة آخر سباق",
              clipped(where, 17, 420, weight="heavy") if where else "",
              "LAST RACE", (90, 110, 150, 255))

    box = [PAD, 122, W - PAD, H - 176]
    _panel(pen, box, "CLASSIFICATION")
    if not rows:
        draw_text(pen, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2),
                  "لا توجد نتيجة سباق بعد", 20, MUTED, anchor="mm",
                  thin=True)
    else:
        top, foot = box[1] + 56, box[3] - 12
        columns, per, step = _columns(len(rows), top, foot, least=32,
                                      most=44)
        wide = (box[2] - box[0] - 24) // columns
        for index, line in enumerate(rows):
            column, seat = divmod(index, per)
            x = box[0] + 12 + column * wide
            y = top + seat * step
            tone = _hex(line.get("colour")) or team_colour(line["team"])
            pen.rounded_rectangle([x, y, x + wide - 14, y + step - 6],
                                  radius=7, fill=PANEL_ALT)
            pen.rounded_rectangle([x + 4, y + 5, x + 10, y + step - 11],
                                  radius=3, fill=tone)
            draw_text(pen, (x + 26, y + (step - 6) // 2), line["pos"], 17,
                      F1_RED if line["pos"] == "1" else WHITE, anchor="lm",
                      weight="heavy")
            draw_text(pen, (x + 58, y + (step - 6) // 2), line["code"], 19,
                      WHITE, anchor="lm", weight="heavy")
            draw_text(pen, (x + 112, y + (step - 6) // 2),
                      clipped(line["team"], 14, 118, weight="mid"), 14,
                      _lift(tone), anchor="lm", weight="mid")
            # THE GAP, OR WHY THERE ISN'T ONE. A retirement says what
            # stopped the car instead of leaving the column blank.
            gap = line.get("gap") or ""
            out = not (line.get("status") or "").startswith("Finished") \
                and not gap[:1].isdigit() and gap
            draw_text(pen, (x + wide - 78, y + (step - 6) // 2),
                      clipped(gap, 14, wide - 300, weight="mid"), 14,
                      F1_RED if out else (160, 176, 202, 255), anchor="rm",
                      weight="mid")
            points = line.get("points") or "0"
            draw_text(pen, (x + wide - 24, y + (step - 6) // 2),
                      points if points != "0" else "—", 17,
                      WHITE if points != "0" else RULE, anchor="rm",
                      weight="heavy")

    # THE FASTEST LAP OF THAT RACE, on a band of its own.
    band = [PAD, H - 166, W - PAD, H - 108]
    best = last.get("fastest") or {}
    pen.rounded_rectangle(band, radius=10, fill=PANEL_ALT)
    draw_text(pen, (band[0] + 20, (band[1] + band[3]) // 2), "FASTEST LAP",
              14, MUTED, anchor="lm", thin=True)
    if best.get("time"):
        tone = _lift(_hex(best.get("colour")), 0.3)
        draw_text(pen, (band[0] + 140, (band[1] + band[3]) // 2),
                  best.get("code") or "", 22, tone, anchor="lm",
                  weight="heavy")
        draw_text(pen, (band[0] + 210, (band[1] + band[3]) // 2),
                  best["time"], 24, WHITE, anchor="lm", weight="heavy")
        said = []
        if best.get("lap"):
            said.append(f"on lap {best['lap']}")
        if best.get("kph"):
            said.append(f"{best['kph']} km/h average")
        if said:
            draw_text(pen, (band[2] - 20, (band[1] + band[3]) // 2),
                      "  ·  ".join(said), 15, (160, 176, 202, 255),
                      anchor="rm", weight="mid")
    else:
        draw_text(pen, (band[0] + 140, (band[1] + band[3]) // 2),
                  "لم يُسجَّل", 16, MUTED, anchor="lm", thin=True)
    _foot(pen, now)
    return board


def page_qualifying(now, state) -> Image.Image:
    """THE WHOLE GRID, AND ALL THREE PARTS OF IT.

    Four rows and one time were what this kept. Q1 and Q2 are how the
    back half of the grid was decided and they were being thrown away,
    so every driver's three laps are here — the ones they did not set
    left blank rather than filled with a dash that looks like a time.
    """
    board = backdrop()
    pen = ImageDraw.Draw(board)
    rows = (state.get("qualifying")
            or (state.get("last") or {}).get("qualifying") or [])
    where = ((state.get("last") or {}).get("at") or "").upper()
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · نتيجة التجارب",
              clipped(where, 17, 420, weight="heavy") if where else "",
              "QUALIFYING", (167, 139, 250, 255))

    box = [PAD, 122, W - PAD, H - 116]
    _panel(pen, box, "STARTING ORDER")
    if not rows:
        draw_text(pen, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2),
                  "لا توجد نتيجة تجارب بعد", 20, MUTED, anchor="mm",
                  thin=True)
        _foot(pen, now)
        return board

    top, foot = box[1] + 78, box[3] - 14
    columns, per, step = _columns(len(rows), top, foot, least=32, most=44)
    wide = (box[2] - box[0] - 24) // columns
    for column in range(columns):
        x = box[0] + 12 + column * wide
        for label, at in (("Q1", 0.50), ("Q2", 0.68), ("Q3", 0.86)):
            draw_text(pen, (x + int((wide - 14) * at), top - 22), label, 13,
                      MUTED, anchor="mm", thin=True)
    for index, line in enumerate(rows):
        column, seat = divmod(index, per)
        x = box[0] + 12 + column * wide
        y = top + seat * step
        tone = _hex(line.get("colour")) or team_colour(line.get("team", ""))
        pen.rounded_rectangle([x, y, x + wide - 14, y + step - 6], radius=7,
                              fill=PANEL_ALT)
        pen.rounded_rectangle([x + 4, y + 5, x + 10, y + step - 11],
                              radius=3, fill=tone)
        mid = y + (step - 6) // 2
        draw_text(pen, (x + 26, mid), line["pos"], 17,
                  (167, 139, 250, 255) if line["pos"] == "1" else WHITE,
                  anchor="lm", weight="heavy")
        draw_text(pen, (x + 58, mid), line["code"], 19, WHITE, anchor="lm",
                  weight="heavy")
        if line.get("team"):
            draw_text(pen, (x + 114, mid),
                      clipped(line["team"], 14,
                              int((wide - 14) * 0.50) - 132, weight="mid"),
                      14, _lift(tone), anchor="lm", weight="mid")
        for key, at in (("q1", 0.50), ("q2", 0.68), ("q3", 0.86)):
            said = line.get(key) or ""
            if not said:
                continue
            best = key == "q3" or (key == "q2" and not line.get("q3")) \
                or (key == "q1" and not line.get("q2") and not line.get("q3"))
            draw_text(pen, (x + int((wide - 14) * at), mid), said, 14,
                      WHITE if best else (146, 162, 190, 255), anchor="mm",
                      weight="heavy" if best else "mid")
    _foot(pen, now)
    return board


def page_session(now, state) -> Image.Image:
    """THE NUMBERS A SESSION LEAVES BEHIND — fastest lap and its three
    sectors, the trap, the pit stops, and what rubber everyone is on."""
    board = backdrop()
    pen = ImageDraw.Draw(board)
    live = state.get("live") or {}
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · تفاصيل الجلسة",
              f"{(live.get('circuit') or '').upper()}", "SESSION",
              (90, 110, 150, 255))

    best = state.get("fastest")
    box = [PAD, 122, W - PAD, 320]
    y = _panel(pen, box, "FASTEST LAP")
    if best:
        draw_text(pen, (box[0] + 24, y + 16), best["code"], 34,
                  _hex(best.get("colour")), anchor="lm", weight="heavy")
        draw_text(pen, (box[0] + 130, y + 16), _lap(best["time"]), 40, WHITE,
                  anchor="lm", weight="heavy")
        draw_text(pen, (box[2] - 24, y + 16), f"lap {best['lap']}", 17, MUTED,
                  anchor="rm", thin=True)
        x = box[0] + 24
        for number, part in enumerate(best.get("sectors") or (), start=1):
            pen.rounded_rectangle([x, y + 54, x + 168, y + 100], radius=8,
                                  fill=PANEL_ALT)
            draw_text(pen, (x + 16, y + 77), f"SECTOR {number}", 14, MUTED,
                      anchor="lm", weight="mid")
            draw_text(pen, (x + 152, y + 77), f"{part:.3f}", 22, WHITE,
                      anchor="rm", weight="heavy")
            x += 182
        if best.get("trap"):
            draw_text(pen, (box[2] - 24, y + 77),
                      f"speed trap {best['trap']} km/h", 17, MUTED,
                      anchor="rm", weight="mid")
    else:
        draw_text(pen, ((box[0] + box[2]) // 2, y + 60),
                  "لا يوجد زمن لفة بعد", 18, MUTED, anchor="mm", thin=True)

    tyres = state.get("tyres") or []
    box = [PAD, 338, PAD + 700, H - 116]
    y = _panel(pen, box, "TYRES")
    if tyres:
        x, row = box[0] + 30, y + 10
        for stint in tyres[:12]:
            tone = TYRE_COLOUR.get((stint.get("compound") or "").upper(),
                                   MUTED)
            pen.ellipse([x, row, x + 52, row + 52], outline=tone, width=6)
            draw_text(pen, (x + 26, row + 26),
                      (stint.get("compound") or "?")[0], 22, tone,
                      anchor="mm", weight="heavy")
            draw_text(pen, (x + 26, row + 70),
                      str(stint.get("code") or f"#{stint.get('driver_number')}"),
                      15, WHITE, anchor="mm", weight="mid")
            if stint.get("laps"):
                draw_text(pen, (x + 26, row + 92), f"{stint['laps']} laps", 12,
                          MUTED, anchor="mm", thin=True)
            x += 82
            if x + 52 > box[2] - 20:
                x, row = box[0] + 30, row + 120
                if row + 52 > box[3] - 20:
                    break
    else:
        draw_text(pen, ((box[0] + box[2]) // 2, y + 60),
                  "لا توجد بيانات إطارات", 18, MUTED, anchor="mm", thin=True)

    box = [PAD + 724, 338, W - PAD, H - 116]
    y = _panel(pen, box, "SESSION")
    top = state.get("top_speed")
    if top:
        draw_text(pen, (box[0] + 22, y + 6), "TOP SPEED", 14, MUTED,
                  anchor="lm", thin=True)
        draw_text(pen, (box[0] + 22, y + 40), f"{top['kph']}", 34,
                  _hex(top.get("colour")), anchor="lm", weight="heavy")
        draw_text(pen, (box[0] + 110, y + 40), f"km/h  {top['code']}", 17,
                  WHITE, anchor="lm", weight="mid")
    pits = state.get("pits")
    if pits:
        draw_text(pen, (box[0] + 22, y + 88), "PIT STOPS", 14, MUTED,
                  anchor="lm", thin=True)
        draw_text(pen, (box[0] + 22, y + 122), str(pits["count"]), 34, WHITE,
                  anchor="lm", weight="heavy")
        if pits.get("best"):
            draw_text(pen, (box[0] + 100, y + 122),
                      f"fastest {pits['best']}  {pits['s']}s", 16, MUTED,
                      anchor="lm", weight="mid")
    _foot(pen, now)
    return board


def draw_between(now, viewer, state) -> Image.Image:
    """No circuit at all. The championship, and what is coming."""
    board = backdrop()
    pen = ImageDraw.Draw(board)
    nxt = state["next"]
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · بطولة العالم",
              f"ROUND {nxt['round']} · {nxt['country'].upper()}",
              countdown(now, nxt["race_at"]), F1_RED)

    left = [PAD, 122, PAD + 530, H - 116]
    y = _panel(pen, left, "NEXT GRAND PRIX")
    draw_text(pen, (left[0] + 20, y + 10),
              clipped(nxt["name"], 27, left[2] - left[0] - 40,
                      weight="heavy"), 27, WHITE, anchor="lm", weight="heavy")
    draw_text(pen, (left[0] + 20, y + 42),
              f"{nxt['circuit']} · {nxt['locality']}, {nxt['country']}", 15,
              F1_RED, anchor="lm", weight="mid")
    row = _session_rows(pen, left, y + 78, nxt["sessions"], viewer)

    draw_text(pen, (left[0] + 20, row + 14), "SEASON", 13, MUTED, anchor="lm",
              thin=True)
    bar = [left[0] + 20, row + 30, left[2] - 20, row + 42]
    pen.rounded_rectangle(bar, radius=6, fill=PANEL_ALT)
    done = int(state["round"]) / max(1, int(state["rounds"]))
    pen.rounded_rectangle([bar[0], bar[1],
                           bar[0] + int((bar[2] - bar[0]) * done), bar[3]],
                          radius=6, fill=F1_RED)
    draw_text(pen, (left[2] - 20, row + 60),
              f"round {state['round']} of {state['rounds']} run", 14, MUTED,
              anchor="rm", thin=True)

    # AND THE WEATHER AT THAT CIRCUIT, in the foot of the same panel.
    # This is the board on screen the five days a week nothing runs, and
    # under it was empty space — so the reading that answers "what is it
    # like there right now" goes where the eye already is, rather than
    # only on a page two turns of the reel away.
    sky = state.get("weather") or {}
    band = [left[0] + 20, H - 224, left[2] - 20, H - 136]
    floor = (band[1] - 14) if sky.get("air_c") is not None else H - 132

    # AND THE CIRCUIT ITSELF, in the room the sessions leave. A viewer
    # recognises Monza's straights or Monaco's harbour before they read
    # either name, and this board has already paid for the coordinates.
    if state.get("shape") and row + 86 < floor - 40:
        draw_track(board, pen, state["shape"],
                   [left[0] + 40, row + 86, left[2] - 40, floor],
                   rotation=state.get("rotation", 0),
                   tone=(78, 96, 132, 255), width=5)
    draw_weather(pen, band, sky)


    right = [PAD + 554, 122, W - PAD, H - 160]  # its foot carries the title
    y = _panel(pen, right, "DRIVERS' CHAMPIONSHIP")
    table = state.get("drivers") or []
    # AS MANY DRIVERS AS THE PANEL HOLDS, not eight. Eight was the count
    # that fit when the fetch only returned eight; the panel's foot is
    # the only real limit and it holds more than that.
    lead = float(table[0]["points"]) if table else 1
    room = (right[3] - 52) - y
    step = 34
    fits = max(1, room // step)
    if len(table) > fits:                 # spread to the foot rather than
        step = max(28, room // min(len(table), room // 28 or 1))
        fits = max(1, room // step)
    for line in table[:fits]:
        _bar_row(pen, right, y + step // 2 - 6, _hex(line.get("colour")),
                 float(line["points"]) / max(lead, 1), line["pos"],
                 line["code"], line["team"], line["points"],
                 f"{line['wins']}W" if int(line["wins"]) else "",
                 tall=min(28, step - 4), room=160)
        y += step

    # THE TITLE, on the championship's own foot rather than in a panel
    # of its own — it is two numbers about the table above it, and a
    # panel around them was a box to hold a sentence.
    if len(table) >= 2:
        gap = int(table[0]["points"]) - int(table[1]["points"])
        rounds_left = int(state["rounds"]) - int(state["round"])
        left_pts = rounds_left * 25
        line = right[3] - 46
        pen.line([(right[0] + 20, line), (right[2] - 20, line)], fill=RULE,
                 width=1)
        draw_text(pen, (right[0] + 20, line + 24),
                  f"{table[0]['code']} leads by {gap}", 17,
                  _lift(_hex(table[0].get("colour")), 0.35), anchor="lm",
                  weight="heavy")
        draw_text(pen, (right[0] + 200, line + 24),
                  f"{left_pts} still available over {rounds_left} rounds", 15,
                  (160, 176, 202, 255), anchor="lm", weight="mid")
        settled = gap > left_pts
        draw_text(pen, (right[2] - 20, line + 24),
                  "DECIDED" if settled else "STILL OPEN", 14,
                  F1_RED if settled else GREEN_FLAG, anchor="rm",
                  weight="heavy")

    # THE TRACK AND THE CHAMPIONSHIP HAVE PAGES OF THEIR OWN NOW, so
    # this one keeps a short signpost rather than a squeezed copy of
    # either. Nothing is lost — it is on the next board round.
    facts = state.get("facts") or {}
    told = []
    if facts.get("corners"):
        told.append(f"{facts['corners']} corners")
    if facts.get("laps"):
        told.append(f"{facts['laps']} laps")
    if facts.get("type"):
        told.append(facts["type"].lower())
    if told:
        draw_text(pen, (PAD + 574, H - 140), "  ·  ".join(told), 16,
                  (150, 166, 194, 255), anchor="lm", weight="mid")
    _foot(pen, now)
    return board


def draw_weekend(now, viewer, state) -> Image.Image:
    """The cars are at a circuit but not on it. What is next, and what
    the last session said."""
    board = backdrop()
    pen = ImageDraw.Draw(board)
    nxt = state["next"]
    ahead = state.get("next_session")
    _masthead(board, pen, "FORMULA 1", "الفورمولا ١ · نهاية أسبوع السباق",
              f"{nxt['circuit'].upper()} · {nxt['country'].upper()}",
              countdown(now, ahead[1]) if ahead else "WEEKEND", F1_RED)

    left = [PAD, 122, PAD + 610, H - 116]
    y = _panel(pen, left, "THIS WEEKEND")
    draw_text(pen, (left[0] + 20, y + 10),
              clipped(nxt["name"], 27, left[2] - left[0] - 40,
                      weight="heavy"), 27, WHITE, anchor="lm", weight="heavy")
    _session_rows(pen, left, y + 62, nxt["sessions"], viewer)

    track = [PAD + 634, 122, W - PAD, 420]
    pen.rounded_rectangle(track, radius=14, fill=PANEL, outline=RULE, width=1)
    draw_text(pen, (track[0] + 20, track[1] + 24), "CIRCUIT", 16, MUTED,
              anchor="lm", weight="mid")
    if state.get("shape"):
        draw_track(board, pen, state["shape"],
                   [track[0] + 40, track[1] + 48, track[2] - 40,
                    track[3] - 20], rotation=state.get("rotation", 0),
                   tone=(90, 110, 150, 255), width=6)

    box = [PAD + 634, 438, W - PAD, H - 116]
    y = _panel(pen, box, f"LAST RACE · {state['last']['at'].upper()}")
    for line in (state["last"].get("top") or [])[:4]:
        _driver_row(pen, box[0] + 16, y - 12, box[2] - box[0] - 32,
                    line["pos"], line["code"], line.get("team", ""),
                    f"GRID {line['grid']}  ·  P{line['pos']}", tall=32,
                    lead=line["pos"] == "1")
        y += 38
    _foot(pen, now)
    return board


def selftest() -> int:
    """Draw all three boards from a made-up state, so a name that is not
    defined is found here rather than on a runner.

    THIS EXISTS BECAUSE ONE WAS NOT. _dim went missing when this file was
    trimmed, every import still passed, and the channel got as far as a
    GitHub runner before anything said so — "F1: between — round 13 of
    23", then NameError. A drawing is not exercised by importing it.
    """
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    now = datetime.now(timezone.utc)
    viewer = ZoneInfo("Asia/Riyadh")
    # A WHOLE FIELD, because the pages now draw a whole field. Eight
    # rows never found the column that a twentieth row falls into.
    teams_of = ["Mercedes", "Ferrari", "McLaren", "Red Bull", "Williams",
                "Aston Martin", "Alpine", "Racing Bulls", "Haas", "Sauber"]
    table = [{"pos": str(n), "code": f"D{n:02d}",
              "team": teams_of[(n - 1) % len(teams_of)],
              "points": str(max(0, 300 - n * 14)), "wins": str(max(0, 5 - n)),
              "name": f"Driver {n}", "number": str(n), "nationality": "British",
              "colour": "00D7B6"}
             for n in range(1, 21)]
    nxt = {"round": "14", "name": "A Grand Prix", "circuit": "A Circuit",
           "locality": "A Town", "country": "A Country",
           "race_at": now + timedelta(days=4),
           "sessions": [(n, now + timedelta(days=2, hours=h)) for h, n in
                        enumerate(("FP1", "FP2", "FP3", "QUALIFYING",
                                   "RACE"))]}
    last = {"at": "A Grand Prix", "circuit": "A Circuit", "date": "2026-09-06",
            "top": [{"pos": str(n), "code": f"D{n:02d}",
                     "team": teams_of[(n - 1) % len(teams_of)], "grid": "9",
                     "laps": "53" if n < 18 else "31",
                     "points": str(max(0, 26 - n * 3)),
                     "name": f"Driver {n}",
                     "gap": ("1:32:11.204" if n == 1 else
                             (f"+{n * 3}.402" if n < 18 else
                              ("Power Unit" if n == 18 else "Collision"))),
                     "status": ("Finished" if n < 18 else "Retired"),
                     "colour": "ED1131"} for n in range(1, 21)],
            "fastest": {"code": "D03", "time": "1:19.813", "lap": "44",
                        "kph": "231.402", "colour": "ED1131"},
            "qualifying": [{"pos": str(n), "code": f"D{n:02d}",
                            "team": teams_of[(n - 1) % len(teams_of)],
                            "q1": f"1:2{n%10}.400",
                            "q2": f"1:2{n%10}.100" if n <= 15 else "",
                            "q3": f"1:19.{800+n}" if n <= 10 else "",
                            "time": f"1:19.{800+n}" if n <= 10 else
                                    f"1:2{n%10}.100",
                            "colour": "00A1E8"} for n in range(1, 21)]}
    state = {"round": "13", "rounds": "23", "drivers": table,
             "teams": [{"pos": str(n), "name": name,
                        "points": str(max(0, 480 - n * 45)),
                        "wins": str(max(0, 4 - n)), "nationality": "German"}
                       for n, name in enumerate(teams_of, start=1)],
             "last": last, "next": nxt, "next_session": nxt["sessions"][0],
             "qualifying": last["qualifying"],
             "shape": [[0, 0], [900, 200], [1400, 900], [400, 1200]],
             "rotation": 20, "corners": 11,
             "facts": {"corners": 11, "laps": "53", "held": "74",
                       "first": "1950", "type": "Permanent",
                       "last_winner": "ANT", "last_winner_year": "2026",
                       "most_wins": ("HAM", 5)},
             "weather": {"air_c": 11.7, "feels_c": 8.0, "surface_c": 10.1,
                         "humidity": 67, "wind_kmh": 17.5, "rain_mm": 0.0,
                         "rain_chance": 17, "code": 2, "day": False,
                         "observed": "2026-09-09T23:30", "zone": "AEST",
                         "where": "Melbourne, Australia"}}
    live = {"session": "Race", "circuit": "A Circuit", "country": "A Country",
            "flag": "GREEN", "lap": 12, "laps": 53,
            "weather": {"track_temperature": 41.0, "air_temperature": 27.0,
                        "humidity": 40.0, "rainfall": 0, "wind_speed": 1.2},
            "order": [{"code": "ABC", "team": "Mercedes", "colour": "00D7B6",
                       "gap": "LEADER" if n == 1 else f"+{n}.100"}
                      for n in range(1, 10)],
            "fastest": {"code": "ABC", "colour": "00D7B6", "lap": 11,
                        "time": 83.5, "sectors": [27.2, 28.6, 27.5],
                        "trap": 314},
            "top_speed": {"code": "XYZ", "kph": 338, "colour": "ED1131"},
            "pits": {"count": 12, "best": "ABC", "s": 24.2},
            "shape": state["shape"], "rotation": 20, "corners": 11}
    drawn = 0
    for name, call in (("live", lambda: draw_live(now, live)),
                       ("weekend", lambda: draw_weekend(now, viewer, state)),
                       ("between", lambda: draw_between(now, viewer, state))):
        board = call()
        if board.size != (W, H):
            print(f"  FAIL {name}: {board.size}")
            return 1
        drawn += 1
        print(f"  ok   {name} board drawn {board.size}")
    # and with everything optional missing, which is what a rate-limited
    # pass actually hands it
    bare = dict(state, qualifying=[], shape=[], teams=[], facts={})
    draw_between(now, viewer, bare)
    print("  ok   between board with nothing optional in it")
    draw_weekend(now, viewer, bare)
    print("  ok   weekend board with no facts to tell")
    half = dict(state, facts={"corners": 11})
    draw_between(now, viewer, half)
    print("  ok   between board knowing only the corner count")

    # THE PAGES THAT CARRY WHAT THE FIRST BOARD NO LONGER CRAMS IN
    live["tyres"] = [{"compound": "SOFT", "code": "ANT", "laps": 12},
                     {"compound": "MEDIUM", "code": "RUS", "laps": 20},
                     {"compound": "HARD", "code": "VER", "laps": 31}]
    for name, call in (("track", lambda: page_track(now, state)),
                       ("championship", lambda: page_championship(now, state)),
                       ("constructors", lambda: page_constructors(now, state)),
                       ("last race", lambda: page_last(now, state)),
                       ("qualifying", lambda: page_qualifying(now, state)),
                       ("session", lambda: page_session(now, live))):
        board = call()
        if board.size != (W, H):
            print(f"  FAIL {name}: {board.size}")
            return 1
        drawn += 1
        print(f"  ok   {name} page drawn {board.size}")
    page_track(now, dict(state, facts={}, shape=[]))
    print("  ok   track page with no facts and no shape")
    page_track(now, dict(state, weather={}))
    print("  ok   track page with no weather back from the forecast")
    page_track(now, dict(state, weather={"air_c": 31.0, "code": 63,
                                         "rain_chance": 80, "rain_mm": 1.4,
                                         "where": "A Town, A Country",
                                         "observed": "2026-09-09T15:30"}))
    print("  ok   track page in the wet, with half the readings missing")
    page_track(now, dict(state, facts={}, shape=[], weather={}))
    print("  ok   track page with nothing on it at all")
    page_session(now, {})
    print("  ok   session page with nothing measured yet")

    # AND EVERY NEW PAGE WITH NOTHING TO PUT ON IT, which is what a
    # rate-limited pass or the week before round one actually hands over.
    page_championship(now, dict(state, drivers=[]))
    page_constructors(now, dict(state, teams=[]))
    page_last(now, dict(state, last={}))
    page_qualifying(now, dict(state, qualifying=[], last={}))
    print("  ok   all four table pages with nothing in them")
    # a season half the length, and one longer than two columns hold
    page_championship(now, dict(state, drivers=table[:5]))
    page_championship(now, dict(state, drivers=table * 3))
    page_last(now, dict(state, last=dict(last, top=last["top"][:3],
                                         fastest={})))
    page_qualifying(now, dict(state, qualifying=last["qualifying"][:2]))
    print("  ok   short fields, an over-long one, and a race with no "
          "fastest lap")
    print(f"{drawn} board(s) drawn")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
