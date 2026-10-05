#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The owner's own Xtream playlist, in one SMALL file (the day ahead, titles
only — asked for as "ملف صغير"): its US| NBC / FOX / CBS / ABC
stations, taken first from the EPG links the owner sent. The "US| AT&T"
category was taken off this guide at the owner's word ("اشطب لينك ال
at&t بالكامل"); att_channels.json stays only for the network cable
channels (FOX NEWS, FS1, BRAVO...) that share its reviewed matches. The playlist's beIN, Alkass and STARZPLAY
channels are not in it: they are assigned on the existing links by name
(playlist_aliases.json, written here), and SOLO rides the unified link.

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

import playlist_match as pm

OUT = "att_epg.xml.gz"
MAP = "att_channels.json"
OWN = "unified_mena_epg.xml"
CATEGORY = re.compile(r"AT\s*&\s*T", re.I)
# Small on purpose — asked for as "ملف صغير": the day ahead, titles only.
BEHIND = timedelta(hours=2)
AHEAD = timedelta(days=1)
# Below this share of mapped channels with programmes, a source is down:
# keep the guide already published rather than replace it with gaps.
FLOOR = 0.6
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/128 Safari/537.36"}
EPGSHARE = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
# The owner's own EPG links, sent for the US networks' stations and asked
# for by name: "بعتلك ٤ او ٥ links تعمل assign منها". ferteque's guide
# carries the provider's own channel names and the stations by call sign
# (kdka.us); iptv-epg.org by network and call sign (CBSKDKA.us). Of the
# others, iptvx.one carries no US station and gabbarit's file is cut
# short (measured 4 October 2026).
USER_LINKS = {
    "ferteque": ("https://github.com/ferteque/Curated-M3U-Repository/raw/"
                 "refs/heads/main/epg6.xml.gz"),
    "iptvepg": "https://iptv-epg.org/files/epg-rhtwyyuokk.xml",
}
MJH = {"pluto": "https://i.mjh.nz/PlutoTV/us.xml.gz",
       "samsung": "https://i.mjh.nz/SamsungTVPlus/us.xml.gz",
       "roku": "https://i.mjh.nz/Roku/all.xml.gz",
       "plexmjh": "https://i.mjh.nz/Plex/us.xml.gz"}


# --- the login, kept out of every line printed --------------------------

# Every playlist the guide serves, by the prefix of its three secrets. Both
# go into the one guide on the one link: a channel the two share is listed
# once, under the names each playlist gives it.
PLAYLISTS = ("XTREAM", "XTREAM2")
# Playlists that bring no guide of their own (the second answers
# xmltv.php with nothing): every one of their channels a trusted source
# names exactly is given one — see playlist_match.py.
GUIDELESS = ("XTREAM2",)
FULL: set[tuple[str, str, str]] = set()


def login(prefix: str = "XTREAM") -> tuple[str, str, str]:
    blob = "\n".join(os.environ.get(f"{prefix}_{k}", "") for k in
                     ("URL", "USER", "PASS"))

    def pick(pattern: str) -> str:
        m = re.search(pattern, blob, re.I)
        return m.group(1).strip() if m else ""

    url = pick(r"(https?://[^\s/?#]+)")
    user = (os.environ.get(f"{prefix}_USER", "").strip()
            or pick(r"[?&]username=([^&\s]+)")
            or pick(r"(?:user\s*name|username|user|اسم المستخدم)\s*[:=]\s*(\S+)"))
    password = (os.environ.get(f"{prefix}_PASS", "").strip()
                or pick(r"[?&]password=([^&\s]+)")
                or pick(r"(?:password|pass|كلمة السر|كلمة المرور)\s*[:=]\s*(\S+)"))
    return url, user, password


SECRETS: list[str] = []


def say(text: str) -> None:
    for secret in SECRETS:
        text = text.replace(secret, "***")
    print(text, flush=True)


