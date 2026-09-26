"""Every F1 circuit's outline from MultiViewer, printed as one JSON line
per circuit for f1_circuits.json. Never fails."""
import json, os, sys
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
meet = S.get("https://api.openf1.org/v1/meetings?year=2026", timeout=60).json()
keys = {}
for m in meet:
    keys.setdefault(m["circuit_key"], m.get("circuit_short_name"))
extra = {3: "Imola", 55: "Zandvoort", 79: "Portimao", 144: "Baku"}
for k, v in extra.items():
    keys.setdefault(k, v)
for key, name in keys.items():
    got = None
    for year in range(2026, 2017, -1):
        try:
            r = S.get(f"https://api.multiviewer.app/api/v1/circuits/{key}/{year}", timeout=40)
            d = r.json() if r.status_code == 200 else None
        except Exception:
            d = None
        if d and d.get("x"):
            got = (year, d); break
    if not got:
        print("MISS", key, name); continue
    year, d = got
    pts = list(zip(d["x"], d["y"]))
    if len(pts) > 360:
        step = len(pts) / 360
        pts = [pts[int(i * step)] for i in range(360)]
    row = {"key": key, "name": name, "circuit": d.get("circuitName"),
           "year": year, "rotation": d.get("rotation") or 0,
           "corners": [{"n": c["number"], "x": round(c["trackPosition"]["x"]), "y": round(c["trackPosition"]["y"])} for c in d.get("corners") or []],
           "points": [[round(a), round(b)] for a, b in pts]}
    print("CIRCUIT " + json.dumps(row, separators=(",", ":")))
