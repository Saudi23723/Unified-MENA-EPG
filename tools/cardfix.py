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

NEW = ""

# header: keep the blinking LIVE label clear of the clock
s = s.replace('d.ellipse([W-300, 34, W-288, 46]', 'd.ellipse([W-330, 34, W-318, 46]')
s = s.replace('text(d, (W-280, 30), "LIVE"', 'text(d, (W-310, 30), "LIVE"')
s = s.replace('text(d, (W-230, 30), clock', 'text(d, (W-225, 30), clock')

# rebuild the region between the time rows and the status badge (drop any old blocks)
start = s.index('        text(d, (cx+360, cy+34)')
end = s.index('        # status badge')
first_line = s[start:end].split("\n")[0]
s = s[:start] + first_line + "\n" + NEW + "\n" + s[end:]

io.open(P, "w", encoding="utf-8").write(s)
compile(s, P, "exec")
print("cardfix ok; blocks:", s.count("cy+80"))
