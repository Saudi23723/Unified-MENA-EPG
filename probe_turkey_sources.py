#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 3: tvyayinakisi.com publishes schema.org BroadcastEvent JSON-LD on
every channel page, which is exactly what the generator needs. Two things
still to pin down before wiring it up:

  * the slug for beIN Sports 5 (the obvious one 404s)
  * how to reach days other than today

Runs on GitHub Actions; deleted once the generator is rewritten.
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
BASE = "https://www.tvyayinakisi.com"


def head(label):
    print(f"\n{'='*72}\n{label}\n{'='*72}")


def get(url):
    try:
        return requests.get(url, headers=H, timeout=30)
    except Exception as exc:
        print(f"  REQUEST FAILED {url}: {exc}")
        return None


def broadcasts(html: str):
    """Every BroadcastEvent in every ld+json block on the page."""
    out = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("@type") == "BroadcastEvent":
                    out.append(node)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return out


def summarise(label, html):
    evs = broadcasts(html)
    starts = sorted(e.get("startDate", "") for e in evs)
    days = sorted({s[:10] for s in starts if s})
    perf = sorted({(e.get("performer") or {}).get("name", "?") for e in evs})
    print(f"  {label:46} events={len(evs):4} days={days} performer={perf}")
    return evs


def find_bein5():
    head("1) hunting the beIN Sports 5 slug")
    for slug in (
        "bein-sports-5", "bein-sports-5-yayin-akisi", "bein-sport-5",
        "bein-sports-5-hd", "beinsports-5", "bein-sports-max-5",
    ):
        r = get(f"{BASE}/{slug}")
        if r is None:
            continue
        title = (re.search(r"<title>(.*?)</title>", r.text, re.S) or [None, "?"])[1].strip()
        print(f"  /{slug:28} status={r.status_code} title={title[:64]!r}")

    r = get(f"{BASE}/?s=beIN+SPORTS+5")
    if r is not None:
        print(f"\n  site search status={r.status_code}")
        links = sorted(set(re.findall(r'href="(https://www\.tvyayinakisi\.com/[^"]*bein[^"]*)"', r.text)))
        for link in links[:30]:
            print(f"    {link}")

    r = get(f"{BASE}/bein-sports-1-yayin-akisi/")
    if r is not None:
        print(f"\n  beIN links listed on the beIN SPORTS 1 page (status={r.status_code}):")
        links = sorted(set(re.findall(r'href="(https://www\.tvyayinakisi\.com/[^"]*bein[^"]*)"', r.text)))
        for link in links[:40]:
            print(f"    {link}")


def find_other_days():
    head("2) how to reach days other than today")
    canonical = f"{BASE}/bein-sports-1-yayin-akisi/"
    r = get(canonical)
    if r is None:
        return
    base_html = r.text
    summarise("canonical page (today)", base_html)

    # What day-navigation links does the page itself offer?
    print("\n  -- day-ish links on the page --")
    for link in sorted(set(re.findall(r'href="([^"]*(?:yarin|dun|hafta|tarih|gun|day)[^"]*)"', base_html, re.I)))[:25]:
        print(f"    {link}")

    print("\n  -- the admin-ajax call the page makes --")
    i = base_html.find("admin-ajax.php")
    if i > 0:
        print(base_html[max(0, i - 1500): i + 1500])

    print("\n  -- URL patterns --")
    for suffix in ("yarin/", "?tarih=2026-08-25", "?gun=1", "2/", "hafta/"):
        rr = get(canonical + suffix if not suffix.startswith("?") else canonical + suffix)
        if rr is None:
            continue
        label = f"{suffix:22} status={rr.status_code}"
        if rr.status_code == 200:
            summarise(label, rr.text)
        else:
            print(f"  {label}")


def check_all_channels():
    head("3) event counts for every reachable beIN slug")
    for slug in ("bein-sports-1", "bein-sports-2", "bein-sports-3", "bein-sports-4",
                 "bein-sports-max-1", "bein-sports-max-2", "bein-sports-haber"):
        r = get(f"{BASE}/{slug}")
        if r is None or r.status_code != 200:
            print(f"  {slug:20} status={r.status_code if r else 'ERR'}")
            continue
        evs = summarise(slug, r.text)
        for e in evs[:2]:
            print(f"      {e.get('startDate')} -> {e.get('endDate')}  {e.get('name', '')[:60]!r}")


def main():
    find_bein5()
    find_other_days()
    check_all_channels()


if __name__ == "__main__":
    main()
