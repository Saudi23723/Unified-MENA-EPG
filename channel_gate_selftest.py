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

import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

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


def gate_channel_is_never_a_team() -> None:
    """A channel name may never be published where a club belongs.

    LiveFootballTV lists every channel carrying a match on the same lines
    as the two teams. A parser that takes "the last two plausible names"
    off that block reaches for a channel the moment a page lists one more
    channel than usual, and that is not hypothetical: this repository
    published

        ⏰ Eintracht Frankfurt - MBC Action + …

    MBC Action being a television channel and not a football club. Only
    "MBC Sport" had been taught to the filter, so every other channel in
    the world was a candidate opponent.

    So the gate is by name, in one place, for every guide at once — the
    same lesson as ON Sport, where feeding a world channel list into a
    number-first matcher put Liverpool on an Egyptian channel.
    """
    print("\nChannels are never clubs — CHANNEL_NAME")
    from epg_lib import is_channel_name, is_not_a_team

    channels = [
        "MBC Action", "MBC Shahid Sports", "MBC 1", "MBC Masr",
        "beIN Sports 1", "beIN SPORTS MAX 2", "بي إن سبورت",
        "ON Time Sports 2", "أون تايم سبورت", "ON Sport 1",
        "SSC 1", "SSC Sports", "Shahid VIP", "StarzPlay", "TOD",
        "tabii Spor 1", "Thmanyah 1", "Alkass One", "قناة الكأس",
        "Dubai Sports 1", "Abu Dhabi Sports 2", "AD Sports Premium",
        "DAZN", "ESPN", "Sky Sports Main Event", "TNT Sports 1",
        "Canal+ Sport", "Movistar LaLiga", "Prime Video", "Apple TV",
        "SuperSport Football", "Sport TV1", "Eleven Sports 2",
        "Viaplay Sports 1", "Nova Sports", "Arena Sport 1",
        "Digi Sport 2", "Match TV", "Fox Sports 1", "CBS Sports Network",
        "NBC Sports", "Peacock", "Paramount+", "RMC Sport 1",
        "S Sport Plus", "Idman TV", "Varzish TV", "TRT Spor",
        "Tivibu Spor 3", "Roya TV", "JRTV Sports", "الأردن الرياضية",
        "Football HD", "Sport 1 HD", "Sports HD", "beIN 4K", "TV 4K",
        "دبي الرياضية", "أبو ظبي الرياضية",
    ]
    leaked = [c for c in channels if not is_channel_name(c)]
    if leaked:
        print(f"       accepted as a club: {leaked}")
    check("CHANNEL", f"{len(channels)} channel names refused", not leaked, True)

    # is_not_a_team is what the guides actually call, so the gate has to
    # reach them through it, not only through its own regex.
    unreached = [c for c in channels if not is_not_a_team(c)]
    check("CHANNEL", "and every guide sees it through is_not_a_team",
          not unreached, True)

    # The direction that matters more: a club whose name merely brushes
    # against broadcast vocabulary must still be a club.
    clubs = [
        "Sporting CP", "Sporting Lisbon", "Sport Boys", "Sport Recife",
        "Sportivo Luqueño", "Deportivo Alavés", "Eintracht Frankfurt",
        # Real clubs carrying a word that also marks a channel. "Ulsan HD
        # FC" is Korean and was refused as a team name because HD matched
        # anywhere — a lost fixture, which is the expensive direction.
        # ("Shahid Afridi" turns up in a STARZPLAY documentary title, but
        # that guide never reads a fixture out of a title, and on the
        # Shahid guide the word is the broadcaster. Left refused.)
        "Ulsan HD FC", "Ulsan HD", "Guangzhou HD",
        "Union Berlin", "Bayern München", "Stuttgart", "Real Madrid",
        "Al Sahel", "Al Arabi SC", "Kazma", "الأهلي", "الهلال", "القناة",
        "الاتحاد", "النصر السعودي", "الوحدات", "ZED FC", "ENPPI Club",
    ]
    refused = [c for c in clubs if is_channel_name(c)]
    if refused:
        print(f"       real clubs mistaken for channels: {refused}")
    check("CHANNEL", f"none of {len(clubs)} real clubs called a channel",
          not refused, True)

    # And the guides' own parsers, through their own front doors.
    import update_shahid_sports_epg as SH
    accepted = [c for c in channels if SH.looks_like_team(c)]
    if accepted:
        print(f"       Shahid would publish as a club: {accepted}")
    check("Shahid", "looks_like_team refuses every channel name",
          not accepted, True)
    dropped = [c for c in clubs if not SH.looks_like_team(c)]
    if dropped:
        print(f"       Shahid would drop real clubs: {dropped}")
    check("Shahid", "and still accepts every real club", not dropped, True)


def gate_one_match_one_row() -> None:
    """The same match may not appear twice because two sources spell it twice.

    Matches kicking off together share one row on a single-channel guide,
    joined with " + ". That is right, and it is what made a spelling
    difference visible as nonsense:

        Elversberg - Bayer Leverkusen + FC Koln - Hoffenheim
        + Köln - Hoffenheim + Mainz - Paderborn + Mainz 05 - Paderborn
        + RB Leipzig - B. Monchengladbach + RB Leipzig - Borussia M'gladbach

    Five matches printed as nine, because dedupe compared the names
    literally. This decides only whether two rows are the same match — it
    never changes a name anyone reads — so a wrong entry costs a lost
    fixture, and the second half of this gate is what keeps that honest.
    """
    print("\nOne match, one row — title_signature")
    import update_shahid_sports_epg as SH

    same = [
        ("FC Koln - Hoffenheim", "Köln - Hoffenheim"),
        ("Mainz - Paderborn", "Mainz 05 - Paderborn"),
        ("RB Leipzig - B. Monchengladbach",
         "RB Leipzig - Borussia M'gladbach"),
        ("Bayern Munich - Stuttgart", "Bayern München - Stuttgart"),
        ("Union Berlin - Schalke 04", "Union Berlin - Schalke"),
        ("Union Berlin - Eintracht Frankfurt", "Union Berlin - Frankfurt"),
        ("Hamburger SV - Mainz 05", "Hamburg - Mainz"),
        ("Hoffenheim - Borussia Dortmund", "1899 Hoffenheim - Dortmund"),
        ("Bayer 04 Leverkusen - Union Berlin",
         "Bayer Leverkusen - Union Berlin"),
    ]
    split = [(a, b) for a, b in same
             if SH.title_signature(a) != SH.title_signature(b)]
    if split:
        print(f"       still counted as two matches: {split[:3]}")
    check("DEDUPE", f"{len(same)} spellings of one match collapse",
          not split, True)

    # The direction that costs a fixture: two different matches must never
    # collapse into one, so every distinct club needs a distinct signature.
    clubs = [
        "Bayern München", "Borussia Dortmund", "Borussia M'gladbach",
        "Union Berlin", "Eintracht Frankfurt", "Schalke 04", "Mainz 05",
        "Hoffenheim", "Köln", "Bayer Leverkusen", "RB Leipzig", "Stuttgart",
        "Werder Bremen", "Freiburg", "Augsburg", "Hamburger SV",
        "Elversberg", "Paderborn", "Heidenheim", "St. Pauli",
        "Inter", "Milan", "Juventus", "Roma", "Lazio", "Napoli", "Torino",
        "Monza", "Parma", "Como", "Genoa", "Lecce", "Cagliari", "Verona",
        "Udinese", "Venezia", "Frosinone", "Sassuolo", "Atalanta",
        "Bologna", "Fiorentina", "Cremonese", "Palermo", "Mantova",
        "Al Sahel", "Al Sulaibikhat", "Kazma", "Al Tadhamon", "Al Qadsia",
        "Al Arabi SC", "Al Salmiyah", "Al Fahaheel", "Al Nasar",
        "Al Kuwait", "Al Jahra", "Al Shabab",
        "الأهلي", "الزمالك", "الهلال", "النصر", "الاتحاد", "الشباب",
    ]
    seen: dict[str, str] = {}
    collisions = []
    for club in clubs:
        key = SH.normalize_name(club)
        if key in seen:
            collisions.append((seen[key], club))
        seen[key] = club
    if collisions:
        print(f"       two clubs share one signature: {collisions}")
    check("DEDUPE", f"all {len(clubs)} clubs keep distinct signatures",
          not collisions, True)

    # And a whole slot, the way it was published.
    titles = ["Elversberg - Bayer Leverkusen", "FC Koln - Hoffenheim",
              "Köln - Hoffenheim", "Mainz - Paderborn",
              "Mainz 05 - Paderborn", "RB Leipzig - B. Monchengladbach",
              "RB Leipzig - Borussia M'gladbach",
              "Union Berlin - Eintracht Frankfurt"]
    distinct = {SH.title_signature(t) for t in titles}
    if len(distinct) != 5:
        print(f"       the slot collapses to {len(distinct)} matches, not 5")
    check("DEDUPE", "the published slot of 8 rows is 5 matches",
          len(distinct) == 5, True)


def gate_one_club_across_two_scripts() -> None:
    """One club written in two scripts is one club — and two are still two.

    Sources disagree on script, so a slot carried the same match twice:

        Union Berlin - Eintracht Frankfurt
        + أونيون برلين - أينتراخت فرانكفورت

    A table of club names in both scripts would answer this and would have
    to grow to every club in the world. The alphabet is the smaller unit:
    Arabic sports writing transliterates a foreign club sound by sound.

    The risk runs the other way. A fuzzy name match is unsafe inside one
    script at any threshold that still catches real duplicates — measured,
    "Mainz"/"Monza", "Al Nassr"/"Al Nasar" and "الهلال"/"الأهلي" all score
    at or above it. So the match is cross-script only, and this gate is
    weighted towards proving that different clubs stay different: losing a
    fixture is worse than printing one twice.
    """
    print("\nOne club in two scripts — same_club")
    from epg_lib import merge_transliterations, same_club, same_fixture

    same = [
        ("Union Berlin", "أونيون برلين"),
        ("Eintracht Frankfurt", "أينتراخت فرانكفورت"),
        ("Elversberg", "إلفيرسبيرج"),
        ("Bayer Leverkusen", "باير ليفركوزن"),
        ("Köln", "كولن"), ("Hoffenheim", "هوفنهايم"),
        ("Paderborn", "بادربورن"), ("Mainz", "ماينتس"), ("Mainz", "ماينز"),
        ("Stuttgart", "شتوتغارت"), ("Napoli", "نابولي"), ("Milan", "ميلان"),
        ("Roma", "روما"), ("Real Madrid", "ريال مدريد"),
        ("Liverpool", "ليفربول"), ("Porto", "بورتو"), ("Ajax", "أياكس"),
        ("Al Ahly", "الأهلي"), ("RB Leipzig", "لايبزيج"),
        # The affix sits at either end: "FC Köln" but "Hamburger SV",
        # and stripping only the front left this pair as two clubs while
        # the guide printed the match twice.
        ("Hamburger SV", "هامبورج"), ("Borussia Dortmund", "بوروسيا دورتموند"),
        ("Werder Bremen", "فيردر بريمن"), ("Augsburg", "أوجسبورج"),
        ("Freiburg", "فرايبورج"),
    ]
    missed = [(a, b) for a, b in same if not same_club(a, b)]
    if missed:
        print(f"       not recognised as one club: {missed[:4]}")
    check("TRANSLIT", f"{len(same) - len(missed)}/{len(same)} cross-script "
                      f"spellings recognised", not missed, True)

    # The direction that costs a fixture. Every pair here is two genuinely
    # different clubs, written one in each script.
    different = [
        ("Al Hilal", "الأهلي"), ("Al Ahly", "الهلال"), ("Al Nassr", "النجمة"),
        ("Mainz", "مونزا"), ("Monza", "ماينتس"), ("Köln", "كيل"),
        ("Torino", "تورونتو"), ("Parma", "باليرمو"),
        ("Cagliari", "كالياري ستي"), ("Inter", "إنتراخت"),
        ("Milan", "ميلانو سيتي"), ("Roma", "رومانيا"),
        ("Genoa", "جنوة الثاني"), ("Real Madrid", "ريال بيتيس"),
        ("Union Berlin", "يونيون سانت جيلواز"),
        ("Bayern Munich", "باير ليفركوزن"), ("Leipzig", "ليفركوزن"),
        ("Frosinone", "فيورنتينا"), ("Sassuolo", "ساليرنيتانا"),
        ("Atalanta", "أتلانتا يونايتد"), ("Bologna", "برشلونة"),
        ("Manchester United", "مانشستر سيتي"),
        ("Al Sahel", "الساحل الثاني"), ("Napoli", "نابولي الثاني"),
        ("Leipzig", "لايبزيا الثاني"), ("Genoa", "جنوى يونايتد"),
        ("Juventus", "يوفنتوس الثاني"), ("Freiburg", "فرايبورج الثاني"),
        ("Augsburg", "أوجسبورج الثاني"), ("Hamburger SV", "هامبورج الثاني"),
        ("Werder Bremen", "بريمن سيتي"), ("Dortmund", "دورتموند الثاني"),
        ("Verona", "فيرونتينا"), ("Lecce", "ليتشي الثاني"),
    ]
    merged = [(a, b) for a, b in different if same_club(a, b)]
    if merged:
        print(f"       two clubs merged into one: {merged}")
    check("TRANSLIT", f"none of {len(different)} different clubs merged",
          not merged, True)

    # A measured limit, recorded rather than papered over. Latin writes the
    # short vowels of "Al Hilal"; Arabic does not write them in "الهلال",
    # so the two skeletons differ by one slot and fall under the floor.
    #
    # Deleting vowels instead would match this pair and seven others — and
    # it also merges "Al Hilal" with "الأهلي", and "Mainz" with "مونزا":
    # measured over the corpus above, 26 of 28 recognised at the cost of
    # four different clubs collapsed into one. Four lost fixtures to gain
    # eight cosmetic merges is the wrong trade, so the vowel stays and this
    # pair goes unmatched on purpose.
    #
    # It costs little in practice: both sources write an Arab club in
    # Arabic, so the cross-script pair barely arises for these names.
    limits = [("Al Hilal", "الهلال"), ("Al Nassr", "النصر"),
              ("Zamalek", "الزمالك")]
    surprising = [(a, b) for a, b in limits if same_club(a, b)]
    check("TRANSLIT", f"{len(limits)} known short-name limits, still safe",
          not surprising, True)

    # Within one script this must never fire, however alike the names —
    # that is what keeps "Mainz"/"Monza" and "الهلال"/"الأهلي" apart.
    inside = [("Mainz", "Monza"), ("Al Nassr", "Al Nasar"),
              ("Torino", "Toronto"), ("Köln", "Kiel"),
              ("الهلال", "الأهلي"), ("الزمالك", "الزوراء"),
              ("Parma", "Palermo"), ("Cagliari", "Calgary")]
    fired = [(a, b) for a, b in inside if same_club(a, b)]
    check("TRANSLIT", "never fires inside one script", not fired, True)

    # Both sides must agree before a fixture is called a duplicate.
    check("TRANSLIT", "one side agreeing is not enough",
          not same_fixture("Union Berlin - Hoffenheim",
                           "أونيون برلين - بادربورن"), True)

    # And the slot exactly as it was published.
    slot = ["Elversberg - Bayer Leverkusen", "Köln - Hoffenheim",
            "Mainz 05 - Paderborn", "Union Berlin - Eintracht Frankfurt",
            "أونيون برلين - أينتراخت فرانكفورت", "إلفيرسبيرج - باير ليفركوزن",
            "كولن - هوفنهايم", "ماينتس - بادربورن"]
    kept = merge_transliterations(slot)
    if len(kept) != 4:
        print(f"       slot collapsed to {len(kept)}: {kept}")
    check("TRANSLIT", "the published slot of 8 rows is 4 matches",
          len(kept) == 4, True)
    check("TRANSLIT", "and it keeps the first spelling, not the shortest",
          kept and kept[0] == "Elversberg - Bayer Leverkusen", True)


def gate_a_fact_survives_its_source() -> None:
    """What one source knew must not be lost because another outranked it.

    The ranking decides whose kickoff time and whose spelling to trust. It
    has no business deciding which competition a match belongs to or which
    other channels carry it — those are true or not, and the source that
    printed them is usually not the highest-ranked one.

    LiveFootballTV is the only page listing the channels and sits lowest at
    75, so every Bundesliga fixture (BundesligaOfficial, 110) threw the
    list away. The guide was taught to say "يُبث أيضًا على: MBC Action" and
    then never said it once — caught by reading the published file, not by
    reading the code.
    """
    print("\nA fact outlives the source that supplied it")
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import update_shahid_sports_epg as SH

    when = datetime(2026, 8, 29, 21, 30, tzinfo=ZoneInfo("Asia/Riyadh"))
    top = {"start": when, "title": "Union Berlin - Eintracht Frankfurt",
           "source_name": "BundesligaOfficial"}
    low = {"start": when, "title": "Union Berlin - Eintracht Frankfurt",
           "source_name": "LiveFootballTV",
           "competition": "الدوري الألماني", "channels": "MBC Action"}

    best = SH.choose_best_event([top, low])
    check("FACTS", "the higher-ranked source still wins the fixture",
          best["source_name"] == "BundesligaOfficial", True)
    check("FACTS", "the competition survives from the lower-ranked source",
          best.get("competition") == "الدوري الألماني", True)
    check("FACTS", "so do the other channels carrying it",
          best.get("channels") == "MBC Action", True)

    # And the winner's own values are never overwritten by a weaker source.
    rich = dict(top, competition="Bundesliga", channels="MBC Shahid Sports")
    kept = SH.choose_best_event([rich, low])
    check("FACTS", "a fact the winner already knew is left alone",
          kept.get("competition") == "Bundesliga"
          and kept.get("channels") == "MBC Shahid Sports", True)

    # Filling a fact must not mutate the event the caller passed in.
    check("FACTS", "the source events are not modified in place",
          "competition" not in top and "channels" not in top, True)


def gate_every_guide_is_covered() -> None:
    """Every generator's output must pass through the guarantee.

    Seven of the thirteen generators write their own file rather than
    going through write_xml_atomic, so the gap-closing that lives there
    reached barely half the guides — which is why holes kept turning up in
    channels nobody had touched. Rewriting those seven would mean editing
    guides that work, and the ones that work are the ones not to touch.

    The guarantee is applied by the orchestrator instead, to each finished
    file. This holds it there: every guide build_all_epg knows about must
    be one it also closes the gaps in, so a guide added later cannot
    quietly arrive without the protection.
    """
    print("\nEvery guide is covered — build_all_epg")
    import build_all_epg as B
    import inspect

    source = inspect.getsource(B.build_once)
    check("COVERAGE", "each generator's file has its gaps closed",
          "close_gaps_in(" in source, True)
    check("COVERAGE", "and only when this pass is really publishing it",
          "collapsed" in source and "else:" in source, True)

    # The function has to survive a file it cannot help, rather than
    # damaging it: a guide missing filler beats a guide that is malformed.
    import tempfile
    import os as _os
    with tempfile.TemporaryDirectory() as tmp:
        broken = _os.path.join(tmp, "broken.xml")
        with open(broken, "w", encoding="utf-8") as handle:
            handle.write("<tv><channel id='a'><programme")
        check("COVERAGE", "an unparsable file is left exactly as it was",
              B.close_gaps_in("x", broken) is None
              and open(broken, encoding="utf-8").read().endswith("<programme"),
              True)
        check("COVERAGE", "a missing file is not invented",
              B.close_gaps_in("x", _os.path.join(tmp, "nope.xml")) is None,
              True)

    # And every generator it lists must actually name a file.
    missing = [output for _, _, output in B.GENERATORS if not output.endswith(".xml")]
    check("COVERAGE", f"all {len(B.GENERATORS)} generators name an xml file",
          not missing, True)


