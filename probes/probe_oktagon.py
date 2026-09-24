"""Why the WNBA/MLB screen gets no live pages, from a runner. Never fails."""
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())
try:
    subprocess.run([sys.executable, "tools/segment_branch.py", "hydrate"])
    code = subprocess.run([sys.executable, "-u", "ball_sports_epg.py"]).returncode
    print("ball_sports_epg exit", code)
    import board_marks
    import match_screen_video as msv
    from epg_lib import status_of, on_air_for
    now = datetime.now(timezone.utc)
    recs = board_marks.every_record()
    print("records:", [r["name"] for r in recs])
    for r in recs:
        if not r["name"].startswith(("ball_sports_", "dubai_ball_sports_")):
            continue
        print("==", r["name"], "style", r.get("style"), "rows", len(r["rows"]))
        for row in r["rows"][:8]:
            print("   ", type(row.get("start")).__name__, row.get("start"), row.get("title"),
                  "| status", status_of(row, now, on_air_for))
        drawn = board_marks.picture(r, now)
        path = os.path.join(r.get("board_dir", "boards"), r["name"])
        disk = open(path, "rb").read() if os.path.exists(path) else b""
        print("   picture==disk:", drawn == disk, len(drawn), len(disk))
    prefix, playlist, stamp, seconds = msv.SCREENS["ball_sports"]
    import glob
    reel = sorted(glob.glob(f"boards/{prefix}*.png"))
    print("reel:", reel)
    variants, generated = msv.status_variants(reel, now)
    print("variants:", {k: v for k, v in variants.items()}, "generated:", list(generated))
except Exception:
    traceback.print_exc()
