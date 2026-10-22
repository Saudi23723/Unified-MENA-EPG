import sys, os, re, time, collections; sys.path.insert(0, os.getcwd())
import requests
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Safari/537.36"
pat = re.compile(r"سوري|سما|لنا|إخبارية|الاخبارية|حلب|شام|syria|sama|lana|halab|sham|ikhbar|اليوم|غوار|المشرق|زنوبيا|تلاقي|نور|دراما", re.I)
codes = collections.Counter()
for i in range(1090, 1460):
    for attempt in range(3):
        try:
            r = s.get(f"https://elcinema.com/ar/tvguide/{i}/", timeout=40)
        except Exception:
            time.sleep(3); continue
        if r.status_code == 429:
            time.sleep(10); continue
        break
    codes[r.status_code] += 1
    if r.status_code == 200:
        t = re.search(r"<title>([^<]*)</title>", r.text); t = t.group(1) if t else ""
        if pat.search(t): print("HIT", i, t[:70], r.text.count('class="boxed-category-'), flush=True)
    time.sleep(0.7)
print(dict(codes))
