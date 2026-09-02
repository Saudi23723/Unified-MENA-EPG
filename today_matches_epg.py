#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مباريات اليوم — one channel that answers the day on a single page.

Every other guide here answers "what is on THIS channel". This one answers
the question a viewer starts with: what is on today, and where do I watch
it — and it answers it without the viewer pressing anything. Highlighting
the channel is enough, because the whole day lives in the description:

    ⏳ بعد 45 دقيقة · Flamengo RJ - Mirassol        <- what the grid shows
    ------------------------------------------------------------------
    مباريات الأربعاء 02/09 — بتوقيت +03:00          <- what the panel shows
      🔴  19:00  Colegiales - Midland · LPF Play
      ⏳  19:30  Flamengo RJ - Mirassol · Flamengo TV YouTube
          21:00  Al Wehda FC - Damac FC · Thmanyah 1 HD

One programme per day, not one per match, and emphatically not one per
countdown step. The first shape published 119 rows for a dozen matches:
a single match owned eight consecutive fifteen-minute blocks that differed
only in an Arabic tail, and a television truncates titles from the right,
so all eight rendered as the same cut-off name. The counter was in the
file and invisible on the screen — all of the cost, none of the benefit.
It is now one row a day, and the counter rides at the FRONT of that row's
title where truncation cannot reach it.

Source — livefootballtv's front page, which lists every match of the day
with every channel carrying it, worldwide. It is the only source here that
publishes the channel list, which is the whole point of this guide.

On its clock, learned the hard way: each row carries both a displayed time
in td.hora and a schema.org startDate in the markup. Measured across 567
rows on one page, the displayed time is exactly two hours ahead of the
markup, flat — the site prints its own local wall clock. So the markup is
the UTC instant and it is what this reads. Deriving the time from the
visible cell means guessing which timezone the site is in today, and that
guess is what put a guide three hours out once already.

Football only, for now. The page covers other sports thinly and they can
be added later without touching what is here.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta, timezone

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

from epg_lib import (
    MATCH_ON_AIR, add_programme, arabic_count, countdown_label, fetch,
    in_reading_order, isolate, log, norm, warn, write_xml_atomic,
)

SOURCE = "https://www.livefootballtv.info/"
OUTPUT = "today_matches_epg.xml"
# An id of its own, not a borrowed one.
#
# Nothing in a viewer's playlist carries this id, and that is deliberate:
# the viewer points whichever channel they like at this guide themselves,
# which every player worth using can do. Borrowing a real channel's id was
# tried and was wrong twice over — it guesses at a playlist nobody here
# can see, and it takes the guide away from that channel to give it here.
CHANNEL_ID = "TodayMatches"
CHANNEL_AR = "مباريات اليوم"
CHANNEL_EN = "Today's Matches"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/today_matches.png")

UTC = timezone.utc

# The clock the list is printed in. Every reader of this guide is in the
# Gulf or the Levant, and a list of kickoffs is useless in a timezone the
# reader has to convert out of: the programme times a player positions the
# row by are converted for them, but the text inside a description is not.
VIEWER = timezone(timedelta(hours=3))

ARABIC_DAY = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس",
              "الجمعة", "السبت", "الأحد")

# How far forward to publish. The page carries a couple of days and a
# viewer scrolling ahead should find them.
KEEP_AHEAD = timedelta(days=2)

# One channel per match. The page has to fit on a television screen in one
# go, and every extra name pushes a line into wrapping onto a second — so
# the list costs two lines for one match and the day stops fitting. The
# first channel named is the one the source lists first.
MAX_CHANNELS = 1

# How wide a line may get before a television wraps it onto a second one.
# Simultaneous kickoffs share a line only while they stay inside this:
# measured, two full fixtures came to 92 characters and wrapped, which
# spends the line the merge was meant to save. Merging is only worth doing
# when it actually removes a line.
LINE_BUDGET = 60

# Inside an hour a printed countdown is stale enough to mislead, so it is
# rounded up to one of these and stated as a bound rather than a fact.
NEAR_STEPS = (15, 30, 45, 60)

LIVE_MARK = "🔴"
NEXT_MARK = "⏳"

