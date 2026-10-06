#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The Alwan channels no guide had: films, series, documentaries, songs,
children's, Quran, and the F1, WWE and UFC sports feeds.

Asked for outright, from photos of the player: every one of them sat on
"No information", with a logo from the playlist and nothing behind it.
Alwan publishes no schedule for them, so this guide says what they are —
channels that run all day — as one "24/7 Program" row a day, under the
names the playlist gives them, each with its own logo in Alwan's style
(make_alwan_channel_logos.py draws them).

They ride on the Alwan guide itself (update_alwan_epg.py adds them to
alwan_sports_epg.xml, beside the numbered Alwan Sport channels and their
real matches): that is the link the player reads Alwan from, and a
separate file never reached it.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme, log, run_main, write_xml_atomic

OUTPUT = "alwan_channels_epg.xml"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/alwan_{key}.png")
TITLE = "24/7 Program"
DAYS_BACK = 1
DAYS_FORWARD = 7

# (key, names the playlist uses, the Arabic name on the logo, colour,
#  the tag above the name)
CHANNELS = (
    ("aflam1", ("Alwan Aflam 1 4K", "Alwan Aflam 1"), "أفلام 1",
     (40, 120, 230), "الوان"),
    ("aflam2", ("Alwan Aflam 2 4K", "Alwan Aflam 2"), "أفلام 2",
     (40, 120, 230), "الوان"),
    ("aflam3", ("Alwan Aflam 3 4K", "Alwan Aflam 3"), "أفلام 3",
     (40, 120, 230), "الوان"),
    ("aflam4", ("Alwan Aflam 4 4K", "Alwan Aflam 4"), "أفلام 4",
     (40, 120, 230), "الوان"),
    ("mosalsalat", ("Alwan Mosalsalat 4K", "Alwan Mosalsalat"), "مسلسلات",
     (70, 90, 225), "الوان"),
    ("mosalsalat_plus", ("Alwan Mosalsalat+ 4K", "Alwan Mosalsalat+",
                         "Alwan Mosalsalat Plus 4K"), "مسلسلات+",
     (70, 90, 225), "الوان"),
    ("turkey", ("Alwan Turkey 4K", "Alwan Turkey"), "تركي",
     (240, 60, 150), "الوان"),
    ("korea", ("Alwan Korea 4K", "Alwan Korea"), "كوريا",
     (160, 80, 225), "الوان"),
    ("bollywood", ("Alwan Bollywood 4K", "Alwan Bollywood"), "بوليوود",
     (245, 130, 30), "الوان"),
    ("anime", ("Alwan Anime 4K", "Alwan Anime"), "أنيمي",
     (20, 185, 190), "الوان"),
    ("wathaeqiya", ("Alwan Alwathaeqye 4K", "Alwan Alwathaeqye",
                    "Alwan Documentary 4K"), "الوثائقية",
     (230, 160, 30), "الوان"),
    ("aghani", ("Alwan Aghani 4K", "Alwan Aghani"), "أغاني",
     (235, 50, 50), "الوان"),
    ("atfal", ("Alwan Atfal 4K", "Alwan Atfal"), "أطفال",
     (245, 160, 30), "الوان"),
    ("quran", ("Alwan Quran 4K", "Alwan Quran"), "القرآن",
     (190, 200, 40), "الوان"),
    ("f1", ("Alwan F1 4K", "Alwan F1"), "الرياضية",
     (230, 40, 40), "F1"),
    ("wwe", ("Alwan WWE 4K", "Alwan WWE"), "الرياضية",
     (230, 40, 40), "WWE"),
    ("ufc", ("Alwan UFC 4K", "Alwan UFC"), "الرياضية",
     (230, 40, 40), "UFC"),
)


