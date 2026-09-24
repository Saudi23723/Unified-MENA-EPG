"""Which of Lega Serie A's listed PDFs carry a fixture table this repo's
parser can read, and what OddAlerts shows for the Kuwaiti league.
Commits nothing."""

import re
from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
# The exact row pattern update_shasha_epg._parse_lega_pdf uses.
ROW = re.compile(
    r"(\d{2}/\d{2}/20\d{2})\s+"
    r"[A-Za-zÀ-ÿ]+\s+"
    r"(\d{1,2}[.:]\d{2})\s+"
    r"([A-Za-zÀ-ÿ\'’ .]+?)\s*-\s*"
    r"([A-Za-zÀ-ÿ\'’ .]+?)\s*(?:\*{1,3})?\s+"
    r"(?:DAZN(?:/SKY)?|SKY)",
    re.I,
)
now = datetime.now(timezone.utc)
rome = ZoneInfo("Europe/Rome")

html = requests.get("https://www.legaseriea.it/lega-serie-a/documentazione",
                    headers=UA, timeout=30).text
urls = sorted(set(re.findall(
    r"https://images\.legaseriea\.it/image/private/fl_attachment/prd/[a-z0-9]+\.pdf", html)))
print(f"=== {len(urls)} PDF(s) listed")
for url in urls:
    try:
        r = requests.get(url, headers=UA, timeout=40)
        text = "\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(r.content)).pages)
    except Exception as exc:
        print(f"- {url[-24:]}: FAILED {exc}")
        continue
    rows = ROW.findall(text)
    future = []
    for d, t, h, a in rows:
        try:
            hh, mm = map(int, re.split(r"[.:]", t))
            dd = datetime.strptime(d, "%d/%m/%Y")
            when = datetime(dd.year, dd.month, dd.day, hh, mm, tzinfo=rome)
        except ValueError:
            continue
        if when > now:
            future.append(f"{when:%Y-%m-%d %H:%M} {h.strip()} - {a.strip()}")
    head = re.sub(r"\s+", " ", text[:160])
    print(f"- {url[-24:]}: {len(r.content)//1024} KB, {len(rows)} row(s), "
          f"{len(future)} still to come | {head!r}")
    for f in future[:12]:
        print(f"      {f}")

print("\n=== OddAlerts Zain Premier League")
soup = BeautifulSoup(requests.get(
    "https://www.oddalerts.com/leagues/kuwait/zain-premier-league/fixtures",
    headers=UA, timeout=30).text, "html.parser")
text = re.sub(r"\s+", " ", soup.get_text(" "))
i = text.find("Fixtures", 400)
print(text[i:i + 1500])
