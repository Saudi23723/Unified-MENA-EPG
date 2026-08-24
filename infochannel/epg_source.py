#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loads the unified XMLTV guide and turns it into what the screen needs:
what is on air right now, and what is coming up next.

The source can be a local file (when the streamer runs on the same machine
that generates the guide) or an HTTP URL (the normal case: the raw GitHub
copy that the Actions workflows keep up to date). Refreshes happen on a
background thread and never take the screen down: a failed fetch keeps the
previous, still-valid data.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

DEFAULT_EPG_URL = (
    "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
    "main/unified_mena_epg.xml"
)

# The Live marker that epg_lib.py appends to titles that are on air. We strip
# it here because this screen shows liveness with its own badge.
LIVE_MARKERS = ("• Live 🟢", "· Live 🟢", "• Live", "🟢")

# Placeholder programmes some generators emit to fill dead air ("no match
# scheduled", "next up in 2h"). They are real XMLTV entries but they are not
# events, and putting them on the board pushes actual fixtures off it.
FILLER_RE = re.compile(
    r"لا\s*(توجد|يوجد)|no\s+(match|event)|^\s*التالي\s*:|coming\s+up\s+next$",
    re.IGNORECASE,
)

# Pictographs (⏰ 🟢 …) have no glyph in the text fonts and render as tofu
# boxes on screen, so they are stripped rather than drawn.
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿️⬀-⯿⏩-⏺⌚-⌛]"
)

# Used by --sports-only to keep the board on matches instead of general
# programming. A bare " - " is deliberately NOT a signal: half the entertainment
# titles in the guide contain one.
MATCH_RE = re.compile(r"\bvs\.?\b|\bv\b|ضد|مباراة|مباريات", re.IGNORECASE)
SPORT_CAT_RE = re.compile(
    r"sport|football|soccer|match|tennis|basket|رياض|كرة|مباراة|دوري", re.IGNORECASE
)
# Most channels in this guide are sports channels outright, so the channel
# name is the strongest and cheapest signal available.
SPORT_CHANNEL_RE = re.compile(
    r"sport|spor|bein|tabii|thmanyah|shahid|alwan|fajer|ssc|رياض|ثمانية", re.IGNORECASE
)


def log(msg: str) -> None:
    print(f"[epg] {msg}", flush=True)


@dataclass(frozen=True)
class Event:
    channel_id: str
    channel_name: str
    title: str
    subtitle: str
    start: datetime
    stop: datetime
    # Position of the channel in the guide, so the board can list events in
    # the broadcaster's own channel order instead of alphabetically.
    channel_index: int = 0

    @property
    def duration(self) -> timedelta:
        return self.stop - self.start

    def progress(self, now: datetime) -> float:
        total = self.duration.total_seconds()
        if total <= 0:
            return 0.0
        return min(1.0, max(0.0, (now - self.start).total_seconds() / total))