# Two more channels on this same link, asked for by name, with the same
# "24/7 Program" row: ShoofMax and Netflix. Not Alwan's, so they keep
# their own ids and names, and wear their own marks (logos/shoofmax.png
# and logos/netflix.png, each service's own logo from its own site, on
# the black square the other logos on this player use).
OTHERS = (
    ("ShoofMax", ("ShoofMax", "Shoof Max", "ShoofMax 4K", "ShoofMax HD",
                  "ShoofMax FHD", "Shoof Max 4K"),
     "شوف ماكس", "shoofmax.png"),
    ("Netflix", ("Netflix", "Netflix 4K", "Netflix HD", "Netflix FHD"),
     "نتفليكس", "netflix.png"),
    # One entry per Netflix channel in the playlist, each its own id: a
    # player that has matched "Netflix" to one channel stops offering it
    # for the next, so every channel needs a guide row of its own, named
    # the way the playlist names it.
    ("Netflix.BoxOffice", ("Box Office 4K", "Netflix Box Office 4K",
                           "Box Office"),
     "نتفليكس بوكس أوفيس", "netflix.png"),
) + tuple(
    (f"Netflix.ActionHD{n}", (f"Netflix Action New HD{n}",
                              f"Netflix Action HD{n}"),
     f"نتفليكس أكشن {n}", "netflix.png")
    for n in range(1, 6)
) + tuple(
    # Al Rabiaa's own channels (Iraq): no schedule is published anywhere
    # for them — alrabiaa.tv sits behind Cloudflare, the public guides
    # carry only the main news channel, and the sports channel's own
    # Telegram names its shows without times — so a 24/7 row with the
    # network's own mark (from its official Telegram), asked for outright.
    (f"AlRabiaa.{key}", tuple(f"{prefix}Al Rabiaa {name}{suffix}"
                              for prefix in ("IQ| ", "")
                              for suffix in ("", " HD", " 4K")),
     arabic, logo)
    for key, name, arabic, logo in (
        ("Sport1", "Sport 1", "الرابعة الرياضية 1", "alrabiaa_sport.png"),
        ("Sport1Plus", "Sport +1", "الرابعة الرياضية +1", "alrabiaa_sport.png"),
        ("Sport2", "Sport 2", "الرابعة الرياضية 2", "alrabiaa_sport.png"),
        ("Sport2Plus", "Sport +2", "الرابعة الرياضية +2", "alrabiaa_sport.png"),
        ("Geo", "Geo", "الرابعة جيو", "alrabiaa_geo.png"),
        ("Movies", "Movies", "الرابعة أفلام", "alrabiaa_movies.png"),
        ("Quran", "Quran", "الرابعة قرآن", "alrabiaa_quran.png"),
    )
)
LOGO_FILE = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/logos/{name}")


def channel_id(key: str) -> str:
    return f"Alwan_{key}"


def add_to(root) -> int:
    """Put the channels and their rows into `root`, a guide being built —
    the Alwan guide, alwan_sports_epg.xml, which is the link the player
    reads Alwan from. Channels go in after the guide's own channels, so
    every channel still comes before every programme."""
    now = datetime.now(timezone.utc)
    first = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)

    at = len(root.findall("channel"))
    every = ([(channel_id(key), names, f"الوان {name_ar}",
               LOGO.format(key=key))
              for key, names, name_ar, _colour, _tag in CHANNELS]
             + [(xid, names, arabic, LOGO_FILE.format(name=logo))
                for xid, names, arabic, logo in OTHERS])
    for xid, names, arabic, icon in every:
        ch = ET.Element("channel", {"id": xid})
        # First name in both scripts: a player lists and searches a guide
        # channel by its first name only, so the Arabic name has to be in it.
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = \
            f"{names[0]} | {arabic}"
        for name in names:
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = arabic
        ET.SubElement(ch, "icon", {"src": icon})
        root.insert(at, ch)
        at += 1

    count = 0
    for xid, names, arabic, _icon in every:
        for day in range(DAYS_BACK + DAYS_FORWARD):
            start = first + timedelta(days=day)
            add_programme(root, xid, start, start + timedelta(days=1), TITLE,
                          f"{names[0]} — {arabic}")
            count += 1
    log(f"Alwan channels: {len(every)} channel(s), {count} programme(s)")
    return count


# Two placeholders to hand-assign in the player, on this same link:
# asked for as "قناة من غير لوجو يكون مكتوب بالشريط LIVE EVENT ONLY" and
# "وحدة ثانية لوجو اخبار يكون مكتوب دائما NEWS 24/7 📰". The bar says
# exactly that and nothing else — neither claims a programme.
# (id, the name a player lists, the bar, logo file or None)
PLACEHOLDERS = (
    ("Placeholder.LiveEventOnly", "LIVE EVENT ONLY", "LIVE EVENT ONLY", None),
    ("Placeholder.News247", "NEWS 24/7", "NEWS 24/7 📰", "news_247.png"),
)


def add_placeholders_to(root) -> int:
    """The two placeholders, channels after the guide's channels."""
    now = datetime.now(timezone.utc)
    first = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    at = len(root.findall("channel"))
    for xid, name, _bar, logo in PLACEHOLDERS:
        ch = ET.Element("channel", {"id": xid})
        ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
        if logo:
            ET.SubElement(ch, "icon", {"src": LOGO_FILE.format(name=logo)})
        root.insert(at, ch)
        at += 1
    count = 0
    for xid, _name, bar, _logo in PLACEHOLDERS:
        for day in range(DAYS_BACK + DAYS_FORWARD):
            start = first + timedelta(days=day)
            add_programme(root, xid, start, start + timedelta(days=1), bar, bar)
            count += 1
    log(f"placeholders: {len(PLACEHOLDERS)} channel(s), {count} programme(s)")
    return count + add_solo_to(root) + add_always_to(root) + add_aljazeera_to(root)


