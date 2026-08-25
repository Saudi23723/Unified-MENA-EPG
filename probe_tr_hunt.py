#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: pin down the two things the last hunt turned up.

tvyayinakisi.com titles its pages "Yayın Akışı: Bugün | Yarın | Haftalık",
so a weekly view exists — the guess /yarin/ 404'd, but the real links are
on the page. If the weekly page carries a week, beIN Türkiye stops being
one day of guide plus epgshare filler. The same site also has a
tabii-spor page (the earlier hunt only tried tabii-spor-1..10, which all
404), which would give tabii the same proven JSON-LD source.

TRT's own payload holds .rows[5].content.epg[] — one entry per date, each
with tvChannels[] carrying past/current/upcoming. This looks inside one
programme object to learn what its time fields are called.

Changes nothing.
"""
from __future__ import annotations

import json
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "tr,en;q=0.8"}
T = (5, 25)
TVY = "https://www.tvyayinakisi.com"
NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def events(text):
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
                                (node.get("name") or "")[:70]))
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    return out


def main():
    section("the real Bugün / Yarın / Haftalık links")
    r = requests.get(f"{TVY}/bein-sports-1-yayin-akisi/", headers=H, timeout=T)
    t = r.text
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{2,20})\s*</a>', t):
        if re.search(r"bugün|bugun|yarın|yarin|haftalık|haftalik", m.group(2), re.I):
            print(f"  {m.group(2).strip():12} -> {m.group(1)}", flush=True)

    section("how much does each view carry?")
    for slug in ("bein-sports-1", "bein-sports-2", "bein-sports-3", "bein-sports-4",
                 "bein-sports-max-1", "bein-sports-max-2", "bein-sports-haber",
                 "tabii-spor"):
        for view in ("", "haftalik/", "yarin/", "haftalik-yayin-akisi/"):
            url = f"{TVY}/{slug}-yayin-akisi/{view}"
            try:
                rr = requests.get(url, headers=H, timeout=T)
            except Exception as exc:
                print(f"  {url:62} FAILED {str(exc)[:50]}", flush=True)
                continue
            if rr.status_code != 200:
                print(f"  {url:62} {rr.status_code}", flush=True)
                continue
            evs = events(rr.text)
            days = sorted({(e[0] or "")[:10] for e in evs})
            print(f"  {url:62} 200  {len(evs):4} events  days={days}", flush=True)
            if view == "" and slug == "tabii-spor" and evs:
                for e in evs[:6]:
                    print(f"        {e[0]} .. {e[1]}  {e[2]}", flush=True)

    section("what a TRT programme object looks like")
    try:
        rr = requests.get("https://www.trtspor.com.tr/yayin-akisi/tabii-spor",
                          headers=H, timeout=T)
        payload = json.loads(NEXT.search(rr.text).group(1))
        epg = payload["props"]["pageProps"]["data"]["rows"][5]["content"]["epg"]
        print(f"epg has {len(epg)} dates: {[d.get('date') for d in epg]}", flush=True)
        for day in epg[:1]:
            for ch in day.get("tvChannels", []):
                shows = (ch.get("upcoming") or []) + (ch.get("past") or [])
                print(f"\n  {ch.get('title')} (id {ch.get('id')}): "
                      f"past={len(ch.get('past') or [])} "
                      f"upcoming={len(ch.get('upcoming') or [])} "
                      f"current={bool(ch.get('current'))}", flush=True)
                if shows:
                    print(f"    keys: {sorted(shows[0])}", flush=True)
                    print(f"    {json.dumps(shows[0], ensure_ascii=False)[:700]}",
                          flush=True)
        # how many shows per channel across every date
        print("\n  totals per channel across all dates:", flush=True)
        tally = {}
        for day in epg:
            for ch in day.get("tvChannels", []):
                n = len(ch.get("past") or []) + len(ch.get("upcoming") or [])
                tally[ch.get("title")] = tally.get(ch.get("title"), 0) + n
        for k, v in tally.items():
            print(f"    {k:20} {v}", flush=True)
    except Exception as exc:
        print(f"FAILED: {exc}", flush=True)


if __name__ == "__main__":
    main()
