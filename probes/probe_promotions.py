#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask PFL, Most Valuable Promotions, Netflix and ESPN for their cards.

Asked directly: "espn, pfl, most valuable promotion ... هدول فحصتهم و
عملت إضافة لل fights تبعهم ؟ و Netflix events".

NO. And the honest shape of "no" matters, because all four ARE in the
repository as words:

    PFL       one mention, in sky_epg's A_FIGHT — so a PFL card is kept
              IF Sky happens to list one. Zero on the published board.
    MVP       only ever seen as "MVP Boxing: ... Hlts", which is
              REFUSED as a highlights show. No source.
    Netflix   a word in a comment. Nothing reads it.
    ESPN      a word in a comment, and a broadcaster label other readers
              print. Nothing reads its schedule.

A name that would be matched if some other source mentioned it is not a
source. That is the mistake this repository has a standing rule about —
counting a word in a page is not finding a row — so nothing is written
until these four have been asked what they publish.

Each candidate below is the promotion's or the broadcaster's OWN site or
API. What is printed per candidate: the status, the size, whether the
schedule is in the HTML at all, whether it carries a machine-readable
INSTANT (the thing every reader here refuses to work without), and the
first rows or records so the shape can be read rather than guessed.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                  " (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

# ESPN's own site API — the endpoints its own pages call. Public, no key.
ESPN = (
    ("ESPN · UFC",
     "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"),
    ("ESPN · PFL",
     "https://site.api.espn.com/apis/site/v2/sports/mma/pfl/scoreboard"),
    ("ESPN · boxing",
     "https://site.api.espn.com/apis/site/v2/sports/boxing/scoreboard"),
)

PAGES = (
    ("PFL", "https://pflmma.com/events"),
    ("PFL (schedule)", "https://pflmma.com/schedule"),
    ("Most Valuable Promotions", "https://mostvaluablepromotions.com/"),
    ("Most Valuable Promotions (events)",
     "https://mostvaluablepromotions.com/events"),
    ("Netflix live", "https://www.netflix.com/live"),
    ("Netflix Tudum sport", "https://www.netflix.com/tudum/live-events"),
)

A_UNIX = re.compile(r"\b1[7-9]\d{8}\b")
AN_ISO = re.compile(r"\b20\d\d-\d\d-\d\dT\d\d:\d\d")
A_DATETIME_ATTR = re.compile(r'datetime="([^"]+)"')
TAGS = re.compile(r"<[^>]+>")


