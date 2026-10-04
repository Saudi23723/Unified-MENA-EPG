#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beIN's entertainment channels — movies, series, Star, documentaries,
kids — read from beIN's own guide at bein.com.

Asked for from photos of the player: beIN Movies 1-4, Series, Drama,
Star Movies/World/Action, BBC Earth, Food Network, Nat Geo and Nat Geo
Wild, Gourmet, Cartoonito, Baraem, Jeem, Disney and Disney Jr all sat on
"No information". The sports guide cannot carry them: beinsports.com's
API is sport only. beIN's MENA site publishes its own grid for the
rest, as HTML, through the same call its TV-guide page makes:

    https://www.bein.com/ar/epg-ajax-template/?action=epg_fetch
        &category=entertainment&cdate=YYYY-MM-DD&offset=+3 ...

Measured on a runner: 39 channels, today and the three days after it
(2148, 988, 580 and 542 rows), nothing further. Each channel is a
block with its logo and a list of rows; a row carries its title, its
category and its start and end as "YYYY-MM-DD HH:MM:SS" in the zone
asked for (offset +3, Mecca). A channel is known by its logo's file
name, which is the only name the page gives it.

The news channels on that grid (Al Jazeera, France 24, CNN, TRT,
Euronews, Al Araby, Bloomberg) are left out: they are not beIN's own,
and this repository's other guides already name several of them.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from epg_lib import (
    add_programme, fetch, log, new_session, run_main, warn, write_xml_atomic,
)

OUTPUT = "bein_entertainment_epg.xml"
# Each channel's own mark, as beIN's guide page shows it (assets.bein.com),
# on a white rounded tile so the black ones — BBC Earth, Cartoon Network,
# Star, Nat Geo — read on a player's dark list. logos/bein_ent_*.png.
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/bein_ent_{}.png")
URL = "https://www.bein.com/ar/epg-ajax-template/"
MECCA = timezone(timedelta(hours=3))
DAYS = 4

# (a piece of the logo's file name, xmltv id, the names a playlist uses)
CHANNELS = (
    ("MOVIES1_", "beINMovies1.qa",
     ("beIN Movies 1", "beIN Movies 1 Premiere", "beIN Movies Premiere")),
    ("MOVIES2_", "beINMovies2.qa",
     ("beIN Movies 2", "beIN Movies 2 Action", "beIN Movies Action")),
    ("MOVIES3_", "beINMovies3.qa",
     ("beIN Movies 3", "beIN Movies 3 Drama", "beIN Movies Drama")),
    ("MOVIES4_", "beINMovies4.qa",
     ("beIN Movies 4", "beIN Movies 4 Family", "beIN Movies Family")),
    ("BoxOffice1", "beINBoxOffice1.qa", ("beIN Box Office 1",)),
    ("BoxOffice2", "beINBoxOffice2.qa", ("beIN Box Office 2",)),
    ("Star_Action", "beINStarAction.qa", ("beIN Star Action", "Star Action")),
    ("Star_Movies", "beINStarMovies.qa", ("beIN Star Movies", "Star Movies")),
    ("Star_World", "beINStarWorld.qa", ("beIN Star World", "Star World")),
    ("SERIES1_", "beINSeries1.qa", ("beIN Series 1", "beIN Series")),
    ("SERIES2_", "beINSeries2.qa", ("beIN Series 2",)),
    ("Drama_", "beINDrama1.qa", ("beIN Drama 1", "beIN Drama")),
    ("GOURMET", "beINGourmet.qa", ("beIN Gourmet",)),
    ("food-network", "beINFoodNetwork.qa",
     ("beIN Food Network", "Food Network")),
    ("HGTV", "beINHGTV.qa", ("beIN HGTV", "HGTV")),
    ("beJUNIOR", "beINJunior.qa", ("beIN Junior", "beJunior")),
    ("Nat_geo", "beINNatGeo.qa",
     ("beIN Nat Geo", "Nat Geo", "National Geographic")),
    ("NGW_", "beINNatGeoWild.qa", ("beIN Nat Geo Wild", "Nat Geo Wild")),
    ("BBCEarth", "beINBBCEarth.qa", ("beIN BBC Earth", "BBC Earth")),
    ("Discovery-logo", "beINDiscovery.qa",
     ("beIN Discovery", "Discovery Channel", "Discovery")),
    ("Aljazeera-Documentary", "beINAlJazeeraDocumentary.qa",
     ("Al Jazeera Documentary", "beIN Al Jazeera Documentary")),
    ("Jeem", "beINJeem.qa", ("beIN Jeem", "Jeem TV", "Jeem")),
    ("Bara3em", "beINBaraem.qa", ("beIN Baraem", "Baraem")),
    ("DC-Blue", "beINDisney.qa",
     ("beIN Disney", "Disney Channel", "Disney")),
    ("/DJ.", "beINDisneyJr.qa",
     ("beIN Disney Jr", "Disney Junior", "Disney Jr")),
    ("Baby-TV", "beINBabyTV.qa", ("beIN Baby TV", "Baby TV")),
    ("cartoonito", "beINCartoonito.qa", ("beIN Cartoonito", "Cartoonito")),
    ("AWG_CN", "beINCartoonNetwork.qa",
     ("beIN Cartoon Network", "Cartoon Network")),
    ("Cartoon-Network-Arabic", "beINCartoonNetworkArabic.qa",
     ("beIN Cartoon Network Arabic", "Cartoon Network Arabic",
      "CN Arabic")),
)


