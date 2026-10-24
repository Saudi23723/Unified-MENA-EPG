import gzip, os, re, urllib.request, traceback
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
SRC = {"italy": "https://cdn.epg.guru/7dayiptv/Italy.xml", "swiss": "https://cdn.epg.guru/7dayiptv/Switzerland.xml.gz",
       "germany": "https://cdn.epg.guru/7dayiptv/Germany.xml.gz", "portugal": "https://iptv-epg.org/files/epg-pt.xml",
       "turkey": "https://iptv-epg.org/files/epg-tr.xml", "combined": "https://iptv-epg.org/files/epg-rhtwyyuokk.xml",
       "iptvx": "https://iptvx.one/EPG", "grabber": "http://gabbarit.epg.one/epg_1.xml.gz",
       "romania": "https://iptv-epg.org/files/epg-ro.xml", "slovenia": "https://iptv-epg.org/files/epg-si.xml"}
os.makedirs("scan", exist_ok=True); log = []
for k, u in SRC.items():
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=300).read()
        if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
        t = b.decode("utf-8", "replace")
        ch = []
        for m in re.finditer(r'<channel\s+id="([^"]*)"[^>]*>(.*?)</channel>', t, re.S):
            ch.append((m.group(1), " | ".join(re.findall(r'<display-name[^>]*>([^<]*)<', m.group(2)))))
        pr = {}
        for c in re.findall(r'<programme[^>]*channel="([^"]*)"', t): pr[c] = pr.get(c, 0) + 1
        open(f"scan/src_{k}.tsv", "w").write("\n".join(f"{a}\t{b}\t{pr.get(a,0)}" for a, b in ch))
        log.append(f"{k}\t{len(ch)} channels\t{sum(pr.values())} programmes\t{len(t)//1048576} MB")
    except Exception as e:
        log.append(f"{k}\tERR {e}")
open("scan/src_log.txt", "w").write("\n".join(log)); print("\n".join(log))
