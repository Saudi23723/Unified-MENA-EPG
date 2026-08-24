#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 4 (final): close the two gaps before rewriting the generator.

Round 3 showed tvyayinakisi.com carries beIN 1/2/3/MAX 1/MAX 2 as
schema.org BroadcastEvent JSON-LD, but the short slugs for beIN 4 and
HABER yielded nothing and beIN 5 has no page at all. This checks the
canonical URLs for those, and measures how far forward epgshare01's
Turkish feed reaches, since that is the obvious filler for whatever
tvyayinakisi cannot supply.

Runs on GitHub Actions; deleted once the generator is rewritten.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict

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
        return requests.get(url, headers=H, timeout=45)
    except Exception as exc:
        print(f"  REQUEST FAILED {url}: {exc}")
        return None


def broadcasts(html: str):
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


def canonical_pages():
    head("1) canonical /<slug>-yayin-akisi/ URLs for the channels that came back empty")
    for slug in ("bein-sports-4", "bein-sports-haber", "bein-sports-5",
                 "bein-sports-1", "bein-sports-max-1"):
        url = f"{BASE}/{slug}-yayin-akisi/"
        r = get(url)
        if r is None:
            continue
        evs = broadcasts(r.text)
        title = (re.search(r"<title>(.*?)</title>", r.text, re.S) or [None, "?"])[1].strip()
        print(f"  {slug:20} status={r.status_code} len={len(r.text):7} events={len(evs):3} "
              f"final_url={r.url}")
        print(f"      title={title[:70]!r}")
        for e in evs[:2]:
            print(f"      {e.get('startDate')} {e.get('name','')[:52]!r}")

    head("2) every channel tvyayinakisi lists (to see how beIN is actually named)")
    r = get(f"{BASE}/tvde-bugun-rehberi/")
    if r is not None and r.status_code == 200:
        links = sorted(set(re.findall(r'href="https://www\.tvyayinakisi\.com/([a-z0-9\-]+)-yayin-akisi/"', r.text)))
        print(f"  {len(links)} channel slugs found; beIN ones:")
        for s in links:
            if "bein" in s:
                print(f"    {s}")


def epgshare():
    head("3) epgshare01.online TR1 — reach and beIN coverage")
    r = get("https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz")
    if r is None or r.status_code != 200:
        print(f"  status={r.status_code if r else 'ERR'}")
        return
    xml = gzip.decompress(r.content).decode("utf-8", "replace")
    print(f"  decompressed={len(xml)} channels={xml.count('<channel ')} programmes={xml.count('<programme ')}")

    per = defaultdict(list)
    for m in re.finditer(r'<programme start="(\d{14})[^"]*"[^>]*channel="([^"]+)"', xml):
        per[m.group(2)].append(m.group(1))

    print("\n  -- every channel id containing 'ein' --")
    for cid in sorted(per):
        if "ein" in cid.lower():
            days = sorted({s[:8] for s in per[cid]})
            print(f"    {cid:36} n={len(per[cid]):4} days={days}")

    print("\n  -- ids with no programmes at all --")
    allids = set(re.findall(r'<channel id="([^"]+)"', xml))
    empty = sorted(i for i in allids - set(per) if "ein" in i.lower())
    print(f"    {empty}")

    print("\n  -- a sample programme block for a beIN channel --")
    for cid in sorted(per):
        if "ein" in cid.lower() and per[cid]:
            i = xml.find(f'channel="{cid}"')
            j = xml.rfind("<programme", 0, i)
            print(xml[j: j + 700])
            break


def main():
    canonical_pages()
    epgshare()


if __name__ == "__main__":
    main()
