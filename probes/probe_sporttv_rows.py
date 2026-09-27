#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round two: the whole Sport TV listing, and what one row carries.

Round one settled two things. /guia is a CALENDAR DRAWN IN THE BROWSER —
1.7MB of HTML holding 26 clocks, and those 26 are the hour ruler
(class="hour" 00:00, 01:00 ...), not programmes. But /jogos/competicao/
IS in the HTML: 258 clocks, 612 structured event fields, and every row
carrying its channel as a logo and the event as an id —

    17:00  <img src="/logos-small/sporttv-2-rebrand.svg" alt="Canal 728"
    19:30  <img src="/logos-small/sporttv-1-rebrand.svg" alt="Canal 727"
           <div id="mg:sportevent:...

That page is ONE competition. This asks for the listing that carries all
of them — every sport, every channel, live and scheduled — and dumps a
whole row so the reader is written from what is there rather than from
a guess about it.

It commits nothing and publishes nothing.
"""
from __future__ import annotations

import json
import re
import sys

import requests

TIMEOUT = 30
HEAD = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"}
BASE = "https://www.sporttv.pt"


def get(session, url):
    try:
        return session.get(url, timeout=TIMEOUT, allow_redirects=True)
    except Exception as exc:                                   # noqa: BLE001
        print(f"    {url[:90]} -> {type(exc).__name__}")
        return None


def report(text: str, url: str) -> None:
    clocks = len(re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", text))
    events = len(set(re.findall(r"mg:sportevent:[A-Za-z0-9]+", text)))
    chans = re.findall(r"logos-small/sporttv-([0-9a-z\-]+?)-?rebrand\.svg", text)
    canals = re.findall(r'alt="Canal (\d+)"', text)
    print(f"      clocks {clocks:<5} distinct events {events:<5}")
    print(f"      channel logos  {dict((c, chans.count(c)) for c in sorted(set(chans)))}")
    print(f"      alt=Canal N    {dict((c, canals.count(c)) for c in sorted(set(canals)))}")


def dump_json_blocks(text: str) -> None:
    """The ld+json and any inline application/json — the clean source."""
    for kind in ("application/ld\\+json", 'application/json'):
        for m in re.finditer(
                rf'<script[^>]*type="{kind}"[^>]*>(.*?)</script>', text, re.S):
            body = m.group(1).strip()
            print(f"      [{kind}] {len(body)} bytes")
            try:
                data = json.loads(body)
            except Exception:                                  # noqa: BLE001
                print(f"          not valid JSON: {body[:160]}")
                continue
            def walk(node, depth=0, path=""):
                if depth > 3: return
                if isinstance(node, dict):
                    keys = list(node)[:14]
                    print(f"          {path or '.'}  keys={keys}")
                    for k in ("startDate", "endDate", "name", "@type",
                              "location", "broadcastOfEvent", "publication"):
                        if k in node:
                            v = node[k]
                            if not isinstance(v, (dict, list)):
                                print(f"              {k} = {str(v)[:90]}")
                    for k, v in list(node.items())[:6]:
                        if isinstance(v, (dict, list)):
                            walk(v, depth + 1, f"{path}.{k}")
                elif isinstance(node, list):
                    print(f"          {path}[] len={len(node)}")
                    if node: walk(node[0], depth + 1, f"{path}[0]")
            walk(data)


def main() -> int:
    session = requests.Session(); session.headers.update(HEAD)

    print("=" * 74)
    print("A LISTING THAT CARRIES EVERY COMPETITION")
    print("=" * 74)
    for path in ("/jogos", "/jogos/hoje", "/jogos/todos", "/diretos",
                 "/直", "/em-direto", "/guia/hoje", "/programacao"):
        r = get(session, BASE + path)
        if r is None: continue
        ok = r.status_code == 200 and "html" in r.headers.get("content-type","")
        print(f"\n  {path:<16} {r.status_code}  {len(r.text) if r.text else 0} bytes"
              f"  final={r.url[len(BASE):][:50]}")
        if ok:
            report(r.text, r.url)

    print()
    print("=" * 74)
    print("live-sitemap.xml — does it list the events themselves?")
    print("=" * 74)
    r = get(session, BASE + "/live-sitemap.xml")
    if r is not None and r.status_code == 200:
        locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
        print(f"  {len(locs)} url(s); first 15:")
        for loc in locs[:15]:
            print(f"      {loc[:110]}")

    print()
    print("=" * 74)
    print("ONE COMPETITION PAGE, WHOLE — the row shape and its JSON")
    print("=" * 74)
    url = (BASE + "/jogos/competicao/mg:competition:14y9s73xvl9b"
                  "/liga-portugal-betclic")
    r = get(session, url)
    if r is not None and r.status_code == 200:
        report(r.text, url)
        dump_json_blocks(r.text)
        print("\n      --- a whole row, tags stripped ---")
        for m in list(re.finditer(r'id="(mg:sportevent:[A-Za-z0-9]+)"', r.text))[:3]:
            a = max(0, m.start() - 1200); b = min(len(r.text), m.end() + 2200)
            flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", r.text[a:b]))
            print(f"      {m.group(1)}")
            print(f"          {flat[:700]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
