"""Channel 6: which airline-logo sources answer from a runner; dump the logos
of every carrier at AMM and AUH today as a tarball. Never fails."""
import base64, io, os, sys, tarfile, time
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
import flight_epg
from epg_lib import new_session
S = new_session()
now = datetime.now(timezone.utc)
codes = {}
for code in ("AMM", "AUH"):
    for mode in ("departures", "arrivals"):
        try:
            for r in flight_epg._read(S, code, mode, now, flight_epg.ROUTE_AHEAD):
                f = r["flight"]; num = (f["identification"]["number"]["default"] or "")[:2].upper()
                al = f.get("airline") or {}
                icao = ((al.get("code") or {}).get("icao")) or ""
                if num: codes.setdefault(num, icao)
        except Exception as e:
            print("FAIL read", code, mode, e)
print("carriers", len(codes), sorted(codes))
tar_buf = io.BytesIO(); tar = tarfile.open(fileobj=tar_buf, mode="w:gz")
for iata, icao in sorted(codes.items()):
    for name, url in (("avs", f"https://pics.avs.io/400/160/{iata}@2x.png"),
                      ("fr24", f"https://images.flightradar24.com/assets/airlines/logotypes/{iata}_{icao}.png"),
                      ("airhex", f"https://content.airhex.com/content/logos/airlines_{iata}_350_100_r.png")):
        try:
            r = S.get(url, timeout=20)
            ok = r.status_code == 200 and r.content[:4] == b"\x89PNG"
            print(name, iata, icao, r.status_code, len(r.content), "PNG" if ok else "")
            if ok:
                info = tarfile.TarInfo(f"{name}/{iata}.png"); info.size = len(r.content)
                tar.addfile(info, io.BytesIO(r.content))
        except Exception as e:
            print(name, iata, "ERR", str(e)[:80])
        time.sleep(0.3)
tar.close()
blob = base64.b64encode(tar_buf.getvalue()).decode()
print("TAR-BEGIN")
for i in range(0, len(blob), 4000):
    print("T|" + blob[i:i + 4000])
print("TAR-END")
