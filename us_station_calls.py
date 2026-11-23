#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Call signs for US network station names that carry none.

The playlist names some stations only by network, channel number and city
("US: ABC 7 HD [BUFFALO]", "US: CW PIX 11 HD"). att_epg.call_sign() reads the
call sign out of the name; for these it asks here: (network, number, city) ->
the station that holds that network on that channel in that city (ABC 7 Buffalo
is WKBW). Asked for as "ABC, NBC, FOX, CBS add for every states channel ... add
every single one" (24 October 2026). A name not in this table stays without a
call sign, as before.
"""
import re

T = {
 # "TV: ABC7 <city>" names
 ("ABC","7","BAY AREA"):"KGO",("ABC","7","CHICAGO"):"WLS",
 ("ABC","","NEW YORK"):"WABC",("ABC","7","NEW YORK"):"WABC",("ABC","2","ATLANTA"):"WSB",("ABC","2","BATON ROUGE"):"WBRZ",
 ("ABC","2","BALTIMORE"):"WMAR",("ABC","3","SHREVEPORT"):"KTBS",("ABC","3","PENSACOLA"):"WEAR",("ABC","4","HONOLULU"):"KITV",
 ("ABC","4","CHARLESTON"):"WCIV",("ABC","5","OKLAHOMA CITY"):"KOCO",("ABC","5","ST. PAUL"):"KSTP",("ABC","6","AUGUSTA"):"WJBF",
 ("ABC","7","EL PASO"):"KVIA",("ABC","7","BUFFALO"):"WKBW",("ABC","7","FORT MYERS"):"WZVN",("ABC","7","SARASOTA"):"WWSB",
 ("ABC","9","MANCHESTER"):"WMUR",("ABC","9","TUCSON"):"KGUN",("ABC","9","CHARLOTTE"):"WSOC",("ABC","9","SYRACUSE"):"WSYR",
 ("ABC","","TAMPA"):"WFTS",("ABC","11","RALEIGH"):"WTVD",("ABC","13","HAMPTON ROADS"):"WVEC",("ABC","13","LAS VEGAS"):"KTNV",
 ("ABC","13","ASHEVILLE"):"WLOS",("ABC","20","GAINESVILLE"):"WCJB",("ABC","26","NEW ORLEANS"):"WGNO",("ABC","22","BURLINGTON"):"WVNY",
 ("ABC","27","MADISON"):"WKOW",("ABC","27","HARRISBURG"):"WHTM",("ABC","36","LEXINGTON"):"WTVQ",("ABC","33/40","BIRMINGHAM"):"WBMA",
 ("ABC","45","WINSTON-SALEM"):"WXLV",
 ("CW","11","PIX"):"WPIX",("CW","11","SEATTLE"):"KSTW",("CW","19","TULSA"):"KQCW",("CW","20","GREENSBORO"):"WCWG",
 ("CW","35","SAN ANTONIO"):"KMYS",("CW","44","ST. PETERSBURG"):"WTOG",("CW","44","TAMPA"):"WTOG",("CW","44","SAN FRANCISCO"):"KBCW",
 ("CW","50","DETROIT"):"WKBD",("CW","53","COLUMBUS"):"WWHO",("CW","58","LOUISVILLE"):"WBKI",("CW","58","NASHVILLE"):"WNAB",
 ("CW","69","ATLANTA"):"WUPA",
 ("CBS","4","BUFFALO"):"WIVB",
 ("FOX","2","SAN FRANCISCO"):"KTVU",("FOX","5","SAN DIEGO"):"KSWB",("FOX","5","LAS VEGAS"):"KVVU",("FOX","5","WASHINGTON"):"WDCA",
 ("FOX","7","AUSTIN"):"KTBC",("FOX","8","GREENSBORO"):"WGHP",("FOX","9","MINNEAPOLIS"):"WFTC",("FOX","10","ALABAMA"):"WALA",
 ("FOX","10","MOBILE"):"WALA",("FOX","10","PHOENIX"):"KUTP",("FOX","13","SEATTLE"):"KCPQ",("FOX","19","CINCINNATI"):"WXIX",
 ("FOX","21","GREENVILLE SC"):"WHNS",("FOX","21","ASHEVILLE"):"WHNS",("FOX","24","FORT SMITH"):"KFTA",("FOX","29","BUFFALO"):"WUTV",
 ("FOX","29","PALM BEACH"):"WFLX",("FOX","35","ORLANDO"):"WRBW",("FOX","41","YAKIMA"):"KCYU",("FOX","43","HARRISBURG"):"WPMT",
 ("FOX","44","EVANSVILLE"):"WEVV",("FOX","46","CHARLOTTE"):"WJZY",("FOX","51","GAINESVILLE"):"WOGX",("FOX","61","HARTFORD"):"WTIC",
 ("FOX","62","YOUNGSTOWN"):"WYFX",("FOX","64","PROVIDENCE"):"WNAC",
}
def lookup(name):
    u = re.sub(r'^[^:]{1,6}:\s*', '', name.upper()).strip()
    u = re.sub(r'[^\x00-\x7f]+', ' ', u)
    u = re.sub(r'\((?:#|FL|[A-Z]{1,2})\)', ' ', u)
    u = re.sub(r'\b(?:CITY )?RAW\b', ' ', u)
    u = re.sub(r'^(ABC|CBS|NBC|FOX)(\d)', r'\1 \2', re.sub(r'\s+', ' ', u).strip())
    m = re.match(r'(ABC|CBS|NBC|FOX|CW)\s*(PIX)?\s*([\d/]*)\s*(?:PLUS|XTRA)?\s*(?:HD)?\s*(?:\[([^\]]+)\]|([A-Z .\-]+?))?\s*(?:HD|\(FL\))?\s*$', u)
    if not m: return None
    net, pix, num, city1, city2 = m.groups(); city = (city1 or city2 or ("PIX" if pix else "")).strip()
    words = city.split(' ')
    for c in [city, city.split('/')[0]] + [' '.join(words[:i]) for i in range(len(words), 0, -1)]:
        if (net, num or "", c) in T: return T[(net, num or "", c)]
        if (net, "", c) in T: return T[(net, "", c)]
    return None