def which(logo: str):
    for piece, xid, names in CHANNELS:
        if piece in logo:
            return xid, names
    return None


def at(stamp: str) -> datetime | None:
    try:
        return datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=MECCA).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def read_day(session, day) -> dict[str, list[dict]]:
    params = {
        "action": "epg_fetch", "category": "entertainment",
        "serviceidentity": "bein.net", "offset": "+3", "mins": "00",
        "cdate": day.isoformat(), "language": "AR", "postid": "25344",
        "loadindex": "0",
    }
    html = fetch(session, URL, params=params,
                 headers={"X-Requested-With": "XMLHttpRequest"}).text
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, list[dict]] = {}
    for block in soup.select("div[id^=channels_]"):
        img = block.find("img")
        known = which(img.get("src") or "") if img else None
        if not known:
            continue
        xid, _names = known
        for li in block.select("li"):
            bar = li.select_one(".progress")
            title = li.select_one("p.title")
            if bar is None or title is None:
                continue
            start, stop = at(bar.get("data-start")), at(bar.get("data-end"))
            name = re.sub(r"\s+", " ", title.get_text(" ", strip=True))
            if not start or not stop or stop <= start or not name:
                continue
            out.setdefault(xid, []).append({
                "start": start, "stop": stop, "title": name,
                "desc": (li.get("data-desc") or "").strip(),
                "category": (li.get("category") or "").strip(),
            })
    return out


# THE GUIDE PAGE'S OWN DATA, and the source read first.
#
# bein.com/en/tv-guide/ was rebuilt: it no longer calls the HTML grid
# above but fetches one JSON file per channel per day from beIN's own
# storage, named by the channel's code, which the page itself lists
# (const channelSets = {"entertainment": [{"file": "165.json", "image":
# ".../MOVIES1_PREMIERE_DIGITAL_Mono.png"}, ...]}). Checked on a runner
# against the grid, programme by programme: "الخادمة" is 00:00 on the
# grid asked for Mecca and 21:00 the evening before in the file, so the
# file's StartTime and EndTime are UTC. It carries more than the grid:
# every row's title in Arabic and English, a synopsis, and Discovery,
# which the grid never listed. Measured: yesterday to three days ahead
# (Movies 1: 39-40 rows a day). The grid stays as the fallback.
PAGE = "https://www.bein.com/en/tv-guide/"
STORE = "https://storagebeincom-b4dvftgkaebcayar.z01.azurefd.net/epg/"


def the_page_channels(session) -> list[tuple[str, str]]:
    """(file, logo) for every entertainment channel the page lists."""
    html = fetch(session, PAGE).text
    found = re.search(r"const channelSets = (\{.*?\});\s*\n", html, re.S)
    if not found:
        raise ValueError("the guide page no longer lists its channels")
    import json
    sets = json.loads(found.group(1))
    return [(one["file"], one.get("image") or "")
            for one in sets.get("entertainment") or []]


