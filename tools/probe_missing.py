#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: does yallakora's match centre take a date, and how wide?

It is the only Arabic page measured whose blocks hold a channel, teams and
a clock together — div.allData. Two things decide whether it is worth
building: can it be asked for a day other than today, and does it carry
anything beyond Egypt. Delete once read.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

BASE = "https://www.yallakora.com/match-center/"


def look(session, url: str) -> None:
    try:
        html = fetch(session, url).text
    except Exception as exc:
        print(f"  {url:62s} -> {type(exc).__name__}")
        return
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    blocks = soup.find_all("div", class_="allData")
    # the competition heading each block sits under
    comps = []
    for b in blocks:
        head = b.find_previous(class_="tourTitle")
        comps.append(norm(head.get_text(" ", strip=True))[:40] if head else "?")
    print(f"  {url:62s} -> {len(blocks):3d} block(s)")
    for b, c in list(zip(blocks, comps))[:8]:
        print(f"        [{c}]  {norm(b.get_text(' ', strip=True))[:110]}")


def main() -> int:
    session = new_session()
    today = date.today()
    print("=== can it be asked for another day? ===")
    for step in (0, 1, 2):
        day = today + timedelta(days=step)
        for shape in (f"{BASE}?date={day:%m/%d/%Y}",
                      f"{BASE}?date={day:%d/%m/%Y}"):
            look(session, shape)
    print("\n=== and what does the plain page carry? ===")
    look(session, BASE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
