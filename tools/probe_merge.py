#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: is a fixture-group nested inside another one?

The first merge probe stamped hundreds of Champions League league-phase
fixtures with one date and put them all on tomorrow's board. Every one of
them is a real fixture; the date is what is wrong. The suspicion is that
div.fixture-group nests — an outer group holding the day headings of every
later day — so walking a group's descendants collects the whole page under
the first date found. This answers it rather than assuming it.

Delete once read.
"""
from __future__ import annotations

import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

import live_football_on_tv as second


def main() -> int:
    html = fetch(new_session(), second.SOURCE).text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    groups = soup.find_all("div", class_="fixture-group")
    fixtures = soup.find_all("div", class_="fixture")
    print(f"groups {len(groups)} | fixtures anywhere {len(fixtures)}")

    nested = sum(1 for g in groups
                 if g.find("div", class_="fixture-group") is not None)
    print(f"groups holding another group: {nested}")

    print("\n-- first eight groups: heading, own date, fixtures inside --")
    for group in groups[:8]:
        heading = norm(group.get_text(" ", strip=True))[:70]
        inside = group.find_all("div", class_="fixture")
        print(f"  {second.day_of(group)}  x{len(inside):4d}  {heading!r}")

    print("\n-- what a fixture's own ancestors look like --")
    if fixtures:
        node = fixtures[0]
        for step in range(6):
            node = node.parent
            if node is None:
                break
            print(f"  up {step + 1}: <{node.name} class={node.get('class')}>")

    print("\n-- the raw HTML of the first two fixtures --")
    for fixture in fixtures[:2]:
        print("  " + str(fixture)[:600].replace("\n", " "))

    print("\n-- and of whatever sits just before the first fixture --")
    if fixtures:
        seen = 0
        for sibling in fixtures[0].previous_siblings:
            text = norm(getattr(sibling, "get_text", lambda *_, **__: str(sibling))(" ", strip=True))
            if text:
                print(f"  <{getattr(sibling, 'name', 'text')} "
                      f"class={getattr(sibling, 'get', lambda _: None)('class')}>"
                      f"  {text[:80]!r}")
                seen += 1
            if seen >= 4:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
