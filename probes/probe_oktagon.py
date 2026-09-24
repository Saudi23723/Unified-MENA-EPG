"""Run the real PFL, BRAVE and OKTAGON readers and the board's filter, from a runner. Never fails."""
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.getcwd())
try:
    import requests
    import brave_cf
    import oktagon
    import other_sports_epg as board
    import pfl_events
    now = datetime.now(timezone.utc)
    s = requests.Session()
    for mod in (pfl_events, brave_cf, oktagon):
        got = mod.events(s, now - timedelta(days=1), now + timedelta(days=120))
        for e in got:
            print(mod.__name__, e["start"].isoformat(), e["title"], "| wanted", board.wanted(e))
        print(mod.__name__, "TOTAL", len(got))
except Exception:
    traceback.print_exc()
