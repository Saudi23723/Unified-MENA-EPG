#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only hunt for two Turkish gaps.

tabii: TRT's own schedule page carries a real EPG in its __NEXT_DATA__,
but names a single channel, "Tabii Spor". The current file claims ten.
This pulls that payload apart to see exactly what TRT publishes, and
looks elsewhere for tabii Spor 2..10.

beIN Türkiye: tvyayinakisi.com gives only the current day for every
channel but HABER, and refuses a date parameter. This tries the other
Turkish TV-guide sites to see whether any publishes a full week.

Changes nothing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import requests

IST = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "tr,en;q=0.8"}
T = (5, 25)
NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def walk(node, want, path="", out=None, depth=0):
    """Every dict that has all of `want` as keys, with where it was found."""
    out = [] if out is None else out
    if depth > 14:
        return out
    if isinstance(node, dict):
        if want <= set(node):
            out.append((path, node))
        for k, v in node.items():
            walk(v, want, f"{path}.{k}", out, depth + 1)
    elif isinstance(node, list):
        for i, v in enumerate(node[:60]):
            walk(v, want, f"{path}[{i}]", out, depth + 1)
    return out


def main():
    section("TRT __NEXT_DATA__ — what tabii Spor really publishes")
    try:
        r = requests.get("https://www.trtspor.com.tr/yayin-akisi/tabii-spor",
                         headers=H, timeout=T)
        blob = NEXT.search(r.text)
        payload = json.loads(blob.group(1))
        print(f"payload {len(blob.group(1))} chars", flush=True)

        chans = walk(payload, {"title", "slug"})
        named = {}
        for path, node in chans:
            title = str(node.get("title") or "")
            if re.search(r"tabii|trt spor", title, re.I):
                named.setdefault(title, path)
        print("channels named on the page:", flush=True)
        for t, p in named.items():
            print(f"  {t:24} at {p[:90]}", flush=True)

        epgs = walk(payload, {"date"})
        print(f"\n{len(epgs)} nodes carrying a 'date'", flush=True)
        for path, node in epgs[:4]:
            print(f"\n  {path[:100]}", flush=True)
            print(f"    keys={sorted(node)[:14]}", flush=True)
            print(f"    {json.dumps(node, ensure_ascii=False)[:900]}", flush=True)

        shows = walk(payload, {"startDate"}) or walk(payload, {"start"})
        print(f"\n{len(shows)} nodes carrying a start time; first three:", flush=True)
        for path, node in shows[:3]:
            print(f"  {path[:90]} -> "
                  f"{json.dumps(node, ensure_ascii=False)[:420]}", flush=True)
    except Exception as exc:
        print(f"FAILED: {exc}", flush=True)

    section("is there any source for tabii Spor 2..10?")
    for url in ("https://www.trtspor.com.tr/yayin-akisi/tabii-spor-2",
                "https://www.tvyayinakisi.com/tabii-spor-yayin-akisi/",
                "https://www.tvyayinakisi.com/tabii-yayin-akisi/",
                "https://www.canlitv.vin/tabii-spor",
                "https://tv.yandex.com.tr/",
                "https://www.digiturk.com.tr/yayin-akisi"):
        try:
            rr = requests.get(url, headers=H, timeout=T, allow_redirects=True)
            body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rr.text))
            print(f"  {url:56} -> {rr.status_code} {len(rr.text)}b", flush=True)
            if rr.status_code == 200:
                print(f"     {body[:150]}", flush=True)
        except Exception as exc:
            print(f"  {url:56} FAILED: {str(exc)[:90]}", flush=True)

    section("other Turkish TV guides — do any carry a full week for beIN?")
    tomorrow = (datetime.now(IST) + timedelta(days=2)).strftime("%Y-%m-%d")
    for url in ("https://www.tvyayinakisi.com/bein-sports-1-yayin-akisi/",
                "https://www.programtv.com.tr/bein-sports-1/",
                "https://www.canlitv.com/yayin-akisi/bein-sports-1",
                "https://www.tvyayinakislari.com/bein-sports-1",
                "https://tvyayinakisi.tv/bein-sports-1",
                "https://www.yayinakisi.com.tr/bein-sports-1",
                f"https://www.programtv.com.tr/bein-sports-1/?tarih={tomorrow}"):
        try:
            rr = requests.get(url, headers=H, timeout=T, allow_redirects=True)
            text = rr.text
            times = len(re.findall(r"\b([01]\d|2[0-3]):[0-5]\d\b", text))
            dates = sorted(set(re.findall(r"20\d{2}-\d{2}-\d{2}", text)))[:8]
            print(f"  {url:60} -> {rr.status_code} {len(text)}b "
                  f"{times} clock strings, dates={dates}", flush=True)
        except Exception as exc:
            print(f"  {url:60} FAILED: {str(exc)[:80]}", flush=True)


if __name__ == "__main__":
    main()
