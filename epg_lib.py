#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared, hardened helpers for every EPG generator script in this repository.

Design goals (applies to every script that imports this module):
  - Never crash the whole run because one source failed (network error,
    schema change, empty response). Log a WARN and continue.
  - Never overwrite a previously good XMLTV file with an empty/broken one.
  - Always write atomically (write to .tmp, validate, os.replace).
  - Always produce valid, non-overlapping XMLTV programmes.
  - Mark events that are happening right now with a "Live" suffix so
    TiviMate (and any XMLTV client) shows it at a glance.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape

import requests

UTC = timezone.utc

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

HTTP_TIMEOUT = 20
# A source having a bad moment should not cost a whole cycle. Four
# attempts with a growing pause spans roughly half a minute of trying,
# which covers a restart or a blip; anything longer than that is not a
# blip, and the guide keeps its previous file and tries again on its own
# schedule rather than holding the run open.
HTTP_RETRIES = 4
HTTP_BACKOFF = 3.0

# Suffix appended to the title of a programme that is airing right now.
# Kept as a single constant so every script renders it identically.
LIVE_SUFFIX = " • Live \U0001F7E2"  # " • Live 🟢"


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"WARN {msg}", flush=True)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_session(extra_headers: dict | None = None) -> requests.Session:
    s = requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)
    s.headers.update(headers)
    return s


def fetch(session: requests.Session, url: str, *, params=None, headers=None,
          method: str = "GET", json_body=None, data=None,
          retries: int = HTTP_RETRIES, timeout: int = HTTP_TIMEOUT):
    """GET/POST with retries + exponential backoff. Raises on final failure.

    `json_body` sends a JSON body; `data` sends a form-encoded (or raw)
    body — pass at most one of them.
    """
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = session.request(
                method, url, params=params, headers=headers,
                json=json_body, data=data, timeout=timeout,
            )
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001 - deliberately broad, retried
            last = exc
            if attempt < retries:
                wait = HTTP_BACKOFF * attempt
                warn(f"retry {attempt}/{retries - 1} after {wait:.0f}s | {url} | {exc}")
                time.sleep(wait)
    raise last  # type: ignore[misc]


def xmltv_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S +0000")


def is_live_now(start: datetime, stop: datetime, now: datetime | None = None) -> bool:
    now = now or utc_now()
    return start <= now < stop


def live_title(title: str, start: datetime, stop: datetime, now: datetime | None = None) -> str:
    """Append the Live marker to a title only while the event is in progress."""
    if is_live_now(start, stop, now):
        return f"{title}{LIVE_SUFFIX}"
    return title


def add_programme(
    root: ET.Element,
    channel_id: str,
    start: datetime,
    stop: datetime,
    title: str,
    desc: str = "",
    *,
    category: str | None = None,
    icon: str | None = None,
    live_eligible: bool = False,
    now: datetime | None = None,
    alt_titles: list[tuple[str, str]] | None = None,
) -> ET.Element:
    """Append one <programme> element. When live_eligible=True the title gets
    the Live marker automatically if `now` falls inside [start, stop).

    `alt_titles` is a list of (lang, text) written as further <title>
    elements right after the main one — for a guide that has the same
    programme in two languages and wants both in the file. XMLTV allows
    repeated <title>, and a player picks whichever language it prefers,
    falling back to the first. So pass the language you want shown as
    `title`, and the other as an alt.
    """
    shown_title = live_title(title, start, stop, now) if live_eligible else title

    p = ET.SubElement(
        root, "programme",
        start=xmltv_time(start), stop=xmltv_time(stop), channel=channel_id,
    )
    lang = "ar" if re.search(r"[؀-ۿ]", shown_title) else "en"
    ET.SubElement(p, "title", lang=lang).text = shown_title
    for alt_lang, alt_text in (alt_titles or []):
        alt_text = (alt_text or "").strip()
        # Skip an alt that is empty or just repeats what is already shown.
        if alt_text and alt_text != shown_title:
            ET.SubElement(p, "title", lang=alt_lang).text = alt_text
    if desc:
        dlang = "ar" if re.search(r"[؀-ۿ]", desc) else "en"
        ET.SubElement(p, "desc", lang=dlang).text = desc
    if category:
        clang = "ar" if re.search(r"[؀-ۿ]", category) else "en"
        ET.SubElement(p, "category", lang=clang).text = category
    # One rule for the Live category, wherever the badge came from: the
    # caller may have badged the title itself (a source that declares a
    # live broadcast), or asked for the on-air rule below. Either way the
    # programme is tagged Live exactly once, so a player can filter on it
    # on every guide rather than only on the ones that remembered.
    if carries_live_badge(shown_title) or (live_eligible and is_live_now(start, stop, now)):
        ET.SubElement(p, "category", lang="en").text = "Live"
    if icon:
        ET.SubElement(p, "icon", src=icon)
    return p


