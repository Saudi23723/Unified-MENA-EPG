#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared, hardened helpers for every EPG generator script in this repository.

Design goals (applies to every script that imports this module):
  - Never crash the whole run because one source failed (network error,
    schema change, empty response). Log a WARN and continue.
  - Never overwrite a previously good XMLTV file with an empty/broken one.
  - Always write atomically (write to .tmp, validate, os.replace).
  - Always produce valid, non-overlapping XMLTV programmes.
  - Mark events that are happening right now with a "Live" suffix so
    TiviMate (and any XMLTV client) shows it at a glance.
"""

from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape

import requests

UTC = timezone.utc

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

HTTP_TIMEOUT = 20
HTTP_RETRIES = 3
HTTP_BACKOFF = 2.0

# Suffix appended to the title of a programme that is airing right now.
# Kept as a single constant so every script renders it identically.
LIVE_SUFFIX = " • Live \U0001F7E2"  # " • Live 🟢"


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"WARN {msg}", flush=True)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_session(extra_headers: dict | None = None) -> requests.Session:
    s = requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)
    s.headers.update(headers)
    return s


def fetch(session: requests.Session, url: str, *, params=None, headers=None,
          method: str = "GET", json_body=None, data=None,
          retries: int = HTTP_RETRIES, timeout: int = HTTP_TIMEOUT):
    """GET/POST with retries + exponential backoff. Raises on final failure.

    `json_body` sends a JSON body; `data` sends a form-encoded (or raw)
    body — pass at most one of them.
    """
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = session.request(
                method, url, params=params, headers=headers,
                json=json_body, data=data, timeout=timeout,
            )
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001 - deliberately broad, retried
            last = exc
            if attempt < retries:
                wait = HTTP_BACKOFF * attempt
                warn(f"retry {attempt}/{retries - 1} after {wait:.0f}s | {url} | {exc}")
                time.sleep(wait)
    raise last  # type: ignore[misc]


def xmltv_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S +0000")


def is_live_now(start: datetime, stop: datetime, now: datetime | None = None) -> bool:
    now = now or utc_now()
    return start <= now < stop


def live_title(title: str, start: datetime, stop: datetime, now: datetime | None = None) -> str:
    """Append the Live marker to a title only while the event is in progress."""
    if is_live_now(start, stop, now):
        return f"{title}{LIVE_SUFFIX}"
    return title


def add_programme(
    root: ET.Element,
    channel_id: str,
    start: datetime,
    stop: datetime,
    title: str,
    desc: str = "",
    *,
    category: str | None = None,
    icon: str | None = None,
    live_eligible: bool = False,
    now: datetime | None = None,
) -> ET.Element:
    """Append one <programme> element. When live_eligible=True the title gets
    the Live marker automatically if `now` falls inside [start, stop)."""
    shown_title = live_title(title, start, stop, now) if live_eligible else title

    p = ET.SubElement(
        root, "programme",
        start=xmltv_time(start), stop=xmltv_time(stop), channel=channel_id,
    )
    lang = "ar" if re.search(r"[؀-ۿ]", shown_title) else "en"
    ET.SubElement(p, "title", lang=lang).text = shown_title
    if desc:
        dlang = "ar" if re.search(r"[؀-ۿ]", desc) else "en"
        ET.SubElement(p, "desc", lang=dlang).text = desc
    if category:
        clang = "ar" if re.search(r"[؀-ۿ]", category) else "en"
        ET.SubElement(p, "category", lang=clang).text = category
    if live_eligible and is_live_now(start, stop, now):
        ET.SubElement(p, "category", lang="en").text = "Live"
    if icon:
        ET.SubElement(p, "icon", src=icon)
    return p


def existing_programme_count(path: str) -> int:
    try:
        if not os.path.exists(path):
            return 0
        return len(ET.parse(path).getroot().findall("programme"))
    except Exception:
        return 0


def write_xml_atomic(
    root: ET.Element,
    output_path: str,
    *,
    keep_old_if_empty: bool = True,
    check_overlaps: bool = True,
    generator_name: str = "Unified MENA EPG",
) -> bool:
    """Validate + atomically write an XMLTV tree. Returns True if written.

    Refuses to replace an existing file that already has programmes with a
    run that produced zero programmes, unless keep_old_if_empty is False.
    """
    programme_count = len(root.findall("programme"))

    if programme_count == 0 and keep_old_if_empty and existing_programme_count(output_path) > 0:
        warn(
            f"0 programmes produced this run — sources likely unreachable. "
            f"Keeping previous {output_path} untouched."
        )
        return False

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    tmp_path = f"{output_path}.tmp"
    ET.ElementTree(root).write(tmp_path, encoding="utf-8", xml_declaration=True)

    # Refuse to ever leave a malformed file behind.
    tree = ET.parse(tmp_path)

    # Structural sanity check: every programme must have stop > start and
    # programmes per channel must not overlap.
    def _p(s: str) -> datetime:
        return datetime.strptime(s, "%Y%m%d%H%M%S %z")

    last_stop: dict[str, datetime] = {}
    for pr in tree.getroot().findall("programme"):
        ch = pr.get("channel")
        st, sp = _p(pr.get("start")), _p(pr.get("stop"))
        if sp <= st:
            raise ValueError(f"invalid programme duration on {ch}: {pr.get('start')} -> {pr.get('stop')}")
        if check_overlaps:
            prev = last_stop.get(ch)
            if prev is not None and st < prev:
                raise ValueError(f"overlapping programmes on {ch} at {pr.get('start')}")
            last_stop[ch] = sp

    os.replace(tmp_path, output_path)
    log(f"Written and XML-validated: {output_path} ({programme_count} programmes)")
    return True


def resolve_overlaps(events: list[dict]) -> list[dict]:
    """Sort a single channel's events by start and remove overlaps.

    Some upstream APIs (seen live on STARZPLAY) return events that overlap
    in time for the same channel — invalid XMLTV. An event fully inside the
    previous one is dropped; a partial overlap has its start pushed to the
    previous event's stop (or is dropped if that leaves no duration left).
    Expects each event to be a dict with "start"/"stop" datetimes.
    """
    ordered = sorted(events, key=lambda e: e["start"])
    out: list[dict] = []
    cursor = None
    for ev in ordered:
        start, stop = ev["start"], ev["stop"]
        if cursor is not None and start < cursor:
            if stop <= cursor:
                continue  # fully swallowed by the previous event
            start = cursor
        if stop <= start:
            continue
        out.append({**ev, "start": start, "stop": stop})
        cursor = stop
    return out


def dedupe_events(events: list[dict], key_fn, priority_fn=None) -> list[dict]:
    """Keep the highest-priority event per key (default: first wins)."""
    best: dict = {}
    for ev in events:
        k = key_fn(ev)
        old = best.get(k)
        if old is None:
            best[k] = ev
            continue
        if priority_fn and priority_fn(ev) > priority_fn(old):
            best[k] = ev
    return list(best.values())


def run_main(build_fn, output_path: str) -> int:
    """Standard entrypoint wrapper: never let an uncaught exception break the
    workflow's git step — always exit cleanly and preserve the old file."""
    try:
        return build_fn()
    except Exception as exc:  # noqa: BLE001
        warn(f"FATAL: {exc}")
        if existing_programme_count(output_path) > 0:
            warn(f"Keeping previous {output_path} untouched after fatal error.")
            return 0
        return 1


