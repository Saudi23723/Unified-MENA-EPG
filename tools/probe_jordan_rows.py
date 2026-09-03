#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The league's OWN page, which has the round the homepage does not.

The reader photographed الوحدات - الفيصلي on the federation's app and it
is real: 04-09-2026 at 20:30, ستاد عمان الدولي. I had said the federation
was not publishing it, and that was wrong — it was true only of the one
page I was reading.

Reading the site's own links found the page that has it:

    jfa.jo/tourn.php?id=1&idcat=6&idsubcat=16   8 club rows, 4 to play
    the homepage                                16 club rows, 1 to play

Four is exactly the round the reader photographed: البقعة-دوقرة,
شباب الأردن-الرمثا, الوحدات-الفيصلي, العربي-السلط.

But the screenshot shows the date and time BELOW each fixture — "ملعب
البترا - 03-09-2026 - 19:00" — where the homepage puts a header ABOVE
it, and collect() refuses any row whose header does not come first. So
the shape has to be printed before a line is written against it. Guessing
this page's arrangement is the exact habit that cost five builds.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402

import jordan_football as jfa                                  # noqa: E402
from epg_lib import fetch, new_session, norm                   # noqa: E402

LEAGUE = ("https://jfa.jo/tourn.php?id=1&idcat=6&idsubcat=16"
          "&title=%D8%A7%D9%84%D8%AF%D9%88%D8%B1%D9%8A")


def main() -> int:
    page = fetch(new_session(), LEAGUE).text
    print(f"the league's own page — {len(page)} bytes\n")

    soup = BeautifulSoup(page, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    print("=== EVERY <tr>, IN ORDER, AS THE PAGE WRITES THEM ===")
    for at, row in enumerate(soup.find_all("tr")):
        text = norm(row.get_text(" | ", strip=True))
        if not text:
            continue
        marks = []
        for css in ("span.haly", "span.haly1", "span.haly2",
                    "span.team1", "span.team2", "span.rrresult"):
            if row.select_one(css):
                marks.append(css.split(".")[1])
        print(f"  [{at:>3}] {'+'.join(marks) or '-':38} {text[:130]}")

    print("\n=== WHAT THE READER MAKES OF IT AS IT STANDS ===")
    for event in jfa.collect(page):
        print(f"    {event['start'].astimezone(jfa.AMMAN):%Y-%m-%d %H:%M} "
              f"| {event['title']} | {event['competition']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
