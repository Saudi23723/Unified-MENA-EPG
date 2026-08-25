#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alkass (الكأس) — Qatar's sports channels, from beIN's own guide.

Source: bein.com's public EPG endpoint, the one its own TV-guide page
calls, in both languages:

  https://www.bein.com/ar/epg-ajax-template/?action=epg_fetch&category=sports&cdate=YYYY-MM-DD&...
  https://www.bein.com/en/epg-ajax-template/?...   (postid 25356 instead of 25344)

Why this and not the epgshare feed this guide used before: audited against
this very endpoint, that feed matched beIN perfectly on Alkass 1, 2 and 4
(141 of 141 slots, time and title) and diverged badly on the rest —
Alkass 6 agreed on 7 slots out of 20. Five of the eight channels were
wrong. beIN is the broadcaster, so the guide now reads beIN directly and
the question of which to trust does not arise.

Two details this endpoint gets right that the feed did not:

  * every slot states its own start AND end, and they butt together with
    no gaps or overlaps, so nothing has to be inferred from the next
    programme's start.
  * times are plain Doha local ("2026-08-25 00:00:00") with no timezone
    label to misread. The feed stamped everything "+0100" whatever the
    channel's country, which is what made this guide two hours late.

Parsing: the page is scanned in document order rather than split on any
wrapper element. Each channel's logo (2023_Alkass_N.png) marks where its
slots begin, and every <li> after it belongs to that channel until the
next logo. The Arabic and English editions nest their rows differently,
so anything keyed on the wrapper works on one and silently collapses the
other onto a single channel.

Titles are shown in English with the Arabic kept alongside, paired by
start time. No Live badge: beIN does not mark which Alkass broadcasts are
live, so nothing here claims to.

