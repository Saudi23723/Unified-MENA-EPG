#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: find sources for a second, non-sport guide.

Wanted: MBC's channels with their programmes, OSN, STC's film and series
channels, and the Arabic news channels — Al Arabiya, Al Hadath,
Al Mayadeen, Al Araby 1 and 2, and their peers across Lebanon, Jordan,
Saudi, Qatar, Syria and the UAE.

Nothing gets built until it is known which of those actually have a
source. This checks three kinds at once: the epgshare01 mirror, which
would cover many channels in one XMLTV file; each broadcaster's own
schedule page, which is the authority where it exists; and the STC
endpoint this project already knows returns listings without names.
Changes nothing.
"""
from __future__ import annotations

import gzip
import io
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 30)
CAP = 60 * 1024 * 1024

WANTED = re.compile(
    r"mbc|osn|shahid|arabiya|hadath|mayadeen|araby|arabi|"
    r"jazeera|sky.?news|alghad|extra|"
    r"stc|jawwy|rotana|art\b|dubai|abu.?dhabi|sharjah|"
    r"lbc|mtv|otv|aljadeed|ntv|"
    r"saudi|ekhbariya|thekafiya|quran|sunnah|"
    r"syria|ikhbaria|"
    r"jordan|mamlaka|roya", re.I)


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def get(url, **kw):
    try:
        return requests.get(url, headers=H, timeout=T, allow_redirects=True, **kw)
    except Exception as exc:
        print(f"  {url}\n     FAILED {str(exc)[:100]}", flush=True)
        return None


def load_gz_xml(url):
    r = get(url, stream=True)
    if r is None or r.status_code != 200:
        if r is not None:
            print(f"  {url} -> {r.status_code}", flush=True)
        return None
    buf = io.BytesIO()
    for chunk in r.iter_content(1 << 16):
        buf.write(chunk)
        if buf.tell() > CAP:
            print(f"  {url}: over cap, skipped", flush=True)
            return None
    try:
        return ET.fromstring(gzip.decompress(buf.getvalue()))
    except Exception as exc:
        print(f"  {url}: unusable ({exc})", flush=True)
        return None


def main():
    section("what country feeds epgshare01 publishes")
    index = get("https://epgshare01.online/epgshare01/")
    codes = []
    if index is not None and index.status_code == 200:
        codes = sorted(set(re.findall(r"epg_ripper_([A-Z0-9_]+)\.xml\.gz", index.text)))
        print(f"  {len(codes)} feeds: {codes}", flush=True)
    else:
        print("  index unavailable", flush=True)

    mena = [c for c in codes
            if re.match(r"^(AR|SA|AE|EG|QA|LB|JO|SY|KW|OM|BH|IQ|MA|DZ|TN|LY|YE|PS|SD)\d*",
                        c)]
    print(f"\n  MENA-looking: {mena}", flush=True)

    section("what those feeds actually carry")
    for code in mena[:8]:
        root = load_gz_xml(
            f"https://epgshare01.online/epgshare01/epg_ripper_{code}.xml.gz")
        if root is None:
            continue
        per = defaultdict(int)
        for p in root.findall("programme"):
            per[p.get("channel")] += 1
        names = {c.get("id"): (c.findtext("display-name") or "")
                 for c in root.findall("channel")}
        hits = sorted(cid for cid in names if WANTED.search(cid or "")
                      or WANTED.search(names[cid] or ""))
        print(f"\n  {code}: {len(names)} channels, {len(root.findall('programme'))} "
              f"programmes | {len(hits)} of interest", flush=True)
        for cid in hits[:45]:
            print(f"      {cid:34} {names[cid][:28]:30} {per[cid]:5} prog", flush=True)

    section("each broadcaster's own schedule page")
    for label, url in (
        ("MBC", "https://www.mbc.net/ar/schedule.html"),
        ("MBC", "https://www.mbc.net/ar/schedule"),
        ("MBC", "https://www.mbc.net/en/schedule"),
        ("Shahid", "https://shahid.mbc.net/ar/livestreams"),
        ("OSN", "https://www.osn.com/en-ae/tv-guide"),
        ("OSN", "https://www.osn.com/ar-ae/tv-guide"),
        ("Al Arabiya", "https://www.alarabiya.net/tv-schedule"),
        ("Al Arabiya", "https://www.alarabiya.net/ar/programs"),
        ("Al Hadath", "https://www.alhadath.net/tv-schedule"),
        ("Al Mayadeen", "https://www.almayadeen.net/programsschedule"),
        ("Al Mayadeen", "https://www.almayadeen.net/shows"),
        ("Al Araby", "https://www.alaraby.tv/schedule"),
        ("Al Araby", "https://alaraby.tv/"),
        ("Al Jazeera", "https://www.aljazeera.net/schedule"),
        ("Dubai TV", "https://www.dmi.ae/"),
        ("STC listings", "https://prod-cdn-content-api.intigral-ott.net/api/v1/epg/listings"),
    ):
        r = get(url)
        if r is None:
            continue
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
        times = len(re.findall(r"\b([01]\d|2[0-3]):[0-5]\d\b", r.text))
        print(f"  {label:12} {url:58} -> {r.status_code} {len(r.text):8}b "
              f"{times:4} clocks", flush=True)
        if r.status_code == 200 and times > 5:
            print(f"      {body[:160]}", flush=True)


if __name__ == "__main__":
    main()
