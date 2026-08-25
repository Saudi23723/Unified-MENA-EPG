#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: dig inside the first-party pages that actually answered.

Browser headers changed nothing for OSN, Al Arabiya, Al Mayadeen and STC
— still 403, several with a zero-byte body, and OSN's api/gateway/cdn
hosts do not resolve at all. Those are edge blocks, not user-agent
filtering.

What did answer: aljazeera.net/schedule (524KB, its جدول البث),
lbcgroup.tv/schedule (22KB), shahid.mbc.net (452KB), alaraby.tv and
mbc.net. Modern sites keep the schedule in an embedded payload or fetch
it from a backend, so this pulls each page apart looking for both: the
internal links that lead to a guide, and any JSON the page ships with.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import requests

T = (5, 25)
BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}
GUIDEISH = re.compile(
    r"schedule|tv-?guide|guide|programs?|barnamej|جدول|برامج|بث|akhbar|epg|grid",
    re.I)
JSON_SCRIPT = re.compile(
    r'<script[^>]*(?:id="__NEXT_DATA__"|id="__NUXT_DATA__"|'
    r'type="application/(?:ld\+)?json")[^>]*>(.*?)</script>', re.S)
API_HINT = re.compile(
    r'["\'](https?://[^"\']*(?:api|graphql|epg|schedule)[^"\']{0,80})["\']', re.I)


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def get(url):
    try:
        return requests.get(url, headers=BROWSER, timeout=T, allow_redirects=True)
    except Exception as exc:
        print(f"  {url} FAILED {str(exc)[:80]}", flush=True)
        return None


def dig(label, url):
    r = get(url)
    if r is None or r.status_code != 200:
        print(f"\n## {label} {url} -> {getattr(r, 'status_code', '-')}", flush=True)
        return
    t = r.text
    print(f"\n## {label} {url} -> 200 {len(t)}b", flush=True)

    links = sorted({urljoin(url, h) for h in re.findall(r'href="([^"#]+)"', t)
                    if GUIDEISH.search(h)})
    print(f"   guide-ish links ({len(links)}):", flush=True)
    for h in links[:22]:
        print(f"     {h}", flush=True)

    apis = sorted({a for a in API_HINT.findall(t)})[:22]
    if apis:
        print(f"   api-ish urls in the page ({len(apis)}):", flush=True)
        for a in apis:
            print(f"     {a[:130]}", flush=True)

    for m in JSON_SCRIPT.finditer(t):
        blob = m.group(1).strip()
        if len(blob) < 200:
            continue
        try:
            payload = json.loads(blob)
        except Exception:
            continue
        flat = json.dumps(payload, ensure_ascii=False)
        keys = re.findall(r'"(\w*(?:schedule|epg|program|channel|airing|slot)\w*)"',
                          flat, re.I)
        print(f"   embedded JSON {len(blob)}b, schedule-ish keys: "
              f"{sorted(set(k.lower() for k in keys))[:14]}", flush=True)
        print(f"     {flat[:320]}", flush=True)


def main():
    section("pages that answered, pulled apart")
    dig("Al Jazeera", "https://www.aljazeera.net/schedule")
    dig("LBC", "https://www.lbcgroup.tv/schedule")
    dig("Shahid", "https://shahid.mbc.net/ar")
    dig("MBC", "https://www.mbc.net/")
    dig("Al Araby", "https://www.alaraby.tv/")
    dig("Al Ekhbariya", "https://www.alekhbariya.net/")
    dig("Al Mamlaka", "https://www.almamlakatv.com/")
    dig("Sky News Arabia", "https://www.skynewsarabia.com/")
    dig("Dubai Media", "https://www.dmi.ae/")
    dig("Abu Dhabi", "https://www.adtv.ae/")
    dig("Saudi TV", "https://www.saudimediacity.sa/")
    dig("Syria TV", "https://www.rtv.gov.sy/")


if __name__ == "__main__":
    main()
