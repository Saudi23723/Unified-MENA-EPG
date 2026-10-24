import urllib.request, os, re, json, datetime
os.makedirs("scan", exist_ok=True); out = []
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "*/*", "Accept-Language": "ar,en"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60); return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)
s, b = get("https://www.bbc.co.uk/schedules")
out.append("== bbc services: " + " | ".join(sorted(set(re.findall(r'href="(?:https://www\.bbc\.co\.uk)?/schedules/(p0[0-9a-z]+)"[^>]*>\s*([^<]{2,60})<', b)))[:120]) if False else "")
svc = sorted(set(re.findall(r'/schedules/(p0[0-9a-z]{6})', b)))
out.append(f"== bbc services {s} {len(svc)}: {svc[:200]}")
for pid in svc[:150]:
    s2, b2 = get(f"https://www.bbc.co.uk/schedules/{pid}")
    t = re.findall(r"<title>([^<]*)", b2)
    out.append(f"{pid}\t{t[:1]}")
for u in ["https://www.alarabiya.net/", "https://www.alhadath.net/", "https://www.bbc.com/arabic"]:
    s, b = get(u)
    links = sorted(set(re.findall(r'https?://[A-Za-z0-9.-]+/[^"\'\s<>]*(?:schedul|epg|guide|programs|برامج|live)[^"\'\s<>]*', b, re.I)))[:30]
    out.append(f"== {u}: {s} len={len(b)} links={links}")
open("scan/probe_bbc2.txt", "w").write("\n".join(out))
