"""EVERY BADGE THE BOARDS CAN NEED, FETCHED ONCE AND KEPT.

A crest looked up while a board is being drawn is a crest that arrives
late or not at all: the search is one request per club, it is slow when
it answers and silent when it does not, and a build that waits on it
publishes an hour late. So the badges are collected here instead —
league by league, off ESPN's own team lists, which carry the official
mark for every club, every franchise and every national side they know
— and written into logos/teams/ under the same slug team_badges reads.

After this has run, a board draws its crests off the disk. Nothing on
the critical path touches the network at all.

    python3 fetch_league_logos.py            # everything below
    python3 fetch_league_logos.py nba nfl    # only those
"""

from __future__ import annotations

import json
import sys
import unicodedata
import re
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image

DIR = Path("logos/teams")
INDEX = DIR / "index.json"
AGENT = {"User-Agent": "unified-mena-epg/1.0 (+github actions)"}
TIMEOUT = 12
LIST = "https://site.api.espn.com/apis/site/v2/sports/{path}/teams?limit=1000"

# The American leagues asked for by name, then the football of the world:
# the continental competitions, the leagues a MENA viewer is watching,
# the big five, and the national-team competitions, whose "clubs" ARE the
# countries — which is where a flag on a World Cup qualifier comes from.
LEAGUES: dict[str, str] = {
    "nba": "basketball/nba",
    "wnba": "basketball/wnba",
    "nfl": "football/nfl",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "ncaam": "basketball/mens-college-basketball",
    "ncaaf": "football/college-football",
}

FOOTBALL = [
    "fifa.world", "fifa.worldq.uefa", "fifa.worldq.afc", "fifa.worldq.caf",
    "fifa.worldq.concacaf", "fifa.worldq.conmebol", "fifa.worldq.ofc",
    "fifa.wwc", "fifa.confederations", "fifa.olympics", "fifa.friendly",
    "uefa.champions", "uefa.europa", "uefa.europa.conf", "uefa.euro",
    "uefa.nations", "uefa.super_cup",
    "afc.champions", "afc.cup", "afc.asian.cup", "caf.champions", "caf.nations",
    "concacaf.champions", "conmebol.libertadores", "conmebol.sudamericana",
    "club.friendly", "fifa.cwc",
    "eng.1", "eng.2", "eng.3", "eng.4", "eng.fa", "eng.league_cup",
    "esp.1", "esp.2", "esp.copa_del_rey",
    "ita.1", "ita.2", "ita.coppa_italia",
    "ger.1", "ger.2", "ger.dfb_pokal",
    "fra.1", "fra.2", "fra.coupe_de_france",
    "ned.1", "por.1", "bel.1", "sco.1", "wal.1", "tur.1", "gre.1", "rus.1",
    "aut.1", "sui.1", "den.1", "swe.1", "nor.1", "pol.1", "cze.1",
    "ukr.1", "rou.1", "cro.1", "srb.1", "hun.1", "isr.1", "cyp.1",
    "ksa.1", "uae.1", "qat.1", "kuw.1", "bhr.1", "omn.1", "jor.1",
    "egy.1", "mar.1", "tun.1", "alg.1", "irq.1", "lib.1", "syr.1",
    "usa.1", "usa.nwsl", "mex.1", "bra.1", "arg.1", "chi.1", "col.1",
    "uru.1", "per.1", "par.1", "ecu.1", "bol.1", "ven.1",
    "jpn.1", "kor.1", "chn.1", "aus.1", "ind.1", "idn.1", "tha.1",
    "eng.w.1", "esp.w.1", "ger.w.1", "fra.w.1", "uefa.wchampions",
]
for slug in FOOTBALL:
    LEAGUES[slug] = f"soccer/{slug}"


