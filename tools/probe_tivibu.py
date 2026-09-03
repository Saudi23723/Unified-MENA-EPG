#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Is the Tivibu feed dead, or has it merely renamed its channels?

health_check has been red since 31 August: bein_sports_turkey_epg.xml is
47% stand-in against a 45% ceiling. The file is not the problem. Measured
channel by channel, the four Tivibu Spor channels are 100% stand-in —
332 rows of "nothing scheduled" — while every beIN channel in the same
file runs between 0% and 13%. Four dead channels are dragging eight live
ones over the line, which also means the ceiling is now masking the
health of the channels anybody actually watches.

Before proposing that four published channels be removed — which is
visible to every viewer whose player is mapped to them — the cause has
to be known, because the two possible causes need opposite fixes:

  the feed has STOPPED carrying them   → the channels have no source
  the feed has RENAMED them            → our matcher is looking for an
                                         id that no longer exists, and
                                         the fix is one line

The module matches by id and by name, so a rename anywhere would look
exactly like a death from the outside. This prints every channel in TR3
whose id or name mentions spor, tivibu or telekom, with how many
programmes each carries — so the difference is visible rather than
assumed.
"""
from __future__ import annotations

import gzip
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter

from epg_lib import fetch, new_session

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_TR3.xml.gz"
INTERESTING = re.compile(r"spor|tivibu|telekom|t[iı]vibu", re.I)


def main() -> int:
    try:
        answer = fetch(new_session(), SOURCE)
    except Exception as exc:                                  # noqa: BLE001
        print(f"the feed is unreachable: {type(exc).__name__}: {exc}")
        return 0

    raw = (gzip.decompress(answer.content)
           if answer.content[:2] == b"\\x1f\\x8b" else answer.content)
    root = ET.fromstring(raw)
    channels = {c.get("id"): (c.findtext("display-name") or "")
                for c in root.findall("channel")}
    counts = Counter(p.get("channel") for p in root.findall("programme"))
    print(f"feed: {len(channels)} channel(s), "
          f"{sum(counts.values())} programme(s)\\n")

    hits = {cid: name for cid, name in channels.items()
            if INTERESTING.search(f"{cid} {name}")}
    print(f"channels mentioning spor / tivibu / telekom: {len(hits)}")
    for cid, name in sorted(hits.items()):
        print(f"    {counts.get(cid, 0):5d}  {cid!r}  ({name})")

    # And what this repository is looking for, so a rename is obvious.
    import tivibu_spor_epg as tv
    wanted = [v for k, v in vars(tv).items()
              if isinstance(v, (list, tuple, dict, set))
              and any("ivibu" in str(item) for item in v)]
    print(f"\\nwhat the module looks for: {str(wanted)[:900]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
