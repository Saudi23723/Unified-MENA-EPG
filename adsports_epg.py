#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AD Sports (Abu Dhabi Sports) — 1 / 2 / Premium / Extra.

Two independent sources feed this file, each clearly labelled in the logs
so it's obvious which channels are officially verified and which are
best-effort:

  1) AD SPORTS 1 HD — OFFICIAL. OSN (osn.com) republishes AD Sports 1 HD in
     its own public EPG API (`osn.com/apidata/...`), the same API the
     osn.com website itself uses. Request parameters are AES-256-CBC
     encrypted in a header, exactly like the live site does; the key/IV are
     embedded in osn.com's own public web bundle (not a secret — anyone's
     browser holds it to render the page), so this is just talking to a
     public API the same way any browser does. No data is invented.

  2) AD SPORTS 2 / PREMIUM / EXTRA — BEST-EFFORT. No public schedule API is
     known for these, so (like this repo's existing Jordan/ON-Sport
     scripts) we read confirmed football fixtures from LiveFootballTV.info
     per-channel pages. If a page doesn't exist or its layout changes, that
     channel simply gets 0 programmes for this run — it never breaks the
     other channels or crashes the workflow.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from epg_lib import (
    add_programme, fetch, log, new_session, norm, resolve_overlaps, run_main,
    utc_now, warn, write_xml_atomic,
)

OUTPUT = "adsports_epg.xml"
UTC = timezone.utc
ABU_DHABI = ZoneInfo("Asia/Dubai")

DAYS_BACK = 1
DAYS_FORWARD = 5


def in_window(dt: datetime, now: datetime) -> bool:
    """LiveFootballTV.info's per-channel pages also list historical
    fixtures going back a long time; without this, old matches (and
    unrelated dates colliding) leak into the guide and can overlap."""
    start = now - timedelta(days=DAYS_BACK)
    end = now + timedelta(days=DAYS_FORWARD + 1)
    return start <= dt < end

# ---------------------------------------------------------------------------
# 1) AD Sports 1 HD via OSN's public EPG API (official data)
# ---------------------------------------------------------------------------

OSN_CHANNEL_ID = "AD_Sports_1_HD"
OSN_CHANNEL_NAME = "AD Sports 1 HD"
OSN_GUID = "9069"  # osn.com internal channel guid for AD Sports 1 HD

OSN_SCHEDULE_URL = "https://www.osn.com/apidata/tv-schedule-timeline"

_CIPHER_KEY = bytes.fromhex(
    "65a04b9b5591f27c837fac433274b494403e0eec5b43698060c28e1162d4460f"
)
_CIPHER_IV = bytes.fromhex("b7cc0a48d6d023bc1a2a670953ec5622")


def _osn_encrypt(payload: str) -> str:
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    data = padder.update(payload.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(_CIPHER_KEY), modes.CBC(_CIPHER_IV))
    encryptor = cipher.encryptor()
    ct = encryptor.update(data) + encryptor.finalize()
    return base64.b64encode(ct).decode("ascii")


def _osn_decrypt(b64: str) -> str:
    ct = base64.b64decode(b64)
    cipher = Cipher(algorithms.AES(_CIPHER_KEY), modes.CBC(_CIPHER_IV))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    data = unpadder.update(padded) + unpadder.finalize()
    return data.decode("utf-8")


def fetch_osn_ad_sports_day(session, day_start_utc: datetime) -> list[dict]:
    day_end_utc = day_start_utc + timedelta(days=1)
    start_ms = int(day_start_utc.timestamp() * 1000)
    end_ms = int(day_end_utc.timestamp() * 1000)

    payload = {
        "channelGuid": OSN_GUID,
        "startTime": start_ms,
        "endTime": end_ms,
    }
    headers = {
        "X-Encrypted-Data": _osn_encrypt(json.dumps(payload)),
        "Referer": "https://www.osn.com/",
        "Origin": "https://www.osn.com",
        "Accept": "application/json, text/plain, */*",
    }
    url = f"{OSN_SCHEDULE_URL}?t=batch1-time{start_ms}-{end_ms}-boxAndroid"

    r = fetch(session, url, headers=headers)
    raw = r.json()
    if isinstance(raw, dict) and raw.get("encrypted"):
        raw = json.loads(_osn_decrypt(raw["encrypted"]))

    events: list[dict] = []
    for entry in raw.get("entries", []) or []:
        if str(entry.get("guid")) != OSN_GUID:
            continue
        for listing in entry.get("listings", []) or []:
            try:
                start = datetime.fromtimestamp(int(listing["startTime"]) / 1000, tz=UTC)
                stop = datetime.fromtimestamp(int(listing["endTime"]) / 1000, tz=UTC)
            except Exception:
                continue
            if stop <= start:
                continue
            program = listing.get("program", {}) or {}
            title = (
                (program.get("titleLocalized") or {}).get("ar")
                or (program.get("titleLocalized") or {}).get("en")
                or ""
            ).strip() or OSN_CHANNEL_NAME
            desc = (
                (program.get("descriptionLocalized") or {}).get("ar")
                or (program.get("descriptionLocalized") or {}).get("en")
                or ""
            ).strip()
            events.append({"start": start, "stop": stop, "title": title, "desc": desc})
    return events