# Competitions worth a place on this channel, as the source names them.
#
# The source labels every match with its competition in a heading row
# (tr.cabeceraCompericion), so this is a list of real names read off the
# page, not a guess at club names. 539 matches across 46 competitions came
# down the wire on the day this was written; almost all of them are
# reserve, youth and third-tier football nobody asked to see.
#
# Matched exactly, because a substring would swallow the wrong thing:
# "Premier League" is also how Egypt, Bahrain, Iceland and Ukraine are
# labelled, none of which was asked for. Italy and Brazil are both wanted
# and are distinguished the same way — the page writes one "Serie A" and
# the other "Brazilian Serie A", so an exact match keeps them apart from
# each other and from "Italian Serie B".
WANTED_EXACT = {
    "saudi pro league", "premier league", "serie a", "brazilian serie a",
    "ligue 1", "laliga", "la liga", "bundesliga", "champions league",
    "europa league", "conference league",
    "turkish süper lig", "süper lig", "super lig",
}

# Matched anywhere in the name, for families whose members all belong:
# every FIFA and UEFA competition, the African and Asian confederations,
# the Gulf cups, Jordan, and the domestic cups of the leagues above.
WANTED_PARTS = (
    "fifa", "world cup", "uefa", "nations league",
    "caf ", "africa cup", "afcon", "afc ", "asian cup",
    "gulf cup", "arabian gulf", "jordan",
    "king cup", "coppa italia", "copa del rey", "coupe de france",
    "copa do brasil", "brasileir",
    "dfb", "fa cup", "efl cup", "carabao", "turkish cup",
)

# Clubs that belong here whatever they are playing in. Asked for by name,
# including the age groups and the women's side, which is why this guide
# has no blanket rule against "Reserva", "Femenino" or "U19" — such a rule
# would drop exactly the matches that were asked for.
WANTED_TEAMS = ("manchester united", "man united", "man utd", "manchester utd")

# The page labels the Austrian Bundesliga with exactly the word it uses for
# the German one, so "Bundesliga" alone let Austria Vienna, Tirol, Salzburg
# and SK Rapid onto the channel on the first day this ran.
#
# The clubs are the only thing that separates them, and it is Austria's
# twelve that are listed rather than Germany's eighteen — deliberately. A
# list of the wanted side would drop a promoted German club the season it
# came up, which is losing a match somebody asked for; a list of the
# unwanted side lets a promoted Austrian club through, which is one extra
# row nobody minds. When in doubt, keep the match.
AUSTRIAN_BUNDESLIGA = (
    "salzburg", "sturm graz", "rapid", "austria vienna", "austria wien",
    "lask", "wolfsberger", "hartberg", "blau-weiß linz", "blau-weiss linz",
    "tirol", "klagenfurt", "altach", "grazer ak",
)

# Worded so the build's own honesty measure counts it: a day with nothing
# on it is the guide saying it has nothing, not a broadcast.
NOTHING_TODAY = "لا توجد مباراة معلنة — No matches listed"


def sources_of(row) -> list[str]:
    """Every channel this row says carries the match, in the page's order."""
    canales = row.find("td", class_="canales")
    if not canales:
        return []
    seen: list[str] = []
    for item in canales.select("ul.listaCanales li"):
        label = norm(item.get("title") or item.get_text(" ", strip=True))
        # The page repeats a channel across its own regional feeds; keep
        # the first spelling and drop the rest.
        if label and label not in seen:
            seen.append(label)
    return seen


def team_in(cell) -> str:
    span = cell.find("span", title=True) if cell else None
    if span and span.get("title"):
        return norm(span["title"])
    return norm(cell.get_text(" ", strip=True)) if cell else ""


def is_match(row) -> bool:
    return bool(row.find("td", class_="local")
                and row.find("td", class_="visitante")
                and row.find("td", class_="canales"))


def competition_of(row) -> str:
    """The competition heading standing above this match row.

    The page groups matches under tr.cabeceraCompericion headings, so the
    nearest <tr> above that is not itself a match is the competition. It
    has to be restricted to rows: walking back over every element instead
    lands inside the previous match and returns a channel or a club name.
    """
    for previous in row.find_all_previous("tr"):
        if is_match(previous):
            continue
        head = norm(previous.get_text(" ", strip=True))
        if 2 < len(head) < 90:
            return head
    return ""


def wanted(event: dict) -> bool:
    """Is this a competition — or a club — that was actually asked for?"""
    competition = event["competition"].casefold()
    teams_folded = event["title"].casefold()

    # Austria borrows Germany's word for its league; the clubs are the only
    # thing that tells the two apart.
    if competition == "bundesliga" and any(club in teams_folded
                                           for club in AUSTRIAN_BUNDESLIGA):
        return False

    if competition in WANTED_EXACT:
        return True
    if any(part in competition for part in WANTED_PARTS):
        return True
    return any(club in teams_folded for club in WANTED_TEAMS)


