import requests
ch = {c["id"]: c for c in requests.get("https://iptv-org.github.io/api/channels.json", timeout=120).json()}
g = requests.get("https://iptv-org.github.io/api/guides.json", timeout=120).json()
by = {}
for x in g:
    by.setdefault(x.get("channel"), []).append(f'{x.get("site")}:{x.get("site_id")}')
sy = sorted((c for c in ch.values() if c.get("country") == "SY"), key=lambda c: c["name"])
print("syrian channels:", len(sy))
for c in sy:
    print(c["id"], "|", c["name"], "|", (by.get(c["id"]) or "-"), "| logo" if c.get("logo") else "")
