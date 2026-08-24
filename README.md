# 📺 Unified MENA Sports EPG

Free, automatically updated **XMLTV EPG guides** for selected sports channels and platforms in the MENA region.

Designed for **TiviMate** and other IPTV players that support XMLTV EPG sources.

---

## 📡 Available EPG Guides

### 🔴 beIN SPORTS Qatar / MENA

**Full official roster:** beIN SPORTS 1–9, MAX 1–6, XTRA 1–9, AFC 1–6, NEWS, NBA, 4K.

Sourced live from beIN's own public TV-guide API — no data is invented, and
every new channel beIN adds shows up automatically.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/bein_sports_qatar_epg.xml

---

### 🇹🇷 beIN SPORTS Türkiye

**Channels:** beIN SPORTS 1–5, MAX 1–2, HABER.

Sourced live from Digiturk's own public TV-guide feed (beIN Sports
Türkiye is carried on Digiturk).

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/bein_sports_turkey_epg.xml

---

### 🟣 STARZPLAY

All categories — sport, movies, series and more — sourced from STARZPLAY's
own public web-EPG API. New channels appear automatically; no channel list
is hardcoded.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/starzplay_epg.xml

---

### 🟡 AD Sports (Abu Dhabi Sports)

**AD Sports 1 HD** is sourced from OSN's official public EPG API (real,
verified data). **AD Sports 2 / Premium / Extra** are best-effort,
auto-discovered from LiveFootballTV.info's own channel index (same
technique already used for ON Sport/Jordan Sports below) — if a channel
isn't currently listed there it simply has no programmes that run, it
never breaks the rest of the file.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/adsports_epg.xml

---

### 🇯🇴 Jordan — Roya TV / Roya News (general programming)

Full daily schedule (news, drama, talk shows, everything Roya airs),
sourced from Roya's own official public schedule API. Complements the
existing **Jordan Sports** guide below.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/roya_jordan_epg.xml

---

### 🇸🇾 🇱🇧 Syria & Lebanon channels

Sourced from Shahid's (MBC) official public API, which republishes a
handful of free-to-air regional channels — currently **السورية /
Al-Souriya TV** (Syria) and **MTV Lebanon**. New Syrian/Lebanese channels
Shahid adds are picked up automatically.

> No public schedule API could be found for LBCI, OTV, Tele Liban, Al
> Jadeed, or Syria TV (Fadaat) — rather than invent data for them, they
> are simply not included. If you know of a public source for any of
> these, please open an issue.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/syria_lebanon_epg.xml

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

### 🇯🇴 Jordan Sports

EPG for **Jordan Sports / الأردن الرياضية**.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/jordan_sports_epg.xml

---

### 🟢 Shahid Sports

Sports-event EPG for supported **Shahid / MBC Sports** coverage.

EPG URL:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/shahid_sports_epg.xml

---

### 🇹🇷 Tabii Spor

**Channels:** Tabii Spor 1–10

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

## 📦 Combined EPG

A combined XMLTV file is also available:

https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/combined_epg_final.xml

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
