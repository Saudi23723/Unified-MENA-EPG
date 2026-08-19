#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, date
from html import unescape
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


OUTPUT = "onsport_epg.xml"

CAIRO = ZoneInfo("Africa/Cairo")
ABU_DHABI = ZoneInfo("Asia/Dubai")
LAS_VEGAS = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc

DAYS_BACK = 1
DAYS_FORWARD = 14
HTTP_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

# Per-channel football schedules. We intentionally do NOT guess a channel:
# an event is only accepted from the page of the channel that lists it.
CHANNELS = {
    "ONSport1": {
        "name": "ON Sport 1",
        "url": "https://www.livefootballtv.info/channel/on-sport-1",
    },
    "ONSport2": {
        "name": "ON Sport 2",
        "url": "https://www.livefootballtv.info/channel/on-sport-2",
    },
    "ONSportMAX": {
        "name": "ON Sport MAX",
        "url": "https://www.livefootballtv.info/channel/on-sport-max",
    },
    "ONSportPLUS": {
        "name": "ON Sport PLUS",
        "url": "https://www.livefootballtv.info/channel/on-sport-plus",
    },
}

OFFICIAL_ONSPORT = "https://www.facebook.com/OnTimeSports/"

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
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


def in_window(dt_utc: datetime) -> bool:
    start, end = window_bounds()
    return start <= dt_utc < end


def fetch_text(url: str) -> str:
    r = session.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.text


def xmltv_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S +0000")


def _month_num(name: str) -> int | None:
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    return months.get(name.casefold())


DATE_NUMERIC = re.compile(
    r"(?:(?:today|tomorrow)\s+)?"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*"
    r"(\d{1,2})/(\d{1,2})/(20\d{2})",
    re.I,
)

DATE_TEXTUAL = re.compile(
    r"(?:(?:today|tomorrow)\s+)?"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*"
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+(20\d{2}))?",
    re.I,
)

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_date_line(line: str, now_local: datetime) -> date | None:
    s = norm(line)

    m = DATE_NUMERIC.search(s)
    if m:
        dd, mm, yy = map(int, m.groups())
        try:
            return date(yy, mm, dd)
        except ValueError:
            return None

    m = DATE_TEXTUAL.search(s)
    if m:
        dd, month_name, yy = m.groups()
        month = _month_num(month_name)
        if not month:
            return None
        year = int(yy) if yy else now_local.year
        try:
            d = date(year, month, int(dd))
        except ValueError:
            return None

        # Handles a December -> January season boundary when year is omitted.
        if yy is None:
            if d < now_local.date() - timedelta(days=180):
                d = date(year + 1, month, int(dd))
            elif d > now_local.date() + timedelta(days=180):
                d = date(year - 1, month, int(dd))
        return d

    # Header style used by the current page:
    # "Football on TV today wednesday, 19/08/2026"
    low = s.casefold()
    if "football on tv today" in low:
        m = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", s)
        if m:
            dd, mm, yy = map(int, m.groups())
            try:
                return date(yy, mm, dd)
            except ValueError:
                return None

    return None


BAD_TEXT = re.compile(
    r"^(?:"
    r"live football on|football on tv|change to your time zone|"
    r"ranking by|statistical data|number of|view full ranking|"
    r"as of today|in this moment|the next match|"
    r"image:|button:|menu|teams|competitions|tv channels|news|free widget|"
    r"arab mena|all teams|all competitions|all channels|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r")",
    re.I,
)

STAGE_TEXT = re.compile(
    r"^(?:playoffs?|final|semi-?finals?|quarter-?finals?|"
    r"group stage|round of \d+|qualifiers?|friendly)$",
    re.I,
)

BROADCASTER_HINTS = re.compile(
    r"(?:sport|sports|tv|youtube|app|bein|dazn|alkass|الكأس|"
    r"riyadiya|sharjah|oman|dubai|abu dhabi|ssc|ktv|fifa\+|ppv)",
    re.I,
)


def _clean_content_line(s: str) -> str:
    s = norm(s)
    s = re.sub(r"^Image:\s*", "", s, flags=re.I)
    return s


