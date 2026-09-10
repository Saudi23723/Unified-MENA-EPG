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
import unicodedata
from datetime import date, datetime, timedelta, timezone

from PIL import ImageDraw

from epg_lib import add_programme, log, new_session, warn, write_xml_atomic

CHANNEL_ID = "TodayQuran"
CHANNEL_AR = "وِرْدُ اليوم"
CHANNEL_EN = "Daily Reading"
OUTPUT = "quran_epg.xml"
BOARD_DIR = "boards"
BOARD_PREFIX = "today_quran_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/today_quran.png")
RAW_BOARD = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/boards/" + BOARD_PREFIX + "{n}.png")

VIEWER = timezone.utc
DAYS_AHEAD = 4

# Complete single-file editions of the Arabic text. Each entry says how
# to walk what it returns; the fetch refuses anything that does not
# yield 6236 ayat, which is the whole point of preferring a complete
# edition over an endpoint answering one ayah at a time.
EDITIONS = (
    # THE SIMPLE SPELLING FIRST, and it is a rendering decision rather
    # than a textual preference. The uthmani edition carries letters
    # the faces on the runner draw badly or not at all — the alef
    # wasla, the dagger alef, the sura marks — and the published board
    # showed it: on one line the ayah came out rough and broken while
    # the tafsir's gloss beside it, written in ordinary spelling, was
    # clean. Tajawal is worse again, drawing empty boxes where those
    # letters belong.
    #
    # So the board takes the spelling it can actually render, and the
    # uthmani stays below it as the fallback. If a face that draws the
    # uthmani properly is ever bundled here, put it back on top.
    ("quran-api · ara-quransimple",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
     "/editions/ara-quransimple.json"),
    ("quran-api · ara-quranuthmanihaf",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
     "/editions/ara-quranuthmanihaf.json"),
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


# ── the tafsir, resolved from the index rather than guessed ──────────
#
# THREE GUESSED SLUGS ALL 404'd. ara-tafsiribnkatheer,
# ara-tafsirmuyassar and ara-tafsiraljalalayn were invented from what
# an edition "ought" to be called, and the source disagreed with all
# three. The index answers though — 240 KB of editions, each with its
# name, its author and its own link — so the link is READ, never
# assembled. A guessed URL is the same fault as a guessed reference.
EDITION_INDEX = ("https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
                 "/editions.json")
A_TAFSIR = ("tafsir", "tafseer", "تفسير")


def the_tafsir(session) -> tuple[str, str, list[dict]]:
    """An Arabic tafsir edition, its author, and a row per ayah."""
    try:
        got = session.get(EDITION_INDEX, timeout=45)
        index = got.json() if got.status_code == 200 else {}
    except Exception as exc:                                   # noqa: BLE001
        warn(f"the edition index is unreachable ({exc})")
        return "", "", []
    if not isinstance(index, dict):
        warn("the edition index came back in an unknown shape")
        return "", "", []

    for key, entry in index.items():
        if not isinstance(entry, dict):
            continue
        if (entry.get("language") or "").lower() not in ("arabic", "ar"):
            continue
        words = f"{key} {entry.get('name', '')} {entry.get('author', '')}"
        if not any(word in words.lower() for word in A_TAFSIR):
            continue
        link = entry.get("link") or entry.get("linkmin")
        if not link:
            continue
        try:
            got = session.get(link, timeout=60)
            if got.status_code != 200:
                warn(f"{key}: HTTP {got.status_code}")
                continue
            rows = _rows_from(got.json())
        except Exception as exc:                               # noqa: BLE001
            warn(f"{key}: unreachable ({exc})")
            continue
        if len(rows) != WHOLE_QURAN:
            warn(f"{key}: {len(rows)} rows, not {WHOLE_QURAN} — refused")
            continue
        name = entry.get("name") or key
        author = entry.get("author") or ""
        log(f"  tafsir from {name}"
            + (f" — {author}" if author else "")
            + f": {len(rows)} rows")
        return name, author, rows
    warn("no Arabic tafsir edition in the index answered — the tafsir "
         "board will say so")
    return "", "", []


# ── the hadith, with the grading the SOURCE states ───────────────────
#
# Measured on a runner: the Arabic editions carry hadithnumber,
# reference, grades and text on every row. The grading is READ, never
# inferred — a program that decides a hadith's grade for itself is the
# whole thing this channel refuses to be.
HADITH_EDITIONS = (
    ("صحيح البخاري",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
     "/editions/ara-bukhari.json"),
    ("صحيح مسلم",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
     "/editions/ara-muslim.json"),
    ("الأربعون النووية",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
     "/editions/ara-nawawi.json"),
)


def _grade_from(row) -> str:
    """The grading as written, or nothing. Never a judgement of ours."""
    grades = row.get("grades")
    if isinstance(grades, list):
        for grade in grades:
            if isinstance(grade, dict) and grade.get("grade"):
                return str(grade["grade"]).strip()
            if isinstance(grade, str) and grade.strip():
                return grade.strip()
    if isinstance(grades, str):
        return grades.strip()
    return ""


def the_hadith(session) -> tuple[str, list[dict]]:
    """One collection, every hadith in it, with its own numbering."""
    for book, url in HADITH_EDITIONS:
        try:
            got = session.get(url, timeout=60)
            if got.status_code != 200:
                warn(f"{book}: HTTP {got.status_code}")
                continue
            payload = got.json()
        except Exception as exc:                               # noqa: BLE001
            warn(f"{book}: unreachable ({exc})")
            continue
        rows = payload.get("hadiths") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            warn(f"{book}: no hadiths in it — refused")
            continue
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            number = row.get("hadithnumber")
            if not text or number in (None, ""):
                continue
            out.append({"text": text,
                        "number": str(number),
                        "reference": str(row.get("reference") or ""),
                        "grade": _grade_from(row)})
        if not out:
            warn(f"{book}: nothing in it carried a number and a text")
            continue
        # AN EDITION WITHOUT GRADINGS IS NO USE HERE, however sound the
        # collection. Measured: الأربعون النووية answered with all 42
        # rows carrying number and text, and every board built from it
        # was then refused by sourced_hadith for having no grading —
        # eight boards drawn and four refused, every day the same one.
        # The gate was right and the edition was wrong, so the choice is
        # made here rather than leaving the gate to reject the whole
        # edition one row at a time.
        graded = sum(1 for row in out if row["grade"])
        if not graded:
            warn(f"{book}: {len(out)} rows and not one grading — "
                 f"refused, since an ungraded hadith is not drawn")
            continue
        log(f"  hadith from {book}: {len(out)} of {len(rows)} rows "
            f"usable, {graded} of them graded")
        return book, [row for row in out if row["grade"]]
    return "", []


def to_the_last_whole_word(text: str, room: int) -> str:
    """Shorten to a WORD boundary, never through the middle of one.

    THE FAULT THIS REPLACES. The guide's titles were cut with a plain
    text[:60], and every one of the four came out ending inside a word
    with a bare vowel mark hanging off it — a dammatan, a kasra, a
    kasratan. A combining mark with nothing to combine with is not a
    shortened word, it is a broken one, and in a guide listing it reads
    as mangled Arabic rather than as a line that continues.

    Latin gets away with cutting mid-word because a half word still
    looks like a word. Arabic does not: the letters change shape by
    position and the vowels sit ON the letters, so the cut has to fall
    where the writing itself allows a break.

    So: back up to the last space inside the room, and then strip any
    combining marks left stranded at the new end. Nothing is added if
    nothing was removed — an ellipsis on a complete line is a promise
    of more that is not there.
    """
    text = " ".join((text or "").split())
    if len(text) <= room:
        return text
    cut = text[:room]
    if " " in cut:
        # A WHOLE WORD KEEPS ITS LAST VOWEL. Cutting at the space ends
        # on the final letter of a complete word, and in vocalised
        # Arabic that letter carries its vowel — أَتْرَابٌ ends on a
        # dammatan, ٱلْحِسَابِ on a kasra. Stripping it, as this did at
        # first, does not tidy a broken word: it takes the harakah off
        # a correct one.
        return f"{cut[:cut.rindex(' ')].rstrip()}…"
    # NO SPACE AT ALL, so the cut really did land inside a single word
    # and whatever marks trail it have lost the letter they sat on.
    # Those are the only ones worth removing.
    while cut and unicodedata.combining(cut[-1]):
        cut = cut[:-1]
    return f"{cut}…" if cut else text[:room]


def sourced(row: dict, edition: str) -> bool:
    """THE GATE. Four things or it is not drawn."""
    return bool(edition) and bool(row.get("text")) \
        and isinstance(row.get("sura"), int) and row["sura"] >= 1 \
        and isinstance(row.get("ayah"), int) and row["ayah"] >= 1


def sourced_tafsir(row: dict, edition: str) -> bool:
    """A tafsir row is drawn only with a named work behind it."""
    return sourced(row, edition)


def sourced_hadith(row: dict, book: str) -> bool:
    """A hadith is drawn only with its book, its number and its GRADING.

    The grading is required, not optional. An ungraded hadith on a
    screen is a claim this program is not entitled to make, and the
    source that has no grading for a row is telling us something we
    must pass on by not drawing it.
    """
    return (bool(book) and bool(row.get("text"))
            and bool(str(row.get("number") or "").strip())
            and bool(str(row.get("grade") or "").strip()))


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


def draw_tafsir(day, row, work, author):
    from nur_theme import (
        GOLD_DIM, H, MUTED, PAD, SANS, SANS_MID, W, WHITE, digits, face,
        frame, ground, masthead, pill_left, wrap, write,
    )
    board = ground()
    pen = ImageDraw.Draw(board)
    top = masthead(board, pen, "التفسير", work or "", day,
                   right_note=author or "")
    frame(pen, (PAD, top, W - PAD, H - 62), ornate=bool(row))
    if not row:
        write(pen, (W // 2, (top + H - 62) // 2),
              "لم يصل التفسيرُ من مصدرِه اليوم", face(SANS, 32), MUTED,
              anchor="mm")
        write(pen, (W // 2, (top + H - 62) // 2 + 52),
              "ولا يُعرَض ما لم يَرِد عن مصدر", face(SANS_MID, 22),
              GOLD_DIM, anchor="mm")
        return board
    pill_left(pen, PAD + 34, top + 26,
              f"{digits(row['sura'])} · {digits(row['ayah'])}",
              face(SANS, 22))
    for size in range(34, 17, -2):
        font = face(SANS_MID, size)
        lines = wrap(pen, row["text"], font, W - 2 * PAD - 120)
        if len(lines) * (size + 16) <= H - 62 - top - 120:
            break
    at = top + 110
    for line in lines[:12]:
        write(pen, (W // 2, at), line, font, WHITE, anchor="mm")
        at += size + 16
    return board


def draw_hadith(day, row, book):
    from nur_theme import (
        GOLD_DIM, GREEN, H, MUTED, NASKH_BOLD, PAD, SANS, SANS_MID, W,
        WHITE, digits, face, frame, ground, masthead, pill_left, wrap,
        write,
    )
    board = ground()
    pen = ImageDraw.Draw(board)
    top = masthead(board, pen, "الحديث", book or "", day)
    frame(pen, (PAD, top, W - PAD, H - 62), ornate=bool(row))
    if not row:
        write(pen, (W // 2, (top + H - 62) // 2),
              "لم يصل الحديثُ من مصدرِه اليوم", face(SANS, 32), MUTED,
              anchor="mm")
        write(pen, (W // 2, (top + H - 62) // 2 + 52),
              "ولا يُعرَض ما لم يَرِد عن مصدر", face(SANS_MID, 22),
              GOLD_DIM, anchor="mm")
        return board
    right = pill_left(pen, PAD + 34, top + 26, digits(row["number"]),
                      face(SANS, 22))
    # The grading is the source's word, printed as the source wrote it.
    pill_left(pen, right + 16, top + 26, row["grade"], face(SANS, 21),
              fill=(20, 62, 46, 255), ink=GREEN)
    if row.get("reference"):
        write(pen, (W - PAD - 34, top + 46), row["reference"],
              face(SANS_MID, 20), MUTED, anchor="rm")
    for size in range(40, 19, -2):
        font = face(NASKH_BOLD, size)
        lines = wrap(pen, row["text"], font, W - 2 * PAD - 130)
        if len(lines) * (size + 20) <= H - 62 - top - 130:
            break
    at = top + 116
    for line in lines[:10]:
        write(pen, (W // 2, at), line, font, WHITE, anchor="mm")
        at += size + 20
    return board


def main() -> int:
    session = new_session()
    edition, rows = the_quran(session)
    if not rows:
        warn("no edition answered — the boards will say so and nothing "
             "will be invented")

    now = datetime.now(VIEWER)
    days = [now.date() + timedelta(days=n) for n in range(DAYS_AHEAD)]
    channel = CHANNEL_ID
    programmes = []
    drawn = refused = 0

    work, author, tafsir_rows = the_tafsir(session)
    book, hadith_rows = the_hadith(session)

    board = 0
    for day in days:
        first_board = board
        # THREE BOARDS A DAY, each refusing on its own. A tafsir that
        # did not arrive does not stop the ayah that did.
        reading = the_days_reading(rows, day) if rows else None
        if reading is not None and not sourced(reading, edition):
            refused += 1
            reading = None
        draw(day, reading, edition).convert("RGB").save(
            f"boards/today_quran_{board}.png")
        board += 1
        drawn += reading is not None

        note = the_days_reading(tafsir_rows, day) if tafsir_rows else None
        if note is not None and not sourced_tafsir(note, work):
            refused += 1
            note = None
        draw_tafsir(day, note, work, author).convert("RGB").save(
            f"boards/today_quran_{board}.png")
        board += 1
        drawn += note is not None

        # A BOARD THAT CAN ONLY EVER SAY "لم يصل" IS NOT DRAWN AT ALL.
        # Measured on a runner: البخاري, مسلم and النووية all answer,
        # all carry a grades KEY, and not one of 14,982 rows between
        # them carries a grading in it. So there is no graded hadith to
        # be had from this source, and a hadith board here would show
        # its own error message every day for ever — which teaches a
        # viewer to ignore the one day it means something.
        #
        # The day the source starts publishing gradings, or a graded
        # one is added to HADITH_EDITIONS, the board appears by itself.
        # Nothing else needs changing.
        if hadith_rows:
            said = the_days_reading(hadith_rows, day)
            if not sourced_hadith(said, book):
                refused += 1
                said = None
            draw_hadith(day, said, book).convert("RGB").save(
                f"boards/today_quran_{board}.png")
            board += 1
            drawn += said is not None

        title = (f"⁦{to_the_last_whole_word(reading['text'], 60)}⁩"
                 if reading else "لم يصل النصُّ من مصدرِه")
        start = datetime.combine(day, datetime.min.time(), VIEWER)
        # THE ICON IS NOT DECORATION, IT IS WHAT THE SCREEN GATE READS.
        # A programme with no <icon> pointing at one of this screen's
        # own boards fails "every real programme points at one of the
        # screen's own boards", the gate names the screen, and
        # quarantine_screens.py holds it back — every pass, for ever.
        # That is why this channel was built and encoded on the runner
        # and never once appeared on main.
        #
        # And it must be the day's FIRST board, not any board of it:
        # that is the page a viewer lands on when the day arrives, and
        # a programme pointing at a later one skips the day's first
        # page on every tune-in. With two boards a day the first ones
        # are 0, 2, 4, 6 — which is what `board` held before this day's
        # boards were drawn.
        programmes.append((channel, start, start + timedelta(days=1),
                           title, RAW_BOARD.format(n=first_board)))

    # The manifest counts what was actually drawn, not what was hoped
    # for: the encoder reads this to know how many boards a day owns,
    # and a count that disagrees with the files is the torn screen the
    # publish gate exists to catch.
    per_day = board // len(days)
    with open("boards/today_quran_days.txt", "w", encoding="utf-8") as out:
        out.write("\n".join(str(per_day) for _ in days) + "\n")
    log(f"  {per_day} board(s) a day")

    root = write_guide(channel, programmes)
    write_xml_atomic(root, "quran_epg.xml")
    log(f"  {drawn} sourced board(s) drawn, {refused} row(s) refused, "
        f"over {len(days)} day(s)")
    return 0


def write_guide(channel: str, programmes):
    import xml.etree.ElementTree as ET
    root = ET.Element("tv")
    node = ET.SubElement(root, "channel", {"id": channel})
    ET.SubElement(node, "display-name").text = "وِرْدُ اليوم"
    for chan, start, stop, title, icon in programmes:
        add_programme(root, chan, start, stop, title, icon=icon)
    return root


if __name__ == "__main__":
    sys.exit(main())
