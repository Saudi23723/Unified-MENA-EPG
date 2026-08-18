#!/usr/bin/env python3
import html, re, sys
from datetime import datetime, timedelta, date
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime.now(TZ)
OUT = Path("alwan_sports_epg.xml")
TELEGRAM_URL = "https://t.me/s/AlwanSports"
KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 7
VALID_CHANNELS = set(range(1, 11))

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ar,en;q=0.8",
}

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")
ALWAN_RE = re.compile(
    r"(?:ألوان|الوان|ALWAN)(?:\s+SPORTS?)?\s*[.\-:]?\s*(10|[1-9])\b",
    re.I,
)
MATCH_RE = re.compile(
    r"(.{2,100}?)\s*(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد|[-–—])\s*(.{2,100})",
    re.I,
)

AR_MONTHS = {
    "يناير":1,"فبراير":2,"مارس":3,"أبريل":4,"ابريل":4,"مايو":5,
    "يونيو":6,"يوليو":7,"أغسطس":8,"اغسطس":8,"سبتمبر":9,
    "أكتوبر":10,"اكتوبر":10,"نوفمبر":11,"ديسمبر":12,
}

BAD = ("please open telegram","view this post","جدول مباريات","جدول اليوم","جدول الغد")

def log(x): print(x, flush=True)
def warn(x): print(f"WARN {x}", file=sys.stderr, flush=True)

def norm(v):
    v = html.unescape(v or "").replace("\u200f"," ").replace("\u200e"," ").replace("\xa0"," ")
    return re.sub(r"[ \t]+"," ",v).strip()

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=35)
    r.raise_for_status()
    return r.text

def in_window(dt):
    return NOW - timedelta(days=KEEP_DAYS_BACK) <= dt <= NOW + timedelta(days=KEEP_DAYS_FORWARD)

def valid_title(t):
    low = norm(t).lower()
    return bool(low) and not any(x in low for x in BAD)

def telegram_post_date(post):
    tag = post.select_one("time[datetime]")
    if tag:
        try:
            return datetime.fromisoformat(tag.get("datetime","").replace("Z","+00:00")).astimezone(TZ).date()
        except Exception:
            pass
    return NOW.date()

def parse_date(text, reference):
    text = norm(text)
    low = text.lower()
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if m:
        d, mo, y = map(int, m.groups())
        try: return date(y, mo, d)
        except ValueError: pass
    months = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(rf"\b(\d{{1,2}})\s+({months})\s+(20\d{{2}})\b", text, re.I)
    if m:
        d, mo, y = int(m.group(1)), AR_MONTHS[m.group(2)], int(m.group(3))
        try: return date(y, mo, d)
        except ValueError: pass
    if "بعد غد" in low: return reference + timedelta(days=2)
    if any(x in low for x in ("غداً","غدا","بكرا","بكرة")): return reference + timedelta(days=1)
    if "اليوم" in low: return reference
    return None

def clean_team(v):
    v = norm(v)
    v = re.sub(r"^(?:⚽|🏆|📺|⏰|🕘|🕗|🕖|🔴|🟢|🔵|🟡|🟣|🟠|⚪|•|\||✅|🔥)+\s*","",v)
    v = re.sub(r"\s*(?:📺|⏰|🎙|🏟|القناة|الساعة).*$","",v,flags=re.I)
    return v.strip(" |:-")

def fixture_from_line(line):
    line = norm(line)
    if any(x in line.lower() for x in BAD): return None
    m = MATCH_RE.search(line)
    if not m: return None
    a, b = clean_team(m.group(1)), clean_team(m.group(2))
    if not a or not b or len(a)>70 or len(b)>70: return None
    return f"{a} - {b}"

def post_text(post):
    parts=[]
    for sel in (".tgme_widget_message_text",".tgme_widget_message_caption"):
        node=post.select_one(sel)
        if node:
            txt=node.get_text("\n",strip=True)
            if txt: parts.append(txt)
    if not parts:
        node=post.select_one(".tgme_widget_message_bubble")
        if node: parts.append(node.get_text("\n",strip=True))
    return html.unescape("\n".join(parts)).strip()

def split_blocks(text):
    lines=[norm(x) for x in text.splitlines() if norm(x)]
    blocks=[]
    for i,line in enumerate(lines):
        if fixture_from_line(line):
            blocks.append("\n".join(lines[max(0,i-3):min(len(lines),i+6)]))
    return list(dict.fromkeys(blocks))