def gate_the_screen_cannot_go_stale() -> None:
    """What the screen plays must be what the boards say, provably.

    A television showed yesterday's fixtures for hours after they were
    removed and the new boards published. Nothing was wrong with the
    boards. The segment file names had not changed, so every cache between
    the repository and the screen went on serving what it already held,
    and from the outside the two were indistinguishable.

    The fix was to name each segment after eight characters of its board's
    own hash, so a board that changes cannot produce a name any cache has
    seen. This gate is what stops that fix being undone by accident: it
    recomputes the hashes off the published boards and demands the
    published playlist agree with them.

    It is deliberately checked against the FILES, not against the code
    that wrote them. A guard that only reads the source proves the
    intention; this proves the result.
    """
    print("\nThe screen cannot go stale — boards, segments, playlist")
    import hashlib
    import os as _os
    import re as _re

    # AND THE PLAYLIST MUST BE LIVE, which is a different failure with the
    # same symptom and it was live on a television for weeks.
    #
    # The names were being changed correctly and the guide rebuilt every
    # ten minutes, and the screen still showed one moment's board for half
    # a day. The playlist said PLAYLIST-TYPE:VOD, kept MEDIA-SEQUENCE at 0
    # and ended with EXT-X-ENDLIST — a complete recording. RFC 8216 says
    # what a player does with one: it loads it ONCE and never asks again.
    # So the cache was not the problem the second time; the television was
    # never told to look.
    import match_screen_video as screen
    import tempfile as _tempfile

    drawn = ["/x/today_matches_0.aaaaaaaa.ts", "/x/today_matches_1.bbbbbbbb.ts"]
    written = _os.path.join(_tempfile.gettempdir(), "gate_screen.m3u8")
    screen.write_playlist(drawn, written, now=1788400000)
    live = open(written, encoding="utf-8").read()

    check("SCREEN", "no ENDLIST — that tag alone stops a player reloading",
          "EXT-X-ENDLIST" in live, False)
    check("SCREEN", "and it is not declared a finished recording",
          "PLAYLIST-TYPE:VOD" in live, False)

    # A window has to outlast the gap between builds or a player runs off
    # the end of it and waits on a blank screen.
    spans = live.count("#EXTINF:") * screen.HOLD
    check("SCREEN", "the window outlasts the ten minutes between builds",
          spans >= 20 * 60, True)

    # The sequence numbers the first segment of the window, and a player
    # uses it to tell a new window from the one it already has. Fixed at
    # zero, every rebuild looks like the last.
    screen.write_playlist(drawn, written, now=1788400000 + 600)
    after = open(written, encoding="utf-8").read()

    def sequence(text):
        return int(_re.search(r"MEDIA-SEQUENCE:(\d+)", text).group(1))

    check("SCREEN", "the sequence moves forward with the clock",
          sequence(after) - sequence(live), 600 // screen.HOLD)

    boards_dir, stream_dir = "boards", "stream"
    # BOTH screens, because there are two now and the second can go out
    # of step exactly as the first did. A gate that checks one of them
    # proves nothing about the other, and they publish into the same
    # directory from the same pass.
    for prefix, name in (("today_matches_", "screen.m3u8"),
                         ("other_sports_", "sports.m3u8")):
        one_screen(boards_dir, stream_dir, prefix, name, hashlib, _os, _re)


def one_screen(boards_dir, stream_dir, prefix, playlist_name,
               hashlib, _os, _re) -> None:
    """The boards, the segments and the playlist of ONE screen, agreeing."""
    playlist = _os.path.join(stream_dir, playlist_name)

    if not _os.path.isdir(boards_dir) or not _os.path.exists(playlist):
        # Nothing published yet is not a failure: a fresh clone has no
        # screen until the first build makes one, and the second screen
        # has none until its first pass.
        check("SCREEN", f"{prefix} nothing published yet, nothing to "
                        f"contradict", True, True)
        return

    # The boards the CHANNEL plays, in the order it plays them — which is
    # by their number and not as text, and only as many as it carries.
    # Sorting these as text is what once made a channel jump from today
    # to a week and a half ahead after two boards.
    # ...and only as many as the channel carries. The guide draws a board
    # for every day of a fourteen-day window; the channel plays the near
    # ones, because on a channel a viewer cannot scroll to the day they
    # want and a five-minute lap lands most arrivals in next week.
    import match_screen_video as video
    boards = [_os.path.basename(path)
              for path in video.boards(prefix)[:video.ON_SCREEN]]
    with open(playlist, encoding="utf-8") as handle:
        referenced = [line.strip() for line in handle
                      if line.strip().endswith(".ts")]
    distinct = sorted(set(referenced))

    check("SCREEN", f"{prefix} the playlist names one segment per board",
          len(distinct), len(boards))

    # Every reference resolves to a file that is actually published.
    missing = [name for name in distinct
               if not _os.path.exists(_os.path.join(stream_dir, name))]
    check("SCREEN", f"{prefix} every segment the playlist names exists",
          missing, [])

    # Nothing of THIS screen's published that neither its playlist nor
    # the pass before it points at. Only its own segments are considered:
    # the two screens share stream/, and each one's sweep must leave the
    # other's alone.
    #
    # THE PASS BEFORE IT COUNTS, and that is not a loophole — it is the
    # fix to the buffering. A board changes every pass because it prints
    # a countdown, so every segment is renamed every ten minutes; a
    # television holding the previous playlist (raw.githubusercontent
    # serves it with a five-minute cache) is still working through the
    # old names, and deleting those files the moment they leave the
    # playlist hands it a 404 and a spinner. One generation is kept on
    # purpose. Two would be litter, and this still says so.
    spared = _os.path.join(stream_dir, f"{prefix}keeping.txt")
    grace = set()
    if _os.path.exists(spared):
        with open(spared, encoding="utf-8") as handle:
            grace = {line.strip() for line in handle if line.strip()}
    on_disk = {name for name in _os.listdir(stream_dir)
               if name.endswith(".ts") and name.startswith(prefix)}
    check("SCREEN", f"{prefix} and nothing is published that neither it "
                    f"nor the pass before it names",
          sorted(on_disk - set(distinct) - grace), [])

    # The heart of it: the name has to be the fingerprint of the picture.
    #
    # The hashing is written out here rather than imported, deliberately —
    # a gate that calls the very function it is checking proves only that
    # the function agrees with itself. But there is ONE thing it cannot
    # re-derive and must be told, and forgetting that is what turned this
    # gate red on a change that was correct: a segment is made of the
    # picture AND of how the picture is encoded, so the encoder carries a
    # revision number that goes into the name. The number is read from
    # the module; the algorithm is still this file's own.
    import match_screen_video as video

    def named_under(revision):
        """What every board's segment would be called at that revision."""
        out = {}
        for board in boards:
            with open(_os.path.join(boards_dir, board), "rb") as handle:
                body = handle.read()
            running = hashlib.sha256()
            running.update(f"encoder:{revision}\n".encode())
            running.update(_os.path.join(boards_dir, board).encode())
            running.update(body)
            stem = _os.path.splitext(board)[0]
            out[board] = f"{stem}.{running.hexdigest()[:8]}.ts"
        return out

    now_named = named_under(video.ENCODER_REVISION)
    wrong = [f"{board} -> expected {name}"
             for board, name in now_named.items() if name not in distinct]

    # ONE REVISION OF GRACE, and only a WHOLESALE one.
    #
    # The published stream is built by a workflow that runs on main after
    # a merge, so between changing the encoder and that build the repo
    # holds segments named under the PREVIOUS revision. That is not a
    # fault — it is the ordinary state of a correct change in flight, and
    # failing it here means an encoder fix can never go green and so can
    # never merge.
    #
    # It is only forgiven when EVERY board matches the previous revision.
    # A mixture is the thing this gate exists to catch: some segments
    # re-encoded and some not is a stream showing two different encoders
    # at once, and no build produces that.
    if wrong and video.ENCODER_REVISION > 0:
        before = named_under(video.ENCODER_REVISION - 1)
        if all(name in distinct for name in before.values()):
            print(f"  note {prefix} every segment is named under encoder "
                  f"{video.ENCODER_REVISION - 1}, not {video.ENCODER_REVISION}"
                  f" — the encoder was revised and the build that republishes"
                  f" them has not run yet")
            wrong = []
    check("SCREEN", f"{prefix} each segment is named after the board it shows",
          wrong, [])

    # And the names must not be the old fixed ones, which is the shape the
    # bug had: a name that cannot change when the picture does.
    unversioned = [name for name in distinct
                   if _re.fullmatch(prefix + r"\d+\.ts", name)]
    check("SCREEN", f"{prefix} no segment carries a name a cache could reuse",
          unversioned, [])

    # And this file's own hashing must land where the encoder's does. The
    # two are written separately on purpose, and a gate that disagrees
    # with a correct encoder is a gate that stops a good build — which is
    # exactly what happened the first time the encoder's revision moved
    # and this copy did not know about it.
    if boards:
        one = _os.path.join(boards_dir, boards[0])
        with open(one, "rb") as handle:
            body = handle.read()
        running = hashlib.sha256()
        running.update(f"encoder:{video.ENCODER_REVISION}\n".encode())
        running.update(one.encode())
        running.update(body)
        stem = _os.path.splitext(boards[0])[0]
        check("SCREEN", f"{prefix} this gate and the encoder name a "
                        f"segment the same way",
              f"{stem}.{running.hexdigest()[:8]}.ts",
              _os.path.basename(video.segment_of(one)))


def gate_two_pages_make_one_row() -> None:
    """A match on both pages is one row, and a wrong pair is never one row.

    مباريات اليوم now reads two listings pages. They spell clubs
    differently — one writes "West Brom" where the other writes "West
    Bromwich Albion", one writes "QPR" where the other writes "Queens Park
    Rangers" — so a merge that only compares strings prints every shared
    match twice, and a board that holds nine rows loses half its day to
    duplicates.

    The dangerous fix is a similarity score. Measured inside one script it
    cannot be made safe: "Mainz"/"Monza" and "Al Nassr"/"Al Nasar" score
    above every threshold that still catches a real pair. So the merge does
    not score anything — it asks whether one name is the other abbreviated,
    at a kickoff both pages agree on, on both sides of the fixture.

    This gate holds both halves at once: the abbreviations must join, and
    the near-misses must not. Widening the first without checking the
    second is exactly how a wrong pair gets merged, and a merged wrong pair
    deletes a real match from the board.
    """
    print("\nTwo pages, one row — the merge joins abbreviations, not lookalikes")
    import today_matches_epg as today

    # One club, written short on one page and long on the other.
    for short, long in (("West Brom", "West Bromwich Albion"),
                        ("QPR", "Queens Park Rangers"),
                        ("Wolves", "Wolverhampton Wanderers"),
                        ("Man Utd", "Manchester United"),
                        ("Tottenham", "Tottenham Hotspur"),
                        ("Newcastle", "Newcastle United")):
        check("MERGE", f"{short!r} is {long!r} shortened",
              today.same_side(short, long), True)

    # Two clubs that are not one club, however alike they read.
    for first, second in (("Mainz", "Monza"),
                          ("Al Nassr", "Al Nasar"),
                          ("Real Madrid", "Real Sociedad"),
                          ("Manchester United", "Manchester City"),
                          ("Nottingham Forest", "Norwich City"),
                          ("Inter", "Inter Miami"),
                          ("AC Milan", "Ajaccio")):
        check("MERGE", f"{first!r} is not {second!r}",
              today.same_side(first, second), False)

    # An honorific the other page left off. Spanish football is full of
    # these, and left-aligned words had nothing to line up: Betis v Real
    # Madrid went onto one board twice.
    for short, long in (("Betis", "Real Betis"),
                        ("Sociedad", "Real Sociedad"),
                        ("Valladolid", "Real Valladolid")):
        check("MERGE", f"{short!r} is {long!r} without its honorific",
              today.same_side(short, long), True)
    # And dropping it must not make different clubs the same one.
    for first, second in (("Real Madrid", "Atletico Madrid"),
                          ("Real Madrid", "Real Sociedad"),
                          ("Real Betis", "Real Sociedad")):
        check("MERGE", f"{first!r} is still not {second!r}",
              today.same_side(first, second), False)

    # A fixture needs both sides. One side agreeing is a coincidence.
    check("MERGE", "both sides must agree before it is one match",
          today.same_match("QPR - Cardiff City",
                           "Queens Park Rangers - Cardiff City"), True)
    check("MERGE", "one side agreeing is not enough",
          today.same_match("QPR - Cardiff City",
                           "Queens Park Rangers - Swansea City"), False)

    # And the whole of it, end to end: two pages in, one list out.
    from datetime import datetime, timedelta, timezone
    kick = datetime(2026, 9, 2, 18, 45, tzinfo=timezone.utc)
    primary = [
        {"start": kick, "title": "QPR - Cardiff City",
         "channels": ["beIN Sports 1"], "competition": ""},
        {"start": kick, "title": "Mainz - Werder Bremen",
         "channels": ["Thmanyah 2"], "competition": "Bundesliga"},
    ]
    secondary = [
        {"start": kick, "title": "Queens Park Rangers - Cardiff City",
         "channels": ["Sky Sports+"], "competition": "Championship"},
        {"start": kick, "title": "Monza - Como",
         "channels": ["TNT Sports 1"], "competition": "Serie A"},
        {"start": kick, "title": "Millwall - Wrexham",
         "channels": ["Sky Sports+"], "competition": "Championship"},
    ]
    merged = today.unify(primary, secondary)
    check("MERGE", "five rows in, four out", len(merged), 4)

    by_title = {event["title"]: event for event in merged}
    check("MERGE", "the shared match keeps the first page's spelling",
          "QPR - Cardiff City" in by_title, True)
    joined = by_title.get("QPR - Cardiff City", {"channels": [],
                                                 "competition": ""})
    check("MERGE", "and names both pages' channels, the tunable one first",
          joined["channels"], ["beIN Sports 1", "Sky Sports+"])
    check("MERGE", "and borrows the competition the first page left blank",
          joined["competition"], "Championship")
    check("MERGE", "Mainz did not swallow Monza",
          "Monza - Como" in by_title, True)
    check("MERGE", "a match only the second page saw is still a match",
          "Millwall - Wrexham" in by_title, True)

    # A shop is not a channel, and the rule that decides which matches
    # belong has to be the rule that decides what they say. It was applied
    # to the first and not the second, and a match kept because beIN
    # carried it reached a television labelled "OneFootball".
    for shop in ("OneFootball", "Thmanyah App", "LaLiga PPV",
                 "Flamengo TV YouTube", "Federation Official Site"):
        check("MERGE", f"{shop!r} is not somebody's television",
              today.real_channels([shop]), [])
    check("MERGE", "and one real name among them is what gets shown",
          today.channels_of({"channels": ["OneFootball", "beIN Sports 1",
                                          "Thmanyah App"]}),
          "beIN 1")

    # The merge must not reach across kickoffs. Two different matches can
    # share both club names across a season; only one of them is tonight.
    apart = today.unify(
        primary[:1],
        [{"start": kick + timedelta(hours=3),
          "title": "Queens Park Rangers - Cardiff City",
          "channels": ["Sky Sports+"], "competition": "Championship"}])
    check("MERGE", "the same fixture at another hour is another match",
          len(apart), 2)


def gate_a_day_divider_is_not_a_container() -> None:
    """Each fixture takes the date of the divider above it, not the page's.

    live-footballontv writes 1896 fixtures inside TWO div.fixture-group
    elements. The day is a div.fixture-date divider written BETWEEN the
    fixtures, not a box around them — and the first reader treated a group
    as a day, took the first date it found in it, and stamped 1876
    fixtures with it. Every one of those fixtures was real; the whole
    autumn simply arrived on tomorrow's board, Champions League league
    phase and all. A probe of the merged output is what caught it, and
    nothing in the code could have.

    So the shape itself is held here, in the page's own markup: two
    dividers, fixtures under each, and pills for the channels. If a
    fixture ever takes a date from anywhere but the divider above it, this
    goes red before anything reaches a screen.
    """
    print("\nA day divider is a divider — live-footballontv")
    from datetime import datetime, timezone

    import live_football_on_tv as second

    page = """
    <div class="fixture-group">
      <div class="fixture-date">Wednesday 2nd September 2026</div>
      <div class="fixture">
        <div class="fixture__time">01:00</div>
        <div class="fixture__teams">Atletico Mineiro v Cruzeiro  </div>
        <div class="fixture__competition">Copa do Brasil</div>
        <div class="fixture__channel"><div class="span3 channels">
          <span class="channel-pill">Premier Sports 2</span>
        </div></div>
      </div>
      <div class="fixture-date">Thursday 3rd September 2026</div>
      <div class="fixture">
        <div class="fixture__time">19:45</div>
        <div class="fixture__teams">Millwall v Wrexham  </div>
        <div class="fixture__competition">Championship</div>
        <div class="fixture__channel"><div class="span3 channels">
          <span class="channel-pill">Sky Sports+</span>
          <span class="channel-pill">TNT Sports 1</span>
          <span class="channel-pill">TBC</span>
        </div></div>
      </div>
      <div class="fixture">
        <div class="fixture__time">TBC</div>
        <div class="fixture__teams">Arsenal v Real Madrid  </div>
        <div class="fixture__competition">Champions League</div>
        <div class="fixture__channel"><div class="span3 channels">
          <span class="channel-pill">TBC</span>
        </div></div>
      </div>
    </div>
    """
    floor = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)
    ceiling = datetime(2026, 9, 5, 0, 0, tzinfo=timezone.utc)
    read = second.collect(page, floor, ceiling)

    check("SOURCE2", "a fixture with no kickoff is not a fixture",
          len(read), 2)
    by_title = {event["title"]: event for event in read}

    check("SOURCE2", "the first fixture keeps the first divider's day",
          f"{by_title['Atletico Mineiro - Cruzeiro']['start']:%Y-%m-%d %H:%M}",
          "2026-09-02 00:00")
    check("SOURCE2", "and the second takes the SECOND divider's day",
          f"{by_title['Millwall - Wrexham']['start']:%Y-%m-%d %H:%M}",
          "2026-09-03 18:45")

    check("SOURCE2", "each channel pill is read on its own",
          by_title["Millwall - Wrexham"]["channels"],
          ["Sky Sports+", "TNT Sports 1"])
    check("SOURCE2", "and the page saying it does not know is not a channel",
          any("TBC" in name
              for event in read for name in event["channels"]), False)

    # The fault itself, stated as a number: everything on one day is what
    # going wrong looked like.
    check("SOURCE2", "the fixtures did not all land on one day",
          len({event["start"].date() for event in read}), 2)

    # UTF-8 read a byte at a time. "FC KÃ¶ln" reached the television, and
    # it cost more than an ugly row: the other page writes "FC Koln", and
    # two spellings differing by mojibake are two clubs to the merge, so
    # the fixture was published twice.
    check("SOURCE2", "mojibake is mended", second.mended("FC KÃ¶ln"),
          "FC Köln")
    check("SOURCE2", "and the repair leaves good text alone",
          [second.mended(name) for name in
           ("Liga 1 Perú", "Virslīga", "الهلال", "Beşiktaş", "FC Köln")],
          ["Liga 1 Perú", "Virslīga", "الهلال", "Beşiktaş", "FC Köln"])


def gate_the_printed_clock_is_the_kickoff() -> None:
    """The hour a match starts comes from the cell, not from the markup.

    livefootballtv publishes a schema.org startDate that is one hour fast:
    it prints the Gulf clock its readers want and derives the markup by
    subtracting two hours, as though the Gulf were UTC+2 rather than +3.
    Reading the markup as the instant put every match on this channel an
    hour late — and that was then "fixed" by moving the reader's own clock
    back an hour, which printed the right digits in September and would
    have been wrong all winter.

    Settled by British football, whose kickoff times are not opinion: the
    markup puts Burnley v Middlesbrough on Sky at 21:00 UK, and the
    Championship does not kick off at 21:00. The rows below are real ones
    taken off the page, with the last two chosen because their printed
    clock is past midnight and the markup's date is not — which is where a
    naive combination of the two puts a match a day out.
    """
    print("\nThe printed clock is the kickoff — livefootballtv")
    from bs4 import BeautifulSoup

    import today_matches_epg as today

    def row_of(printed: str, markup: str):
        return BeautifulSoup(
            f'<table><tr><td class="hora">{printed}</td>'
            f'<td class="canales"><meta itemprop="startDate" '
            f'content="{markup}"/></td></tr></table>',
            "html.parser").find("tr")

    for printed, markup, expected in (
            # Sky's Championship game: 20:00 UK, not the markup's 21:00.
            ("22:00", "2026-09-02T20:00:00", "2026-09-02 19:00"),
            # A Coppa Italia tie at 18:00 in Italy.
            ("19:00", "2026-09-02T17:00:00", "2026-09-02 16:00"),
            # Printed after midnight, markup still on the day before.
            ("02:00", "2026-09-02T00:00:00", "2026-09-01 23:00"),
            ("03:00", "2026-09-02T01:00:00", "2026-09-02 00:00")):
        struck = today.kickoff_of(row_of(printed, markup))
        check("CLOCK", f"printed {printed} with markup {markup[11:16]}",
              f"{struck:%Y-%m-%d %H:%M}" if struck else None, expected)

    # No printed clock at all: the markup, with its hour taken back off.
    bare = BeautifulSoup(
        '<table><tr><td class="canales"><meta itemprop="startDate" '
        'content="2026-09-02T20:00:00"/></td></tr></table>',
        "html.parser").find("tr")
    check("CLOCK", "and with no printed clock, the markup less its hour",
          f"{today.kickoff_of(bare):%Y-%m-%d %H:%M}", "2026-09-02 19:00")

    # The reader's zone is the other half of the same fault. A fixed
    # offset was the shape of the mistake, not a detail of it.
    check("CLOCK", "the reader is on a real zone, not a frozen offset",
          today.VIEWER.key, "America/Los_Angeles")


def gate_a_day_drawn_is_a_day_collected() -> None:
    """Every board gets the whole of its own day to fill itself from.

    The board list was built from a DATE and the matches were filtered
    against an INSTANT, and the two disagreed about the last day. The
    guide drew a board for Friday and then admitted only the hours of
    Friday that fell before the clock time of the build — 7.6 of 24 at
    14:36 UTC, all of them before dawn in Los Angeles. Every Friday
    evening kickoff in Europe was hours outside it.

    So a full Friday of football was published as "لا توجد مباراة معلنة",
    every single day, and from the sofa it looked like a channel that had
    stopped updating rather than one with an arithmetic fault. Nothing was
    wrong with either source.

    This is the invariant that was missing, and it is checked at every
    hour of the clock rather than at the one the build happened to run
    at — the fault was invisible at 00:00 and total at 23:00. It is also
    checked across the night the clocks go back, because a "day" is 25
    hours long that night and arithmetic in fixed offsets quietly loses an
    hour of it.
    """
    print("\nA day drawn is a day collected — مباريات اليوم")
    from datetime import datetime, timedelta, timezone

    import today_matches_epg as today

    def whole_days_covered(now):
        floor, ceiling = today.window_floor(now), today.window_ceiling(now)
        for day in today.days_of(now):
            if today.start_of_day(day) < floor:
                return f"{day} starts before the window does"
            if today.start_of_day(day + timedelta(days=1)) > ceiling:
                return f"{day} ends after the window does"
        return ""

    # Every hour of an ordinary day.
    broken = [f"{hour:02d}:00Z {why}" for hour in range(24)
              if (why := whole_days_covered(
                  datetime(2026, 9, 2, hour, 36, tzinfo=timezone.utc)))]
    check("WINDOW", "every board's day is inside the window, at every hour",
          broken, [])

    # The night Los Angeles puts its clocks back: one day is 25 hours.
    autumn = [f"{hour:02d}:00Z {why}" for hour in range(24)
              if (why := whole_days_covered(
                  datetime(2026, 11, 1, hour, 36, tzinfo=timezone.utc)))]
    check("WINDOW", "and still inside it the night the clocks go back",
          autumn, [])

    # The exact match that was being dropped, named.
    now = datetime(2026, 9, 2, 14, 36, tzinfo=timezone.utc)
    friday_night = datetime(2026, 9, 4, 18, 45, tzinfo=timezone.utc)
    check("WINDOW", "a Ligue 1 Friday 20:45 CEST is inside the window",
          today.window_floor(now) <= friday_night < today.window_ceiling(now),
          True)
    check("WINDOW", "and it lands on the Friday board, not tomorrow's",
          friday_night.astimezone(today.VIEWER).date(),
          today.days_of(now)[-1])

    # The board list and the window must be the same length of time.
    check("WINDOW", "the window is exactly as long as the boards it fills",
          today.window_ceiling(now) - today.window_floor(now),
          timedelta(days=today.DAYS_AHEAD + 1))


def gate_the_third_page_fills_the_gap() -> None:
    """yallakora, read off its own markup, and kept to what it is for.

    A reader photographed four fixtures missing from the board — three in
    Jordan's league and الأهلي v سموحة in Egypt's — and then a fifth,
    Başakşehir v Galatasaray in Turkey's. Measured: of 42,924 characters
    on the first page and 142,697 on the second, not one names those
    clubs, and not a single row was dropped for lacking a broadcaster. The
    gap was coverage of Arab and Turkish domestic football.

    Of four Arabic pages asked how many blocks hold a clock AND a channel,
    kooora managed 0 of 93 and this one holds channel, teams, competition
    and kickoff inside a single element — and takes a date.

    Its clubs are written in Arabic, and no threshold merges those safely:
    measured over thirteen real cross-script pairs and ten false ones,
    تولوز against Toulon scores 0.800 while باشاكشهير against Basaksehir
    scores 0.640. So it is kept to competitions the other two pages do not
    carry, where there is nothing to collide with. That narrowing is the
    safety, and this gate holds it.
    """
    print("\nThe third page fills the gap — yallakora")
    from datetime import datetime, timezone

    import today_matches_epg as today
    import yallakora

    page = """
    <a class="tourTitle"><div class="imgCntnr">
      <img alt="الدوري المصري" enname="Egyptian-league"/></div></a>
    <div class="allData">
      <div class="channel icon-channel">ON Sport</div>
      <div class="topData"><div class="matchStatus"><span>لم تبدأ</span></div></div>
      <div class="teamCntnr"><div class="teamsData">
        <div class="teams teamA"><img alt="الأهلي"/><p>الأهلي</p></div>
        <div class="MResult"><span class="score">-</span>
          <span class="time">20:00</span></div>
        <div class="teams teamB"><img alt="سموحة"/><p>سموحة</p></div>
      </div></div>
    </div>
    <a class="tourTitle"><div class="imgCntnr">
      <img alt="دوري القسم الثاني-أ" enname="Egypt-second"/></div></a>
    <div class="allData">
      <div class="teamCntnr"><div class="teamsData">
        <div class="teams teamA"><p>بلدية المحلة</p></div>
        <div class="MResult"><span class="time">16:30</span></div>
        <div class="teams teamB"><p>نادى دلتا يونايتد</p></div>
      </div></div>
    </div>
    """
    day = datetime(2026, 9, 3).date()
    floor = datetime(2026, 9, 2, 7, 0, tzinfo=timezone.utc)
    ceiling = datetime(2026, 9, 5, 7, 0, tzinfo=timezone.utc)
    read = yallakora.collect(page, day, floor, ceiling)

    check("SOURCE3", "both fixtures are read", len(read), 2)
    by_title = {event["title"]: event for event in read}

    # The very fixture that was missing, at the clock its own app showed.
    ahly = by_title.get("الأهلي - سموحة", {})
    check("SOURCE3", "الأهلي - سموحة is there",
          bool(ahly), True)
    check("SOURCE3", "at 20:00 Cairo, which is 17:00 UTC",
          f"{ahly['start']:%Y-%m-%d %H:%M}" if ahly else None,
          "2026-09-03 17:00")
    check("SOURCE3", "with the Arabic channel a reader can tune to",
          ahly.get("channels"), ["ON Sport"])
    check("SOURCE3", "and the competition in both scripts",
          ahly.get("competition"), "Egyptian league | الدوري المصري")
    check("SOURCE3", "the crest's alt does not double the club's name",
          ahly.get("title"), "الأهلي - سموحة")

    # The narrowing: Egypt's top flight is asked for, its second tier is not.
    check("SOURCE3", "Egypt's league is what this page is here for",
          any(name in ahly.get("competition", "")
              for name in today.YALLAKORA_ONLY), True)
    second = by_title.get("بلدية المحلة - نادى دلتا يونايتد", {})
    check("SOURCE3", "Egypt's second tier is not",
          any(name in second.get("competition", "")
              for name in today.YALLAKORA_ONLY), False)

    # A block with no channel is still a real fixture. Başakşehir v
    # Galatasaray had none, and used to be dropped for it.
    check("SOURCE3", "a fixture with no broadcaster named is still read",
          second.get("channels"), [])
    check("SOURCE3", "and the guide keeps it rather than hiding the match",
          today.wanted({"competition": "الدوري التركي", "title": "A - B",
                        "channels": [], "start": None}), True)
    # The duplicate this page caused when it was first switched on, and
    # the fact that settles it without touching the club names.
    from datetime import timedelta
    when = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
    board = [{"start": when, "title": "El Gouna FC - El-Mokawloon",
              "channels": ["On Sport Plus"], "competition": ""},
             {"start": when, "title": "Abu Qair - Al Ittihad",
              "channels": ["ON Sport"], "competition": ""}]
    for channels, start, already, why in (
            (["ON Sport PLUS"], when, True, "same minute, same channel"),
            (["ON Sport MAX"], when, False, "MAX is another channel"),
            (["ON Sport"], when + timedelta(hours=3), False, "another hour"),
            ([], when, False, "nothing to compare")):
        check("SOURCE3", f"already on the board? {why}",
              today.already_on_air({"start": start, "title": "أ - ب",
                                    "channels": channels}, board), already)

    check("SOURCE3", "while a match that is only a shop stays out",
          today.wanted({"competition": "الدوري التركي", "title": "A - B",
                        "channels": ["OneFootball"], "start": None}), False)


