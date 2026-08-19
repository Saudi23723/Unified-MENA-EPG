#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import unescape
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


OUTPUT = "fajer_sports_epg.xml"

UTC = timezone.utc
PALESTINE = ZoneInfo("Asia/Hebron")

DAYS_BACK = 1
DAYS_FORWARD = 7
HTTP_TIMEOUT = 25

TELEGRAM_URLS = [
    "https://t.me/s/fajersport",
    "https://telegram.me/s/fajersport",
]

CHANNELS = {
    1: ("FajerSport1", "Fajer Sport 1 | فجر سبورت 1"),
    2: ("FajerSport2", "Fajer Sport 2 | فجر سبورت 2"),
    3: ("FajerSport3", "Fajer Sport 3 | فجر سبورت 3"),
    4: ("FajerSport4", "Fajer Sport 4 | فجر سبورت 4"),
    5: ("FajerSport5", "Fajer Sport 5 | فجر سبورت 5"),
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
})


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"WARN {msg}", flush=True)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def utc_now() -> datetime:
    return datetime.now(UTC)


def window_bounds():
    now = utc_now()
    start = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = (now + timedelta(days=DAYS_FORWARD + 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, end


def in_window(dt: datetime) -> bool:
    start, end = window_bounds()
    return start <= dt.astimezone(UTC) < end


def fetch_text(url: str) -> str:
    r = session.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.text


def xmltv_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S +0000")


# ---------------------------------------------------------------------------
# Telegram parsing
# ---------------------------------------------------------------------------

MATCH_PAIR_RE = re.compile(
    r"(?P<home>[\w\u0600-\u06ff .'\-]+?)\s*(?:x|X|×|🆚|[-–—])\s*"
    r"(?P<away>[\w\u0600-\u06ff .'\-]+)",
    re.UNICODE,
)

CHANNEL_RE = re.compile(
    r"(?:قناة|قناتنا|القناة)\s*(?P<num>[1-5])"
)

EXPLICIT_NOW_RE = re.compile(
    r"تشاهدون\s+الآن|تشاهدون\s+الان|الآن\s+عبر|الان\s+عبر",
    re.I,
)

SCHEDULE_HINT_RE = re.compile(
    r"تشاهدون\s+(?:اليوم|الليلة)|"
    r"المواجهة\s+النارية|"
    r"الموعد\s*:|"
    r"الساعة\s+\d{1,2}",
    re.I,
)

TIME_AR_RE = re.compile(
    r"(?:الموعد\s*:\s*)?(?:اليوم\s+)?(?:الساعة\s+)?"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<ampm>صباح(?:اً|ا)?|مساء(?:ً|ا)?|فجر(?:اً|ا)?)",
    re.I,
)

TIME_24_RE = re.compile(
    r"(?:الموعد\s*:\s*)?(?:الساعة\s+)"
    r"(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)(?!\s*(?:صباح|مساء|فجر))",
    re.I,
)

AFTER_MIDNIGHT_RE = re.compile(
    r"بعد\s+منتصف\s+(?:الليلة|الليل)|فجر(?:اً|ا)?",
    re.I,
)


def clean_team(s: str) -> str:
    s = norm(s)
    s = re.sub(
        r"^(?:تشاهدون\s+(?:الآن|الان|اليوم|الليلة)\s+.*?"
        r"(?:مباراة|مباريات)?\s*:?\s*|"
        r"مباراة\s*:?\s*|"
        r"المواجهة\s+النارية\s*|"
        r"نهائي\s+(?:بطولة\s+)?[^:|]{0,80}?\s+)",
        "",
        s,
        flags=re.I,
    )
    # Strip common schedule/broadcast prose from the tail.
    s = re.split(
        r"\s*(?:\||⏰|📺|الساعة|الموعد|عبر\s+القنوات|روابط?\s+المشاهدة)",
        s,
        maxsplit=1,
        flags=re.I,
    )[0]
    return norm(s.strip(" :-–—⚽️🔥🏆"))


def channels_mentioned(text: str) -> list[int]:
    found = []
    for m in CHANNEL_RE.finditer(text):
        n = int(m.group("num"))
        if n not in found:
            found.append(n)

    for n in range(1, 6):
        if f"link.fajer.tv/{n}" in text and n not in found:
            found.append(n)

    return found


def _parse_clock(text: str) -> tuple[int, int] | None:
    m = TIME_AR_RE.search(text)
    if m:
        hh = int(m.group("hour"))
        mm = int(m.group("minute") or 0)
        ampm = m.group("ampm")

        if "مساء" in ampm:
            if hh != 12:
                hh += 12
        else:
            if hh == 12:
                hh = 0
        return hh, mm

    m = TIME_24_RE.search(text)
    if m:
        return int(m.group("hour")), int(m.group("minute"))

    return None


def _event_date_from_post(text: str, post_time: datetime, hh: int) -> date:
    """
    FajerSport posts use relative wording such as اليوم / الليلة.
    We anchor that wording to the Telegram post's date in Palestine time.

    For clearly after-midnight wording (e.g. "بعد منتصف الليلة", "3 فجراً"),
    an early-morning kickoff belongs to the following calendar day.
    """
    local_post = post_time.astimezone(PALESTINE)
    d = local_post.date()

    if hh <= 6 and AFTER_MIDNIGHT_RE.search(text):
        d += timedelta(days=1)

    return d


def _extract_pairs_with_channels(text: str) -> list[tuple[str, str, list[int]]]:
    pairs = list(MATCH_PAIR_RE.finditer(text))
    out = []

    for idx, m in enumerate(pairs):
        seg_start = m.start()
        seg_end = pairs[idx + 1].start() if idx + 1 < len(pairs) else len(text)
        segment = text[seg_start:seg_end]

        home = clean_team(m.group("home"))
        away = clean_team(m.group("away"))
        if not home or not away or home == away:
            continue

        chs = channels_mentioned(segment)

        # A single scheduled match often lists channels after the matchup.
        if not chs and len(pairs) == 1:
            chs = channels_mentioned(text)

        out.append((home, away, chs))

    return out


def parse_single_scheduled_post(text: str, post_time: datetime) -> list[dict]:
    """
    Parse future/same-day announcements only when ALL are explicit:
      * match pairing
      * clock time
      * Fajer channel number(s) 1..5

    The post's local Palestine date resolves relative terms such as "today".
    """
    text = norm(text)

    if EXPLICIT_NOW_RE.search(text):
        return []
    if not SCHEDULE_HINT_RE.search(text):
        return []

    clock = _parse_clock(text)
    if not clock:
        return []

    hh, mm = clock
    d = _event_date_from_post(text, post_time, hh)

    try:
        start_local = datetime(d.year, d.month, d.day, hh, mm, tzinfo=PALESTINE)
        start_utc = start_local.astimezone(UTC)
    except Exception:
        return []

    if not in_window(start_utc):
        return []

    events = []
    for home, away, chs in _extract_pairs_with_channels(text):
        for ch in chs:
            cid, cname = CHANNELS[ch]
            events.append({
                "channel_num": ch,
                "channel_id": cid,
                "channel_name": cname,
                "start": start_utc,
                "title": f"{home} - {away}",
                "source_name": "FajerSportOfficialTelegramSchedule",
                "source": "https://t.me/fajersport",
                "duration_minutes": 135,
                "time_type": "scheduled",
            })

    return dedupe(events)


def parse_single_now_post(text: str, post_time: datetime) -> list[dict]:
    """
    Fallback for an explicit currently-airing post when no advance scheduled
    event for the same channel/match has been found. Telegram post time is
    treated only as the observed on-air start.
    """
    text = norm(text)
    if not EXPLICIT_NOW_RE.search(text):
        return []

    events = []
    for home, away, chs in _extract_pairs_with_channels(text):
        for ch in chs:
            cid, cname = CHANNELS[ch]
            events.append({
                "channel_num": ch,
                "channel_id": cid,
                "channel_name": cname,
                "start": post_time.astimezone(UTC),
                "title": f"{home} - {away}",
                "source_name": "FajerSportOfficialTelegramNow",
                "source": "https://t.me/fajersport",
                "duration_minutes": 135,
                "time_type": "observed-now",
            })

    return dedupe(events)


def _match_identity(ev: dict) -> str:
    title = re.sub(
        r"[^a-z0-9\u0600-\u06ff]+",
        " ",
        ev["title"].casefold(),
    )
    return f"{ev['channel_id']}|{norm(title)}"


def parse_telegram_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    scheduled = []
    observed_now = []

    messages = soup.select(".tgme_widget_message")
    for msg in messages:
        body = msg.select_one(".tgme_widget_message_text")
        time_el = msg.select_one("time[datetime]")
        if not body or not time_el:
            continue

        text = norm(body.get_text(" ", strip=True))
        dt_raw = time_el.get("datetime", "")
        try:
            post_time = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
            if post_time.tzinfo is None:
                post_time = post_time.replace(tzinfo=UTC)
        except Exception:
            continue

        scheduled.extend(parse_single_scheduled_post(text, post_time))
        observed_now.extend(parse_single_now_post(text, post_time))

    scheduled = dedupe(scheduled)

    # Prefer a genuine announced kickoff over a later "watch now" post.
    scheduled_ids = {_match_identity(ev) for ev in scheduled}
    fallback_now = [
        ev for ev in dedupe(observed_now)
        if _match_identity(ev) not in scheduled_ids and in_window(ev["start"])
    ]

    return dedupe(scheduled + fallback_now)


def collect_telegram_events() -> list[dict]:
    last_exc = None
    for url in TELEGRAM_URLS:
        try:
            html = fetch_text(url)
            events = parse_telegram_html(html)
            scheduled_count = sum(1 for x in events if x.get("time_type") == "scheduled")
            now_count = sum(1 for x in events if x.get("time_type") == "observed-now")
            log(
                f"FajerSport official Telegram events detected: {len(events)} "
                f"| scheduled={scheduled_count} | now-fallback={now_count} | {url}"
            )
            return events
        except Exception as exc:
            last_exc = exc
            warn(f"Telegram source failed: {url} | {exc}")

    if last_exc:
        warn("All Telegram mirrors failed")
    return []


# ---------------------------------------------------------------------------
# Event handling / XML
# ---------------------------------------------------------------------------

def event_key(ev: dict) -> str:
    t = ev["start"].astimezone(UTC).replace(second=0, microsecond=0)
    title = re.sub(
        r"[^a-z0-9\u0600-\u06ff]+",
        " ",
        ev["title"].casefold(),
    )
    return f"{ev['channel_id']}|{t:%Y%m%d%H%M}|{norm(title)}"


def dedupe(events: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for ev in sorted(events, key=lambda x: (x["start"], x["channel_id"])):
        k = event_key(ev)
        if k in seen:
            continue
        seen.add(k)
        out.append(ev)
    return out


def add_programme(
    root,
    channel_id: str,
    start: datetime,
    stop: datetime,
    title: str,
    desc: str,
):
    p = ET.SubElement(
        root,
        "programme",
        start=xmltv_time(start),
        stop=xmltv_time(stop),
        channel=channel_id,
    )
    ET.SubElement(p, "title", lang="ar").text = title
    ET.SubElement(p, "desc", lang="ar").text = desc
    ET.SubElement(p, "category", lang="en").text = "Sports"


def build_description(ev: dict) -> str:
    local = ev["start"].astimezone(PALESTINE)
    if ev.get("time_type") == "scheduled":
        timing = f"الموعد المعلن: {local:%Y-%m-%d %H:%M} بتوقيت فلسطين."
    else:
        timing = (
            f"وقت رصد البث: {local:%Y-%m-%d %H:%M} بتوقيت فلسطين "
            f"(من منشور تشاهدون الآن)."
        )
    return (
        f"{ev['title']}\n"
        f"{ev['channel_name']}\n"
        f"{timing}\n"
        f"المصدر: FajerSport Official Telegram"
    )


def write_xml(events: list[dict]) -> None:
    root = ET.Element(
        "tv",
        generator_info_name="Fajer Sport official Telegram EPG",
    )

    for n in range(1, 6):
        cid, cname = CHANNELS[n]
        ch = ET.SubElement(root, "channel", id=cid)
        ET.SubElement(ch, "display-name", lang="ar").text = cname
        ET.SubElement(ch, "display-name", lang="en").text = f"Fajer Sport {n}"

    # Only verified timed event blocks are written. No fake 24h filler.
    for ev in sorted(events, key=lambda x: (x["channel_id"], x["start"])):
        start = ev["start"].astimezone(UTC)
        stop = start + timedelta(minutes=int(ev.get("duration_minutes", 135)))
        add_programme(
            root,
            ev["channel_id"],
            start,
            stop,
            ev["title"],
            build_description(ev),
        )

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    ET.ElementTree(root).write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True,
    )
    ET.parse(OUTPUT)
    log(f"Written and XML-validated: {OUTPUT}")


# ---------------------------------------------------------------------------
# Self tests
# ---------------------------------------------------------------------------

def _self_test() -> None:
    # 1) Future scheduled match with explicit time and channels.
    dt = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
    text1 = (
        "المواجهة النارية نهائي بطولة أمم أوروبا "
        "إسبانيا - إنجلترا | الساعة 10 مساءً "
        "بمعلقين مختلفين عبر القنوات : قناة 1 - قناة 3"
    )
    e1 = parse_single_scheduled_post(text1, dt)
    assert len(e1) == 2
    assert {x["channel_num"] for x in e1} == {1, 3}
    assert all(x["start"].astimezone(PALESTINE).hour == 22 for x in e1)
    assert all(x["time_type"] == "scheduled" for x in e1)

    # 2) After-midnight wording moves an early-morning kickoff to next day.
    text2 = (
        "تشاهدون بعد منتصف الليلة نهائي بطولة كوبا أمريكا "
        "الأرجنتين - كولومبيا | الساعة 3 فجراً "
        "عبر القنوات : قناة 1 - قناة 3"
    )
    e2 = parse_single_scheduled_post(text2, dt)
    assert len(e2) == 2
    p2 = e2[0]["start"].astimezone(PALESTINE)
    assert p2.hour == 3
    assert p2.date() == (dt.astimezone(PALESTINE).date() + timedelta(days=1))

    # 3) Explicit "now" is accepted as fallback.
    text3 = (
        "تشاهدون الآن عبر شاشة وموقع الفجر مباراة : "
        "ريال سوسييداد x أتلتيك بيلباو "
        "روابط المشاهدة: قناة 1"
    )
    e3 = parse_single_now_post(text3, dt)
    assert len(e3) == 1
    assert e3[0]["channel_num"] == 1
    assert e3[0]["time_type"] == "observed-now"

    # 4) Generic daily links with no match/time must be rejected.
    text4 = (
        "تشاهدون اليوم الثلاثاء عبر قنواتنا وموقعنا "
        "قناة 1 https://link.fajer.tv/1 قناة 2 https://link.fajer.tv/2"
    )
    assert parse_single_scheduled_post(text4, dt) == []
    assert parse_single_now_post(text4, dt) == []

    # 5) HTML integration: scheduled event must win over later now-post.
    html = """
    <html><body>
      <div class="tgme_widget_message">
        <div class="tgme_widget_message_text">
        المواجهة النارية إسبانيا - إنجلترا | الساعة 10 مساءً
        عبر القنوات : قناة 1
        </div>
        <time datetime="2026-08-19T08:00:00+00:00"></time>
      </div>
      <div class="tgme_widget_message">
        <div class="tgme_widget_message_text">
        تشاهدون الآن إسبانيا - إنجلترا روابط المشاهدة: قناة 1
        </div>
        <time datetime="2026-08-19T18:58:00+00:00"></time>
      </div>
    </body></html>
    """
    old_window = globals()["in_window"]
    try:
        globals()["in_window"] = lambda x: True
        wrapped = parse_telegram_html(html)
    finally:
        globals()["in_window"] = old_window

    assert len(wrapped) == 1
    assert wrapped[0]["time_type"] == "scheduled"
    assert wrapped[0]["start"].astimezone(PALESTINE).hour == 22

    log("SELF TEST | PASS")

def main():
    log(
        "FAJER SPORT EPG | channels 1-5 | official @fajersport Telegram | "
        "scheduled match times + explicit channel assignments | now-post fallback | NO OCR | NO CHANNEL GUESSING"
    )

    _self_test()
    events = collect_telegram_events()

    log(f"Fajer Sport total verified event blocks: {len(events)}")
    for ev in events:
        local = ev["start"].astimezone(PALESTINE)
        log(
            f"  {ev['channel_name']} | "
            f"{local:%Y-%m-%d %H:%M} Palestine | "
            f"{ev['title']} | {ev['source_name']}"
        )

    write_xml(events)


if __name__ == "__main__":
    main()
