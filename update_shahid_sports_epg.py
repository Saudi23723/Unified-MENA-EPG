#!/usr/bin/env python3
import html
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

TZ = ZoneInfo('Asia/Riyadh')
ABU_DHABI_TZ = ZoneInfo('Asia/Dubai')
VEGAS_TZ = ZoneInfo('America/Los_Angeles')
NOW = datetime.now(TZ)
OUT = Path('shahid_sports_epg.xml')
CHANNEL_ID = 'ShahidSportsGuide'

GOAL_HOME = 'https://www.goal.com/ar'
KOOORA_HOME = 'https://www.kooora.com/'
LIVE_SOCCER_TV = 'https://www.livesoccertv.com/channels/shahid/'

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 10

HEADERS = {
    'User-Agent': 'Mozilla/5.0 AppleWebKit/537.36 Chrome/126.0 Safari/537.36',
    'Accept-Language': 'ar,en;q=0.8',
}

TIME_RE = re.compile(r'(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)')
MATCH_RE = re.compile(r'(.{2,100}?)\s*(?:🆚|⚔️|⚔|vs\.?|v\.?|ضد|[-–—])\s*(.{2,100})', re.I)
SHAHID_RE = re.compile(
    r"(?:mbc\s*)?(?:شاهد|shahid)"
    r"|(?:شاهد|shahid)\s*(?:vip|sports?)?"
    r"|mbc\s*(?:sports?|sport)"
    r"|mbc\s*(?:شاهد|shahid)\s*(?:vip|sports?)?",
    re.I,
)
AR_MONTHS = {
    'يناير':1,'فبراير':2,'مارس':3,'أبريل':4,'ابريل':4,'مايو':5,'يونيو':6,
    'يوليو':7,'أغسطس':8,'اغسطس':8,'سبتمبر':9,'أكتوبر':10,'اكتوبر':10,
    'نوفمبر':11,'ديسمبر':12,
}


def log(msg):
    print(msg, flush=True)


def warn(msg):
    print(f'WARN {msg}', file=sys.stderr, flush=True)


def norm(value):
    value = html.unescape(value or '').replace('\u200f',' ').replace('\u200e',' ').replace('\xa0',' ')
    return re.sub(r'[ \t]+', ' ', value).strip()



def shahid_marker_text(node):
    """
    Collect visible text plus HTML hints that may identify Shahid/MBC branding
    without OCR: alt/title/src/href/class/id/aria-label/data-*.
    """
    parts = []

    try:
        parts.append(norm(node.get_text(" ", strip=True)))
    except Exception:
        pass

    if hasattr(node, "attrs"):
        for key, value in node.attrs.items():
            if key in ("title", "aria-label", "href", "src", "class", "id") or str(key).startswith("data-"):
                if isinstance(value, (list, tuple)):
                    value = " ".join(map(str, value))
                parts.append(norm(str(value)))

    try:
        for child in node.find_all(True):
            for key in ("alt", "title", "aria-label", "href", "src", "class", "id"):
                value = child.get(key)
                if not value:
                    continue
                if isinstance(value, (list, tuple)):
                    value = " ".join(map(str, value))
                parts.append(norm(str(value)))
    except Exception:
        pass

    return " | ".join(part for part in parts if part)


def has_shahid_marker(node_or_text):
    if isinstance(node_or_text, str):
        haystack = norm(node_or_text)
    else:
        haystack = shahid_marker_text(node_or_text)

    return bool(SHAHID_RE.search(haystack))


def nearby_structural_block(node):
    candidates = [node]
    parent = getattr(node, "parent", None)

    for _ in range(3):
        if parent is None:
            break
        candidates.append(parent)
        parent = getattr(parent, "parent", None)

    for candidate in candidates:
        text = shahid_marker_text(candidate)
        if has_shahid_marker(text) and extract_time(text):
            return candidate, text

    return node, shahid_marker_text(node)

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text


def in_window(dt):
    return NOW - timedelta(days=KEEP_DAYS_BACK) <= dt <= NOW + timedelta(days=KEEP_DAYS_FORWARD)


