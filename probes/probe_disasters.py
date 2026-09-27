#!/usr/bin/env python3
"""Ask the disaster feeds what they publish, before a reader is written.

A channel was asked for: storms, earthquakes, floods and the like, and
nothing else — not news, not sport. None of these sources is read
anywhere in this repository. This prints, for each: does it answer a
runner, in what shape, how many events, and how fresh the newest is.
It commits nothing.
"""
import json
import sys
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126 Safari/537.36",
      "Accept": "application/json, application/xml, text/xml, */*"}
NOW = datetime.now(timezone.utc)

PROBES = [
    ("USGS 4.5+ day", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"),
    ("USGS significant week", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"),
    ("GDACS events4app", "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP"),
    ("GDACS rss", "https://www.gdacs.org/xml/rss.xml"),
    ("GDACS search 7d", "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ;TC;FL;VO;DR;WF&alertlevel=Green;Orange;Red"),
    ("EONET open", "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=7"),
    ("ReliefWeb disasters", "https://api.reliefweb.int/v1/disasters?appname=unified-mena-epg&limit=10&sort[]=date:desc&profile=list"),
    ("EMSC fdsn", "https://www.seismicportal.eu/fdsnws/event/1/query?limit=20&minmag=4.5&format=json"),
    ("NHC current storms", "https://www.nhc.noaa.gov/CurrentStorms.json"),
    ("Smithsonian volcano rss", "https://volcano.si.edu/news/WeeklyVolcanoRSS.xml"),
]


def main() -> int:
    for name, url in PROBES:
        print(f"\n===== {name}\n{url}")
        try:
            r = requests.get(url, headers=UA, timeout=30)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue
        print(f"  {r.status_code} {r.headers.get('content-type')} {len(r.content)} bytes")
        text = r.text
        try:
            data = r.json()
        except Exception:
            print("  not json; head:")
            print("  " + text[:1500].replace("\n", "\n  "))
            continue
        # Show the structure and the first two items, whatever the shape.
        items = None
        if isinstance(data, dict):
            print(f"  keys: {list(data)[:15]}")
            for key in ("features", "events", "data", "activeStorms"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    print(f"  {key}: {len(items)} item(s)")
                    break
        elif isinstance(data, list):
            items = data
            print(f"  list of {len(items)}")
        for item in (items or [])[:3]:
            print("  ITEM " + json.dumps(item, ensure_ascii=False)[:1800])
        if items is None:
            print("  " + json.dumps(data, ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
