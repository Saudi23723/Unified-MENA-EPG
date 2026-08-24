#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 2: the first probe found two reachable Turkish sources. Work out
which one actually carries all eight beIN Sports Türkiye channels and what
its markup looks like, so the generator can be pointed at it.

Runs on GitHub Actions; deleted once the source is wired up.
"""
from __future__ import annotations

import json
import re

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)
H = {"User-Agent": UA, "Accept-Language": "tr,en;q=0.8"}


def head(label):
    print(f"\n{'='*72}\n{label}\n{'='*72}")


def get(url, **kw):
    try:
        return requests.get(url, headers=H, timeout=30, **kw)
    except Exception as exc:
        print(f"  REQUEST FAILED: {exc}")
        return None


# ------------------------------------------------------- beinsports.com.tr
def probe_official():
    head("1) beinsports.com.tr/yayin-akisi — structure")
    r = get("https://www.beinsports.com.tr/yayin-akisi")
    if r is None:
        return
    print(f"  status={r.status_code} len={len(r.text)}")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    print(f"  __NEXT_DATA__ present: {bool(m)}")
    if m:
        try:
            data = json.loads(m.group(1))
        except Exception as exc:
            print(f"  !! bad JSON: {exc}")
        else:
            props = data.get("props", {}).get("pageProps", {})
            print(f"  pageProps keys: {list(props)[:25]}")
            blob = json.dumps(props, ensure_ascii=False)
            print(f"  pageProps size: {len(blob)}")
            print(f"  mentions 'bein sports 1': {'bein sports 1' in blob.lower()}")
            print("  head:", blob[:1200])
            print(f"  buildId: {data.get('buildId')}")
    # any API hints
    for pat in (r'"[^"]*api[^"]*"', r"/api/[A-Za-z0-9_\-/]+"):
        hits = sorted(set(re.findall(pat, r.text)))[:15]
        print(f"  {pat} -> {hits}")


# ------------------------------------------------------- tvyayinakisi.com
SLUGS = [
    "bein-sports-1", "bein-sports-2", "bein-sports-3", "bein-sports-4",
    "bein-sports-5", "bein-sports-max-1", "bein-sports-max-2",
    "bein-sports-haber",
]


def probe_tvy():
    head("2) tvyayinakisi.com — which beIN slugs exist")
    for slug in SLUGS:
        r = get(f"https://www.tvyayinakisi.com/{slug}")
        if r is None:
            continue
        title = (re.search(r"<title>(.*?)</title>", r.text, re.S) or [None, "?"])[1]
        rows = len(re.findall(r'class="[^"]*akis[^"]*"', r.text))
        print(f"  {slug:20} status={r.status_code} len={len(r.text):7} rows~{rows:4} title={title.strip()[:60]!r}")

    head("3) tvyayinakisi.com — markup of bein-sports-1")
    r = get("https://www.tvyayinakisi.com/bein-sports-1")
    if r is None or r.status_code != 200:
        return
    t = r.text
    # time-looking anchors
    times = re.findall(r"\b([01]\d|2[0-3]):[0-5]\d\b", t)
    print(f"  HH:MM occurrences: {len(times)}")
    for kw in ("data-", "itemprop", "schedule", "yayin-akisi", "program", "json"):
        print(f"  contains {kw!r}: {t.lower().count(kw.lower())}")
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', t, re.S)
    print(f"  ld+json present: {bool(m)}")
    if m:
        print("  ld+json head:", m.group(1)[:800].replace("\n", " "))
    # dump the region around the first time string
    for probe in ("19:", "20:", "21:"):
        j = t.find(probe)
        if j > 0:
            print(f"\n  --- 1400 chars around first {probe!r} ---")
            print(t[max(0, j - 700): j + 700])
            break
    # look for an XHR the page uses
    for pat in (r'url\s*:\s*"([^"]+)"', r"fetch\(\s*[\"']([^\"']+)", r'ajax[^"\']*["\']([^"\']+)'):
        hits = sorted(set(re.findall(pat, t)))[:12]
        if hits:
            print(f"  {pat} -> {hits}")


def main():
    probe_official()
    probe_tvy()


if __name__ == "__main__":
    main()
