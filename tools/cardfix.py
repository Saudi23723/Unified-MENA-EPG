import re, io, sys
P = "tools/generate_flight_tracker.py"
s = io.open(P, encoding="utf-8").read()

if "def fit_text(" not in s:
    s = s.replace("def text(d, xy, s, f, fill=TEXT, anchor=None):", '''def fit_text(d, s, f, maxw):
    if d.textlength(s, font=f) <= maxw:
        return s
    while s and d.textlength(s + "\\u2026", font=f) > maxw:
        s = s[:-1]
    return s.rstrip() + "\\u2026"


def text(d, xy, s, f, fill=TEXT, anchor=None):''', 1)

s = re.sub(r'text\(d, \(cx\+76, cy\+38\), f"\{aname\}[^\n]*\n',
           lambda m: 'text(d, (cx+76, cy+38), fit_text(d, f"{aname}  \u2022  {f[\'ac\']}", F_SMALL, 140), F_SMALL, MUTED)\n', s)

NEW = '''        # bottom-middle amber line: remaining time to landing while airborne
        if f["status"] == "IN FLIGHT":
            rem = int(round(f['arr'] - now_min))
            if rem < 0: rem += 1440
            if rem > 1080: rem = 0
            lbl = f"LANDS IN  {rem//60}h {rem%60:02d}m" if rem > 0 else "LANDING NOW"
        else:
            dur = int(round(f['arr'] - f['dep']))
            if dur < 0: dur += 1440
            lbl = f"FLIGHT TIME  {dur//60}h {dur%60:02d}m"
        text(d, (cx+335, cy+80), lbl, F_SMALL, AMBER, anchor="mm")
'''
# drop any previous duration/remaining block, then insert the new one
s = re.sub(r'[ ]*# (?:flight duration|bottom-middle amber line)[^\n]*\n(?:[ ]{8}.*\n)*?[ ]{8}text\(d, \(cx\+335, cy\+80\)[^\n]*\n', NEW, s)
if "LANDS IN" not in s:
    s = re.sub(r'([ ]{8}text\(d, \(cx\+360, cy\+34\)[^\n]*\n)', lambda m: m.group(1) + NEW, s, count=1)

io.open(P, "w", encoding="utf-8").write(s)
compile(s, P, "exec")
print("cardfix ok; LANDS IN present:", "LANDS IN" in s)
