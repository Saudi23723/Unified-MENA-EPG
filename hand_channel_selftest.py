#!/usr/bin/env python3
"""The owner's hand-assign channels, written the way the build writes
them, must pass the health check and reach the merged link exactly once.

    python hand_channel_selftest.py

WHY. On 7 October 2026 the hand-assign channels (Hydra, NEWS 24/7, LIVE
EVENT ONLY) went on the Alkass and Roya links as well as Alwan's, so a
playlist reading any of them lists them. Every check before the merge
passed — they read the committed guides, which did not carry the new
channels yet — and the health check failed only after the next build
wrote them, because it kept its own copy of the rule for which channels
several links may share. Now the rule is one function
(merge_epg.off_merged_link) and this test builds the channels in memory
on every link that carries them and runs the health check's own rule
(health_check.id_clash) over them, before anything is merged.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

import alwan_channels_epg as alwan
import health_check
import merge_epg

failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        failures.append(what)


def ids_of(root) -> list[str]:
    return [c.get("id") for c in root.findall("channel")]


# Each link as the build writes its hand-assign channels.
links: dict[str, list[str]] = {}
links["alwan_sports_epg.xml"] = [xid for xid, *_ in alwan.PLACEHOLDERS]
for path in ("alkass_epg.xml", "roya_jordan_epg.xml"):
    root = ET.Element("tv")
    alwan.add_hand_channels_to(root)
    links[path] = ids_of(root)

every = [xid for xid, *_ in alwan.PLACEHOLDERS]
check(len(every) == len(set(every)), "every hand-assign channel has its own id")
for path in ("alkass_epg.xml", "roya_jordan_epg.xml"):
    check(len(links[path]) == len(every),
          f"{path} carries every hand-assign channel ({len(links[path])}/{len(every)})")

# The health check's own rule, over the links in merge order.
seen: dict[str, str] = {}
for path in merge_epg.SOURCE_FILES:
    for cid in links.get(path, []):
        problem = health_check.id_clash(seen, cid, path)
        check(problem is None, f"{path}: {cid} passes the health check"
              + (f" — {problem}" if problem else ""))
        seen.setdefault(cid, path)

# And the merged link lists each of them once: Alwan's copy goes in, the
# other links' copies are left out.
merged = [cid for path in merge_epg.SOURCE_FILES for cid in links.get(path, [])
          if not merge_epg.off_merged_link(cid)]
check(sorted(merged) == sorted(every),
      "the merged link lists each hand-assign channel exactly once")

if failures:
    print(f"\n{len(failures)} failure(s).")
    sys.exit(1)
print("\nAll good.")
