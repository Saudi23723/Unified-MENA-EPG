import sys, os, re; sys.path.insert(0, os.getcwd())
import requests, gzip, xml.etree.ElementTree as ET
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
PAT = re.compile(r"syria|souri|suri|sooria|sama\b|sama tv|lana|ikhbar|ekhbar|halab|aleppo|al ?yaum|sham|drama|rojava|qanat 9|ghouta|orient|سوري|سما|لنا|الإخبارية|حلب|شام", re.I)
URLS = {f"es:{c}": f"https://epgshare01.online/epgshare01/epg_ripper_{c}.xml.gz" for c in ("SY1", "AE1", "AE2", "SA1", "SA2", "LB1", "JO1", "IQ1", "EG1", "ALL_SOURCES1", "QA1", "KW1", "TR1")}
URLS.update({"ipe-sy": "https://iptv-epg.org/files/epg-sy.xml", "ipe-ae": "https://iptv-epg.org/files/epg-ae.xml", "ipe-lb": "https://iptv-epg.org/files/epg-lb.xml", "ipe-sa": "https://iptv-epg.org/files/epg-sa.xml",
             "oe-syria": "https://www.open-epg.com/files/syria1.xml", "oe-syria2": "https://www.open-epg.com/files/syria2.xml", "oe-leb": "https://www.open-epg.com/files/lebanon1.xml", "oe-uae1": "https://www.open-epg.com/files/uae1.xml",
             "ferteque": "https://github.com/ferteque/Curated-M3U-Repository/raw/refs/heads/main/epg6.xml.gz"})
for key, url in URLS.items():
    try:
        r = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            print(key, r.status_code); continue
        raw = r.content
        root = ET.fromstring(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    except Exception as e:
        print(key, "ERR", type(e).__name__); continue
    fut, titles = {}, {}
    for p in root.iter("programme"):
        try:
            if datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z") > now:
                fut[p.get("channel")] = fut.get(p.get("channel"), 0) + 1
                titles.setdefault(p.get("channel"), set()).add(p.findtext("title") or "")
        except Exception:
            pass
    hits = []
    for ch in root.findall("channel"):
        n = " / ".join(d.text or "" for d in ch.findall("display-name"))
        if PAT.search(n + " " + ch.get("id", "")) and (".sy" in ch.get("id", "").lower() or re.search(r"syria|souri|sooria|سوري|lana|sama\b|sama tv|ikhbar|ekhbar|halab|aleppo|yaum|sham|rojava", n + ch.get("id", ""), re.I)):
            c = ch.get("id")
            hits.append(f"{c}={n[:40]}:{fut.get(c,0)}r/{len(titles.get(c, ()))}t")
    print(key, len(root.findall("channel")), "ch |", "; ".join(hits)[:1500])
