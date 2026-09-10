#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""وِرْدُ اليوم — an ayah a day, and not one letter that is not sourced.

THE RULE THIS FILE EXISTS FOR
-----------------------------
Every other channel here may show a fixture with no broadcaster beside
it, because a missing channel name costs a viewer a click. This board is
not that. The reader put it plainly: هاد دين مش هبل — so the rule is
absolute and it is enforced in code, not in a comment:

    NOTHING IS DRAWN THAT DID NOT ARRIVE VERBATIM FROM A SOURCE,
    CARRYING ITS OWN REFERENCE.

A row reaches the board only if the fetch handed back all four of:
the text, the sura number, the ayah number, and the name of the edition
it came from. A row missing any one of them is refused — not guessed,
not filled in, not approximated from anything this program knows. If no
source answers, the channel draws its "no reading today" board and says
so. An empty board is a fault to be fixed; a board with an invented
ayah on it is not a fault, it is a lie.

WHAT IS NOT HERE, AND WHY
-------------------------
No tafsir and no hadith. Both were drawn in a preview and both were
written from memory, which is exactly the thing this file forbids: a
tafsir needs a named published work quoted verbatim, and a hadith needs
its takhrij and its grading as the source states them, not as a program
infers them. Neither is shipped until a source is measured that carries
that attribution itself. The board is smaller for it and correct.

THE TEXT IS FETCHED, NOT CARRIED
--------------------------------
The editions below are tried in order and the first that answers with a
complete, well-formed Quran is used; the run logs which one won, so the
board's provenance is in the build log and not only in this comment.
Nothing is bundled in this repository, so there is no copy here that can
drift from what the source publishes.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone

from PIL import ImageDraw

from epg_lib import add_programme, log, new_session, warn, write_xml_atomic

VIEWER = timezone.utc
DAYS_AHEAD = 4

# Complete single-file editions of the Arabic text. Each entry says how
# to walk what it returns; the fetch refuses anything that does not
# yield 6236 ayat, which is the whole point of preferring a complete
# edition over an endpoint answering one ayah at a time.
EDITIONS = (
    ("quran-api · ara-quranuthmanihaf",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
     "/editions/ara-quranuthmanihaf.json"),
    ("quran-api · ara-quransimple",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
     "/editions/ara-quransimple.json"),
    ("alquran.cloud · quran-uthmani",
     "https://api.alquran.cloud/v1/quran/quran-uthmani"),
)

WHOLE_QURAN = 6236


def _rows_from(payload) -> list[dict]:
    """Every ayah in whatever shape this edition publishes.

    Two shapes are known and both are walked explicitly rather than by
    guessing at keys: a flat list under "quran", and alquran.cloud's
    surahs-then-ayahs nesting. An edition in a third shape yields
    nothing and the next one is tried — which is the correct outcome,
    because a parser that guesses is how a wrong reference reaches a
    board.
    """
    out: list[dict] = []
    if isinstance(payload, dict) and isinstance(payload.get("quran"), list):
        for row in payload["quran"]:
            try:
                out.append({"sura": int(row["chapter"]),
                            "ayah": int(row["verse"]),
                            "text": str(row["text"]).strip()})
            except (KeyError, TypeError, ValueError):
                return []
        return out
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict) and isinstance(data.get("surahs"), list):
        for sura in data["surahs"]:
            try:
                number = int(sura["number"])
                for ayah in sura["ayahs"]:
                    out.append({"sura": number,
                                "ayah": int(ayah["numberInSurah"]),
                                "text": str(ayah["text"]).strip()})
            except (KeyError, TypeError, ValueError):
                return []
        return out
    return []


def the_quran(session) -> tuple[str, list[dict]]:
    """The first complete edition that answers, and its name."""
    for name, url in EDITIONS:
        try:
            got = session.get(url, timeout=40)
            if got.status_code != 200:
                warn(f"{name}: HTTP {got.status_code}")
                continue
            rows = _rows_from(got.json())
        except (ValueError, json.JSONDecodeError) as exc:
            warn(f"{name}: not readable JSON ({exc})")
            continue
        except Exception as exc:                               # noqa: BLE001
            warn(f"{name}: unreachable ({exc})")
            continue
        if len(rows) != WHOLE_QURAN:
            warn(f"{name}: {len(rows)} ayat, not {WHOLE_QURAN} — refused")
            continue
        if any(not row["text"] or row["sura"] < 1 or row["ayah"] < 1
               for row in rows):
            warn(f"{name}: an ayah came back empty or unnumbered — refused")
            continue
        log(f"  reading from {name}: {len(rows)} ayat")
        return name, rows
    return "", []


