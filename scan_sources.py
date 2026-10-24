import urllib.request, os, re
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
b = urllib.request.urlopen(urllib.request.Request("https://watch.sportsnet.ca/schedule", headers=UA), timeout=60).read().decode("utf-8", "replace")
os.makedirs("scan", exist_ok=True)
out = []
out.append("scripts: " + " | ".join(sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', b)))[:30]))
out.append("urls: " + " | ".join(sorted(set(re.findall(r'https?://[A-Za-z0-9.-]+/[A-Za-z0-9./_-]*(?:schedul|epg|listing|guide|airing|linear)[A-Za-z0-9./_?=&%-]*', b, re.I)))[:40]))
for w in ["Sportsnet ONE", "SN1", "startTime", "start_time", "airing", "__NEXT_DATA__", "window.__", "epg", "channelId"]:
    i = b.find(w); out.append(f"== {w} @{i}: " + (b[max(0, i-300):i+600].replace("\n", " ") if i >= 0 else ""))
open("scan/probe_sn2.txt", "w").write("\n".join(out))