def parse_date(text, reference=None):
    text = norm(text)
    low = text.lower()
    reference = reference or NOW.date()
    m = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b', text)
    if m:
        d, mo, y = map(int, m.groups())
        try: return date(y, mo, d)
        except ValueError: pass
    months = '|'.join(map(re.escape, AR_MONTHS))
    m = re.search(rf'\b(\d{{1,2}})\s+({months})(?:\s+(20\d{{2}}))?\b', text, re.I)
    if m:
        d, mo = int(m.group(1)), AR_MONTHS[m.group(2)]
        y = int(m.group(3)) if m.group(3) else reference.year
        try:
            candidate = date(y, mo, d)
            if candidate < reference - timedelta(days=180):
                candidate = date(y+1, mo, d)
            return candidate
        except ValueError: pass
    if 'بعد غد' in low: return reference + timedelta(days=2)
    if any(x in low for x in ('غداً','غدا','بكرا','بكرة','tomorrow')): return reference + timedelta(days=1)
    if any(x in low for x in ('اليوم','today')): return reference
    return None


def extract_time(text):
    text = norm(text)
    m = TIME_RE.search(text)
    if not m: return None
    h, minute = int(m.group(1)), int(m.group(2))
    nearby = text[max(0,m.start()-18):min(len(text),m.end()+22)].casefold()
    if 1 <= h <= 11 and ('مساء' in nearby or 'pm' in nearby): h += 12
    elif h == 12 and ('صباح' in nearby or 'am' in nearby): h = 0
    return h, minute


def make_dt(day, hour, minute):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def clean_fixture_side(value):
    value = norm(value)

    # Remove common bullets/icons/noise.
    value = re.sub(r"^(?:⚽|🏆|📺|⏰|•|\||✅|🔥|🎙️|🎙|🗓️|🗓)+\s*", "", value)

    # Remove leading/trailing punctuation.
    value = value.strip(" |:-–—")

    return value


