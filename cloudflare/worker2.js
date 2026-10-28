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
// Live names for event / PPV channels, read from the provider with the viewer's own login (see get_live_streams).
const LIVE_EVENT_NAMES = true;
const EVENT_GROUP = /^(?!.*24\/7)(?:.*(PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\+|TSN\+|SN\+|PEACOCK|PARAMOUNT|CUP GAMES|NFL SPORTS)|STAN|MAX|SOCCER|DAZN)$|^(?!.*24\/7).*(PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\+|TSN\+|SN\+|PEACOCK|PARAMOUNT|CUP GAMES|NFL SPORTS|ᴘᴘᴠ|ᴇᴠᴇɴᴛ|ᴱᵛᵉⁿᵗ|NBA PASS|DAZN|STAN\b|SOCCER)/i;
// ASCII-only JSON (\u escapes): DreamTV reads answers as Latin-1, so Arabic / Turkish names must be escaped.
const asciiJson = (o) => JSON.stringify(o).replace(/[\u007f-\uffff]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
const ESC = new Array(65536);
const esc = (c) => { const k = c.charCodeAt(0); return ESC[k] || (ESC[k] = "\\u" + k.toString(16).padStart(4, "0")); };
const json = (o, ttl = 60) => new Response(asciiJson(o), { headers: { ...JSONH, "Cache-Control": `max-age=${ttl}` } });

// Pass a repo file straight through (no parsing, so big lists cost almost no CPU).
async function pass(url, ttl, empty) {
  const r = await fetch(url, { cf: { cacheTtl: ttl, cacheEverything: true } });
  if (!r.ok) return empty !== undefined ? json(empty, 60) : new Response("not found", { status: 404, headers: CORS });
  return new Response(r.body, { headers: { ...JSONH, "Cache-Control": `max-age=${Math.min(ttl, 300)}` } });
}

const MEMO = new Map();  // login -> { t, list } for this worker instance

async function digest(t) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t));
  return [...new Uint8Array(b)].slice(0, 12).map((x) => x.toString(16).padStart(2, "0")).join("");
}