def text_of(pair) -> str:
    """Arabic when there is Arabic, else the English."""
    if not isinstance(pair, dict):
        return ""
    arabic = (pair.get("Arabic") or "").strip()
    return arabic or (pair.get("English") or "").strip()


def read_store(session) -> dict[str, dict[datetime, dict]]:
    rows: dict[str, dict[datetime, dict]] = {}
    first = datetime.now(timezone.utc).date() - timedelta(days=1)
    for file, logo in the_page_channels(session):
        known = which(logo)
        if not known:
            continue
        xid, _names = known
        for step in range(DAYS + 1):
            day = (first + timedelta(days=step)).isoformat()
            try:
                items = fetch(session, f"{STORE}{day}/{file}",
                              retries=1).json().get("responseObj") or []
            except Exception:                               # noqa: BLE001
                continue
            for item in items:
                try:
                    start = datetime.fromisoformat(item["StartTime"]).replace(
                        tzinfo=timezone.utc)
                    stop = datetime.fromisoformat(item["EndTime"]).replace(
                        tzinfo=timezone.utc)
                except (KeyError, TypeError, ValueError):
                    continue
                title = text_of(item.get("Title"))
                if not title or stop <= start:
                    continue
                rows.setdefault(xid, {})[start] = {
                    "start": start, "stop": stop, "title": title,
                    "desc": text_of(item.get("Synopsis"))
                            or text_of(item.get("Remarks")),
                    "category": text_of(item.get("Category")),
                }
    return rows


def read_all(session) -> dict[str, dict[datetime, dict]]:
    """The page's own data first; the HTML grid when that gives nothing."""
    try:
        rows = read_store(session)
        if rows:
            log(f"  bein.com guide data: {sum(len(v) for v in rows.values())}"
                f" rows on {len(rows)} channel(s)")
            return rows
        warn("bein.com guide data gave nothing — reading the grid instead")
    except Exception as exc:                                # noqa: BLE001
        warn(f"bein.com guide data failed ({exc}) — reading the grid instead")
    return read_grid(session)


def read_grid(session) -> dict[str, dict[datetime, dict]]:
    today = datetime.now(MECCA).date()
    rows: dict[str, dict[datetime, dict]] = {}
    for step in range(DAYS):
        day = today + timedelta(days=step)
        try:
            got = read_day(session, day)
        except Exception as exc:                            # noqa: BLE001
            warn(f"bein.com {day}: {exc}")
            continue
        log(f"  bein.com {day}: {sum(len(v) for v in got.values())} rows "
            f"on {len(got)} channel(s)")
        for xid, events in got.items():
            for ev in events:
                rows.setdefault(xid, {})[ev["start"]] = ev

    return rows


def add_to(root, session=None) -> tuple[int, int]:
    """Put every channel bein.com answers for into `root`, a guide being
    built — the beIN Qatar guide, which is where they were asked for.

    Returns (channels, programmes). write_xml_atomic puts channels
    before programmes however they were appended.
    """
    rows = read_all(session or new_session())
    for _piece, xid, names in CHANNELS:
        if not rows.get(xid):
            continue
        ch = ET.SubElement(root, "channel", {"id": xid})
        for name in names:
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
        ET.SubElement(ch, "icon", {"src": LOGO.format(
            xid.replace("beIN", "").replace(".qa", "").lower())})

    total = 0
    for _piece, xid, _names in CHANNELS:
        events = sorted(rows.get(xid, {}).values(), key=lambda e: e["start"])
        for i, ev in enumerate(events):
            # A row never runs over the next one's start.
            stop = ev["stop"]
            if i + 1 < len(events) and events[i + 1]["start"] < stop:
                stop = events[i + 1]["start"]
            if stop <= ev["start"]:
                continue
            add_programme(root, xid, ev["start"], stop, ev["title"],
                          ev["desc"], category=ev["category"] or None)
            total += 1
    log(f"beIN entertainment: {len(rows)} channel(s), {total} programme(s)")
    return len(rows), total


def build() -> int:
    """Standalone: the entertainment channels alone, for a look at them."""
    root = ET.Element("tv", {"generator-info-name": "beIN entertainment"})
    add_to(root)
    ok = write_xml_atomic(root, OUTPUT, generator_name="beIN entertainment",
                          min_programmes=1)
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