# The owner's playlist's SOLO channels — each plays one thing round the
# clock — asked for as a "24/7 program": one row a day named for what the
# channel plays, under every name the playlist gives it (kept by att_epg.py
# in playlist_aliases.json). On this link because it is the one the player
# has; the unified link picks them up from this file.
def add_solo_to(root) -> int:
    import hashlib
    import json
    try:
        with open("playlist_aliases.json", encoding="utf-8") as handle:
            solo = json.load(handle).get("solo") or {}
    except (OSError, ValueError):
        return 0
    now = datetime.now(timezone.utc)
    first = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    at = len(root.findall("channel"))
    for subject, names in sorted(solo.items()):
        ch = ET.Element("channel", {"id": "Playlist.Solo." + hashlib.md5(
            subject.encode()).hexdigest()[:10]})
        for name in names:
            ET.SubElement(ch, "display-name").text = name
        root.insert(at, ch)
        at += 1
    count = 0
    for subject in sorted(solo):
        cid = "Playlist.Solo." + hashlib.md5(subject.encode()).hexdigest()[:10]
        for day in range(DAYS_BACK + DAYS_FORWARD):
            start = first + timedelta(days=day)
            add_programme(root, cid, start, start + timedelta(days=1),
                          f"{subject} 24/7", f"{subject} — على مدار الساعة")
            count += 1
    log(f"SOLO: {len(solo)} channel(s), {count} programme(s)")
    return count


# The second playlist's channels that play one thing round the clock —
# its Quran reciters (under the Quran mark), its azkar and sunnah
# channels, and the ones that loop one series — kept by att_epg.py in
# playlist_aliases.json. One row a day saying what the channel plays,
# under every name the playlist gives it; on this link for the same
# reason as SOLO: it is the one the owner's player loads.
def add_always_to(root) -> int:
    import hashlib
    import json
    try:
        with open("playlist_aliases.json", encoding="utf-8") as handle:
            always = json.load(handle).get("always") or {}
    except (OSError, ValueError):
        return 0
    now = datetime.now(timezone.utc)
    first = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    at = len(root.findall("channel"))
    count = 0
    for key, entry in sorted(always.items()):
        cid = "Playlist.Always." + hashlib.md5(key.encode()).hexdigest()[:10]
        ch = ET.Element("channel", {"id": cid})
        for name in entry.get("names") or []:
            ET.SubElement(ch, "display-name").text = name
        logo = entry.get("logo")
        if logo and os.path.exists(f"logos/{logo}"):
            ET.SubElement(ch, "icon", {"src": LOGO_FILE.format(name=logo)})
        elif entry.get("logo_url"):
            # A mark drawn for it by playlist_logos.py, beside the playlist guide.
            ET.SubElement(ch, "icon", {"src": entry["logo_url"]})
        root.insert(at, ch)
        at += 1
        # Six-hour rows over three days rather than one a day over eight:
        # a day-long row starts off screen and the player draws its bar
        # with no title on it (the owner's screen, 5 October 2026).
        start = first
        while start < now + timedelta(days=2):
            add_programme(root, cid, start, start + timedelta(hours=6),
                          entry["title"], entry.get("desc") or entry["title"])
            start += timedelta(hours=6)
            count += 1
    log(f"round the clock: {len(always)} channel(s), {count} programme(s)")
    return count


def add_others_to(root, prefix: str) -> int:
    """ShoofMax and Netflix alone, on another link — the beIN Qatar guide
    carries them too, under its own ids (prefix) so the merged link never
    holds one id twice."""
    now = datetime.now(timezone.utc)
    first = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    count = 0
    for xid, names, arabic, logo in OTHERS:
        ch = ET.SubElement(root, "channel", {"id": prefix + xid})
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = \
            f"{names[0]} | {arabic}"
        for name in names:
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = arabic
        ET.SubElement(ch, "icon", {"src": LOGO_FILE.format(name=logo)})
        for day in range(DAYS_BACK + DAYS_FORWARD):
            start = first + timedelta(days=day)
            add_programme(root, prefix + xid, start, start + timedelta(days=1),
                          TITLE, f"{names[0]} — {arabic}")
            count += 1
    return count


def build() -> int:
    """Standalone: these channels alone, for a look at them."""
    root = ET.Element("tv", {"generator-info-name": "Alwan channels"})
    add_to(root)
    write_xml_atomic(root, OUTPUT, generator_name="Alwan channels",
                     guard_regression=False, min_programmes=1)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))