def slug(name: str) -> str:
    flat = unicodedata.normalize("NFKD", name or "")
    flat = "".join(ch for ch in flat if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", flat.casefold()).strip("-")


def read(url: str) -> bytes | None:
    try:
        with urlopen(Request(url, headers=AGENT), timeout=TIMEOUT) as answer:
            return answer.read()
    except Exception:
        return None


def teams(path: str) -> list[dict]:
    raw = read(LIST.format(path=path))
    if not raw:
        return []
    try:
        found = json.loads(raw)
        return (found["sports"][0]["leagues"][0].get("teams") or [])
    except Exception:
        return []


def names_of(team: dict) -> list[str]:
    """Every spelling of the club a board might carry."""
    out = [team.get("displayName"), team.get("shortDisplayName"),
           team.get("name"), team.get("nickname"), team.get("location")]
    if team.get("location") and team.get("name"):
        out.append(f"{team['location']} {team['name']}")
    return [one for one in out if one and len(one) > 2]


def badge_url(team: dict) -> str | None:
    for logo in team.get("logos") or []:
        href = logo.get("href")
        rel = " ".join(logo.get("rel") or [])
        if href and "dark" not in rel:
            return href
    return (team.get("logos") or [{}])[0].get("href")


def keep(team: dict, index: dict) -> int:
    url = badge_url(team)
    if not url:
        return 0
    keys = [slug(one) for one in names_of(team)]
    keys = [key for key in keys if key]
    if not keys:
        return 0
    if all((DIR / f"{key}.png").exists() for key in keys):
        return 0
    raw = read(url)
    if not raw:
        return 0
    try:
        crest = Image.open(BytesIO(raw)).convert("RGBA")
    except Exception:
        return 0
    crest.thumbnail((128, 128), Image.LANCZOS)
    written = 0
    for key in keys:
        path = DIR / f"{key}.png"
        if not path.exists():
            crest.save(path)
            written += 1
        index[key] = url
    return written


# LEAGUES ESPN HAS NEVER HEARD OF. Jordan's top flight returns a plain
# 404 from every ESPN path, so its clubs were the one MENA league whose
# crests could never arrive with the sweeps above. TheSportsDB publishes
# the same roster — badge, English name, and the Arabic spelling the
# guide actually prints — so those leagues are collected from there and
# written under every spelling, Latin and Arabic alike.
SPORTSDB_LEAGUES = [
    "Jordanian Pro League",
    "Jordanian First Division League",
]
SPORTSDB_ROSTER = "https://www.thesportsdb.com/api/v1/json/3/search_all_teams.php?l="


def sportsdb_keys(team: dict) -> list[str]:
    from urllib.parse import quote  # noqa: F401  (kept local, see below)
    from team_badges import _slug as arabic_slug

    names = [team.get("strTeam") or ""]
    names += (team.get("strTeamAlternate") or "").split(",")
    keys = [arabic_slug(one.strip()) for one in names if one.strip()]
    return [key for key in keys if key and len(key) > 2]


def sportsdb_league(name: str) -> int:
    from urllib.parse import quote

    raw = read(SPORTSDB_ROSTER + quote(name))
    if not raw:
        print(f"  {name}: nothing (source quiet)")
        return 0
    try:
        rows = json.loads(raw).get("teams") or []
    except Exception:
        return 0
    written = 0
    for team in rows:
        url = team.get("strBadge") or team.get("strTeamBadge")
        keys = sportsdb_keys(team)
        if not url or not keys:
            continue
        if all((DIR / f"{key}.png").exists() for key in keys):
            continue
        raw_badge = read(url)
        if not raw_badge:
            continue
        try:
            crest = Image.open(BytesIO(raw_badge)).convert("RGBA")
        except Exception:
            continue
        crest.thumbnail((128, 128), Image.LANCZOS)
        for key in keys:
            path = DIR / f"{key}.png"
            if not path.exists():
                crest.save(path)
                written += 1
    print(f"  {name}: {len(rows)} sides, {written} badges written")
    return written


def main(argv: list[str]) -> int:
    wanted = argv or list(LEAGUES)
    DIR.mkdir(parents=True, exist_ok=True)
    try:
        index = json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        index = {}

    total = 0
    if not argv or "jordan" in argv:
        for league in SPORTSDB_LEAGUES:
            total += sportsdb_league(league)
        wanted = [one for one in wanted if one != "jordan"]
    for name in wanted:
        path = LEAGUES.get(name, name)
        found = teams(path)
        if not found:
            print(f"  {name}: nothing (source quiet)")
            continue
        rows = [one.get("team") or {} for one in found]
        with ThreadPoolExecutor(max_workers=8) as pool:
            written = sum(pool.map(lambda team: keep(team, index), rows))
        total += written
        print(f"  {name}: {len(rows)} sides, {written} badges written")

    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1,
                                sort_keys=True), encoding="utf-8")
    print(f"{total} badges written into {DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
