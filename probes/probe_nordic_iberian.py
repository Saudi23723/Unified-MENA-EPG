#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round two: does the Viaplay feed hold a DAY, and where is SPORT TV's?

Round one settled that content.viaplay.dk answers 200 with JSON and 468
instants in it, that vsport.dk and vsport.se do not resolve at all, and
that sporttv.pt's guessed schedule paths are 404. A feed answering 200
is not a guide, so this walks the Viaplay JSON and prints what is
actually in it — the blocks, and one broadcast whole — and asks SPORT
TV's own sitemap where its schedule lives rather than guessing again.
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


def viaplay(session) -> None:
    print("=" * 70)
    print("VIAPLAY DK — what is actually inside the feed")
    print("=" * 70)
    url = "https://content.viaplay.dk/pcdash-dk/sport"
    got = session.get(url, timeout=TIMEOUT)
    data = got.json()
    blocks = (data.get("_embedded") or {}).get("viaplay:blocks") or []
    print(f"  {len(blocks)} block(s) on the sport page")
    for block in blocks:
        title = block.get("title") or block.get("type") or "?"
        items = ((block.get("_embedded") or {}).get("viaplay:products")
                 or (block.get("_embedded") or {}).get("viaplay:blocks") or [])
        print(f"    - {str(title)[:46]:<46} {len(items)} item(s)"
              f"   type={block.get('type')}")
        for item in items[:1]:
            epg = item.get("epg") or {}
            content = item.get("content") or {}
            when = (item.get("system") or {}).get("availability") or {}
            print(f"        title   : {(content.get('title') or '')[:50]}")
            print(f"        start   : {epg.get('start') or when.get('start')}")
            print(f"        end     : {epg.get('end') or when.get('end')}")
            print(f"        channel : {epg.get('channel') or item.get('channel')}")
            print(f"        keys    : {sorted(item)[:12]}")
    # and the endpoints a schedule would live behind
    for tail in ("sport/today", "sport?sort=starttime", "channels",
                 "sport/live", "sport/kommende"):
        try:
            probe = session.get(f"https://content.viaplay.dk/pcdash-dk/{tail}",
                                timeout=TIMEOUT)
            print(f"  /{tail:<22} {probe.status_code}  {len(probe.text):>8} bytes")
        except Exception as exc:                              # noqa: BLE001
            print(f"  /{tail:<22} {type(exc).__name__}")


def sporttv(session) -> None:
    print()
    print("=" * 70)
    print("SPORT TV PT — where does its own sitemap say the schedule is")
    print("=" * 70)
    for path in ("robots.txt", "sitemap.xml"):
        try:
            got = session.get(f"https://www.sporttv.pt/{path}", timeout=TIMEOUT)
            print(f"  /{path}  {got.status_code}  {len(got.text)} bytes")
            if got.status_code == 200:
                for line in got.text.splitlines()[:25]:
                    if line.strip():
                        print(f"      {line.strip()[:100]}")
        except Exception as exc:                              # noqa: BLE001
            print(f"  /{path}  {type(exc).__name__}")
    # every link on the homepage whose text or href smells like a schedule
    try:
        home = session.get("https://www.sporttv.pt/", timeout=TIMEOUT).text
        wanted = re.compile(r"guia|grelha|programa|emiss|horario|horário|tv",
                            re.I)
        links = set()
        for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                                     home, re.S | re.I):
            flat = re.sub(r"<[^>]+>", " ", text)
            flat = re.sub(r"\s+", " ", flat).strip()
            if wanted.search(href) or wanted.search(flat):
                links.add((href[:70], flat[:40]))
        print(f"\n  {len(links)} link(s) on the homepage that look like a guide:")
        for href, text in sorted(links)[:25]:
            print(f"      {href:<70}  {text}")
    except Exception as exc:                                  # noqa: BLE001
        print(f"  homepage: {type(exc).__name__}")


def vsport(session) -> None:
    print()
    print("=" * 70)
    print("V SPORT — does the brand have a site at all")
    print("=" * 70)
    for url in ("https://vsport.se/", "https://www.vsport.dk/",
                "https://viaplay.dk/kanaler", "https://viaplay.dk/channels",
                "https://content.viaplay.dk/pcdash-dk/kanaler"):
        try:
            got = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            print(f"  {url:<46} {got.status_code}  {len(got.text):>8} bytes"
                  f"  -> {got.url[:50]}")
        except Exception as exc:                              # noqa: BLE001
            print(f"  {url:<46} {type(exc).__name__}")


def main() -> int:
    session = requests.Session()
    session.headers.update(HEAD)
    for step in (viaplay, sporttv, vsport):
        try:
            step(session)
        except Exception as exc:                              # noqa: BLE001
            print(f"  {step.__name__} failed: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
