"""UAE broadcasters' own schedule pages: download each as it is served to a
runner and dump them as a tarball, so their structure can be read. Never fails."""
import base64, io, os, re, sys, tarfile, time
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/124 Safari/537.36", "Accept-Language": "ar,en;q=0.8"}
URLS = {
 "dubaitv": "https://www.dubaitv.ae/content/dubaitv/ar-ae/program-schedule.html",
 "samadubai": "https://www.samadubai.ae/content/samadubai/ar-ae/program-schedule.html",
 "samadubai_sched": "https://www.samadubai.ae/content/samadubai/ar-ae/schedule.html",
 "dubaizaman": "https://www.dubaizaman.ae/content/dubaizaman/ar-ae/schedule.html",
 "dubairacing": "https://www.dubairacing.ae/content/dubairacing/ar-ae/schedule/1.html",
 "dubairacing2": "https://www.dubairacing.ae/content/dubairacing/ar-ae/schedule/2.html",
 "noordubai": "https://www.noordubai.com/content/noordubai/ar-ae/tv-schedule.html",
 "dubaione": "https://www.dubaione.ae/content/dubaione/en-ae/schedule.html",
 "dubaione2": "https://www.dubaione.ae/content/dubaione/en-ae/program-schedule.html",
 "dubaisports": "https://www.dubaisports.ae/content/dubaisports/ar-ae/schedule.html",
 "dubaisports2": "https://www.dubaisports.ae/content/dubaisports/ar-ae/program-schedule.html",
 "adtv_en": "https://adtv.ae/en/schedule/null",
 "adtv_ar": "https://adtv.ae/ar/schedule",
 "sba": "https://www.sba.net.ae/",
 "sharjahtv": "https://www.sharjahtv.ae/",
 "fujairah": "https://www.fujairahtv.ae/",
}
buf = io.BytesIO(); tar = tarfile.open(fileobj=buf, mode="w:gz")
for name, url in URLS.items():
    try:
        r = S.get(url, headers=H, timeout=40, allow_redirects=True)
        body = r.content
        times = len(re.findall(rb"\b\d{1,2}:\d{2}\b", body))
        print(f"{name}: {r.status_code} {len(body)}B final={r.url} times={times}")
        info = tarfile.TarInfo(f"{name}.html"); info.size = len(body); tar.addfile(info, io.BytesIO(body))
    except Exception as e:
        print(f"{name}: ERR {str(e)[:150]}")
    time.sleep(1)
tar.close()
blob = base64.b64encode(buf.getvalue()).decode()
print("TAR-BEGIN")
for i in range(0, len(blob), 4000):
    print("T|" + blob[i:i + 4000])
print("TAR-END")
