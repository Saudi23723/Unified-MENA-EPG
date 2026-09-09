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
              clipped(team, 14, wide - 230, weight="mid"), 14, tone,
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


def _hex(code: str):
    code = (code or "").lstrip("#")
    if len(code) != 6:
        return MUTED
    return (int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16), 255)


def _clock(pen, x, y, label, value, tone=WHITE, big=30):
    draw_text(pen, (x, y), label, 13, MUTED, anchor="lm", thin=True)
    draw_text(pen, (x, y + 28), value, big, tone, anchor="lm", weight="heavy")


def _bar_row(pen, box, y, tone, share, pos, code, team, right, note=""):
    """One championship row: a bar as long as the points it stands for."""
    wide = box[2] - box[0] - 40
    pen.rounded_rectangle([box[0] + 20, y - 10, box[0] + 20 + int(wide * share),
                           y + 16], radius=6, fill=_dim(tone, 0.28))
    pen.rounded_rectangle([box[0] + 20, y - 10, box[0] + 26, y + 16],
                          radius=3, fill=tone)
    draw_text(pen, (box[0] + 38, y + 3), pos, 15, MUTED, anchor="lm",
              weight="mid")
    draw_text(pen, (box[0] + 62, y + 3), code, 18, WHITE, anchor="lm",
              weight="heavy")
    draw_text(pen, (box[0] + 116, y + 3),
              clipped(team, 14, 150, weight="mid"), 14, tone, anchor="lm",
              weight="mid")
    if note:
        draw_text(pen, (box[2] - 86, y + 3), note, 13, MUTED, anchor="rm",
                  thin=True)
    draw_text(pen, (box[2] - 20, y + 3), right, 17, WHITE, anchor="rm",
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

    # AND THE CIRCUIT ITSELF, in the room the sessions leave. A viewer
    # recognises Monza's straights or Monaco's harbour before they read
    # either name, and this board has already paid for the coordinates.
    if state.get("shape") and row + 86 < H - 150:
        draw_track(board, pen, state["shape"],
                   [left[0] + 40, row + 86, left[2] - 40, H - 132],
                   rotation=state.get("rotation", 0),
                   tone=(78, 96, 132, 255), width=5)


    right = [PAD + 554, 122, W - PAD, 486]  # its foot carries the title
    y = _panel(pen, right, "DRIVERS' CHAMPIONSHIP")
    table = state.get("drivers") or []
    lead = float(table[0]["points"]) if table else 1
    for line in table[:8]:
        _bar_row(pen, right, y, _hex(line.get("colour")),
                 float(line["points"]) / max(lead, 1), line["pos"],
                 line["code"], line["team"], line["points"],
                 f"{line['wins']} wins" if int(line["wins"]) else "")
        y += 34

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
                  _hex(table[0].get("colour")), anchor="lm", weight="heavy")
        draw_text(pen, (right[0] + 200, line + 24),
                  f"{left_pts} still available over {rounds_left} rounds", 15,
                  MUTED, anchor="lm", weight="mid")
        settled = gap > left_pts
        draw_text(pen, (right[2] - 20, line + 24),
                  "DECIDED" if settled else "STILL OPEN", 14,
                  F1_RED if settled else GREEN_FLAG, anchor="rm",
                  weight="heavy")

    facts = state.get("facts") or {}
    if any(facts.get(k) for k in ("corners", "laps", "held", "first")):
        draw_facts(pen, [PAD + 554, 504, W - PAD, H - 116], facts)
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

    facts = state.get("facts") or {}
    if any(facts.get(k) for k in ("corners", "laps", "held", "last_winner")):
        draw_facts(pen, [PAD + 634, 438, W - PAD, H - 116], facts)
        _foot(pen, now)
        return board

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
    table = [{"pos": str(n), "code": "ABC", "team": "Mercedes",
              "points": str(300 - n * 30), "wins": str(n), "colour": "00D7B6"}
             for n in range(1, 9)]
    nxt = {"round": "14", "name": "A Grand Prix", "circuit": "A Circuit",
           "locality": "A Town", "country": "A Country",
           "race_at": now + timedelta(days=4),
           "sessions": [(n, now + timedelta(days=2, hours=h)) for h, n in
                        enumerate(("FP1", "FP2", "FP3", "QUALIFYING",
                                   "RACE"))]}
    last = {"at": "A Grand Prix", "top": [
        {"pos": str(n), "code": "XYZ", "team": "Ferrari", "grid": "9",
         "colour": "ED1131"} for n in range(1, 5)]}
    state = {"round": "13", "rounds": "23", "drivers": table,
             "teams": [{"pos": "1", "name": "Mercedes", "points": "468"}],
             "last": last, "next": nxt, "next_session": nxt["sessions"][0],
             "qualifying": [{"pos": "1", "code": "GAS", "time": "1:21.786",
                             "colour": "00A1E8"}],
             "shape": [[0, 0], [900, 200], [1400, 900], [400, 1200]],
             "rotation": 20, "corners": 11,
             "facts": {"corners": 11, "laps": "53", "held": "74",
                       "first": "1950", "type": "Permanent",
                       "last_winner": "ANT", "last_winner_year": "2026",
                       "most_wins": ("HAM", 5)}}
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
    print(f"{drawn} board(s) drawn")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
