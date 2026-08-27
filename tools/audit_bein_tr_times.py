#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Are beIN Türkiye's times right?

Three sources feed this guide and each states time its own way, so the
failure to look for is a silent offset: a feed that publishes local time
with no UTC offset, read as if it carried one, lands every programme
hours from where it belongs and still looks like a plausible schedule.

The test is agreement. Where two sources list the same programme title
for the same channel, they must also agree on when it starts. If they
disagree by a constant — three hours, say — that is an offset bug, and
the constant names which feed is being misread.

It also prints the merged timeline with the source of every event
beside it, and flags a football fixture given an implausibly short
slot, since a "match" fifteen minutes long is either a highlights show
or a stop that has been cut back by an overlap.

Reads only; writes nothing.
"""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from epg_lib import new_session, utc_now  # noqa: E402
import bein_sports_turkey_epg as g  # noqa: E402

TR = timezone(timedelta(hours=3))

# A fixture title: two team names either side of a dash. Deliberately
# loose — it only decides what gets a second look, never what is kept.
def looks_like_fixture(title: str) -> bool:
    return (" - " in title
            and not title.lower().startswith(("arşiv", "arsiv"))
            and len(title) < 60)


def main() -> int:
    now = utc_now()
    session = new_session()
    print(f"beIN Türkiye time audit | now={now.astimezone(TR):%Y-%m-%d %H:%M} TR\n")

    share = g.fetch_xmltv_feed(session, g.EPGSHARE_URL, "epgshare01", now)
    openepg = g.fetch_xmltv_feed(session, g.OPENEPG_URL, "open-epg", now)

    for ch in g.CHANNELS:
        name, slug = ch["name"], ch["slug"]
        primary = []
        if slug:
            try:
                primary = g.fetch_tvy_channel(session, slug, now)
            except Exception as exc:
                print(f"  {name}: tvyayinakisi failed: {exc}")
        from_share = [ev for cid in ch["share"] for ev in share.get(cid, [])]
        from_open = openepg.get(ch.get("open", ""), [])

        by_source = {
            "tvyayinakisi": primary,
            "epgshare": from_share,
            "open-epg": from_open,
        }

        print("=" * 70)
        print(f"{name}   tvy={len(primary)} share={len(from_share)} "
              f"open={len(from_open)}")

        # --- agreement on time, per pair of sources ---------------------
        labels = [k for k, v in by_source.items() if v]
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                index = defaultdict(list)
                for ev in by_source[b]:
                    index[ev["title"].strip().lower()].append(ev["start"])
                deltas = []
                for ev in by_source[a]:
                    for other in index.get(ev["title"].strip().lower(), []):
                        deltas.append(
                            round((other - ev["start"]).total_seconds() / 60))
                if not deltas:
                    print(f"    {a} vs {b}: no shared title to compare")
                    continue
                counts = Counter(deltas)
                shown = ", ".join(f"{d:+d}min x{n}"
                                  for d, n in counts.most_common(4))
                verdict = ("AGREE" if set(counts) == {0} else
                           "OFFSET" if len(counts) == 1 else "MIXED")
                print(f"    {a} vs {b}: {len(deltas)} shared title(s) "
                      f"-> {verdict}  [{shown}]")

        # --- the merged timeline, with where each event came from -------
        merged = g.merge_events(g.merge_events(primary, from_share), from_open)
        origin = {}
        for label in ("open-epg", "epgshare", "tvyayinakisi"):
            for ev in by_source[label]:
                origin[(ev["start"], ev["title"])] = label

        print(f"    merged {len(merged)} event(s); first day shown:")
        first_day = None
        for ev in merged:
            day = ev["start"].astimezone(TR).date()
            if first_day is None:
                first_day = day
            if day != first_day:
                break
            start = ev["start"].astimezone(TR)
            minutes = round((ev["stop"] - ev["start"]).total_seconds() / 60)
            src = origin.get((ev["start"], ev["title"]), "?")
            flag = ""
            if looks_like_fixture(ev["title"]) and minutes < 60:
                flag = f"   <-- fixture in only {minutes}min"
            print(f"      {start:%m-%d %H:%M} {minutes:>4}min  "
                  f"[{src:<12}] {ev['title'][:44]}{flag}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
