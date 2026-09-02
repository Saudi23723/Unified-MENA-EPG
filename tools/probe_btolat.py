#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: how much does بطولات actually cover, and worldcup26?

بطولات was the only one of seven candidates whose HTML carried both a
kickoff and a channel. But the sample that proved it was entirely
Egyptian — On Sport, المقاولون, أبو قير — and a source that only covers
Egypt patches a small hole, not the one that hurt: three Championship
matches livefootballtv never listed.

So the question is coverage, not usability: which competitions does it
carry, does a Saudi or an English match appear, and is the channel
attached to the row or merely somewhere on the page.

worldcup26.ir is asked the same three questions from scratch.

Delete once answered.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

BTOLAT = "https://www.btolat.com/match-score"
WORLDCUP = "https://worldcup26.ir/"

TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
KNOWN = ("bein", "بي ان", "بين سبورت", "ssc", "thmanyah", "ثمانية", "shahid",
         "شاهد", "sky", "espn", "fox", "on sport", "أبوظبي", "abu dhabi",
         "alkass", "الكأس", "tod", "starzplay", "دبي", "الرياضية")


def soup_of(url: str):
    html = fetch(new_session(), url).text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return html, soup


def look_btolat() -> None:
    print(f"\n{'=' * 72}\nبطولات — coverage\n  {BTOLAT}\n{'=' * 72}")
    try:
        html, soup = soup_of(BTOLAT)
    except Exception as exc:
        print(f"  unreachable: {str(exc)[:120]}")
        return
    print(f"  {len(html) // 1024} KB")

    # Rows: anything holding a clock and at least two link-looking names.
    rows = []
    for node in soup.find_all(["tr", "li", "div", "article"]):
        text = norm(node.get_text(" ", strip=True))
        if not (30 < len(text) < 260 and TIME.search(text)):
            continue
        if node.find(["tr", "li", "article"]):
            continue                      # keep the innermost block only
        rows.append((node, text))

    print(f"  blocks that look like a match row: {len(rows)}")
    print("\n  -- the first twelve, and what channel is inside each --")
    for node, text in rows[:12]:
        inside = sorted({k for k in KNOWN if k in text.lower()})
        print(f"    {text[:96]!r}")
        print(f"       channel in the row: {inside or '— none —'}"
              f" | classes={node.get('class')}")

    whole = norm(soup.get_text(" ", strip=True)).lower()
    print("\n  -- which leagues are named anywhere on the page --")
    for label, needle in (("Saudi", "السعود"), ("English", "الإنجليز"),
                          ("Spanish", "الإسبان"), ("Italian", "الإيطال"),
                          ("Egyptian", "المصري"), ("Jordan", "الأردن"),
                          ("Champions", "أبطال"), ("Turkish", "الترك")):
        print(f"     {label:<10} {'yes' if needle in whole else 'no'}")


def look_worldcup() -> None:
    print(f"\n{'=' * 72}\nworldcup26.ir\n  {WORLDCUP}\n{'=' * 72}")
    try:
        html, soup = soup_of(WORLDCUP)
    except Exception as exc:
        print(f"  unreachable: {str(exc)[:160]}")
        return
    text = norm(soup.get_text(" ", strip=True))
    clocks = TIME.findall(text)
    found = sorted({k for k in KNOWN if k in text.lower()})
    print(f"  {len(html) // 1024} KB | visible text {len(text)} chars "
          f"| clocks {len(clocks)}")
    print(f"  channels recognised: {found or '— none —'}")
    print(f"  first 400 characters of what it says:\n    {text[:400]!r}")


def main() -> int:
    look_btolat()
    look_worldcup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
