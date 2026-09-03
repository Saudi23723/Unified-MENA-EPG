#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The American and Canadian half, since the British source has neither.

wheresthematch is settled and read, and measured over all 44 of its
pages it names Sky Sports 1106 times, TNT 363, DAZN 226, BBC 80, Premier
Sports 74, ITV 2 — and Fox, NBC, ABC, CBS, ESPN, TSN, Sportsnet,
Paramount and Stan not once. It has no NFL page at all.

So this asks who publishes NFL, NBA and the North American channels with
the broadcaster beside them. livesportsontv files them under /league/nfl
and /league/nba — read off its own links, after two urls guessed from the
outside answered 404 — and Canada's own broadcasters publish schedules of
their own.

The same three questions as before, and the same refusal: an event with
no published broadcaster is no use here however complete the calendar is.
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402
from epg_lib import new_session, norm                          # noqa: E402

CANDIDATES = [
    ("livesportsontv NFL", "https://www.livesportsontv.com/league/nfl"),
    ("livesportsontv NBA", "https://www.livesportsontv.com/league/nba"),
    ("TSN schedule",       "https://www.tsn.ca/schedule"),
    ("Sportsnet schedule", "https://www.sportsnet.ca/schedule/"),
    ("CBC Sports",         "https://www.cbc.ca/sports/live"),
    ("NBA on its own site", "https://www.nba.com/schedule"),
]

CHANNELS = re.compile(
    r"sky sports?|tnt sports?|\bTSN\d?\b|sportsnet|\bfox\b|fs1|\bnbc\b"
    r"|peacock|\babc\b|\bcbc\b|\bespn\b|\bcbs\b|paramount|\bitv\b|\bbbc\b"
    r"|\bbein\b|dazn|stan sport|kayo|foxtel|prime video|netflix|amazon"
    r"|\brds\b|citytv|\btva\b", re.I)
A_CLOCK = re.compile(r"\b([01]?\d|2[0-3])[:.][0-5]\d\b|\b\d{1,2}\s?[ap]m\b",
                     re.I)


def look(name: str, url: str, session) -> None:
    print(f"\n=== {name} — {url}")
    try:
        reply = session.get(url, timeout=30)
    except Exception as exc:
        print(f"  SHUT — {type(exc).__name__}: {str(exc)[:110]}")
        return
    page = reply.text
    print(f"  {reply.status_code} — {len(page)} bytes")
    if reply.status_code != 200:
        return

    # Is the schedule shipped as JSON the page carries?
    for tag in ("__NEXT_DATA__", "__NUXT_DATA__", "__remixContext"):
        if f'id="{tag}"' in page:
            print(f"  ships {tag}")
    blocks = re.findall(
        r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S)
    kinds: dict[str, int] = {}
    for raw in blocks:
        try:
            blob = json.loads(raw)
        except Exception:
            continue
        stack = [blob]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                kind = str(item.get("@type", ""))
                if kind:
                    kinds[kind] = kinds.get(kind, 0) + 1
                stack.extend(v for v in item.values()
                             if isinstance(v, (dict, list)))
    print(f"  ld+json @types: {dict(sorted(kinds.items(), key=lambda x: -x[1])[:8]) or '— none —'}")

    soup = BeautifulSoup(page, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    rows = []
    for node in soup.find_all(["tr", "li", "article", "div", "section"]):
        text = norm(node.get_text(" ", strip=True))
        if not text or len(text) > 300:
            continue
        if A_CLOCK.search(text) and CHANNELS.search(text):
            rows.append((node.name,
                         " ".join(node.get("class") or []) or "-", text))
    print(f"  {len(rows)} container(s) holding a clock AND a channel")
    for tag, classes, text in rows[:5]:
        print(f"    <{tag} class={classes[:34]}> {text[:180]}")

    named: list[str] = []
    whole = norm(soup.get_text(" ", strip=True))
    for hit in CHANNELS.findall(whole):
        if hit.casefold() not in [x.casefold() for x in named]:
            named.append(hit)
    print(f"  channels in the visible text: {named[:14] or '— none —'}")


def main() -> int:
    session = new_session()
    for name, url in CANDIDATES:
        look(name, url, session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
