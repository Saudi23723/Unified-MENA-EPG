# 📺 Unified MENA Sports EPG

Free, automatically updated **XMLTV EPG guides** for selected sports channels and platforms in the MENA region.

Designed for **TiviMate** and other IPTV players that support XMLTV EPG sources.

---

## 📡 Available EPG Guides

### 🔴 beIN SPORTS Qatar / MENA

**Full official roster:** beIN SPORTS 1–9, MAX 1–6, XTRA 1–9, AFC 1–6, NEWS, NBA, 4K.

Sourced live from beIN's own public TV-guide API — no data is invented, and
every new channel beIN adds shows up automatically.

**The Live badge is checked, not trusted.** Every match row beIN returns
also carries the real kick-off time, so a broadcast whose own window
contains the kick-off is by definition the live airing and one that does
not is a replay. Across all 40 channels — 3,569 rows, 361 of them match
rows — beIN's live flag agreed with that test every single time: no live
airing left unflagged, no replay flagged. The check runs on **every
build**, so if beIN ever stops setting the flag the guide badges from the
kick-off instead and says so in the log.

**Nothing is silently truncated.** The endpoint hands back 100 rows and no
more unless asked, while reporting the real total. Left at its default it
had been cutting beIN SPORTS NEWS from 290 programmes to 100 and beIN
SPORTS 1 from 156 to 100 — three days of guide, live matches included,
simply absent. The guide now pages until the count is satisfied, and warns
if it ever comes back short.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/bein_sports_qatar_epg.xml

---

### 🇹🇷 beIN SPORTS Türkiye

**Channels:** beIN SPORTS 1–4, MAX 1–2, HABER.

Sourced from tvyayinakisi.com, which publishes each channel's schedule as
schema.org `BroadcastEvent` data, with the Turkish feed of
epgshare01.online filling any time that source leaves empty. Broadcasts
the source marks "Canlı" (live) carry the Live badge.

HABER is carried under two ids in the Turkish feed and each holds
programmes the other does not, so both are read and merged.

beIN SPORTS 5 is not listed: neither source publishes a schedule for it.

How far ahead each channel reaches is a limit of the sources, not of this
guide: tvyayinakisi publishes only the current day for beIN 1–4 and MAX,
a full week for HABER, and refuses a date parameter; epgshare's Turkish
feed adds three to four days. Six other Turkish TV-guide sites were
checked — four do not resolve at all, one serves an empty page, and
Digiturk answers 403.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/bein_sports_turkey_epg.xml

---

### 🇶🇦 Alkass — الكأس

**Channels:** الكأس 1-8.

Sourced from **Alkass's own TV guide** at `alkass.net/tvguide`.

It used to read beIN's guide. Audited channel by channel on the same day,
the two disagree almost completely: of the slots that even start at the
same minute, beIN's title matched Alkass's on 0 of 13 for Alkass 1, 0 of
13 for Alkass 4, 1 of 15 for Alkass 2. beIN also repeated Alkass 1's
whole schedule on Alkass 4 (71 of 87 slots identical) and Alkass 5's on
Alkass 7 (76 of 78). Alkass is the broadcaster, so the guide reads Alkass.

Two details worth knowing. The page renders the same guide twice, and the
collapsible list near the top is broken — it repeats whole channels and
duplicates rows — so only the grid underneath is read, with each channel
matched to its own logo in the column beside it rather than to a
position. And the page carries **one day, in English only**; that is what
Alkass publishes, and it is the cost of reading the source that is right.

No Live badge: neither the page nor beIN marks which Alkass broadcasts
are live, so nothing here claims to.

Alkass 9, 10, 11 and the two SHOOF channels are not listed — no reachable
source publishes a schedule for them.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/alkass_epg.xml

---

### 🎬 STARZPLAY Sports

**Channels:** 20, picked by STARZPLAY's own classification rather than a
fixed list — among them AD Sports 1 and 2, AD Sports Premium 2, AD Sports
Extra, Yas TV, AD Fight and the STARZPLAY-branded sport channels.

Sourced from STARZPLAY's own public web-EPG API, called once in English
and once in Arabic: titles and channel names are shown in English with the
Arabic alongside.

