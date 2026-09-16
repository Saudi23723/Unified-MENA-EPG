#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canal 11 — the Portuguese Football Federation's own channel, live only.

"كمان ضيف Canal 11 و مباريات المباشر تبعها القناة البرتغال". Canal 11 is
the FPF's channel: the national teams and the under-21s, Liga 3 and the
Campeonato de Portugal, Liga Revelação, futsal, beach soccer and the
women's game. None of that is on SPORT TV's live pages and none of it is
on DAZN's rail, so the twelfth channel was carrying none of it.

WHERE IT IS READ FROM, AND WHY THAT PAGE. Two rounds of probing, both on
a runner rather than guessed at:

  canal11.pt            200 but 15KB and not one clock — a shell
  tvepg.eu              403
  programacaotv         200, a FULL EPG — carries the debates and the
                        magazines this channel has been told to exclude
  futebolnatv           200, names Canal 11 46 times, and not one block
                        pairs the name with a time — shaped otherwise
  livesoccertv channel  200, 227KB, seven tr.matchrow, EVERY one
                        carrying a dv epoch and none without

THE ROWS ARE THIS CHANNEL'S, WHICH HAD TO BE PROVEN. Round one found Al
Ain x Al Nassr and Al Hilal x Al Gharafa among seven otherwise Portuguese
fixtures, and an AFC Champions League tie on a Portuguese federation
channel is either true or a selector that reached into a neighbouring
block. So round two asked the page, and all seven rows sit in ONE table,
class 'schedules blueborder', under ONE heading, "Canal 11 Streaming ao
Vivo e Programação de TV". There is no neighbouring block. The page is
asserting all seven, and the reader confirmed it expects the channel to
carry them.

THE INSTANT IS THE EPOCH, NEVER THE PRINTED CLOCK. live_soccer_tv.py
records the trap and this page walks straight into it: printed '8:00',
data-ko '2026-09-15 08:00:00', dv 12:00Z. Four hours apart, because
data-ko is the site's Eastern wall clock and dv is a true epoch. dv is
read and data-ko is not, and instant() is imported from that module
rather than written a second time.

THE CHANNEL IS THE PAGE, NOT A COLUMN. div.mchannels is empty on every
row — correctly, because a channel page does not repeat its own name in
each row — so the name is supplied here. That is safe only because the
rows were proven to be this channel's, above.

AND THE SEPARATOR IS AN x. live_soccer_tv.fixture_of splits on "vs",
which is what the American page writes; this page is Portuguese and
writes "Penafiel Sub23 x Santa Clara Sub23". Reusing that function
unchanged would return nothing on every row, silently. So the split is
this module's own, and it accepts both.

WHAT THIS DOES NOT CROSS. live_soccer_tv carries the limit "used to NAME
channels, never to add fixtures", and that is right for /schedules/ — a
global aggregate where a row is one of thousands. A CHANNEL page is a
different claim: it is one broadcaster's own listing, which is what
update_shahid_sports_epg already reads livesoccertv for. This module is
separate so that limit stays where it belongs.
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

import dazn_pt
from epg_lib import fetch, log, norm, warn
from live_soccer_tv import instant

SOURCE = "https://www.livesoccertv.com/channels/canal-11-portugal/"

# What the board prints beside the row. The page never says it, because
# the page IS the channel — see the note above.
CHANNEL = "Canal 11"

# livesoccertv is a football site and this is a football channel's page.
# Canal 11 also carries futsal and beach soccer, and if those ever appear
# here they arrive as fixtures like any other; they are filed under the
# sport this board can order them by rather than guessed at individually.
SPORT = "Football"

# "Penafiel Sub23 x Santa Clara Sub23" — Portuguese. Also accepts the
# "vs" the same site writes in English, so a change of wording on the
# page does not silently empty this reader.
THE_TWO_SIDES = re.compile(r"\s+(?:x|vs?\.?)\s+", re.I)


def sides_of(row) -> str:
    """The two clubs, from the link that names them."""
    link = row.find("a", title=True)
    title = norm(link.get("title") or "") if link else ""
    if not title:
        return ""
    sides = [norm(side) for side in THE_TWO_SIDES.split(title)]
    if len(sides) == 2 and all(sides):
        return f"{sides[0]} - {sides[1]}"
    return ""


def collect(html: str) -> list[dict]:
    """Every fixture the channel page publishes, as the board's rows."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    rows = soup.find_all("tr", class_="matchrow")
    out: list[dict] = []
    no_instant = 0
    not_a_contest = 0
    for row in rows:
        clock = row.find("span", class_="ts")
        start = instant(clock.get("dv")) if clock else None
        title = sides_of(row)
        if start is None or not title:
            no_instant += 1
            continue
        # THE SAME VOCABULARY THE OTHER TWO PORTUGUESE READERS USE.
        # "إعادة لا ، مجلة لا ، برامج لا" is one rule for this channel, so
        # it is one list — see dazn_pt.NOT_A_LIVE_CONTEST for which words
        # and why each is in it.
        if dazn_pt.NOT_A_LIVE_CONTEST.search(title):
            not_a_contest += 1
            continue
        out.append({
            "start": start,
            "title": title,
            "competition": norm(row.get("data-tournament") or ""),
            "sport": SPORT,
            "channels": [CHANNEL],
        })

    log(f"  canal11: {len(rows)} row(s), {no_instant} with no instant or "
        f"no fixture, {not_a_contest} not a contest, {len(out)} kept")
    return out


def events(session, floor: datetime | None = None,
           ceiling: datetime | None = None) -> list[dict]:
    """Canal 11's fixtures, or nothing at all — never an exception.

    A source that cannot be read is one source short, not a channel off
    the air: the board keeps whatever SPORT TV and DAZN gave it, exactly
    as it does when tapology refuses.
    """
    try:
        got = fetch(session, SOURCE)
        rows = collect(got.text)
    except Exception as exc:                              # noqa: BLE001
        warn(f"canal11 is unreadable ({exc}) — the board keeps what the "
             f"other Portuguese sources gave it")
        return []

    if floor and ceiling:
        inside = [row for row in rows if floor <= row["start"] < ceiling]
        if len(inside) != len(rows):
            log(f"  canal11: {len(rows) - len(inside)} row(s) outside the "
                f"window, {len(inside)} inside")
        rows = inside
    return rows
