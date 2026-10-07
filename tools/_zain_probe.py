import sys; sys.path.insert(0, ".")
import update_shasha_epg as s
from zoneinfo import ZoneInfo
K = ZoneInfo("Asia/Kuwait")
ev = s.parse_zain()
print("::notice::" + "%0A".join(f"{e['start']:%a %d %H:%M} UTC = {e['start'].astimezone(K):%H:%M} KWT | {e['title']}" for e in sorted(ev, key=lambda e: e['start'])))
