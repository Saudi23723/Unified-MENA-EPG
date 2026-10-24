import json, urllib.request, os
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
b = urllib.request.urlopen(urllib.request.Request("https://awk.epgsky.com/hawk/linear/services/4101/1", headers=UA), timeout=60).read()
sv = json.loads(b)["services"]
os.makedirs("scan", exist_ok=True)
open("scan/sky_services.tsv", "w").write("\n".join(f'{x["sid"]}\t{x["c"]}\t{x["t"]}\t{x.get("sf","")}' for x in sv))
print(len(sv))
