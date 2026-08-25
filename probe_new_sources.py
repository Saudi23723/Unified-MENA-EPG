#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 2 — the sources are settled, now design against the real data.

Alkass comes from epgshare01's BEIN1 feed (channels 1-8, Arabic, four days
ahead, already XMLTV with Arabic titles and categories). STARZPLAY comes
from its own web-EPG API. What is still unknown is how to tell a live match
from a studio show on either, and whether a countdown filler has any gaps
to fill.

Runs on GitHub Actions; deleted once the generators are written.
"""
from __future__ import annotations

import gzip
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import requests

UTC = timezone.utc
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"}
TIMEOUT = (5, 15)
BEIN1 = "https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz"


def head(x):
    print(f"\n{'='*76}\n{x}\n{'='*76}", flush=True)


def fetch_gz(url, cap=60_000_000):
    try:
        with requests.get(url, headers=H, timeout=TIMEOUT, stream=True) as r:
            if r.status_code != 200:
                print(f"  status={r.status_code}", flush=True)
                return None
            buf = bytearray()
            for chunk in r.iter_content(65536):
                buf.extend(chunk)
                if len(buf) > cap:
                    return None
        return gzip.decompress(bytes(buf)).decode("utf-8", "replace")
    except Exception as exc:
        print(f"  {type(exc).__name__}: {str(exc)[:100]}", flush=True)
        return None


PROG_RE = re.compile(
    r'<programme start="([^"]+)" stop="([^"]+)" channel="([^"]+)"[^>]*>(.*?)</programme>',
    re.S)


def tag(block, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
    return (m.group(1).strip() if m else "")


def parse_ts(v):
    m = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?$", v.strip())
    if not m:
        return None
    dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2)
    if off:
        sign = 1 if off[0] == "+" else -1
        dt = dt.replace(tzinfo=timezone(
            sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))))
    else:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def probe_alkass_shape():
    head("1) Alkass Arabic data — categories, live markers, and gaps")
    xml = fetch_gz(BEIN1)
    if xml is None:
        return
    rows = defaultdict(list)
    for st, sp, ch, body in PROG_RE.findall(xml):
        if not ch.lower().startswith("alkass") or "_ar" not in ch.lower():
            continue
        a, b = parse_ts(st), parse_ts(sp)
        if not a or not b:
            continue
        rows[ch].append({"start": a, "stop": b, "title": tag(body, "title"),
                         "sub": tag(body, "sub-title"), "cat": tag(body, "category"),
                         "desc": tag(body, "desc")})

    print(f"  Arabic Alkass channels: {sorted(rows)}")
    allr = [r for v in rows.values() for r in v]
    print(f"  total programmes: {len(allr)}")

    print("\n  -- every category present --")
    for k, v in Counter(r["cat"] for r in allr).most_common():
        print(f"    {v:5}  {k!r}")

    print("\n  -- does anything mark a live broadcast? --")
    for kw in ("مباشر", "مباشرة", "LIVE", "Live", "بث حي", "اعادة", "إعادة", "ملخص"):
        n = sum(1 for r in allr if kw in r["title"] or kw in r["sub"] or kw in r["desc"])
        print(f"    {kw:10} -> {n}")

    print("\n  -- descriptions present? --")
    print(f"    with desc: {sum(1 for r in allr if r['desc'])}/{len(allr)}")
    print(f"    sub-title differs from title: "
          f"{sum(1 for r in allr if r['sub'] and r['sub'] != r['title'])}/{len(allr)}")

    print("\n  -- 20 sample titles --")
    for r in allr[:20]:
        print(f"    {r['start']:%m-%d %H:%M}->{r['stop']:%H:%M} [{r['cat']}] {r['title'][:52]}")

    print("\n  -- gap coverage per channel (does a countdown have anywhere to go?) --")
    for ch in sorted(rows):
        evs = sorted(rows[ch], key=lambda r: r["start"])
        gaps = []
        for i in range(1, len(evs)):
            g = (evs[i]["start"] - evs[i - 1]["stop"]).total_seconds() / 60
            if g > 1:
                gaps.append(g)
        span = (evs[-1]["stop"] - evs[0]["start"]).total_seconds() / 3600 if evs else 0
        print(f"    {ch:22} n={len(evs):3} span={span:6.1f}h gaps>1min={len(gaps):3} "
              f"total_gap={sum(gaps):7.0f}min overlaps="
              f"{sum(1 for i in range(1, len(evs)) if evs[i]['start'] < evs[i-1]['stop'])}")


def probe_starzplay_status():
    head("2) STARZPLAY — what does event.status hold, and is there a live marker?")
    now = int(datetime.now(UTC).timestamp())
    api = "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"
    try:
        r = requests.get(api, headers=H, timeout=(5, 30), params={
            "ts_start": now - 86400, "ts_end": now + 3 * 86400, "lang": "ar",
            "pg": 18, "category": "all", "limit": 40, "x-geo-country": "SA", "page": 1})
        data = r.json()
    except Exception as exc:
        print(f"  FAILED {type(exc).__name__}: {str(exc)[:100]}", flush=True)
        return
    want = {"starzplaysports1", "starzplaysports2", "starzplaysport1"}
    for ch in data.get("data") or []:
        if not isinstance(ch, dict) or ch.get("slug") not in want:
            continue
        evs = ch.get("events") or []
        print(f"\n  {ch.get('slug')} — {ch.get('title')}  events={len(evs)}")
        print(f"    category={ch.get('category')!r} genres={ch.get('genres')}")
        imgs = ch.get("images") or []
        print(f"    images: {[(i.get('type'), (i.get('url') or '')[:56]) for i in imgs][:3]}")
        print(f"    status values: {dict(Counter(e.get('status') for e in evs))}")
        print(f"    contentType  : {dict(Counter(e.get('contentType') for e in evs))}")
        gen = Counter()
        for e in evs:
            for g in (e.get("genres") or []):
                gen[str(g)[:26]] += 1
        print(f"    genres       : {dict(gen.most_common(6))}")
        for kw in ("مباشر", "LIVE", "Live", "إعادة"):
            print(f"    kw {kw:8} in title: "
                  f"{sum(1 for e in evs if kw in str(e.get('title') or ''))}")
        evs_sorted = sorted(evs, key=lambda e: e.get("tsStart") or 0)
        gaps = 0
        for i in range(1, len(evs_sorted)):
            if (evs_sorted[i].get("tsStart") or 0) - (evs_sorted[i-1].get("tsEnd") or 0) > 60:
                gaps += 1
        print(f"    gaps>1min between events: {gaps}")
        for e in evs_sorted[:6]:
            st = datetime.fromtimestamp(e.get("tsStart") or 0, UTC)
            print(f"      {st:%m-%d %H:%M} [{e.get('status')}] {str(e.get('title'))[:54]}")


def main():
    for step in (probe_alkass_shape, probe_starzplay_status):
        try:
            step()
        except Exception as exc:
            print(f"\n  !! {step.__name__}: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
