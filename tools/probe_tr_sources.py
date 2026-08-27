#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hunt for a Turkish source that schedules tabii Spor 1-10 and beIN SPORTS
Türkiye more than one day ahead.

Two channels sets are short today:

  tabii Spor 1..10   nothing at all beyond the current day
  beIN SPORTS 1      27 programmes today, none tomorrow
  beIN SPORTS MAX 1/2   the same

beIN SPORTS HABER carries a full week from the same site, so this is not
a site-wide limit — it is per channel, and a different source may not
share it. epgshare01 is already read here as filler for beIN; whether it
also carries tabii has never been checked, and that is the first thing
asked below.

Every request goes to a public endpoint. Nothing here signs in, and no
paywall is involved: a listings feed is published to be read.

Prints only; writes nothing.
"""

from __future__ import annotations

import gzip
import io
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

TR = timezone(timedelta(hours=3))
TODAY = datetime.now(TR).date()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")

WANTED = re.compile(r"tab(?:i|İ|ı)i|bein", re.I)


def get(session, url, **kw):
    return session.get(url, timeout=40, headers={"User-Agent": UA}, **kw)


def report_xmltv(label: str, raw: bytes) -> None:
    """Per-channel day coverage for every tabii/beIN channel in a feed."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    try:
        root = ET.parse(io.BytesIO(raw)).getroot()
    except Exception as exc:
        print(f"    not parseable as XMLTV: {exc}")
        return

    names = {}
    for channel in root.findall("channel"):
        display = " / ".join(d.text or "" for d in channel.findall("display-name"))
        names[channel.get("id")] = display

    per = defaultdict(lambda: defaultdict(int))
    for programme in root.findall("programme"):
        cid = programme.get("channel")
        try:
            when = datetime.strptime(programme.get("start"),
                                     "%Y%m%d%H%M%S %z").astimezone(TR).date()
        except Exception:
            continue
        per[cid][when] += 1

    hits = [cid for cid in names
            if WANTED.search(cid) or WANTED.search(names[cid])]
    print(f"    {len(names)} channels, {len(root.findall('programme'))} programmes")
    if not hits:
        print("    no tabii / beIN channel in this feed")
        return

    print(f"    {len(hits)} tabii/beIN channel(s):")
    for cid in sorted(hits):
        days = sorted(per[cid])
        ahead = [d for d in days if d > TODAY]
        span = f"{days[0]}..{days[-1]}" if days else "no programmes"
        print(f"      {cid:<34} {sum(per[cid].values()):>5} progs  "
              f"{span}  ahead={len(ahead)}d  | {names[cid][:44]}")


def probe_feed(session, label: str, url: str) -> None:
    print(f"\n[{label}] {url}")
    try:
        response = get(session, url)
    except Exception as exc:
        print(f"    ERROR {type(exc).__name__}: {exc}")
        return
    print(f"    http={response.status_code} bytes={len(response.content)}")
    if response.status_code != 200 or not response.content:
        return
    report_xmltv(label, response.content)


def probe_page(session, label: str, url: str) -> None:
    """A plain page: does it answer, and does it name what we want?"""
    print(f"\n[{label}] {url}")
    try:
        response = get(session, url)
    except Exception as exc:
        print(f"    ERROR {type(exc).__name__}: {exc}")
        return
    text = response.text or ""
    numbered = sorted({m.group(0).strip().lower()
                       for m in re.finditer(
                           r"tab(?:i|İ|ı)i?\s*spor\s*\d{1,2}", text, re.I)})
    beins = sorted({m.group(0).strip().lower()
                    for m in re.finditer(
                        r"bein\s*sports?\s*(?:max\s*)?\d", text, re.I)})
    dates = sorted({d for d in re.findall(r"20\d{2}-\d{2}-\d{2}", text)
                    if d > TODAY.isoformat()})[:6]
    print(f"    http={response.status_code} bytes={len(response.content)} "
          f"ctype={response.headers.get('content-type','?')[:40]}")
    print(f"      numbered tabii : {numbered or '—'}")
    print(f"      beIN named     : {beins[:8] or '—'}")
    print(f"      future dates   : {dates or '—'}")


def main() -> int:
    print(f"Turkish source hunt | today={TODAY} (TR)")
    session = requests.Session()

    print("\n" + "=" * 72)
    print("1. epgshare01 — already read as beIN filler; does it carry tabii?")
    print("=" * 72)
    for name in ("TR1", "TR2", "TR3"):
        probe_feed(session, f"epgshare {name}",
                   f"https://epgshare01.online/epgshare01/"
                   f"epg_ripper_{name}.xml.gz")
    probe_page(session, "epgshare index", "https://epgshare01.online/epgshare01/")

    print("\n" + "=" * 72)
    print("2. Other public XMLTV feeds that cover Türkiye")
    print("=" * 72)
    for label, url in [
        ("iptv-org TR", "https://iptv-org.github.io/epg/guides/tr.xml"),
        ("open-epg TR", "https://www.open-epg.com/files/turkey1.xml"),
        ("open-epg TR2", "https://www.open-epg.com/files/turkey2.xml"),
        ("open-epg TR3", "https://www.open-epg.com/files/turkey3.xml"),
        ("open-epg TR4", "https://www.open-epg.com/files/turkey4.xml"),
    ]:
        probe_feed(session, label, url)

    print("\n" + "=" * 72)
    print("3. Operator and broadcaster guides")
    print("=" * 72)
    for label, url in [
        ("beIN TR site", "https://www.beinsports.com.tr/yayin-akisi"),
        ("beIN TR api", "https://www.beinsports.com.tr/api/yayin-akisi"),
        ("Digiturk guide", "https://www.digiturk.com.tr/yayin-akisi"),
        ("TV+ (Turkcell)", "https://tvplus.com.tr/canli-tv"),
        ("Vodafone TV", "https://vodafonetv.com.tr/canli-tv"),
        ("tvarsivi", "https://www.tvarsivi.com/"),
        ("canlitv rehber", "https://www.canlitv.com/yayin-akisi"),
        ("tvyayinakisi index", "https://www.tvyayinakisi.com/"),
        ("tvyayinakisi tabii", "https://www.tvyayinakisi.com/tabii-spor-yayin-akisi/"),
        ("tvyayinakisi bein1", "https://www.tvyayinakisi.com/bein-sports-1-yayin-akisi/"),
    ]:
        probe_page(session, label, url)

    return 0


if __name__ == "__main__":
    sys.exit(main())
