import sys, requests, json
sys.path.insert(0, ".")
import update_shasha_epg as s
from zoneinfo import ZoneInfo
K = ZoneInfo("Asia/Kuwait")
out = []
for name in ["parse_shasha_channel", "parse_shasha_upcoming", "_parse_oddalerts_zain", "_parse_soccerway_zain", "parse_zain"]:
    try:
        ev = getattr(s, name)()
    except Exception as e:
        out.append(f"{name} ERR {type(e).__name__}"); continue
    for e in ev:
        if e.get("competition", "").lower().find("zain") >= 0 or "زين" in e.get("competition", "") or any(k in e["title"] for k in ("Nasar", "Kazma", "Tadhamon", "Qadsia", "Arabi", "Kuwait")):
            out.append(f"{name} {e['start'].astimezone(K):%a %d %H:%M} KWT | {e['title']} | {e.get('source_name')}")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
for d in ("2026-10-08", "2026-10-09", "2026-10-10", "2026-10-11"):
    try:
        j = requests.get(f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{d}", headers=H, timeout=60).json()
        for ev in j.get("events", []):
            t = ev.get("tournament", {}); c = t.get("category", {}).get("name", "")
            if c == "Kuwait":
                from datetime import datetime, timezone
                st = datetime.fromtimestamp(ev["startTimestamp"], timezone.utc).astimezone(K)
                out.append(f"SOFA {st:%a %d %H:%M} KWT | {ev['homeTeam']['name']} - {ev['awayTeam']['name']} | {t.get('name')}")
    except Exception as e:
        out.append(f"SOFA {d} ERR {type(e).__name__}")
print("::notice::" + "%0A".join(sorted(set(out)))[:6000])
