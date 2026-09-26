"""UAE official schedules, round three. Never fails."""
import base64, io, json, os, re, sys, tarfile, time
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
import starzplay_epg
S = new_session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/124 Safari/537.36", "Accept-Language": "ar,en;q=0.8"}
buf = io.BytesIO(); tar = tarfile.open(fileobj=buf, mode="w:gz")
def keep(name, body):
    info = tarfile.TarInfo(name); info.size = len(body); tar.addfile(info, io.BytesIO(body))
def get(name, url, save=True, quiet=False, **kw):
    try:
        r = S.get(url, headers=kw.pop("headers", H), timeout=40, **kw)
        if not quiet or r.status_code == 200:
            print(f"{name}: {r.status_code} {len(r.content)}B {r.headers.get('content-type','')[:30]} {r.url[:110]}")
        if save and r.status_code == 200:
            keep(name, r.content)
        return r
    except Exception as e:
        print(f"{name}: ERR {str(e)[:140]}")
# Dubai Media: schedule pages of the other channels, and their data-json-url
for name, url in (("dsports_sched", "https://www.dubaisports.ae/content/dubaisports/schedule.html"),
                  ("dsports_live", "https://www.dubaisports.ae/content/dubaisports/home/_jcr_content/channel-programs.home-live-schedule.html"),
                  ("dracing_sched", "https://www.dubairacing.ae/content/dubairacing/ar-ae/schedule.html"),
                  ("dracing_sched_en", "https://www.dubairacing.ae/content/dubairacing/en-ae/schedule.html"),
                  ("dzaman_widget", "https://www.dubaizaman.ae/content/dubaizaman/ar-ae/jcr:content/liveschedule.schedule-widget.html"),
                  ("done_sched", "https://www.dubaione.ae/content/dubaione/en-ae/schedule.html")):
    r = get(name + ".html", url)
    if r is not None and r.status_code == 200:
        print("    json:", sorted(set(re.findall(r'data-json-url="([^"]+)"', r.text))),
              "links:", sorted(set(re.findall(r'"(/content/[^"]*schedule[^"]*)"', r.text)))[:12])
for c in ["ONE", "DO", "D1", "DSC", "DS", "DSC1", "DSC2", "DSC3", "DSP", "SPORTS", "SPT1", "SPT2", "DS1", "DS2", "DS3",
          "DRC1", "DRC2", "DRC3", "DR", "RAC", "RAC1", "RAC2", "RACING", "DRACING", "ZMN", "ZMAN", "DZ", "ZAMAN", "DUBAIZAMAN",
          "DONE", "DONETV", "ONETV", "DOTV", "DUB1", "DUB2", "SAMA1", "DUBAIRACING", "DUBAISPORTS", "DUBAIONE"]:
    for host in ("www.dubaitv.ae", "www.dubaisports.ae", "www.dubairacing.ae"):
        get(f"dm_{host.split('.')[1]}_{c}.json", f"https://{host}/content/dam/Common/json/{c}.json", quiet=True)
# STARZPLAY: every channel, every category
now = datetime.now(timezone.utc)
for lang in ("en", "ar"):
    chans = starzplay_epg.fetch_all_channels(S, now, lang)
    keep(f"starz_{lang}.json", json.dumps(chans, ensure_ascii=False).encode())
    print(f"starz {lang}: {len(chans)}")
    for ch in chans:
        ev = ch.get("events") or ch.get("epg") or ch.get("programs") or []
        print("   ", ch.get("slug"), "|", ch.get("title") or ch.get("name"), "|", ch.get("category"), "|",
              ch.get("genres"), "|", len(ev), "|", (ch.get("logo") or ch.get("image") or "")[:90])
# Sharjah (faulio): keep the app bundle, and try the usual paths
for js in ("34a6549.modern.js", "85fcb42.js"):
    get("sba_" + js, "https://www.sba.net.ae/_nuxt/" + js)
for path in ("channels", "v1/channels", "live", "v1/live", "epg", "v1/epg", "v1/tv/channels", "channel/list",
             "v1/channel", "v2/channels", "schedule", "v1/schedule"):
    get("sba_api_" + path.replace("/", "_") + ".json", "https://sbauae.faulio.com/api/" + path, quiet=True)
# Fujairah: one day page, raw
get("fuj_day.html", f"https://www.fujairahtv.ae/schedule-channels-date/1/{now:%Y/%m/%d}")
tar.close()
blob = base64.b64encode(buf.getvalue()).decode()
print("TAR-BEGIN")
for i in range(0, len(blob), 4000):
    print("T|" + blob[i:i + 4000])
print("TAR-END")
