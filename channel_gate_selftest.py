#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Every gate that decides "this match is on MY channel", attacked.

On 28 August this guide published Liverpool - Nottingham, Al Wasl -
Shabab Al Ahli, Tottenham - Newcastle and Gençlerbirligi - Erzurumspor on
ON Time Sports, an Egyptian channel that carries none of them. The times
were right; the broadcasts were invented.

The cause was one function reading a number before a name:

    AD Sports 1        -> ONSport1
    beIN Sports 1      -> ONSport1
    beIN Sports MAX 1  -> ONSportMAX
    TNT Sports 1       -> ONSport1
    Sky Sports Plus    -> ONSportPLUS

It had been correct for months, because it had only ever been shown
labels from ON Sport's own pages. It broke the day it was handed
livefootballtv's front page, which lists every channel in the world
against every match. Nothing tested it against that input, so nothing
caught it until a viewer saw Liverpool on an Egyptian channel.

This file is that test. Every guide that takes a broadcaster's name from
a source and decides whether the match is one of its own is given the
same corpus of real channel names — its own, which it must accept, and
forty foreign ones, which it must refuse. It runs in CI on every push.

A guide that invents a broadcast is worse than one that admits it does
not know. A viewer who trusts an empty row loses nothing; a viewer who
trusts an invented one turns on the television and finds something else,
and stops believing the rest of the guide.

