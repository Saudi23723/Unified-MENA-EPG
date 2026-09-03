#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every row jfa.jo publishes, accepted and refused, with the reason.

The reader asks why الوحدات and الفيصلي are not on the board. There are
only three possible answers and this tells them apart instead of
guessing: the federation is not listing them, or it is listing them and
something here refuses them, or they are outside the three days the board
covers.

So this prints the WHOLE upcoming table — every row, whether it was kept
or dropped and why — rather than the summary the build already logs.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402

import jordan_football as jfa                                  # noqa: E402
from epg_lib import fetch, new_session, norm                   # noqa: E402


def main() -> int:
    page = fetch(new_session(), jfa.SOURCE).text
    soup = BeautifulSoup(page, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    print(f"jfa.jo — {len(page)} bytes\n")
    print("=== EVERY ROW, AND WHAT HAPPENS TO IT ===")
    waiting = None
    rows = kept = 0
    for row in soup.find_all("tr"):
        if row.select_one("span.haly1"):
            start = jfa.a_day_and_a_clock(row)
            competition = jfa.competition_of(row)
            waiting = (competition, start) if start is not None else None
            print(f"\n  header: {competition}  |  "
                  f"{start.astimezone(jfa.AMMAN):%Y-%m-%d %H:%M} Amman"
                  if start else f"\n  header: {competition}  |  NO TIME")
            continue

        home = row.select_one("span.team1")
        away = row.select_one("span.team2")
        if home is None or away is None:
            continue
        rows += 1
        header, waiting = waiting, None
        verdict = row.select_one("span.rrresult")
        mark = norm(verdict.get_text(" ", strip=True)) if verdict else "—"
        home_name = norm(home.get_text(" ", strip=True))
        away_name = norm(away.get_text(" ", strip=True))

        why = ""
        if verdict is None or not jfa.NOT_PLAYED_YET.match(mark):
            why = f"already played ({mark})"
        elif header is None:
            why = "no header of its own"
        elif not jfa.wanted_here(header[0]):
            why = f"not professional or national ({header[0]})"
        elif not jfa.the_clubs_belong(header[0], home_name, away_name):
            why = "these clubs do not play that competition"
        else:
            kept += 1
        print(f"    {'KEPT ' if not why else 'drop '} "
              f"{home_name} - {away_name}"
              + (f"   <- {why}" if why else
                 f"   -> {jfa.carried_by(header[0]) or 'no channel'}"))

    print(f"\n{rows} club row(s), {kept} kept")

    print("\n=== AND WHAT THE BOARD'S THREE-DAY WINDOW WOULD TAKE ===")
    now = datetime.now(timezone.utc)
    inside = jfa.fetch_events(new_session(), now - timedelta(days=1),
                              now + timedelta(days=3))
    for event in inside:
        print(f"    {event['start'].astimezone(jfa.AMMAN):%Y-%m-%d %H:%M} "
              f"| {event['title']} | {event['competition']}")

    print("\n=== IS EITHER CLUB ANYWHERE ON THE PAGE AT ALL ===")
    whole = norm(soup.get_text(" ", strip=True))
    for club in ("الوحدات", "الفيصلي", "الرمثا", "الحسين", "الجزيرة",
                 "العربي", "شباب الأردن", "السلط"):
        print(f"    {club}: {whole.count(club)} mention(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