def existing_programme_count(path: str) -> int:
    try:
        if not os.path.exists(path):
            return 0
        return len(ET.parse(path).getroot().findall("programme"))
    except Exception:
        return 0


def existing_channel_count(path: str) -> int:
    try:
        if not os.path.exists(path):
            return 0
        return len(ET.parse(path).getroot().findall("channel"))
    except Exception:
        return 0


# A run that comes back with a fraction of what the file already holds is
# far more likely to be a source half-answering than a real schedule
# change, and publishing it would empty out a guide people are using. The
# floor is deliberately low — a guide may legitimately shrink when a
# source is swapped or a tournament ends — so it only catches a collapse,
# not ordinary movement. MIN_KEEP_RATIO is what a run must retain of the
# previous file to be allowed to replace it.
MIN_KEEP_RATIO = 0.35
# Below this many programmes the ratio is meaningless: a guide with 8
# entries dropping to 2 is noise, not a collapse.
REGRESSION_FLOOR = 40


def collapsed_against_previous(root: ET.Element, output_path: str) -> str:
    """Why this run must not replace the existing file, or "" if it may.

    Compares both counts. Returning a reason rather than a bool keeps the
    warning specific enough to act on.
    """
    for label, new_count, old_count in (
        ("programmes", len(root.findall("programme")),
         existing_programme_count(output_path)),
        ("channels", len(root.findall("channel")),
         existing_channel_count(output_path)),
    ):
        if old_count < REGRESSION_FLOOR or new_count >= old_count * MIN_KEEP_RATIO:
            continue
        return (f"{new_count} {label} this run against {old_count} in the "
                f"existing file — under {MIN_KEEP_RATIO:.0%} of it")
    return ""


def order_for_xmltv(root: ET.Element) -> int:
    """Put every <channel> before every <programme>, in place.

    XMLTV's DTD is `<!ELEMENT tv (channel*, programme*)>` — all channels,
    then all programmes. A guide that appends a channel after it has begun
    writing programmes still *contains* that channel, and every check here
    still finds it, but a strict reader is entitled to stop accepting
    channel declarations once programmes have started, and TiviMate does.

    That is not hypothetical. The Jordan guide reads its own channels and
    then hands the tree to aljadeed_epg, aljazeera_epg and filler_epg in
    turn, each declaring its channel and then writing its programmes — four
    channel blocks interleaved with programmes. On a television, the first
    twenty-seven channels appeared and the eighteen after them did not,
    while every check in this repository reported them present, because
    they *were* present, only in a place a reader may ignore. The merged
    guide had thirteen such blocks, one per source.

    Ordering here rather than in each generator means no guide can make
    this mistake again: they may build a tree in whatever order suits
    them, and it leaves through this function correct.

    Returns the number of channel blocks the tree had before reordering —
    1 (or 0) was already valid, more was not.
    """
    children = list(root)
    blocks, previous = 0, None
    for node in children:
        if node.tag not in ("channel", "programme"):
            continue
        if node.tag == "channel" and previous != "channel":
            blocks += 1
        previous = node.tag

    if blocks > 1:
        channels = [n for n in children if n.tag == "channel"]
        programmes = [n for n in children if n.tag == "programme"]
        others = [n for n in children if n.tag not in ("channel", "programme")]
        for node in children:
            root.remove(node)
        for node in others + channels + programmes:
            root.append(node)

    return blocks


