import re, io
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
        dur = int(round(f['arr'] - f['dep']))
        if dur < 0: dur += 1440
        lbl = f"FLIGHT TIME  {dur//60}h {dur%60:02d}m"
        if f["status"] == "IN FLIGHT":
            rem = int(round(f['arr'] - now_min))
            if rem < 0: rem += 1440
            if 0 < rem <= 900:
                lbl = f"LANDS IN  {rem//60}h {rem%60:02d}m"
            elif rem == 0:
                lbl = "LANDING NOW"
        text(d, (cx+335, cy+80), lbl, F_SMALL, AMBER, anchor="mm")
'''
# rebuild the region between the time rows and the status badge (drop any old blocks)
start = s.index('        text(d, (cx+360, cy+34)')
end = s.index('        # status badge')
first_line = s[start:end].split("\n")[0]
s = s[:start] + first_line + "\n" + NEW + "\n" + s[end:]

io.open(P, "w", encoding="utf-8").write(s)
compile(s, P, "exec")
print("cardfix ok; blocks:", s.count("cy+80"))
