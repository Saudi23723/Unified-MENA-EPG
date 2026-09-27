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

    # The clubs are in <tr>s and the stadium-date-time line is NOT — the
    # rows between them printed empty. So look OUTSIDE the row: at what
    # follows it, and at the block that contains it. One of those holds
    # "ملعب البترا - 03-09-2026 - 19:00", and until it is found the
    # fixture has no time and is rightly refused.
    print("=== EACH UPCOMING FIXTURE, AND WHAT SITS AROUND IT ===")
    for row in soup.find_all("tr"):
        home = row.select_one("span.team1")
        away = row.select_one("span.team2")
        verdict = row.select_one("span.rrresult")
        if home is None or away is None or verdict is None:
            continue
        if not jfa.NOT_PLAYED_YET.match(norm(verdict.get_text(" ", strip=True))):
            continue
        print(f"\n  ── {norm(home.get_text())} vs {norm(away.get_text())}")

        after = []
        node = row
        for _ in range(4):
            node = node.find_next_sibling()
            if node is None:
                break
            after.append(f"<{node.name} class="
                         f"{' '.join(node.get('class') or []) or '-'}> "
                         f"{norm(node.get_text(' | ', strip=True))[:140]}")
        print("     next siblings:")
        for line in after:
            print(f"       {line}")

        holder = row.parent
        for step in range(3):
            if holder is None:
                break
            text = norm(holder.get_text(" | ", strip=True))
            print(f"     {step} up <{holder.name} class="
                  f"{' '.join(holder.get('class') or []) or '-'}>: "
                  f"{text[:200]}")
            holder = holder.parent

        for stamp in (row.find_all("time")
                      + (row.parent.find_all("time") if row.parent else [])):
            print(f"     <time datetime={stamp.get('datetime')!r}>")

    print("\n=== ANY DATE ANYWHERE IN THE PAGE TEXT ===")
    import re as _re
    whole = norm(soup.get_text(" ", strip=True))
    for hit in _re.findall(r"[^|]{0,40}\d{2}-\d{2}-\d{4}[^|]{0,30}", whole)[:8]:
        print(f"    {norm(hit)}")
    for hit in _re.findall(r"[^|]{0,30}\d{4}-\d{2}-\d{2}[^|]{0,30}", whole)[:8]:
        print(f"    {norm(hit)}")

    print("\n=== WHAT THE READER MAKES OF IT AS IT STANDS ===")
    for event in jfa.collect(page):
        print(f"    {event['start'].astimezone(jfa.AMMAN):%Y-%m-%d %H:%M} "
              f"| {event['title']} | {event['competition']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