def _plausible_name(s: str) -> bool:
    if not s or len(s) > 70:
        return False
    if BAD_TEXT.search(s):
        return False
    if TIME_RE.match(s):
        return False
    if parse_date_line(s, utc_now().astimezone(CAIRO)):
        return False
    if s.isdigit():
        return False
    if re.fullmatch(r"[\d\s().%+-]+", s):
        return False
    return True


def _extract_event_from_block(
    block: list[str],
    channel_name: str,
) -> tuple[str, str, str] | None:
    """
    Return (competition, home, away) conservatively.

    Expected rendered order is:
      competition
      [stage]
      home
      away
      broadcaster(s)

    We stop at the first broadcaster line. This avoids treating another TV
    channel as a team when several broadcasters carry the same match.
    """
    cleaned = [_clean_content_line(x) for x in block]
    cleaned = [x for x in cleaned if x and _plausible_name(x)]

    # The current channel page must explicitly list its own channel in the row.
    # Match spelling case-insensitively and allow MAX/Plus capitalization.
    own_idx = None
    for i, x in enumerate(cleaned):
        if x.casefold() == channel_name.casefold():
            own_idx = i
            break

    if own_idx is None:
        # Some pages omit the channel text because it is implicit in the page.
        # In that case we only accept a row if the pre-broadcaster structure is
        # unambiguous (competition + two teams).
        first_broadcaster = next(
            (i for i, x in enumerate(cleaned) if BROADCASTER_HINTS.search(x)),
            len(cleaned),
        )
    else:
        first_broadcaster = next(
            (
                i for i, x in enumerate(cleaned[:own_idx + 1])
                if BROADCASTER_HINTS.search(x)
            ),
            own_idx,
        )

    core = cleaned[:first_broadcaster]
    if own_idx == 0:
        return None

    # If the current channel is the first broadcaster, core is exactly the
    # competition/stage/teams section. If another broadcaster occurs first,
    # core still ends before broadcasters.
    if len(core) < 3:
        # Try using everything before the current channel only when no other
        # broadcaster marker was detected.
        if own_idx is not None:
            core = [
                x for x in cleaned[:own_idx]
                if not BROADCASTER_HINTS.search(x)
            ]

    if len(core) < 3:
        return None

    # Team names are the last two non-stage fields before broadcaster list.
    non_stage = [x for x in core if not STAGE_TEXT.match(x)]
    if len(non_stage) < 3:
        return None

    home, away = non_stage[-2], non_stage[-1]
    competition_parts = non_stage[:-2]
    competition = competition_parts[-1] if competition_parts else "Football"

    if not (_plausible_name(home) and _plausible_name(away)):
        return None
    if BROADCASTER_HINTS.search(home) or BROADCASTER_HINTS.search(away):
        return None
    if home.casefold() == away.casefold():
        return None

    return competition, home, away


def parse_channel_html(
    html: str,
    channel_id: str,
    channel_name: str,
    source_url: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style noise before reading visible strings.
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = [norm(x) for x in soup.stripped_strings if norm(x)]
    now_cairo = utc_now().astimezone(CAIRO)

    events: list[dict] = []
    current_date: date | None = None
    i = 0

    while i < len(lines):
        maybe_date = parse_date_line(lines[i], now_cairo)
        if maybe_date:
            current_date = maybe_date
            i += 1
            continue

        tm = TIME_RE.match(lines[i])
        if not tm or current_date is None:
            i += 1
            continue

        hh, mm = map(int, tm.groups())

        # Collect this event row until next time/date. Limit prevents a broken
        # page from swallowing a large part of the document.
        block: list[str] = []
        j = i + 1
        while j < len(lines) and j <= i + 30:
            if TIME_RE.match(lines[j]):
                break
            if parse_date_line(lines[j], now_cairo):
                break
            block.append(lines[j])
            j += 1

        parsed = _extract_event_from_block(block, channel_name)
        if parsed:
            competition, home, away = parsed
            try:
                local = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    hh,
                    mm,
                    tzinfo=CAIRO,
                )
                start_utc = local.astimezone(UTC)
            except Exception:
                start_utc = None

            if start_utc and in_window(start_utc):
                events.append({
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "start": start_utc,
                    "title": f"{home} - {away}",
                    "competition": competition,
                    "source_name": "LiveFootballTV",
                    "source": source_url,
                    "duration_minutes": 135,
                })

        i = max(i + 1, j)

    return dedupe(events)


