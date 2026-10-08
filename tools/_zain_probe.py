import re, requests
H = {"User-Agent": "Unified-MENA-EPG logo search (github.com/Saudi23723/Unified-MENA-EPG)"}
out = []
t = requests.get("https://api.github.com/repos/tv-logo/tv-logos/git/trees/main?recursive=1", headers=H, timeout=60).json()
out += ["TVL " + p["path"] for p in t.get("tree", []) if re.search(r"stc|jawwy|intigral", p["path"], re.I)]
for q in ["stc tv logo", "stc tv", "Saudi Telecom Company logo", "stc logo"]:
    j = requests.get("https://commons.wikimedia.org/w/api.php", params={"action": "query", "list": "search", "srsearch": q, "srnamespace": 6, "format": "json", "srlimit": 10}, headers=H, timeout=60).json()
    out += ["WM " + x["title"] for x in j.get("query", {}).get("search", [])]
for title in ["Stc_tv", "Saudi_Telecom_Company", "Intigral"]:
    j = requests.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "titles": title, "prop": "pageimages", "piprop": "original", "format": "json"}, headers=H, timeout=60).json()
    for p in j.get("query", {}).get("pages", {}).values():
        out.append(f"WP {title}: {p.get('original', {}).get('source')}")
print("::notice::" + "%0A".join(sorted(set(out)))[:8000])
