"""Run the real OSN reader against the live feeds, from a runner. Never fails."""
import os
import sys
import traceback
from datetime import datetime, timezone

import xml.etree.ElementTree as ET

sys.path.insert(0, os.getcwd())
try:
    import osn_epg
    from epg_lib import new_session
    now = datetime.now(timezone.utc)
    got = osn_epg.collect(new_session(), "roya_jordan_epg.xml")
    root = ET.Element("tv")
    print("TOTAL", osn_epg.emit(root, got))
    for cid, rows in got.items():
        cur = [r for r in rows if r["start"] <= now < r["stop"]]
        print(f"{cid:24} rows={len(rows):4} until={max(r['stop'] for r in rows):%d.%m %H:%M}Z now={cur[0]['title'][:40] if cur else '-'}")
except Exception:
    traceback.print_exc()
