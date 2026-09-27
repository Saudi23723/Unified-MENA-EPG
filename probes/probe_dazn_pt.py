#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask DAZN Portugal where its schedule is, before a line is written.

"هسع في قنوات dazn البرتغالية / ضيفهم على sports Portugal" — so DAZN's
Portuguese channels are to join the Sport TV channel, and the same rule
holds that Sport TV cost five rounds to learn: NOTHING is written
against a page until the page has been read.

WHAT IS ALREADY KNOWN, and it is only the names. Eleven Sports Portugal
became DAZN in 2023 and the Eleven brand left the linear channels in
July 2024, so the channels are DAZN 1 to DAZN 5 — and a sixth is named
in DAZN's own programming page. Which of them actually exist, and how
the site spells them, is a question for the site, not for me.

THE ONE QUESTION THAT DECIDES EVERYTHING is whether a grid is in the
HTML or drawn in the browser. Sport TV's /guia is 1.7MB holding
twenty-six clocks and all twenty-six are the hour ruler; tvkampen put
up the same wall. So every candidate here is asked that outright: what
fraction of its clocks fall exactly on the hour. A page whose clocks
are nearly all :00 is a ruler, not a schedule, and following it would
produce a reader that can never answer.

It commits nothing and publishes nothing.
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, ".")

from epg_lib import fetch, new_session, log      # noqa: E402

A_CLOCK = re.compile(r"\b([0-2]?\d):([0-5]\d)\b")
A_BLOB = re.compile(
    r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', re.S)

# DAZN's own pages first, then the Portuguese operators' guides, then the
# listings sites. A source of DAZN's own is worth more than one about it.
CANDIDATES = [
    ("DAZN programming article (pt)",
     "https://www.dazn.com/pt-PT/news/other/"
     "e-programacao-dazn-dazn-1-dazn-2-dazn-3-dazn-4-dazn-5-dazn-6-e-todas-"
     "as-transmissoes/1cbg3l63cijpf1eyophn4s0mwv"),
    ("DAZN schedule (en-PT)", "https://www.dazn.com/en-PT/schedule"),
    ("DAZN schedule (pt-PT)", "https://www.dazn.com/pt-PT/schedule"),
    ("DAZN weekend agenda",
     "https://www.dazn.com/pt-PT/news/outros/dazn-agenda-o-que-ver-esta-"
     "semana/gcx49a3bl2yq1hurw2ofgx2sa"),
    ("MEO guide DAZN1",
     "https://www.meo.pt/tv/canais-programacao/guia-tv?canal=DAZN1"),
    ("MEO guide DAZN1 (en)",
     "https://en.meo.pt/tv/channels-programming/tv-guide?canal=DAZN1"),
    ("tvepg.eu DAZN 1", "https://tvepg.eu/pt/portugal/channel/dazn_1"),
    ("tvepg.eu DAZN 2", "https://tvepg.eu/pt/portugal/channel/dazn_2"),
    ("livesoccertv DAZN Portugal",
     "https://www.livesoccertv.com/channels/dazn-portugal/"),
    ("DAZN robots", "https://www.dazn.com/robots.txt"),
    ("DAZN sitemap", "https://www.dazn.com/sitemap.xml"),
]

# How the channels might be spelled, so a page that names them is found
# by what it says rather than by what I expect it to say.
SPELLINGS = [
    "DAZN 1", "DAZN1", "DAZN Eleven 1", "DAZN 2", "DAZN2", "DAZN 3", "DAZN3",
    "DAZN 4", "DAZN4", "DAZN 5", "DAZN5", "DAZN 6", "DAZN6",
    "Eleven Sports", "Eleven 1", "DAZN Eleven",
]


def ruler_or_rows(text: str) -> str:
    """Are these clocks a schedule, or the hour ruler down the side?"""
    clocks = A_CLOCK.findall(text)
    if not clocks:
        return "no clocks at all"
    on_hour = sum(1 for _, minute in clocks if minute == "00")
    share = on_hour * 100 // len(clocks)
    verdict = ("A RULER — nearly every clock is exactly on the hour"
               if share >= 80 else
               "real rows — the clocks land off the hour" if share <= 60 else
               "unclear — mixed")
    return f"{len(clocks)} clock(s), {share}% on the hour  ->  {verdict}"


def blobs(text: str) -> list[str]:
    return [one.strip() for one in A_BLOB.findall(text)]


def look(session, name: str, url: str) -> None:
    log(f"\n───── {name}")
    log(f"  {url}")
    try:
        answer = fetch(session, url, timeout=30)
    except Exception as exc:                                  # noqa: BLE001
        log(f"  UNREACHABLE: {type(exc).__name__} {exc}")
        return
    text = answer.text
    log(f"  {answer.status_code}, {len(text) // 1024} KB, "
        f"landed on {answer.url}")
    log(f"  {ruler_or_rows(text)}")

    named = {spelling: text.count(spelling) for spelling in SPELLINGS
             if text.count(spelling)}
    log(f"  channel spellings present: {named or 'none'}")

    found = blobs(text)
    if found:
        log(f"  {len(found)} inline JSON blob(s), "
            f"largest {max(len(b) for b in found) // 1024} KB")
        big = max(found, key=len)
        try:
            parsed = json.loads(big)
        except ValueError as exc:
            log(f"    the largest does not parse: {exc}")
        else:
            shape = type(parsed).__name__
            log(f"    largest parses as {shape}")
            if isinstance(parsed, dict):
                log(f"    its keys: {sorted(parsed)[:20]}")
            elif isinstance(parsed, list):
                log(f"    {len(parsed)} entries; first: "
                    f"{str(parsed[0])[:200] if parsed else '(empty)'}")
    else:
        log("  no inline JSON blob")

    # An hour in its own context, so the shape of a row can be seen.
    hit = A_CLOCK.search(text)
    if hit:
        start = max(0, hit.start() - 400)
        window = re.sub(r"\s+", " ", text[start:hit.end() + 600])
        log(f"  around the first clock:\n    {window[:900]}")


def main() -> int:
    session = new_session()
    log("DAZN PORTUGAL — round one: where is the schedule, and is it in "
        "the HTML at all")
    for name, url in CANDIDATES:
        look(session, name, url)
    log("\nNothing was written and nothing was published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