def collect_osn_ad_sports_1(session) -> list[dict]:
    events: list[dict] = []
    today = utc_now().astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    ok_days = 0
    for offset in range(-DAYS_BACK, DAYS_FORWARD + 1):
        day_start = today + timedelta(days=offset)
        try:
            day_events = fetch_osn_ad_sports_day(session, day_start)
            if day_events:
                ok_days += 1
            events.extend(day_events)
        except Exception as exc:
            warn(f"AD Sports 1 (OSN) day {day_start.date()} failed: {exc}")
    log(f"AD Sports 1 HD (OSN official): {ok_days} days OK, {len(events)} programmes")
    return events


# ---------------------------------------------------------------------------
# 2) AD Sports 2 / Premium / Extra via LiveFootballTV.info (best-effort)
# ---------------------------------------------------------------------------

LFTV_INDEX = "https://www.livefootballtv.info/channel"

# LiveFootballTV.info's own slugs for the AD Sports family are not
# consistently named (e.g. "abu-dhabi-sports-1" but "ad-sports-premium-1"),
# so instead of hardcoding guesses we discover the real slugs by reading
# the site's own channel index and matching on the visible channel name.
# "Asia" feeds are excluded — they're a different regional simulcast, not
# the UAE AD Sports 1/2/Premium/Extra channels that were asked for.
AD_SPORTS_NAME_RE = re.compile(
    r"^(?:ad|abu\s*dhabi)\s*sports\s*"
    r"(?P<variant>\d+|premium(?:\s*\d+)?|extra(?:\s*\d+)?)$",
    re.I,
)


def discover_ad_sports_channels(session) -> dict[str, tuple[str, str]]:
    """xmltv_id -> (display_name, page_url), discovered from the live index."""
    r = fetch(session, LFTV_INDEX)
    soup = BeautifulSoup(r.text, "html.parser")

    found: dict[str, tuple[str, str]] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/channel/" not in href:
            continue
        label = norm(a.get_text(" ", strip=True))
        if not label or "asia" in label.casefold():
            continue
        if not AD_SPORTS_NAME_RE.match(label):
            continue

        url = href if href.startswith("http") else f"https://www.livefootballtv.info{href}"
        xid = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
        found[xid] = (label, url)

    return found

DATE_NUMERIC = re.compile(
    r"(?:(?:today|tomorrow)\s+)?"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*"
    r"(\d{1,2})/(\d{1,2})/(20\d{2})",
    re.I,
)
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
BAD_TEXT = re.compile(
    r"^(?:live football on|football on tv|change to your time zone|"
    r"ranking by|statistical data|number of|view full ranking|"
    r"as of today|in this moment|the next match|"
    r"image:|button:|menu|teams|competitions|tv channels|news|free widget|"
    r"arab mena|all teams|all competitions|all channels|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    re.I,
)
STAGE_TEXT = re.compile(
    r"^(?:playoffs?|final|semi-?finals?|quarter-?finals?|"
    r"group stage|round of \d+|qualifiers?|friendly)$",
    re.I,
)
BROADCASTER_HINTS = re.compile(
    r"(?:sport|sports|tv|youtube|app|bein|dazn|alkass|الكأس|ssc|ppv)", re.I,
)
MATCH_MINUTES = 135


def _clean_line(s: str) -> str:
    return re.sub(r"^Image:\s*", "", norm(s), flags=re.I)


def _plausible(s: str) -> bool:
    if not s or len(s) > 80:
        return False
    if BAD_TEXT.search(s) or TIME_RE.match(s) or s.isdigit():
        return False
    return True


def _extract_match_block(block: list[str], channel_name: str) -> tuple[str, str, str] | None:
    cleaned = [_clean_line(x) for x in block]
    cleaned = [x for x in cleaned if x and _plausible(x)]

    own_idx = next(
        (i for i, x in enumerate(cleaned) if x.casefold() == channel_name.casefold()),
        None,
    )
    if own_idx is None:
        return None

    first_broadcaster = next(
        (i for i, x in enumerate(cleaned[:own_idx + 1]) if BROADCASTER_HINTS.search(x)),
        own_idx,
    )
    core = cleaned[:first_broadcaster]
    if len(core) < 3:
        core = [x for x in cleaned[:own_idx] if not BROADCASTER_HINTS.search(x)]
    if len(core) < 3:
        return None

    non_stage = [x for x in core if not STAGE_TEXT.match(x)]
    if len(non_stage) < 3:
        return None

    home, away = non_stage[-2], non_stage[-1]
    competition = non_stage[-3]
    if home.casefold() == away.casefold():
        return None
    if BROADCASTER_HINTS.search(home) or BROADCASTER_HINTS.search(away):
        return None
    return norm(competition), norm(home), norm(away)


