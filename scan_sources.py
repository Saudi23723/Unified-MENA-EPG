import gzip, io, re, urllib.request, os, json
UA = {"User-Agent": "Mozilla/5.0"}
def get(u, t=120):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read()
os.makedirs("scan", exist_ok=True)
log = []
idx = get("https://epgshare01.online/epgshare01/").decode("utf-8", "replace")
files = sorted(set(re.findall(r'href="([^"]+\.xml\.gz)"', idx)))
open("scan/epgshare01_files.txt", "w").write("\n".join(files))
want = re.compile(r"_(CA|CH|EG|SA|JO|LB|AE|QA|OM|SY|KW|IQ|UK|US2|US_SPORTS|FR|ALL_SOURCES|BEIN|DAZN|SPORT)", re.I)
for f in files:
    if not want.search(f):
        continue
    try:
        raw = gzip.decompress(get("https://epgshare01.online/epgshare01/" + f, 300)).decode("utf-8", "replace")
    except Exception as e:
        log.append(f"{f}\tERR {e}"); continue
    chans = []
    for m in re.finditer(r'<channel\s+id="([^"]*)"[^>]*>(.*?)</channel>', raw, re.S):
        names = re.findall(r'<display-name[^>]*>([^<]*)<', m.group(2))
        chans.append((m.group(1), " | ".join(names)))
    progs = len(re.findall(r"<programme ", raw))
    open(f"scan/{f[:-7]}.tsv", "w").write("\n".join(f"{a}\t{b}" for a, b in chans))
    log.append(f"{f}\t{len(chans)} channels\t{progs} programmes\t{len(raw)//1048576} MB")
open("scan/log.txt", "w").write("\n".join(log))
print("\n".join(log))
