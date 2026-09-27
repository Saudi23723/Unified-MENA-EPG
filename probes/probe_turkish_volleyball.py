#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round two: the Turkish broadcasters, where these competitions actually air.

Round one ruled out the easy answers. The listings site channel 2 reads has
no volleyball and no handball page — both 404, against a basketball control
that answers 200 with five rows. The confederations publish calendars their
HTML does not contain: CEV, EuroVolley, Volleyball World and the EHF all
render in JavaScript and carry nought instants between them, and the IHF's
sixteen are a calendar with no broadcaster beside them.

One lead survived. Spor Ekranı's page says "voleybol" 146 times and
"hentbol" 42, and two of the three its ld+json exposes are Bulgaristan -
Kuzey Makedonya and Romanya - Letonya — international volleyball, which is
what was asked for. But the ld+json holds 78 broadcasts where the page
holds hundreds, and those three name no channel.

So the rows are in the HTML rather than the structured block, and this
asks the question that decides everything: does the MARKUP around a
volleyball row carry a channel and an instant, or only Turkish prose? A
channel picked out of prose is the guess this project has been burned by,
and spor_ekrani.py already refuses it by name.

Beside it, the two Turkish schedules this repository already reads for
tabii, and S Sport, which the reader named.

Measurement only: nothing here writes to any guide.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402
from epg_lib import new_session, fetch, norm                   # noqa: E402

SPOREKRANI = "https://www.sporekrani.com/"
OTHERS = (
    ("TRT Spor / tabii", "https://www.trtspor.com.tr/yayin-akisi/tabii-spor"),
    ("tvyayinakisi tabii", "https://www.tvyayinakisi.com/tabii-spor-yayin-akisi/"),
    ("S Sport schedule", "https://www.ssport.com.tr/yayin-akisi"),
    ("S Sport plus", "https://www.ssportplus.com/yayin-akisi"),
    ("tvyayinakisi s sport", "https://www.tvyayinakisi.com/s-sport-yayin-akisi/"),
    ("tvyayinakisi s sport 2", "https://www.tvyayinakisi.com/s-sport-2-yayin-akisi/"),
)

SPORT = re.compile(r"voleybol|hentbol", re.I)
A_CLOCK = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def line(text=""):
    print(text, flush=True)


def rule(text):
    line()
    line("=" * 74)
    line(text)
    line("=" * 74)


def get(session, url):
    try:
        got = fetch(session, url)
    except Exception as exc:                                   # noqa: BLE001
        return None, str(exc)
    if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
        got.encoding = "utf-8"
    return got, None


def the_markup_around_the_sport(session):
    rule("SPOR EKRANI — what the markup around a volleyball row holds")
    got, why = get(session, SPOREKRANI)
    if got is None:
        line(f"unreachable — {why}")
        return
    soup = BeautifulSoup(got.text, "html.parser")

    # every element whose OWN text names the sport, smallest first
    hits = [el for el in soup.find_all(True)
            if el.string and SPORT.search(el.string)]
    line(f"elements whose own text names voleybol/hentbol: {len(hits)}")

    shown = 0
    seen_rows = set()
    for el in hits:
        row = el
        for _ in range(6):                 # climb to the row that holds it
            if row.parent is None:
                break
            row = row.parent
            text = norm(row.get_text(" ", strip=True))
            if len(text) > 40:
                break
        key = id(row)
        if key in seen_rows:
            continue
        seen_rows.add(key)
        text = norm(row.get_text(" ", strip=True))
        clock = A_CLOCK.search(text)
        stamp = row.find("time")
        links = [norm(a.get_text(" ", strip=True))
                 for a in row.find_all("a")][:6]
        line()
        line(f"  <{row.name} class={row.get('class')}>")
        line(f"    text  : {text[:150]}")
        line(f"    clock : {clock.group(0) if clock else 'none'}   "
             f"<time>: {stamp.get('datetime') if stamp else 'none'}")
        line(f"    links : {links}")
        shown += 1
        if shown >= 8:
            break

    line()
    line(f"rows shown: {shown}")
    # is a channel logo/name near these rows at all?
    imgs = [i.get("alt") or i.get("title") or ""
            for i in soup.find_all("img")]
    named = [a for a in imgs if a and len(a) < 40]
    line(f"img alt/title values on the page (first 25): {named[:25]}")


def the_other_schedules(session):
    rule("THE TURKISH SCHEDULES — tabii's two, and S Sport as named")
    for who, url in OTHERS:
        got, why = get(session, url)
        if got is None:
            line(f"{who:24} unreachable — {why[:60]}")
            continue
        page = got.text
        soup = BeautifulSoup(page, "html.parser")
        hits = SPORT.findall(page)
        line(f"{who:24} {got.status_code}  {len(page):>9,} bytes   "
             f"voleybol/hentbol: {len(hits)}")
        line(f"     <time>: {len(soup.find_all('time'))}   "
             f"rows: {len(soup.find_all('tr'))}   "
             f"ld+json: {len(soup.find_all('script', type='application/ld+json'))}")
        if hits:
            for el in soup.find_all(True):
                if el.string and SPORT.search(el.string):
                    row = el.parent if el.parent is not None else el
                    text = norm(row.get_text(" ", strip=True))
                    clock = A_CLOCK.search(text)
                    line(f"     e.g. {clock.group(0) if clock else '--:--'}  "
                         f"{text[:110]}")
                    break
        line()


def main() -> int:
    session = new_session()
    the_markup_around_the_sport(session)
    the_other_schedules(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
