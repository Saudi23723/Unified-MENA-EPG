#!/usr/bin/env python3
"""Xtream-style data for the DreamTV relays (cloudflare/worker.js).

DreamTV shows a guide only for Xtream logins, from the server's get_simple_data_table answer.
The relay answers from files built here. Names only: no links or logins anywhere.

Input  xtream/<playlist>/channel_map.json  [{stream_id, name, group, epg}]
       epg = "<id>" or "u:<id>"  -> unified_mena_epg.xml (this repo)
             "o:<id>"            -> official_sports_epg.xml / official_tv_epg.xml (this repo: Sky, TNT,
                                    TSN, Sportsnet / BBC, Al Arabiya, MBC on Shahid)
             "a:<id>"            -> att_epg.xml.gz (this repo's guide for the same Xtream playlist,
                                    att-epg branch; the workflow copies it in with git)
             "r:<file>/<id>"     -> one of this repository's own guides (<file>.xml), e.g. Turkey's beIN,
                                    Tivibu and tabii (bein_sports_turkey_epg, tabii_spor_1_10_epg)
             "l:<src>/<id>"      -> the owner's own EPG links, as TiviMate shows them (OWNER_LINKS)
             "e:<id>"            -> reserved for an approved public source (none yet)
Output (main branch, small, change rarely)
       xtream/<playlist>/live_categories.json, live_streams.json, cat/<category_id>.json
       xtream/epg/<id>.json      guide for unified ids (kept for the first Hydra relay)
Output (_data/, published to the xtream-data branch with no history)
       epg/u|o|e/<id>.json   {"epg_listings": [...]}, 3 h back, 36 h ahead
       map/<playlist>/<n>.json            {stream_id: "u/<id>"}, n = stream_id % 256
"""
import base64, datetime, glob, gzip, html, json, os, re, shutil, sys, urllib.request, zlib

import xtream_order
import official_fill  # official guides for channels the maps leave without one (27 Oct 2026)

SRC = "unified_mena_epg.xml"
OFFICIAL = "official_sports_epg.xml"
OFFICIAL_TV = "official_tv_epg.xml"
ATT = "att_epg.xml.gz"
# The owner's own EPG links, read off their TiviMate EPG sources (24 October 2026),
# for the countries this repository has no guide of its own for ("check from my
# tivimate app how is there guide for ... Italy, Morocco, NOW TV UK, Australia,
# Switzerland, Portugal, Turkey, Bulgaria"). Only the ones a playlist uses are read.
OWNER_LINKS = {
    "italy": "https://cdn.epg.guru/7dayiptv/Italy.xml",
    "swiss": "https://cdn.epg.guru/7dayiptv/Switzerland.xml.gz",
    "germany": "https://cdn.epg.guru/7dayiptv/Germany.xml.gz",
    "portugal": "https://iptv-epg.org/files/epg-pt.xml",
    "turkey": "https://iptv-epg.org/files/epg-tr.xml",
    "romania": "https://iptv-epg.org/files/epg-ro.xml",
    "slovenia": "https://iptv-epg.org/files/epg-si.xml",
    "combined": "https://iptv-epg.org/files/epg-rhtwyyuokk.xml",
    "iptvx": "https://iptvx.one/EPG",
}
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
    if epg.startswith(("u:", "o:", "a:", "r:", "l:", "e:")):
        return epg[0], epg[2:]
    return "u", epg


# Channel logos (owner, 27 October 2026): repo logos first, then the public tv-logos collection (channel_logos.py);
# the worker fills the rest with the provider's logo.
import channel_logos
LOGOS = channel_logos.Logos()
# logos shared between playlists: the last build's real logos of every playlist (xtream/*/live_streams.json)
for _f in glob.glob("xtream/*/live_streams.json"):
    try:
        _p = os.path.basename(os.path.dirname(_f))
        _cats = {c["category_id"]: c["category_name"] for c in json.load(open(os.path.dirname(_f) + "/live_categories.json", encoding="utf-8"))}
        LOGOS.share_from(json.load(open(_f, encoding="utf-8")), _cats, _p)
    except Exception:
        pass
# A small mark after every group name, so the owner can tell the playlists apart now that they share
# Strong's layout (owner, 27 October 2026). Display only: ids, order and guides use the plain names.
MARK = {}  # owner, 28 Oct 2026: no marks
# Up1 keeps its own (Turkish-first) order; only the shown names get the same look as the others.
FLAG = {"TR": "🇹🇷", "UK": "🇬🇧", "US": "🇺🇲"}


def shown(g: str, playlist: str) -> str:
    if playlist == "up1":
        m = re.match(r"^(TR|UK|US|PPV)\s*\|\s*(.*)$", g.strip())
        if m:
            g = ("🔥 " + m.group(2)) if m.group(1) == "PPV" else f"{FLAG[m.group(1)]} | {m.group(2)}"
    return g.rstrip() + MARK.get(playlist, "")


