#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: can an Arabic page give a kickoff AND a channel?

Settled already: neither listings page mentions Smouha, Al Ramtha, Al
Buqaa or Al Wehdat at all, and not one row was dropped for lacking a
broadcaster. The gap is coverage of Arab domestic leagues, not a filter.

kooora carries those club names in plain HTML. The only question that
matters now is the one asked of every candidate before: how many
innermost blocks hold a CLOCK and a CHANNEL together? Names on a page
and a channel in a row are different things, and a page that lists
matches without saying where to watch them is not usable here.

Delete once read.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

CLOCK = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
CHANNEL = re.compile(
    r"bein|بي ?ان|بين سبورت|ssc|الكأس|alkass|on ?sport|أون ?سبورت|"
    r"ثمانية|thmanyah|ad ?sports|أبوظبي|dubai|دبي|الأردن|شاشة|sky|رياضية",
    re.I)

PAGES = ("https://www.kooora.com/",
         "https://www.kooora.com/?m=1",
         "https://www.yallakora.com/match-center/",
         "https://www.filgoal.com/matches/")


def look(session, url: str) -> None:
    try:
        html = fetch(session, url).text
    except Exception as exc:
        print(f"\n### {url}\n  unreachable — {type(exc).__name__}: {exc}")
        return
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    both = []
    for node in soup.find_all(True):
        if node.find(True):
            continue                      # innermost blocks only
        pass
    # A block is any element whose OWN text holds a clock; then ask whether
    # a channel name sits within the same small container.
    for node in soup.find_all(True):
        text = norm(node.get_text(" ", strip=True))
        if not text or len(text) > 400 or not CLOCK.search(text):
            continue
        if CHANNEL.search(text) and not node.find(
                lambda kid: kid is not node
                and CLOCK.search(norm(kid.get_text(" ", strip=True) or ""))
                and CHANNEL.search(norm(kid.get_text(" ", strip=True) or ""))):
            both.append((node.name, node.get("class"), text[:150]))

    clocks = sum(1 for n in soup.find_all(True)
                 if CLOCK.search(norm(n.get_text(" ", strip=True) or ""))
                 and not n.find(True))
    print(f"\n### {url}")
    print(f"  {len(norm(soup.get_text(' ', strip=True)))} chars of text, "
          f"{clocks} innermost blocks hold a clock, "
          f"{len(both)} hold a clock AND a channel")
    for name, klass, text in both[:6]:
        print(f"    <{name} class={klass}>  {text}")


def main() -> int:
    session = new_session()
    for url in PAGES:
        look(session, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
