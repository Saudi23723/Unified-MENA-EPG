"""EVERY CLUB IN THE WORLD, NOT ONLY THE ONES ESPN INDEXES.

ESPN's team lists carry the big five and the American franchises and
almost nothing else: the Jordanian, Egyptian, Iraqi, Turkish lower and
second-division sides a MENA board is full of came back empty, so those
rows wore lettered discs. TheSportsDB knows them, league by league, and
knows each club's Arabic spelling too — which is the spelling the guide
usually carries.

So this walks every football competition the service has, takes the
badge of every club in it, and writes it under every name that club is
known by, in the exact slug team_badges reads. It is slow and it is
meant to be: it runs in the badge-collection job, once, and every board
built afterwards reads crests off the disk.

    python3 fetch_sportsdb_logos.py           # every competition
    python3 fetch_sportsdb_logos.py 4328 5055 # only those league ids
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image

from team_badges import _query, _slug

DIR = Path("logos/teams")
INDEX = DIR / "index.json"
API = "https://www.thesportsdb.com/api/v1/json/3/"
AGENT = {"User-Agent": "unified-mena-epg/1.0 (+github actions)"}
TIMEOUT = 20

# The service's competitions live in one contiguous stretch of ids.
FIRST_LEAGUE = 4328
LAST_LEAGUE = 5600


def read(url: str) -> bytes | None:
    try:
        with urlopen(Request(url, headers=AGENT), timeout=TIMEOUT) as answer:
            return answer.read()
    except Exception:
        return None


def json_of(url: str) -> dict:
    raw = read(url)
    if not raw:
        return {}
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


def league(one: int) -> dict | None:
    found = (json_of(f"{API}lookupleague.php?id={one}").get("leagues") or [None])[0]
    if not found or found.get("strSport") != "Soccer":
        return None
    return found


def clubs(name: str) -> list[dict]:
    found = json_of(f"{API}search_all_teams.php?l={quote(name)}")
    return found.get("teams") or []


def names_of(team: dict) -> list[str]:
    """Every spelling of the club a board might carry, Arabic included."""
    out = [team.get("strTeam"), team.get("strTeamShort")]
    for part in (team.get("strTeamAlternate") or "").split(","):
        out.append(part.strip())
    return [one for one in out if one and len(one) > 2]


def keep(team: dict, index: dict) -> int:
    url = team.get("strBadge") or team.get("strTeamBadge")
    if not url or team.get("strSport") != "Soccer":
        return 0
    spellings = names_of(team)
    spellings += [_query(one) for one in spellings]
    keys = []
    for one in spellings:
        key = _slug(one)
        if key and key not in keys:
            keys.append(key)
    if not keys or all((DIR / f"{key}.png").exists() for key in keys):
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
        index.setdefault(key, url)
    return written


def main(argv: list[str]) -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    try:
        index = json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        index = {}

    ids = [int(one) for one in argv] or list(range(FIRST_LEAGUE, LAST_LEAGUE + 1))
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = [one for one in pool.map(league, ids) if one]
    print(f"{len(found)} football competitions")

    total = 0
    for one in found:
        name = one.get("strLeague") or ""
        sides = clubs(name)
        if not sides:
            continue
        with ThreadPoolExecutor(max_workers=8) as pool:
            written = sum(pool.map(lambda team: keep(team, index), sides))
        total += written
        if written:
            print(f"  {name}: {len(sides)} sides, {written} badges")
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1,
                                    sort_keys=True), encoding="utf-8")

    print(f"{total} badges written into {DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
