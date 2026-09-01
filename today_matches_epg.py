#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مباريات اليوم — one channel whose timeline IS the day's football.

Every other guide in this repository answers "what is on THIS channel".
This one answers the question a viewer actually starts with: what is on
today, and where do I watch it. One channel, and scrolling it left to
right walks through the day:

    17:45 - 19:00   ⏰ بعد ساعة و15 دقيقة · Greece - Spain
    19:00 - 19:30      Greece - Spain        │ S Sport · S Sport Plus
    19:30 - 20:30      Lecce - Roma          │ S Sport 2 · S Sport Plus
    20:30 - 21:30      Osasuna - Getafe      │ S Sport Plus

Source — livefootballtv's front page, which lists every match of the day
with every channel carrying it, worldwide. It is the only source here that
publishes the channel list, which is the whole point of this guide, and it
is already read (and already understood) by two other generators.

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

import re
import sys
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, countdown_step, countdown_title, fetch, in_reading_order,
    isolate, log, norm, resolve_overlaps, warn, with_live_badge,
    write_xml_atomic,
)

SOURCE = "https://www.livefootballtv.info/"
OUTPUT = "today_matches_epg.xml"
CHANNEL_ID = "TodayMatches"
CHANNEL_AR = "مباريات اليوم"
CHANNEL_EN = "Today's Matches"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/today_matches.png")

UTC = timezone.utc

# How much of the day to carry. Behind, so a match that kicked off an hour
# ago is still on the strip; ahead, because the page publishes a couple of
# days and a viewer scrolling forward should find them.
KEEP_BEHIND = timedelta(hours=3)
KEEP_AHEAD = timedelta(days=2)

# How long a match occupies the strip. Not a claim about the broadcast —
# it is how long the row stays worth looking at, and the next match's row
# cuts it short anyway.
MATCH_MINUTES = 115

# A row with more channels than this is unreadable on a television, and
# past the tenth nobody is still counting.
MAX_CHANNELS = 8

NOTHING_TODAY = "لا توجد مباريات معلنة اليوم — No matches listed today"


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


def collect(html: str) -> list[dict]:
    """Every match on the page, with its kickoff and its channels."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    now = datetime.now(UTC)
    events: list[dict] = []
    no_time = no_channel = 0

    for row in soup.find_all("tr"):
        local = row.find("td", class_="local")
        visit = row.find("td", class_="visitante")
        canales = row.find("td", class_="canales")
        if not (local and visit and canales):
            continue

        home, away = team_in(local), team_in(visit)
        if not home or not away:
            continue

        # The markup instant, not the printed clock — see the module note.
        meta = canales.find("meta", attrs={"itemprop": "startDate"})
        raw = (meta.get("content") if meta else "") or ""
        try:
            start = datetime.fromisoformat(raw)
        except ValueError:
            no_time += 1
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        start = start.astimezone(UTC)

        if not (now - KEEP_BEHIND <= start <= now + KEEP_AHEAD):
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
    return sorted(merged.values(), key=lambda e: e["start"])


def strip_title(event: dict) -> str:
    """What one match's row says: the match, then where to watch it."""
    channels = event["channels"][:MAX_CHANNELS]
    more = len(event["channels"]) - len(channels)
    shown = " · ".join(channels) + (f" +{more}" if more > 0 else "")
    return in_reading_order(
        f"{isolate(event['title'])} {isolate('│')} {isolate(shown)}",
        names=event["title"])


def day_list(events: list[dict], now: datetime) -> str:
    """The whole day in the description, the way the photo showed it."""
    lines = [f"مباريات اليوم — {now:%Y-%m-%d} UTC", ""]
    for event in events:
        channels = " · ".join(event["channels"][:MAX_CHANNELS])
        lines.append(f"{event['start']:%H:%M}  {event['title']}"
                     + (f"   │ {channels}" if channels else ""))
    return "\n".join(lines) if len(lines) > 2 else NOTHING_TODAY


def build() -> int:
    now = datetime.now(UTC)
    try:
        html = fetch(SOURCE)
    except Exception as exc:
        warn(f"livefootballtv is unreachable ({exc}) — the previous guide "
             f"stays exactly as it is")
        return 1

    events = collect(html)
    log(f"today's matches with a named channel: {len(events)}")
    for event in events[:12]:
        log(f"  {event['start']:%m-%d %H:%M}Z  {event['title']}"
            f"   │ {' · '.join(event['channels'][:4])}")

    tv = ET.Element("tv", {"generator-info-name": "Today's Matches"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    description = day_list(events, now)

    if not events:
        add_programme(tv, CHANNEL_ID, now - KEEP_BEHIND, now + timedelta(hours=8),
                      NOTHING_TODAY, description)
        write_xml_atomic(tv, OUTPUT, generator_name="Today's Matches",
                         guard_regression=False)
        return 0

    # One block per match, each ending where the next begins.
    blocks: list[dict] = []
    for index, event in enumerate(events):
        natural = event["start"] + timedelta(minutes=MATCH_MINUTES)
        following = (events[index + 1]["start"] if index + 1 < len(events)
                     else None)
        stop = min(natural, following) if following else natural
        if stop <= event["start"]:
            continue
        blocks.append({"start": event["start"], "stop": stop,
                       "title": strip_title(event), "event": event})

    # And a countdown filling the space before the first one, so the strip
    # answers "what is next" at any moment rather than starting blank.
    first = blocks[0]["start"] if blocks else None
    if first and first > now - KEEP_BEHIND:
        cursor = now - KEEP_BEHIND
        while cursor < first:
            remaining = first - cursor
            stop = min(cursor + countdown_step(remaining), first)
            if stop <= cursor:
                break
            add_programme(tv, CHANNEL_ID, cursor, stop,
                          countdown_title(isolate(blocks[0]["event"]["title"]),
                                          remaining.total_seconds() // 60),
                          description)
            cursor = stop

    for block in resolve_overlaps(blocks):
        add_programme(tv, CHANNEL_ID, block["start"], block["stop"],
                      with_live_badge(block["title"]), description,
                      live_eligible=True, now=now)

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Today's Matches",
                          guard_regression=False, min_programmes=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