def write_xml_atomic(
    root: ET.Element,
    output_path: str,
    *,
    keep_old_if_empty: bool = True,
    check_overlaps: bool = True,
    guard_regression: bool = True,
    min_programmes: int = 0,
    generator_name: str = "Unified MENA EPG",
) -> bool:
    """Validate + atomically write an XMLTV tree. Returns True if written.

    Two things it refuses to do, both about protecting a file that is
    already good: replace it with a run that produced nothing, and replace
    it with a run that collapsed to a fraction of it. Either way the
    previous file stays exactly as it is and the run says why.

    Pass guard_regression=False only where a large drop is expected and
    intended — a guide deliberately narrowed to fewer channels, or moved
    to a source that publishes fewer days. Give such a guide a
    min_programmes floor instead: comparing against the previous file is
    meaningless once the size has legitimately changed, but an absolute
    floor still catches a source that half-answers.
    """
    blocks = order_for_xmltv(root)
    if blocks > 1:
        log(f"{output_path}: {blocks} channel blocks were interleaved with "
            f"programmes — reordered so every channel precedes every "
            f"programme, as XMLTV requires")

    programme_count = len(root.findall("programme"))

    if programme_count == 0 and keep_old_if_empty and existing_programme_count(output_path) > 0:
        warn(
            f"0 programmes produced this run — sources likely unreachable. "
            f"Keeping previous {output_path} untouched."
        )
        return False

    if min_programmes and programme_count < min_programmes:
        if existing_programme_count(output_path) > 0:
            warn(
                f"REFUSING to publish {output_path}: {programme_count} programmes "
                f"is under this guide's floor of {min_programmes}. Keeping the "
                f"previous file untouched."
            )
            return False
        warn(f"{output_path}: {programme_count} programmes is under the floor of "
             f"{min_programmes}, but there is no previous file to keep — "
             f"publishing it rather than leaving nothing.")

    if guard_regression:
        reason = collapsed_against_previous(root, output_path)
        if reason:
            warn(
                f"REFUSING to publish {output_path}: {reason}. "
                f"Keeping the previous file untouched. If this drop is real "
                f"and intended, pass guard_regression=False for this guide."
            )
            return False

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    tmp_path = f"{output_path}.tmp"
    ET.ElementTree(root).write(tmp_path, encoding="utf-8", xml_declaration=True)

    # Refuse to ever leave a malformed file behind.
    tree = ET.parse(tmp_path)

    # Structural sanity check: every programme must have stop > start and
    # programmes per channel must not overlap.
    def _p(s: str) -> datetime:
        return datetime.strptime(s, "%Y%m%d%H%M%S %z")

    # Overlap is a property of the schedule, not of the order the file
    # happens to store it in — XMLTV allows any order and several guides
    # here do write out of order. Collect per channel, then judge sorted,
    # so an unsorted-but-valid file is never rejected.
    spans: dict[str, list[tuple[datetime, datetime]]] = {}
    for pr in tree.getroot().findall("programme"):
        ch = pr.get("channel")
        st, sp = _p(pr.get("start")), _p(pr.get("stop"))
        if sp <= st:
            raise ValueError(f"invalid programme duration on {ch}: {pr.get('start')} -> {pr.get('stop')}")
        if check_overlaps:
            spans.setdefault(ch, []).append((st, sp))

    for ch, rows in spans.items():
        cursor = None
        for st, sp in sorted(rows):
            if cursor is not None and st < cursor:
                raise ValueError(f"overlapping programmes on {ch} at {st:%Y%m%d%H%M%S %z}")
            cursor = sp if cursor is None else max(cursor, sp)

    os.replace(tmp_path, output_path)
    log(f"Written and XML-validated: {output_path} ({programme_count} programmes)")
    return True


def resolve_overlaps(events: list[dict]) -> list[dict]:
    """Sort a single channel's events by start and remove overlaps.

    XMLTV cannot express two programmes at once on one channel, and some
    sources publish them anyway — Spor Ekranı gives every live slot a
    padded three-hour window, so two events beginning together is routine.
    Something has to give; this chooses which.

    **A start time is kept as published; a stop time is what gives way.**
    An event that begins before the previous one has ended cuts that
    previous event short rather than being pushed out behind it.

    It used to be the other way round, and it put real broadcasts at the
    wrong hour. Spor Ekranı listed both "Badminton - Neslihan Arın" and
    "Paletli Yüzme" starting 18:00 on tabii Spor 7; the second was shoved
    to 21:00, three hours after it actually began, and published that way.
    A viewer setting a reminder from that would have missed it entirely.
    A stop time is an estimate — for a live match nobody knows it in
    advance — while a start time is the one number the source is sure of
    and the one a viewer acts on. So the estimate yields.

    Two events that begin at the very same minute cannot both survive: the
    first in sort order is kept and the other dropped, since cutting one
    short would leave it with no duration at all.
    """
    ordered = sorted(events, key=lambda e: (e["start"], e["stop"]))
    out: list[dict] = []
    for ev in ordered:
        start, stop = ev["start"], ev["stop"]
        if stop <= start:
            continue
        if out:
            previous = out[-1]
            if start < previous["stop"]:
                if start <= previous["start"]:
                    # Same minute: keeping both is impossible and cutting
                    # the earlier one leaves it empty, so this one goes.
                    continue
                previous["stop"] = start
        out.append({**ev, "start": start, "stop": stop})
    return out


def dedupe_events(events: list[dict], key_fn, priority_fn=None) -> list[dict]:
    """Keep the highest-priority event per key (default: first wins)."""
    best: dict = {}
    for ev in events:
        k = key_fn(ev)
        old = best.get(k)
        if old is None:
            best[k] = ev
            continue
        if priority_fn and priority_fn(ev) > priority_fn(old):
            best[k] = ev
    return list(best.values())


def run_main(build_fn, output_path: str) -> int:
    """Standard entrypoint wrapper: never let an uncaught exception break the
    workflow's git step — always exit cleanly and preserve the old file."""
    try:
        return build_fn()
    except Exception as exc:  # noqa: BLE001
        warn(f"FATAL: {exc}")
        if existing_programme_count(output_path) > 0:
            warn(f"Keeping previous {output_path} untouched after fatal error.")
            return 0
        return 1


# ---------------------------------------------------------------------------
# Guide-channel helpers: live badge + "time until kickoff" countdown
# ---------------------------------------------------------------------------

LRM = "‎"

