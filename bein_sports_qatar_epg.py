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
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from epg_lib import add_programme, fetch, log, new_session, run_main, utc_now, warn, write_xml_atomic

OUTPUT = "bein_sports_qatar_epg.xml"

QATAR = ZoneInfo("Asia/Qatar")
UTC = timezone.utc

DAYS_BACK = 1
DAYS_FORWARD = 6

API_CHANNELS = "https://www.beinsports.com/api/opta/tv-channel"
API_EVENTS = "https://www.beinsports.com/api/opta/tv-event"

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
        events.append({
            "start": start.astimezone(UTC),
            "stop": stop.astimezone(UTC),
            "title": (row.get("title") or "").strip() or "beIN SPORTS",
            "desc": (row.get("description") or "").strip(),
        })
    return sorted(events, key=lambda e: e["start"])


def build() -> int:
    log("beIN SPORTS QATAR/MENA EPG | official beinsports.com Opta API | full roster")
    session = new_session()
    channels = load_channels(session)
    log(f"Total channels in roster: {len(channels)}")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — beIN Sports Qatar"})
    for xid, (name, _guid) in sorted(channels.items()):
        ch = ET.SubElement(root, "channel", id=xid)
        ET.SubElement(ch, "display-name", lang="en").text = name

    now = utc_now()
    total = 0
    ok_channels = 0
    for xid, (name, guid) in sorted(channels.items()):
        try:
            events = fetch_events_for_channel(session, guid)
        except Exception as exc:
            warn(f"{name}: schedule fetch failed | {exc}")
            continue

        if events:
            ok_channels += 1
        for ev in events:
            add_programme(
                root, xid, ev["start"], ev["stop"], ev["title"], ev["desc"],
                category="Sports", live_eligible=True, now=now,
            )
            total += 1

    log(f"beIN Qatar/MENA: {ok_channels}/{len(channels)} channels returned programmes, {total} programmes total")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — beIN Sports Qatar")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