def collect(html: str, now: datetime) -> list[dict]:
    """Every match worth showing, with its kickoff, channels and competition."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # The whole of the viewer's today, however much of it has already been
    # played — the description is a list of the day, not of what is left.
    floor = datetime.combine(now.astimezone(VIEWER).date(), time(0, 0),
                             VIEWER).astimezone(UTC)

    events: list[dict] = []
    no_time = no_channel = 0

    for row in soup.find_all("tr"):
        if not is_match(row):
            continue

        home = team_in(row.find("td", class_="local"))
        away = team_in(row.find("td", class_="visitante"))
        if not home or not away:
            continue

        # The markup instant, not the printed clock — see the module note.
        meta = row.find("td", class_="canales").find(
            "meta", attrs={"itemprop": "startDate"})
        raw = (meta.get("content") if meta else "") or ""
        try:
            start = datetime.fromisoformat(raw)
        except ValueError:
            no_time += 1
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        start = start.astimezone(UTC)

        if not (floor <= start <= now + KEEP_AHEAD):
            continue

        channels = sources_of(row)
        if not channels:
            # Without a channel this guide has nothing to say that the
            # other thirteen do not already say better.
            no_channel += 1
            continue

        events.append({
            "start": start,
            "title": f"{home} - {away}",
            "channels": channels,
            "competition": competition_of(row),
        })

    if no_time:
        log(f"  {no_time} row(s) carried no readable kickoff and were skipped")
    if no_channel:
        log(f"  {no_channel} row(s) named no channel and were skipped")

    # The same match can appear twice when the page lists it under two
    # competitions; one kickoff and one pair of names is one match.
    merged: dict[tuple, dict] = {}
    for event in sorted(events, key=lambda e: e["start"]):
        key = (event["start"], event["title"].casefold())
        if key in merged:
            for channel in event["channels"]:
                if channel not in merged[key]["channels"]:
                    merged[key]["channels"].append(channel)
        else:
            merged[key] = event

    everything = sorted(merged.values(), key=lambda e: e["start"])
    keep = [event for event in everything if wanted(event)]
    log(f"  {len(everything)} match(es) in the window, "
        f"{len(keep)} in a competition worth showing")
    return keep


def channels_of(event: dict) -> str:
    shown = event["channels"][:MAX_CHANNELS]
    more = len(event["channels"]) - len(shown)
    return " · ".join(shown) + (f" +{more}" if more > 0 else "")


def fixture_of(event: dict) -> str:
    """The one line a viewer is actually after: who, and on what."""
    channels = channels_of(event)
    return f"{event['title']} · {channels}" if channels else event["title"]


def when(start: datetime, now: datetime) -> str:
    """How long until this kicks off, rather than the hour it kicks off at.

    Asked for outright: a viewer glancing at the page wants "in forty
    minutes", not a clock they then have to subtract from. The words are
    spelled out rather than abbreviated for the reason countdown_label
    exists — single letters drift away from their numbers on a line that
    also carries Latin club names, and "19 س و30 د" was read three
    different ways on a television.

    A printed countdown is frozen the moment the file is written, and the
    file is read minutes or tens of minutes later, so a precise number is
    a number that is wrong. Near kickoff, where being wrong matters, this
    states an upper bound instead: the time left only ever shrinks, so
    "less than an hour" written at fifty minutes is still true at five.
    Coarser, and never a lie.

    Further out the bound is pointless — the gap between the build and the
    reading is nothing beside three hours — so the exact wording stands.
    """
    if start <= now:
        return "الآن"
    minutes = (start - now).total_seconds() // 60
    for step in NEAR_STEPS:
        if minutes <= step:
            return f"بعد أقل من {countdown_label(step)}"
    return f"بعد {countdown_label(minutes)}"


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Midnight to midnight in the viewer's clock, expressed in UTC."""
    opens = datetime.combine(day, time(0, 0), VIEWER).astimezone(UTC)
    return opens, opens + timedelta(days=1)


def day_name(day: date) -> str:
    return f"{ARABIC_DAY[day.weekday()]} {day:%d/%m}"