# The blue badge used by the guide-style channels (Shasha, Shahid). It marks
# the programme as a LIVE BROADCAST — the standard EPG meaning — so it stays
# visible when browsing ahead, exactly like update_alwan_epg.py does.
LIVE_BADGE = "• Live \U0001F535"  # "• Live 🔵"

# Same badge in other colours, so each guide can be told apart at a glance
# in a merged listing: green for Thmanyah, purple for Alkass and STARZPLAY.
LIVE_BADGE_GREEN = "• Live \U0001F7E2"   # "• Live 🟢"
LIVE_BADGE_PURPLE = "• Live \U0001F7E3"  # "• Live 🟣"


def ltr(value: str) -> str:
    """Wrap a Latin run so it keeps its own order inside RTL text."""
    return f"{LRM}{value}{LRM}"


def with_live_badge(title: str, badge: str = LIVE_BADGE) -> str:
    return f"{title} {ltr(badge)}"


def carries_live_badge(title: str) -> bool:
    """Whether a title has already been marked as a live broadcast.

    Any of the three colours counts. add_programme uses this to attach the
    Live category, so a guide that badges a title never has to remember to
    add the category too — the two can no longer drift apart.
    """
    return any(b in (title or "")
               for b in (LIVE_BADGE, LIVE_BADGE_GREEN, LIVE_BADGE_PURPLE, LIVE_SUFFIX))


# Marks a row as a countdown rather than a broadcast. Without it a guide
# full of "Bayern München - Stuttgart · بعد 7 س" reads, at a glance in a
# grid, as seven hours of Bayern München — the clock is what says the row
# is a wait, not a programme.
COUNTDOWN_MARK = "\u23f0"          # ⏰


# Words that name a date, a competition or a stage of one — never a club.
#
# Every guide that reads a fixture out of prose has to tell a team from a
# heading, and each had learned that in one language only. Shahid rejected
# "أغسطس" and published "August"; rejected "الجولة 2" and published
# "Round 2"; rejected "الدوري الفرنسي" and published "Premier League" —
# and the mirror image, rejecting "Monday" while publishing "الاثنين".
# Nine such pairs, each one a heading that reached the guide dressed as a
# fixture in whichever language the filter had not been taught.
#
# One vocabulary, both scripts, in one place, so a guide cannot be strict
# in Arabic and careless in English.
#
# Matched on word boundaries, never as substrings, and that matters in
# both directions: "ودية" sits inside "السعودية" and "cup" inside a dozen
# innocent words. \b works on Arabic letters here because they are word
# characters, so "ودية" cannot fire inside "السعودية".
# Split in two, because the two halves are worth different things.
#
# A date is furniture: "أغسطس" on a page is the day the page was written,
# and there is nothing to keep. A competition is not — "الدوري الألماني،
# الجولة 2" says which league and which matchday, which is exactly what a
# viewer opening a programme wants to read. Telling a club from a heading
# is one job; throwing the heading away afterwards is a different and
# worse decision, and this repository was making it.
DATE_WORD = re.compile(
    # months
    r"\b(?:january|february|march|april|may|june|july|august|september"
    r"|october|november|december)\b"
    r"|\b(?:jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\b"
    r"|\b(?:يناير|فبراير|مارس|[أا]بريل|مايو|يونيو|يوليو|[أا]غسطس|سبتمبر"
    r"|[أا]كتوبر|نوفمبر|ديسمبر|كانون|شباط|[آأا]ذار|نيسان|[أا]يار|حزيران"
    r"|تموز|[آأا]ب|[أا]يلول|تشرين)\b"
    # weekdays
    r"|\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\b(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b"
    r"|\b(?:الاثنين|الإثنين|الثلاثاء|الأربعاء|الاربعاء|الخميس|الجمعة"
    r"|السبت|الأحد|الاحد|اليوم|غدا|غد[اً]?|[أا]مس)\b"
    , re.I,
)

COMPETITION_NAME = re.compile(
    r"\b(?:league|cup|supercup|trophy|championship|friendly|qualifier"
    r"|qualifiers|playoff|playoffs|matchday|matchweek|gameweek|round"
    r"|week|leg|group|stage|final|finals|semi|quarter)\b"
    r"|\b(?:semi|quarter)[\s-]?finals?\b"
    r"|\b(?:super\s+cup|play[\s-]?off)\b"
    # Competition names in their own language, which is how a source
    # prints them whatever language the rest of the page is in.
    r"|\b(?:coppa|copa|supercoppa|supercopa|liga|laliga|serie|bundesliga"
    r"|ligue|eredivisie|primeira|dfb|dfl|efl|uefa|fifa|caf|afc|concacaf"
    r"|pokal|taca|superliga)\b"
    r"|\b(?:الدوري|الجولة|الأسبوع|الاسبوع|بطولة|البطولة|كأس|الكأس|السوبر"
    r"|النهائي|نهائي|المجموعة|مجموعة|ذهاب|[إا]ياب|ودية|تصفيات|تمهيدي"
    r"|الترتيب|الممتاز)\b",
    re.I,
)