# ---------------------------------------------------------------------------
# Guide-channel helpers: live badge + "time until kickoff" countdown
# ---------------------------------------------------------------------------

LRM = "‎"

# The blue badge used by the guide-style channels (Shasha, Shahid). It marks
# the programme as a LIVE BROADCAST — the standard EPG meaning — so it stays
# visible when browsing ahead, exactly like update_alwan_epg.py does.
LIVE_BADGE = "• Live \U0001F535"  # "• Live 🔵"


def ltr(value: str) -> str:
    """Wrap a Latin run so it keeps its own order inside RTL text."""
    return f"{LRM}{value}{LRM}"


def with_live_badge(title: str) -> str:
    return f"{title} {ltr(LIVE_BADGE)}"


def countdown_label(minutes) -> str:
    """Arabic 'time remaining' label: '15 د', '2 س', '2 س و15 د', '1 ي و3 س'."""
    minutes = max(int(minutes), 0)
    hours, mins = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days} ي و{hours} س" if hours else f"{days} ي"
    if hours and mins:
        return f"{hours} س و{mins} د"
    if hours:
        return f"{hours} س"
    return f"{mins} د"


def countdown_step(remaining: timedelta) -> timedelta:
    """How long the next countdown block should last.

    A countdown written into a static XMLTV file would go stale instantly,
    so instead the gap before a match is filled with consecutive blocks,
    each labelled with the time left at *its own* start. The player always
    shows the block covering "now", so the number stays correct without the
    file being re-downloaded. Blocks get shorter as kickoff approaches, so
    the figure is never more than one step out of date.
    """
    if remaining <= timedelta(hours=1):
        return timedelta(minutes=10)
    if remaining <= timedelta(hours=3):
        return timedelta(minutes=15)
    if remaining <= timedelta(hours=8):
        return timedelta(minutes=30)
    return timedelta(hours=1)


def group_concurrent(events: list[dict], key="start") -> dict:
    """start-time -> [events]. Matches kicking off together must become ONE
    programme: a guide channel can only show one entry per time slot, so
    emitting them separately makes the player hide all but one."""
    slots: dict = {}
    for ev in events:
        slots.setdefault(ev[key], []).append(ev)
    return slots
