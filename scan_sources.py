import urllib.request, os, re, json, traceback
os.makedirs("scan", exist_ok=True); out = []
try:
    UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
    b = urllib.request.urlopen(urllib.request.Request("https://watch.sportsnet.ca/schedule", headers=UA), timeout=60).read().decode("utf-8", "replace")
    t = b.replace("\\\\u002F", "/").replace("\\u002F", "/")
    urls = sorted(set(re.findall(r'https?://[A-Za-z0-9.-]+[A-Za-z0-9./_?=&%{}-]*', t)))
    out.append("== hosts: " + " | ".join(sorted(set(re.findall(r'https?://([A-Za-z0-9.-]+)', t)))))
    out += [u for u in urls if re.search(r'api|epg|schedul|listing|service', u, re.I)][:80]
    for w in ["\"services\"", "serviceUrl", "rocket", "\"epg\"", "channel_id", "\"channels\"", "SN1", "Sportsnet One", "SPORTSNET ONE"]:
        i = t.find(w); out.append(f"== {w} @{i}: " + (t[max(0, i-200):i+500].replace("\n", " ") if i >= 0 else ""))
except Exception:
    out.append(traceback.format_exc())
open("scan/probe_sn3.txt", "w").write("\n".join(out))
