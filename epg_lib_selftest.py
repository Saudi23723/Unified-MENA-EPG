#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The guards in epg_lib, tested.

These are the things standing between a bad run and a broken link, so
they are worth holding still. No network, no fixtures on disk beyond a
temporary directory — run it with `python epg_lib_selftest.py`.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

import epg_lib as L

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{f' — {detail}' if detail else ''}")
        failures.append(name)


def guide(channels: int, programmes: int, *, day: int = 24, ordered: bool = True):
    """A tree with `programmes` non-overlapping entries spread over the
    channels, optionally stored out of time order."""
    root = ET.Element("tv")
    for i in range(channels):
        ET.SubElement(root, "channel", id=f"C{i}")
    rows = []
    for i in range(programmes):
        minute = i % 60
        hour = (i // 60) % 24
        rows.append((f"202608{day:02d}{hour:02d}{minute:02d}00 +0000",
                     f"202608{day:02d}{hour:02d}{minute:02d}30 +0000",
                     f"C{i % max(channels, 1)}"))
    if not ordered:
        rows.reverse()
    for start, stop, cid in rows:
        ET.SubElement(root, "programme", start=start, stop=stop, channel=cid)
    return root


def write(root, path, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            ok = L.write_xml_atomic(root, path, **kw)
        except Exception as exc:
            return exc, buf.getvalue()
    return ok, buf.getvalue()


def main() -> int:
    work = tempfile.mkdtemp()
    path = os.path.join(work, "guide.xml")

    print("write_xml_atomic — publishing")
    ok, _ = write(guide(10, 1000), path, check_overlaps=False)
    check("a healthy run is published", ok is True)
    check("and lands on disk", L.existing_programme_count(path) == 1000)

    print("\nwrite_xml_atomic — the empty-run guard")
    ok, log = write(guide(0, 0), path, check_overlaps=False)
    check("a run with nothing is refused", ok is False)
    check("it says why", "0 programmes produced" in log, log)
    check("the previous file is untouched", L.existing_programme_count(path) == 1000)

    print("\nwrite_xml_atomic — the collapse guard")
    for count in (1200, 900, 700, 400):
        ok, log = write(guide(10, count), path, check_overlaps=False)
        check(f"ordinary movement to {count} still publishes",
              ok is True and "REFUSING" not in log, log)
    ok, log = write(guide(10, 90), path, check_overlaps=False)
    check("a collapse to a fraction is refused", ok is False)
    check("it names the counts", "REFUSING" in log and "programmes" in log, log)
    check("the previous file survives", L.existing_programme_count(path) == 400)

    ok, _ = write(guide(100, 5000), path, check_overlaps=False)
    ok, log = write(guide(9, 4900), path, check_overlaps=False)
    check("losing most channels is refused even with programmes intact",
          ok is False and "channels" in log, log)
    check("channels survive", L.existing_channel_count(path) == 100)

    ok, log = write(guide(3, 50), path, check_overlaps=False, guard_regression=False)
    check("a deliberate narrowing can opt out", ok is True, log)

    small = os.path.join(work, "small.xml")
    write(guide(1, 30), small, check_overlaps=False)
    ok, log = write(guide(1, 6), small, check_overlaps=False)
    check("a small guide is not judged by the ratio",
          ok is True and "REFUSING" not in log, log)

    fresh = os.path.join(work, "fresh.xml")
    ok, _ = write(guide(2, 5), fresh, check_overlaps=False)
    check("a brand-new file always publishes", ok is True)

    print("\nwrite_xml_atomic — overlap is judged in time order, not file order")
    unsorted_path = os.path.join(work, "unsorted.xml")
    ok, log = write(guide(4, 200, ordered=False), unsorted_path, check_overlaps=True)
    check("a valid guide stored out of order is accepted", ok is True, str(log))

    overlapping = ET.Element("tv")
    ET.SubElement(overlapping, "channel", id="C0")
    for start, stop in (("20260824120000 +0000", "20260824140000 +0000"),
                        ("20260824130000 +0000", "20260824150000 +0000")):
        ET.SubElement(overlapping, "programme", start=start, stop=stop, channel="C0")
    result, _ = write(overlapping, os.path.join(work, "bad.xml"), check_overlaps=True)
    check("a real overlap is still rejected", isinstance(result, ValueError), str(result))

    backwards = ET.Element("tv")
    ET.SubElement(backwards, "channel", id="C0")
    ET.SubElement(backwards, "programme", start="20260824140000 +0000",
                  stop="20260824120000 +0000", channel="C0")
    result, _ = write(backwards, os.path.join(work, "back.xml"))
    check("a programme ending before it starts is rejected",
          isinstance(result, ValueError), str(result))

    print("\nresolve_overlaps")
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 8, 24, tzinfo=timezone.utc)
    events = [
        {"start": base, "stop": base + timedelta(hours=2), "title": "A"},
        {"start": base + timedelta(hours=1), "stop": base + timedelta(hours=3), "title": "B"},
        {"start": base + timedelta(minutes=30), "stop": base + timedelta(hours=1), "title": "C"},
    ]
    out = L.resolve_overlaps(events)
    check("swallowed events are dropped", [e["title"] for e in out] == ["A", "B"],
          str([e["title"] for e in out]))
    check("partial overlap is clipped", out[1]["start"] == base + timedelta(hours=2))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all epg_lib guards hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
