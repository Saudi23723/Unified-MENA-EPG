import json, requests
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone.utc); day = now.strftime("%Y-%m-%d")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Safari/537.36"}
for host in ("api2.shahid.net", "api3.shahid.net"):
    url = (f"https://{host}/proxy/v2.1/shahid-epg-api/?csvChannelIds=49923775805582"
           f"&from={day}T00:00:00.000Z&to={day}T23:59:59.999Z&country=SA&language=ar&Accept-Language=ar")
    try:
        r = requests.get(url, headers=UA, timeout=60); print(host, r.status_code, r.text[:600].replace("\n", " "))
    except Exception as e:
        print(host, "ERR", e)
d = now.strftime("%Y%m%d")
try:
    r = requests.get(f"https://static-cdn.tv.sfr.net/data/epg/gen8/guide_web_{d}.json", headers=UA, timeout=60)
    print("sfr", r.status_code, len(r.content))
    j = r.json(); e = j.get("epg", {}).get("4141") or j.get("epg", {}).get(4141)
    print("sfr 4141:", json.dumps(e[:6] if e else e, ensure_ascii=False)[:1200])
except Exception as ex:
    print("sfr ERR", ex)
