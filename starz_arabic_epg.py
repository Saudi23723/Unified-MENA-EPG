#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Arab channels STARZPLAY carries that no guide here had — on the Roya link.

Asked for after the UAE channels, in those words: "look at everything you
can find, and are sure of". STARZPLAY's web-EPG — the licensed platform
that already gives this project the UAE and sports channels — lists 117
channels; the ones below are the Arab channels among them that no guide
in this project carried, each measured on 26 September 2026 to have a
real schedule: named programmes, no gap anywhere in the next 72 hours,
and no placeholder.

WHAT WAS MEASURED AND LEFT OUT. A channel whose schedule says nothing is
not given one here:
  Majid TV         one "BELFORT&LUPIN" row ninety-two hours long
  Baynounah TV     "No program available" eight times, and a 59-hour row
  Sky News Arabia  "Sky News Arabia HD", ninety-seven times
  Asharq Bloomberg "Asharq", twenty-five times
  Al Sanafer       "Al Sanafer", 222 times
  Saudi Quran, ADMN Quran Kareem — one title, or "Generic Program 535"
  France 24 Arabic — its rows are the French channel's ("Le journal")
Radio, the South Asian and French channels, and STARZPLAY's own branded
channels are not Arab broadcast channels a playlist carries, and are not
read.

Everything else — the reading, the Arabic title with the English beside
it, dropping the platform's placeholder rows, the names and the logo — is
uae_epg's own, and the catalogue is fetched once for both.
"""
from __future__ import annotations

import os

import xml.etree.ElementTree as ET

import uae_epg
from epg_lib import log, utc_now, warn

LOGO_BASE = uae_epg.LOGO_BASE.rsplit("/", 1)[0] + "/arabic"
LOGO_DIR = os.path.join("logos", "arabic")

# (xmltv id, STARZPLAY slug, logo stem, [every name a playlist uses])
CHANNELS = [
    ("RotanaClassic.sa", "rotanaclassic", "rotana_classic",
     ["Rotana Classic", "ROTANA CLASSIC", "Rotana Classic HD", "روتانا كلاسيك"]),
    ("RotanaComedy.sa", "rotanacomedy", "rotana_comedy",
     ["Rotana Comedy", "ROTANA COMEDY", "Rotana Comedy HD", "روتانا كوميدي"]),
    ("RotanaDrama.sa", "rotanadrama", "rotana_drama",
     ["Rotana Drama", "ROTANA DRAMA", "Rotana Drama HD", "روتانا دراما"]),
    ("RotanaKhaleejiah.sa", "rotanakhaleejiah", "rotana_khaleejiah",
     ["Rotana Khaleejiah", "ROTANA KHALEEJIA", "Rotana Khalijia", "Rotana Khaleejia",
      "Rotana Khaleejiah HD", "روتانا خليجية"]),
    ("RotanaCinemaKSA.sa", "rotanacinemaksa", "rotana_cinema_ksa",
     ["Rotana Cinema KSA", "ROTANA CINEMA", "Rotana Cinema", "Rotana Cinema HD",
      "روتانا سينما السعودية", "روتانا سينما"]),
    ("RotanaCinemaEgypt.sa", "rotanacinemaegypt", "rotana_cinema_egypt",
     ["Rotana Cinema Egypt", "ROTANA CINEMA EGYPT", "Rotana Cinema Masr",
      "Rotana Masriya", "روتانا سينما مصر"]),
    ("Saudi1.sa", "saudionehd", "saudi_1",
     ["Saudi 1", "SAUDI 1", "Saudi TV", "Al Saudiya", "Saudi 1 HD", "السعودية 1",
      "السعودية"]),
    ("LBCSat.lb", "lbcsat", "lbc_sat",
     ["LBC Sat", "LBC SAT", "LBC", "LBCI Sat", "أل بي سي سات"]),
    ("KanalDDrama.tr", "kanalddrama", "kanal_d_drama",
     ["Kanal D Drama", "KANAL D DRAMA", "Kanal D Drama HD", "كنال دي دراما"]),
    ("ZeeAlwan.ae", "zeealwan", "zee_alwan",
     ["Zee Alwan", "ZEE ALWAN", "Zee Alwan HD", "زي ألوان"]),
    ("ZeeAflam.ae", "zeeaflam", "zee_aflam",
     ["Zee Aflam", "ZEE AFLAM", "Zee Aflam HD", "زي أفلام"]),
    ("MBCPluseLife.ae", "mbcpluselife", "mbc_plus_elife",
     ["MBC+ e&", "MBC+ ELIFE", "MBC Plus eLife", "MBC+ eLife"]),
    ("AlWoustaAlDhaid.ae", "alwoustaaldhaid", "al_wousta",
     ["Al Wousta Al Dhaid", "AL WOUSTA", "Al Wousta", "Al Wousta TV", "الوسطى من الذيد",
      "قناة الوسطى"]),
    ("AlHadath.ae", "alhadath", "al_hadath",
     ["Al Hadath", "AL HADATH", "Al Hadath HD", "Alhadath", "الحدث", "قناة الحدث"]),
    ("AlArabiyaBusiness.ae", "alarabiyabusiness", "al_arabiya_business",
     ["Al Arabiya Business", "AL ARABIYA BUSINESS", "Alarabiya Business",
      "العربية بيزنس"]),
    ("CNBCArabiya.ae", "cnbcarabiya", "cnbc_arabiya",
     ["CNBC Arabiya", "CNBC ARABIYA", "CNBC Arabiya HD", "CNBC Arabia",
      "سي إن بي سي عربية"]),
    ("CNNInternational.us", "cnninternational", "cnn_international",
     ["CNN International", "CNN INTERNATIONAL", "CNN", "CNN Int", "CNN HD"]),
    ("Spacetoon.ae", "spacetoon", "spacetoon",
     ["Spacetoon", "SPACETOON", "Space Toon", "Spacetoon HD", "سبيستون", "سبيس تون"]),
    ("CartoonNetworkArabic.ae", "cartoonnetworkarabic", "cartoon_network_arabic",
     ["Cartoon Network Arabic", "CARTOON NETWORK ARABIC", "Cartoon Network Arabia",
      "CN Arabic", "Cartoon Network", "كرتون نتورك بالعربية"]),
    ("2MMonde.ma", "twommonde", "2m_monde",
     ["2M Monde", "2M MONDE", "2M", "2M Maroc", "2M TV"]),
]


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    floor = utc_now() - uae_epg.KEEP_BEHIND
    try:
        catalogue = uae_epg.starz_catalogue(session)
    except Exception as exc:                                      # noqa: BLE001
        warn(f"STARZPLAY Arab channels: the catalogue could not be read ({exc})")
        return {}
    out: dict[str, list[dict]] = {}
    for xmltv_id, slug, _logo, names in CHANNELS:
        rows = uae_epg.starz_rows(catalogue, slug, floor)
        if rows:
            out[xmltv_id] = rows
            log(f"  {names[0]:26} {len(rows):4} programmes")
        else:
            warn(f"STARZPLAY Arab channels: {names[0]} has nothing this run")
    return out


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    channels = [(xmltv_id, logo, names, None)
                for xmltv_id, _slug, logo, names in CHANNELS]
    return uae_epg.write_channels(root, per_channel, channels, LOGO_DIR,
                                  LOGO_BASE, "STARZPLAY Arab channels")