def parse_lftv_channel(html: str, channel_name: str, source_url: str, now: datetime | None = None) -> list[dict]:
    now = now or utc_now()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = [norm(x) for x in soup.stripped_strings if norm(x)]
    events: list[dict] = []
    current_date: date | None = None

    i = 0
    while i < len(lines):
        m = DATE_NUMERIC.search(lines[i])
        if m:
            dd, mm, yy = map(int, m.groups())
            try:
                current_date = date(yy, mm, dd)
            except ValueError:
                current_date = None
            i += 1
            continue

        tm = TIME_RE.match(lines[i])
        if not tm or current_date is None:
            i += 1
            continue

        hh, mm = map(int, tm.groups())
        block: list[str] = []
        j = i + 1
        while j < len(lines) and j <= i + 30:
            if TIME_RE.match(lines[j]) or DATE_NUMERIC.search(lines[j]):
                break
            block.append(lines[j])
            j += 1

        parsed = _extract_match_block(block, channel_name)
        if parsed:
            competition, home, away = parsed
            local = datetime(current_date.year, current_date.month, current_date.day, hh, mm, tzinfo=ABU_DHABI)
            start_utc = local.astimezone(UTC)
            # LiveFootballTV.info's per-channel pages also list historical
            # fixtures far in the past — skip anything outside our window.
            if in_window(start_utc, now):
                events.append({
                    "start": start_utc,
                    "stop": start_utc + timedelta(minutes=MATCH_MINUTES),
                    "title": f"{home} - {away}",
                    "desc": competition,
                    "source": source_url,
                })

        i = max(i + 1, j)

    return resolve_overlaps(events)


# Last-known-good fallback if the index page itself can't be reached —
# still best-effort, still gracefully degrades to 0 events if wrong/stale.
FALLBACK_LFTV_CHANNELS = {
    "AD_Sports_1": ("AD Sports 1", "https://www.livefootballtv.info/channel/abu-dhabi-sports-1"),
    "AD_Sports_Premium_1": ("AD Sports Premium 1", "https://www.livefootballtv.info/channel/ad-sports-premium-1"),
}


def collect_lftv_ad_sports(session, now: datetime):
    try:
        channels = discover_ad_sports_channels(session)
        if channels:
            log(f"AD Sports (LiveFootballTV index): discovered {len(channels)} channels -> "
                f"{[n for n, _ in channels.values()]}")
        else:
            raise ValueError("index discovery returned no matches")
    except Exception as exc:
        warn(f"AD Sports LiveFootballTV index discovery failed, using fallback list: {exc}")
        channels = FALLBACK_LFTV_CHANNELS

    # AD Sports 1 is already covered officially via OSN above; skip it here
    # to avoid duplicate/conflicting programmes for the same channel.
    channels = {
        xid: (name, url) for xid, (name, url) in channels.items()
        if re.sub(r"[^a-z0-9]", "", name.lower()) not in {"adsports1", "abudhabisports1"}
    }

    out: dict[str, list[dict]] = {}
    for xid, (name, url) in channels.items():
        try:
            r = fetch(session, url)
            events = parse_lftv_channel(r.text, name, url, now)
            out[xid] = events
            log(f"{name} (LiveFootballTV best-effort): {len(events)} fixtures")
        except Exception as exc:
            warn(f"{name} (LiveFootballTV) failed — 0 programmes this run: {exc}")
            out[xid] = []
    return out, channels


# ---------------------------------------------------------------------------

def build() -> int:
    log("AD SPORTS EPG | AD Sports 1 = official OSN API | others = best-effort LiveFootballTV (auto-discovered)")
    session = new_session()
    now = utc_now()

    lftv_events, lftv_channels = collect_lftv_ad_sports(session, now)

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — AD Sports"})

    ch = ET.SubElement(root, "channel", id=OSN_CHANNEL_ID)
    ET.SubElement(ch, "display-name", lang="en").text = OSN_CHANNEL_NAME
    for xid, (name, _url) in lftv_channels.items():
        ch = ET.SubElement(root, "channel", id=xid)
        ET.SubElement(ch, "display-name", lang="en").text = name

    total = 0

    try:
        osn_events = collect_osn_ad_sports_1(session)
    except Exception as exc:
        warn(f"AD Sports 1 (OSN) collection failed entirely: {exc}")
        osn_events = []

    for ev in resolve_overlaps(osn_events):
        add_programme(
            root, OSN_CHANNEL_ID, ev["start"], ev["stop"], ev["title"], ev["desc"],
            category="Sports", live_eligible=True, now=now,
        )
        total += 1

    for xid, events in lftv_events.items():
        for ev in events:
            add_programme(
                root, xid, ev["start"], ev["stop"], ev["title"], ev["desc"],
                category="Sports", live_eligible=True, now=now,
            )
            total += 1

    log(f"AD Sports: {total} programmes total across {1 + len(lftv_channels)} channels")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — AD Sports")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
