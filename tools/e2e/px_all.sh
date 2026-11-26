#!/bin/bash
# The web player's route (our server /api/px → relay → provider) for EVERY playlist of the test device, one channel
# each, one request each (owner, 25 Nov 2026: "find a solution for Safari"). Prints playlist names and HTTP codes
# only: no logins, no host names.
set -u
SITE=https://saudi1.1saifsaudi.workers.dev
J=$(curl -sS "$SITE/api/device?code=$CODE&model=test")
python3 - "$J" > pls.tsv <<'P'
import json,sys
o=json.loads(sys.argv[1])
for p in o.get("playlists",[]):
    print("\t".join([p.get("name",""),p.get("server",""),p.get("user",""),p.get("pass","")]))
P
while IFS=$'\t' read -r PL S U P; do
  [ -n "${ONLY:-}" ] && [ "$PL" != "$ONLY" ] && continue
  echo "::add-mask::$U"; echo "::add-mask::$P"
  ID=$(curl -sS -m 60 "$S/player_api.php?username=$U&password=$P&action=get_live_streams" | python3 -c 'import json,sys
try:
  a=json.load(sys.stdin); print(next((str(x["stream_id"]) for x in a if "news" in (x.get("name") or "").lower()), str(a[0]["stream_id"]) if a else ""))
except Exception: print("")')
  [ -z "$ID" ] && { echo "$PL: no channel list"; continue; }
  RAW="$S/live/$U/$P/$ID.m3u8"
  ENC=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$RAW")
  echo "   steps: $(curl -sS -m 30 "$SITE/api/px?code=$CODE&dbg=1&u=$ENC" | head -c 300)"
  M=$(curl -sS -m 30 -o m.txt -w "%{http_code}" "$SITE/api/px?code=$CODE&u=$ENC")
  SEG=$(grep -v '^#' m.txt 2>/dev/null | grep -m1 .)
  if [ "$M" = 200 ] && [ -n "$SEG" ]; then
    S2=$(curl -sS -m 30 -o seg.bin -w "%{http_code}" "$SEG"); B=$(stat -c %s seg.bin 2>/dev/null || echo 0)
    echo "$PL: list $M, first piece $S2 ($B bytes)"
  else
    echo "$PL: list $M $(head -c 80 m.txt | tr -dc '[:print:]' | sed "s/$U//g;s/$P//g")"
  fi
  # the second route (Deno Deploy, deno/px.ts), when it is up
  DN=$(curl -sS -m 30 -o dm.txt -w "%{http_code}" "https://saudi1-px.deno.dev/px?code=$CODE&u=$ENC" 2>/dev/null)
  DSEG=$(grep -v '^#' dm.txt 2>/dev/null | grep -m1 .)
  if [ "$DN" = 200 ] && [ -n "$DSEG" ]; then echo "   Deno route: list 200, first piece $(curl -sS -m 30 -o dseg.bin -w '%{http_code}' "$DSEG") ($(stat -c %s dseg.bin 2>/dev/null) bytes)"; else echo "   Deno route: $DN"; fi
  # the same channel straight from this runner (not through Cloudflare), for comparison
  D=$(curl -sS -m 20 -o /dev/null -w "%{http_code}" -L -A "Lavf/60.3.100" "$RAW"); echo "   straight from a server (no Cloudflare): $D"
  sleep 2
done < pls.tsv
