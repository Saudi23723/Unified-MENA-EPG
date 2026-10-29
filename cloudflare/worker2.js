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
const EVENT_GROUP = /^(?!.*24\/7)(?:.*(PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\+|TSN\+|SN\+|PEACOCK|PARAMOUNT|CUP GAMES|NFL SPORTS)|STAN|MAX|SOCCER|DAZN)$|^(?!.*24\/7).*(PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\+|TSN\+|SN\+|PEACOCK|PARAMOUNT|CUP GAMES|NFL SPORTS|ᴘᴘᴠ|ᴇᴠᴇɴᴛ|ᴱᵛᵉⁿᵗ|NBA PASS|DAZN|STAN\b|SOCCER|\bNBA\b|\bNFL\b|\bNHL\b|\bMLB\b|\bNCAA|REPLAY|MAX ESPN|\bFLO\b|FLOSPORT)/i;
// ASCII-only JSON (\u escapes): DreamTV reads answers as Latin-1, so Arabic / Turkish names must be escaped.
const ESC = new Array(65536);
const esc = (c) => { const k = c.charCodeAt(0); return ESC[k] || (ESC[k] = "\\u" + k.toString(16).padStart(4, "0")); };
const asciiJson = (o) => JSON.stringify(o).replace(/[\u007f-\uffff]/g, esc);
const json = (o, ttl = 60) => new Response(asciiJson(o), { headers: { ...JSONH, "Cache-Control": `max-age=${ttl}` } });

// Pass a repo file straight through (no parsing, so big lists cost almost no CPU).
// Repo files are read with a 2-minute version tag, so a change on GitHub reaches the TV within minutes instead
// of after Cloudflare's 15-minute copy runs out (owner, 28 Oct 2026: new US Local groups did not show).
const fresh = (u) => (u.startsWith(MAIN) ? u + (u.includes("?") ? "&" : "?") + "v=" + Math.floor(Date.now() / 120000) : u);
async function pass(url, ttl, empty) {
  if (url.startsWith(MAIN)) ttl = Math.min(ttl, 120);
  const r = await fetch(fresh(url), { cf: { cacheTtl: ttl, cacheEverything: true } });
  if (!r.ok) return empty !== undefined ? json(empty, 60) : new Response("not found", { status: 404, headers: CORS });
  return new Response(r.body, { headers: { ...JSONH, "Cache-Control": `max-age=${Math.min(ttl, 300)}` } });
}


async function digest(t) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t));
  return [...new Uint8Array(b)].slice(0, 12).map((x) => x.toString(16).padStart(2, "0")).join("");
}

// Today's event names and the provider's logos where the repo has none (owner, 27 Oct 2026), as a small patch
// { t, n: {stream_id: name}, i: {stream_id: logo} }. Built in the background (never makes DreamTV wait) from the
// provider's full list, at most every 15 minutes, and kept in KV (binding LIVE, key = playlist) so every worker
// instance and every category request gets it (owner, 28 Oct 2026: NBA PASS names stayed on yesterday's games).
const PATCH_AGE = 15 * 60000;
const DYN = { id: "9001", name: "🤼 | FLO WRESTLING", from: /\bFLO\b|FLOSPORT/i, match: /WRESTL|مصارع/i,
  near: /FLO\s*SPORTS?\s*PPV|FLO\s*FLSP|FLOSPORTS?\s*TV/i };
let PATCH = null, BUILDING = 0;
// playlists whose provider refuses the relay's live-list request: their names come from GitHub (tools/live_patch.py)
const GITHUB_LIVE = new Set(["strong", "dream4k"]);
// playlists whose provider sends movies / series without a listed group (they show as "-1")
const ORPHANS = new Set(["argon"]);
// Some providers refuse Cloudflare's addresses (Strong answers 403, 28 Oct 2026): after a refusal this worker stops
// asking for an hour, so the provider does not see a stream of refused requests; DreamTV then talks to it directly.
let REFUSED = 0;
const refused = () => Date.now() - REFUSED < 3600000;
const note = (r) => { if (r && (r.status === 403 || r.status === 401)) REFUSED = Date.now(); return r; };
// the full live list is refused separately (Dream4k, 28 Oct 2026: 403 on the live list while movies still worked)
let LIVE_REFUSED = 0;
const liveRefused = () => Date.now() - LIVE_REFUSED < 3600000;