# Al Jazeera on this link too, asked for as "زبط الجزيرة": the player has
# this link and not the unified one, and the provider files its "Al
# Jazeera 4K" under AlJazeera.qa — the id of this repository's guide —
# with nothing in its own EPG under it. The rows are the Roya guide's own
# (aljazeera_epg: the broadcaster's page, AE1 for the hours between),
# copied as they stand; the names are the playlist's.
ALJAZEERA_ID = "AlJazeera.qa"
ALJAZEERA_NAMES = ("Al Jazeera 4K", "AR: Al Jazeera 4K", "AR: Al Jazeera HD",
                   "AR: Al Jazeera UHD", "Al Jazeera HD", "Al Jazeera",
                   "الجزيرة")


def add_aljazeera_to(root, source: str = "roya_jordan_epg.xml") -> int:
    try:
        guide = ET.parse(source).getroot()
    except Exception as exc:                                # noqa: BLE001
        log(f"Al Jazeera: {source} unreadable ({exc}) — left off this link")
        return 0
    found = guide.find(f"channel[@id='{ALJAZEERA_ID}']")
    rows = [p for p in guide.findall("programme")
            if p.get("channel") == ALJAZEERA_ID]
    if found is None or not rows:
        return 0
    ch = ET.Element("channel", {"id": ALJAZEERA_ID})
    for name in ALJAZEERA_NAMES:
        ET.SubElement(ch, "display-name").text = name
    icon = found.find("icon")
    if icon is not None:
        ch.append(icon)
    root.insert(len(root.findall("channel")), ch)
    for p in rows:
        root.append(p)
    log(f"Al Jazeera: {len(rows)} programme(s) on this link")
    return len(rows)


# EVERY OTHER CHANNEL OF THE OWNER'S PLAYLISTS, on this link too.
#
# att_epg.py builds the guide for both Xtream playlists (the second one,
# "Family4k", sends no guide of its own) and publishes it on the att-epg
# branch. The owner's player does not load that link for Family4k and the
# owner will not add one ("ما بدي أضيف لينك ثاني", 6 October 2026): every
# one of its channels showed "No information" while the guide held them.
# This link is the one the player has on for it, so the same channels and
# rows ride here, under their own ids (Playlist.Guide.*) so nothing clashes,
# leaving out any channel this link already names.
#
# If the playlist guide cannot be read this pass, the rows the last
# published copy of this link carried are kept, so a passing network
# fault never empties the channels.
PLAYLIST_GUIDE = ("https://raw.githubusercontent.com/Saudi23723/"
                  "Unified-MENA-EPG/att-epg/att_epg.xml.gz")
PLAYLIST_PREFIX = "Playlist.Guide."
PUBLISHED = "alwan_sports_epg.xml"


def _playlist_guide_root():
    import gzip
    import requests
    r = requests.get(PLAYLIST_GUIDE, timeout=120)
    r.raise_for_status()
    raw = r.content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return ET.fromstring(raw), False


def _published_root():
    root = ET.parse(PUBLISHED).getroot()
    keep = ET.Element("tv")
    for el in root:
        if (el.get("id") or el.get("channel") or "").startswith(PLAYLIST_PREFIX):
            keep.append(el)
    return keep, True


def add_playlist_guide_to(root) -> int:
    try:
        source, prefixed = _playlist_guide_root()
    except Exception as exc:                                # noqa: BLE001
        log(f"playlist guide unreadable ({type(exc).__name__}) — keeping "
            f"the rows already published")
        try:
            source, prefixed = _published_root()
        except Exception:                                   # noqa: BLE001
            return 0
    have = {(d.text or "").strip().lower()
            for c in root.findall("channel") for d in c.findall("display-name")}
    taken = {c.get("id") for c in root.findall("channel")}

    def own_id(cid: str) -> str:
        return cid if prefixed else PLAYLIST_PREFIX + cid

    chosen: set[str] = set()
    at = len(root.findall("channel"))
    for ch in source.findall("channel"):
        names = [(d.text or "").strip() for d in ch.findall("display-name")]
        if not names or any(n.lower() in have for n in names):
            continue
        cid = own_id(ch.get("id") or "")
        if cid in taken or cid in chosen:
            continue
        ch.set("id", cid)
        root.insert(at, ch)
        at += 1
        chosen.add(cid)
    count = 0
    for pr in source.findall("programme"):
        cid = own_id(pr.get("channel") or "")
        if cid in chosen:
            pr.set("channel", cid)
            root.append(pr)
            count += 1
    log(f"playlist guide: {len(chosen)} channel(s), {count} programme(s)")
    return count
