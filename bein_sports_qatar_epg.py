#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beIN SPORTS Qatar / MENA — full official EPG.

Source: beinsports.com's own public "Opta" TV-guide API (the same API the
official beinsports.com website itself calls to render its TV guide and
that beinsports.com/en-us/tv-guide exposes publicly). No data is invented:
every title/description/start/stop comes straight from that API.

  Channel list : GET /api/opta/tv-channel?region=ar-mena
  Schedule     : GET /api/opta/tv-event?startBefore=...&endAfter=...&channelIds=<id>

If the live channel-list call fails, we fall back to the last-known-good
channel roster below (site_id GUIDs are stable — beIN does not recycle
them), so the script still produces a full, correct EPG.

Two things the API gives us that are used here:

  * every event row carries beIN's own `live` flag ("True"/"False"). The
    Live badge follows that flag, not the clock, so a match still shows as
    a live broadcast when you browse ahead to it — which is what LIVE means
    in an EPG.
  * some channels (the AFC set, NBA, 4K HDR) answer 200 with zero rows:
    beIN publishes no schedule for them. Those are left out of the file
    entirely rather than shown as empty rows in TiviMate. Nothing is
    hardcoded — a channel reappears by itself the moment beIN starts
    scheduling it again.

Logos are served from this repository (see fetch_logos.py), not hot-linked,
because third-party image hosts rate-limit and break.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, run_main, utc_now, warn,
    with_live_badge, write_xml_atomic,
)

OUTPUT = "bein_sports_qatar_epg.xml"

QATAR = ZoneInfo("Asia/Qatar")
UTC = timezone.utc

DAYS_BACK = 1
DAYS_FORWARD = 6

API_CHANNELS = "https://www.beinsports.com/api/opta/tv-channel"
API_EVENTS = "https://www.beinsports.com/api/opta/tv-event"

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

# xmltv id -> the logo file fetch_logos.py writes into logos/. A channel
# missing from this map simply gets no icon; it never breaks the guide.
LOGO_KEYS = {
    "beIN4K.qa": "bein_4k",
    "beINSports.qa": "bein_brand",
    "beINSports1.qa": "bein_1",
    "beINSports2.qa": "bein_2",
    "beINSports3.qa": "bein_3",
    "beINSports4.qa": "bein_4",
    "beINSports4KHdr.qa": "bein_4khdr",
    "beINSports5.qa": "bein_5",
    "beINSports6.qa": "bein_6",
    "beINSports7.qa": "bein_7",
    "beINSports8.qa": "bein_8",
    "beINSports9.qa": "bein_9",
    "beINSportsAFC.qa": "bein_afc",
    "beINSportsAFC1.qa": "bein_afc1",
    "beINSportsAFC2.qa": "bein_afc2",
    "beINSportsAFC3.qa": "bein_afc3",
    "beINSportsAFC4.qa": "bein_afc4",
    "beINSportsAFC5.qa": "bein_afc5",
    "beINSportsAFC6.qa": "bein_afc6",
    "beINSportsEn1.qa": "bein_en1",
    "beINSportsEn2.qa": "bein_en2",
    "beINSportsFr1.qa": "bein_fr1",
    "beINSportsFr2.qa": "bein_fr2",
    "beINSportsMax1.qa": "bein_max1",
    "beINSportsMax2.qa": "bein_max2",
    "beINSportsMax3.qa": "bein_max3",
    "beINSportsMax4.qa": "bein_max4",
    "beINSportsMax5.qa": "bein_max5",
    "beINSportsMax6.qa": "bein_max6",
    "beINSportsNBA.qa": "bein_nba",
    "beINSportsNews.qa": "bein_news",
    "beINSportsXtra1.qa": "bein_xtra1",
    "beINSportsXtra2.qa": "bein_xtra2",
    "beINSportsXtra3.qa": "bein_xtra3",
    "beINSportsXtra4.qa": "bein_xtra4",
    "beINSportsXtra5.qa": "bein_xtra5",
    "beINSportsXtra6.qa": "bein_xtra6",
    "beINSportsXtra7.qa": "bein_xtra7",
    "beINSportsXtra8.qa": "bein_xtra8",
    "beINSportsXtra9.qa": "bein_xtra9",
}


def channel_icon(xid: str) -> str | None:
    keyname = LOGO_KEYS.get(xid)
    return f"{LOGO_BASE}/{keyname}.png" if keyname else None


