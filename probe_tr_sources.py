#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: can tabii Spor be given a real schedule?

Its current script does not read one. It scrapes match mentions out of
trtspor.com.tr news pages, which is why the file holds 83 programmes with
only 6 still in the future and three channels empty.

tvyayinakisi.com, the proven source for beIN Türkiye, has no tabii pages
at all (every slug 404s). But TRT's own broadcast-schedule page —
trtspor.com.tr/yayin-akisi/tabii-spor, the URL the script already names
and then ignores — answers 200 with 364KB. This maps what is inside it,
and tries the endpoints tabii's own player would call. Changes nothing.
"""
from __future__ import annotations

import json
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "tr,en;q=0.8"}
T = (5, 25)
URL = "https://www.trtspor.com.tr/yayin-akisi/tabii-spor"


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def text_of(html_text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text or ""))


def main():
    r = requests.get(URL, headers=H, timeout=T)
    t = r.text
    print(f"{URL} -> {r.status_code} {len(t)}b", flush=True)

    section("clock-like strings and what wraps them")
    hits = list(re.finditer(r"\b([01]\d|2[0-3]):[0-5]\d\b", t))
    print(f"{len(hits)} clock strings", flush=True)
    for m in hits[:4]:
        print(f"\n---- at {m.start()} ----", flush=True)
        print(t[max(0, m.start() - 900):m.start() + 700].replace("\n", " "), flush=True)

    section("tabii Spor channel names on the page")
    for m in list(re.finditer(r"[Tt]ab(?:i|İ|ı)i?\s*[Ss]por\s*\d{0,2}", t))[:25]:
        print(f"  {m.start():7} {text_of(t[max(0, m.start()-120):m.start()+160])[:170]}",
              flush=True)

    section("embedded JSON payloads")
    for m in re.finditer(r'<script[^>]*(?:id="__NEXT_DATA__"|type="application/(?:ld\+)?json")[^>]*>(.*?)</script>',
                         t, re.S):
        blob = m.group(1).strip()
        print(f"\n  script at {m.start()}, {len(blob)} chars", flush=True)
        try:
            payload = json.loads(blob)
        except Exception as exc:
            print(f"    unparsable: {exc}", flush=True)
            continue
        print(f"    {json.dumps(payload, ensure_ascii=False)[:1200]}", flush=True)

    section("classes and ids that look like a schedule")
    names = {}
    for m in re.finditer(r'(?:class|id)="([^"]{2,80})"', t):
        for token in m.group(1).split():
            if re.search(r"akis|yayin|program|schedule|epg|channel|kanal|saat|time|hour",
                         token, re.I):
                names[token] = names.get(token, 0) + 1
    for k, v in sorted(names.items(), key=lambda x: -x[1])[:35]:
        print(f"  {v:5}  {k}", flush=True)

    section("endpoints tabii's own player might expose")
    for url in ("https://www.tabii.com/watch/live/tabiispor?trackId=419561",
                "https://eu1-prod-direct.tabii.com/api/v1/channels",
                "https://www.tabii.com/api/v1/epg",
                "https://www.trtspor.com.tr/api/yayin-akisi/tabii-spor",
                "https://www.trtspor.com.tr/yayin-akisi/trt-spor"):
        try:
            rr = requests.get(url, headers=H, timeout=T, allow_redirects=True)
            print(f"\n  {url} -> {rr.status_code} {len(rr.text)}b", flush=True)
            print(f"    {text_of(rr.text)[:220]}", flush=True)
        except Exception as exc:
            print(f"  {url} FAILED: {exc}", flush=True)


if __name__ == "__main__":
    main()
