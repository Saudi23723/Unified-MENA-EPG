#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: why does الأردن الرياضية find only one fixture in 24 days?

The Live badge rule on that channel is already right — it goes on every
real fixture and never on a studio show. The problem is upstream: over 24
days the guide holds 33 entries, 30 of them the same "الأردن الرياضية"
filler block, and exactly one badged match. Jordan's Pro League plays
every week, so fixtures are being missed, not mis-badged.

This checks each source the generator reads — JRTV, livefootballtv,
JFA, sport24 — to see which are alive and how many fixtures each yields,
and looks for a fixture list the channel does not currently read.
Changes nothing.
"""
from __future__ import annotations

import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def text_of(html_text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text or ""))


def get(url, **kw):
    try:
        return requests.get(url, headers=H, timeout=T, allow_redirects=True, **kw)
    except Exception as exc:
        print(f"  {url}\n    FAILED: {str(exc)[:120]}", flush=True)
        return None


def report(url, r, keywords=()):
    if r is None:
        return
    body = text_of(r.text)
    print(f"  {url}\n    -> {r.status_code} {len(r.text)}b  final={r.url}", flush=True)
    if r.status_code != 200:
        return
    print(f"    text: {body[:200]}", flush=True)
    times = re.findall(r"\b([01]?\d|2[0-3]):[0-5]\d\b", r.text)
    print(f"    {len(times)} clock strings", flush=True)
    for kw in keywords:
        n = len(re.findall(kw, r.text, re.I))
        if n:
            print(f"    /{kw}/ x{n}", flush=True)


def main():
    section("the four sources the generator already reads")
    report("https://www.jrtv.gov.jo/", get("https://www.jrtv.gov.jo/"),
           ("الأردن الرياضية", "رياضة", "مباراة"))
    report("https://www.livefootballtv.info/channel/jordan-sports",
           get("https://www.livefootballtv.info/channel/jordan-sports"),
           ("jordan", "vs", "faisaly", "wehdat"))
    report("https://jfa.jo/", get("https://jfa.jo/"), ("مباريات", "الدوري", "جدول"))
    report("https://www.sport24.rest/", get("https://www.sport24.rest/"))

    section("does JRTV publish a schedule page of its own?")
    for path in ("/ar/tv-guide", "/ar/schedule", "/tv-guide", "/ar/sport",
                 "/ar/channels/sport", "/ar/live", "/ar"):
        r = get(f"https://www.jrtv.gov.jo{path}")
        if r is not None:
            print(f"  {path:22} -> {r.status_code} {len(r.text)}b", flush=True)

    section("Jordan Pro League fixture lists worth reading")
    for url in ("https://jfa.jo/matches.php",
                "https://jfa.jo/tourn.php?id=1",
                "https://www.jfa.jo/ar/matches",
                "https://www.kooora.com/",
                "https://www.livefootballtv.info/country/jordan",
                "https://www.livefootballtv.info/"):
        r = get(url)
        if r is not None and r.status_code == 200:
            body = text_of(r.text)
            print(f"  {url}\n    -> 200 {len(r.text)}b  {body[:160]}", flush=True)
        elif r is not None:
            print(f"  {url}\n    -> {r.status_code}", flush=True)

    section("what livefootballtv actually lists for the channel")
    r = get("https://www.livefootballtv.info/channel/jordan-sports")
    if r is not None and r.status_code == 200:
        body = text_of(r.text)
        print(body[:3000], flush=True)


if __name__ == "__main__":
    main()
