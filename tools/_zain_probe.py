import re, sys, glob
sys.path.insert(0, ".")
import att_epg, family_coverage as fc
ids, names = set(), set()
for label, where in fc.OWNER_LINKS + [("alkass", "alkass_epg.xml"), ("unified", "unified_mena_epg.xml")]:
    try:
        i, n, _ = fc.channels_of(where); ids |= i; names |= n
    except Exception as e:
        print("unreadable", label, type(e).__name__)
out = []
for prefix in ("XTREAM", "XTREAM2"):
    rows = att_epg.playlist(prefix) or []
    for cat, name, epg in rows:
        if re.search(r"stc|jawwy", name + " " + cat, re.I):
            out.append(f"{prefix} | {cat[:25]} | {name} | id={epg or '-'} | id_in_links={epg in ids if epg else '-'} | name_in_links={name.lower() in names}")
text = "%0A".join(out)
for s in att_epg.SECRETS:
    if s: text = text.replace(s, "***")
print("::notice::" + text[:9000])
print("::notice::" + text[9000:18000])