# 1) channel lists -> Xtream answers + what guides are needed
want = {"u": set(), "o": set(), "a": set(), "r": set(), "l": set(), "e": set()}
hydra_compat = set()
maps = {}
for f in sorted(glob.glob("xtream/*/channel_map.json")):
    play = os.path.dirname(f); name = os.path.basename(play)
    chans = xtream_order.order(json.load(open(f, encoding="utf-8")), name)
    # one entry per stream id: DreamTV keeps only the LAST channel with a given id, so a channel listed in two
    # groups vanished from the first one (Strong's Fox News left the USA group, owner 28 Oct 2026)
    _seen = set()
    chans = [c for c in chans if not (c["stream_id"] in _seen or _seen.add(c["stream_id"]))]
    cats = []
    for c in chans:
        if c["group"] not in cats:
            cats.append(c["group"])
    # fixed ids when the playlist has them (DreamTV remembers hidden / sorted groups by category id,
    # so ids must not move when the order changes); new groups get the next free numbers
    fixed = {}
    if os.path.exists(f"{play}/category_ids.json"):
        fixed = {g: int(i) for g, i in json.load(open(f"{play}/category_ids.json", encoding="utf-8"))["ids"].items()}
    nxt = max(fixed.values(), default=0)
    catid = {}
    for i, g in enumerate(cats):
        if fixed:
            if g not in fixed:
                nxt += 1; fixed[g] = nxt
            catid[g] = str(fixed[g])
        else:
            catid[g] = str(i + 1)
    streams, bycat, mp = [], {}, {}
    for n, c in enumerate(chans, 1):
        sp = split(official_fill.override(c["name"]) or c.get("epg") or official_fill.fill(c["name"], c["group"]))
        cid = catid[c["group"]]
        icon = LOGOS.find(c["name"], c["group"], name, sp[0] if sp else None, sp[1] if sp else None)
        s = {"num": n, "name": c["name"], "stream_type": "live", "stream_id": c["stream_id"], "stream_icon": icon,
             "epg_channel_id": sp[1] if sp else None, "added": "0", "category_id": cid, "custom_sid": "",
             "tv_archive": 0, "direct_source": "", "tv_archive_duration": 0}
        streams.append(s); bycat.setdefault(cid, []).append(s)
        if sp:
            want[sp[0]].add(sp[1])
            mp.setdefault(str(c["stream_id"] % 256), {})[str(c["stream_id"])] = f"{sp[0]}/{safe(sp[1])}"
            if name == "hydra" and sp[0] in ("u", "o"):
                hydra_compat.add((sp[0], sp[1]))
    LOGOS.fill_playlist(streams, {catid[g]: g for g in cats}, name)
    LOGOS.share_from(streams, {catid[g]: g for g in cats}, name)
    dump = lambda o, p: json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=True, separators=(",", ":"))
    dump([{"category_id": catid[g], "category_name": shown(g, name), "parent_id": 0} for g in cats],
         f"{play}/live_categories.json")
    dump(streams, f"{play}/live_streams.json")
    shutil.rmtree(f"{play}/cat", ignore_errors=True); os.makedirs(f"{play}/cat")
    for cid, items in bycat.items():
        dump(items, f"{play}/cat/{cid}.json")
    maps[name] = mp

listings = {k: {c: [] for c in v} for k, v in want.items()}
# a shifted copy ("<id>@+180", see 2a) needs its base guide read too
for _k in ("u", "o", "a"):
    for _c in list(listings[_k]):
        _m = re.fullmatch(r"(.+)@\+(\d{1,4})", _c)
        if _m:
            listings[_k].setdefault(_m.group(1), [])

# 2) this repository's own guides: the unified one, and the broadcasters' own (official_sports_epg.py)
for kind, path in (("u", SRC), ("o", OFFICIAL), ("o", OFFICIAL_TV), ("a", ATT)):
    if not os.path.exists(path):
        continue
    src = (gzip.open(path) if path.endswith(".gz") else open(path, "rb")).read().decode("utf-8", "replace")
    for m in re.finditer(r'<programme\b([^>]*)>(.*?)</programme>', src, re.S):
        a = m.group(1)
        c = re.search(r'channel="([^"]*)"', a)
        c = html.unescape(c.group(1)) if c else None
        if c not in listings[kind]:
            continue
        t = re.search(r"<title\b[^>]*>(.*?)</title>", m.group(2), re.S)
        d = re.search(r"<desc\b[^>]*>(.*?)</desc>", m.group(2), re.S)
        it = item(c, re.search(r'start="([^"]*)"', a).group(1), re.search(r'stop="([^"]*)"', a).group(1),
                  t and t.group(1), d and d.group(1))
        if it:
            listings[kind][c].append(it)
    del src

