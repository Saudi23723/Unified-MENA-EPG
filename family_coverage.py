#!/usr/bin/env python3
"""Which playlist channels NONE of the owner's other links guide.

    python family_coverage.py      # reads att_epg.xml.gz, writes alkass_extra.json

The playlist guide (att_epg.xml.gz) rides the SAIF ALKASS link for the
second playlist, Family4k (alwan_channels_epg.add_playlist_guide_to). That
link sits high in the owner's TiviMate list, so a channel it carries wins
over the same channel on a link lower down. Carrying channels other links
already guide is how MBC and OSN went blank on 6 October 2026: a partial
or filler guide here beat the full one the player had been reading.

So the only channels that go there are the ones no other link the owner
has on for Family4k matches — by id, by exact name, or by the near name a
player also accepts ("MBC 1 HD" for "MBC 1"). For those, the guide here is
the only one there is, and nothing can be overridden.

OWNER_LINKS is the owner's list as their screen showed it (6 October
2026), SAIF ALKASS itself left out. If any of them cannot be read, no list
is written at all, and the Alkass link falls back to its strict rule —
a link we could not read might guide any channel.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import requests

import playlist_match as pm

GUIDE = "att_epg.xml.gz"
# A name that says which country's feed it is — "Fr: BeIN Sports 1",
# "TR: CNN Turk", "Spt-VIP| UK: ...". Its near name drops the country, and
# "beIN Sports 1" on SAIF beIN QA is Qatar's channel, not France's: such a
# name is covered only by an exact match, so the French feed rides here
# under its own name and its own schedule.
COUNTRY = re.compile(r"(?i)^\s*(?:spt-vip\s*\|\s*)?[a-z]{2,4}(?:\s*\|\s*[a-z]{2,4})?\s*[:|]")
OUT = "alkass_extra.json"
FAMILY = "family_channels.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}

# (label, a file of this repository, or an address)
OWNER_LINKS = [
    ("ALWAN Sports", "alwan_sports_epg.xml"),
    ("FajerTv", "fajer_sports_epg.xml"),
    ("JORDAN SPORTS", "jordan_sports_epg.xml"),
    ("Saif beIN TR", "bein_sports_turkey_epg.xml"),
    ("SAIF beIN QA", "bein_sports_qatar_epg.xml"),
    ("SAIF Jo", "roya_jordan_epg.xml"),
    ("SAIF Starzplay", "starzplay_epg.xml"),
    ("SAIF TABII", "tabii_spor_1_10_epg.xml"),
    ("SHASHA", "shasha_epg.xml"),
    ("TURKEY", "https://iptv-epg.org/files/epg-tr.xml"),
    ("ثمانية", "thmanyah_epg.xml"),
    ("US5", "https://www.open-epg.com/files/unitedstates5.xml.gz"),
    ("Egy1", "https://www.open-epg.com/files/egypt1.xml.gz"),
    ("Egy2", "https://www.open-epg.com/files/egypt2.xml.gz"),
    ("Saudi1", "https://www.open-epg.com/files/saudiarabia1.xml.gz"),
    ("Saudi2", "https://www.open-epg.com/files/saudiarabia2.xml.gz"),
    ("iptvx.one", "https://iptvx.one/EPG"),
]


def channels_of(where: str) -> tuple[set[str], set[str], set[str]]:
    """(ids, lower-case names, near names) of one link's channels."""
    if where.startswith("http"):
        raw = requests.get(where, headers=UA, timeout=180).content
    else:
        with open(where, "rb") as handle:
            raw = handle.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    ids, names, near = set(), set(), set()
    for _event, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if el.tag == "channel":
            ids.add(el.get("id") or "")
            for d in el.findall("display-name"):
                text = (d.text or "").strip()
                if text:
                    names.add(text.lower())
                    near.add(pm.norm(text))
            el.clear()
        elif el.tag == "programme":
            el.clear()
    near.discard("")
    return ids, names, near


def main() -> int:
    if not os.path.exists(GUIDE):
        print(f"coverage: no {GUIDE} — nothing to decide")
        return 0
    ids, names, near = set(), set(), set()
    for label, where in OWNER_LINKS:
        try:
            i, n, r = channels_of(where)
        except Exception as exc:                            # noqa: BLE001
            # FAIL SAFE. A link that cannot be read might guide any channel,
            # and putting a channel here that it guides is the MBC fault
            # over again. So no list at all this run: the Alkass link keeps
            # its strict rule (real schedules, nothing Arabic).
            print(f"::warning::coverage: {label} unreadable "
                  f"({type(exc).__name__}) — no list this run")
            if os.path.exists(OUT):
                os.remove(OUT)
            return 0
        ids |= i
        names |= n
        near |= r
        print(f"coverage: {label:15} {len(i):5} channel(s)")

    # Judged on Family4k's own channels, as the player shows them — not on
    # the guide's extra names: "Fr: BeIN Sports 1 FHD" is not covered by
    # Qatar's "beIN Sports 1" just because the guide also lists it so.
    try:
        with open(FAMILY, encoding="utf-8") as handle:
            family = json.load(handle)
    except (OSError, ValueError):
        print(f"::warning::coverage: no {FAMILY} — no list this run")
        return 0
    root = ET.parse(gzip.open(GUIDE)).getroot()
    carrier: dict[str, str] = {}
    for ch in root.findall("channel"):
        carrier.setdefault(ch.get("id") or "", ch.get("id") or "")
        for d in ch.findall("display-name"):
            carrier.setdefault(("name", (d.text or "").strip().lower()), ch.get("id"))
    # cid -> the Family4k names it is the only guide for. ONLY those names
    # ride the Alkass link: the guide's other names ("beIN Sports 1") would
    # take a channel another link guides — Qatar's, lower in the list.
    extra: dict[str, list[str]] = {}
    covered, lost = 0, 0
    for name, epg in family:
        if (epg and epg in ids) or name.lower() in names or \
                (not COUNTRY.match(name) and pm.norm(name) in near):
            covered += 1
            continue
        cid = carrier.get(("name", name.lower()))
        if cid:
            extra.setdefault(cid, []).append(name)
        else:
            lost += 1
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({k: sorted(set(v)) for k, v in sorted(extra.items())}, handle,
                  ensure_ascii=False)
    print(f"coverage: of {len(family)} Family4k channel(s), {covered} guided by "
          f"another link, {len(family) - covered - lost} only here "
          f"({len(extra)} guide channel(s)), {lost} in no guide at all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
