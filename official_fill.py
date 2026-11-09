#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guides for relay channels that have none yet, from OFFICIAL sources only (owner, 27 October 2026:
"fill the missing guides, if the sources are official").

Only ids this repository already builds from the broadcasters themselves are used:
  o:  official_sports_epg.xml (Sky Sports / TNT via Sky, TSN via Bell, Sportsnet via Rogers)
      official_tv_epg.xml (BBC via iPlayer; Al Arabiya, Al Hadath, MBC, Asharq, MTV Lebanon via Shahid)
  u:  unified_mena_epg.xml channels built from the broadcaster's own site (Al Jazeera, Al Jadeed,
      Jordan TV, Amman TV, Al Mamlaka, Roya, Al Mashhad, LBC, Thmanyah, Shasha, STARZPLAY/AD Sports...)
A channel that already has a guide is never changed. Names are matched by a pattern written for that one
channel (never by fuzzy name likeness), and a few foreign look-alikes are excluded (Sky Italy/Germany/NZ...).
"""
from __future__ import annotations

import re

_Q = r"(\s+(UHD|FHD|HD|SD|LQ|4K|8K|HEVC|RAW|VIP|HDR|TV|60FPS|50FPS|50 FPS|60 FPS|\(.*?\)|/\s*4K))*\s*$"
_FOREIGN = re.compile(r"\b(IT|ITA|ITALIA|ITALY|DE|GER|GERMANY|NZ|MX|BR|AT|CH)\b|ESPA|DEUTSCH", re.I)
_UK_GROUP_BAD = re.compile(r"ITALY|ITALIA|GERMAN|DEUTSCH|SKY SPORTS NZ|HONGKONG|SWITZERLAND|^DE\b|^IT\b|^CH\b|AUSTRALIA|^AU\b", re.I)

_NOT_ARABIC_GROUP = re.compile(r"^(PT|FR|IT|ES|DE|NL|CA|UK|8K|4K)\s*\||PORTUGAL|ITALY|FRANCE|CANADA|SWITZERLAND|NOW TV|^GENERAL$|MUSIC|MUSICA", re.I)
_LEBANON = re.compile(r"LEBANON|^LBN|^LEB|لبنان", re.I)

# (name pattern, epg id, where): "uk" = not in a foreign group, "ar" = not in a non-Arabic country group,
# "lb" = Lebanon only, False = anywhere
RULES: list[tuple[str, str, object]] = [
    # --- Sky Sports / TNT Sports (UK), official Sky listings
    (r"^(UK:?\s*)?SKY ?SPORTS? ?MAIN ?EVENTS?" + _Q, "o:SkySportsMainEvent.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?(PREMIER ?LEAGUE|PL)" + _Q, "o:SkySportsPremierLeague.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?FOOTBALL" + _Q, "o:SkySportsFootball.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?(\+|PLUS)" + _Q, "o:SkySportsPlus.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?CRICKET" + _Q, "o:SkySportsCricket.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?GOLF" + _Q, "o:SkySportsGolf.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?F1" + _Q, "o:SkySportsF1.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?TENNIS" + _Q, "o:SkySportsTennis.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?NEWS" + _Q, "o:SkySportsNews.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?NFL" + _Q, "o:SkySportsNFL.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?RACING" + _Q, "o:SkySportsRacing.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?MIX" + _Q, "o:SkySportsMix.uk", True),
    (r"^(UK:?\s*)?SKY ?SPORTS? ?BOX ?OFFICE" + _Q, "o:SkySportsBoxOffice.uk", True),
    (r"^(UK:?\s*)?TNT ?SPORTS? ?1" + _Q, "o:TNTSports1.uk", True),
    (r"^(UK:?\s*)?TNT ?SPORTS? ?2" + _Q, "o:TNTSports2.uk", True),
    (r"^(UK:?\s*)?TNT ?SPORTS? ?3" + _Q, "o:TNTSports3.uk", True),
    (r"^(UK:?\s*)?TNT ?SPORTS? ?4" + _Q, "o:TNTSports4.uk", True),
    # --- TSN (Bell) / Sportsnet (Rogers)
    (r"^(CA:?\s*)?TSN ?1" + _Q, "o:TSN1.ca", False), (r"^(CA:?\s*)?TSN ?2" + _Q, "o:TSN2.ca", False),
    (r"^(CA:?\s*)?TSN ?3" + _Q, "o:TSN3.ca", False), (r"^(CA:?\s*)?TSN ?4" + _Q, "o:TSN4.ca", False),
    (r"^(CA:?\s*)?TSN ?5" + _Q, "o:TSN5.ca", False),
    (r"^(CA:?\s*)?SPORTSNET ?EAST" + _Q, "o:SportsnetEast.ca", False),
    (r"^(CA:?\s*)?SPORTSNET ?(ONE|1)" + _Q, "o:SportsnetOne.ca", False),
    (r"^(CA:?\s*)?SPORTSNET ?PACIFIC" + _Q, "o:SportsnetPacific.ca", False),
    (r"^(CA:?\s*)?SPORTSNET( ?ONTARIO)?" + _Q, "o:SportsnetOntario.ca", False),
    (r"^(CA:?\s*)?SPORTSNET ?WEST" + _Q, "o:SportsnetWest.ca", False),
    (r"^(CA:?\s*)?SPORTSNET ?360" + _Q, "o:Sportsnet360.ca", False),
    (r"^(CA:?\s*)?SPORTSNET ?WORLD" + _Q, "o:SportsnetWorld.ca", False),
    # --- BBC (iPlayer)
    (r"^(UK:?\s*)?BBC ?(ONE|1)" + _Q, "o:BBCOne.uk", True), (r"^(UK:?\s*)?BBC ?(TWO|2)" + _Q, "o:BBCTwo.uk", True),
    (r"^(UK:?\s*)?BBC ?(THREE|3)" + _Q, "o:BBCThree.uk", True), (r"^(UK:?\s*)?BBC ?(FOUR|4)" + _Q, "o:BBCFour.uk", True),
    (r"^(UK:?\s*)?BBC ?NEWS" + _Q, "o:BBCNews.uk", True), (r"^(UK:?\s*)?BBC ?PARLIA?MENT" + _Q, "o:BBCParliament.uk", True),
    (r"^(UK:?\s*)?BBC ?SCOTLAND" + _Q, "o:BBCScotland.uk", True), (r"^(UK:?\s*)?BBC ?ALBA" + _Q, "o:BBCAlba.uk", True),
    # --- Fox News (owner, 28 Oct 2026: Strong "US: FOX NEWS" had no guide)
    (r"^(US:?\s*|OSN\s*)?FOX\s*NEWS(\s*CHANNEL)?\b(?!.*(WEATHER|RADIO|NOW|TALK|BUSINESS|INTERNATIONAL))", "a:Playlist.US2FoxNewsChannelHDus2", None),
    # --- TNT Sports UK (owner, 28 Oct 2026: Dream4k "NOW TNT SPORTS 1 UHD" had no guide)
    (r"^(NOW\s*|D\+\s*|UK:?\s*)?TNT\s*SPORTS?\s*1" + _Q, "o:TNTSports1.uk", None),
    (r"^(NOW\s*|D\+\s*|UK:?\s*)?TNT\s*SPORTS?\s*2" + _Q, "o:TNTSports2.uk", None),
    (r"^(NOW\s*|D\+\s*|UK:?\s*)?TNT\s*SPORTS?\s*3" + _Q, "o:TNTSports3.uk", None),
    (r"^(NOW\s*|D\+\s*|UK:?\s*)?TNT\s*SPORTS?\s*4" + _Q, "o:TNTSports4.uk", None),
    (r"^(NOW\s*|D\+\s*|UK:?\s*)?TNT\s*SPORTS?\s*(EXTRA\s*)?5" + _Q, "a:Playlist.UK1TNTSports5HDuk", None),
    # --- MBC group, Al Arabiya, Asharq, MTV Lebanon (Shahid)
    (r"^(AL\s*)?ARABIYA" + _Q, "o:Shahid387286.mbc", "ar"),
    (r"^(AL\s*)?ARABIYA\s*(AL\s*)?HADATH" + _Q + r"|^(AL\s*)?HADATH" + _Q, "o:Shahid387288.mbc", "ar"),
    (r"^(AL\s*)?ARABIYA\s*BUSINESS" + _Q, "o:Shahid1003218.mbc", "ar"),
    (r"^ASHARQ\s*(NEWS\s*)?BLOOMBERG" + _Q + r"|^ASHARQ\s*NEWS" + _Q, "o:Shahid862837.mbc", "ar"),
    (r"^MBC\s*(1|ONE)" + _Q, "o:Shahid387238.mbc", "ar"), (r"^MBC\s*2" + _Q, "o:Shahid400917.mbc", "ar"),
    (r"^MBC\s*3" + _Q, "o:Shahid409385.mbc", "ar"), (r"^MBC\s*4" + _Q, "o:Shahid400919.mbc", "ar"),
    (r"^MBC\s*5" + _Q, "o:Shahid387937.mbc", "ar"),
    (r"^MBC\s*ACTION" + _Q, "o:Shahid400921.mbc", "ar"), (r"^MBC\s*MAX" + _Q, "o:Shahid400924.mbc", "ar"),
    (r"^MBC\s*DRAMA" + _Q, "o:Shahid387251.mbc", "ar"),
    (r"^MBC\s*(\+|PLUS)\s*DRAMA" + _Q, "o:Shahid387296.mbc", "ar"),
    (r"^MBC\s*MASR\s*2" + _Q, "o:Shahid387293.mbc", "ar"), (r"^MBC\s*MASR" + _Q, "o:Shahid387290.mbc", "ar"),
    (r"^MBC\s*IRAQ" + _Q, "o:Shahid387294.mbc", "ar"), (r"^MBC\s*BOLLYWOOD" + _Q, "o:Shahid409387.mbc", "ar"),
    (r"^MBC\s*PERSIA" + _Q, "o:Shahid418308.mbc", "ar"),
    (r"^MTV\s*(LEBANON|LB)?" + _Q, "o:Shahid49923518527492.mbc", "lb"),
    # --- broadcasters' own sites (unified guide)
    (r"^(AL\s*)?JAZEERA" + _Q, "u:AlJazeera.qa", "ar"),
    (r"^(AL\s*)?JADEED" + _Q, "u:AlJadeed.lb", "ar"),
    (r"^(JORDAN|الأردن)" + _Q, "u:JordanTV.jo", "ar"),
    (r"^AMMAN" + _Q, "u:AmmanTV.jo", "ar"),
    (r"^(AL\s*)?MAMLAKA" + _Q, "u:AlMamlaka.jo", "ar"),
    (r"^ROYA" + _Q, "u:Roya_RoyaTV", "ar"), (r"^ROYA\s*NEWS" + _Q, "u:Roya_RoyaNews", "ar"),
    (r"^ROYA\s*COMEDY" + _Q, "u:Roya_RoyaComedy", "ar"), (r"^ROYA\s*KITCHEN" + _Q, "u:Roya_RoyaKitchen", "ar"),
    (r"^ROYA\s*KIDS" + _Q, "u:Roya_RoyaKids", "ar"),
    (r"^(AL\s*)?MASHHAD" + _Q, "u:AlMashhad.ae", "ar"),
    (r"^LBC\s*SAT" + _Q, "u:LBCSat.lb", "ar"),
    (r"^THMANYAH\s*1" + _Q, "u:Thmanyah1.sa", "ar"), (r"^THMANYAH\s*2" + _Q, "u:Thmanyah2.sa", "ar"),
    (r"^THMANYAH\s*3" + _Q, "u:Thmanyah3.sa", "ar"),
    (r"^SHASHA\s*(SPORTS?\s*)?1" + _Q, "u:ShashaSport1", "ar"), (r"^SHASHA\s*(SPORTS?\s*)?2" + _Q, "u:ShashaSport2", "ar"),
    (r"^SHASHA\s*(SPORTS?\s*)?3" + _Q, "u:ShashaSport3", "ar"),
    (r"^(ABU\s*DHABI|AD)\s*SPORTS?\s*1" + _Q, "u:Starz_admnadsports1", "ar"),
    (r"^(ABU\s*DHABI|AD)\s*SPORTS?\s*2" + _Q, "u:Starz_admnadsports2", "ar"),
    (r"^(ABU\s*DHABI\s*TV|ABU\s*DHABI)" + _Q, "u:AbuDhabiTV.ae", "ar"),
    (r"^(ABU\s*DHABI\s*)?(AL\s*)?EMARAT" + _Q, "u:AlEmaratTV.ae", "ar"),
    (r"^SHARJAH" + _Q, "u:SharjahTV.ae", "ar"),
    (r"^DUBAI" + _Q, "u:DubaiTV.ae", "ar"),
    (r"^SAUDI\s*(1|ONE|TV)" + _Q, "u:Saudi1.sa", "ar"),
    (r"^STARZ\s*PLAY\s*SPORTS?\s*1" + _Q, "u:Starz_starzplaysports1", "ar"),
    (r"^STARZ\s*PLAY\s*SPORTS?\s*2" + _Q, "u:Starz_starzplaysports2", "ar"),
]
_COMPILED = [(re.compile(rx, re.I), epg, where) for rx, epg, where in RULES]


def clean(name: str) -> str:
    n = " ".join(str(name).split())
    n = re.sub(r"^(LBN|LEB|AR|UK|US|CA|BE|STC|TOD)\s*\|\s*", "", n, flags=re.I)
    return n.strip()


def fill(name: str, group: str) -> str | None:
    """An official guide id for a channel that has none, or None."""
    n = clean(name)
    if _FOREIGN.search(n):
        return None
    g = group or ""
    for rx, epg, where in _COMPILED:
        if rx.search(n):
            if where is True and _UK_GROUP_BAD.search(g):
                return None
            if where == "ar" and _NOT_ARABIC_GROUP.search(g):
                return None
            if where == "lb" and not (_LEBANON.search(g) or _LEBANON.search(n)):
                return None
            return epg
    return None


# Roya's own sub-channels (roya.tv guide, unified ids). These win over a channel_map guide: providers
# label e.g. "Roya 911" with the main Roya TV guide (owner, 28 Oct 2026: "Roya SPORTS" had no guide).
_ROYA_SUB = [(re.compile(rx, re.I), epg) for rx, epg in [
    (r"SPORTS?|رياض", "u:Roya_RoyaSport"),
    (r"DO[CU]+ME?NT|وثائق", "u:Roya_Documentaries"),
    (r"PAL[AE]ST|فلسطين", "u:Roya_Ch38"),
    (r"PRODUCTION|إنتاجات|انتاجات", "u:Roya_Ch40"),
    (r"CARAVAN|كرفان", "u:Roya_Ch41"),
    (r"SIT\s*AL\s*N?KHAT|NAKHAT|النكهات", "u:Roya_Ch13"),
    (r"CHE?IE?F\s*MANN?|شيف مان", "u:Roya_Ch8"),
    (r"ADVENTURE|مغامرات", "u:Roya_Ch26"),
    (r"AROUND\s*THE\s*WORLD|حول العالم", "u:Roya_Ch37"),
    (r"WORLD\s*BEAUTIFUL|حلوة يا دنيا", "u:Roya_Ch30"),
    (r"BIG\s*WORLDS?|العالم الكبير", "u:Roya_Ch28"),
    (r"911|٩١١", "u:Roya_Ch31"),
    (r"GALTA|جلطة", "u:Roya_Ch9"),
    (r"WATAN\s*(ALA|A)?\s*WATAR|وطن ع", "u:Roya_Ch10"),
    (r"STORIES|القصة", "u:Roya_Ch33"),
    (r"VARIOUS|منوّع|منوع", "u:Roya_Ch36"),
    (r"SOCIAL|مجتمعي", "u:Roya_Ch22"),
]]


def override(name: str) -> str | None:
    n = clean(name)
    m = re.match(r"^\s*(?:VIP\s+)?(?:ROYA|رؤيا)\s+(.+)$", n, re.I)
    if not m or re.search(r"KIDS", m.group(1), re.I):  # Roya Kids Songs / Stories are not on roya.tv
        return None
    for rx, epg in _ROYA_SUB:
        if rx.search(m.group(1)):
            return epg
    return None
