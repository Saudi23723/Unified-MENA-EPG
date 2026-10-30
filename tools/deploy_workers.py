"""Upload cloudflare/worker2.js to the seven DreamTV relays (Cloudflare API token from the repository secrets).

Each relay keeps its own provider address: it is read from the relay that is running now and put back in the new
code, so no provider address or login is ever written in this repository.
usage: CLOUDFLARE_API_TOKEN=... python tools/deploy_workers.py [names...]
"""
import json
import os
import re
import sys
import urllib.request
import uuid

ACCOUNT = "6ebea2f90132db027f0713f5ca1ffa01"
NAMES = sys.argv[1:] or ["strong", "dream4k", "hydra", "family4k", "argon", "aroma", "up1"]
TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
API = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/workers/scripts/"


def call(method, url, body=None, ctype=None):
    req = urllib.request.Request(url, data=body, method=method, headers={"Authorization": f"Bearer {TOKEN}"})
    if ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    if not TOKEN:
        print("no CLOUDFLARE_API_TOKEN"); return 1
    tpl = open(os.path.join(os.path.dirname(__file__), "..", "cloudflare", "worker2.js"), encoding="utf-8").read()
    bad = 0
    for n in NAMES:
        try:
            cur = call("GET", API + n + "/content/v2").decode("utf-8", "replace")
            prov = re.search(r'const PROVIDER = "([^"]+)"', cur)
            play = re.search(r'const PLAYLIST = "([^"]+)"', cur)
            if not prov or not play:
                print(n, "skipped (not a v2 relay)"); continue
            code = tpl.replace("PROVIDER_ADDRESS", prov.group(1)).replace("PLAYLIST_NAME", play.group(1))
            b = uuid.uuid4().hex
            parts = [f'--{b}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'
                     + json.dumps({"main_module": "worker.js"}) + "\r\n",
                     f'--{b}\r\nContent-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
                     'Content-Type: application/javascript+module\r\n\r\n' + code + f"\r\n--{b}--\r\n"]
            res = json.loads(call("PUT", API + n + "/content", "".join(parts).encode("utf-8"), f"multipart/form-data; boundary={b}"))
            print(n, "deployed" if res.get("success") else f"failed {res.get('errors')}")
            bad += 0 if res.get("success") else 1
        except Exception as e:  # noqa: BLE001
            print(n, "failed", type(e).__name__, getattr(e, "code", ""))
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
