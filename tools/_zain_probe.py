import sys, os, re, gzip; sys.path.insert(0, os.getcwd())
import requests, xml.etree.ElementTree as ET
ch = requests.get("https://iptv-org.github.io/api/channels.json", timeout=120).json()
logos = {l["channel"] for l in requests.get("https://iptv-org.github.io/api/logos.json", timeout=120).json() if l.get("channel")}
pat = re.compile(r"syria|souri|qanat|yaum|ana s|alalam|sham|makan|nablus|najah|maan|ma'an|musawa|fajr|fadjr|quds|hala|arena sport|yes sport|irib|varzesh|movistar|m\+|liga tv|tivibu|bein sports 1|sport klub|tring|rtsh", re.I)
for c in ch:
    names = [c["name"]] + (c.get("alt_names") or [])
    if any(pat.search(n) for n in names) and c.get("country") in ("SY", "PS", "IL", "IR", "ES", "RS", "TR", "AL", "LB", "JO", "IQ"):
        print(c["id"], "|", names[:4], "|", "logo" if c["id"] in logos else "-", "| closed" if c.get("closed") else "")
for cc in ("IR1", "ES1"):
    r = requests.get(f"https://epgshare01.online/epgshare01/epg_ripper_{cc}.xml.gz", timeout=120)
    if r.status_code != 200: print(cc, r.status_code); continue
    root = ET.fromstring(gzip.decompress(r.content))
    print(cc, "|", "; ".join(f"{c.get('id')}={c.findtext('display-name')}" for c in root.findall("channel") if pat.search((c.findtext("display-name") or "") + c.get("id"))))
