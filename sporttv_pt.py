#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPORT TV Portugal's own EPG, read off each channel's live page.

FIVE ROUNDS OF PROBES BEFORE A LINE OF THIS WAS WRITTEN, because every
obvious way in was a dead end and following one would have produced a
reader that could never work:

  /guia            1.7MB of HTML holding 26 clocks — and all 26 are the
                   hour ruler (class="hour" 00:00, 01:00 …). The grid is
                   drawn in the browser. The same wall tvkampen put up.
  /jogos           200, and ZERO clocks, ZERO events. An empty shell.
  /jogos/hoje      404, and so are /diretos, /em-direto, /programacao.

WHAT DOES ANSWER is each channel's own live page. It carries a 164KB
<script type="application/json"> whose commonest keys are a broadcast
schedule in Portuguese, 85 of each — one per programme:

    data · descricao · modalidade · duracao · canal
    tipoEmissao · evento · id_epg · nomeModalidade

AND ITS FIELDS ARE INDICES, NOT VALUES. tipoEmissao reads 2021, data
reads 2198, and 336 rows all report exclusivo=2021. They are POSITIONS
in a flat reference table — the whole blob is one list, and a field is
read by following its index, which is how a store is serialised without
repeating a string four hundred times. Read as values they are a filter
on a number nobody wrote. Followed, they say:

    data        1789335000000                      a real UNIX instant
    duracao     1800000                            thirty minutes
    evento      LIGA PORTUGAL BETCLIC - FUTEBOL    competition and sport
    descricao   CASA PIA AC X FC PORTO             the fixture
    descricao   RANGERS X CELTIC - QUARTOS DE FINAL

THE CHANNELS ARE THE SITE'S OWN, from live-sitemap.xml rather than
guessed. It publishes EIGHT; six were asked for and six are read —
"+ و ١ و ٢ و ٣ و ٤ و ٥ و البلس". SPORT.TV6 and SPORT.TV7 exist and are
deliberately not here.

ONLY WHAT IS BEING PLAYED, asked for in those words. The site says so
itself in the rows this refuses: SEM TRANSMISSÃO is no broadcast at
all, INFORMAÇÃO is the news category, and RESCALDO is the aftermath
programme. The store's tipoEmissao is now used as the authoritative gate:
only DIRETO survives, while Recorded, Magazine, Long Summary, replay, and
empty-state rows are rejected.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn
import canal11_pt
import dazn_pt

BASE = "https://www.sporttv.pt"

# The site's own ids and names, out of live-sitemap.xml. Six of the eight
# it publishes: SPORT.TV6 (7577) and SPORT.TV7 (7600) were not asked for.
CHANNELS = (
    ("727", "SPORT.TV1", "Sport TV1"),
    ("728", "SPORT.TV2", "Sport TV2"),
    ("729", "SPORT.TV3", "Sport TV3"),
    ("5406", "SPORT.TV4", "Sport TV4"),
    ("5422", "SPORT.TV5", "Sport TV5"),
    ("7133", "SPORT.TV+", "Sport TV+"),
)

# The sport, in this board's words, from the site's own modalidade.
A_SPORT = {
    "FUTEBOL": "Football", "FUTSAL": "Futsal", "ANDEBOL": "Handball",
    "BASQUETEBOL": "Basketball", "VOLEIBOL": "Volleyball",
    "AUTOMOBILISMO": "Motorsport", "MOTOCICLISMO": "Motorsport",
    "TENIS": "Tennis", "TÉNIS": "Tennis", "PADEL": "Padel",
    "GOLFE": "Golf", "RUGBY": "Rugby", "CICLISMO": "Cycling",
    "ATLETISMO": "Athletics", "NATACAO": "Swimming", "NATAÇÃO": "Swimming",
    "HOQUEI": "Hockey", "HÓQUEI": "Hockey", "BOXE": "Boxing",
    "MMA": "MMA", "VELA": "Sailing", "SNOOKER": "Snooker",
    "DARDOS": "Darts", "TRIATLO": "Triathlon",
    # "DESPORTOS COMBATE" — combat sports, the word SPORT TV files UFC BJJ
    # and ONE Championship under ("UFC BJJ - DESPORTOS COMBATE", "BJJ 11 -
    # MUSUMECI X MITCHELL", live on SPORT TV1, measured 25.09.2026). Left
    # out of this table, every one of those rows was dropped as a sport
    # the board does not carry: "why isn't Sport TV showing UFC BJJ live
    # on Sport TV 1?". They sit with the MMA they are shown beside.
    "DESPORTOS COMBATE": "MMA", "DESPORTOS DE COMBATE": "MMA",
}

