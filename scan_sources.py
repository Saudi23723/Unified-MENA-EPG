import json, urllib.request, datetime, os
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "application/json"}
def get(u, t=60):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t)
        return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)
os.makedirs("scan", exist_ok=True)
out = []
today = datetime.datetime.utcnow().strftime("%Y%m%d")
# Sky UK official guide: services for a few bouquets/regions
for bq in ["4101/1", "4101/2", "4097/1", "4103/1"]:
    s, b = get(f"https://awk.epgsky.com/hawk/linear/services/{bq}")
    out.append(f"== sky services {bq}: {s} {len(b)}")
    try:
        sv = json.loads(b).get("services", [])
        keep = [x for x in sv if any(w in (x.get("t") or "") for w in ("Sky Sp", "TNT", "Premier", "Eurosport", "LFC", "MUTV", "Racing", "Sky Cinema", "Sky Atl", "Sky News"))]
        out.append(json.dumps(keep[:120]))
    except Exception as e:
        out.append(b[:300])
s, b = get(f"https://awk.epgsky.com/hawk/linear/schedule/{today}/1301")
out.append(f"== sky schedule 1301 {today}: {s}"); out.append(b[:1500])
# TSN (Bell Media) official schedule API variants
st = datetime.datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z"); en = (datetime.datetime.utcnow()+datetime.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
for dest in ["tsn_web", "tsn_ott", "tsn_android"]:
    for ch in ["tsn1", "tsn_1", "TSN1"]:
        u = f"https://capi.9c9media.com/destinations/{dest}/platforms/desktop/channelaffiliates/{ch}/schedules?StartTime={st}&EndTime={en}&Inclusions=Desc"
        s, b = get(u); out.append(f"== tsn {dest} {ch}: {s} {len(b)}"); out.append(b[:400])
s, b = get("https://capi.9c9media.com/destinations/tsn_web/platforms/desktop/channelaffiliates")
out.append(f"== tsn affiliates: {s}"); out.append(b[:2000])
open("scan/probe_official.txt", "w").write("\n".join(out))
print("\n".join(x[:200] for x in out))
