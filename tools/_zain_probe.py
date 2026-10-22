import re, requests
ch = requests.get("https://iptv-org.github.io/api/channels.json", timeout=120).json()
logos = {l["channel"] for l in requests.get("https://iptv-org.github.io/api/logos.json", timeout=120).json() if l.get("channel")}
pat = re.compile(r"makan|nablus|najah|ma'?an\b|musawa|fajr|fadjr|quds|syria 2|syria news|sham|ana s|alalam|al-alam|yes sport|^sport ?[1-5]$|irib|varzesh|movistar|vamos|liga tv|tivibu|tvp sport", re.I)
for c in ch:
    names = [c["name"]] + (c.get("alt_names") or [])
    if any(pat.search(n) for n in names):
        print(c["id"], "|", names[:3], "|", "logo" if c["id"] in logos else "-", "| closed" if c.get("closed") else "")