# NOT A CONTEST — the shared Portuguese vocabulary, not a second copy.
#
# This list used to be this module's own, and it was missing the four
# words that matter most to "إعادة لا": repetição, replay, gravado
# and recorded. DAZN's reader had them; this one did not, so a repeat on
# SPORT TV was stopped only by the store's tipoEmissao — the field whose
# values the note below says were not readable in the probe.
#
# Both readers now ask the same question with the same words. See
# dazn_pt.NOT_A_LIVE_CONTEST for which words, and why each is there.
NOT_A_CONTEST = dazn_pt.NOT_A_LIVE_CONTEST

# The broadcaster's own state is authoritative. Only DIRETO is a live
# broadcast; Recorded, Magazine, Long Summary, replay, and empty-state rows
# are never allowed onto this channel.
LIVE_BROADCAST = "DIRETO"


def biggest_json(text: str) -> str:
    """The largest inline application/json — the serialised store."""
    best = ""
    for found in re.finditer(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            text, re.S):
        if len(found.group(1)) > len(best):
            best = found.group(1)
    return best


def follower(table: list):
    """Follow an index into the flat table, and keep following."""
    def at(index, depth: int = 0):
        if depth > 6 or not isinstance(index, int):
            return index
        if not 0 <= index < len(table):
            return index
        value = table[index]
        if isinstance(value, dict):
            return {k: at(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [at(v, depth + 1) for v in value]
        return value
    return at


def split_event(name: str) -> tuple[str, str]:
    """"LIGA PORTUGAL BETCLIC - FUTEBOL" -> competition, sport-word."""
    if " - " in name:
        head, _, tail = name.rpartition(" - ")
        return head.strip(), tail.strip()
    return name.strip(), ""


# WHICH CHANNEL A ROW IS ON comes from the ROW, never from the page it
# was fetched off. Each channel's page carries the schedule for ALL of
# them — "epg" appears eight times in the store — so taking the page's
# channel put every fixture on all six at once: 54 rows each, "Casa Pia
# AC X FC Porto" on TV1 and TV2 and TV+ together. The row's own canal
# says which one it really is.
BY_ID = {int(cid): shown for cid, _slug, shown in CHANNELS}
BY_NAME = {slug.replace(".", "").replace(" ", "").upper(): shown
           for _cid, slug, shown in CHANNELS}


def channel_of(value) -> str:
    """The display name for a row's canal, or "" if it is not one of ours."""
    if isinstance(value, dict):
        for key in ("id", "codigo", "canalId"):
            try:
                found = BY_ID.get(int(value.get(key)))
            except (TypeError, ValueError):
                found = None
            if found:
                return found
        for key in ("nome", "name", "descricao"):
            word = str(value.get(key) or "").replace(".", "")
            word = word.replace(" ", "").replace("-", "").upper()
            if word in BY_NAME:
                return BY_NAME[word]
        return ""
    try:
        return BY_ID.get(int(value), "")
    except (TypeError, ValueError):
        return ""


def one_channel(session, cid: str, slug: str, shown: str,
                seen_types: Counter, seen_canal: Counter) -> list[dict]:
    """Every live contest in this page's store, each on its OWN channel."""
    got = fetch(session, f"{BASE}/live/canal/{cid}/{slug}")
    table = json.loads(biggest_json(got.text))
    if not isinstance(table, list):
        warn(f"sporttv {shown}: the store is not the flat table expected")
        return []
    at = follower(table)

    out = []
    for row in table:
        if not (isinstance(row, dict) and "tipoEmissao" in row):
            continue
        seen_types[str(at(row.get("tipoEmissao")))] += 1
        canal = at(row.get("canal"))
        seen_canal[json.dumps(canal, ensure_ascii=False)[:60]
                   if isinstance(canal, (dict, list)) else str(canal)] += 1
        on = channel_of(canal)
        if not on:
            # Not one of the six asked for — SPORT.TV6 and SPORT.TV7 are
            # in this store too and were not asked for.
            continue

        if str(at(row.get("tipoEmissao")) or "").strip().upper() != LIVE_BROADCAST:
            continue

        when = at(row.get("data"))
        if not isinstance(when, int) or when < 1_000_000_000_000:
            continue
        start = datetime.fromtimestamp(when / 1000, tz=timezone.utc)

        event = at(row.get("evento")) or {}
        name = (event.get("nome") or "") if isinstance(event, dict) else ""
        fixture = norm(str(at(row.get("descricao")) or ""))
        competition, sport_word = split_event(norm(str(name)))

        if NOT_A_CONTEST.search(f"{name} {fixture}"):
            continue
        if not fixture:
            continue

        mode = at(row.get("modalidade")) or {}
        word = (mode.get("nomeModalidade") if isinstance(mode, dict)
                else None) or sport_word
        sport = A_SPORT.get(str(word).strip().upper())
        if not sport:
            continue

        # THE LENGTH THE BROADCASTER PUBLISHED, so مباشر comes off this
        # row when the broadcast ends rather than when a table guesses
        # it should. epg_lib.on_air_span prefers this over the sport's
        # figure and still bounds it by the floor and the ceiling.
        span = at(row.get("duracao"))
        stated = (timedelta(milliseconds=span)
                  if isinstance(span, int) and span > 0 else None)

        out.append({
            "start": start,
            "on_air_for": stated,
            "title": fixture.title() if fixture.isupper() else fixture,
            "competition": (competition.title()
                            if competition.isupper() else competition),
            "sport": sport,
            "channels": [on],
        })
    return out


def events(session, floor: datetime | None = None,
           ceiling: datetime | None = None) -> list[dict]:
    """Live Sport TV contests plus live/scheduled DAZN Portugal events."""
    seen_types: Counter = Counter()
    seen_canal: Counter = Counter()
    out: list[dict] = []

    # EVERY PAGE CARRIES EVERY CHANNEL'S SCHEDULE, so the same broadcast
    # arrives six times over. They are folded on what actually
    # identifies one — the instant, the fixture and the channel it is
    # really on — rather than counted six times.
    seen: set = set()
    for cid, slug, shown in CHANNELS:
        try:
            rows = one_channel(session, cid, slug, shown,
                               seen_types, seen_canal)
        except Exception as exc:                               # noqa: BLE001
            warn(f"sporttv {shown} is unreadable ({exc}) — the other "
                 f"pages still count")
            continue
        fresh = 0
        for row in rows:
            key = (row["start"], row["title"], row["channels"][0])
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
            fresh += 1
        log(f"  sporttv page {shown}: {len(rows)} row(s), {fresh} new")

    if seen_canal:
        log(f"  sporttv canal seen: {dict(seen_canal.most_common(10))}")
    if seen_types:
        # The field that SHOULD settle live from recorded outright. Its
        # values were not readable in the probe, so they are printed on
        # every build: the day one of them says "direto", this reader
        # uses it and NOT_A_CONTEST stops carrying the weight alone.
        log(f"  sporttv tipoEmissao seen: {dict(seen_types.most_common(8))}")

    if floor and ceiling:
        out = [e for e in out if floor <= e["start"] < ceiling]
    dazn = dazn_pt.events(session, floor, ceiling)
    out.extend(dazn)

    # AND THE FEDERATION'S OWN CHANNEL. Canal 11 carries the national
    # teams and the under-21s, Liga 3, the Campeonato de Portugal, Liga
    # Revelação and the women's game — none of which is on SPORT TV's six
    # live pages or DAZN's rail, so none of it was reaching this channel.
    # See canal11_pt.py for which page it is read from and why, and for
    # the two rounds of probing that proved the rows are that channel's.
    onze = canal11_pt.events(session, floor, ceiling)
    out.extend(onze)

    log(f"sporttv Portugal: {len(out)} live/scheduled event(s), including "
        f"{len(dazn)} from DAZN Portugal and {len(onze)} from Canal 11")
    return out
