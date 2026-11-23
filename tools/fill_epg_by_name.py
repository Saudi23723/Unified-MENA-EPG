#!/usr/bin/env python3
"""A channel without a guide takes the guide its twins already have.

Many channels come in several qualities ("Eurosport 1 HD", "Eurosport 1 FHD", "Eurosport 1 HEVC") and in several
playlists, and only some of them were given a guide. This reads every xtream/<playlist>/channel_map.json, and
for each name (quality words taken off) that has exactly ONE guide among all its twins, gives that guide to the
twins that have none. Names with two different guides anywhere are left alone (never a guess), and so are
event slots. Run: python tools/fill_epg_by_name.py [--write]
"""
import collections, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUAL = re.compile(r"\b(4K|UHD|FHD|HD|SD|HEVC|RAW|LQ|HQ|H\.?265|H\.?264|\d{2}\s*FPS|3840P|1080P?|720P?|BACKUP|VIP|ᴴᴰ|ᴿᴬᵂ)\b|[⁰¹²³⁴-⁹ᴬ-ᵛ]+", re.I)
EVENT = re.compile(r"[()]|\bvs\.?\b| @ |\d{1,2}[:.]\d{2}|\b(PPV|EVENT|REPLAY|24/7)\b|[|:]", re.I)


def norm(n: str) -> str:
    n = n.upper().replace("&", " AND ").replace("+", " PLUS ")
    n = QUAL.sub(" ", n)
    n = re.sub(r"\bSPORTS\b", "SPORT", n).replace("EUROSPORTS", "EUROSPORT")
    return re.sub(r"[^A-Z0-9؀-ۿ]+", " ", n).strip()


def main():
    write = "--write" in sys.argv
    maps = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "xtream", "*", "channel_map.json"))):
        maps[f] = json.load(open(f, encoding="utf-8"))
    keys = collections.defaultdict(collections.Counter)
    for m in maps.values():
        for c in m:
            if c.get("epg") and not EVENT.search(c["name"]):
                keys[norm(c["name"])][c["epg"]] += 1
    total = 0
    for f, m in maps.items():
        n = 0; ex = []
        for c in m:
            if c.get("epg") or EVENT.search(c["name"]):
                continue
            k = norm(c["name"])
            if len(k) < 4 or len(keys.get(k, ())) != 1:
                continue
            pick = next(iter(keys[k]))
            # never a twin from another country (owner, 11 Nov 2026)
            from epg_country_check import country_of, fits, flag, SAME
            g, ec = flag(c.get("group", "")), country_of(pick)
            if g and ec and not fits(g, ec) and not SAME.search(c["name"]):
                continue
            c["epg"] = pick; n += 1
            if len(ex) < 6: ex.append((c["name"], c["epg"]))
        total += n
        print(os.path.basename(os.path.dirname(f)), n, ex)
        if write and n:
            json.dump(m, open(f, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("filled", total, "(written)" if write else "(dry run)")


if __name__ == "__main__":
    main()
