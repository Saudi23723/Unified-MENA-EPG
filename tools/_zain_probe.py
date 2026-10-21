import sys, re, requests
sys.path.insert(0, ".")
import att_epg
url, user, pw = att_epg.login("XTREAM2")
secrets = [x for x in (url, user, pw, re.sub(r"^https?://", "", url or "").split(":")[0]) if x]
out = []
for ua in ("TiviMate/4.7.0", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "okhttp/4.9.0"):
    for kw in ({}, {"action": "get_live_categories"}):
        try:
            r = requests.get(url + "/player_api.php", params={"username": user, "password": pw, **kw}, headers={"User-Agent": ua}, timeout=60)
            body = r.text[:300]
            out.append(f"{ua[:12]} {kw or 'auth'} -> {r.status_code} | {body}")
        except Exception as e:
            out.append(f"{ua[:12]} {kw} -> {type(e).__name__}")
try:
    ip = requests.get("https://api.ipify.org", timeout=20).text
    out.append(f"runner ip {ip}")
except Exception: pass
text = "%0A".join(out)
for s in secrets: text = text.replace(s, "***")
print("::notice::" + text[:6000])
