#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The UAE's own channels — Dubai, Abu Dhabi and Sharjah — on the Roya link.

Asked for from three photographs of a player's guide, rows of Dubai, Abu
Dhabi, Dubai One, Al Emarat, Sama Dubai, Al Sharjah, Sharqia, AD Nat Geo,
Dubai Sports and Dubai Racing standing empty or wrong: "can you find the
correct, original schedules, and add them with the original logos?" —
and then, of where they come from, "a reliable source".

So every schedule here comes from the broadcaster or its licensed
platform, never from a feed that copies channels into one another. The
aggregated UAE feeds were measured first, on 26 September 2026, and
failed that test outright: open-epg's uae1 gives "Sharjah Quran TV" the
cartoons of Majid Kids and a dozen stations one identical filler day.

WHERE EACH SCHEDULE COMES FROM

  Dubai Media Incorporated publishes a week of each channel as JSON, the
  file its own sites' schedule pages read:
      https://www.dubaitv.ae/content/dam/Common/json/<CODE>.json
  DUB  Dubai TV       DUB1 Dubai One       SAMA Sama Dubai
  NOOR Noor Dubai     RACE Dubai Racing    RAC2 Dubai Racing 2
  SPRT Dubai Sports    SPT2 Dubai Sports 2
  Each programme carries its start as "calendar_time", the Gulf's wall
  clock ("2026-09-26T00:05:04:10" — date, time, frames), with the same
  instant again as "start_time_gmt" four hours earlier. The clock is the
  file's own, stated twice, so nothing about it is assumed.

  Abu Dhabi Media's own site hands its schedule to STARZPLAY, its
  licensed platform (adtv.ae/schedule redirects to starzplay.com/admn),
  and STARZPLAY's web-EPG API is the one starzplay_epg.py already reads.
  The same API carries the Sharjah Broadcasting Authority's Sharjah TV and
  Sharqiya from Kalba, whose own programme grid (sbauae.faulio.com)
  answers every channel with an empty grid. Every event there is a pair
  of UNIX instants — again no clock to guess.

WHAT IS NOT HERE, AND WHY. Sharjah 2 has no schedule on either SBA's
grid or STARZPLAY. Fujairah TV's own site lists six to eight programmes
a day with long gaps and no stated clock. A channel with no reliable
schedule is left without one rather than given a wrong one.

