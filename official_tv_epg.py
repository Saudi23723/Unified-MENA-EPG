#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BBC and the MBC group's channels (Al Arabiya, Al Hadath and the rest), each from
the broadcaster's OWN guide ("BBC channels, Alarabiya هدول مافي EPG", 24 October 2026).

    BBC One (every region), Two, Three, Four, News, Parliament, Scotland, Alba
                    BBC's own iPlayer schedule service (ibl.api.bbc.co.uk).
    BBC News international (BBC World News)
                    BBC's own schedule pages (bbc.co.uk/schedules, BBC News Middle East).
    Al Arabiya, Al Hadath, Al Arabiya Business, MBC 1-5, MBC Action/Drama/Max/..., the
    Saudi channels on Shahid
                    Shahid's own live-channel guide (MBC Group's platform, api3.shahid.net).
A slot the broadcaster marks as having no schedule ("جدول البرامج غير متاح") is dropped,
and a channel whose broadcaster does not answer this run is left out: no guide is better
than a wrong one.

    python official_tv_epg.py      # writes official_tv_epg.xml
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import urllib.parse
import urllib.request

OUT = "official_tv_epg.xml"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "application/json"}
NOW = dt.datetime.now(dt.timezone.utc)
FROM = NOW - dt.timedelta(hours=6)
TO = NOW + dt.timedelta(hours=48)

# iPlayer channel ids -> (our id, names)
BBC = {
    "bbc_one_london": ("BBCOne.uk", ["BBC One", "BBC One London", "BBC 1"]),
    "bbc_two_england": ("BBCTwo.uk", ["BBC Two", "BBC 2"]),
    "bbc_three": ("BBCThree.uk", ["BBC Three", "BBC 3"]),
    "bbc_four": ("BBCFour.uk", ["BBC Four", "BBC 4"]),
    "bbc_news24": ("BBCNews.uk", ["BBC News", "BBC News Channel", "BBC News UK"]),
    "bbc_parliament": ("BBCParliament.uk", ["BBC Parliament"]),
    "bbc_scotland": ("BBCScotland.uk", ["BBC Scotland"]),
    "bbc_alba": ("BBCAlba.uk", ["BBC Alba"]),
}
for region, words in {
        "scotland": ["Scotland"], "wales": ["Wales"], "northern_ireland": ["Northern Ireland", "NI"],
        "east": ["East"], "east_midlands": ["East Midlands"], "west": ["West"], "west_midlands": ["West Midlands"],
        "north_west": ["North West"], "north_east": ["North East", "North East and Cumbria", "North East & Cumbria"],
        "south": ["South"], "south_east": ["South East"], "south_west": ["South West"],
        "yorkshire": ["Yorkshire"], "east_yorkshire": ["East Yorkshire", "Yorkshire and Lincolnshire", "Yorkshire & Lincolnshire"],
        "oxford": ["Oxford", "Oxfordshire"], "cambridge": ["Cambridge", "Cambridgeshire"], "channel_islands": ["Channel Islands"]}.items():
    BBC[f"bbc_one_{region}"] = (f"BBCOne{region.title().replace('_', '')}.uk", [f"BBC One {w}" for w in words])
BBC_WORLD = ("BBCWorldNews.int", ["BBC World News", "BBC News International"], "p00fzl9l")
SHAHID = "https://api3.shahid.net/proxy/v2.1"
SHAHID_H = dict(UA, Origin="https://shahid.mbc.net", Referer="https://shahid.mbc.net/")
EMPTY = "جدول البرامج غير متاح"


