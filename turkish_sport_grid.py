#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spor Ekranı's own grid, read for the two sports no other source carries.

Asked for on channel 2: major WOMEN'S international volleyball, and the
MEN'S handball World Cup with the major internationals beside it.

WHY THIS SOURCE AND NOT ANOTHER, measured on a runner before a line here
was written (probes/probe_volleyball_and_handball.py and the three that
follow it):

    wheresthematch      no volleyball page, no handball page — both 404,
                        against a basketball control answering 200
    CEV, EuroVolley,    calendars rendered in JavaScript; nought
    Volleyball World,   machine-readable instants between all four
    EHF
    IHF                 sixteen instants, and no broadcaster beside them
    S Sport             a certificate served for the wrong hostname;
                        its Plus site says "voleybol" nought times
    TRT / tabii         says the sports 108 times, and carries no <time>,
                        no table row and no ld+json
    beIN, Alkass        26 rows across both sports, every one a CLUB
    (already here)      league — the Daikin StarLigue, the Championnat
                        de France, Qatar's beach team

Spor Ekranı is the one that answers. Its schedule is not in its ld+json —
that holds 78 broadcasts where the page holds hundreds — but in a div
called event-list, one link per broadcast, and the link carries every
field this board needs:

    img.event-list__sport-icon  alt   the sport
    span.event-list__time             the clock
    p.event-list__name                the two sides
    p.event-list__league              the competition
    img inside .event-list__channel   THE BROADCASTER

The channel is in the ROW. That was the question that decided this: a
channel list down the side of a page is a filter menu, which is what
boxingscene's turned out to be the last time this project went looking
for broadcasters, and a channel read from the page rather than from the
row is the guess spor_ekrani.py already refuses by name.

THE CLOCK IS PRINTED, AND THE ZONE IS ISTANBUL'S. A printed clock with no
offset is what once put every match on this project an hour out, so the
zone is not assumed quietly: the same page's ld+json stamps its own
broadcasts +03:00, which is Europe/Istanbul, and that is read from the tz
database rather than written down as a number so the hour stays right
across a daylight-saving change. A gate holds it.

ONLY TODAY. The site's day links — /home/day/2026-09-06 and the rest —
all return the identical eighty rows: the date is applied in the browser,
so the server has only ever one day to give. This reads that day. The
board's other two days are filled by the sources that can reach them.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from epg_lib import fetch, log, norm, warn

SOURCE = "https://www.sporekrani.com/"

# The page prints Turkey's clock. Proven, not assumed: its own ld+json
# stamps every broadcast +03:00.
ISTANBUL = ZoneInfo("Europe/Istanbul")

# The sport is the icon's own word, never a guess from the title.
#
# EVERY SPORT THE GRID CARRIES, asked for outright: "download all their
# listings for every sport and every competition it's fine just don't
# duplicate". The Turkish word on the icon is mapped to the board's own
# name for the sport, and each channel's own order decides what it shows.
#
# FOOTBALL AND BASKETBALL WERE LEFT OUT OF THIS MAP, and that is what
# was silently costing TRT Spor, S Sport and HT Spor every row they had.
# Asked for them by name; measured first (probes/probe_turkish_channels
# .py, on a runner, 80 rows):
#
#     TRT Spor         13 rows — 13 studio programmes, no match
#     HT Spor          11 rows —  3 basketball, 8 programmes
#     S Sport Plus      4 rows —  2 basketball, 2 football
#     S Sport           2 rows —  2 basketball
#     TRT Spor Yildiz   1 row  —  1 basketball
#
# Nothing here has ever filtered on a channel name; every broadcaster
# the grid prints is carried. It was the SPORT that refused them, and
# with these two mapped their ten real matches reach a board. The
# programmes stay refused, by A_PROGRAMME below and by their own icon:
# "events / matches" is what was asked for, and a studio show is
# neither.
#
# WHICH BOARD SEES THEM IS STILL EACH CHANNEL'S OWN DECISION. Channel 2
# refuses any sport outside its IN_ORDER by name, and football and
# basketball are not in it, so nothing here can put a football match on
# the sports guide — they belong to the first channel and to the
# NBA/NFL one. The Turkish channel, whose whole subject is what is on
# Turkish screens, takes them.
A_SPORT = {
    "futbol": "Football",
    "basketbol": "Basketball",
    "voleybol": "Volleyball",
    "hentbol": "Handball",
    "plaj voleybolu": "Beach Volleyball",
    "futsal": "Futsal",
    "tenis": "Tennis",
    "snooker": "Snooker",
    "bisiklet": "Cycling",
    "padel": "Padel",
    "golf": "Golf",
    "ragbi": "Rugby",
    "rugby": "Rugby",
    "atletizm": "Athletics",
    "yüzme": "Swimming",
    "yuzme": "Swimming",
    "triatlon": "Triathlon",
    "boks": "Boxing",
    "mma": "MMA",
    "ufc": "MMA",
    "dart": "Darts",
    "darts": "Darts",
    "formula 1": "F1",
    "motogp": "MotoGP",
    "motor sporları": "MotoGP",
    "ralli": "WRC",
    "olimpiyat": "Olympics",
    # The wrestling, asked for by name for the second channel. Turkish
    # names it "güreş", with and without its dotless spelling.
    "güreş": "Wrestling",
    "gures": "Wrestling",
    "güres": "Wrestling",
    "wrestling": "Wrestling",
}