# One club, written in two scripts.
#
# A guide reading several sources gets the same match twice, once in each
# script, and printed them both into one slot:
#
#     Union Berlin - Eintracht Frankfurt
#     + أونيون برلين - أينتراخت فرانكفورت
#
# A table of club names in both scripts would answer this, and would have
# to grow to every club in the world and be kept there. It is the wrong
# unit of work. The alphabet is the right one: Arabic sports writing
# transliterates a foreign club sound by sound, and there are 28 letters.
# Reduce both spellings to the same skeleton and the comparison holds for
# any club, including ones nobody has heard of yet.
ARABIC_LETTER = re.compile(r"[\u0600-\u06ff]")

# Arabic letter to the Latin sound it stands for. Emphatic pairs collapse
# (ص/س, ض/د, ط/ت, ظ/ز) — no European name distinguishes them — and ع, which
# has no Latin sound at all, disappears.
ARABIC_SOUND = {
    "ب": "b", "ت": "t", "ث": "t", "ج": "g", "ح": "h", "خ": "k", "د": "d",
    # ج stands for both sounds a source may write, and Latin "j" is levelled
    # to a vowel below (Juventus is يوفنتوس). Reading it as "g" is what lets
    # "Leipzig" meet "لايبزيج"; as "j" the Arabic ended in a vowel and the
    # Latin in a consonant, and they never met.
    "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "s", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "ع": "", "غ": "g", "ف": "f", "ق": "k", "ك": "k",
    "ل": "l", "م": "m", "ن": "n", "ه": "h", "ة": "h", "و": "w", "ي": "y",
    "ى": "y", "ا": "a", "أ": "a", "إ": "a", "آ": "a", "ء": "", "ؤ": "w",
    "ئ": "y", "پ": "b", "چ": "s", "ڤ": "f", "گ": "g", "ژ": "j",
}

# Latin spellings of one sound, longest first so "sch" is read before "ch".
_SOUND_DIGRAPHS = (("tsch", "s"), ("sch", "s"), ("ch", "s"), ("sh", "s"),
                   ("ph", "f"), ("th", "t"), ("ck", "k"), ("kh", "k"),
                   ("gh", "g"), ("ts", "s"), ("zz", "s"))
_SOUND_SINGLES = (("c", "k"), ("q", "k"), ("x", "ks"), ("v", "f"),
                  ("z", "s"), ("p", "b"), ("j", "y"))

# Corporate furniture that one source prints and another does not.
_CLUB_PREFIX = re.compile(
    r"^(?:rb|ac|as|ss|ssc|sc|fc|cf|afc|cd|ca|us|vfb|vfl|tsg|fsv|sv)\b", re.I)

# The definite article, stripped from the RAW text on purpose: "الهلال"
# carries it, "إلفيرسبيرج" begins with a hamza and does not. Folding first
# turns إ into ا and destroys the difference, which cost Elversberg its
# match against its own Arabic spelling.
_CLUB_ARTICLE = re.compile(r"^(?:al|el)[\s-]+|^ال(?=.)", re.I)


def club_skeleton(value: str) -> str:
    """A club name reduced to the sounds both scripts agree on."""
    value = _CLUB_ARTICLE.sub("", _CLUB_PREFIX.sub("", (value or "").strip())
                             .strip())
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    if ARABIC_LETTER.search(value):
        value = "".join(ARABIC_SOUND.get(ch, ch if ch.isascii() else "")
                        for ch in value)
    for old, new in _SOUND_DIGRAPHS:
        value = value.replace(old, new)
    for old, new in _SOUND_SINGLES:
        value = value.replace(old, new)
    value = re.sub(r"[^a-z]", "", value)
    # Arabic writes long vowels only, so every vowel becomes one symbol
    # rather than vanishing. Deleting them made "الهلال" and "الأهلي" the
    # same string, and "Mainz" the same as "Monza".
    value = re.sub(r"[aeiouwy]+", "a", value)
    return re.sub(r"(.)\1+", r"\1", value)


# Below this, a skeleton is too small to judge on resemblance alone: at
# five letters "Torino" and "Toronto" score 0.92. Short names still match,
# but only on an exact skeleton.
CLUB_SKELETON_FLOOR = 7
CLUB_SIMILARITY = 0.88


def same_club(first: str, second: str) -> bool:
    """Whether two spellings, one Arabic and one Latin, name one club.

    Cross-script only, deliberately. Within one script the guides already
    compare names strictly, and measured against real pairs a fuzzy match
    inside one script is unsafe at every threshold — "Mainz"/"Monza",
    "Al Nassr"/"Al Nasar" and "الهلال"/"الأهلي" all score at or above
    anything that still catches real duplicates. Across scripts the same
    measurement is clean: of 28 pairs of genuinely different clubs written
    one in each script, none matched.

    Losing a fixture is worse than showing one twice, so this errs at the
    strict end and misses some real pairs rather than risking a wrong one.
    """
    if bool(ARABIC_LETTER.search(first)) == bool(ARABIC_LETTER.search(second)):
        return False
    a, b = club_skeleton(first), club_skeleton(second)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < CLUB_SKELETON_FLOOR or len(b) < CLUB_SKELETON_FLOOR:
        return False
    return SequenceMatcher(None, a, b).ratio() >= CLUB_SIMILARITY


