import sys, os; sys.path.insert(0, os.getcwd())
import att_epg
for pre in ("XTREAM", "XTREAM2", "XTREAM3", "XTREAM4"):
    have = {k: bool(os.environ.get(f"{pre}_{k}", "").strip()) for k in ("URL", "USER", "PASS")}
    print(pre, "secrets set:", have)
    if not any(have.values()):
        continue
    try:
        rows = att_epg.playlist(pre)
    except Exception as e:
        print("  read failed:", type(e).__name__); continue
    if rows is None:
        print("  unreadable"); continue
    names = {n.strip().upper() for _c, n, _e in rows}
    print("  channels:", len(rows))
    for w in ("US: USA NETWORK", "US: ESPN", "SP: RMC SPORT 1", "FRANCE 2", "TF1", "BEIN SPORTS 1", "FOX SPORTS 501", "CANAL+ SPORT 1"):
        print("   ", w, w in names)