def sourced(row: dict, edition: str) -> bool:
    """THE GATE. Four things or it is not drawn."""
    return bool(edition) and bool(row.get("text")) \
        and isinstance(row.get("sura"), int) and row["sura"] >= 1 \
        and isinstance(row.get("ayah"), int) and row["ayah"] >= 1


def the_days_reading(rows: list[dict], day: date) -> dict:
    """Which ayah this day gets.

    The day's ordinal walks the whole book, so the reading is settled by
    the calendar and not by a random seed: the same day gives the same
    ayah on every machine and on every rebuild, which is what stops the
    board changing under a television that is already showing it.
    """
    return rows[day.toordinal() % len(rows)]


# ── the board ─────────────────────────────────────────────────────────
def draw(day: date, reading: dict | None, edition: str):
    """One board. With a reading, or saying plainly that there is none."""
    from nur_theme import (
        GOLD_DIM, H, MUTED, NASKH_BOLD, PAD, SANS, SANS_MID, W, WHITE,
        digits, face, frame, ground, masthead, pill_left, wrap, write,
    )
    board = ground()
    pen = ImageDraw.Draw(board)
    top = masthead(board, pen, "وِرْدُ اليوم", "آيةُ اليوم", day,
                   right_note=edition or "")

    if reading is None:
        frame(pen, (PAD, top, W - PAD, H - 62))
        write(pen, (W // 2, (top + H - 62) // 2),
              "لم يصل النصُّ من مصدرِه اليوم", face(SANS, 34), MUTED,
              anchor="mm")
        write(pen, (W // 2, (top + H - 62) // 2 + 56),
              "ولا يُعرَض ما لم يَرِد عن مصدر", face(SANS_MID, 23),
              GOLD_DIM, anchor="mm")
        return board

    frame(pen, (PAD, top, W - PAD, H - 62), ornate=True)
    reference = f"{digits(reading['sura'])} · {digits(reading['ayah'])}"
    pill_left(pen, PAD + 34, top + 26, reference, face(SANS, 22))
    write(pen, (W - PAD - 34, top + 46), edition, face(SANS_MID, 20),
          MUTED, anchor="rm")

    # The size steps down until the whole ayah fits: an ayah is never
    # cut, never ellipsised and never spilled off the card.
    for size in range(48, 21, -2):
        font = face(NASKH_BOLD, size)
        lines = wrap(pen, reading["text"], font, W - 2 * PAD - 140)
        if len(lines) * (size + 22) <= H - 62 - top - 130:
            break
    middle = top + 100 + (H - 62 - 60 - (top + 100)) // 2
    step = size + 22
    at = middle - (len(lines) - 1) * step // 2
    for line in lines:
        write(pen, (W // 2, at), line, font, WHITE, anchor="mm")
        at += step
    return board


def main() -> int:
    session = new_session()
    edition, rows = the_quran(session)
    if not rows:
        warn("no edition answered — the boards will say so and nothing "
             "will be invented")

    now = datetime.now(VIEWER)
    days = [now.date() + timedelta(days=n) for n in range(DAYS_AHEAD)]
    channel = "quran.today"
    programmes = []
    drawn = refused = 0

    for n, day in enumerate(days):
        reading = the_days_reading(rows, day) if rows else None
        if reading is not None and not sourced(reading, edition):
            refused += 1
            reading = None
        draw(day, reading, edition).convert("RGB").save(
            f"boards/today_quran_{n}.png")
        drawn += reading is not None
        title = (f"⁦{reading['text'][:60]}…⁩" if reading
                 else "لم يصل النصُّ من مصدرِه")
        start = datetime.combine(day, datetime.min.time(), VIEWER)
        programmes.append((channel, start, start + timedelta(days=1), title))

    with open("boards/today_quran_days.txt", "w", encoding="utf-8") as out:
        out.write("\n".join("1" for _ in days) + "\n")

    root = write_guide(channel, programmes)
    write_xml_atomic("quran_epg.xml", root)
    log(f"  {drawn} day(s) with a sourced reading, {refused} refused, "
        f"{len(days) - drawn - refused} with none to show")
    return 0


def write_guide(channel: str, programmes):
    import xml.etree.ElementTree as ET
    root = ET.Element("tv")
    node = ET.SubElement(root, "channel", {"id": channel})
    ET.SubElement(node, "display-name").text = "وِرْدُ اليوم"
    for chan, start, stop, title in programmes:
        add_programme(root, chan, start, stop, title)
    return root


if __name__ == "__main__":
    sys.exit(main())