def parse_post(post):
    text=post_text(post)
    if not text or "please open telegram" in text.lower(): return []
    post_day=telegram_post_date(post)
    default_day=parse_date(text,post_day) or post_day
    out=[]
    for block in split_blocks(text):
        title=None
        for line in block.splitlines():
            title=fixture_from_line(line)
            if title: break
        cm=ALWAN_RE.search(block)
        tm=TIME_RE.search(block)
        if not title or not cm or not tm: continue
        ch=int(cm.group(1))
        if ch not in VALID_CHANNELS: continue
        hh,mm=int(tm.group(1)),int(tm.group(2))
        low=block.lower()
        if ("pm" in low or "مساء" in low) and 1<=hh<=11: hh+=12
        if ("am" in low or "صباح" in low) and hh==12: hh=0
        day=parse_date(block,default_day) or default_day
        dt=datetime(day.year,day.month,day.day,hh,mm,tzinfo=TZ)
        if in_window(dt) and valid_title(title):
            out.append({"channel":ch,"start":dt,"title":title})
    return out

def key(e):
    return (int(e["channel"]), e["start"].strftime("%Y%m%d%H%M"), norm(e["title"]).casefold())

def dedupe(events):
    seen=set(); out=[]
    for e in sorted(events,key=lambda x:(x["start"],int(x["channel"]),x["title"])):
        k=key(e)
        if k not in seen:
            seen.add(k); out.append(e)
    return out

def old_channel_id(cid):
    if cid=="AlwanSports": return 1
    m=re.fullmatch(r"AlwanSports(10|[1-9])",cid or "",re.I)
    return int(m.group(1)) if m else None

def read_existing():
    if not OUT.exists(): return []
    try: root=ET.parse(OUT).getroot()
    except Exception as exc:
        warn(f"Existing XML unreadable: {exc}")
        return []
    out=[]
    for p in root.findall("programme"):
        ch=old_channel_id(p.get("channel") or "")
        if ch not in VALID_CHANNELS: continue
        try:
            dt=datetime.strptime((p.get("start") or "")[:14],"%Y%m%d%H%M%S").replace(tzinfo=TZ)
        except Exception:
            continue
        if not in_window(dt): continue
        t=p.find("title")
        title=norm(t.text) if t is not None else ""
        if valid_title(title):
            out.append({"channel":ch,"start":dt,"title":title})
    return out

def write_xml(events):
    tv=ET.Element("tv",{"generator-info-name":"Alwan Sports Telegram EPG"})
    # ALWAYS 10 CHANNELS
    for n in range(1,11):
        cid=f"AlwanSports{n}"
        ch=ET.SubElement(tv,"channel",{"id":cid})
        ET.SubElement(ch,"display-name",{"lang":"ar"}).text=f"ألوان الرياضية {n}"
        ET.SubElement(ch,"display-name",{"lang":"en"}).text=f"Alwan Sports {n}"
    for e in events:
        n=int(e["channel"])
        if n not in VALID_CHANNELS: continue
        cid=f"AlwanSports{n}"
        stop=e["start"]+timedelta(hours=3)
        p=ET.SubElement(tv,"programme",{
            "start":e["start"].strftime("%Y%m%d%H%M%S %z"),
            "stop":stop.strftime("%Y%m%d%H%M%S %z"),
            "channel":cid,
        })
        ET.SubElement(p,"title",{"lang":"ar"}).text=e["title"]
        ET.SubElement(p,"category",{"lang":"en"}).text="Sports"
        ET.SubElement(p,"desc",{"lang":"ar"}).text="مباراة منقولة على قنوات ألوان الرياضية"
    ET.indent(tv,space="  ")
    ET.ElementTree(tv).write(OUT,encoding="utf-8",xml_declaration=True)

def main():
    old=read_existing()
    log(f"Existing valid Alwan programmes kept: {len(old)}")
    fresh=[]
    try:
        soup=BeautifulSoup(fetch(TELEGRAM_URL),"html.parser")
        posts=soup.select(".tgme_widget_message")
        log(f"Alwan Telegram posts visible: {len(posts)}")
        for post in posts:
            fresh.extend(parse_post(post))
    except Exception as exc:
        warn(f"Telegram fetch failed: {exc}")
    fresh=dedupe(fresh)
    log(f"Alwan newly detected programmes: {len(fresh)}")
    final=dedupe(fresh if fresh else old)
    if not fresh and old:
        warn("No fresh Alwan data; preserving programmes while refreshing channels 1..10")
    log(f"Alwan total programmes written: {len(final)}")
    write_xml(final)
    log("Guaranteed channel definitions written: AlwanSports1 ... AlwanSports10")
    log(f"Written: {OUT}")

if __name__=="__main__":
    main()
