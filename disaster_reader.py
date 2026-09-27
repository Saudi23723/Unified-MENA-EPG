#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What the world's disaster monitors are reporting right now.

"قناة الكوارث في العالم … عواصف زلازل فيضانات و ما شابه … مخصصه لهيك
اشياء مش اخبار و رياضة" — so this reads the MONITORS, not newsrooms. A
newsroom decides what is a story; a monitor records that the ground
moved, that a storm formed, that a river rose, whether or not anybody
wrote about it. That is what makes the channel "only this" rather than a
news channel with a filter on it.

TWO SOURCES, asked first and read as they answered (probe_disasters):

    USGS   earthquake.usgs.gov — every M4.5+ quake of the last day,
           with its magnitude, depth, place, PAGER alert and tsunami
           flag. The earthquakes come from here and nowhere else.
    GDACS  gdacs.org — the UN/EU alert system. Tropical cyclones,
           floods, volcanoes, wildfires and droughts, each with an
           alert level (Green/Orange/Red), its countries and whether it
           is still current. Its earthquakes are the same NEIC events
           USGS publishes, so they are not read twice.

Nothing here is translated from a source's prose. What is written in
Arabic is built from the numbers — a kind, a magnitude, a wind speed, a
country — and a place the table below does not know keeps the name the
monitor gave it.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from epg_lib import arabic_count, fetch, log, norm, warn

UTC = timezone.utc

USGS_DAY = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
            "4.5_day.geojson")
USGS_SIGNIFICANT = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/"
                    "summary/significant_week.geojson")
GDACS = ("https://www.gdacs.org/gdacsapi/api/events/geteventlist/"
         "EVENTS4APP")

# WHICH QUAKES. The day's M4.5+ feed holds twenty to forty events, most of
# them offshore and felt by nobody. Five is where a quake is news
# anywhere; nearer home the line is lower, because an M4.6 under Amman
# or Izmir is felt by the people watching this channel.
WORLD_MAGNITUDE = 5.0
NEAR_MAGNITUDE = 4.5
# The Middle East and Turkey, as a box: the Levant, the Gulf, Iraq, Iran,
# Egypt and Anatolia.
NEAR = (10.0, 43.0, 24.0, 63.0)          # south, north, west, east
QUAKE_HOURS = 48

# Anything else GDACS still calls current, if it was last seen inside
# this many days. A flood GDACS stopped updating a fortnight ago is over
# whatever its flag says.
GDACS_DAYS = 7

# FIRES AND DROUGHTS ONLY WHEN THEY ARE BAD. GDACS files every wildfire
# a satellite sees: the first live pass read 63 of them, all Green, and
# they filled four of the five pages and pushed eleven of twelve
# earthquakes off the board. A green fire in the Mozambique bush is a
# fire, not a disaster; an orange or red one is. A drought is the same.
ONLY_WHEN_ALERTED = {"WF", "DR"}

KIND_AR = {
    "EQ": "زلزال",
    "TC": "إعصار",
    "FL": "فيضانات",
    "VO": "بركان",
    "WF": "حرائق",
    "DR": "جفاف",
    "TS": "تسونامي",
}

ALERT_AR = {"Red": "أحمر", "Orange": "برتقالي", "Green": "أخضر",
            "Yellow": "أصفر"}
# How the page is ordered: the worst first.
ALERT_RANK = {"Red": 3, "Orange": 2, "Yellow": 2, "Green": 1}

