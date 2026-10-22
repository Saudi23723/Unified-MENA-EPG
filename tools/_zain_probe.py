import sys, os; sys.path.insert(0, os.getcwd())
import requests, gzip, xml.etree.ElementTree as ET, re
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
want = {"TR": ["beIN Sports 1", "beIN Sports 2", "TiviBu Spor 2", "S Sport", "Eurosport 1"],
        "RS": ["Arena Sport 1", "Arena Sport 2", "Sport Klub 1", "Sport Klub 4"],
        "AL": ["Tring Sport 1", "SuperSport 1", "RTSH Sport", "Eurosport 1"],
        "CA": ["TSN 1", "TSN 2", "TSN 4", "Sportsnet ONE"], "PL": ["TVP Sport", "Polsat Sport"],
        "IL": ["Sport 1", "Sport 5", "Yes Sport"], "PT": ["Sport TV 1"], "GR": ["Nova Sports 1"], "HR": ["Arena Sport 1", "Sport Klub 1"], "BA": ["Arena Sport 1"]}
for cc in ["TR1", "TR2", "TR3", "RS1", "RS2", "AL1", "AL2", "CA1", "CA2", "CA3", "PL1", "PL2", "IL1", "IL2", "PT1", "GR1", "HR1", "BA1", "MK1", "ME1", "SI1", "RO1", "BG1", "HU1", "CZ1", "SK1", "NL1", "BE1", "CH1", "AT1", "SE1", "NO1", "DK1", "FI1", "IE1", "NZ1", "ZA1", "IN1", "MX1", "BR1", "AR1"]:
    try:
        r = requests.get(f"https://epgshare01.online/epgshare01/epg_ripper_{cc}.xml.gz", timeout=120)
        if r.status_code != 200:
            print(cc, r.status_code); continue
        root = ET.fromstring(gzip.decompress(r.content))
    except Exception as e:
        print(cc, "ERR", type(e).__name__); continue
    fut = {}
    for p in root.iter("programme"):
        if datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z") > now:
            fut[p.get("channel")] = fut.get(p.get("channel"), 0) + 1
    names = {(d.text or "").strip().lower(): ch.get("id") for ch in root.findall("channel") for d in ch.findall("display-name")}
    hits = []
    for w in want.get(cc[:2], []):
        k = [n for n in names if re.sub(r"\W", "", n).startswith(re.sub(r"\W", "", w.lower())) and fut.get(names[n])]
        hits.append(f"{w}:{'Y' if k else '-'}")
    print(cc, len(root.findall("channel")), "ch,", len(fut), "with rows |", " ".join(hits))
