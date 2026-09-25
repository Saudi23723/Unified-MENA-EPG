"""Every Sport TV row that mentions UFC/BJJ/jiu-jitsu or a sport word the
reader does not map, from a runner. Never fails."""
import json, os, re, sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
import sporttv_pt as st
from epg_lib import new_session, fetch, norm
S = new_session()
unmapped = Counter()
for cid, slug, shown in st.CHANNELS if hasattr(st, "CHANNELS") else []:
    try:
        got = fetch(S, f"{st.BASE}/live/canal/{cid}/{slug}")
        table = json.loads(st.biggest_json(got.text)); at = st.follower(table)
    except Exception as exc:
        print("FAIL", shown, exc); continue
    for row in table:
        if not (isinstance(row, dict) and "tipoEmissao" in row):
            continue
        ev = at(row.get("evento")) or {}
        name = (ev.get("nome") or "") if isinstance(ev, dict) else ""
        fixture = norm(str(at(row.get("descricao")) or ""))
        mode = at(row.get("modalidade")) or {}
        word = (mode.get("nomeModalidade") if isinstance(mode, dict) else None) or st.split_event(norm(str(name)))[1]
        when = at(row.get("data"))
        t = datetime.fromtimestamp(when/1000, tz=timezone.utc).strftime("%d %H:%M") if isinstance(when, int) else when
        canal = st.channel_of(at(row.get("canal")))
        if str(word).strip().upper() not in st.A_SPORT:
            unmapped[str(word)] += 1
        if re.search(r"ufc|bjj|jiu|jitsu|grappl|luta|combat", f"{name} {fixture} {word}", re.I):
            print(f"ROW page={shown} canal={canal} {t} tipo={at(row.get('tipoEmissao'))} word={word!r} name={name!r} fixture={fixture!r} dur={at(row.get('duracao'))}")
print("UNMAPPED", unmapped.most_common(30))