def playlists() -> list[tuple[str, str, str]] | None:
    """Every configured playlist's channels together, or None.

    A playlist with no secrets is simply not configured. One that is
    configured but cannot be read makes the whole answer None, so the
    published guide is kept rather than rebuilt without its channels.
    """
    found = False
    streams: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for prefix in PLAYLISTS:
        if not any(os.environ.get(f"{prefix}_{k}", "").strip()
                   for k in ("URL", "USER", "PASS")):
            continue
        found = True
        part = playlist(prefix)
        if part is None:
            return None
        if prefix in GUIDELESS:
            FULL.update(part)
        for stream in part:
            if stream not in seen:
                seen.add(stream)
                streams.append(stream)
    if not found:
        say("playlist: no login in the secrets")
        return None
    return streams


def playlist(prefix: str = "XTREAM") -> list[tuple[str, str, str]] | None:
    """[(category, channel name, epg id)] for the whole playlist, or None."""
    url, user, password = login(prefix)
    host = re.sub(r"^https?://", "", url).split(":")[0]
    SECRETS.extend(x for x in (url, user, password, host) if x)
    if not (url and user and password):
        say(f"playlist {prefix}: its login is incomplete in the secrets")
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
    say(f"playlist {prefix}: {len(streams)} channel(s) in {len(cats)} categories")
    return streams


# --- names ---------------------------------------------------------------

# --- the sources ---------------------------------------------------------

def source_url(source: str) -> str | None:
    if source == "own":
        return None
    return USER_LINKS.get(source) or MJH.get(source) or EPGSHARE.format(source)


def read_source(session, source: str, wanted, floor, ceiling, on_channel=None):
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
                if (wanted(cid) if callable(wanted) else cid in wanted):
                    start, stop = when(el.get("start")), when(el.get("stop"))
                    if start and stop and stop > floor and start < ceiling \
                            and stop > start:
                        found.setdefault(cid, []).append(el)
                        continue
                el.clear()
            elif el.tag == "channel":
                if on_channel:
                    on_channel(el.get("id") or "",
                               [d.text or "" for d in el.findall("display-name")])
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
ALKASS_N = re.compile(r"AL\s*-?\s*KASS\s*(\d|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT)\b", re.I)
WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6,
         "SEVEN": 7, "EIGHT": 8}


def alkass_number(name: str) -> int | None:
    m = ALKASS_N.search(name)
    if not m:
        return None
    word = m.group(1).upper()
    return WORDS.get(word) or int(word)
ALKASS_IDS = {1: "AlkassOne.qa", 2: "AlkassTwo.qa", 3: "AlkassThree.qa",
              4: "AlkassFour.qa", 5: "AlkassFive.qa", 6: "AlkassSix.qa",
              7: "AlkassSeven.qa", 8: "AlkassEight.qa"}
ALKASS_LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
               "main/logos/alkass{}.png")
# SOLO: channels that each play one thing around the clock, asked for as
# a "24/7 program" — the programme is the channel's own subject.
SOLO = re.compile(r"\bSOLO\b", re.I)
SOLO_BLOCK = timedelta(hours=6)


# beIN SPORTS (MENA), in every one of the playlist's beIN categories, on
# this repository's own beIN guide — read from beIN's own site. Matched
# by NAME: the provider's epg ids for these say English where the name
# does not, and its own listing for them runs three hours off beIN's
# (measured 4 October 2026: Finland v Albania 06:30 there, 03:27 on
# beIN's site). FRANCE, AFC, NBA and 4K have no guide here — beIN's
# site answers those with nothing — and are left alone.
BEIN = re.compile(r"\bbe\s*IN\b", re.I)


