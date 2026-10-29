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


# Playlists that only carry a few countries, in the owner's own order (Up.1, 25 October 2026:
# "only uk, us and turkish channels ... turkish 1st in order"). Their late groups (events, 24/7)
# follow in the same country order, after all the live channels.
PLAYLIST_COUNTRY = {"up1": {"TR": 1, "UK": 2, "US": 3}}
# Groups the owner wants at the very top of a playlist ("Mozaik ... fixture ... in their own category, first").
PLAYLIST_FIRST = {"up1": r"MOZAIK|FIKSTUR"}
# Groups the owner removed from a playlist (Hydra, 25 October 2026: "remove Yemen, Oman, Qatar and ShowTime").
PLAYLIST_DROP = {"hydra": r"^(YEMEN|OMAN|QATAR|SHOWTIME\b.*)$"}
# Channels that always lead their group (Hydra, 25 October 2026: "Sportsnet and TSN always at the start of the group").
PLAYLIST_CHANNEL_FIRST = {"hydra": r"^(SPORTSNET|TSN)\b"}

# Channels that lead a kind of group, in every playlist, in this order (owner, 27 October 2026):
# Jordan: Jordan TV, Al Mamlaka, Roya; Lebanon: Al Jadeed, Al Mayadeen, Al Manar; Arabic news: Al Jazeera,
# Al Arabiya, Al Araby 1 and 2, Al Mashhad; US news: Fox News, LiveNOW from Fox, NBC, ABC, the weather
# channels, BBC World News; UK news: BBC World News; UK channels: Sky Sports, TNT Sports, MUTV.
_Q = r"(\s+(UHD|FHD|HD|SD|4K|8K|HEVC|RAW|TV))*\s*$"
GROUP_LEADS = [
    (r"JORDAN|ROYA|الأردن|رؤيا", [r"^(JORDAN|الأردن|التلفزيون الأردني)" + _Q, r"MAMLAKA|المملكة", r"^(ROYA|رؤيا)" + _Q]),
    (r"LEBANON|لبنان", [r"JADEED|الجديد", r"MAYADEEN|MAYDEEN|الميادين", r"MANAR|المنار"]),
    (r"^(AR\s*\|\s*)?(ARABIC\s+)?NEWS\b(?!.*NETWORK)|^الأخبار|^اخبار|قنوات الأخبار", [r"JAZEERA(?!.*(ENGLISH|\bEN\b|DOCUMENT|MUBASH|BALKAN|إنجليزي|\b2\b|360))|^الجزيرة$",
                                                       r"MASHHAD|المشهد",  # owner: Al Mashhad right under Al Jazeera
                                                       r"^(AL\s*)?ARABIYA(?!.*BUSINESS)|^العربية", r"^(AL\s*)?ARAB(Y|I)\b(?!.*BUSINESS)|^العربي"]),
    (r"^USA?\b.*NEWS|NEWS NETWORK|^🇺🇲 \| USA$", [r"FOX NEWS", r"\bCNN\b(?!.*(INTERNATIONAL|BRASIL|TURK|ESPAÑOL))", r"LIVE\s?NOW", r"^NBC(\s+NEWS\b.*)?" + _Q, r"^ABC(\s+NEWS\b.*)?" + _Q, r"WEATHER", r"BBC WORLD"]),
    (r"SAUDI ARABIA|السعودية|\bKSA\b", [r"QURAN|القرآن|القران", r"AL\s*AAN|ALAAN|الآن|الان", r"SUNNA|السنة",
                                          r"SAUDI\s*1\b|SAUDI\s*TV\s*1|السعودية\s*(1|الأولى)"]),  # owner, 28 Oct
    # owner, 28 Oct 2026: Egypt starts with these, in this order
    (r"\bEGYPT\b(?!IAN)", [r"(KAHERA|QAHERA)\s*WA(L)?\s*(AL)?\s*NAS(?!.*(\+|PLUS|\b2\b))", r"(KAHERA|QAHERA)\s*WA(L)?\s*(AL)?\s*NAS",
                            r"^AL\s*NAHAR\b(?!.*(DRAMA|LIFE))", r"^AL\s*NAS\b", r"^CBC\b(?!.*(DRAMA|SOFRA|EXTRA))", r"^CBC\s*DRAMA",
                            r"^DMC\b(?!.*DRAMA)", r"^DMC\s*DRAMA", r"^NILE\b", r"^SADA\s*(EL|AL)\s*BA?LA?D"]),
    (r"^UK\b.*NEWS", [r"BBC WORLD"]),
    (r"AUSTRALIA|ᴀᴜꜱᴛʀᴀʟɪᴀ", [r"\bESPN\b", r"\bFOX\b"]),  # owner: ESPN and Fox first in Australia
    # owner, 28 Oct 2026: Canada - Sportsnet first, then TSN
    (r"CANADA\s*-\s*TSN\s*-\s*SN", [r"SPORTSNET\s*(360|EAST|ONE|ONTARIO|PACIFIC|WEST)", r"SPORTSNET", r"^TSN\s*\d|^TSN\b"]),
    # owner, 28 Oct 2026: USA Network first in its package, then TNT, TBS, truTV, LiveNOW from Fox, Fox, Weather
    (r"\bUS\s*ENTERTAINMENT", [r"^(US:?\s*)?USA\s*NETWORK", r"^(US:?\s*)?TNT\b(?!\s*SPORTS?)", r"^(US:?\s*)?TBS\b", r"^(US:?\s*)?TRU\s*TV",
                                 r"LIVE\s*NOW", r"^(US:?\s*)?FOX\b(?!.*(SPORT|NEWS|BUSINESS|SOUL|DEPORTES|SOCCER))", r"WEATHER"]),
    # owner, 28 Oct 2026: Sky Sports, then TNT Sports right after, then MUTV, then the rest
    (r"SKY SPORTS\s*🔺\s*TNT", [r"^(UK:?\s*)?SKY\s*SPORTS?\b", r"^(NOW\s*|D\+\s*|UK:?\s*)?TNT\b", r"\bMUTV\b"]),
    (r"^UK\b|^SPORTS$|^NOW TV$", [r"^(UK:?\s*)?SKY ?SPORTS?\b", r"^(UK:?\s*)?TNT ?SPORTS?\b", r"\bMUTV\b"]),
]


