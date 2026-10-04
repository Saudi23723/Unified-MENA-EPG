#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The "US| AT&T" category of the owner's own Xtream playlist — a guide and
the AT&T mark for every channel in it.

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

import gzip
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


def playlist_names() -> list[str]:
    """Every channel name in the playlist's AT&T category, or []."""
    url, user, password = login()
    host = re.sub(r"^https?://", "", url).split(":")[0]
    SECRETS.extend(x for x in (url, user, password, host) if x)
    if not (url and user and password):
        say("playlist: no login in the secrets")
        return []
    auth = {"username": user, "password": password}
    try:
        def api(**kw):
            r = requests.get(url + "/player_api.php", params={**auth, **kw},
                             headers={"User-Agent": "TiviMate/4.7.0"}, timeout=90)
            r.raise_for_status()
            return r.json()
        cats = {str(c["category_id"]) for c in api(action="get_live_categories")
                if CATEGORY.search(c.get("category_name") or "")}
        names = [s["name"] for s in api(action="get_live_streams")
                 if str(s.get("category_id")) in cats
                 and (s.get("name") or "").strip()
                 and not s["name"].lstrip().startswith("#")]
    except Exception as exc:  # noqa: BLE001 - scrubbed and reported
        say(f"playlist: unreadable ({type(exc).__name__}: {exc})"[:300])
        return []
    say(f"playlist: {len(names)} channel(s) in {len(cats)} AT&T categor"
        f"{'y' if len(cats) == 1 else 'ies'}")
    return names


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

def build() -> int:
    mapping: dict[str, list[str]] = json.load(open(MAP, encoding="utf-8"))
    names = playlist_names()
    if not names:
        # The playlist could not be read this time: publish the channels
        # it had when they were mapped, under the name it gives them.
        names = [f"AT&T: {key} ᴿᴬᵂ" for key in mapping]
        say(f"playlist: using the {len(names)} mapped channel names")

    now = datetime.now(timezone.utc)
    floor, ceiling = now - BEHIND, now + AHEAD
    wanted: dict[str, set[str]] = {}
    for name in names:
        hit = mapping.get(core(name))
        if hit:
            wanted.setdefault(hit[0], set()).add(hit[1])

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

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — AT&T"})
    seen, mapped, filled, total = set(), 0, 0, 0
    for name in names:
        key = core(name)
        cid = channel_id(key)
        if cid in seen:
            continue
        seen.add(cid)
        ch = ET.SubElement(root, "channel", {"id": cid})
        ET.SubElement(ch, "display-name").text = name.strip()
        if f"AT&T: {key}" != name.strip():
            ET.SubElement(ch, "display-name").text = f"AT&T: {key}"
        ET.SubElement(ch, "icon", {"src": LOGO})
        hit = mapping.get(key)
        if not hit:
            continue
        mapped += 1
        programmes = sorted(rows.get(tuple(hit), []), key=lambda p: p.get("start"))
        last_stop = None
        for p in programmes:
            start = when(p.get("start"))
            if last_stop and start < last_stop:
                continue                     # an overlap in the source
            p.set("channel", cid)
            root.append(p)
            last_stop = when(p.get("stop"))
            total += 1
        filled += bool(programmes)

    say(f"guide: {len(seen)} channel(s), {mapped} with a source, {filled} with "
        f"programmes, {total} programme(s)")
    if mapped and filled < FLOOR * mapped:
        say(f"guide: only {filled}/{mapped} filled — a source is down; "
            f"keeping the published guide")
        return 1
    ET.indent(root, space=" ")
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with gzip.open(OUT + ".tmp", "wb", compresslevel=9) as handle:
        handle.write(data)
    os.replace(OUT + ".tmp", OUT)
    say(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
