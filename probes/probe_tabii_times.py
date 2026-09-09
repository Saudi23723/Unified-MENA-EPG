"""What TRT actually prints, and whether it says anything about live.

TWO QUESTIONS, AND NOTHING IS CHANGED UNTIL THEY ARE ANSWERED.

1. THE CLOCK. The linear channel's guide was reported three hours late:
   Liverpool - Atletico Madrid shown starting at 22:00 UTC while the
   match was already on. A fix that assumed TRT prints naive Istanbul
   times was merged and changed NOTHING — the rebuilt file carried the
   same times — which means the stamps already carry an offset and the
   assumption was wrong. So: print the RAW starttime string, byte for
   byte, and work out from there what it really means.

2. THE LIVE MARKER. A live badge was asked for. The file's own comment
   says "TRT publishes no live marker", so before inventing one from
   the title, print EVERY key a show object carries and see whether
   there is something honest to read.

It prints. It changes nothing.
"""
import json
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")
from epg_lib import fetch, new_session                       # noqa: E402
import update_tabii_epg as T                                 # noqa: E402

ISTANBUL = ZoneInfo("Europe/Istanbul")


def main() -> int:
    session = new_session()
    now = datetime.now(timezone.utc)
    print(f"now: {now:%Y-%m-%d %H:%M} UTC | Istanbul "
          f"{now.astimezone(ISTANBUL):%H:%M}\n")

    page = fetch(session, T.TRT_URL).text
    blob = T.NEXT_DATA_RE.search(page)
    if not blob:
        print("no __NEXT_DATA__"); return 1
    payload = json.loads(blob.group(1))
    days = T.find_epg_days(payload)
    print(f"days in payload: {len(days)}\n")

    shown = 0
    for day in days:
        for channel in day.get("tvChannels") or []:
            title = str(channel.get("title") or "")
            if channel.get("id") != T.TABII_CHANNEL_ID \
               and not T.TABII_TITLE_RE.search(title):
                continue
            print(f"--- channel {channel.get('id')!r} {title!r} "
                  f"| day {day.get('date')!r} ---")
            print(f"    channel keys: {sorted(channel.keys())}")
            current = channel.get("current")
            shows = list(channel.get("past") or [])
            shows += [current] if isinstance(current, dict) and current else []
            shows += list(channel.get("upcoming") or [])
            for show in shows:
                if shown == 0:
                    print(f"    SHOW KEYS: {sorted(show.keys())}")
                    print(f"    FULL FIRST SHOW: "
                          f"{json.dumps(show, ensure_ascii=False)[:900]}")
                raw = show.get("starttime")
                name = (show.get("title") or "")[:46]
                # THE RAW STRING, then every reading of it, so the right
                # one is chosen by looking rather than by assuming.
                try:
                    stamp = datetime.fromisoformat(
                        str(raw).replace("Z", "+00:00"))
                except Exception:
                    print(f"    raw={raw!r}  UNPARSABLE  {name}")
                    shown += 1
                    continue
                aware = stamp.tzinfo is not None
                as_utc = (stamp.astimezone(timezone.utc) if aware
                          else stamp.replace(tzinfo=timezone.utc))
                as_ist = (stamp.astimezone(timezone.utc) if aware
                          else stamp.replace(tzinfo=ISTANBUL).astimezone(
                              timezone.utc))
                print(f"    raw={str(raw):26} tz={'yes' if aware else 'NO '} "
                      f"| read-as-UTC {as_utc:%H:%M} "
                      f"| read-as-Istanbul {as_ist:%H:%M} | {name}")
                shown += 1
                if shown >= 26:
                    break
            if shown >= 26:
                break
        if shown >= 26:
            break

    print("\n=== anything in a show that looks like a live flag ===")
    keys = set()
    for day in days:
        for channel in day.get("tvChannels") or []:
            for show in (list(channel.get("past") or [])
                         + list(channel.get("upcoming") or [])):
                keys.update(show.keys())
    print("  every key seen on any show:", sorted(keys))
    for k in sorted(keys):
        if re.search(r"live|canli|canlı|now|current|on_?air", k, re.I):
            print(f"  CANDIDATE: {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