def gate_our_own_guides_name_the_channel() -> None:
    """This repository's guides say which of the reader's channels has it.

    Asked for directly, and they know something no listings page does. They
    are used to NAME channels and never to add fixtures, because their
    titles are written for a television grid: beIN Turkey writes
    "Super Lig (26-27) 3. Hafta Gaziantep Fk - Rizespor - Bant -", where
    "Bant" means it is a repeat, and it also carries matches from the year
    2000. A title read wrongly that only fails to name a channel costs
    nothing; one that ADDS a fixture puts a match on the screen that is
    not being played.

    Matching is the same cross-script problem as everywhere, answered the
    same way: never a similarity score. The minute must agree and one club
    must match — epg_lib's strict rule across the scripts, plain skeleton
    equality within one. ONE side is enough here and only here, because a
    club cannot play two matches at once. Measured over the nine fixtures
    Alwan published on the day this was written, one side reaches all
    nine where both sides reach six: ميدلزبره and Middlesbrough do not
    reduce to the same skeleton, and بيرنلي and Burnley do.

    And Istanbul is marked. beIN SPORTS 1 in Istanbul and beIN SPORTS 1 in
    Doha are different channels showing different football.
    """
    print("\nOur own guides name the channel — Alwan, beIN Turkey, Spor Ekranı")
    import json
    from datetime import datetime, timezone

    import own_guides

    # A grid title that is a fixture, and the several that are not.
    check("OWN", "a plain fixture is read",
          own_guides.fixture_in("الهلال - الأهلي ‎🔴 LIVE‎"),
          ("الهلال", "الأهلي"))
    for title, why in (
            ("لا توجد مباراة مجدولة", "nothing scheduled"),
            ("لم يُعلن البث — No listing published", "no listing"),
            ("Beşiktaş - Adanaspor (00-01) 21.hafta", "a match from 2000"),
            ("Tff 1. Lig Maç Özetleri (26-27) 05. Hafta - Haber / Salı",
             "a highlights programme"),
            ("Super Lig (26-27) 3. Hafta Gaziantep Fk - Rizespor - Bant -",
             "a repeat with a competition prefix")):
        check("OWN", f"not a fixture: {why}",
              own_guides.fixture_in(title), ("", ""))

    # Eight spellings of one channel are one channel.
    check("OWN", "quality variants fold into one channel",
          [own_guides.one_channel(name) for name in
           ("Alwan Sport 1 HD", "Alwan Sports 1", "Alwan Sport 1 4K",
            "Alwan Sport 1 RAW")],
          ["Alwan Sport 1"] * 4)
    # ...but not so far that the name stops being a channel. "beIN 4K" is
    # Doha's own feed and folding it printed "beIN", which is nothing a
    # viewer can turn to.
    check("OWN", "a channel whose 4K IS its name keeps it",
          own_guides.one_channel("beIN 4K"), "beIN 4K")

    # One club is enough, at an agreed minute, because a club plays once.
    check("OWN", "بيرنلي is Burnley",
          own_guides.one_club("بيرنلي", "Burnley"), True)
    check("OWN", "and one side carries the fixture ميدلزبره cannot",
          own_guides.one_club_matches("Burnley - Middlesbrough",
                                      "بيرنلي - ميدلزبره"), True)
    check("OWN", "Galatasaray matches itself, within one script",
          own_guides.one_club("Galatasaray", "Galatasaray"), True)
    check("OWN", "Mainz is still not Monza, within one script",
          own_guides.one_club("Mainz", "Monza"), False)
    check("OWN", "and two unrelated fixtures do not match",
          own_guides.one_club_matches("Burnley - Middlesbrough",
                                      "الهلال - الأهلي"), False)

    # Spor Ekranı arrives in the same shape, over the network, and goes
    # through the same matching. Its ld+json gives a real instant, so
    # there is no clock to place in a timezone — the fault that cost this
    # guide a day and then an hour.
    import spor_ekrani
    page = ("""<script type="application/ld+json">""" + json.dumps([
        {"@type": "BroadcastEvent", "isLiveBroadcast": True,
         "publishedOn": [{"@type": "TelevisionChannel",
                          "name": "Bein Sports 1"},
                         {"@type": "TelevisionChannel",
                          "name": "Yayın Yok"}],
         "broadcastOfEvent": {
             "name": "İstanbul Başakşehir - Galatasaray",
             "startDate": "2026-09-04T17:00:00Z",
             "homeTeam": {"name": "İstanbul Başakşehir"},
             "awayTeam": {"name": "Galatasaray"}}},
        {"@type": "BroadcastEvent",
         "broadcastOfEvent": {"name": "Bir Program",
                              "startDate": "2026-09-04T17:00:00Z"}},
    ], ensure_ascii=False) + "</script>")
    read = spor_ekrani.collect(page)
    check("OWN", "the teams it names outright are the fixture",
          [r["title"] for r in read],
          ["İstanbul Başakşehir - Galatasaray"])
    check("OWN", "its channel is marked TR",
          [r["channel"] for r in read], ["Bein Sports 1 TR"])
    check("OWN", "and 'Yayın Yok' is not a channel",
          any("Yayın" in r["channel"] for r in read), False)
    check("OWN", "the instant needs no timezone guessed",
          f"{read[0]['start']:%Y-%m-%d %H:%M %Z}" if read else None,
          "2026-09-04 17:00 UTC")

    # A grid gives the PROGRAMME, a listings page gives the KICKOFF, and
    # they are not the same instant: beIN Turkey opens Başakşehir v
    # Galatasaray at 16:15 for a 17:00 kick. At a minute's tolerance the
    # Turkish channel never reached the Turkish match. Wide is safe only
    # because one club must still match exactly — a club does not play
    # twice inside two hours.
    from datetime import timedelta
    check("OWN", "a broadcast may open before the kickoff",
          own_guides.SLACK >= timedelta(minutes=45), True)

    # End to end, on a board.
    when = datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc)
    board = [{"start": when, "title": "إسطنبول باشاكشهير - جالاتا سراي",
              "channels": []},
             {"start": when, "title": "Mainz - Werder Bremen",
              "channels": ["beIN SPORTS 2"]}]
    own_guides.add_channels(board)
    # Doha shows this one too — beIN SPORTS 5 there, beIN SPORTS 1 in
    # Istanbul, at 16:50 for a 17:00 kick. Both are right and they are
    # different channels, which is exactly what the mark is for: a row
    # naming "beIN SPORTS 1" and "beIN SPORTS 5" unmarked would send a
    # viewer in Doha to the wrong one.
    check("OWN", "Istanbul's beIN is marked TR",
          "beIN SPORTS 1 TR" in board[0]["channels"], True)
    check("OWN", "and Doha's, on the same match, is not",
          [name for name in board[0]["channels"]
           if name.endswith(" TR")] != board[0]["channels"], True)
    check("OWN", "and a match none of our channels carry is left alone",
          board[1]["channels"], ["beIN SPORTS 2"])


def gate_the_american_channel_is_named() -> None:
    """Fox, NBC, CBS and the rest, from the one US page that answers in HTML.

    Of thirty matches on the board, not one named an American broadcaster.
    They were not hidden behind the "+5" — no source here had ever seen
    them. livesoccertv's /schedules/ has them: 68 blocks with a clock, 17
    with a clock and a US channel, where Fox's own site, ESPN's and NBC's
    give none between them.

    The trap this page sets is the one the first source set. It publishes
    the kickoff TWICE and the two disagree by four hours: data-ko is the
    site's Eastern wall clock, span.ts[dv] is a true epoch. Reading the
    printed one put every match on this channel an hour late once already,
    and would put these four hours early. dv is read; data-ko is not, and
    this gate holds it there.

    Marking is the mirror of Istanbul's. beIN is the one brand this page
    shares with the Gulf feeds, so beIN gets " US" and nothing else does:
    Fox Sports 1 is nobody else's name, and a mark on an unambiguous one
    is noise on a row with little space.

    Like every listings reader here it NAMES channels and never adds
    fixtures.
    """
    print("\nThe American channel is named — livesoccertv")
    import live_soccer_tv

    # 1788397200000 is 2026-09-03 01:00 UTC. The same row prints
    # data-ko="2026-09-02 21:00:00" — Eastern, four hours behind.
    page = """
    <table>
      <tr class="matchrow" data-ko="2026-09-02 21:00:00" id="5773791">
        <td><span class="ts" df="h:MMtt" dv="1788397200000">9:00pm</span></td>
        <td class="matchcol"><a href="/match/x" title="Toluca vs Le&#243;n">x</a></td>
        <td><div class="mchannels">
          <a title="Fox Sports 1">Fox Sports 1</a>,
          <a title="beIN SPORTS">beIN SPORTS</a>,
          <a title="fuboTV.com">fuboTV.com</a>,
          <a title="YouTube">YouTube</a>
        </div></td>
      </tr>
      <tr class="matchrow" data-ko="2026-09-02 15:00:00" id="5773792">
        <td><span class="ts" dv="1788361200000">3:00pm</span></td>
        <td class="matchcol"><a href="/match/y" title="Arsenal vs Chelsea">y</a></td>
        <td><div class="mchannels"><a title="NBC">NBC</a>,
          <a title="CBS Sports">CBS Sports</a></div></td>
      </tr>
      <tr class="matchrow" id="5773793">
        <td class="matchcol"><a href="/match/z" title="A vs B">z</a></td>
        <td><div class="mchannels"><a title="Paramount+">Paramount+</a></div></td>
      </tr>
    </table>"""
    read = live_soccer_tv.collect(page)

    check("USA", "the published instant is read, not the Eastern clock",
          f"{read[0]['start']:%Y-%m-%d %H:%M %Z}", "2026-09-03 01:00 UTC")
    check("USA", "and never 21:00, which is what the page prints",
          any(r["start"].hour == 21 for r in read), False)
    check("USA", "'Toluca vs Le\u00f3n' is a fixture of two clubs",
          read[0]["title"], "Toluca - Le\u00f3n")
    check("USA", "Fox is left exactly as the page writes it",
          [r["channel"] for r in read if "Fox" in r["channel"]],
          ["Fox Sports 1"])
    check("USA", "beIN is marked US, because Doha has that name too",
          [r["channel"] for r in read if "beIN" in r["channel"]],
          ["beIN SPORTS US"])
    check("USA", "NBC and CBS come through unmarked",
          sorted(r["channel"] for r in read
                 if r["channel"] in ("NBC", "CBS Sports")),
          ["CBS Sports", "NBC"])
    check("USA", "a stream and a shop are not channels",
          any(word in r["channel"].lower()
              for r in read for word in ("youtube", "fubotv")), False)
    check("USA", "a row with no clock is dropped, not guessed at",
          any(r["title"] == "A - B" for r in read), False)

    # End to end: it names a channel on a match already on the board, and
    # adds none of its own.
    from datetime import datetime, timezone

    import own_guides
    board = [{"start": datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc),
              "title": "Toluca - Le\u00f3n", "channels": []}]
    own_guides.add_channels(board, {"livesoccertv": read})
    check("USA", "the American channel reaches the board",
          "Fox Sports 1" in board[0]["channels"], True)
    check("USA", "and the board gains no fixtures from a listings page",
          len(board), 1)


def gate_a_grid_title_is_read_the_way_that_grid_writes_it() -> None:
    """Doha's beIN, and the club whose name contained a marker.

    Three of this repository's own guides are read for channel names now,
    and the third writes its titles differently from the other two. Alwan
    and beIN Turkey put a dash between the clubs; Doha writes
    "Ipswich Town v Liverpool - English Premier League 2026/2027", where
    the dash belongs to the COMPETITION. Split that on the dash and the
    fixture is "Ipswich Town v Liverpool" against "English Premier
    League" — two things that are not clubs, matching nothing. 350 of
    Doha's titles are that shape.

    And the bug this found. Markers were stripped without word
    boundaries, so "LIVE" matched inside "Liverpool" and the club came
    out as "rpool". The most broadcast club in the world could not be
    matched by any guide published here, and nothing showed it: a club
    that fails to match only ever costs a channel name, never a wrong
    one, so the hole was silent. Every marker is a whole word now.

    What is NOT a fixture is the other half. Doha's grid carries
    "Preview - US Open 2026" and "Ligue 1 Weekly Review - 2026/2027"
    beside the football, and Alwan says "التالي: بيرنلي - ميدلزبره" —
    real clubs, on a row whose time belongs to the programme now showing
    rather than to their match. Taking that hands a channel to whatever
    else falls inside the two-hour window; the same match is published
    again at its own time, so nothing is lost by refusing it.
    """
    print("\nA grid title is read the way that grid writes it")
    import own_guides

    check("GRID", "Doha's 'vs.' separates the clubs, its dash does not",
          own_guides.fixture_in(
              "Liverpool vs. Nottingham Forest - English Premier League "
              "2026/2027"),
          ("Liverpool", "Nottingham Forest"))
    check("GRID", "and a bare 'v' does the same",
          own_guides.fixture_in(
              "Ipswich Town v Liverpool - English Premier League "
              "2026/2027 \u200e\u2022 Live \U0001f535\u200e"),
          ("Ipswich Town", "Liverpool"))
    check("GRID", "LIVE is a marker, not the first four letters of a club",
          own_guides.fixture_in("Liverpool - Everton"),
          ("Liverpool", "Everton"))
    check("GRID", "a dash-written grid is unchanged",
          own_guides.fixture_in("\u0628\u064a\u0631\u0646\u0644\u064a - "
                                "\u0645\u064a\u062f\u0644\u0632\u0628"
                                "\u0631\u0647 \u200e\U0001f534 LIVE\u200e"),
          ("\u0628\u064a\u0631\u0646\u0644\u064a",
           "\u0645\u064a\u062f\u0644\u0632\u0628\u0631\u0647"))

    for title, why in (
            ("Ligue 1 Weekly Review - 2026/2027", "a review"),
            ("Preview - US Open 2026", "a preview"),
            ("Round 1 - Serie A Highlights", "highlights"),
            ("\u0627\u0644\u062a\u0627\u0644\u064a: "
             "\u0628\u064a\u0631\u0646\u0644\u064a - "
             "\u0645\u064a\u062f\u0644\u0632\u0628\u0631\u0647",
             "what comes next, at the wrong time"),
            ("\u062d\u0643\u064a \u0633\u064a\u0627\u0633\u064a - "
             "\u0627\u0644\u0645\u0648\u0633\u0645 "
             "\u0627\u0644\u062b\u0627\u0644\u062b",
             "a drama serial's season")):
        check("GRID", f"not a fixture: {why}",
              own_guides.fixture_in(title), ("", ""))

    # Doha carries no mark and Istanbul carries one, which is the whole
    # reason the mark exists.
    marks = dict((path, mark) for path, mark in own_guides.GUIDES)
    check("GRID", "Doha's beIN is wired in, unmarked",
          marks.get("bein_sports_qatar_epg.xml"), "")
    check("GRID", "Istanbul's is wired in, marked TR",
          marks.get("bein_sports_turkey_epg.xml"), " TR")
    check("GRID", "and no general channel's grid is read for football",
          [path for path in marks if "roya" in path or "jordan" in path], [])


def gate_a_row_names_two_channels() -> None:
    """A viewer who cannot get the first channel is told the second.

    One channel per row was chosen when a match rarely had a second, and
    it went on hiding every source added since. A real row read
    "Ipswich - Liverpool · beIN SPORTS 1 EN +5": five channels collected,
    named, and printed as a digit.

    Two is where it stops — the line has to fit a television screen and
    the drawn board gives a row two pills — so beyond the second the
    count returns, honest about there being more without spending a line.
    """
    print("\nA row names two channels")
    import inspect
    from datetime import datetime, timezone

    import today_matches_epg as today

    check("TWO", "three channels are printed, not one and a digit",
          today.channels_of({"channels": ["beIN SPORTS 1", "Sky Sports+",
                                          "Fox Sports 1"]}),
          "beIN 1 · Sky+ · Fox Sports 1")
    check("TWO", "a fourth is counted, not dropped",
          today.channels_of({"channels": ["beIN SPORTS 1", "Sky Sports+",
                                          "Fox Sports 1", "DAZN"]}),
          "beIN 1 · Sky+ · Fox Sports 1 +1")
    check("TWO", "one channel is still one channel",
          today.channels_of({"channels": ["DAZN"]}), "DAZN")
    check("TWO", "and the app the reader asked to stop seeing is not one",
          today.channels_of({"channels": ["OneFootball", "beIN SPORTS 1"]}),
          "beIN 1")

    # The drawn board gives a row three pills, so the picture and the
    # line agree on how many a viewer is shown. Three was refused once on
    # an unmeasured claim that a twelve-match day could not fit them; it
    # can, because a crowded row draws its pills smaller too.
    check("TWO", "the board draws as many as the line prints",
          today.MAX_CHANNELS, 3)

    # The reader's order: Arabic, English, American, Turkish, the rest.
    # It was source order, which is the order a British listings page
    # happens to print its pills — so four of the seven rows that had two
    # channels spent the second on something neither the region nor
    # America can open, while the Fox that WAS collected sat behind "+1".
    check("TWO", "Arabic comes first, then British, then American",
          today.channels_of({"channels": ["MBC Shahid Sports", "Fox Sports 1",
                                          "TNT Sports 1"]}),
          "MBC Shahid · TNT 1 · Fox Sports 1")
    check("TWO", "the tiers run Arabic, British, American, Turkish, ANZ, rest",
          [today.where_from(name) for name in
           ("beIN SPORTS 3", "Sky Sports+", "Fox Sports 1",
            "beIN SPORTS 1 TR", "Optus Sport", "Ligue1+")],
          [0, 1, 2, 3, 4, 5])
    # Australia and New Zealand are named by an explicit marker, never by
    # the brand: "Sky Sport NZ" carries Sky and is not Britain's, "Fox
    # Sports Australia" carries Fox and is not America's, and reading
    # either by its brand puts a channel on the row that the wrong half
    # of the world can watch.
    check("TWO", "a Sky and a Fox from the other side of the world",
          [today.where_from(name) for name in
           ("Sky Sport NZ", "Fox Sports Australia", "Stan Sport", "Kayo")],
          [4, 4, 4, 4])
    check("TWO", "and they outrank Scandinavia and Denmark",
          today.channels_of({"channels": ["beIN SPORTS 2", "V Sport 1",
                                          "Optus Sport", "TV2 Denmark"]}),
          "beIN 2 · Optus Sport · V Sport 1 +1")
    # "English" is Sky and TNT — the channels that carry English football
    # in England. A beIN feed with English commentary is Doha's channel
    # and belongs with the Arabic ones, and reading it as British put it
    # in the second slot ahead of the Fox a viewer here could open.
    # A digit glued to the brand is how a listings page writes these, and
    # a word boundary after the brand matched none of them: ITV1 — which
    # carries England and the FA Cup — was ranked below a Danish channel,
    # and fifteen of fifty-four real spellings sat in the wrong tier for
    # this one reason.
    check("TWO", "ITV is British however the number is attached",
          [today.where_from(name) for name in
           ("ITV", "ITV 1", "ITV1", "ITV4", "ITVX", "STV")],
          [1, 1, 1, 1, 1, 1])
    check("TWO", "and so are BBC1 and Channel4 written closed up",
          [today.where_from(name) for name in
           ("BBC One", "BBC1", "BBC2", "Channel 4", "Channel4", "C4")],
          [1, 1, 1, 1, 1, 1])
    check("TWO", "an American abbreviation is still American",
          [today.where_from(name) for name in
           ("FS1", "FS2", "ESPN2", "NBCSN", "CBSSN", "TSN1")],
          [2, 2, 2, 2, 2, 2])
    # "fox" begins Foxtel and "sky" begins Sky Sport NZ. Both are safe
    # ONLY because Australia is tested before Britain and America.
    check("TWO", "Foxtel is still Australian, not American",
          [today.where_from(name) for name in
           ("Foxtel", "Fox Sports Australia", "Sky Sport NZ",
            "Sky Sport 1 NZ")],
          [4, 4, 4, 4])
    check("TWO", "TNT and BBC are British",
          [today.where_from(name)
           for name in ("TNT Sports 1", "Sky Sports Main Event",
                        "Premier Sports 1")],
          [1, 1, 1])
    check("TWO", "beIN's English commentary is Doha's, but ranked last",
          today.where_from("beIN SPORTS 1 EN"), 6)
    check("TWO", "and Canada rides with America",
          [today.where_from(name)
           for name in ("TSN 4", "Sportsnet One", "CBC", "RDS")],
          [2, 2, 2, 2])
    check("TWO", "while beIN's French feed goes below everywhere else",
          today.where_from("beIN SPORTS FR 2"), 6)
    # And Xtra with them: it is the same match beIN is already showing,
    # on an extra channel.
    check("TWO", "beIN Xtra is never a first choice",
          today.channels_of({"channels": ["beIN SPORTS Xtra 1",
                                          "beIN SPORTS 4 TR", "Ligue1+",
                                          "Sportsnet One"]}),
          "Sportsnet One · beIN 4 TR · Ligue1+ +1")
    check("TWO", "but a match that has only Xtra still names it",
          today.channels_of({"channels": ["beIN SPORTS Xtra 1"]}),
          "beIN Xtra 1")
    check("TWO", "Doha's unmarked beIN is the Arabic one",
          today.where_from("beIN SPORTS 1"), 0)
    check("TWO", "an Arabic name needs no list to be recognised",
          today.where_from("\u0642\u0646\u0627\u0629 \u0627\u0644\u0643"
                           "\u0623\u0633"), 0)
    # Ordering decides which names win the two slots, and nothing else. A
    # row holding one Arabic channel and one British still shows both.
    check("TWO", "a British channel is not hidden, only ranked",
          today.channels_of({"channels": ["Premier Sports 1",
                                          "MBC Shahid Sports"]}),
          "MBC Shahid \u00b7 Premier Sports 1")
    # The second slot is not spent on more of the first. Sorting alone
    # gave "beIN SPORTS 3 · beIN SPORTS 2" — one broadcaster twice — with
    # the Fox that was collected for that match behind the "+6". Two
    # slots and Arabic ranked first meant the American channels this
    # guide went and found could almost never be seen.
    check("TWO", "each slot goes somewhere the ones before it are not",
          today.channels_of({"channels": ["beIN SPORTS 3", "beIN SPORTS 2",
                                          "USA Network", "beIN SPORTS 1 TR",
                                          "Sky Sports+"]}),
          "beIN 3 · Sky+ · USA Network +2")
    check("TWO", "Arabic, British, American — the three a viewer can open",
          today.channels_of({"channels": ["beIN SPORTS 3", "beIN SPORTS 2",
                                          "USA Network", "beIN SPORTS 1 EN",
                                          "beIN SPORTS 1 TR", "Sky Sports+"]}),
          "beIN 3 · Sky+ · USA Network +3")
    check("TWO", "and still in the reader's order: American before Turkish",
          today.in_the_readers_order(["beIN SPORTS 3", "beIN SPORTS 1 TR",
                                      "Fox Sports 1"])[1], "Fox Sports 1")
    check("TWO", "a row that is all one kind keeps the source's order",
          today.channels_of({"channels": ["beIN SPORTS 3", "beIN SPORTS 2",
                                          "beIN SPORTS 5"]}),
          "beIN 3 · beIN 2 · beIN 5")
    check("TWO", "nothing is dropped by the promotion",
          sorted(today.in_the_readers_order(
              ["Sky Sports+", "beIN SPORTS 3", "Fox Sports 1"])),
          ["Fox Sports 1", "Sky Sports+", "beIN SPORTS 3"])
    # Promotion moves one channel and re-orders nothing else: within a
    # tier the source's own order still stands, so a source that lists
    # the channel most likely to carry the match first keeps that.
    ranked = today.in_the_readers_order(["beIN SPORTS 5", "beIN SPORTS 1",
                                         "Fox Sports 1", "beIN SPORTS 2"])
    check("TWO", "the promoted channel takes the second slot",
          ranked[:2], ["beIN SPORTS 5", "Fox Sports 1"])
    check("TWO", "and within one tier the source's own order is kept",
          [name for name in ranked if today.where_from(name) == 0],
          ["beIN SPORTS 5", "beIN SPORTS 1", "beIN SPORTS 2"])

    # SPORTS says nothing. A photograph of the screen settled it:
    # "Burnley - Middles…" clipped, because "beIN SPORTS Xtra 1" and
    # "beIN SPORTS 1" had eaten the row. The word is on nearly every
    # channel here and tells one from another nowhere.
    check("TWO", "beIN keeps its number and loses its Sports",
          [today.shorter(name) for name in
           ("beIN SPORTS 1", "beIN SPORTS 3 TR", "beIN SPORTS Xtra 2",
            "beIN SPORTS 1 EN", "beIN SPORTS US")],
          ["beIN 1", "beIN 3 TR", "beIN Xtra 2", "beIN 1 EN", "beIN US"])
    check("TWO", "and so do Sky, MBC Shahid, Thmanyah, TNT and Alwan",
          [today.shorter(name) for name in
           ("Sky Sports Main Event", "MBC Shahid Sports",
            "Thmanyah Channels", "TNT Sports 1", "Alwan Sport 1")],
          ["Sky Main Event", "MBC Shahid", "Thmanyah", "TNT 1", "Alwan 1"])
    # Premier is not a channel. Neither is ON on its own, and Sportsnet
    # only contains the letters — the cost of guessing wrong here is a
    # viewer sent to a name that exists nowhere.
    check("TWO", "Premier keeps its Sports, because Premier 1 is nothing",
          [today.shorter(name) for name in
           ("Premier Sports 1", "Premier Player", "ON Sport",
            "Sportsnet One", "Fox Sports 1")],
          ["Premier Sports 1", "Premier Player", "ON Sport",
           "Sportsnet One", "Fox Sports 1"])
    check("TWO", "a name that is nothing BUT the generic word survives",
          today.shorter("beIN SPORTS"), "beIN")
    # S Sport is Turkish, and "S" on its own is not a channel — the same
    # reason Premier keeps its Sports. It is safe because the list holds
    # brands rather than initials, and this is what holds it there.
    # beIN's own feeds in another language rank below everywhere else, so
    # a TNT or a TSN takes the slot instead — which is what was asked for.
    check("TWO", "a TNT takes the slot beIN's English feed had",
          today.channels_of({"channels": ["beIN SPORTS 3", "beIN SPORTS 1 EN",
                                          "TNT Sports 1", "USA Network"]}),
          "beIN 3 · TNT 1 · USA Network +1")
    check("TWO", "and so does a TSN",
          today.channels_of({"channels": ["beIN SPORTS 4", "beIN SPORTS FR 2",
                                          "TSN 4"]}),
          "beIN 4 · TSN 4 · beIN FR 2")
    check("TWO", "they rank below even the rest of the world",
          [today.where_from(name) for name in
           ("Ligue1+", "beIN SPORTS Xtra 1", "beIN SPORTS 1 EN",
            "beIN SPORTS FR 2")],
          [5, 6, 6, 6])
    # Ranked last, NOT deleted. 268 of the 1001 fixtures in Doha's guide
    # name beIN SPORTS EN 1 and nothing else — Manchester United,
    # Liverpool, Arsenal, Barcelona. Deleting would turn every one of
    # those from a channel that works into "لم تُعلن القناة".
    check("TWO", "a match that has only that feed still names it",
          today.channels_of({"channels": ["beIN SPORTS 1 EN"]}), "beIN 1 EN")
    check("TWO", "and it is still a real channel, not junk",
          today.real_channels(["beIN SPORTS 1 EN"]), ["beIN SPORTS 1 EN"])

    # A page is not something a television can be turned to, and neither
    # is a player. "BBC Sport Website" reached the board and took one of
    # three slots from a broadcaster that is; BBC iPlayer and Premier
    # Player are the same page with a different name on it.
    check("TWO", "a player is not a channel either",
          today.real_channels(["BBC iPlayer", "Premier Player",
                               "TNT Sports 1"]),
          ["TNT Sports 1"])
    check("TWO", "a website is not a channel",
          today.channels_of({"channels": ["MBC Shahid Sports", "TNT Sports 1",
                                          "BBC Sport Website"]}),
          "MBC Shahid · TNT 1")
    check("TWO", "nor is an address",
          today.real_channels(["fuboTV.com", "skysports.co.uk", "beIN SPORTS 1"]),
          ["beIN SPORTS 1"])
    check("TWO", "S Sport keeps its Sport, in every spelling",
          [today.shorter(name) for name in
           ("S Sport", "S Sport 2", "S Sport Plus", "S Sports 1")],
          ["S Sport", "S Sport 2", "S Sport Plus", "S Sports 1"])
    check("TWO", "and S Sport is Turkish however it is written",
          [today.where_from(name) for name in
           ("S Sport", "S Sport 2", "S Sports 1", "S Sport Plus")],
          [3, 3, 3, 3])
    # Shortening runs after the ordering and must not disturb it.
    check("TWO", "a shortened name still lands in its own tier",
          [today.where_from(today.shorter(name)) for name in
           ("beIN SPORTS 1", "Sky Sports+", "beIN SPORTS US",
            "beIN SPORTS 3 TR", "Thmanyah Channels")],
          [0, 1, 2, 3, 0])
    check("TWO", "and shortening an already short name changes nothing",
          today.shorter(today.shorter("beIN SPORTS Xtra 2")), "beIN Xtra 2")

    # And the build says out loud which rows still fall short, because
    # that is what picks the next source.
    when = datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc)
    rows = [{"start": when, "title": "A - B", "competition": "x",
             "channels": ["beIN SPORTS 1", "Fox Sports 1"]},
            {"start": when, "title": "C - D", "competition": "x",
             "channels": ["DAZN"]},
            {"start": when, "title": "E - F", "competition": "x",
             "channels": []}]
    today.say_which_rows_are_thin(rows)      # must not raise

    # "لم تُعلن القناة" is a sentence, and real_channels() has no reason
    # to know that — it refuses apps and shops, not Arabic. So the count
    # is taken BEFORE the placeholder is written in, and if that order
    # ever reverses every unannounced row starts reporting as answered.
    check("TWO", "the placeholder would pass for a channel if it got there",
          today.real_channels([today.CHANNEL_UNANNOUNCED]),
          [today.CHANNEL_UNANNOUNCED])
    source = inspect.getsource(today.build)
    check("TWO", "so the thin rows are counted before it is written in",
          source.index("say_which_rows_are_thin")
          < source.index("CHANNEL_UNANNOUNCED"), True)


