#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Can Viaplay Denmark, V Sport and SPORT TV Portugal be read at all?

Asked before anything is built: a channel is only worth making if its
sources answer with a machine-readable day. So each candidate is fetched
once, with a hard timeout, and what it answers is PRINTED — the status,
the size, and then the three things that decide it:

    ld+json events      a schema.org Event/BroadcastEvent block
    <time> elements     a datetime attribute a parser can read
    ISO instants        a timestamp anywhere in the body

A page that says "football" a hundred times and carries none of these is
a page, not a guide. Counting a word is not finding a row.
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, ".")

import requests

TIMEOUT = 12
HEAD = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "en,da;q=0.8,pt;q=0.7"}

ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
TIME_EL = re.compile(r"<time[^>]*datetime=", re.I)
LDJSON = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
                    re.S | re.I)

TARGETS = [
    ("Viaplay DK — site",        "https://viaplay.dk/"),
    ("Viaplay DK — sport",       "https://viaplay.dk/sport"),
    ("Viaplay DK — content API", "https://content.viaplay.dk/pcdash-dk/sport"),
    ("Viaplay DK — schedule API",
     "https://content.viaplay.dk/pcdash-dk/sport/kalender"),
    ("V Sport DK",               "https://vsport.dk/"),
    ("V Sport SE",               "https://www.vsport.se/"),
    ("V Sport — tv guide",       "https://vsport.dk/tv-guide"),
    ("SPORT TV PT — site",       "https://www.sporttv.pt/"),
    ("SPORT TV PT — guia",       "https://www.sporttv.pt/guia-tv"),
    ("SPORT TV PT — programacao",
     "https://www.sporttv.pt/programacao"),
]


def count_ld_events(body: str) -> int:
    found = 0
    for block in LDJSON.findall(body):
        try:
            data = json.loads(block)
        except Exception:                                     # noqa: BLE001
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                kind = str(item.get("@type") or "")
                if "Event" in kind:
                    found += 1
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
    return found


def main() -> int:
    session = requests.Session()
    session.headers.update(HEAD)
    for name, url in TARGETS:
        try:
            got = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        except Exception as exc:                              # noqa: BLE001
            print(f"\n{name}\n  {url}\n  UNREACHABLE  "
                  f"{type(exc).__name__}: {str(exc)[:120]}")
            continue
        body = got.text or ""
        kind = got.headers.get("content-type", "")[:40]
        print(f"\n{name}\n  {url}")
        print(f"  {got.status_code}  {len(body):>8} bytes  {kind}")
        if got.status_code != 200 or not body:
            continue
        events = count_ld_events(body)
        times = len(TIME_EL.findall(body))
        stamps = ISO.findall(body)
        print(f"  ld+json Event blocks : {events}")
        print(f"  <time datetime=...>  : {times}")
        print(f"  ISO instants in body : {len(stamps)}"
              f"   {sorted(set(stamps))[:4]}")
        if kind.startswith("application/json"):
            try:
                data = got.json()
                keys = list(data)[:10] if isinstance(data, dict) else "list"
                print(f"  JSON top-level keys  : {keys}")
            except Exception:                                 # noqa: BLE001
                pass
        verdict = ("READABLE" if (events or times or len(stamps) > 5)
                   else "no machine-readable day here")
        print(f"  -> {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
