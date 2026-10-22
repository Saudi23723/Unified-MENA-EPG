"""Every common name and id a playlist may give a country's channels.

The owner's third playlist ("STRONG") cannot be read from GitHub — its
provider answers 403 — so the guide cannot learn its names the way it
learns the other two's. Its French, American and Australian channels read
"No information" (22 October 2026): "TF1", "FRANCE 2", "SP: RMC SPORT 1",
"US: USA NETWORK", "KAYO - FOX SPORTS 505". Each channel of those
countries' guides is therefore published under the spellings playlists
use for it — its own name, in capitals, without accents, with and without
a quality mark, behind the country marks providers put in front — and
under the plain ids providers file it as (tf1.fr, beinsports1.fr). A form
another channel already answers to is left to that channel, so the order
of COUNTRIES decides a name two countries share ("BEIN SPORTS 1").
"""
from __future__ import annotations

import re
import unicodedata

# source -> (country id suffix, the marks providers put before a name).
# France first: its playlist group names channels bare ("BEIN SPORTS 1",
# "SYFY"), where the American one marks them "US:".
COUNTRIES = {
    "FR1": ("fr", ("FR", "SP")),
    "AU1": ("au", ("AU", "KAYO")),
    "US2": ("us", ("US", "USA")),
    # The Argon playlist's Italian group ("IT: SKY SPORT UNO"), and the
    # other European guides alongside, so no country is left out.
    "IT1": ("it", ("IT",)),
    "UK1": ("uk", ("UK",)),
    "DE1": ("de", ("DE",)),
    "ES1": ("es", ("ES",)),
}
QUALITY = ("", " HD", " FHD", " 4K")
TRAILING = re.compile(r"(?:\s+(?:HD|FHD|UHD|SD|4K|HEVC)|\s*\(s\))+\s*$", re.I)
PACIFIC = re.compile(r"\s*\(?\bpacific\b\)?", re.I)
# What a source calls a channel -> what playlists call it too.
ALSO = {"FS1": ["FOX SPORTS 1"], "FS2": ["FOX SPORTS 2"], "TRUTV": ["TRU TV"],
        "ESPN": ["ESPN 1"], "FOX CRICKET": ["FOX SPORTS 501"],
        "FOX LEAGUE": ["FOX SPORTS 502"], "FOX FOOTY": ["FOX SPORTS 504"],
        "FOX SPORTS MORE": ["FOX SPORTS 507"], "TF1 SERIES FILMS": ["TF1 SERIES"],
        "CANAL+ PREMIER LEAGUE": ["CANAL+ PL"], "13EME RUE": ["13 EME RUE", "13E RUE", "13 EMERUE"],
        "EUROSPORT 1": ["SKY EUROSPORT 1"], "EUROSPORT 2": ["SKY EUROSPORT 2"],
        # Italy: the Argon playlist's spellings of IT1's channels.
        "RAISPORT": ["RAI SPORT"], "SPORTITALIA": ["SPORT ITALIA"],
        "EUROSPORT ITALIA": ["SKY EUROSPORT 1", "EUROSPORT 1"],
        "EUROSPORT 2 ITALIA": ["SKY EUROSPORT 2", "EUROSPORT 2"],
        "MILAN TV": ["SKY MILAN TV"],
        **{f"SKY SPORT {250 + n}": [f"SKY CALCIO {n}"] for n in range(1, 9)}}


def fold(text: str) -> str:
    """'Téva' -> 'Teva'."""
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def cores(name: str) -> list[str]:
    """The bare names one source name stands for, in capitals."""
    name = " ".join(name.split())
    west = bool(PACIFIC.search(name))
    core = TRAILING.sub("", PACIFIC.sub("", name)).strip()
    if not core:
        return []
    out = [fold(core).upper()]
    out += [re.sub(r"(?<=[A-Z])(?=\d)", " ", out[0]),     # ESPN2 -> ESPN 2
            re.sub(r"(?<=[A-Z]) (?=\d+$)", "", out[0])]    # ESPN 2 -> ESPN2
    out += [also for c in list(out) for also in ALSO.get(c, [])]
    if west:
        out = [c if re.search(r"\bWEST\b", c) else c + " WEST" for c in out]
    return list(dict.fromkeys(out))


def forms(name: str, marks) -> list[str]:
    """Every spelling of one channel name, most exact first."""
    out = [name]
    for core in cores(name):
        for q in QUALITY:
            out.append(core + q)
            for mark in marks:
                out.append(f"{mark}{' - ' if mark == 'KAYO' else ': '}{core}{q}")
    return list(dict.fromkeys(out))


def plain_ids(name: str, country: str) -> list[str]:
    """'Canal+ Sport' in France -> ['canalplussport.fr', 'canalplussporthd.fr']."""
    out = []
    for core in cores(name)[:1]:
        squeezed = re.sub(r"[^a-z0-9]", "", core.lower().replace("+", "plus")
                          .replace("&", "and"))
        if squeezed:
            out += [f"{squeezed}.{country}", f"{squeezed}hd.{country}"]
    return out