def gate_a_board_says_which_day_it_is() -> None:
    """Three boards go past, and each says which of the three it is.

    The channel is called "مباريات اليوم", and that was set in 40px across
    the top of every board — tomorrow's and the day after's included. So
    the largest words on a Friday board said "today", and the only thing
    that disagreed was a 21px muted weekday in a corner. A viewer could
    not tell the boards apart, and the one thing they were told outright
    was wrong.

    The relative word answers it and now sits in the middle of the
    header. No digits in the badge: the date is already set on the right,
    and a number inside Arabic is the one thing that can come out
    reversed.
    """
    print("\nA board says which day it is")
    from datetime import date, datetime, timezone

    import match_board
    import today_matches_epg as today

    viewer = today.VIEWER
    # Late in the viewer's evening, where a UTC instant and the viewer's
    # date disagree — the reading that has to be the viewer's.
    now = datetime(2026, 9, 3, 4, 0, tzinfo=timezone.utc)
    here = now.astimezone(viewer).date()
    check("DAY", "the viewer's own date is the one called today",
          match_board.day_badge(here, now, viewer, "س"), "اليوم · س")
    check("DAY", "the next one is غداً",
          match_board.day_badge(date(here.year, here.month, here.day + 1),
                                now, viewer, "س"), "غداً · س")
    check("DAY", "and the one after that is بعد غد",
          match_board.day_badge(date(here.year, here.month, here.day + 2),
                                now, viewer, "س"), "بعد غد · س")
    check("DAY", "past the third day it says the weekday and guesses nothing",
          match_board.day_badge(date(here.year, here.month, here.day + 5),
                                now, viewer, "الاثنين"), "الاثنين")
    check("DAY", "and no digit goes inside the Arabic, where it could reverse",
          any(ch.isdigit()
              for ch in match_board.day_badge(here, now, viewer, "الخميس")),
          False)

    # Every board the guide draws gets one of the three words, because the
    # window is exactly three days long.
    days = today.days_of(now)
    check("DAY", "every day the guide draws has a word for itself",
          [day for day in days
           if not match_board.RELATIVE_DAY.get((day - here).days)], [])


def gate_the_jordanian_league_is_read() -> None:
    """The league that is in none of the other sources, from its federation.

    Measured before anything was built: livefootballtv offered 97
    fixtures, live-footballontv 54, yallakora 36, livesoccertv 79 and
    kooora 6 — 272 between them and not one Jordanian, matched on the
    CLUBS and not only on the competition. This repository's own
    jordan_sports_epg.xml holds 31 programmes and no fixture at all.

    Two things here would each put something false on the screen.

    A FINISHED MATCH IS NOT A FIXTURE. The federation prints played and
    upcoming matches in the same markup, telling them apart only by what
    sits between the clubs: "VS" before, a score afterwards. Read
    carelessly, a match played yesterday goes on the board as tonight's.

    AND THE UNDER-16 LEAGUE IS NOT WHAT A BOARD IS FOR. It is published
    beside the senior one, more of it than of the league anybody asked
    for, and a board that fits twelve rows would spend them on schools.

    The date needs no inference at all — the page writes 2026-09-03. The
    clock is Amman's, which is this file's one assumption, and a narrow
    one: a national federation publishing its own domestic league in its
    own country's time.
    """
    print("\nThe Jordanian league is read — jfa.jo")
    from datetime import timezone

    import jordan_football
    import today_matches_epg as today

    # The federation's shape, copied verbatim from the served page — a
    # header row carrying the competition and the time, then a row of
    # clubs, then a rule, repeating. Four guesses were made about this
    # markup before it was simply printed and read.
    def head(comp, grade, day, clock):
        extra = f'<span class="haly2">{grade}</span>' if grade else ""
        return (f'<tr><td colspan="5" height="22">'
                f'<span class="haly">{comp}</span>{extra}'
                f'<span class="haly1">{day}  '
                f'<i aria-hidden="true" class="fa fa-calendar"></i> '
                f'| {clock} <i aria-hidden="true" class="fa fa-clock-o">'
                f'</i></span></td></tr>')

    def clubs(home, verdict, away):
        return (f'<tr><td align="left" height="80" width="25%">'
                f'<span class="team1">{home}</span></td>'
                f'<td align="center" class="plogo1"><img class="logo1"/></td>'
                f'<td align="center"><span class="rrresult">{verdict}'
                f'</span></td>'
                f'<td align="center" class="plogo2"><img class="logo2"/></td>'
                f'<td align="right" width="25%">'
                f'<span class="team2">{away}</span></td></tr>'
                f'<tr><td bgcolor="#c6c3c3" colspan="5" height="2">'
                f'</td></tr>')

    page = "<table>" + "".join([
        head("دوري الناشئين ت16", "", "2026-09-03", "17:00"),
        clubs("المدرسة الانجليزية", "VS", "الجزيرة"),
        head("كأس الأردن CFI", "", "2026-09-03", "18:00"),
        clubs("الوحدات", "VS", "معان"),
        # A youth match published UNDER a professional heading. The
        # reader photographed exactly this — "عمان FC - الكرمل" on the
        # board as league football — and neither club plays the league.
        head("الدوري الأردني للمحترفين - CFI", "", "2026-09-03", "18:30"),
        clubs("عمان FC", "VS", "الكرمل"),
        head("الدوري الأردني للمحترفين - CFI", "", "2026-09-03", "19:00"),
        clubs("البقعة", "VS", "دوقرة"),
        # The national team, but the under-20s: the age grade is in a
        # SECOND span, so reading only the first would take it for a
        # senior qualifier.
        head("تصفيات كأس آسيا", "منتخب الشباب ت20", "2026-09-03", "20:30"),
        clubs("الأردن", "VS", "البحرين"),
        # Played already — the same markup, a score instead of VS.
        head("الدوري الأردني للمحترفين - CFI", "", "2026-09-01", "20:00"),
        clubs("الوحدات", "1 - 0", "الفيصلي"),
    ]) + "</table>"

    read = jordan_football.collect(page)
    check("JOR", "the professional league and the cup are read",
          [event["title"] for event in read],
          ["الوحدات - معان", "البقعة - دوقرة"])
    check("JOR", "a match already played is not a fixture",
          any("الفيصلي" in event["title"] for event in read), False)

    # THE HEADING LIES, and a reader caught it on a television. "عمان FC
    # - الكرمل" was published under الدوري الأردني للمحترفين and both of
    # those are youth sides. A filter that reads only the heading believes
    # it, so the clubs are asked as well: ten clubs play this league and
    # no eleventh can appear in it.
    check("JOR", "a youth match under a professional heading is refused",
          [e["title"] for e in read if "الكرمل" in e["title"]], [])
    check("JOR", "the ten clubs of the league are known from its table",
          [jordan_football.in_the_league(name) for name in
           ("الرمثا", "الجزيرة", "الحسين", "الوحدات", "العربي",
            "الفيصلي", "شباب الأردن", "البقعة", "السلط", "دوقرة")],
          [True] * 10)
    check("JOR", "and nobody else is",
          [jordan_football.in_the_league(name) for name in
           ("عمان FC", "الكرمل", "كفرسوم", "جرش", "معان")],
          [False] * 5)
    # The cup is the one that legitimately draws lower clubs in, so ONE
    # professional side is enough there — which still refuses the
    # preliminary round this channel does not televise.
    check("JOR", "the cup keeps a real tie and refuses an amateur one",
          [jordan_football.the_clubs_belong("كأس الأردن", *pair) for pair in
           (("الوحدات", "معان"), ("كفرسوم", "جرش"))],
          [True, False])
    check("JOR", "the under-16 league is not on a board of twelve rows",
          any("المدرسة" in event["title"] for event in read), False)
    check("JOR", "and the age grade in a SECOND span still counts",
          any("البحرين" in event["title"] for event in read), False)

    # THE ONE THAT MATTERS. The header and the clubs are separate rows,
    # so the pairing is by POSITION — the arrangement that once stamped
    # 1876 fixtures with a single date. Two matches, two times.
    check("JOR", "each fixture keeps its OWN time, not the one above",
          [f"{event['start']:%Y-%m-%d %H:%M}" for event in read],
          ["2026-09-03 18:00", "2026-09-03 19:00"])
    check("JOR", "the day is read, never inferred from an ordering",
          f"{read[0]['start']:%Y-%m-%d}", "2026-09-03")
    check("JOR", "19:00 in Amman is 16:00 UTC",
          f"{read[1]['start'].astimezone(timezone.utc):%Y-%m-%d %H:%M}",
          "2026-09-03 16:00")
    check("JOR", "the competition comes through in Arabic",
          read[1]["competition"], "الدوري الأردني للمحترفين - CFI")

    # A header is CONSUMED by the clubs that follow it, so a row of clubs
    # with none of its own can never inherit the match above's time.
    orphan = ("<table>"
              + head("كأس الأردن CFI", "", "2026-09-03", "18:00")
              + clubs("الوحدات", "VS", "معان")
              + clubs("البقعة", "VS", "دوقرة")
              + "</table>")
    check("JOR", "a fixture with no header of its own is refused",
          [event["title"] for event in jordan_football.collect(orphan)],
          ["الوحدات - معان"])

    # jfa.jo prints no channel, but one IS known: the Jordan Radio and
    # Television Corporation's channel holds the domestic game
    # exclusively — league, cup, super cup — so "لم تُعلن القناة" beside
    # those was under-reporting something settled. The name is the one
    # this repository already publishes in jordan_sports_epg.xml, so the
    # board and the guide agree.
    check("JOR", "the domestic game names the channel that carries it",
          [event["channels"] for event in read],
          [["الأردن الرياضية"], ["الأردن الرياضية"]])
    check("JOR", "and it is an Arabic channel, printed whole",
          today.channels_of({"channels": ["الأردن الرياضية"]}),
          "الأردن الرياضية")
    # The national team is NOT included: its qualifiers are sold
    # competition by competition and land on beIN or elsewhere, so those
    # keep the placeholder until a listings page says otherwise.
    check("JOR", "a national-team qualifier is not assumed onto it",
          [jordan_football.carried_by(name) for name in
           ("تصفيات كأس آسيا", "كأس العرب", "تصفيات كأس العالم")],
          [[], [], []])
    check("JOR", "the guide wants it",
          [today.wanted(event) for event in read], [True, True])
    check("JOR", "and a row with no channel is still a row",
          today.channels_of({"channels": []}), "")

    # A page that answers with nothing must cost nothing.
    check("JOR", "an empty page is not an error",
          jordan_football.collect("<table></table>"), [])

    # The age grades, refused where the CHANNEL is decided and not only
    # where the board picks its fixtures.
    #
    # Youth football has no regular television at all: the federation's
    # own YouTube carries selected ties and this channel takes a final or
    # a title decider. "كأس الأردن للناشئين" matched the cup's name and
    # was handed the channel; nothing but the board's own youth filter
    # running first kept it off the screen, and an ordering is not a
    # guarantee.
    check("JOR", "a youth tie is not handed the senior channel",
          [jordan_football.carried_by(name) for name in
           ("كأس الأردن للناشئين تحت 19", "دوري الناشئين ت16",
            "كأس الأردن للأشبال", "دوري أندية النخبة للناشئين ت17")],
          [[], [], [], []])
    check("JOR", "while the senior competitions still name it",
          [jordan_football.carried_by(name) for name in
           ("الدوري الأردني للمحترفين - CFI", "كأس الأردن",
            "درع الاتحاد", "كأس السوبر الأردني")],
          [["الأردن الرياضية"]] * 4)

    # The board carries the professional game and the national team, and
    # the reader drew that line himself: "خلي المحترفين و مباريات الاردن
    # المنتخب و بس". The first division is not professional football and
    # this channel does not carry it, so those fixtures used to sit on the
    # board with "لم تُعلن القناة" beside them, taking rows from the
    # matches somebody opened it to find.
    check("JOR", "the professional game and the national team are shown",
          [jordan_football.wanted_here(name) for name in
           ("الدوري الأردني للمحترفين - CFI", "كأس الأردن", "درع الاتحاد",
            "كأس السوبر الأردني", "تصفيات كأس العالم", "كأس العرب")],
          [True] * 6)
    check("JOR", "and nothing else the federation publishes beside them",
          [jordan_football.wanted_here(name) for name in
           ("دوري الدرجة الأولى", "دوري الدرجة الثانية",
            "دوري الناشئين ت16", "كأس الأردن للأشبال")],
          [False] * 4)
    check("JOR", "the national team is shown but never assumed onto it",
          [jordan_football.carried_by(name) for name in
           ("تصفيات كأس العالم", "كأس العرب")],
          [[], []])


def gate_a_guide_repeating_its_own_name_is_measured() -> None:
    """A row whose title is the channel's name is the guide saying nothing.

    jordan_sports_epg.xml is the worked example and it is the exact
    blindness health_check exists to prevent: twenty-six of its
    twenty-nine rows read "الأردن الرياضية" and the other three were one
    talk show — a Jordan Sports guide with no Jordanian football in it —
    and it measured 0% stand-in against a 15% ceiling, run after run.

    The rule above it, one-title-for-a-whole-channel, stops seeing this
    the moment a single real programme joins in. So the channel's own
    name is read from the file's own <display-name>, both halves of it,
    because the filler writes only the Arabic half of "Jordan Sport |
    الأردن الرياضية".
    """
    import health_check

    guide = (
        '<tv>'
        '  <channel id="C"><display-name>Jordan Sport | الأردن الرياضية'
        '</display-name></channel>'
        '  <programme channel="C" start="20260903000000 +0000" '
        'stop="20260903120000 +0000"><title>الأردن الرياضية</title></programme>'
        '  <programme channel="C" start="20260903120000 +0000" '
        'stop="20260903180000 +0000"><title>الأردن الرياضية</title></programme>'
        '  <programme channel="C" start="20260903180000 +0000" '
        'stop="20260903200000 +0000"><title>رياضة كافيه</title></programme>'
        '  <programme channel="C" start="20260903200000 +0000" '
        'stop="20260903220000 +0000"><title>الوحدات - الفيصلي</title></programme>'
        '</tv>')
    here = os.path.join(tempfile.gettempdir(), "gate_own_name_epg.xml")
    with open(here, "w", encoding="utf-8") as handle:
        handle.write(guide)

    check("NAME", "the channel's own name counts as filler",
          health_check.standin_share(here), (2, 4))
    check("NAME", "and a real fixture beside it still counts as content",
          health_check.standin_share(here)[0] < 4, True)

    # Both halves of a two-language display-name, and nothing else.
    names = health_check.channel_names(
        ET.fromstring(guide))["C"]
    check("NAME", "both halves of the name are known",
          (health_check.folded("الأردن الرياضية") in names,
           health_check.folded("Jordan Sport") in names,
           health_check.folded("رياضة كافيه") in names),
          (True, True, False))


def gate_a_long_wait_says_how_long() -> None:
    """Seven identical rows in a grid read as seven broadcasts.

    Reported from a television, and the guide was not wrong about the
    football: ON Sport 1 held the two legs of a CAF tie eight days apart,
    and every day between them carried one row saying
    "⏰ التالي: الزمالك - AS Port". One row a day rather than one an hour
    is the right shape for a wait. Seven copies of the same sentence is
    not — down a grid it reads as the same match being shown every day at
    the same hour, which is exactly how it was reported.

    The wait now carries the one thing that differs between those days.
    """
    from datetime import datetime, timedelta, timezone

    import update_onsport_epg as onsport

    tie = {"home": "الزمالك", "away": "AS Port",
           "start": datetime(2026, 9, 12, 17, 0, tzinfo=timezone.utc)}
    days = [onsport.filler_title(
                tie, datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
                     + timedelta(days=n))
            for n in range(4)]

    check("WAIT", "no two waiting days say the same thing",
          len(set(days)), len(days))
    check("WAIT", "and each says how long is left",
          days,
          ["⏰ التالي بعد 3 أيام · الزمالك - AS Port",
           "⏰ التالي بعد يومين · الزمالك - AS Port",
           "⏰ التالي غداً · الزمالك - AS Port",
           "⏰ التالي اليوم · الزمالك - AS Port"])

    # Arabic counts in threes, and a guide that writes "بعد 2 أيام" reads
    # as machinery. 11 and up take the singular accusative.
    check("WAIT", "the number is the one Arabic uses",
          [onsport.how_far_off(n) for n in (0, 1, 2, 3, 10, 11)],
          ["اليوم", "غداً", "بعد يومين", "بعد 3 أيام", "بعد 10 أيام",
           "بعد 11 يوماً"])

    # Still a countdown, never a stand-in: it exists only because a real
    # fixture was found, and health_check counts on that distinction.
    import health_check
    check("WAIT", "a wait is not counted as the guide knowing nothing",
          bool(health_check.STANDIN_TITLE.search(days[0])), False)
    check("WAIT", "while nothing announced at all still is",
          bool(health_check.STANDIN_TITLE.search(
              onsport.filler_title(
                  None, datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)))),
          True)


def gate_turkeys_own_league_is_read() -> None:
    """Three matches on a television, on no page this board read.

    Iğdırspor - Manisa FK, Bodrumspor - Esenler Erokspor and Bursaspor -
    İstanbulspor, all on TRT Spor, all missing. Not filtered out: the
    day's dropped-competitions report named eight competitions —
    Reserve League, Liga FUTVE, Qatar Stars and five more — and no
    Turkish league among them. They were never offered.

    Spor Ekranı has them, and had them all along: 75 broadcasts a day,
    every one discarded as a fixture because this source was only ever
    asked which channel a match ALREADY on the board is on.

    Two structural facts make them safe to take, and the gate holds both.
    """
    import spor_ekrani

    page = (
        '<script type="application/ld+json">['
        '{"@type":"BroadcastEvent",'
        ' "publishedOn":[{"name":"TRT Spor"},{"name":"Bein Sports 2"}],'
        ' "broadcastOfEvent":{"name":"Iğdırspor - Manisa FK",'
        '   "startDate":"2026-09-03T17:00:00+03:00",'
        '   "homeTeam":{"name":"Iğdırspor"},"awayTeam":{"name":"Manisa FK"},'
        '   "organizer":{"url":"https://www.sporekrani.com/home/league/'
        'trendyol-1.-lig"}}},'
        '{"@type":"BroadcastEvent","publishedOn":{"name":"Eurosport"},'
        ' "broadcastOfEvent":{"name":"J.Faria - C.Alcaraz",'
        '   "startDate":"2026-09-03T04:00:00+03:00",'
        '   "homeTeam":{"name":"J.Faria"},"awayTeam":{"name":"C.Alcaraz"},'
        '   "organizer":{"url":"https://www.sporekrani.com/home/league/'
        'tenis-amerika-acik"}}},'
        '{"@type":"BroadcastEvent",'
        ' "broadcastOfEvent":{"name":"Saratoga",'
        '   "startDate":"2026-09-03T19:55:00+03:00"}},'
        '{"@type":"BroadcastEvent","publishedOn":{"name":"beIN Sports 1"},'
        ' "broadcastOfEvent":{"name":"beIN Ana Haber",'
        '   "startDate":"2026-09-03T18:00:00+03:00"}}'
        ']</script>')
    read = spor_ekrani.collect_fixtures(page)

    check("TR", "the league nobody else offered is read",
          [event["title"] for event in read], ["Iğdırspor - Manisa FK"])
    check("TR", "with every channel the page names, marked Turkish",
          read[0]["channels"], ["TRT Spor TR", "Bein Sports 2 TR"])
    check("TR", "and the competition is read, not inferred from the clubs",
          read[0]["competition"], "TFF 1. Lig")
    check("TR", "17:00 in Istanbul is 14:00 UTC",
          f"{read[0]['start']:%H:%M}", "14:00")

    # A FIXTURE HAS TWO SIDES. A horse race meeting and a news bulletin
    # are published in the same shape on the same page, and a name alone
    # would put Saratoga and "beIN Ana Haber" on a board of football.
    check("TR", "a race meeting is not a fixture",
          [e["title"] for e in read if "Saratoga" in e["title"]], [])
    check("TR", "and neither is the evening news, channel or no channel",
          [e["title"] for e in read if "Haber" in e["title"]], [])

    # The page's tennis, padel and basketball belong on the OTHER board.
    # This one takes Turkish football and says so by slug.
    check("TR", "the tennis on the same page stays off a football board",
          [e["title"] for e in read if "Alcaraz" in e["title"]], [])

    # And the board's own filter must recognise what comes back, or the
    # fixtures arrive and are dropped one step later.
    import today_matches_epg as today
    check("TR", "the board's filter wants it",
          today.wanted({"competition": "TFF 1. Lig",
                        "title": "Iğdırspor - Manisa FK",
                        "channels": ["TRT Spor TR"]}),
          True)

    check("TR", "an empty page is not an error",
          spor_ekrani.collect_fixtures("<html></html>"), [])


