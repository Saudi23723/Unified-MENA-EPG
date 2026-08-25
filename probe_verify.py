#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary verification of three doubts raised about the new guides:

  1. Is Alkass's schedule actually right? The feed stamps Qatari channels
     +0100, which is not Qatar's offset, so a two-hour shift is plausible.
     Compare the feed against bein.com's own Arabic guide for the same day.
  2. Is there an AD Sports Premium 1 on STARZPLAY, or only Premium 2?
  3. What are adsportsasia01/02 actually called?

Runs on GitHub Actions; deleted once answered.
"""
from __future__ import annotations

import gzip
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

UTC = timezone.utc
DOHA = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)
BEIN1 = "https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz"
API = "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"
PROG = re.compile(r'<programme start="([^"]+)" stop="([^"]+)" channel="([^"]+)"[^>]*>(.*?)</programme>', re.S)


def head(x):
    print(f"\n{'='*78}\n{x}\n{'='*78}", flush=True)


def parse_ts(v):
    m = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?$", v.strip())
    if not m:
        return None, None
    dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2)
    if off:
        sign = 1 if off[0] == "+" else -1
        dt = dt.replace(tzinfo=timezone(
            sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))))
    return dt, off


def probe_alkass_times():
    head("1) Alkass — what offsets does the feed use, and what does the day look like?")
    with requests.get(BEIN1, headers=H, timeout=T, stream=True) as r:
        buf = bytearray()
        for c in r.iter_content(65536):
            buf.extend(c)
    xml = gzip.decompress(bytes(buf)).decode("utf-8", "replace")

    offsets = defaultdict(int)
    rows = []
    for st, sp, ch, body in PROG.findall(xml):
        if ch.lower() != "alkass_1_ar.bein":
            continue
        dt, off = parse_ts(st)
        offsets[off] += 1
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S)
        rows.append((dt, m.group(1).strip() if m else "?", st))
    print(f"  Alkass_1_AR offsets seen: {dict(offsets)}")

    # what offsets does the rest of the file use?
    all_off = defaultdict(int)
    for st, _sp, ch, _b in PROG.findall(xml):
        _dt, off = parse_ts(st)
        all_off[off] += 1
    print(f"  offsets across the whole BEIN1 file: {dict(all_off)}")

    rows.sort(key=lambda r: r[0])
    today = datetime.now(DOHA).date()
    print(f"\n  -- Alkass 1, as the feed states it vs converted to Doha (today {today}) --")
    print(f"  {'raw':22} {'-> Doha':10} title")
    shown = 0
    for dt, title, raw in rows:
        doha = dt.astimezone(DOHA)
        if doha.date() != today:
            continue
        print(f"  {raw:22} {doha:%H:%M}      {title[:46]}")
        shown += 1
        if shown >= 26:
            break


def probe_bein_com():
    head("2) bein.com's own Arabic guide — cross-check Alkass times")
    today = datetime.now(DOHA).strftime("%Y-%m-%d")
    url = ("https://www.bein.com/ar/epg-ajax-template/?action=epg_fetch"
           f"&category=sports&cdate={today}&language=AR&loadindex=0&mins=00"
           "&offset=0&postid=25344&serviceidentity=bein.net")
    r = requests.get(url, headers=H, timeout=T)
    print(f"  status={r.status_code} len={len(r.text)}")
    if r.status_code != 200:
        return
    t = r.text
    # find the Alkass block and the times around it
    for needle in ("الكأس", "Alkass", "ALKASS"):
        i = t.find(needle)
        if i > 0:
            print(f"\n  found {needle!r} at offset {i}; 1200 chars around it:")
            print("  " + t[max(0, i - 300): i + 900].replace("\n", " "))
            break
    else:
        print("  no Alkass mention in the response")
    times = re.findall(r">\s*([012]?\d:[0-5]\d)\s*<", t)
    print(f"\n  distinct HH:MM values in the page: {len(set(times))} "
          f"(first 24: {sorted(set(times))[:24]})")


def probe_starz_names():
    head("3) STARZPLAY — every sport channel, EN and AR names side by side")
    now = int(datetime.now(UTC).timestamp())
    base = {"ts_start": now - 86400, "ts_end": now + 3 * 86400, "pg": 18,
            "category": "all", "limit": 40, "x-geo-country": "SA"}
    got = {}
    for lang in ("en", "ar"):
        seen = {}
        for page in range(1, 16):
            data = requests.get(API, headers=H, timeout=(5, 30),
                                params=dict(base, lang=lang, page=page)).json()
            rows = data.get("data") or []
            if not rows:
                break
            new = 0
            for c in rows:
                s = c.get("slug")
                if s and s not in seen:
                    seen[s] = c
                    new += 1
            if new == 0:
                break
        got[lang] = seen
        print(f"  lang={lang}: {len(seen)} channels")

    def sport(c):
        g = {str(x).lower() for x in (c.get("genres") or [])}
        return "sports" in g or str(c.get("category") or "").lower() == "sports"

    print(f"\n  {'slug':24} {'English':38} Arabic")
    for slug, c in sorted(got["en"].items()):
        if not sport(c):
            continue
        ar = got["ar"].get(slug, {}).get("title", "")
        print(f"  {slug:24} {str(c.get('title'))[:36]:38} {ar}")

    print("\n  -- anything mentioning premium / بريميوم / asia / آسيا anywhere --")
    for slug in sorted(set(got["en"]) | set(got["ar"])):
        en = str(got["en"].get(slug, {}).get("title", ""))
        ar = str(got["ar"].get(slug, {}).get("title", ""))
        if re.search(r"premium|بريميوم|asia|آسيا|اسيا", f"{slug} {en} {ar}", re.I):
            issport = sport(got["en"].get(slug) or got["ar"].get(slug) or {})
            print(f"    {slug:24} sport={issport}  EN={en[:34]:36} AR={ar}")


def main():
    for step in (probe_alkass_times, probe_bein_com, probe_starz_names):
        try:
            step()
        except Exception as exc:
            print(f"\n  !! {step.__name__}: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