THE LOGOS are each broadcaster's own, downloaded once from its own site
(Dubai Media's, SBA's) or its licensed platform (ADMN's, from STARZPLAY)
and kept in logos/uae/.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

import starzplay_epg
from epg_lib import add_programme, fetch, log, norm, resolve_overlaps, utc_now, warn

UTC = timezone.utc
GULF = ZoneInfo("Asia/Dubai")

DUBAI_JSON = "https://www.dubaitv.ae/content/dam/Common/json/{code}.json"
LOGO_BASE = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/logos/uae")
LOGO_DIR = os.path.join("logos", "uae")

# (xmltv id, logo stem, [every name a playlist uses — the first is the one
#  shown], (source, the source's own key))
CHANNELS = [
    ("DubaiTV.ae", "dubai_tv",
     ["Dubai TV", "DUBAI TV", "DUBAI", "Dubai", "Dubai HD", "تلفزيون دبي", "دبي"],
     ("dubai", "DUB")),
    ("DubaiOne.ae", "dubai_one",
     ["Dubai One", "DUBAI ONE", "Dubai One HD", "دبي وان"],
     ("dubai", "DUB1")),
    ("SamaDubai.ae", "sama_dubai",
     ["Sama Dubai", "SAMA DUBAI", "Sama Dubai HD", "سما دبي"],
     ("dubai", "SAMA")),
    ("NoorDubai.ae", "noor_dubai",
     ["Noor Dubai", "NOOR DUBAI", "Noor Dubai TV", "Noor DubaiTV", "نور دبي"],
     ("dubai", "NOOR")),
    ("DubaiSports.ae", "dubai_sports",
     ["Dubai Sports 1", "DUBAI SPORTS 1", "Dubai Sports", "DUBAI SPORTS",
      "Dubai Sport 1", "DUBAI SPORT 1", "Dubai Sports 1 HD", "دبي الرياضية",
      "دبي الرياضية 1"],
     ("dubai", "SPRT")),
    ("DubaiSports2.ae", "dubai_sports",
     ["Dubai Sports 2", "DUBAI SPORT 2", "DUBAI SPORTS 2", "Dubai Sport 2",
      "دبي الرياضية 2"],
     ("dubai", "SPT2")),
    ("DubaiRacing.ae", "dubai_racing",
     ["Dubai Racing", "DUBAI RACING 1 TV", "DUBAI RACING 1", "Dubai Racing 1",
      "Dubai Racing 1 HD", "Dubai Racing 1 TV", "دبي ريسنج", "دبي للسباقات"],
     ("dubai", "RACE")),
    ("DubaiRacing2.ae", "dubai_racing",
     ["Dubai Racing 2", "DUBAI RACING 2", "Dubai Racing 2 TV", "دبي ريسنج 2",
      "دبي للسباقات 2"],
     ("dubai", "RAC2")),
    ("AbuDhabiTV.ae", "abu_dhabi_tv",
     ["Abu Dhabi TV", "ABU DHABI", "Abu Dhabi", "ABU DHABI TV", "Abu Dhabi HD",
      "قناة أبوظبي", "أبوظبي"],
     ("starz", "admnabudhabichannel")),
    ("AlEmaratTV.ae", "al_emarat",
     ["Al Emarat", "AL EMARAT", "Al Emarat TV", "Emarat TV", "Emarat HD",
      "قناة الإمارات"],
     ("starz", "admnalemarattv")),
    ("NatGeoAbuDhabi.ae", "natgeo_ad",
     ["National Geographic Abu Dhabi", "AD NAT GEO", "Nat Geo Abu Dhabi",
      "Nat Geo AD", "NatGeo Abu Dhabi", "ناشيونال جيوغرافيك أبوظبي"],
     ("starz", "nationalgeographicabudhabitv")),
    ("SharjahTV.ae", "sharjah_tv",
     ["Sharjah TV", "AL SHARJAH", "Al Sharjah", "AI SHARJAH", "Sharjah",
      "Sharjah HD", "تلفزيون الشارقة", "الشارقة"],
     ("starz", "sharjahtv")),
    ("SharqiyaKalba.ae", "sharqiya_kalba",
     ["Sharqiya from Kalba", "SHARQIA", "Sharqia", "Al Sharqiya",
      "Sharqiya from Kalba HD", "الشرقية من كلباء", "الشرقية"],
     ("starz", "sharqiyafromKalba")),
]

KEEP_BEHIND = timedelta(days=1)
# The last programme in a Dubai file has no successor to end it.
LAST_RUN = timedelta(hours=1)
# Longer than this between two starts is a gap in the file, not a programme.
LONGEST = timedelta(hours=6)

AN_EPISODE = re.compile(r"\s*:\s*Ep\s*(\d+)\s*$", re.I)


def a_title(raw: str) -> str:
    """"الراوي: Ep   01" → "الراوي - الحلقة 1"; anything else as written."""
    title = norm(raw or "")
    found = AN_EPISODE.search(title)
    if found:
        base = norm(title[:found.start()]).rstrip(":").strip()
        return f"{base} - الحلقة {int(found.group(1))}"
    return title


def gulf_start(row: dict) -> datetime | None:
    """The start the file states, in the Gulf's clock, as UTC."""
    stamp = (row.get("calendar_time") or "")[:19]
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=GULF).astimezone(UTC)
    except ValueError:
        return None