def get(url, headers=UA, raw=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        body = r.read().decode("utf-8", "replace")
    return body if raw else json.loads(body)


def iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def bbc(channel):
    out, page = [], 1
    while page <= 6:
        d = get(f"https://ibl.api.bbc.co.uk/ibl/v1/channels/{channel}/broadcasts?per_page=100&page={page}")
        b = d.get("broadcasts", {})
        for e in b.get("elements", []):
            ep = e.get("episode") or {}
            title = ep.get("title") or ""
            sub = ep.get("subtitle") or ""
            desc = ((ep.get("synopses") or {}).get("small") or "")
            out.append((iso(e["scheduled_start"]), iso(e["scheduled_end"]), title, (sub + " - " + desc).strip(" -") if sub else desc))
        if not b.get("elements") or page * b.get("per_page", 100) >= b.get("count", 0) or out[-1][0] > TO:
            break
        page += 1
    return out


def bbc_world(pid):
    out = []
    d = FROM.date()
    while d <= TO.date():
        page = get(f"https://www.bbc.co.uk/schedules/{pid}/{d:%Y/%m/%d}", raw=True)
        for block in re.findall(r'<li[^>]*class="[^"]*grid[^"]*"[^>]*>(.*?)</li>', page, re.S):
            st = re.search(r'property="startDate"\s+content="([^"]+)"', block)
            en = re.search(r'property="endDate"\s+content="([^"]+)"', block)
            ti = re.search(r'class="programme__title[^"]*"[^>]*>\s*<span[^>]*>([^<]+)<', block)
            sy = re.search(r'class="programme__synopsis[^"]*"[^>]*>\s*<span[^>]*>([^<]+)<', block)
            if st and en and ti:
                out.append((iso(st.group(1)), iso(en.group(1)), html.unescape(ti.group(1)), html.unescape(sy.group(1)) if sy else ""))
        d += dt.timedelta(days=1)
    return out


def shahid_channels():
    chans = {}
    for page in range(0, 10):
        f = {"pageNumber": page, "pageSize": 100, "productType": "LIVESTREAM", "productSubType": "LIVE_CHANNEL"}
        d = get(f"{SHAHID}/product/filter?filter={urllib.parse.quote(json.dumps(f))}&country=SA&language=ar", SHAHID_H)
        items = (d.get("productList") or {}).get("products") or []
        for it in items:
            if it.get("id") and it.get("title"):
                chans[str(it["id"])] = it["title"].strip()
        if len(items) < 30:
            break
    return chans


def shahid_guide(ids):
    out = {}
    fr = FROM.strftime("%Y-%m-%dT%H:00:00.000Z"); to = TO.strftime("%Y-%m-%dT%H:00:00.000Z")
    for i in range(0, len(ids), 10):
        part = ids[i:i + 10]
        d = get(f"{SHAHID}/shahid-epg-api/?csvChannelIds={','.join(part)}&from={fr}&to={to}"
                "&country=SA&language=ar&offset=0&limit=500", SHAHID_H)
        for ch in d.get("items", []):
            for e in ch.get("items", []):
                if e.get("emptySlot") or (e.get("title") or "").strip() == EMPTY:
                    continue
                out.setdefault(str(ch["channelId"]), []).append(
                    (iso(e["from"]), iso(e["to"]), e.get("title") or "", e.get("description") or ""))
    return out


def main() -> int:
    guides, failed = [], []
    for ch, (cid, names) in BBC.items():
        try:
            guides.append((cid, names, bbc(ch)))
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{cid}: {exc}")
    try:
        guides.append((BBC_WORLD[0], BBC_WORLD[1], bbc_world(BBC_WORLD[2])))
    except Exception as exc:  # noqa: BLE001
        failed.append(f"{BBC_WORLD[0]}: {exc}")
    try:
        chans = shahid_channels()
        got = shahid_guide(sorted(chans))
        for sid, title in chans.items():
            guides.append((f"Shahid{sid}.mbc", [title], got.get(sid, [])))
    except Exception as exc:  # noqa: BLE001
        failed.append(f"Shahid: {exc}")

    esc = lambda s: html.escape(" ".join((s or "").split()), quote=True)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="Unified-MENA-EPG official_tv_epg">']
    body, kept = [], 0
    for cid, names, progs in guides:
        progs = sorted(p for p in progs if p[1] > FROM and p[0] < TO and p[1] > p[0] and p[2])
        if not progs:
            continue
        kept += 1
        lines.append(f'  <channel id="{esc(cid)}">' + "".join(f"<display-name>{esc(n)}</display-name>" for n in names) + "</channel>")
        seen = set()
        for st, sp, title, desc in progs:
            if st in seen:
                continue
            seen.add(st)
            body.append(f'  <programme start="{st:%Y%m%d%H%M%S} +0000" stop="{sp:%Y%m%d%H%M%S} +0000" channel="{esc(cid)}">'
                        f"<title>{esc(title)}</title>" + (f"<desc>{esc(desc)}</desc>" if desc else "") + "</programme>")
    lines += body + ["</tv>"]
    for f in failed:
        print("not read this run:", f, file=sys.stderr)
    if kept == 0:
        print("no broadcaster answered: keeping the last file", file=sys.stderr)
        return 1
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{OUT}: {kept} channels, {len(body)} programmes, {len(failed)} not read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
