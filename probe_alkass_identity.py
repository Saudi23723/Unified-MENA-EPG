#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: beIN's own guide publishes Alkass 1 and Alkass 4 as nearly the
same schedule (71 of 87 rows identical), and Alkass 5 and Alkass 7 likewise
(76 of 78). The parse was verified faithful, so the duplication is in
beIN's data. This looks for a second source to check it against —
Alkass's own site and the epgshare Qatar feed — and prints the disputed
channels side by side. Changes nothing.
"""
from __future__ import annotations

import gzip
import html
import io
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

DOHA = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
BEIN = ("https://www.bein.com/en/epg-ajax-template/?action=epg_fetch"
        "&category=sports&cdate={d}&language=EN&loadindex=0&mins=00"
        "&offset=0&postid=25356&serviceidentity=bein.net")
T = (5, 20)

TOKEN = re.compile(r"(?P<logo>/\d{4}_[A-Za-z0-9_]+\.png)"
                   r"|(?P<row><li(?:\s[^>]*?)?>.*?</li>)", re.S | re.I)
ALKASS = re.compile(r"/\d{4}_Alkass_(\d+)\.png", re.I)
RANGE = re.compile(r"data-start='([\d\- :]+)'\s+data-end='([\d\- :]+)'")
TITLE = re.compile(r"<p class=title>(.*?)</p>", re.S)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def bein_day(d):
    out, cur = defaultdict(dict), None
    r = requests.get(BEIN.format(d=d), headers=H, timeout=T)
    for m in TOKEN.finditer(r.text):
        if m.group("logo"):
            hit = ALKASS.match(m.group("logo"))
            cur = int(hit.group(1)) if hit else None
            continue
        if cur is None:
            continue
        span, title = RANGE.search(m.group("row")), TITLE.search(m.group("row"))
        if span and title:
            out[cur][span.group(1)] = clean(title.group(1))
    return out


def try_get(url, **kw):
    try:
        r = requests.get(url, headers=H, timeout=T, allow_redirects=True, **kw)
        return r
    except Exception as exc:
        print(f"  {url} FAILED: {exc}", flush=True)
        return None


def main():
    today = datetime.now(DOHA).strftime("%Y-%m-%d")
    print(f"Doha today {today}", flush=True)

    section("beIN EN — the four disputed channels, today, side by side")
    try:
        day = bein_day(today)
        for pair in ((1, 4), (5, 7)):
            a, b = pair
            starts = sorted(set(day[a]) | set(day[b]))
            print(f"\n  time        Alkass {a:<34} Alkass {b}", flush=True)
            for s in starts:
                ta, tb = day[a].get(s, "—"), day[b].get(s, "—")
                flag = "" if ta == tb else "   <<< differs"
                print(f"  {s[11:16]}  {ta[:40]:<42}{tb[:40]}{flag}", flush=True)
    except Exception as exc:
        print(f"beIN failed: {exc}", flush=True)

    section("alkass.net — does it publish its own guide?")
    for url in ("https://www.alkass.net/",
                "https://www.alkass.net/ar",
                "https://www.alkass.net/sitemap.xml",
                "https://www.alkass.net/schedule",
                "https://www.alkass.net/epg",
                "https://www.alkass.net/api/schedule"):
        r = try_get(url)
        if r is None:
            continue
        print(f"  {url} -> {r.status_code} {len(r.text)}b final={r.url}", flush=True)
        if r.status_code != 200:
            continue
        hits = sorted({h for h in re.findall(r"href=['\"]([^'\"]+)['\"]", r.text)
                       if re.search(r"schedul|guide|epg|جدول|برامج|program", h, re.I)})[:15]
        print(f"    candidate links: {hits}", flush=True)
        print(f"    text: {clean(r.text)[:200]}", flush=True)

    section("epgshare01 Qatar feed — second opinion on Alkass")
    for name in ("QA1", "AR1"):
        url = f"https://epgshare01.online/epgshare01/epg_ripper_{name}.xml.gz"
        r = try_get(url, stream=True)
        if r is None or r.status_code != 200:
            if r is not None:
                print(f"  {url} -> {r.status_code}", flush=True)
            continue
        buf, cap = io.BytesIO(), 60 * 1024 * 1024
        for chunk in r.iter_content(1 << 16):
            buf.write(chunk)
            if buf.tell() > cap:
                print("  (capped)", flush=True)
                break
        try:
            root = ET.fromstring(gzip.decompress(buf.getvalue()))
        except Exception as exc:
            print(f"  {name}: unusable ({exc})", flush=True)
            continue
        ids = [c.get("id") for c in root.findall("channel")
               if re.search(r"alkass|kass", c.get("id") or "", re.I)]
        print(f"  {name}: {len(root.findall('channel'))} channels; Alkass ids={ids}",
              flush=True)
        per = defaultdict(dict)
        for p in root.findall("programme"):
            cid = p.get("channel")
            if cid in ids and p.get("start", "")[:8] == today.replace("-", ""):
                per[cid][p.get("start")] = (p.findtext("title") or "").strip()
        for cid in ids:
            rows = sorted(per[cid])
            print(f"\n    {cid}: {len(rows)} rows today", flush=True)
            for s in rows[:30]:
                print(f"      {s} {per[cid][s][:55]}", flush=True)
        break


if __name__ == "__main__":
    main()
