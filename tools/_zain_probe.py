import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
t = requests.get("https://www.oddalerts.com/leagues/kuwait/zain-premier-league/fixtures", headers=H, timeout=60).text
pairs = re.findall(r'"name":"([^"]+ vs [^"]+)".{0,400}?"startDate":"([^"]+)"', t)
lines = re.findall(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} \w{3}, \d{1,2}:\d{2}", re.sub("<[^>]+>", "\n", t))
print("::notice::" + "%0A".join(f"{a} | {b}" for a, b in pairs[:14]) + "%0A--%0A" + "%0A".join(lines[:14]))
