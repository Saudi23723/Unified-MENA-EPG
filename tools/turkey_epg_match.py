#!/usr/bin/env python3
"""Turkish channels get the owner's Turkish guide (owner, 11 Nov 2026: "Turkish channels: look at my repo, we made EPG").

For every playlist channel that is Turkish (a TR / 🇹🇷 / ULUSAL group, or a TRT name) and has no guide yet,
the channel is looked up, by its cleaned-up name, in
  1. this repository's own Turkish guides (beIN Sports Turkey, tabii Spor 1-10, Turkish PPV) -> "r:<file>/<id>"
  2. the owner's TiviMate link for Turkey, iptv-epg.org epg-tr.xml (OWNER_LINKS["turkey"]) -> "l:turkey/<id>"
Only an exact match of the cleaned name is taken (no guessing), so a channel never gets another channel's guide.
Episode lists ("S01 E03"), mosaics and info screens are left alone.

    python tools/turkey_epg_match.py            # writes the maps, prints a report, saves turkey_epg_report.txt
"""
import gzip, html, json, re, sys, unicodedata, urllib.request, glob, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OWN = ["bein_sports_turkey_epg.xml", "tabii_spor_1_10_epg.xml", "turkish_ppv_epg.xml", "dubai_turkish_ppv_epg.xml"]
LINK = "https://iptv-epg.org/files/epg-tr.xml"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}

FOLD = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})
NOISE = re.compile(r"\b(uhd|fhd|hd|sd|4k|8k|hevc|h265|raw|50fps|60fps|1080p?|720p?|backup|yedek|vip|tr|turk(iye|ey)?|int)\b")


def key(name: str) -> str:
    n = name.translate(FOLD).lower()
    n = unicodedata.normalize("NFKD", n)
    n = "".join(ch for ch in n if not unicodedata.combining(ch))
    n = re.sub(r"^\s*[a-z]{2,4}\s*[:|]\s*", "", n)          # "TR: ", "TR | "
    n = re.sub(r"[\(\[].*?[\)\]]", " ", n)
    n = NOISE.sub(" ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def turkish(c) -> bool:
    g = c.get("group", ""); n = c.get("name", "")
    if re.search(r"S\d{1,2}\s*E\d{1,3}|mozaik|fikstur|info\b|series|مسلسل", g + " " + n, re.I):
        return False
    return bool(re.search(r"(^|\W)(TR|ULUSAL|TÜRK|TURK|🇹🇷)(\W|$)", g, re.I) or re.match(r"(?i)\s*(TR\s*[:|]|TRT\b)", n))


def alts(k: str):
    """the same name with and without "tv" (\"24 HD\" = \"24 TV\", \"TV 8\" = \"TV8\")"""
    out = [k]
    b = re.sub(r"^tv|tv$", "", k)
    if b and b != k: out.append(b)
    if not k.endswith("tv"): out.append(k + "tv")
    return out


def channels(raw: bytes) -> dict:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    t = raw.decode("utf-8", "replace")
    out = {}
    for m in re.finditer(r'<channel\b[^>]*\bid="([^"]*)"[^>]*>(.*?)</channel>', t, re.S):
        cid = html.unescape(m.group(1))
        for dn in re.findall(r"<display-name\b[^>]*>(.*?)</display-name>", m.group(2), re.S):
            for k in alts(key(html.unescape(dn))):
                if len(k) >= 2:
                    out.setdefault(k, cid)
        k = key(re.sub(r"\.[a-z]{2}$", "", cid))
        if k:
            out.setdefault(k, cid)
    return out


def main():
    index = []   # (prefix, {key: id})
    for f in OWN:
        if os.path.isfile(f):
            index.append(("r:" + f[:-4] + "/", channels(open(f, "rb").read())))
    try:
        raw = urllib.request.urlopen(urllib.request.Request(LINK, headers=UA), timeout=300).read()
        index.append(("l:turkey/", channels(raw)))
        print(f"epg-tr.xml: {len(index[-1][1])} names")
    except Exception as exc:  # noqa: BLE001
        print(f"epg-tr.xml not read: {exc}")
    report = []
    total = 0
    for f in sorted(glob.glob("xtream/*/channel_map.json")):
        pl = f.split("/")[1]
        m = json.load(open(f, encoding="utf-8"))
        got = miss = 0
        for c in m:
            if c.get("epg") or not turkish(c):
                continue
            k = key(c["name"])
            hit = None
            for prefix, ix in index:
                for a in (alts(k) if k else []):
                    if a in ix:
                        hit = prefix + ix[a]; break
                if hit:
                    break
            if hit:
                c["epg"] = hit; got += 1; report.append(f"{pl}\t{c['group']}\t{c['name']}\t{hit}")
            else:
                miss += 1; report.append(f"{pl}\t{c['group']}\t{c['name']}\t-")
        if got:
            json.dump(m, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        total += got
        print(f"{pl}: {got} Turkish channels got a guide, {miss} still without")
    open("turkey_epg_report.txt", "w", encoding="utf-8").write("\n".join(report) + "\n")
    print(f"total {total}")


if __name__ == "__main__":
    main()
