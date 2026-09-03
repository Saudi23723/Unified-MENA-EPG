#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: what the fight-sport pages actually carry.

Asked for: UFC prelims and main card, Dana White's Contender Series,
The Ultimate Fighter, PFL, and boxing from more than one source.

Four of those five may already be arriving — /live-ufc-on-tv/ is read
with no competition filter at all, so whatever it lists reaches the
board. Whether it lists them is a fact about that page, and this prints
it rather than assuming either way. The fifth, a second boxing source,
needs a page nobody here has measured.

Nothing is wired off this file. It prints; a human reads; the reader is
written afterwards against what was printed. That order is the whole
lesson of this repository — five wrong guesses at jfa.jo's markup, a
404 for /live-formula-1-on-tv/ whose real slug was spelled out, and two
"perfect" calendars that named no broadcaster at all.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, ".")
from epg_lib import fetch, new_session, norm            # noqa: E402

WTM = "https://www.wheresthematch.com"

# What the reader named. Printed as a tally per page so the answer is a
# number, not an impression.
ASKED = {
    "UFC": re.compile(r"\bUFC\b", re.I),
    "prelims": re.compile(r"prelim", re.I),
    "main card": re.compile(r"main card", re.I),
    "Contender Series": re.compile(r"contender series|dana white", re.I),
    "TUF": re.compile(r"ultimate fighter|\bTUF\b", re.I),
    "PFL": re.compile(r"\bPFL\b|professional fighters league", re.I),
    "Bellator": re.compile(r"bellator", re.I),
    "ONE": re.compile(r"one championship|one fight night", re.I),
    "boxing": re.compile(r"boxing", re.I),
}

A_BROADCASTER = re.compile(
    r"sky sports|tnt sports|dazn|espn|abc\b|fox\b|paramount|bt sport"
    r"|channel 5|bbc\b|itv\b|premier sports|prime video|amazon", re.I)


def rows_of(html: str):
    """Every row the reader already reads, in the shape it already reads."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for row in soup.find_all("tr"):
        fixture = row.select_one(".fixture-details")
        if fixture is None:
            continue
        when = row.select_one("time[datetime]")
        competition = row.select_one(".competition-name")
        channels = row.select_one(".channel-details")
        yield {
            "fixture": norm(fixture.get_text(" ", strip=True)),
            "when": when.get("datetime") if when else None,
            "competition": norm(competition.get_text(" ", strip=True))
                           if competition else "",
            "channels": [norm(a.get_text(" ", strip=True))
                         for a in channels.find_all("a")] if channels else [],
        }


def read_page(session, path: str) -> None:
    print(f"\n=== {WTM}{path} " + "=" * 30)
    try:
        answer = fetch(session, WTM + path)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  SHUT: {exc}")
        return
    print(f"  {answer.status_code}, {len(answer.text) // 1024} KB")
    rows = list(rows_of(answer.text))
    print(f"  {len(rows)} row(s) in the shape the reader already reads")
    for row in rows[:40]:
        print(f"    {row['when']}  {row['fixture'][:70]}")
        print(f"        competition: {row['competition']}")
        print(f"        channels:    {row['channels']}")
    whole = answer.text
    print("  -- what the reader asked for, counted in the whole page --")
    for name, pattern in ASKED.items():
        print(f"    {name:<18} {len(pattern.findall(whole))}")


def list_fight_pages(session) -> None:
    """Its own links, so no slug is ever guessed at again."""
    print("\n=== every fight-sport page this site links to " + "=" * 12)
    try:
        home = fetch(session, WTM + "/").text
    except Exception as exc:                                  # noqa: BLE001
        print(f"  SHUT: {exc}")
        return
    soup = BeautifulSoup(home, "html.parser")
    seen = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if re.search(r"ufc|mma|box|wrestl|fight", href, re.I) and href not in seen:
            seen.add(href)
            print(f"    {href}   <- {norm(link.get_text(' ', strip=True))[:40]}")
    if not seen:
        print("    none linked from the homepage")


# A second boxing source, and PFL if anybody publishes it with a channel.
# Measured the same way every candidate on this project is: does it
# answer, how big, and does a broadcaster's name appear in it at all. A
# page that names no broadcaster cannot be a source here however complete
# its calendar is — that is what sank pdc.tv and motogp.com.
CANDIDATES = (
    "https://www.tapology.com/fightcenter",
    "https://www.sherdog.com/events",
    "https://www.espn.com/mma/schedule",
    "https://www.espn.com/boxing/schedule",
    "https://boxrec.com/en/schedule",
    "https://www.boxingscene.com/schedule",
    "https://www.pflmma.com/events",
    "https://www.ufc.com/events",
    "https://www.livesportsontv.com/sport/mma",
    "https://www.livesportsontv.com/sport/boxing",
)


def probe_candidates(session) -> None:
    print("\n=== candidates for a second fight source " + "=" * 18)
    for url in CANDIDATES:
        try:
            answer = fetch(session, url, retries=1)
        except Exception as exc:                              # noqa: BLE001
            print(f"  SHUT  {url}\n        {str(exc)[:120]}")
            continue
        text = answer.text
        hits = A_BROADCASTER.findall(text)
        distinct = sorted({h.lower() for h in hits})
        print(f"  {answer.status_code}  {len(text)//1024:>5} KB  {url}")
        print(f"        broadcaster mentions: {len(hits)}  {distinct[:8]}")
        print(f"        <time datetime=: {text.count('<time datetime=')}, "
              f"ld+json: {text.count('application/ld+json')}")


def main() -> int:
    session = new_session()
    list_fight_pages(session)
    for path in ("/live-ufc-on-tv/", "/live-boxing-on-tv/",
                 "/live-mma-on-tv/", "/live-wrestling-on-tv/"):
        read_page(session, path)
    probe_candidates(session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
