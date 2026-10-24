#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The order the DreamTV relays show their groups and channels in.

Asked for as "Can you organize categories and channels in a nice order !"
(24 October 2026). Groups: Arabic sports first, then the Arabic channels by
country, then international sports, then the other countries, and the event,
pay-per-view, 24/7, on-demand and radio groups last. Channels: by name in
numeric order (beIN SPORTS 2 before beIN SPORTS 10), each channel's copies
together, best picture first (4K, FHD, HD, SD, then HEVC, RAW and the rest).
"""
from __future__ import annotations

import re

# (rank, pattern on the group name). First match wins; unknown groups sit in the middle.
GROUP_RANK = [
    (1, r"\bBEIN\b(?!.*\b(TR|TURK|FR|FRANCE|EN|AU)\b)"), (2, r"AL.?KASS"), (3, r"THMANYAH|THAMANYA|\bSSC\b"),
    (4, r"\bAD\b|STARZ ?PLAY"), (5, r"ALWAN"), (6, r"SHAHID SPORT|SOLO|SHASHA|\bTOD\b|1001"),
    (7, r"ARABIC SPORT|EGYPT SPORT|AL FAJER|FAJER|NM SPORT|SPORTS PPV NM|UEFA CHAMPIONS|SPORT LQ"),
    (10, r"NEWS"), (11, r"\bMBC\b"), (12, r"SAUDI|السعودية"), (13, r"EMIRATES|\bUAE\b"), (14, r"QATAR"),
    (15, r"EGYPT|مصر"), (16, r"JORDAN|ROYA"), (17, r"LEBANON"), (18, r"SYRIA"), (19, r"IRAQ"), (20, r"KUWAIT|OMAN|YEMEN|BAHRAIN"),
    (21, r"MOROCCO|ALGERIA|TUNISIA|MAGHREB"), (22, r"\bOSN\b|GOBX"), (23, r"SHAHID|STC|SHOOF|STARZ PLAY 4K|NOOR|MAJESTIC|ON DEMAND|NETFLIX (MOVIES|SERIES|GERMANY)"),
    (24, r"KIDS|CARTOON"), (25, r"DOCUMENT|DISCOVERY"), (26, r"ISLAMIC|QURAN|القران"), (27, r"MUSIC|KITCHEN|MASRAH|ALRABIAA|TABII"),
    (30, r"SKY SPORT(?!S NZ)|TNT|PREMIER LEAGUE|PREMIER SPORT|EPL"), (31, r"DAZN"), (32, r"EUROSPORT"), (33, r"\bESPN\b(?!\+)"),
    (34, r"TSN(?!\+)|SPORTSNET(?!\+)|\bCA\b.*SPORT"), (35, r"\bUS\b.*SPORT|SPORTS NETWORK|NBA|NFL|NHL|MLB|UFC|BOXING|TENNIS|GOLF|MOTO|F1|FORMULA"),
    (36, r"SPORT|SPOR\b|DESPORTO"),
    (40, r"^UK\b|\bUK\b|NOW TV|ITV|BBC"), (41, r"^US\b|\bUS\b|ABC|CBS|NBC|FOX|\bCW\b"), (42, r"^CA\b|\bCA\b|CANADA"),
    (43, r"ITALY|^IT\b"), (44, r"SWITZERLAND|SWISS|^CH\b"), (45, r"FRANCE|^FR\b"), (46, r"PORTUGAL|^PT\b"), (47, r"TURK|^TR\b|HABER"),
    (48, r"IRELAND|^IE\b"), (49, r"AUSTRALIA|^AU\b"), (50, r"BULGARIA|SLOVENIA|ROMANIA|SERBIA|GREECE|POLAND"),
    (90, r"PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\+|TSN\+|SN\+|PEACOCK|PARAMOUNT|STAN\b|FLO\b|BTN\+|MAX\b|HBO|VICTORY|FUBO|CUP GAMES|ONBOARD"),
    (95, r"24/7|ROKU|TUBI|PLUTO|ONEPLAY|CINEMA TV SHOWS|REPLAY|SERIES"), (99, r"RADIO"),
]
QUALITY = ["8K", "4K", "UHD", "3840P", "FHD", "HD", "SD", "LQ", "HEVC", "RAW"]


# "UK | SPORT HD", "TR | beIN SPORTS GOLD": a country prefix puts the group in that
# country's block (its sport first, then the rest); AR keeps the Arabic order above.
COUNTRY = {"UK": 40, "US": 41, "CA": 42, "IT": 43, "CH": 44, "FR": 45, "PT": 46, "TR": 47, "IE": 48, "AU": 49,
           "TS": 35, "8K": 36, "4K": 36}
LATE = re.compile(r"PPV|PAY PER VIEW|EVENT|PACKAGE|24/7|REPLAY|RADIO|ROKU|TUBI|ONEPLAY|SERIES|CINEMA TV SHOWS", re.I)


def group_rank(group: str) -> float:
    g = group.upper()
    m = re.match(r"^([A-Z0-9]{2,3})\s*\|", g)
    if m and m.group(1) in COUNTRY and not LATE.search(g):
        return COUNTRY[m.group(1)] + (0.1 if re.search(r"SPORT|SPOR\b|DESPORTO|TSN|DAZN|ESPN|TNT|SKY SPORT", g) else 0.5)
    for rank, pattern in GROUP_RANK:
        if re.search(pattern, g):
            return rank
    return 60


def group_quality(group: str) -> int:
    g = group.upper()
    if re.search(r"\b(4K|8K|UHD|3840P)\b", g) and not re.search(r"\b(SD|LQ)\b", g):
        return 0
    if re.search(r"\b(SD|LQ)\b", g):
        return 3
    if re.search(r"\b(RAW|HEVC)\b", g):
        return 2
    return 1


def natural(text: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text.upper())]


def channel_key(name: str):
    words = name.upper().split()
    q = [w for w in words if w in QUALITY]
    rest = [w for w in words if w not in QUALITY]
    # the channel's number sorts after its words: beIN SPORTS 1..9, then beIN SPORTS XTRA 1..9
    numbers = [int(w) for w in rest if w.isdigit()]
    words_only = " ".join(w for w in rest if not w.isdigit())
    qrank = min((QUALITY.index(w) for w in q), default=len(QUALITY))
    return natural(words_only), numbers, qrank, natural(name)


def order(chans: list[dict]) -> list[dict]:
    first_seen = {}
    for i, c in enumerate(chans):
        first_seen.setdefault(c["group"], i)
    return sorted(chans, key=lambda c: (group_rank(c["group"]), group_quality(c["group"]), first_seen[c["group"]],
                                          channel_key(c["name"])))