def bein_target(name: str) -> str | None:
    text = name.replace("⚽", "O").upper()
    text = re.sub(r"^[^:]{1,6}:\s*", "", text)
    text = re.sub(r"[ᴬ-ᵿʰ-˿ᵃ-ᶻ⁰-⁹◉▼]", " ", text)
    text = re.sub(r"\b0(\d)\b", r"\1", text)
    if not re.match(r"BEIN\s*SPORTS?\b", text):
        return None
    rest = re.sub(r"^BEIN\s*SPORTS?\s*", "", text)
    rest = re.sub(r"\b(HD|SD|LQ|FHD|UHD|4K|8K|RAW|HEVC)\b|\(.*?\)", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip()
    if re.search(r"FRANCE|\bFR\b|AFC|NBA|PREMIUM|MAX|TURK|ASIA", rest):
        m = re.fullmatch(r"MAX (\d)", rest)
        return f"beINSportsMax{m.group(1)}.qa" if m else None
    m = (re.fullmatch(r"(\d) (?:ENGLISH|ENG|EN)", rest)
         or re.fullmatch(r"(?:ENGLISH|ENG|EN) (\d)", rest))
    if m:
        return f"beINSportsEn{m.group(1)}.qa" if m.group(1) in "12" else None
    m = re.fullmatch(r"(\d) XTRA", rest) or re.fullmatch(r"XTRA (\d)", rest)
    if m:
        return f"beINSportsXtra{m.group(1)}.qa"
    if re.fullmatch(r"[1-9]", rest):
        return f"beINSports{rest}.qa"
    if rest == "NEWS":
        return "beINSportsNews.qa"
    if rest in ("", "GLOBAL"):
        return "beINSports.qa"
    return None


# STARZPLAY's sport channels — AD Sports and friends — on this repository's
# own STARZPLAY guide, read from STARZPLAY's own EPG API. AD Premium 2 is
# the feed STARZPLAY itself titles "أبوظبي الرياضية بريميوم 2", Premium 1
# its sister; AD Sports Asia 1 and 2 are STARZPLAY's adsportsasia01/02.
STARZ_CATEGORY = re.compile(r"STARZ\s*PLAY\s*SPORT", re.I)
STARZ_RULES = [
    (r"AD (?:SPORTS? )?(?:1 PREMIUM|PREMIUM 1)\b", "Starz_starzplaysports1"),
    (r"AD (?:SPORTS? )?(?:2 PREMIUM|PREMIUM 2)\b", "Starz_starzplaysports2"),
    (r"AD SPORTS? ASIA 1\b", "Starz_adsportsasia01"),
    (r"AD SPORTS? ASIA 2\b", "Starz_adsportsasia02"),
    (r"AD SPORTS? FIGHT\b", "Starz_adfight"),
    (r"AD SPORTS? 1\b", "Starz_admnadsports1"),
    (r"AD SPORTS? 2\b", "Starz_admnadsports2"),
    (r"CRLIFE 1\b", "Starz_criclife1"),
    (r"GOLF TV\b", "Starz_golflife"),
]


def starz_target(name: str) -> str | None:
    text = re.sub(r"^[^:]{1,6}:\s*", "", name.upper())
    for pattern, target in STARZ_RULES:
        if re.match(pattern, text):
            return target
    return None


# The US networks' local stations — NBC, FOX, CBS and ABC — each by the
# call sign in its name, on Gracenote's local listings for that very
# station (epgshare01 US_LOCALS1). A name whose call sign disagrees with
# the provider's own id ("CBS (WSBK) BOSTON" filed as WBZ) is left alone:
# which station it really is cannot be told. Network cable channels in
# the same categories (FOX NEWS, FS1, NBC's BRAVO...) take the AT&T
# category's reviewed match.
US_NETWORK = re.compile(r"^US\|\s*(NBC|FOX|CBS|ABC)\b", re.I)
CALL = re.compile(r"\b([KW][A-Z]{2,3})\b")
NOT_CALLS = {"WEST", "WACO", "KIDS", "WILD", "WIDE", "WIRE", "WOW", "WWE"}


def call_sign(name: str, epg: str) -> str | None:
    text = re.sub(r"^[^:]{1,6}:\s*", "", name.upper())
    inside = [c for part in re.findall(r"\(([^)]*)\)", text)
              for c in CALL.findall(part) if c not in NOT_CALLS]
    calls = inside or [c for c in CALL.findall(text) if c not in NOT_CALLS]
    if not calls:
        return None
    filed = re.match(r"([KW][A-Z]{2,3})\.us$", epg or "", re.I)
    if filed and filed.group(1).upper() != calls[0]:
        return None
    return calls[0]


# Names in the network categories that are not the AT&T category's words.
US_ALIASES = {"FOX NEWS CHANNEL": "FOX NEWS", "GOLF": "GOLF CHANNEL"}
US_EXTRA = {"FOX DEPORTES": ["US2", "Fox.Deportes.HD.us2"],
            "FOX SPORTS DEPORTES": ["US2", "Fox.Deportes.HD.us2"],
            "FOX SOCCER PLUS": ["US2", "Fox.Soccer.Plus.HD.us2"]}


def us_cable_target(name: str, mapping) -> list[str] | None:
    key = us_cable_key(name)
    if not key:
        return None
    for k in (key, re.sub(r"^(NBC|FOX|CBS|ABC) ", "", key)):
        k = US_ALIASES.get(k, k)
        if k in US_EXTRA:
            return US_EXTRA[k]
        if k in mapping:
            return mapping[k]
    return None


def us_cable_key(name: str) -> str | None:
    """'US: NBC BRAVO (EAST) (D) ᴿᴬᵂ' -> 'BRAVO', in att_channels.json's terms."""
    text = re.sub(r"^[^:]{1,6}:\s*", "", name.upper())
    if re.search(r"\(WEST\)|\bWEST\b|PACIFIC", text):
        return None
    text = re.sub(r"[ᴬ-ᵿʰ-˿ᵃ-ᶻ⁰-⁹]", " ", text)
    text = re.sub(r"\((?:EAST|[A-Z]{1,2}|#)\)", " ", text)
    text = re.sub(r"\b(HD|SD|FHD|UHD|4K|RAW|NETWORK)\b|\.", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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


def add_rows(out: list, cid: str, programmes) -> int:
    """Copies, in time order, without overlaps. Returns how many."""
    count, last_stop = 0, None
    for p in sorted(programmes, key=lambda p: when(p.get("start"))):
        start = when(p.get("start"))
        if last_stop and start < last_stop:
            continue                         # an overlap in the source
        # A copy: two playlist channels can share one feed (DISCOVERY
        # TURBO and DISCOVERY TURBO TV), and the same element appended
        # twice would end up under the second channel both times.
        slim = ET.Element("programme", {"start": p.get("start"),
                                        "stop": p.get("stop"), "channel": cid})
        title = p.find("title")
        if title is not None:
            slim.append(copy.deepcopy(title))
        p = slim
        out.append(p)
        last_stop = when(p.get("stop"))
        count += 1
    return count


def fill_holes(out: list, since: int, cid: str, name: str, floor, ceiling) -> None:
    """Every stretch of floor..ceiling that out[since:] leaves empty, ten
    minutes or more, becomes a row with the channel's own name."""
    spans = sorted((when(p.get("start")), when(p.get("stop"))) for p in out[since:])
    cursor, holes = floor, []
    for start, stop in spans:
        if start - cursor >= timedelta(minutes=10):
            holes.append((cursor, start))
        cursor = max(cursor, stop)
    if ceiling - cursor >= timedelta(minutes=10):
        holes.append((cursor, ceiling))
    for start, stop in holes:
        p = ET.Element("programme", {"start": stamp(start), "stop": stamp(stop),
                                     "channel": cid})
        ET.SubElement(p, "title").text = name
        ET.SubElement(p, "desc").text = "لا يوجد جدول منشور لهذا الوقت"
        out.append(p)
    out[since:] = sorted(out[since:], key=lambda p: when(p.get("start")))


def write_aliases(names: dict[str, list[str]], solo: list[str],
                  always: dict[str, dict] | None = None) -> None:
    """playlist_aliases.json — the playlist's names for channels this
    repository already guides, and its SOLO channels. Every guide written
    through epg_lib carries these names, so the owner's existing links
    match these channels: an "assign", not a new link."""
    subjects: dict[str, list[str]] = {}
    for name in solo:
        subjects.setdefault(solo_subject(name), []).append(name)
    data = {"names": {k: sorted(set(v)) for k, v in sorted(names.items())},
            "solo": {k: sorted(set(v)) for k, v in sorted(subjects.items())},
            "always": {k: {**v, "names": sorted(set(v["names"]))}
                       for k, v in sorted((always or {}).items())}}
    with open("playlist_aliases.json", "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    say(f"aliases: {sum(map(len, data['names'].values()))} name(s) on "
        f"{len(data['names'])} guided channel(s), {len(subjects)} SOLO, "
        f"{len(data['always'])} round the clock")


def build() -> int:
    mapping: dict[str, list[str]] = json.load(open(MAP, encoding="utf-8"))
    streams = playlists()
    if streams is None:
        say("guide: playlist unreadable — keeping the published guide")
        return 0

    # Who goes where. A target is (source, id); every playlist name that
    # shows the same feed becomes one channel carrying all those names.
    solo = []
    groups: dict[tuple[str, str], dict] = {}

    def assign(target, name, logo=None, ids=()):
        g = groups.setdefault(tuple(target), {"names": [], "logo": logo, "ids": []})
        g["names"].append(name)
        g["ids"].extend(i for i in ids if i)

    counts = {"Alkass": 0, "beIN": 0, "STARZPLAY": 0, "US local": 0, "US cable": 0}
    us_pending: dict[str, str | None] = {}      # name -> call sign, or None
    for cat, name, epg in streams:
        number = alkass_number(name)
        if CATEGORY.search(cat):
            continue          # AT&T: taken off this guide at the owner's word
        elif number and number in ALKASS_IDS:
            assign(("own", ALKASS_IDS[number]), name, ALKASS_LOGO.format(number),
                   [epg] if re.fullmatch(r"alkass\w+\.qa", epg or "", re.I) else [])
            counts["Alkass"] += 1
        elif SOLO.search(cat):
            solo.append(name)
        elif BEIN.search(cat) and bein_target(name):
            assign(("own", bein_target(name)), name)
            counts["beIN"] += 1
        elif STARZ_CATEGORY.search(cat) and starz_target(name):
            assign(("own", starz_target(name)), name)
            counts["STARZPLAY"] += 1
        elif US_NETWORK.search(cat):
            sign = call_sign(name, epg)
            target = None if sign else us_cable_target(name, mapping)
            if target:
                assign(target, name)
                counts["US cable"] += 1
            else:
                us_pending[name] = sign
        elif (cat, name, epg) in FULL and re.match(r"\s*USA\b", cat, re.I):
            # The guideless playlist's local stations, by the call sign it
            # writes in brackets ("ABC 7 (WABC) New York") — and only then.
            sign = re.search(r"\(([KW][A-Z]{2,3})\)", name.upper())
            if sign and sign.group(1) not in NOT_CALLS and call_sign(name, epg):
                us_pending[name] = sign.group(1)
    say(f"playlist: {len(solo)} SOLO, "
        + ", ".join(f"{v} {k}" for k, v in counts.items())
        + f", {len(us_pending)} US station name(s)")

    now = datetime.now(timezone.utc)
    floor, ceiling = now - BEHIND, now + AHEAD
    wanted: dict[str, set[str]] = {}
    for source, cid in groups:
        wanted.setdefault(source, set()).add(cid)

    session = requests.Session()
    rows: dict[tuple[str, str], list[ET.Element]] = {}

    def load(source, test, on_channel=None):
        try:
            got = read_source(session, source, test, floor, ceiling, on_channel)
        except Exception as exc:  # noqa: BLE001 - one source down is reported
            say(f"  {source:13} FAILED ({type(exc).__name__}: {exc})"[:200])
            return
        say(f"  {source:13} {len(got):4} channel(s) with programmes")
        for cid, programmes in got.items():
            rows[(source, cid)] = programmes

    for source in sorted(wanted):
        load(source, wanted[source])

    # The US networks' stations, from the owner's own links first: the
    # provider's exact name in ferteque's guide, then the call sign there,
    # then the call sign in iptv-epg.org's; Gracenote's listing for the
    # station last. A station counts only where it has programmes.
    def settle(source, claims):
        for name, options in claims.items():
            live = [cid for cid in options if rows.get((source, cid))]
            if name in us_pending and live:
                assign((source, live[0]), name)
                del us_pending[name]

    def claim_by(pattern, exact):
        by_name: dict[str, list[str]] = {}
        by_sign: dict[str, list[str]] = {}
        claimed: set[str] = set()
        signs: dict[str, list[str]] = {}
        for name, sign in us_pending.items():
            if sign:
                signs.setdefault(sign, []).append(name)

        def on_channel(cid, names):
            if exact:
                for n in names:
                    if n in us_pending:
                        by_name.setdefault(n, []).append(cid)
                        claimed.add(cid)
            m = re.fullmatch(pattern, cid, re.I)
            if m:
                for name in signs.get(m.group(1).upper(), []):
                    by_sign.setdefault(name, []).append(cid)
                    claimed.add(cid)
        return by_name, by_sign, claimed, on_channel

    for source, pattern, exact in (
            ("ferteque", r"([KW][A-Z]{2,3})(?:DT)?\.us", True),
            ("iptvepg", r"(?:ABC|CBS|NBC|FOX|CW|MNT|MY|PBS)?(?:East_|West_)?"
                        r"([KW][A-Z]{2,3})\.us", False),
            ("US_LOCALS1", r"([KW][A-Z]{2,3})-DT\.us_locals1", False)):
        if not us_pending:
            break
        by_name, by_sign, claimed, on_channel = claim_by(pattern, exact)
        load(source, claimed.__contains__, on_channel)
        # The provider's exact name first; then the call sign, a plain
        # call sign before its DT twin.
        settle(source, by_name)
        for name in by_sign:
            by_sign[name].sort(key=lambda c: ("dt." in c.lower(), c))
        settle(source, by_sign)
    say(f"US stations: {len(us_pending)} name(s) left with no listing")

    # The guideless playlist: every channel the rules above did not take is
    # matched by name — ours first, then its country's sources — or, for
    # the Quran and the channels that loop one title, given that title
    # round the clock. See playlist_match.py for why no provider id is used.
    taken = {n for g in groups.values() for n in g["names"]} | set(solo) | set(us_pending)
    always: dict[str, dict] = {}
    pending: dict[str, tuple[str, str]] = {}          # name -> (category, key)
    try:
        own = pm.own_index(ET.parse(OWN).getroot())
    except Exception as exc:  # noqa: BLE001 - reported, the rest goes on
        say(f"guideless: our own guide unreadable ({type(exc).__name__})")
        own = {}
    for cat, name, epg in sorted(FULL):
        if name in taken or CATEGORY.search(cat):
            continue
        if re.fullmatch(r"\s*TOD\s*", cat):
            target = bein_target(re.sub(r"\bTod\b", "", re.sub(
                r"(?i)rnglish", "English", name), flags=re.I))
            if target:
                assign(("own", target), name)
                continue
        target = pm.own_target(own, cat, name)
        if target:
            assign(("own", target), name)
            continue
        if pm.ISLAMIC.match(cat) or (pm.route(cat, name) is pm.ARAB
                                     and pm.QURAN_CHANNEL.search(name)):
            kind = pm.islamic(name)
            if kind:
                title, what = kind
                subject = pm.reciter(name)
                entry = always.setdefault(f"{what}:{subject}", {
                    "title": title, "desc": subject,
                    "logo": "quran.png" if what == "quran" else None, "names": []})
                entry["names"].append(name)
                continue
        pending[name] = (cat, pm.norm(name))

    found: dict[str, tuple[str, str]] = {}            # name -> (source, id)
    for source in pm.SOURCE_ORDER:
        asking: dict[str, list[str]] = {}
        for name, (cat, key) in pending.items():
            sources, countries = pm.route(cat, name)
            if source in sources and name not in found:
                asking.setdefault(key, []).append(name)
        if not asking:
            continue
        claims: dict[str, set[str]] = {}
        countries_of = {name: pm.route(pending[name][0], name)[1]
                        for names in asking.values() for name in names}

        def on_channel(cid, names, asking=asking, claims=claims):
            if not pm.usable(cid):
                return
            for key in {pm.norm(n) for n in names}:
                for name in asking.get(key, ()):
                    # A West Coast copy runs three hours behind: it is the
                    # channel only for a name that says West, and only then.
                    if pm.suffix(cid) in countries_of[name] and \
                            pm.west(cid + " " + " ".join(names)) == pm.west(name):
                        claims.setdefault(name, set()).add(cid)

        claimed: set[str] = set()

        def wants(cid, claims=claims, claimed=claimed):
            if cid in claimed:
                return True
            if any(cid in c for c in claims.values()):
                claimed.add(cid)
                return True
            return False

        before = set(rows)
        load(source, wants, on_channel)
        for name, cids in claims.items():
            live = {cid: len(rows.get((source, cid), [])) for cid in cids}
            live = {cid: n for cid, n in live.items() if n}
            if live:
                # One source's duplicates of one name (A2.tr, A2.HD.tr) are
                # one channel: the copy with the most rows.
                best = max(live, key=lambda c: (live[c], -len(c)))
                found[name] = (source, best)
        keep = set(found.values())
        for key in set(rows) - before:
            if key not in keep:
                del rows[key]
    for name, (source, cid) in found.items():
        assign((source, cid), name)
        del pending[name]

    looped = 0
    for name, (cat, key) in list(pending.items()):
        if pm.LOOP.match(cat):
            subject = pm.loop_subject(name)
            always.setdefault(f"loop:{subject}", {
                "title": f"{subject} 24/7", "desc": f"{subject} — على مدار الساعة",
                "logo": None, "names": []})["names"].append(name)
            del pending[name]
            looped += 1
    # The rest no trusted source schedules at all. Each still says what it
    # is — its own name, all day — so no channel of the playlist shows
    # "No information"; nothing is claimed about what it is airing.
    named: dict[str, list[str]] = {}
    for name in pending:
        named.setdefault(pm.shown_name(name), []).append(name)
    say(f"guideless: {len(FULL)} channel(s) — {len(found)} matched in a source, "
        f"{sum(len(v['names']) for v in always.values())} round the clock, "
        f"{len(pending)} with no trusted source, shown by name")

    write_aliases({cid: g["names"] for (src, cid), g in groups.items() if src == "own"},
                  solo, always)

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — playlist"})
    # XMLTV puts every <channel> before the first <programme>. A player
    # reads the channel list at the top and matches against that alone:
    # written one channel and its programmes at a time, the guide loaded
    # with nothing matched (4 October 2026).
    programmes_out: list[ET.Element] = []

    # Everything grouped by feed: Alkass, beIN, STARZPLAY, the US networks.
    shown = empty = 0
    for (source, target), g in sorted(groups.items()):
        if source == "own":
            continue                     # on the existing links, by name
        cids = list(dict.fromkeys(g["ids"])) or [
            "Playlist." + re.sub(r"[^A-Za-z0-9]+", "", f"{source}.{target}")]
        for cid in cids:
            add_channel(root, cid, g["names"], g["logo"])
            before = len(programmes_out)
            added = add_rows(programmes_out, cid, rows.get((source, target), []))
            shown += bool(added)
            empty += not added
            # A source's own holes (and a feed with nothing today) say the
            # channel's name rather than "No information".
            fill_holes(programmes_out, before, cid, pm.shown_name(g["names"][0]),
                       floor, ceiling)
    say(f"feeds: {len(groups)} — {shown} channel(s) with programmes, {empty} without")
    if (shown + empty) and shown < FLOOR * (shown + empty):
        say(f"guide: only {shown}/{shown + empty} filled — a source is down; "
            f"keeping the published guide")
        return 0

    # SOLO rides the unified link (merge_epg.add_solo), not this file.

    # The guideless playlist's channels no source schedules: their own
    # name in six-hour rows, so none of them reads "No information".
    first = floor.replace(minute=0, second=0, microsecond=0)
    for subject, names in sorted(named.items()):
        cid = "Playlist.Name." + hashlib.md5(subject.encode()).hexdigest()[:10]
        add_channel(root, cid, names, None)
        start = first
        while start < ceiling:
            stop = start + timedelta(hours=6)
            p = ET.Element("programme", {"start": stamp(start), "stop": stamp(stop),
                                         "channel": cid})
            ET.SubElement(p, "title").text = subject
            ET.SubElement(p, "desc").text = "لا يوجد جدول منشور لهذه القناة"
            programmes_out.append(p)
            start = stop

    root.extend(programmes_out)
    ET.indent(root, space=" ")
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with gzip.open(OUT + ".tmp", "wb", compresslevel=9) as handle:
        handle.write(data)
    os.replace(OUT + ".tmp", OUT)
    say(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
