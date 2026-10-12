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
import time
from urllib.request import Request, urlopen

from PIL import Image

DIR = Path("logos/teams")
INDEX = DIR / "index.json"
SEARCH = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t="
AGENT = {"User-Agent": "unified-mena-epg/1.0 (+github actions)"}
TIMEOUT = 6

# A BOARD THAT NEVER FINISHES IS WORSE THAN A BOARD WITHOUT CRESTS.
# The first build after this change asks the crest service about every
# club it has never asked about, and an unknown name costs a search, a
# retry and sometimes a wait — hundreds of those in a row and the
# channel simply stops being rebuilt. So the whole run gets a budget:
# once it is spent, the remaining names take their lettered discs for
# this build and are asked again on the next one, which starts with
# everything the previous run cached.
BUDGET = 300.0
_SPENT = [0.0]

# Words a listing carries that a badge search does not know: the board
# says "Real Madrid Academy" where the search knows "Real Madrid", and
# an academy side wearing its parent club's crest is right rather than
# wrong — it is the same badge on the same shirt.
# Sports where an entry is a person or a squad nobody knows by badge.
SOLO_SPORTS = {"Motorsport", "Fighting", "Boxing", "Cycling", "Golf",
               "Tennis", "Athletics", "Skiing", "Horse Racing", "Darts",
               "Snooker", "Extreme Sports", "Motorcycle Racing"}

NOISE = re.compile(
    r"\b(fc|cf|sc|ac|afc|cd|sk|fk|if|bk|club|academy|acad|reserves?|"
    r"u\d{2}|women'?s?|femenino|team)\b", re.I)

# THE JORDANIAN LEAGUE HAS NO ESPN PAGE, so none of its crests ever
# arrived with the league sweeps, and the one name the search DID answer
# answered wrong: asked for "Al-Faisaly" it returns the SAUDI club, and
# the Amman side — the one this guide carries every week — wore a
# stranger's badge. So the Jordanian top flight is written down here,
# club by club, off TheSportsDB's own league roster, and taken from this
# table before any search is made.
JORDAN_BADGES = {
    "al-faisaly-amman":
        "https://r2.thesportsdb.com/images/media/team/badge/ja0udy1753205043.png",
    "al-wehdat":
        "https://r2.thesportsdb.com/images/media/team/badge/82f0fc1617889632.png",
    "al-ramtha":
        "https://r2.thesportsdb.com/images/media/team/badge/kczgws1753204656.png",
    "al-hussein-irbid":
        "https://r2.thesportsdb.com/images/media/team/badge/ijbwwm1753204799.png",
    "al-jazeera-amman":
        "https://r2.thesportsdb.com/images/media/team/badge/6yt0y51753204931.png",
    "al-baqaa":
        "https://r2.thesportsdb.com/images/media/team/badge/ng6x581625310975.png",
    "al-arabi-irbid":
        "https://www.thesportsdb.com/images/media/team/badge/96ad9u1786985546.png",
    "al-salt":
        "https://r2.thesportsdb.com/images/media/team/badge/5808ya1618585977.png",
    "dougra":
        "https://www.thesportsdb.com/images/media/team/badge/oin4hz1786985757.png",
    "shabab-al-ordon":
        "https://www.thesportsdb.com/images/media/team/badge/knxyd41786985786.png",
    "sahab":
        "https://r2.thesportsdb.com/images/media/team/badge/ye5h3z1625311112.png",
    "maan":
        "https://r2.thesportsdb.com/images/media/team/badge/yfjtd61625311108.png",
}

# Arabic guide spellings mapped to the official cached league badges.
BADGE_ALIASES = {
    "الوحدات": "al-wehdat", "الفيصلي": "al-faisaly-amman",
    "الفيصلي الأردني": "al-faisaly-amman", "الفيصلي الاردني": "al-faisaly-amman",
    "الفيصلي عمان": "al-faisaly-amman", "al-faisaly amman": "al-faisaly-amman",
    "al faisaly amman": "al-faisaly-amman",
    "الرمثا": "al-ramtha", "الحسين إربد": "al-hussein-irbid",
    "الحسين اربد": "al-hussein-irbid", "شباب الأردن": "shabab-al-ordon",
    "شباب الاردن": "shabab-al-ordon", "الجزيرة": "al-jazeera-amman",
    "الجزيرة عمان": "al-jazeera-amman",
    "العربي إربد": "al-arabi-irbid", "العربي اربد": "al-arabi-irbid",
    "البقعة": "al-baqaa", "دوقرة": "dougra", "دوقره": "dougra",
    "السلط": "al-salt", "سحاب": "sahab", "معان": "maan",
    "الأهلي الأردني": "al-ahli-jordan", "الاهلي الاردني": "al-ahli-jordan",
    "الأهلي": "al-ahly", "الاهلي": "al-ahly", "الزمالك": "zamalek-sc",
    "بيراميدز": "pyramids-fc", "المصري": "al-masry",
    "الإسماعيلي": "ismaily", "الاسماعيلي": "ismaily", "سموحة": "smouha",
    "سيراميكا كليوباترا": "ceramica-cleopatra", "الجونة": "el-gouna",
    "إنبي": "enppi", "انبي": "enppi", "الاتحاد السكندري": "al-ittihad-alexandria",
    "zamalek": "zamalek-sc", "pyramids": "pyramids-fc",
    "مانشستر يونايتد": "manchester-united", "مانشستر سيتي": "manchester-city",
    "ليفربول": "liverpool", "أرسنال": "arsenal", "ارسنال": "arsenal",
    "تشيلسي": "chelsea", "توتنهام": "tottenham-hotspur",
    "ريال مدريد": "real-madrid", "برشلونة": "barcelona",
    "أتلتيكو مدريد": "atletico-madrid", "اتلتيكو مدريد": "atletico-madrid",
    "يوفنتوس": "juventus", "إنتر ميلان": "inter-milan",
    "انتر ميلان": "inter-milan", "ميلان": "ac-milan",
    "بايرن ميونخ": "bayern-munich", "بوروسيا دورتموند": "borussia-dortmund",
    "باريس سان جيرمان": "paris-saint-germain", "مارسيليا": "marseille",
}

