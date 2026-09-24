"""What Shasha's sources answer from a runner: ESPN's Serie A and Kuwaiti
league feeds, and the PDFs Lega Serie A lists. Commits nothing."""

import re
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
today = date.today()

print("=== ESPN Serie A (ita.1), next 10 days")
for base in ("https://site.api.espn.com", "https://site.web.api.espn.com"):
    url = f"{base}/apis/site/v2/sports/soccer/ita.1/scoreboard"
    total = 0
    for i in range(10):
        d = today + timedelta(days=i)
        try:
            j = requests.get(url, params={"dates": d.strftime("%Y%m%d")},
                             headers=UA, timeout=20).json()
        except Exception as exc:
            print(f"  {base} {d}: FAILED {exc}")
            continue
        for ev in j.get("events") or []:
            total += 1
            c = (ev.get("competitions") or [{}])[0]
            sides = {s.get("homeAway"): (s.get("team") or {}).get("displayName")
                     for s in c.get("competitors") or []}
            st = ((ev.get("status") or {}).get("type") or {}).get("state")
            print(f"  {ev.get('date')}  {sides.get('home')} - {sides.get('away')}"
                  f"  state={st} timeValid={c.get('timeValid')}")
    print(f"  {base}: {total} event(s)")
    if total:
        break

print("\n=== ESPN Kuwait candidates")
for slug in ("kuw.1", "kwt.1", "kuw.premier"):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
    try:
        r = requests.get(url, headers=UA, timeout=20)
        j = r.json() if r.ok else {}
        lg = (j.get("leagues") or [{}])[0]
        print(f"  {slug}: {r.status_code} league={lg.get('name')!r} "
              f"events={len(j.get('events') or [])} "
              f"calendar={str(lg.get('calendar'))[:120]}")
    except Exception as exc:
        print(f"  {slug}: FAILED {exc}")

print("\n=== Lega Serie A documentazione PDFs")
try:
    html = requests.get("https://www.legaseriea.it/lega-serie-a/documentazione",
                        headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    pdfs = [(a.get_text(" ", strip=True)[:90], a["href"]) for a in soup.find_all("a", href=True)
            if ".pdf" in a["href"].lower()]
    print(f"  {len(pdfs)} pdf link(s)")
    for label, href in pdfs[:40]:
        print(f"  - {label!r} -> {href[:140]}")
    for m in sorted(set(re.findall(r"https?://[^\"' ]+\.pdf", html)))[:20]:
        print(f"  raw: {m[:160]}")
except Exception as exc:
    print(f"  FAILED {exc}")
