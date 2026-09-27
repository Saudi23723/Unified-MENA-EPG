#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round three: one question, and everything turns on it.

Rounds one and two closed every other door. The listings site has no
volleyball or handball page (404 against a 200 control). The
confederations render their calendars in JavaScript — CEV, EuroVolley,
Volleyball World and the EHF carry nought instants between them, and the
IHF's sixteen name no broadcaster. S Sport's own site serves a
certificate for the wrong hostname and cannot be read at all; its Plus
site says "voleybol" nought times. TRT's grid says it 108 times and
carries no <time>, no table row and no ld+json.

What is left is Spor Ekranı's own schedule, which round two found is not
in the ld+json at all but in a div called event-list, one link per
broadcast:

    02:00 J.Pegula - E.Navarro Tenis Amerika Açik Kadınlar Çeyrek Final
    04:00 B.Shelton - C.Alcaraz Tenis Amerika Açik Erkekler Çeyrek Final

A clock, the two sides, THE SPORT, and the competition — which is every
field this board needs except one. The page also carries channel logos,
alt-texted "TRT Spor", "Eurosport", and a channel list down the side.

So: is that channel list a FILTER MENU, or is a channel attached to each
row? The difference decides the whole thing. A menu is what boxingscene
turned out to be when this project last went looking for broadcasters,
and a channel picked out of the page rather than out of the row is the
guess spor_ekrani.py already refuses by name.

This prints every volleyball and handball row of the list with everything
inside it, and nothing from outside it.

Measurement only.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402
from epg_lib import new_session, fetch, norm                   # noqa: E402

SOURCE = "https://www.sporekrani.com/"
SPORT = re.compile(r"voleybol|hentbol", re.I)
A_CLOCK = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def line(text=""):
    print(text, flush=True)


def main() -> int:
    session = new_session()
    got = fetch(session, SOURCE)
    if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
        got.encoding = "utf-8"
    soup = BeautifulSoup(got.text, "html.parser")

    lists = soup.select("div.event-list")
    line(f"event-list containers: {len(lists)}")
    if not lists:
        line("no event-list — the page shape has changed")
        return 0

    rows = []
    for box in lists:
        rows.extend(box.find_all("a"))
    line(f"rows (links) inside them: {len(rows)}")

    hits = [r for r in rows if SPORT.search(r.get_text(" ", strip=True))]
    line(f"rows naming voleybol or hentbol: {len(hits)}")
    line()

    for row in hits[:20]:
        text = norm(row.get_text(" ", strip=True))
        clock = A_CLOCK.search(text)
        imgs = [(i.get("alt") or i.get("title") or "").strip()
                for i in row.find_all("img")]
        stamp = row.find("time")
        line("-" * 70)
        line(f"  text     : {text[:130]}")
        line(f"  clock    : {clock.group(0) if clock else 'none'}")
        line(f"  <time>   : {stamp.get('datetime') if stamp else 'none'}")
        line(f"  img alts : {[a for a in imgs if a]}")
        line(f"  href     : {(row.get('href') or '')[:80]}")
        # every data- attribute the row carries
        data = {k: v for k, v in row.attrs.items() if k.startswith("data")}
        line(f"  data-*   : {data}")
        # any nested element whose class mentions a channel
        chan = [norm(e.get_text(' ', strip=True))
                for e in row.find_all(True)
                if any("chan" in c or "kanal" in c.lower()
                       for c in (e.get("class") or []))]
        line(f"  channel-classed elements: {chan[:4]}")

    line()
    line("-" * 70)
    line("ONE ROW IN FULL, so the shape is not guessed:")
    if hits:
        line(hits[0].prettify()[:1600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