# Names such as Al Faisaly, Al Ahli and Al Jazeera exist in several Arab
# leagues.  Never decide which crest they mean from the club name alone.
# A Jordanian competition/source makes these spellings unambiguous; outside
# that context the ordinary league cache/search remains in charge.
JORDAN_CONTEXT = re.compile(r"jordan|jordanian|الأردن|الاردن|أردني|اردني", re.I)
JORDAN_CONTEXT_ALIASES = {
    "al faisaly": "al-faisaly-amman", "al-faisaly": "al-faisaly-amman",
    "al faisaly fc": "al-faisaly-amman", "al-faisaly fc": "al-faisaly-amman",
    "al wehdat": "al-wehdat", "al-wehdat": "al-wehdat",
    "al ramtha": "al-ramtha", "al-ramtha": "al-ramtha",
    "al hussein irbid": "al-hussein-irbid", "al-hussein irbid": "al-hussein-irbid",
    "al jazeera": "al-jazeera-amman", "al-jazeera": "al-jazeera-amman",
    "al jazeera amman": "al-jazeera-amman",
    "al baqaa": "al-baqaa", "al-baqaa": "al-baqaa",
    "al arabi irbid": "al-arabi-irbid", "al-arabi irbid": "al-arabi-irbid",
    "al salt": "al-salt", "al-salt": "al-salt",
    "shabab al ordon": "shabab-al-ordon", "shabab al-ordon": "shabab-al-ordon",
    "maan": "maan", "ma'an": "maan", "sahab": "sahab",
}


# ARABIC NAMES HAD NO BADGE AT ALL, and not because the search could not
# find them — because they never reached it. The slug kept Latin letters
# and digits and nothing else, so "الهلال" reduced to the empty string,
# the key was empty and badge() returned None on its first line. Every
# Arabic-spelled club on the board — the Saudi, Egyptian, Jordanian and
# Gulf rows, which is most of what this channel exists for — wore a
# lettered disc while their crests sat one search away.
#
# The alphabet answers it, the same way the guide's own duplicate test
# does: Arabic sports writing spells a club sound by sound, so the name
# is transliterated to Latin letters and the search is asked in the
# script it actually indexes.
ARABIC_LETTER = re.compile(r"[\u0600-\u06ff]")

ARABIC_SOUND = {
    "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d",
    "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "q", "ك": "k",
    "ل": "l", "م": "m", "ن": "n", "ه": "h", "ة": "a", "و": "u", "ي": "i",
    "ى": "a", "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ء": "", "ؤ": "u",
    "ئ": "i", "پ": "p", "چ": "ch", "ڤ": "v", "گ": "g", "ژ": "j",
    "\u064b": "", "\u064c": "", "\u064d": "", "\u064e": "", "\u064f": "",
    "\u0650": "", "\u0651": "", "\u0652": "",
}


