#!/usr/bin/env python3
"""
Channel 6 — fetch today's flights for the 5 tracked airlines from AviationStack
and cache them to flights.json for the video generator.

Usage:
    AVIATIONSTACK_API_KEY=xxxx python3 fetch_flights.py --out /path/flights.json

Costs 5 API requests per run (one per airline). Run once or twice a day; the
generator recomputes live status / progress locally every time it renders.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error, urllib.parse, datetime

AIRLINES = ["EY", "EK", "RJ"]
API = "https://api.aviationstack.com/v1/flights"


def get(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                wait = 20 * (attempt + 1)
                print(f"  rate-limited, retrying in {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise


def minutes(iso):
    """ISO timestamp -> minutes since UTC midnight."""
    if not iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt.hour * 60 + dt.minute


def fetch(key, iata, date):
    # NOTE: the free plan does not allow the flight_date filter, so we request
    # the airline's current feed and filter to today's date locally.
    # Paginate (limit 100 per page) so we capture the airline's FULL day,
    # not just the first 100 results.
    rows = []
    offset = 0
    while True:
        q = urllib.parse.urlencode({
            "access_key": key, "airline_iata": iata,
            "limit": 100, "offset": offset,
        })
        data = get(f"{API}?{q}")
        batch = data.get("data", [])
        rows += batch
        total = (data.get("pagination") or {}).get("total", len(rows))
        if not batch or len(rows) >= total:
            break
        offset += 100
        time.sleep(5)  # stay under the free plan's per-minute rate limit
    out = []
    for f in rows:
        if f.get("flight_date") != date:
            continue
        fl0 = f.get("flight") or {}
        if fl0.get("codeshared"):
            continue  # marketing duplicate of another carrier's flight
        dep, arr = f.get("departure") or {}, f.get("arrival") or {}
        d0 = minutes(dep.get("estimated") or dep.get("scheduled"))
        a0 = minutes(arr.get("estimated") or arr.get("scheduled"))
        if d0 is None or a0 is None:
            continue
        fl = f.get("flight") or {}
        acd = f.get("aircraft") or {}
        ac = acd.get("iata") or acd.get("icao") or acd.get("registration") or ""
        live = f.get("live") or {}
        out.append({
            "code": iata,
            "num": (fl.get("iata") or f"{iata}{fl.get('number') or ''}").strip(),
            "o": dep.get("iata") or "---",
            "d": arr.get("iata") or "---",
            "dep": d0,
            "arr": a0 if a0 >= d0 else a0 + 1440,
            "ac": ac or "—",
            "api_status": (f.get("flight_status") or "").upper(),
            "delay": int(dep.get("delay") or 0),
            "lat": live.get("latitude"),
            "lon": live.get("longitude"),
            "alt": live.get("altitude"),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    key = os.environ.get("AVIATIONSTACK_API_KEY")
    if not key:
        sys.exit("AVIATIONSTACK_API_KEY not set")

    date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    flights, errors = [], []
    for a in AIRLINES:
        try:
            got = fetch(key, a, date)
            flights += got
            print(f"{a}: {len(got)} flights", flush=True)
        except Exception as e:  # keep going, partial data is still useful
            errors.append(f"{a}: {e}")
            print(f"{a}: FAILED {e}", flush=True)

    if not flights:
        sys.exit("no flights fetched: " + "; ".join(errors))

    flights.sort(key=lambda f: (f["dep"], f["num"]))
    payload = {
        "generated_utc": datetime.datetime.utcnow().isoformat(timespec="seconds"),
        "date": date,
        "errors": errors,
        "flights": flights,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=1)
    print(f"wrote {len(flights)} flights -> {args.out}")


if __name__ == "__main__":
    main()
