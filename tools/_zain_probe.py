import sys, os, re; sys.path.insert(0, os.getcwd())
import requests, concurrent.futures as cf
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Safari/537.36"
def get(i):
    try:
        r = s.get(f"https://elcinema.com/ar/tvguide/{i}/", timeout=40)
        t = re.search(r"<title>([^<]*)</title>", r.text)
        rows = r.text.count('class="boxed-category-')
        return i, r.status_code, (t.group(1) if t else "")[:70], rows
    except Exception as e:
        return i, "ERR", type(e).__name__, 0
with cf.ThreadPoolExecutor(8) as ex:
    res = list(ex.map(get, range(1090, 1460)))
pat = re.compile(r"سوري|سما|لنا|إخبارية|الاخبارية|حلب|شام|syria|sama|lana|halab|sham|ikhbar|اليوم|غوار|المشرق|زنوبيا|تلاقي|الأولى|نور", re.I)
for i, st, t, n in res:
    if st == 200 and pat.search(t): print("HIT", i, t, n)
print("ok pages", sum(1 for x in res if x[1] == 200))
