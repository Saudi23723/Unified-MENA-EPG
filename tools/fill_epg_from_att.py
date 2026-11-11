#!/usr/bin/env python3
"""Channels without a guide take it from the repo's big guide (att-epg branch, att_epg.xml.gz: 30,000 channels).

Owner, 10 Nov 2026: "look at my repo, every guide should be there". The big guide lists, for each of its
channels, the names providers use for it. A channel of ours with no guide is given the guide whose list has
its name (quality words off) — only when the country fits: the flag (or "TR |") of our group must be the country of the
guide's id; a group without a country is left alone. A name that
fits two guides of the same country is left alone. Event slots are never touched.
Run: python tools/fill_epg_from_att.py <att_epg.xml.gz> [--write]
"""
import collections, glob, gzip, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fill_epg_by_name import EVENT, norm  # the same idea of "the same name"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = re.compile(r"^\s*(?:[A-Za-z-]{2,8}\|\s*)?(?:[A-Za-z]{2,5}\s*[:|]\s*)+")


def country(cid: str) -> str:
    m = re.search(r"([a-z]{2})\d?$", cid)
    return m.group(1) if m else ""


def flag(group: str) -> str:
    cps = [ord(ch) - 0x1F1E6 for ch in group if 0x1F1E6 <= ord(ch) <= 0x1F1FF]
    if len(cps) >= 2:
        cc = chr(97 + cps[0]) + chr(97 + cps[1])
        return {"gb": "uk", "um": "us", "hm": "au"}.get(cc, cc)
    if "\U0001F3F4" in group: return "uk"
    m = re.match(r"\s*([A-Z]{2})\s*\|", group)   # "TR | SPOR"
    return {"UK": "uk", "US": "us", "TR": "tr", "DE": "de", "FR": "fr", "IT": "it"}.get(m.group(1), "") if m else ""


def main():
    src = sys.argv[1]; write = "--write" in sys.argv
    names = collections.defaultdict(set); has = set(); cur = None
    with gzip.open(src, "rt", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "<programme" in line:
                m = re.search(r'channel="([^"]+)"', line)
                if m: has.add(m.group(1))
                continue
            m = re.search(r'<channel id="([^"]+)"', line)
            if m: cur = m.group(1)
            for d in re.findall(r"<display-name[^>]*>([^<]*)", line):
                if cur:
                    k = norm(PREFIX.sub("", d))
                    if len(k) >= 3: names[k].add(cur)
    total = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "xtream", "*", "channel_map.json"))):
        m = json.load(open(f, encoding="utf-8")); n = 0; ex = []
        for c in m:
            if c.get("epg") or EVENT.search(c["name"]): continue
            k = norm(PREFIX.sub("", c["name"]))
            cands = [i for i in names.get(k, ()) if i in has]
            if not cands: continue
            cc = flag(c.get("group", ""))
            # the country must be known and must fit (a name alone is not enough: "TRT" is also a Greek id)
            if not cc or "ESPN+" in c["name"].upper(): continue
            cands = [i for i in cands if country(i) == cc]
            # the provider's own id and the plain id of one channel are the same guide: one of them is enough
            plain = sorted(i for i in cands if not i.startswith("Playlist."))
            pick = sorted(cands)
            if len(pick) > 1:
                if len(plain) == 1: pick = plain
                elif len([i for i in cands if i.startswith("Playlist.")]) == 1: pick = [i for i in cands if i.startswith("Playlist.")]
            if len(pick) != 1: continue
            c["epg"] = "a:" + pick[0]; n += 1
            if len(ex) < 5: ex.append((c["name"], c["epg"]))
        total += n
        print(os.path.basename(os.path.dirname(f)), n, ex)
        if write and n:
            json.dump(m, open(f, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("filled", total, "(written)" if write else "(dry run)")


if __name__ == "__main__":
    main()
