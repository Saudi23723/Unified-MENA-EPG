#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Can anything unsourced reach the board? It must not.

The fixtures here carry NO scripture. Every text field is the word
"نص" repeated, because a test fixture written from memory is the same
fault the channel exists to prevent — and because what is under test is
the shape of a row and the refusal of a bad one, never the words.
"""
import sys

import quran_epg as q

FAILED = 0


def check(what, got, want):
    global FAILED
    ok = got == want
    FAILED += not ok
    print(f"  {'ok  ' if ok else 'BAD '} {what}"
          + ("" if ok else f"\n         got {got!r}, wanted {want!r}"))


print("A row is drawn only if it is sourced")
good = {"sura": 2, "ayah": 255, "text": "نص"}
check("a complete row with a named edition passes",
      q.sourced(good, "an edition"), True)
check("the same row with NO edition named is refused",
      q.sourced(good, ""), False)
for missing in ("text", "sura", "ayah"):
    row = dict(good)
    row.pop(missing)
    check(f"a row with no {missing} is refused",
          q.sourced(row, "an edition"), False)
check("an empty text is refused",
      q.sourced({**good, "text": ""}, "an edition"), False)
check("a zero sura is refused",
      q.sourced({**good, "sura": 0}, "an edition"), False)
check("a sura that is not a number is refused",
      q.sourced({**good, "sura": "2"}, "an edition"), False)

print("\nA hadith is drawn only with its book, its number AND its grading")
said = {"text": "نص", "number": "1", "reference": "ref", "grade": "درجة"}
check("a complete hadith with a named book passes",
      q.sourced_hadith(said, "كتاب"), True)
check("with NO book named it is refused",
      q.sourced_hadith(said, ""), False)
check("with no number it is refused",
      q.sourced_hadith({**said, "number": ""}, "كتاب"), False)
check("with no text it is refused",
      q.sourced_hadith({**said, "text": ""}, "كتاب"), False)
check("AND WITH NO GRADING IT IS REFUSED — the whole point",
      q.sourced_hadith({**said, "grade": ""}, "كتاب"), False)
check("a grading of whitespace is not a grading",
      q.sourced_hadith({**said, "grade": "   "}, "كتاب"), False)
check("a missing reference does not refuse it — the book and number "
      "already say where it is",
      q.sourced_hadith({**said, "reference": ""}, "كتاب"), True)

print("\nThe grading is read, never decided here")
check("a list of grade objects yields the first grade as written",
      q._grade_from({"grades": [{"name": "x", "grade": "صحيح"}]}), "صحيح")
check("a list of plain strings works too",
      q._grade_from({"grades": ["حسن"]}), "حسن")
check("a bare string works too", q._grade_from({"grades": "ضعيف"}), "ضعيف")
check("no grades field yields nothing — NOT a default of 'صحيح'",
      q._grade_from({}), "")
check("an empty grades list yields nothing",
      q._grade_from({"grades": []}), "")
check("a grade object with no grade in it yields nothing",
      q._grade_from({"grades": [{"name": "x"}]}), "")

print("\nA tafsir row obeys the same rule as an ayah")
note = {"sura": 2, "ayah": 255, "text": "نص"}
check("a complete tafsir row with a named work passes",
      q.sourced_tafsir(note, "عمل"), True)
check("with no work named it is refused",
      q.sourced_tafsir(note, ""), False)

print("\nAn edition is refused unless it is the whole book")
flat = {"quran": [{"chapter": 1, "verse": n, "text": "نص"}
                  for n in range(1, 8)]}
check("a flat edition is walked",
      len(q._rows_from(flat)), 7)
nested = {"data": {"surahs": [
    {"number": 1, "ayahs": [{"numberInSurah": n, "text": "نص"}
                            for n in range(1, 8)]}]}}
check("a nested edition is walked too",
      len(q._rows_from(nested)), 7)
check("a shape this file does not know yields nothing, "
      "rather than a guess",
      q._rows_from({"verses": [{"id": 1, "t": "نص"}]}), [])
check("a flat edition with a broken row yields nothing at all",
      q._rows_from({"quran": [{"chapter": 1, "verse": 1, "text": "نص"},
                              {"chapter": 1, "text": "نص"}]}), [])
check("the whole book is 6236 ayat", q.WHOLE_QURAN, 6236)


class Answer:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


class Source:
    """Stands in for the network, which this machine cannot reach."""

    def __init__(self, *answers):
        self.answers, self.asked = list(answers), 0

    def get(self, url, **kw):
        answer = self.answers[min(self.asked, len(self.answers) - 1)]
        self.asked += 1
        if isinstance(answer, Exception):
            raise answer
        return answer


whole = {"quran": [{"chapter": 1, "verse": n, "text": "نص"}
                   for n in range(1, q.WHOLE_QURAN + 1)]}
short = {"quran": [{"chapter": 1, "verse": n, "text": "نص"}
                   for n in range(1, 100)]}

print("\nWhich edition is used, and when none is")
name, rows = q.the_quran(Source(Answer(200, whole)))
check("a complete edition is taken, and named", (bool(name), len(rows)),
      (True, q.WHOLE_QURAN))
name, rows = q.the_quran(Source(Answer(200, short)))
check("a SHORT edition is refused outright — every one of them",
      (name, rows), ("", []))
name, rows = q.the_quran(Source(Answer(404, {})))
check("an edition that 404s is refused", (name, rows), ("", []))
name, rows = q.the_quran(Source(RuntimeError("no network")))
check("an unreachable edition is refused, not retried into a guess",
      (name, rows), ("", []))
name, rows = q.the_quran(Source(Answer(500, {}), Answer(200, whole)))
check("a failed first edition falls through to the next",
      (bool(name), len(rows)), (True, q.WHOLE_QURAN))

print("\nAn edition carrying no gradings at all is refused whole")


class Book:
    def __init__(self, *answers):
        self.answers, self.asked = list(answers), 0

    def get(self, url, **kw):
        answer = self.answers[min(self.asked, len(self.answers) - 1)]
        self.asked += 1
        return answer


ungraded = Answer(200, {"hadiths": [
    {"text": "نص", "hadithnumber": n, "reference": "r", "grades": []}
    for n in range(1, 43)]})
graded = Answer(200, {"hadiths": [
    {"text": "نص", "hadithnumber": n, "reference": "r",
     "grades": [{"name": "x", "grade": "درجة"}]} for n in range(1, 43)]})
book, rows = q.the_hadith(Book(ungraded))
check("every edition ungraded means no hadith at all — not a board "
      "refused one row at a time",
      (book, rows), ("", []))
book, rows = q.the_hadith(Book(ungraded, graded))
check("an ungraded edition falls through to a graded one",
      (bool(book), len(rows)), (True, 42))
mixed = Answer(200, {"hadiths": [
    {"text": "نص", "hadithnumber": 1, "grades": [{"grade": "درجة"}]},
    {"text": "نص", "hadithnumber": 2, "grades": []}]})
book, rows = q.the_hadith(Book(mixed))
check("and a part-graded edition keeps only the graded rows",
      len(rows), 1)

print("\nA title is shortened at a word, never through one")
import unicodedata as _u
LONG = "\u0643\u0644\u0645\u0629 " * 40          # "kalima " forty times
check("a short line is left alone",
      q.to_the_last_whole_word("\u0643\u0644\u0645\u0629", 60),
      "\u0643\u0644\u0645\u0629")
short = q.to_the_last_whole_word(LONG, 60)
check("a long one is shortened", len(short) <= 61, True)
check("and it ends on a word, not inside one",
      short.rstrip("\u2026").endswith("\u0629"), True)

# A WHOLE WORD KEEPS ITS LAST VOWEL. The first version of this helper
# stripped every trailing combining mark, and in vocalised Arabic that
# is the harakah of a perfectly good final word — so it tidied correct
# text into incorrect text. Only a cut that lands INSIDE a word leaves
# marks with nothing to sit on.
DAMMATAN = "\u064c"
KALIMA = "\u0643\u0644\u0645\u0629"
marked = (KALIMA + DAMMATAN + " ") * 30
out = q.to_the_last_whole_word(marked, 40).rstrip("\u2026").rstrip()
check("a complete word keeps the vowel it ends on",
      bool(out) and _u.combining(out[-1]) > 0, True)
check("and the cut fell on a word boundary, not inside one",
      out.endswith(KALIMA + DAMMATAN), True)
# One word longer than the room has no boundary to fall on, and the
# marks past the cut really have lost their letter.
lone = (KALIMA + DAMMATAN) * 10
solo = q.to_the_last_whole_word(lone, 15).rstrip("\u2026")
check("but a cut inside a lone word drops the orphaned marks",
      bool(solo) and _u.combining(solo[-1]) == 0, True)
check("nothing is appended when nothing was removed",
      "\u2026" not in q.to_the_last_whole_word("\u0643\u0644\u0645\u0629", 60),
      True)
check("a single word longer than the room still yields something",
      bool(q.to_the_last_whole_word("\u0643" * 80, 20)), True)

print("\nEvery programme carries the board the screen gate reads")
import re as _re
_src = open("quran_epg.py", encoding="utf-8").read()
check("the guide writer passes an icon through to add_programme",
      "icon=icon" in _src, True)
check("and the icon is a board of THIS screen",
      bool(_re.search(r'RAW_BOARD\s*=.*BOARD_PREFIX', _src, _re.S)), True)
check("the board it names is the day's FIRST, not any board of it",
      "RAW_BOARD.format(n=first_board)" in _src, True)
check("and first_board is taken before that day's boards are drawn",
      bool(_re.search(r"for day in days:\s*\n\s*first_board = board",
                      _src)), True)

print("\nThe same day gives the same ayah, on every machine")
from datetime import date
rows = [{"sura": 1, "ayah": n, "text": "نص"} for n in range(1, 6237)]
one = q.the_days_reading(rows, date(2026, 9, 10))
check("twice on one day is the same reading",
      q.the_days_reading(rows, date(2026, 9, 10)), one)
check("and the next day is a different one",
      q.the_days_reading(rows, date(2026, 9, 11)) != one, True)

print("\nall quran guards hold" if not FAILED
      else f"\n{FAILED} guard(s) did not hold")
sys.exit(1 if FAILED else 0)
