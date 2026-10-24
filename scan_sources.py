import urllib.request, urllib.parse, os, re, json, datetime
os.makedirs("scan", exist_ok=True); out = []
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "application/json", "Origin": "https://shahid.mbc.net", "Referer": "https://shahid.mbc.net/"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60); return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)
f = {"pageNumber": 0, "pageSize": 100, "productType": "LIVESTREAM", "productSubType": "LIVE_CHANNEL"}
for host in ["api3.shahid.net", "api2.shahid.net"]:
    u = f"https://{host}/proxy/v2.1/product/filter?filter={urllib.parse.quote(json.dumps(f))}&country=SA&language=ar"
    s, b = get(u); out.append(f"== {host} channels: {s} len={len(b)}")
    chans = re.findall(r'"id":(\d+),[^{}]*?"title":"([^"]*)"', b)
    out.append(json.dumps(chans[:200], ensure_ascii=False))
    ids = [i for i, t in chans if re.search(r"العربية|الحدث|Arabiya|Hadath", t)]
    out.append("arabiya ids: " + str(ids))
    if ids:
        now = datetime.datetime.utcnow(); fr = now.strftime("%Y-%m-%dT%H:00:00.000Z"); to = (now + datetime.timedelta(hours=12)).strftime("%Y-%m-%dT%H:00:00.000Z")
        for path in [f"/proxy/v2.1/shahid-epg-api/?csvChannelIds={','.join(ids)}&from={fr}&to={to}&country=SA&language=ar&offset=0&limit=50",
                     f"/proxy/v2.1/epg?channelIds={','.join(ids)}&from={fr}&to={to}"]:
            s, b = get(f"https://{host}{path}"); out.append(f"== epg {path[:40]}: {s} {b[:1200]}")
open("scan/probe_shahid.txt", "w").write("\n".join(out))
