import sys, os, re; sys.path.insert(0, os.getcwd())
import requests
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Safari/537.36"
seen = {}
for url in ("https://elcinema.com/ar/tvguide/", "https://elcinema.com/ar/tvguide/?country=sy", "https://elcinema.com/ar/tvguide/channels/", "https://elcinema.com/en/tvguide/"):
    try:
        r = s.get(url, timeout=60); print(url, r.status_code, len(r.text))
        for cid, name in re.findall(r'href="/(?:ar|en)/tvguide/(\d+)/"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,60})', r.text):
            seen.setdefault(cid, name.strip())
    except Exception as e:
        print(url, "ERR", type(e).__name__)
print(len(seen))
pat = re.compile(r"سوري|سما|لنا|الإخبارية|حلب|شام|الدراما|syria|sama|lana|halab|sham|drama|ikhbar|الأولى|الثانية|اليوم|غوار|روجافا|المشرق|الفضائية السورية|زنوبيا", re.I)
print("; ".join(f"{k}={v}" for k, v in seen.items() if pat.search(v)))
print("ALL:", "; ".join(f"{k}={v}" for k, v in list(seen.items())[:400]))
