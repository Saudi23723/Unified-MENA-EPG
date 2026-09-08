"""THE CREST BESIDE THE NAME.

A viewer four metres from a television does not read "Real Madrid CF -
FC Internazionale Milano" — they see two badges and know the match
before a word of it. The board had no badges at all, so every row was a
line of text and a row about Bayern looked exactly like a row about a
youth-league side nobody has heard of.

The badges come from TheSportsDB's open search — no key, no account —
and every one that arrives is written into `logos/teams/` and committed
with the boards. So a club is fetched once in its life: every build
after that reads it off the disk, the board draws the same picture
whether the search answers or not, and a service having a bad morning
costs the board nothing.

A club the search cannot place gets no badge and no blank hole either:
the board falls back to a lettered disc in a colour taken from the
club's own name, which is the same on every board forever.
"""

from __future__ import annotations

import json
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image

DIR = Path("logos/teams")
INDEX = DIR / "index.json"
SEARCH = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t="
AGENT = {"User-Agent": "unified-mena-epg/1.0 (+github actions)"}
TIMEOUT = 12

# Words a listing carries that a badge search does not know: the board
# says "Real Madrid Academy" where the search knows "Real Madrid", and
# an academy side wearing its parent club's crest is right rather than
# wrong — it is the same badge on the same shirt.
NOISE = re.compile(
    r"\b(fc|cf|sc|ac|afc|cd|sk|fk|if|bk|club|academy|acad|reserves?|"
    r"u\d{2}|women'?s?|femenino|team)\b", re.I)


def _slug(name: str) -> str:
    flat = unicodedata.normalize("NFKD", name)
    flat = "".join(ch for ch in flat if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", flat.casefold()).strip("-")


def _query(name: str) -> str:
    trimmed = NOISE.sub(" ", name)
    trimmed = re.sub(r"\s+", " ", trimmed).strip(" .-")
    return trimmed or name.strip()


def _index() -> dict:
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _remember(index: dict) -> None:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1,
                                    sort_keys=True), encoding="utf-8")
    except Exception:
        pass


def _download(url: str) -> Image.Image | None:
    try:
        with urlopen(Request(url, headers=AGENT), timeout=TIMEOUT) as answer:
            raw = answer.read()
        badge = Image.open(BytesIO(raw)).convert("RGBA")
    except Exception:
        return None
    # A crest is drawn small; a 500px original is stored at the size the
    # board can actually use, so the repository does not grow by a
    # megabyte a club.
    badge.thumbnail((128, 128), Image.LANCZOS)
    return badge


def _search(name: str) -> str | None:
    try:
        url = SEARCH + quote(_query(name))
        with urlopen(Request(url, headers=AGENT), timeout=TIMEOUT) as answer:
            found = json.load(answer)
    except Exception:
        return None
    teams = found.get("teams") or []
    wanted = _slug(_query(name))
    best = None
    for team in teams:
        badge = team.get("strBadge") or team.get("strTeamBadge")
        if not badge:
            continue
        names = [team.get("strTeam") or ""]
        names += (team.get("strTeamAlternate") or "").split(",")
        if any(_slug(other) == wanted for other in names):
            return badge
        best = best or badge
    return best


def badge(name: str) -> Image.Image | None:
    """The club's crest, off the disk if it is there and off the wire once."""
    key = _slug(name)
    if not key:
        return None
    stored = DIR / f"{key}.png"
    if stored.exists():
        try:
            return Image.open(stored).convert("RGBA")
        except Exception:
            return None
    index = _index()
    if index.get(key) == "":                    # searched once, not found
        return None
    url = _search(name)
    index[key] = url or ""
    _remember(index)
    if not url:
        return None
    crest = _download(url)
    if crest is None:
        return None
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        crest.save(stored)
    except Exception:
        pass
    return crest
