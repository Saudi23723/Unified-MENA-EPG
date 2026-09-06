#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESPN's own scoreboard, as the fights board's forward calendar.

Asked for in the reader's own words — "check new reliable sources similar
to tapology or other websites !!! FOR FUTURE LIVE ONLY EVENTS" — and what
ESPN has that no other source on this board does is the fights' own
forward clock: tapology carries the cards of the coming fortnight and
its reader can refuse on any given pass, wheresthematch's boxing page
carries only what a British channel picked up, and neither carries the
UFC's own midweek card, Dana White's Contender Series, week by week
through the season. ESPN's scoreboard for the league carries every one
of them, months ahead, with the two things a board row needs printed
beside each: the exact UTC instant and the broadcaster's own name.

THE JSON IS OPEN. No key, no wall, no reader in front of it — the same
shape of source as TSN's and Sportsnet's own feeds, a broadcaster's own
grid read straight from its own API. Two leagues are read, both under
mma: ufc and pfl. Bellator was measured and left out of the wiring
below — its scoreboard answers but carries its last card from 2024, a
page that is alive only as an archive.

THE BROADCASTER IS THE COMPETITION'S OWN BROADCAST LIST. Every card
prints one:

    "broadcasts": [{"market": "national", "names": ["Paramount+"]}]

Nothing here claims a channel the league did not name itself, and a
card whose competitions[0] carries no broadcast list at all is left
alone — an event with no published broadcaster is not shown, the same
rule every row on this board obeys.

THE CARD IS FUTURE, OR IT IS NOT A ROW. Every event prints its own
status, and the fights this board was asked for are the LIVE ones —
"FOR FUTURE LIVE ONLY EVENTS", the reader's own capitals. A card whose
status has moved past "pre" — in, post, whatever the league calls it —
is a fight that has already been fought or is being fought under a
clock this board does not re-report; it is refused, and only
STATUS_SCHEDULED cards reach the board.

A TBA CLOCK IS NOT A CLOCK. The same competitions[0] that carries the
broadcast carries "timeValid": false on a card whose instant is not
published yet, and the league's own word for it is honest: a card
without a time cannot be placed, so it is left rather than put an hour
wrong. The same rule tapology's Eastern-word guard obeys, in ESPN's
own spelling.

THE NAME IS THE CARD'S OWN, in the casing the promotion itself uses —
"UFC 331: Van vs. Pantoja 2", "Dana White's Contender Series: Season
10, Week 7" — exactly as the board's other numbered cards spell
themselves. Nothing is renamed and no venue is appended: a numbered
card is a name, not a sentence to be decorated.

AND THE IDENTITY IS THE CARD'S OWN FAMILY. A UFC Fight Night and its
prelims are one broadcast in two parts, and the board's fold reads
that already: _the_same_ufc_card folds two rows that share "UFC <the
card's number or Fight Night>" and the same part of the night. Where
another source has the same card at the same minute, ESPN's row folds
into it under that rule — and where ESPN is the only source that has
the card at all, its row stands alone, at its own minute, with its own
broadcaster.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

# The two leagues this board carries fights from, both under ESPN's
# mma sport. Read straight from the scoreboard endpoint with a dates
# window, the same way the reader of any other feed here reads its own.
HOST = "https://site.web.api.espn.com/apis/site/v2/sports/mma"
LEAGUES = ("ufc", "pfl")

# The window asked for in days. The board's own window is four days
# now ("make schadule every 4 days"), and this calendar is read with a
# handful of days of slack on each side so a card that starts inside
# the board's window but was published under an earlier day's run is
# still found: ESPN's scoreboard carries the present week by default
# and honours a dates range, and the range is the belt-and-braces.
WINDOW_DAYS = 16

# How the league's own broadcaster names are spelled the way a board
# spells them. The names left unmapped keep their own casing —
# Paramount+ and ESPN+ need no help — and "PPV" is already the honest
# word the reader asked for twice over ("if no broadcast channels write
# PPV or ON DEMAND").
AS_PRINTED = {
    "ufc fight pass": "UFC Fight Pass",
    "espn+": "ESPN+",
    "espn2": "ESPN2",
    "espnews": "ESPNEWS",
    "paramount+": "Paramount+",
    "paramount network": "Paramount Network",
    "spike tv": "Spike TV",
    "spike": "Spike TV",
}


def _a_date_window(today: datetime) -> tuple[datetime, datetime]:
    """The scoreboard's window: enough slack to never miss a card."""
    from datetime import date
    the_day = today.date()
    first = datetime.combine(the_day - timedelta(days=WINDOW_DAYS),
                             datetime.min.time(), timezone.utc)
    last = datetime.combine(the_day + timedelta(days=WINDOW_DAYS),
                            datetime.min.time(), timezone.utc)
    return first, last


def collect(payload: str) -> list[dict]:
    """Every future card on the scoreboard that names a clock and a home."""
    out: list[dict] = []
    try:
        page = json.loads(payload)
    except ValueError as exc:
        warn(f"espn printed a page this reader cannot read ({exc}) — "
             f"no card from it this pass")
        return out
    for event in page.get("events", []):
        name = norm(event.get("name") or "")
        if not name:
            continue
        when = (event.get("date") or "").strip()
        if not when:
            continue

        # A TBA clock is not a clock. The league's own flag, read where
        # the broadcast itself is read, and a card without a placeable
        # instant is left rather than put an hour wrong.
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        one = competitions[0]
        if one.get("timeValid") is False:
            continue
        status = ((event.get("status") or {}).get("type") or {})
        if status.get("state") != "pre":
            # THE CARD IS FUTURE, OR IT IS NOT A ROW. The league's own
            # word for a card yet to be fought is "pre"; anything else
            # has been fought or is being fought, and neither is the
            # live-only future this board was asked for.
            continue

        try:
            start = datetime.strptime(when, "%Y-%m-%dT%H:%MZ").replace(
                tzinfo=timezone.utc)
        except ValueError:
            warn(f"espn printed a clock this reader cannot read "
                 f"('{when}') — the card is left alone")
            continue

        # THE BROADCASTER IS THE COMPETITION'S OWN BROADCAST LIST.
        names: list[str] = []
        for cast in one.get("broadcasts") or []:
            for said in cast.get("names") or []:
                said = norm(said)
                if not said:
                    continue
                channel = AS_PRINTED.get(said.casefold(), said)
                if channel not in names:
                    names.append(channel)
        if not names:
            continue

        out.append({
            "start": start,
            "title": name,
            "sport": "MMA",
            "channels": names,
        })
        log(f"  espn: {name} on {' · '.join(names)}, {start:%d.%m %H:%M} UTC")
    if not out:
        log("  espn: no future card on the page this pass")
    return out


def events(session, floor=None, ceiling=None) -> list[dict]:
    """ESPN's future cards, or none if the feed is having a bad day."""
    from datetime import date as _date

    out: list[dict] = []
    first, last = _a_date_window(
        datetime.now(timezone.utc))
    window = f"{first:%Y%m%d}-{last:%Y%m%d}"
    for league in LEAGUES:
        url = f"{HOST}/{league}/scoreboard?dates={window}"
        try:
            payload = fetch(session, url).text
        except Exception as exc:                                  # noqa: BLE001
            warn(f"espn's {league} scoreboard is unreachable ({exc}) — "
                 f"the board keeps what the other sources gave it")
            continue
        for event in collect(payload):
            event["source"] = "espn"
            out.append(event)
    if floor is not None:
        out = [event for event in out if floor <= event["start"] < ceiling]
    return out