def event_key(ev: dict) -> str:
    start = ev["start"].astimezone(UTC).replace(second=0, microsecond=0)
    title = re.sub(
        r"[^a-z0-9\u0600-\u06ff]+",
        " ",
        ev["title"].casefold(),
    )
    return f"{ev['channel_id']}|{start:%Y%m%d%H%M}|{norm(title)}"


def dedupe(events: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for ev in sorted(events, key=lambda x: (x["channel_id"], x["start"])):
        key = event_key(ev)
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def collect_events() -> list[dict]:
    all_events: list[dict] = []

    for channel_id, cfg in CHANNELS.items():
        try:
            html = fetch_text(cfg["url"])
            events = parse_channel_html(
                html,
                channel_id,
                cfg["name"],
                cfg["url"],
            )
            log(f"{cfg['name']} fixtures detected: {len(events)}")
            all_events.extend(events)
        except Exception as exc:
            warn(f"{cfg['name']} failed: {exc}")

    return dedupe(all_events)


def build_day_description(
    channel_name: str,
    day_ad: date,
    events: list[dict],
) -> str:
    if not events:
        return (
            f"{channel_name} | {day_ad.isoformat()}\n\n"
            "لا توجد مباراة مؤكدة مجدولة في المصدر الحالي."
        )

    lines = [f"جدول {channel_name} | {day_ad.isoformat()}", ""]
    for ev in sorted(events, key=lambda x: x["start"]):
        ad = ev["start"].astimezone(ABU_DHABI)
        lv = ev["start"].astimezone(LAS_VEGAS)
        lines.append(f"• {ev['title']} — {ev['competition']}")
        lines.append(
            f"  {ad:%H:%M} أبو ظبي | {lv:%H:%M} لاس فيغاس"
        )

    lines.extend([
        "",
        "توزيع القناة مأخوذ من صفحة الجدول الخاصة بالقناة؛ لا يتم تخمين القناة.",
    ])
    return "\n".join(lines)


def add_programme(
    root,
    channel_id: str,
    start: datetime,
    stop: datetime,
    title: str,
    desc: str,
    category: str = "Sports",
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
    ET.SubElement(p, "category", lang="en").text = category


def write_xml(events: list[dict]) -> None:
    root = ET.Element(
        "tv",
        generator_info_name="ON Sport verified football EPG",
    )

    for channel_id, cfg in CHANNELS.items():
        ch = ET.SubElement(root, "channel", id=channel_id)
        ET.SubElement(ch, "display-name", lang="en").text = cfg["name"]
        ET.SubElement(ch, "display-name", lang="ar").text = cfg["name"]

    today_ad = utc_now().astimezone(ABU_DHABI).date()
    first_day = today_ad - timedelta(days=DAYS_BACK)
    last_day = today_ad + timedelta(days=DAYS_FORWARD)

    by_channel_day: dict[tuple[str, date], list[dict]] = {}
    for ev in events:
        d = ev["start"].astimezone(ABU_DHABI).date()
        by_channel_day.setdefault((ev["channel_id"], d), []).append(ev)

    for channel_id, cfg in CHANNELS.items():
        for offset in range((last_day - first_day).days + 1):
            d = first_day + timedelta(days=offset)
            day_events = sorted(
                by_channel_day.get((channel_id, d), []),
                key=lambda x: x["start"],
            )
            desc = build_day_description(cfg["name"], d, day_events)

            day_start_ad = datetime(
                d.year, d.month, d.day, 0, 0, tzinfo=ABU_DHABI
            )
            day_end_ad = day_start_ad + timedelta(days=1)
            day_start = day_start_ad.astimezone(UTC)
            day_end = day_end_ad.astimezone(UTC)

            if not day_events:
                add_programme(
                    root,
                    channel_id,
                    day_start,
                    day_end,
                    "لا توجد مباراة مؤكدة مجدولة",
                    desc,
                )
                continue

            cursor = day_start
            for ev in day_events:
                ev_start = ev["start"].astimezone(UTC)
                if ev_start > cursor:
                    add_programme(
                        root,
                        channel_id,
                        cursor,
                        ev_start,
                        f"جدول {cfg['name']} اليوم",
                        desc,
                    )

                ev_stop = min(
                    ev_start + timedelta(
                        minutes=int(ev.get("duration_minutes", 135))
                    ),
                    day_end,
                )
                ad = ev_start.astimezone(ABU_DHABI)
                lv = ev_start.astimezone(LAS_VEGAS)
                title = (
                    f"{ev['title']} | "
                    f"{ad:%H:%M} أبو ظبي | "
                    f"{lv:%H:%M} لاس فيغاس"
                )
                add_programme(
                    root,
                    channel_id,
                    ev_start,
                    ev_stop,
                    title,
                    desc,
                    category=ev["competition"],
                )
                cursor = max(cursor, ev_stop)

            if cursor < day_end:
                add_programme(
                    root,
                    channel_id,
                    cursor,
                    day_end,
                    f"جدول {cfg['name']} اليوم",
                    desc,
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

    # Re-open generated XML so malformed output cannot silently pass.
    ET.parse(OUTPUT)
    log(f"Written and XML-validated: {OUTPUT}")


def _self_test() -> None:
    """
    Offline parser checks based on the current rendered page format.
    This is intentionally run on every execution before any network request.
    """
    sample = """
    <html><body>
    <div>Football on TV today wednesday, 19/08/2026</div>
    <div>21:00</div>
    <div>Trofeo Joan Gamper</div>
    <div>Barcelona</div>
    <div>Al Ahly</div>
    <div>FC Barcelona PPV YouTube</div>
    <div>On Sport App</div>
    <div>On Sport 1</div>
    <div>Tomorrow thursday, 20/08/2026</div>
    <div>20:00</div>
    <div>Europa League</div>
    <div>Playoffs</div>
    <div>Trabzonspor</div>
    <div>Ferencvaros</div>
    <div>On Sport 1</div>
    </body></html>
    """
    parsed = parse_channel_html(
        sample,
        "ONSport1",
        "ON Sport 1",
        "self-test",
    )

    # The runtime date window could exclude sample dates in future years.
    # Therefore test the structural extractor independently too.
    block1 = [
        "Trofeo Joan Gamper",
        "Barcelona",
        "Al Ahly",
        "FC Barcelona PPV YouTube",
        "On Sport App",
        "On Sport 1",
    ]
    assert _extract_event_from_block(
        block1, "ON Sport 1"
    ) == ("Trofeo Joan Gamper", "Barcelona", "Al Ahly")

    block2 = [
        "Europa League",
        "Playoffs",
        "Trabzonspor",
        "Ferencvaros",
        "On Sport 1",
    ]
    assert _extract_event_from_block(
        block2, "ON Sport 1"
    ) == ("Europa League", "Trabzonspor", "Ferencvaros")

    d = parse_date_line(
        "Football on TV today wednesday, 19/08/2026",
        datetime(2026, 8, 19, tzinfo=CAIRO),
    )
    assert d == date(2026, 8, 19)

    log("SELF TEST | PASS")


def main():
    log(
        "ON SPORT EPG | 1 + 2 + MAX + PLUS | "
        "NO CHANNEL GUESSING | Cairo source time -> Abu Dhabi + Las Vegas"
    )

    _self_test()

    events = collect_events()

    log(f"ON Sport total verified football events: {len(events)}")
    for ev in events:
        ad = ev["start"].astimezone(ABU_DHABI)
        lv = ev["start"].astimezone(LAS_VEGAS)
        log(
            f"  {ev['channel_name']} | "
            f"{ad:%Y-%m-%d %H:%M} أبو ظبي | "
            f"{lv:%Y-%m-%d %H:%M} لاس فيغاس | "
            f"{ev['title']} | {ev['competition']} | "
            f"{ev['source_name']}"
        )

    write_xml(events)


if __name__ == "__main__":
    main()