# Last-known-good roster (site_id is a stable Opta GUID beIN does not
# recycle). Used whenever the live channel-list call fails, and merged
# with any channel the live call discovers so new channels appear too.
FALLBACK_CHANNELS = {
    "beINSports1.qa": ("beIN SPORTS 1", "7836FEA9-6B39-4A1A-8352-DC5FCB97A16C"),
    "beINSports2.qa": ("beIN SPORTS 2", "FD1DD7DD-1E7B-4AA2-8682-BFA17338E653"),
    "beINSports3.qa": ("beIN SPORTS 3", "8AEA2426-D451-4BA5-BF48-114A1F04B1A8"),
    "beINSports4.qa": ("beIN SPORTS 4", "DB9361E8-B3EB-4D6F-9A82-75B5F09E2F92"),
    "beINSports5.qa": ("beIN SPORTS 5", "964E6246-CA95-410B-82C4-EA75DD979435"),
    "beINSports6.qa": ("beIN SPORTS 6", "E24D9C11-A8B4-4C7F-AD3E-B3364FB6D5A2"),
    "beINSports7.qa": ("beIN SPORTS 7", "A892063B-A5D9-4199-95AC-6A214515FA6B"),
    "beINSports8.qa": ("beIN SPORTS 8", "0F8D20A4-D46C-4B18-9242-8E7B3E978FF8"),
    "beINSportsMax1.qa": ("beIN SPORTS MAX 1", "2FB43094-3598-43C1-A3BA-44BFB40092E0"),
    "beINSportsMax2.qa": ("beIN SPORTS MAX 2", "008F0EA9-FCD9-4E8C-849A-913979E7450A"),
    "beINSportsMax3.qa": ("beIN SPORTS MAX 3", "7783DC02-4527-4094-9EE3-CDA8E093E4EB"),
    "beINSportsMax4.qa": ("beIN SPORTS MAX 4", "5B15611A-5F9D-4EF0-89A6-677C9CA2BD5D"),
    "beINSportsMax5.qa": ("beIN SPORTS MAX 5", "F7215920-CCF9-4DBB-8B9D-152E232FA549"),
    "beINSportsMax6.qa": ("beIN SPORTS MAX 6", "DC04009D-7E18-4D1C-BA7F-7269B8F8D065"),
    "beINSportsXtra1.qa": ("beIN SPORTS XTRA 1", "E3B37FA0-E582-45B2-BB8E-516E1A714EF6"),
    "beINSportsXtra2.qa": ("beIN SPORTS XTRA 2", "27E67022-B943-4913-9AF3-AFD3DAC9854B"),
    "beINSportsXtra3.qa": ("beIN SPORTS XTRA 3", "CDF1A4C8-26DD-4C33-A239-F729A3B09295"),
    "beINSportsXtra4.qa": ("beIN SPORTS XTRA 4", "7A8040D9-7BAF-477E-B9F7-8BAB88F677E8"),
    "beINSportsXtra5.qa": ("beIN SPORTS XTRA 5", "51D28C47-7B79-4007-81A3-BFDF9BC65A3B"),
    "beINSportsXtra6.qa": ("beIN SPORTS XTRA 6", "9ABD32F9-C6D9-4DD5-B936-2C7E6546292E"),
    "beINSportsXtra7.qa": ("beIN SPORTS XTRA 7", "1752F091-A114-4629-BED4-46E0BB488A24"),
    "beINSportsXtra8.qa": ("beIN SPORTS XTRA 8", "CD634732-20D1-4137-94E7-939DE93D056D"),
    "beINSportsXtra9.qa": ("beIN SPORTS XTRA 9", "522050CE-EBD3-43EA-B636-42B034FDC05C"),
    "beINSportsAFC.qa": ("beIN SPORTS AFC", "10A2A142-F98C-4706-9FD0-2D3C36045D63"),
    "beINSportsAFC1.qa": ("beIN SPORTS 1 AFC", "0CB3E227-4376-4545-AB64-D6C390F644D8"),
    "beINSportsAFC2.qa": ("beIN SPORTS 2 AFC", "EEB3E4E8-0F9D-4735-943C-AEA3E39C87DE"),
    "beINSportsAFC3.qa": ("beIN SPORTS 3 AFC", "A2D36A21-00D5-4001-A443-81CF2C06553F"),
    "beINSportsAFC4.qa": ("beIN SPORTS 4 AFC", "42680C3C-580F-43DA-BDD8-02651BD10F32"),
    "beINSportsAFC5.qa": ("beIN SPORTS 5 AFC", "B0DBD19A-9F44-4197-BD09-2B6A5F315F3B"),
    "beINSportsAFC6.qa": ("beIN SPORTS 6 AFC", "2BF668DF-1B76-4199-88CE-8691FD86AD8C"),
    "beINSports9.qa": ("beIN SPORTS 9", "5C08D9D3-C713-4F1F-947E-87C761428B9B"),
    "beINSportsNews.qa": ("beIN SPORTS NEWS", "7B558284-F996-4123-9584-1E5D01844270"),
    "beINSportsNBA.qa": ("beIN SPORTS NBA", "2F518547-2269-4C07-93D5-2733397472BD"),
    "beIN4K.qa": ("beIN 4K", "67DD49E9-E3A2-4B3A-94B8-88C620A4DFB1"),
}


def slugify(name: str) -> str:
    words = re.findall(r"[A-Za-z]+|\d+", name)
    rest = [w for w in words if w.upper() not in {"BEIN", "SPORTS"}]
    titled = [w if w.isdigit() else w[:1].upper() + w[1:].lower() for w in rest]
    return "beINSports" + "".join(titled) + ".qa"


