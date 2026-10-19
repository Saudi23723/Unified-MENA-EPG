"""The merge's rules, in a module that imports nothing.

health_check.py runs in a job with no packages installed, so it cannot
import merge_epg (which needs requests, through epg_lib). It imported it
once and failed on 7 October 2026. Both read the rule from here.
"""

from __future__ import annotations


def off_merged_link(cid: str) -> bool:
    """A channel this merge leaves out on purpose: the playlists' own
    channels and the owner's hand-assign channels, which ride the links
    their players read (Playlist.Guide. ids). THE ONE RULE — health_check
    asks this same function, so the two can never disagree about which
    channels a link may share (they did on 7 October 2026: the hand-assign
    channels went on two links, the merge skipped them as designed, and
    the health check, with its own copy of the rule, failed the build)."""
    return cid.startswith("Playlist.Guide.")