# --- Event / pay-per-view groups (owner, 27 October 2026: "the PPV is all mixed up, order it properly").
# Their channel names carry the event of the day they were exported (stale a day later) and sort badly by name.
# They go in slot-number order (NBA 01, NBA 02...; the names themselves stay the provider's); channels without
# a slot (NFL Network, Sky Box Office, team channels) stay first, in the provider's order.
EVENT_GROUP = re.compile(r"(?!.*24/7)(?:PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\+|TSN\+|SN\+|PEACOCK|PARAMOUNT|^STAN$|^MAX$|^SOCCER$|^DAZN$|CUP GAMES|NFL SPORTS|DAZN EVENTS|ᴘᴘᴠ|ᴇᴠᴇɴᴛ|ᴱᵛᵉⁿᵗ|NBA PASS|\bDAZN\b|\bSTAN\b|\bFLO\b|FLOSPORT)", re.I)
_JUNK = r"[ⓧâ§§ⓧ]+"
_Q = r"(\s*(UHD|FHD|HD|SD|4K|8K|HEVC|RAW|3840P))?"
def event_label(name, group):
    n = re.sub(_JUNK, "", name).strip()
    if n.startswith("24/7"):
        return None
    # "Flo (FLSP) 193: ..."
    m = re.match(r"^[A-Za-z+ ]+?\s*\(([A-Za-z+]+)\)\s*0*(\d{1,4})\b", n)
    if m:
        return m.group(1), int(m.group(2))
    # "... | 8K EXCLUSIVE | US: ESPN+ PPV 12"
    m = re.search(r"\|\s*(?:[A-Z]{2}:\s*)?([A-Z][A-Za-z0-9+&/ .]*?)\s+0*(\d{1,4})\s*$", n)
    if m and "EXCLUSIVE" in n.upper():
        return m.group(1).strip(), int(m.group(2))
    # "US (ESPN+ 001) | ...", "(FLSP 001) | ...", "(US) (BTN+ 001) | ...", "(Apple) (MLS) 001 | ...", "AU (STAN 01) | ..."
    m = re.match(r"^(?:[A-Z]{2}\s*)?(?:\([A-Za-z]+\)\s*)?\(([A-Za-z+ .]+?)\s*0*(\d{1,4})\)", n) or re.match(r"^\([A-Za-z]+\)\s*\(([A-Za-z+ ]+)\)\s*0*(\d{1,4})\b", n)
    if m:
        return m.group(1).strip(), int(m.group(2))
    # "... @ Oct 24 8:30 PM :NBA 06", "... :Paramount+ 01 FHD", "...: USA: SOCCER 4 FHD", "... :Flo College 01"
    m = re.search(r":\s*([A-Za-z][A-Za-z0-9+ .]*?)\s+0*(\d{1,4})" + _Q + r"\s*$", n)
    if m and not re.search(r"\d\s*$", m.group(1)):
        return m.group(1).strip(), int(m.group(2))
    # leading "NFL | 03 - ...", "Live Football 01 : ...", "NCAAF 01: ...", "Boxing 6: ...", "PSF01 | ...", "NBA 01: ..."
    m = re.match(r"^([A-Za-z][A-Za-z+&. ]*?)\s*\|?\s*0*(\d{1,4})\s*(?:[:|\-]|$|\s+[A-Za-z(])", n)
    if m and len(m.group(1)) <= 24:
        return m.group(1).strip(" |"), int(m.group(2))
    # Argon packages: "02 - 9:30am Steelers at Saints FHD" -> group's sport + number
    m = re.match(r"^0*(\d{1,3})\b", n)
    if m:
        base = re.sub(r"\s*(PACKAGE|PPV|EVENTS?|AND INTERNATIONAL)\b.*$", "", group, flags=re.I).strip() or group
        return base.title() if base.isupper() and len(base) > 4 else base, int(m.group(1))
    return None


