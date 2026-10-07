import re, requests, json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
K = ZoneInfo("Asia/Kuwait")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36", "Accept": "*/*"}
out = []
t = requests.get("https://www.oddalerts.com/leagues/kuwait/zain-premier-league/fixtures", headers=H, timeout=60).text
for pat in [r"timezone[^,]{0,80}", r"Europe/[A-Za-z_]+", r"UTC[^<]{0,30}", r"GMT[^<]{0,30}", r'"(?:kickoff|unix|timestamp|start)[a-z_]*"\s*:\s*"?\d+']:
    out.append(f"ODD {pat}: {sorted(set(re.findall(pat, t, re.I)))[:6]}")
i = t.find("Al Nasar"); out.append("ODD ctx: " + re.sub(r"\s+", " ", t[max(0, i-700):i+100])[:800])
for u in ["https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-10-09",
          "https://www.sofascore.com/api/v1/sport/football/scheduled-events/2026-10-09"]:
    try:
        r = requests.get(u, headers=H, timeout=60); out.append(f"SOFA {r.status_code} {len(r.text)}")
        for ev in r.json().get("events", []):
            if ev.get("tournament", {}).get("category", {}).get("name") == "Kuwait":
                st = datetime.fromtimestamp(ev["startTimestamp"], timezone.utc)
                out.append(f"SOFA {st:%H:%M} UTC | {ev['homeTeam']['name']} - {ev['awayTeam']['name']}")
    except Exception as e:
        out.append(f"SOFA ERR {type(e).__name__}")
try:
    r = requests.get("https://site.api.espn.com/apis/site/v2/sports/soccer/kuw.1/scoreboard?dates=20261009-20261011", headers=H, timeout=60)
    out.append(f"ESPN {r.status_code}")
    for ev in r.json().get("events", []):
        out.append(f"ESPN {ev['date']} | {ev['name']}")
except Exception as e:
    out.append(f"ESPN ERR {type(e).__name__}")
try:
    r = requests.get("https://www.fotmob.com/api/matches?date=20261009&timezone=UTC", headers=H, timeout=60)
    out.append(f"FOTMOB {r.status_code}")
    for lg in r.json().get("leagues", []):
        if lg.get("ccode") == "KUW":
            for m in lg.get("matches", []):
                out.append(f"FOTMOB {m.get('status',{}).get('utcTime')} | {m['home']['name']} - {m['away']['name']}")
except Exception as e:
    out.append(f"FOTMOB ERR {type(e).__name__}")
print("::notice::" + "%0A".join(out)[:7000])
