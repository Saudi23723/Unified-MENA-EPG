import urllib.request, os, re, json, traceback, datetime
os.makedirs("scan", exist_ok=True); out = []
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "application/json"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60); return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)
d = datetime.datetime.utcnow().strftime("%Y-%m-%d")
A = "https://production-cdn.d3-rgr-diva.com/api"
for u in [A + "/page?path=%2Fschedule&device=web_browser&ff=idp,ldp,rpt,cd&lang=en-CA&segments=",
          A + "/page?path=/schedule", A + "/lists?ids=&device=web_browser",
          "https://schedule-admin.sportsnet.ca/v1/schedule", "https://schedule-admin.sportsnet.ca/v1/channels",
          "https://schedule-admin.sportsnet.ca/v1/linear", f"https://schedule-admin.sportsnet.ca/v1/schedule?date={d}",
          f"https://schedule-admin.sportsnet.ca/v1/linear-schedule?date={d}", "https://schedule-admin.sportsnet.ca/v1/"]:
    s, b = get(u)
    out.append(f"== {u}: {s} len={len(b)}"); out.append(b[:1500].replace("\n", " "))
    ids = re.findall(r'"id":"?([A-Za-z0-9_-]+)"?,"(?:title|name)":"([^"]*(?:Sportsnet|SN)[^"]*)"', b)
    if ids: out.append("chan ids: " + json.dumps(ids[:40]))
open("scan/probe_sn4.txt", "w").write("\n".join(out))
