#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: are the Türkiye guides actually being fed?

tabii's file holds 83 programmes across ten channels and only 6 of them
are still in the future — three channels are empty and the newest day is
today. Its script does not read a schedule at all: it scrapes match
mentions out of trtspor.com.tr news pages.

beIN Türkiye is thinner than it looks too: beIN SPORTS 1 has 33
programmes spread over eight days, about four a day, because
tvyayinakisi.com publishes only the current day for most channels and
epgshare fills the rest.

tvyayinakisi.com is already the proven source for beIN Türkiye and
publishes schema.org JSON-LD. This checks whether it also carries the
tabii Spor channels, whether it can be asked for a specific day, and what
the epgshare Turkish feed really holds for both. Changes nothing.
"""
from __future__ import annotations

import gzip
import io
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

IST = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "tr,en;q=0.8"}
T = (5, 25)
TVY = "https://www.tvyayinakisi.com"
LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def events_from(text):
    """Every BroadcastEvent on a tvyayinakisi page."""
    out = []
    for block in LD.findall(text or ""):
        try:
            payload = json.loads(block)
        except Exception:
            continue
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if node.get("@type") in ("BroadcastEvent", "Event") and node.get("startDate"):
                    out.append((node.get("startDate"), node.get("endDate"),
                                (node.get("name") or "")[:60]))
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    return out


def probe(slug, suffix=""):
    url = f"{TVY}/{slug}-yayin-akisi/{suffix}"
    try:
        r = requests.get(url, headers=H, timeout=T)
    except Exception as exc:
        return url, f"FAILED {exc}", []
    if r.status_code != 200:
        return url, f"HTTP {r.status_code}", []
    return url, f"200 {len(r.text)}b", events_from(r.text)


def main():
    today = datetime.now(IST)
    print(f"Istanbul now {today:%Y-%m-%d %H:%M}", flush=True)

    section("does tvyayinakisi carry the tabii Spor channels?")
    for n in range(1, 11):
        for slug in (f"tabii-spor-{n}", f"tabii-spor-{n}-hd"):
            url, status, evs = probe(slug)
            days = sorted({(e[0] or "")[:10] for e in evs})
            print(f"  {slug:18} {status:14} {len(evs):3} events  days={days}", flush=True)
            if evs:
                for e in evs[:3]:
                    print(f"       {e[0]} .. {e[1]}  {e[2]}", flush=True)
                break

    section("can tvyayinakisi be asked for a specific day?")
    for suffix in ("", "yarin/", "?tarih=" + (today + timedelta(days=1)).strftime("%Y-%m-%d"),
                   (today + timedelta(days=1)).strftime("%Y-%m-%d") + "/"):
        url, status, evs = probe("bein-sports-1", suffix)
        days = sorted({(e[0] or "")[:10] for e in evs})
        print(f"  {url:70} {status:14} {len(evs):3} events days={days}", flush=True)

    section("beIN Türkiye channels on tvyayinakisi today")
    for slug in ("bein-sports-1", "bein-sports-2", "bein-sports-3", "bein-sports-4",
                 "bein-sports-max-1", "bein-sports-max-2", "bein-sports-haber",
                 "bein-sports-5"):
        url, status, evs = probe(slug)
        days = sorted({(e[0] or "")[:10] for e in evs})
        print(f"  {slug:20} {status:14} {len(evs):3} events days={days}", flush=True)

    section("what the epgshare Turkish feed actually holds")
    try:
        r = requests.get("https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz",
                         headers=H, timeout=T, stream=True)
        buf = io.BytesIO()
        for chunk in r.iter_content(1 << 16):
            buf.write(chunk)
            if buf.tell() > 80 * 1024 * 1024:
                break
        root = ET.fromstring(gzip.decompress(buf.getvalue()))
        per = defaultdict(lambda: defaultdict(int))
        for p in root.findall("programme"):
            per[p.get("channel")][p.get("start", "")[:8]] += 1
        wanted = [c.get("id") for c in root.findall("channel")
                  if re.search(r"bein|tabii", c.get("id") or "", re.I)]
        print(f"  feed has {len(root.findall('channel'))} channels, "
              f"{len(root.findall('programme'))} programmes", flush=True)
        for cid in sorted(wanted):
            days = per[cid]
            print(f"  {cid:26} {sum(days.values()):4} programmes over "
                  f"{len(days)} days {sorted(days)[:3]}...", flush=True)
    except Exception as exc:
        print(f"  epgshare FAILED: {exc}", flush=True)

    section("tabii's own site and the URL its script points at")
    for url in ("https://www.trtspor.com.tr/yayin-akisi/tabii-spor",
                "https://www.tabii.com/tr/live",
                "https://www.tabii.com/tr/channels",
                "https://www.tvyayinakisi.com/kanallar/"):
        try:
            r = requests.get(url, headers=H, timeout=T, allow_redirects=True)
            body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
            print(f"\n  {url} -> {r.status_code} {len(r.text)}b", flush=True)
            print(f"    {body[:260]}", flush=True)
            hits = sorted({h for h in re.findall(r'href="([^"]+)"', r.text)
                           if re.search(r"tabii", h, re.I)})[:20]
            if hits:
                print(f"    tabii links: {hits}", flush=True)
        except Exception as exc:
            print(f"  {url} FAILED: {exc}", flush=True)


if __name__ == "__main__":
    main()
