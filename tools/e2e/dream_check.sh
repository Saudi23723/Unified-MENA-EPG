#!/bin/bash
# Dream4k as a viewer gets it (owner, 26 Nov 2026: "did Dream work or not"). The test device's own login, one request
# of each kind. Prints counts and channel names only: no host names, no logins.
set -u
J=$(curl -sS "https://saudi1.1saifsaudi.workers.dev/api/device?code=$CODE&model=test")
read -r PL S U P < <(python3 -c 'import json,sys; o=json.loads(sys.argv[1]); p=[x for x in o["playlists"] if x["name"]=="dream4k"][0]; print(p["name"], p["server"], p["user"], p["pass"])' "$J")
echo "::add-mask::$U"; echo "::add-mask::$P"
echo "playlist: $PL"
echo "relay status: $(curl -sS -m 20 "$S/_status")"
python3 - "$S" "$U" "$P" <<'PY'
import json,sys,urllib.request,re,time
s,u,p=sys.argv[1:]
api=f"{s}/player_api.php?username={u}&password={p}"
def get(a): return json.load(urllib.request.urlopen(urllib.request.Request(api+a,headers={"User-Agent":"Lavf/60.3.100"}),timeout=60))
i=get("").get("user_info",{}); print("login:", "works" if str(i.get("auth"))=="1" else "REFUSED")
cats=get("&action=get_live_categories"); print("live groups:", len(cats))
st=get("&action=get_live_streams"); print("live channels:", len(st))
ev=re.compile(r"PPV|EVENT|ᴘᴘᴠ|ᴇᴠᴇɴᴛ|NBA|NFL|NHL|ESPN\+|DAZN|PEACOCK",re.I)
evc={str(c["category_id"]):c["category_name"] for c in cats if ev.search(c["category_name"] or "")}
print("event groups:", len(evc))
by={}
for x in st:
  if str(x.get("category_id")) in evc: by.setdefault(str(x["category_id"]),[]).append(x["name"])
for c,ns in list(by.items())[:8]:
  print(" ", evc[c], "->", " | ".join(ns[:4]))
for a in ("get_vod_categories","get_series_categories"):
  try: print(a, len(get("&action="+a)))
  except Exception as e: print(a,"failed",type(e).__name__)
PY
ID=$(python3 -c 'import json,sys,urllib.request; s,u,p=sys.argv[1:]; a=json.load(urllib.request.urlopen(urllib.request.Request(f"{s}/player_api.php?username={u}&password={p}&action=get_live_streams",headers={"User-Agent":"Lavf/60.3.100"}),timeout=60)); print(a[0]["stream_id"])' "$S" "$U" "$P")
echo "a channel link: relay answers $(curl -A Lavf/60.3.100 -sS -o /dev/null -w '%{http_code}' "$S/live/$U/$P/$ID.ts")"
echo "the provider's own live list from this runner (one try): $(curl -sS -o /dev/null -m 60 -w '%{http_code}' -A 'Lavf/60.3.100' "$(curl -A Lavf/60.3.100 -sS -o /dev/null -w '%{redirect_url}' "$S/live/$U/$P/$ID.ts" | python3 -c 'import sys,urllib.parse as q; x=q.urlparse(sys.stdin.read()); print(f"{x.scheme}://{x.netloc}")')/player_api.php?username=$U&password=$P&action=get_live_categories")"
O=$(curl -A Lavf/60.3.100 -sS -o /dev/null -w '%{redirect_url}' "$S/live/$U/$P/$ID.ts" | python3 -c 'import sys,urllib.parse as q; x=q.urlparse(sys.stdin.read()); print(f"{x.scheme}://{x.netloc}")'); echo "::add-mask::$O"
echo "the provider's whole live list with this device's login (one try): $(curl -sS -o /tmp/l.json -m 90 -w '%{http_code}' -A 'Lavf/60.3.100' "$O/player_api.php?username=$U&password=$P&action=get_live_streams") · $(python3 -c 'import json; print(len(json.load(open("/tmp/l.json"))), "channels")' 2>/dev/null)"
echo "the same with the names job's old User-Agent: $(curl -sS -o /dev/null -m 90 -w '%{http_code}' -A 'Unified-MENA-EPG' "$O/player_api.php?username=$U&password=$P&action=get_live_categories")"
