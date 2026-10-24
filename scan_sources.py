import urllib.request, urllib.parse, os, re, json, datetime
os.makedirs("scan", exist_ok=True); out = []
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "application/json", "Origin": "https://shahid.mbc.net", "Referer": "https://shahid.mbc.net/"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60); return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)
allc = {}
for page in range(0, 6):
    f = {"pageNumber": page, "pageSize": 100, "productType": "LIVESTREAM", "productSubType": "LIVE_CHANNEL"}
    s, b = get(f"https://api3.shahid.net/proxy/v2.1/product/filter?filter={urllib.parse.quote(json.dumps(f))}&country=SA&language=ar")
    try:
        d = json.loads(b)
    except Exception:
        out.append(f"page {page}: {s} {b[:200]}"); break
    items = (d.get("productList") or {}).get("products") or d.get("products") or []
    out.append(f"page {page}: {len(items)} items keys={list(d.keys())[:8]}")
    for it in items:
        allc[str(it.get("id"))] = it.get("title")
    if not items: break
out.append(json.dumps(allc, ensure_ascii=False))
ids = [i for i, t in allc.items() if t and re.search(r"العربية|الحدث|Arabiya|Hadath|BBC|بي بي سي", t)]
out.append("match: " + json.dumps({i: allc[i] for i in ids}, ensure_ascii=False))
now = datetime.datetime.utcnow(); fr = now.strftime("%Y-%m-%dT%H:00:00.000Z"); to = (now + datetime.timedelta(hours=12)).strftime("%Y-%m-%dT%H:00:00.000Z")
if ids:
    s, b = get(f"https://api3.shahid.net/proxy/v2.1/shahid-epg-api/?csvChannelIds={','.join(ids)}&from={fr}&to={to}&country=SA&language=ar&offset=0&limit=50")
    try:
        for ch in json.loads(b)["items"]:
            out.append(f"{ch['channelId']} {allc.get(ch['channelId'])}: {len(ch['items'])} -> " + " | ".join(x['title'] for x in ch['items'][:6]))
    except Exception as e:
        out.append(f"epg err {s} {b[:300]}")
open("scan/probe_shahid2.txt", "w").write("\n".join(out))
