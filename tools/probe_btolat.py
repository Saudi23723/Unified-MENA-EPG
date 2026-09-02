#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: the exact shape of a live-footballontv row.

It carries the three Championship matches livefootballtv never listed,
with competition and channel attached — 1283 blocks holding a clock and a
broadcaster together. Before writing a reader for it, the structure has
to be seen rather than guessed: which element is a row, which parts of it
are time, teams, competition and channels, and how the page says which
day a row belongs to.

The clock is presumably London, this being a UK listings site, and that
has to be confirmed too — a source read in the wrong timezone is the exact
fault that just cost a day.

Delete once answered.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

URL = "https://www.live-footballontv.com/"
LONDON = ZoneInfo("Europe/London")
TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def main() -> int:
    now = datetime.now(timezone.utc)
    print(f"now {now:%Y-%m-%d %H:%M} UTC | London "
          f"{now.astimezone(LONDON):%H:%M} (offset "
          f"{now.astimezone(LONDON).utcoffset()})")

    soup = BeautifulSoup(fetch(new_session(), URL).text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # Which classes recur on things that look like a row?
    print("\n=== elements whose text starts with a clock ===")
    seen = {}
    for node in soup.find_all(True):
        text = norm(node.get_text(" ", strip=True))
        if not TIME.match(text or ""):
            continue
        if any(TIME.match(norm(k.get_text(' ', strip=True)) or "")
               for k in node.find_all(True, recursive=False)):
            continue                      # innermost only
        key = (node.name, tuple(node.get("class") or ()))
        seen.setdefault(key, []).append(text)
    for key, texts in sorted(seen.items(), key=lambda kv: -len(kv[1]))[:6]:
        print(f"  {key[0]} class={list(key[1])}  x{len(texts)}")
        for t in texts[:3]:
            print(f"      {t[:120]!r}")

    # The parts inside one such row.
    print("\n=== the parts inside the first three rows ===")
    shown = 0
    for node in soup.find_all(True):
        text = norm(node.get_text(" ", strip=True))
        if not TIME.match(text or "") or shown >= 3:
            continue
        if any(TIME.match(norm(k.get_text(' ', strip=True)) or "")
               for k in node.find_all(True, recursive=False)):
            continue
        print(f"  ROW <{node.name} class={node.get('class')}>")
        for kid in node.find_all(True, recursive=False):
            print(f"     <{kid.name} class={kid.get('class')}> "
                  f"{norm(kid.get_text(' ', strip=True))[:70]!r}")
        shown += 1

    # How is the day said? Look upward from a row for a date-looking line.
    print("\n=== headings that look like a date ===")
    DATE = re.compile(r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s+\d{1,2}"
                      r"|\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
                      re.I)
    found = 0
    for node in soup.find_all(True):
        text = norm(node.get_text(" ", strip=True))
        if text and len(text) < 60 and DATE.search(text) and not TIME.search(text):
            if any(DATE.search(norm(k.get_text(' ', strip=True)) or "")
                   for k in node.find_all(True, recursive=False)):
                continue
            print(f"  <{node.name} class={node.get('class')}> {text!r}")
            found += 1
            if found >= 6:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