# Countries, in the names the monitors use, and the Arabic this channel
# prints. Only names: a place missing here keeps the monitor's own words.
COUNTRY_AR = {
    "Afghanistan": "أفغانستان", "Albania": "ألبانيا", "Algeria": "الجزائر",
    "Angola": "أنغولا", "Cape Verde": "الرأس الأخضر",
    "Cabo Verde": "الرأس الأخضر", "Botswana": "بوتسوانا",
    "Namibia": "ناميبيا", "Congo": "الكونغو",
    "Democratic Republic of the Congo": "الكونغو الديمقراطية",
    "Central African Republic": "أفريقيا الوسطى", "Benin": "بنين",
    "Burkina Faso": "بوركينا فاسو", "Guinea": "غينيا",
    "Sierra Leone": "سيراليون", "Liberia": "ليبيريا", "Togo": "توغو",
    "Rwanda": "رواندا", "Burundi": "بوروندي", "Lesotho": "ليسوتو",
    "Eswatini": "إسواتيني", "Mauritius": "موريشيوس", "Comoros": "جزر القمر",
    "Reunion": "ريونيون", "Micronesia": "ميكرونيزيا",
    "Marshall Islands": "جزر مارشال", "Kiribati": "كيريباتي",
    "Tuvalu": "توفالو", "French Polynesia": "بولينيزيا الفرنسية",
    "Paraguay": "باراغواي", "Uruguay": "الأوروغواي", "Guyana": "غيانا",
    "Suriname": "سورينام", "Trinidad and Tobago": "ترينيداد وتوباغو",
    "Barbados": "باربادوس", "Bermuda": "برمودا", "Poland": "بولندا",
    "Hungary": "المجر", "Slovakia": "سلوفاكيا", "Slovenia": "سلوفينيا",
    "Czech Republic": "التشيك", "Czechia": "التشيك",
    "Switzerland": "سويسرا", "Belgium": "بلجيكا",
    "Netherlands": "هولندا", "Ireland": "أيرلندا", "Norway": "النرويج",
    "Sweden": "السويد", "Finland": "فنلندا", "Denmark": "الدنمارك",
    "Moldova": "مولدوفا", "Belarus": "بيلاروسيا",
    "North Macedonia": "مقدونيا الشمالية", "Kosovo": "كوسوفو",
    "Argentina": "الأرجنتين", "Armenia": "أرمينيا", "Australia": "أستراليا",
    "Austria": "النمسا", "Azerbaijan": "أذربيجان", "Bahamas": "الباهاماس",
    "Bahrain": "البحرين", "Bangladesh": "بنغلاديش", "Belize": "بليز",
    "Bhutan": "بوتان", "Bolivia": "بوليفيا", "Bosnia and Herzegovina":
    "البوسنة والهرسك", "Brazil": "البرازيل", "Bulgaria": "بلغاريا",
    "Burma": "ميانمار", "Myanmar": "ميانمار", "Cambodia": "كمبوديا",
    "Cameroon": "الكاميرون", "Canada": "كندا", "Chad": "تشاد",
    "Chile": "تشيلي", "China": "الصين", "Colombia": "كولومبيا",
    "Costa Rica": "كوستاريكا", "Croatia": "كرواتيا", "Cuba": "كوبا",
    "Cyprus": "قبرص", "Djibouti": "جيبوتي", "Dominican Republic":
    "الدومينيكان", "Ecuador": "الإكوادور", "Egypt": "مصر",
    "El Salvador": "السلفادور", "Eritrea": "إريتريا", "Ethiopia": "إثيوبيا",
    "Fiji": "فيجي", "France": "فرنسا", "Georgia": "جورجيا",
    "Germany": "ألمانيا", "Ghana": "غانا", "Greece": "اليونان",
    "Guatemala": "غواتيمالا", "Haiti": "هايتي", "Honduras": "هندوراس",
    "Hong Kong": "هونغ كونغ", "Iceland": "آيسلندا", "India": "الهند",
    "Indonesia": "إندونيسيا", "Iran": "إيران", "Iraq": "العراق",
    "Israel": "إسرائيل", "Italy": "إيطاليا", "Jamaica": "جامايكا",
    "Japan": "اليابان", "Jordan": "الأردن", "Kazakhstan": "كازاخستان",
    "Kenya": "كينيا", "Kuwait": "الكويت", "Kyrgyzstan": "قيرغيزستان",
    "Laos": "لاوس", "Lebanon": "لبنان", "Libya": "ليبيا",
    "Madagascar": "مدغشقر", "Malawi": "ملاوي", "Malaysia": "ماليزيا",
    "Mali": "مالي", "Mauritania": "موريتانيا", "Mexico": "المكسيك",
    "Mongolia": "منغوليا", "Montenegro": "الجبل الأسود",
    "Morocco": "المغرب", "Mozambique": "موزمبيق", "Nepal": "نيبال",
    "New Caledonia": "كاليدونيا الجديدة", "New Zealand": "نيوزيلندا",
    "Nicaragua": "نيكاراغوا", "Niger": "النيجر", "Nigeria": "نيجيريا",
    "North Korea": "كوريا الشمالية", "Oman": "عُمان",
    "Pakistan": "باكستان", "Palestine": "فلسطين", "Panama": "بنما",
    "Papua New Guinea": "بابوا غينيا الجديدة", "Peru": "بيرو",
    "Philippines": "الفلبين", "Portugal": "البرتغال",
    "Puerto Rico": "بورتوريكو", "Qatar": "قطر", "Romania": "رومانيا",
    "Russia": "روسيا", "Russian Federation": "روسيا",
    "Samoa": "ساموا", "Saudi Arabia": "السعودية", "Senegal": "السنغال",
    "Serbia": "صربيا", "Solomon Islands": "جزر سليمان",
    "Somalia": "الصومال", "South Africa": "جنوب أفريقيا",
    "South Korea": "كوريا الجنوبية", "Korea": "كوريا",
    "South Sudan": "جنوب السودان", "Spain": "إسبانيا",
    "Sri Lanka": "سريلانكا", "Sudan": "السودان", "Syria": "سوريا",
    "Taiwan": "تايوان", "Tajikistan": "طاجيكستان", "Tanzania": "تنزانيا",
    "Thailand": "تايلاند", "Timor-Leste": "تيمور الشرقية",
    "East Timor": "تيمور الشرقية", "Tonga": "تونغا", "Tunisia": "تونس",
    "Turkey": "تركيا", "Türkiye": "تركيا", "Turkiye": "تركيا",
    "Turkmenistan": "تركمانستان", "Uganda": "أوغندا", "Ukraine": "أوكرانيا",
    "United Arab Emirates": "الإمارات", "United Kingdom": "بريطانيا",
    "United States": "الولايات المتحدة", "USA": "الولايات المتحدة",
    "Uzbekistan": "أوزبكستان", "Vanuatu": "فانواتو",
    "Venezuela": "فنزويلا", "Vietnam": "فيتنام", "Viet Nam": "فيتنام",
    "Yemen": "اليمن", "Zambia": "زامبيا", "Zimbabwe": "زيمبابوي",
    # The places USGS names instead of a country.
    "Alaska": "ألاسكا", "Hawaii": "هاواي", "California": "كاليفورنيا",
    "CA": "كاليفورنيا", "Nevada": "نيفادا", "Oregon": "أوريغون",
    "Washington": "واشنطن", "Guam": "غوام",
    "Northern Mariana Islands": "جزر ماريانا الشمالية",
    "Kermadec Islands": "جزر كيرماديك", "Fiji Islands": "فيجي",
    "Aleutian Islands": "جزر ألوشيان", "Kuril Islands": "جزر الكوريل",
    "South Sandwich Islands": "جزر ساندويتش الجنوبية",
    "Mid-Atlantic Ridge": "حيد وسط الأطلسي", "Crete": "كريت",
    "Sumatra": "سومطرة", "Java": "جاوة", "Molucca Sea": "بحر مولوكا",
    "Banda Sea": "بحر باندا", "Kamchatka": "كامتشاتكا",
}


