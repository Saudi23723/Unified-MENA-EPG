"""Every common name and id a playlist may give a country's channels.

The owner's third playlist ("STRONG") cannot be read from GitHub — its
provider answers 403 — so the guide cannot learn its names the way it
learns the other two's. Its French, American and Australian channels read
"No information" (22 October 2026): "TF1", "FRANCE 2", "SP: RMC SPORT 1",
"US: USA NETWORK", "KAYO - FOX SPORTS 505". Each channel of those
countries' guides is therefore published under the spellings playlists
use for it — its own name, in capitals, with and without a quality mark,
behind the country marks providers put in front — and under the plain ids
providers file it as (tf1.fr, beinsports1.fr). A form another channel of
the guide already answers to is left to that channel.
"""
from __future__ import annotations

import re

# source -> (country id suffix, the marks providers put before a name)
COUNTRIES = {
    "FR1": ("fr", ("FR", "SP", "FRA", "FRANCE")),
    "US2": ("us", ("US", "USA")),
    "AU1": ("au", ("AU", "AUS", "KAYO")),
}
QUALITY = ("", " HD", " FHD", " UHD", " 4K", " SD")
TRAILING = re.compile(r"(?:\s+(?:HD|FHD|UHD|SD|4K|HEVC|\(\w+\)))+\s*$", re.I)


def base(name: str) -> str:
    """'USA Network HD' -> 'USA Network'; 'Fox Sports 503 (AU)' -> 'Fox Sports 503'."""
    return TRAILING.sub("", " ".join(name.split())).strip()


def forms(name: str, marks) -> list[str]:
    """Every spelling of one channel name, most exact first."""
    core = base(name)
    if not core:
        return []
    out = [name]
    for b in dict.fromkeys((core, core.upper())):
        for q in QUALITY:
            out.append(b + q)
            for mark in marks:
                sep = " - " if mark == "KAYO" else ": "
                out.append(f"{mark}{sep}{b}{q}")
    return list(dict.fromkeys(out))


def plain_ids(name: str, country: str) -> list[str]:
    """'Canal+ Sport 1' in France -> ['canalplussport1.fr', 'canalplussport1hd.fr']."""
    core = base(name).lower().replace("+", "plus").replace("&", "and")
    squeezed = re.sub(r"[^a-z0-9]", "", core)
    return [f"{squeezed}.{country}", f"{squeezed}hd.{country}"] if squeezed else []
