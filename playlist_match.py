#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Name matching for a playlist that brings no guide of its own.

The owner's second playlist answers xmltv.php with nothing, and the epg
ids it files its channels under are often another channel's ("Al Jazeera
4K" under Orient TV's, "BBC World News" under BBC Four's). So nothing
here trusts those ids. A channel is matched by its NAME, and only:

  * exactly — the same words once quality tags (HD, FHD, 4K...) are set
    aside; "+1" stays a word of its own, a timeshift is not its channel;
  * inside its own country — a Portuguese category takes Portuguese ids
    only, so "Pt: Discovery 4K" can never take the American Discovery;
  * from a source the owner trusts: this repository's own guides first,
    then epgshare01's country files, then the owner's own links.

A channel none of those name exactly is left to the 24/7 rows below or
to nothing: an empty row is better than another channel's programmes.
"""

from __future__ import annotations

import re
import unicodedata

DROP = {"hd", "fhd", "sd", "uhd", "4k", "8k", "hdr", "low", "raw", "backup",
        "hevc", "h265"}
NUMBERS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
           "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


def norm(name: str | None) -> str:
    """'Fr: Canal + Action HD' -> 'canal plus action'; 'UK: E4 +1' -> 'e 4 plus 1'."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"^\s*spt-vip\s*\|\s*", "", s)
    s = re.sub(r"^\s*([a-z]{2,6}(?:-[a-z]{2,4})?(?:\s*\|\s*[a-z]{2,4})?)\s*[:|]\s*", "", s)
    # iptv-epg.org writes the country with a dash: "FR - Ligue 1+".
    s = re.sub(r"^\s*[a-z]{2}\s+-\s+", "", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)          # "[ Live ]", "[ Match Time ]"
    s = re.sub(r"\bhd\s*\+", " hd ", s)
    s = re.sub(r"\+\s*(\d)\b", r" plus\1 ", s)
    s = s.replace("+", " plus ")
    s = re.sub(r"\s+new\s*$", "", s)
    words = [t for t in re.split(r"[^a-z0-9؀-ۿ]+", s) if t and t not in DROP]
    # "SPORT TV1" is "Sport TV 1", "ESPN2" is "ESPN 2" — split only once
    # the quality tags (4k, h265) are gone, so those are dropped, not split.
    words = [p for t in words for p in re.split(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", t)]
    return " ".join(NUMBERS.get(t, t) for t in words if t not in DROP)


def suffix(cid: str) -> str:
    return cid.rsplit(".", 1)[-1].lower() if "." in cid else ""


# This repository's own channels under a second name the playlist uses —
# each checked by hand against the broadcaster: MBC Masr 1 is MBC Masr,
# Wanasah is MBC's, Dubai Sports is the channel the playlist calls Sport.
OWN_ALIASES = {
    "mbc masr 1": "mbc masr", "mbc wanasah": "wanasah",
    "dubai sport 1": "dubai sports 1", "dubai sport 2": "dubai sports 2",
    "dubai racing 1": "dubai racing", "roya": "roya tv",
    "spacetoon tv": "spacetoon", "abu dhabi al emarat": "al emarat",
    # Thmanyah's sport channels, which the playlist spells "Thamanya".
    "thamanya 1 sport": "thmanyah 1", "thamanya 2 sport": "thmanyah 2",
    "thamanya 3 sport": "thmanyah 3",
}


def own_index(root) -> dict[str, set[str]]:
    """norm(name) -> ids, over every display-name of this repository's guide
    (and each half of a 'Jordan Sport | الأردنية الرياضية' name)."""
    index: dict[str, set[str]] = {}
    for ch in root.findall("channel"):
        cid = ch.get("id") or ""
        if cid.startswith(("Playlist.", "Placeholder.", "RoyaPH")):
            continue
        for d in ch.findall("display-name"):
            text = d.text or ""
            for part in {text, *re.split(r"\s+[|/]\s+", text)}:
                key = norm(part)
                if key:
                    index.setdefault(key, set()).add(cid)
    return index


def own_target(index, category: str, name: str) -> str | None:
    """The one channel of ours this playlist name is, or None."""
    # Ours are the Arab world's feeds (and beIN's Turkish ones): a UK, French
    # or American category's Nat Geo or beIN is that country's own feed.
    turkish = category.strip().lower().startswith("turkish")
    if route(category, name) not in (ARAB, ARAB_WIDE) and not turkish:
        return None
    key = norm(name)
    keys = [key, OWN_ALIASES.get(key, key)]
    if category.strip().lower().startswith("shahid"):
        keys.append(re.sub(r"^shahid\s+", "", key))
    for k in keys:
        ids = {i for i in index.get(k, ()) if (suffix(i) == "tr") == turkish}
        # Name variants of one feed (Alwan2_sport, _hd, _4k) are one channel.
        if ids and len({re.sub(r"_(hd|sd|4k|raw)$", "", i) for i in ids}) == 1:
            return min(ids, key=len)
    return None


# A source's own spelling of a channel the playlist names otherwise.
SOURCE_ALIASES = {"sky news arabic": "sky news arabia", "sky stv": "stv",
                  "sky cinema premier": "sky cinema premiere"}


def source_key(name: str) -> str:
    key = norm(name)
    return SOURCE_ALIASES.get(key, key)


# Category -> (sources in order, the country ids it may take).
ARAB = (["AE1", "SA2", "BEIN1", "ALJAZEERA1"],
        {"ae", "sa", "qa", "eg", "lb", "jo", "kw", "iq", "sy", "bh", "om"})
ROUTES = [
    (r"^UK \| India", (["IN1", "IN2", "UK1", "ferteque", "iptvepg"], {"in", "uk"})),
    # Not Ireland's file: its "BBC 1" is BBC One Northern Ireland.
    (r"^UK\b", (["UK1", "ferteque", "iptvepg"], {"uk"})),
    (r"^France", (["FR1", "ferteque", "iptvepg"], {"fr"})),
    (r"^Portugal", (["PT1", "ferteque", "iptvepg"], {"pt"})),
    (r"^Turkish", (["TR3", "TR1", "ferteque", "iptvepg"], {"tr"})),
    (r"^USA", (["US2", "US_SPORTS1", "ferteque", "iptvepg"], {"us", "us2"})),
]
# The Arab world's own channels — news, faith, sport, MBC — broadcast one
# feed everywhere: the owner's two links file Al Araby, Iqraa, DW English or
# Arryadia under whichever country they were picked up in (.us, .fr, .uk).
# By exact name only; not the documentary shelf, whose Arabic Discovery or
# DMAX is not the American or British channel of the same name.
ARAB_WIDE = (ARAB[0] + ["ferteque", "iptvepg"],
             ARAB[1] | {"us", "us2", "uk", "fr", "ca", "de", "nl", "tr", "it", "es"})
ARAB_WIDE_CATEGORY = re.compile(r"^(News|Islamic|Arabic Sports|MBC\b)", re.I)
SPORT_PREFIX = {"de": (["DE1"], {"de"}), "es": (["ES1"], {"es"}),
                "it": (["IT1"], {"it"}), "nl": (["NL1"], {"nl"}),
                "uk": (["UK1"], {"uk"}), "fr": (["FR1"], {"fr"}),
                "us": (["US2", "US_SPORTS1"], {"us", "us2"}),
                "usa": (["US2", "US_SPORTS1"], {"us", "us2"}),
                "in": (["IN1", "IN2"], {"in"}),
                "pt": (["PT1"], {"pt"}), "tr": (["TR3", "TR1"], {"tr"})}
# The order the sources are read in, smallest and most exact first.
SOURCE_ORDER = ["AE1", "SA2", "BEIN1", "ALJAZEERA1", "UK1", "FR1", "PT1",
                "TR3", "TR1", "US2", "US_SPORTS1", "DE1", "ES1", "IT1", "NL1",
                "IN1", "IN2", "ferteque", "iptvepg"]


def route(category: str, name: str) -> tuple[list[str], set[str]]:
    category = category.strip()
    for pattern, answer in ROUTES:
        if re.search(pattern, category):
            return answer
    if re.match(r"Real 4K", category, re.I):
        # A mixed shelf — UK, French, Italian, Spanish 4K feeds side by side:
        # every country's files, by exact name only.
        # Not Italy's: its "Sky Sport F1" would take the UK's "Sky Sports F1 4K".
        return (["UK1", "FR1", "DE1", "ES1", "US2", "PT1", "TR3", "ferteque",
                 "iptvepg"], {"uk", "fr", "de", "es", "us", "us2", "pt", "tr"})
    if category.startswith("International Sports"):
        m = re.match(r"\s*spt-vip\s*\|\s*([a-z]{2,3})\s*:", name, re.I)
        if m and m.group(1).lower() in SPORT_PREFIX:
            sources, countries = SPORT_PREFIX[m.group(1).lower()]
            return sources + ["ferteque", "iptvepg"], countries
        return [], set()
    if ARAB_WIDE_CATEGORY.match(category):
        return ARAB_WIDE
    return ARAB


def west(text: str) -> bool:
    """A West Coast copy runs three hours behind its East one."""
    return bool(re.search(r"west(?!ern)|pacific", text, re.I))


def source_names(names) -> set[str]:
    """A source's names as keys, also without a bracketed call sign or
    region: "CBS HARTFORD (WFSB)" is the playlist's "CBS Hartford"."""
    keys = set()
    for n in names:
        keys.add(norm(n))
        bare = re.sub(r"\([^)]*\)", " ", n)
        # Only a call sign in the bracket ("France 24 (I)" is not France 24),
        # and not when the bracket was the name ("CBS (New York)").
        inside = " ".join(re.findall(r"\(([^)]*)\)", n))
        if bare != n and _signs(inside) and not west(n) and len(norm(bare).split()) >= 2:
            keys.add(norm(bare))
    return {k for k in keys if k}


def usable(cid: str) -> bool:
    return bool(cid) and not cid.lower().startswith(("dummy", "plex."))


# --- channels that play one thing round the clock --------------------------

ISLAMIC = re.compile(r"^\s*Islamic\s*$", re.I)
QURAN = re.compile(r"quran|qur'an|قرآن|القرآن|القران|قران|surah|sorah|surat|"
                   r"tilawa|baqa?b?ara|kahi?f|afas[iy]|العفاس|سديس|sudais|"
                   r"معيقلي|mueaqly|منشاوي|عبدالباسط|sawt", re.I)
# A Quran channel outside the Islamic category ("Sa| Saudia Quran HD").
QURAN_CHANNEL = re.compile(r"\bquran\b|قرآن|القرآن|القران", re.I)
AZKAR = re.compile(r"az[a]?kar|أذكار|اذكار", re.I)
SUNNAH = re.compile(r"sunnah|hadi?th|hadeeth|nabaw|نبوي", re.I)
LOOP = re.compile(r"^\s*(Shoof Max|Netflix Movies|Shahid Ramadan.*|Shahid TV)\s*$", re.I)


def islamic(name: str) -> tuple[str, str] | None:
    """(title, kind) for a channel of the Islamic category, or None for a
    general station (Iqraa, Resala...) whose programmes are its own."""
    text = re.sub(r"^\s*(Islam|Quran)\s*:\s*", "", name, flags=re.I)
    if AZKAR.search(name):
        return "أذكار الصباح", "azkar"
    if SUNNAH.search(name):
        return "السنة النبوية", "sunnah"
    general = re.match(r"^\s*Islam\s*:", name, re.I) and not QURAN.search(text)
    if general:
        return None
    return "القرآن الكريم", "quran"


def reciter(name: str) -> str:
    """'Quran: محمد صديق المنشاوي' -> 'محمد صديق المنشاوي'."""
    text = re.sub(r"^\s*(Islam|Quran)\s*:\s*", "", name, flags=re.I)
    return re.sub(r"\s+(HD|FHD|SD|4K|New)\s*$", "", text, flags=re.I).strip()


def loop_subject(name: str) -> str:
    """'ShoofMax- قابل للكسر New' -> 'قابل للكسر'; 'Netflix Action New HD1' -> 'Netflix Action 1'."""
    text = re.sub(r"^\s*Shoof\s*(Max|Drama)\s*-\s*", "", name, flags=re.I)
    text = re.sub(r"\bNew\b", " ", text, flags=re.I)
    text = re.sub(r"\bHD(\d+)\b", r"\1", text, flags=re.I)        # "HD3" -> "3"
    text = re.sub(r"\b(HD|FHD|SD|4K|UHD)\b\+?", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def shown_name(name: str) -> str:
    """'Sy| Lana TV HD' -> 'Lana TV'; 'News | Ar: Al Mayadeen TV' -> 'Al Mayadeen TV'."""
    text = re.sub(r"^\s*spt-vip\s*\|\s*", "", name, flags=re.I)
    text = re.sub(r"^\s*[^\W\d_]{2,6}(?:-[^\W\d_]{2,6})?(?:\s*\|\s*[^\W\d_]{2,4})?\s*[:|]\s*",
                  "", text)
    text = re.sub(r"\[\s*live\s*\]", " ", text, flags=re.I)
    text = re.sub(r"\b(HD|FHD|SD|4K|8K|UHD|HDR|Low|Backup)\b\+?", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" -|") or name.strip()


QUALITY = re.compile(r"(?:\s*\b(?:HD|FHD|SD|UHD|4K|8K|HDR|HEVC|Backup)\b\+?|\s*\[\s*live\s*\])+\s*$",
                     re.I)
PREFIX = re.compile(r"^\s*(?:spt-vip\s*\|\s*)?(?:[^\W\d_]{2,6}(?:-[^\W\d_]{2,6})?"
                    r"(?:\s*\|\s*[^\W\d_]{2,4})?\s*[:|]\s*)?")


def name_variants(name: str) -> list[str]:
    """The forms a player may list the same channel under. The owner's
    device shows "ABC 7 (WABC) New York" and "Fox News" where the account
    the guide reads says "USA: ABC 7 (WABC) New York" and "Usa: Fox News
    HD" (5 October 2026): with and without the country prefix, with and
    without the quality tag."""
    base = name.strip()
    bare = QUALITY.sub("", base).strip()
    out = [base, bare, PREFIX.sub("", base, count=1).strip(), PREFIX.sub("", bare, count=1).strip()]
    return [v for v in dict.fromkeys(out) if v]


def id_stem(epg_id: str) -> str:
    """'bbc1.uk' -> 'bbc1' — the channel an id is named after, squeezed."""
    return re.sub(r"[^a-z0-9]", "", (epg_id or "").rsplit(".", 1)[0].lower())


def squeezed(name: str) -> str:
    return norm(name).replace(" ", "")


# --- real logos ---------------------------------------------------------------

# iptv-org's open channel database (iptv-org.github.io/api): 31,000 channels,
# each with its country and its own logo. A channel no source gives a logo
# takes the one iptv-org files under the same name in the same country.
IPTV_ORG = ("https://iptv-org.github.io/api/channels.json",
            "https://iptv-org.github.io/api/logos.json")
ARAB_COUNTRIES = {"ae", "sa", "qa", "eg", "lb", "jo", "kw", "iq", "sy", "bh", "om",
                  "ps", "ye", "ly", "ma", "dz", "tn", "sd"}
COUNTRY_OF_SUFFIX = {"uk": "gb", "us2": "us"}


def logo_key(name: str) -> str:
    """norm() without the words a logo's name may or may not carry."""
    return " ".join(t for t in norm(name).split()
                    if t not in ("tv", "channel", "television", "network"))


def logo_index(channels: list, logos: list) -> dict:
    first: dict[str, str] = {}
    for logo in logos:
        if logo.get("feed") is None and logo.get("channel") and logo.get("url"):
            first.setdefault(logo["channel"], logo["url"])
    index: dict[tuple, str] = {}
    for ch in channels:
        url = first.get(ch.get("id"))
        if not url:
            continue
        for name in [ch.get("name") or ""] + list(ch.get("alt_names") or []):
            key = logo_key(name)
            if key:
                index.setdefault(((ch.get("country") or "").lower(), key), url)
    return index


def real_logo(index: dict, category: str, name: str) -> str | None:
    if not index:
        return None
    _sources, countries = route(category, name)
    wanted = {COUNTRY_OF_SUFFIX.get(c, c) for c in countries}
    if countries is ARAB[1] or wanted & ARAB_COUNTRIES:
        wanted |= ARAB_COUNTRIES
    key = logo_key(name)
    for country in sorted(wanted):
        url = index.get((country, key))
        if url:
            return url
    return None




CALL_SIGN = re.compile(r"([kw][a-z]{2,3})(?:dt|ld)?")
NOT_SIGNS = {"world", "west", "wild", "kids", "king", "week", "work", "wine", "wolf", "word",
             "wave", "wake", "wall", "war", "way", "web", "wet", "win", "wow", "key",
             "kid", "kim", "kia", "keep", "kiss", "know", "wise", "with", "will", "well",
             "what", "when", "warm", "wire", "wood", "kong", "kino", "kika", "korn"}
FILLER = {"tv", "hd", "channel", "the", "us", "uk", "east", "network", "television",
          "entertainment", "latino", "dt", "raw", "uhd", "fhd", "sd", "hdr", "and"}


def _tokens(name: str) -> set[str]:
    return set(norm(re.sub(r"[ᴬ-ᶻ]+|\[[^\]]*\]", " ", name)).split()) - FILLER


def _signs(name: str) -> set[str]:
    """An American station's call sign, "WFSB" in "CBS HARTFORD (WFSB)"."""
    out = set()
    for word in norm(name).split():
        m = CALL_SIGN.fullmatch(word)
        if m and word not in NOT_SIGNS and m.group(1) not in NOT_SIGNS:
            out.add(m.group(1))
    return out


def _squeeze(name: str) -> str:
    """A name without spaces, quality marks or filler words, nor a trailing "tv"."""
    toks = [t for t in norm(re.sub(r"[ᴬ-ᶻ]+|\[[^\]]*\]", " ", name)).split() if t not in FILLER]
    return re.sub(r"tv$", "", "".join(toks))


def trusted_names(names) -> list[str]:
    """The names of one source id that are that channel. ferteque files a
    channel's own name first, then names gathered from playlists, and some
    of those are other channels — "Dw News", "Gb News" and "Rt News" under
    "News"; "Cbs Salt Lake City (kutv)" under "ABC Salt Lake City"; "Al
    Araby 2" under "Al Araby TV". A later name counts only when it agrees
    with the first: the same call sign, or the same words and numbers with
    only quality marks or a city added."""
    names = [n for n in names if n and n.strip()]
    if not names:
        return []
    first = names[0]
    head = _tokens(first)
    signs = _signs(first)
    digits = sorted(re.findall(r"\d+", norm(first)))
    out = [first]
    same = _squeeze(first)
    for n in names[1:]:
        toks = _tokens(n)
        if same and _squeeze(n) == same:
            out.append(n)              # "Cinemax East", "Teennick", "Outside Tv"
        elif signs & _signs(n):
            out.append(n)
        elif toks and len(head) >= 2 and head <= toks and \
                sorted(re.findall(r"\d+", norm(n))) == digits:
            out.append(n)
        elif toks and toks <= head and len(toks) >= 2 and \
                sorted(re.findall(r"\d+", norm(n))) == digits:
            out.append(n)
    # A station's network and city alone ("CBS (Denver)") when a name that
    # carries its call sign says the same ("CBS 4 (kcnc) Denver").
    signed = [_tokens(n) for n in out if signs & _signs(n)]
    for n in names[1:]:
        toks = _tokens(n)
        if n not in out and len(toks) >= 2 and not re.search(r"\d", norm(n)) and \
                any(toks <= t for t in signed):
            out.append(n)
    return out
