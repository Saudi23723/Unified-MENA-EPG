#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: does livefootballtv name the competition of each match?

today_matches_epg reads the team names, the kickoff and the channels out of
each <tr>, and nothing else. Before promising a competition filter, find out
whether the page says which competition a row belongs to, and in what shape.

Delete this file and its workflow once the question is answered.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session

SOURCE = "https://www.livefootballtv.info/"


def text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def main() -> int:
    html = fetch(new_session(), SOURCE).text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    rows = [r for r in soup.find_all("tr")
            if r.find("td", class_="local")
            and r.find("td", class_="visitante")
            and r.find("td", class_="canales")]
    print(f"match rows found: {len(rows)}")

    # 1. Anything on the row itself that could name a competition?
    print("\n=== classes and attributes on a match row ===")
    for r in rows[:3]:
        print("  tr attrs:", dict(r.attrs))
        for td in r.find_all("td"):
            print("     td", dict(td.attrs), "|", text(td)[:70])
        print("   ---")

    # 2. The nearest thing above the row that is not a match row.
    print("\n=== nearest heading above each of the first 25 match rows ===")
    seen = {}
    for r in rows[:25]:
        head = ""
        node = r
        for _ in range(60):
            node = node.find_previous(["tr", "h1", "h2", "h3", "h4",
                                       "div", "caption", "thead", "a"])
            if node is None:
                break
            if node.name == "tr" and node.find("td", class_="local"):
                continue
            candidate = text(node)
            if 2 < len(candidate) < 90:
                head = candidate
                break
        home = text(r.find("td", class_="local"))
        away = text(r.find("td", class_="visitante"))
        print(f"  {head[:55]:<55} | {home} - {away}"[:130])
        seen[head] = seen.get(head, 0) + 1

    print("\n=== distinct headings seen ===")
    for head, n in sorted(seen.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3}  {head[:100]}")

    # 3. Does any itemprop or microdata name a competition?
    print("\n=== itemprop values anywhere on the page ===")
    props = {}
    for node in soup.find_all(attrs={"itemprop": True}):
        props[node["itemprop"]] = props.get(node["itemprop"], 0) + 1
    print(" ", props)

    return 0


if __name__ == "__main__":
    sys.exit(main())
