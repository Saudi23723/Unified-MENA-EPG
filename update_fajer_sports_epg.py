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
    r"(?P<home>[\w\u0600-\u06ff .'\-]+?)\s*[xX×]\s*"
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

NOISE_PREFIXES = (
    "للمشاهدة",
    "رابط المشاهدة",
    "روابط المشاهدة",
    "مشاهدة ممتعة",
)


def clean_team(s: str) -> str:
    s = norm(s)
    # Remove common prose fragments around team names.
    s = re.sub(
        r"^(?:تشاهدون\s+(?:الآن|الان)\s+عبر.*?مباراة\s*:?\s*|"
        r"تشاهدون\s+(?:الآن|الان)\s+عبر.*?:\s*|"
        r"مباراة\s*:?\s*)",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\s*(?:\.\.\.|…).*?$",
        "",
        s,
    )
    return norm(s.strip(" :-–—⚽️"))


def split_lines(text: str) -> list[str]:
    # Telegram can render <br> as line breaks, but get_text may also flatten.
    text = text.replace("👈🏻", " ").replace("⚽️", " ")
    chunks = re.split(r"[\n\r]+|(?=\s*(?:قناة|رابط المشاهدة|للمشاهدة)\s*:?)", text)
    return [norm(x) for x in chunks if norm(x)]


def channels_mentioned(text: str) -> list[int]:
    found = []
    for m in CHANNEL_RE.finditer(text):
        n = int(m.group("num"))
        if n not in found:
            found.append(n)

    # Direct links are also explicit channel declarations.
    for n in range(1, 6):
        if f"link.fajer.tv/{n}" in text and n not in found:
            found.append(n)

    return found


def parse_single_now_post(text: str, post_time: datetime) -> list[dict]:
    """
    Parse only explicit 'watching now' posts.

    Conservative rule:
    - must explicitly say "تشاهدون الآن/الان"
    - must contain a team pair
    - must explicitly identify channel 1..5 by name/number or link

    Telegram post time is used as the start of the currently-airing block.
    This is intentionally NOT presented as an official kickoff time.
    """
    text = norm(text)
    if not EXPLICIT_NOW_RE.search(text):
        return []

    events = []

    # Handle common multi-match format:
    # team A x team B ... قناة 3
    # team C x team D ... قناة 5
    # Search pair-by-pair and inspect text until the next pair.
    pairs = list(MATCH_PAIR_RE.finditer(text))
    for idx, m in enumerate(pairs):
        start = m.start()
        end = pairs[idx + 1].start() if idx + 1 < len(pairs) else len(text)
        segment = text[start:end]

        home = clean_team(m.group("home"))
        away = clean_team(m.group("away"))
        if not home or not away or home == away:
            continue

        chs = channels_mentioned(segment)

        # If channel appears before the pair in a single-match post
        # ("عبر قناتنا الرابعة ... Roma x Monza"), inspect the whole post.
        if not chs and len(pairs) == 1:
            chs = channels_mentioned(text)

        for ch in chs:
            cid, cname = CHANNELS[ch]
            events.append({
                "channel_num": ch,
                "channel_id": cid,
                "channel_name": cname,
                "start": post_time.astimezone(UTC),
                "title": f"{home} - {away}",
                "source_name": "FajerSportOfficialTelegram",
                "source": "https://t.me/fajersport",
                "duration_minutes": 135,
            })

    return dedupe(events)


def parse_telegram_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events = []

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

        if not in_window(post_time):
            continue

        events.extend(parse_single_now_post(text, post_time))

    return dedupe(events)


def collect_telegram_events() -> list[dict]:
    last_exc = None
    for url in TELEGRAM_URLS:
        try:
            html = fetch_text(url)
            events = parse_telegram_html(html)
            log(f"FajerSport official Telegram events detected: {len(events)} | {url}")
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
    return (
        f"{ev['title']}\n"
        f"{ev['channel_name']}\n"
        f"تم رصد البث من إعلان فجر سبورت الرسمي على Telegram.\n"
        f"وقت الرصد على القناة: {local:%Y-%m-%d %H:%M} بتوقيت فلسطين.\n"
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
    # Single-match channel-before-pair format.
    text1 = (
        "تشاهدون الآن عبر قناتنا الرابعة مباراة : "
        "الاتحاد X العين للمشاهدة: قناة 4"
    )
    dt = datetime(2026, 8, 19, 17, 54, tzinfo=UTC)
    e1 = parse_single_now_post(text1, dt)
    assert len(e1) == 1
    assert e1[0]["channel_num"] == 4
    assert "الاتحاد" in e1[0]["title"]
    assert "العين" in e1[0]["title"]

    # Two simultaneous matches.
    text2 = (
        "تشاهدون الآن عبر قناتنا الثالثة والخامسة "
        "مانشستر سيتي X واتفورد ... رابط المشاهدة قناة 3 "
        "تشيلسي X بارو ... رابط المشاهدة قناة 5"
    )
    e2 = parse_single_now_post(text2, dt)
    assert len(e2) == 2
    assert {x["channel_num"] for x in e2} == {3, 5}

    # Must reject a generic "today" post with no explicit match assignment.
    text3 = (
        "تشاهدون اليوم الثلاثاء عبر قنواتنا وموقعنا "
        "قناة 1 https://link.fajer.tv/1 قناة 2 https://link.fajer.tv/2"
    )
    assert parse_single_now_post(text3, dt) == []

    # HTML wrapper test.
    html = f"""
    <html><body>
      <div class="tgme_widget_message">
        <div class="tgme_widget_message_text">{text1}</div>
        <time datetime="2026-08-19T17:54:00+00:00"></time>
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
    assert wrapped[0]["channel_num"] == 4

    log("SELF TEST | PASS")


def main():
    log(
        "FAJER SPORT EPG | channels 1-5 | official @fajersport Telegram | "
        "explicit current-match assignments only | NO OCR | NO CHANNEL GUESSING"
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
