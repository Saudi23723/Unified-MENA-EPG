#!/usr/bin/env python3
import html, re, sys
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

TZ = ZoneInfo('Asia/Riyadh')
NOW = datetime.now(TZ)
THMANYAH_OUT = Path('thmanyah_epg.xml')
ALWAN_OUT = Path('alwan_sports_epg.xml')
GOAL_HOME = 'https://www.goal.com/ar'
KOOORA_HOME = 'https://www.kooora.com/'
ALWAN_TELEGRAM = 'https://t.me/s/AlwanSports'
KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 7
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36',
    'Accept-Language': 'ar,en;q=0.8',
}
TIME_RE = re.compile(r'\b([01]?\d|2[0-3])[:.]([0-5]\d)\b')
THMANYAH_CHANNEL_RE = re.compile(r'(?:ثمانية|thmanyah)\s*[.\-:]?\s*([1-7])\b', re.I)
ALWAN_CHANNEL_RE = re.compile(r'(?:ألوان|الوان|alwan)(?:\s+sports?)?\s*[.\-:]?\s*([1-9]|10)\b', re.I)
MATCH_SEP_RE = re.compile(r'\s+(?:-|–|—|vs\.?|v)\s+', re.I)
AR_MONTHS = {'يناير':1,'فبراير':2,'مارس':3,'أبريل':4,'ابريل':4,'مايو':5,'يونيو':6,'يوليو':7,'أغسطس':8,'اغسطس':8,'سبتمبر':9,'أكتوبر':10,'اكتوبر':10,'نوفمبر':11,'ديسمبر':12}

def log(m): print(m, flush=True)
def warn(m): print(f'WARN {m}', file=sys.stderr, flush=True)
def norm(v):
    v = html.unescape(v or '').replace('\u200f',' ').replace('\u200e',' ').replace('\xa0',' ')
    return re.sub(r'\s+', ' ', v).strip()
def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status(); return r.text

def parse_date(text, fallback=None):
    text = norm(text); low = text.lower(); today = NOW.date()
    m = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b', text)
    if m:
        d,mth,y = map(int,m.groups())
        try: return date(y,mth,d)
        except ValueError: pass
    months_pattern='|'.join(map(re.escape, AR_MONTHS))
    m = re.search(rf'\b(\d{{1,2}})\s+({months_pattern})\s+(20\d{{2}})\b', text, re.I)
    if m:
        d=int(m.group(1)); mth=AR_MONTHS[m.group(2)]; y=int(m.group(3))
        try: return date(y,mth,d)
        except ValueError: pass
    if any(x in low for x in ['غداً','غدا','بكرا','بكرة']): return today + timedelta(days=1)
    if 'اليوم' in low: return today
    return fallback

def make_dt(day,hh,mm): return datetime(day.year,day.month,day.day,int(hh),int(mm),tzinfo=TZ)
def programme_key(e): return (str(e['channel']), e['start'].strftime('%Y%m%d%H%M'), norm(e['title']).casefold())
def dedupe(events):
    out=[]; seen=set()
    for e in sorted(events,key=lambda x:(x['start'],str(x['channel']),x['title'])):
        k=programme_key(e)
        if k not in seen: seen.add(k); out.append(e)
    return out

def in_keep_window(dt): return NOW-timedelta(days=KEEP_DAYS_BACK) <= dt <= NOW+timedelta(days=KEEP_DAYS_FORWARD)

def read_existing_xml(path, kind):
    if not path.exists(): return []
    try: root=ET.parse(path).getroot()
    except Exception as exc: warn(f'could not read existing {path}: {exc}'); return []
    events=[]
    for p in root.findall('programme'):
        raw=(p.get('start') or '').strip()
        try: start=datetime.strptime(raw[:14],'%Y%m%d%H%M%S').replace(tzinfo=TZ)
        except Exception: continue
        if not in_keep_window(start): continue
        title_el=p.find('title')
        if title_el is None or not norm(title_el.text): continue
        cid=p.get('channel') or ''
        if kind=='thmanyah':
            m=re.search(r'Thmanyah([1-7])',cid,re.I)
            if not m: continue
            channel=int(m.group(1))
        else:
            m=re.search(r'AlwanSports(?:([1-9]|10))?',cid,re.I); channel=int(m.group(1)) if m and m.group(1) else 1
        desc=p.find('desc')
        events.append({'channel':channel,'start':start,'title':norm(title_el.text),'source':norm(desc.text) if desc is not None else 'existing XML'})
    return events

