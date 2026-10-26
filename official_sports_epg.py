#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sky Sports, TNT Sports, TSN and Sportsnet, each from the broadcaster's OWN guide
(asked for in those words: "ADD SKY AND TSN AND TNT FROM OFFICIAL SOURCES AND ADD
THEM TO MY REPO" and "and SPORTSONE channels", 24 October 2026).

    Sky Sports + TNT Sports   Sky's own EPG service, the one sky.com's TV guide reads
                              (awk.epgsky.com, Sky UK bouquet 4101). TNT Sports is
                              carried on Sky, so its listings come from the same guide.
    TSN 1-5                   Bell Media's own schedule service (capi.9c9media.com),
                              the one tsn.ca reads.
    Sportsnet                 Rogers' own schedule service, the one watch.sportsnet.ca
                              reads (production-cdn.d3-rgr-diva.com).

A channel whose broadcaster does not answer this run is left out of the file rather
than filled from anywhere else: no guide is better than a wrong one.

    python official_sports_epg.py     # writes official_sports_epg.xml
"""
from __future__ import annotations

import datetime as dt
import html
import json
import sys
import urllib.request

OUT = "official_sports_epg.xml"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0", "Accept": "application/json"}
NOW = dt.datetime.now(dt.timezone.utc)
FROM = NOW - dt.timedelta(hours=6)
TO = NOW + dt.timedelta(hours=48)

# (channel id, display names, Sky service id) - ids from Sky's service list, bouquet 4101
SKY = [
    ("SkySportsMainEvent.uk", ["Sky Sports Main Event", "Sky Sports Main Event HD"], "4002"),
    ("SkySportsPremierLeague.uk", ["Sky Sports Premier League", "Sky Sports Premier League HD"], "4010"),
    ("SkySportsFootball.uk", ["Sky Sports Football", "Sky Sports Football HD"], "3939"),
    ("SkySportsPlus.uk", ["Sky Sports+", "Sky Sports Plus", "Sky Sports+ HD"], "3940"),
    ("SkySportsCricket.uk", ["Sky Sports Cricket", "Sky Sports Cricket HD"], "4081"),
    ("SkySportsGolf.uk", ["Sky Sports Golf", "Sky Sports Golf HD"], "4026"),
    ("SkySportsF1.uk", ["Sky Sports F1", "Sky Sports F1 HD"], "3835"),
    ("SkySportsTennis.uk", ["Sky Sports Tennis", "Sky Sports Tennis HD"], "1284"),
    ("SkySportsNews.uk", ["Sky Sports News", "Sky Sports News HD"], "4049"),
    ("SkySportsNFL.uk", ["Sky Sports NFL", "Sky Sports NFL HD"], "4022"),
    ("SkySportsRacing.uk", ["Sky Sports Racing", "Sky Sports Racing HD"], "4032"),
    ("SkySportsMix.uk", ["Sky Sports Mix", "Sky Sports Mix HD"], "4090"),
    ("SkySportsBoxOffice.uk", ["Sky Sports Box Office", "Sky Sports Box Office HD"], "1035"),
    ("TNTSports1.uk", ["TNT Sports 1", "TNT Sports 1 HD"], "3625"),
    ("TNTSports2.uk", ["TNT Sports 2", "TNT Sports 2 HD"], "3627"),
    ("TNTSports3.uk", ["TNT Sports 3", "TNT Sports 3 HD"], "3629"),
    ("TNTSports4.uk", ["TNT Sports 4", "TNT Sports 4 HD"], "4040"),
    ("TNTSportsBoxOffice.uk", ["TNT Sports Box Office", "TNT Sports Box Office HD"], "1210"),
    ("TNTSportsBoxOffice2.uk", ["TNT Sports Box Office 2", "TNT Sports Box Office 2 HD"], "1099"),
]
# (channel id, display names, Bell Media channel affiliate)
TSN = [(f"TSN{n}.ca", [f"TSN {n}", f"TSN{n}"], f"tsn{n}") for n in range(1, 6)]
# (channel id, display names, Rogers channel id) - from watch.sportsnet.ca's channel page
SPORTSNET = [
    ("SportsnetEast.ca", ["Sportsnet East"], "155046"),
    ("SportsnetOne.ca", ["Sportsnet One", "Sportsnet ONE", "SN1"], "155047"),
    ("SportsnetPacific.ca", ["Sportsnet Pacific"], "155048"),
    ("SportsnetOntario.ca", ["Sportsnet Ontario"], "155049"),
    ("SportsnetWest.ca", ["Sportsnet West"], "155050"),
    ("Sportsnet360.ca", ["Sportsnet 360"], "155068"),
    ("SportsnetWorld.ca", ["Sportsnet World"], "155080"),
]


def get_json(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def days():
    d = FROM.date()
    while d <= TO.date():
        yield d
        d += dt.timedelta(days=1)


def sky(sid: str):
    for d in days():
        data = get_json(f"https://awk.epgsky.com/hawk/linear/schedule/{d:%Y%m%d}/{sid}")
        for ch in data.get("schedule", []):
            for e in ch.get("events", []):
                st = dt.datetime.fromtimestamp(int(e["st"]), dt.timezone.utc)
                yield st, st + dt.timedelta(seconds=int(e.get("d", 0))), e.get("t", ""), e.get("sy", "")


def tsn(aff: str):
    start = FROM.strftime("%Y-%m-%dT%H:00:00Z"); end = TO.strftime("%Y-%m-%dT%H:00:00Z")
    data = get_json("https://capi.9c9media.com/destinations/tsn_web/platforms/desktop/channelaffiliates/"
                    f"{aff}/schedules?StartTime={start}&EndTime={end}&Inclusions=Desc")
    for it in data.get("Items", []):
        yield iso(it["StartTime"]), iso(it["EndTime"]), it.get("Title") or it.get("Name") or "", it.get("Desc") or ""


def sportsnet(ids: list[str]):
    out = {i: [] for i in ids}
    for d in days():
        data = get_json("https://production-cdn.d3-rgr-diva.com/api/schedules?channels="
                        f"{','.join(ids)}&date={d:%Y-%m-%d}&hour=0&duration=24&intersect=true&device=web_browser")
        for block in data:
            for s in block.get("schedules", []):
                item = s.get("item") or {}
                out.setdefault(s.get("channelId"), []).append(
                    (iso(s["startDate"]), iso(s["endDate"]), item.get("title", ""), item.get("shortDescription", "")))
    return out


def main() -> int:
    guides: list[tuple[str, list[str], list]] = []
    failed = []
    for cid, names, sid in SKY:
        try:
            guides.append((cid, names, list(sky(sid))))
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{cid}: {exc}")
    for cid, names, aff in TSN:
        try:
            guides.append((cid, names, list(tsn(aff))))
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{cid}: {exc}")
    try:
        sn = sportsnet([x[2] for x in SPORTSNET])
        for cid, names, rid in SPORTSNET:
            guides.append((cid, names, sn.get(rid, [])))
    except Exception as exc:  # noqa: BLE001
        failed.append(f"Sportsnet: {exc}")

    esc = lambda s: html.escape(" ".join((s or "").split()), quote=True)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tv generator-info-name="Unified-MENA-EPG official_sports_epg">']
    body, kept = [], 0
    for cid, names, progs in guides:
        seen = set(); progs = sorted(p for p in progs if p[1] > FROM and p[0] < TO and p[1] > p[0])
        if not progs:
            continue
        kept += 1
        lines.append(f'  <channel id="{esc(cid)}">' + "".join(f"<display-name>{esc(n)}</display-name>" for n in names)
                     + "</channel>")
        for st, sp, title, desc in progs:
            if st in seen:
                continue
            seen.add(st)
            body.append(f'  <programme start="{st:%Y%m%d%H%M%S} +0000" stop="{sp:%Y%m%d%H%M%S} +0000" '
                        f'channel="{esc(cid)}"><title lang="en">{esc(title)}</title>'
                        + (f'<desc lang="en">{esc(desc)}</desc>' if desc else "") + "</programme>")
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
