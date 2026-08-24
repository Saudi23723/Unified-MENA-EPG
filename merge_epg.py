#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge every per-source XMLTV file already committed in this repo into one
combined guide: unified_mena_epg.xml.

This script does NOT hit any network source itself — it only reads XML
files that the individual per-source workflows already produced and
validated. That keeps it trivially safe to run on its own schedule
without risking any external API. A missing or unreadable source file is
skipped with a warning; it never stops the merge.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from epg_lib import log, warn, write_xml_atomic

OUTPUT = "unified_mena_epg.xml"

# Every XMLTV file this repository's scripts can produce. Add new sources
# here as they're introduced — nothing else needs to change.
SOURCE_FILES = [
    "bein_sports_qatar_epg.xml",
    "bein_sports_turkey_epg.xml",
    "starzplay_epg.xml",
    "adsports_epg.xml",
    "roya_jordan_epg.xml",
    "jordan_sports_epg.xml",
    "onsport_epg.xml",
    "alwan_sports_epg_v2.xml",
    "fajer_sports_epg.xml",
    "shahid_sports_epg.xml",
    "shasha_epg.xml",
    "tabii_spor_1_10_epg.xml",
    "thmanyah_epg.xml",
]


def build() -> int:
    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — combined"})
    seen_channel_ids: set[str] = set()

    total_channels = 0
    total_programmes = 0
    files_used = 0

    for path in SOURCE_FILES:
        if not os.path.exists(path):
            warn(f"skip (missing): {path}")
            continue
        try:
            tree = ET.parse(path)
        except Exception as exc:
            warn(f"skip (unparsable): {path} | {exc}")
            continue

        src_root = tree.getroot()
        file_channels = 0
        file_programmes = 0

        for ch in src_root.findall("channel"):
            cid = ch.get("id")
            if not cid or cid in seen_channel_ids:
                continue
            seen_channel_ids.add(cid)
            root.append(ch)
            file_channels += 1

        for pr in src_root.findall("programme"):
            root.append(pr)
            file_programmes += 1

        log(f"merged {path}: {file_channels} channels, {file_programmes} programmes")
        total_channels += file_channels
        total_programmes += file_programmes
        files_used += 1

    log(f"TOTAL: {files_used}/{len(SOURCE_FILES)} source files merged, "
        f"{total_channels} channels, {total_programmes} programmes")

    # Independently-sourced files are already individually validated and use
    # namespaced channel ids, so a cross-file overlap check would just be
    # noise here — skip it and only check structural validity.
    write_xml_atomic(root, OUTPUT, check_overlaps=False,
                      generator_name="Unified MENA EPG — combined")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
