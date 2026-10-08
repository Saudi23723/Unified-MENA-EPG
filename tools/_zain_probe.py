import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36", "Accept-Language": "ar,en"}
out = []
for u in ["https://elcinema.com/tvguide/", "https://elcinema.com/en/tvguide/", "https://www.stctv.com/", "https://www.stctv.com/en/live", "https://stctv.com/ar/live-tv",
          "https://www.intigral.net/", "https://iptv-epg.org/files/epg-sa.xml", "https://epgshare01.online/epgshare01/epg_ripper_SA1.xml.gz"]:
    try:
        r = requests.get(u, headers=H, timeout=60)
        t = r.content
        if t[:2] == b"\x1f\x8b":
            import gzip; t = gzip.decompress(t)
        t = t.decode("utf-8", "replace")
        hits = sorted(set(re.findall(r"[^<>\"]{0,40}(?:stc ?tv|STC TV|إس تي سي|اس تي سي|جوّي|jawwy)[^<>\"]{0,60}", t, re.I)))[:12]
        links = sorted(set(re.findall(r'href="(/tvguide/\d+/)"[^>]*>\s*([^<]{0,40})', t)))
        stcl = [l for l in links if re.search("stc|اس تي|إس تي", l[1], re.I)]
        out.append(f"{r.status_code} {len(t)} {u} | hits={hits} | tvguide links={len(links)} stc={stcl}")
    except Exception as e:
        out.append(f"ERR {u} {type(e).__name__}")
print("::notice::" + "%0A".join(out)[:9000])
