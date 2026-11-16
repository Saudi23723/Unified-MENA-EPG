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
import threading
import time
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

# THE SERVICE ANSWERS THIRTY QUESTIONS A MINUTE AND REFUSES THE REST.
# Asked any faster it returns 429 to everything, which is how the first
# run found twenty-two competitions out of thirteen hundred and wrote no
# badges at all. So every question to the API waits its turn — two
# seconds apart, one at a time — and a refusal is simply asked again.
# The badge images themselves come off a plain file host and are not
# counted, so those still come down as fast as the network allows.
PACE = 2.1
_gate = threading.Lock()
_last = [0.0]


def paced() -> None:
    with _gate:
        wait = PACE - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()

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
    for _ in range(4):
        paced()
        raw = read(url)
        if raw:
            try:
                return json.loads(raw) or {}
            except Exception:
                return {}
        time.sleep(20)
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
    found = []
    for one in ids:
        got = league(one)
        if got:
            found.append(got)
    print(f"{len(found)} football competitions", flush=True)

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
            print(f"  {name}: {len(sides)} sides, {written} badges", flush=True)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1,
                                    sort_keys=True), encoding="utf-8")

    print(f"{total} badges written into {DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
