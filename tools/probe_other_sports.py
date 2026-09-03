#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Four more for the American half, after the first four were all shut.

Written down so none of them is tried twice:

  livesportsontv /league/nfl and /league/nba  200, 913 and 940 KB, and
      NOTHING that holds a channel sits under anything holding a clock.
      ABC, ESPN, NBC and Peacock are in the page and not attached to a
      game: the schedule is assembled in the browser.
  tsn.ca            200, 144 KB, names only the word "TSN".
  sportsnet.ca      200, an 18 KB shell.
  cbc.ca/sports/live  404.
  nba.com/schedule  ships __NEXT_DATA__ and shows no channel at all.

All of them build the schedule in a browser, so a runner sees furniture.

These four are chosen because a schedule PAGE with a network COLUMN is a
different thing from a schedule app: ESPN and CBS have printed the
broadcaster beside each game for twenty years, and the league's own site
has to say where to watch. Whether any still renders it server-side is
the question, and it is asked rather than assumed.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402
from epg_lib import new_session, norm                          # noqa: E402

PAGES = [
    ("ESPN NFL schedule",  "https://www.espn.com/nfl/schedule"),
    ("ESPN NBA schedule",  "https://www.espn.com/nba/schedule"),
    ("NFL.com schedules",  "https://www.nfl.com/schedules/"),
    ("CBS Sports NFL",     "https://www.cbssports.com/nfl/schedule/"),
]

CHANNELS = re.compile(
    r"\bABC\b|\bESPN\d?\b|ESPN\+|\bNBC\b|Peacock|\bFOX\b|\bFS1\b|\bCBS\b"
    r"|Paramount|\bTSN\d?\b|Sportsnet|Prime Video|Amazon|NFL Network"
    r"|\bNBA TV\b|\bTNT\b|\bDAZN\b|Netflix", re.I)
A_CLOCK = re.compile(r"\b\d{1,2}:\d{2}\s?(?:[AP]M)?\b", re.I)


def look(name: str, url: str, session) -> None:
    print(f"\n=== {name} — {url}")
    try:
        reply = session.get(url, timeout=30)
    except Exception as exc:
        print(f"  SHUT — {type(exc).__name__}: {str(exc)[:110]}")
        return
    print(f"  {reply.status_code} — {len(reply.text)} bytes")
    if reply.status_code != 200:
        return

    soup = BeautifulSoup(reply.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Climb from a channel until an ancestor also holds a clock, and stop
    # there. Found rather than assumed, and the stop is what keeps it from
    # climbing to the whole page.
    printed = 0
    for node in soup.find_all(string=CHANNELS):
        holder = node.parent
        for _ in range(8):
            if holder is None:
                break
            text = norm(holder.get_text(" | ", strip=True))
            if A_CLOCK.search(text) and len(text) < 400:
                print(f"    <{holder.name} class="
                      f"{' '.join(holder.get('class') or []) or '-'}> "
                      f"{text[:230]}")
                printed += 1
                break
            holder = holder.parent
        if printed >= 4:
            break
    if not printed:
        seen = sorted({hit.upper() for hit in CHANNELS.findall(
            norm(soup.get_text(" ", strip=True)))})
        print("    no game pairs a channel with a clock in the markup"
              f" | channels loose in the text: {seen[:10] or '— none —'}")


def main() -> int:
    session = new_session()
    for name, url in PAGES:
        look(name, url, session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