Alkass 9, 10, 11 and the two SHOOF channels are not carried by this
endpoint and are not in this guide.
"""

from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, resolve_overlaps, run_main,
    utc_now, warn, write_xml_atomic,
)

OUTPUT = "alkass_epg.xml"
UTC = timezone.utc
DOHA = timezone(timedelta(hours=3))

ENDPOINT = ("https://www.bein.com/{lang}/epg-ajax-template/"
            "?action=epg_fetch&category=sports&cdate={date}&language={LANG}"
            "&loadindex=0&mins=00&offset=0&postid={postid}"
            "&serviceidentity=bein.net")
EDITIONS = {"ar": "25344", "en": "25356"}

# beIN publishes today plus three days; asking for more returns an empty page.
DAYS_FORWARD = 3

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

CHANNELS = [
    (1, "AlkassOne.qa", "Alkass 1", "الكأس 1", "alkass1"),
    (2, "AlkassTwo.qa", "Alkass 2", "الكأس 2", "alkass2"),
    (3, "AlkassThree.qa", "Alkass 3", "الكأس 3", "alkass3"),
    (4, "AlkassFour.qa", "Alkass 4", "الكأس 4", "alkass4"),
    (5, "AlkassFive.qa", "Alkass 5", "الكأس 5", "alkass5"),
    (6, "AlkassSix.qa", "Alkass 6", "الكأس 6", "alkass6"),
    (7, "AlkassSeven.qa", "Alkass 7", "الكأس 7", "alkass7"),
    (8, "AlkassEight.qa", "Alkass 8", "الكأس 8", "alkass8"),
]

# A channel logo or a programme row, matched together so document order
# decides which channel each row belongs to.
TOKEN_RE = re.compile(
    r"(?P<logo>/\d{4}_[A-Za-z0-9_]+\.png)"
    # `<li ...>` or a bare `<li>` - the row carries attributes on the live
    # pages, but requiring them would silently drop any that does not.
    r"|(?P<row><li(?:\s[^>]*?)?>.*?</li>)", re.S | re.I)
ALKASS_LOGO_RE = re.compile(r"/\d{4}_Alkass_(\d+)\.png", re.I)
RANGE_RE = re.compile(
    r"data-start='(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'\s+"
    r"data-end='(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'")
TITLE_RE = re.compile(r"<p class=title>(.*?)</p>", re.S)
FORMAT_RE = re.compile(r"<p class=format>(.*?)</p>", re.S)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


def parse_local(value: str) -> datetime | None:
    """beIN states plain Doha wall-clock, with no offset to misread."""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=DOHA)
    except ValueError:
        return None


def parse_page(text: str) -> dict[int, dict[datetime, dict]]:
    """{alkass number: {start: {stop, title, category}}} from one page."""
    out: dict[int, dict[datetime, dict]] = defaultdict(dict)
    current: int | None = None

    for m in TOKEN_RE.finditer(text or ""):
        if m.group("logo"):
            hit = ALKASS_LOGO_RE.match(m.group("logo"))
            # Any other channel's logo ends the Alkass block it followed.
            current = int(hit.group(1)) if hit else None
            continue
        if current is None:
            continue

        row = m.group("row")
        span = RANGE_RE.search(row)
        title = TITLE_RE.search(row)
        if not span or not title:
            continue
        start, stop = parse_local(span.group(1)), parse_local(span.group(2))
        text_title = clean(title.group(1))
        if start is None or stop is None or stop <= start or not text_title:
            continue

        fmt = FORMAT_RE.search(row)
        out[current][start] = {
            "stop": stop,
            "title": text_title,
            "category": clean(fmt.group(1)) if fmt else "",
        }
    return out


def fetch_edition(session, lang: str, days: list[str]) -> dict[int, dict[datetime, dict]]:
    """One language across every day, merged. Never raises: a day that
    fails costs that day only."""
    merged: dict[int, dict[datetime, dict]] = defaultdict(dict)
    ok = 0
    for date in days:
        url = ENDPOINT.format(lang=lang, LANG=lang.upper(),
                              postid=EDITIONS[lang], date=date)
        try:
            page = fetch(session, url).text
        except Exception as exc:
            warn(f"bein.com {lang} {date} failed: {exc}")
            continue
        got = parse_page(page)
        if got:
            ok += 1
        for n, slots in got.items():
            merged[n].update(slots)
    log(f"  {lang}: {ok}/{len(days)} days, "
        f"{sum(len(v) for v in merged.values())} slots across {len(merged)} channels")
    return merged


def build() -> int:
    log("ALKASS (الكأس) EPG | bein.com official guide, Arabic + English")
    session = new_session()
    now = utc_now()

    today = now.astimezone(DOHA)
    days = [(today + timedelta(days=d)).strftime("%Y-%m-%d")
            for d in range(0, DAYS_FORWARD + 1)]

    english = fetch_edition(session, "en", days)
    arabic = fetch_edition(session, "ar", days)

    if not english and not arabic:
        # write_xml_atomic keeps the previous file rather than publishing an
        # empty one, so a bad fetch costs nothing.
        write_xml_atomic(ET.Element("tv"), OUTPUT,
                         generator_name="Unified MENA EPG — Alkass")
        return 0

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Alkass"})
    with_data = [c for c in CHANNELS if english.get(c[0]) or arabic.get(c[0])]
    missing = [c[3] for c in CHANNELS if not (english.get(c[0]) or arabic.get(c[0]))]
    if missing:
        log(f"No schedule published for: {', '.join(missing)}")

    for _n, xid, en_name, ar_name, key in with_data:
        ch = ET.SubElement(root, "channel", id=xid)
        # English first: a player shows the first display-name it can use.
        ET.SubElement(ch, "display-name", lang="en").text = en_name
        ET.SubElement(ch, "display-name", lang="ar").text = ar_name
        ET.SubElement(ch, "icon", src=f"{LOGO_BASE}/{key}.png")

    total = paired = 0
    for n, xid, _en_name, _ar_name, _key in with_data:
        en_slots, ar_slots = english.get(n, {}), arabic.get(n, {})

        events = []
        for start in sorted(set(en_slots) | set(ar_slots)):
            en, ar = en_slots.get(start), ar_slots.get(start)
            primary = en or ar
            events.append({
                "start": start,
                "stop": primary["stop"],
                "title": primary["title"],
                "alt": ar["title"] if (en and ar) else "",
                "category": (ar or en).get("category", ""),
            })

        for ev in resolve_overlaps(events):
            if ev["alt"]:
                paired += 1
            add_programme(
                root, xid, ev["start"], ev["stop"], ev["title"],
                category=ev["category"] or "الرياضة",
                alt_titles=[("ar", ev["alt"])] if ev["alt"] else None,
            )
            total += 1

    log(f"Alkass: {len(with_data)}/{len(CHANNELS)} channels, {total} programmes, "
        f"{paired} with both languages")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Alkass")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
