#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the real sporttv_pt reader and print what it returns.

The five rounds before this measured the site. This runs the READER
written from those measurements against the live site and prints every
row it produces — so the channel is wired to something whose output has
been looked at, not to something that merely imports.

It commits nothing and publishes nothing.
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, ".")
import sporttv_pt


def main() -> int:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"})

    now = datetime.now(timezone.utc)
    rows = sporttv_pt.events(session, now - timedelta(hours=6),
                             now + timedelta(days=7))

    print()
    print("=" * 74)
    print(f"{len(rows)} row(s) — the first 30, as the board would take them")
    print("=" * 74)
    for e in sorted(rows, key=lambda r: r["start"])[:30]:
        print(f"  {e['start']:%d/%m %H:%M}Z  {e['sport']:<11} "
              f"{e['competition'][:30]:<30} {e['title'][:34]:<34} "
              f"{'·'.join(e['channels'])}")

    print()
    print("  by sport:   ", dict(Counter(e["sport"] for e in rows)))
    print("  by channel: ", dict(Counter(c for e in rows
                                         for c in e["channels"])))
    print("  days covered:", sorted({e['start'].strftime('%d/%m')
                                     for e in rows}))
    bad = [e for e in rows if not e["title"] or not e["start"]]
    print(f"  rows missing a title or a time: {len(bad)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
