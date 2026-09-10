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


def main() -> int:
    session = new_session()
    for name, url in ENDPOINTS:
        try:
            probe(session, name, url)
        except Exception as exc:
            warn(f"{name} could not be probed: {exc}")
    log("\nWhat matters: whether a day the guide draws as 100% filler "
        "comes back with programmes here. If it does, the generator is "
        "dropping them. If it does not, the API has gone quiet and the "
        "filler is honest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