def country_ar(name: str) -> str:
    """The Arabic for a place, or the monitor's own name for it."""
    name = norm(name)
    name = re.sub(r"\s+region$", "", name, flags=re.I)
    name = re.sub(r"^(?:off the coast of|near the coast of|off coast of"
                  r"|south of the|north of the|east of the|west of the"
                  r"|southern|northern|eastern|western|central)\s+", "",
                  name, flags=re.I)
    for key, value in COUNTRY_AR.items():
        if key.casefold() == name.casefold():
            return value
    # "Off Coast Of Central Chile", "Near Coast Of Peru" — a known
    # country inside a longer name is still that country.
    for key, value in COUNTRY_AR.items():
        if len(key) > 3 and re.search(rf"\b{re.escape(key)}\b", name, re.I):
            return value
    return name


def place_of_quake(place: str) -> str:
    """"159 km ESE of Gizo, Solomon Islands" → the part after the comma."""
    place = norm(place)
    return place.rsplit(",", 1)[-1].strip() if "," in place else place


def near_home(lat: float, lon: float) -> bool:
    south, north, west, east = NEAR
    return south <= lat <= north and west <= lon <= east


def magnitude_rank(mag: float, alert: str | None, tsunami: bool) -> int:
    """How bad a quake is, on the same scale as a GDACS alert."""
    rank = ALERT_RANK.get((alert or "").capitalize(), 0)
    if mag >= 7.0 or tsunami:
        rank = max(rank, 3)
    elif mag >= 6.0:
        rank = max(rank, 2)
    return max(rank, 1)


