import re, glob, requests, unicodedata, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
STOP = {"al", "fc", "sc", "cf", "afc", "club", "de", "the", "united", "city", "real", "sporting", "fk", "sk", "ac", "as", "cd", "ud", "1"}
def toks(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("nott'm", "nottingham").replace("man utd", "manchester").replace("man city", "manchester").replace("utd", "")
    return {w for w in re.findall(r"[a-z]{3,}", s) if w not in STOP}
ref = []
today = datetime.now(timezone.utc).date()
for d in range(-1, 8):
    day = today + timedelta(days=d)
    try:
        j = requests.get(f"https://www.fotmob.com/api/data/matches?date={day:%Y%m%d}", headers=H, timeout=60).json()
    except Exception as e:
        print("fotmob fail", day, e); continue
    for lg in j.get("leagues", []):
        for m in lg.get("matches", []):
            ut = (m.get("status") or {}).get("utcTime")
            if not ut: continue
            st = datetime.fromisoformat(ut.replace("Z", "+00:00"))
            ref.append((toks(m["home"]["name"]), toks(m["away"]["name"]), st, f"{m['home']['name']} - {m['away']['name']} [{lg.get('name')}]"))
SEP = re.compile(r"\s+(?:-|–|×|vs\.?|v)\s+", re.I)
def clean(t):
    t = re.sub(r"[⁦-⁩‎‏‪-‮]", "", t)
    return re.sub(r"[⏰🔵🔴⚽•●·]|\bLive\b|\(.*?\)|\[.*?\]", " ", t).strip()
flag = {}
checked = 0
for f in sorted(glob.glob("*.xml")):
    if f == "unified_mena_epg.xml": continue
    try: root = ET.parse(f).getroot()
    except Exception: continue
    for p in root.iter("programme"):
        t = p.findtext("title") or ""
        if "بعد" in t or "⏰" in t or "القادمة" in t: continue
        parts = SEP.split(clean(t))
        if len(parts) < 2: continue
        a, b = toks(parts[0].split(":")[-1][-40:]), toks(parts[1][:40])
        if not a or not b: continue
        st = datetime.strptime(p.get("start"), "%Y%m%d%H%M%S %z")
        sp = datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z")
        if (sp - st) < timedelta(minutes=80): continue
        for ha, aw, rst, name in ref:
            if (a & ha and b & aw) or (a & aw and b & ha):
                checked += 1
                diff = (st - rst).total_seconds() / 60
                if 30 <= abs(diff) <= 8 * 60:
                    k = (f, p.get("channel"), name)
                    flag.setdefault(k, (int(diff), f"{st:%m-%d %H:%M}Z vs ref {rst:%m-%d %H:%M}Z", t[:60]))
                break
lines = [f"{k[0]} {k[1]} | {k[2]} | off {v[0]:+d}m | {v[1]} | {v[2]}" for k, v in sorted(flag.items())]
print(f"::notice::ref {len(ref)} matches; checked {checked} rows; flagged {len(flag)}%0A" + "%0A".join(lines)[:8000])
