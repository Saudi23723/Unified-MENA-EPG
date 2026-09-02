#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: can a second and third source give what the first misses?

livefootballtv missed three Championship matches a scores app had, so the
gap is real. Two candidates are already proved inside this repository —
LiveSoccerTV, read by the Shahid guide, and Spor Ekranı, read by the tabii
guide — but both are read there through channel-specific pages that do not
carry a broadcaster list. The general schedule pages are a different shape
and nobody here has looked at them.

The only question that matters for this guide: does a page give, for each
match, a kickoff AND the names of the channels showing it? A source with
times and no channels is no use — the guide drops such a match by its own
rule.

Delete once it has answered.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

PAGES = [
    ("LiveSoccerTV schedule", "https://www.livesoccertv.com/schedules/"),
    ("Spor Ekranı", "https://www.sporekrani.com/"),
]

TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def describe(name: str, url: str) -> None:
    print(f"\n{'=' * 70}\n{name}  {url}\n{'=' * 70}")
    try:
        html = fetch(new_session(), url).text
    except Exception as exc:
        print(f"  unreachable: {exc}")
        return
    print(f"  fetched {len(html) // 1024} KB")

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # What kind of container holds a row here?
    rows = soup.find_all("tr")
    print(f"  <tr> count: {len(rows)}")
    with_time = [r for r in rows if TIME.search(norm(r.get_text(" ", strip=True)))]
    print(f"  <tr> carrying a clock: {len(with_time)}")

    print("\n  -- first rows that carry a clock, with their cell classes --")
    for row in with_time[:6]:
        cells = row.find_all(["td", "th"])
        print(f"    row class={row.get('class')}")
        for cell in cells:
            text = norm(cell.get_text(" ", strip=True))
            links = [norm(a.get_text(' ', strip=True))
                     for a in cell.find_all("a")][:4]
            print(f"       td class={cell.get('class')} | {text[:60]!r}"
                  + (f" | links={links}" if links else ""))
        print("       ---")

    # Anything that looks like a channel list?
    print("\n  -- classes whose name mentions channel/broadcast/kanal --")
    seen = set()
    for node in soup.find_all(attrs={"class": True}):
        for name in node.get("class"):
            low = name.lower()
            if any(w in low for w in ("channel", "broadcast", "kanal", "tv",
                                      "canal")) and name not in seen:
                seen.add(name)
                print(f"     .{name}  e.g. "
                      f"{norm(node.get_text(' ', strip=True))[:70]!r}")
            if len(seen) >= 12:
                return


def main() -> int:
    for name, url in PAGES:
        describe(name, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