// The repo's list with today's event names and the provider's logos where the repo has none (owner, 27 Oct 2026).
async function merged(user, pass_, req) {
  const [mine, cats] = await Promise.all([
    fetch(MAIN + "live_streams.json", { cf: { cacheTtl: 900, cacheEverything: true } }).then((r) => (r.ok ? r.json() : [])),
    fetch(MAIN + "live_categories.json", { cf: { cacheTtl: 900, cacheEverything: true } }).then((r) => (r.ok ? r.json() : [])),
  ]);
  const live = await Promise.race([
    fetch(`${PROVIDER}/player_api.php?username=${encodeURIComponent(user)}&password=${encodeURIComponent(pass_)}&action=get_live_streams`,
      { headers: { "User-Agent": req.headers.get("User-Agent") || "" }, cf: { cacheTtl: 300, cacheEverything: true } })
      .then((r) => (r.ok ? r.json() : [])).catch(() => []),
    new Promise((r) => setTimeout(() => r(null), 4000)),
  ]);
  const strip = (l) => l.map((s) => (s.stream_icon ? { ...s, stream_icon: String(s.stream_icon).replace(/#weak$/, "") } : s));
  if (!Array.isArray(live) || !live.length) return { list: strip(mine), fresh: false };
  const ev = new Set(cats.filter((c) => EVENT_GROUP.test(c.category_name || "")).map((c) => String(c.category_id)));
  const now = new Map();
  for (const s of live) now.set(String(s.stream_id), s);
  for (const s of mine) {
    const p = now.get(String(s.stream_id));
    if (!p) continue;
    if ((!s.stream_icon || String(s.stream_icon).endsWith("#weak")) && p.stream_icon) s.stream_icon = p.stream_icon;
    if (ev.has(String(s.category_id)) && p.name)
      s.name = String(p.name).replace(/[\u24e7\u00a7]/g, "").replace(/\s+/g, " ").trim();
  }
  const base = (s) => String(s.category_id) + "|" + String(s.name || "").toUpperCase()
    .replace(/\b(UHD|FHD|HD|SD|LQ|4K|8K|HEVC|RAW|3840P|60FPS|50FPS|HDR|BACKUP|BK)\b/g, " ").replace(/[^A-Z0-9\u0600-\u06FF+]/g, "");
  const weak = (s) => !s.stream_icon || String(s.stream_icon).endsWith("#weak");
  const logo = new Map();
  for (const s of mine) if (!weak(s) && !logo.has(base(s))) logo.set(base(s), s.stream_icon);
  for (const s of mine) if (weak(s)) { const l = logo.get(base(s)); if (l) s.stream_icon = l; }
  return { list: strip(mine), fresh: true };
}

export default {
  async fetch(req) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const p = url.pathname;
    if (p === "/") return new Response("ok", { headers: CORS });

    // M3U playlist link (get.php), for apps that take a "playlist URL": same clean names and groups, in the
    // same order. Each link points back here and is redirected to the provider like the Xtream ones.
    if (p === "/get.php") {
      const q = url.searchParams, user = q.get("username") || "", pass_ = q.get("password") || "";
      if (!user || !pass_) return new Response("username and password needed", { status: 401, headers: CORS });
      const [cats, streams] = await Promise.all([
        fetch(MAIN + "live_categories.json", { cf: { cacheTtl: 900, cacheEverything: true } }).then((r) => r.json()),
        fetch(MAIN + "live_streams.json", { cf: { cacheTtl: 900, cacheEverything: true } }).then((r) => r.json()),
      ]);
      const group = {};
      for (const c of cats) group[c.category_id] = c.category_name;
      const ext = q.get("output") === "m3u8" || q.get("output") === "hls" ? "m3u8" : "ts";
      const base = `${url.origin}/live/${encodeURIComponent(user)}/${encodeURIComponent(pass_)}/`;
      const clean = (t) => String(t || "").replace(/[",\r\n]/g, " ");
      const out = ["#EXTM3U"];
      for (const s of streams) {
        out.push(`#EXTINF:-1 tvg-id="${clean(s.epg_channel_id)}" tvg-name="${clean(s.name)}" tvg-logo="${clean(s.stream_icon)}" group-title="${clean(group[s.category_id])}",${clean(s.name)}`);
        out.push(`${base}${s.stream_id}.${ext}`);
      }
      return new Response(out.join("\n") + "\n", { headers: { ...CORS, "Content-Type": "audio/x-mpegurl; charset=utf-8",
        "Content-Disposition": `inline; filename="${PLAYLIST}.m3u"`, "Cache-Control": "no-store" } });
    }

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
        const file = cat ? MAIN + `cat/${encodeURIComponent(cat)}.json` : MAIN + "live_streams.json";
        if (!LIVE_EVENT_NAMES) return pass(file, 900, []);
        // Event / PPV channels: the provider renames them for each match ("Hawks vs Rockets :NBA 06"); the repo's
        // copy is from the export day, so take today's names from the provider (owner, 27 October 2026).
        // Speed (owner, 28 Oct 2026: DreamTV hangs on start): the provider's full list is read only for the full
        // list request, at most once per 10 minutes per login (kept in this worker's memory), and only if the
        // provider answers within 4 s; a single category is cut from that copy or served straight from the repo.
        try {
          const k = await digest(user + "\n" + pass_);
          const c = MEMO.get(k);
          if (c && Date.now() - c.t < 600000) {
            return json(cat ? c.list.filter((s) => String(s.category_id) === String(cat)) : c.list, 300);
          }
          if (cat) return pass(file, 900, []);
          const all = await merged(user, pass_, req);
          if (all.fresh) { MEMO.set(k, { t: Date.now(), list: all.list }); if (MEMO.size > 20) MEMO.delete(MEMO.keys().next().value); }
          return json(all.list, 300);
        } catch (e) {
          return pass(file, 900, []);
        }
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
      // Movie / series groups: the provider's own list, put in the owner's order when the repo has one
      // (xtream/<playlist>/vod_order.json or series_order.json: names in order; groups not listed follow).
      if (action === "get_vod_categories" || action === "get_series_categories") {
        const file = action === "get_vod_categories" ? "vod_order.json" : "series_order.json";
        try {
          const [cr, or] = await Promise.all([
            fetch(`${PROVIDER}/player_api.php${url.search}`, { headers: { "User-Agent": req.headers.get("User-Agent") || "" } }),
            // short cache: a new or changed order file shows within 2 minutes (a cached "not found" kept
            // Dream4k's new lists away, 28 Oct 2026)
            fetch(MAIN + file + "?v=" + Math.floor(Date.now() / 120000), { cf: { cacheTtl: 120, cacheEverything: true } }),
          ]);
          if (cr.ok) {
            let cats = await cr.json();
            // group names only (no login) in the worker log, so the owner's hide / order lists can be written
            if (Array.isArray(cats)) console.log(action + " " + JSON.stringify(cats.map((c) => c.category_name)));
            if (!or.ok || !Array.isArray(cats)) return json(cats, 300);
            const want = await or.json(), pos = {};
            // "tidy": names compared (and shown) without the "|AR| ✪ " prefix and the stretching dashes
            // ("افــــلام" -> "افلام"); "only": groups not in "visible" are hidden (Dream4k, 28 October 2026)
            const tidy = (n) => String(n || "").replace(/^\s*\|[A-Z]{2,6}\|\s*✪?\s*/, "").replace(/\u0640/g, "").replace(/\s+/g, " ").trim();
            if (want.tidy && Array.isArray(cats)) cats = cats.map((c) => ({ ...c, category_name: tidy(c.category_name) }));
            (want.visible || (Array.isArray(want) ? want : [])).forEach((n, i) => { pos[want.tidy ? tidy(n) : String(n).trim()] = i; });
            if (want.only && Array.isArray(cats)) cats = cats.filter((c) => String(c.category_name || "").trim() in pos);
            // "first": patterns for groups that always lead, whatever the provider calls them
            // (Hydra, 25 October 2026: "Turkish series always first")
            const first = (want.first || []).map((f) => new RegExp(f, "i"));
            // "hide": patterns for groups the owner does not want at all (Family4k, 28 October 2026)
            const hide = (want.hide || []).map((f) => new RegExp(f, "i"));
            if (hide.length) cats = cats.filter((c) => !hide.some((r) => r.test(String(c.category_name || ""))));
            const lead = (name) => { const i = first.findIndex((r) => r.test(name)); return i < 0 ? first.length : i; };
            const rank = (c) => { const n = String(c.category_name || "").trim(); return lead(n) * 1e7 + (pos[n] ?? 1e6); };
            return json(cats.map((c, i) => [c, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map((x) => x[0]), 300);
          }
        } catch (e) { /* fall through to the provider */ }
      }
      // Movie / series lists and details: some providers (Argon, 28 Oct 2026) send raw UTF-8, which DreamTV reads
      // as Latin-1 ("AR - Ù…Ø³Ù„Ø³Ù„"); pass them through here with non-ASCII as \u escapes. ASCII answers are
      // passed unchanged.
      if (/^get_(series|vod_streams|series_info|vod_info)$/.test(action)) {
        try {
          const r = await fetch(`${PROVIDER}/player_api.php${url.search}`, { headers: { "User-Agent": req.headers.get("User-Agent") || "" } });
          if (r.ok) {
            const t = await r.text();
            const out = /[^\x00-\x7f]/.test(t) ? t.replace(/[^\x00-\x7f]/g, esc) : t;
            return new Response(out, { headers: { ...JSONH, "Cache-Control": "max-age=300" } });
          }
        } catch (e) { /* fall through to the provider */ }
      }
      // Anything else: answered by the provider itself.
      return Response.redirect(`${PROVIDER}/player_api.php${url.search}`, 302);
    }
    // Video links (live / movie / series / timeshift): straight to the provider.
    return Response.redirect(PROVIDER + p + url.search, 302);
  },
};
