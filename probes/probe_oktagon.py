"""UAE channels: download each broadcaster's own logo; last guesses at the
Dubai Sports 1 schedule file. Never fails."""
import base64, io, os, sys, tarfile
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/124 Safari/537.36"}
SZ = "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/"
LOGOS = {
 "dubai_tv": "https://www.dubaitv.ae/content/dam/dubaitv/icons/2023/logo.png",
 "sama_dubai": "https://www.samadubai.ae/content/dam/samadubai/icons/2023/samadubai_logo.png",
 "noor_dubai": "https://www.noordubai.com/etc/designs/noordubai/orginal/static/images/logo-noordubai.png",
 "dubai_one": "https://www.dubaione.ae/content/dam/dubaione/icons/logo-310320/400x170.png",
 "dubai_sports": "https://www.dubaisports.ae/content/dam/dubaisports/images/logo.png",
 "dubai_racing": "https://www.dubairacing.ae/content/dam/Common/brands1/dubairacing-logo.png",
 "dubai_racing_wide": "https://www.dubairacing.ae/etc/designs/dubai-racing/orginal/static/images/logo-wide.png",
 "abu_dhabi_tv": SZ + "admnabudhabichannel/active/5053dc59a6720698c26127b27e5e2098.png",
 "al_emarat": SZ + "admnalemarattv/active/2b6092733df431e839de5e8b5acc5170.png",
 "natgeo_ad": SZ + "nationalgeographicabudhabitv/active/28116b613c9c8ccbb1a27a47cc862b6c.png",
 "sharjah_tv": "https://sbauae.faulio.com/storage/mediagallery/cb/85/fullhd_85193bcdcc44114327c4f9ad3c0fc9555c72f501.png",
 "sharqiya_kalba": "https://sbauae.faulio.com/storage/mediagallery/55/38/fullhd_4bfa9ec0919d329eb750401a28b6a2ab4bb1ce52.png",
 "sharjah_2": "https://sbauae.faulio.com/storage/mediagallery/89/14/fullhd_791cecd44950e87d0558b783273de114cf7656f7.png",
}
buf = io.BytesIO(); tar = tarfile.open(fileobj=buf, mode="w:gz")
for name, url in LOGOS.items():
    try:
        r = S.get(url, headers=H, timeout=40)
        print(name, r.status_code, len(r.content), r.headers.get("content-type"))
        if r.status_code == 200:
            info = tarfile.TarInfo(name + ".img"); info.size = len(r.content); tar.addfile(info, io.BytesIO(r.content))
    except Exception as e:
        print(name, "ERR", str(e)[:120])
for c in ["SPT1", "DSC", "DSC1", "SPTS", "SPTS1", "SPORT1", "SPORTS1", "SP1", "SP", "DSPORT", "DSPORTS", "DS",
          "DXS", "DXS1", "SPT1HD", "SPTHD", "SPRT", "SPR1", "SPR", "DUBS", "DSP", "SPO1", "SPO", "DUBSPT", "SPTA"]:
    try:
        r = S.get(f"https://www.dubaitv.ae/content/dam/Common/json/{c}.json", headers=H, timeout=30)
        if r.status_code == 200:
            print("FOUND", c, len(r.content), r.text[:200])
    except Exception:
        pass
tar.close()
blob = base64.b64encode(buf.getvalue()).decode()
print("TAR-BEGIN")
for i in range(0, len(blob), 4000):
    print("T|" + blob[i:i + 4000])
print("TAR-END")