async function readPatch(env) {
  if (PATCH && Date.now() - PATCH.t < PATCH_AGE) return PATCH;
  // playlists whose provider refuses Cloudflare get the patch from GitHub (tools/live_patch.py, branch live-patch)
  if (liveRefused() || GITHUB_LIVE.has(PLAYLIST)) {
    try {
      const r = await fetch(REPO + "live-patch/" + PLAYLIST + ".json?v=" + Math.floor(Date.now() / 120000), { cf: { cacheTtl: 120, cacheEverything: true } });
      if (r.ok) { const k = await r.json(); if (k && k.t && (!PATCH || k.t > PATCH.t)) PATCH = k; }
    } catch (e) {}
    if (PATCH) return PATCH;
  }
  if (env && env.LIVE) {
    try { const k = await env.LIVE.get(PLAYLIST, { type: "json", cacheTtl: 60 }); if (k && (!PATCH || k.t > PATCH.t)) PATCH = k; } catch (e) {}
  }
  return PATCH;
}

async function buildPatch(env, user, pass_, ua) {
  if (Date.now() - BUILDING < 120000 || liveRefused() || GITHUB_LIVE.has(PLAYLIST)) return;
  BUILDING = Date.now();
  try {
    const [mine, cats, live] = await Promise.all([
      fetch(fresh(MAIN + "live_streams.json"), { cf: { cacheTtl: 120, cacheEverything: true } }).then((r) => (r.ok ? r.json() : [])),
      fetch(fresh(MAIN + "live_categories.json"), { cf: { cacheTtl: 120, cacheEverything: true } }).then((r) => (r.ok ? r.json() : [])),
      fetch(`${PROVIDER}/player_api.php?username=${encodeURIComponent(user)}&password=${encodeURIComponent(pass_)}&action=get_live_streams`,
        { headers: { "User-Agent": ua } }).then((r) => { if (r.status === 403 || r.status === 401) LIVE_REFUSED = Date.now(); return r.ok ? r.json() : []; }).catch(() => []),
    ]);
    if (!Array.isArray(live) || !live.length) return;
    const ev = new Set(cats.filter((c) => EVENT_GROUP.test(c.category_name || "")).map((c) => String(c.category_id)));
    const now = new Map();
    for (const x of live) now.set(String(x.stream_id), x);
    const n = {}, i = {};
    const weak = (x) => !x.stream_icon || String(x.stream_icon).endsWith("#weak");
    for (const x of mine) {
      const pv = now.get(String(x.stream_id));
      if (!pv) continue;
      if (ev.has(String(x.category_id)) && pv.name) {
        // the provider's quality tag ("[1080p]") is dropped: the owner's names carry none
        const nm = String(pv.name).replace(/[\u24e7\u00a7]/g, "").replace(/\s*\[(\d{3,4}p|4K|UHD|FHD|HD|SD)\]\s*$/i, "").replace(/\s+/g, " ").trim();
        // the same channel with only a country prefix / quality marks / spacing changed keeps the owner's name
        const key = (t) => String(t).normalize("NFKC").toUpperCase().replace(/^[A-Z]{2,3}\s*[:|]\s*/, "")
          .replace(/\b(UHD|FHD|HD|SD|4K|8K|HEVC|RAW|\d{3,4}P)\b/g, "").replace(/[^A-Z0-9\u0600-\u06FF]/g, "");
        if (nm && nm !== x.name && key(nm) !== key(x.name)) n[x.stream_id] = nm;
      }
      if (weak(x) && pv.stream_icon) i[x.stream_id] = pv.stream_icon;
    }
    // New channels: a provider group whose channels are (mostly) in one of our groups gets its new channels
    // added at the end of that group; channels the provider removed are taken out (owner, 28 Oct 2026: "if the
    // provider updates something, I get the update").
    const ours = new Map(mine.map((x) => [String(x.stream_id), x]));
    const byCat = new Map();
    for (const x of live) { const c = String(x.category_id); if (!byCat.has(c)) byCat.set(c, []); byCat.get(c).push(x); }
    const add = {};
    for (const [, xs] of byCat) {
      const known = xs.filter((x) => ours.has(String(x.stream_id)));
      if (known.length < Math.max(2, xs.length / 2)) continue;
      const votes = {};
      for (const x of known) { const g = String(ours.get(String(x.stream_id)).category_id); votes[g] = (votes[g] || 0) + 1; }
      const g = Object.keys(votes).sort((a, b) => votes[b] - votes[a])[0];
      // only into event / PPV groups: elsewhere the owner's groups are hand-picked (Up1 test, 28 Oct 2026: kids
      // channels landed in Sky Sports)
      if (!ev.has(g)) continue;
      for (const x of xs) {
        if (ours.has(String(x.stream_id)) || !x.name) continue;
        (add[g] = add[g] || []).push({ stream_id: x.stream_id, name: String(x.name).replace(/[\u24e7\u00a7]/g, "").replace(/\s+/g, " ").trim(),
          stream_icon: x.stream_icon || "", epg_channel_id: null });
      }
    }
    const gone = mine.filter((x) => !now.has(String(x.stream_id))).map((x) => x.stream_id);
    // a provider answer missing most of our channels is a broken answer, not a removal
    PATCH = { t: Date.now(), n, i, add, gone: gone.length < mine.length / 3 ? gone : [] };
    if (env && env.LIVE) await env.LIVE.put(PLAYLIST, JSON.stringify(PATCH));
  } catch (e) { /* next request tries again */ } finally { BUILDING = 0; }
}

