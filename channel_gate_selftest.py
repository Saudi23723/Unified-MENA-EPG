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

    boards_dir, stream_dir = "boards", "stream"
    playlist = _os.path.join(stream_dir, "screen.m3u8")

    if not _os.path.isdir(boards_dir) or not _os.path.exists(playlist):
        # Nothing published yet is not a failure: a fresh clone has no
        # screen until the first build makes one.
        check("SCREEN", "nothing published yet, nothing to contradict",
              True, True)
        return

    boards = sorted(name for name in _os.listdir(boards_dir)
                    if name.startswith("today_matches_")
                    and name.endswith(".png"))
    with open(playlist, encoding="utf-8") as handle:
        referenced = [line.strip() for line in handle
                      if line.strip().endswith(".ts")]
    distinct = sorted(set(referenced))

    check("SCREEN", "the playlist names one segment per board",
          len(distinct), len(boards))

    # Every reference resolves to a file that is actually published.
    missing = [name for name in distinct
               if not _os.path.exists(_os.path.join(stream_dir, name))]
    check("SCREEN", "every segment the playlist names exists",
          missing, [])

    # Nothing published that no playlist points at — the deletion pass has
    # to keep working or the repository grows a few files a day forever.
    on_disk = {name for name in _os.listdir(stream_dir)
               if name.endswith(".ts")}
    check("SCREEN", "and nothing is published that it does not name",
          sorted(on_disk - set(distinct)), [])

    # The heart of it: the name has to be the fingerprint of the picture.
    wrong = []
    for board in boards:
        with open(_os.path.join(boards_dir, board), "rb") as handle:
            body = handle.read()
        running = hashlib.sha256()
        running.update(_os.path.join(boards_dir, board).encode())
        running.update(body)
        stem = _os.path.splitext(board)[0]
        expected = f"{stem}.{running.hexdigest()[:8]}.ts"
        if expected not in distinct:
            wrong.append(f"{board} -> expected {expected}")
    check("SCREEN", "each segment is named after the board it shows",
          wrong, [])

    # And the names must not be the old fixed ones, which is the shape the
    # bug had: a name that cannot change when the picture does.
    unversioned = [name for name in distinct
                   if _re.fullmatch(r"today_matches_\d+\.ts", name)]
    check("SCREEN", "no segment carries a name a cache could reuse",
          unversioned, [])


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
        clubs("كفرسوم", "VS", "جرش"),
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
          ["كفرسوم - جرش", "البقعة - دوقرة"])
    check("JOR", "a match already played is not a fixture",
          any("الوحدات" in event["title"] for event in read), False)
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
              + clubs("كفرسوم", "VS", "جرش")
              + clubs("البقعة", "VS", "دوقرة")
              + "</table>")
    check("JOR", "a fixture with no header of its own is refused",
          [event["title"] for event in jordan_football.collect(orphan)],
          ["كفرسوم - جرش"])

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
                 gate_a_long_wait_says_how_long):
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
