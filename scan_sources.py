import urllib.request, os, re, json, datetime
os.makedirs("scan", exist_ok=True); out = []
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "*/*"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60); return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)
d = datetime.datetime.utcnow().strftime("%Y-%m-%d")
for ch in ["bbc_one_london", "bbc_news24", "bbc_world_news", "bbc_arabic", "bbc_two_england", "bbc_one_scotland"]:
    s, b = get(f"https://ibl.api.bbc.co.uk/ibl/v1/channels/{ch}/broadcasts?per_page=5")
    out.append(f"== ibl {ch}: {s} {b[:400]}")
s, b = get("https://ibl.api.bbc.co.uk/ibl/v1/channels"); out.append(f"== ibl channels: {s} " + " ".join(re.findall(r'"id":"(bbc_[a-z0-9_]+)"', b)[:80]))
for u in ["https://www.bbc.co.uk/schedules/p00fzl9r", "https://www.bbc.com/arabic/tv-and-radio-schedule", "https://www.bbc.com/arabic/tv",
          "https://www.alarabiya.net/schedule", "https://www.alarabiya.net/programs", "https://www.alhadath.net/schedule", "https://www.alarabiya.net/tv-schedule",
          f"https://www.bbc.co.uk/schedules/p00fzl9r/{d.replace('-','/')}"]:
    s, b = get(u)
    hints = sorted(set(re.findall(r'https?://[A-Za-z0-9.-]+/[A-Za-z0-9./_?=&%-]*(?:schedul|epg|guide|broadcast|programm)[A-Za-z0-9./_?=&%-]*', b, re.I)))[:15]
    out.append(f"== {u}: {s} len={len(b)} title={re.findall(r'<title>([^<]*)', b)[:1]} hints={hints}")
    for w in ["startTime", "start_time", "\"start\"", "broadcast", "schedule"]:
        i = b.find(w)
        if i > 0: out.append(f"   {w}: " + b[max(0,i-150):i+300].replace("\n", " ")); break
open("scan/probe_bbc.txt", "w").write("\n".join(out))
