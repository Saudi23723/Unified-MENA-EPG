"""Channel 6 rebuild: run flight_epg's own collector on a runner and dump
the raw answers it kept, so the boards can be drawn and checked. Never fails."""
import base64, gzip, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
import flight_epg
from epg_lib import new_session
try:
    flight_epg.collect(new_session(), datetime.now(timezone.utc))
    blob = base64.b64encode(gzip.compress(open(flight_epg.STATE, "rb").read())).decode()
    print("STATE-BEGIN")
    for i in range(0, len(blob), 4000):
        print("S|" + blob[i:i + 4000])
    print("STATE-END")
except Exception as e:
    print("FAIL", e)
