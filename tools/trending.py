#!/usr/bin/env python3
"""What the world is watching, for SAUDI.TV's Home showcase (owner, 10 Nov 2026: "trending, box office foreign
and Arabic, top rated, kept up to date").

Reads The Movie Database (TMDB) with the key in the TMDB_KEY secret and writes trending.json: a few short lists
of titles (name, original name, year, rating, poster, backdrop, overview). The app shows the ones the playlist
in use really has. No key = nothing written (the app then shows the playlist's own newest / top rated).
"""
import json, os, sys, time, urllib.parse, urllib.request

KEY = os.environ.get("TMDB_KEY", "").strip()
IMG = "https://image.tmdb.org/t/p/"


def get(path, **q):
    bearer = len(KEY) > 60  # a v4 token (long) goes in the header, a v3 key in the address
    if not bearer: q["api_key"] = KEY
    url = "https://api.themoviedb.org/3/" + path + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"Accept": "application/json", **({"Authorization": "Bearer " + KEY} if bearer else {})})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if i == 2: raise
            time.sleep(2 + 3 * i)


def rows(path, kind, pages=2, **q):
    """titles of one TMDB list; each also carries its Arabic name (playlists often use it)"""
    out = []; ar = {}
    for p in range(1, pages + 1):
        try:
            for x in get(path, page=p, language="ar", **q).get("results", []):
                ar[x.get("id")] = x.get("title") or x.get("name") or ""
        except Exception:
            pass
        for x in get(path, page=p, **q).get("results", []):
            k = x.get("media_type") or kind
            if k not in ("movie", "tv") or not x.get("poster_path"): continue
            out.append({
                "kind": "series" if k == "tv" else "movie",
                "title": x.get("title") or x.get("name") or "",
                "original": x.get("original_title") or x.get("original_name") or "",
                "ar": ar.get(x.get("id"), ""),
                "year": (x.get("release_date") or x.get("first_air_date") or "")[:4],
                "rating": round(float(x.get("vote_average") or 0), 1),
                "poster": IMG + "w500" + x["poster_path"],
                "backdrop": IMG + "w1280" + x["backdrop_path"] if x.get("backdrop_path") else "",
                "overview": (x.get("overview") or "")[:400],
            })
    return out


def main():
    if not KEY:
        print("no TMDB_KEY secret: nothing to do"); return 0
    today = time.strftime("%Y-%m-%d"); past = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 400 * 86400))
    recent = {"primary_release_date.gte": past}; recent_tv = {"first_air_date.gte": past}
    lists = [
        ("Trending this week", rows("trending/all/week", "movie", 4)),
        ("Trending today", rows("trending/all/day", "movie", 2)),
        ("In cinemas now · box office", rows("movie/now_playing", "movie", 3, region="US")),
        ("Arabic series · trending", rows("discover/tv", "tv", 4, with_original_language="ar", sort_by="popularity.desc", **recent_tv)
            + rows("discover/tv", "tv", 3, with_original_language="ar", sort_by="popularity.desc")),
        ("Arabic movies · trending", rows("discover/movie", "movie", 4, with_original_language="ar", sort_by="popularity.desc", **recent)
            + rows("discover/movie", "movie", 3, with_original_language="ar", sort_by="popularity.desc")),
        ("Turkish series · trending", rows("discover/tv", "tv", 5, with_original_language="tr", sort_by="popularity.desc")),
        ("Turkish movies · trending", rows("discover/movie", "movie", 3, with_original_language="tr", sort_by="popularity.desc")),
        ("Arabic · top rated", rows("discover/tv", "tv", 2, with_original_language="ar", sort_by="vote_average.desc", **{"vote_count.gte": 15})
            + rows("discover/movie", "movie", 2, with_original_language="ar", sort_by="vote_average.desc", **{"vote_count.gte": 30})),
        ("Popular series", rows("tv/popular", "tv", 3)),
        ("Popular movies", rows("movie/popular", "movie", 3)),
        ("Top rated movies", rows("movie/top_rated", "movie", 3)),
        ("Top rated series", rows("tv/top_rated", "tv", 3)),
    ]
    out = {"updated": today, "source": "TMDB", "lists": [{"name": n, "items": l} for n, l in lists if l]}
    json.dump(out, open("trending.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("trending.json:", {l["name"]: len(l["items"]) for l in out["lists"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
