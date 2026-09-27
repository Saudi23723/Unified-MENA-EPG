"""Ask every source behind the six guides that stopped updating what it
answers from a GitHub runner — status, size, title, and a sample — so the
reason each one collapsed can be read off one log.

It commits nothing and publishes nothing.
"""

import re
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

today = date.today()
tomorrow = today + timedelta(days=1)

SOURCES = {
    "Alwan": ["https://t.me/s/AlwanSports"],
    "Fajer": ["https://t.me/s/fajersport", "https://www.livefootballtv.info/"],
    "Shahid": [
        "https://www.livesoccertv.com/channels/shahid/",
        "https://www.livefootballtv.info/channel/mbc-shahid-sports",
        "https://www.365scores.com/ar/news/magazine/",
        "https://www.kooora.com/",
    ],
    "Shasha": [
        "https://www.oddalerts.com/leagues/kuwait/zain-premier-league/fixtures",
        "https://www.fotmob.com/api/leagues?id=529&ccode3=KWT&season=2026%2F2027",
        "https://www.legaseriea.it/lega-serie-a/documentazione",
        "https://www.kswmma.com/en",
    ],
    "tabii": [
        "https://www.trtspor.com.tr/yayin-akisi/tabii-spor",
        "https://www.tvyayinakisi.com/tabii-spor-yayin-akisi/",
        "https://www.sporekrani.com/",
    ],
    "Thmanyah": [
        "https://t.me/s/matches_today2",
        f"https://www.yallakora.com/matches-center?date={today:%m/%d/%Y}",
        f"https://www.yallakora.com/match-center/?date={today:%m/%d/%Y}",
        "https://www.filgoal.com/matches/",
        "https://www.masrawy.com/sports",
        "https://elgoal.net/",
        "https://www.365scores.com/ar/where-to-watch",
    ],
}

KEYWORDS = ["ثمانية", "Thmanyah", "شاهد", "Shahid", "شاشا", "Shasha",
            "tabii", "ألوان", "Alwan", "فجر", "Fajer"]


def telegram(soup):
    posts = soup.select(".tgme_widget_message_wrap")
    print(f"   telegram posts on page: {len(posts)}")
    for post in posts[-6:]:
        when = post.select_one("time")
        text = post.select_one(".tgme_widget_message_text")
        photo = bool(post.select(".tgme_widget_message_photo_wrap"))
        body = re.sub(r"\s+", " ", text.get_text(" ")) if text else ""
        print(f"   - {when.get('datetime') if when else '?'} "
              f"photo={photo} | {body[:220]}")


for guide, urls in SOURCES.items():
    print(f"\n{'=' * 70}\n{guide}\n{'=' * 70}")
    for url in urls:
        try:
            r = requests.get(url, headers={"User-Agent": UA,
                                           "Accept-Language": "ar,en;q=0.8"},
                             timeout=30)
        except Exception as exc:
            print(f"-- {url}\n   FAILED: {exc}")
            continue
        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        blocked = any(k in html for k in ("cf-chl", "Just a moment",
                                          "Attention Required", "captcha"))
        print(f"-- {url}\n   {r.status_code} -> {r.url} | {len(html)} bytes | "
              f"title={title[:90]!r} | challenge={blocked}")
        hits = {k: html.count(k) for k in KEYWORDS if k in html}
        print(f"   keyword hits: {hits}")
        if "t.me/" in url:
            telegram(soup)
        else:
            text = re.sub(r"\s+", " ", soup.get_text(" "))
            print(f"   text sample: {text[:400]}")
