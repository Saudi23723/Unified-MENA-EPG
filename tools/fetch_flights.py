#!/usr/bin/env python3
"""
Channel 6 - fetch today's flights for the tracked airlines from AviationStack
and cache them to flights.json for the video generator.

Usage:
    AVIATIONSTACK_API_KEY=xxxx python3 fetch_flights.py --out /path/flights.json

Quota safety (free plan = ~100 API requests / month):
  * MAX_PAGES pages per airline per run, so a run costs at most
    len(AIRLINES) * MAX_PAGES requests.
  * If the monthly quota is exhausted (HTTP 429 usage_limit_reached) the run
    stops calling the API and KEEPS the previously cached flights for every
    airline it could not refresh, so the channel never loses an airline.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error, urllib.parse, datetime

AIRLINES = ["EY", "EK", "RJ"]
MAX_PAGES = 1  # pages (100 flights) per airline per run -> 3 requests/run
API = "https://api.aviationstack.com/v1/flights"


class QuotaExhausted(Exception):
    pass


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            if e.code == 429 and "usage_limit" in body:
                raise QuotaExhausted(body)
            if e.code == 429 and attempt < 3:
                wait = 20 * (attempt + 1)
                print(f"  rate-limited, retrying in {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code} {body[:200]}")


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
    rows = []
    for page in range(MAX_PAGES):
        q = urllib.parse.urlencode({
            "access_key": key, "airline_iata": iata,
            "limit": 100, "offset": page * 100,
        })
        data = get(f"{API}?{q}")
        batch = data.get("data", [])
        rows += batch
        total = (data.get("pagination") or {}).get("total", len(rows))
        if not batch or len(rows) >= total:
            break
        if page + 1 < MAX_PAGES:
            time.sleep(5)  # stay under the per-minute rate limit
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
        acd = f.get("aircraft") or {}
        ac = acd.get("iata") or acd.get("icao") or acd.get("registration") or ""
        live = f.get("live") or {}
        out.append({
            "code": iata,
            "num": (fl0.get("iata") or f"{iata}{fl0.get('number') or ''}").strip(),
            "o": dep.get("iata") or "---",
            "d": arr.get("iata") or "---",
            "dep": d0,
            "arr": a0 if a0 >= d0 else a0 + 1440,
            "ac": ac or "\u2014",
            "api_status": (f.get("flight_status") or "").upper(),
            "delay": int(dep.get("delay") or 0),
            "lat": live.get("latitude"),
            "lon": live.get("longitude"),
            "alt": live.get("altitude"),
        })
    return out


def load_cache(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    key = os.environ.get("AVIATIONSTACK_API_KEY")
    if not key:
        sys.exit("AVIATIONSTACK_API_KEY not set")

    date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    cache = load_cache(args.out)
    cached = cache.get("flights") or []
    cache_is_today = cache.get("date") == date

    flights, errors, quota_done = [], [], False
    for a in AIRLINES:
        if quota_done:
            errors.append(f"{a}: skipped (monthly API quota reached)")
            continue
        try:
            got = fetch(key, a, date)
            print(f"{a}: {len(got)} flights", flush=True)
        except QuotaExhausted:
            quota_done = True
            got = []
            errors.append(f"{a}: monthly API quota reached")
            print(f"{a}: monthly API quota reached", flush=True)
        except Exception as e:
            got = []
            errors.append(f"{a}: {e}")
            print(f"{a}: FAILED {e}", flush=True)
        if not got and cache_is_today:
            got = [f for f in cached if f.get("code") == a]
            if got:
                print(f"{a}: reusing {len(got)} cached flights", flush=True)
        flights += got

    if not flights and cached:
        flights = cached
        errors.append("no fresh data: reused full cache")

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