def discover_schedule_articles(home_url, name):
    try: soup=BeautifulSoup(fetch(home_url),'html.parser')
    except Exception as exc: warn(f'{name} discovery failed: {exc}'); return []
    urls=[]; seen=set()
    for a in soup.find_all('a',href=True):
        label=norm(a.get_text(' ',strip=True)); href=a.get('href',''); combined=f'{label} {href}'
        if 'جدول مباريات اليوم' not in combined: continue
        url=urljoin(home_url,href).split('#',1)[0]
        if url not in seen: seen.add(url); urls.append(url)
    log(f'{name} schedule articles discovered: {len(urls)}')
    return urls[:12]

def extract_article_date(soup):
    candidates=[]
    for tag in [soup.find('h1'), soup.find('title')]:
        if tag: candidates.append(norm(tag.get_text(' ',strip=True)))
    for tag in soup.find_all(['h2','h3'],limit=15):
        txt=norm(tag.get_text(' ',strip=True))
        if 'جدول مباريات اليوم' in txt: candidates.append(txt)
    candidates.append(norm(soup.get_text(' ',strip=True))[:5000])
    for t in candidates:
        d=parse_date(t)
        if d: return d
    return None

def parse_thmanyah_article(url):
    try: soup=BeautifulSoup(fetch(url),'html.parser')
    except Exception as exc: warn(f'Thmanyah article failed {url}: {exc}'); return []
    day=extract_article_date(soup) or NOW.date(); events=[]
    for tr in soup.find_all('tr'):
        cells=[norm(x.get_text(' ',strip=True)) for x in tr.find_all(['th','td'])]
        cells=[x for x in cells if x]; joined=' | '.join(cells)
        cm=THMANYAH_CHANNEL_RE.search(joined); tm=TIME_RE.search(joined)
        if not cm or not tm: continue
        title=next((c for c in cells if MATCH_SEP_RE.search(c) and not THMANYAH_CHANNEL_RE.search(c)), cells[0] if cells else None)
        if not title or title=='المباراة': continue
        events.append({'channel':int(cm.group(1)),'start':make_dt(day,tm.group(1),tm.group(2)),'title':norm(title),'source':url})
    if events: return dedupe(events)
    lines=[norm(x) for x in soup.get_text('\n',strip=True).splitlines() if norm(x)]
    for i,line in enumerate(lines):
        cm=THMANYAH_CHANNEL_RE.search(line)
        if not cm: continue
        block=lines[max(0,i-5):min(len(lines),i+5)]; joined=' | '.join(block); tm=TIME_RE.search(joined)
        if not tm: continue
        title=next((c for c in block if MATCH_SEP_RE.search(c) and not THMANYAH_CHANNEL_RE.search(c)),None)
        if title: events.append({'channel':int(cm.group(1)),'start':make_dt(day,tm.group(1),tm.group(2)),'title':norm(title),'source':url})
    return dedupe(events)

def scrape_thmanyah():
    urls=list(dict.fromkeys(discover_schedule_articles(GOAL_HOME,'Goal')+discover_schedule_articles(KOOORA_HOME,'Kooora')))
    events=[]
    for url in urls:
        found=parse_thmanyah_article(url)
        if found: log(f'Thmanyah: {len(found)} programme(s) from {url}'); events.extend(found)
    events=[e for e in dedupe(events) if in_keep_window(e['start'])]
    log(f'Thmanyah newly detected programmes: {len(events)}'); return events

def telegram_post_date(post):
    t=post.select_one('time[datetime]')
    if t:
        try: return datetime.fromisoformat(t.get('datetime','').replace('Z','+00:00')).astimezone(TZ).date()
        except Exception: pass
    return None

def extract_alwan_title(text):
    lines=[norm(x) for x in re.split(r'[\n\r]+',text) if norm(x)]
    for line in lines:
        if MATCH_SEP_RE.search(line): return line
    m=re.search(r'([^\n|•]{2,80}?\s+(?:-|–|—|vs\.?|v)\s+[^\n|•]{2,80})',text,re.I)
    return norm(m.group(1)) if m else None

