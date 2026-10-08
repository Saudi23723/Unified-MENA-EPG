import re, sys
sys.path.insert(0, ".")
import att_epg
rows = att_epg.playlist("XTREAM") or []
out = []
for cat, name, epg in rows:
    if re.search(r"STC TV (CINEMA|DRAMA|FAMILY|MUNDIAL|SHABAB)", name):
        out.append(f"{name} | icon={att_epg.PROVIDER_ICONS.get(name)}")
text = "%0A".join(out)
for s in att_epg.SECRETS:
    if s: text = text.replace(s, "***")
print("::notice::" + text)
