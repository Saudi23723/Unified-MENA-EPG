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


def raw_stamps(session) -> None:
    """The timestamp strings the two XMLTV feeds actually publish.

    A three-hour disagreement can come from either side, and the fix
    differs: a feed that omits the offset is being defaulted correctly, a
    feed that stamps local time and labels it +0000 is not. Only the raw
    string says which, so it is printed before anything is concluded.
    """
    import re
    import gzip
    from epg_lib import fetch

    for label, url in (("epgshare01", g.EPGSHARE_URL),
                       ("open-epg", g.OPENEPG_URL)):
        print(f"--- {label}: raw <programme> stamps ---")
        try:
            raw = fetch(session, url).content
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", "replace")
        except Exception as exc:
            print(f"    unavailable: {exc}\n")
            continue

        shown = 0
        for m in re.finditer(r'<programme([^>]*)>', text):
            attrs = m.group(1)
            if "beIN SPORTS 1" not in attrs and "Beinsports.tr" not in attrs:
                continue
            print(f"    {attrs.strip()[:120]}")
            shown += 1
            if shown >= 4:
                break
        if not shown:
            print("    no beIN SPORTS 1 programme found under either id")
        print()


def main() -> int:
    now = utc_now()
    session = new_session()
    print(f"beIN Türkiye time audit | now={now.astimezone(TR):%Y-%m-%d %H:%M} TR\n")
    raw_stamps(session)

    share = g.fetch_xmltv_feed(session, g.EPGSHARE_URL, "epgshare01", now)
    # assume_local mirrors what build() does, so this measures the fix
    # rather than the state it was written to correct.
    openepg = g.fetch_xmltv_feed(session, g.OPENEPG_URL, "open-epg", now,
                                 assume_local=True)

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
        #
        # Only titles that occur exactly once on BOTH sides are compared.
        # A channel that fills its day with its own name repeated, as MAX 1
        # and 2 do, otherwise pairs every copy with every other and returns
        # the whole spread of the day, which says nothing about the clock.
        labels = [k for k, v in by_source.items() if v]
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                left = Counter(ev["title"].strip().lower() for ev in by_source[a])
                right = Counter(ev["title"].strip().lower() for ev in by_source[b])
                unique = {t for t in left if left[t] == 1 and right.get(t) == 1}
                if not unique:
                    print(f"    {a} vs {b}: no title occurs once on both sides")
                    continue
                at = {ev["title"].strip().lower(): ev["start"]
                      for ev in by_source[a]}
                bt = {ev["title"].strip().lower(): ev["start"]
                      for ev in by_source[b]}
                deltas = [round((bt[t] - at[t]).total_seconds() / 60)
                          for t in unique]
                counts = Counter(deltas)
                shown = ", ".join(f"{d:+d}min x{n}"
                                  for d, n in counts.most_common(4))
                verdict = ("SAME CLOCK" if set(counts) == {0} else
                           "CONSTANT OFFSET — BUG" if len(counts) == 1 else
                           "no single offset")
                print(f"    {a} vs {b}: {len(deltas)} unique shared title(s) "
                      f"-> {verdict}  [{shown}]")

        # --- the merged timeline, with where each event came from -------
        merged = g.merge_events(g.merge_events(primary, from_share), from_open)
        origin = {}
        for label in ("open-epg", "epgshare", "tvyayinakisi"):
            for ev in by_source[label]:
                origin[(ev["start"], ev["title"])] = label

        # --- what the sources themselves published, before merging -----
        #
        # A thirty-minute Premier League match is the sign of a stop that
        # was cut back, so the raw events are shown wherever two of them
        # from the SAME source overlap: that is the source contradicting
        # itself, and no merge rule can repair it.
        for label, evs in by_source.items():
            ordered = sorted(evs, key=lambda e: e["start"])
            clashes = [(x, y) for x, y in zip(ordered, ordered[1:])
                       if y["start"] < x["stop"]]
            if clashes:
                print(f"    {label}: {len(clashes)} self-overlap(s), "
                      f"first three:")
                for x, y in clashes[:3]:
                    print(f"        {x['start'].astimezone(TR):%m-%d %H:%M}"
                          f"-{x['stop'].astimezone(TR):%H:%M} {x['title'][:34]}")
                    print(f"        {y['start'].astimezone(TR):%m-%d %H:%M}"
                          f"-{y['stop'].astimezone(TR):%H:%M} {y['title'][:34]}"
                          f"   <-- starts before the one above ends")

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
