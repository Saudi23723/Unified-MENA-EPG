import urllib.request, os, re, json
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
b = urllib.request.urlopen(urllib.request.Request("https://watch.sportsnet.ca/schedule", headers=UA), timeout=60).read().decode("utf-8", "replace")
m = re.search(r"window\.__data = JSON\.parse\('(.*?)'\);", b, re.S)
raw = m.group(1).encode().decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")
out = []
try:
    d = json.loads(raw)
except Exception as e:
    out.append("parse err " + str(e)); d = {}
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, path + "/" + k)
    elif isinstance(o, list):
        for i, v in enumerate(o[:200]): yield from walk(v, path + f"[{i}]")
    else:
        yield path, o
urls = [(p, v) for p, v in walk(d) if isinstance(v, str) and v.startswith("http") and ("api" in v or "epg" in v.lower() or "schedul" in v.lower())]
out += [f"{p} = {v}" for p, v in urls[:80]]
chans = [(p, v) for p, v in walk(d) if isinstance(v, str) and re.search(r"Sportsnet|SN ?(One|1|360|World)", v)]
out.append("== channel-ish"); out += [f"{p} = {v[:120]}" for p, v in chans[:80]]
out.append("== top keys " + json.dumps({k: list(v.keys())[:40] if isinstance(v, dict) else type(v).__name__ for k, v in d.items()}))
open("scan/probe_sn3.txt", "w").write("\n".join(out))
