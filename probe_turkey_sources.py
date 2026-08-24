#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: find a reachable, trustworthy Turkish source for the
beIN Sports Türkiye guide, now that digiturk.com.tr answers 403 to us.

Candidates were picked from the iptv-org/epg grabber set (the sources that
project keeps tested), preferring ones that actually carry all eight beIN
Sports TR channels. Runs on GitHub Actions; deleted once a winner is chosen.
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

ISTANBUL = ZoneInfo("Europe/Istanbul")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)


def show(label, resp, body_head=400):
    print(f"\n{'='*72}\n{label}\n{'='*72}")
    if resp is None:
        return
    print(f"  status={resp.status_code}  len={len(resp.content)}  "
          f"ctype={resp.headers.get('content-type')}  server={resp.headers.get('server')}")
    try:
        text = resp.text
    except Exception:
        text = ""
    print("  head:", text[:body_head].replace("\n", " "))


def get(url, label, headers=None):
    try:
        r = requests.get(url, headers=headers or {"User-Agent": UA}, timeout=30)
    except Exception as exc:
        print(f"\n{'='*72}\n{label}\n{'='*72}\n  REQUEST FAILED: {exc}")
        return None
    show(label, r)
    return r


# ---------------------------------------------------------------- tvprofil
def tvprofil_query(site_id: str, datum: str) -> str:
    """Port of the token the site's own JS builds before it will answer."""
    c = 4
    a = f"{datum}{site_id}{c}"
    ua = f"{site_id}{datum}"
    for ch in ua:
        c += ord(ch)
    b = 2
    for i in range(len(a) - 1, -1, -1):
        b += (ord(a[i]) + c * 2) * i
    b = str(b)
    last = ord(b[-1])
    from urllib.parse import urlencode
    return urlencode({
        "datum": datum,
        "kanal": site_id,
        "callback": f"tvprogramit{last}",
        f"b{last}": b,
    })


def probe_tvprofil():
    datum = datetime.now(ISTANBUL).strftime("%Y-%m-%d")
    headers = {
        "x-requested-with": "XMLHttpRequest",
        "user-agent": UA,
        "referer": "https://tvprofil.com/tvprogram/",
        "accept": "text/javascript, application/javascript, application/ecmascript,"
                  " application/x-ecmascript, */*; q=0.01",
    }
    for kanal in ("bein-sports-1-tr", "bein-sports-max-1-tr"):
        url = f"https://tvprofil.com/tr/program/?{tvprofil_query(kanal, datum)}"
        r = get(url, f"A) tvprofil.com  {kanal}  {datum}", headers=headers)
        if r is None or r.status_code != 200:
            continue
        m = re.match(r"^[^(]+\(([\s\S]*)\)$", r.text.strip())
        if not m:
            print("  !! not JSONP")
            continue
        try:
            data = json.loads(m.group(1))
        except Exception as exc:
            print(f"  !! bad JSON: {exc}")
            continue
        html = (data.get("data") or {}).get("program") or ""
        rows = re.findall(r'data-ts="(\d+)"[^>]*data-len="(\d+)"', html)
        rows2 = re.findall(r'data-ts="(\d+)"', html)
        print(f"  JSONP OK. program html len={len(html)}  "
              f"rows(ts+len)={len(rows)}  rows(ts)={len(rows2)}")
        titles = re.findall(r'<div class="col[^"]*">\s*<a[^>]*>([^<]{3,60})</a>', html)
        print(f"  sample titles: {titles[:6]}")
        print("  html head:", html[:500].replace("\n", " "))

    get("https://tvprofil.com/tr/channels/getChannels/?callback=cb",
        "B) tvprofil.com channel list (tr)", headers=headers)


def probe_turksat():
    dd = datetime.now(ISTANBUL).strftime("%d")
    r = get(f"https://www.turksatkablo.com.tr/userUpload/EPG/{dd}.json",
            f"C) turksatkablo.com.tr static JSON ({dd}.json)")
    if r is not None and r.status_code == 200:
        try:
            data = r.json()
        except Exception as exc:
            print(f"  !! bad JSON: {exc}")
            return
        chans = data.get("k") or []
        print(f"  channels={len(chans)}")
        for c in chans:
            if "BEIN" in str(c.get("n", "")).upper() or "SPOR" in str(c.get("n", "")).upper():
                print(f"    id={c.get('x')!r:8} name={c.get('n')!r:28} programmes={len(c.get('p') or [])}")


def probe_epgshare():
    r = None
    url = "https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    except Exception as exc:
        print(f"\n{'='*72}\nD) epgshare01.online TR1\n{'='*72}\n  REQUEST FAILED: {exc}")
        return
    print(f"\n{'='*72}\nD) epgshare01.online TR1\n{'='*72}")
    print(f"  status={r.status_code}  len={len(r.content)}  ctype={r.headers.get('content-type')}")
    if r.status_code != 200:
        print("  head:", r.text[:300])
        return
    try:
        xml = gzip.decompress(r.content).decode("utf-8", "replace")
    except Exception as exc:
        print(f"  !! gunzip failed: {exc}")
        return
    print(f"  decompressed={len(xml)}  channels={xml.count('<channel ')}  "
          f"programmes={xml.count('<programme ')}")
    for cid in re.findall(r'<channel id="([^"]*[Bb][Ee][Ii][Nn][^"]*)"', xml):
        n = xml.count(f'channel="{cid}"')
        print(f"    {cid:44} programmes={n}")


def probe_others():
    get("https://www.beinsports.com.tr/yayin-akisi", "E) beinsports.com.tr (official TR site)")
    get("https://www.digiturk.com.tr/yayin-akisi", "F) digiturk.com.tr control (expect 403)")
    get("https://www.tvyayinakisi.com/bein-sports-1", "G) tvyayinakisi.com")
    get("https://www.canlitv.me/yayin-akisi", "H) canlitv.me")
    get("https://www.tvplus.com.tr/canli-tv-izle", "I) tvplus.com.tr (Turkcell)")


def main():
    probe_tvprofil()
    probe_turksat()
    probe_epgshare()
    probe_others()


if __name__ == "__main__":
    main()
