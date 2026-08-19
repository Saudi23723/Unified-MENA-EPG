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
SHAHID_RE = re.compile(r'(?:mbc\s*)?شاهد|shahid|mbc\s*shahid', re.I)
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


def fixture_from_text(text):
    m = MATCH_RE.search(norm(text))
    if not m: return None
    a = norm(m.group(1)).strip(' |:-')
    b = norm(m.group(2)).strip(' |:-')
    if not a or not b or len(a) > 80 or len(b) > 80: return None
    return f'{a} - {b}'


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
    try:
        soup = BeautifulSoup(fetch(url), 'html.parser')
    except Exception as exc:
        warn(f'{label} schedule failed {url}: {exc}')
        return []
    day = article_date(soup)
    events = []
    for row in soup.find_all('tr'):
        cells = [norm(c.get_text(' ', strip=True)) for c in row.find_all(['td','th'])]
        cells = [c for c in cells if c]
        joined = ' | '.join(cells)
        if not SHAHID_RE.search(joined): continue
        tv = extract_time(joined)
        if not tv: continue
        title = next((fixture_from_text(c) for c in cells if fixture_from_text(c)), None) or fixture_from_text(joined)
        if not title: continue
        start = make_dt(day, tv[0], tv[1])
        if in_window(start): events.append({'start':start,'title':title,'source':f'{label}: {url}'})
    if not events:
        lines = [norm(x) for x in soup.get_text('\n', strip=True).splitlines() if norm(x)]
        for i, line in enumerate(lines):
            block_lines = lines[max(0,i-3):min(len(lines),i+4)]
            block = ' | '.join(block_lines)
            if not SHAHID_RE.search(block): continue
            tv = extract_time(block)
            if not tv: continue
            title = next((fixture_from_text(c) for c in block_lines if fixture_from_text(c)), None)
            if not title: continue
            d = parse_date(block, day) or day
            start = make_dt(d, tv[0], tv[1])
            if in_window(start): events.append({'start':start,'title':title,'source':f'{label}: {url}'})
    events = dedupe(events)
    if events: log(f'{label} Shahid fixtures from {url}: {len(events)}')
    return events


def parse_livesoccertv():
    try:
        soup = BeautifulSoup(fetch(LIVE_SOCCER_TV), 'html.parser')
    except Exception as exc:
        warn(f'LiveSoccerTV failed: {exc}')
        return []
    lines = [norm(x) for x in soup.get_text('\n', strip=True).splitlines() if norm(x)]
    events = []
    for i, line in enumerate(lines):
        title = fixture_from_text(line)
        if not title: continue
        block = ' | '.join(lines[max(0,i-4):min(len(lines),i+5)])
        tv = extract_time(block)
        d = parse_date(block, NOW.date())
        if not tv or not d: continue
        start = make_dt(d, tv[0], tv[1])
        if in_window(start): events.append({'start':start,'title':title,'source':LIVE_SOCCER_TV})
    events = dedupe(events)
    log(f'LiveSoccerTV Shahid fixtures detected: {len(events)}')
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
            vegas_time = e['start'].astimezone(VEGAS_TZ)
            lines.append(
                f"{e['start']:%H:%M} مكة | "
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
    log('SHAHID SPORTS GUIDE | text sources only')
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
        vegas_time = e['start'].astimezone(VEGAS_TZ)
        log(
            f"  SHAHID GUIDE | "
            f"{e['start']:%Y-%m-%d %H:%M} مكة | "
            f"{vegas_time:%Y-%m-%d %H:%M} لاس فيغاس | "
            f"{e['title']}"
        )
    merged = merge_existing(existing, fresh)
    log(f'Shahid total REAL programmes after merge: {len(merged)}')
    write_xml(merged)
    log(f'Written: {OUT}')


if __name__ == '__main__':
    main()
