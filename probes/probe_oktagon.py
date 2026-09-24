"""Which public feeds schedule OSN's channels, and how well. Never fails."""
import gzip
import re
from collections import Counter
from datetime import datetime, timezone

import requests

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
WANT = re.compile(r"\bosn\b|أو إس إن|او اس ان", re.I)
FEEDS = [f"https://epgshare01.online/epgshare01/epg_ripper_{c}.xml.gz" for c in ("AE1", "SA2", "EG1")]
FEEDS += [f"https://www.open-epg.com/files/{c}.xml" for c in
          ("uae1", "uae2", "saudiarabia1", "saudiarabia2", "egypt1", "egypt2", "qatar1")]
now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
for url in FEEDS:
    try:
        r = S.get(url, timeout=90)
        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        t = raw.decode("utf-8", "replace")
        print("==", url, r.status_code, len(t))
        chans = {}
        for m in re.finditer(r'<channel id="([^"]+)"[^>]*>(.*?)</channel>', t, re.S):
            names = re.findall(r"<display-name[^>]*>(.*?)</display-name>", m.group(2), re.S)
            if WANT.search(m.group(1) + " " + " ".join(names)):
                chans[m.group(1)] = " | ".join(names)[:40]
        if not chans:
            print("   none")
            continue
        future = Counter(); distinct = {}; last = {}; first = {}
        for m in re.finditer(r'<programme start="(\d{14})([^"]*)" stop="(\d{14})[^"]*" channel="([^"]+)"(.*?)</programme>', t, re.S):
            c = m.group(4)
            if c in chans:
                first.setdefault(c, m.group(1) + m.group(2))
                if m.group(3) > now:
                    future[c] += 1
                    last[c] = max(last.get(c, ""), m.group(3))
                    tt = re.search(r"<title[^>]*>(.*?)</title>", m.group(5), re.S)
                    distinct.setdefault(c, set()).add(tt.group(1) if tt else "")
        print(f"   {len(chans)} OSN channels, {sum(1 for c in chans if future[c])} with future rows; first raw start {next(iter(first.values()), '')}")
        for c, n in sorted(chans.items()):
            print(f"   {c:34} future={future[c]:4} last={last.get(c,'')[:12]} distinct={len(distinct.get(c, []))} {list(distinct.get(c, []))[:2]}")
    except Exception as exc:
        print("== ERR", url, type(exc).__name__, str(exc)[:150])
