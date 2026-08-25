#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe for three new guides: Alkass (QA), STARZPLAY sport,
and whatever sports channels STC TV publishes.

Runs on GitHub Actions; deleted once the sources are settled.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

import requests

UTC = timezone.utc
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"}
ARABIC = re.compile(r"[؀-ۿ]")


def head(x):
    print(f"\n{'='*76}\n{x}\n{'='*76}")


def get(url, **kw):
    try:
        return requests.get(url, headers=H, timeout=40, **kw)
    except Exception as exc:
        print(f"  FAILED {url[:70]}: {exc}")
        return None


def brief(label, r, n=200):
    if r is None:
        return
    print(f"  {label:52} status={r.status_code} len={len(r.content)} "
          f"ctype={(r.headers.get('content-type') or '')[:28]}")
    if r.status_code != 200:
        print(f"      {r.text[:n]}".replace("\n", " "))


# ------------------------------------------------------------------ Alkass
def probe_alkass_official():
    head("1) alkass.net — the broadcaster's own site")
    for url in (
        "https://alkass.net/",
        "https://www.alkass.net/",
        "https://alkass.net/schedule",
        "https://alkass.net/epg",
        "https://alkass.net/ar/schedule",
        "https://alkass.net/api/schedule",
    ):
        r = get(url)
        brief(url, r)
        if r is not None and r.status_code == 200 and "html" in (r.headers.get("content-type") or ""):
            t = r.text
            print(f"      __NEXT_DATA__={bool(re.search('__NEXT_DATA__', t))} "
                  f"ld+json={len(re.findall(r'application/ld.json', t))} "
                  f"HH:MM={len(re.findall(r'[012]?[0-9]:[0-5][0-9]', t))} "
                  f"arabic={bool(ARABIC.search(t))}")
            for pat in (r'/api/[A-Za-z0-9_\-/]+', r'wp-json/[A-Za-z0-9_\-/]+'):
                hits = sorted(set(re.findall(pat, t)))[:8]
                if hits:
                    print(f"      {pat} -> {hits}")


def probe_bein_com_alkass():
    head("2) bein.com Arabic EPG ajax — Alkass sits on ids 33-40 there")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    url = ("https://www.bein.com/ar/epg-ajax-template/?action=epg_fetch"
           f"&category=sports&cdate={today}&language=AR&loadindex=0&mins=00"
           "&offset=0&postid=25344&serviceidentity=bein.net")
    r = get(url)
    brief("bein.com ar epg_fetch (category=sports)", r)
    if r is not None and r.status_code == 200:
        t = r.text
        print(f"      arabic={bool(ARABIC.search(t))}  len={len(t)}")
        ids = Counter(re.findall(r'data-channel[^=]*="(\d+)"', t))
        print(f"      data-channel ids: {dict(list(ids.items())[:20])}")
        for cls in ("epg-item", "epg-channel", "programme", "epg_time", "epg-title"):
            print(f"      class {cls!r}: {t.count(cls)}")
        print("      head:", t[:400].replace("\n", " "))


def probe_epgshare_alkass():
    head("3) epgshare01 BEIN1 — Alkass coverage and reach")
    r = get("https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz")
    if r is None or r.status_code != 200:
        brief("epgshare BEIN1", r)
        return
    xml = gzip.decompress(r.content).decode("utf-8", "replace")
    print(f"  decompressed={len(xml)} channels={xml.count('<channel ')} "
          f"programmes={xml.count('<programme ')}")
    per = defaultdict(list)
    for m in re.finditer(r'<programme start="(\d{8})[^"]*"[^>]*channel="([^"]+)"', xml):
        per[m.group(2)].append(m.group(1))
    print("\n  -- every channel id mentioning Alkass --")
    for cid in sorted(per):
        if "alkass" in cid.lower():
            print(f"    {cid:34} n={len(per[cid]):4} days={sorted(set(per[cid]))}")
    empty = sorted(c for c in re.findall(r'<channel id="([^"]+)"', xml)
                   if "alkass" in c.lower() and c not in per)
    print(f"  Alkass ids with NO programmes: {empty}")
    # sample
    for cid in sorted(per):
        if "alkass" in cid.lower() and "_AR" in cid:
            i = xml.find(f'channel="{cid}"')
            j = xml.rfind("<programme", 0, i)
            print("\n  sample block:\n", xml[j:j + 460])
            break


# --------------------------------------------------------------- STARZPLAY
def probe_starzplay():
    head("4) STARZPLAY web-EPG API — still alive? which sport channels?")
    now = int(datetime.now(UTC).timestamp())
    api = "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"
    params = {
        "ts_start": now - 86400, "ts_end": now + 3 * 86400,
        "lang": "ar", "pg": 18, "category": "all", "limit": 40,
        "x-geo-country": "SA", "page": 1,
    }
    r = get(api, params=params)
    brief("starzplay page=1", r)
    if r is None or r.status_code != 200:
        return
    try:
        data = r.json()
    except Exception as exc:
        print(f"   not JSON: {exc}")
        return
    print(f"   top-level keys: {list(data)[:12]}")
    chans = data.get("channels") or data.get("data") or []
    if isinstance(chans, dict):
        chans = list(chans.values())
    print(f"   channels on page 1: {len(chans)}")
    for c in chans:
        if not isinstance(c, dict):
            continue
        hay = f"{c.get('title')} {c.get('slug')} {c.get('categories')}".lower()
        mark = "  <-- SPORT" if "sport" in hay else ""
        print(f"     slug={str(c.get('slug'))[:30]:32} title={str(c.get('title'))[:34]:36} "
              f"events={len(c.get('events') or [])}{mark}")
    if chans and isinstance(chans[0], dict):
        print(f"\n   CHANNEL KEYS: {sorted(chans[0].keys())}")
        evs = chans[0].get("events") or []
        if evs:
            print(f"   EVENT KEYS: {sorted(evs[0].keys())}")
            print(f"   sample event: {json.dumps(evs[0], ensure_ascii=False)[:600]}")


# ------------------------------------------------------------------ STC TV
def probe_stc():
    head("5) STC TV — is there any public schedule at all?")
    for url in (
        "https://www.stctv.com/",
        "https://stctv.com/",
        "https://www.stctv.com/ar",
        "https://api.stctv.com/",
        "https://www.jawwy.tv/",
        "https://shahid.mbc.net/",
    ):
        brief(url, get(url))
    print("\n  -- Saudi sport feeds on epgshare, for comparison --")
    for tag in ("SA1", "AR1", "QA1"):
        r = get(f"https://epgshare01.online/epgshare01/epg_ripper_{tag}.xml.gz")
        if r is None:
            continue
        if r.status_code != 200:
            print(f"    {tag}: status={r.status_code}")
            continue
        try:
            xml = gzip.decompress(r.content).decode("utf-8", "replace")
        except Exception as exc:
            print(f"    {tag}: gunzip failed {exc}")
            continue
        ids = re.findall(r'<channel id="([^"]+)"', xml)
        hits = [i for i in ids if re.search(r"ssc|stc|sport|alkass|kass", i, re.I)]
        print(f"    {tag}: channels={len(ids)} programmes={xml.count('<programme ')} "
              f"sport-ish={len(hits)}")
        for i in hits[:22]:
            n = xml.count(f'channel="{i}"')
            print(f"       {i:40} n={n}")


def main():
    probe_alkass_official()
    probe_bein_com_alkass()
    probe_epgshare_alkass()
    probe_starzplay()
    probe_stc()


if __name__ == "__main__":
    main()
