#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Channel logos for the relays (owner, 27 October 2026: "why is there no logo on any channel ... do it without me").

Order of preference for one channel:
  1. the repo's own logo for its guide id (unified_mena_epg.xml <icon>)
  2. the repo's own logo for a channel of the same name in that guide
  3. the public tv-logo/tv-logos collection (tv_logos_index.json), same region first, then international
The worker fills whatever is still empty with the provider's logo (with the viewer's own login).
Names are compared after dropping picture words (HD, FHD, 4K, HEVC, RAW...), "TV" and country prefixes.
"""
from __future__ import annotations

import html
import json
import os
import re

_Q = r"\b(UHD|FHD|HD|SD|LQ|4K|8K|HEVC|RAW|3840P|60FPS|50FPS|HDR|ULTRA|VIP|TV|CHANNEL|BACKUP|BK|ME|SAT)\b"
_PREFIX = r"^\s*(\[[A-Z]{2}(-[A-Z]{2})?\]|[A-Z]{2,3}(-[A-Z])?|PAL|JO|LEB|LBN|KSA|UAE|BE|STC|TOD|US-S)\s*[|:\]]?\s+"
_IDX = {}
try:
    _IDX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tv_logos_index.json"), encoding="utf-8"))
except (OSError, ValueError):
    pass
TVLOGOS = _IDX.get("base", "")  # picture links only; nothing is downloaded at build time
REPO = _IDX.get("repo_base", "")
LB = TVLOGOS + "countries/lebanon/"
# Hand-checked brand rules (owner's photos, 27 Oct 2026): (group regex or None, name regex, logo).
# A logo of "" means: leave it to the provider (a same-named channel elsewhere is a different one).
ALIASES = [
    (r"LEBANON|^LB", r"^(LBN|LEB)?\s*\|?\s*ONE\b", ""),
    (None, r"\bMTV\b.*|^(LBN|LEB)\s*\|\s*MTV", None),
    (None, r"FAJE?R\b|FAJR\b", REPO + "fajer.png"),
    (None, r"KOFIYA|KUFIYA", REPO + "alkofiya.png"),
    (None, r"QUDS\s*(AL)?\s*(TODAY|ALYAWM|AL YAWM)", REPO + "alquds_today.png"),
    (None, r"PALESTINE\s*SPORT|FALASTIN\w*\s*SPORT", REPO + "palestine_sport.png"),
    (None, r"PALESTINE\s*(MUBASHER|MUBASHIR|LIVE)", REPO + "palestine_mubashir.png"),
    (None, r"PALESTINE\s*(AL)?\s*YAWM|PALESTINE TODAY", REPO + "palestine_alyawm.png"),
    (None, r"^(\w+\s*\|\s*)?(PALESTINE|FALASTIN\w*|PAL)\s*(TV|HD|FHD|4K|$)", REPO + "palestine_tv.png"),
    (None, r"FATAFEAT|FATAFIT", REPO + "fatafeat_v2.png"),
    (None, r"BARA[EI]+M", REPO + "bein_ent_baraem.png"),
    (None, r"\bJEEM\b", REPO + "bein_ent_jeem.png"),
    (None, r"ROYA\s*NEWS", REPO + "roya_news.png"),
    (None, r"ROYA\s*KIDS", REPO + "roya_kids.png"),
    (None, r"ROYA\s*KITCHEN", REPO + "roya_kitchen.png"),
    (None, r"ROYA\s*COMEDY", REPO + "roya_comedy.png"),
    (None, r"^(\w+\s*\|\s*)?ROYA\b", REPO + "roya_tv.png"),
    (None, r"^(\w+\s*\|\s*)?JORDAN\s*SPORT", REPO + "jordan_sport.png"),
    (r"JORDAN|^JO\b", r"^JR\b", REPO + "jordan_tv.png"),
    (None, r"\bLBC\b", LB + "lbc-international-lb.png"),
    (None, r"TELE\s*LUMIERE|NOURSAT", LB + "tele-lumiere-lb.png"),
    (None, r"FUTURE\s*TV", LB + "future-tv-lb.png"),
]
_SUP = str.maketrans({"ᴿ": "", "ᴬ": "", "ᵂ": "", "ʰ": "", "ᵉ": "", "ᵛ": "", "ᶜ": "", "ᴴ": "", "ᴰ": "", "ⓧ": "", "§": ""})


def key(name: str) -> str:
    n = html.unescape(str(name)).translate(_SUP).upper()
    n = re.sub(r"^\s*\[[A-Z-]+\]\s*:?\s*", "", n)
    n = re.sub(r"^\s*([A-Z]{2,3}|PAL|JO|LEB|LBN|KSA|UAE|BE|STC|TOD|US-S)\s*[|:]\s*", "", n)
    n = re.sub(r"\(.*?\)", " ", n)
    n = n.replace("&", " AND ").replace("+", " PLUS ")
    n = re.sub(_Q, " ", n)
    n = re.sub(r"[^A-Z0-9؀-ۿ]", "", n)
    n = re.sub(r"^AL", "", n)
    return n


def region(group: str, playlist: str) -> str | None:
    g = group.upper().strip()
    m = re.match(r"^([A-Z]{2})\s*\|", g)
    if m:
        cc = m.group(1)
        return {"AR": "AR", "UK": "UK", "IE": "UK", "US": "US", "CA": "CA", "TR": "TR", "IT": "IT", "FR": "FR",
                "PT": "PT", "AU": "AU", "CH": "CH", "DE": "DE", "ES": "ES"}.get(cc)
    for rx, r in [(r"^UK\b|UNITED KINGDOM|NOW TV|ITV X|^SPORTS$|^GENERAL$", "UK"), (r"^USA?\b|NETWORK$|^ENTERTAINMENT$", "US"),
                  (r"CANADA", "CA"), (r"TURK|TÜRK|^HABER", "TR"), (r"ITALY|ITALIA", "IT"), (r"FRANCE", "FR"),
                  (r"PORTUGAL", "PT"), (r"AUSTRALIA", "AU"), (r"SWITZERLAND", "CH")]:
        if re.search(rx, g):
            return r
    if playlist in ("hydra", "argon", "aroma"):
        return "AR"
    return None


class Logos:
    def __init__(self, unified: str = "unified_mena_epg.xml", index: str = "tv_logos_index.json"):
        self.by_id, by_name = {}, {}
        try:
            u = open(unified, encoding="utf-8").read()
            for cid, body in re.findall(r'<channel id="([^"]+)">(.*?)</channel>', u, re.S):
                m = re.search(r'<icon src="([^"]+)"', body)
                if not m:
                    continue
                url = html.unescape(m.group(1))
                self.by_id[html.unescape(cid)] = url
                for dn in re.findall(r"<display-name[^>]*>(.*?)</display-name>", body):
                    k = key(dn)
                    if len(k) >= 3:
                        by_name.setdefault(k, set()).add(url)
        except OSError:
            pass
        self.by_name = {k: next(iter(v)) for k, v in by_name.items() if len(v) == 1}
        self.tv = {}
        if os.path.exists(index):
            self.tv = json.load(open(index, encoding="utf-8")).get("regions", {})

    def find(self, name: str, group: str, playlist: str, epg_src: str | None, epg_id: str | None) -> str:
        if epg_src == "u" and epg_id and self.by_id.get(epg_id):
            return self.by_id[epg_id]
        up = html.unescape(str(name)).upper()
        g = str(group).upper()
        for grx, nrx, url in ALIASES:
            if grx and not re.search(grx, g):
                continue
            if re.search(nrx, up):
                if url is None:
                    if re.search(r"LEBANON|^(LBN|LEB)\b", g + " " + up):
                        return LB + "mtv-lebanon-lb.png"
                    continue
                return url
        k = key(name)
        if len(k) < 2:
            return ""
        r = region(group, playlist)
        hit = self._look(k, r)
        if hit:
            return hit
        # Same channel with a regional / timeshift / country tail ("BBC One London", "MBC 1 USA", "Pop +1"):
        # drop trailing words one by one, never a number (Sky Sports 1 must not become Sky Sports).
        words = re.sub(r"\(.*?\)", " ", html.unescape(str(name))).replace("+", " +").split()
        while len(words) > 1:
            last = words.pop()
            if re.search(r"\d", last) and not re.fullmatch(r"\+\d", last):
                break
            k2 = key(" ".join(words))
            if len(k2) >= 3:
                hit = self._look(k2, r)
                if hit:
                    return hit
        return ""

    def _look(self, k: str, r: str | None) -> str:
        if (r == "AR" or r is None) and self.by_name.get(k):
            return self.by_name[k]
        for reg in ([r] if r else []) + ["INT"]:
            p = self.tv.get(reg, {}).get(k)
            if p:
                return TVLOGOS + p
        return ""
