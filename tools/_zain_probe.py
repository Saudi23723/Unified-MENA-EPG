import sys, os; sys.path.insert(0, os.getcwd())
import requests
from datetime import datetime, timezone, timedelta
import att_epg, every_name as en, playlist_match as pm
now = datetime.now(timezone.utc)
floor, ceiling = now - timedelta(hours=2), now + timedelta(days=1)
s = requests.Session()
owner = {}
for src, (cc, marks) in en.COUNTRIES.items():
    names = {}
    rows = att_epg.read_source(s, src, lambda c: True, floor, ceiling,
                               lambda cid, ns: names.setdefault(cid, ns))
    print(src, "channels with rows:", len(rows), "of", len(names))
    for cid in rows:
        for n in names.get(cid, []):
            for f in en.forms(n, marks):
                owner.setdefault(f.casefold(), set()).add(f"{src}:{cid}")
want = ["US: USA NETWORK", "US: USA NETWORK 4K", "US: USA NETWORK WEST", "US: FOX SPORTS 1", "US: ESPN", "US: ESPN 2", "US: BET", "US: TBS", "US: TNT", "US: CNBC", "US: BRAVO", "US: FOX SOCCER PLUS", "US: TRUTV", "US: TRU TV",
        "BEIN SPORTS 1", "BEIN SPORTS 2", "BEIN SPORTS 3", "RMC SPORT 1", "RMC SPORT 2", "CANAL+ PL", "TF1", "FRANCE 2", "FRANCE 3", "FRANCE 4", "FRANCE 5", "M6", "ARTE", "W9", "C8", "TF1 SERIES", "6TER", "TFX", "SYFY", "ACTION", "13 EMERUE", "TEVA", "RTL 9", "CANAL+", "CANAL+ CINEMA", "CANAL+ KIDS", "CANAL+ SPORT",
        "SP: RMC SPORT 1", "SP: RMC SPORT 2", "SP: BEIN SPORTS 1", "CANAL+ SPORT 1", "CANAL+ SPORT 2", "CANAL+ SPORT 3", "SP: CANAL+ PL", "SP: RMC SPORT LIVE 5", "SP: OL TV", "SP: EUROSPORT 1", "SP: EUROSPORT 2",
        "FOX SPORTS 501", "FOX SPORTS 503", "FOX SPORTS 506", "KAYO - ESPN 1", "ESPN 1", "ESPN 2", "KAYO - FOX SPORTS 506", "AL JAZEERA (NZ)", "CHANNEL 9 SYDNEY", "RACING", "FOX SPORTS NEWS", "SKY NEWS", "SKY RACING 1"]
for w in want:
    o = owner.get(w.casefold())
    print(f"  {w:24} {'MISSING' if not o else ('AMBIG ' if len({x.split(':')[0] for x in o}) > 1 else '') + ', '.join(sorted(o))[:120]}")
# French channel names in FR1, to learn its spellings
names = {}
att_epg.read_source(s, "FR1", lambda c: False, floor, ceiling, lambda cid, ns: names.setdefault(cid, ns))
print("FR1 ids:", ", ".join(sorted(names)[:200]))
