#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Digging for two competitions channel 2 does not have.

Asked for: major WOMEN'S INTERNATIONAL volleyball — the European
Championship and its like — and the MEN'S HANDBALL World Cup and the
major internationals beside it.

What this repository already holds is not it. beIN's own guide carries 26
titled rows across the two sports and every one is a club league: the
Daikin StarLigue from France for the handball, the Championnat de France
and Qatar's beach team for the volleyball. Alkass has one volleyball row
and it is a repeat. So the source has to come from outside, and this asks
every candidate what it actually publishes before a line is written.

Three things decide whether a source can be used, and all three are
printed for each:

    does the page exist at all
    does a row carry a machine-readable instant, not a printed clock
    does a row name a BROADCASTER

A calendar with no channel is no use to this board, and a printed clock
with no offset is what once put every match an hour out.

Measurement only: nothing here writes to any guide.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402
from epg_lib import new_session, fetch, norm                   # noqa: E402
import world_sport_on_tv as world                              # noqa: E402


def line(text=""):
    print(text, flush=True)


def rule(text):
    line()
    line("=" * 74)
    line(text)
    line("=" * 74)


def get(session, url):
    try:
        got = fetch(session, url)
    except Exception as exc:                                   # noqa: BLE001
        return None, str(exc)
    if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
        got.encoding = "utf-8"
    return got, None


# ── one: the listings source already wired ──────────────────────────────
WTM = (
    "/live-volleyball-on-tv/",
    "/live-handball-on-tv/",
    "/live-netball-on-tv/",          # the neighbouring index shape
    "/live-basketball-on-tv/",       # known-good control
)


def the_listings_pages(session):
    rule("ONE — wheresthematch, the source channel 2 already reads")
    for path in WTM:
        got, why = get(session, world.SOURCE + path)
        if got is None:
            line(f"{path:34} unreachable — {why[:70]}")
            continue
        line(f"{path:34} {got.status_code}  {len(got.text):>8,} bytes")
        if got.status_code != 200:
            continue
        rows = world.collect(got.text, "Probe", None, None)
        named = sum(1 for r in rows if r["channels"])
        line(f"     {len(rows)} dated row(s), {named} naming a broadcaster")
        for r in rows[:14]:
            line(f"       {r['start']:%m-%d %H:%M}  {r['title'][:46]:46} "
                 f"{r['competition'][:22]:22} {r['channels']}")
        line()


# ── two: the Turkish grid, which carries what Turkey broadcasts ─────────
SPOREKRANI = "https://www.sporekrani.com/"
TURKISH_SPORT = ("voleybol", "hentbol", "volleyball", "handball")


def the_turkish_grid(session):
    rule("TWO — Spor Ekranı, read already for football's Turkish channels")
    got, why = get(session, SPOREKRANI)
    if got is None:
        line(f"unreachable — {why}")
        return
    line(f"{SPOREKRANI}  {got.status_code}  {len(got.text):,} bytes")

    soup = BeautifulSoup(got.text, "html.parser")
    blocks = soup.find_all("script", type="application/ld+json")
    line(f"ld+json blocks: {len(blocks)}")

    events = []
    for block in blocks:
        try:
            data = json.loads(block.string or "{}")
        except Exception:                                      # noqa: BLE001
            continue
        for item in (data if isinstance(data, list) else [data]):
            if isinstance(item, dict):
                events.append(item)
    line(f"parsed objects: {len(events)}")

    kinds = {}
    for e in events:
        kinds[e.get("@type")] = kinds.get(e.get("@type"), 0) + 1
    line(f"types: {kinds}")

    # what sports does the page name at all?
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]{4,}", got.text.lower())
    for word in TURKISH_SPORT:
        line(f"  the page says {word!r}: {words.count(word)} time(s)")

    hits = 0
    for e in events:
        blob = json.dumps(e, ensure_ascii=False).lower()
        if any(w in blob for w in TURKISH_SPORT):
            hits += 1
            of = e.get("broadcastOfEvent") or {}
            on = e.get("publishedOn") or []
            names = [c.get("name") for c in on if isinstance(c, dict)]
            line(f"  {of.get('startDate','?')}  {of.get('name','?')[:46]:46} "
                 f"{names}")
    line(f"broadcasts naming either sport: {hits}")


# ── three: the confederations' own pages ────────────────────────────────
OFFICIAL = (
    ("CEV — European volleyball", "https://www.cev.eu/calendar/"),
    ("CEV EuroVolley women", "https://eurovolley.cev.eu/en/"),
    ("FIVB volleyball", "https://en.volleyballworld.com/volleyball/competitions/"),
    ("EHF — European handball", "https://www.eurohandball.com/en/"),
    ("IHF — world handball", "https://www.ihf.info/competitions"),
)

A_TIME_ATTR = re.compile(r'datetime="([^"]+)"|data-(?:date|time|start)="([^"]+)"')
AN_ISO = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d")


def the_official_pages(session):
    rule("THREE — the confederations, for the calendar if not the channel")
    for who, url in OFFICIAL:
        got, why = get(session, url)
        if got is None:
            line(f"{who:28} unreachable — {why[:60]}")
            continue
        page = got.text
        line(f"{who:28} {got.status_code}  {len(page):>9,} bytes")
        if got.status_code != 200:
            continue
        stamps = A_TIME_ATTR.findall(page)
        line(f"     time attributes: {len(stamps)}   "
             f"bare ISO instants: {len(AN_ISO.findall(page))}")
        soup = BeautifulSoup(page, "html.parser")
        line(f"     <time> tags: {len(soup.find_all('time'))}   "
             f"rows: {len(soup.find_all('tr'))}")
        broadcasters = ("tnt", "sky", "bein", "dazn", "trt", "s sport",
                        "eurosport", "viaplay", "ard", "zdf")
        said = [b for b in broadcasters if b in page.lower()]
        line(f"     broadcaster words in the page: {said or 'none'}")
        line()


def main() -> int:
    session = new_session()
    now = datetime.now(timezone.utc)
    line(f"now {now:%Y-%m-%d %H:%M} UTC")
    the_listings_pages(session)
    the_turkish_grid(session)
    the_official_pages(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