def _parse_xmltv_time(value: str) -> datetime | None:
    """XMLTV timestamps are `YYYYMMDDHHMMSS +ZZZZ`, sometimes without the
    offset. Anything unparseable is dropped rather than crashing the frame."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M%S%z", "%Y%m%d%H%M%S"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _clean_title(title: str) -> tuple[str, str]:
    """Strip the Live marker and split a `A vs B - Competition` title into a
    headline and a smaller subtitle line."""
    text = (title or "").strip()
    for marker in LIVE_MARKERS:
        text = text.replace(marker, "")
    # Some generators append their own countdown after a clock pictograph
    # ("الاتحاد - الحزم ⏰ بعد 2 س و30 د"); this screen renders its own.
    text = re.split(r"[⏰⌚🕐]", text)[0]
    text = EMOJI_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—•·")

    # `Arsenal vs. Coventry City - English Premier League 2026/2027`
    parts = re.split(r"\s+[-–—]\s+", text)
    if len(parts) >= 2 and re.search(r"\bvs\.?\b", parts[0], re.IGNORECASE):
        return parts[0].strip(), " - ".join(p.strip() for p in parts[1:])
    return text, ""


class EPGSource:
    """Thread-safe holder for the parsed guide."""

    def __init__(
        self,
        location: str = DEFAULT_EPG_URL,
        *,
        refresh_seconds: int = 300,
        channel_filter: str | None = None,
        exclude_filter: str | None = None,
        sports_only: bool = False,
        timeout: int = 30,
    ) -> None:
        self.location = location
        self.refresh_seconds = refresh_seconds
        self.timeout = timeout
        self.sports_only = sports_only
        self._include = re.compile(channel_filter, re.IGNORECASE) if channel_filter else None
        self._exclude = re.compile(exclude_filter, re.IGNORECASE) if exclude_filter else None

        self._lock = threading.Lock()
        self._events: list[Event] = []
        self._loaded_at: datetime | None = None
        self._stop = threading.Event()

    # -- loading -------------------------------------------------------------
    def _read_bytes(self) -> bytes:
        if re.match(r"^https?://", self.location):
            req = urllib.request.Request(
                self.location,
                headers={"User-Agent": "Unified-MENA-EPG-InfoChannel/1.0"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        with open(self.location, "rb") as fh:
            return fh.read()

    def _keep_channel(self, channel_id: str, name: str) -> bool:
        blob = f"{channel_id} {name}"
        if self._include and not self._include.search(blob):
            return False
        if self._exclude and self._exclude.search(blob):
            return False
        return True

    def _keep_event(self, title: str, categories: list[str], channel: str) -> bool:
        if not self.sports_only:
            return True
        if SPORT_CHANNEL_RE.search(channel):
            return True
        if any(SPORT_CAT_RE.search(c) for c in categories):
            return True
        return bool(MATCH_RE.search(title))

    def load(self) -> bool:
        """Fetch + parse. Returns True when the in-memory guide was replaced."""
        try:
            raw = self._read_bytes()
            root = ET.fromstring(raw)
        except Exception as exc:  # noqa: BLE001 - keep the screen alive
            log(f"WARN refresh failed, keeping previous data | {exc}")
            return False

        names: dict[str, str] = {}
        order: dict[str, int] = {}
        for index, ch in enumerate(root.findall("channel")):
            cid = ch.get("id") or ""
            display = ""
            for dn in ch.findall("display-name"):
                if (dn.text or "").strip():
                    display = dn.text.strip()
                    break
            names[cid] = EMOJI_RE.sub("", display or cid).strip()
            order[cid] = index

        events: list[Event] = []
        for pr in root.findall("programme"):
            cid = pr.get("channel") or ""
            name = names.get(cid, cid)
            if not self._keep_channel(cid, name):
                continue

            start = _parse_xmltv_time(pr.get("start") or "")
            stop = _parse_xmltv_time(pr.get("stop") or "")
            if not start or not stop or stop <= start:
                continue

            raw_title = (pr.findtext("title") or "").strip()
            if not raw_title:
                continue
            if FILLER_RE.search(raw_title):
                continue
            cats = [(c.text or "") for c in pr.findall("category")]
            if not self._keep_event(raw_title, cats, f"{cid} {name}"):
                continue

            title, subtitle = _clean_title(raw_title)
            if not title:
                continue
            events.append(
                Event(
                    channel_id=cid,
                    channel_name=name,
                    title=title,
                    subtitle=subtitle,
                    start=start,
                    stop=stop,
                    channel_index=order.get(cid, 9999),
                )
            )

        if not events:
            log("WARN parsed 0 events, keeping previous data")
            return False

        events.sort(key=lambda e: (e.start, e.channel_index))
        with self._lock:
            self._events = events
            self._loaded_at = datetime.now(UTC)
        log(f"loaded {len(events)} events from {len(names)} channels")
        return True

    # -- queries -------------------------------------------------------------
    @property
    def loaded_at(self) -> datetime | None:
        with self._lock:
            return self._loaded_at

    @property
    def total_events(self) -> int:
        with self._lock:
            return len(self._events)

    def live_now(self, now: datetime) -> list[Event]:
        with self._lock:
            events = self._events
        live = [e for e in events if e.start <= now < e.stop]
        # Channel order, the way a viewer reads a channel list — not by start
        # time, which would scatter the same broadcaster across pages.
        live.sort(key=lambda e: (e.channel_index, e.start))
        return live

    def upcoming(self, now: datetime, *, within_hours: int = 36) -> list[Event]:
        horizon = now + timedelta(hours=within_hours)
        with self._lock:
            events = self._events
        nxt = [e for e in events if now < e.start <= horizon]
        nxt.sort(key=lambda e: (e.start, e.channel_index))
        return nxt

    # -- background refresh --------------------------------------------------
    def start_refresh_thread(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self.refresh_seconds):
                self.load()

        threading.Thread(target=loop, name="epg-refresh", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def wait_for_first_load(source: EPGSource, *, attempts: int = 5) -> bool:
    """Block until the guide loads once, backing off between tries so a box
    that boots before the network is up still comes online by itself."""
    for attempt in range(1, attempts + 1):
        if source.load():
            return True
        wait = min(30, 2 ** attempt)
        log(f"initial load failed ({attempt}/{attempts}), retrying in {wait}s")
        time.sleep(wait)
    return False