def load_channels(session) -> dict[str, tuple[str, str]]:
    """Return {xmltv_id: (display_name, site_id_guid)}; merges live + fallback."""
    channels = dict(FALLBACK_CHANNELS)
    known_guids = {guid for _, guid in channels.values()}

    try:
        r = fetch(session, API_CHANNELS, params={"region": "ar-mena"})
        data = r.json()
        rows = data.get("rows", [])
        added = 0
        for row in rows:
            guid = row.get("id")
            name = (row.get("name") or "").strip()
            if not guid or not name or guid in known_guids:
                continue
            xid = slugify(name)
            # avoid id collisions
            base_xid, i = xid, 2
            while xid in channels:
                xid = f"{base_xid.rsplit('.qa', 1)[0]}{i}.qa"
                i += 1
            channels[xid] = (name, guid)
            known_guids.add(guid)
            added += 1
        log(f"beIN Qatar live channel list OK: {len(rows)} channels ({added} new vs fallback)")
    except Exception as exc:
        warn(f"beIN Qatar live channel list failed, using fallback roster only: {exc}")

    return channels


def fetch_events_for_channel(session, guid: str) -> list[dict]:
    now = utc_now()
    start_before = (now + timedelta(days=DAYS_FORWARD)).strftime("%Y-%m-%dT%H:%M:%S.000")
    end_after = (now - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%S.000")

    r = fetch(
        session, API_EVENTS,
        params={
            "startBefore": f"{start_before}Z",
            "endAfter": f"{end_after}Z",
            "channelIds": guid,
        },
    )
    data = r.json()
    rows = data.get("rows", []) or []

    events = []
    for row in rows:
        try:
            start = datetime.fromisoformat(row["startDate"].replace("Z", "+00:00"))
            stop = datetime.fromisoformat(row["endDate"].replace("Z", "+00:00"))
        except Exception:
            continue
        if stop <= start:
            continue
        # beIN sends the flag as the string "True"/"False", and older rows
        # have carried a real bool, so accept both.
        flag = row.get("live")
        is_live = flag is True or (isinstance(flag, str) and flag.strip().lower() == "true")

        events.append({
            "start": start.astimezone(UTC),
            "stop": stop.astimezone(UTC),
            "title": (row.get("title") or "").strip() or "beIN SPORTS",
            "desc": (row.get("description") or "").strip(),
            "live": is_live,
        })
    return sorted(events, key=lambda e: e["start"])


def build() -> int:
    log("beIN SPORTS QATAR/MENA EPG | official beinsports.com Opta API | full roster")
    session = new_session()
    channels = load_channels(session)
    log(f"Total channels in roster: {len(channels)}")

    # Collect first, emit second: a channel beIN publishes no schedule for
    # must not appear in the file as an empty row.
    per_channel: dict[str, list[dict]] = {}
    for xid, (name, guid) in sorted(channels.items()):
        try:
            per_channel[xid] = fetch_events_for_channel(session, guid)
        except Exception as exc:
            warn(f"{name}: schedule fetch failed | {exc}")
            per_channel[xid] = []

    # A channel whose whole schedule is one repeated title is not publishing a
    # schedule at all: it is the channel's own blurb chopped into equal blocks
    # (beIN does this on XTRA and MAX). beIN sets its live flag on those rows
    # too, which would badge every hour of every day on nine channels and bury
    # the real matches. Detected from the data, so the moment beIN publishes a
    # genuine schedule for one of them it starts being badged normally.
    placeholder = {
        xid for xid, evs in per_channel.items()
        if len(evs) > 1 and len({e["title"] for e in evs}) == 1
    }
    if placeholder:
        log(
            f"{len(placeholder)} channel(s) carry only a repeated blurb, not a real "
            f"schedule — not badging those: "
            f"{', '.join(channels[x][0] for x in sorted(placeholder))}"
        )

    with_data = [x for x in sorted(channels) if per_channel.get(x)]
    empty = [channels[x][0] for x in sorted(channels) if not per_channel.get(x)]
    if empty:
        log(f"No schedule published for {len(empty)} channel(s), left out: {', '.join(empty)}")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — beIN Sports Qatar"})
    for xid in with_data:
        name, _guid = channels[xid]
        ch = ET.SubElement(root, "channel", id=xid)
        ET.SubElement(ch, "display-name", lang="en").text = name
        icon = channel_icon(xid)
        if icon:
            ET.SubElement(ch, "icon", src=icon)

    total = 0
    live_count = 0
    for xid in with_data:
        for ev in per_channel[xid]:
            live = ev["live"] and xid not in placeholder
            title = with_live_badge(ev["title"]) if live else ev["title"]
            if live:
                live_count += 1
            p = add_programme(
                root, xid, ev["start"], ev["stop"], title, ev["desc"],
                category="Sports",
            )
            if live:
                ET.SubElement(p, "category", lang="en").text = "Live"
            total += 1

    icons = sum(1 for c in root.findall("channel") if c.find("icon") is not None)
    log(
        f"beIN Qatar/MENA: {len(with_data)}/{len(channels)} channels with a schedule, "
        f"{total} programmes, {live_count} live, {icons} channel logos"
    )

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — beIN Sports Qatar")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
