#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Philippines — the channels of a Philippine playlist ("PH: …" / "PH…"),
asked for from photos of the player, every one on "No information".

Where each schedule comes from (checked 30 September):

- TV5: its own broadcast guide, tv5.com.ph/schedule — the week, each
  programme with its weekday, its start in Philippine time and its title.
- One Sports: its own programme guide, onesports.ph's programGuide.json —
  a week of days with every game, its time and whether it is live.
- The pan-Asian channels a Philippine line-up carries — HBO, Cinemax,
  History, BBC, CNN, CNA, NHK, KBS, Animax, beIN, SPOTV, GMA Pinoy TV and
  the rest: the same regional feeds air across South-East Asia, and
  epgshare01 carries their full schedules from the Singapore, Malaysian
  and Indonesian operators (SG1, MY1, ID1). Its Philippine files (PH1,
  PH2) list these channels with no programmes at all, so they are not used.

Not here, because nothing publishes them: ABS-CBN's channels (Kapamilya,
TFC, ANC, Cinemo, Myx, Teleradyo) — abs-cbn.com and tfc.tv refuse every
request (403); One Sports+, PBA Rush and UAAP Varsity (pba.ph sits behind
Cloudflare's challenge, UAAP has no site, Cignal Play needs a Philippine
login), RPTV, Buko, Tap, PBO, TMC, PTV,
Light TV, TV Maria, DepEd and Knowledge Channel publish no schedule; and
the GMA Pinoy TV "(NA)" feeds run on North American time, which no source
here carries.

