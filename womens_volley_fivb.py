#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAJOR INTERNATIONAL WOMEN'S (INDOOR) VOLLEYBALL, from the sport's own
governing body — asked for by name: "Add women's international volleyball
to channel 2", with the listings of Poland, Sweden, Turkey, Germany,
Italy, France, Spain, Russia and Serbia looked at first.

WHAT WAS MEASURED BEFORE THIS FILE WAS WRITTEN (this runner, plain HTTP):

    tvmatchen.nu (Sweden)      404 on every volleyball path
    sport.tvp.pl (Poland)      200, but the grid is drawn in the browser
    sportowefakty (Poland)     404
    sport1.de / tvsport.de     404 / no host
    sportface.it, sportitalia  404
    programme-television.org   200, three volleyball words in the page
    sports.ru, matchtv.ru      the grid is drawn in the browser / 403
    mozzartsport, telesport.rs 404
    futbolenlatv.es (Spain)    ANSWERS with rows AND broadcasters —
                               already read, see spanish_sport_grid.py
    Spor Ekranı (Turkey)       answers, and has a channel of its own now
                               (turkish_ppv_epg.py); nothing of it here
    FIVB VIS                   ANSWERS, plain XML, no key, no browser

So the fixtures come from VIS, the same service the federation's own
site reads and the same door beach_volley_fivb.py already uses:

    GetVolleyTournamentList   every tournament, its dates and its GENDER
    GetVolleyMatchList        every match of ONE tournament, filtered
                              with <Filter NoTournament="..."/>

WOMEN ONLY: VIS stamps Gender="1" on the women's tournament, so the half
of the sport shown is the feed's own word for it, never a guess.

THE INSTANT IS UTC. VIS gives DateTimeUtc on the indoor match list — a
real UTC stamp, not a printed local clock — so no zone is assumed and no
daylight-saving change can move an hour. A match without it is skipped.

THE CHANNEL, WHERE IT IS KNOWN AND ONLY THERE. Volleyball World streams
the competitions it runs worldwide on VBTV (volleyballworld.tv), and CEV
streams EuroVolley on EuroVolley TV; those two are named. Nothing else is
guessed: a continental cup nobody announced reaches the board naming no
channel, and the board's own rule prints PPV beside a row with none.
Where a listings grid has the same fixture WITH a broadcaster, the
board's one-row-per-broadcast fold keeps that one.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from epg_lib import log, norm, warn

VIS = "https://www.fivb.org/vis2009/XmlRequest.asmx?Request="

# Major and international. The world and continental championships, the
# Nations League, the Olympic tournament and its qualifiers, the Asian
# and Pan American Games, the continental cups the confederations run.
A_MAJOR = re.compile(
    r"world championship|world cup|world grand|grand champions"
    r"|nations league|vnl"
    r"|olympic|qualif"
    r"|european championship|eurovolley"
    r"|continental|asian games|pan.?american|panamerican"
    r"|african nations|asian championship|south american"
    r"|final six|final four|challenger cup|nations cup"
    r"|games\b",
    re.I)

# Not what was asked for: the age groups, the club competitions, the
# federation's own test entries.
A_YOUTH = re.compile(r"\bu1[0-9]\b|\bu2[0-3]\b|under.?\d\d|youth|junior"
                     r"|girls|boys|school|university", re.I)
A_CLUB = re.compile(r"\bclub\b|champions league|cev cup|challenge cup", re.I)
A_TEST = re.compile(r"\btest\b|\bdemo\b", re.I)

# The two carriers that are published facts rather than a guess.
VBTV = re.compile(r"fivb|nations league|vnl|world championship|world cup"
                  r"|club world|challenger cup|olympic", re.I)
EUROVOLLEY = re.compile(r"eurovolley|cev\b", re.I)


def _ask(session, request: str) -> str:
    got = session.get(VIS + quote(request), timeout=40)
    got.raise_for_status()
    return got.text


def _attributes(xml: str, tag: str) -> list[dict]:
    return [dict(re.findall(r'(\w+)="([^"]*)"', piece))
            for piece in re.findall(rf"<{tag}\b([^>]*)/?>", xml)]


def _is_major_women(row: dict) -> bool:
    name = row.get("Name") or ""
    if row.get("Gender") != "1":
        return False
    if A_YOUTH.search(name) or A_CLUB.search(name) or A_TEST.search(name):
        return False
    return bool(A_MAJOR.search(name))


def _channels_for(name: str) -> list[str]:
    if EUROVOLLEY.search(name):
        return ["EuroVolley TV"]
    if VBTV.search(name):
        return ["VBTV"]
    return []


def tournaments(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every women's major whose dates touch the board's window."""
    xml = _ask(session, '<Request Type="GetVolleyTournamentList" '
                        'Fields="No Name Gender StartDate EndDate"/>')
    first, last = floor.date().isoformat(), ceiling.date().isoformat()
    out = []
    for row in _attributes(xml, "VolleyballTournament"):
        start, end = row.get("StartDate") or "", row.get("EndDate") or ""
        if not start:
            continue
        if (end or start) < first or start > last:
            continue
        if _is_major_women(row):
            out.append(row)
    return out


def events(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every women's match of a major indoor tournament inside the window."""
    try:
        majors = tournaments(session, floor, ceiling)
    except Exception as exc:                                   # noqa: BLE001
        warn(f"fivb indoor tournament list unreachable ({exc})")
        return []

    out: list[dict] = []
    for major in majors:
        name = norm(major.get("Name") or "")
        number = major.get("No")
        if not number:
            continue
        try:
            xml = _ask(session,
                       '<Request Type="GetVolleyMatchList" '
                       'Fields="No NoTournament DateTimeUtc TeamAName '
                       'TeamBName">'
                       f'<Filter NoTournament="{number}"/></Request>')
        except Exception as exc:                               # noqa: BLE001
            warn(f"fivb indoor matches unreachable for {name} ({exc})")
            continue
        for match in _attributes(xml, "VolleyballMatch"):
            stamp = match.get("DateTimeUtc") or ""
            home = norm(match.get("TeamAName") or "")
            away = norm(match.get("TeamBName") or "")
            if not stamp or not home or not away:
                continue
            try:
                start = datetime.strptime(
                    stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if start < floor or start >= ceiling:
                continue
            out.append({
                "start": start,
                "title": f"{home} vs {away}",
                "competition": name,
                "sport": "Volleyball",
                "channels": _channels_for(name),
                "source": "fivb-indoor",
            })

    unique, seen = [], set()
    for row in out:
        key = (row["start"], row["title"].casefold())
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    log(f"  fivb indoor: {len(unique)} women's international volleyball "
        f"match(es) across {len(majors)} major(s)")
    return unique
