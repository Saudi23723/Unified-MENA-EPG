"""Today's names for a playlist whose provider refuses Cloudflare (Strong, owner 28 Oct 2026).

Reads the provider's live list ONCE with the login kept in GitHub secrets (never printed, never written) and
writes only a small patch the DreamTV relay applies, the same one the relay builds itself for the other playlists:
    {"t": ms, "n": {stream_id: event name}, "i": {stream_id: logo}, "add": {category_id: [new channels]}, "gone": [ids]}

usage: PROVIDER_HOST=... PROVIDER_USER=... PROVIDER_PASS=... python tools/live_patch.py strong out/strong.json
Exit 0 with a patch; exit 3 when the provider refuses (the workflow then switches itself off).
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# same rule as the relay's EVENT_GROUP (cloudflare/worker2.js)
EVENT_GROUP = re.compile(
    r"^(?!.*24/7)(?:.*(PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\+|TSN\+|SN\+|PEACOCK|PARAMOUNT|CUP GAMES|NFL SPORTS)|STAN|MAX|SOCCER|DAZN)$"
    r"|^(?!.*24/7).*(PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\+|TSN\+|SN\+|PEACOCK|PARAMOUNT|CUP GAMES|NFL SPORTS|ᴘᴘᴠ|ᴇᴠᴇɴᴛ|ᴱᵛᵉⁿᵗ|NBA PASS|DAZN|STAN\b|SOCCER)",
    re.I)


def clean(n):
    return re.sub(r"\s+", " ", re.sub(r"[ⓧ§]", "", str(n or ""))).strip()


def main(playlist, out):
    host = os.environ.get("PROVIDER_HOST", "").rstrip("/")
    user, pw = os.environ.get("PROVIDER_USER", ""), os.environ.get("PROVIDER_PASS", "")
    # or one secret with the whole playlist link: http://host/get.php?username=..&password=..&type=m3u_plus
    link = os.environ.get("PROVIDER_URL", "").strip()
    if link and not (user and pw):
        u = urllib.parse.urlsplit(link)
        q0 = urllib.parse.parse_qs(u.query)
        host = f"{u.scheme}://{u.netloc}"
        user, pw = (q0.get("username") or [""])[0], (q0.get("password") or [""])[0]
        if not (user and pw):  # http://host/live/user/pass/... style
            parts = [x for x in u.path.split("/") if x]
            if len(parts) >= 3 and parts[0] in ("live", "movie", "series"):
                user, pw = parts[1], parts[2]
    if not (host and user and pw):
        print("login secrets not set - nothing done")
        return 0
    q = urllib.parse.urlencode({"username": user, "password": pw, "action": "get_live_streams"})
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{host}/player_api.php?{q}",
                                                           headers={"User-Agent": "Unified-MENA-EPG"}), timeout=90) as r:
            live = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"provider answered {e.code}")
        return 3 if e.code in (401, 403) else 1
    except Exception as e:  # noqa: BLE001 - never print the URL (it holds the login)
        print(f"provider not reachable ({type(e).__name__})")
        return 1
    if not isinstance(live, list) or not live:
        print("provider sent an empty list")
        return 1
    d = os.path.join(ROOT, "xtream", playlist)
    mine = json.load(open(os.path.join(d, "live_streams.json"), encoding="utf-8"))
    cats = json.load(open(os.path.join(d, "live_categories.json"), encoding="utf-8"))
    ev = {str(c["category_id"]) for c in cats if EVENT_GROUP.search(c.get("category_name") or "")}
    now = {str(x["stream_id"]): x for x in live}
    ours = {str(x["stream_id"]): x for x in mine}
    weak = lambda x: not x.get("stream_icon") or str(x["stream_icon"]).endswith("#weak")
    n, i = {}, {}
    for x in mine:
        p = now.get(str(x["stream_id"]))
        if not p:
            continue
        if str(x["category_id"]) in ev and p.get("name"):
            nm = clean(p["name"])
            if nm and nm != x["name"]:
                n[str(x["stream_id"])] = nm
        if weak(x) and p.get("stream_icon"):
            i[str(x["stream_id"])] = p["stream_icon"]
    by_cat = {}
    for x in live:
        by_cat.setdefault(str(x.get("category_id")), []).append(x)
    add = {}
    for xs in by_cat.values():
        known = [x for x in xs if str(x["stream_id"]) in ours]
        if len(known) < max(2, len(xs) / 2):
            continue
        votes = {}
        for x in known:
            g = str(ours[str(x["stream_id"])]["category_id"])
            votes[g] = votes.get(g, 0) + 1
        g = max(votes, key=votes.get)
        for x in xs:
            if str(x["stream_id"]) in ours or not x.get("name"):
                continue
            add.setdefault(g, []).append({"stream_id": x["stream_id"], "name": clean(x["name"]),
                                          "stream_icon": x.get("stream_icon") or "", "epg_channel_id": None})
    gone = [x["stream_id"] for x in mine if str(x["stream_id"]) not in now]
    patch = {"t": int(time.time() * 1000), "n": n, "i": i, "add": add, "gone": gone if len(gone) < len(mine) / 3 else []}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(patch, open(out, "w", encoding="utf-8"), ensure_ascii=True, separators=(",", ":"))
    print(f"{playlist}: {len(n)} event names, {len(i)} logos, {sum(len(v) for v in add.values())} new, {len(patch['gone'])} removed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
