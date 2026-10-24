// DreamTV relay v2 ("my own m3u4u") - works for big playlists (Strong: 22,000+ channels).
// DreamTV logs in here as an Xtream server. Channel list, groups, clean names and guide come from the
// Unified-MENA-EPG repo; every video link is redirected (302) to the real provider, so no video passes here.
// No logins stored: DreamTV sends the username/password typed into its Xtream form; they only go into
// the redirect to the provider.
const PROVIDER = "PROVIDER_ADDRESS";   // server address only, e.g. http://example.com:8080
const PLAYLIST = "PLAYLIST_NAME";      // folder name in xtream/ (strong, hydra, ...)
const REPO = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/";
const MAIN = REPO + "main/xtream/" + PLAYLIST + "/";
const DATA = REPO + "xtream-data/";

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*" };
const JSONH = { ...CORS, "Content-Type": "application/json; charset=utf-8" };
const json = (o, ttl = 60) => new Response(JSON.stringify(o), { headers: { ...JSONH, "Cache-Control": `max-age=${ttl}` } });

// Pass a repo file straight through (no parsing, so big lists cost almost no CPU).
async function pass(url, ttl, empty) {
  const r = await fetch(url, { cf: { cacheTtl: ttl, cacheEverything: true } });
  if (!r.ok) return empty !== undefined ? json(empty, 60) : new Response("not found", { status: 404, headers: CORS });
  return new Response(r.body, { headers: { ...JSONH, "Cache-Control": `max-age=${Math.min(ttl, 300)}` } });
}

export default {
  async fetch(req) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const p = url.pathname;
    if (p === "/") return new Response("ok", { headers: CORS });

    if (p === "/player_api.php") {
      const q = url.searchParams, user = q.get("username") || "", pass_ = q.get("password") || "";
      const action = q.get("action") || "";
      if (!user || !pass_) return json({ user_info: { auth: 0 } }, 0);
      if (!action) {
        const now = Math.floor(Date.now() / 1000);
        return json({
          user_info: { username: user, password: pass_, message: "", auth: 1, status: "Active", exp_date: null,
            is_trial: "0", active_cons: "0", created_at: String(now), max_connections: "1",
            allowed_output_formats: ["m3u8", "ts"] },
          server_info: { url: url.hostname, port: url.protocol === "https:" ? "443" : "80", https_port: "443",
            server_protocol: url.protocol.replace(":", ""), rtmp_port: "0", timezone: "UTC", timestamp_now: now,
            time_now: new Date().toISOString().slice(0, 19).replace("T", " ") },
        }, 0);
      }
      if (action === "get_live_categories") return pass(MAIN + "live_categories.json", 900, []);
      if (action === "get_live_streams") {
        const cat = q.get("category_id");
        return cat ? pass(MAIN + `cat/${encodeURIComponent(cat)}.json`, 900, [])
                   : pass(MAIN + "live_streams.json", 900, []);
      }
      if (action === "get_simple_data_table" || action === "get_short_epg") {
        const id = q.get("stream_id") || "";
        const m = await fetch(DATA + `map/${PLAYLIST}/${Number(id) % 256}.json`, { cf: { cacheTtl: 900, cacheEverything: true } });
        if (!m.ok) return json({ epg_listings: [] });
        const file = (await m.json())[id];
        if (!file) return json({ epg_listings: [] });
        if (action === "get_simple_data_table") return pass(DATA + `epg/${file}.json`, 600, { epg_listings: [] });
        const r = await fetch(DATA + `epg/${file}.json`, { cf: { cacheTtl: 600, cacheEverything: true } });
        if (!r.ok) return json({ epg_listings: [] });
        const now = Date.now() / 1000;
        const list = ((await r.json()).epg_listings || []).filter((x) => Number(x.stop_timestamp) > now)
          .slice(0, Number(q.get("limit")) || 4);
        return json({ epg_listings: list }, 300);
      }
      // Movies / series: answered by the provider itself.
      return Response.redirect(`${PROVIDER}/player_api.php${url.search}`, 302);
    }
    // Video links (live / movie / series / timeshift): straight to the provider.
    return Response.redirect(PROVIDER + p + url.search, 302);
  },
};
