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
programme. tipoEmissao is the field that should settle it outright and
its values were not readable in the probe, so every distinct value this
sees is LOGGED on each build: the day it shows a word for "live", this
reader uses it and the name list stops mattering.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

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
}

# NOT A CONTEST. The site's own words for the things around a fixture:
# no broadcast at all, the news category, the aftermath and the preview,
# the magazine and the round-up.
NOT_A_CONTEST = re.compile(
    r"sem\s+transmiss[ãa]o|informa[çc][ãa]o|not[íi]cias"
    r"|rescaldo|antevis[ãa]o|magazine|resumo|highlights"
    r"|melhores\s+momentos|reda[çc][ãa]o|estúdio|estudio", re.I)


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


def one_channel(session, cid: str, slug: str, shown: str,
                seen_types: Counter) -> list[dict]:
    """Every live contest this one channel is carrying."""
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

        out.append({
            "start": start,
            "title": fixture.title() if fixture.isupper() else fixture,
            "competition": (competition.title()
                            if competition.isupper() else competition),
            "sport": sport,
            "channels": [shown],
        })
    return out


def events(session, floor: datetime | None = None,
           ceiling: datetime | None = None) -> list[dict]:
    """Every live contest the six channels carry, inside the window."""
    seen_types: Counter = Counter()
    out: list[dict] = []
    for cid, slug, shown in CHANNELS:
        try:
            rows = one_channel(session, cid, slug, shown, seen_types)
        except Exception as exc:                               # noqa: BLE001
            warn(f"sporttv {shown} is unreadable ({exc}) — the other "
                 f"channels still count")
            continue
        log(f"  sporttv {shown}: {len(rows)} live contest(s)")
        out += rows

    if seen_types:
        # The field that SHOULD settle live from recorded outright. Its
        # values were not readable in the probe, so they are printed on
        # every build: the day one of them says "direto", this reader
        # uses it and NOT_A_CONTEST stops carrying the weight alone.
        log(f"  sporttv tipoEmissao seen: {dict(seen_types.most_common(8))}")

    if floor and ceiling:
        out = [e for e in out if floor <= e["start"] < ceiling]
    log(f"sporttv: {len(out)} live contest(s) across "
        f"{len(CHANNELS)} channel(s)")
    return out
