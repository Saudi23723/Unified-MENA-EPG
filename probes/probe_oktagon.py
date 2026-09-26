"""UAE official schedules, round two: Dubai Media's own JSON files, the
STARZPLAY (ADMN) channel list in every category, dubaiplus.net's epg, the
Sharjah Broadcasting Authority's app bundle, and Fujairah TV's schedule.
Dumps what it reads as a tarball. Never fails."""
import base64, io, json, os, re, sys, tarfile, time
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/124 Safari/537.36", "Accept-Language": "ar,en;q=0.8"}
buf = io.BytesIO(); tar = tarfile.open(fileobj=buf, mode="w:gz")
def keep(name, body):
    info = tarfile.TarInfo(name); info.size = len(body); tar.addfile(info, io.BytesIO(body))
def get(name, url, save=True, **kw):
    try:
        r = S.get(url, headers=H, timeout=40, **kw)
        print(f"{name}: {r.status_code} {len(r.content)}B {r.headers.get('content-type','')[:40]} {r.url[:120]}")
        if save and r.status_code == 200:
            keep(name, r.content)
        return r
    except Exception as e:
        print(f"{name}: ERR {str(e)[:140]}")
# 1. Dubai Media JSON files, on every Dubai Media host
codes = ["DUB", "SAMA", "NOOR", "ONE", "DONE", "DUBAIONE", "DO", "DS1", "DS2", "DS3",
         "DSP1", "DSP2", "DUBAISPORTS1", "DUBAISPORTS2", "SPORTS1", "SPORTS2",
         "DR1", "DR2", "DR3", "DRC", "RACING1", "RACING2", "RACING", "DZ", "ZAMAN",
         "DUBAIZAMAN", "DUBAI", "DTV"]
for c in codes:
    get(f"dm_{c}.json", f"https://www.dubaitv.ae/content/dam/Common/json/{c}.json")
    time.sleep(0.3)
# 2. Pages of the other Dubai Media sites, to find their own json names
for name, url in (("dubaisports_home", "https://www.dubaisports.ae/"),
                  ("dubairacing_home", "https://www.dubairacing.ae/"),
                  ("dubaizaman_home", "https://www.dubaizaman.ae/"),
                  ("dubaione_s2", "https://www.dubaione.ae/content/dubaione/en-ae/schedule.2.html"),
                  ("dubaiplus", "https://www.dubaiplus.net/epg?channel=702096936062"),
                  ("fujairah_schedule", "https://www.fujairahtv.ae/schedule")):
    get(name + ".html", url)
# 3. STARZPLAY, every category
API = "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"
now = int(datetime.now(timezone.utc).timestamp())
for lang in ("en", "ar"):
    chans = []
    for page in range(1, 16):
        try:
            r = S.get(API, params={"category": "all", "lang": lang, "page": page, "limit": 40,
                                   "from": now - 3600, "to": now + 86400}, timeout=40)
            d = r.json()
        except Exception as e:
            print("starz ERR", e); break
        items = d.get("data") or d.get("channels") or d
        if isinstance(items, dict):
            items = items.get("channels") or items.get("items") or []
        if not items:
            break
        chans += items
        if len(items) < 40: break
    keep(f"starz_{lang}.json", json.dumps(chans, ensure_ascii=False).encode())
    print(f"starz {lang}: {len(chans)} channels")
    for ch in chans:
        print("   ", ch.get("slug") or ch.get("id"), "|", ch.get("title") or ch.get("name"), "|",
              ch.get("category"), "|", len(ch.get("events") or ch.get("programs") or []))
# 4. SBA app bundles -> API endpoints
r = get("sba_index.html", "https://www.sba.net.ae/")
if r is not None:
    for js in re.findall(r'src="(/_nuxt/[^"]+\.js)"', r.text)[:8]:
        rj = get("sba" + js.replace("/", "_"), "https://www.sba.net.ae" + js, save=False)
        if rj is not None:
            hits = sorted(set(re.findall(r'["\'`](https?://[^"\'`\s]{6,120}|/api/[^"\'`\s]{2,120})["\'`]', rj.text)))
            print("   endpoints:", hits[:60])
tar.close()
blob = base64.b64encode(buf.getvalue()).decode()
print("TAR-BEGIN")
for i in range(0, len(blob), 4000):
    print("T|" + blob[i:i + 4000])
print("TAR-END")