def same_fixture(first: str, second: str) -> bool:
    """Whether two "A - B" titles name one match across the two scripts.

    Both sides must match. One side agreeing is a coincidence; two sides
    agreeing, at the same kickoff minute on the same channel, is the same
    match written twice.
    """
    left = [x.strip() for x in (first or "").split(" - ")]
    right = [x.strip() for x in (second or "").split(" - ")]
    if len(left) != 2 or len(right) != 2 or not all(left) or not all(right):
        return False
    return same_club(left[0], right[0]) and same_club(left[1], right[1])


def merge_transliterations(titles):
    """Collapse one slot's titles so a match appears once, not once a script.

    Order is preserved and the first spelling of each match wins, so the
    guide keeps whichever the higher-priority source supplied rather than
    whichever sorts first.
    """
    kept: list[str] = []
    for title in titles:
        if not any(same_fixture(title, other) for other in kept):
            kept.append(title)
    return kept


def fold_name(value: str) -> str:
    """A club name with its accents and Arabic diacritics folded away.

    Sources spell the same club differently and a guide that compares
    names literally then shows one match twice:

        Elversberg - Bayer Leverkusen + FC Koln - Hoffenheim
        + Köln - Hoffenheim + Mainz 05 - Paderborn …

    "FC Koln" and "Köln" are one club; so are "Bayern München" and
    "Bayern Munchen". Folding the accent (and ß, ø, æ, đ, which decomposing
    alone does not touch) makes those spellings one string, so dedupe can
    do its job.

    On Arabic the same fold removes the harakat a source may or may not
    print and levels the alef and ya variants — أ إ آ to ا, ى to ي, ة to ه
    — which is the same class of difference in that script.
    """
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    for old, new in (("ß", "ss"), ("ø", "o"), ("æ", "ae"), ("œ", "oe"),
                     ("đ", "d"), ("ł", "l"), ("ð", "d"), ("þ", "th"),
                     ("ى", "ي"), ("ة", "ه")):
        value = value.replace(old, new).replace(old.upper(), new)
    return value


CHANNEL_NAME = re.compile(
    # Broadcaster and channel brands, in both scripts. A club never carries
    # one of these words, and a channel almost always does.
    r"\b(?:bein|be\s?in|ssc|ssc\s*sports?|shahid|starzplay|tod|tabii"
    r"|thmanyah|alkass|al\s*kass|dubai\s*sports?|abu\s*dhabi\s*sports?"
    r"|ad\s*sports?|dazn|espn|sky\s*sports?|bt\s*sports?|tnt\s*sports?"
    r"|canal\+?|movistar|amazon\s*prime|prime\s*video|dsports?"
    r"|supersport|sporttv|sport\s*tv|eleven\s*sports?|viaplay|nova\s*sports?"
    r"|arena\s*sport|digi\s*sport|match\s*tv|setanta|astro|sonyliv"
    r"|fox\s*sports?|cbs\s*sports?|nbc\s*sports?|usa\s*network|peacock"
    r"|paramount\+?|apple\s*tv|netflix|youtube|twitch|rmc\s*sport"
    r"|s\s*sport|idman|varzish|ontime|on\s*time|onsport|on\s*sport"
    # A trailing number is part of the channel, not the end of the name:
    # "Sport TV1" reached a guide as a club because the word boundary
    # after "tv" fell inside "tv1" and the whole brand stopped matching.
    r"|jrtv|roya|tivibu|trt\s*spor|smart\s*spor)\s*\d*\b"
    # MBC's own family: any MBC-something is a channel, never a club, and
    # that is the whole point — "MBC Action" reached a guide dressed as
    # Eintracht Frankfurt's opponent because only "MBC Sport" was known.
    r"|\bmbc(?:\s*\w+)?\b"
    # The generic words a channel name is built from. "sports" alone is not
    # enough (Sporting, Sport Boys), so these need a qualifier or a number.
    r"|\b(?:channel|kanal|قناة|قنوات)\b"
    # A picture-quality suffix is weak evidence on its own: "Football HD"
    # is a channel and "Ulsan HD FC" is a Korean football club. Matching HD
    # anywhere refused that club as a team name, which costs a fixture —
    # the expensive direction. So the suffix only counts behind a word that
    # is itself broadcast vocabulary, and only at the end of the name.
    r"|\b(?:sports?|football|channel|tv|movies?|news|cinema|drama|max|extra)"
    r"\s*\w*\s*(?:hd|sd|4k|uhd)\s*\d*\s*$"
    r"|\b(?:بي\s*[إا]ن|بين\s*سبورت|[أا]بو\s*ظبي\s*الرياضية"
    r"|دبي\s*الرياضية|الكأس|ثمانية|شاهد|ستارزبلاي|تود|تابي"
    r"|[أا]ون\s*تايم|[أا]ون\s*سبورت|الرياضية)\b",
    re.I,
)


