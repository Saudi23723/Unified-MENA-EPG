#!/usr/bin/env python3
"""Temporary structural probe — run on GitHub Actions (unrestricted network)
to inspect real markup this sandbox can't reach directly. Removed once done."""
import json
import sys
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}


def probe_satTV():
    print("=" * 20, "SAT.TV PROBE", "=" * 20)
    url = "https://www.sat.tv/wp-content/themes/twentytwenty-child/ajax_chaines.php"
    import datetime
    today = datetime.date.today()
    data = {
        "dateFiltre": today.strftime("%Y-%m-%d"),
        "hoursFiltre": "0",
        "satLineup": "38",
        "satSatellite": "1",
        "userDateTime": str(int(datetime.datetime.now().timestamp() * 1000)),
        "userTimezone": "Europe/London",
    }
    headers = dict(HEADERS)
    headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    headers["Cookie"] = "pll_language=ar"
    r = requests.post(url, data=data, headers=headers, timeout=20)
    print("status", r.status_code, "len", len(r.text))
    print(r.text[:6000])
    print("...")
    print(r.text[-3000:])


def probe_roya():
    print("=" * 20, "ROYA PROBE", "=" * 20)
    url = "https://backend.roya.tv/api/v01/channels/schedule-pagination"
    for day in [0, 1, 2, -1]:
        r = requests.get(url, params={"day_number": day}, headers=HEADERS, timeout=20)
        try:
            data = r.json()
        except Exception as exc:
            print("day", day, "FAILED", exc, r.text[:500])
            continue
        days = data.get("data", [])
        names = set()
        for d in days:
            for ch in d.get("channel", []):
                names.add((ch.get("id"), ch.get("title")))
        print(f"day={day} channels={sorted(names)}")


def probe_aljazeera():
    print("=" * 20, "AL JAZEERA PROBE", "=" * 20)
    r = requests.get("https://www.aljazeera.net/schedule", headers=HEADERS, timeout=20)
    print("status", r.status_code, "len", len(r.text))
    idx = r.text.find('__NEXT_DATA__')
    print("has __NEXT_DATA__:", idx != -1)
    if idx != -1:
        print(r.text[idx:idx + 2000])


def probe_alarabiya():
    print("=" * 20, "AL ARABIYA PROBE", "=" * 20)
    for url in [
        "https://www.alarabiya.net/schedule",
        "https://english.alarabiya.net/schedule",
        "https://www.alarabiya.net/ar/schedule.html",
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            print(url, "->", r.status_code, len(r.text))
        except Exception as exc:
            print(url, "-> FAILED", exc)


def probe_almayadeen():
    print("=" * 20, "AL MAYADEEN PROBE", "=" * 20)
    for url in [
        "https://www.almayadeen.net/schedule",
        "https://www.almayadeen.net/live",
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            print(url, "->", r.status_code, len(r.text))
        except Exception as exc:
            print(url, "-> FAILED", exc)


if __name__ == "__main__":
    probe_aljazeera()
    probe_alarabiya()
    probe_almayadeen()
