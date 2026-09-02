#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: the container around div.fixture__time.

The clock lives in div.fixture__time, 1884 of them, and the day is written
"Wed 2 SEP". What is still unknown is the element that holds a clock
together with its teams, its competition and its channels — and how a
fixture is tied to the day it belongs to. Both are in the parent chain,
which the last probe printed from the wrong end.

Delete once answered.
"""
from __future__ import annotations

import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

URL = "https://www.live-footballontv.com/"


def main() -> int:
    soup = BeautifulSoup(fetch(new_session(), URL).text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    clocks = soup.find_all("div", class_="fixture__time")
    print(f"clocks found: {len(clocks)}")

    print("\n=== the parent of the first three clocks, in full ===")
    for clock in clocks[:3]:
        row = clock.parent
        print(f"\n  PARENT <{row.name} class={row.get('class')}>")
        print(f"    whole text: {norm(row.get_text(' ', strip=True))[:150]!r}")
        for kid in row.find_all(True, recursive=False):
            print(f"      <{kid.name} class={kid.get('class')}> "
                  f"{norm(kid.get_text(' ', strip=True))[:80]!r}")
            for grand in kid.find_all(True, recursive=False)[:4]:
                print(f"          <{grand.name} class={grand.get('class')}> "
                      f"{norm(grand.get_text(' ', strip=True))[:60]!r}")

    print("\n=== walking up from a clock until something names the day ===")
    clock = clocks[0]
    node = clock
    for step in range(6):
        node = node.parent
        if node is None:
            break
        classes = node.get("class")
        head = norm(node.get_text(" ", strip=True))[:90]
        print(f"  up {step + 1}: <{node.name} class={classes}> {head!r}")

    print("\n=== siblings before the first fixture's block ===")
    block = clocks[0].parent.parent
    seen = 0
    for previous in block.find_all_previous(True):
        text = norm(previous.get_text(" ", strip=True))
        if text and len(text) < 40:
            print(f"  <{previous.name} class={previous.get('class')}> {text!r}")
            seen += 1
            if seen >= 8:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