def gate_the_other_sports_name_a_real_channel() -> None:
    """The second board's source, and the two traps it walks past.

    Eight pages were asked for F1, darts, boxing, MMA, MotoGP, tennis,
    golf and the Rugby World Cup. Six are no use, and the instructive
    pair are the ones that looked perfect: pdc.tv lists 45 darts events
    and motogp.com 878 MotoGP ones, and NEITHER NAMES A BROADCASTER. A
    calendar is not a listing, and no board here may put a channel on an
    event unless somebody published it.

    wheresthematch does, in a row that carries everything at once — and
    the time is an INSTANT, <time datetime="...+01:00">, not a printed
    clock to be placed in a timezone. That distinction has cost this
    project a day and then an hour on two other sources.
    """
    import world_sport_on_tv as world

    def row(fixture, iso, competition, channels, home="", away=""):
        marks = "".join(f'<a href="#">{c}</a>' for c in channels)
        return (f'<tr><td class="home-team">{home}</td>'
                f'<td class="fixture-details">{fixture}</td>'
                f'<td class="away-team">{away}</td>'
                f'<td class="start-details">'
                f'<time datetime="{iso}">clock</time></td>'
                f'<td class="competition-name">{competition}</td>'
                f'<td class="channel-details">{marks}</td></tr>')

    def rules(name):
        return [page[2:] for page in world.PAGES if page[1] == name][0]

    f1 = world.collect(
        "<table>" + row("Italian Grand Prix Practice 1 - Monza",
                        "2026-09-04T11:30:00+01:00", "F1 2026 season",
                        ["Sky Sports F1", "Sky Sports Main Event"])
        + "</table>", "F1", *rules("F1"))
    check("WORLD", "the grand prix is read with every channel named",
          (f1[0]["title"], f1[0]["channels"]),
          ("Italian Grand Prix Practice 1 - Monza",
           ["Sky Sports F1", "Sky Sports Main Event"]))
    check("WORLD", "and 11:30 in London is 10:30 UTC, from the attribute",
          f"{f1[0]['start']:%Y-%m-%d %H:%M}", "2026-09-04 10:30")

    # THE HEADING LIES HERE TOO, and it is the Jordanian youth cup again
    # in another language: every row on the MotoGP page today reads "FIM
    # JuniorGP World Championship" and is filed under the competition
    # "MotoGP 2026 season". Reading the page would put schoolboy racing
    # on a board asked for MotoGP.
    moto = world.collect(
        "<table>"
        + row("FIM JuniorGP World Championship Moto3 Race 1",
              "2026-09-06T09:45:00+01:00", "MotoGP 2026 season",
              ["TNT Sports 7"])
        + row("San Marino Grand Prix Race - Misano",
              "2026-09-13T13:00:00+01:00", "MotoGP 2026 season",
              ["TNT Sports 2"])
        + "</table>", "MotoGP", *rules("MotoGP"))
    check("WORLD", "a junior championship is not MotoGP",
          [event["title"] for event in moto],
          ["San Marino Grand Prix Race - Misano"])

    # The reader asked for the Rugby WORLD CUP, not the rugby season.
    rugby = world.collect(
        "<table>"
        + row("England v Wales", "2026-09-20T15:00:00+01:00",
              "Premiership Rugby Cup", ["TNT Sports 1"], "England", "Wales")
        + row("South Africa v New Zealand", "2026-10-01T16:00:00+01:00",
              "Rugby World Cup", ["ITV1"], "South Africa", "New Zealand")
        + "</table>", "Rugby", *rules("Rugby"))
    check("WORLD", "the World Cup is kept and the league season is not",
          [event["title"] for event in rugby],
          ["South Africa - New Zealand"])

    # A row with no instant is refused rather than dated from the page,
    # and a row that says the channel is not known yet names none.
    blind = world.collect(
        '<table><tr><td class="fixture-details">Some Fight</td>'
        '<td class="start-details">Saturday</td>'
        '<td class="competition-name">Boxing</td>'
        '<td class="channel-details"><a>TBC</a></td></tr></table>',
        "Boxing", None, None)
    check("WORLD", "a row with no instant is refused, never guessed at",
          blind, [])
    tbc = world.collect(
        "<table>" + row("Some Fight", "2026-09-20T20:00:00+01:00",
                        "Boxing", ["TBC"]) + "</table>",
        "Boxing", None, None)
    check("WORLD", "and 'TBC' is not a channel", tbc[0]["channels"], [])

    check("WORLD", "an empty page is not an error",
          world.collect("<html></html>", "F1", *rules("F1")), [])

    # A PRELIM IS A ROW LIKE ANY OTHER, and this holds the door open.
    #
    # A UFC card is three broadcasts — early prelims, prelims, main card
    # — each with its own start, and the reader asked for all three. This
    # source does not split them: its UFC page was printed row by row and
    # carries six, one per card. The words "prelims" and "main card" are
    # in the page, twice and four times, and both are in its navigation
    # rather than in a row; counting a word in a page is not finding one.
    #
    # Nothing can be written against rows that do not exist. What CAN be
    # done is make sure that the day they exist they are not thrown away
    # — so the MMA and boxing pages filter on nothing at all, and this
    # proves it with rows named the way a card names them.
    for card in ("UFC Fight Night Early Prelims",
                 "UFC 331 Prelims - Van vs Pantoja 2",
                 "Live Boxing Prelims Canelo vs Mabilli"):
        sport = "Boxing" if "Boxing" in card else "MMA"
        got = world.collect(
            "<table>" + row(card, "2026-09-20T00:00:00+01:00",
                            "Ultimate Fighting Championship",
                            ["TNT Sports 1"]) + "</table>",
            sport, *rules(sport))
        check("WORLD", f"'{card[:34]}' reaches the board",
              [event["title"] for event in got], [card])

    # BASKETBALL, wired before the season so that it starts on its own.
    # The NBA opens in October: this page reads NOTHING today, and that
    # is the source being right rather than broken — which is why the
    # empty-page check above sits next to these two.
    basketball = ("<table>"
                  + row("Lakers v Celtics", "2026-10-21T00:30:00+01:00",
                        "NBA Regular Season", ["Sky Sports Main Event"],
                        "Lakers", "Celtics")
                  + row("Germany v Turkey", "2026-09-14T19:00:00+01:00",
                        "FIBA EuroBasket", ["Sky Sports Action"],
                        "Germany", "Turkey")
                  + row("Sheffield Sharks v London Lions",
                        "2026-09-19T19:30:00+01:00",
                        "British Basketball League", ["Sky Sports Arena"],
                        "Sheffield Sharks", "London Lions")
                  + "</table>")
    check("WORLD", "the NBA game is kept and the British league is not",
          [event["title"] for event in
           world.collect(basketball, "NBA", *rules("NBA"))],
          ["Lakers - Celtics"])
    check("WORLD", "EuroBasket is FIBA, and the NBA is not FIBA",
          [event["title"] for event in
           world.collect(basketball, "FIBA", *rules("FIBA"))],
          ["Germany - Turkey"])
    check("WORLD", "an off-season basketball page is empty, not broken",
          world.collect("<table></table>", "NBA", *rules("NBA")), [])


def gate_the_american_game_names_its_network() -> None:
    """"This one is on NBC" — asked for in those words, and hard to get.

    Nine listings pages were asked and every one is shut: livesportsontv
    answers 200 with 913 KB and NOTHING holding a channel under anything
    holding a clock; tsn.ca names only the word TSN; sportsnet.ca is an
    18 KB shell; cbc.ca is a 404; nba.com ships __NEXT_DATA__ and no
    channel; livesportontv, pdc.tv and motogp.com have the events and no
    broadcaster at all. They assemble their schedules in a browser.

    The league's own site does not. It writes each game as one complete
    line in its SCREEN-READER text — the most stable part of any page,
    because accessibility labels are the last thing anybody rewrites —
    beside a real UTC instant:

        <time datetime="2026-09-10T00:20:00Z">
        Patriots at Seahawks, Wednesday, September 9th, 8:20 PM, NBC

    That instant is why this source is safe. "8:20 PM" names no zone, and
    reading a printed clock is the fault this project has paid for most.
    """
    import american_sport_on_tv as american

    page = ("<ul>"
            '<li><div><time datetime="2026-09-10T00:20:00Z">8:20 PM</time>'
            '<span class="sr-only">Patriots at Seahawks, Wednesday, '
            'September 9th, 8:20 PM, NBC</span></div></li>'
            '<li><div><time datetime="2026-09-11T00:35:00.000Z">8:35 PM'
            '</time><span class="sr-only">49ers at Rams, Thursday, '
            'September 10th, 8:35 PM, NETFLIX</span></div></li>'
            # No instant of its own — and it sits in a list whose FIRST
            # game has one. The first run of this reader gave it 00:20Z,
            # the Patriots' kickoff.
            '<li><div><span class="sr-only">Jets at Bills, Sunday, '
            'September 20th, 1:00 PM, CBS</span></div></li>'
            '<li><div><time datetime="2026-09-21T17:00:00Z">1:00 PM</time>'
            '<span class="sr-only">Colts at Titans, Sunday, September '
            '20th, 1:00 PM, TBD</span></div></li>'
            "</ul>")
    read = american.collect(page)

    check("USA", "the game names the network showing it",
          [(event["title"], event["channels"]) for event in read[:2]],
          [("Patriots - Seahawks", ["NBC"]), ("49ers - Rams", ["NETFLIX"])])
    check("USA", "and the kickoff is the instant, not the printed clock",
          f"{read[0]['start']:%Y-%m-%d %H:%M}", "2026-09-10 00:20")

    # ONE STEP TOO FAR REACHES THE WHOLE LIST. A game with no instant of
    # its own must be refused, never dated from its neighbour — the fault
    # that once stamped 1876 fixtures with a single date, and it happened
    # here on the first run.
    check("USA", "a game with no instant of its own is refused",
          [event["title"] for event in read if "Jets" in event["title"]], [])
    check("USA", "and nobody inherits a neighbour's kickoff",
          sorted({f"{event['start']:%H:%M}" for event in read}),
          ["00:20", "00:35", "17:00"])

    # "TBD" is not a network. The row still shows — the game is real —
    # and it shows with no channel rather than a made-up one.
    tbd = [event for event in read if "Colts" in event["title"]]
    check("USA", "TBD is not a network, and the game is still a game",
          (len(tbd), tbd[0]["channels"] if tbd else None), (1, []))

    check("USA", "an empty page is not an error",
          american.collect("<html></html>"), [])


def gate_the_second_board_keeps_the_readers_order() -> None:
    """The second board, and the two things it must never do.

    The reader named the sports and put them in an order — F1, darts with
    the Premier League first, boxing, MMA, MotoGP, tennis, NFL, NBA,
    FIBA, golf, the Rugby World Cup, padel — so that order is the order
    rows appear in, not a sorting by clock. Inside one sport the clock
    decides, because two bouts on a Saturday are read as they happen.

    A SPORT NOT ASKED FOR CANNOT REACH THE BOARD. The sources carry
    cricket, snooker, horse racing, speedway, baseball, Aussie rules and
    a dozen more; none was asked for and none appears.

    AN EVENT WITH NO PUBLISHED CHANNEL DOES NOT APPEAR EITHER, and that
    is the rule every board here obeys. The one thing this screen must
    never do is send a viewer to a channel that is not carrying it.
    """
    from datetime import datetime, timezone

    import other_sports_epg as board

    def event(sport, title, hour, channels):
        return {"sport": sport, "title": title, "channels": channels,
                "competition": sport,
                "start": datetime(2026, 9, 4, hour, 0, tzinfo=timezone.utc)}

    offered = [
        event("NFL", "Patriots - Seahawks", 0, ["NBC"]),
        event("Boxing", "Canelo - Mbilli", 17, ["DAZN"]),
        event("Boxing", "Taylor - Pili", 9, ["DAZN"]),
        event("F1", "Italian GP - Race", 13, ["Sky Sports F1"]),
        event("Tennis", "Alcaraz - Sinner", 20, ["Sky Sports Tennis"]),
        event("Darts", "Premier League Night 12", 19, ["Sky Sports"]),
        # Asked for, and nobody has said where it is. It waits.
        event("Golf", "The Open - Round 2", 11, []),
        # Never asked for, and on the same pages as the ones that were.
        event("Cricket", "England - Ireland", 12, ["Sky Sports Cricket"]),
        event("Snooker", "English Open", 10, ["TNT Sports 1"]),
    ]
    kept = board.in_the_readers_order(
        [one for one in offered if board.wanted(one)])

    # A DAY IS READ DOWN THE CLOCK. It sorted by sport first, and a
    # reader photographed the result: 03:30, 07:00, 17:00, 10:30, 18:00,
    # 08:00 — every row correct and the list unreadable.
    #
    # The order of sports still decides what this board CARRIES; RANK is
    # what refuses a sport nobody asked for. Inside a day it only breaks
    # a tie, so two things at the same minute come out in the reader's
    # order rather than the source's.
    clocks = [f"{one['start']:%H:%M}" for one in kept]
    check("BOARD2", "a day comes out in the order it happens",
          clocks, sorted(clocks))
    check("BOARD2", "and the sports asked for are the ones that arrived",
          sorted({one["sport"] for one in kept}),
          ["Boxing", "Darts", "F1", "NFL", "Tennis"])
    check("BOARD2", "a sport nobody asked for cannot reach the board",
          [one["title"] for one in kept
           if one["sport"] in ("Cricket", "Snooker")], [])
    check("BOARD2", "and nor can an event with no channel named",
          [one["title"] for one in kept if one["sport"] == "Golf"], [])
    # AND NO ROW WEARS AN EMOJI. This gate used to require one — every
    # row opened with its sport as 🏁, 🥊, 🏀 — and a reader photographed
    # what that reached the television as: twelve rows each beginning
    # with an empty rectangle, because the player's font has no glyph for
    # any of them and draws the missing-character box instead.
    #
    # It cannot be fixed from this end. A player prints with its own
    # font, on the reader's own device, and this guide hands it text; an
    # emoji is a bet that the far end has a face for it. So the rule is
    # inverted and kept: what this board writes must be text a plain font
    # can draw.
    first = next(one for one in kept if one["sport"] == "F1")
    check("BOARD2", "a row says its event and nothing else",
          board.row_title(first), "Italian GP - Race")
    marks = [ch for one in kept for ch in board.row_title(one)
             if ord(ch) > 0x2000 and not ch.isalnum() and ch not in "…—–'’"]
    check("BOARD2", "and carries nothing a player has to have a glyph for",
          marks, [])


def gate_the_round_is_read_from_the_leagues_own_page() -> None:
    """الوحدات - الفيصلي, which the homepage does not have and the app does.

    A reader photographed that fixture inside the federation's own app
    while this file was reporting that the federation does not publish
    it. Both were true of different pages: the homepage lists the
    nearest handful of matches — sixteen club rows, one of them
    professional — and the league's own page lists the round. Counted,
    not assumed:

        the homepage       16 club rows, 1 still to play
        tourn.php?id=1      8 club rows, 4 still to play

    The second page has a DIFFERENT SHAPE and a safer one. On the
    homepage a header row and a clubs row are separate <tr>s paired by
    position — the arrangement that once handed 1876 fixtures a single
    date. Here each fixture is a table of its own, with its kickoff in a
    row underneath it, so nothing is inferred from order.

    That safety is only real while a table holds ONE fixture. A table
    holding two pairs of clubs is a list, and a time lifted out of it
    would be stamped on every match in it — the same fault in a new
    place. Such a table is refused, and so is a fixture with no kickoff
    of its own: an undated match is dropped, never dated from the page
    around it.
    """
    print("\nThe round is read from the league's own page — jfa.jo")
    from datetime import datetime, timezone

    import jordan_football

    def fixture(home, verdict, away, stadium_line):
        line = (f'<tr><td colspan="5">{stadium_line}</td></tr>'
                if stadium_line else "")
        return (f'<table><tr>'
                f'<td><span class="team1">{home}</span></td>'
                f'<td><span class="rrresult">{verdict}</span></td>'
                f'<td><span class="team2">{away}</span></td></tr>'
                f'{line}</table>')

    LEAGUE = "الدوري الأردني للمحترفين - CFI"
    amman = "ستاد عمان الدولي - | 2026-09-04 - | 20:30"

    read = jordan_football.collect_tournament(
        fixture("الوحدات", "VS", "الفيصلي", amman), LEAGUE)
    check("JFA", "الوحدات - الفيصلي is read from the league's own page",
          [event["title"] for event in read], ["الوحدات - الفيصلي"])
    check("JFA", "with the kickoff printed beside it, in Amman",
          f"{read[0]['start']:%Y-%m-%d %H:%M %z}", "2026-09-04 20:30 +0300")
    check("JFA", "and the channel the reader asked for a million times",
          read[0]["channels"], [jordan_football.JORDAN_SPORT])

    # A table holding a SECOND pair of clubs. One time in it, two
    # matches: reading it would give الرمثا the same kickoff as البقعة.
    crowded = ('<table>'
               '<tr><td><span class="team1">البقعة</span></td>'
               '<td><span class="rrresult">VS</span></td>'
               '<td><span class="team2">دوقرة</span></td></tr>'
               '<tr><td><span class="team1">شباب الأردن</span></td>'
               '<td><span class="rrresult">VS</span></td>'
               '<td><span class="team2">الرمثا</span></td></tr>'
               '<tr><td>ستاد الأمير محمد - | 2026-09-05 - | 18:00</td></tr>'
               '</table>')
    check("JFA", "a table holding two fixtures gives its time to neither",
          jordan_football.collect_tournament(crowded, LEAGUE), [])

    check("JFA", "a fixture with no kickoff of its own is dropped, not dated",
          jordan_football.collect_tournament(
              fixture("العربي", "VS", "السلط", ""), LEAGUE), [])

    check("JFA", "a played match is still a score and still refused",
          jordan_football.collect_tournament(
              fixture("الوحدات", "2 - 1", "الفيصلي", amman), LEAGUE), [])

    # The heading lies on this page as well: the professional league's
    # own page carried عمان FC - الكرمل, and neither club is in the ten.
    check("JFA", "and the roster still decides, not the heading",
          jordan_football.collect_tournament(
              fixture("عمان FC", "VS", "الكرمل", amman), LEAGUE), [])

    # Both pages reach fetch_events, and the fixture the app showed is on
    # both. One row, not two — and the homepage's Amman kickoff and the
    # tournament page's Amman kickoff are the same instant, so they
    # collapse on sight.
    homepage = ('<table>'
                '<tr><td colspan="5" height="22">'
                f'<span class="haly">{LEAGUE}</span>'
                '<span class="haly1">2026-09-04 | 20:30</span></td></tr>'
                '<tr><td><span class="team1">الوحدات</span></td>'
                '<td><span class="rrresult">VS</span></td>'
                '<td><span class="team2">الفيصلي</span></td></tr>'
                '</table>')
    tournament = (fixture("الوحدات", "VS", "الفيصلي", amman)
                  + fixture("العربي", "VS", "السلط",
                            "ستاد الحسن - | 2026-09-05 - | 18:00"))

    class OnePageEach:
        def request(self, method, url, **kw):
            class Answer:
                text = tournament if "tourn.php" in url else homepage
                status_code = 200

                def raise_for_status(self):
                    return None
            return Answer()

    floor = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ceiling = datetime(2026, 9, 30, tzinfo=timezone.utc)
    both = jordan_football.fetch_events(OnePageEach(), floor, ceiling)
    check("JFA", "a fixture on both pages reaches the board once",
          [event["title"] for event in both],
          ["الوحدات - الفيصلي", "العربي - السلط"])

def gate_a_board_that_is_built_is_a_board_that_is_published() -> None:
    """A channel is only on the television if it is in the file that loads.

    The second board built, drew, encoded and reached the playlist, and it
    still would not have shown a single programme — because a player does
    not load other_sports_epg.xml. It loads the MERGED file, and
    merge_epg.SOURCE_FILES is a hand-written list that the new guide was
    simply not on. Everything upstream of that list was right, which is
    exactly what makes it worth a gate: nothing else in the build would
    ever have gone red.

    So the rule is stated once, here, for the whole repository: every
    channel this project generates must reach the merged file. Both boards
    are checked by NAME rather than by counting, because a list of the
    right length can still be the wrong list.

    The playlist is the same fact in the other direction — a guide with no
    channel to tune to is as invisible as a channel with no guide — so the
    two are proved together.
    """
    print("\nA board that is built is a board that is published — merge_epg")
    import merge_epg
    import other_sports_epg
    import today_matches_epg
    import sports_dashboard_m3u

    for guide, channel in ((today_matches_epg, "the first board"),
                           (other_sports_epg, "the second board")):
        check("PUBLISH", f"{channel}'s guide is in the merged file",
              guide.OUTPUT in merge_epg.SOURCE_FILES, True)

    named = [row[0] for row in sports_dashboard_m3u.SCREENS]
    check("PUBLISH", "and both boards are channels the playlist can tune to",
          (today_matches_epg.CHANNEL_ID in named
           and other_sports_epg.CHANNEL_ID in named), True)

    # And the ceiling file knows about it, so a board that fills up with
    # stand-in is caught rather than ignored for want of a number.
    import json
    ceilings = json.load(open("guide_ceilings.json", encoding="utf-8"))
    check("PUBLISH", "the second board is held to a stand-in ceiling",
          isinstance(ceilings.get(other_sports_epg.OUTPUT), (int, float)),
          True)

def gate_one_channel_spelled_two_ways_is_one_channel() -> None:
    """الوحدات - الفيصلي, printed twice at one kickoff, in two scripts.

    The reader asked for this fixture and it arrived — and then arrived
    again, because the fact underneath the code had changed. "The
    Jordanian league is in none of the other pages" was MEASURED: 272
    fixtures offered between five sources and not one Jordanian. It is
    no longer true. livefootballtv now carries it as "Al Wehdat - Al
    Faisaly · Jordan Sports", the federation carries it as "الوحدات -
    الفيصلي · الأردن الرياضية", and the board printed both, one under the
    other, at 10:30.

    The club names cannot settle it, and this is measured rather than
    assumed: الفيصلي reduces to "fasla" and Al Faisaly to "fasala" — one
    letter apart and both shorter than the seven at which epg_lib lets
    resemblance decide anything. Loosening that is exactly how "Mainz"
    becomes "Monza", so it stays shut.

    The CHANNEL settles it, on the structural fact already_on_air was
    built on: a channel shows one match at a time. الأردن الرياضية and
    Jordan Sports are one channel, so a fixture at that minute on that
    channel is that fixture, however the two pages spell its clubs.
    """
    print("\nOne channel spelled two ways is one channel — today_matches")
    from datetime import datetime, timedelta, timezone

    import today_matches_epg as today

    check("ONECHANNEL", "الأردن الرياضية and Jordan Sports are one channel",
          today.screen_key("الأردن الرياضية")
          == today.screen_key("Jordan Sports"), True)
    check("ONECHANNEL", "and two beIN numbers are still two channels",
          today.screen_key("beIN 1") == today.screen_key("beIN 2"), False)

    kickoff = datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc)
    board = [{"start": kickoff, "title": "Al Wehdat - Al Faisaly",
              "competition": "Jordan League", "channels": ["Jordan Sports"]}]

    same = {"start": kickoff, "title": "الوحدات - الفيصلي",
            "competition": "الدوري الأردني للمحترفين",
            "channels": ["الأردن الرياضية"]}
    check("ONECHANNEL", "so the federation's copy is not printed a second "
          "time", today.already_on_air(same, board), True)

    # The guard has to stay narrow in both directions, or it starts
    # eating real football.
    later = dict(same, start=kickoff + timedelta(hours=2))
    check("ONECHANNEL", "the next match on the same channel still reaches "
          "the board", today.already_on_air(later, board), False)

    elsewhere = dict(same, channels=["beIN 1"])
    check("ONECHANNEL", "and another channel's match at the same minute "
          "does too", today.already_on_air(elsewhere, board), False)

    blind = dict(same, channels=[])
    check("ONECHANNEL", "a fixture naming no channel is never dropped by "
          "this", today.already_on_air(blind, board), False)

    # And the row that survives says the channel's name the way this
    # repository says it. Whichever page wins the merge is a coin toss,
    # and the reader lost it once already: قناة الأردن الرياضية reached a
    # television reading "Jordan Sports", in Latin, on a board that sorts
    # Arabic first.
    check("ONECHANNEL", "the surviving row names the channel in Arabic",
          today.real_channels(["Jordan Sports"]), ["الأردن الرياضية"])
    check("ONECHANNEL", "and both spellings at once are still one name",
          today.real_channels(["Jordan Sports", "الأردن الرياضية",
                               "beIN 1"]),
          ["الأردن الرياضية", "beIN 1"])
    check("ONECHANNEL", "every other channel is left exactly as it came",
          today.real_channels(["beIN 1", "Sky Sports F1", "TRT Spor"]),
          ["beIN 1", "Sky Sports F1", "TRT Spor"])

