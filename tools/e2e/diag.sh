#!/bin/bash
# Why does the provider answer 461 to our server? (owner, 25 Nov 2026) One request of each kind, with the test
# device's own login, from this runner (not Cloudflare). Prints codes and counts only: no host names, no logins.
set -u
J=$(curl -sS "https://saudi1.1saifsaudi.workers.dev/api/device?code=$CODE&model=test")
read -r PL S U P < <(python3 -c 'import json,sys; o=json.loads(sys.argv[1]); p=o["playlists"][0]; print(p["name"], p["server"], p["user"], p["pass"])' "$J")
echo "::add-mask::$U"; echo "::add-mask::$P"
echo "playlist: $PL"
python3 - "$S" "$U" "$P" <<'P'
import json,sys,urllib.request
s,u,p=sys.argv[1:]
try:
  o=json.load(urllib.request.urlopen(f"{s}/player_api.php?username={u}&password={p}",timeout=30))
  i=o.get("user_info",{})
  print("account:",i.get("status"),"| connections in use",i.get("active_cons"),"of",i.get("max_connections"),"| expires",i.get("exp_date"))
except Exception as e: print("account check failed:",type(e).__name__)
P
ID=$(python3 -c 'import json,sys,urllib.request; s,u,p=sys.argv[1:]; a=json.load(urllib.request.urlopen(f"{s}/player_api.php?username={u}&password={p}&action=get_live_streams&category_id=",timeout=60)); print(a[0]["stream_id"] if a else "")' "$S" "$U" "$P" 2>/dev/null)
[ -z "$ID" ] && ID=1
LOC=$(curl -sS -o /dev/null -w "%{redirect_url}" "$S/live/$U/$P/$ID.m3u8")
H=$(python3 -c 'import sys,urllib.parse as u; print(u.urlparse(sys.argv[1]).hostname or "")' "$LOC"); echo "::add-mask::$H"
echo "relay sends the player to: $(python3 -c 'import sys,urllib.parse as u; p=u.urlparse(sys.argv[1]); print(p.scheme, "port", p.port or 80)' "$LOC")"
echo "the channel from this runner (not Cloudflare), UA Lavf: $(curl -sS -o /dev/null -m 20 -A 'Lavf/60.3.100' -w '%{http_code} after redirects to %{scheme}' -L "$LOC" 2>&1 | head -c 120)"
echo "the same with Safari's UA: $(curl -sS -o /dev/null -m 20 -A 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1' -w '%{http_code}' -L "$LOC" 2>&1 | head -c 80)"
for port in 443 8443 2096 25463; do
  r=$(curl -sS -o /dev/null -m 8 -w "%{http_code}" "https://$H:$port/" 2>&1 | head -c 60 | sed "s/$H/<host>/g")
  echo "https on port $port: $r"
done
