#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: which page ties a channel to a match, and not merely to itself?

The last round found channels on بطولات and no channel inside any match
row, which are both true and mean nothing apart. A page can print "On
Sport Plus" in a sidebar all day without ever saying which match is on it.

So this asks one measurable thing of every candidate: how many blocks in
the HTML contain a clock AND the name of a channel AND two names either
side of a separator. That is a match with a broadcaster attached, and it
is the only thing this guide can use.

Delete once answered.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

CANDIDATES = [
    ("btolat (بطولات)",       "https://www.btolat.com/match-score"),
    ("ukfootballontv",        "https://www.ukfootballontv.co.uk/"),
    ("wheresthematch",        "https://www.wheresthematch.com/live-football-on-tv/"),
    ("live-footballontv",     "https://www.live-footballontv.com/"),
    ("oddalerts tv-guide",    "https://www.oddalerts.com/tv-guide"),
]

TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
CHANNEL = re.compile(
    r"bein|ssc\b|thmanyah|ثمانية|shahid|شاهد|sky\s*sport|tnt\s*sport|espn|"
    r"fox\s*sport|premier\s*sport|bbc|itv|on\s*sport|dazn|amazon|tod\b|"
    r"canal\+|abu\s*dhabi|أبوظبي|الكأس|alkass|viaplay|s\s*sport",
    re.I)


def blocks_with_both(soup) -> list[str]:
    """Innermost elements holding a clock and a channel name together."""
    found = []
    for node in soup.find_all(["tr", "li", "div", "article", "section", "p"]):
        text = norm(node.get_text(" ", strip=True))
        if not (20 < len(text) < 320):
            continue
        if not (TIME.search(text) and CHANNEL.search(text)):
            continue
        # innermost only: no child that also qualifies
        if any(TIME.search(norm(kid.get_text(" ", strip=True)) or "")
               and CHANNEL.search(norm(kid.get_text(" ", strip=True)) or "")
               for kid in node.find_all(True, recursive=False)):
            continue
        found.append(text)
    return found


def look(name: str, url: str) -> None:
    print(f"\n{'─' * 74}\n{name}\n  {url}")
    try:
        html = fetch(new_session(), url).text
    except Exception as exc:
        print(f"  ✗ unreachable: {str(exc)[:110]}")
        return
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    text = norm(soup.get_text(" ", strip=True))
    pairs = blocks_with_both(soup)
    print(f"  {len(html) // 1024:>4} KB | text {len(text):>6} | "
          f"clocks {len(TIME.findall(text)):>4} | "
          f"blocks with clock AND channel: {len(pairs)}")
    for sample in pairs[:6]:
        print(f"      {sample[:130]!r}")
    print(f"  -> {'USABLE — the channel sits with the match' if len(pairs) >= 5 else 'not usable for this guide'}")


def main() -> int:
    for name, url in CANDIDATES:
        look(name, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
