"""Does a free forecast answer for a CIRCUIT, and with what?

WHY THIS EXISTS. The F1 channel already shows weather, but only from
OpenF1's trackside sensors, and those only exist while a session is
running. On the five days a week when nothing is on the circuit the
board has no weather at all — the number it would show is whatever the
last session left behind, which is not a reading, it is a memory.

So the question this probe answers is narrow and worth answering before
a line of the channel is changed:

  1. Does Jolpica's calendar carry the CIRCUIT'S COORDINATES? If it
     does not, there is nothing to ask a forecast about and the idea
     stops here.
  2. Does Open-Meteo — already this repository's weather source, free
     and keyless — answer at those coordinates?
  3. What does it actually carry: air temperature, humidity, wind, the
     chance of rain, and is there anything honest to say about the
     SURFACE, which is the number an F1 viewer looks for first?

It prints what it gets. It changes nothing.
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from epg_lib import fetch, new_session                       # noqa: E402

JOLPICA = "https://api.jolpi.ca/ergast/f1"
METEO = "https://api.open-meteo.com/v1/forecast"


def main() -> int:
    session = new_session()
    now = datetime.now(timezone.utc)
    print(f"probing at {now:%Y-%m-%d %H:%M} UTC\n")

    # ---- 1. does the calendar carry coordinates ----------------------
    data = fetch(session, f"{JOLPICA}/current.json").json()
    races = (data.get("MRData", {}).get("RaceTable", {}).get("Races") or [])
    print(f"calendar: {len(races)} rounds")
    placed = 0
    rows = []
    for race in races:
        place = (race.get("Circuit") or {}).get("Location") or {}
        lat, lon = place.get("lat"), place.get("long")
        if lat and lon:
            placed += 1
        rows.append((race.get("round"), race.get("raceName"),
                     (race.get("Circuit") or {}).get("circuitName"),
                     lat, lon, place.get("locality"), place.get("country")))
    print(f"rounds carrying lat/long: {placed} of {len(races)}")
    for row in rows[:5]:
        print(f"  R{row[0]:>2}  {row[1][:30]:<30} {str(row[3]):>10},"
              f"{str(row[4]):>10}  {row[5]}, {row[6]}")
    if not placed:
        print("\nNO COORDINATES — nothing to ask a forecast about. Stop.")
        return 1
    print()

    # ---- 2. does the forecast answer at a circuit --------------------
    # EVERY ROUND AT ONCE, the way weather_epg.py asks for every city —
    # one request, so wiring this into the channel costs one call a
    # pass no matter how long the season is. The channel will only ever
    # need the one circuit it is on, but if the batch form answers then
    # the single form certainly does.
    lats = ",".join(str(r[3]) for r in rows if r[3])
    lons = ",".join(str(r[4]) for r in rows if r[4])
    params = {
        "latitude": lats, "longitude": lons,
        "current": ("temperature_2m,apparent_temperature,"
                    "relative_humidity_2m,weather_code,wind_speed_10m,"
                    "precipitation,is_day"),
        "hourly": "precipitation_probability,soil_temperature_0cm",
        "forecast_days": 2, "timezone": "auto",
    }
    answer = fetch(session, METEO, params=params).json()
    if isinstance(answer, dict):
        answer = [answer]
    print(f"Open-Meteo answered for {len(answer)} of {placed} circuits\n")

    for row, block in list(zip([r for r in rows if r[3]], answer))[:6]:
        current = block.get("current") or {}
        hourly = block.get("hourly") or {}
        cut = (current.get("time") or "")[:13]
        times = hourly.get("time") or []
        at = next((i for i, one in enumerate(times) if one[:13] == cut), None)
        rain = surface = None
        if at is not None:
            probs = hourly.get("precipitation_probability") or []
            soil = hourly.get("soil_temperature_0cm") or []
            rain = probs[at] if at < len(probs) else None
            surface = soil[at] if at < len(soil) else None
        print(f"  {row[2][:34]:<34} {row[5]}, {row[6]}")
        print(f"      air {current.get('temperature_2m')}°  "
              f"feels {current.get('apparent_temperature')}°  "
              f"surface {surface}°")
        print(f"      humidity {current.get('relative_humidity_2m')}%  "
              f"wind {current.get('wind_speed_10m')} km/h  "
              f"code {current.get('weather_code')}  "
              f"rain now {current.get('precipitation')}mm  "
              f"chance {rain}%  day={current.get('is_day')}")
        print(f"      observed {current.get('time')}  "
              f"tz {block.get('timezone')} ({block.get('utc_offset_seconds')}s)")

    # ---- 3. what is missing, said plainly ----------------------------
    have = [k for k in ("temperature_2m", "apparent_temperature",
                        "relative_humidity_2m", "weather_code",
                        "wind_speed_10m", "precipitation", "is_day")
            if (answer[0].get("current") or {}).get(k) is not None]
    print(f"\ncurrent fields that came back: {', '.join(have)}")
    soil = (answer[0].get("hourly") or {}).get("soil_temperature_0cm") or []
    print(f"soil_temperature_0cm samples: {len([s for s in soil if s is not None])}"
          f" of {len(soil)}")
    print("\nunits:", json.dumps(answer[0].get("current_units") or {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