# WHOSE COMPETITION. Turkish names the side outright — Kadınlar is the
# women's, Erkekler the men's — and the reader asked for one of each:
# the women's volleyball, the men's handball. A row that names neither
# is not placed in one; it is refused, because a guess about which half
# of a sport a viewer is being shown is the same class of guess as a
# guessed channel.
WOMEN = re.compile(r"kadınlar|kadinlar|women", re.I)
MEN = re.compile(r"erkekler|men\b", re.I)

WANTED = {"Volleyball": WOMEN, "Handball": MEN}

# MAJOR AND INTERNATIONAL, in the words this source uses for them: the
# European and World championships, the Nations League, the World Cup,
# the Olympics, the world qualifiers. Everything else the grid carries
# for these sports is a club league — the Sultanlar and Efeler Ligi at
# home, the Champions League in Europe — and none of it was asked for.
A_MAJOR = re.compile(
    r"avrupa şampiyonas|avrupa sampiyonas"          # European Championship
    r"|dünya şampiyonas|dunya sampiyonas"           # World Championship
    r"|dünya kupas|dunya kupas"                     # World Cup
    r"|milletler ligi"                              # Nations League
    r"|olimpiyat"                                   # Olympics
    r"|elemeler|eleme grubu"                        # qualifiers
    r"|european championship|world championship|world cup"
    r"|nations league|olympic",
    re.I)

# A programme about the sport is not the sport. The grid marks these
# itself — the icon says Programlar and the league says Programi — and
# the board refuses them anyway, but they are dropped here so a
# programme never even reaches it wearing a sport's name.
A_PROGRAMME = re.compile(r"program|stüdyo|studyo|özet|ozet|tekrar", re.I)


def _rows(soup):
    return [a for box in soup.select("div.event-list")
            for a in box.find_all("a")]


def _text(row, css):
    found = row.select_one(css)
    return norm(found.get_text(" ", strip=True)) if found else ""


def collect(html: str, today: datetime | None = None) -> list[dict]:
    """Every row of this grid that is one of the two competitions asked for."""
    soup = BeautifulSoup(html, "html.parser")
    rows = _rows(soup)
    now = (today or datetime.now(timezone.utc)).astimezone(ISTANBUL)

    out: list[dict] = []
    seen = wrong_sport = not_major = wrong_side = no_channel = 0

    for row in rows:
        seen += 1
        icon = row.select_one("img.event-list__sport-icon")
        word = (icon.get("alt") or "").strip().lower() if icon else ""
        sport = A_SPORT.get(word)
        if not sport:
            wrong_sport += 1
            continue

        league = _text(row, "p.event-list__league")
        title = _text(row, "p.event-list__name")
        if A_PROGRAMME.search(f"{league} {title}"):
            not_major += 1
            continue
        # EVERY COMPETITION, not only the majors — "every sport and every
        # competition it's fine just don't duplicate". The major-only and
        # whose-half gates that stood here were written when this source
        # answered for two sports alone; the board's own sport order and
        # its one-row-per-broadcast fold now do the deciding, and the
        # fold is what keeps a competition arriving twice to one row.
        # A_MAJOR and WANTED stay defined for the gate that reads them.

        channels = []
        for img in row.select("div[class*=channel] img"):
            name = norm(img.get("alt") or "")
            if name and name not in channels:
                channels.append(name)
        if not channels:
            # A row with no broadcaster is no use to this board.
            no_channel += 1
            continue

        clock = _text(row, "span.event-list__time")
        stamp = re.match(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$", clock)
        if not stamp:
            continue
        start = now.replace(hour=int(stamp.group(1)),
                            minute=int(stamp.group(2)),
                            second=0, microsecond=0)

        out.append({
            "start": start.astimezone(timezone.utc),
            "title": title or league,
            "competition": league,
            "sport": sport,
            "channels": channels,
            "source": "sporekrani",
        })

    log(f"  sporekrani: {seen} row(s), {wrong_sport} another sport, "
        f"{not_major} not a major or a programme, {wrong_side} the other "
        f"side of the sport, {no_channel} with no broadcaster, "
        f"{len(out)} kept")
    return out


def events(session) -> list[dict]:
    """The grid's own rows for the two competitions, or nothing at all."""
    try:
        got = fetch(session, SOURCE)
        if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
            got.encoding = "utf-8"
        return collect(got.text)
    except Exception as exc:                                   # noqa: BLE001
        warn(f"sporekrani is unreachable ({exc}) — the board keeps what "
             f"the other sources gave it")
        return []