def is_channel_name(value: str) -> bool:
    """Whether this text names a channel or a broadcaster rather than a club.

    Every guide in this repository reads fixtures out of prose, and every
    source prints the carrying channel on the same lines as the two teams.
    A parser that takes "the last two plausible names" therefore reaches
    for the channel the moment a page lists one more channel than usual —
    which is how "Eintracht Frankfurt - MBC Action" was published as a
    fixture, MBC Action being a television channel and not a football club.

    The name is the gate, in one place, so no guide can be strict about the
    broadcaster it belongs to and careless about everybody else's.
    """
    return bool(CHANNEL_NAME.search(value or ""))


def is_not_a_team(value: str) -> bool:
    """Whether this text names something other than a club.

    Three kinds of text turn up where a team name belongs, and each one
    reached a published guide at some point: a date ("August", "الجولة 2"
    is not a date but arrives the same way), a competition, and a channel.
    """
    return bool(DATE_WORD.search(value or "")
                or COMPETITION_NAME.search(value or "")
                or CHANNEL_NAME.search(value or ""))


def arabic_count(number: int, one: str, two: str, few: str, many: str) -> str:
    """A number with its unit, in the form Arabic actually uses.

    Arabic does not simply put a numeral in front of a noun. One and two
    are the word alone, three to ten take the plural, and eleven upward
    take the singular again:

        1  ساعة        2  ساعتين      3  3 ساعات     19  19 ساعة
        1  دقيقة       2  دقيقتين     5  5 دقائق     30  30 دقيقة

    Written the wrong way it reads as a machine talking. Written this way
    a viewer reads it without stopping, which is the whole point of a
    countdown they glance at.
    """
    if number == 1:
        return one
    if number == 2:
        return two
    if 3 <= number <= 10:
        return f"{number} {few}"
    return f"{number} {many}"


def countdown_label(minutes) -> str:
    """Arabic 'time remaining', spelled so it can only be read one way.

    This used to abbreviate: "19 س و30 د". On a television, in a line that
    also carries Latin club names, the single letters drift away from
    their numbers and a viewer cannot tell whether that says nineteen
    minutes, thirty minutes, or thirty hours and nineteen minutes. It was
    reported as exactly those three readings.

    So the units are written out. "19 ساعة و30 دقيقة" cannot be read three
    ways however the line is laid out, because each number carries its own
    word rather than a letter that can float off.
    """
    minutes = max(int(minutes), 0)
    if minutes == 0:
        # The last block of a countdown ends at kickoff, so this is the
        # width of one rounding — "0 د" would read as though the match had
        # already started.
        return "أقل من دقيقة"

    hours, mins = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    def days_word(n):
        return arabic_count(n, "يوم", "يومين", "أيام", "يوم")

    def hours_word(n):
        return arabic_count(n, "ساعة", "ساعتين", "ساعات", "ساعة")

    def mins_word(n):
        return arabic_count(n, "دقيقة", "دقيقتين", "دقائق", "دقيقة")

    if days:
        return (f"{days_word(days)} و{hours_word(hours)}" if hours
                else days_word(days))
    if hours and mins:
        return f"{hours_word(hours)} و{mins_word(mins)}"
    if hours:
        return hours_word(hours)
    return mins_word(mins)


def countdown_step(remaining: timedelta) -> timedelta:
    """How long the next countdown block should last.

    A countdown written into a static XMLTV file would go stale instantly,
    so instead the gap before a match is filled with consecutive blocks,
    each labelled with the time left at *its own* start. The player always
    shows the block covering "now", so the number stays correct without the
    file being re-downloaded.

    The one rule that matters: a block may never be longer than the time
    it is counting down. At ten-minute blocks inside the last hour, a
    viewer sitting in front of the guide two minutes before kickoff was
    being shown "بعد 12 د" — the coarsest reading at the moment it matters
    most, and wrong in the direction that makes someone miss the start.

    So the step shortens as kickoff nears, and never exceeds a third of
    what is left. The cost is rows, which are cheap; the gain is that the
    figure is never out by more than one step, and near kickoff that step
    is two minutes.
    """
    if remaining <= timedelta(minutes=15):
        step = timedelta(minutes=2)
    elif remaining <= timedelta(hours=1):
        step = timedelta(minutes=5)
    elif remaining <= timedelta(hours=3):
        step = timedelta(minutes=15)
    elif remaining <= timedelta(hours=12):
        step = timedelta(minutes=30)
    else:
        step = timedelta(hours=1)

    # Both callers already clamp the block to kickoff, so this changes
    # nothing they do — but a function that answers "two minutes" when one
    # is left is stating something untrue, and the next caller may not
    # clamp. It never proposes a block longer than what remains.
    return min(step, remaining) if remaining > timedelta(0) else step


