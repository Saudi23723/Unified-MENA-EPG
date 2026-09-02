#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: the exact shape of one yallakora match block.

The date parameter is MM/DD/YYYY and ?date=09/03/2026 carries the very
fixture that was missing — الأهلي v سموحة on ON Sport at 20:00 Cairo,
which is 10:00 on the reader's clock, the figure their own app showed.
Its Cairo clock also agrees with this guide's corrected times: it puts
Toulouse v Lille at 21:45, which is 18:45 UTC, exactly what the board now
says.

What is NOT known is the markup inside div.allData, and guessing that is
the mistake that stamped 1876 fixtures with one date last time. So this
prints the raw HTML of two blocks and their child classes. Delete once
read.
"""
from __future__ import annotations

import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

URL = "https://www.yallakora.com/match-center/?date=09/03/2026"


def main() -> int:
    soup = BeautifulSoup(fetch(new_session(), URL).text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    blocks = soup.find_all("div", class_="allData")
    print(f"{len(blocks)} block(s)\n")

    for block in blocks[:2]:
        print("=" * 70)
        print(str(block)[:1800].replace("\n", " "))
        print("\n-- every descendant with a class, in order --")
        for kid in block.find_all(True):
            klass = kid.get("class")
            if not klass:
                continue
            own = norm(kid.get_text(" ", strip=True))
            if own:
                print(f"   <{kid.name} class={klass}>  {own[:60]!r}")

    print("\n-- the heading each block sits under --")
    for block in blocks[:4]:
        head = block.find_previous(class_="tourTitle")
        print(f"   {str(head)[:220] if head else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
