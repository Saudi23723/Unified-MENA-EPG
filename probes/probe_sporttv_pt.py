#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where is SPORT TV Portugal's schedule, and what is actually in a row?

Asked for outright: "Sport tv portogues ضيف جميع ال مباشر عندهم كمان
بالترتيب ... كل المباريات و ال events ال live او scheduled Live".

An earlier probe found sporttv.pt's GUESSED schedule paths 404 and went
no further. This one does not guess: it reads the sitemap and the
homepage for a link that looks like a guide, follows the best ones, and
then DUMPS WHAT IS IN THE PAGE — how many rows, what an hour looks like,
whether the grid is in the HTML at all or drawn in the browser, and
whether any JSON endpoint is handing it the data.

It commits nothing and publishes nothing. Nothing is written from this
until it has been read.
"""
from __future__ import annotations

import json
import re
import sys

import requests

TIMEOUT = 25
HEAD = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"}


def get(session, url):
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        return r
    except Exception as exc:                                   # noqa: BLE001
        print(f"    {url[:88]}  -> {type(exc).__name__}: {exc}")
        return None


def structure(text: str) -> None:
    """What shape is this page — a grid in the HTML, or an empty shell?"""
    print(f"      length            {len(text)} bytes")
    for label, pattern in (
            ("<time> elements   ", r"<time[^>]*>"),
            ("hh:mm in text     ", r">\s*([01]?\d|2[0-3]):[0-5]\d\s*<"),
            ("datetime= attrs   ", r'datetime="[^"]+"'),
            ("<tr> rows         ", r"<tr[\s>]"),
            ("__NEXT_DATA__     ", r"__NEXT_DATA__"),
            ("application/json  ", r'type="application/json"'),
            ("application/ld    ", r'application/ld\+json'),
            ("JSON-ish events   ", r'"startDate"|"startTime"|"start_time"'),
    ):
        found = re.findall(pattern, text, re.I)
        print(f"      {label}{len(found)}")
    # the first few clocks, in context, so the row shape is visible
    rows = re.findall(r".{90}\b([01]?\d|2[0-3]):[0-5]\d\b.{90}", text)
    hits = re.finditer(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", text)
    shown = 0
    for m in hits:
        a, b = max(0, m.start() - 110), min(len(text), m.end() + 110)
        chunk = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text[a:b])).strip()
        if len(chunk) > 30:
            print(f"      ...{chunk[:170]}")
            shown += 1
        if shown >= 6:
            break


def main() -> int:
    session = requests.Session()
    session.headers.update(HEAD)

    print("=" * 74)
    print("SPORT TV PT — sitemap and homepage, for the real schedule URL")
    print("=" * 74)

    candidates: set[str] = set()
    for path in ("robots.txt", "sitemap.xml", "sitemap_index.xml"):
        r = get(session, f"https://www.sporttv.pt/{path}")
        if r is None:
            continue
        print(f"  /{path}  {r.status_code}  {len(r.text)} bytes")
        if r.status_code == 200:
            for loc in re.findall(r"<loc>([^<]+)</loc>", r.text)[:40]:
                if re.search(r"guia|grelha|programa|emiss|hor[aá]rio|tv|jogos",
                             loc, re.I):
                    candidates.add(loc.strip())
            for sm in re.findall(r"Sitemap:\s*(\S+)", r.text, re.I):
                print(f"      sitemap -> {sm}")

    r = get(session, "https://www.sporttv.pt/")
    if r is not None:
        print(f"  homepage  {r.status_code}  {len(r.text)} bytes"
              f"  final={r.url}")
        want = re.compile(r"guia|grelha|programa|emiss|hor[aá]rio|jogos|diretos?"
                          r"|direto|agenda", re.I)
        for href in set(re.findall(r'href="([^"]+)"', r.text)):
            if want.search(href):
                full = href if href.startswith("http") else \
                    "https://www.sporttv.pt" + ("" if href.startswith("/") else "/") + href
                candidates.add(full)

    print(f"\n  {len(candidates)} candidate schedule URL(s)")
    for url in sorted(candidates)[:25]:
        print(f"      {url[:110]}")

    print()
    print("=" * 74)
    print("FOLLOWING EACH CANDIDATE — is the grid in the HTML?")
    print("=" * 74)
    for url in sorted(candidates)[:10]:
        r = get(session, url)
        if r is None:
            continue
        print(f"\n  {url[:100]}")
        print(f"      status {r.status_code}  type "
              f"{r.headers.get('content-type','?')[:40]}")
        if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
            structure(r.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
