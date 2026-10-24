#!/usr/bin/env python3
"""Xtream-style data for the DreamTV relay (cloudflare/worker.js).

DreamTV only shows a guide for Xtream logins, read from the server's
get_simple_data_table answer. The relay answers that from these files:
  xtream/<playlist>/channels.json  - order, clean name, group and guide id per stream id (names only)
  xtream/<playlist>/live_categories.json, live_streams.json - ready Xtream answers
  xtream/epg/<guide id>.json       - {"epg_listings": [...]} from unified_mena_epg.xml, 3 h back, 48 h ahead
No links or logins live here.
"""
import base64, datetime, glob, html, json, os, re

SRC = "unified_mena_epg.xml"
now = datetime.datetime.now(datetime.timezone.utc)
lo, hi = now - datetime.timedelta(hours=3), now + datetime.timedelta(hours=48)


def safe(cid):
    return re.sub(r"[^A-Za-z0-9._-]", "_", cid)


def ts(s):
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", s)
    t = datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2) or "+0000"
    tz = datetime.timezone(datetime.timedelta(hours=int(off[1:3]), minutes=int(off[3:])) * (1 if off[0] == "+" else -1))
    return t.replace(tzinfo=tz)


def b64(s):
    return base64.b64encode(s.encode("utf-8")).decode()


def text(tag, body):
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", body, re.S)
    return " ".join(html.unescape(m.group(1)).split()) if m else ""


wanted = set()
for f in glob.glob("xtream/*/channels.json"):
    play = os.path.dirname(f)
    chans = json.load(open(f, encoding="utf-8"))
    cats, streams = [], []
    for c in chans:
        if c["group"] not in cats:
            cats.append(c["group"])
    for n, c in enumerate(chans, 1):
        streams.append({"num": n, "name": c["name"], "stream_type": "live", "stream_id": c["stream_id"],
                        "stream_icon": "", "epg_channel_id": c["epg"] or None, "added": "0",
                        "category_id": str(cats.index(c["group"]) + 1), "custom_sid": "", "tv_archive": 0,
                        "direct_source": "", "tv_archive_duration": 0})
        if c["epg"]:
            wanted.add(c["epg"])
    json.dump([{"category_id": str(i + 1), "category_name": g, "parent_id": 0} for i, g in enumerate(cats)],
              open(f"{play}/live_categories.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(streams, open(f"{play}/live_streams.json", "w", encoding="utf-8"), ensure_ascii=False)

src = open(SRC, encoding="utf-8").read()
listings = {c: [] for c in wanted}
for m in re.finditer(r'<programme\b([^>]*)>(.*?)</programme>', src, re.S):
    a = m.group(1)
    cid = re.search(r'channel="([^"]*)"', a)
    if not cid or html.unescape(cid.group(1)) not in listings:
        continue
    try:
        st, sp = ts(re.search(r'start="([^"]*)"', a).group(1)), ts(re.search(r'stop="([^"]*)"', a).group(1))
    except Exception:
        continue
    if sp < lo or st > hi:
        continue
    c = html.unescape(cid.group(1))
    title, desc = text("title", m.group(2)), text("desc", m.group(2))
    if len(desc) > 300:
        desc = desc[:297].rsplit(" ", 1)[0] + "..."
    s, e = int(st.timestamp()), int(sp.timestamp())
    fmt = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    listings[c].append({"id": str(s), "epg_id": c, "title": b64(title), "lang": "", "start": fmt(s), "end": fmt(e),
                        "description": b64(desc), "channel_id": c, "start_timestamp": str(s), "stop_timestamp": str(e),
                        "now_playing": 0, "has_archive": 0})

os.makedirs("xtream/epg", exist_ok=True)
for old in glob.glob("xtream/epg/*.json"):
    os.remove(old)
n = 0
for c, items in listings.items():
    items.sort(key=lambda x: int(x["start_timestamp"]))
    json.dump({"epg_listings": items}, open(f"xtream/epg/{safe(c)}.json", "w", encoding="utf-8"), ensure_ascii=False)
    n += len(items)
print(f"xtream: {len(listings)} guide channels, {n} programmes")