def day_title(day: date, events: list[dict], now: datetime) -> str:
    """What the grid shows for this day, on one line.

    The status rides at the FRONT. A television truncates a title from the
    right, so anything put after the names is thrown away before a viewer
    ever sees it — which is exactly how the previous shape lost every one
    of its countdowns.
    """
    if not events:
        return in_reading_order(f"{day_name(day)} — {NOTHING_TODAY}")

    live = [e for e in events if e["start"] <= now < e["start"] + MATCH_ON_AIR]
    if live:
        event = live[-1]
        return in_reading_order(
            f"{LIVE_MARK} مباشر {isolate('·')} {isolate(fixture_of(event))}",
            names=event["title"])

    ahead = [e for e in events if e["start"] > now]
    if ahead:
        event = ahead[0]
        minutes = (event["start"] - now).total_seconds() // 60
        return in_reading_order(
            f"{NEXT_MARK} بعد {countdown_label(minutes)} {isolate('·')} "
            f"{isolate(fixture_of(event))}",
            names=event["title"])

    # arabic_count carries the number itself — "مباراتان", "3 مباريات" —
    # so putting a numeral in front of it would say the count twice.
    count = arabic_count(len(events), "مباراة", "مباراتان", "مباريات", "مباراة")
    if day == now.astimezone(VIEWER).date():
        return in_reading_order(f"انتهت مباريات اليوم — {count}")
    return in_reading_order(f"مباريات {day_name(day)} — {count}")


def day_page(day: date, events: list[dict], now: datetime) -> str:
    """The whole day on one page — what a viewer sees without pressing.

    This is the guide. The grid row above it only says which match is next;
    everything a viewer came for is here, and highlighting the channel is
    enough to see it.

    Every line here is a line of a television screen, and a page that does
    not fit in one screenful is not one page. So: matches already over are
    dropped, kickoffs that share a time share a line, one channel is named
    per match, and there is no blank line under the header.
    """
    header = f"مباريات {day_name(day)} — بتوقيت +03:00"
    left = [e for e in events if e["start"] + MATCH_ON_AIR > now]
    if not left:
        return f"{header}\n{'انتهت مباريات اليوم' if events else NOTHING_TODAY}"

    # Kickoffs at the same minute are one entry, not one each.
    slots: list[list[dict]] = []
    for event in left:
        if slots and event["start"] == slots[-1][0]["start"]:
            slots[-1].append(event)
        else:
            slots.append([event])

    coming = next((e for e in left if e["start"] > now), None)
    lines = [header]
    for slot in slots:
        if any(e["start"] <= now for e in slot):
            mark = LIVE_MARK
        elif coming in slot:
            mark = NEXT_MARK
        else:
            mark = "  "
        opening = f"{mark} {when(slot[0]['start'], now)}  "
        line = opening
        for event in slot:
            fixture = fixture_of(event)
            if line != opening and len(line) + 3 + len(fixture) > LINE_BUDGET:
                lines.append(line)
                # A continuation of the same kickoff: the time is already
                # on the line above, and repeating it reads as two slots.
                line = "        "
            line += ("" if line in (opening, "        ") else " ، ") + fixture
        lines.append(line)
    return "\n".join(lines)


def build() -> int:
    now = datetime.now(UTC)
    session = requests.Session()
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        "Accept-Language": "ar,en;q=0.8,tr;q=0.6",
    })
    try:
        html = fetch(session, SOURCE).text
    except Exception as exc:
        warn(f"livefootballtv is unreachable ({exc}) — the previous guide "
             f"stays exactly as it is")
        return 1

    events = collect(html, now)
    for event in events[:12]:
        log(f"  {event['start']:%m-%d %H:%M}Z  {event['title']}"
            f"   │ {event['competition']}")

    tv = ET.Element("tv", {"generator-info-name": "Today's Matches"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    # Today first, then every further day the page reached, so a viewer
    # scrolling forward finds tomorrow rather than the end of the guide.
    today = now.astimezone(VIEWER).date()
    last = (now + KEEP_AHEAD).astimezone(VIEWER).date()
    days: list[date] = []
    day = today
    while day <= last:
        days.append(day)
        day += timedelta(days=1)

    by_day: dict[date, list[dict]] = {day: [] for day in days}
    for event in events:
        day = event["start"].astimezone(VIEWER).date()
        if day in by_day:
            by_day[day].append(event)

    for day in days:
        opens, closes = day_bounds(day)
        add_programme(tv, CHANNEL_ID, opens, closes,
                      day_title(day, by_day[day], now),
                      day_page(day, by_day[day], now))
        log(f"  {day} -> {len(by_day[day])} match(es) on one page")

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Today's Matches",
                          guard_regression=False, min_programmes=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
