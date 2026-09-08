import sys
p = "tools/generate_flight_tracker.py"
s = open(p).read()
old = """        text(d, (cx+230, ry-14), f"{dlab} {hhmm(dep_o)}", F_SMALL, GREEN if dep_act else ACCENT)
        text(d, (cx+360, ry-14), f"{alab} {hhmm(arr_d)}", F_SMALL, GREEN if arr_act else ACCENT)
        text(d, (cx+230, ry+4), f"{hhmm(dep_l)} {tzcity}", F_TINY, GREY)
        text(d, (cx+360, ry+4), f"{hhmm(arr_l)} {tzcity}", F_TINY, GREY)"""
new = """        text(d, (cx+230, cy+14), f"{dlab} {hhmm(dep_o)}", F_SMALL, GREEN if dep_act else ACCENT)
        text(d, (cx+360, cy+14), f"{alab} {hhmm(arr_d)}", F_SMALL, GREEN if arr_act else ACCENT)
        text(d, (cx+230, cy+34), f"{hhmm(dep_l)} {tzcity}", F_TINY, GREY)
        text(d, (cx+360, cy+34), f"{hhmm(arr_l)} {tzcity}", F_TINY, GREY)
        dur = int(round(f["arr"] - f["dep"]))
        if dur < 0: dur += 1440
        text(d, (cx+230, cy+54), f"{dur//60}h {dur%60:02d}m", F_SMALL, MUTED)"""
if new in s:
    print("already patched"); sys.exit(0)
assert old in s, "pattern not found"
open(p, "w").write(s.replace(old, new))
print("patched ok")
