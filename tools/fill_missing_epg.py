#!/usr/bin/env python3
"""Every channel of every playlist checked for a guide (owner, 11 Nov 2026: "check everything, on every playlist").

For each xtream/<playlist>/channel_map.json channel that has no guide (event slots and 24/7 loops left alone),
by its cleaned-up name and ONLY within the same country (or the Arabic world for an Arabic channel):
  1. its twins: the same channel in another quality or another playlist that already has ONE guide
  2. this repository's own guides (unified_mena_epg.xml, the official ones, every *_epg.xml here)
  3. the owner's own TiviMate links (OWNER_LINKS in xtream_epg.py), each for its own country
  4. US local stations: by their call sign (KABB, WFLD...) in a US guide
An exact match of the cleaned name only; a name with two different guides is left alone (never a guess).
Writes the maps (--write) and fill_missing_report.txt with what is still without a guide, group by group.

    python tools/fill_missing_epg.py [--write]
"""
from __future__ import annotations

import collections, glob, gzip, html, json, os, re, sys, unicodedata, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import official_fill, xtream_order  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
ARAB = {"SA", "AE", "QA", "KW", "BH", "OM", "JO", "LB", "EG", "SY", "IQ", "PS", "YE", "MA", "DZ", "TN", "LY", "SD", "AR"}
SMALL = str.maketrans("ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡʏᴢѕх", "ABCDEFGHIJKLMNOPQRSTUVWYZSX")
QUAL = re.compile(r"\b(4K|8K|UHD|FHD|QHD|HD|SD|LQ|HQ|HEVC|H\.?26[45]|RAW|HDR|\d{2}\s*FPS|3840P|2160P|1080P?|720P?|BACKUP|"
                  r"VIP|MULTI|AAC|DOLBY|ATMOS|ULTRA|DIRECT|LIVE|ONLY|DEVICES|ON|NEW|OFFLINE|HD\+|PLUS HD)\b", re.I)
SRC247 = re.compile(r"24\s*/\s*7")
# names too plain to say which channel they are ("Sports 1", "One", "Action"): never matched by name
GENERIC = re.compile(r"^(SPORT|NEWS|MOVIES?|CINEMA|KIDS|ONE|TWO|ACTION|DRAMA|COMEDY|MUSIC|FILM|SERIES|DOCUMENTARY|LIVE|EVENT|"
                     r"FIRE|MAX|PLUS|PREMIUM|EXTRA|HITS|CLASSIC|FAMILY)\d{0,2}$")


def country_of_group(g: str, name: str) -> str | None:
    ri = [c for c in g if 0x1F1E6 <= ord(c) <= 0x1F1FF]
    if len(ri) >= 2:
        cc = chr(ord(ri[0]) - 0x1F1E6 + 65) + chr(ord(ri[1]) - 0x1F1E6 + 65)
        return {"UM": "US", "HM": "AU", "GB": "GB"}.get(cc, cc)
    if "\U0001F3F4" in g:
        return "GB"
    m = re.match(r"^\s*\|?([A-Z]{2,3})\s*[|:]", g) or re.match(r"^\s*\|?([A-Z]{2,3})\s*[|:]", name)
    if m:
        c = m.group(1)
        return {"UK": "GB", "USA": "US", "KSA": "SA", "LBN": "LB", "LEB": "LB", "JOR": "JO", "EGY": "EG", "ARA": "AR"}.get(c, c if len(c) == 2 else None)
    if re.search(r"[؀-ۿ]", g) or re.search(r"OSN|SHAHID|SHOOF|MBC|ROTANA|ARAB|ISLAM|QURAN|ALWAN|STC|THMANYAH|JORDAN|SAUDI|EGYPT|LEBAN", g, re.I):
        return "AR"
    return None


def country_of_id(cid: str, default: str | None) -> str | None:
    m = re.search(r"\.([a-z]{2})$", cid)
    if m:
        c = m.group(1).upper()
        return {"UK": "GB"}.get(c, c)
    return default


def ref_country(ref: str) -> str | None:
    """the country a guide id is for: "...Sports1.qa", "Playlist.US2BravoHDus2", "Playlist.fertequekxasus" """
    cid = ref.split("/", 1)[-1].split(":", 1)[-1]
    m = re.search(r"\.([a-z]{2})$", cid) or (re.search(r"([a-z]{2})\d?$", cid) if cid.startswith("Playlist.") else None)
    if not m:
        return None
    c = m.group(1).upper()
    return {"UK": "GB"}.get(c, c)


def same_country(ref: str, cc: str | None) -> bool:
    rc = ref_country(ref)
    return rc is None or cc is None or fam(rc) == fam(cc)


def fam(c: str | None) -> str | None:
    return "AR" if c in ARAB else c


def key(name: str) -> str:
    n = unicodedata.normalize("NFKC", str(name).translate(SMALL))
    n = re.sub(r"^\s*(\|?[A-Z]{2,4}\|?\s*[:|]\s*)+", "", n.upper())
    n = re.sub(r"[\(\[].*?[\)\]]", " ", n)
    n = n.replace("&", " AND ").replace("+", " PLUS ")
    n = QUAL.sub(" ", n)
    n = re.sub(r"\bSPORTS\b", "SPORT", n)
    n = re.sub(r"\b(TV|CHANNEL|CHANEL|القناة|قناة)\b", " ", n)
    n = re.sub(r"\bAL[\s-]+", "AL", n)
    return re.sub(r"[^A-Z0-9؀-ۿ]+", "", n)


