#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask every source every guide reads whether it is still there.

FilGoal's RSS died silently and ON Sport went blind for days without one
red run. This asks the question for all of them at once: what does each
source answer, and does the published guide it feeds actually contain
programmes or only a placeholder standing in for them.
"""
import os, re, sys, gzip, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import Counter
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
UTC = timezone.utc
now = datetime.now(UTC)
today = now.strftime("%Y-%m-%d")

# (guide, source, url) — the concrete endpoints, not the templates.
SOURCES = [
    ("beIN Qatar", "beIN opta channels",
     "https://www.beinsports.com/api/opta/tv-channel?region=ar-mena"),
    ("beIN Qatar", "beIN opta events",
     f"https://www.beinsports.com/api/opta/tv-event?region=ar-mena&date={today}"),

    ("beIN Türkiye", "tvyayinakisi bein-sports-1",
     "https://www.tvyayinakisi.com/bein-sports-1-yayin-akisi/"),
    ("beIN Türkiye", "epgshare TR1",
     "https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz"),
    ("beIN Türkiye", "open-epg turkey1",
     "https://www.open-epg.com/files/turkey1.xml"),
    ("beIN Türkiye", "Spor Ekranı", "https://www.sporekrani.com/"),
    ("Tivibu", "epgshare TR3",
     "https://epgshare01.online/epgshare01/epg_ripper_TR3.xml.gz"),

    ("Roya", "roya backend",
     "https://backend.roya.tv/api/v01/channels/schedule-pagination?day_number=0"),
    ("Al Jadeed", "aljadeed schedule",
     f"https://www.aljadeed.tv/schedule-channels-date/1/{now:%Y/%m/%d}/ar"),
    ("Al Jazeera", "aljazeera schedule", "https://www.aljazeera.net/schedule"),

    ("Jordan Sports", "JRTV", "https://www.jrtv.gov.jo/"),
    ("Jordan Sports", "JFA", "https://jfa.jo/tourn.php?id=10&idcat=6&idsubcat=34&"),
    ("Jordan Sports", "sport24", "https://www.sport24.rest/competition/18668"),
    ("Jordan Sports", "lftv jordan-sports",
     "https://www.livefootballtv.info/channel/jordan-sports"),

    ("ON Sport", "filgoal RSS 88",
     "https://www.filgoal.com/section/88/rss/الدوري-المصري"),
    ("ON Sport", "filgoal section 88",
     "https://www.filgoal.com/section/88/articles/"),
    ("ON Sport", "filgoal matches", "https://www.filgoal.com/matches"),
    ("ON Sport", "EPL official", "https://www.egyptianproleague.com/"),
    ("ON Sport", "lftv on-sport-1",
     "https://www.livefootballtv.info/channel/on-sport-1"),
    ("ON Sport", "yallakora match-center",
     "https://www.yallakora.com/match-center"),

    ("Alwan", "telegram AlwanSports", "https://t.me/s/AlwanSports"),
    ("Alkass", "alkass tvguide", "https://www.alkass.net/tvguide"),
    ("STARZPLAY", "playco epg",
     "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"),
    ("Fajer", "telegram fajersport", "https://t.me/s/fajersport"),
    ("Fajer", "lftv home", "https://www.livefootballtv.info/"),

    ("Shahid", "lftv mbc-shahid-sports",
     "https://www.livefootballtv.info/channel/mbc-shahid-sports"),
    ("Shahid", "livesoccertv shahid",
     "https://www.livesoccertv.com/channels/shahid/"),
    ("Shahid", "kooora", "https://www.kooora.com/"),
    ("Shahid", "goal.com ar", "https://www.goal.com/ar"),

    ("Shasha", "fotmob kuwait league",
     "https://www.fotmob.com/api/leagues?id=529&ccode3=KWT&season=2026%2F2027"),
    ("Shasha", "legaseriea", "https://www.legaseriea.it"),
    ("Shasha", "oddalerts kuwait",
     "https://www.oddalerts.com/leagues/kuwait/zain-premier-league/fixtures"),

    ("tabii", "TRT tabii-spor",
     "https://www.trtspor.com.tr/yayin-akisi/tabii-spor"),
    ("tabii", "tvyayinakisi tabii",
     "https://www.tvyayinakisi.com/tabii-spor-yayin-akisi/"),
    ("tabii", "Spor Ekranı", "https://www.sporekrani.com/"),

    ("Thmanyah", "telegram matches_today2", "https://t.me/s/matches_today2"),
    ("Thmanyah", "elgoal channels",
     "https://elgoal.net/broadcasting-channels-today-matches/"),
    ("Thmanyah", "365scores where-to-watch",
     "https://www.365scores.com/ar/where-to-watch"),
    ("Thmanyah", "filgoal matches", "https://www.filgoal.com/matches/"),
]

print(f"SOURCE HEALTH | {now:%Y-%m-%d %H:%M} UTC\n")
print(f"{'guide':14} {'source':28} {'code':>5} {'bytes':>9}  note")
dead = []
for guide, label, url in SOURCES:
    try:
        r = requests.get(url, headers={"User-Agent": UA,
                                       "Accept-Language": "ar,en;q=0.9"},
                         timeout=30)
        body = r.content
        note = ""
        if r.status_code != 200:
            note = re.sub(r"\s+", " ", r.text[:70])
            dead.append((guide, label, r.status_code, note))
        elif len(body) < 2000:
            note = "suspiciously small"
            dead.append((guide, label, r.status_code, note))
        print(f"{guide:14} {label:28} {r.status_code:>5} {len(body):>9}  {note}")
    except Exception as exc:
        print(f"{guide:14} {label:28} {'ERR':>5} {'-':>9}  {str(exc)[:60]}")
        dead.append((guide, label, "ERR", str(exc)[:60]))

print("\n\nPUBLISHED GUIDES — how much of each is a placeholder\n")
# A title that stands in for a schedule rather than being one.
STANDIN = re.compile(
    r"لا توجد مباراة|لا يوجد|PPV — حسب المباراة|Tanıtım|24/7|"
    r"⏰ التالي|بث مباشر على مدار|قناة .* على مدار", re.I)

print(f"{'file':32} {'ch':>4} {'prog':>6} {'stand-in':>9} {'%':>5}  worst channel")
for path in sorted(f for f in os.listdir(".") if f.endswith("_epg.xml")):
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        print(f"{path:32} UNPARSABLE {exc}")
        continue
    per = {}
    total = standin = 0
    for p in root.findall("programme"):
        t = p.findtext("title") or ""
        cid = p.get("channel")
        s = bool(STANDIN.search(t))
        # a channel whose every title is its own name is the same failure
        per.setdefault(cid, [0, 0, Counter()])
        per[cid][0] += 1
        per[cid][2][t] += 1
        if s:
            per[cid][1] += 1
        total += 1
        standin += s
    for cid, v in per.items():
        # one title repeated for the whole channel is a placeholder too
        if v[0] >= 4 and len(v[2]) == 1:
            v[1] = v[0]
    standin = sum(v[1] for v in per.values())
    worst = sorted(((v[1] / v[0], cid, v[0], v[1]) for cid, v in per.items()
                    if v[0] >= 3), reverse=True)[:3]
    pct = 100 * standin / total if total else 0
    tag = "  <-- LOOK" if pct >= 25 else ""
    print(f"{path:32} {len(root.findall('channel')):>4} {total:>6} "
          f"{standin:>9} {pct:>4.0f}%  "
          f"{', '.join(f'{c} {b}/{a}' for _r, c, a, b in worst if _r > 0)}{tag}")

print("\n\nSOURCES THAT DID NOT ANSWER PROPERLY\n")
for guide, label, code, note in dead:
    print(f"  {guide:14} {label:28} {code}  {note}")
if not dead:
    print("  none")