No Live badge. The API's per-event `live` flag is computed at request time
— only ever one event per channel — so it would be stale within the hour,
and marking every event instead would distinguish nothing.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/starzplay_epg.xml

---

### 🇯🇴 Jordan — Roya TV / Roya News (general programming)

No Live badge on any Roya channel. Roya publishes no live marker of any
kind, so the only badge possible would be "this was on air when the
workflow ran", read off the clock — which had put Live on a cooking show
and a comedy rerun, and went stale minutes later either way. The Live
badge belongs on الأردن الرياضية, which has real fixtures to put it on.

Full daily schedule (news, drama, talk shows, everything Roya airs),
sourced from Roya's own official public schedule API. Complements the
existing **Jordan Sports** guide below.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/roya_jordan_epg.xml

---

### 📦 Unified MENA EPG (all sources merged)

Every guide above, plus every guide below, merged into one file:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/unified_mena_epg.xml

---

### 🇪🇬 ON Sport

**Channels:** ON Sport 1, ON Sport 2, ON Sport MAX, ON Sport PLUS

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/onsport_epg.xml

---

### 🇯🇴 Jordan Sports — الأردن الرياضية

Fixtures are read from the **schema.org microdata** livefootballtv
publishes for each match — its name, its exact start and its duration —
rather than from the visible text. That matters for more than tidiness:
the time shown in the visible row is the site's own display zone, two
hours off the microdata, so reading it as Amman wall-clock had been
putting every match here an hour early. The microdata states UTC, so
there is no timezone to guess at.

The Live badge goes on every real fixture and never on a studio show.
A quiet week — livefootballtv saying "at this time there is no football
match being televised" and listing past matches below — is reported as
such rather than as a failure.

EPG for **Jordan Sports / الأردن الرياضية**.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/jordan_sports_epg.xml

---

### 🟢 Shahid Sports

Sports-event EPG for supported **Shahid / MBC Sports** coverage.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/shahid_sports_epg.xml

---

### 🇹🇷 tabii Spor

**Channel:** tabii Spor.

Sourced from **TRT's own broadcast-schedule page**, which carries a full
week of EPG, with tvyayinakisi.com filling the current day where TRT
gives a generic block instead of the fixture.

It used to claim ten channels. That was an artefact: the old generator
read no schedule at all — it scraped mentions of matches out of
trtspor.com.tr *news* pages and split them across ten invented channels,
leaving 83 programmes of which 6 were still in the future and three
channels empty. There is no source for "tabii Spor 2" and up: TRT names
exactly one channel, and tvyayinakisi 404s on every numbered slug.

No Live badge: neither source marks which broadcasts are live.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/tabii_spor_1_10_epg.xml

---

### 🟢 Thmanyah

Sports EPG for supported **Thmanyah / ثمانية** channels and events.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/thmanyah_epg.xml

---

### 🔵 Alwan Sports

Sports EPG for supported **Alwan Sports / ألوان الرياضية** channels.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/alwan_sports_epg.xml

---

### 📺 Shasha

Sports programming guide for **Shasha / شاشا**.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/shasha_epg.xml

---

### 🟠 Fajer Sports

**Channels:** Fajer Sport 1–5.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/fajer_sports_epg.xml

---

## 📦 Combined EPG

A combined XMLTV file is also available:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/combined_epg_final.xml

---

---

## 🛡️ How the guides are protected

The links above are meant to keep working without anyone watching them.
Four things stand between a bad run and a broken guide. None of them
changes what a guide contains — they only decide whether a run is allowed
to replace one.

**1. A run that produced nothing cannot overwrite one that did.**
If the sources are unreachable and a build ends with zero programmes, the
previous file stays exactly as it is and the run says so.

**2. A run that collapsed cannot overwrite either.**
A build that comes back with under 35% of the channels or programmes the
file already holds is refused. Sources half-answer far more often than a
guide genuinely loses two thirds of itself overnight. Ordinary movement —
a guide breathing between 400 and 1,200 entries as fixtures come and go —
publishes untouched, and a guide small enough that the ratio is
meaningless (under 40 programmes) is never judged by it. Where a large
drop is real and intended, the guide opts out explicitly.

