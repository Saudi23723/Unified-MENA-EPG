"""Run the real MBC reader against the live feeds, from a runner. Never fails."""
import os
import sys
import traceback
from datetime import datetime, timezone

import xml.etree.ElementTree as ET

sys.path.insert(0, os.getcwd())
try:
    import mbc_epg
    from epg_lib import new_session
    now = datetime.now(timezone.utc)
    got = mbc_epg.collect(new_session(), "roya_jordan_epg.xml")
    root = ET.Element("tv")
    total = mbc_epg.emit(root, got)
    print("TOTAL", total)
    for cid, rows in got.items():
        future = [r for r in rows if r["stop"] > now]
        nxt = [r for r in rows if r["start"] <= now < r["stop"]]
        print(f"{cid:18} rows={len(rows):4} future={len(future):4} "
              f"until={max(r['stop'] for r in rows):%d.%m %H:%M}Z now={nxt[0]['title'][:40] if nxt else '-'}")
except Exception:
    traceback.print_exc()
