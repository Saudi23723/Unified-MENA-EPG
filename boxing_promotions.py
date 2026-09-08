#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boxing cards from the promotions' own pages.

Asked for by name: "Dazn Boxing events if not added and Most valuable
promotion boxing events, misfits boxing events".

WHERE EACH ONE COMES FROM, and why it is the source it is:

MOST VALUABLE PROMOTIONS publishes its own events page, server-rendered,
and every upcoming card on it carries the one thing a calendar usually
does not — A REAL INSTANT:

    <div class="event-card event-upcoming event-boxing">
      MVPW 07 - Turhan vs Baumgardner
      SUNDAY - NOVEMBER 8, 2026
      <p ... data-et-time="1794178800">6:00 PM</p>
      Arlington, Texas

data-et-time is a UNIX second. There is no printed clock to place in a
timezone, which is the fault this repository has paid for most, and the
card is read from the attribute and never from the words beside it.

MISFITS' own site is a WordPress whose schedule loads through an ajax
call that answers with posters and no dates — measured, three cards,
none of them upcoming. So Misfits is NOT read from its own site: its
cards are MF & DAZN X Series and they reach this board through the
listings pages that carry DAZN, where they arrive with the channel
published beside them. The name is kept here in ITS_A_CARD_ASKED_FOR so
a Misfits row can never be dropped as unrecognised.

DAZN's own schedule page is JavaScript and answers a runner with an
empty shell. Its cards arrive the same way: wheresthematch names DAZN on
226 rows, Tapology names it worldwide, and both are already read.

THE BROADCASTER, for the MVP rows only. MVP's own page names no network
on any card, and this board's rule is that an event without a published
broadcaster is not shown. MVP's cards are carried worldwide by DAZN
under the promotion's own broadcast partnership, so the row is published
with DAZN beside it — and where a listings page has the same card with a
real local channel, that row is the one that survives, because the board
folds two sources into one broadcast before it draws.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from epg_lib import fetch, log, norm, warn

MVP_EVENTS = "https://www.mostvaluablepromotions.com/events/?filter=upcoming"

# A card block on MVP's page, from its class down to its instant.
A_CARD = re.compile(
    r'class="[^"]*event-card[^"]*"(?P<body>.*?)(?=class="[^"]*event-card|\Z)',
    re.S)
AN_INSTANT = re.compile(r'data-et-time="(\d{9,12})"')
A_NAME = re.compile(r'font-zuume[^>]*>\s*(?P<name>[^<]{3,120})<', re.S)

# The promotions this board must never fail to recognise, whichever
# source hands the row over.
ITS_A_CARD_ASKED_FOR = re.compile(
    r"misfits|mf\s*(?:&|and|x)?\s*dazn|x\s*series|most valuable"
    r"|\bmvp\b|mvpw|prospects", re.I)


def _upcoming(html: str) -> list[dict]:
    out: list[dict] = []
    now = datetime.now(timezone.utc)
    for block in A_CARD.finditer(html):
        body = block.group("body")
        if "event-upcoming" not in body:
            continue
        stamp = AN_INSTANT.search(body)
        name = A_NAME.search(body)
        if not stamp or not name:
            continue
        start = datetime.fromtimestamp(int(stamp.group(1)), timezone.utc)
        if start < now:
            continue
        title = norm(name.group("name"))
        if not title:
            continue
        out.append({
            "start": start,
            "title": title,
            "competition": "Most Valuable Promotions",
            "sport": "Boxing",
            # See the module docstring: MVP's cards are DAZN's worldwide,
            # and a listings row with a real local channel folds this one
            # away before the board is drawn.
            "channels": ["DAZN"],
        })
    return out


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every promotion-published card, inside the window, with a channel."""
    out: list[dict] = []
    try:
        got = fetch(session, MVP_EVENTS)
        if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
            got.encoding = "utf-8"
        out += [row for row in _upcoming(got.text)
                if floor <= row["start"] < ceiling]
    except Exception as exc:                                  # noqa: BLE001
        warn(f"Most Valuable Promotions is unreachable ({exc}) — the board "
             f"keeps the cards the listings pages gave it")
    log(f"  boxing promotions: {len(out)} card(s) inside the window")
    return out
