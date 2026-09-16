#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WHO PUT Benfica - Sporting CP ON CANAL 11, AND AT 12:05?

The reader: "Benfica vs Sporting هاي غلط، يعني بكرا Benifica vs AC milan
بس، اما الموجودة هاي يمكن recorded".

DAZN WAS ASKED FIRST AND CLEARED ITSELF. Its rail carries no such fixture
at all; every Benfica row on DAZN 1-5 is "AC Milan x Benfica", Liga
Europa, "Do Estádio de San Siro", and every one of them reports
IsLive=False, so dazn_pt refused all of them. The dash that pointed there
was the wrong clue.

THE DASH IS CANAL 11'S. canal11_pt.sides_of ends:

    return f"{sides[0]} - {sides[1]}"

and it is the only place in the build that joins two clubs with " - ".

WHAT IS PUBLISHED, off sporttv_epg.xml on main:

    16/09 23:30  🔴  Benfica - Sporting CP    ✅ انتهى at 01:25
    17/09 12:05  🔴  Benfica - Sporting CP

Two rows, the same fixture, twelve and a half hours apart, on the
Portuguese Football Federation's own channel — which does not carry the
Lisbon derby. The 115 minutes each one runs for is correct, so the
duration is not the fault; the ROWS are.

THREE THINGS CAN PRODUCE THIS AND THEY NEED DIFFERENT FIXES:

1. THE PAGE LISTS IT TWICE, once per leg or once per listing, and the
   reader keeps both. Then the fix is de-duplication.
2. THE PAGE LISTS IT ONCE and the dv epoch is being read twice over, or
   read wrong. live_soccer_tv.instant is shared, so this would be a fault
   in a function three readers depend on — the most expensive outcome and
   the one worth knowing about first.
3. THE ROW IS NOT CANAL 11'S AT ALL. Round two of the Canal 11 change
   established that all seven rows then on the page sat in ONE table
   under ONE heading. If a Benfica row is sitting in a DIFFERENT table
   now, that finding has expired and the selector is reaching.

So this prints, for the live page: every matchrow with its raw printed
clock, its dv attribute, what instant() makes of it, the tournament, and
the table and heading it sits under. Then it runs canal11_pt.events()
itself and prints what the build would actually take today.

Wired to nothing. It prints; a human reads.
"""

import sys
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

sys.path.insert(0, ".")

import canal11_pt
from epg_lib import fetch, new_session
from live_soccer_tv import instant


def heading_above(row):
    """The nearest heading before this row's table -- whose rows are these?"""
    table = row.find_parent("table")

    if table is None:
        return "(no table)", "(no heading)"

    where = " ".join(table.get("class") or []) or "(no class)"

    for tag in table.find_all_previous(["h1", "h2", "h3", "h4"]):
        text = " ".join(tag.get_text(" ", strip=True).split())

        if text:
            return where, text[:80]

    return where, "(no heading)"


def main():
    session = new_session()

    try:
        got = fetch(session, canal11_pt.SOURCE)
    except Exception as exc:
        print(f"PAGE UNREADABLE: {type(exc).__name__}: {exc}")
        return 1

    html = got.text
    print(f"{canal11_pt.SOURCE}\n  {len(html):,}B")

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    rows = soup.find_all("tr", class_="matchrow")
    print(f"  {len(rows)} matchrow(s)\n")

    tables = {}

    for row in rows:
        clock = row.find("span", class_="ts")
        dv = clock.get("dv") if clock else None
        printed = clock.get_text(" ", strip=True) if clock else ""
        when = instant(dv) if dv else None
        link = row.find("a", title=True)
        raw = (link.get("title") or "") if link else ""
        where, head = heading_above(row)
        tables[where] = head

        print(f"  dv={str(dv):<16} printed={printed:<10} "
              f"instant={str(when)[:16]:<16}")
        print(f"      raw title : {raw[:70]}")
        print(f"      sides_of  : {canal11_pt.sides_of(row)[:70]}")
        print(f"      tournament: {(row.get('data-tournament') or '')[:50]}")
        print(f"      table     : {where}  |  under: {head}")

        # Three airings of one derby, none at a plausible Lisbon
        # kick-off. If the page marks a repeat ANYWHERE, it is in this
        # row and not in the link title the reader currently reads.
        if "Benfica" in raw:
            print("      ---- the whole row, verbatim ----")
            print("      " + " ".join(str(row).split())[:1400])
            print("      --------------------------------")

    print(f"\n  tables seen: {len(tables)}")

    for where, head in tables.items():
        print(f"    {where}  ->  {head}")

    # And what the build would actually take, window and all.
    now = datetime.now(timezone.utc)
    kept = canal11_pt.events(session, now - timedelta(days=1),
                             now + timedelta(days=3))
    print(f"\n  canal11_pt.events() -> {len(kept)} row(s)")

    for row in kept:
        print(f"    {str(row['start'])[:16]}  {row['title'][:50]}  "
              f"[{row.get('competition') or '-'}]  dur={row.get('on_air_for')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