def _romanised(name: str) -> str:
    """An Arabic club name written in the letters the search indexes."""
    if not ARABIC_LETTER.search(name or ""):
        return name
    out = []
    for word in (name or "").split():
        if word.startswith("ال") and len(word) > 3:
            out.append("al " + "".join(
                ARABIC_SOUND.get(ch, ch if ch.isascii() else "")
                for ch in word[2:]))
        else:
            out.append("".join(ARABIC_SOUND.get(ch, ch if ch.isascii() else "")
                               for ch in word))
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def _slug(name: str) -> str:
    flat = unicodedata.normalize("NFKD", _romanised(name))
    flat = "".join(ch for ch in flat if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", flat.casefold()).strip("-")


def _query(name: str) -> str:
    trimmed = NOISE.sub(" ", _romanised(name))
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


def _out_of_time() -> bool:
    return _SPENT[0] >= BUDGET


def _ask(term: str, loose: bool) -> str | None:
    """One search. Exact name wins; a loose ask takes the closest offered.

    "Closest" is not "first". Asked for "Al Hilal" the search offers
    "Al Hilal Wau" — a Sudanese club — ahead of the Riyadh one, and a
    board wearing the wrong crest is a board telling a lie confidently.
    So an exact name is taken outright, and failing that the shortest
    name that CONTAINS the one asked for, which is the club itself
    rather than a namesake with a town bolted on.
    """
    if _out_of_time():
        return None
    started = time.monotonic()
    try:
        url = SEARCH + quote(term)
        with urlopen(Request(url, headers=AGENT), timeout=TIMEOUT) as answer:
            found = json.load(answer)
    except Exception:
        return None
    finally:
        _SPENT[0] += time.monotonic() - started
    teams = found.get("teams") or []
    wanted = _slug(term)
    near: list[tuple[int, str]] = []
    for team in teams:
        # A CREST BELONGS TO A CLUB, NOT TO A MAN. Asked for the boxer
        # "Jones" the search offered a motorsport outfit called Parnelli
        # Jones, and the board put its logo beside a fighter's name.
        # Individual sports have no crests worth wearing, so their
        # entries are refused outright and the fighter keeps the
        # lettered disc that is honest about what it is.
        if (team.get("strSport") or "") in SOLO_SPORTS:
            continue
        badge = team.get("strBadge") or team.get("strTeamBadge")
        if not badge:
            continue
        names = [team.get("strTeam") or ""]
        names += (team.get("strTeamAlternate") or "").split(",")
        slugs = [_slug(other) for other in names if other.strip()]
        if wanted and any(other == wanted for other in slugs):
            return badge
        if wanted and any(wanted in other or other in wanted
                          for other in slugs if other):
            near.append((min(len(other) for other in slugs if other), badge))
    if near:
        near.sort(key=lambda pair: pair[0])
        return near[0][1]
    if loose:
        for team in teams:
            badge = team.get("strBadge") or team.get("strTeamBadge")
            if badge:
                return badge
    return None


def _search(name: str) -> str | None:
    """The club's badge, asked for in the ways a listing spells a club.

    The Arabic spelling is asked FIRST when there is one, because the
    search carries Arabic names and answers them precisely: "الهلال"
    returns Al-Hilal and nothing else, where the Latin "Al Hilal" leads
    with a Sudanese club of the same name.

    Then the romanised name whole, then with its last word dropped, then
    its first two words — a listings page prints "Al Hilal SFC Riyadh"
    where the search knows "Al Hilal". A one-word name is never taken
    loosely: a loose answer to "Norris" is somebody else's crest, and a
    wrong badge is worse than a lettered disc.
    """
    term = _query(name)
    if not term:
        return None
    tries: list[tuple[str, bool]] = []
    if ARABIC_LETTER.search(name or ""):
        raw = re.sub(r"\s+", " ", (name or "")).strip()
        if raw:
            tries.append((raw, True))
    words = term.split()
    tries.append((term, len(words) > 1))
    if len(words) > 2:
        tries.append((" ".join(words[:-1]), False))
        tries.append((" ".join(words[:2]), False))
    for attempt, loose in tries:
        badge = _ask(attempt, loose=loose)
        if badge:
            return badge
    return None


def badge(name: str, context: str = "") -> Image.Image | None:
    """The club's crest, off the disk if it is there and off the wire once."""
    key = _slug(name)
    if not key:
        return None
    clean_name = re.sub(r"\s+", " ", (name or "").strip()).casefold()
    alias = None
    if JORDAN_CONTEXT.search(context or ""):
        alias = JORDAN_CONTEXT_ALIASES.get(clean_name)
    if alias is None:
        alias = BADGE_ALIASES.get(clean_name)
    if alias:
        aliased = DIR / f"{alias}.png"
        if aliased.exists():
            try:
                return Image.open(aliased).convert("RGBA")
            except Exception:
                pass
        key = alias
    # A club written down by hand is never searched for: the roster is
    # the answer, and the first build that meets the club keeps it.
    fixed = JORDAN_BADGES.get(key)
    stored = DIR / f"{key}.png"
    if fixed and not stored.exists():
        crest = _download(fixed)
        if crest is not None:
            try:
                DIR.mkdir(parents=True, exist_ok=True)
                crest.save(stored)
            except Exception:
                pass
            index = _index()
            index[key] = fixed
            _remember(index)
            return crest
    stored = DIR / f"{key}.png"
    if stored.exists():
        try:
            return Image.open(stored).convert("RGBA")
        except Exception:
            return None
    if _out_of_time():
        return None
    index = _index()
    # A MISS RECORDED UNDER THE OLD SEARCH IS NOT A MISS. Arabic names
    # could never reach the wire before, so every one of them was filed
    # as "searched, nothing there" — and left alone, that file would keep
    # the new search from ever running. Old misses were written as "";
    # misses the current search made are written as "no", so the empty
    # ones are asked again exactly once and then settle.
    if index.get(key) == "no":                  # searched once, not found
        return None
    # A successful lookup can outlive its local PNG (for example after an
    # interrupted asset sync). Reuse the known official URL before spending
    # another search request, and restore the missing cached file.
    known = index.get(key)
    url = known if isinstance(known, str) and known.startswith("http") \
        else _search(name)
    index[key] = url or "no"
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