Every playlist name gets a guide channel of its own, named exactly as the
playlist names it, so a player matches it by name and a second playlist
entry for the same channel is never left without one to pick.
"""

from __future__ import annotations

import gzip
import html as htmllib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import (add_programme, fetch, log, new_session, run_main, warn,
                     write_xml_atomic)

OUTPUT = "philippines_epg.xml"
EPGSHARE = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
TV5_GUIDE = "https://www.tv5.com.ph/schedule"
ONE_SPORTS_GUIDE = "https://www.onesports.ph/data/os/7/c/programGuide.json"
KEEP_BEHIND = timedelta(hours=12)
MANILA = timezone(timedelta(hours=8))

# source key -> (epgshare file, channel id there)
SOURCES = {
    "hbofamily": ("SG1", "HBO.Family.(HD).sg"),
    "hbohits": ("SG1", "HBO.Hits.(HD).sg"),
    "hbosig": ("SG1", "HBO.Signature.(HD).sg"),
    "cinemax": ("SG1", "CINEMAX.(HD).sg"),
    "lifetime": ("SG1", "Lifetime.(HD).sg"),
    "history": ("SG1", "HISTORY™.(HD).sg"),
    "discovery": ("MY1", "Discovery.Channel.HD.my"),
    "bbcearth": ("SG1", "BBC.Earth.(HD).sg"),
    "bbcworld": ("ID1", "BBC.World.News.id"),
    "cnn": ("SG1", "CNN.International.(HD).sg"),
    "cna": ("SG1", "CNA.(HD).sg"),
    "france24": ("SG1", "France.24.(English).sg"),
    "cgtn": ("SG1", "CGTN.sg"),
    "cctv4": ("SG1", "CCTV-4.(HD).sg"),
    "nhk": ("SG1", "NHK.World.–.Japan.(HD).sg"),
    "kbs": ("SG1", "KBS.World.(HD).sg"),
    "arirang": ("ID1", "Arirang.id"),
    "aljazeera": ("MY1", "Al.Jazeera.English.HD.my"),
    "animax": ("SG1", "Animax.(HD).sg"),
    "aniplus": ("SG1", "ANIPLUS.HD.sg"),
    "dreamworks": ("ID1", "Dreamworks.id"),
    "nickjr": ("SG1", "Nick.Jr..sg"),
    "hgtv": ("SG1", "HGTV.(HD).sg"),
    "hits": ("ID1", "HITS.id"),
    "hitsmovies": ("SG1", "HITS.Movies.HD..sg"),
    "rockaction": ("SG1", "ROCK.Action.(HD).sg"),
    "rockent": ("SG1", "ROCK.Entertainment.(HD).sg"),
    "outdoor": ("ID1", "Outdoor.Channel.id"),
    "afn": ("SG1", "AFN.(HD).sg"),
    "bein1": ("MY1", "beIN.SPORTS.1.my"),
    "bein2": ("SG1", "beIN.SPORTS.2.(HD).sg"),
    "spotv": ("ID1", "SPOTV.id"),
    "spotv2": ("SG1", "SPOTV.2.(HD).sg"),
    "premier": ("SG1", "Premier.Sports.sg"),
    "tvn": ("ID1", "tvN.id"),
    "techstorm": ("SG1", "TechStorm.(HD).sg"),
    "gmapinoy": ("SG1", "GMA.Pinoy.TV..sg"),
    "gmalife": ("SG1", "GMA.Life.TV.sg"),
    "gmanews": ("SG1", "GMA.News.TV.sg"),
    "tv5": ("TV5", ""),
    "onesports": ("ONESPORTS", ""),
}

# (the playlist's name for the channel, other names it goes by, source)
CHANNELS = (
    ("PH: DREAMWORKS", ("DreamWorks",), "dreamworks"),
    ("PHDREAMWORKS (TAGALOG)", ("PHDREAMWORKS (TAG)", "PHDREAMWORKS TAGALOG"), "dreamworks"),
    ("PH: GMA PINOY", ("GMA Pinoy TV",), "gmapinoy"),
    ("PHGMA PINOY TV", (), "gmapinoy"),
    ("PH: GMA NEWS TV", ("GMA News TV",), "gmanews"),
    ("PHGMA NEWS TV", (), "gmanews"),
    ("PH: GMA LIFE TV", ("GMA Life TV",), "gmalife"),
    ("PHSPOTV", ("SPOTV",), "spotv"),
    ("PHSPOTV 2", ("SPOTV 2",), "spotv2"),
    ("PHLIFETIME", ("Lifetime",), "lifetime"),
    ("PHHBO FAMILY", ("HBO Family",), "hbofamily"),
    ("PHHBO HITS", ("HBO Hits",), "hbohits"),
    ("PHHBO SIGNATURE", ("HBO Signature",), "hbosig"),
    ("PHFRANCE 24", ("France 24",), "france24"),
    ("PHCNN", ("CNN",), "cnn"),
    ("PHNICK JR", ("Nick Jr",), "nickjr"),
    ("PHCGTN", ("CGTN",), "cgtn"),
    ("PHHISTORY", ("History",), "history"),
    ("PHCCTV 4", ("CCTV 4",), "cctv4"),
    ("PHROCK ACTION", ("Rock Action",), "rockaction"),
    ("PHROCK ENTERTAINMENT", ("Rock Entertainment",), "rockent"),
    ("PH: TVN", ("tvN",), "tvn"),
    ("PHBBC WORLD NEWS", ("BBC World News",), "bbcworld"),
    ("PH: BBC NEWS", (), "bbcworld"),
    ("PHBBC EARTH", ("BBC Earth",), "bbcearth"),
    ("PH: BBC EARTH", (), "bbcearth"),
    ("PHARIRANG TV WORLD", ("Arirang",), "arirang"),
    ("PHAL JAZEERA", ("Al Jazeera English",), "aljazeera"),
    ("PH: AL JAZEERA", (), "aljazeera"),
    ("PHNHK WORLD", ("NHK World Japan",), "nhk"),
    ("PH: NHK JAPAN DR", ("PH: NHK JAPAN",), "nhk"),
    ("PHCHANNEL NEWS ASIA (CNA)", ("CNA", "Channel News Asia"), "cna"),
    ("PHDISCOVERY CHANNEL", ("Discovery Channel",), "discovery"),
    ("PHHGTV", ("HGTV",), "hgtv"),
    ("PH: HITS", ("HITS",), "hits"),
    ("PHHITS MOVIES", ("HITS Movies",), "hitsmovies"),
    ("PHKBS WORLD", ("KBS World",), "kbs"),
    ("PHANIMAX", ("Animax",), "animax"),
    ("PH: ANIMAX", (), "animax"),
    ("PH: ANIPLUS", ("Aniplus",), "aniplus"),
    ("PHCINEMAX", ("Cinemax",), "cinemax"),
    ("PHOUTDOOR CHANNEL", ("Outdoor Channel",), "outdoor"),
    ("PH: ASIAN FOOD", ("Asian Food Network", "AFN"), "afn"),
    ("PH: BEIN SPORTS 1", ("beIN Sports 1 PH",), "bein1"),
    ("PH: BEIN SPORTS 2", ("beIN Sports 2 PH",), "bein2"),
    ("PH: PREMIER SPORTS", ("Premier Sports",), "premier"),
    ("PH: TECHSTORM", ("TechStorm",), "techstorm"),
    ("PHTV5", ("PH: TV5", "TV5"), "tv5"),
    ("PHONE SPORTS", ("PH: ONE SPORTS", "One Sports"), "onesports"),
)


def channel_id(name: str) -> str:
    """"PH: ANIMAX" -> PH.PH_ANIMAX and "PHANIMAX" -> PH.PHANIMAX: two
    playlist entries, two guide channels."""
    return "PH." + re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def xmltv(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.strip(), "%Y%m%d%H%M%S %z").astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def read_epgshare(session, wanted: dict[str, set[str]]) -> tuple[dict, dict]:
    """source key -> rows, source key -> icon, from the epgshare files."""
    rows: dict[str, list[dict]] = {}
    icons: dict[str, str] = {}
    floor = datetime.now(timezone.utc) - KEEP_BEHIND
    for code, ids in wanted.items():
        try:
            text = gzip.decompress(fetch(session, EPGSHARE.format(code),
                                         timeout=180).content).decode("utf-8", "ignore")
        except Exception as exc:
            warn(f"Philippines: epgshare {code} unreadable ({exc})")
            continue
        for key, source_id in ids:
            esc = re.escape(htmllib.escape(source_id, quote=True))
            m = re.search(r'<channel id="' + esc + r'">.*?</channel>', text, re.S)
            if m:
                icon = re.search(r'<icon src="([^"]+)"', m.group(0))
                if icon:
                    icons[key] = htmllib.unescape(icon.group(1))
            got = []
            for block in re.findall(r'<programme\b[^>]*channel="' + esc
                                    + r'"[^>]*>.*?</programme>', text, re.S):
                node = ET.fromstring(block)
                start, stop = xmltv(node.get("start")), xmltv(node.get("stop"))
                title = (node.findtext("title") or "").strip()
                if not start or not stop or stop <= start or not title or stop < floor:
                    continue
                sub = (node.findtext("sub-title") or "").strip()
                desc = (node.findtext("desc") or "").strip()
                got.append({"start": start, "stop": stop, "title": title,
                            "desc": " — ".join(x for x in (sub, desc) if x)})
            rows[key] = got
    return rows, icons


def read_tv5(session) -> list[dict]:
    """TV5's own weekly guide. Each programme is an <li class="schedule-item">
    carrying its weekday, its start in Manila time and its title; a
    programme runs until the next one starts."""
    page = fetch(session, TV5_GUIDE, timeout=60).text
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")
    by_day: dict[int, dict[str, str]] = {}
    for tag in re.findall(r'<li class="schedule-item"[^>]*>', page):
        day = re.search(r'data-day="(\w+)"', tag)
        start = re.search(r'data-start-time="(\d{1,2}):(\d{2})"', tag)
        title = re.search(r'data-title="([^"]*)"', tag)
        if not (day and start and title) or day.group(1) not in days:
            continue
        hhmm = f"{int(start.group(1)):02d}:{start.group(2)}"
        by_day.setdefault(days.index(day.group(1)), {})[hhmm] = \
            htmllib.unescape(title.group(1)).strip()
    if not by_day:
        return []
    today = datetime.now(MANILA).date()
    starts = []
    for n in range(-1, 8):
        date = today + timedelta(days=n)
        for hhmm, title in sorted(by_day.get(date.weekday(), {}).items()):
            h, m = map(int, hhmm.split(":"))
            starts.append((datetime(date.year, date.month, date.day, h, m,
                                    tzinfo=MANILA).astimezone(timezone.utc), title))
    starts.sort()
    return [{"start": a, "stop": b, "title": t, "desc": ""}
            for (a, t), (b, _) in zip(starts, starts[1:])]


def read_one_sports(session) -> list[dict]:
    """One Sports' own programme guide (onesports.ph), a week of days, each
    programme with its date and time in Philippine time, its title, the
    match or episode, and whether it is live."""
    data = fetch(session, ONE_SPORTS_GUIDE, timeout=60).json()
    starts = {}
    for day in data.get("schedule") or []:
        for prog in day.get("programs") or []:
            hm = re.match(r"(\d{1,2}):(\d{2})", prog.get("time") or "")
            date = re.match(r"(\d{4})-(\d{2})-(\d{2})", day.get("date") or "")
            if not hm or not date:
                continue
            start = datetime(int(date.group(1)), int(date.group(2)), int(date.group(3)),
                             int(hm.group(1)), int(hm.group(2)),
                             tzinfo=MANILA).astimezone(timezone.utc)
            title = re.sub(r"\s+", " ", prog.get("title") or "").strip()
            sub = re.sub(r"\s+", " ", prog.get("subtitle") or "").strip()
            if not title:
                continue
            # The guide's editor splits "…9:00Pm Game)" at its colon.
            if sub and re.search(r"\d$", title) and re.match(r"\d{2}\s*[AaPp]m", sub):
                title, sub = f"{title}:{sub}", ""
            if sub:
                title = f"{title}: {sub}"
            if prog.get("live") and "live" not in title.lower():
                title += " (Live)"
            starts[start] = title
    ordered = sorted(starts.items())
    out = [{"start": a, "stop": b, "title": t, "desc": ""}
           for (a, t), (b, _) in zip(ordered, ordered[1:])]
    if ordered:
        a, t = ordered[-1]
        out.append({"start": a, "stop": a + timedelta(hours=2), "title": t, "desc": ""})
    return out


def tidy(rows: list[dict]) -> list[dict]:
    rows = sorted(rows, key=lambda r: r["start"])
    for a, b in zip(rows, rows[1:]):
        if b["start"] < a["stop"]:
            a["stop"] = b["start"]
    return [r for r in rows if r["stop"] > r["start"]]


# The Philippine sports channels, asked for on the Roya link as well. The
# Roya guide reads them through collect/emit like its other readers, under
# ids of their own (RoyaPH.…) so the merged link never holds one id twice.
SPORTS = ("onesports", "bein1", "bein2", "spotv", "spotv2", "premier")


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    wanted: dict[str, set] = {}
    for key in SPORTS:
        code, sid = SOURCES[key]
        if code != "ONESPORTS":
            wanted.setdefault(code, set()).add((key, sid))
    rows, icons = read_epgshare(session, wanted)
    try:
        rows["onesports"] = read_one_sports(session)
    except Exception as exc:
        warn(f"Philippines: One Sports guide unreadable ({exc})")
    out = {}
    for name, others, key in CHANNELS:
        if key in SPORTS and rows.get(key):
            out["Roya" + channel_id(name)] = {
                "names": (name,) + tuple(others), "icon": icons.get(key, ""),
                "rows": tidy([dict(r) for r in rows[key]])}
    log(f"  Philippine sports{'':13} {len(out)} channels")
    return out


def emit(root: ET.Element, per_channel: dict) -> int:
    count = 0
    for xid, ch_data in per_channel.items():
        ch = ET.SubElement(root, "channel", {"id": xid})
        for n in ch_data["names"]:
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = n
        if ch_data["icon"]:
            ET.SubElement(ch, "icon", {"src": ch_data["icon"]})
        for r in ch_data["rows"]:
            add_programme(root, xid, r["start"], r["stop"], r["title"], r["desc"])
            count += 1
    return count



def build() -> int:
    log("PHILIPPINES EPG | TV5 own guide + pan-Asian feeds (epgshare SG1/MY1/ID1)")
    session = new_session()
    wanted: dict[str, set] = {}
    for key, (code, sid) in SOURCES.items():
        if code not in ("TV5", "ONESPORTS"):
            wanted.setdefault(code, set()).add((key, sid))
    rows, icons = read_epgshare(session, wanted)
    for key, reader in (("tv5", read_tv5), ("onesports", read_one_sports)):
        try:
            rows[key] = reader(session)
        except Exception as exc:
            warn(f"Philippines: {key} guide unreadable ({exc})")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Philippines"})
    written = []
    for name, others, key in CHANNELS:
        got = tidy([dict(r) for r in rows.get(key) or []])
        if not got:
            warn(f"Philippines: nothing for {name} ({key}) this run")
            continue
        xid = channel_id(name)
        ch = ET.SubElement(root, "channel", {"id": xid})
        for n in (name,) + tuple(others):
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = n
        if icons.get(key):
            ET.SubElement(ch, "icon", {"src": icons[key]})
        written.append((xid, got))
    total = 0
    for xid, got in written:
        for r in got:
            add_programme(root, xid, r["start"], r["stop"], r["title"], r["desc"])
            total += 1
    log(f"Philippines: {len(written)}/{len(CHANNELS)} channels, {total} programmes")
    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Philippines",
                     min_programmes=500)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
