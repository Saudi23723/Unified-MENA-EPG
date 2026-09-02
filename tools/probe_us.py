#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: which American page names a channel with a match?

Settled: of thirty matches on the board, not one names an American
channel. The whole census is Gulf, British, French and Turkish. Fox, NBC,
CBS and USA Network are not hidden behind the "+5" — no source here has
ever seen them.

So the candidates get the measurement every candidate gets: how many
innermost blocks hold a CLOCK and a CHANNEL together, where "channel"
means an American broadcaster by name. A page that lists fixtures without
a broadcaster is still worth knowing about — that rule changed — so the
clock count is reported separately.

Delete once read.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

CLOCK = re.compile(r"\b(\d{1,2}):([0-5]\d)\s*(?:am|pm|AM|PM)?\b")
US = re.compile(
    r"\bfox\b|fs1|fs2|\bnbc\b|peacock|\bcbs\b|paramount\+?|\bespn\b|espn\+|"
    r"\busa network\b|telemundo|univision|tudn|\btnt\b|trutv|\bhbo\b|"
    r"sportsnet|\btsn\b|apple tv|amazon prime|max\b", re.I)

PAGES = (
    "https://worldsoccertalk.com/tv-schedules/",
    "https://www.livesoccertv.com/schedules/",
    "https://www.foxsports.com/soccer/scores",
    "https://www.espn.com/soccer/schedule",
    "https://www.nbcsports.com/soccer/premier-league/schedule",
    "https://www.livesportsontv.com/",
)


def look(session, url: str) -> None:
    try:
        html = fetch(session, url).text
    except Exception as exc:
        print(f"  {url:58s} -> {type(exc).__name__}")
        return
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    innermost = [n for n in soup.find_all(True) if not n.find(True)]
    clocks = [n for n in innermost
              if CLOCK.search(norm(n.get_text(" ", strip=True) or ""))]

    both = []
    for node in soup.find_all(True):
        text = norm(node.get_text(" ", strip=True))
        if not text or len(text) > 300 or not CLOCK.search(text):
            continue
        if US.search(text) and not any(
                CLOCK.search(norm(kid.get_text(" ", strip=True) or ""))
                and US.search(norm(kid.get_text(" ", strip=True) or ""))
                for kid in node.find_all(True)):
            both.append(text[:130])

    text = norm(soup.get_text(" ", strip=True))
    names = sorted({m.group(0) for m in US.finditer(text)})[:10]
    print(f"\n  {url}")
    print(f"    {len(text)} chars | {len(clocks)} block(s) with a clock | "
          f"{len(both)} with a clock AND a US channel")
    print(f"    US names anywhere: {names or 'none'}")
    for line in both[:4]:
        print(f"      {line}")


def main() -> int:
    session = new_session()
    for url in PAGES:
        look(session, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