def parse_alwan_post(post):
    node=post.select_one('.tgme_widget_message_text') or post.select_one('.tgme_widget_message_bubble')
    if not node: return []
    text=html.unescape(node.get_text('\n',strip=True) or '').strip()
    if not text: return []
    times=list(TIME_RE.finditer(text)); title=extract_alwan_title(text)
    if not times or not title: return []
    day=parse_date(text, fallback=telegram_post_date(post) or NOW.date())
    cm=ALWAN_CHANNEL_RE.search(text); channel=int(cm.group(1)) if cm else 1
    tm=times[0]
    return [{'channel':channel,'start':make_dt(day,tm.group(1),tm.group(2)),'title':title,'source':ALWAN_TELEGRAM}]

def scrape_alwan():
    try: soup=BeautifulSoup(fetch(ALWAN_TELEGRAM),'html.parser')
    except Exception as exc: warn(f'Alwan Telegram fetch failed: {exc}'); return []
    posts=soup.select('.tgme_widget_message'); log(f'Alwan Telegram posts visible: {len(posts)}')
    events=[]
    for p in posts: events.extend(parse_alwan_post(p))
    events=[e for e in dedupe(events) if in_keep_window(e['start'])]
    log(f'Alwan newly detected programmes: {len(events)}'); return events

def merge_with_existing(existing,fresh):
    merged={programme_key(e):e for e in existing}
    for e in fresh: merged[programme_key(e)]=e
    return dedupe([e for e in merged.values() if in_keep_window(e['start'])])

def write_xml(path,kind,events):
    if kind=='thmanyah': nums=list(range(1,8)); prefix='Thmanyah'; ar='ثمانية'; gen='Thmanyah Sports EPG'
    else: nums=sorted({int(e['channel']) for e in events}) or [1]; prefix='AlwanSports'; ar='ألوان الرياضية'; gen='Alwan Sports EPG'
    tv=ET.Element('tv',{'generator-info-name':gen})
    for n in nums:
        if kind=='thmanyah': cid=f'{prefix}{n}.sa'; da=f'{ar} {n}'; de=f'Thmanyah {n}'
        else: cid=prefix if n==1 else f'{prefix}{n}'; da=ar if n==1 else f'{ar} {n}'; de='Alwan Sports' if n==1 else f'Alwan Sports {n}'
        ch=ET.SubElement(tv,'channel',{'id':cid}); ET.SubElement(ch,'display-name',{'lang':'ar'}).text=da; ET.SubElement(ch,'display-name',{'lang':'en'}).text=de
    for e in events:
        cid=f"Thmanyah{int(e['channel'])}.sa" if kind=='thmanyah' else ('AlwanSports' if int(e['channel'])==1 else f"AlwanSports{int(e['channel'])}")
        stop=e['start']+timedelta(hours=3)
        p=ET.SubElement(tv,'programme',{'start':e['start'].strftime('%Y%m%d%H%M%S %z'),'stop':stop.strftime('%Y%m%d%H%M%S %z'),'channel':cid})
        ET.SubElement(p,'title',{'lang':'ar'}).text=e['title']; ET.SubElement(p,'category',{'lang':'en'}).text='Sports'; ET.SubElement(p,'desc',{'lang':'ar'}).text=f"المصدر: {e['source']}"
    ET.indent(tv,space='  '); ET.ElementTree(tv).write(path,encoding='utf-8',xml_declaration=True)

def main():
    old_t=read_existing_xml(THMANYAH_OUT,'thmanyah'); old_a=read_existing_xml(ALWAN_OUT,'alwan')
    log(f'Existing Thmanyah programmes kept: {len(old_t)}'); log(f'Existing Alwan programmes kept: {len(old_a)}')
    fresh_t=scrape_thmanyah(); fresh_a=scrape_alwan(); t=merge_with_existing(old_t,fresh_t); a=merge_with_existing(old_a,fresh_a)
    log(f'Thmanyah total programmes after merge: {len(t)}')
    for e in t: log(f"  THMANYAH {e['channel']} | {e['start']:%Y-%m-%d %H:%M} | {e['title']}")
    log(f'Alwan total programmes after merge: {len(a)}')
    for e in a: log(f"  ALWAN {e['channel']} | {e['start']:%Y-%m-%d %H:%M} | {e['title']}")
    if t or not THMANYAH_OUT.exists(): write_xml(THMANYAH_OUT,'thmanyah',t); log(f'Written: {THMANYAH_OUT}')
    else: warn('Thmanyah scrape returned no data; existing XML left untouched')
    if a or not ALWAN_OUT.exists(): write_xml(ALWAN_OUT,'alwan',a); log(f'Written: {ALWAN_OUT}')
    else: warn('Alwan scrape returned no data; existing XML left untouched')

if __name__=='__main__': main()
