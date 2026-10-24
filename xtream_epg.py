#!/usr/bin/env python3
"""Xtream-style data for the DreamTV relays (cloudflare/worker.js).

DreamTV shows a guide only for Xtream logins, from the server's get_simple_data_table answer.
The relay answers from files built here. Names only: no links or logins anywhere.

Input  xtream/<playlist>/channels.json  [{stream_id, name, group, epg}]
       epg = "<id>" or "u:<id>"  -> unified_mena_epg.xml (this repo)
             "e:<id>"            -> reserved for an approved public source (none yet)
Output (main branch, small, change rarely)
       xtream/<playlist>/live_categories.json, live_streams.json, cat/<category_id>.json
       xtream/epg/<id>.json      guide for unified ids (kept for the first Hydra relay)
Output (_data/, published to the xtream-data branch with no history)
       epg/u/<id>.json, epg/e/<id>.json   {"epg_listings": [...]}, 3 h back, 36 h ahead
       map/<playlist>/<n>.json            {stream_id: "u/<id>"}, n = stream_id % 256
"""
import base64, datetime, glob, html, json, os, re, shutil

SRC = "unified_mena_epg.xml"
now = datetime.datetime.now(datetime.timezone.utc)
lo, hi = now - datetime.timedelta(hours=3), now + datetime.timedelta(hours=36)
OUT = "_data"


def safe(cid):
    return re.sub(r"[^A-Za-z0-9._-]", "_", cid)


def ts(s):
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", s)
    t = datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2) or "+0000"
    sign = 1 if off[0] == "+" else -1
    return t.replace(tzinfo=datetime.timezone(sign * datetime.timedelta(hours=int(off[1:3]), minutes=int(off[3:]))))


def b64(s):
    return base64.b64encode(s.encode("utf-8")).decode()


def fmt(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def item(cid, start, stop, title, desc):
    try:
        st, sp = ts(start), ts(stop)
    except Exception:
        return None
    if sp < lo or st > hi:
        return None
    title = " ".join(html.unescape(title or "").split())
    desc = " ".join(html.unescape(desc or "").split())
    if len(desc) > 300:
        desc = desc[:297].rsplit(" ", 1)[0] + "..."
    s, e = int(st.timestamp()), int(sp.timestamp())
    return {"id": str(s), "epg_id": cid, "title": b64(title), "lang": "", "start": fmt(s), "end": fmt(e),
            "description": b64(desc), "channel_id": cid, "start_timestamp": str(s), "stop_timestamp": str(e),
            "now_playing": 0, "has_archive": 0}


def split(epg):
    if not epg:
        return None
    if epg.startswith(("u:", "e:")):
        return epg[0], epg[2:]
    return "u", epg


# 1) channel lists -> Xtream answers + what guides are needed
want = {"u": set(), "e": set()}
hydra_compat = set()
maps = {}
for f in sorted(glob.glob("xtream/*/channels.json")):
    play = os.path.dirname(f); name = os.path.basename(play)
    chans = json.load(open(f, encoding="utf-8"))
    cats = []
    for c in chans:
        if c["group"] not in cats:
            cats.append(c["group"])
    streams, bycat, mp = [], {}, {}
    for n, c in enumerate(chans, 1):
        sp = split(c.get("epg"))
        cid = str(cats.index(c["group"]) + 1)
        s = {"num": n, "name": c["name"], "stream_type": "live", "stream_id": c["stream_id"], "stream_icon": "",
             "epg_channel_id": sp[1] if sp else None, "added": "0", "category_id": cid, "custom_sid": "",
             "tv_archive": 0, "direct_source": "", "tv_archive_duration": 0}
        streams.append(s); bycat.setdefault(cid, []).append(s)
        if sp:
            want[sp[0]].add(sp[1])
            mp.setdefault(str(c["stream_id"] % 256), {})[str(c["stream_id"])] = f"{sp[0]}/{safe(sp[1])}"
            if name == "hydra" and sp[0] == "u":
                hydra_compat.add(sp[1])
    dump = lambda o, p: json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=True, separators=(",", ":"))
    dump([{"category_id": str(i + 1), "category_name": g, "parent_id": 0} for i, g in enumerate(cats)],
         f"{play}/live_categories.json")
    dump(streams, f"{play}/live_streams.json")
    shutil.rmtree(f"{play}/cat", ignore_errors=True); os.makedirs(f"{play}/cat")
    for cid, items in bycat.items():
        dump(items, f"{play}/cat/{cid}.json")
    maps[name] = mp

listings = {"u": {c: [] for c in want["u"]}, "e": {c: [] for c in want["e"]}}

# 2) unified guide (this repo)
src = open(SRC, encoding="utf-8").read()
for m in re.finditer(r'<programme\b([^>]*)>(.*?)</programme>', src, re.S):
    a = m.group(1)
    c = re.search(r'channel="([^"]*)"', a)
    c = html.unescape(c.group(1)) if c else None
    if c not in listings["u"]:
        continue
    t = re.search(r"<title\b[^>]*>(.*?)</title>", m.group(2), re.S)
    d = re.search(r"<desc\b[^>]*>(.*?)</desc>", m.group(2), re.S)
    it = item(c, re.search(r'start="([^"]*)"', a).group(1), re.search(r'stop="([^"]*)"', a).group(1),
              t and t.group(1), d and d.group(1))
    if it:
        listings["u"][c].append(it)
del src

# 3) "e:" ids (non-Arabic channels such as TSN) wait for an approved public source: this repository's
#    gate (channel_gate_selftest.py) allows no aggregated dump that is not on its named list.

# 4) write
shutil.rmtree(OUT, ignore_errors=True)
for kind in ("u", "e"):
    os.makedirs(f"{OUT}/epg/{kind}", exist_ok=True)
    for c, items in listings[kind].items():
        items.sort(key=lambda x: int(x["start_timestamp"]))
        json.dump({"epg_listings": items}, open(f"{OUT}/epg/{kind}/{safe(c)}.json", "w", encoding="utf-8"),
                  ensure_ascii=True, separators=(",", ":"))
for name, mp in maps.items():
    os.makedirs(f"{OUT}/map/{name}", exist_ok=True)
    for shard, d in mp.items():
        json.dump(d, open(f"{OUT}/map/{name}/{shard}.json", "w"), separators=(",", ":"))
os.makedirs("xtream/epg", exist_ok=True)
for old in glob.glob("xtream/epg/*.json"):
    os.remove(old)
for c in hydra_compat:
    json.dump({"epg_listings": listings["u"][c]}, open(f"xtream/epg/{safe(c)}.json", "w", encoding="utf-8"),
              ensure_ascii=True)
for kind in ("u", "e"):
    full = sum(1 for v in listings[kind].values() if v)
    print(f"xtream {kind}: {full}/{len(listings[kind])} guide channels with programmes, "
          f"{sum(map(len, listings[kind].values()))} programmes")