def quakes_from(features: list[dict], now: datetime) -> list[dict]:
    """The USGS features worth a row, as events."""
    out: list[dict] = []
    for feature in features:
        props = feature.get("properties") or {}
        if (props.get("type") or "earthquake") != "earthquake":
            continue
        mag = props.get("mag")
        millis = props.get("time")
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if mag is None or millis is None or len(coords) < 2:
            continue
        when = datetime.fromtimestamp(millis / 1000, UTC)
        if not (now - timedelta(hours=QUAKE_HOURS) <= when <= now
                + timedelta(minutes=5)):
            continue
        lon, lat = float(coords[0]), float(coords[1])
        depth = float(coords[2]) if len(coords) > 2 and coords[2] else None
        mag = float(mag)
        if mag < WORLD_MAGNITUDE and not (mag >= NEAR_MAGNITUDE
                                          and near_home(lat, lon)):
            continue
        tsunami = bool(props.get("tsunami"))
        alert = props.get("alert")
        place = norm(props.get("place") or "")
        out.append({
            "id": f"usgs:{feature.get('id')}",
            "kind": "EQ",
            "start": when,
            "country": country_ar(place_of_quake(place)),
            "place": place,
            "magnitude": mag,
            "depth": depth,
            "tsunami": tsunami,
            "alert": (alert or "").capitalize() or None,
            "rank": magnitude_rank(mag, alert, tsunami),
            "outlet": "USGS",
            "url": props.get("url") or "",
        })
    return out


def fold_swarms(quakes: list[dict]) -> list[dict]:
    """One row per place for the small quakes, beside the strongest there.

    The first live pass had an M6.6 off New Caledonia and nine M5.0–5.2
    after it, and the nine took a page between them — ten rows saying
    one thing. So a quake that is not bad on its own (rank 1) is folded
    into the strongest quake in the same place, which says how many
    more there were. A quake that IS bad keeps its own row whatever is
    around it: two M6s in one country are two events.
    """
    by_place: dict[str, list[dict]] = {}
    for quake in quakes:
        by_place.setdefault(quake["country"], []).append(quake)

    out: list[dict] = []
    for group in by_place.values():
        group.sort(key=lambda one: one["magnitude"], reverse=True)
        head = dict(group[0])
        folded = [one for one in group[1:] if one["rank"] < 2]
        head["more"] = len(folded)
        if folded:
            head["start"] = max([head["start"]] + [one["start"]
                                                   for one in folded])
            head["first"] = group[0]["start"]
        out.append(head)
        out += [one for one in group[1:] if one["rank"] >= 2]
    return out


def gdacs_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")).replace(
            tzinfo=UTC)
    except ValueError:
        return None


A_WIND = re.compile(r"(\d+(?:\.\d+)?)\s*km/h", re.I)


def storm_word(severity_text: str) -> str:
    """Hurricane, storm or depression — the three things GDACS calls a TC."""
    text = severity_text.casefold()
    if "hurricane" in text or "typhoon" in text or "cyclone" in text:
        return "إعصار"
    if "storm" in text:
        return "عاصفة استوائية"
    if "depression" in text:
        return "منخفض استوائي"
    return "إعصار"


def gdacs_from(features: list[dict], now: datetime) -> list[dict]:
    """GDACS events other than earthquakes, still current, as events."""
    out: list[dict] = []
    for feature in features:
        props = feature.get("properties") or {}
        kind = props.get("eventtype")
        if kind not in KIND_AR or kind == "EQ":
            continue
        if str(props.get("iscurrent")).lower() != "true":
            continue
        began = gdacs_time(props.get("fromdate"))
        last = gdacs_time(props.get("todate")) or began
        touched = gdacs_time(props.get("datemodified")) or last
        if began is None or touched is None:
            continue
        if touched < now - timedelta(days=GDACS_DAYS):
            continue

        countries = [norm(one.get("countryname") or "")
                     for one in props.get("affectedcountries") or []]
        countries = [one for one in countries if one]
        if not countries and props.get("country"):
            countries = [norm(part) for part in
                         str(props["country"]).split(",") if norm(part)]
        places = []
        for one in countries:
            arabic = country_ar(one)
            if arabic not in places:
                places.append(arabic)

        severity = (props.get("severitydata") or {})
        severity_text = norm(severity.get("severitytext") or "")
        alert = (props.get("alertlevel") or "Green").capitalize()
        if kind in ONLY_WHEN_ALERTED and ALERT_RANK.get(alert, 1) < 2:
            continue
        name = norm(props.get("eventname") or "")
        name = re.sub(r"-\d{2}$", "", name)          # "NOLO-26" → "NOLO"

        event = {
            "id": f"gdacs:{kind}:{props.get('eventid')}",
            "kind": kind,
            "start": began,
            "last": last,
            "touched": touched,
            "country": "، ".join(places[:2]) or "",
            "name": name,
            "severity_text": severity_text,
            "alert": alert,
            "rank": ALERT_RANK.get(alert, 1),
            "outlet": "GDACS",
            "url": ((props.get("url") or {}).get("report") or ""),
        }
        if kind == "TC":
            wind = A_WIND.search(severity_text)
            event["wind"] = round(float(wind.group(1))) if wind else None
            event["storm_word"] = storm_word(severity_text)
        out.append(event)
    return out


