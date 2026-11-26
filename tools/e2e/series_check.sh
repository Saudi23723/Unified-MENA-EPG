#!/bin/bash
# The owner's favourite series on his playlist: when each one's newest episode came out (26 Nov 2026). Names and dates only.
set -u
J=$(curl -sS "https://saudi1.1saifsaudi.workers.dev/api/device?code=$CODE&model=test")
read -r PL S U P < <(python3 -c 'import json,sys; o=json.loads(sys.argv[1]); p=[x for x in o["playlists"] if x["name"]==sys.argv[2]][0]; print(p["name"], p["server"], p["user"], p["pass"])' "$J" "$WANT")
echo "::add-mask::$U"; echo "::add-mask::$P"; echo "playlist: $PL"
python3 - "$S" "$U" "$P" <<'PY'
import json,sys,urllib.request,datetime,re
s,u,p=sys.argv[1:]
def get(a): return json.load(urllib.request.urlopen(urllib.request.Request(f"{s}/player_api.php?username={u}&password={p}"+a,headers={"User-Agent":"Lavf/60.3.100"}),timeout=90))
want=["عبر الموت","Yeralti","Yeraltı","دافنينه سوا","Tulsa King","MobLand","Mehmed: Fetihler","Kin"]
allx=get("&action=get_series")
def d(t):
  try: return datetime.datetime.fromtimestamp(int(t),datetime.UTC).strftime("%Y-%m-%d %H:%M")
  except: return "-"
for w in want:
  hits=[x for x in allx if w.lower() in (x.get("name") or "").lower()][:3]
  for x in hits:
    i=get(f"&action=get_series_info&series_id={x['series_id']}")
    lm=(i.get("info") or {}).get("last_modified")
    eps=i.get("episodes") or {}
    best=(0,"")
    if isinstance(eps,dict):
      for sn,a in eps.items():
        for e in a or []:
          t=int(e.get("added") or 0)
          if t>best[0]: best=(t,f"S{sn} E{e.get('episode_num')}")
    print(f"{x['series_id']:>7} | {x['name'][:45]:45} | list last_modified {d(x.get('last_modified'))} | info last_modified {d(lm)} | newest episode {best[1]} added {d(best[0])}")
PY