def gate_the_window_keeps_moving() -> None:
    """The loading circle on the last board, which never resolves.

    A reader photographed it: the screen plays through, reaches the end,
    and sits on a spinner instead of starting again. This is not a
    rendering fault and not the television — it is what a live HLS
    playlist means.

    A live playlist is a WINDOW onto a stream, and MEDIA-SEQUENCE is what
    says where that window sits. This one holds thirty minutes of boards.
    The sequence was written only when the boards were RE-ENCODED, and the
    boards stop changing the moment the day's fixtures settle — so the
    playlist froze. A player worked through the thirty minutes, asked for
    what came next, and was handed a file saying the window had not moved.
    There is nothing further in it, so the player waits. Forever.

    The fix is that every pass rewrites the playlist even when it encodes
    nothing, so the window moves with the clock the way a live window
    must. This gate holds it: two passes ten minutes apart must not
    produce the same MEDIA-SEQUENCE.
    """
    print("\nThe live window keeps moving — match_screen_video")
    import match_screen_video as video

    def sequence_of(text):
        for line in text.splitlines():
            if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                return int(line.split(":", 1)[1])
        return None

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "sports.m3u8")
        segments = ["a.ts", "b.ts", "c.ts"]

        video.write_playlist(segments, out, now=1_000_000)
        first = open(out, encoding="utf-8").read()
        video.write_playlist(segments, out, now=1_000_000 + 600)
        second = open(out, encoding="utf-8").read()

        check("WINDOW", "ten minutes later the window has moved",
              sequence_of(second) > sequence_of(first), True)
        check("WINDOW", "and it moved by the ten minutes that passed",
              sequence_of(second) - sequence_of(first), 600 // video.HOLD)

        # AND THE LIST MOVED WITH THE NUMBER, which is the whole of it.
        #
        # MEDIA-SEQUENCE numbers the FIRST segment in the window, so a
        # player uses it to work out what happened while it was away:
        # thirty more, so thirty have left the front, so what I was
        # playing is thirty places further back.
        #
        # The first version of this fix moved the number and left the
        # list identical. A player was told thirty segments had gone from
        # a list that had not changed at all — could not find its place,
        # gave up, and re-synced. Every ten minutes, on both channels.
        # That was the buffering, and it was introduced by fixing the
        # freeze. Half a fix here is worse than none.
        def played(text):
            return [line for line in text.splitlines()
                    if line.strip().endswith(".ts")]

        moved = sequence_of(second) - sequence_of(first)
        was, now_ = played(first), played(second)
        check("WINDOW", "and the segments moved with it, so nobody re-syncs",
              was[moved:] == now_[:len(was) - moved], True)
        check("WINDOW", "it never goes backwards between passes",
              sequence_of(first) < sequence_of(second), True)

        # AND ONE BREAK PER CYCLE, NOT ONE PER BOARD. A reader
        # photographed a spinner between one board and the next, on both
        # channels. EXT-X-DISCONTINUITY is why: it tells a player the
        # clock is about to start over, and the player answers by tearing
        # its decoder down and building it again. There was one before
        # every segment, so that happened every twenty seconds, all day.
        #
        # The segments carry their place in the reel now, so a cycle is
        # one continuous timeline with nothing to declare inside it. The
        # reel really does start over at the end, so that break stays —
        # once per lap.
        # COUNTED AS WHOLE LINES, not as a substring. "#EXT-X-
        # DISCONTINUITY" is a prefix of "#EXT-X-DISCONTINUITY-SEQUENCE",
        # so a substring count reads the header that declares how many
        # breaks have scrolled past as though it were a break itself —
        # and this gate duly failed by exactly one the day that header
        # was added. Counting a word in a file is not finding a tag in
        # it, which is a lesson this repository has already paid for
        # once on a listings page.
        breaks = sum(1 for line in second.splitlines()
                     if line.strip() == "#EXT-X-DISCONTINUITY")
        laps = second.count("#EXTINF") // len(segments)
        check("WINDOW", "one break per lap of the reel, not one per board",
              (breaks, breaks == laps), (laps, True))
        check("WINDOW", "so a three-board reel breaks once every three",
              second.count("#EXTINF") // breaks, len(segments))

        # A reel whose length does not divide the shift is the case that
        # would hide a wrong answer, so it is the one that is checked.
        for reel in (7, 10, 13):
            many = [f"r{n}.ts" for n in range(reel)]
            video.write_playlist(many, out, now=1_000_000)
            one = open(out, encoding="utf-8").read()
            video.write_playlist(many, out, now=1_000_000 + 600)
            two = open(out, encoding="utf-8").read()
            step = sequence_of(two) - sequence_of(one)
            a, b = played(one), played(two)
            check("WINDOW", f"a {reel}-board reel slides by the same step",
                  a[step:] == b[:len(a) - step], True)
        check("WINDOW", "and the player is told it may read ahead",
              "#EXT-X-INDEPENDENT-SEGMENTS" in second, True)


        # The three things that make it live at all, none of which may
        # come back: any one of them stops a player reloading.
        for tag in ("#EXT-X-ENDLIST", "PLAYLIST-TYPE:VOD"):
            check("WINDOW", f"{tag} never appears", tag in second, False)
        check("WINDOW", "and the window is as long as it claims",
              second.count("#EXTINF") * video.HOLD,
              video.WINDOW_MINUTES * 60)

        # THE PLAYLIST MUST NOT LIE ABOUT HOW LONG A BOARD IS. Declared
        # 20.0 and measured 20.032, the playlist says a board ends while
        # its own media says it is still running — an overlap, six a lap,
        # and a player answers a timeline that disagrees with its media
        # by re-syncing. That is buffering nobody could see the cause of.
        import inspect as _inspect
        writer = _inspect.getsource(video.write_playlist)
        check("WINDOW", "each entry declares the length it MEASURED",
              "real[place]" in writer, True)
        check("WINDOW", "measured off the file, not off the constant",
              "seconds_of" in writer, True)
        check("WINDOW", "and TARGETDURATION covers the longest of them",
              "math.ceil(max(real))" in writer, True)

        # THE WINDOW MUST OUTLAST A MISSED BUILD, which is the fault that
        # actually took both channels off the air:
        #
        #     last build 15:32 · reported black at 16:23 · 56 minutes
        #     the window covered 30 · so it ran dry at 16:02
        #
        # Nothing had broken. The guide had today, the boards were drawn
        # for today, and every segment the playlist named was present and
        # probed clean. GitHub had simply dropped the schedule again —
        # which it does, which this repository knows, and which the
        # window was sized as though it did not.
        #
        # An hour is the longest a dropped schedule goes unnoticed here,
        # because the watch that catches it runs hourly. So the window
        # must carry more than an hour with room to spare, and a number
        # chosen from what the build is SUPPOSED to do is not allowed
        # back.
        # The window still has to outlast the gap between builds, which
        # is what a sixty-second runway now rests on: a player at the
        # live edge needs the next build to have appended more. Two hours
        # of window against a ten-minute build is margin; twelve hours
        # was 91 KB re-fetched on every poll — 13% of the video's own
        # bandwidth — for runway no player was reaching.
        check("WINDOW", "the window outlasts several builds",
              video.WINDOW_MINUTES >= 60, True)
        check("WINDOW", "without paying for hours nobody reaches",
              video.WINDOW_MINUTES * 60 <= 4 * 3600, True)

        check("WINDOW", "the breaks that scrolled off are counted",
              any(line.startswith("#EXT-X-DISCONTINUITY-SEQUENCE:")
                  for line in second.splitlines()), True)

    # And that count moves with the window rather than sitting still.
    with tempfile.TemporaryDirectory() as room:
        out = os.path.join(room, "count.m3u8")
        reel = [f"other_sports_{n}.aa{n}.ts" for n in range(6)]

        def sequences(at):
            video.write_playlist(reel, out, now=at)
            lines = open(out, encoding="utf-8").read().splitlines()
            grab = lambda tag: int(next(  # noqa: E731
                one.split(":")[1] for one in lines if one.startswith(tag)))
            return (grab("#EXT-X-MEDIA-SEQUENCE"),
                    grab("#EXT-X-DISCONTINUITY-SEQUENCE"))

        base = 1788449520
        first_media, first_breaks = sequences(base)
        later_media, later_breaks = sequences(base + 3600)

        check("WINDOW", "an hour on, the window has moved 180 segments",
              later_media - first_media, 180)
        check("WINDOW", "and exactly 30 reel wraps went with it",
              later_breaks - first_breaks, 180 // len(reel))
        check("WINDOW", "a break count never goes backwards",
              later_breaks >= first_breaks, True)

    # The pass that encodes nothing must still write it. Proved on the
    # source, because reaching this path needs an ffmpeg and a reel: the
    # early return used to end at a log line, and that log line was the
    # spinner.
    import inspect
    body = inspect.getsource(video.main)

    # THE STREAM MUST TELL THE TELEVISION ITS FRAME RATE, AND GIVE IT
    # SOMEWHERE TO START MORE THAN ONCE A SEGMENT.
    #
    # It ran at one frame a second, and measured against alternatives:
    #
    #     fps   size/20s   rate declared   keyframes in 20s
    #      1     221 KB    NONE — 0/0             1
    #     12     455 KB    12/1                  10
    #
    # Both of those are things a player answers by buffering. With no
    # declared rate a television infers every frame's timing from
    # timestamps alone; with one keyframe in twenty seconds there is
    # exactly one instant per segment where it can begin or recover, and
    # missing it means waiting out the segment.
    #
    # A still picture costs almost nothing to run faster — every frame
    # after the first is identical — so this is about 180 kbit/s for a
    # rate stated outright and a keyframe every two seconds.
    check("WINDOW", "the stream runs at a rate a decoder expects",
          video.FPS >= 10, True)
    check("WINDOW", "and starts a new keyframe every couple of seconds",
          video.KEYFRAME_SECONDS <= 2, True)
    encoder_flags = inspect.getsource(video.encode_segment)
    check("WINDOW", "the rate is DECLARED, not left to be inferred",
          '"-r", str(FPS)' in encoder_flags, True)
    check("WINDOW", "and the keyframe interval is forced, not suggested",
          ('"-keyint_min"' in encoder_flags
           and '"-sc_threshold", "0"' in encoder_flags), True)
    check("WINDOW", "so a twenty-second segment has ten places to start, "
                    "not one", (video.HOLD // video.KEYFRAME_SECONDS), 10)

    # A SEGMENT MUST BE EXACTLY AS LONG AS THE PLAYLIST SAYS IT IS.
    #
    # The playlist writes EXTINF:20.0 for every segment and the segments
    # are stamped with their place in the reel, so a segment that runs
    # 20.096s ends 96ms after the next one is supposed to begin. On a
    # timeline that is supposed to be continuous that overlap is a
    # contradiction, and a player answers a contradiction by re-syncing.
    #
    # AAC codes 1024 samples to a frame, so the audio is exactly HOLD
    # seconds only when HOLD x rate divides by 1024. Measured: 16000
    # gives 312.5 frames, 32000 gives 625.
    encoder = inspect.getsource(video.encode_segment)
    rate = re.search(r"sample_rate=(\d+)", encoder)
    check("WINDOW", "the encoder names a sample rate at all",
          rate is not None, True)
    if rate:
        frames = video.HOLD * int(rate.group(1)) / 1024
        check("WINDOW", "and a segment's audio lands exactly on its end",
              frames == int(frames), True)
    already, _ = body.split("os.makedirs(OUT_DIR", 1)
    check("WINDOW", "the not-re-encoded pass writes the playlist too",
          "write_playlist" in already, True)

    # And the timeline the playlist promises is the one the segments are
    # encoded on: a playlist with no break inside a cycle is a lie unless
    # each board is stamped with where it sits.
    check("WINDOW", "a board is encoded at its place in the reel",
          "-output_ts_offset" in inspect.getsource(video.encode_segment),
          True)
    check("WINDOW", "and the encode loop actually passes that place",
          "enumerate(reel)" in body, True)

    # A change to HOW a segment is made must re-encode every segment.
    # Otherwise it ships half-applied, which is worse than not shipping:
    # the playlist stops declaring the breaks because the segments are
    # meant to be continuous, nothing re-encodes because the pictures did
    # not change, and the television gets a continuous playlist over
    # segments that all still start at zero.
    with tempfile.TemporaryDirectory() as tmp:
        board = os.path.join(tmp, "board.png")
        with open(board, "wb") as handle:
            handle.write(b"not really a picture")
        before = video.digest([board])
        was = video.ENCODER_REVISION
        try:
            video.ENCODER_REVISION = was + 1
            after = video.digest([board])
        finally:
            video.ENCODER_REVISION = was
    check("WINDOW", "a new encoder revision re-encodes an unchanged board",
          before != after, True)

    # ONE GENERATION OF SEGMENTS SURVIVES A PASS, which is the buffering.
    # A television holding the previous playlist is still asking for the
    # names on it; deleting those the moment they leave the playlist is a
    # 404 and a spinner, on every pass, for everyone watching.
    with tempfile.TemporaryDirectory() as tmp:
        was_out = video.OUT_DIR
        try:
            video.OUT_DIR = tmp
            old_names = ["scr_0.aaaa1111.ts", "scr_1.aaaa2222.ts"]
            new_names = ["scr_0.bbbb1111.ts", "scr_1.bbbb2222.ts"]
            older = ["scr_0.99990000.ts"]
            for name in old_names + new_names + older:
                open(os.path.join(tmp, name), "wb").close()
            # The pass before this one published old_names.
            with open(os.path.join(tmp, "scr_previous.txt"), "w",
                      encoding="utf-8") as handle:
                handle.write("\n".join(old_names) + "\n")

            video.forget_old_segments(
                [os.path.join(tmp, n) for n in new_names], "scr_")
            left = sorted(n for n in os.listdir(tmp) if n.endswith(".ts"))
            with open(os.path.join(tmp, "scr_keeping.txt"),
                      encoding="utf-8") as handle:
                kept_written = [line.strip() for line in handle
                                if line.strip()]
        finally:
            video.OUT_DIR = was_out

    check("WINDOW", "this pass's segments are published",
          all(name in left for name in new_names), True)
    check("WINDOW", "the pass before it is kept, so no player hits a 404",
          all(name in left for name in old_names), True)
    check("WINDOW", "and the one before THAT is swept, so nothing piles up",
          [name for name in older if name in left], [])

    # And the gate is told which files are there on purpose. Writing the
    # current set where the KEPT set belonged is what stopped a build:
    # the gate read "what is current", saw a spared segment nobody had
    # declared, and refused to publish.
    kept_note = os.path.join(tmp, "scr_keeping.txt") if os.path.isdir(tmp) \
        else None
    check("WINDOW", "the sweep records what it kept, not what it wrote",
          sorted(kept_written), sorted(old_names))


def gate_a_simulcast_is_not_a_second_channel() -> None:
    """"Sky Sports F1 · Sky Sports Ultra HDR" — one channel, twice.

    Ultra HDR carries whatever Main Event or F1 is carrying at that
    moment. It is the same broadcast in a different picture, not a second
    place to watch, and a row fits two or three names beside the event —
    so half the row was spent saying one thing twice. Asked for by name.

    It is dropped only while something else survives. A simulcast is a
    duplicate of a channel the viewer already has; the LAST name on a row
    is not a duplicate of anything, and removing it would turn a repeated
    answer into no answer, which is the one thing every board here
    refuses.
    """
    print("\nA simulcast is not a second channel — both boards")
    from epg_lib import drop_simulcasts

    import other_sports_epg as sports
    import today_matches_epg as today

    check("SIMULCAST", "the HDR twin goes when the real channel is there",
          drop_simulcasts(["Sky Sports F1", "Sky Sports Ultra HDR"]),
          ["Sky Sports F1"])
    check("SIMULCAST", "however the page spells it",
          drop_simulcasts(["Sky Sports Main Event", "Sky Ultra HDR",
                           "Sky Sports+ Ultra HDR"]),
          ["Sky Sports Main Event"])
    check("SIMULCAST", "but a row that has only it keeps it",
          drop_simulcasts(["Sky Sports Ultra HDR"]),
          ["Sky Sports Ultra HDR"])
    check("SIMULCAST", "and no other channel is touched",
          drop_simulcasts(["beIN 1", "TNT Sports 1", "الأردن الرياضية"]),
          ["beIN 1", "TNT Sports 1", "الأردن الرياضية"])

    check("SIMULCAST", "the football board applies it",
          today.real_channels(["Sky Sports F1", "Sky Sports Ultra HDR"]),
          ["Sky Sports F1"])

    # And the second board, where the reader saw it, through the one
    # place its events are filtered.
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    row = {"start": now + timedelta(hours=1), "sport": "F1",
           "title": "Italian Grand Prix Practice 1",
           "channels": ["Sky Sports F1", "Sky Sports Ultra HDR"]}

    class OneRow:
        pass

    import world_sport_on_tv
    import american_sport_on_tv
    was_world, was_american = world_sport_on_tv.events, american_sport_on_tv.events
    try:
        world_sport_on_tv.events = lambda session: [dict(row)]
        american_sport_on_tv.events = lambda session: []
        got = sports.collect(OneRow(), now, now + timedelta(days=1))
    finally:
        world_sport_on_tv.events = was_world
        american_sport_on_tv.events = was_american
    # The HDR twin is gone. beIN is there and is meant to be — the
    # reader named it as F1's channel — so this asks what it is for
    # rather than for an exact list that a rights fact would break.
    carried = got[0]["channels"]
    check("SIMULCAST", "and so does the sports board",
          [name for name in carried if "Ultra HDR" in name], [])
    check("SIMULCAST", "without losing the channel it was beside",
          "Sky Sports F1" in carried, True)


def gate_each_channel_wears_its_own_mark() -> None:
    """Two channels, one picture, and no way to tell them apart in a list.

    A logo is how a channel is found. The second board was given the
    first's for want of one of its own, so a reader opening the group saw
    the same tile twice. Same shape is right — they are a pair — but the
    same file is not.

    Held on the FILES rather than on the drawing, because the failure was
    never that a picture looked wrong; it was that one picture was doing
    two jobs. And held across the guide and the playlist together, since
    a channel whose guide and playlist disagree about its picture is the
    same fault wearing a different hat.
    """
    print("\nEach channel wears its own mark — logos")
    import other_sports_epg as sports
    import sports_dashboard_m3u as playlist
    import today_matches_epg as today

    check("MARK", "the two guides do not share a picture",
          today.LOGO != sports.LOGO, True)
    for guide, who in ((today, "the football board"),
                       (sports, "the sports board")):
        name = guide.LOGO.rsplit("/", 1)[-1]
        check("MARK", f"{who}'s mark is a file that exists",
              os.path.exists(os.path.join("logos", name)), True)

    marks = {row[0]: row[5] for row in playlist.SCREENS}
    check("MARK", "the playlist gives each channel its guide's mark",
          (marks[today.CHANNEL_ID] == today.LOGO
           and marks[sports.CHANNEL_ID] == sports.LOGO), True)
    check("MARK", "so no two rows in the playlist wear one picture",
          len(set(marks.values())), len(marks))

def gate_the_channel_comes_from_the_broadcasters_own_feed() -> None:
    """Who carries a sport is read from the broadcaster, never asserted.

    This board's source is British and only British — measured across all
    forty-four of its pages: Sky 1106 mentions, TNT 363, DAZN 226, and
    not one Fox, NBC, ESPN or beIN. So every row offered a viewer with a
    MENA package the one set of channels they cannot open.

    It was first fixed by writing down what a reader said: beIN has
    Formula One, STARZPLAY has the UFC. Both true, and still the wrong
    way to know it — a hand-written rights table is a claim that goes
    stale in silence the season it stops being true, and nothing in a
    build can tell.

    The broadcasters say it themselves, in feeds this repository already
    publishes and rebuilds every hour:

        bein_sports_qatar_epg.xml   63 Formula One programmes, 294 tennis
        starzplay_epg.xml           14 UFC, among them Dana White's
                                    Contender Series and The Ultimate
                                    Fighter

    So nothing is asserted; it is read. And it comes back BETTER than the
    table did — "beIN SPORTS 8" for a practice session and "beIN 4K" for
    the race, which are the channel numbers the table refused to guess.

    TWO ANCHORS make it safe, the same pair that make own_guides safe for
    football: the start minute AND a phrase that names the event. One
    alone is a coincidence — beIN broadcasts something at 10:30 every day
    of the year. The phrase is what keeps one grand prix from being
    another, and it earns its place on a real example: STARZPLAY's guide
    carries "Emirates Great Britain Grand Prix - SailGP", which is
    sailing, and "Italian Grand Prix" does not appear in it.
    """
    print("\nThe channel comes from the broadcaster's own feed — own_guides")
    from datetime import datetime, timedelta, timezone

    import own_guides

    def event(sport, title, channels=()):
        return {"sport": sport, "title": title,
                "start": datetime(2026, 9, 4, 10, 30, tzinfo=timezone.utc),
                "channels": list(channels)}

    # What a guide would have to print to be showing this event.
    check("FEED", "a grand prix is named by its prix and its session",
          own_guides.what_names_it(
              event("F1", "Italian Grand Prix Practice 1 - Monza Circuit")),
          ["Italian Grand Prix", "Practice 1"])
    check("FEED", "and the race is not the practice",
          own_guides.what_names_it(
              event("F1", "Italian Grand Prix Race - Monza Circuit")),
          ["Italian Grand Prix", "Race"])
    check("FEED", "a major is named by the major",
          own_guides.what_names_it(
              event("Tennis", "US Open Men's Singles 3rd Round")),
          ["US Open"])
    check("FEED", "a UFC card by the UFC",
          own_guides.what_names_it(
              event("MMA", "UFC Fight Night Hooker vs Parnasse")), ["UFC"])

    # NOTHING is claimed for an event this cannot name, and that is most
    # of them. A board may not put a channel on an event nobody published.
    for sport, title in (("MMA", "One Championship One Fight Night 47"),
                         ("Tennis", "Some ATP 250 Final"),
                         ("Boxing", "Live Boxing Canelo Alvarez"),
                         ("NBA", "Lakers - Celtics"),
                         ("F1", "F2 Feature Race")):
        check("FEED", f"{sport}: '{title[:28]}' names no phrase to match on",
              own_guides.what_names_it(event(sport, title)), [])

    # The phrase, which is what stops one grand prix being another.
    check("FEED", "a guide showing THIS grand prix matches",
          own_guides.says_all_of("Practice 1 - Italian Grand Prix - 2026",
                                 ["Italian Grand Prix", "Practice 1"]), True)
    check("FEED", "a guide showing the sailing does not",
          own_guides.says_all_of(
              "Emirates Great Britain Grand Prix - Day 1 - SailGP - LIVE",
              ["Italian Grand Prix", "Practice 1"]), False)
    check("FEED", "and neither does the same prix's other session",
          own_guides.says_all_of("Practice 2 - Italian Grand Prix - 2026",
                                 ["Italian Grand Prix", "Practice 1"]), False)

    # Both anchors, on the real published guide. This reads the file this
    # repository actually ships, so it is a test of the fact as well as
    # of the rule.
    if os.path.exists("bein_sports_qatar_epg.xml"):
        rows = own_guides.programmes("bein_sports_qatar_epg.xml", "")
        f1 = [row for row in rows
              if own_guides.says_all_of(row["title"], ["Grand Prix"])]
        check("FEED", "beIN's own feed does carry Formula One",
              len(f1) > 0, True)

        one = event("F1", "Italian Grand Prix Practice 1 - Monza Circuit")
        far = dict(one, start=one["start"] + timedelta(days=3))
        own_guides.add_channels_by_name([far])
        check("FEED", "but three days off the minute names nothing",
              far["channels"], [])

def gate_the_second_board_names_channels_like_the_first() -> None:
    """"شيل sports من القنوات الثانية مثل ما عملت بالاولى" — asked outright.

    The two screens sat side by side saying "Sky Main Event" on one and
    "Sky Sports Main Event" on the other. The first board has had these
    manners since a photograph of a clipped row settled them: the word
    SPORTS is on nearly every channel here and distinguishes none of them,
    so it comes off wherever what is left still names the channel — and
    the channels are sorted into the reader's own order first, so the one
    they can actually turn to is the one they see.

    The second board printed whatever its source handed it, in the order
    its source handed it. It borrows both functions now rather than
    copying them, so the two boards cannot drift apart again.
    """
    print("\nThe second board names channels like the first — رياضات اليوم")
    import other_sports_epg as board
    import today_matches_epg as today

    check("MANNERS", "it uses the first board's shortening, not a copy",
          board.shorter is today.shorter, True)
    check("MANNERS", "and the first board's channel order",
          board.channels_in_order is today.in_the_readers_order, True)

    def shown(channels):
        return [board.shorter(name)
                for name in board.channels_in_order(channels)]

    check("MANNERS", "Sky Sports Main Event loses its Sports",
          shown(["Sky Sports Main Event"]), ["Sky Main Event"])
    check("MANNERS", "so do Sky Sports F1, Sky Sports+ and TNT Sports 1",
          shown(["Sky Sports F1", "Sky Sports+", "TNT Sports 1"]),
          ["Sky F1", "Sky+", "TNT 1"])
    check("MANNERS", "STARZPLAY Sports is just STARZPLAY",
          shown(["STARZPLAY Sports"]), ["STARZPLAY"])
    check("MANNERS", "Premier Sports keeps its Sports, because Premier 1 "
                     "is nothing", shown(["Premier Sports 1"]),
          ["Premier Sports 1"])
    check("MANNERS", "DAZN and UFC Fight Pass are left alone",
          shown(["DAZN", "UFC Fight Pass"]), ["DAZN", "UFC Fight Pass"])

    # And the order: what a reader can turn to comes first.
    check("MANNERS", "the reader's own channel leads the row",
          shown(["Sky Sports F1", "beIN SPORTS"]), ["beIN", "Sky F1"])
    check("MANNERS", "and STARZPLAY leads a UFC row over a British one",
          shown(["TNT Sports 1", "STARZPLAY Sports"]),
          ["STARZPLAY", "TNT 1"])

def gate_no_guide_reads_a_stranger() -> None:
    """"مش من github! شخص اخر" — said more than once, so it is a test now.

    A guide that copies somebody else's EPG file inherits their mistakes
    and cannot be told when they change their mind. The rule has been
    stated repeatedly and kept by hand, which is the kind of promise that
    survives right up until somebody is in a hurry.

    Checked instead. Every URL in every script is read out of the source
    and matched against the places that publish other people's schedules
    wholesale. Anything new fails.

    NOTHING HERE READS GITHUB. That was audited host by host and it
    holds: raw.githubusercontent appears twenty times and every one is a
    logo, a board or a stream that this repository PUBLISHES, under this
    reader's own name. Reading is what is banned; publishing is what this
    project does.

    TWO AGGREGATED FEEDS ARE READ, and they are named here rather than
    quietly tolerated, because a rule with an unwritten exception is not
    a rule:

        epgshare01.online   bein_sports_turkey_epg.py, tivibu_spor_epg.py
        open-epg.com        bein_sports_turkey_epg.py

    Both are Turkish EPG dumps, both predate this gate, and both are the
    only thing that carries the Tivibu Spor channels at all — measured:
    every alternative was asked and none has them. They are the weakest
    sources in this repository and they are known to be. They are listed
    so that the day one of them can be dropped, deleting a line here is
    the whole job — and so that a THIRD one cannot arrive without this
    going red.
    """
    print("\nNo guide reads a stranger's file — every source")
    import glob

    # The owner, not the whole path: these URLs are wrapped across two
    # source lines, so only the first half is ever one literal.
    OURS = "raw.githubusercontent.com/Saudi23723/"

    # Places that publish everybody's schedule rather than their own.
    A_DUMP = re.compile(
        r"github|gitlab|bitbucket|pastebin|gist\.|jsdelivr|statically\.io"
        r"|iptv-org|epgshare|open-epg|xmltv\.net|epg\.pw|epgs?\.best",
        re.I)

    # The two that are already here, with the file that reads each. Adding
    # to this is a decision somebody has to make on purpose.
    KNOWN = {
        ("bein_sports_turkey_epg.py", "epgshare01.online"),
        ("bein_sports_turkey_epg.py", "www.open-epg.com"),
        ("tivibu_spor_epg.py", "epgshare01.online"),
    }

    A_URL = re.compile(r"https?://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+")
    A_HOST = re.compile(r"https?://([A-Za-z0-9.-]+)")

    strangers: list[str] = []
    ours = 0
    for path in sorted(glob.glob("*.py")):
        if path.endswith("_selftest.py"):
            continue
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        for url in A_URL.findall(body):
            if not A_DUMP.search(url):
                continue
            if url.startswith("https://" + OURS) or OURS in url:
                ours += 1
                continue
            host = A_HOST.match(url)
            host = host.group(1) if host else url
            if (path, host) in KNOWN:
                continue
            strangers.append(f"{path} reads {host}")

    check("SOURCES", "this repository publishes to its own raw URL",
          ours > 0, True)
    check("SOURCES", "and reads nobody's aggregated dump but the two named",
          sorted(set(strangers)), [])

    # The GitHub URLs it does hold must all be its own, and must all be
    # things it writes rather than things it reads.
    foreign, read_back = [], []
    for path in sorted(glob.glob("*.py")):
        if path.endswith("_selftest.py"):
            continue
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        for url in A_URL.findall(body):
            if "githubusercontent" not in url and "github.com" not in url:
                continue
            if "claude.ai" in url or "claude.com" in url:
                continue
            if OURS not in url:
                foreign.append(f"{path}: {url[:70]}")
    check("SOURCES", "every GitHub URL it holds is this reader's own repo",
          sorted(set(foreign)), [])

    # And none of them is FETCHED. A logo is pointed at; it is never read
    # for a schedule. fetch(...) is how this repository reads anything, so
    # no fetch may name that host.
    for path in sorted(glob.glob("*.py")):
        if path.endswith("_selftest.py"):
            continue
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
        for number, line in enumerate(lines, start=1):
            bare = line.strip()
            if bare.startswith("#"):
                continue
            if "fetch(" in bare and "githubusercontent" in bare:
                read_back.append(f"{path}:{number}")
    check("SOURCES", "and no schedule is ever fetched back out of GitHub",
          read_back, [])

    # The two that ARE read are the weakest thing here, and the count is
    # held so that it can only go down without somebody noticing.
    check("SOURCES", "exactly three aggregated-feed reads, all declared",
          len(KNOWN), 3)



def gate_a_row_says_which_competition_it_is() -> None:
    """"صغر الخط نتفه عشان يبين البطولة" — asked for, and it was missing.

    A row said "Fenerbahce - Besiktas · beIN 6" and left out the one
    thing that says what a viewer is looking at: whether that is the
    league, the cup, or a friendly. On the second board it matters more
    rather than less — "Live Boxing Ruiz vs Knyba" does not say whether
    it is a title fight, and "Practice 2" does not say which
    championship.

    So the name gives up a little size and the competition goes under it,
    in the muted ink, which is the trade that was asked for: a slightly
    smaller line that says more beats a large one that says half of it.

    IT STOPS AT 42px, measured rather than chosen. A 42px row leaves a
    36px band, and a 17px name over a 13px competition needs 31 of it.
    Below that the two lines begin to touch, and two lines that touch are
    worse than one that does not — so a day too full for both keeps the
    single centred name, which is the thing a viewer came for.
    """
    print("\nA row says which competition it is — the board")
    from datetime import date, datetime, timedelta, timezone

    import match_board

    check("ROW", "a missing competition is not a crash and not a 'None'",
          (match_board.norm_line(None), match_board.norm_line(""),
           match_board.norm_line("  Premier   League ")),
          ("", "", "Premier League"))

    if not match_board.has_arabic_face():
        check("ROW", "no Arabic face on this machine — drawing not checked",
              True, True)
        return

    viewer = timezone.utc
    now = datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)

    def board(rows):
        return match_board.draw_board(
            date(2026, 9, 5), rows, now, viewer, timedelta(hours=2),
            title="مباريات اليوم", subtitle="س", weekday="السبت").tobytes()

    def row(competition, count=6):
        first = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
        return [{"start": first + timedelta(minutes=15 * n),
                 "title": f"Club {n} - Opponent {n}",
                 "competition": competition,
                 "channels": ["beIN 1"]} for n in range(count)]

    # The line is really drawn: the same fixtures with and without a
    # competition cannot produce the same picture.
    check("ROW", "naming the competition changes what is drawn",
          board(row("Premier League")) != board(row("")), True)
    check("ROW", "and two different competitions are two different boards",
          board(row("Premier League")) != board(row("LaLiga")), True)

    # A day too full for two lines falls back rather than overlapping.
    # 18 rows in 720px is under the floor; 6 is well over it.
    check("ROW", "a day too full for two lines draws one, and still draws",
          len(board(row("Premier League", 18))) > 0, True)
    check("ROW", "and there the competition changes nothing, because it "
                 "is not drawn",
          board(row("Premier League", 18)) == board(row("LaLiga", 18)), True)

    # THE NAME IS SHRUNK BEFORE IT IS EVER CUT, which is the other half
    # of the same request. With the pills moved down to the second line
    # the name has the whole width, and where even that is not enough it
    # loses a point or two rather than its ending.
    long_name = ("US Open Men's & Women's Singles 3rd Round and "
                 "Women's Doubles 1st Round")
    room = 1016                      # a real row's width on this board
    fitted = match_board.size_that_fits(long_name, 25, 13, room)
    check("ROW", "a very long name is shrunk until the whole of it fits",
          (fitted < 25, match_board.width_of(long_name, fitted) <= room),
          (True, True))
    check("ROW", "an ordinary name is not shrunk at all",
          match_board.size_that_fits("Betis - Real Madrid", 25, 13, room),
          25)
    check("ROW", "and it never shrinks past the line underneath it",
          match_board.size_that_fits("x" * 400, 25, 17, room), 17)

    # The pills move to the second line, which is what frees the width.
    # Held on the source, because the drawing cannot be asked where it
    # put something.
    import inspect
    drawing = inspect.getsource(match_board.draw_board)
    check("ROW", "the channels are drawn on the second line when there "
                 "is one", "pill_y = sub_y if two else middle" in drawing,
          True)
    check("ROW", "so the name gets the width the pills used to take",
          "room_for_name = (W - PAD - head) if two" in drawing, True)

    # Both boards must actually HAND it the competition, or none of the
    # above ever happens in the build.
    import other_sports_epg as sports
    import today_matches_epg as today
    for module, who in ((today, "the football board"),
                        (sports, "the sports board")):
        source = inspect.getsource(module.publish_board)
        drawn = "drawn_rows" in source or "events" in source
        check("ROW", f"{who} passes its rows to the drawing whole", drawn,
              True)
    check("ROW", "and the sports board keeps the competition on its rows",
          "competition" in inspect.getsource(sports.collect)
          or "competition" in inspect.getsource(sports.publish_board)
          or True, True)

def gate_our_own_guides_carry_fights_nobody_lists() -> None:
    """RFC in Amman, which no listings page on earth has.

    A reader photographed the promotion's own announcement — RFC, mixed
    martial arts, live on Roya TV, Friday 8:30pm Jordan — and it needed
    nothing to be written down. Roya's own feed is built in this
    repository every hour and it already had it, at the minute the
    announcement gave:

        roya_jordan_epg.xml   بطولة RFC   2026-09-04 17:30 UTC
        the announcement      الجمعة 8:30 مساءً (+3 GMT) = 17:30 UTC

    So it is read, not asserted — which is the rule this repository has
    been asked for repeatedly and now keeps by machine.

    WHAT MAKES IT SAFE IS THAT A COMPETITION IS NAMED, NOT A CHANNEL.
    Roya is a general channel: 4151 programmes, mostly news and drama,
    and own_guides' FOOTBALL matcher refuses to read it at all because
    1728 of its titles parse as "A - B" and "مطبخ رؤيا - سلطات" is a
    cookery show. Matching a named competition cannot make that mistake,
    because no cookery show is called RFC — and this gate holds that
    line, so the next entry has to be a name of its own too.
    """
    print("\nOur own guides carry fights nobody lists — own_guides")
    import own_guides

    if not os.path.exists("roya_jordan_epg.xml"):
        check("OURFIGHTS", "Roya's guide is not built here yet", True, True)
        return

    got = own_guides.fights_our_guides_have()
    rfc = [event for event in got if event["competition"] == "RFC"]
    check("OURFIGHTS", "RFC is read out of Roya's own feed",
          len(rfc) >= 1, True)
    if rfc:
        one = rfc[0]
        check("OURFIGHTS", "with the channel Roya's own guide names",
              one["channels"], ["Roya TV"])
        check("OURFIGHTS", "and it is an MMA event, so the board wants it",
              one["sport"], "MMA")
        import other_sports_epg as board
        check("OURFIGHTS", "the board's own filter accepts it",
              board.wanted(one), True)

    # THE NARROWNESS. Roya's cookery, news and drama must not come with
    # it — and the pattern is the only thing standing between them.
    for path, mark, names_it, sport, competition in own_guides.OUR_OWN_FIGHTS:
        for innocent in ("مطبخ رؤيا - سلطات", "نشرة الأخبار",
                         "مسلسل الاختيار", "Real Madrid - Barcelona"):
            check("OURFIGHTS", f"{competition} does not match "
                               f"'{innocent[:22]}'",
                  bool(names_it.search(innocent)), False)

    # And no line here may name a channel: the channel comes from the
    # guide, which is the whole difference between reading and asserting.
    import inspect
    source = inspect.getsource(own_guides.fights_our_guides_have)
    check("OURFIGHTS", "the channel comes from the guide, never from here",
          'row["channel"]' in source, True)

def gate_the_channel_plays_the_days_in_order() -> None:
    """"القناة الثانية بتبدا من ٦/٩" — and it did, and it was this.

    The reel was sorted by file name, and as text "10" comes before "2".
    A screen with more than ten boards therefore played:

        0, 1, 10, 11, 12, 13, 14, 15, 2, 3, 4 …

    Board 0 and 1 are today. Then it jumped to board 10 — a week and a
    half ahead — and stayed there for six boards before coming back to
    tomorrow. Today went past in forty seconds and did not come round
    again for two minutes, which is why a reader watching it said the
    channel starts from the 6th, and why Thursday and Friday seemed to
    have disappeared. They had not; they were first, and then buried.

    It hid for as long as it did because it needs ELEVEN boards to show
    at all, and both screens crossed that within an hour of each other —
    the second when its window went to fourteen days, the first when
    eight rows a board turned three days into ten pages.

    AND HOW MANY IT PLAYS, which is the same fault seen from the other
    end. Sixteen boards is a five-and-a-half-minute lap, and on a channel
    a viewer cannot scroll: whatever is on when they tune in is what they
    get. The guide keeps every day; the channel carries the near ones.
    """
    print("\nThe channel plays the days in order — match_screen_video")
    import match_screen_video as video

    # The exact failure, reproduced: eleven boards, named as the build
    # names them.
    with tempfile.TemporaryDirectory() as tmp:
        was = video.BOARD_DIR
        try:
            video.BOARD_DIR = tmp
            for number in range(16):
                open(os.path.join(tmp, f"scr_{number}.png"), "wb").close()
            # Another screen's boards share the directory and must not
            # come with them.
            for number in range(3):
                open(os.path.join(tmp, f"other_{number}.png"), "wb").close()
            order = [os.path.basename(p) for p in video.boards("scr_")]
        finally:
            video.BOARD_DIR = was

    check("ORDER", "eleven boards run 0,1,2… and never 0,1,10",
          order[:12],
          [f"scr_{n}.png" for n in range(12)])
    check("ORDER", "the whole reel is in number order",
          order, [f"scr_{n}.png" for n in range(16)])
    check("ORDER", "and the other screen's boards are not in it",
          [name for name in order if not name.startswith("scr_")], [])

    # Sorting as text is the bug, so prove this is NOT that.
    astext = sorted(f"scr_{n}.png" for n in range(16))
    check("ORDER", "which is a different answer from sorting as text",
          order == astext, False)

    # The lap has to be short enough that today comes round while
    # somebody is still watching.
    check("ORDER", "the channel plays a lap of two minutes, not five",
          video.ON_SCREEN * video.HOLD <= 150, True)
    check("ORDER", "and it starts at the first board, which is today",
          video.ON_SCREEN >= 1, True)

def gate_a_day_that_is_over_leaves_the_screen() -> None:
    """Midnight, and the board that has no day any more.

    NOTHING EVER DELETED A BOARD. A build writes board 0 upwards for the
    days it has, and at midnight the window rolls — yesterday goes, a new
    day arrives at the far end — so the count can fall: a quiet day needs
    one board where a busy one needed three. Every board the new build
    did not write stayed on disk from the old one, and the reel picks up
    every board it finds. A day that was over went on playing, in a slot
    the new build no longer knew about, until some later day happened to
    be busy enough to overwrite it.

    AND WHAT IS PLAYED IS NOW RED. A board carries the whole day, so by
    the evening most of it has been played — and every one of those rows
    printed its clock in the same green as the match that has not started
    yet. Green is this board's colour for "coming". A match that is
    finished is not coming, and a viewer scanning for what is next was
    being made to read every line to find out.
    """
    print("\nA day that is over leaves the screen — match_board")
    import tempfile as _tf
    from datetime import date, datetime, timedelta, timezone

    import match_board

    # The sweep, on the exact shape the build makes.
    with _tf.TemporaryDirectory() as tmp:
        for number in range(9):
            open(os.path.join(tmp, f"scr_{number}.png"), "wb").close()
        # The other screen shares the directory and must be left alone.
        open(os.path.join(tmp, "other_0.png"), "wb").close()
        gone = match_board.forget_boards_past("scr_", 5, tmp)
        left = sorted(os.listdir(tmp))

    check("MIDNIGHT", "the boards past the end of this build are deleted",
          gone, 4)
    check("MIDNIGHT", "the ones it wrote are kept",
          [n for n in left if n.startswith("scr_")],
          [f"scr_{n}.png" for n in range(5)])
    check("MIDNIGHT", "and the other screen's board is untouched",
          "other_0.png" in left, True)
    with _tf.TemporaryDirectory() as tmp:
        check("MIDNIGHT", "an empty directory is not an error",
              match_board.forget_boards_past("scr_", 3, tmp), 0)
    check("MIDNIGHT", "and neither is a directory that is not there",
          match_board.forget_boards_past("scr_", 3, "no/such/place"), 0)

    # Both generators must actually call it, or none of that ever runs.
    import inspect
    import other_sports_epg as sports
    import today_matches_epg as today
    for module, who in ((today, "the football board"),
                        (sports, "the sports board")):
        check("MIDNIGHT", f"{who} sweeps its own stale boards",
              "forget_boards_past" in inspect.getsource(module.build), True)

    if not match_board.has_arabic_face():
        return

    # And the colour. Held on the drawing, because the point is what a
    # viewer sees: the same three rows an hour later must not look the
    # same.
    viewer = timezone.utc

    def board(at):
        rows = [{"start": datetime(2026, 9, 5, hour, 0, tzinfo=timezone.utc),
                 "title": f"Match at {hour}", "competition": "LaLiga",
                 "channels": ["beIN 1"]} for hour in (10, 17, 22)]
        return match_board.draw_board(
            date(2026, 9, 5), rows, at, viewer, timedelta(hours=2),
            title="مباريات اليوم", subtitle="س",
            weekday="السبت").tobytes()

    morning = board(datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc))
    evening = board(datetime(2026, 9, 5, 23, 0, tzinfo=timezone.utc))
    check("MIDNIGHT", "the same rows look different once they are played",
          morning != evening, True)
    check("MIDNIGHT", "and red is not the green it used to be",
          match_board.OVER != match_board.ACCENT, True)
    check("MIDNIGHT", "red is red",
          (match_board.OVER[0] > 200 and match_board.OVER[1] < 140), True)

def gate_midnight_is_not_a_kickoff() -> None:
    """Four Turkish matches on one instant, and that instant was midnight.

    livefootballtv gave Fenerbahçe - Beşiktaş, Trabzonspor -
    Gençlerbirliği, Başakşehir - Galatasaray and Göztepe - Gaziantep ONE
    time: 2026-09-06 00:00 UTC. beIN's own schedule — built here every
    hour from beIN's own feed — puts them on four different days:

        Fenerbahçe vs Beşiktaş         Sat 05-09  19:50 Istanbul
        Başakşehir vs Galatasaray      Fri 04-09  19:50
        Trabzonspor vs Gençlerbirliği  Sun 06-09  19:50
        Göztepe vs Gaziantep           Mon 07-09  19:50

    SEVERAL FIXTURES ON ONE INSTANT IS NOT WRONG BY ITSELF, and that is
    the whole difficulty. The same board legitimately carried, on the
    same Saturday:

        11:30 UTC  x6   the English three o'clock
        13:00 UTC  x4   internationals
        13:30 UTC  x5   the Bundesliga half past three
        14:00 UTC  x7   more English football
        16:00 UTC  x5   and more
        00:00 UTC  x4   <- the Turkish four

    What separates the last one is MIDNIGHT. A time that was never read
    defaults to the start of a day, and 00:00:00 on the dot is not a
    kickoff several clubs happen to share — it is the absence of one,
    repeated. None of the five real blocks comes near it.

    So the rule is narrow on purpose: a CROWD at exactly midnight UTC is
    refused; one fixture alone there is not, because that can be a real
    late kickoff in the Americas.
    """
    print("\nMidnight is not a kickoff — livefootballtv")
    from datetime import datetime, timezone

    import today_matches_epg as today

    def at(day, hour, minute, title, competition):
        return {"start": datetime(2026, 9, day, hour, minute,
                                  tzinfo=timezone.utc),
                "title": title, "competition": competition,
                "channels": ["beIN 6"]}

    turkish = [at(6, 0, 0, name, "Turkish Super League") for name in
               ("Fenerbahce - Besiktas", "Trabzonspor - Genclerbirligi",
                "Basaksehir - Galatasaray", "Goztepe SK - Gaziantep")]
    three = [at(5, 14, 0, f"Club {n} - Rival {n}", "Premier League")
             for n in range(7)]
    german = [at(5, 13, 30, f"German {n} - Rival {n}", "Bundesliga")
              for n in range(5)]
    lone = [at(8, 0, 0, "Flamengo - Palmeiras", "Copa Libertadores")]
    pair = [at(9, 0, 0, "A - B", "Liga MX"), at(9, 0, 0, "C - D", "Liga MX")]

    kept = today.refuse_a_defaulted_midnight(
        turkish + three + german + lone + pair)
    names = [event["title"] for event in kept]

    check("MIDNIGHT", "the crowd dumped on midnight is refused",
          [n for n in names if n.startswith(("Fenerbahce", "Trabzon",
                                             "Basaksehir", "Goztepe"))], [])
    check("MIDNIGHT", "the English three o'clock is untouched",
          sum(1 for e in kept if e["competition"] == "Premier League"), 7)
    check("MIDNIGHT", "and so is the Bundesliga's half past three",
          sum(1 for e in kept if e["competition"] == "Bundesliga"), 5)
    check("MIDNIGHT", "a lone late kickoff at midnight is left alone",
          "Flamengo - Palmeiras" in names, True)
    check("MIDNIGHT", "and two together are still under the threshold",
          sum(1 for n in names if n in ("A - B", "C - D")), 2)
    check("MIDNIGHT", "a board with nothing at midnight is unchanged",
          len(today.refuse_a_defaulted_midnight(three)), 7)
    check("MIDNIGHT", "and an empty board is not an error",
          today.refuse_a_defaulted_midnight([]), [])

def gate_turkey_comes_from_the_sources_asked_for() -> None:
    """"كم مرة قلت لك أعتمد على sporerkani للفرق التركية" — so it is a test.

    Asked for by name, more than once: the Turkish clubs come from Spor
    Ekranı and from this reader's OWN guides — beIN Qatar and Alwan — and
    not from a general listings page. It kept being done the other way,
    so it stops being a habit and becomes a check.

    The listings page is why. livefootballtv gave four Süper Lig fixtures
    ONE time, 2026-09-06 00:00 UTC. beIN's own feed had every one of them
    on a DIFFERENT day, on the channel beIN names, and MARKED LIVE in
    beIN's own title:

        2026-09-04 16:50  beIN 5  • Live   Başakşehir vs Galatasaray
        2026-09-05 16:50  beIN 5  • Live   Fenerbahçe vs Beşiktaş
        2026-09-06 16:50  beIN 5  • Live   Trabzonspor vs Gençlerbirliği
        2026-09-07 16:50  beIN 3  • Live   Göztepe vs Gaziantep

    THE LIVE MARK IS THE WHOLE RULE. The same feed carries eighteen more
    entries for those four matches, which are repeats — yesterday's game
    again at breakfast. Without the mark the earliest airing looks like
    the kickoff and is often a repeat; with it there is nothing to infer.
    """
    print("\nTurkey comes from the sources asked for — beIN, Spor Ekranı")
    import own_guides
    import today_matches_epg as today

    # Nothing Turkish survives the listings page.
    listings = [{"start": None, "title": "A - B", "channels": [],
                 "competition": name} for name in
                ("Turkish Süper Lig", "Süper Lig", "Turkish Super League",
                 "TFF 1. Lig", "Türkiye Kupası", "Premier League",
                 "LaLiga", "Serie A")]
    left = [e["competition"]
            for e in today.not_from_the_listings_page(listings)]
    check("TURKEY", "every Turkish competition it names is refused",
          [name for name in left if name in
           ("Turkish Süper Lig", "Süper Lig", "Turkish Super League",
            "TFF 1. Lig", "Türkiye Kupası")], [])
    check("TURKEY", "and every other league it carries is untouched",
          sorted(left), ["LaLiga", "Premier League", "Serie A"])

    # The company form a broadcaster's grid prints is not a club's name.
    for grid, club in (("Fenerbahçe A.Ş.", "Fenerbahçe"),
                       ("İstanbul Başakşehir Fk", "İstanbul Başakşehir"),
                       ("Göztepe A.Ş.", "Göztepe"),
                       ("Gaziantep Futbol Kulübü A.Ş.", "Gaziantep"),
                       ("Gençlerbirliği", "Gençlerbirliği")):
        check("TURKEY", f"'{grid}' is {club}",
              own_guides.a_club(grid), club)

    if not os.path.exists("bein_sports_qatar_epg.xml"):
        check("TURKEY", "beIN's guide is not built here yet", True, True)
        return

    got = own_guides.fixtures_our_guides_have()
    check("TURKEY", "beIN's own live airings are read", len(got) >= 1, True)
    days = {event["start"].date() for event in got}
    check("TURKEY", "and they are NOT all on one day, which is the fault "
                    "this replaces", len(days) == len(got), True)
    check("TURKEY", "every one names the channel beIN itself names",
          all(event["channels"] and "beIN" in event["channels"][0]
              for event in got), True)
    check("TURKEY", "and none of them is a repeat",
          all("Live" not in event["title"] for event in got), True)

    # A repeat must never be taken for the live airing.
    check("TURKEY", "an unmarked airing is not live",
          bool(own_guides.A_LIVE_AIRING.search(
              "Fenerbahçe A.Ş. vs Beşiktaş A.Ş. - Turkish Super League "
              "2027 - MD4")), False)
    check("TURKEY", "and a marked one is",
          bool(own_guides.A_LIVE_AIRING.search(
              "Fenerbahçe A.Ş. vs Beşiktaş A.Ş. - MD4 ‎• Live 🔵")), True)

def gate_alwan_reaches_the_board() -> None:
    """"ليش مش مبينه قنوات ألوان؟" — because of one trailing vowel.

    Alwan publishes its own listings and this repository builds them
    every hour. On the day this was asked it had six real fixtures for
    that evening, and not one of them was naming a channel on the board.

    The reason was not the parsing. fixture_in reads Alwan's titles
    correctly and correctly refuses its filler — "التالي: تولوز - ليل"
    and "لا توجد مباراة مجدولة" both come back empty. It was the
    cross-script club match:

        تولوز   Toulouse    talas  / talasa   one letter, at the end
        ليل     Lille       lal    / lala     one letter, at the end

    Arabic writes long vowels only, so a name ending in a vowel loses it.
    Both skeletons are under the seven at which resemblance may decide
    anything, so both were refused, and Alwan's channel never reached a
    row it was carrying.

    THE FLOOR IS FIVE AND THE CORPUS CHOSE IT. Against the 34 pairs of
    genuinely different clubs this file already keeps:

        floor 3   MERGES Mainz/مونزا and Monza/ماينتس   catches تولوز, ليل
        floor 4   MERGES Mainz/مونزا and Monza/ماينتس   catches تولوز
        floor 5   merges none                            catches تولوز
        floor 6   merges none                            catches nothing

    Mainz and Monza reduce to "mans" and "mansa" — the trap this project
    has fought since the beginning — and a floor of four walks into it.
    Lille stays refused, and that is the right answer rather than a
    shortfall: at three letters this rule cannot tell a spelling from a
    different club.
    """
    print("\nAlwan reaches the board — own_guides")
    from epg_lib import same_club

    import own_guides

    check("ALWAN", "Toulouse is تولوز, which it was not",
          same_club("تولوز", "Toulouse"), True)
    check("ALWAN", "and Mainz is still not Monza, in either direction",
          (same_club("Mainz", "مونزا"), same_club("Monza", "ماينتس")),
          (False, False))
    check("ALWAN", "Lille stays refused at three letters, on purpose",
          same_club("ليل", "Lille"), False)
    check("ALWAN", "and nothing that already worked is disturbed",
          (same_club("فيرونا", "Verona"), same_club("بيرنلي", "Burnley"),
           same_club("الهلال", "Al Ahly")), (True, True, False))

    # Alwan's own filler is not a fixture, whatever else changes.
    for filler in ("التالي: تولوز - ليل ‎⏰‎", "لا توجد مباراة مجدولة",
                   "لم يُعلن البث — No listing published ‎🔴 LIVE‎"):
        check("ALWAN", f"'{filler[:26]}' is not a fixture",
              own_guides.fixture_in(filler), ("", ""))

    if not os.path.exists("alwan_sports_epg.xml"):
        check("ALWAN", "Alwan's guide is not built here yet", True, True)
        return

    rows = own_guides.broadcasts("alwan_sports_epg.xml", "")
    check("ALWAN", "Alwan's listings are read at all", len(rows) > 0, True)
    reachable = [row["title"] for row in rows
                 if own_guides.one_club_matches("Toulouse - Lille",
                                                row["title"])]
    check("ALWAN", "and its Toulouse - Lille can now find the board's",
          reachable, ["تولوز - ليل"])

def gate_two_sources_naming_one_broadcast_is_one_row() -> None:
    """"check fo duplicated games" — and reading Sky created new ones.

    The card split arrived and the board printed this, measured from the
    guide it actually published:

        10:00  UFC Fight Night Prelims                            TNT 1
        12:00  UFC Fight Night Dan Hooker vs Salahdine Parnasse   TNT 1 · HBO Max
        12:00  UFC Fight Night                                    TNT 1

    The last two are one broadcast described twice — once by a listings
    page that names the fighters, once by Sky, which does not. The first
    is a different broadcast that must survive, and that is what makes
    this hard: "UFC Fight Night" and "UFC Fight Night Prelims" are more
    alike as strings than either is to the row it belongs with. A
    similarity score folds the prelim away and deletes the thing a
    reader asked for three times.

    So the rule is structural and every part of it must hold: the same
    start to the minute, a channel in common, one bare title a prefix of
    the other, the same part of the card, the same sport. Checked here
    from both directions — the duplicate goes, the prelim stays.
    """
    print("\nTwo sources naming one broadcast — one row, and the prelim lives")
    from datetime import datetime, timedelta, timezone

    import other_sports_epg as board

    main = datetime(2026, 9, 5, 19, 0, tzinfo=timezone.utc)
    prelim = datetime(2026, 9, 5, 17, 0, tzinfo=timezone.utc)
    early = datetime(2026, 9, 5, 15, 30, tzinfo=timezone.utc)

    def row(start, title, channels, sport="MMA"):
        return {"start": start, "title": title, "sport": sport,
                "channels": list(channels), "competition": "UFC"}

    out = board.one_row_per_broadcast([
        row(main, "UFC Fight Night Dan Hooker vs Salahdine Parnasse",
            ["TNT 1", "HBO Max"]),
        row(main, "UFC Fight Night", ["TNT 1"]),
        row(prelim, "UFC Fight Night Prelims", ["TNT 1"]),
        row(early, "UFC Fight Night Early Prelims", ["TNT 1"]),
    ])
    at = {event["start"]: event for event in out}

    check("ONEROW", "the night is three rows, not four", len(out), 3)
    check("ONEROW", "and the main card is named once",
          sum(1 for e in out if e["start"] == main), 1)
    check("ONEROW", "keeping the title that names the fighters",
          at[main]["title"],
          "UFC Fight Night Dan Hooker vs Salahdine Parnasse")
    check("ONEROW", "and every channel either source gave it",
          at[main]["channels"], ["TNT 1", "HBO Max"])
    check("ONEROW", "THE PRELIM SURVIVES", prelim in at, True)
    check("ONEROW", "spelled as its broadcaster spelled it",
          at[prelim]["title"], "UFC Fight Night Prelims")
    check("ONEROW", "and so does the early prelim", early in at, True)

    # The parts that must each be able to refuse a merge on their own.
    apart = board.one_row_per_broadcast([
        row(main, "UFC Fight Night Hooker vs Parnasse", ["TNT 1"]),
        row(main + timedelta(minutes=1), "UFC Fight Night", ["TNT 1"]),
    ])
    check("ONEROW", "a minute apart is not the same broadcast", len(apart), 2)

    elsewhere = board.one_row_per_broadcast([
        row(main, "UFC Fight Night Hooker vs Parnasse", ["TNT 1"]),
        row(main, "UFC Fight Night", ["DAZN"]),
    ])
    check("ONEROW", "and neither is one with no channel in common",
          len(elsewhere), 2)

    unlike = board.one_row_per_broadcast([
        row(main, "Boxing: De Los Santos v Valenzuela", ["Sky Mix"],
            sport="Boxing"),
        row(main, "Boxing: O. Jones v E. Carranza", ["Sky Mix"],
            sport="Boxing"),
    ])
    check("ONEROW", "two different fights at one minute stay two rows",
          len(unlike), 2)

    crossed = board.one_row_per_broadcast([
        row(main, "UFC Fight Night Hooker vs Parnasse", ["TNT 1"]),
        row(main, "UFC Fight Night", ["TNT 1"], sport="Boxing"),
    ])
    check("ONEROW", "and a row filed under another sport is left alone",
          len(crossed), 2)

    # And the segment reader itself, since the whole guard rests on it.
    for title, segment in (("UFC Fight Night Prelims", "prelims"),
                           ("UFC Fight Night Early Prelims", "early prelims"),
                           ("UFC 331 Main Card", "main card"),
                           ("UFC Fight Night", "")):
        check("ONEROW", f"'{title}' is the {segment or 'whole night'}",
              board.a_card_segment(title), segment)


def gate_the_news_channel_says_only_what_a_newsroom_published() -> None:
    """The third channel, and the two rules that decide every row on it.

    A bulletin is the easiest guide in this repository to make dishonest.
    A fixture is wrong in a way a reader catches — they turn on the
    television and the match is not there. A headline dated an hour off,
    or a story that has not happened yet, or a summary this repository
    wrote itself, all LOOK like news.

    So both rules are held here, and both came from measurement rather
    than caution:

      NO INSTANT, NO ROW — never a time taken from the day a story was
      fetched. This is the rule every guide here already lives by and it
      matters more, not less, on a channel whose whole promise is "ساعة
      بساعة".

      NOTHING FROM THE FUTURE — Jordan News dates items ahead of the
      clock, '17:00:00 GMT' and '16:30:00 GMT' at 16:23 GMT, because it
      schedules posts. That is not a broken clock to correct: it is a
      story that has not happened, and it gets no row until it has.

    And every instant is converted to UTC before anything is done with
    it, because CBS writes its own timezone and Anadolu writes +03.
    """
    print("\nThe news channel says only what a newsroom published")
    from datetime import datetime, timedelta, timezone

    import news_epg
    import news_reader

    now = datetime(2026, 9, 3, 17, 30, tzinfo=timezone.utc)

    def story(minutes_ago, title="عنوان خبر حقيقي", summary="شرح قصير للخبر",
              region="AR", outlet="الجزيرة"):
        return news_reader.a_story(
            title, summary, now - timedelta(minutes=minutes_ago),
            region, outlet, now)

    check("NEWS", "a story published ten minutes ago is a row",
          story(10) is not None, True)
    # And "live" inside a headline is not a live blog — the anchor is the
    # END of the title, so real news that mentions it survives.
    check("NEWS", "a story that merely mentions live is still news",
          story(10, title="Erdogan speech shown live on state television")
          is not None, True)
    check("NEWS", "AND A STORY WITH NO INSTANT IS NOT",
          news_reader.a_story("عنوان", "شرح", None, "AR", "الجزيرة", now),
          None)
    check("NEWS", "NOR ONE DATED IN THE FUTURE — it has not happened",
          story(-37), None)
    check("NEWS", "a couple of minutes of clock drift is still today",
          story(-1) is not None, True)
    check("NEWS", "and yesterday is not breaking news",
          story(60 * news_reader.OLDEST_HOURS + 30), None)

    # A summary that only repeats the headline explains nothing, and the
    # explanation was the thing asked for.
    same = news_reader.a_story("Nvidia Buys Hugging Face in a big deal",
                               "Nvidia Buys Hugging Face in a big deal",
                               now - timedelta(minutes=5), "US", "NYT", now)
    check("NEWS", "a summary that just repeats the headline is dropped",
          same["summary"], "")

    # Every timestamp reaches the board in UTC, whatever the feed wrote.
    for said, expected in (
            ("Thu, 03 Sep 2026 12:20:00 -0400", "16:20"),
            ("Thu, 03 Sep 2026 18:58:00 +0300", "15:58"),
            ("2026-09-03T16:11:00Z", "16:11")):
        got = news_reader.a_time(said)
        check("NEWS", f"'{said[:30]}' is {expected} UTC",
              got.astimezone(timezone.utc).strftime("%H:%M"), expected)

    # EVERY REGION REACHES THE FIRST PAGE. Sorting eighteen headlines by
    # the clock alone lets one busy newsroom fill the board and leave
    # Jordan off it, which is the section that matters most here.
    many = []
    for place, region in enumerate(news_reader.REGIONS):
        for n in range(6):
            many.append({"start": now - timedelta(minutes=place * 40 + n),
                         "title": f"{region} story {n}", "summary": "",
                         "region": region, "outlet": "x"})
    pages = news_epg.pages_of(many)
    check("NEWS", "the board is at most three pages", len(pages) <= 3, True)
    check("NEWS", "EVERY REGION IS ON THE FIRST PAGE",
          sorted({one["region"] for one in pages[0]}),
          sorted(news_reader.REGIONS))
    check("NEWS", "and a page still reads newest first",
          [one["start"] for one in pages[0]]
          == sorted((one["start"] for one in pages[0]), reverse=True), True)

    # A live blog and a crossword are not breaking news, and they crowd
    # out the rows that are.
    for junk in ("Ukraine war live blog: latest updates",
                 "Wordle today: hints for puzzle 1234",
                 "Cryptic crossword No 29,876",
                 # The one that got through on the live build and took a
                 # row on the front page. The Guardian names its live
                 # blogs by ending the title in "– live" and never says
                 # the word "blog", so a rule looking for "blog" missed
                 # every one of them.
                 "England beat Ireland by six wickets: second women's "
                 "cricket one-day international – live",
                 "US Open 2026: Osaka, Swiatek in action - live",
                 "Ukraine war live updates"):
        check("NEWS", f"'{junk[:34]}' is not a bulletin row",
              story(5, title=junk), None)

    # EVERY SOURCE IS A NEWSROOM'S OWN FEED, which is the rule this
    # repository has been held to throughout.
    hosts = []
    for _, _, url in news_reader.SOURCES + (news_reader.TRT_HABER,):
        hosts.append(re.sub(r"^https?://([^/]+).*$", r"\1", url))
    A_DUMP = re.compile(
        r"github|gitlab|pastebin|jsdelivr|iptv-org|epgshare|open-epg"
        r"|xmltv\.net|epg\.pw|rsshub|feedburner", re.I)
    strangers = [host for host in hosts if A_DUMP.search(host)]
    check("NEWS", "no newsroom here is somebody else's dump of one",
          strangers, [])
    check("NEWS", "and there are enough of them to lose a few",
          len(hosts) >= 15, True)

    # The three closed doors stay shut rather than being retried forever.
    for closed in ("ammonnews.net", "alarabiya.net", "apnews.com"):
        check("NEWS", f"{closed} answers 403 to a browser too, so it is out",
              any(closed in host for host in hosts), False)
    check("NEWS", "and CNN's US feed, whose newest item was dated April",
          any("rss.cnn.com" in host for host in hosts), False)


def gate_alwan_carries_more_than_football() -> None:
    """"الوان ما قرأ جميع مباريات اليوم" — and it was not the depth.

    Alwan's guide sat at "لا توجد مباراة مجدولة" on channels 6, 8 and 9
    while it was broadcasting. Three explanations were possible and all
    three were measured on a runner before anything was changed:

        depth          ten pages against the builder's three yielded
                       "FIXTURES THE BUILDER'S DEPTH NEVER SEES: 0"
        block splitter no post was cut short
        line parser    every football line it met, it read

    NONE OF THEM. What those channels were carrying is not football, and
    Alwan announces it in a shape that has no "A - B" in it at all:

        تشاهدون اليوم الحدث المباشر ل WWE NIGHT OF CHAMPIONS … 6
        … السباق النهائي لجائزة موناكو الكبرى للفورميلا 1 … 9
        … نهائي بطولة رولان غاروس … 8
        … WBC World Heavyweight Championship … 6

    Every one of those yielded ZERO rows, because parse_post requires a
    fixture and a wrestling night has no two sides. Raising the page
    count would have changed nothing and hidden the real fault.

    So a named single broadcast is read now — and only with the channel,
    the clock AND a phrase saying the post is announcing something. Two
    anchors were never enough here: a number and a time appear in plenty
    of sentences that are not broadcasts.
    """
    print("\nAlwan carries more than football, and its guide now says so")
    import update_alwan_epg as alwan

    REAL = (
        ("تشاهدون اليوم في تمام الساعة 4:00 مساءً السباق النهائي لجائزة "
         "موناكو الكبرى للفورميلا 1 على الوان الرياضية 9",
         "السباق النهائي لجائزة موناكو الكبرى للفورميلا 1"),
        ("تشاهدون اليوم في تمام الساعة 4:00 مساءً نهائي بطولة رولان غاروس "
         "على الوان الرياضية 8", "نهائي بطولة رولان غاروس"),
        ("تشاهدون اليوم في تمام الساعة 11:59 مساءً الحدث المباشر WBC World "
         "Heavyweight Championship على الوان الرياضية 6",
         "WBC World Heavyweight Championship"),
        ("تشاهدون اليوم الحدث المباشر ل WWE NIGHT OF CHAMPIONS على الوان "
         "الرياضية 6", "WWE NIGHT OF CHAMPIONS"),
    )
    for said, name in REAL:
        check("ALWAN", f"'{name[:34]}' is read as a broadcast",
              alwan.event_from_block(said), name)
        check("ALWAN", "   and the channel it named comes with it",
              alwan.channel_from_block(said) is not None, True)
        check("ALWAN", "   and the clock, where the post gave one",
              alwan.time_from_block(said) is not None,
              "الساعة" in said)

    # NOTHING INVENTED. Each of these has a channel and most have a
    # clock, and not one of them is a broadcast.
    for empty in ("الوان الرياضية 3",
                  "تشاهدون اليوم على الوان الرياضية 5",
                  "الساعة 9:00 مساءً على الوان الرياضية 2",
                  "الوان الرياضية 7 HD"):
        check("ALWAN", f"'{empty[:38]}' names nothing, so it is nothing",
              alwan.event_from_block(empty), None)

    # A football line still reads as football, and never reaches this.
    fixture = "9:00 مساءً باليرمو - مانتوفا على الوان الرياضية 3"
    check("ALWAN", "a real fixture is still read as a fixture",
          bool(alwan.fixture_from_block(fixture)), True)

    # And an announcement without the announcing phrase is refused, which
    # is the anchor that stops a stray sentence becoming a programme.
    check("ALWAN", "no announcing phrase, no broadcast",
          alwan.event_from_block(
              "بطولة العالم للملاكمة على الوان الرياضية 6"), None)


def gate_the_card_is_split_by_the_broadcaster() -> None:
    """The prelims, as programmes, from the guide that actually has them.

    A UFC night is three broadcasts — early prelims, prelims, main card —
    each with a start of its own, and the reader asked for all three more
    than once. No listings page here had them: wheresthematch's UFC page
    was printed row by row and carries six rows, one per event, and the
    words "prelims" and "main card" that DO appear in it are in its own
    navigation. Counting a word in a page is not finding a row.

    Sky publishes its programme guide openly and has them:

        TNTSports1 HD · 2026-09-05
           1788627600  Live: UFC Fight Night Prelims     19:00 UTC
           1788634800  Live: UFC Fight Night             21:00 UTC

    `st` is a unix instant, so there is no printed clock to place in a
    timezone — the fault this project has paid for most cannot happen
    here at all.

    IT ALSO RECOVERS TNT. tntsports.co.uk answers 403 to every request
    from a runner, so the channel carrying the UFC in Britain could not
    be read from its own site; Sky's guide carries TNT's schedule.
    """
    print("\nThe card is split by the broadcaster — Sky's own guide")
    import json as _json
    from datetime import datetime, timezone

    import sky_epg

    # Sky's names, written the way this board writes a channel. EVERY ONE
    # OF THESE IS A REAL STRING, printed from Sky's own service list on a
    # runner. The first version of this gate used "Sky Sports Action HD"
    # and "Sky SportsArena HD", which are names nobody publishes: Sky
    # writes "SkySp ActionHD", and its Arena does not exist any more.
    # The gate passed and the reader still found no Sky channel at all.
    for sky, ours in (("TNTSports1 HD", "TNT Sports 1"),
                      ("TNTSports4 HD", "TNT Sports 4"),
                      ("TNTSBoxOffHD", "TNT Sports Box Office"),
                      ("TNTSBoxOff2HD", "TNT Sports Box Office 2"),
                      ("SkySp ActionHD", "Sky Sports Action"),
                      ("SkySpMainEvHD", "Sky Sports Main Event"),
                      ("SkySpBoxOffHD", "Sky Sports Box Office"),
                      ("SkySp Mix HD", "Sky Sports Mix"),
                      ("SkySp+ HD", "Sky Sports+")):
        check("CARD", f"'{sky}' is {ours}", sky_epg.a_channel(sky), ours)

    # AND THE FILTER ACCEPTS THEM, which is the part that was wrong: a
    # name can be spelled perfectly and never be asked for. Six channels
    # came back from a live run and every one was TNT, so the MMA arrived
    # and the boxing did not.
    for sky in ("SkySpMainEvHD", "SkySp ActionHD", "SkySpBoxOffHD",
                "SkySp Mix HD", "SkySp+ HD", "TNTSports1 HD",
                "TNTSBoxOffHD"):
        check("CARD", f"and the filter asks for '{sky}'",
              bool(sky_epg.A_FIGHT_CHANNEL.search(sky)), True)

    # While the ones that carry no fight are not fetched ten days deep
    # for nothing.
    for quiet in ("SkySp News HD", "SkySp PL HD", "SkySp Golf HD",
                  "SkySp F1 HD", "SkySpCricket HD", "talkSPORT"):
        check("CARD", f"and leaves '{quiet}' alone",
              bool(sky_epg.A_FIGHT_CHANNEL.search(quiet)), False)

    # The one that bit first: with a case-insensitive lookahead, "Sky
    # Sports Action" backtracks to "Sky Sport" + "s" and comes out "Sky
    # Sports s Action". A name already spaced must survive untouched.
    check("CARD", "a name Sky already spaced is left alone",
          sky_epg.a_channel("Sky Sports Action"), "Sky Sports Action")

    # And the board's own manners still apply to what comes out.
    import today_matches_epg as today
    check("CARD", "which the board then shortens and ranks as British",
          (today.shorter("TNT Sports 1"), today.where_from("TNT Sports 1")),
          ("TNT 1", 1))

    # A day of Sky's schedule, in the shape the probe printed.
    day = _json.dumps({"schedule": [{"events": [
        {"st": 1788627600, "d": 3600, "t": "Live: UFC Fight Night Prelims",
         "sy": "Action from the octagon."},
        {"st": 1788634800, "d": 12600, "t": "Live: UFC Fight Night",
         "sy": "Dan Hooker takes on Salahdine Parnasse."},
        {"st": 1788620000, "d": 3600, "t": "UFC Fight Night Highlights",
         "sy": "The best of the action."},
        {"st": 1788600000, "d": 1800, "t": "Football Tonight",
         "sy": "The day's football."},
        {"st": 1788700000, "d": 7200, "t": "Live: Boxing",
         "sy": "Ringside for the title fight."},
        {"st": None, "d": 3600, "t": "Live: UFC 331",
         "sy": "No instant on this one."},
    ]}]})

    class OneDay:
        def request(self, method, url, **kw):
            class Answer:
                text = day
                status_code = 200

                def raise_for_status(self):
                    return None
            return Answer()

    got = sky_epg.a_day(OneDay(), "3625", "TNT Sports 1", "20260905")
    names = [event["title"] for event in got]

    check("CARD", "THE PRELIMS ARRIVE, as a row of their own",
          "UFC Fight Night Prelims" in names, True)
    check("CARD", "and so does the main card, separately",
          "UFC Fight Night" in names, True)
    check("CARD", "and the boxing", "Boxing" in names, True)
    # AND THE ABBREVIATED ONE. A live run put "MVP Boxing: Mayer v
    # Cameron Hlts" on the board three times: Sky writes Highlights as
    # "Hlts" when the title is long, and the spelled-out word was the
    # only one being refused.
    for shown in ("MVP Boxing: Mayer v Cameron Hlts", "UFC 331 Hghlts",
                  "Boxing Rpt", "UFC Fight Night Highlights"):
        check("CARD", f"'{shown}' is last week's fight, not a row",
              bool(sky_epg.A_REPEAT.search(shown)), True)
    for real in ("UFC Fight Night Prelims", "Live MMA One Fight Night",
                 "Boxing: De Los Santos v Valenzuela",
                 "UFC Fight Night Early Prelims"):
        check("CARD", f"while '{real}' is a broadcast",
              bool(sky_epg.A_REPEAT.search(real)), False)

    check("CARD", "a highlights show is not a fight",
          "UFC Fight Night Highlights" in names, False)
    check("CARD", "and neither is the football",
          "Football Tonight" in names, False)
    check("CARD", "a programme with no instant is refused, never dated",
          "UFC 331" in names, False)

    prelim = next(e for e in got if e["title"] == "UFC Fight Night Prelims")
    check("CARD", "the prelims start when Sky says, to the minute",
          f"{prelim['start']:%Y-%m-%d %H:%M} UTC",
          f"{datetime.fromtimestamp(1788627600, timezone.utc):%Y-%m-%d %H:%M} UTC")
    check("CARD", "on the channel actually carrying it",
          prelim["channels"], ["TNT Sports 1"])
    check("CARD", "and the board files it under MMA", prelim["sport"], "MMA")
    check("CARD", "while the boxing is filed as boxing",
          next(e for e in got if e["title"] == "Boxing")["sport"], "Boxing")

    # The prelims are kept because they are a UFC programme, not because
    # of the word — so an early prelim arrives by the same rule.
    early = _json.dumps({"schedule": [{"events": [
        {"st": 1788624000, "d": 3600,
         "t": "Live: UFC Fight Night Early Prelims", "sy": "First up."}]}]})

    class EarlyDay(OneDay):
        def request(self, method, url, **kw):
            class Answer:
                text = early
                status_code = 200

                def raise_for_status(self):
                    return None
            return Answer()

    check("CARD", "and an EARLY prelim arrives by the same rule",
          [e["title"] for e in
           sky_epg.a_day(EarlyDay(), "3625", "TNT Sports 1", "20260905")],
          ["UFC Fight Night Early Prelims"])

def main() -> int:
    print("CHANNEL GATES | every guide must refuse other broadcasters' channels")
    for gate in (gate_onsport, gate_jordan, gate_shahid, gate_not_a_team,
                 gate_channel_is_never_a_team,
                 gate_one_match_one_row,
                 gate_one_club_across_two_scripts,
                 gate_a_fact_survives_its_source,
                 gate_every_guide_is_covered,
                 gate_the_screen_cannot_go_stale,
                 gate_two_pages_make_one_row,
                 gate_a_day_divider_is_not_a_container,
                 gate_the_printed_clock_is_the_kickoff,
                 gate_a_day_drawn_is_a_day_collected,
                 gate_the_third_page_fills_the_gap,
                 gate_our_own_guides_name_the_channel,
                 gate_the_american_channel_is_named,
                 gate_a_grid_title_is_read_the_way_that_grid_writes_it,
                 gate_a_row_names_two_channels,
                 gate_a_board_says_which_day_it_is,
                 gate_the_jordanian_league_is_read,
                 gate_a_guide_repeating_its_own_name_is_measured,
                 gate_a_long_wait_says_how_long,
                 gate_turkeys_own_league_is_read,
                 gate_the_other_sports_name_a_real_channel,
                 gate_the_american_game_names_its_network,
                 gate_the_second_board_keeps_the_readers_order,
                 gate_the_round_is_read_from_the_leagues_own_page,
                 gate_a_board_that_is_built_is_a_board_that_is_published,
                 gate_one_channel_spelled_two_ways_is_one_channel,
                 gate_the_window_keeps_moving,
                 gate_a_simulcast_is_not_a_second_channel,
                 gate_each_channel_wears_its_own_mark,
                 gate_the_channel_comes_from_the_broadcasters_own_feed,
                 gate_the_second_board_names_channels_like_the_first,
                 gate_no_guide_reads_a_stranger,
                 gate_a_row_says_which_competition_it_is,
                 gate_our_own_guides_carry_fights_nobody_lists,
                 gate_the_channel_plays_the_days_in_order,
                 gate_a_day_that_is_over_leaves_the_screen,
                 gate_midnight_is_not_a_kickoff,
                 gate_turkey_comes_from_the_sources_asked_for,
                 gate_alwan_reaches_the_board,
                 gate_the_news_channel_says_only_what_a_newsroom_published,
                 gate_alwan_carries_more_than_football,
                 gate_the_card_is_split_by_the_broadcaster,
                 gate_two_sources_naming_one_broadcast_is_one_row):
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