**3. Every file is validated before it is written.**
Atomically, to a temporary file that is re-parsed and checked before it
replaces anything: a programme must end after it starts, and no two
programmes may overlap on one channel. Overlap is judged after sorting by
time rather than in the order the file happens to store them — XMLTV
allows any order, several guides here do write out of order, and judging
in file order reported 82 valid channels as broken.

**4. A twice-daily health check reads what is published.**
`health_check.py` never writes anything. It fails the run when a source
file named in `merge_epg.py` is missing or unreadable, a programme is
malformed or overlapping, a channel has no name or points at a logo this
repository does not have, two source files claim the same channel id (the
merge would keep one and drop the other), a channel present in a source
is missing from the merged link, or **a guide has less than half a day
left in the future**. That last one is what tabii's guide had looked like
for weeks — 83 programmes, one of them still ahead — with nothing saying
so.

It also reports, without failing: channels carrying no programmes, and
guides with under two days ahead.

Run it yourself at any time:

```bash
python health_check.py                   # everything, including freshness
python health_check.py --structure-only  # skip the "has it aged out" checks
```

Exit code 1 means something needs attention.

**Every push is checked before it can reach a guide.** CI compiles every
script, fails on any name that would not exist at runtime, runs
`test_epg_lib.py` — twenty checks holding the guards above in place — and
runs the health check in `--structure-only` mode. Freshness is left to
the scheduled run on purpose: a pull request should not go red because a
data file aged overnight.

### If something does go wrong

Every guide is a file in git history, so a bad update is never permanent:

```bash
git log --oneline -- unified_mena_epg.xml   # find the last good version
git checkout <commit> -- unified_mena_epg.xml
git commit -m "Roll back the merged guide" && git push
```

The link keeps its URL, so nothing on the player side needs changing.

---

## 🟢 Live indicator

Any match or event that is airing **right now** gets its title suffixed
with **`• Live 🟢`** automatically, on every sports guide in this repo.
This is computed fresh on every regeneration (every 15 minutes for the
sports guides), so as soon as TiviMate refreshes its EPG the tag appears
and disappears exactly when the match starts/ends — no manual action
needed.

---

## 📲 How to Add to TiviMate

1. Open **TiviMate**
2. Go to **Settings**
3. Select **EPG**
4. Select **EPG Sources**
5. Choose **Add source**
6. Enter one of the EPG URLs above
7. Select **Update EPG**

If a channel is not matched automatically, manually assign the corresponding EPG channel to it.

---

## 🌍 Time Zones

Programme times are stored using timezone-aware XMLTV timestamps.

TiviMate and other compatible applications can display the programme at the correct **local device time**.

For example, the same match may appear at:

- 11:00 AM in Las Vegas
- 10:00 PM in Abu Dhabi

It is still the **same event at the same moment**.

If you travel or change the device timezone, you should not need a different EPG file.

---

## 🔄 Automatic Updates

The EPG files are generated automatically using **GitHub Actions**.

The workflows periodically:

1. Check the available schedule information
2. Generate a new XMLTV guide
3. Validate the XML
4. Replace the previous EPG file
5. Publish the updated guide to this repository

You normally only need to add the EPG URL **once** to your IPTV application.

There is no need to manually download a new XML file after every update.

---

## 🧹 Old Events

Generated EPG files are rebuilt during updates.

Old events are therefore not intended to accumulate permanently in the XMLTV files.

---

## ⚠️ Accuracy

The project attempts to use reliable schedule information and preserve the actual event times.

However:

- Broadcasters can change schedules
- Matches can be postponed or rescheduled
- External schedule websites can change
- Channel assignments can change at short notice
- Some channels may not publish complete schedules in advance

An empty or partially populated guide does **not necessarily mean that the workflow is broken**. It can mean that reliable timed programme information was not available during that update.

---

## 📄 XMLTV

All EPG files use the standard **XMLTV** format.

They can be used with applications that support external XMLTV EPG sources.

---

## ⚖️ Disclaimer

This repository provides **programme-guide metadata only**.

It does **not** provide:

- IPTV streams
- TV subscriptions
- User accounts
- Video content
- Rebroadcasts

Channel names and trademarks belong to their respective owners.

---

⭐ **Unified MENA Sports EPG**
