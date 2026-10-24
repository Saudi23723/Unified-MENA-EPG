import json, urllib.request, os, re, datetime
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "*/*"}
def get(u, t=60):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t)
        return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)
os.makedirs("scan", exist_ok=True); out = []
st = datetime.datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z"); en = (datetime.datetime.utcnow()+datetime.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
for ch in ["tsn2", "tsn3", "tsn4", "tsn5"]:
    s, b = get(f"https://capi.9c9media.com/destinations/tsn_web/platforms/desktop/channelaffiliates/{ch}/schedules?StartTime={st}&EndTime={en}&Inclusions=Desc")
    out.append(f"== tsn {ch}: {s} items={b.count('StartTime')}")
for u in ["https://www.sportsnet.ca/tv-schedule/", "https://www.sportsnet.ca/watch/tv-schedule/", "https://www.sportsnet.ca/schedule/",
          "https://www.sportsnet.ca/wp-json/sportsnet/v1/tv-schedule", "https://www.sportsnet.ca/wp-json/sportsnet/v2/tv-schedule",
          "https://mobile-ifs.sportsnet.ca/schedule", "https://www.sportsnetnow.ca/schedule", "https://watch.sportsnet.ca/schedule"]:
    s, b = get(u)
    hints = sorted(set(re.findall(r'https?://[A-Za-z0-9.-]*(?:sportsnet|rogers|sn\.)[A-Za-z0-9./_?=&%-]*(?:schedul|epg|listing|guide)[A-Za-z0-9./_?=&%-]*', b)))[:25]
    out.append(f"== {u}: {s} len={len(b)}"); out.append(b[:300].replace("\n", " ")); out.append("hints: " + " | ".join(hints))
open("scan/probe_sn.txt", "w").write("\n".join(out)); print("\n".join(out)[:4000])
