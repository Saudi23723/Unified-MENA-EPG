import sys, os, re; sys.path.insert(0, os.getcwd())
import requests, att_epg
url, user, pw = att_epg.login("XTREAM3")
secrets = [x for x in (url, user, pw, re.sub(r"^https?://", "", url).split(":")[0]) if x]
def clean(t):
    for s in secrets: t = t.replace(s, "***")
    return t
print("scheme", url.split(":")[0], "has port", bool(re.search(r":\d+$", url)), "user len", len(user), "pass len", len(pw))
r = requests.get(url + "/player_api.php", params={"username": user, "password": pw}, headers={"User-Agent": "TiviMate/4.7.0"}, timeout=40)
print("status", r.status_code, "server", clean(r.headers.get("server", "")), "ctype", r.headers.get("content-type"))
print("body:", clean(r.text[:300]).replace("\n", " "))
r = requests.get(url + "/", headers={"User-Agent": "TiviMate/4.7.0"}, timeout=40)
print("root status", r.status_code, clean(r.text[:120]).replace("\n", " "))
