"""Run the real Oktagon reader and the board's own filter, from a runner. Never fails."""
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.getcwd())
try:
    import requests
    import oktagon
    import other_sports_epg as board
    now = datetime.now(timezone.utc)
    got = oktagon.events(requests.Session(), now - timedelta(days=1), now + timedelta(days=120))
    for e in got:
        print(e["start"].isoformat(), e["title"], "| channels", e["channels"],
              "| wanted", board.wanted(e))
    print("TOTAL", len(got))
except Exception:
    traceback.print_exc()
