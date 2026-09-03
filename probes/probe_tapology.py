#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask tapology.com/fightcenter what it publishes, before believing it.

Proposed directly. Three of the four sources asked before it were dead
ends — ESPN 403 on every endpoint, Netflix's live page a 22 KB shell,
and pflmma carrying 77 ISO instants of which every one is from 2018 —
so this is asked the same way rather than taken on trust.

WHAT DECIDES IT, in order:

  A MACHINE-READABLE INSTANT. Every reader here refuses to place a row
  without one, and pflmma is the standing proof that a page can be full
  of dates and still be an archive. So the stamps are decoded and DATED,
  not counted.

  A BROADCASTER. This is the question that matters most and the one a
  fight database usually answers worst: the board's rule is that an
  event nobody can name a channel for does not go on it. A card with a
  date and no channel cannot become a row here.

  THE CARD, SPLIT. Prelims and early prelims were asked for repeatedly
  and only Sky has ever supplied them. Whether this does is printed.

One thing is written down rather than glossed: tapology is a fight
DATABASE, not a promotion's own site nor a broadcaster's own guide. The
standing rule in this repository is the official source — "بدك تاخد يا
من github تبعي او المصدر الرسمي" — and this is neither. It was asked
for by name, so it is measured; whether it is used is a decision that
belongs to whoever set that rule, and this prints what it would cost.

It prints. It writes nothing.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                  " (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en",
}

PAGES = (
    ("fightcenter", "https://www.tapology.com/fightcenter"),
    ("fightcenter events", "https://www.tapology.com/fightcenter/events"),
    ("boxing", "https://www.tapology.com/fightcenter?group=boxing"),
)

A_UNIX = re.compile(r"\b1[7-9]\d{8}\b")
AN_ISO = re.compile(r"\b20\d\d-\d\d-\d\dT?\s?\d\d:\d\d")
A_DATETIME_ATTR = re.compile(r'datetime="([^"]+)"')
TAGS = re.compile(r"<[^>]+>")

# What a broadcaster looks like, so "does it name one" is answered with
# names rather than an impression.
A_BROADCASTER = re.compile(
    r"\b(?:ESPN\+?|UFC Fight Pass|DAZN|TNT Sports|Sky Sports|Netflix|"
    r"Paramount\+|Prime Video|beIN|Showtime|PPV|Pay-Per-View|BT Sport)\b",
    re.I)


def one(session, name: str, url: str) -> None:
    print(f"\n── {name}\n   {url}")
    try:
        page = session.get(url, timeout=30, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE {str(exc)[:100]}")
        return
    print(f"   {page.status_code}  {len(page.content) // 1024} KB  "
          f"{page.headers.get('content-type', '?')[:34]}")
    if page.status_code != 200:
        return

    html = page.text
    now = datetime.now(timezone.utc)

    blocks = len(re.findall(r"application/ld\+json", html))
    print(f"   ld+json blocks: {blocks}"
          f"   <time datetime>: {len(A_DATETIME_ATTR.findall(html))}"
          f"   unix: {len(A_UNIX.findall(html))}"
          f"   iso-ish: {len(AN_ISO.findall(html))}")

    # DECODED AND DATED, because pflmma proved counting is not knowing.
    stamps = sorted({int(x) for x in A_UNIX.findall(html)})
    ahead = [s for s in stamps
             if (datetime.fromtimestamp(s, timezone.utc) - now).days > -2]
    print(f"   {len(stamps)} distinct unix stamp(s), {len(ahead)} at or "
          f"after today")
    for s in stamps[:6]:
        when = datetime.fromtimestamp(s, timezone.utc)
        print(f"      {s}  {when:%Y-%m-%d %H:%M} UTC  "
              f"{(when - now).total_seconds() / 86400:+.1f} day(s)")
    for stamp in A_DATETIME_ATTR.findall(html)[:6]:
        print(f"      datetime={stamp!r}")

    plain = re.sub(r"\s+", " ", TAGS.sub(" ", html))

    # THE BROADCASTER — the thing the board cannot do without.
    casters = {}
    for found in A_BROADCASTER.finditer(plain):
        casters[found.group(0)] = casters.get(found.group(0), 0) + 1
    print(f"   broadcasters named: {len(casters)}")
    for who, n in sorted(casters.items(), key=lambda kv: -kv[1])[:10]:
        print(f"      {who:<22} x{n}")
    if not casters:
        print("      NONE — a card with no channel cannot become a row here")

    # The card, split.
    for word in ("Prelim", "Early Prelim", "Main Card", "Main Event"):
        print(f"   '{word}' appears {plain.count(word)} time(s)")

    # And what an event row actually looks like, so the shape is read.
    for found in list(re.finditer(r"\bvs\.?\b", plain))[:6]:
        at = found.start()
        print(f"      ...{plain[max(0, at - 90):at + 70].strip()}...")


def main() -> int:
    session = requests.Session()
    print(f"asked at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    for name, url in PAGES:
        one(session, name, url)
    print("\nDone. Nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
