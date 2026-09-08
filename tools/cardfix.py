import sys
p = "tools/generate_flight_tracker.py"
s = open(p).read()

# 1) add fit_text helper before def text(
anchor = "def text(d, xy, s, f, fill=TEXT, anchor=None):"
helper = '''def fit_text(d, s, f, maxw):
    """Truncate s with an ellipsis so it never exceeds maxw pixels."""
    if d.textlength(s, font=f) <= maxw:
        return s
    while s and d.textlength(s + "\\u2026", font=f) > maxw:
        s = s[:-1]
    return s.rstrip() + "\\u2026"


'''
if "def fit_text" not in s:
    assert anchor in s, "text() not found"
    s = s.replace(anchor, helper + anchor, 1)

# 2) truncate airline line so it can't reach the time columns
old_air = '        text(d, (cx+76, cy+38), f"{aname}  \u2022  {f[\'ac\']}", F_SMALL, MUTED)'
new_air = '        text(d, (cx+76, cy+38), fit_text(d, f"{aname}  \u2022  {f[\'ac\']}", F_SMALL, 140), F_SMALL, MUTED)'
if new_air not in s:
    assert old_air in s, "airline line not found"
    s = s.replace(old_air, new_air, 1)

# 3) move duration to bottom-middle, amber, labeled FLIGHT TIME
old_dur = """        dur = int(round(f["arr"] - f["dep"]))
        if dur < 0: dur += 1440
        text(d, (cx+230, cy+54), f"{dur//60}h {dur%60:02d}m", F_SMALL, MUTED)"""
new_dur = """        dur = int(round(f['arr'] - f['dep']))
        if dur < 0: dur += 1440
        text(d, (cx+335, cy+80), f"FLIGHT TIME  {dur//60}h {dur%60:02d}m", F_SMALL, AMBER, anchor="mm")"""
if new_dur not in s:
    assert old_dur in s, "duration block not found"
    s = s.replace(old_dur, new_dur, 1)

open(p, "w").write(s)
import ast
ast.parse(open(p).read())
print("card layout patch applied OK")
