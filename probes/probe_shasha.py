"""Print what the Shasha generator now collects, from a runner. Never fails."""
import os
import sys
import traceback
from collections import Counter

sys.path.insert(0, os.getcwd())
try:
    import today_matches_epg as front
    import update_shasha_epg as s
    floor, ceiling = s.window_bounds()
    rows = front.collect(s.fetch_text(front.SOURCE), s.utc_now(), floor, ceiling)
    print("HEADINGS:")
    for h, n in Counter(r["competition"] for r in rows).most_common():
        print(f"  {n:3} {h!r} -> {bool(s.SHASHA_CARRIES_WHOLE.match(s.norm(h)))}")
    print("UPCOMING:")
    for e in s.parse_shasha_upcoming():
        print(" ", e["start"].isoformat(), e["competition"], "|", e["title"])
    print("CHANNEL PAGE:")
    for e in s.parse_shasha_channel():
        print(" ", e["start"].isoformat(), e["competition"], "|", e["title"])
except Exception:
    traceback.print_exc()
