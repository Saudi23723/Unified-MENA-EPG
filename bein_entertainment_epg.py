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


def read_all(session) -> dict[str, dict[datetime, dict]]:
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
