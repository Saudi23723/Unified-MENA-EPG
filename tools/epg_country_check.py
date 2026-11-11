#!/usr/bin/env python3
"""Every guide must be the one of the channel's own country (owner, 11 Nov 2026: "make sure no channel takes its
guide from another country"). A channel in a group with a country (its flag, or "TR |") whose guide id is of
another country loses that guide: no guide is better than another country's programmes (Italy's Sky Sport F1 is
not the UK's, the US beIN Sports is not Qatar's). Channels that really are one channel for several countries
(Al Jazeera, CNN International, Swiss RSI / TVM3 in the Italian / French groups...) are kept.
Run: python tools/epg_country_check.py [--write]
"""
import collections, glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fill_epg_from_att import flag

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARAB = {"ae", "sa", "eg", "qa", "kw", "lb", "jo", "ps", "iq", "ma", "dz", "tn", "ly", "sy", "om", "bh", "ye", "sd"}
LINK = {"italy": "it", "swiss": "ch", "germany": "de", "portugal": "pt", "turkey": "tr", "romania": "ro", "slovenia": "si"}
# one channel for many countries, or a neighbour's channel in that language's group
SAME = re.compile(r"JAZEERA|\bCNN\b|\bRSI\b|\bTVM\s*3\b|FIGHT\s*BOX|BOX\s*OFFICE|\bTRT\b|EURONEWS|FRANCE\s*24|\bDW\b|BLOOMBERG|SKY\s*NEWS", re.I)
FRIENDS = [{"uk", "gb", "ie"}, ARAB, {"it", "ch"}, {"fr", "ch"}, {"de", "ch"}, {"de", "at"}, {"us"}]


def country_of(epg: str):
    k, _, i = epg.partition(":")
    if k == "l":
        return LINK.get(i.split("/")[0])
    if k not in ("a", "r", "o", "u"):
        return None
    m = re.search(r"\.([a-z]{2})(?:@.*)?$", i)
    return m.group(1) if m else None


def fits(g: str, e: str) -> bool:
    return g == e or any(g in s and e in s for s in FRIENDS)


def main():
    write = "--write" in sys.argv
    total = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "xtream", "*", "channel_map.json"))):
        m = json.load(open(f, encoding="utf-8")); out = collections.Counter(); n = 0
        for c in m:
            e = c.get("epg") or ""; g = flag(c.get("group", "")); ec = country_of(e)
            if not g or not ec or fits(g, ec) or SAME.search(c["name"]):
                continue
            out[f"{g}<-{ec}"] += 1; n += 1
            c["epg"] = ""
        total += n
        print(os.path.basename(os.path.dirname(f)), n, dict(out))
        if write and n:
            json.dump(m, open(f, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("guides of another country taken off:", total, "(written)" if write else "(dry run)")
    return total


if __name__ == "__main__":
    main()