# How long before kickoff a countdown starts.
#
# A countdown has to be cut into blocks to stay accurate in a static file,
# and that is fine for the last stretch before a match. Run over an empty
# night it turns the channel into a wall: a guide with 17 matches in it was
# publishing 640 rows, 623 of them countdown blocks, because a five-day gap
# between two matches was filled hour by hour with "بعد 4 أيام و7 ساعات".
# Nobody reads a ticker four days out — scrolling the guide, every row said
# the same thing.
#
# Past this horizon the whole wait is one row instead, naming what is
# coming. The grid already prints when that row ends, in the viewer's own
# timezone, so the guide answers "what is next, and when" the way a
# television guide does, without a clock baked into a title that would be
# wrong everywhere but one country.
COUNTDOWN_HORIZON = timedelta(hours=3)


def waiting_title(what: str) -> str:
    """The title of the single row that covers a long wait."""
    return f"{COUNTDOWN_MARK} المباراة القادمة · {what}"


def close_channel_gaps(rows, window_start, window_end, title: str):
    """Give a channel something to show at every minute of its window.

    A player renders a hole as a blank row, and a viewer reads a blank row
    as a dead channel. Two of these were live in the published guides:
    Tivibu Spor, whose upstream feed had stopped supplying anything past
    yesterday evening, and Al Jadeed, whose source publishes 03:00 to 20:59
    and leaves six hours of every night unwritten.

    Neither is our data being wrong. Both are the guide having nothing to
    say and saying it by going blank instead of out loud.

    Takes and returns rows of {"start", "stop", "title"}, sorted, with the
    holes — and any lead-in or run-out inside the window — filled by a row
    carrying `title`. Existing rows are never moved, shortened or dropped:
    the filler only occupies time nothing else claims.
    """
    kept = sorted((r for r in rows if r["stop"] > r["start"]),
                  key=lambda r: r["start"])
    out: list[dict] = []
    cursor = window_start

    for row in kept:
        if row["start"] > cursor:
            out.append({"start": cursor, "stop": row["start"], "title": title,
                        "filler": True})
        out.append(row)
        cursor = max(cursor, row["stop"])

    if cursor < window_end:
        out.append({"start": cursor, "stop": window_end, "title": title,
                    "filler": True})
    return out


def fill_wait(gap_start, gap_stop, next_kickoff_after, title_at, emit,
              nothing_title: str) -> None:
    """Fill the space between broadcasts the way a guide should read.

    One shape, shared, because two guides had grown their own copy of it
    and both had the same fault. A gap is covered by:

      * one row for the long wait, up to COUNTDOWN_HORIZON before kickoff,
      * a countdown from there to kickoff, blocks shortening as it nears,
      * one row to the end of the gap when no match is announced at all.

    The caller supplies the pieces that differ between guides:
      next_kickoff_after(moment) -> the next kickoff at or after moment
      title_at(kickoff)          -> what to call the match(es) then
      emit(start, stop, title)   -> add one programme
      nothing_title              -> what to show when nothing is coming

    Callers pass gaps that already stop at a day boundary, so a wait row
    never spans two dates in the grid.
    """
    cursor = gap_start
    while cursor < gap_stop:
        upcoming = next_kickoff_after(cursor)
        if upcoming is None:
            # Nothing announced. One row for the rest, not a row per hour
            # repeating that there is nothing.
            emit(cursor, gap_stop, nothing_title)
            return

        what = title_at(upcoming)

        # Still far out: one row for the whole wait.
        countdown_from = upcoming - COUNTDOWN_HORIZON
        if cursor < countdown_from:
            stop = min(countdown_from, gap_stop)
            if stop <= cursor:
                return
            emit(cursor, stop, waiting_title(what))
            cursor = stop
            continue

        remaining = upcoming - cursor
        stop = min(cursor + countdown_step(remaining), gap_stop, upcoming)
        if stop <= cursor:
            return
        emit(cursor, stop,
             countdown_title(what, remaining.total_seconds() // 60))
        cursor = stop


def countdown_title(what: str, minutes) -> str:
    """One countdown row, worded identically wherever it is used.

    Shahid and Shasha each built this string themselves and had drifted
    apart in their separators. Building it here means the two guides
    cannot disagree about how a wait is written.
    """
    return f"{COUNTDOWN_MARK} {what} · بعد {countdown_label(minutes)}"


def group_concurrent(events: list[dict], key="start") -> dict:
    """start-time -> [events]. Matches kicking off together must become ONE
    programme: a guide channel can only show one entry per time slot, so
    emitting them separately makes the player hide all but one."""
    slots: dict = {}
    for ev in events:
        slots.setdefault(ev[key], []).append(ev)
    return slots
