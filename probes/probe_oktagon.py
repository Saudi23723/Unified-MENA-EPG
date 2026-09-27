"""Download the original logos of the STARZPLAY Arab channels. Never fails."""
import base64, io, os, sys, tarfile
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
LOGOS = {
 "rotanaclassic": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/rotanaclassic/active/05a3c50c26e3e404d3a7e56244fb7013.png",
 "rotanacomedy": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/rotanacomedy/active/c30fba551543a57259a2d90338ab3df0.png",
 "rotanadrama": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/rotanadrama/active/94a2fae0a57c87b45b17f7ff2e4d8cd6.png",
 "rotanakhaleejiah": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/rotanakhaleejiah/active/dcb462c1b2beb45e46627850f23b98cc.png",
 "rotanacinemaksa": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/rotanacinemaksa/active/f5eac282ac0d1b54d7ec9e8bc3ff0ee0.png",
 "rotanacinemaegypt": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/rotanacinemaegypt/active/bdfeccb2a06631affbc6c40489ef8a05.png",
 "saudionehd": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/saudione-active.png",
 "lbcsat": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/lbcsat/active/030caf0d1d289752808053bf531b1a8f.png",
 "kanalddrama": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/kanalddrama/active/d1f21ca8367d4176212f2b5573950418.png",
 "zeealwan": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/zeealwan-active.png",
 "zeeaflam": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/zeeaflam-active.png",
 "mbcpluselife": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/mbcpluselife-active.png",
 "alwoustaaldhaid": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/alwoustaaldhaid/active/c5c38ed9b3be97200d47dfcc5914221d.png",
 "alhadath": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/alhadath-active.png",
 "alarabiyabusiness": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/alarabiyabusiness-active.png",
 "cnbcarabiya": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/cnbc-active.png",
 "cnninternational": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/cnninternational/active/a214e2ce83044afc7df54bad50236dbc.png",
 "spacetoon": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/spacetoon/active/49f3866d8762fa3a0ee59cf27d218550.png",
 "cartoonnetworkarabic": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/cartoonnetworkarabic/active/93e98df5ba32fbc19119bd5257ad5011.png",
 "twommonde": "https://starzplay-img-prod-ssl.akamaized.net/prd-peg-data/default/images/logos/live/v2/2mmondetv-active.png"
}
buf = io.BytesIO(); tar = tarfile.open(fileobj=buf, mode="w:gz")
for name, url in LOGOS.items():
    try:
        r = S.get(url, timeout=40)
        print(name, r.status_code, len(r.content))
        if r.status_code == 200:
            info = tarfile.TarInfo(name + ".img"); info.size = len(r.content); tar.addfile(info, io.BytesIO(r.content))
    except Exception as e:
        print(name, "ERR", str(e)[:120])
tar.close()
blob = base64.b64encode(buf.getvalue()).decode()
print("TAR-BEGIN")
for i in range(0, len(blob), 4000):
    print("T|" + blob[i:i + 4000])
print("TAR-END")