def callsign(name: str) -> str | None:
    m = re.search(r"\b([KW][A-Z]{2,3})\b", str(name).upper())
    return m.group(1) if m and m.group(1) not in ("KIDS", "WEST", "WWE", "KING", "WORK", "WILD", "WOW", "KTV") else None


def xml_channels(raw: bytes):
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    t = raw.decode("utf-8", "replace")
    for m in re.finditer(r'<channel\b[^>]*\bid="([^"]*)"[^>]*>(.*?)</channel>', t, re.S):
        cid = html.unescape(m.group(1))
        names = [html.unescape(x) for x in re.findall(r"<display-name\b[^>]*>(.*?)</display-name>", m.group(2), re.S)]
        yield cid, names


def main():
    write = "--write" in sys.argv
    maps = {f: json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob("xtream/*/channel_map.json"))}

    def has(c):
        return official_fill.override(c["name"]) or c.get("epg") or official_fill.fill(c["name"], c.get("group", ""))

    def skip(c):
        g = c.get("group", "")
        return bool(xtream_order.EVENT_GROUP.search(g) or SRC247.search(g + " " + c["name"]))

    # 1) twins: (country family, key) -> guides
    twins = collections.defaultdict(collections.Counter)
    for m in maps.values():
        for c in m:
            e = has(c)
            if e and not skip(c):
                twins[(fam(country_of_group(c.get("group", ""), c["name"])), key(c["name"]))][e] += 1

    # 2) + 3) sources: (country family, key) -> set of epg refs ; callsigns for US
    index = collections.defaultdict(set)
    calls = collections.defaultdict(set)

    def add(ref, cid, names, default_cc):
        cc = fam(country_of_id(cid, default_cc))
        for n in names + [re.sub(r"\.[a-z]{2}$", "", cid)]:
            k = key(n)
            if len(k) >= 2:
                index[(cc, k)].add(ref)
            if cc == "US":
                cs = callsign(n)
                if cs:
                    calls[cs].add(ref)

    for f in sorted(set(glob.glob("*_epg.xml")) | {"unified_mena_epg.xml"}):
        if not os.path.isfile(f) or f in ("argon_epg.xml", "hydra_epg.xml"):
            continue
        kind = "u:" if f == "unified_mena_epg.xml" else ("o:" if f.startswith("official_") else "r:" + f[:-4] + "/")
        for cid, names in xml_channels(open(f, "rb").read()):
            add(kind + cid, cid, names, None)
    links = dict(re.findall(r'^\s*"(\w+)":\s*"(https?://[^"]+)"', open("xtream_epg.py", encoding="utf-8").read().split("OWNER_LINKS = {", 1)[1].split("}", 1)[0], re.M))
    link_cc = {"italy": "IT", "swiss": "CH", "germany": "DE", "portugal": "PT", "turkey": "TR", "romania": "RO", "slovenia": "SI"}
    for src, url in links.items():
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()
            n0 = len(index)
            for cid, names in xml_channels(raw):
                add(f"l:{src}/{cid}", cid, names, link_cc.get(src))
            print(f"owner link {src}: read ({len(index) - n0} new names)")
        except Exception as exc:  # noqa: BLE001
            print(f"owner link {src}: not read ({exc})")

    by_key = collections.defaultdict(set)
    for (_, k2), v in index.items():
        by_key[k2] |= v

    def pick(refs):
        refs = set(refs)
        return next(iter(refs)) if len(refs) == 1 else None

    report, total = [], 0
    for f, m in maps.items():
        pl = f.split("/")[1]
        got = left = 0
        missing = collections.defaultdict(list)
        for c in m:
            if has(c) or skip(c):
                continue
            g = c.get("group", ""); cc = fam(country_of_group(g, c["name"])); k = key(c["name"])
            hit = None
            if len(k) >= 5 and not GENERIC.match(k):
                tw = twins.get((cc, k))
                if tw and len(tw) == 1:
                    hit = next(iter(tw))
                if not hit:
                    hit = pick(index.get((cc, k), ()))
                if not hit and cc is None:                       # a group with no country: one guide in the whole world only
                    hit = pick(by_key.get(k, ()))
            if not hit and cc == "US":
                cs = callsign(c["name"])
                if cs:
                    hit = pick(calls.get(cs, ()))
            if hit and not same_country(hit, cc):
                hit = None
            if hit:
                c["epg"] = hit; got += 1
            else:
                left += 1; missing[g].append(c["name"])
        total += got
        report.append(f"== {pl}: {got} channels got a guide now, {left} still without (events and 24/7 loops not counted)")
        for g, v in sorted(missing.items(), key=lambda x: -len(x[1])):
            report.append(f"  {len(v):4d}  {g}  ·  " + " · ".join(v[:6]))
        print(report[-1 - len(missing)] if missing else report[-1])
        if write and got:
            compact = open(f, encoding="utf-8").read(2) == "[{"       # each map keeps its own layout
            with open(f, "w", encoding="utf-8") as out:
                json.dump(m, out, ensure_ascii=False, **({"separators": (",", ":")} if compact else {"indent": 1}))
    open("fill_missing_report.txt", "w", encoding="utf-8").write("\n".join(report) + "\n")
    print(f"total {total} new guides")


if __name__ == "__main__":
    main()
