#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where is RMC Sport's schedule, and what is in a row?

Asked for beside Sport TV Portugal: "او اعملهم قناة لحالهم / مع RMC
france" — so the two broadcasters are to share a channel of their own,
the way the Turkish grid got one.

RMC Sport has lived at more than one address (rmcsport.bfmtv.com, and
rmcbfmplay for the streaming side), so nothing here is guessed: each
host is asked for its robots and sitemap, its homepage links are read
for anything that looks like a guide, and every candidate is followed
and DUMPED — how many clocks, whether they are programmes or an hour
ruler, whether a grid is in the HTML at all or drawn in the browser,
and whether a JSON endpoint is feeding it.

That last question is the one that matters. Sport TV's own /guia is
1.7MB of HTML holding twenty-six clocks, and all twenty-six are the
hour ruler — a page like that cannot be read at any effort, and knowing
so early is what stops a reader being written against it.

It commits nothing and publishes nothing.
"""
from __future__ import annotations

import re
import sys

import requests

TIMEOUT = 25
HEAD = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}

# RMC BFM Play REDIRECTS to rmcplus.fr — measured, not assumed: its
# homepage answers 200 and lands on https://www.rmcplus.fr/. The brand
# moved, and the first round chased 483 candidates on the old host that
# were every one of them a VOD catalogue page — documentaries, fiction,
# the weather — carrying "Diffusé le 09/09/2026", a broadcast already
# gone. None of that is a live sports guide.
#
# So the new host is asked directly, and the paths a French broadcaster
# actually uses for one: le direct, le guide, la grille, les chaînes.
HOSTS = ("https://www.rmcplus.fr", "https://rmcsport.bfmtv.com",
         "https://www.rmcsport.fr")

# Tried outright on the new host, because a link list is a poor way to
# find a page that may only be reachable from an app.
DIRECT = ("/direct", "/en-direct", "/live", "/sport", "/sports",
          "/guide-tv", "/guide", "/grille-tv", "/grille", "/chaines",
          "/programme-tv", "/programmes", "/epg", "/tv")

WANTED = re.compile(r"guide|grille|programme|programmation|direct|live"
                    r"|diffusion|horaire|agenda|tv", re.I)


def get(session, url):
    try:
        return session.get(url, timeout=TIMEOUT, allow_redirects=True)
    except Exception as exc:                                   # noqa: BLE001
        print(f"      {url[:88]} -> {type(exc).__name__}")
        return None


def shape(text: str) -> None:
    print(f"        length          {len(text)} bytes")
    clocks = re.findall(r"\b(?:[01]?\d|2[0-3])[:h][0-5]\d\b", text)
    print(f"        clocks          {len(clocks)}")
    for label, pat in (("<time>        ", r"<time[^>]*>"),
                       ("datetime=     ", r'datetime="[^"]+"'),
                       ("<tr>          ", r"<tr[\s>]"),
                       ("__NEXT_DATA__ ", r"__NEXT_DATA__"),
                       ("ld+json       ", r'application/ld\+json'),
                       ("startDate-ish ", r'"startDate"|"startTime"|"start_time"|"debut"')):
        print(f"        {label}  {len(re.findall(pat, text, re.I))}")
    # is the hour column just a ruler? a ruler is 00:00,01:00,... on the hour
    on_hour = sum(1 for c in clocks if c.endswith(("00", "h00")))
    print(f"        of those, on the hour: {on_hour}"
          f"  ({'looks like a RULER' if clocks and on_hour/len(clocks) > 0.8 else 'looks like real rows'})")
    shown = 0
    for m in re.finditer(r"\b(?:[01]?\d|2[0-3])[:h][0-5]\d\b", text):
        a, b = max(0, m.start() - 120), min(len(text), m.end() + 120)
        flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", text[a:b])).strip()
        if len(flat) > 40:
            print(f"        ...{flat[:180]}")
            shown += 1
        if shown >= 5:
            break


def main() -> int:
    session = requests.Session(); session.headers.update(HEAD)
    candidates: set[str] = set()

    for host in HOSTS:
        print("=" * 74)
        print(host)
        print("=" * 74)
        r = get(session, host + "/")
        if r is None:
            continue
        print(f"  homepage {r.status_code}  {len(r.text)} bytes  final={r.url[:60]}")
        if r.status_code != 200:
            continue
        for href in set(re.findall(r'href="([^"]+)"', r.text)):
            if WANTED.search(href):
                full = href if href.startswith("http") else \
                    host + ("" if href.startswith("/") else "/") + href
                if full.startswith(host):
                    candidates.add(full)
        for path in ("robots.txt", "sitemap.xml"):
            s = get(session, f"{host}/{path}")
            if s is not None and s.status_code == 200:
                print(f"  /{path}  200  {len(s.text)} bytes")
                for sm in re.findall(r"Sitemap:\s*(\S+)", s.text, re.I)[:6]:
                    print(f"      sitemap -> {sm}")
                for loc in re.findall(r"<loc>([^<]+)</loc>", s.text)[:30]:
                    if WANTED.search(loc):
                        candidates.add(loc.strip())

    print()
    print("=" * 74)
    print("THE PATHS A FRENCH BROADCASTER USES FOR A LIVE GUIDE")
    print("=" * 74)
    for path in DIRECT:
        r = get(session, "https://www.rmcplus.fr" + path)
        if r is None:
            continue
        kind = r.headers.get("content-type", "?")[:30]
        print(f"\n  {path:<16} {r.status_code}  {len(r.text or ''):>8} bytes"
              f"  {kind}  final={r.url[-44:]}")
        if r.status_code == 200 and "html" in kind:
            shape(r.text)

    print()
    print("=" * 74)
    print(f"{len(candidates)} candidate(s) — following the most likely")
    print("=" * 74)
    # A CATALOGUE PAGE IS NOT A GUIDE. /programme/<slug> and
    # /s-programme/<slug> are the VOD catalogue — one show each, with
    # the date it was last broadcast — and the first round followed
    # eight of them and learned nothing. They are skipped by shape.
    catalogue = re.compile(r"/s?-?programme/[^/]+$", re.I)
    ranked = sorted((u for u in candidates if not catalogue.search(u)),
                    key=lambda u: (
        0 if re.search(r"direct|guide|grille|chaine", u, re.I) else 1, len(u)))
    print(f"  ({len(candidates) - len(ranked)} catalogue page(s) skipped)")
    for url in ranked[:10]:
        r = get(session, url)
        if r is None:
            continue
        print(f"\n  {url[:104]}")
        print(f"      {r.status_code}  {r.headers.get('content-type','?')[:40]}")
        if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
            shape(r.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
