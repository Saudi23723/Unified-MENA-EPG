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
import re
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

    print("\nwrite_xml_atomic — the absolute floor, for guides that shrank on purpose")
    floored = os.path.join(work, "floored.xml")
    ok, _ = write(guide(8, 180), floored, check_overlaps=False,
                  guard_regression=False, min_programmes=60)
    check("a run above the floor publishes", ok is True)
    ok, log = write(guide(8, 200), floored, check_overlaps=False,
                    guard_regression=False, min_programmes=60)
    check("so does the next one", ok is True, log)
    ok, log = write(guide(8, 12), floored, check_overlaps=False,
                    guard_regression=False, min_programmes=60)
    check("a run under the floor is refused", ok is False)
    check("it names the floor", "floor of 60" in log, log)
    check("the previous file survives", L.existing_programme_count(floored) == 200)

    # The case that made the floor necessary: a guide that deliberately
    # shrank to a third of itself must still be publishable.
    narrowed = os.path.join(work, "narrowed.xml")
    write(guide(8, 666), narrowed, check_overlaps=False)
    ok, log = write(guide(8, 180), narrowed, check_overlaps=False,
                    guard_regression=False, min_programmes=60)
    check("a deliberate drop to 27% publishes with a floor instead of the ratio",
          ok is True, log)
    check("and it really replaced the file",
          L.existing_programme_count(narrowed) == 180)

    empty_start = os.path.join(work, "nofile.xml")
    ok, log = write(guide(1, 5), empty_start, check_overlaps=False,
                    min_programmes=60)
    check("with no previous file, a thin run is published rather than nothing",
          ok is True, log)

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
    # A start is published as the source gave it; a stop yields instead.
    check("every start survives untouched",
          [e["start"] for e in out] == [base, base + timedelta(minutes=30),
                                        base + timedelta(hours=1)],
          str([str(e["start"]) for e in out]))
    check("nothing is dropped when starts differ",
          [e["title"] for e in out] == ["A", "C", "B"],
          str([e["title"] for e in out]))
    check("the earlier event is cut short, not the later one delayed",
          out[0]["stop"] == base + timedelta(minutes=30)
          and out[1]["stop"] == base + timedelta(hours=1))
    check("no overlap remains",
          all(a["stop"] <= b["start"] for a, b in zip(out, out[1:])))

    # The real case this was changed for: Spor Ekranı gave two tabii Spor 7
    # slots the same 18:00 start, and the second was published at 21:00.
    same = [
        {"start": base + timedelta(hours=18), "stop": base + timedelta(hours=21),
         "title": "Badminton"},
        {"start": base + timedelta(hours=18), "stop": base + timedelta(hours=21),
         "title": "Paletli Yuzme"},
    ]
    out2 = L.resolve_overlaps(same)
    check("two events on the same minute keep one, and it is not moved",
          len(out2) == 1 and out2[0]["start"] == base + timedelta(hours=18),
          str([(e["title"], str(e["start"])) for e in out2]))

    # An event wholly inside another must not be pushed past it either.
    inside = [
        {"start": base, "stop": base + timedelta(hours=3), "title": "long"},
        {"start": base + timedelta(hours=1), "stop": base + timedelta(hours=2),
         "title": "inside"},
    ]
    out3 = L.resolve_overlaps(inside)
    check("an event inside another keeps its own start",
          [e["start"] for e in out3] == [base, base + timedelta(hours=1)],
          str([(e["title"], str(e["start"])) for e in out3]))

    # ------------------------------------------------------------ countdown
    #
    # A countdown block may never outlast the time it counts down. When it
    # did, a viewer two minutes from kickoff was shown "بعد 12 د" — the
    # coarsest reading at the moment it matters most, and wrong in the
    # direction that makes someone miss the start.
    print("\ncountdown")

    too_long = [
        left for left in range(1, 60 * 30)
        if L.countdown_step(timedelta(minutes=left)).total_seconds() // 60
        > max(left, 1)
    ]
    check("no block outlasts the time it counts down, over 30 hours",
          not too_long, f"first bad offset: {too_long[:3]}")

    # The old rule here demanded two-minute blocks in the last quarter
    # hour. It bought an exact number and cost the guide its shape: 93% of
    # every published row was countdown, which is what a viewer sees when
    # they scroll. Rows are the scarce thing, not minutes.
    #
    # What still has to hold is the ceiling on the whole run: three hours
    # out, a countdown must not need more than a handful of blocks.
    blocks, left = 0, 180
    while left > 0:
        left -= int(L.countdown_step(timedelta(minutes=left)
                                     ).total_seconds() // 60)
        blocks += 1
    check("a countdown from the horizon costs at most 6 rows",
          blocks <= 6, f"{blocks} rows per kickoff")

    check("and no block is longer than an hour",
          max(int(L.countdown_step(timedelta(minutes=m)).total_seconds() // 60)
              for m in range(1, 60 * 30)) <= 60, "a block runs over an hour")

    check("every unit is a whole word, so a number cannot drift from it",
          L.countdown_label(0) == "أقل من دقيقة"
          and L.countdown_label(1) == "دقيقة"
          and L.countdown_label(2) == "دقيقتين"
          and L.countdown_label(5) == "5 دقائق"
          and L.countdown_label(45) == "45 دقيقة"
          and L.countdown_label(60) == "ساعة"
          and L.countdown_label(95) == "ساعة و35 دقيقة"
          and L.countdown_label(150) == "ساعتين و30 دقيقة"
          and L.countdown_label(1170) == "19 ساعة و30 دقيقة"
          and L.countdown_label(60 * 24) == "يوم"
          and L.countdown_label(60 * 25) == "يوم وساعة"
          and L.countdown_label(60 * 24 * 3 + 60) == "3 أيام وساعة",
          L.countdown_label(1170))

    # "19 س و30 د" was read on a television as nineteen minutes, as thirty
    # minutes, and as thirty hours and nineteen minutes — three readings of
    # one line, because a lone letter beside a Latin club name does not stay
    # next to its number. No abbreviated unit may come back.
    letters = re.compile(r"(?:^|\s)[سدي](?:\s|$)")
    abbreviated = [m for m in range(0, 60 * 30, 7)
                   if letters.search(L.countdown_label(m))]
    check("no label falls back to a single-letter unit, over 30 hours",
          not abbreviated,
          f"first abbreviated offset: {abbreviated[:3]}")

    # The separator is isolated from the names in front of it: on a real
    # screen "⏰ Fiorentina - Frosinone + Monza - Udinese · بعد15 ساعة و"
    # came out as one unbroken run, the countdown drifting from its number.
    # That is a direction problem, not a wording one — see isolate().
    dot = L.isolate("·")
    title = L.countdown_title("A - B", 95)
    check("one wording, marked as a wait rather than a broadcast",
          title == f"{L.COUNTDOWN_MARK} A - B {dot} بعد ساعة و35 دقيقة"
          and L.countdown_title("A - B", 3)
          == f"{L.COUNTDOWN_MARK} A - B {dot} بعد 3 دقائق",
          title)

    # ---------------------------------------------------- label_fixtures
    print("\nlabel_fixtures — several matches in one row")
    three = L.label_fixtures(["Fiorentina - Frosinone", "Monza - Udinese",
                              "Sassuolo - Torino"])
    check("each match is lettered so the eye has somewhere to land",
          "A) Fiorentina" in three and "B) Monza" in three
          and "C) Sassuolo" in three, three)
    check("and each is isolated, so no name reorders its neighbour",
          three.count(L.FSI) == 3 and three.count(L.PDI) == 3, three)
    check("a single match is not lettered",
          L.label_fixtures(["Milan - Venezia"]) == L.isolate("Milan - Venezia"),
          L.label_fixtures(["Milan - Venezia"]))
    check("nothing in, nothing out", L.label_fixtures([]) == "", "!")
    check("every isolate opened is closed, in the finished title",
          (lambda t: t.count(L.FSI) == t.count(L.PDI))(
              L.countdown_title(three, 930)), "unbalanced")

    # -------------------------------------------------------- fill_wait
    #
    # 17 matches were being published as 640 rows, 623 of them countdown
    # blocks, because a five-day gap was filled hour by hour. A guide is
    # meant to answer "what is next" in one row, not repeat it 120 times.
    print("\nfill_wait — a long wait is one row, not a ticker")

    day0 = datetime(2026, 8, 28, 0, 0)
    kickoff = day0 + timedelta(days=5, hours=21, minutes=30)

    rows: list[tuple[datetime, datetime, str]] = []

    def emit(start, stop, title):
        rows.append((start, stop, title))

    # One day at a time, the way both guides call it.
    for offset in range(6):
        start = day0 + timedelta(days=offset)
        stop = min(start + timedelta(days=1), kickoff)
        if stop <= start:
            continue
        L.fill_wait(start, stop,
                    lambda m: kickoff if kickoff >= m else None,
                    lambda k: "A - B", emit, "nothing")

    waits = [r for r in rows if r[2].startswith(f"{L.COUNTDOWN_MARK} المباراة القادمة")]
    counts = [r for r in rows if "بعد" in r[2]]
    check("a five-day wait is one row a day, not one an hour",
          len(waits) == 6, f"{len(waits)} wait rows over six days")
    check("the countdown is short and only near kickoff",
          len(counts) <= 30
          and all(kickoff - c[0] <= L.COUNTDOWN_HORIZON for c in counts),
          f"{len(counts)} countdown rows, "
          f"earliest {min((kickoff - c[0] for c in counts), default=0)} out")
    check("the whole span is covered with no gap and no overlap",
          all(rows[i][1] == rows[i + 1][0] for i in range(len(rows) - 1))
          and rows[0][0] == day0 and rows[-1][1] == kickoff,
          f"{len(rows)} rows, {rows[0][0]} .. {rows[-1][1]}")
    check("every row ends after it starts",
          all(a < b for a, b, _ in rows), "a row ends before it starts")
    check("the wait row names the match without a clock in the title",
          waits and "A - B" in waits[0][2]
          and not re.search(r"\d{1,2}:\d{2}", waits[0][2]),
          waits[0][2] if waits else "no wait row")

    # Nothing announced: one row, not one an hour saying nothing is on.
    empty: list[tuple[datetime, datetime, str]] = []
    L.fill_wait(day0, day0 + timedelta(days=3),
                lambda m: None, lambda k: "",
                lambda a, b, t: empty.append((a, b, t)), "لا شيء")
    check("an unannounced stretch is a single row",
          len(empty) == 1 and empty[0][2] == "لا شيء"
          and empty[0][1] - empty[0][0] == timedelta(days=3),
          f"{len(empty)} rows")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all epg_lib guards hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