def espn_api(session, name: str, url: str) -> None:
    print(f"\n── {name}\n   {url}")
    try:
        page = session.get(url, timeout=25, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE {str(exc)[:90]}")
        return
    print(f"   {page.status_code}  {len(page.content) // 1024} KB")
    if page.status_code != 200:
        return
    try:
        body = json.loads(page.text)
    except ValueError as exc:
        print(f"   NOT JSON {str(exc)[:60]}")
        return

    print(f"   top-level keys: {list(body)[:10]}")
    events = body.get("events") or []
    print(f"   {len(events)} event(s)")
    for one in events[:6]:
        when = one.get("date") or ""
        name_of = one.get("name") or one.get("shortName") or ""
        where = ""
        for comp in one.get("competitions") or []:
            for cast in comp.get("broadcasts") or []:
                where = ", ".join(cast.get("names") or []) or where
        print(f"      {when:<26} {name_of[:52]}")
        print(f"          broadcast: {where or '(none named)'}")
    if not events:
        # A season with nothing on today still says what it CAN carry.
        print(f"      (leagues: "
              f"{[l.get('name') for l in body.get('leagues') or []]})")


def a_page(session, name: str, url: str) -> None:
    print(f"\n── {name}\n   {url}")
    try:
        page = session.get(url, timeout=30, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE {str(exc)[:90]}")
        return
    print(f"   {page.status_code}  {len(page.content) // 1024} KB  "
          f"{page.headers.get('content-type', '?')[:36]}")
    if page.status_code != 200:
        return

    html = page.text
    blocks = len(re.findall(r"application/ld\+json", html))
    print(f"   ld+json blocks: {blocks}")
    print(f"   <time datetime>: {len(A_DATETIME_ATTR.findall(html))}"
          f"   ISO instants: {len(AN_ISO.findall(html))}"
          f"   unix stamps: {len(A_UNIX.findall(html))}")

    for stamp in A_DATETIME_ATTR.findall(html)[:4]:
        print(f"      datetime={stamp!r}")
    for stamp in AN_ISO.findall(html)[:4]:
        print(f"      iso {stamp}")

    plain = re.sub(r"\s+", " ", TAGS.sub(" ", html))
    for word in ("vs", "Fight Night", "Championship", "Live", "Tickets"):
        print(f"   '{word}' appears {plain.count(word)} time(s)")
    if not (A_DATETIME_ATTR.search(html) or AN_ISO.search(html)
            or A_UNIX.search(html)):
        print("   NO MACHINE-READABLE INSTANT ANYWHERE — nothing here can "
              "become a row, whatever the page says in words")


def mvp_shape(session) -> None:
    """The one candidate with a pulse, read rather than counted.

    mostvaluablepromotions.com/events carries 34 unix stamps and 33 "vs".
    That is promising and it is not proof: pflmma.com carries 77 ISO
    instants too and every one of them is from 2018 — an archive that
    counts exactly like a schedule. So the stamps here are decoded and
    dated, and the text around them printed, before anything is written.
    """
    url = "https://mostvaluablepromotions.com/events"
    print("\n" + "=" * 72)
    print("MOST VALUABLE PROMOTIONS — what its stamps actually say")
    print("=" * 72)
    print(f"   {url}")
    try:
        page = session.get(url, timeout=30, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE {str(exc)[:90]}")
        return
    html = page.text
    now = datetime.now(timezone.utc)

    stamps = sorted({int(one) for one in A_UNIX.findall(html)})
    print(f"   {len(stamps)} distinct unix stamp(s)")
    ahead = 0
    for one in stamps:
        when = datetime.fromtimestamp(one, timezone.utc)
        days = (when - now).total_seconds() / 86400
        if days > -1:
            ahead += 1
        print(f"      {one}  {when:%Y-%m-%d %H:%M} UTC  "
              f"{days:+.1f} day(s)")
    print(f"   STAMPS AT OR AFTER TODAY: {ahead}"
          f"{'' if ahead else '   <- an ARCHIVE, like pflmma'}")

    # ld+json is where a site usually puts an Event properly.
    for block in re.findall(
            r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
            html, re.S)[:3]:
        try:
            data = json.loads(block.strip())
        except ValueError:
            print("   ld+json present but does not parse")
            continue
        kinds = data if isinstance(data, list) else [data]
        for kind in kinds:
            print(f"   ld+json @type={kind.get('@type')!r} "
                  f"keys={list(kind)[:9]}")

    # And the fights themselves, as text around each "vs".
    plain = re.sub(r"\s+", " ", TAGS.sub(" ", html))
    for found in list(re.finditer(r"\bvs\b", plain))[:8]:
        at = found.start()
        print(f"      ...{plain[max(0, at - 70):at + 60].strip()}...")


def main() -> int:
    session = requests.Session()
    print(f"asked at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n")
    print("=" * 72)
    print("ESPN'S OWN SITE API — the endpoints its own pages call")
    print("=" * 72)
    for name, url in ESPN:
        espn_api(session, name, url)

    print("\n" + "=" * 72)
    print("THE PROMOTIONS' AND NETFLIX'S OWN PAGES")
    print("=" * 72)
    for name, url in PAGES:
        a_page(session, name, url)

    mvp_shape(session)
    print("\nDone. Nothing was written; the readers are written afterwards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
