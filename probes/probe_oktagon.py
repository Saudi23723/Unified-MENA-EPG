"""Find Animal Planet in the MENA feeds, from a runner. Never fails."""
import gzip, io, os, re, sys, traceback
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
now = datetime.now(timezone.utc)
URLS = [f"https://www.open-epg.com/files/{n}.xml" for n in
        ("egypt1", "egypt2", "saudiarabia1", "saudiarabia2", "uae1", "uae2",
         "kuwait1", "qatar1", "bahrain1", "oman1", "jordan1", "lebanon1")]
URLS += [f"https://epgshare01.online/epgshare01/epg_ripper_{c}.xml.gz" for c in
         ("AE1", "SA1", "SA2", "EG1", "QA1", "KW1")]
for url in URLS:
    try:
        b = S.get(url, timeout=90).content
        if url.endswith(".gz"):
            b = gzip.decompress(b)
        root = ET.fromstring(b)
        hits = [c for c in root.findall("channel")
                if re.search(r"animal|planet", (c.get("id") or "") + " ".join(d.text or "" for d in c.findall("display-name")), re.I)]
        for c in hits:
            cid = c.get("id")
            ps = [p for p in root.findall("programme") if p.get("channel") == cid]
            fut = [p for p in ps if datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z") > now]
            last = max((p.get("stop") for p in ps), default="-")
            print(f"HIT {url.split('/')[-1]:32} id={cid!r} names={[d.text for d in c.findall('display-name')][:3]} rows={len(ps)} future={len(fut)} until={last} sample={[p.findtext('title') for p in fut[:4]]}")
        print(f"DONE {url.split('/')[-1]} channels={len(root.findall('channel'))} hits={len(hits)}")
    except Exception as exc:
        print(f"FAIL {url} {exc}")
