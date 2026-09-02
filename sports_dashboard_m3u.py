#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI Sports Dashboard — today's matches as a PLAYLIST, not as a guide.

Why this exists, after everything else was tried.

A guide file cannot lay anything out. It hands a player text and the
player decides what that looks like, which is why the day ended up as
lines in a description panel instead of the ruled board a viewer pictures.
The board was drawn and hung on the programme's <icon>; TiviMate ignored
it. That is the ceiling of an EPG, and no amount of work moves it.

A playlist is different. A player renders a playlist group as a full
screen list of rows — which is exactly the shape that was asked for. So
the day is written as a group of "channels", one per match, named with the
kickoff, the fixture and the broadcaster:

    AI Sports Dashboard
      19:00 · Real Madrid - Barcelona · beIN SPORTS 1
      21:45 · Al Hilal - Al Nassr · Thmanyah 1
      23:00 · Flamengo - Palmeiras · OneFootball

WHERE YOUR STREAM URLS GO
=========================
Every entry needs a URL to play. This file does not know yours and must
never hold them: a playlist URL carries your username and password, and
this repository is public.

So the mapping lives in a file of your own, next to this one:

    stream_map.json          <- yours, git-ignored, never committed

        {
          "beIN SPORTS 1": "http://your-provider/live/USER/PASS/1234.ts",
          "Thmanyah 1":    "http://your-provider/live/USER/PASS/5678.ts"
        }

The key is the broadcaster exactly as the guide names it; the value is the
URL of that channel in your own playlist. Copy it out of your m3u file —
the line under the #EXTINF for that channel.

A match whose broadcaster is not in the map still gets a row, pointing at
PLACEHOLDER_URL, so the day is complete and you can see what is missing
rather than wondering why a match vanished.

WHAT MAKES IT SAFE FOR TIVIMATE
===============================
  * #EXTM3U first, one #EXTINF per entry, URL on the very next line.
  * Attribute values are quoted and any quote inside them is stripped,
    because a stray " ends the attribute and swallows the rest of the line.
  * The display name after the comma carries no comma of its own — a comma
    there is what splits a name in half in some players.
  * Newlines and tabs are flattened out of every name.
  * Written UTF-8 without a BOM. A BOM before #EXTM3U makes a player
    reject the whole file as not a playlist.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

import requests

from epg_lib import fetch, log, warn
from today_matches_epg import (
    ARABIC_DAY, CHANNEL_AR, LOGO, MATCH_ON_AIR, SOURCE, UTC, VIEWER, collect,
)

OUTPUT = "ai_sports_dashboard.m3u"
GROUP = "AI Sports Dashboard"
STREAM_MAP = "stream_map.json"

# Every entry must have a URL or a player drops the row. This one is
# deliberately unplayable rather than pointing anywhere real.
PLACEHOLDER_URL = "http://0.0.0.0/no-stream-configured"

LIVE_MARK = "🔴"


def clean(value: str) -> str:
    """Flatten anything that would break the line this sits on."""
    return re.sub(r"\s+", " ", (value or "").replace('"', "")).strip()


def attribute(value: str) -> str:
    """A value safe to put inside double quotes in an #EXTINF line."""
    return clean(value).replace(",", " ")


def display(value: str) -> str:
    """The name after the comma, which may not contain a comma itself."""
    return clean(value).replace(",", " ·")


def stream_map() -> dict[str, str]:
    """Your own broadcaster -> URL mapping, if you have written one."""
    if not os.path.exists(STREAM_MAP):
        warn(f"{STREAM_MAP} not found — every row will carry the "
             f"placeholder URL. See the note at the top of this file.")
        return {}
    try:
        with open(STREAM_MAP, encoding="utf-8") as handle:
            mapping = json.load(handle)
    except Exception as exc:
        warn(f"{STREAM_MAP} could not be read ({exc}) — placeholders only")
        return {}
    return {clean(k).casefold(): v for k, v in mapping.items() if v}


def url_for(event: dict, mapping: dict[str, str]) -> tuple[str, bool]:
    """The first broadcaster of this match that you have a URL for."""
    for channel in event["channels"]:
        found = mapping.get(clean(channel).casefold())
        if found:
            return found, True
    return PLACEHOLDER_URL, False


def entry(event: dict, mapping: dict[str, str],
          now: datetime) -> tuple[list[str], bool]:
    """One #EXTINF and its URL, as the two lines a player expects."""
    local = event["start"].astimezone(VIEWER)
    clock = local.strftime("%H:%M")

    # The rows run in true order, but a list that crosses midnight shows
    # 18:00 then 07:00 and reads as though it were shuffled. Anything not
    # on today's date says which day it is, so the order explains itself.
    if local.date() != now.astimezone(VIEWER).date():
        clock = f"{ARABIC_DAY[local.weekday()]} {clock}"
    live = event["start"] <= now < event["start"] + MATCH_ON_AIR
    channels = " · ".join(event["channels"][:2])

    name = f"{clock} · {event['title']}"
    if channels:
        name += f" · {channels}"
    if live:
        name = f"{LIVE_MARK} {name}"

    url, mapped = url_for(event, mapping)
    return [
        f'#EXTINF:-1 tvg-id="" tvg-name="{attribute(event["title"])}" '
        f'tvg-logo="{LOGO}" group-title="{attribute(GROUP)}",'
        f"{display(name)}",
        url,
    ], mapped


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
        warn(f"livefootballtv is unreachable ({exc}) — the published "
             f"playlist stays exactly as it is")
        return 1

    events = collect(html, now)
    mapping = stream_map()

    lines = ["#EXTM3U"]
    mapped = 0
    for event in sorted(events, key=lambda e: e["start"]):
        rows, was_mapped = entry(event, mapping, now)
        lines.extend(rows)
        mapped += 1 if was_mapped else 0

    # Written without a BOM: a byte-order mark in front of #EXTM3U makes a
    # player refuse the file outright.
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as out:
        out.write("\n".join(lines) + "\n")

    log(f"{OUTPUT}: {len(events)} match(es) under “{GROUP}”, "
        f"{mapped} with a stream of yours, {len(events) - mapped} on the "
        f"placeholder")
    log(f"the guide {CHANNEL_AR} still publishes alongside this, unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(build())
