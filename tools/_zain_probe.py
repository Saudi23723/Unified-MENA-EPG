import re, json, requests, unicodedata
from datetime import datetime, timezone, timedelta
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
out = []
def get(u):
    try:
        r = requests.get(u, headers=H, timeout=60); return r.status_code, r.text
    except Exception as e:
        return type(e).__name__, ""
for u in ["https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates=20261009",
          "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates=20261017",
          "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=2026-10-09&s=Soccer",
          "https://www.fotmob.com/api/data/matches?date=20261009",
          "https://api.football-data.org/v4/matches",
          "https://www.livescore.com/en/football/2026-10-09/",
          "https://prod-public-api.livescore.com/v1/api/app/date/soccer/20261009/0?MD=1"]:
    s, t = get(u); out.append(f"{s} {len(t)} {u[:80]} :: {t[:150]!r}")
print("::notice::" + "%0A".join(out))
