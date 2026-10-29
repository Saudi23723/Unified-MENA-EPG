#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Channel logos for the relays (owner, 27 October 2026: "why is there no logo on any channel ... do it without me",
then "try your hardest so as few channels as possible are left without a logo").

Order of preference for one channel:
  0. hand-checked rules that must win (Lebanese "One" is not OSN One, MTV in Lebanon is MTV Lebanon)
  1. the logo of its own guide id (unified_mena_epg.xml for u:, att_epg.xml.gz for a:)
  2. the same name in this repo's guides (every *.xml here, then the AT&T guide, same country first)
     and in this repo's logos/ folder (file names)
  3. the public tv-logo/tv-logos collection (tv_logos_index.json), same country first, then international
  4. the same with the name's tail dropped ("BBC One London" -> "BBC One", "MBC 1 USA" -> "MBC 1"; never a number)
  5. brand rules (Roya ..., Jr ..., Alfajer N, US local NBC/CBS/ABC/FOX stations -> the network)
  6. (fill_playlist) another channel of the same playlist with the same name core ("MBC Family 4K" <- "MBC Family")
  7. (fill_playlist) the group's own brand when it is one ("AR | SHAHID VIP 4K" -> Shahid, "US | ESPN+ PPV" -> ESPN+)
Logos from steps 4, 5 and 7, and every logo in an event group, end in "#weak": the worker swaps those for the
provider's own logo when the provider has one, and fills whatever is still empty the same way.
Names are never changed here; they are only compared.
"""
from __future__ import annotations

import collections
import glob
import gzip
import html
import json
import os
import re

_Q = r"\b(UHD|FHD|HD|SD|LQ|4K|8K|HEVC|H265|RAW|3840P|1080P|720P|60FPS|50FPS|HDR|ULTRA|VIP|TV|CHANNEL|BACKUP|BK|ME|SAT|LIVE)\b"
_SUP = str.maketrans({"ᴿ": "", "ᴬ": "", "ᵂ": "", "ʰ": "", "ᵉ": "", "ᵛ": "", "ᶜ": "", "ᴴ": "", "ᴰ": "", "ⓧ": "", "§": "",
                      "ᵁ": "", "ᴷ": "", "ˢ": "", "ᴳ": ""})
HERE = os.path.dirname(os.path.abspath(__file__))
_IDX = {}
try:
    _IDX = json.load(open(os.path.join(HERE, "tv_logos_index.json"), encoding="utf-8"))
except (OSError, ValueError):
    pass
TVLOGOS = _IDX.get("base", "")  # picture links only; nothing is downloaded at build time
REPO = _IDX.get("repo_base", "")
LB = TVLOGOS + "countries/lebanon/"
US = TVLOGOS + "countries/united-states/"

ARAB = {"ae", "sa", "eg", "qa", "kw", "lb", "jo", "ps", "iq", "ma", "dz", "tn", "ly", "sy", "om", "bh", "ye", "sd", "mr"}
CC = {"us": "US", "uk": "UK", "gb": "UK", "ie": "UK", "ca": "CA", "tr": "TR", "it": "IT", "fr": "FR", "pt": "PT",
      "au": "AU", "ch": "CH", "de": "DE", "es": "ES"}

# (group regex or None, name regex, logo). "" = leave it to the provider. Checked before everything else.
FIRST = [
    # US networks: the collection's colour logos (the guide's ones are dark / odd on DreamTV; owner, 28 Oct 2026)
    (r"US|ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ|ENTERTAINMENT", r"^(US:?\s*)?TNT\b(?!.*(SPORT|BOX|ULTIMATE|2M|AL\s|ARRIADIA|MEDI|TAMAZIGHT|ALMAGHRIB|ASSADISSA))", TVLOGOS + "countries/united-states/tnt-us.png"),
    (r"US|ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ|ENTERTAINMENT", r"^(US:?\s*)?TRU\s*TV\b", TVLOGOS + "countries/united-states/tru-tv-us.png"),
    (r"US|ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ|ENTERTAINMENT", r"^(US:?\s*)?TBS\b", TVLOGOS + "countries/united-states/tbs-us.png"),
    (r"US|ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ|ENTERTAINMENT", r"^(US:?\s*)?FOX\s*WEATHER", TVLOGOS + "countries/united-states/fox-weather-us.png"),
    (r"US|ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ|ENTERTAINMENT", r"^(US:?\s*)?(THE\s*)?WEATHER\s*CHANNEL", TVLOGOS + "countries/united-states/weather-channel-us.png"),
    (r"US|ᴇɴᴛᴇʀᴛᴀɪɴᴍᴇɴᴛ|ENTERTAINMENT", r"LIVE\s*NOW", TVLOGOS + "countries/united-states/live-now-fox-us.png"),
    (r"LEBANON|^LB", r"^((LBN|LEB)\s*\|\s*)?ONE\b", ""),
    (r"LEBANON|^LB", r"\bMTV\b", LB + "mtv-lebanon-lb.png"),
    (None, r"^(LBN|LEB)\s*\|\s*MTV\b", LB + "mtv-lebanon-lb.png"),
    # owner's photos, 27 Oct 2026
    (None, r"FAJE?R", "https://i.imgur.com/1xERxmB.png"),
    (None, r"^((AR|[A-Z0-9]{1,4})\s*:\s*)?(AL\s*)?ARABY\s*2\b", "https://i.imgur.com/YMqWEe4.png"),
    (None, r"\bSOLO\b", "REPO:solo_sports.png"),
    (r"SHOOF\s*(ᴍᴀx|MAX)", r".", "REPO:shoofmax.png"),
    (r"FORMULA\s*1", r".", "REPO:f1.png"),
    (None, r"^F1\s*:", "REPO:f1.png"),
    (None, r"(ROYA|رؤيا)\s*(كوميدي|COMEDY)", "https://img.roya.tv/imagechanger/Size01Q40R927/storage/app/public/images/channels/GACtHgmN6t9X6RO.png"),
    (None, r"(ROYA|رؤيا)\s*(الوثائقية|DOCUMENTAR)", "https://img.roya.tv/imagechanger/Size01Q40R927/storage/app/public/images/channels/O3Ghqm99JvIWQe7.png"),
    (None, r"(ROYA|رؤيا)\s*(KITCHEN|مطبخ)", "REPO:roya_kitchen.png"),
    (None, r"(ROYA|رؤيا)\s*(KIDS|أطفال|اطفال)", "REPO:roya_kids.png"),
    (None, r"(ROYA|رؤيا)\s*(NEWS|الإخبارية|الاخبارية)", "REPO:roya_news.png"),
    (None, r"ROYA|رؤيا", "https://img.roya.tv/imagechanger/Size01Q40R927/storage/app/public/images/channels/iMoPuU3u5qnqMsL.png"),
]
# Brand rules, used when nothing more exact was found.
BRANDS = [
    # brand logos for numbered event / extra channels (owner, 28 Oct 2026: groups without logos)
    (None, r"SKY\s*SPORTS?\s*(\+|PLUS)|SKY\s*SPORT\+", TVLOGOS + "countries/united-kingdom/sky-sports-plus-icon-uk.png"),
    (None, r"^(UK\s*[:|]?\s*)?SKY\s*SPORTS?\s*(UK\s*)?\d+\b", TVLOGOS + "countries/united-kingdom/sky-sports-icon-uk.png"),
    (None, r"SKY\s*(BOX\s*OFFICE)", TVLOGOS + "countries/united-kingdom/sky-sports-box-office-uk.png"),
    (None, r"^(UK:?\s*)?SKY\s*(MOVIES|CINEMA)", TVLOGOS + "countries/united-kingdom/sky-cinema-uk.png"),
    (None, r"^(UK:?\s*)?SKY\s*MIX", TVLOGOS + "countries/united-kingdom/sky-mix-uk.png"),
    (None, r"NETFLIX", TVLOGOS + "countries/international/netflix-int.png"),
    (None, r"^HUB\s*(PREMIER|SPORTS?)", "gen/football.png"),
    (None, r"^DAZN\b|\bDAZN\s*(EVENT|\d)", TVLOGOS + "countries/international/dazn-int.png"),
    (None, r"FAJE?R\b|FAJR\b", "fajer.png"),
    (None, r"KOFIYA|KUFIYA", "alkofiya.png"),
    (None, r"QUDS\s*(AL)?\s*(TODAY|ALYAWM|AL YAWM)", "alquds_today.png"),
    (None, r"PALESTINE\s*SPORT|FALASTIN\w*\s*SPORT", "palestine_sport.png"),
    (None, r"PALESTINE\s*(MUBASHER|MUBASHIR|LIVE)", "palestine_mubashir.png"),
    (None, r"PALESTINE\s*(AL)?\s*YAWM|PALESTINE TODAY", "palestine_alyawm.png"),
    (None, r"^(\w+\s*[|:]\s*)?(PALESTINE|FALASTIN\w*)\b", "palestine_tv.png"),
    (None, r"FATAFEAT|FATAFIT", "fatafeat_v2.png"),
    (None, r"BARA[EI]+M", "bein_ent_baraem.png"),
    (None, r"\bJEEM\b", "bein_ent_jeem.png"),
    (None, r"ROYA\s*NEWS", "roya_news.png"),
    (None, r"ROYA\s*KIDS", "roya_kids.png"),
    (None, r"ROYA\s*KITCHEN", "roya_kitchen.png"),
    (None, r"ROYA\s*COMEDY", "roya_comedy.png"),
    (None, r"^(\w+\s*[|:]\s*)?ROYA\b", "roya_tv.png"),
    (None, r"^(\w+\s*[|:]\s*)?JORDAN\s*SPORT", "jordan_sport.png"),
    (r"JORDAN|^JO\b", r"^JR\b", "jordan_tv.png"),
    (None, r"\bMAMLAKA\b", "al_mamlaka.png"),
    (None, r"\bLBC\b", LB + "lbc-international-lb.png"),
    (None, r"TELE\s*LUMIERE|NOURSAT", LB + "tele-lumiere-lb.png"),
    (None, r"FUTURE\s*TV", LB + "future-tv-lb.png"),
    (None, r"JAZEERA", "aljazeera.png"),
    (None, r"\bALKASS\b|\bAL KASS\b", "alkass1.png"),
    (None, r"\bSHAHID\b", "shahid.png"),
    (None, r"\bSHASHA\b", "shasha.png"),
    (None, r"\bTHMANYAH\b|ثمانية", "thmanyah1.png"),
    (None, r"\bTABII\b", "tabii.png"),
    (None, r"\bTIVIBU\b", "tivibu_spor.png"),
    (None, r"\bON\s*SPORT", "onsport1.png"),
    (None, r"\bALWAN\b", "alwan.png"),
    (None, r"\bOSN\b", "osn_one_v5.png"),
    (None, r"\bMBC\b", "mbc1_v2.png"),
    (None, r"\bQURAN\b|QORAN|KORAN|قرآن|القران", "quran.png"),
    (None, r"\bSUNNAH?\b|السنة", "sunnah.png"),
    (None, r"\bAZKAR\b|اذكار|أذكار", "azkar.png"),
    (None, r"\bMAJID\b", TVLOGOS + "countries/united-arab-emirates/majid-tv-ae.png"),
    # US local stations carry their network's name: "NBC 6 Johnstown PA", "WPVI ABC6 PHILADELPHIA"
    (None, r"\bNBC\s*NEWS\b", US + "nbc-news-flat-us.png"),
    (None, r"\bCBS\s*NEWS\b", US + "cbs-news-us.png"),
    (None, r"\bABC\s*NEWS\b", US + "abc-news-us.png"),
    (None, r"\bFOX\s*NEWS\b", US + "fox-news-us.png"),
    (None, r"\bNBC\s*SPORTS?\b", US + "nbc-sports-us.png"),
    (None, r"\bCBS\s*SPORTS?\b", US + "cbs-sports-us.png"),
    (None, r"\bFOX\s*SPORTS?\b", US + "fox-sports-us.png"),
    (None, r"\bTELEMUNDO\b", US + "telemundo-us.png"),
    (None, r"\bUNIVISION\b", US + "univision-us.png"),
    (None, r"\bUNIMAS\b", US + "unimas-us.png"),
    (None, r"\bION\b", US + "ion-television-us.png"),
    (None, r"\bPBS\b", US + "pbs-us.png"),
    (None, r"\bTHE\s*CW\b|\bCW\s*\d|\bCW\b", US + "cw-us.png"),
    (None, r"\bNBC\s*\d|\bNBC\b", US + "nbc-us.png"),
    (None, r"\bCBS\s*\d|\bCBS\b", US + "cbs-logo-white-us.png"),
    (None, r"\bABC\s*\d|\bABC\b", US + "abc-us.png"),
    (None, r"\bFOX\s*\d|\bFOX\b", US + "fox-us.png"),
]
# A group's own brand, for its channels that have nothing better (always weak: the provider's picture wins).
GROUP_BRANDS = [
    # generic marks for groups of 24/7 series / music / kids channels that have no logo of their own (28 Oct 2026)
    (r"EGYPT\w*\s*SERIES|مسلسلات مصرية", "gen/series_egypt.png"),
    (r"SYRIA\w*\s*SERIES|مسلسلات سورية", "gen/series_syria.png"),
    (r"TURK\w*\s*SERIES|مسلسلات تركية|YERLI\s*DIZI|YABANCI\s*DIZI", "gen/series_turkish.png"),
    (r"KIDS\s*SERIES|مسلسلات أطفال|COCUK|ÇOCUK", "gen/series_kids.png"),
    (r"MANZARA|RELAX", "gen/relax.png"),
    (r"24/7\s*SHOW|24/7", "gen/tv247.png"),
    (r"MUSIC|MUZIK|MÜZIK|أغاني|موسيقى", "gen/music.png"),
    (r"KITCHEN|مطبخ", "gen/kitchen.png"),
    (r"\|\s*KIDS\b|أطفال", "gen/kids.png"),
    (r"MOVIES\s*▶|أفلام$", "gen/movies.png"),
    (r"ROYA|رؤيا", "https://img.roya.tv/imagechanger/Size01Q40R927/storage/app/public/images/channels/iMoPuU3u5qnqMsL.png"),
    (r"SHOOF\s*(ᴄᴏᴍᴇᴅʏ|COMEDY)", "gen/shoof_comedy.png"),
    (r"SHOOF", "shoofmax.png"),
    (r"NOOR\s*PLAY", "gen/noor_play.png"),
    (r"MOTO\s*GP", "gen/motogp.png"),
    (r"TENNIS", "gen/tennis.png"),
    (r"ONBOARD|FORMULA", "f1.png"),
    (r"HBO\s*MAX|^🇬🇧 \| MAX|\bMAX\s*(ᴘᴘᴠ|PPV)", "gen/max_ppv.png"),
    (r"SOCCER|CUP GAMES|FOOTBALL|UEFA|EPL", "gen/football.png"),
    (r"PPV EVENT|PAY PER VIEW|LIVE EVENTS?$|^🔥", "gen/ppv.png"),
    (r"ISLAM|اسلام|إسلام|QURAN|قرآن", "quran.png"),
    (r"\bSN\s*\+|SPORTSNET|ROGERS", TVLOGOS + "countries/canada/sportsnet-ca.png"),
    (r"\bTSN", TVLOGOS + "countries/canada/tsn-ca.png"),
    (r"\bSTAN\b", TVLOGOS + "countries/australia/stan-sport-au.png"),
    (r"PEACOCK", TVLOGOS + "misc/media/peacock.png"),
    (r"\bFLO\b|FLOSPORT", TVLOGOS + "misc/media/flosports.png"),
    (r"DAZN", TVLOGOS + "countries/international/dazn-int.png"),
    (r"ESPN\s*(\+|PLUS)", TVLOGOS + "countries/united-states/espn-plus-us.png"),
    (r"PARAMOUNT", TVLOGOS + "countries/united-states/paramount-plus-us.png"),
    (r"\bNHL\b", TVLOGOS + "countries/united-states/nhl-network-us.png"),
    (r"\bNBA\b", TVLOGOS + "countries/canada/nba-tv-ca.png"),
    (r"\bMLB\b|MILB", TVLOGOS + "countries/united-states/mlb-network-us.png"),
    (r"\bNFL\b", TVLOGOS + "countries/united-states/nfl-network-us.png"),
    (r"BEIN|بي ان", "bein_brand.png"),
    (r"\bSOLO\b", ""),
]
WEAK = "#weak"
KNOWN = {"AR"} | set(CC.values())
EVENT_GROUP = r"PPV|EVENT|LIVE\s*EVENTS|MATCH|مباريات"


def key(name: str) -> str:
    n = html.unescape(str(name)).translate(_SUP).upper()
    n = re.sub(r"^\s*\[[A-Z-]+\]\s*:?\s*", "", n)
    n = re.sub(r"^\s*([A-Z]{2,4}(\s*VIP)?|PAL|JO|LEB|LBN|KSA|UAE|BE|STC|TOD|US-S|SPO|SPORT)\s*[|:]\s*", "", n)
    n = re.sub(r"\(.*?\)|\[.*?\]", " ", n)
    n = n.replace("&", " AND ").replace("+", " PLUS ")
    n = re.sub(_Q, " ", n)
    n = re.sub(r"[^A-Z0-9؀-ۿ]", "", n)
    n = re.sub(r"^AL", "", n)
    return _post(n)


def _post(n: str) -> str:
    """"TNT SPORT 1" and "TNT SPORTS 1" are the same channel."""
    return n.replace("SPORTS", "SPORT")


def region(group: str, playlist: str) -> str | None:
    g = group.upper().strip()
    g = re.sub(r"^\|?([A-Z]{2,3})\|\s*✪?\s*", r"\1 | ", g)  # Dream4k: "|UK| ✪ SPORTS"
    for flag, cc in (("🇺🇸", "US"), ("🇺🇲", "US"), ("🇬🇧", "UK"), ("🏴", "UK"), ("🇨🇦", "CA"), ("🇦🇺", "AU"), ("🇭🇲", "AU"), ("🇹🇷", "TR")):
        if g.startswith(flag):  # Strong-style names: "🇬🇧 | SKY ᴄɪɴᴇᴍᴀ"
            return cc
    m = re.match(r"^([A-Z]{2})\s*\|", g)
    if m:
        cc = m.group(1)
        return {"AR": "AR", "UK": "UK", "IE": "UK", "US": "US", "CA": "CA", "TR": "TR", "IT": "IT", "FR": "FR",
                "PT": "PT", "AU": "AU", "CH": "CH", "DE": "DE", "ES": "ES"}.get(cc)
    for rx, r in [(r"^UK\b|UNITED KINGDOM|NOW TV|ITV X|^SPORTS$|^GENERAL$", "UK"), (r"^USA?\b|NETWORK$|^ENTERTAINMENT$", "US"),
                  (r"CANADA|^SN\+|^TSN", "CA"), (r"TURK|TÜRK|^HABER", "TR"), (r"ITALY|ITALIA", "IT"), (r"FRANCE", "FR"),
                  (r"PORTUGAL", "PT"), (r"AUSTRALIA", "AU"), (r"SWITZERLAND", "CH"), (r"GERMANY|DEUTSCH", "DE"),
                  (r"SPAIN|ESPA", "ES")]:
        if re.search(rx, g):
            return r
    if playlist in ("hydra", "argon", "aroma", "dream4k", "family4k"):
        return "AR"
    return None


def _id_region(cid: str) -> str:
    m = re.search(r"([a-z]{2})\d*$", cid)
    if not m:
        return "*"
    cc = m.group(1)
    return "AR" if cc in ARAB else CC.get(cc, cc)


def _best(c: collections.Counter) -> str:
    (u, n), tot = c.most_common(1)[0], sum(c.values())
    return u if n * 2 > tot else ""


class Logos:
    def __init__(self, unified: str = "unified_mena_epg.xml", index: str = "tv_logos_index.json",
                 att: str = "att_epg.xml.gz"):
        self.by_id = {"u": {}, "a": {}}
        names = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))  # region -> key -> urls
        files = [unified] + sorted(f for f in glob.glob("*.xml") if f != unified)
        for f in files:
            try:
                u = open(f, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for cid, body in re.findall(r'<channel id="([^"]+)">(.*?)</channel>', u, re.S):
                m = re.search(r'<icon src="([^"]+)"', body)
                if not m:
                    continue
                url = html.unescape(m.group(1))
                if f == unified:
                    self.by_id["u"][html.unescape(cid)] = url
                r = _id_region(html.unescape(cid))
                r = r if r in KNOWN else "X"
                for dn in re.findall(r"<display-name[^>]*>(.*?)</display-name>", body):
                    k = key(dn)
                    if len(k) >= 3:
                        names[r][k][url] += 3 if f == unified else 1
        self.repo_reg = {r: {k: _best(v) for k, v in d.items()} for r, d in names.items()}
        self.repo_reg = {r: {k: v for k, v in d.items() if v} for r, d in self.repo_reg.items()}
        self.repo = dict(self.repo_reg.get("X", {}))
        self.repo.update(self.repo_reg.get("AR", {}))
        # this repo's logos/ folder by file name (mbc_masr2_v2.png -> MBCMASR2)
        for p in sorted(glob.glob(os.path.join(HERE, "logos", "**", "*.png"), recursive=True)):
            if os.sep + "teams" + os.sep in p:  # club badges and flags, not channels
                continue
            rel = os.path.relpath(p, os.path.join(HERE, "logos")).replace(os.sep, "/")
            k = key(re.sub(r"_v\d+$|_logo$", "", os.path.basename(p)[:-4]).replace("_", " "))
            if len(k) >= 3 and k not in self.repo and REPO:
                self.repo[k] = REPO + rel
        # the AT&T guide (this repo's, att-epg branch; the workflow copies it in)
        self.att = collections.defaultdict(dict)
        self.att_regions = collections.defaultdict(set)
        try:
            a = gzip.open(att, "rt", encoding="utf-8", errors="ignore").read()
            an = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
            for cid, body in re.findall(r'<channel id="([^"]+)">(.*?)</channel>', a, re.S):
                m = re.search(r'<icon src="([^"]+)"', body)
                if not m:
                    continue
                url = html.unescape(m.group(1))
                cid = html.unescape(cid)
                self.by_id["a"][cid] = url
                r = _id_region(cid)
                for dn in set(re.findall(r"<display-name[^>]*>(.*?)</display-name>", body)):
                    k = key(dn)
                    if len(k) >= 3:
                        an[r][k][url] += 1
                        an["*"][k][url] += 1
                        self.att_regions[k].add(r)
            for r, d in an.items():
                for k, c in d.items():
                    b = _best(c)
                    if b:
                        self.att[r][k] = b
        except (OSError, EOFError):
            pass
        self.tv = {}
        if os.path.exists(index):
            self.tv = {r: {_post(k): v for k, v in d.items()}
                       for r, d in json.load(open(index, encoding="utf-8")).get("regions", {}).items()}

    # ---- one channel -------------------------------------------------------------------------------
    def find(self, name: str, group: str, playlist: str, epg_src: str | None, epg_id: str | None) -> str:
        up = html.unescape(str(name)).upper()
        g = str(group).upper()
        for grx, nrx, url in FIRST:
            if (not grx or re.search(grx, g, re.I)) and re.search(nrx, up):
                return REPO + url[5:] if url.startswith("REPO:") else url
        if epg_src in ("u", "a") and epg_id and self.by_id[epg_src].get(epg_id):
            return self.by_id[epg_src][epg_id]
        r = region(group, playlist)
        weak = WEAK if re.search(EVENT_GROUP, g, re.I) else ""
        for i, k in enumerate(self.keys(name)):
            hit = self._look(k, r)
            if hit:
                return hit + (WEAK if i else weak)
        # "SKY Action", "Skyanimation", "SKY Scfi/Hor": Sky Cinema channels under their short names (Argon NOW TV)
        m = re.match(r"^(?:UK:?\s*)?SKY\s*(ACTION|GREATS|ANIMATION|SCI-?FI|SCFI|FAMILY|COMEDY|DRAMA|THRILLER|PREMIERE|HITS|SELECT|"
                     r"BOURNE|CHRISTMAS|KIDS|SPOTLIGHT)\b", up)
        if m and "CINEMA" not in up:
            alias = "SKY CINEMA " + {"SCFI": "SCI-FI HORROR", "SCIFI": "SCI-FI HORROR", "SCI-FI": "SCI-FI HORROR"}.get(m.group(1), m.group(1))
            for k in self.keys(alias):
                hit = self._look(k, r or "UK")
                if hit:
                    return hit
        for grx, nrx, url in BRANDS:
            if (not grx or re.search(grx, g)) and re.search(nrx, up):
                return (url if url.startswith("http") else REPO + url) + WEAK
        # last: the exact name in another country's collection (a provider logo, if any, still wins: "#weak")
        k0 = self.keys(name)[:1]
        if k0 and len(k0[0]) >= 4:
            # (Sky's German / Italian channels share names with the UK ones: not for an English "SKY ..." name)
            regs = ("UK", "US", "INT", "CA", "AU") if up.lstrip("UK|: ").startswith("SKY") else (
                "UK", "US", "INT", "CA", "AU", "FR", "DE", "IT", "ES", "PT", "TR", "CH", "AR")
            for reg in regs:
                p = self.tv.get(reg, {}).get(k0[0])
                if p:
                    return TVLOGOS + p + WEAK
        return ""

    @staticmethod
    def keys(name: str) -> list:
        """The name's key, then the same with trailing words dropped one by one (never a number)."""
        out = []
        k = key(name)
        if len(k) >= 2:
            out.append(k)
        words = re.sub(r"\(.*?\)|\[.*?\]", " ", html.unescape(str(name))).replace("+", " +").split()
        while len(words) > 1:
            last = words.pop()
            if re.search(r"\d", last) and not re.fullmatch(r"\+\d", last):
                break
            k2 = key(" ".join(words))
            if len(k2) >= 3 and k2 not in out:
                out.append(k2)
        return out

    def _look(self, k: str, r: str | None) -> str:
        if r in ("AR", None) and self.repo.get(k):
            return self.repo[k]
        if r and r != "AR" and self.repo_reg.get(r, {}).get(k):
            return self.repo_reg[r][k]
        for reg in ([r] if r else ["AR"]):
            if self.att.get(reg, {}).get(k):
                return self.att[reg][k]
        for reg in ([r] if r else []) + ["INT"]:
            p = self.tv.get(reg, {}).get(k)
            if p:
                return TVLOGOS + p
        # an English-language channel listed in an Arabic playlist's own group ("Solo SPORTS", "Kitchen"):
        # the AT&T guide's logo when that name is only known in the US / UK / Canada / Australia / Arab lists
        if r in ("AR", None) and self.att["*"].get(k) and self.att_regions[k] <= {"US", "UK", "CA", "AU", "AR", "*"}:
            return self.att["*"][k]
        return ""

    # ---- a whole playlist -------------------------------------------------------------------------
    shared: dict = {}

    def share_from(self, streams: list, group_of: dict, playlist: str) -> None:
        """Remember this playlist's real (not "#weak") logos for the other playlists, by country and name."""
        for s in streams:
            ic = s.get("stream_icon") or ""
            if not ic or ic.endswith(WEAK):
                continue
            r = region(group_of.get(s["category_id"], ""), playlist)
            for k in self.keys(s["name"])[:1]:
                if len(k) >= 4:
                    self.shared.setdefault((r, k), ic)

    def fill_playlist(self, streams: list, group_of: dict, playlist: str) -> None:
        """Second pass over one playlist's live_streams (dicts with name/stream_icon/category_id)."""
        have = {}
        for s in streams:
            if s.get("stream_icon"):
                for k in self.keys(s["name"])[:1]:
                    have.setdefault(k, s["stream_icon"])
        def blocked(s):
            g, up = group_of.get(s["category_id"], "").upper(), html.unescape(str(s["name"])).upper()
            return any(not url and (not grx or re.search(grx, g)) and re.search(nrx, up) for grx, nrx, url in FIRST)
        for s in streams:
            if s.get("stream_icon") or blocked(s):
                continue
            for k in self.keys(s["name"]):
                if have.get(k):
                    s["stream_icon"] = have[k]
                    break
        # the same channel in another playlist (same country) that has a real logo (owner, 28 Oct 2026:
        # "check the others for logos")
        for s in streams:
            if s.get("stream_icon") or blocked(s):
                continue
            r = region(group_of.get(s["category_id"], ""), playlist)
            for k in self.keys(s["name"])[:1]:
                hit = self.shared.get((r, k)) if len(k) >= 4 else None
                if hit:
                    s["stream_icon"] = hit
        for s in streams:
            if s.get("stream_icon") or blocked(s):
                continue
            g = group_of.get(s["category_id"], "")
            b = self.group_brand(g, playlist)
            s["stream_icon"] = b + WEAK if b else ""

    def group_brand(self, group: str, playlist: str) -> str:
        g = re.sub(r"\s*-\s*[؀-ۿ\s]+$", "", group)  # "ITALY - أيطاليا" -> "ITALY"
        g = re.sub(r"\b(NETWORK|VIP|PLATINUM|GOBX|RAW|60FPS|4K|HD|FHD|SD|HEVC|PLUS|24/7|SERIES|REGIONALS?)\b", " ", g,
                   flags=re.I)
        up = g.upper()
        for rx, url in GROUP_BRANDS:
            if re.search(rx, group, re.I):
                return url if not url or url.startswith("http") else REPO + url
        for grx, nrx, url in BRANDS:
            if not grx and re.search(nrx, up):
                return url if url.startswith("http") else REPO + url
        return ""
        r = region(group, playlist)
        for k in self.keys(g):
            if len(k) >= 3:
                hit = self._look(k, r)
                if hit:
                    return hit
        return ""
