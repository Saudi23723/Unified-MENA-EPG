import urllib.request, os, re, json, datetime
os.makedirs("scan", exist_ok=True); out = []
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "application/json"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60); return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)
A = "https://production-cdn.d3-rgr-diva.com/api"
chans = {}
def walk(o):
    if isinstance(o, dict):
        if o.get("type") in ("channel", "link") and o.get("id") and re.search(r"sportsnet|sn ", (o.get("title") or "").lower()):
            chans[o["id"]] = (o.get("type"), o.get("title"), o.get("path"))
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
for p in ["/schedule", "/live", "/channels", "/", "/tv-schedule", "/linear"]:
    s, b = get(A + "/page?path=" + p + "&device=web_browser")
    out.append(f"== page {p}: {s} len={len(b)}")
    try: walk(json.loads(b))
    except Exception: pass
    out.append("types: " + " ".join(sorted(set(re.findall(r'"type":"([a-z]+)"', b)))))
out.append("chans: " + json.dumps(chans))
d = datetime.datetime.utcnow().strftime("%Y-%m-%d")
ids = [k for k, v in chans.items() if v[0] == "channel"][:12]
if ids:
    for u in [f"{A}/schedules?channels={','.join(ids)}&date={d}&hour=0&duration=24&intersect=true&device=web_browser",
              f"{A}/schedules?channels={','.join(ids)}&date={d}&hour=0&duration=24"]:
        s, b = get(u); out.append(f"== {u}: {s} len={len(b)}"); out.append(b[:2500])
open("scan/probe_sn5.txt", "w").write("\n".join(out))