def headline(event: dict) -> str:
    """The line a row leads with, built from the monitor's numbers."""
    kind = event["kind"]
    where = event.get("country") or ""
    if kind == "EQ":
        what = f"زلزال بقوة {event['magnitude']:.1f}"
        if event.get("tsunami"):
            what += " · تحذير تسونامي"
        if event.get("more"):
            what += " · و" + arabic_count(event["more"], "هزة أخرى",
                                          "هزتان أخريان", "هزات أخرى",
                                          "هزة أخرى")
    elif kind == "TC":
        # The name in guillemets. Bare, a Latin name beside Arabic lost
        # the space before it on the board — "إعصارMAWAR" — with every
        # bidi mark tried; the quotes hold it apart.
        what = event.get("storm_word") or KIND_AR["TC"]
        if event.get("name"):
            what += f" «{event['name']}»"
    elif kind == "VO":
        what = (f"ثوران بركان «{event['name']}»"
                if event.get("name") else "نشاط بركاني")
    elif kind == "WF":
        what = "حرائق غابات"
    else:
        what = KIND_AR[kind]
    return f"{what} — {where}" if where else what


def summary(event: dict, viewer, place: bool = True) -> str:
    """The line beneath the headline: the numbers that explain it.

    The monitor's English place ("35 km SW of Malatya, Turkey") is left
    off the BOARD: at the end of an Arabic line its number is pulled to
    the far side and it reads "km SW of Malatya, Turkey 35". The guide,
    which a player lays out as plain text, keeps it.
    """
    parts: list[str] = []
    kind = event["kind"]
    if kind == "EQ":
        if event.get("depth") is not None:
            parts.append(f"على عمق {event['depth']:.0f} كم")
        at = (event.get("first") or event["start"]).astimezone(viewer)
        parts.append(f"{at:%d.%m} الساعة {at:%H:%M}")
        if place and event.get("place"):
            parts.append(event["place"])
    else:
        if kind == "TC" and event.get("wind"):
            parts.append(f"رياح حتى {event['wind']} كم/س")
        since = event["start"].astimezone(viewer)
        parts.append(f"منذ {since:%d.%m}")
        if event.get("alert"):
            parts.append(f"تنبيه {ALERT_AR.get(event['alert'], '')}".strip())
    return " · ".join(part for part in parts if part)


def events(session, now: datetime) -> list[dict]:
    """Everything current, the worst first and the newest first within it."""
    found: list[dict] = []

    seen_quakes: set[str] = set()
    quakes: list[dict] = []
    for url in (USGS_SIGNIFICANT, USGS_DAY):
        try:
            data = fetch(session, url).json()
        except Exception as exc:                              # noqa: BLE001
            warn(f"USGS is unreachable ({exc}) — no earthquakes this pass")
            continue
        for quake in quakes_from(data.get("features") or [], now):
            if quake["id"] not in seen_quakes:
                seen_quakes.add(quake["id"])
                quakes.append(quake)
    found += fold_swarms(quakes)

    try:
        data = fetch(session, GDACS).json()
        others = gdacs_from(data.get("features") or [], now)
        found += others
    except Exception as exc:                                  # noqa: BLE001
        warn(f"GDACS is unreachable ({exc}) — no storms, floods or "
             f"volcanoes this pass")

    by_kind: dict[str, int] = {}
    for one in found:
        by_kind[one["kind"]] = by_kind.get(one["kind"], 0) + 1
    log("  disasters: " + (", ".join(f"{KIND_AR[k]} {n}"
                                     for k, n in sorted(by_kind.items()))
                           or "none"))
    return in_order(found)


def in_order(found: list[dict]) -> list[dict]:
    """The worst first; within an alert level, the newest first.

    NEWEST BY WHEN IT BEGAN, not by when the monitor last touched it.
    GDACS re-stamps every current event on every update, so ordering by
    that put a three-week-old flood above a quake from this morning.
    """
    return sorted(found, key=lambda one: (one["rank"], one["start"]),
                  reverse=True)
