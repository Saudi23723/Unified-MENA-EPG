#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: which of these pages actually names the channel?

livefootballtv missed three Championship matches a scores app carried, so
a second source is wanted — and the requirement is narrower than "a
fixtures site". A source with kickoffs and no broadcasters is no use here:
the guide drops such a match by its own rule.

Two things sink a candidate, and both are invisible from the outside:
the page may be built in the browser, so the HTML a fetch returns holds
no matches at all; or it may list matches and simply not say where to
watch them.

So each candidate is asked three questions: does it answer at all, does
its HTML contain clock times, and does it contain the name of a channel
anyone would recognise. Delete once it has answered.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

CANDIDATES = [
    ("livesportsontv — all sports", "https://www.livesportsontv.com/"),
    ("livesportsontv — football",   "https://www.livesportsontv.com/sport/football"),
    ("btolat (بطولات)",             "https://www.btolat.com/match-score"),
    ("365scores where-to-watch",    "https://www.365scores.com/ar/where-to-watch"),
    ("basrawe (بصراوي)",            "https://basrawe.com/matches-today/"),
    ("jdwel (جدول)",                "https://jdwel.com/today/"),
    ("livesoccertv schedule",       "https://www.livesoccertv.com/schedules/"),
]

TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")

# Channels a reader here would recognise. Finding one in the HTML is the
# whole test: it means the page says where to watch, not merely when.
KNOWN = ("bein", "ssc", "thmanyah", "ثمانية", "shahid", "شاهد", "sky",
         "espn", "fox sports", "tnt", "canal+", "dazn", "on sport",
         "abu dhabi", "أبوظبي", "alkass", "الكأس", "starzplay", "tod")


def look(name: str, url: str) -> None:
    print(f"\n{'─' * 72}\n{name}\n  {url}")
    try:
        html = fetch(new_session(), url).text
    except Exception as exc:
        print(f"  ✗ unreachable: {str(exc)[:90]}")
        return

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = norm(soup.get_text(" ", strip=True))

    clocks = TIME.findall(text)
    found = sorted({k for k in KNOWN if k in text.lower()})
    print(f"  fetched {len(html) // 1024:>4} KB | visible text "
          f"{len(text):>6} chars | clocks {len(clocks):>3}")
    print(f"  channels recognised: {', '.join(found) if found else '— none —'}")

    if clocks and found:
        # Show a little of it, so the shape is visible and not just a score.
        window = text.lower().find(found[0])
        print(f"  around the first one: …{text[max(0, window - 120):window + 90]}…")
    verdict = ("USABLE" if clocks and found
               else "times but no channels" if clocks
               else "nothing readable — probably built in the browser")
    print(f"  -> {verdict}")


def main() -> int:
    for name, url in CANDIDATES:
        look(name, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
