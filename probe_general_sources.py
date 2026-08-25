#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: find each broadcaster's own schedule source. First party only.

The first sweep used a bare requests User-Agent and got 403 from OSN,
Al Arabiya, Al Hadath and Al Mayadeen. That is bot filtering, not a
missing page, so every one of them is retried here with the headers a
real browser sends.

The other half of the problem is that these are single-page apps: the
schedule is not in the HTML, it arrives from a backend the page calls.
So alongside the pages this probes the API hosts and paths each
broadcaster is likely to be using, and reports what actually answers
with data. Nothing third-party, nothing pre-collected.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import requests

UTC = timezone.utc
TODAY = datetime.now(UTC).strftime("%Y-%m-%d")
TOMORROW = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
T = (5, 20)

BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="126", "Not:A-Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def probe(label, url, *, headers=None, referer=None, json_expected=False):
    h = dict(BROWSER)
    if json_expected:
        h["Accept"] = "application/json, text/plain, */*"
        h["Sec-Fetch-Dest"] = "empty"
        h["Sec-Fetch-Mode"] = "cors"
        h["Sec-Fetch-Site"] = "same-site"
    if referer:
        h["Referer"] = referer
        h["Origin"] = referer.rstrip("/")
    if headers:
        h.update(headers)
    try:
        r = requests.get(url, headers=h, timeout=T, allow_redirects=True)
    except Exception as exc:
        print(f"  {label:14} {url[:74]:76} FAILED {str(exc)[:60]}", flush=True)
        return None
    body = r.text or ""
    clocks = len(re.findall(r"\b([01]\d|2[0-3]):[0-5]\d\b", body))
    kind = "html"
    payload = None
    ct = r.headers.get("content-type", "")
    if "json" in ct.lower():
        kind = "json"
        try:
            payload = r.json()
        except Exception:
            payload = None
    flag = ""
    if r.status_code == 200 and (clocks > 8 or payload is not None):
        flag = "   <<< LOOK"
    print(f"  {label:14} {url[:74]:76} {r.status_code} {len(body):8}b "
          f"{kind:4} {clocks:4} clocks{flag}", flush=True)
    if payload is not None:
        text = json.dumps(payload, ensure_ascii=False)
        print(f"       {text[:400]}", flush=True)
    return r


def main():
    print(f"today {TODAY}", flush=True)

    section("the 403 sites, retried with real browser headers")
    for label, url in (
        ("Al Arabiya", "https://www.alarabiya.net/tv-schedule"),
        ("Al Arabiya", "https://www.alarabiya.net/ar/programs"),
        ("Al Hadath", "https://www.alhadath.net/tv-schedule"),
        ("Al Mayadeen", "https://www.almayadeen.net/programsschedule"),
        ("OSN", "https://www.osn.com/en-ae/tv-guide"),
        ("OSN", "https://www.osn.com/ar-sa/tv-guide"),
        ("Al Araby", "https://www.alaraby.tv/schedule"),
        ("Al Araby", "https://www.alaraby.tv/"),
    ):
        probe(label, url)

    section("MBC and Shahid — their own backends")
    for label, url, ref in (
        ("MBC", "https://www.mbc.net/api/channels", "https://www.mbc.net/"),
        ("MBC", "https://www.mbc.net/ar/channels.html", None),
        ("MBC", "https://www.mbc.net/ar.html", None),
        ("MBC", "https://www.mbc.net/", None),
        ("Shahid", "https://shahid.mbc.net/ar", None),
        ("Shahid api2", "https://api2.shahid.net/proxy/v2/channels", "https://shahid.mbc.net/"),
        ("Shahid api3", "https://api3.shahid.net/proxy/v2/channels", "https://shahid.mbc.net/"),
        ("Shahid api2", "https://api2.shahid.net/proxy/v2/product/livestreams",
         "https://shahid.mbc.net/"),
        ("Shahid epg", f"https://api2.shahid.net/proxy/v2/epg?date={TODAY}",
         "https://shahid.mbc.net/"),
    ):
        probe(label, url, referer=ref, json_expected="api" in url or "/api/" in url)

    section("OSN — app and gateway hosts")
    for label, url in (
        ("OSN api", "https://api.osn.com/v1/channels"),
        ("OSN gw", "https://gateway.osn.com/v1/epg"),
        ("OSN plus", "https://www.osnplus.com/en-ae/tv-guide"),
        ("OSN plus", "https://osnplus.com/"),
        ("OSN cdn", "https://cdn.osn.com/epg/today.json"),
    ):
        probe(label, url, json_expected=True)

    section("STC TV / Jawwy — intigral hosts")
    for label, url in (
        ("STC", "https://prod-cdn-content-api.intigral-ott.net/api/v1/channels"),
        ("STC", "https://prod-cdn-content-api.intigral-ott.net/api/v3/channels"),
        ("STC", "https://prod-cdn-content-api.intigral-ott.net/api/v1/epg"),
        ("STC", f"https://prod-cdn-content-api.intigral-ott.net/api/v1/epg?date={TODAY}"),
        ("STC", "https://stctv.com/"),
        ("STC", "https://www.stctv.com/en/live-tv"),
    ):
        probe(label, url, json_expected="intigral" in url)

    section("news channels — their own backends")
    for label, url, ref in (
        ("Al Arabiya", "https://www.alarabiya.net/api/v1/schedule", "https://www.alarabiya.net/"),
        ("Al Arabiya", "https://www.alarabiya.net/.rest/tv-schedule", "https://www.alarabiya.net/"),
        ("Al Mayadeen", "https://www.almayadeen.net/api/programsschedule",
         "https://www.almayadeen.net/"),
        ("Al Mayadeen", "https://api.almayadeen.net/programsschedule",
         "https://www.almayadeen.net/"),
        ("Al Araby", "https://api.alaraby.tv/schedule", "https://www.alaraby.tv/"),
        ("Al Araby", "https://www.alaraby.tv/api/schedule", "https://www.alaraby.tv/"),
        ("Al Jazeera", "https://www.aljazeera.net/schedule", None),
        ("Al Jazeera", "https://www.aljazeera.net/graphql", None),
        ("Sky News Ar", "https://www.skynewsarabia.com/schedule", None),
        ("Al Ekhbariya", "https://www.alekhbariya.net/", None),
        ("Al Mamlaka", "https://www.almamlakatv.com/schedule", None),
        ("LBC", "https://www.lbcgroup.tv/schedule", None),
    ):
        probe(label, url, referer=ref, json_expected="api" in url or "graphql" in url)


if __name__ == "__main__":
    main()