def event_name(base: str, num: int) -> str:
    return f"{base} {num:02d}"


_SMALLCAPS = str.maketrans("ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡʏᴢѕ", "ABCDEFGHIJKLMNOPQRSTUVWYZS")


def group_lead(group: str, name: str) -> int:
    g, n = group.strip().translate(_SMALLCAPS).upper(), " ".join(name.upper().split())
    g = re.sub(r"^\|?([A-Z]{2,3})\|\s*✪?\s*", r"\1 | ", g)  # Dream4k: "|AR| ✪ ARABIC NEWS"
    n = re.sub(r"^(LBN|LEB|AR|UK|US)\s*\|\s*", "", n)
    for grx, leads in GROUP_LEADS:
        if re.search(grx, g):
            for i, rx in enumerate(leads):
                if re.search(rx, n):
                    return i
            return len(leads)
    return 0


def group_rank(group: str, country: dict | None = None) -> float:
    g = group.upper()
    m = re.match(r"^([A-Z0-9]{2,3})\s*\|", g)
    if country and m and m.group(1) in country:
        if LATE.search(g):
            return 90 + country[m.group(1)] / 100
        return country[m.group(1)] + (0.1 if re.search(r"SPORT|SPOR\b|DESPORTO|TSN|DAZN|ESPN|TNT|SKY SPORT", g) else 0.5)
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
    # a name with no picture word is the plain HD feed
    qrank = min((QUALITY.index(w) for w in q), default=QUALITY.index("HD"))
    return natural(words_only), numbers, qrank, natural(name)


# "in every category, Sky Sports channels first" (25 October 2026), in Sky's own channel order.
SKY_ORDER = ["MAIN EVENT", "PREMIER LEAGUE", "PL", "FOOTBALL", "PLUS", "+", "F1", "CRICKET", "GOLF", "TENNIS", "ACTION",
             "NFL", "ARENA", "MIX", "RACING", "DARTS", "NEWS", "BOX OFFICE"]


def sky_rank(name: str) -> int:
    n = " ".join(name.upper().split())
    m = re.match(r"^(UK:?\s*)?SKY ?SPORTS?\b\s*(.*)$", n)
    if not m:
        return 1000
    rest = m.group(2)
    for i, w in enumerate(SKY_ORDER):
        if rest.startswith(w):
            return i
    return 50


def saved_group_order(playlist: str | None) -> dict:
    """xtream/<playlist>/group_order.json: an order the owner chose ("visible" groups first, in his order)."""
    import json, os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xtream", playlist or "", "group_order.json")
    if not playlist or not os.path.exists(path):
        return {}
    return {g: i for i, g in enumerate(json.load(open(path, encoding="utf-8")).get("visible", []))}


# Playlists copied channel by channel from the owner's own TiviMate: channel_map.json is already in his order
PLAYLIST_EXACT = {"strong"}


def order(chans: list[dict], playlist: str | None = None) -> list[dict]:
    if playlist in PLAYLIST_EXACT:
        return list(chans)
    drop = PLAYLIST_DROP.get(playlist or "")
    if drop:
        chans = [c for c in chans if not re.search(drop, c["group"].strip().upper())]
    lead = PLAYLIST_CHANNEL_FIRST.get(playlist or "")
    lead_rank = lambda n: 0 if lead and re.search(lead, n.strip().upper()) else 1
    # event groups: slot names and slot order
    ev_key = {}
    renamed = []
    for i, c in enumerate(chans):
        if EVENT_GROUP.search(c["group"]):
            lab = event_label(c["name"], c["group"])
            # the owner wants the provider's own names kept (27 Oct): only the ORDER follows the slot numbers
            c = dict(c)
            # owner, 28 Oct 2026: live game slots on top, team channels / NBA TV / others below them
            ev_key[id(c)] = (0, lab[0].upper(), lab[1]) if lab else (1, "", i)
        renamed.append(c)
    chans = renamed
    evk = lambda c: ev_key.get(id(c), (0, "", 0))
    first_seen = {}
    for i, c in enumerate(chans):
        first_seen.setdefault(c["group"], i)
    country = PLAYLIST_COUNTRY.get(playlist or "")
    first = PLAYLIST_FIRST.get(playlist or "")
    saved = saved_group_order(playlist)
    top = lambda g: (0 if first and re.search(first, g.upper()) else 1, saved.get(g, len(saved)))
    # an optional "sort" in channel_map.json puts a group's main channels first (TRT 1, ATV, Show TV...)
    return sorted(chans, key=lambda c: (top(c["group"]), group_rank(c["group"], country), group_quality(c["group"]), first_seen[c["group"]],
                                          evk(c), lead_rank(c["name"]), group_lead(c["group"], c["name"]), sky_rank(c["name"]), c.get("sort", 999), channel_key(c["name"])))
