"""Real airport schedules for channel 6: does FR24's airport API answer
from a runner, and with what? Never fails."""
import json, os, sys, time
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
     "Accept": "application/json", "Origin": "https://www.flightradar24.com",
     "Referer": "https://www.flightradar24.com/"}
for code in ("AMM", "DXB", "AUH", "IST"):
    for mode in ("departures", "arrivals"):
        url = (f"https://api.flightradar24.com/common/v1/airport.json?code={code}"
               f"&plugin[]=schedule&plugin-setting[schedule][mode]={mode}"
               f"&plugin-setting[schedule][timestamp]={int(time.time())}&page=1&limit=100")
        try:
            r = S.get(url, headers=H, timeout=40)
            d = r.json()
            sch = d["result"]["response"]["airport"]["pluginData"]["schedule"][mode]
            rows = sch["data"]; tot = sch["item"]["total"]
            print(f"OK {code} {mode} status={r.status_code} rows={len(rows)} total={tot}")
            for x in rows[:3]:
                f = x["flight"]
                print("   ", f["identification"]["number"]["default"], f["airline"] and f["airline"]["code"],
                      f["airport"]["origin"] and f["airport"]["origin"]["code"]["iata"] if mode=="arrivals" else f["airport"]["destination"]["code"]["iata"],
                      json.dumps(f["time"]), f["status"]["text"], f["status"]["generic"]["status"])
        except Exception as e:
            print("FAIL", code, mode, getattr(r, "status_code", None) if 'r' in dir() else None, str(e)[:200])
        time.sleep(2)
