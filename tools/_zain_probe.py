import sys, os; sys.path.insert(0, os.getcwd())
import osn_epg, requests
from epg_lib import new_session
out = []
per = osn_epg.collect(new_session())
for xid in ("OSNYaHala.osn", "OSNYaHalaBilArabi.osn", "OSNCrime.osn", "OSNYaHalaAflam.osn"):
    rows = per.get(xid, [])
    out.append(f"{xid}: {len(rows)} rows, last {max((r['stop'] for r in rows), default='-')}")
    out += [f"   {r['start']:%m-%d %H:%M} {r['title']}" for r in rows if r['start'].day == 22][:5]
print("::notice::" + "%0A".join(out))