Adding a channel means adding it here. Loosening a gate means this goes
red, which is the point.
"""

from __future__ import annotations

import sys

FAILURES: list[str] = []


def check(gate: str, label: str, got, want) -> None:
    ok = got == want
    if not ok:
        FAILURES.append(f"{gate}: {label!r} -> {got!r}, expected {want!r}")
    print(f"  {'ok  ' if ok else 'FAIL'} {label:34} -> {str(got):14} "
          f"{'' if ok else 'expected ' + str(want)}")


# Real channel names, none of them belonging to any guide here. Kept in
# one list so every gate is attacked with the same corpus, and so adding
# a name that once slipped through protects every guide at once.
# The same foreign channels an Arabic page would print them as. A gate
# taught only Latin names refuses these by accident, not by design, and
# will keep refusing them right up until it does not.
FOREIGN_AR = [
    "بي ان سبورت 1", "بي إن سبورت 2", "بين سبورت ماكس 1",
    "أبوظبي الرياضية 1", "أبو ظبي الرياضية 2", "دبي الرياضية",
    "الشارقة الرياضية", "السعودية الرياضية 1", "الكأس 1", "ثمانية 1",
    "قناة الرياضية السعودية", "الكويت الرياضية", "عمان الرياضية",
]

FOREIGN = [
    "beIN Sports 1", "beIN Sports 2", "beIN Sports MAX 1", "beIN Sports MAX 2",
    "beIN Sports XTRA 1", "AD Sports 1", "AD Sports 2", "AD Sports Premium 1",
    "Abu Dhabi Sports 1", "Dubai Sports 1", "Dubai Sports 2", "Sharjah Sports",
    "SSC 1", "SSC 2", "SSC Extra 1", "Thmanyah 1", "Thmanyah 2",
    "Alkass One", "Alkass Two", "Alkass Three",
    "TNT Sports 1", "TNT Sports 2", "Sky Sports Main Event",
    "Sky Sports Premier League", "Sky Sports Plus", "Sky Sport 1",
    "Canal+ Sport", "Canal+ Foot", "DAZN 1", "DAZN 2",
    "Movistar Plus+", "Movistar Liga de Campeones 1",
    "Sport TV 1", "Sport TV 2", "Eleven Sports 1",
    "ESPN 1", "ESPN 2", "Fox Sports 1", "Fox Sports 2",
    "MBC Sports+", "Star Sports 1", "Astro SuperSport 1",
    "SuperSport Premier League", "Arena Sport 1", "Nova Sports 1",
    "Digi Sport 1", "Match TV", "Ziggo Sport Select",
    "S Sport 1", "Tivibu Spor 1", "beIN Sports Türkiye 1",
    "Idman TV", "Varzish Sport", "Football HD",
]


def gate_onsport() -> None:
    print("\nON Sport — onsport_channel_from_label")
    import update_onsport_epg as m
    mine = [
        ("ON Sport", "ONSport1"),
        ("On Sport 1", "ONSport1"),
        ("ON Time Sports 1", "ONSport1"),
        ("On Sport 2", "ONSport2"),
        ("ON Time Sports 2", "ONSport2"),
        ("On Sport Max", "ONSportMAX"),
        ("ON Time Sports Max", "ONSportMAX"),
        ("On Sport Plus", "ONSportPLUS"),
        ("أون سبورت", "ONSport1"),
        ("أون سبورت ماكس", "ONSportMAX"),
        ("اون سبورت 2", "ONSport2"),
    ]
    for label, want in mine:
        check("ON Sport", label, m.onsport_channel_from_label(label), want)
    print("  -- foreign channels, in both scripts, every one refused --")
    every = FOREIGN + FOREIGN_AR
    for label in every:
        got = m.onsport_channel_from_label(label)
        if got is not None:
            check("ON Sport", label, got, None)
    print(f"  {len(every)} foreign labels offered, "
          f"{sum(m.onsport_channel_from_label(x) is not None for x in every)} accepted")


def gate_jordan() -> None:
    print("\nJordan Sports — _lftv_row_names_channel")
    from bs4 import BeautifulSoup
    import JORDAN_SPORTS_FINAL_VERIFIED as m

    def row(*channels: str):
        lis = "".join(f'<li title="{c}">{c}</li>' for c in channels)
        html = (f'<tr><td class="canales"><div id="ev"></div>'
                f'<ul class="listaCanales">{lis}</ul></td></tr>')
        return BeautifulSoup(html, "html.parser").find(id="ev")

    # Its own name in every spelling a source might print, including the
    # Arabic one. This gate once accepted the literal "jordan sports" and
    # nothing else, so an Arabic page would have emptied the guide in
    # silence.
    for label in ("Jordan Sports", "Jordan Sport", "JRTV Sports",
                  "الأردن الرياضية", "الاردن الرياضية",
                  "الرياضية الأردنية"):
        check("Jordan", label, m._lftv_row_names_channel(row(label)), True)
    check("Jordan", "Jordan Sports beside beIN",
          m._lftv_row_names_channel(row("beIN Sports 1", "Jordan Sports")), True)

    print("  -- foreign channels, in both scripts, every one refused --")
    every = FOREIGN + FOREIGN_AR
    leaked = 0
    for label in every:
        if m._lftv_row_names_channel(row(label)):
            check("Jordan", label, True, False)
            leaked += 1
    # and the whole foreign list at once, as a real row would carry it
    if m._lftv_row_names_channel(row(*every)):
        check("Jordan", "<all foreign at once>", True, False)
        leaked += 1
    print(f"  {len(every)} foreign labels offered, {leaked} accepted")


def gate_shahid() -> None:
    print("\nShahid — SHAHID_RE")
    import update_shahid_sports_epg as m
    for label in ("MBC Shahid Sports", "Shahid", "Shahid VIP", "Shahid Sports",
                  "شاهد", "شاهد سبورت", "MBC Sport"):
        check("Shahid", label, bool(m.SHAHID_RE.search(label)), True)
    print("  -- foreign channels, in both scripts, every one refused --")
    every = FOREIGN + FOREIGN_AR
    leaked = []
    for label in every:
        if m.SHAHID_RE.search(label):
            leaked.append(label)
            check("Shahid", label, True, False)
    print(f"  {len(every)} foreign labels offered, {len(leaked)} accepted")


def gate_not_a_team() -> None:
    """A date or a competition is not a club — in either language.

    Every guide that reads a fixture out of prose has to tell a team from
    a heading, and each had learned that in one language only. Shahid
    rejected "أغسطس" and published "August"; rejected "الجولة 2" and
    published "Round 2"; rejected "الدوري الفرنسي" and published "Premier
    League"; and, the other way about, rejected "Monday" while publishing
    "الاثنين". Nine such pairs.
    """
    print("\nHeadings and dates — NOT_A_TEAM_NAME, both scripts")
    from epg_lib import is_not_a_team as NOT_A_TEAM

    pairs = [
        ("August", "أغسطس"), ("September", "سبتمبر"), ("Aug", "آب"),
        ("Monday", "الاثنين"), ("Friday", "الجمعة"), ("Sun", "الأحد"),
        ("Premier League", "الدوري الإنجليزي"),
        ("Round 2", "الجولة 2"), ("Matchweek 2", "الأسبوع الثاني"),
        ("Semi-final", "نصف النهائي"), ("Quarter Final", "ربع النهائي"),
        ("Group A", "المجموعة الأولى"), ("Friendly", "ودية"),
        ("Qualifiers", "تصفيات"), ("Super Cup", "كأس السوبر"),
        ("Coppa Italia", "بطولة الكأس"), ("Serie A", "الدوري السعودي الممتاز"),
    ]
    asymmetric = [(en, ar) for en, ar in pairs
                  if NOT_A_TEAM(en) != NOT_A_TEAM(ar)]
    missed = [x for pair in pairs for x in pair if not NOT_A_TEAM(x)]
    if asymmetric or missed:
        print(f"       asymmetric pairs: {asymmetric[:4]}")
        print(f"       let through     : {missed[:6]}")
    check("NOT_A_TEAM", f"{len(pairs)} pairs rejected in both scripts",
          not asymmetric and not missed, True)

    # And the direction that matters more: never refuse a real club.
    clubs = [
        "Bayern München", "Borussia M'gladbach", "Eintracht Frankfurt",
        "Cremonese", "Sassuolo", "Hamburger SV", "Schalke 04", "Mainz 05",
        "Al Sahel", "Kazma", "Al Sulaibikhat", "Al Tadhamon", "Al Qadsia",
        "Al Arabi SC", "Al Salmiyah", "Al Fahaheel", "Al Nasar",
        "الأهلي", "الزمالك", "الاتحاد السكندري", "سيراميكا كليوباترا",
        "إنبي", "وادي دجلة", "القناة", "الجونة", "زد",
        "الأهلي السعودي", "النصر السعودي", "الهلال", "الاتحاد", "الشباب",
        "الوحدة", "الرياض", "نادي قطر", "السد", "الوصل", "شباب الأهلي",
        "الجزيرة", "عجمان", "الفيصلي", "الوحدات", "الرمثا",
        "Real Madrid", "Atl. Madrid", "Rayo Vallecano", "Sporting Lisbon",
        "Galatasaray", "Gençlerbirligi", "Erzurumspor", "Nottingham",
        "Aston Villa", "Sheffield Utd", "West Brom", "Khor Fakkan",
        "Ceramica Cleopatra FC", "ENPPI Club", "El Gouna FC", "ZED FC",
    ]
    caught = [c for c in clubs if NOT_A_TEAM(c)]
    if caught:
        print(f"       real clubs wrongly refused: {caught}")
    check("NOT_A_TEAM", f"none of {len(clubs)} real clubs refused",
          not caught, True)

    # And the half that is kept rather than dropped: a competition must be
    # recognisable as one, so the guide can show which league a match
    # belongs to instead of silently discarding the line that said so.
    from epg_lib import COMPETITION_NAME, DATE_WORD
    comps = ["الدوري الألماني", "الجولة 2", "Bundesliga", "Matchday 2",
             "Premier League", "Coppa Italia", "نصف النهائي", "Semi-final",
             "كأس السوبر", "Super Cup", "الأسبوع الثاني", "Gameweek 3"]
    dates = ["أغسطس", "August", "الاثنين", "Monday", "آب", "Sep"]
    check("COMPETITION", f"{len(comps)} competitions recognised, both scripts",
          all(COMPETITION_NAME.search(c) for c in comps), True)
    check("COMPETITION", "a date is never mistaken for a competition",
          not any(COMPETITION_NAME.search(d) for d in dates), True)
    check("COMPETITION", "a club is never mistaken for a competition",
          not any(COMPETITION_NAME.search(c) or DATE_WORD.search(c)
                  for c in clubs), True)


def main() -> int:
    print("CHANNEL GATES | every guide must refuse other broadcasters' channels")
    for gate in (gate_onsport, gate_jordan, gate_shahid, gate_not_a_team):
        try:
            gate()
        except Exception as exc:
            FAILURES.append(f"{gate.__name__} could not run: {exc}")
            print(f"  FAIL {gate.__name__} could not run: {exc}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} gate(s) let something through:\n")
        for f in FAILURES:
            print(f"  {f}")
        print("\nA guide that publishes another channel's match is worse than "
              "one that publishes nothing. Fix the gate, do not widen the test.")
        return 1
    print("every gate holds: each guide accepts its own channels in both "
          "scripts, refuses every foreign one, and no real club is mistaken "
          "for a heading")
    return 0


if __name__ == "__main__":
    sys.exit(main())
