#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The owner's own Xtream playlist: its "US| AT&T" category (a guide and the
AT&T mark for every channel), its two AL-KASS categories (on this
repository's own Alkass guide; KASS SHOOF has no schedule anywhere) and
its SOLO categories (one 24/7 programme each, named for what it plays).
All in one file, on the one link already added to the player.

    "قنوات الكأس كلها تعملها assign على link الكأس تبعي"
    "قنوات solo كلها تعملها 24/7 program"

Asked for in those words: "صلح تبع US| AT&T ... حاول القنوات تكون من
هدول مصادر رسمية او صحيحة ١٠٠٪" and "خلي لوجو AT&T عليهم".

WHAT THE PLAYLIST GIVES. 846 channels named "AT&T: A&E ᴿᴬᵂ" and so on —
the DirecTV Stream lineup (once AT&T TV) plus its free channels — and not
one epg_channel_id. A player can only match them by name, so every
channel here is published under its exact name in the playlist.

WHERE EACH SCHEDULE COMES FROM. DirecTV's own guide refuses a runner
(403 from its CDN, 500 from its API, measured 4 October 2026). Every
channel was then matched once, by hand where the names differ, to the
source that publishes that very feed — att_channels.json, reviewed:

  US cable networks   epgshare01 US2 — Gracenote's US listings. A West
                      channel takes the network's own Pacific feed.
  free channels       the platform the channel is made for: Plex,
                      Samsung TV Plus, Roku, Pluto (i.mjh.nz reads each
                      platform's own guide API).
  MLB, NBA, WNBA      epgshare01 US_SPORTS1 — the team's game schedule.
  Arabic              this repository's own guides first (Al Jazeera,
                      Roya, Jordan TV...), then epgshare01 AE1.

A channel with no source anyone can vouch for gets NO programmes rather
than a neighbour's: a guide that is wrong is worse than an empty one.
It still gets its name and the AT&T mark.

THE LOGIN never appears in a log. It lives in the repository's secrets
(XTREAM_URL / XTREAM_USER / XTREAM_PASS, or the whole message the
provider sent pasted into XTREAM_URL) and every line this prints is
scrubbed of the address, the user name and the password.

    python att_epg.py            # writes att_epg.xml.gz
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from io import BytesIO

import requests

OUT = "att_epg.xml.gz"
MAP = "att_channels.json"
OWN = "unified_mena_epg.xml"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/att.png")
CATEGORY = re.compile(r"AT\s*&\s*T", re.I)
BEHIND = timedelta(hours=6)
AHEAD = timedelta(days=3)
# Below this share of mapped channels with programmes, a source is down:
# keep the guide already published rather than replace it with gaps.
FLOOR = 0.6
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/128 Safari/537.36"}
EPGSHARE = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
MJH = {"pluto": "https://i.mjh.nz/PlutoTV/us.xml.gz",
       "samsung": "https://i.mjh.nz/SamsungTVPlus/us.xml.gz",
       "roku": "https://i.mjh.nz/Roku/all.xml.gz",
       "plexmjh": "https://i.mjh.nz/Plex/us.xml.gz"}


# --- the login, kept out of every line printed --------------------------

def login() -> tuple[str, str, str]:
    blob = "\n".join(os.environ.get(k, "") for k in
                     ("XTREAM_URL", "XTREAM_USER", "XTREAM_PASS"))

    def pick(pattern: str) -> str:
        m = re.search(pattern, blob, re.I)
        return m.group(1).strip() if m else ""

    url = pick(r"(https?://[^\s/?#]+)")
    user = (os.environ.get("XTREAM_USER", "").strip()
            or pick(r"[?&]username=([^&\s]+)")
            or pick(r"(?:user\s*name|username|user|اسم المستخدم)\s*[:=]\s*(\S+)"))
    password = (os.environ.get("XTREAM_PASS", "").strip()
                or pick(r"[?&]password=([^&\s]+)")
                or pick(r"(?:password|pass|كلمة السر|كلمة المرور)\s*[:=]\s*(\S+)"))
    return url, user, password


SECRETS: list[str] = []


def say(text: str) -> None:
    for secret in SECRETS:
        text = text.replace(secret, "***")
    print(text, flush=True)


def playlist() -> list[tuple[str, str, str]] | None:
    """[(category, channel name, epg id)] for the whole playlist, or None."""
    url, user, password = login()
    host = re.sub(r"^https?://", "", url).split(":")[0]
    SECRETS.extend(x for x in (url, user, password, host) if x)
    if not (url and user and password):
        say("playlist: no login in the secrets")
        return None
    auth = {"username": user, "password": password}
    try:
        def api(**kw):
            r = requests.get(url + "/player_api.php", params={**auth, **kw},
                             headers={"User-Agent": "TiviMate/4.7.0"}, timeout=90)
            r.raise_for_status()
            return r.json()
        cats = {str(c["category_id"]): c.get("category_name") or ""
                for c in api(action="get_live_categories")}
        streams = [(cats.get(str(s.get("category_id")), ""), s["name"].strip(),
                    (s.get("epg_channel_id") or "").strip())
                   for s in api(action="get_live_streams")
                   if (s.get("name") or "").strip()
                   and not s["name"].lstrip().startswith("#")]
    except Exception as exc:  # noqa: BLE001 - scrubbed and reported
        say(f"playlist: unreadable ({type(exc).__name__}: {exc})"[:300])
        return None
    say(f"playlist: {len(streams)} channel(s) in {len(cats)} categories")
    return streams


# --- names ---------------------------------------------------------------

def core(name: str) -> str:
    """'AT&T: A&E ᴿᴬᵂ' -> 'A&E' — the key att_channels.json is kept by."""
    name = re.sub(r"^\s*AT\s*&\s*T\s*:\s*", "", name)
    name = re.sub(r"[\sᴬ-ᵿ⁰-⁹]+$", "", name)
    return re.sub(r"\s+", " ", name).strip().upper()


def channel_id(key: str) -> str:
    key = key.replace("+", " Plus").replace("&", " And ").replace("!", " Bang")
    return "ATT." + (re.sub(r"[^A-Za-z0-9]+", "", key.title()) or "Channel")


# --- the sources ---------------------------------------------------------

def source_url(source: str) -> str | None:
    if source == "own":
        return None
    return MJH.get(source) or EPGSHARE.format(source)


def read_source(session, source: str, wanted: set[str], floor, ceiling):
    """{channel id: [programme elements]} for the wanted ids of one source."""
    if source == "own":
        handle = open(OWN, "rb")
    else:
        r = session.get(source_url(source), headers=UA, timeout=300)
        r.raise_for_status()
        raw = r.content
        handle = BytesIO(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    found: dict[str, list[ET.Element]] = {}
    with handle:
        for _event, el in ET.iterparse(handle, events=("end",)):
            if el.tag == "programme":
                cid = el.get("channel")
                if cid in wanted:
                    start, stop = when(el.get("start")), when(el.get("stop"))
                    if start and stop and stop > floor and start < ceiling \
                            and stop > start:
                        found.setdefault(cid, []).append(el)
                        continue
                el.clear()
            elif el.tag == "channel":
                el.clear()
    return found


def when(stamp: str | None) -> datetime | None:
    try:
        return datetime.strptime((stamp or "").strip(), "%Y%m%d%H%M%S %z")
    except ValueError:
        return None


# --- the guide -----------------------------------------------------------

# Alkass: the playlist's two AL-KASS categories, each "AL-KASS n", on this
# repository's own Alkass guide (alkass_epg.py, from the broadcaster's
# site). KASS SHOOF has no published schedule anywhere and is left alone.
ALKASS = re.compile(r"AL-?\s*KASS", re.I)
ALKASS_N = re.compile(r"AL-?\s*KASS\s*(\d)\b", re.I)
ALKASS_IDS = {1: "AlkassOne.qa", 2: "AlkassTwo.qa", 3: "AlkassThree.qa",
              4: "AlkassFour.qa", 5: "AlkassFive.qa", 6: "AlkassSix.qa",
              7: "AlkassSeven.qa", 8: "AlkassEight.qa"}
ALKASS_LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
               "main/logos/alkass{}.png")
# SOLO: channels that each play one thing around the clock, asked for as
# a "24/7 program" — the programme is the channel's own subject.
SOLO = re.compile(r"\bSOLO\b", re.I)
SOLO_BLOCK = timedelta(hours=6)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%d%H%M%S +0000")


def solo_subject(name: str) -> str:
    """'BE: SOLO باب الحارة ᴿᴬᵂ' -> 'باب الحارة'; 'BE: SOLO SPORT 1 SD' ->
    'SOLO SPORT 1'."""
    name = re.sub(r"^\s*[^:]{1,6}:\s*", "", name)
    name = re.sub(r"[\sᴬ-ᵿʰ-ʸᵃ-ᶻ⁰-⁹]+$", "", name)
    name = re.sub(r"\s+(HD|SD|FHD|4K)$", "", name, flags=re.I).strip()
    rest = re.sub(r"^SOLO\s+", "", name, flags=re.I).strip()
    return name if re.match(r"SPORT\b", rest, re.I) or not rest else rest


def add_channel(root, cid: str, names: list[str], logo: str | None):
    ch = ET.SubElement(root, "channel", {"id": cid})
    for name in dict.fromkeys(names):
        ET.SubElement(ch, "display-name").text = name
    if logo:
        ET.SubElement(ch, "icon", {"src": logo})


def add_rows(root, cid: str, programmes) -> int:
    """Copies, in time order, without overlaps. Returns how many."""
    count, last_stop = 0, None
    for p in sorted(programmes, key=lambda p: when(p.get("start"))):
        start = when(p.get("start"))
        if last_stop and start < last_stop:
            continue                         # an overlap in the source
        # A copy: two playlist channels can share one feed (DISCOVERY
        # TURBO and DISCOVERY TURBO TV), and the same element appended
        # twice would end up under the second channel both times.
        p = copy.deepcopy(p)
        p.set("channel", cid)
        root.append(p)
        last_stop = when(p.get("stop"))
        count += 1
    return count


def build() -> int:
    mapping: dict[str, list[str]] = json.load(open(MAP, encoding="utf-8"))
    streams = playlist()
    if streams is None:
        say("guide: playlist unreadable — keeping the published guide")
        return 0
    att = [name for cat, name, _ in streams if CATEGORY.search(cat)]
    kass = [(name, epg) for cat, name, epg in streams
            if ALKASS.search(cat) and ALKASS_N.search(name)]
    solo = [name for cat, name, _ in streams if SOLO.search(cat)]
    say(f"playlist: {len(att)} AT&T, {len(kass)} Alkass, {len(solo)} SOLO")

    now = datetime.now(timezone.utc)
    floor, ceiling = now - BEHIND, now + AHEAD
    wanted: dict[str, set[str]] = {}
    for name in att:
        hit = mapping.get(core(name))
        if hit:
            wanted.setdefault(hit[0], set()).add(hit[1])
    if kass:
        wanted.setdefault("own", set()).update(ALKASS_IDS.values())

    session = requests.Session()
    rows: dict[tuple[str, str], list[ET.Element]] = {}
    for source, ids in sorted(wanted.items()):
        try:
            got = read_source(session, source, ids, floor, ceiling)
        except Exception as exc:  # noqa: BLE001 - one source down is reported
            say(f"  {source:13} FAILED ({type(exc).__name__}: {exc})"[:200])
            continue
        say(f"  {source:13} {len(got):4}/{len(ids):<4} channel(s) with programmes")
        for cid, programmes in got.items():
            rows[(source, cid)] = programmes

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — playlist"})

    # AT&T
    seen, mapped, filled, total = set(), 0, 0, 0
    for name in att:
        key = core(name)
        cid = channel_id(key)
        if cid in seen:
            continue
        seen.add(cid)
        add_channel(root, cid, [name, f"AT&T: {key}"], LOGO)
        hit = mapping.get(key)
        if hit:
            mapped += 1
            added = add_rows(root, cid, rows.get(tuple(hit), []))
            filled += bool(added)
            total += added
    say(f"AT&T: {len(seen)} channel(s), {mapped} with a source, {filled} with "
        f"programmes, {total} programme(s)")
    if mapped and filled < FLOOR * mapped:
        say(f"guide: only {filled}/{mapped} filled — a source is down; "
            f"keeping the published guide")
        return 0

    # Alkass — one channel per number, under the playlist's own epg id and
    # every name the playlist gives it.
    by_number: dict[int, list[tuple[str, str]]] = {}
    for name, epg in kass:
        by_number.setdefault(int(ALKASS_N.search(name).group(1)), []).append((name, epg))
    kass_rows = 0
    for number, entries in sorted(by_number.items()):
        if number not in ALKASS_IDS:
            continue
        ids = [epg for _, epg in entries if epg] or [f"Playlist.Alkass{number}"]
        names = [name for name, _ in entries] + [f"Alkass {number}", f"الكأس {number}"]
        for cid in dict.fromkeys(ids):
            add_channel(root, cid, names, ALKASS_LOGO.format(number))
            kass_rows += add_rows(root, cid, rows.get(("own", ALKASS_IDS[number]), []))
    say(f"Alkass: {len(by_number)} channel(s), {kass_rows} programme(s)")

    # SOLO — one 24/7 programme, in six-hour blocks so a player's grid
    # always has a row under "now".
    first = floor.replace(minute=0, second=0, microsecond=0)
    first -= timedelta(hours=first.hour % 6)
    subjects: dict[str, list[str]] = {}
    for name in solo:
        subjects.setdefault(solo_subject(name), []).append(name)
    for subject, names in subjects.items():
        # HD, SD, HEVC and RAW of one channel are one channel here.
        cid = "Playlist.Solo." + hashlib.md5(subject.encode()).hexdigest()[:10]
        add_channel(root, cid, names, None)
        moment = first
        while moment < ceiling:
            p = ET.SubElement(root, "programme", {
                "start": stamp(moment), "stop": stamp(moment + SOLO_BLOCK),
                "channel": cid})
            ET.SubElement(p, "title", {"lang": "ar"}).text = f"{subject} 24/7"
            ET.SubElement(p, "desc", {"lang": "ar"}).text = \
                f"{subject} — على مدار الساعة"
            moment += SOLO_BLOCK
    say(f"SOLO: {len(solo)} name(s) on {len(subjects)} channel(s), 24/7")

    ET.indent(root, space=" ")
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with gzip.open(OUT + ".tmp", "wb", compresslevel=9) as handle:
        handle.write(data)
    os.replace(OUT + ".tmp", OUT)
    say(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
