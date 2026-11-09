// DreamTV relay ("my own m3u4u"): an Xtream server that DreamTV logs in to.
// - channel list, groups and clean names come from this repo (xtream/<playlist>/)
// - the guide comes from this repo too (xtream/epg/), in the get_simple_data_table format DreamTV reads
// - every video link is sent straight on (302) to the real provider, so no video passes through here
// No logins are stored here: DreamTV sends the username/password typed into its own Xtream form,
// and they are only placed in the redirect to the provider.
const PROVIDER = "PROVIDER_ADDRESS";   // e.g. http://example.com:8080  (server address only, no login)
const PLAYLIST = "hydra";
const DATA = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/xtream/";

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*" };
const json = (o, ttl = 60) => new Response(JSON.stringify(o), {
  headers: { ...CORS, "Content-Type": "application/json; charset=utf-8", "Cache-Control": `max-age=${ttl}` } });
const safe = (s) => s.replace(/[^A-Za-z0-9._-]/g, "_");

async function data(path, ttl = 900) {
  const r = await fetch(DATA + path, { cf: { cacheTtl: ttl, cacheEverything: true } });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

let streamsCache = null, streamsAt = 0;
async function streams() {
  if (!streamsCache || Date.now() - streamsAt > 900000) {
    streamsCache = await data(`${PLAYLIST}/live_streams.json`); streamsAt = Date.now();
  }
  return streamsCache;
}

export default {
  async fetch(req) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const p = url.pathname;

    if (p === "/" ) return new Response("ok", { headers: CORS });

    if (p === "/player_api.php") {
      const q = url.searchParams, user = q.get("username") || "", pass = q.get("password") || "";
      const action = q.get("action") || "";
      if (!user || !pass) return json({ user_info: { auth: 0 } }, 0);
      if (!action) {
        const now = Math.floor(Date.now() / 1000);
        return json({
          user_info: { username: user, password: pass, message: "", auth: 1, status: "Active", exp_date: null,
            is_trial: "0", active_cons: "0", created_at: String(now), max_connections: "1",
            allowed_output_formats: ["m3u8", "ts"] },
          server_info: { url: url.hostname, port: url.protocol === "https:" ? "443" : "80", https_port: "443",
            server_protocol: url.protocol.replace(":", ""),
            rtmp_port: "0", timezone: "UTC", timestamp_now: now, time_now: new Date().toISOString().slice(0, 19).replace("T", " ") },
        }, 0);
      }
      if (action === "get_live_categories") return json(await data(`${PLAYLIST}/live_categories.json`));
      if (action === "get_live_streams") {
        const all = await streams(), cat = q.get("category_id");
        return json(cat ? all.filter((s) => s.category_id === cat) : all);
      }
      if (action === "get_simple_data_table" || action === "get_short_epg") {
        const id = Number(q.get("stream_id"));
        const s = (await streams()).find((x) => x.stream_id === id);
        if (!s || !s.epg_channel_id) return json({ epg_listings: [] });
        let d;
        try { d = await data(`epg/${safe(s.epg_channel_id)}.json`, 600); } catch (e) { return json({ epg_listings: [] }); }
        let list = d.epg_listings || [];
        if (action === "get_short_epg") {
          const now = Date.now() / 1000;
          list = list.filter((x) => Number(x.stop_timestamp) > now).slice(0, Number(q.get("limit")) || 4);
        }
        return json({ epg_listings: list }, 300);
      }
      // Movies / series: no changes, answered by the provider itself.
      return Response.redirect(`${PROVIDER}/player_api.php${url.search}`, 302);
    }

    // Video links (live / movie / series / timeshift, with or without the folder): straight to the provider.
    return Response.redirect(PROVIDER + p + url.search, 302);
  },
};