def looks_like_team_name(value):
    """
    Reject dates, times, author/date metadata, scores and article boilerplate.
    A team side should look like a short club/country name, not page metadata.
    """
    value = clean_fixture_side(value)

    if not value:
        return False

    low = value.casefold()

    # Obvious article/date/time noise.
    bad_words = (
        "أغسطس", "اغسطس", "سبتمبر", "أكتوبر", "اكتوبر", "نوفمبر", "ديسمبر",
        "يناير", "فبراير", "مارس", "أبريل", "ابريل", "مايو", "يونيو", "يوليو",
        "اليوم", "غدا", "غداً", "أمس", "امس",
        "بتوقيت", "الساعة", "موعد", "مواعيد",
        "المصدر", "كتب", "تحرير", "آخر تحديث", "اخر تحديث",
        "views", "view", "edited",
    )

    if any(word in low for word in bad_words):
        return False

    # Reject strings dominated by digits/time/date syntax.
    if re.search(r"\b20\d{2}\b", value):
        return False
    if TIME_RE.search(value):
        return False
    if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", value):
        return False

    digits = sum(ch.isdigit() for ch in value)
    letters = sum(ch.isalpha() for ch in value)

    if letters < 2:
        return False

    if digits > max(2, letters // 2):
        return False

    # Keep names compact; article metadata tends to be long.
    words = value.split()
    if len(words) > 7:
        return False

    if len(value) > 60:
        return False

    return True


def fixture_from_text(text):
    text = norm(text)

    # Prefer explicit VS-style separators.
    separators = (
        r"🆚",
        r"⚔️?",
        r"\bvs\.?\b",
        r"\bv\.?\b",
        r"\bضد\b",
        r"\s[-–—]\s",
    )

    for sep in separators:
        m = re.search(rf"(.{{2,70}}?)\s*(?:{sep})\s*(.{{2,70}})", text, re.I)
        if not m:
            continue

        first = clean_fixture_side(m.group(1))
        second = clean_fixture_side(m.group(2))

        if not looks_like_team_name(first) or not looks_like_team_name(second):
            continue

        return f"{first} - {second}"

    return None

def fixture_key(e):
    return (e['start'].strftime('%Y%m%d%H%M'), norm(e['title']).casefold())


def dedupe(events):
    out, seen = [], set()
    for e in sorted(events, key=lambda x:(x['start'], x['title'])):
        k = fixture_key(e)
        if k in seen: continue
        seen.add(k); out.append(e)
    return out


def article_date(soup):
    candidates = []
    for selector in ('h1','title'):
        tag = soup.select_one(selector)
        if tag: candidates.append(norm(tag.get_text(' ', strip=True)))
    candidates.append(norm(soup.get_text(' ', strip=True))[:6000])
    for c in candidates:
        d = parse_date(c, NOW.date())
        if d: return d
    return NOW.date()


def discover_daily_articles(home_url, label):
    try:
        soup = BeautifulSoup(fetch(home_url), 'html.parser')
    except Exception as exc:
        warn(f'{label} discovery failed: {exc}')
        return []
    urls, seen = [], set()
    for a in soup.find_all('a', href=True):
        text = norm(a.get_text(' ', strip=True))
        href = a['href']
        if 'جدول مباريات اليوم' not in f'{text} {href}':
            continue
        url = urljoin(home_url, href).split('#',1)[0]
        if url in seen: continue
        seen.add(url); urls.append(url)
    log(f'{label} schedule articles discovered: {len(urls)}')
    return urls[:10]


def parse_daily_article(url, label):
    """
    Detect Shahid matches from visible text and HTML/logo metadata.

    Supported markers include:
      Shahid / شاهد
      MBC Shahid / MBC شاهد
      Shahid VIP / شاهد VIP
      MBC Sports

    Also reads alt/title/src/class/aria-label around logos without OCR.
    """
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception as exc:
        warn(f"{label} schedule failed {url}: {exc}")
        return []

    day = article_date(soup)
    events = []

    def build_event_from_node(node):
        block_node, joined = nearby_structural_block(node)

        if not has_shahid_marker(joined):
            return None

        time_value = extract_time(joined)
        if not time_value:
            return None

        title = None

        try:
            chunks = [
                norm(x.get_text(" ", strip=True))
                for x in block_node.find_all(
                    ["td", "th", "div", "span", "a", "p", "li"],
                    recursive=True,
                )
            ]
        except Exception:
            chunks = []

        chunks = [x for x in chunks if x]

        for chunk in chunks:
            candidate = fixture_from_text(chunk)
            if candidate:
                title = candidate
                break

        if not title:
            title = fixture_from_text(norm(block_node.get_text(" ", strip=True)))

        if not title:
            return None

        # Final guard against article metadata being mistaken for a fixture.
        parts = [part.strip() for part in title.split(" - ", 1)]
        if len(parts) != 2 or not all(looks_like_team_name(part) for part in parts):
            return None

        block_day = parse_date(joined, day) or day
        start = make_dt(block_day, time_value[0], time_value[1])

        if not in_window(start):
            return None

        return {
            "start": start,
            "title": title,
            "source": f"{label}: {url}",
        }

    candidate_nodes = []

    for selector in (
        "tr",
        "article",
        "li",
        "[class*='match']",
        "[class*='fixture']",
        "[class*='game']",
        "[class*='event']",
    ):
        candidate_nodes.extend(soup.select(selector))

    seen_nodes = set()

    for node in candidate_nodes:
        marker = id(node)
        if marker in seen_nodes:
            continue
        seen_nodes.add(marker)

        if not has_shahid_marker(node):
            continue

        event = build_event_from_node(node)
        if event:
            events.append(event)

    # Detect logos / badges that identify Shahid even if visible text omits it.
    for node in soup.find_all(True):
        attrs_text = " ".join(
            norm(str(node.get(key) or ""))
            for key in ("alt", "title", "aria-label", "src", "href", "class", "id")
        )

        if not has_shahid_marker(attrs_text):
            continue

        event = build_event_from_node(node)
        if event:
            events.append(event)

    # Plain-text fallback.
    if not events:
        lines = [
            norm(x)
            for x in soup.get_text("\n", strip=True).splitlines()
            if norm(x)
        ]

        for i, line in enumerate(lines):
            block_lines = lines[max(0, i - 4):min(len(lines), i + 5)]
            block = " | ".join(block_lines)

            if not has_shahid_marker(block):
                continue

            time_value = extract_time(block)
            if not time_value:
                continue

            title = None
            for candidate_line in block_lines:
                candidate = fixture_from_text(candidate_line)
                if candidate:
                    title = candidate
                    break

            if not title:
                continue

            block_day = parse_date(block, day) or day
            start = make_dt(block_day, time_value[0], time_value[1])

            if in_window(start):
                events.append({
                    "start": start,
                    "title": title,
                    "source": f"{label}: {url}",
                })

    events = dedupe(events)

    if events:
        log(f"{label} Shahid fixtures from {url}: {len(events)}")

    return events

def parse_livesoccertv():
    try:
        soup = BeautifulSoup(fetch(LIVE_SOCCER_TV), "html.parser")
    except Exception as exc:
        warn(f"LiveSoccerTV failed: {exc}")
        return []

    events = []

    for node in soup.find_all(["tr", "li", "article", "div"]):
        text = shahid_marker_text(node)
        title = fixture_from_text(norm(node.get_text(" ", strip=True)))

        if not title:
            continue

        time_value = extract_time(text)
        day = parse_date(text, NOW.date())

        if not time_value or not day:
            continue

        start = make_dt(day, time_value[0], time_value[1])

        if in_window(start):
            events.append({
                "start": start,
                "title": title,
                "source": LIVE_SOCCER_TV,
            })

    if not events:
        lines = [
            norm(x)
            for x in soup.get_text("\n", strip=True).splitlines()
            if norm(x)
        ]

        for i, line in enumerate(lines):
            title = fixture_from_text(line)
            if not title:
                continue

            block = " | ".join(lines[max(0, i - 4):min(len(lines), i + 5)])
            time_value = extract_time(block)
            day = parse_date(block, NOW.date())

            if not time_value or not day:
                continue

            start = make_dt(day, time_value[0], time_value[1])

            if in_window(start):
                events.append({
                    "start": start,
                    "title": title,
                    "source": LIVE_SOCCER_TV,
                })

    events = dedupe(events)
    log(f"LiveSoccerTV Shahid fixtures detected: {len(events)}")
    return events

def read_existing():
    if not OUT.exists(): return []
    try: root = ET.parse(OUT).getroot()
    except Exception as exc:
        warn(f'Existing Shahid XML unreadable: {exc}')
        return []
    fillers = {'مباريات Shahid Sports اليوم','لا توجد مباريات مجدولة','لا توجد مباراة حالياً','No scheduled matches'}
    events = []
    for p in root.findall('programme'):
        if (p.get('channel') or '') != CHANNEL_ID: continue
        try: start = datetime.strptime((p.get('start') or '')[:14], '%Y%m%d%H%M%S').replace(tzinfo=TZ)
        except Exception: continue
        if not in_window(start): continue
        n = p.find('title'); title = norm(n.text) if n is not None else ''
        if not title or title in fillers or ' / ' in title: continue
        events.append({'start':start,'title':title,'source':'existing XML'})
    return dedupe(events)


def merge_existing(existing, fresh):
    merged = {fixture_key(e):e for e in existing}
    for e in fresh: merged[fixture_key(e)] = e
    return dedupe([e for e in merged.values() if in_window(e['start'])])


def write_xml(events):
    tv = ET.Element('tv', {'generator-info-name':'Shahid Sports Daily Guide'})
    ch = ET.SubElement(tv, 'channel', {'id':CHANNEL_ID})
    ET.SubElement(ch, 'display-name', {'lang':'en'}).text = 'Shahid Sports | Guide'
    ET.SubElement(ch, 'display-name', {'lang':'ar'}).text = 'شاهد الرياضية | Guide'

    window_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = window_start + timedelta(days=KEEP_DAYS_FORWARD+1)
    by_day = defaultdict(list)
    for e in events:
        if in_window(e['start']): by_day[e['start'].date()].append(e)

    def desc_for(day, day_events):
        if not day_events:
            return f'مباريات Shahid Sports - {day:%Y-%m-%d}\n\nلا توجد مباريات مجدولة.'
        lines = [f'مباريات Shahid Sports - {day:%Y-%m-%d}', '']
        for e in sorted(day_events, key=lambda x:(x['start'],x['title'])):
            abu_dhabi_time = e['start'].astimezone(ABU_DHABI_TZ)
            vegas_time = e['start'].astimezone(VEGAS_TZ)
            lines.append(
                f"{abu_dhabi_time:%H:%M} أبو ظبي | "
                f"{vegas_time:%H:%M} لاس فيغاس | "
                f"{e['title']}"
            )
        return '\n'.join(lines)

    def add(start, stop, title, desc):
        if stop <= start: return
        p = ET.SubElement(tv, 'programme', {
            'start':start.strftime('%Y%m%d%H%M%S %z'),
            'stop':stop.strftime('%Y%m%d%H%M%S %z'),
            'channel':CHANNEL_ID,
        })
        ET.SubElement(p, 'title', {'lang':'ar'}).text = title
        ET.SubElement(p, 'category', {'lang':'en'}).text = 'Sports'
        ET.SubElement(p, 'desc', {'lang':'ar'}).text = desc

    day_cursor = window_start
    while day_cursor < window_end:
        day_start = day_cursor
        day_stop = min(day_start + timedelta(days=1), window_end)
        current_day = day_start.date()
        unique = {fixture_key(e):e for e in by_day.get(current_day, []) if day_start <= e['start'] < day_stop}
        day_events = sorted(unique.values(), key=lambda x:(x['start'],x['title']))
        desc = desc_for(current_day, day_events)
        if not day_events:
            add(day_start, day_stop, 'لا توجد مباريات مجدولة', desc)
            day_cursor = day_stop
            continue
        groups = defaultdict(list)
        for e in day_events: groups[e['start']].append(e)
        times = sorted(groups)
        if times[0] > day_start:
            add(day_start, times[0], 'مباريات Shahid Sports اليوم', desc)
        for i, kickoff in enumerate(times):
            stop = min(times[i+1], day_stop) if i+1 < len(times) else min(kickoff + timedelta(hours=3), day_stop)
            title = ' / '.join(e['title'] for e in sorted(groups[kickoff], key=lambda x:x['title']))
            add(kickoff, stop, title, desc)
        last_stop = min(times[-1] + timedelta(hours=3), day_stop)
        if last_stop < day_stop:
            add(last_stop, day_stop, 'مباريات Shahid Sports اليوم', desc)
        day_cursor = day_stop

    ET.indent(tv, space='  ')
    ET.ElementTree(tv).write(OUT, encoding='utf-8', xml_declaration=True)

    root = ET.parse(OUT).getroot()
    slots = []
    for p in root.findall('programme'):
        if p.get('channel') != CHANNEL_ID: continue
        s = datetime.strptime((p.get('start') or '')[:14], '%Y%m%d%H%M%S').replace(tzinfo=TZ)
        e = datetime.strptime((p.get('stop') or '')[:14], '%Y%m%d%H%M%S').replace(tzinfo=TZ)
        slots.append((s,e))
    slots.sort()
    for i in range(1,len(slots)):
        if slots[i][0] < slots[i-1][1]:
            raise RuntimeError('Shahid Guide XML validation failed: overlapping programmes')
    current = any(s <= NOW < e for s,e in slots)
    log('SHAHID CURRENT COVERAGE | ' + ('YES' if current else 'NO'))
    log('SHAHID GUIDE DAYS | ' + ', '.join(f'{d}:{len(v)}' for d,v in sorted(by_day.items())))
    if not current:
        raise RuntimeError('Shahid Guide XML validation failed: no current coverage')


def main():
    log('SHAHID SPORTS GUIDE v3 | strict fixtures + HTML/logo detection | Abu Dhabi + Las Vegas')
    existing = read_existing()
    log(f'Existing REAL Shahid programmes kept: {len(existing)}')
    urls = discover_daily_articles(GOAL_HOME,'Goal') + discover_daily_articles(KOOORA_HOME,'Kooora')
    urls = list(dict.fromkeys(urls))
    fresh = []
    for url in urls:
        fresh.extend(parse_daily_article(url, 'Goal' if 'goal.com' in url else 'Kooora'))
    fresh.extend(parse_livesoccertv())
    fresh = dedupe(fresh)
    log(f'Shahid newly detected programmes: {len(fresh)}')
    for e in fresh:
        abu_dhabi_time = e['start'].astimezone(ABU_DHABI_TZ)
        vegas_time = e['start'].astimezone(VEGAS_TZ)
        log(
            f"  SHAHID GUIDE | "
            f"{abu_dhabi_time:%Y-%m-%d %H:%M} أبو ظبي | "
            f"{vegas_time:%Y-%m-%d %H:%M} لاس فيغاس | "
            f"{e['title']}"
        )
    merged = merge_existing(existing, fresh)
    log(f'Shahid total REAL programmes after merge: {len(merged)}')
    write_xml(merged)
    log(f'Written: {OUT}')


if __name__ == '__main__':
    main()
