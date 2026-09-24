"""Which public XMLTV feeds carry MBC's channels, and how well. Never fails."""
import gzip
import re
import traceback
from collections import Counter
from datetime import datetime, timezone

import requests

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

FEEDS = [f"https://epgshare01.online/epgshare01/epg_ripper_{c}.xml.gz"
         for c in ("SA1", "SA2", "AE1", "AE2", "ARABIA1", "EG1", "QA1", "KW1", "JO1", "LB1", "BH1", "ALL_SOURCES1")]
FEEDS += [f"https://www.open-epg.com/files/{c}.xml" for c in
          ("saudiarabia1", "saudiarabia2", "saudiarabia", "uae1", "uae2", "unitedarabemirates1", "egypt1", "egypt2", "arabic1", "qatar1", "kuwait1")]
now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

for url in FEEDS:
    try:
        r = S.get(url, timeout=60)
        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        t = raw.decode("utf-8", "replace")
        print("==", url, r.status_code, len(t))
        if r.status_code != 200 or "<tv" not in t[:2000]:
            continue
        chans = {}
        for m in re.finditer(r'<channel id="([^"]+)"[^>]*>(.*?)</channel>', t, re.S):
            name = re.search(r"<display-name[^>]*>(.*?)</display-name>", m.group(2), re.S)
            chans[m.group(1)] = name.group(1) if name else ""
        mbc = {k: v for k, v in chans.items() if re.search(r"mbc|wanasah|وناسة|shahid", k + v, re.I)}
        if not mbc:
            print("   no MBC channels among", len(chans))
            continue
        per = Counter(); future = Counter(); last = {}; titles = {}
        for m in re.finditer(r'<programme start="(\d{14})[^"]*" stop="(\d{14})[^"]*" channel="([^"]+)"(.*?)</programme>', t, re.S):
            c = m.group(3)
            if c in mbc:
                per[c] += 1
                if m.group(2) > now:
                    future[c] += 1
                last[c] = max(last.get(c, ""), m.group(2))
                tt = re.search(r"<title[^>]*>(.*?)</title>", m.group(4), re.S)
                titles.setdefault(c, set()).add(tt.group(1) if tt else "")
        for c, v in sorted(mbc.items()):
            sample = list(titles.get(c, []))[:3]
            print(f"   {c:40} {v[:30]:30} rows={per[c]:4} future={future[c]:4} last={last.get(c,'')[:12]} distinct={len(titles.get(c, []))} {sample}")
    except Exception as exc:
        print("== ERR", url, type(exc).__name__, str(exc)[:150])
