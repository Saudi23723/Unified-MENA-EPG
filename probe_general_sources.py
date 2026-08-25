#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: judge the one feed that could carry the new guide.

Every broadcaster's own page is shut: MBC 404s on every schedule path,
OSN, Al Arabiya, Al Hadath and Al Mayadeen all answer 403, Al Araby's
schedule 500s. Al Jazeera's جدول البث is the single official page that
answers at all.

That leaves epgshare01's AE1 feed — 813 channels, 69,699 programmes —
which named Al Arabiya, Al Hadath, Al Mayadeen, Al Araby 1 and 2 and much
else with real programme counts. The earlier listing was cut off at 45
entries, alphabetically before M, so MBC, OSN and Rotana were never seen.

Before any of it can be recommended it has to be judged, not just
counted: which channels, how many days each, what the titles look like,
and whether they are Arabic. Changes nothing.
"""
from __future__ import annotations

import gzip
import io
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 40)
CAP = 120 * 1024 * 1024
ARABIC = re.compile(r"[؀-ۿ]")

GROUPS = {
    "MBC": re.compile(r"\bmbc\b", re.I),
    "OSN": re.compile(r"\bosn", re.I),
    "Rotana": re.compile(r"rotana", re.I),
    "News AR": re.compile(r"arabiya|hadath|mayadeen|araby|jazeera|sky.?news|"
                          r"bbc.?arabic|france.?24|dw.arab|cnbc|extra.?news|"
                          r"ekhbariya|ikhbariya|alghad", re.I),
    "Levant/Gulf general": re.compile(
        r"\blbc|\bmtv\b|otv|jadeed|dubai|abu.?dhabi|sharjah|sama|"
        r"saudi|syria|jordan|mamlaka|roya|kuwait|qatar|oman|bahrain", re.I),
    "STC / Jawwy": re.compile(r"\bstc\b|jawwy", re.I),
}


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def load(code):
    url = f"https://epgshare01.online/epgshare01/epg_ripper_{code}.xml.gz"
    try:
        r = requests.get(url, headers=H, timeout=T, stream=True)
    except Exception as exc:
        print(f"  {code}: FAILED {str(exc)[:90]}", flush=True)
        return None
    if r.status_code != 200:
        print(f"  {code}: HTTP {r.status_code}", flush=True)
        return None
    buf = io.BytesIO()
    for chunk in r.iter_content(1 << 16):
        buf.write(chunk)
        if buf.tell() > CAP:
            print(f"  {code}: over cap", flush=True)
            return None
    try:
        return ET.fromstring(gzip.decompress(buf.getvalue()))
    except Exception as exc:
        print(f"  {code}: unusable ({exc})", flush=True)
        return None


def survey(code):
    root = load(code)
    if root is None:
        return
    names = {c.get("id"): (c.findtext("display-name") or "") for c in root.findall("channel")}
    per = defaultdict(list)
    for p in root.findall("programme"):
        per[p.get("channel")].append(p)

    print(f"\n{code}: {len(names)} channels, {sum(len(v) for v in per.values())} programmes",
          flush=True)

    for label, pattern in GROUPS.items():
        hits = sorted(cid for cid in names
                      if pattern.search(cid or "") or pattern.search(names[cid] or ""))
        withdata = [c for c in hits if per[c]]
        print(f"\n  --- {label}: {len(hits)} channels, {len(withdata)} with programmes ---",
              flush=True)
        for cid in hits:
            rows = per[cid]
            if not rows:
                continue
            days = sorted({p.get("start", "")[:8] for p in rows})
            titles = [(p.findtext("title") or "") for p in rows]
            arabic = sum(1 for t in titles if ARABIC.search(t))
            print(f"    {names[cid][:30]:32} {len(rows):4} prog  {len(days)} days "
                  f"({days[0][:8]}..{days[-1][:8]})  {arabic:4} Arabic titles", flush=True)
        # what the data actually looks like, for the first two channels
        for cid in withdata[:2]:
            rows = sorted(per[cid], key=lambda p: p.get("start"))
            print(f"      e.g. {names[cid]}:", flush=True)
            for p in rows[:5]:
                s = p.get("start", "")
                print(f"         {s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}  "
                      f"{(p.findtext('title') or '')[:58]}", flush=True)


def main():
    print(f"now UTC {datetime.now(timezone.utc):%Y-%m-%d %H:%M}", flush=True)
    section("AE1 — the only feed with broad Arabic coverage")
    survey("AE1")
    section("ALJAZEERA1 — the broadcaster's own feed on the same mirror")
    survey("ALJAZEERA1")


if __name__ == "__main__":
    main()
