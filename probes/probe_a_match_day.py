#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round four, and the last: a day that HAS the competition on it.

Round three proved the shape. Spor Ekranı's event-list carries, inside
one link per broadcast, every field this board needs:

    img.event-list__sport-icon  alt   the sport
    span.event-list__time             the clock
    p.event-list__name                the title
    p.event-list__league              the competition
    img inside .event-list__channel   THE BROADCASTER

That last one is the answer that mattered: the channel is in the ROW, not
in a filter menu down the side.

But it was proved on the only volleyball row today, and that row is "Set
Sayısı — Voleybol Programi", a talk programme whose sport icon says
Programlar. A programme is refused by this board's live-only rule before
anything else looks at it, so the shape of a real MATCH row is still
unmeasured, and no handball row appeared at all.

The ld+json on the same page named two real ones — Bulgaristan - Kuzey
Makedonya at 19:00+03:00 and Romanya - Letonya at 20:00+03:00, both on
the 9th. So this walks the site's own day navigation to that day and
prints every volleyball and handball row it holds, with the channel each
one names.

If a match row names a broadcaster, the source can be wired. If it names
none, it cannot, and that is the answer.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402
from epg_lib import new_session, fetch, norm                   # noqa: E402

SOURCE = "https://www.sporekrani.com"
SPORT = re.compile(r"voleybol|hentbol", re.I)


def line(text=""):
    print(text, flush=True)


def page(session, url):
    got = fetch(session, url)
    if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
        got.encoding = "utf-8"
    return BeautifulSoup(got.text, "html.parser"), got


def read_rows(soup, where):
    box = soup.select("div.event-list")
    rows = [a for b in box for a in b.find_all("a")]
    line(f"\n{where}: {len(rows)} row(s) in the list")
    hits = []
    for row in rows:
        league = row.select_one("p.event-list__league")
        name = row.select_one("p.event-list__name")
        icon = row.select_one("img.event-list__sport-icon")
        blob = " ".join(filter(None, [
            norm(league.get_text(" ", strip=True)) if league else "",
            (icon.get("alt") or "") if icon else ""]))
        if not SPORT.search(blob):
            continue
        clock = row.select_one("span.event-list__time")
        chans = [ (i.get("alt") or "").strip()
                  for i in row.select("div[class*=channel] img") ]
        hits.append((
            norm(clock.get_text(strip=True)) if clock else "--:--",
            norm(name.get_text(" ", strip=True)) if name else "",
            blob,
            (icon.get("alt") or "") if icon else "",
            [c for c in chans if c]))
    line(f"  of which volleyball or handball: {len(hits)}")
    for clock, title, league, sport, chans in hits:
        line(f"    {clock}  {title[:42]:42} | {league[:34]:34} "
             f"| sport={sport:12} | {chans}")
    return hits


def main() -> int:
    session = new_session()
    soup, got = page(session, SOURCE + "/")
    line(f"home {got.status_code}  {len(got.text):,} bytes")
    read_rows(soup, "today")

    # the site's own day navigation, whatever shape it is
    days = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/\d{4}[-/]\d{2}[-/]\d{2}", href) and "match" not in href:
            days.append(href)
    days = list(dict.fromkeys(days))
    line(f"\nday links on the page: {len(days)}")
    for d in days[:8]:
        line(f"   {d}")

    for href in days[:3]:
        url = href if href.startswith("http") else SOURCE + href
        try:
            other, got = page(session, url)
        except Exception as exc:                               # noqa: BLE001
            line(f"\n{url} unreachable — {exc}")
            continue
        read_rows(other, url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
