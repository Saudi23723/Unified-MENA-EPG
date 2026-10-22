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
    # The rest of the second playlist's world (22 October 2026: Srb: Arena
    # Sport, Alb: Tring Sport, TSN, PL: TVP Sport read their own name).
    # "AR" is not Argentina's mark: playlists use it for Arabic channels.
    "TR1": ("tr", ("TR", "TR VIP")), "TR3": ("tr", ("TR", "TR VIP")),
    "RS1": ("rs", ("SRB", "RS", "EXYU")), "HR1": ("hr", ("HR", "CRO", "EXYU")),
    "BA1": ("ba", ("BA", "BIH", "EXYU")), "AL1": ("al", ("ALB", "AL")),
    "CA2": ("ca", ("CA",)), "PL1": ("pl", ("PL",)), "PT1": ("pt", ("PT",)),
    "GR1": ("gr", ("GR",)), "IL1": ("il", ("IL", "IS", "ISR")),
    "NL1": ("nl", ("NL",)), "IE1": ("ie", ("IE", "IRL")), "RO1": ("ro", ("RO",)),
    "BG1": ("bg", ("BG",)), "HU1": ("hu", ("HU",)), "CZ1": ("cz", ("CZ",)),
    "SK1": ("sk", ("SK",)), "CH1": ("ch", ("CH",)), "AT1": ("at", ("AT",)),
    "SE1": ("se", ("SE",)), "NO1": ("no", ("NO",)), "DK1": ("dk", ("DK",)),
    "FI1": ("fi", ("FI",)), "NZ1": ("nz", ("NZ",)), "ZA1": ("za", ("ZA",)),
    "MX1": ("mx", ("MX",)), "BR1": ("br", ("BR",)), "AR1": ("ar", ("ARG",)),
    "IN1": ("in", ("IN",)),
}
# The countries whose channels are also published under a plain provider
# id (tf1.fr). The others go by name only: the file would otherwise grow
# by every programme of every country a second time.
PLAIN_IDS = {"FR1", "AU1", "US2", "IT1", "UK1", "DE1", "ES1"}
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
    # Turkish "Spor" for "Sport" (TiviBu Spor 2 / TR: TiviBu Sport 2), and
    # SuperSport written apart (Alb: Super Sport 1).
    out += [re.sub(r"\bSPOR\b", "SPORT", c) for c in out]
    out += [re.sub(r"SUPERSPORT", "SUPER SPORT", c) for c in out]
    out += [re.sub(r"BEINSPORTS", "BEIN SPORTS", c) for c in out]   # TR1's "Beinsports 3"
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


MARKS = re.compile(r"[\u1d2c-\u1d7f\u02b0-\u02b8\u1d43-\u1dbf\u2070-\u209f\u207d\u207e◉⚽]+")
# A playlist's word for a channel the guides spell otherwise.
CALLED = {"ALEPPO TODAY": "HALAB TODAY", "ALSOURIYA": "AL SOURIYA",
          "AL EKHBARIYA SY": "AL EKHBARIYA SYRIA", "SYRIA AL EKHBARIYA": "AL EKHBARIYA SYRIA",
          "ALARABY": "AL ARABY", "ALARABY 1": "AL ARABY", "AL ARABY 1": "AL ARABY",
          "ALARABY 2": "AL ARABY 2"}


def bare(name: str, shown) -> list[str]:
    """What a playlist name says once its marks are off: "AR: HALAB TODAY ᴴᴰ
    ⁽ᴮᴷ⁾" -> HALAB TODAY, and with or without a closing TV."""
    text = MARKS.sub(" ", shown(name))
    text = re.sub(r"\b(RAW|HEVC|BK|LQ|BACKUP)\b", " ", text, flags=re.I)
    out = []
    for core in cores(text):
        plain = re.sub(r"\s+TV$", "", core)
        plain = CALLED.get(plain, plain)
        out += [CALLED.get(core, core), plain + " TV"]
        # Without TV only while a name is left: "SYRIA" alone could be any.
        if len(plain.split()) > 1:
            out.append(plain)
    return [c for c in dict.fromkeys(out) if c]
