"""UAE channels (Dubai, Abu Dhabi, Sharjah, Sharqia, Fujairah, Dubai Sports,
Dubai Racing, AD Nat Geo...): which aggregated feeds carry them, under
which ids, and how many programmes over what span. Never fails."""
import gzip, os, re, sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
FEEDS = {
    "oe_uae1": "https://www.open-epg.com/files/uae1.xml",
    "oe_uae2": "https://www.open-epg.com/files/uae2.xml",
    "oe_uae3": "https://www.open-epg.com/files/uae3.xml",
    "es_AE1": "https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz",
    "es_AE2": "https://epgshare01.online/epgshare01/epg_ripper_AE2.xml.gz",
    "es_ALL_SOURCES_ar": "https://epgshare01.online/epgshare01/epg_ripper_SA1.xml.gz",
}
PAT = re.compile(r"dubai|abu ?dhabi|abudhabi|sharjah|sharqia|sharqiya|fujairah|emarat|sama|nat ?geo|ajman|\bad\b|yas|majid|racing|zayed|baynounah|noor dubai|dubai one|dxb|\.ae\b", re.I)
now = datetime.now(timezone.utc)
for name, url in FEEDS.items():
    try:
        r = S.get(url, timeout=60); raw = r.content
        if raw[:2] == b"\x1f\x8b": raw = gzip.decompress(raw)
        root = ET.fromstring(raw)
    except Exception as e:
        print("FAIL", name, getattr(locals().get('r'), 'status_code', None), str(e)[:120]); continue
    names = {}
    for ch in root.iter("channel"):
        dn = [d.text or "" for d in ch.findall("display-name")]
        icon = ch.find("icon")
        names[ch.get("id")] = (dn, icon.get("src") if icon is not None else "")
    count = defaultdict(int); first = {}; last = {}; sample = defaultdict(list)
    for p in root.iter("programme"):
        c = p.get("channel")
        if not (PAT.search(c or "") or any(PAT.search(x) for x in names.get(c, ([], ""))[0])):
            continue
        count[c] += 1
        s = p.get("start", "")[:12]; first[c] = min(first.get(c, s), s); last[c] = max(last.get(c, s), s)
        if len(sample[c]) < 3: sample[c].append((p.get("start"), (p.findtext("title") or "")[:40]))
    print(f"== {name}: {len(names)} channels")
    for c in sorted(set(count) | {k for k, v in names.items() if PAT.search(k) or any(PAT.search(x) for x in v[0])}):
        dn, icon = names.get(c, ([], ""))
        print(f"  {c!r} names={dn[:3]} progs={count.get(c,0)} span={first.get(c)}..{last.get(c)} icon={icon[:90]}")
        for s in sample.get(c, [])[:2]:
            print("      ", s)
