#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: where did Al Ahly - Smouha and the Jordanian league go?

Four fixtures were shown missing from the board: three in Jordan's Premier
League and Al Ahly v Smouha in Egypt's. None of them are in this
repository's own guides — checked first, because that was free. So either
the two listings pages never mention them, or they mention them without a
broadcaster and this guide drops anything it cannot tell you where to
watch.

Those need opposite fixes, so the difference is worth one measurement:
  * never mentioned  -> a source that covers Arab domestic leagues
  * mentioned, no channel -> show it anyway, without a channel

It also counts how many fixtures a day are dropped for that reason alone,
and asks four Arabic sports pages whether they carry the same fixtures.

Delete once read.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime, timezone

from bs4 import BeautifulSoup

import live_football_on_tv as second
import today_matches_epg as today
from epg_lib import fetch, new_session, norm

WANTED = ("Smouha", "سموحة", "Ahly", "الأهلي", "Ramtha", "الرمثا",
          "Wehdat", "الوحدات", "Buqaa", "البقعة", "Faisaly", "الفيصلي")

ARABIC_PAGES = ("https://www.kooora.com/", "https://www.filgoal.com/",
                "https://www.yallakora.com/", "https://elgoal.net/")


def mentions(label: str, html: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = norm(soup.get_text(" ", strip=True))
    found = [w for w in WANTED if w.lower() in text.lower()]
    print(f"  {label:34s} {len(text):8d} chars  names: {found or 'none'}")


def main() -> int:
    now = datetime.now(timezone.utc)
    session = new_session()
    floor, ceiling = today.window_floor(now), today.window_ceiling(now)

    print("=== do the two pages mention them at all? ===")
    primary_html = fetch(session, today.SOURCE).text
    mentions("livefootballtv", primary_html)
    try:
        mentions("live-footballontv", fetch(session, second.SOURCE).text)
    except Exception as exc:
        print(f"  live-footballontv unreachable: {exc}")

    print("\n=== how many rows does the first page drop for having no channel? ===")
    soup = BeautifulSoup(primary_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    no_channel: Counter = Counter()
    named = 0
    for row in soup.find_all("tr"):
        if not today.is_match(row):
            continue
        start = today.kickoff_of(row)
        if start is None or not (floor <= start < ceiling):
            continue
        if today.sources_of(row):
            named += 1
            continue
        home = today.team_in(row.find("td", class_="local"))
        away = today.team_in(row.find("td", class_="visitante"))
        day = start.astimezone(today.VIEWER).date()
        no_channel[day] += 1
        if re.search("|".join(WANTED), f"{home} {away}", re.I):
            print(f"  *** {start:%m-%d %H:%M}Z  {home} - {away}  "
                  f"({today.competition_of(row)})  NO CHANNEL")
    print(f"  {named} row(s) name a channel; dropped for naming none, by day: "
          f"{dict(no_channel)}")

    print("\n=== do Arabic pages carry them, in plain HTML? ===")
    for url in ARABIC_PAGES:
        try:
            mentions(url, fetch(session, url).text)
        except Exception as exc:
            print(f"  {url:34s} unreachable — {type(exc).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
