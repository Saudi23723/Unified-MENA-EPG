"""UAE official schedules, round four. Never fails."""
import base64, io, os, re, sys, tarfile
from datetime import datetime, timezone, timedelta
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
        print(f"{name}: {r.status_code} {len(r.content)}B {r.headers.get('content-type','')[:30]} {r.url[:130]}")
        if save and r.status_code == 200:
            keep(name, r.content)
        return r
    except Exception as e:
        print(f"{name}: ERR {str(e)[:140]}")
now = datetime.now(timezone.utc)
# Dubai Media: which json names do the sports / racing / zaman pages' scripts ask for?
for site, page in (("dubaisports", "https://www.dubaisports.ae/content/dubaisports/schedule/1.html"),
                   ("dubaisports2", "https://www.dubaisports.ae/content/dubaisports/schedule/2.html"),
                   ("dubairacing", "https://www.dubairacing.ae/content/dubairacing/ar-ae/home.html"),
                   ("dubaizaman", "https://www.dubaizaman.ae/content/dubaizaman/ar-ae/schedule.html")):
    r = get(site + ".html", page)
    if r is None or r.status_code != 200:
        continue
    host = re.match(r"https://[^/]+", r.url).group(0)
    print("   inline json refs:", sorted(set(re.findall(r"[\w/.-]*\.json", r.text)))[:20])
    for src in sorted(set(re.findall(r'src="(/[^"]+\.js)"', r.text))):
        rj = get(site + src.replace("/", "_"), host + src, save=False)
        if rj is not None and rj.status_code == 200:
            refs = sorted(set(re.findall(r"[\w/.-]*(?:json|Common)[\w/.-]*", rj.text)))
            if refs:
                print("      js refs:", refs[:25])
for c in ["SPT1", "SPT", "SPT3", "SPT0", "SPRT1", "DSPT", "DSP1", "SPORT", "RAC1", "RAC", "RAC3", "RAC0", "RACE",
          "RCE", "DRAC", "ZMN", "ZAMN", "ZMAN", "DZMN", "ZAMAN", "DUBZ", "DUB2", "DUB3", "SAMA2", "NOOR2"]:
    get(f"dm_{c}.json", f"https://www.dubaitv.ae/content/dam/Common/json/{c}.json")
# Sharjah: the programme grid
for q in ({}, {"channel": 8}, {"channel_id": 8}, {"channel": 8, "date": f"{now:%Y-%m-%d}"},
          {"channel_id": 8, "date": f"{now:%Y-%m-%d}"}, {"channel": 8, "day": f"{now:%Y-%m-%d}"}):
    tag = "_".join(f"{k}{v}" for k, v in q.items()) or "bare"
    get(f"sba_grid_{tag}.json", "https://sbauae.faulio.com/api/v1/programgrid", params=q)
get("sba_ch8.json", "https://sbauae.faulio.com/api/v1/channels/8")
get("sba_ch12.json", "https://sbauae.faulio.com/api/v1/channels/12")
# Fujairah: how full is a week of its own schedule?
for d in range(0, 4):
    day = now + timedelta(days=d)
    r = get(f"fuj_{day:%m%d}.html", f"https://www.fujairahtv.ae/schedule-channels-date/1/{day:%Y/%m/%d}")
    if r is not None:
        print("    cards:", r.text.count("المدة"))
tar.close()
blob = base64.b64encode(buf.getvalue()).decode()
print("TAR-BEGIN")
for i in range(0, len(blob), 4000):
    print("T|" + blob[i:i + 4000])
print("TAR-END")
