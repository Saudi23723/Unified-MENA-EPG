"""Movies and series for a playlist whose provider refuses the Cloudflare relay (Dream4k, Strong; 28 Oct 2026).

Reads the provider's movie / series groups and lists ONCE with the login from the GitHub secrets (never printed,
never written), applies the owner's order file (xtream/<playlist>/vod_order.json, series_order.json: the same
"tidy" / "only" / "first" / "hide" / "visible" rules as the relay) and writes what the relay then serves as is:
    <out>/vod_categories.json, <out>/series_categories.json, <out>/vod/<category_id>.json, <out>/series/<category_id>.json,
    <out>/vod_streams.json, <out>/series.json
Hidden groups' titles are left out. JSON is ASCII-only (\\u escapes), as DreamTV needs.

usage: PROVIDER_URL=... python tools/vod_patch.py dream4k _patch/dream4k
exit 0 = written, 3 = refused, 1 = other failure (nothing written)
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def login():
    host = os.environ.get("PROVIDER_HOST", "").rstrip("/")
    user, pw = os.environ.get("PROVIDER_USER", ""), os.environ.get("PROVIDER_PASS", "")
    link = os.environ.get("PROVIDER_URL", "").strip()
    if link and not (user and pw):
        u = urllib.parse.urlsplit(link)
        q = urllib.parse.parse_qs(u.query)
        host, user, pw = f"{u.scheme}://{u.netloc}", (q.get("username") or [""])[0], (q.get("password") or [""])[0]
    return host, user, pw


def get(host, user, pw, action):
    q = urllib.parse.urlencode({"username": user, "password": pw, "action": action})
    with urllib.request.urlopen(urllib.request.Request(f"{host}/player_api.php?{q}",
                                                       headers={"User-Agent": "Unified-MENA-EPG"}), timeout=180) as r:
        return json.load(r)


def tidy(n):
    n = re.sub(r"^\s*\|[A-Z]{2,6}\|\s*✪?\s*", "", str(n or "")).replace("ـ", "")
    n = re.sub(r"\s*\[(\d{3,4}p)\]\s*$", "", re.sub(r"^\s*[A-Z]{2,6}\s*:\s*", "", n), flags=re.I)
    return re.sub(r"\s+", " ", n).strip()


def arrange(cats, want):
    """The relay's rules (cloudflare/worker2.js groups())."""
    if want.get("tidy"):
        cats = [dict(c, category_name=tidy(c.get("category_name"))) for c in cats]
    vis = want.get("visible") or []
    pos = {(tidy(n) if want.get("tidy") else str(n).strip()): i for i, n in enumerate(vis)}
    if want.get("only"):
        cats = [c for c in cats if str(c.get("category_name") or "").strip() in pos]
    first = [re.compile(f, re.I) for f in want.get("first") or []]
    hide = [re.compile(f, re.I) for f in want.get("hide") or []]
    if hide:
        cats = [c for c in cats if not any(r.search(str(c.get("category_name") or "")) for r in hide)]
    def lead(n):
        for i, r in enumerate(first):
            if r.search(n):
                return i
        return len(first)
    order = sorted(enumerate(cats), key=lambda t: (lead(str(t[1].get("category_name") or "").strip()) * 10**7
                                                   + pos.get(str(t[1].get("category_name") or "").strip(), 10**6), t[0]))
    return [c for _, c in order]


def main(playlist, out):
    host, user, pw = login()
    if not (host and user and pw):
        print("login secrets not set - nothing done")
        return 0
    res = {}
    try:
        for kind, cat_action, list_action in (("vod", "get_vod_categories", "get_vod_streams"),
                                              ("series", "get_series_categories", "get_series")):
            res[kind] = (get(host, user, pw, cat_action), get(host, user, pw, list_action))
    except urllib.error.HTTPError as e:
        print(f"provider answered {e.code}")
        return 3 if e.code in (401, 403) else 1
    except Exception as e:  # noqa: BLE001 - never print the URL (it holds the login)
        print(f"provider not reachable ({type(e).__name__})")
        return 1
    dump = lambda o, p: (os.makedirs(os.path.dirname(p), exist_ok=True),
                         json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=True, separators=(",", ":")))
    for kind, (cats, items) in res.items():
        if not isinstance(cats, list) or not isinstance(items, list):
            print(f"{kind}: unexpected answer")
            return 1
        f = os.path.join(ROOT, "xtream", playlist, "vod_order.json" if kind == "vod" else "series_order.json")
        want = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        shown = arrange(cats, want)
        keep = {str(c.get("category_id")) for c in shown}
        items = [x for x in items if str(x.get("category_id")) in keep]
        dump(shown, os.path.join(out, f"{kind}_categories.json"))
        dump(items, os.path.join(out, "vod_streams.json" if kind == "vod" else "series.json"))
        by = {}
        for x in items:
            by.setdefault(str(x.get("category_id")), []).append(x)
        for cid in keep:
            dump(by.get(cid, []), os.path.join(out, kind, f"{cid}.json"))
        print(f"{playlist} {kind}: {len(shown)} of {len(cats)} groups, {len(items)} titles")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
