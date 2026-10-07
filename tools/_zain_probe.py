import re, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
out = []
for u in ["https://www.livefootballtv.info/", "https://www.livefootballtv.info/channel/on-sport"]:
    t = requests.get(u, headers=H, timeout=60).text
    lines = [l.strip() for l in BeautifulSoup(t, "html.parser").get_text("\n").split("\n") if l.strip()]
    for i, l in enumerate(lines):
        if re.search(r"Mehalla|Mahalla", l):
            day = next((lines[j] for j in range(i, -1, -1) if re.search(r"\d{2}/\d{2}/\d{4}", lines[j])), "?")
            out.append(f"{u[-20:]} | {day} | " + " / ".join(lines[max(0, i-4):i+3]))
    for m in re.finditer(r"Mehalla.{0,300}", t):
        out.append("RAW " + re.sub(r"\s+", " ", t[max(0, m.start()-600):m.start()+50]))
        break
print("::notice::" + "%0A".join(out)[:7000])