// The repo's list (or one category) with the patch applied; "#weak" logos without a provider logo take the logo
// of the same channel in another quality, else stay as they are.
function applyPatch(list, pt, cat) {
  if (pt && pt.gone && pt.gone.length) { const g = new Set(pt.gone.map(String)); list = list.filter((x) => !g.has(String(x.stream_id))); }
  if (pt && pt.add) {
    const have = new Set(list.map((x) => String(x.stream_id)));
    // numbers from 90000 up, the same in the full list and in a single group
    let num = 90000;
    const extra = [];
    for (const [g, xs] of Object.entries(pt.add)) {
      for (const x of xs) if (++num && !(cat && String(cat) !== g) && !have.has(String(x.stream_id))) {
        have.add(String(x.stream_id));
        extra.push({ num, name: x.name, stream_type: "live", stream_id: x.stream_id, stream_icon: x.stream_icon,
          epg_channel_id: null, added: "0", category_id: g, custom_sid: "", tv_archive: 0, direct_source: "", tv_archive_duration: 0 });
      }
    }
    if (extra.length) {
      // each new channel right after the last channel of its group
      // (in a group with game slots, after the last slot: team channels / NBA TV stay at the bottom)
      const slot = (n) => /:\s*[A-Za-z][A-Za-z0-9+ .]*?\s+0*\d{1,4}\b|^[A-Za-z][A-Za-z+ .]{0,23}?\s*0*\d{1,4}\s*[:|\-]|^\(?[A-Za-z+ ]+\s*0*\d{1,4}\)|^[A-Za-z][A-Za-z+ .]{0,23}?\s+0*\d{1,4}(\s+(UHD|FHD|HD|SD|4K))?\s*$/.test(String(n || ""));
      const last = {}, lastSlot = {};
      list.forEach((x, k) => { last[String(x.category_id)] = k; if (slot(x.name)) lastSlot[String(x.category_id)] = k; });
      for (const g of Object.keys(lastSlot)) last[g] = lastSlot[g];
      const out = [];
      const after = {};
      for (const x of extra) (after[x.category_id] = after[x.category_id] || []).push(x);
      list.forEach((x, k) => { out.push(x); if (last[String(x.category_id)] === k && after[String(x.category_id)]) out.push(...after[String(x.category_id)]); });
      for (const g of Object.keys(after)) if (!(g in last)) out.push(...after[g]);
      list = out;
    }
  }
  const base = (x) => String(x.category_id) + "|" + String(x.name || "").toUpperCase()
    .replace(/\b(UHD|FHD|HD|SD|LQ|4K|8K|HEVC|RAW|3840P|60FPS|50FPS|HDR|BACKUP|BK)\b/g, " ").replace(/[^A-Z0-9\u0600-\u06FF+]/g, "");
  const weak = (x) => !x.stream_icon || String(x.stream_icon).endsWith("#weak");
  for (const x of list) {
    if (pt && pt.n[x.stream_id]) x.name = pt.n[x.stream_id];
    if (pt && weak(x) && pt.i[x.stream_id]) x.stream_icon = pt.i[x.stream_id];
  }
  const logo = new Map();
  for (const x of list) if (!weak(x) && !logo.has(base(x))) logo.set(base(x), x.stream_icon);
  for (const x of list) {
    if (weak(x)) { const l = logo.get(base(x)); if (l) x.stream_icon = l; }
    if (x.stream_icon) x.stream_icon = String(x.stream_icon).replace(/#weak$/, "");
  }
  return list;
}

// The provider's movie / series groups in the owner's order (xtream/<playlist>/vod_order.json or series_order.json).
// Returns null when the provider does not answer; filtered = some groups are hidden.
async function groups(action, url, req) {
  const file = action === "get_vod_categories" ? "vod_order.json" : "series_order.json";
  const q = new URLSearchParams(url.search); q.set("action", action); q.delete("category_id");
  const [cr, or] = await Promise.all([
    fetch(`${PROVIDER}/player_api.php?${q}`, { headers: { "User-Agent": req.headers.get("User-Agent") || "" }, cf: { cacheTtl: 300, cacheEverything: true } }),
    // short cache: a new or changed order file shows within 2 minutes (a cached "not found" kept
    // Dream4k's new lists away, 28 Oct 2026)
    fetch(MAIN + file + "?v=" + Math.floor(Date.now() / 120000), { cf: { cacheTtl: 120, cacheEverything: true } }),
  ]);
  note(cr);
  if (!cr.ok) return null;
  let cats = await cr.json();
  if (!or.ok || !Array.isArray(cats)) return { cats, filtered: false };
  const want = await or.json(), pos = {};
  const n0 = cats.length;
  // "tidy": names compared (and shown) without the "|AR| ✪ " prefix and the stretching dashes
  // ("افــــلام" -> "افلام"); "only": groups not in "visible" are hidden (Dream4k, 28 October 2026)
  // also "EN: " / "ARA: " / "MULTI: " in front and a plain "[1080p]" / "[720p]" behind (Argon, 28 Oct 2026)
  const tidy = (n) => String(n || "").replace(/^\s*\|[A-Z]{2,6}\|\s*✪?\s*/, "").replace(/^\s*[A-Z]{2,6}\s*:\s*/, "")
    .replace(/\s*\[(\d{3,4}p)\]\s*$/i, "").replace(/\u0640/g, "").replace(/\s+/g, " ").trim();
  if (want.tidy) cats = cats.map((c) => ({ ...c, category_name: tidy(c.category_name) }));
  (want.visible || (Array.isArray(want) ? want : [])).forEach((n, i) => { pos[want.tidy ? tidy(n) : String(n).trim()] = i; });
  if (want.only) cats = cats.filter((c) => String(c.category_name || "").trim() in pos);
  // "first": patterns for groups that always lead, whatever the provider calls them
  // (Hydra, 25 October 2026: "Turkish series always first")
  const first = (want.first || []).map((f) => new RegExp(f, "i"));
  // "hide": patterns for groups the owner does not want at all (Family4k, 28 October 2026)
  const hide = (want.hide || []).map((f) => new RegExp(f, "i"));
  if (hide.length) cats = cats.filter((c) => !hide.some((r) => r.test(String(c.category_name || ""))));
  const lead = (name) => { const i = first.findIndex((r) => r.test(name)); return i < 0 ? first.length : i; };
  const rank = (c) => { const n = String(c.category_name || "").trim(); return lead(n) * 1e7 + (pos[n] ?? 1e6); };
  cats = cats.map((c, i) => [c, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map((x) => x[0]);
  return { cats, filtered: cats.length < n0 };
}

export default {
  async fetch(req, env, ctx) {
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
        fetch(fresh(MAIN + "live_categories.json"), { cf: { cacheTtl: 120, cacheEverything: true } }).then((r) => r.json()),
        fetch(fresh(MAIN + "live_streams.json"), { cf: { cacheTtl: 120, cacheEverything: true } }).then((r) => r.json()),
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
      if (action === "get_live_categories") {
        // a group that follows today's names: Flo channels showing wrestling (owner, 28 Oct 2026)
        try {
          const r = await fetch(fresh(MAIN + "live_categories.json"), { cf: { cacheTtl: 120, cacheEverything: true } });
          const cats = r.ok ? await r.json() : [];
          // right after the Flo Sports PPV / FLSP / FloSports TV groups (owner, 28 Oct 2026), else after the last Flo group
          let i = -1;
          cats.forEach((c, k) => { if (DYN.near.test(c.category_name || "")) i = k; });
          if (i < 0) cats.forEach((c, k) => { if (DYN.from.test(c.category_name || "")) i = k; });
          if (i >= 0) cats.splice(i + 1, 0, { category_id: DYN.id, category_name: DYN.name, parent_id: 0 });
          return json(cats, 120);
        } catch (e) { return pass(MAIN + "live_categories.json", 900, []); }
      }
      if (action === "get_live_streams") {
        const cat = q.get("category_id");
        const dynCat = cat === DYN.id;
        const file = cat && !dynCat ? MAIN + `cat/${encodeURIComponent(cat)}.json` : MAIN + "live_streams.json";
        if (!LIVE_EVENT_NAMES) return pass(file, 900, []);
        // Event / PPV channels: the provider renames them for each match ("Hawks vs Rockets :NBA 06"); the repo's
        // copy is from the export day, so today's names come from the provider (see buildPatch).
        try {
          let pt = await readPatch(env);
          if (!pt || Date.now() - pt.t > PATCH_AGE) {
            const b = buildPatch(env, user, pass_, req.headers.get("User-Agent") || "");
            if (ctx) ctx.waitUntil(b);
            // no names yet in this worker instance: wait for them a little (Dream4k builds in under 2 s), so the
            // first open already shows today's games instead of only the next one (owner, 28 Oct 2026)
            if (!pt) { await Promise.race([b, new Promise((r) => setTimeout(r, 4000))]); pt = PATCH; }
          }
          if (!pt && !dynCat) return pass(file, 900, []);
          const [r, cr] = await Promise.all([fetch(fresh(file), { cf: { cacheTtl: 120, cacheEverything: true } }),
            fetch(fresh(MAIN + "live_categories.json"), { cf: { cacheTtl: 120, cacheEverything: true } })]);
          if (!r.ok) return json([], 60);
          let L = applyPatch(await r.json(), pt || { n: {}, i: {} }, dynCat ? null : cat);
          // Flo channels whose name today is a wrestling event go to the wrestling group
          const flo = new Set((cr.ok ? await cr.json() : []).filter((c) => DYN.from.test(c.category_name || "")).map((c) => String(c.category_id)));
          if (flo.size) for (const x of L) if (flo.has(String(x.category_id)) && DYN.match.test(String(x.name || ""))) x.category_id = DYN.id;
          if (cat) L = L.filter((x) => String(x.category_id) === String(cat));
          return json(L, 120);
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
      // Playlists whose provider refuses the relay (Dream4k, Strong): movies / series groups and lists already
      // arranged by GitHub (tools/vod_patch.py, branch live-patch), passed through as they are.
      if (GITHUB_LIVE.has(PLAYLIST) && /^get_(vod_categories|series_categories|vod_streams|series)$/.test(action)) {
        const kind = /vod/.test(action) ? "vod" : "series";
        const cat = q.get("category_id");
        const f = action.endsWith("categories") ? `${kind}_categories.json` : cat ? `${kind}/${encodeURIComponent(cat)}.json`
          : kind === "vod" ? "vod_streams.json" : "series.json";
        const r = await fetch(REPO + "live-patch/" + PLAYLIST + "/" + f + "?v=" + Math.floor(Date.now() / 120000), { cf: { cacheTtl: 120, cacheEverything: true } });
        if (r.ok) return new Response(r.body, { headers: { ...JSONH, "Cache-Control": "max-age=120" } });
        if (cat && r.status === 404) return json([], 60);  // a hidden group
      }
      // Movie / series groups: the provider's own list, put in the owner's order when the repo has one
      // (xtream/<playlist>/vod_order.json or series_order.json: names in order; groups not listed follow).
      if ((action === "get_vod_categories" || action === "get_series_categories") && !refused()) {
        try {
          const g = await groups(action, url, req);
          if (g) return json(g.cats, 300);
        } catch (e) { /* fall through to the provider */ }
      }
      // Movie / series lists and details: some providers (Argon, 28 Oct 2026) send raw UTF-8, which DreamTV reads
      // as Latin-1 ("AR - Ù…Ø³Ù„Ø³Ù„"); pass them through here with non-ASCII as \u escapes. ASCII answers are
      // passed unchanged. Titles of hidden groups are left out too: DreamTV otherwise shows them under bare
      // group numbers ("2588", "343"... Dream4k, 28 Oct 2026).
      if (/^get_(series|vod_streams|series_info|vod_info)$/.test(action) && !refused()) {
        try {
          const list = action === "get_series" || action === "get_vod_streams";
          const catAction = action === "get_series" ? "get_series_categories" : "get_vod_categories";
          const [r, g] = await Promise.all([
            fetch(`${PROVIDER}/player_api.php${url.search}`, { headers: { "User-Agent": req.headers.get("User-Agent") || "" } }),
            list ? groups(catAction, url, req).catch(() => null) : null,
          ]);
          note(r);
          if (r.ok) {
            let t = await r.text();
            // titles whose group the provider does not list (DreamTV shows them under "-1", Argon 28 Oct 2026) or the
            // owner hid are left out
            if (g && Array.isArray(g.cats) && (g.filtered || ORPHANS.has(PLAYLIST))) {
              const keep = new Set(g.cats.map((c) => String(c.category_id)));
              const cat = url.searchParams.get("category_id");
              if (cat) { if (!keep.has(String(cat))) t = "[]"; }
              else {
                const items = JSON.parse(t);
                if (Array.isArray(items)) t = JSON.stringify(items.filter((x) => keep.has(String(x.category_id))));
              }
            }
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