# 2a) West-coast feeds whose own guide is stale: "<id>@+180" = that guide 180 minutes later
#     (TNT / TBS / truTV / USA Network West air the East schedule three hours later; owner, 28 Oct 2026)
for kind in ("u", "o", "a"):
    for c in list(listings[kind]):
        m = re.fullmatch(r"(.+)@\+(\d{1,4})", c)
        if not m:
            continue
        base, mins = m.group(1), int(m.group(2))
        shift = mins * 60
        for it in listings[kind].get(base, []):
            s, e = int(it["start_timestamp"]) + shift, int(it["stop_timestamp"]) + shift
            listings[kind][c].append(dict(it, id=str(s), epg_id=c, channel_id=c, start=fmt(s), end=fmt(e),
                                          start_timestamp=str(s), stop_timestamp=str(e)))

# 2b) the repository's other own guides ("r:<file>/<id>")
by_file = {}
for full in want["r"]:
    f, cid = full.split("/", 1)
    by_file.setdefault(f, set()).add(cid)
for f, ids in sorted(by_file.items()):
    if not re.fullmatch(r"[a-z0-9_]+", f) or not os.path.exists(f + ".xml"):
        continue
    for m in re.finditer(r'<programme\b([^>]*)>(.*?)</programme>', open(f + ".xml", encoding="utf-8").read(), re.S):
        a = m.group(1)
        c = re.search(r'channel="([^"]*)"', a)
        c = html.unescape(c.group(1)) if c else None
        if c not in ids:
            continue
        t = re.search(r"<title\b[^>]*>(.*?)</title>", m.group(2), re.S)
        d = re.search(r"<desc\b[^>]*>(.*?)</desc>", m.group(2), re.S)
        it = item(c, re.search(r'start="([^"]*)"', a).group(1), re.search(r'stop="([^"]*)"', a).group(1),
                  t and t.group(1), d and d.group(1))
        if it:
            listings["r"][f"{f}/{c}"].append(it)

# 3) the owner's own links ("l:<src>/<id>"), streamed, never kept whole
by_src = {}
for full in want["l"]:
    src_name, cid = full.split("/", 1)
    by_src.setdefault(src_name, set()).add(cid)


def programmes_from(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        first = r.read(2)
        unzip = zlib.decompressobj(16 + zlib.MAX_WBITS) if first == b"\x1f\x8b" else None
        buf = ""
        chunk = first
        while chunk:
            data = unzip.decompress(chunk) if unzip else chunk
            buf += data.decode("utf-8", "replace")
            last = buf.rfind("</programme>")
            if last >= 0:
                part, buf = buf[:last + 12], buf[last + 12:]
                yield from re.finditer(r'<programme\b([^>]*)>(.*?)</programme>', part, re.S)
            chunk = r.read(1 << 20)


for src_name, ids in sorted(by_src.items()):
    url = OWNER_LINKS.get(src_name)
    if not url:
        continue
    got = 0
    try:
        for m in programmes_from(url):
            a = m.group(1)
            c = re.search(r'channel="([^"]*)"', a)
            c = html.unescape(c.group(1)) if c else None
            if c not in ids:
                continue
            st = re.search(r'start="([^"]*)"', a); sp = re.search(r'stop="([^"]*)"', a)
            t = re.search(r"<title\b[^>]*>(.*?)</title>", m.group(2), re.S)
            d = re.search(r"<desc\b[^>]*>(.*?)</desc>", m.group(2), re.S)
            if st and sp:
                it = item(c, st.group(1), sp.group(1), t and t.group(1), d and d.group(1))
                if it:
                    listings["l"][f"{src_name}/{c}"].append(it); got += 1
    except Exception as exc:  # noqa: BLE001 - one link down: its channels wait for the next run
        print(f"owner link {src_name} not read this run: {exc}", file=sys.stderr)
    print(f"owner link {src_name}: {got} programmes for {len(ids)} channel(s)")

# 3b) "e:" ids (non-Arabic channels such as TSN) wait for an approved public source: this repository's
#    gate (channel_gate_selftest.py) allows no aggregated dump that is not on its named list.

# 4) write
shutil.rmtree(OUT, ignore_errors=True)
for kind in ("u", "o", "a", "r", "l", "e"):
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
for kind, c in hydra_compat:
    json.dump({"epg_listings": listings[kind][c]}, open(f"xtream/epg/{safe(c)}.json", "w", encoding="utf-8"),
              ensure_ascii=True)
for kind in ("u", "o", "a", "r", "l", "e"):
    full = sum(1 for v in listings[kind].values() if v)
    print(f"xtream {kind}: {full}/{len(listings[kind])} guide channels with programmes, "
          f"{sum(map(len, listings[kind].values()))} programmes")
