"""Is Roya's own backend still publishing a schedule?

MEASUREMENT ONLY — this writes nothing and changes nothing.

The published guide says something is wrong and says it precisely. Its
rows are filler in exactly the shape a source that has gone quiet leaves
behind: the OLD days hold real listings and the NEW ones hold almost
none, because the old days were fetched while the API still answered and
every build since has had nothing to put in the gaps.

    day        rows  filler    %
    20260902     15       0    0%
    20260905   1949      73    4%
    20260907   1823     765   42%
    20260909   1965    1749   89%
    20260910   1995    1890   95%   <- today
    20260911    810     810  100%   <- tomorrow, nothing but filler

So the question is not "is the ratio too high". It is: WHAT DOES THE API
RETURN NOW. Both endpoints are asked, because the generator reads one
and its own docstring describes the other, and they have changed shape
before.

Prints shape and counts. Never a programme's text.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from epg_lib import fetch, log, new_session, warn  # noqa: E402

ENDPOINTS = (
    ("schedule", "https://backend.roya.tv/api/v01/channels/schedule"),
    ("schedule-pagination",
     "https://backend.roya.tv/api/v01/channels/schedule-pagination"),
)


def channel_blocks(payload) -> list[dict]:
    """The generator's own recogniser, copied so the probe sees what it sees."""
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if "programs" in node and (node.get("title") or node.get("name")):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def probe(session, name: str, url: str) -> None:
    log(f"\n=== {name}  {url}")
    for day in (-1, 0, 1, 2, 3, 6):
        try:
            response = fetch(session, url, params={"day_number": day})
        except Exception as exc:
            log(f"  day {day:>2}: {type(exc).__name__}: {str(exc)[:90]}")
            continue

        body = response.content or b""
        try:
            payload = response.json()
        except Exception as exc:
            log(f"  day {day:>2}: HTTP {response.status_code}, {len(body)} bytes, "
                f"NOT JSON ({str(exc)[:40]}) — starts {body[:60]!r}")
            continue

        blocks = channel_blocks(payload)
        programmes = sum(len(b.get("programs") or []) for b in blocks)
        empty = sum(1 for b in blocks if not (b.get("programs") or []))
        top = list(payload)[:6] if isinstance(payload, dict) else type(payload).__name__
        log(f"  day {day:>2}: HTTP {response.status_code}, {len(body):>7} bytes, "
            f"{len(blocks):>3} channel(s), {programmes:>5} programme(s), "
            f"{empty:>3} of them empty")
        if day == 0:
            log(f"           top-level: {top}")
            if blocks:
                one = blocks[0]
                log(f"           a channel's keys: {sorted(one)[:12]}")
                rows = one.get("programs") or []
                if rows and isinstance(rows[0], dict):
                    log(f"           a programme's keys: {sorted(rows[0])[:12]}")
                else:
                    log(f"           its programs list is {len(rows)} long")


def reproduce_the_build(session) -> None:
    """Run the generator's OWN filter over day 0 and count what it drops.

    The API answers with 1741 programmes for today and the published
    guide carries about a hundred real rows for it, so something between
    the two is throwing them away. This is that gap, counted by reason
    rather than reasoned about — the last guess about this guide was
    wrong and cost a round trip.
    """
    log("\n=== the build's own filter, over day 0")

    import roya_jordan_epg as roya

    channels = roya.canonical_channels(roya.discover_channels(session))
    log(f"  channels the build knows: {len(channels)}")

    blocks = roya.fetch_day(session, 0)
    ids_seen = {str(b.get("id")) for b in blocks}
    log(f"  channel ids in the day response: {len(ids_seen)}")
    log(f"  ids the build has no meta for:   "
        f"{len(ids_seen - set(channels))}")

    kept = 0
    no_meta = no_start = no_end = bad_span = no_title = 0
    all_keys: set[str] = set()
    for block in blocks:
        meta = channels.get(str(block.get("id")))
        rows = block.get("programs") or []
        if not meta:
            no_meta += len(rows)
            continue
        for row in rows:
            if isinstance(row, dict):
                all_keys |= set(row)
            if row.get("start_timestamp") is None:
                no_start += 1
                continue
            if row.get("end_timestamp") is None:
                no_end += 1
                continue
            try:
                if int(row["end_timestamp"]) <= int(row["start_timestamp"]):
                    bad_span += 1
                    continue
            except Exception:
                bad_span += 1
                continue
            if not (row.get("name") or "").strip():
                no_title += 1
                continue
            kept += 1

    log(f"  KEPT                              {kept}")
    log(f"  dropped, channel not in the map   {no_meta}")
    log(f"  dropped, no start_timestamp       {no_start}")
    log(f"  dropped, no end_timestamp         {no_end}")
    log(f"  dropped, stop not after start     {bad_span}")
    log(f"  dropped, no title                 {no_title}")
    log(f"\n  EVERY key a programme carries: {sorted(all_keys)}")


def run_the_real_build() -> None:
    """Run the generator for real and measure the file it writes.

    The filter keeps all 1741 — so whatever loses them happens AFTER it,
    and reading the build's own output is the only way to see where. The
    probe still commits nothing: the file lands in the runner's checkout
    and dies with it.
    """
    log("\n=== the real build, and the file it writes")

    import collections
    import xml.etree.ElementTree as ET

    import roya_jordan_epg as roya

    code = roya.build()
    log(f"  build() returned {code}")

    root = ET.parse(roya.OUTPUT).getroot()
    rows = list(root.iter("programme"))
    channels = list(root.iter("channel"))
    filler = [p for p in rows
              if "لم يُعلن" in (p.findtext("title") or "")]
    log(f"  {len(channels)} channel(s), {len(rows)} row(s), "
        f"{len(filler)} filler ({round(100 * len(filler) / max(len(rows), 1))}%)")

    per_day = collections.Counter(p.get("start")[:8] for p in rows)
    blind_day = collections.Counter(p.get("start")[:8] for p in filler)
    log(f"  {'day':10} {'rows':>6} {'filler':>7} {'%':>5}")
    for day in sorted(per_day):
        n, b = per_day[day], blind_day[day]
        log(f"  {day:10} {n:6} {b:7} {round(100 * b / n):4}%")


def main() -> int:
    session = new_session()
    for name, url in ENDPOINTS:
        try:
            probe(session, name, url)
        except Exception as exc:
            warn(f"{name} could not be probed: {exc}")
    try:
        reproduce_the_build(session)
    except Exception as exc:
        warn(f"the build's filter could not be reproduced: {exc}")
    try:
        run_the_real_build()
    except Exception as exc:
        warn(f"the real build could not be run: {exc}")
    log("\nWhat matters: whether a day the guide draws as 100% filler "
        "comes back with programmes here. If it does, the generator is "
        "dropping them. If it does not, the API has gone quiet and the "
        "filler is honest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
