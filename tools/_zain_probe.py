import sys, os; sys.path.insert(0, os.getcwd())
import requests, att_epg
for pre in ("XTREAM2", "XTREAM3"):
    url, user, pw = att_epg.login(pre)
    auth = {"username": user, "password": pw}
    for path, extra in (("/player_api.php", {}), ("/get.php", {"type": "m3u_plus", "output": "ts"}), ("/xmltv.php", {})):
        for ua in ("TiviMate/4.7.0", "okhttp/4.12.0", "VLC/3.0.20 LibVLC/3.0.20", "IPTVSmartersPro", "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"):
            try:
                r = requests.get(url + path, params={**auth, **extra}, headers={"User-Agent": ua}, timeout=40, stream=True)
                head = r.raw.read(200, decode_content=True)
                print(pre, path, ua[:14], r.status_code, len(head), head[:20].replace(b"\n", b" ") if r.status_code == 200 else b"")
            except Exception as e:
                print(pre, path, ua[:14], "ERR", type(e).__name__)