def dubai_rows(session, code: str, floor: datetime) -> list[dict]:
    data = fetch(session, DUBAI_JSON.format(code=code)).json()
    starts: dict[datetime, dict] = {}
    for day in (data.get("programmes_by_date") or {}).values():
        for row in day or []:
            start = gulf_start(row)
            title = a_title(row.get("title") or row.get("arabic_title") or "")
            if start and title:
                starts.setdefault(start, {"start": start, "title": title,
                                          "desc": norm(row.get("synopsis") or "")})
    ordered = [starts[k] for k in sorted(starts)]
    out = []
    for this, after in zip(ordered, ordered[1:] + [None]):
        stop = after["start"] if after else this["start"] + LAST_RUN
        if stop - this["start"] > LONGEST:
            stop = this["start"] + LAST_RUN
        if stop <= this["start"] or stop < floor:
            continue
        out.append(dict(this, stop=stop))
    return out


def starz_rows(by_lang: dict[str, dict], slug: str, floor: datetime) -> list[dict]:
    ar = by_lang.get("ar", {}).get(slug) or {}
    en = by_lang.get("en", {}).get(slug) or {}
    english = {int(e["tsStart"]): e for e in en.get("events") or [] if e.get("tsStart")}
    out = []
    for event in ar.get("events") or en.get("events") or []:
        try:
            start = datetime.fromtimestamp(int(event["tsStart"]), UTC)
            stop = datetime.fromtimestamp(int(event["tsEnd"]), UTC)
        except (KeyError, TypeError, ValueError):
            continue
        title = norm(event.get("title") or "")
        if not title or stop <= start or stop < floor:
            continue
        other = norm((english.get(int(event["tsStart"])) or {}).get("title") or "")
        out.append({"start": start, "stop": stop, "title": title,
                    "alt": other if other and other != title else "",
                    "desc": norm(event.get("description") or "")})
    return out


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    """Every UAE channel's programmes, from its broadcaster's own schedule."""
    floor = utc_now() - KEEP_BEHIND
    by_lang: dict[str, dict] | None = None
    out: dict[str, list[dict]] = {}
    for xmltv_id, _logo, names, (source, key) in CHANNELS:
        try:
            if source == "dubai":
                rows = dubai_rows(session, key, floor)
            else:
                if by_lang is None:
                    now = utc_now()
                    by_lang = {lang: {c.get("slug"): c for c in
                                      starzplay_epg.fetch_all_channels(session, now, lang)}
                               for lang in ("ar", "en")}
                rows = starz_rows(by_lang, key, floor)
        except Exception as exc:                                  # noqa: BLE001
            warn(f"UAE: {names[0]} could not be read ({exc}) — left out this run")
            continue
        if rows:
            out[xmltv_id] = rows
            log(f"  {names[0]:30} {len(rows):4} programmes ({source})")
        else:
            warn(f"UAE: {names[0]} has nothing this run and is left out")
    return out


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    """Declare the UAE channels that have programmes and write them."""
    total = 0
    for xmltv_id, logo, names, _source in CHANNELS:
        rows = per_channel.get(xmltv_id)
        if not rows:
            continue
        channel = ET.SubElement(root, "channel", id=xmltv_id)
        # The name a player shows first, under both language tags, then
        # every spelling a playlist uses — "DUBAI RACING 1 TV", "AD NAT
        # GEO" — so a player matching by name finds the channel whichever
        # way its list writes it. The same rule as osn_epg.emit.
        ET.SubElement(channel, "display-name", lang="ar").text = names[0]
        seen: set[str] = set()
        for name in names + [n.upper() for n in names if n.isascii()]:
            if name in seen:
                continue
            seen.add(name)
            ET.SubElement(channel, "display-name",
                          lang="en" if name.isascii() else "ar").text = name
        if os.path.exists(os.path.join(LOGO_DIR, f"{logo}.png")):
            ET.SubElement(channel, "icon", src=f"{LOGO_BASE}/{logo}.png")
        for event in resolve_overlaps(sorted(rows, key=lambda e: e["start"])):
            add_programme(root, xmltv_id, event["start"], event["stop"],
                          event["title"], event.get("desc", ""),
                          alt_titles=[("en", event["alt"])] if event.get("alt") else None)
            total += 1
    log(f"UAE: {len(per_channel)}/{len(CHANNELS)} channels, {total} programmes")
    return total
