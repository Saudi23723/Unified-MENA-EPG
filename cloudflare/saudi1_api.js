// SAUDI.1 accounts: the owner's admin page + the app's device activation (owner, 3 Nov 2026).
// The app shows a device code; the owner opens /admin, enters the code, picks the playlist and types the
// customer's login. The app's Reload then gets it. Logins are kept encrypted (AES-GCM, key = secret ENC_KEY).
// Bindings: D1 database DB, secret ENC_KEY (random, set once). The admin password is chosen by the owner on
// first open of /admin and stored only as a salted PBKDF2 hash.
const PLAYLISTS = {
  strong: "https://strong.1saifsaudi.workers.dev", dream4k: "https://dream4k.1saifsaudi.workers.dev",
  argon: "https://argon.1saifsaudi.workers.dev", hydra: "https://hydra.1saifsaudi.workers.dev",
  family4k: "https://family4k.1saifsaudi.workers.dev", aroma: "https://aroma.1saifsaudi.workers.dev",
  up1: "https://up1.1saifsaudi.workers.dev",
};
const J = { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store" };
const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: J });
const b64 = (u8) => btoa(String.fromCharCode(...new Uint8Array(u8)));
const ub64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

async function schema(db) {
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS devices (code TEXT PRIMARY KEY, created INTEGER, seen INTEGER, model TEXT, name TEXT, playlist TEXT, login TEXT, expires INTEGER, active INTEGER DEFAULT 1)"),
    db.prepare("CREATE TABLE IF NOT EXISTS admin (k TEXT PRIMARY KEY, v TEXT)"),
    db.prepare("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, until INTEGER)"),
    // more playlists on the same device (owner, 3 Nov 2026): the app's Playlists screen switches between them
    db.prepare("CREATE TABLE IF NOT EXISTS extras (code TEXT, playlist TEXT, login TEXT, PRIMARY KEY (code, playlist))"),
    // a WireGuard VPN for the device (owner, 3 Nov 2026), stored encrypted like the logins
    db.prepare("CREATE TABLE IF NOT EXISTS vpn (code TEXT PRIMARY KEY, conf TEXT)"),
    // what each device is watching (owner, 6 Nov 2026) and the viewer's own backup (favorites, continue watching...)
    db.prepare("CREATE TABLE IF NOT EXISTS now (code TEXT PRIMARY KEY, t INTEGER, playlist TEXT, kind TEXT, title TEXT)"),
    // where the device is (owner, 11 Nov 2026): country/city of its internet, and whether it comes through our VPN
    // the Oracle VPN server and its files are gone (owner, 11 Nov 2026): only a Proton file pasted for each device
    db.prepare("DROP TABLE IF EXISTS vpnpool"),
    db.prepare("CREATE TABLE IF NOT EXISTS place (code TEXT PRIMARY KEY, t INTEGER, country TEXT, city TEXT, vpn INTEGER)"),
    db.prepare("CREATE TABLE IF NOT EXISTS backup (code TEXT PRIMARY KEY, t INTEGER, data TEXT)"),
    // devices of one customer share favorites + continue watching (owner, 24 Nov 2026): one slice per customer name
    db.prepare("CREATE TABLE IF NOT EXISTS sync (name TEXT PRIMARY KEY, t INTEGER, h TEXT, data TEXT)"),
    // promo codes (owner, 9 Nov 2026): made on the admin page, each opens ONE device ONCE
    // the name on the welcome screen (owner, 11 Nov 2026): typed by the owner for each device
    db.prepare("CREATE TABLE IF NOT EXISTS welcome (code TEXT PRIMARY KEY, name TEXT)"),
    db.prepare("CREATE TABLE IF NOT EXISTS promo (code TEXT PRIMARY KEY, created INTEGER, note TEXT, used_by TEXT, used_at INTEGER)"),
    // the app's own health reports (owner, 13 Nov 2026: "make sure these errors never happen again"): when the app
    // stops by an error or its screen freezes, the device sends what happened, so it is seen and fixed the same day
    db.prepare("CREATE TABLE IF NOT EXISTS health (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, t INTEGER, kind TEXT, ver TEXT, info TEXT)"),
  ]);
}

async function key(env) {
  return crypto.subtle.importKey("raw", ub64(env.ENC_KEY), "AES-GCM", false, ["encrypt", "decrypt"]);
}
async function seal(env, obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await key(env), new TextEncoder().encode(JSON.stringify(obj)));
  return b64(iv) + "." + b64(ct);
}
async function open(env, s) {
  const [iv, ct] = s.split(".");
  return JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: ub64(iv) }, await key(env), ub64(ct))));
}
async function hash(pw, salt) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveBits"]);
  return b64(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: ub64(salt), iterations: 100000 }, k, 256));
}
const cookie = (req) => (req.headers.get("Cookie") || "").match(/s1=([A-Za-z0-9_-]+)/)?.[1] || "";

async function authed(env, req) {
  const t = cookie(req);
  if (!t) return false;
  const r = await env.DB.prepare("SELECT until FROM sessions WHERE token=?").bind(t).first();
  return !!r && r.until > Date.now();
}

// our own VPN server (Oracle, 11 Nov 2026): a device whose address is this one is on the VPN
async function place(env, req, code) {
  const cf = req.cf || {};
  // the app says whether its VPN is on (?vpn=1)
  const on = new URL(req.url).searchParams.get("vpn") === "1";
  try {
    await env.DB.prepare("INSERT OR REPLACE INTO place (code, t, country, city, vpn) VALUES (?,?,?,?,?)")
      .bind(code, Date.now(), String(cf.country || ""), String(cf.city || "").slice(0, 60), on ? 1 : 0).run();
  } catch (e) {}
}
export default {
  async fetch(req, env) {
    const url = new URL(req.url), p = url.pathname;
    if (req.method === "OPTIONS") return new Response(null, { headers: J });
    await schema(env.DB);

    // ---- the app ----
    // GET /api/device?code=12345678&model=Chromecast  -> {status:"pending"} | {status:"active", server, user, pass, name, expires}
    if (p === "/api/device") {
      const code = (url.searchParams.get("code") || "").replace(/\D/g, "");
      if (code.length !== 8) return json({ status: "bad code" }, 400);
      const now = Date.now();
      if (await env.DB.prepare("SELECT code FROM devices WHERE code=?").bind(code).first()) await place(env, req, code);
      const d = await env.DB.prepare("SELECT * FROM devices WHERE code=?").bind(code).first();
      if (!d) {
        await env.DB.prepare("INSERT INTO devices (code, created, seen, model, active) VALUES (?,?,?,?,1)")
          .bind(code, now, now, (url.searchParams.get("model") || "").slice(0, 60)).run();
        return json({ status: "pending" });
      }
      await env.DB.prepare("UPDATE devices SET seen=? WHERE code=?").bind(now, code).run();
      if (!d.active) return json({ status: "stopped" });
      if (d.expires && d.expires < now) return json({ status: "expired", expires: d.expires });
      if (!d.login || !d.playlist) return json({ status: "pending" });
      const l = await open(env, d.login);
      const lists = [{ name: d.playlist, server: PLAYLISTS[d.playlist] || d.playlist, user: l.user, pass: l.pass }];
      const ex = await env.DB.prepare("SELECT playlist, login FROM extras WHERE code=?").bind(code).all();
      for (const e of ex.results || []) {
        try { const x = await open(env, e.login); lists.push({ name: e.playlist, server: PLAYLISTS[e.playlist] || e.playlist, user: x.user, pass: x.pass }); } catch (err) {}
      }
      let vpn = "";
      const v = await env.DB.prepare("SELECT conf FROM vpn WHERE code=?").bind(code).first();
      if (v) { try { vpn = (await open(env, v.conf)).conf || ""; } catch (err) {} }
      const wr = await env.DB.prepare("SELECT name FROM welcome WHERE code=?").bind(code).first();
      return json({ status: "active", server: lists[0].server, user: l.user, pass: l.pass, name: d.name || "", welcome: (wr && wr.name) || "", expires: d.expires || 0, playlists: lists, vpn,
        // the time zone of where the device is now (from its internet): the guide and the matches follow a traveller (owner, 11 Nov 2026)
        // (none while the device's VPN is on: that is the VPN's country, not where the device is)
        tz: url.searchParams.get("vpn") === "1" ? "" : ((req.cf && req.cf.timezone) || "") });
    }

    // POST /api/now {code, playlist, kind, title}: the app says what is playing (every 100 s while it plays)
    if (p === "/api/now" && req.method === "POST") {
      const b = await req.json().catch(() => ({}));
      const code = String(b.code || "").replace(/\D/g, "");
      if (code.length !== 8) return json({ error: "bad code" }, 400);
      const d = await env.DB.prepare("SELECT code FROM devices WHERE code=?").bind(code).first();
      if (!d) return json({ error: "unknown device" }, 404);
      const now = Date.now();
      await env.DB.batch([
        env.DB.prepare("INSERT OR REPLACE INTO now (code, t, playlist, kind, title) VALUES (?,?,?,?,?)")
          .bind(code, now, String(b.playlist || "").slice(0, 40), String(b.kind || "").slice(0, 16), String(b.title || "").slice(0, 160)),
        env.DB.prepare("UPDATE devices SET seen=? WHERE code=?").bind(now, code),
      ]);
      await place(env, req, code);
      return json({ ok: true });
    }
    // POST /api/health {code, kind: crash|freeze, ver, info}: the app reports an error or a frozen screen
    if (p === "/api/health" && req.method === "POST") {
      const b = await req.json().catch(() => ({}));
      const code = String(b.code || "").replace(/\D/g, "");
      if (code.length !== 8) return json({ error: "bad code" }, 400);
      const d = await env.DB.prepare("SELECT code FROM devices WHERE code=?").bind(code).first();
      if (!d) return json({ error: "unknown device" }, 404);
      const now = Date.now();
      const n = await env.DB.prepare("SELECT COUNT(*) AS n FROM health WHERE code=? AND t>?").bind(code, now - 86400000).first();
      if ((n && n.n) >= 30) return json({ ok: true, kept: false });   // a device in a loop does not fill the table
      const kind = String(b.kind || "") === "freeze" ? "freeze" : "crash";
      await env.DB.batch([
        env.DB.prepare("INSERT INTO health (code, t, kind, ver, info) VALUES (?,?,?,?,?)")
          .bind(code, now, kind, String(b.ver || "").slice(0, 20), String(b.info || "").slice(0, 6000)),
        env.DB.prepare("DELETE FROM health WHERE id NOT IN (SELECT id FROM health ORDER BY id DESC LIMIT 500)"),
      ]);
      return json({ ok: true });
    }
    // POST /api/promo {code: device code, promo}: a promo code is spent on this device (once, one device)
    if (p === "/api/promo" && req.method === "POST") {
      const b = await req.json().catch(() => ({}));
      const code = String(b.code || "").replace(/\D/g, "");
      const promo = String(b.promo || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
      if (code.length !== 8 || promo.length !== 8) return json({ error: "The promo code has 8 letters and numbers" }, 400);
      await new Promise((r) => setTimeout(r, 800));   // slow guessing down
      const pr = await env.DB.prepare("SELECT code, used_by FROM promo WHERE code=?").bind(promo).first();
      if (!pr) return json({ error: "This promo code is not valid" }, 404);
      if (pr.used_by && pr.used_by !== code) return json({ error: "This promo code was already used" }, 409);
      const now = Date.now();
      const d = await env.DB.prepare("SELECT code FROM devices WHERE code=?").bind(code).first();
      if (!d) await env.DB.prepare("INSERT INTO devices (code, created, seen, model, active) VALUES (?,?,?,?,1)").bind(code, now, now, "").run();
      // spent only if still free (two devices at the same moment: one wins)
      const u = await env.DB.prepare("UPDATE promo SET used_by=?, used_at=? WHERE code=? AND (used_by IS NULL OR used_by=?)").bind(code, now, promo, code).run();
      if (!u.meta || !u.meta.changes) return json({ error: "This promo code was already used" }, 409);
      return json({ ok: true });
    }
    // the viewer's backup, kept under the device code: POST {code, data} saves, GET ?code= gives it back
    if (p === "/api/backup") {
      if (req.method === "POST") {
        const b = await req.json().catch(() => ({}));
        const code = String(b.code || "").replace(/\D/g, "");
        const data = String(b.data || "");
        if (code.length !== 8 || !data || data.length > 400000) return json({ error: "bad backup" }, 400);
        const d = await env.DB.prepare("SELECT code FROM devices WHERE code=?").bind(code).first();
        if (!d) return json({ error: "unknown device" }, 404);
        await env.DB.prepare("INSERT OR REPLACE INTO backup (code, t, data) VALUES (?,?,?)").bind(code, Date.now(), data).run();
        return json({ ok: true });
      }
      const code = (url.searchParams.get("code") || "").replace(/\D/g, "");
      const r = await env.DB.prepare("SELECT t, data FROM backup WHERE code=?").bind(code).first();
      return r ? json({ t: r.t, data: r.data }) : json({ error: "no backup" }, 404);
    }

    // cloud sync per customer: the devices that carry the same customer name (set by the owner) see the same favorites
    // and continue-watching. POST {code, data, h} stores the slice, GET ?code=&h= gives it only when it differs from h
    if (p === "/api/sync") {
      const code = String((req.method === "POST" ? (await req.clone().json().catch(() => ({}))).code : url.searchParams.get("code")) || "").replace(/\D/g, "");
      const d = code.length === 8 ? await env.DB.prepare("SELECT name FROM devices WHERE code=?").bind(code).first() : null;
      const nm = d && String(d.name || "").trim().toLowerCase();
      if (!nm) return json({ error: "no customer" }, 404);
      if (req.method === "POST") {
        const b = await req.json().catch(() => ({}));
        const data = String(b.data || "");
        if (!data || data.length > 300000) return json({ error: "bad data" }, 400);
        await env.DB.prepare("INSERT OR REPLACE INTO sync (name, t, h, data) VALUES (?,?,?,?)").bind(nm, Date.now(), String(b.h || ""), data).run();
        return json({ ok: true });
      }
      const r = await env.DB.prepare("SELECT t, h, data FROM sync WHERE name=?").bind(nm).first();
      if (!r) return json({ none: true });
      if (r.h && r.h === (url.searchParams.get("h") || "")) return json({ same: true });
      return json({ t: r.t, h: r.h, data: r.data });
    }

    // ---- paying for access (owner, 10 Nov 2026): someone outside the owner's circle pays through the owner's own
    // Stripe Payment Link; the paid device is marked for the owner, who then finishes the activation as always.
    const adminV = async (k) => (await env.DB.prepare("SELECT v FROM admin WHERE k=?").bind(k).first())?.v || "";
    const html = (body) => new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SAUDI.TV</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#070a12;color:#fff;font-family:system-ui,sans-serif}main{max-width:420px;padding:32px 24px;text-align:center}
h1{letter-spacing:.2em;font-size:22px}h1 b{color:#10b981}p{color:#b6bfd0;line-height:1.7}.price{font-size:44px;font-weight:800;margin:18px 0}.code{font:700 22px ui-monospace,monospace;letter-spacing:.12em;color:#10b981}
a.btn{display:block;margin-top:22px;background:#10b981;color:#04130d;font-weight:800;font-size:19px;padding:16px;border-radius:14px;text-decoration:none}</style></head><body><main><h1>SAUDI<b>.TV</b></h1>${body}</main></body></html>`,
      { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
    const safe = (t) => String(t).replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
    if (p === "/api/pay") {
      const on = (await adminV("pay_on")) === "1" && !!(await adminV("pay_link"));
      const pr = String(await adminV("pay_price")).replace(/[^0-9.]/g, "");
      return json({ on, price: on && pr ? "$" + pr : "", url: on ? url.origin + "/buy?d=" + (url.searchParams.get("code") || "").replace(/\D/g, "") : "" });
    }
    if (p === "/buy") {
      const d = (url.searchParams.get("d") || "").replace(/\D/g, "");
      const link = await adminV("pay_link");
      if ((await adminV("pay_on")) !== "1" || !link || d.length !== 8) return html("<p>This page is not available.</p>");
      // Venmo (owner, 10 Nov 2026): the amount and the device code are filled in; the owner activates on seeing the payment
      const price = String(await adminV("pay_price")).replace(/[^0-9.]/g, "");
      const note = "SAUDI.TV device " + d.slice(0, 4) + " " + d.slice(4);
      const go = /^https?:\/\//i.test(link) ? link
        : "https://venmo.com/" + encodeURIComponent(link.replace(/^@/, "")) + "?txn=pay" + (price ? "&amount=" + price : "") + "&note=" + encodeURIComponent(note);
      return html(`<p>Access for the device</p><div class="code">${d.slice(0, 4)} ${d.slice(4)}</div><div class="price">${price ? "$" + safe(price) : ""}</div>
<p>One payment with Venmo. Keep the note as it is (it has your device code): your device is activated as soon as the payment is seen.</p><a class="btn" href="${safe(go)}">Pay with Venmo</a>`);
    }
    if (p === "/paid") {
      const sid = url.searchParams.get("session_id") || "";
      if (!env.STRIPE_KEY || !/^cs_[A-Za-z0-9_]+$/.test(sid)) return html("<p>This page is not available.</p>");
      const r = await fetch("https://api.stripe.com/v1/checkout/sessions/" + sid, { headers: { Authorization: "Bearer " + env.STRIPE_KEY } });
      const sx = r.ok ? await r.json() : {};
      const d = String(sx.client_reference_id || "").replace(/\D/g, "");
      if (sx.payment_status !== "paid" || d.length !== 8) return html("<p>The payment is not complete yet. If you paid, wait a minute and open this page again.</p>");
      const now = Date.now();
      // one mark per payment (opening the page twice changes nothing)
      const had = await env.DB.prepare("SELECT code FROM promo WHERE note=?").bind("stripe " + sid).first();
      if (!had) {
        const dev = await env.DB.prepare("SELECT code FROM devices WHERE code=?").bind(d).first();
        if (!dev) await env.DB.prepare("INSERT INTO devices (code, created, seen, model, active) VALUES (?,?,?,?,1)").bind(d, now, now, "").run();
        const A = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        const c = "PAID" + Array.from(crypto.getRandomValues(new Uint8Array(4)), (x) => A[x % A.length]).join("");
        await env.DB.prepare("INSERT INTO promo (code, created, note, used_by, used_at) VALUES (?,?,?,?,?)").bind(c, now, "stripe " + sid, d, now).run();
      }
      return html(`<p style="font-size:54px;margin:0">✓</p><p>Payment received. Thank you.</p><div class="code">${d.slice(0, 4)} ${d.slice(4)}</div><p>Your device will be activated shortly — keep SAUDI.TV open, it starts by itself.</p>`);
    }

    // short link for Downloader: saudi1.1saifsaudi.workers.dev/apk
    // the iPhone / iPad app (owner, 18 Nov 2026): a web app at /tv, its files read from the repo's ios/ folder, so a
    // change to the app needs no new paste of this worker. Open https://saudi1.1saifsaudi.workers.dev/tv on the phone.
    if (p === "/tv") return Response.redirect(url.origin + "/tv/", 301);
    if (p.startsWith("/tv/")) {
      const f = p.slice(4) || "index.html";
      const types = { html: "text/html; charset=utf-8", json: "application/manifest+json", png: "image/png", js: "text/javascript" };
      const ext = f.split(".").pop();
      if (!/^[a-z0-9_-]+\.[a-z0-9]+$/.test(f) || !types[ext]) return new Response("not found", { status: 404 });
      const r = await fetch("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/ios/" + f, { cf: { cacheTtl: 120, cacheEverything: true } });
      if (!r.ok) return new Response("not found", { status: 404 });
      return new Response(r.body, { headers: { "Content-Type": types[ext], "Cache-Control": "public, max-age=120" } });
    }
    // the page sent to customers: how to install on a TV, an Android phone / tablet and an iPhone (owner, 21 Nov 2026)
    if (p === "/get" || p === "/get/" || p === "/download") {
      const r = await fetch("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/ios/get.html", { cf: { cacheTtl: 120, cacheEverything: true } });
      if (!r.ok) return Response.redirect(url.origin + "/apk", 302);
      return new Response(r.body, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=120" } });
    }
    if (p === "/apk" || p === "/apk/") return Response.redirect("https://github.com/Saudi23723/Unified-MENA-EPG/releases/download/saudi1/SAUDI1.apk", 302);

    // ---- the owner's admin page ----
    if (p === "/" || p === "/admin") return new Response(PAGE, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });

    if (p === "/admin/api/state") {
      const set = await env.DB.prepare("SELECT v FROM admin WHERE k='hash'").first();
      return json({ setup: !set, signed: await authed(env, req), playlists: Object.keys(PLAYLISTS) });
    }
    if (p === "/admin/api/login" && req.method === "POST") {
      const { password, setup } = await req.json();
      if (!password || password.length < 8) return json({ error: "The password needs at least 8 characters" }, 400);
      const h = await env.DB.prepare("SELECT v FROM admin WHERE k='hash'").first();
      const s = await env.DB.prepare("SELECT v FROM admin WHERE k='salt'").first();
      if (!h) {  // first open: the owner chooses the password (only with the one-time setup link)
        if (!env.SETUP_KEY || setup !== env.SETUP_KEY) return json({ error: "Use the setup link" }, 403);
        const salt = b64(crypto.getRandomValues(new Uint8Array(16)));
        await env.DB.batch([
          env.DB.prepare("INSERT INTO admin (k,v) VALUES ('salt',?)").bind(salt),
          env.DB.prepare("INSERT INTO admin (k,v) VALUES ('hash',?)").bind(await hash(password, salt)),
        ]);
      } else if ((await hash(password, s.v)) !== h.v) {
        await new Promise((r) => setTimeout(r, 1500));
        return json({ error: "Wrong password" }, 401);
      }
      const token = b64(crypto.getRandomValues(new Uint8Array(24))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
      await env.DB.prepare("INSERT INTO sessions (token, until) VALUES (?,?)").bind(token, Date.now() + 30 * 86400000).run();
      return new Response(JSON.stringify({ ok: true }), { headers: { ...J,
        "Set-Cookie": `s1=${token}; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Strict` } });
    }
    if (p.startsWith("/admin/api/")) {
      if (!(await authed(env, req))) return json({ error: "Sign in" }, 401);
      // the last health reports of all devices, newest first, with the device's name
      if (p === "/admin/api/health") {
        const r = await env.DB.prepare("SELECT h.id, h.code, h.t, h.kind, h.ver, h.info, d.name FROM health h LEFT JOIN devices d ON d.code=h.code ORDER BY h.id DESC LIMIT 100").all();
        return json({ health: r.results || [] });
      }
      if (p === "/admin/api/health/clear" && req.method === "POST") {
        await env.DB.prepare("DELETE FROM health").run();
        return json({ ok: true });
      }
      if (p === "/admin/api/devices") {
        const r = await env.DB.prepare("SELECT code, created, seen, model, name, playlist, expires, active, login IS NOT NULL AS has_login FROM devices ORDER BY seen DESC").all();
        const ex = await env.DB.prepare("SELECT code, playlist FROM extras").all();
        const by = {};
        for (const e of ex.results || []) (by[e.code] = by[e.code] || []).push(e.playlist);
        const vp = await env.DB.prepare("SELECT code FROM vpn").all();
        const hv = new Set((vp.results || []).map((x) => x.code));
        const prs = await env.DB.prepare("SELECT code, used_by FROM promo WHERE used_by IS NOT NULL").all();
        const pb = {};
        for (const x of prs.results || []) pb[x.used_by] = x.code;
        const pl = await env.DB.prepare("SELECT code, t, country, city, vpn FROM place").all();
        const wb = {};
        for (const x of pl.results || []) wb[x.code] = x;
        const wl = await env.DB.prepare("SELECT code, name FROM welcome").all();
        const wn = {};
        for (const x of wl.results || []) wn[x.code] = x.name;
        const nw = await env.DB.prepare("SELECT code, t, playlist, kind, title FROM now").all();
        const nb = {};
        for (const n of nw.results || []) nb[n.code] = n;
        return json({ devices: (r.results || []).map((d) => ({ ...d, extras: by[d.code] || [], has_vpn: hv.has(d.code), promo: pb[d.code] || "",
          now_t: nb[d.code]?.t || 0, now_playlist: nb[d.code]?.playlist || "", now_kind: nb[d.code]?.kind || "", now_title: nb[d.code]?.title || "",
          welcome: wn[d.code] || "", country: wb[d.code]?.country || "", city: wb[d.code]?.city || "", on_vpn: !!wb[d.code]?.vpn, place_t: wb[d.code]?.t || 0 })) });
      }
      if (p === "/admin/api/pay") {
        if (req.method === "POST") {
          const b = await req.json();
          const link = String(b.link || "").trim();
          if (link && !/^https:\/\/[a-z0-9.-]+\//i.test(link) && !/^@?[A-Za-z0-9_-]{3,40}$/.test(link)) return json({ error: "اكتب اسم المستخدم على Venmo بس (حروف وأرقام و - و _)" }, 400);
          await env.DB.batch([
            env.DB.prepare("INSERT OR REPLACE INTO admin (k,v) VALUES ('pay_price',?)").bind(String(b.price || "").slice(0, 30)),
            env.DB.prepare("INSERT OR REPLACE INTO admin (k,v) VALUES ('pay_link',?)").bind(link.slice(0, 300)),
            env.DB.prepare("INSERT OR REPLACE INTO admin (k,v) VALUES ('pay_on',?)").bind(b.on ? "1" : "0"),
          ]);
          return json({ ok: true });
        }
        return json({ price: await adminV("pay_price"), link: await adminV("pay_link"), on: (await adminV("pay_on")) === "1", has_key: !!env.STRIPE_KEY });
      }
      if (p === "/admin/api/promos") {
        const r = await env.DB.prepare("SELECT code, created, note, used_by, used_at FROM promo ORDER BY created DESC").all();
        return json({ promos: r.results || [] });
      }
      if (p === "/admin/api/promo" && req.method === "POST") {
        const b = await req.json();
        const n = Math.max(1, Math.min(20, Number(b.n) || 1));
        const A = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";   // no 0/O, 1/I: read out loud without mistakes
        const codes = [];
        for (let i = 0; i < n; i++) {
          const r = crypto.getRandomValues(new Uint8Array(8));
          const c = Array.from(r, (x) => A[x % A.length]).join("");
          await env.DB.prepare("INSERT OR IGNORE INTO promo (code, created, note) VALUES (?,?,?)").bind(c, Date.now() + i, String(b.note || "").slice(0, 60)).run();
          codes.push(c);
        }
        return json({ ok: true, codes });
      }
      if (p === "/admin/api/promo_delete" && req.method === "POST") {
        const { code } = await req.json();
        await env.DB.prepare("DELETE FROM promo WHERE code=?").bind(String(code)).run();
        return json({ ok: true });
      }
      if (p === "/admin/api/vpn" && req.method === "POST") {
        const b = await req.json();
        const code = String(b.code || "").replace(/\D/g, "");
        const conf = String(b.conf || "").trim();
        if (!conf) { await env.DB.prepare("DELETE FROM vpn WHERE code=?").bind(code).run(); return json({ ok: true }); }
        if (!/\[Interface\]/i.test(conf) || !/\[Peer\]/i.test(conf) || !/PrivateKey\s*=/i.test(conf)) return json({ error: "هذا مش ملف WireGuard (.conf) — من Proton: Downloads ← WireGuard configuration" }, 400);
        await env.DB.prepare("INSERT OR REPLACE INTO vpn (code, conf) VALUES (?,?)").bind(code, await seal(env, { conf })).run();
        return json({ ok: true });
      }
      if (p === "/admin/api/extra" && req.method === "POST") {
        const b = await req.json();
        const code = String(b.code || "").replace(/\D/g, "");
        if (!PLAYLISTS[b.playlist]) return json({ error: "Unknown playlist" }, 400);
        if (b.remove) { await env.DB.prepare("DELETE FROM extras WHERE code=? AND playlist=?").bind(code, b.playlist).run(); return json({ ok: true }); }
        if (!b.user || !b.pass) return json({ error: "اكتب اليوزر والباسوورد" }, 400);
        const d = await env.DB.prepare("SELECT code FROM devices WHERE code=?").bind(code).first();
        if (!d) return json({ error: "احفظ الجهاز أول" }, 400);
        await env.DB.prepare("INSERT OR REPLACE INTO extras (code, playlist, login) VALUES (?,?,?)")
          .bind(code, b.playlist, await seal(env, { user: String(b.user).trim(), pass: String(b.pass).trim() })).run();
        return json({ ok: true });
      }
      if (p === "/admin/api/save" && req.method === "POST") {
        const b = await req.json();
        const code = String(b.code || "").replace(/\D/g, "");
        if (code.length !== 8) return json({ error: "The device code has 8 digits" }, 400);
        if (b.playlist && !PLAYLISTS[b.playlist]) return json({ error: "Unknown playlist" }, 400);
        const d = await env.DB.prepare("SELECT code, login FROM devices WHERE code=?").bind(code).first();
        const login = b.user && b.pass ? await seal(env, { user: String(b.user).trim(), pass: String(b.pass).trim() }) : d?.login || null;
        const expires = b.expires ? Date.parse(b.expires + "T23:59:59Z") || 0 : 0;
        if (!d) await env.DB.prepare("INSERT INTO devices (code, created, seen, name, playlist, login, expires, active) VALUES (?,?,?,?,?,?,?,1)")
          .bind(code, Date.now(), 0, b.name || "", b.playlist || "", login, expires).run();
        else await env.DB.prepare("UPDATE devices SET name=?, playlist=?, login=?, expires=?, active=? WHERE code=?")
          .bind(b.name || "", b.playlist || "", login, expires, b.active === false ? 0 : 1, code).run();
        if (b.welcome !== undefined) {
          const w = String(b.welcome || "").trim().slice(0, 30);
          if (w) await env.DB.prepare("INSERT OR REPLACE INTO welcome (code, name) VALUES (?,?)").bind(code, w).run();
          else await env.DB.prepare("DELETE FROM welcome WHERE code=?").bind(code).run();
        }
        return json({ ok: true });
      }
      // a device that got a new code (the app was removed and put back): its customer, playlists, VPN, settings
      // backup and history move to the new code (owner, 22 Nov 2026)
      if (p === "/admin/api/recode" && req.method === "POST") {
        const b = await req.json();
        const from = String(b.from || "").replace(/\D/g, ""), to = String(b.to || "").replace(/\D/g, "");
        if (from.length !== 8 || to.length !== 8 || from === to) return json({ error: "كود الجهاز 8 أرقام" }, 400);
        const old = await env.DB.prepare("SELECT code FROM devices WHERE code=?").bind(from).first();
        if (!old) return json({ error: "الجهاز القديم مش موجود" }, 400);
        const taken = await env.DB.prepare("SELECT login FROM devices WHERE code=?").bind(to).first();
        if (taken && taken.login) return json({ error: "الكود الجديد مفعّل على جهاز ثاني" }, 400);
        const tables = ["devices", "extras", "vpn", "now", "place", "backup", "welcome", "health"];
        const st = [];
        for (const t of tables) if (t !== "health") st.push(env.DB.prepare(`DELETE FROM ${t} WHERE code=?`).bind(to));
        for (const t of tables) st.push(env.DB.prepare(`UPDATE ${t} SET code=? WHERE code=?`).bind(to, from));
        await env.DB.batch(st);
        return json({ ok: true });
      }
      if (p === "/admin/api/delete" && req.method === "POST") {
        const { code } = await req.json();
        await env.DB.prepare("DELETE FROM devices WHERE code=?").bind(String(code)).run();
        await env.DB.prepare("DELETE FROM extras WHERE code=?").bind(String(code)).run();
        await env.DB.prepare("DELETE FROM vpn WHERE code=?").bind(String(code)).run();
        await env.DB.prepare("DELETE FROM now WHERE code=?").bind(String(code)).run();
        await env.DB.prepare("DELETE FROM backup WHERE code=?").bind(String(code)).run();
        await env.DB.prepare("DELETE FROM welcome WHERE code=?").bind(String(code)).run();
        return json({ ok: true });
      }
      if (p === "/admin/api/logout" && req.method === "POST") {
        await env.DB.prepare("DELETE FROM sessions WHERE token=?").bind(cookie(req)).run();
        return json({ ok: true });
      }
    }
    return json({ error: "not found" }, 404);
  },
};

// the admin page (scratch source: admin.html), stored as base64 so the upload is plain code
const PAGE = new TextDecoder().decode(Uint8Array.from(atob("PCFkb2N0eXBlIGh0bWw+PGh0bWwgbGFuZz0iYXIiIGRpcj0icnRsIj48aGVhZD48bWV0YSBjaGFyc2V0PSJ1dGYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEiPgo8dGl0bGU+U0FVREkuVFYgwrcg2YTZiNit2Kkg2KfZhNil2K/Yp9ix2Kk8L3RpdGxlPgo8c3R5bGU+Cjpyb290ey0tYmc6IzA5MGMxMjstLXA6IzEyMTcyMjstLXAyOiMxOTIwMmU7LS1wMzojMjIyYjNkOy0tbGluZTojMjMyYzNlOy0tdDojZjJmNGY4Oy0tdDI6IzlhYTNiNTstLXQzOiM2Yjc0ODg7LS1hOiMwMGQ2OGY7LS1hMjojMDBiMzc3Oy0tcjojZmY0ZDVlOy0teTojZmZiMDIwOy0tYjojNGRhM2ZmOy0tc2g6MCAxMHB4IDMwcHggcmdiYSgwLDAsMCwuMzUpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveH1odG1sLGJvZHl7aGVpZ2h0OjEwMCV9CmJvZHl7bWFyZ2luOjA7YmFja2dyb3VuZDpyYWRpYWwtZ3JhZGllbnQoMTIwMHB4IDYwMHB4IGF0IDEwMCUgLTEwJSwjMGYyYTIwIDAsdHJhbnNwYXJlbnQgNjAlKSx2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdCk7Zm9udDoxNXB4LzEuNTUgc3lzdGVtLXVpLC1hcHBsZS1zeXN0ZW0sIlNlZ29lIFVJIixUYWhvbWEsc2Fucy1zZXJpZn0KYXtjb2xvcjppbmhlcml0fS5oaWRle2Rpc3BsYXk6bm9uZSFpbXBvcnRhbnR9Lm11dGVke2NvbG9yOnZhcigtLXQyKX0uY29kZXtmb250LWZhbWlseTp1aS1tb25vc3BhY2UsTWVubG8sbW9ub3NwYWNlO2xldHRlci1zcGFjaW5nOjEuNXB4O2RpcmVjdGlvbjpsdHI7ZGlzcGxheTppbmxpbmUtYmxvY2s7d2hpdGUtc3BhY2U6bm93cmFwfQouc2hlbGx7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyNDBweCAxZnI7bWluLWhlaWdodDoxMDB2aH0KYXNpZGV7YmFja2dyb3VuZDpyZ2JhKDE4LDIzLDM0LC44NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMTBweCk7Ym9yZGVyLWxlZnQ6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6MjJweCAxNHB4O3Bvc2l0aW9uOnN0aWNreTt0b3A6MDtoZWlnaHQ6MTAwdmg7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4fQouYnJhbmR7Zm9udC1zaXplOjI0cHg7Zm9udC13ZWlnaHQ6ODAwO2xldHRlci1zcGFjaW5nOi41cHg7cGFkZGluZzo0cHggMTBweCAxOHB4O2RpcmVjdGlvbjpsdHI7dGV4dC1hbGlnbjpyaWdodH0uYnJhbmQgYntjb2xvcjp2YXIoLS1hKX0KLm5hdntkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4O3BhZGRpbmc6MTFweCAxMnB4O2JvcmRlci1yYWRpdXM6MTJweDtjb2xvcjp2YXIoLS10Mik7Y3Vyc29yOnBvaW50ZXI7Zm9udC13ZWlnaHQ6NjAwO2JvcmRlcjowO2JhY2tncm91bmQ6bm9uZTt3aWR0aDoxMDAlO3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjE1cHh9Ci5uYXY6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCl9Lm5hdi5vbntiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx0cmFuc3BhcmVudCxyZ2JhKDAsMjE0LDE0MywuMTYpKTtjb2xvcjp2YXIoLS10KTtib3gtc2hhZG93Omluc2V0IC0zcHggMCAwIHZhcigtLWEpfQoubmF2IC5pY3t3aWR0aDoyMnB4O3RleHQtYWxpZ246Y2VudGVyfS5zcGFjZXJ7ZmxleDoxfQptYWlue3BhZGRpbmc6MjZweCAzMHB4IDYwcHg7bWF4LXdpZHRoOjEyNDBweDt3aWR0aDoxMDAlfQoudG9we2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjE0cHg7bWFyZ2luLWJvdHRvbToyMnB4O2ZsZXgtd3JhcDp3cmFwfQpoMXttYXJnaW46MDtmb250LXNpemU6MjZweH1oMnttYXJnaW46MCAwIDRweDtmb250LXNpemU6MThweH0uc3Vie2NvbG9yOnZhcigtLXQyKTttYXJnaW46MnB4IDAgMH0KLmJ0bntiYWNrZ3JvdW5kOnZhcigtLWEpO2NvbG9yOiMwMzE0MGM7Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czoxMXB4O3BhZGRpbmc6MTFweCAxOHB4O2ZvbnQtd2VpZ2h0OjgwMDtmb250LXNpemU6MTQuNXB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo4cHg7dHJhbnNpdGlvbjouMTVzfQouYnRuOmhvdmVye2JhY2tncm91bmQ6dmFyKC0tYTIpfS5idG4uZ2hvc3R7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKX0uYnRuLmdob3N0OmhvdmVye2JhY2tncm91bmQ6dmFyKC0tcDMpfQouYnRuLnJlZHtiYWNrZ3JvdW5kOnJnYmEoMjU1LDc3LDk0LC4xNCk7Y29sb3I6dmFyKC0tcik7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDI1NSw3Nyw5NCwuMzUpfS5idG4uc217cGFkZGluZzo3cHggMTJweDtmb250LXNpemU6MTNweDtib3JkZXItcmFkaXVzOjlweH0KLnN0YXRze2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KGF1dG8tZml0LG1pbm1heCgxMzhweCwxZnIpKTtnYXA6MTRweDttYXJnaW4tYm90dG9tOjIycHh9Ci5zdGF0e2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDE4MGRlZyx2YXIoLS1wMiksdmFyKC0tcCkpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNnB4O3BhZGRpbmc6MTZweCAxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpO2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246LjE1c30KLnN0YXQ6aG92ZXJ7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoLTJweCk7Ym9yZGVyLWNvbG9yOiMyZjNhNTJ9Ci5zdGF0IC5ue2ZvbnQtc2l6ZTozMHB4O2ZvbnQtd2VpZ2h0OjgwMDttYXJnaW4tdG9wOjRweH0uc3RhdCAubHtjb2xvcjp2YXIoLS10Mik7Zm9udC1zaXplOjEzcHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6N3B4fQouZG90e3dpZHRoOjlweDtoZWlnaHQ6OXB4O2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrfQouY2FyZHtiYWNrZ3JvdW5kOnZhcigtLXApO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpfQouY2FyZC1oe2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjEycHg7cGFkZGluZzoxNnB4IDE4cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7ZmxleC13cmFwOndyYXB9Ci50b29sc3tkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5zZWFyY2h7YmFja2dyb3VuZDp2YXIoLS1wMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjExcHg7cGFkZGluZzo5cHggMTJweDtjb2xvcjp2YXIoLS10KTttaW4td2lkdGg6MjQwcHg7Zm9udC1zaXplOjE0cHh9Ci5jaGlwe2JhY2tncm91bmQ6dmFyKC0tcDIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Y29sb3I6dmFyKC0tdDIpO2JvcmRlci1yYWRpdXM6OTlweDtwYWRkaW5nOjZweCAxM3B4O2ZvbnQtc2l6ZToxM3B4O2N1cnNvcjpwb2ludGVyO2ZvbnQtd2VpZ2h0OjYwMH0KLmNoaXAub257YmFja2dyb3VuZDpyZ2JhKDAsMjE0LDE0MywuMTQpO2JvcmRlci1jb2xvcjpyZ2JhKDAsMjE0LDE0MywuNSk7Y29sb3I6dmFyKC0tYSl9Ci53cmFwe292ZXJmbG93LXg6YXV0b310YWJsZXt3aWR0aDoxMDAlO2JvcmRlci1jb2xsYXBzZTpjb2xsYXBzZX0KdGgsdGR7dGV4dC1hbGlnbjpyaWdodDtwYWRkaW5nOjEycHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1saW5lKTtmb250LXNpemU6MTRweDt2ZXJ0aWNhbC1hbGlnbjptaWRkbGV9CnRoe2NvbG9yOnZhcigtLXQzKTtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHh9CnRib2R5IHRye3RyYW5zaXRpb246LjEycztjdXJzb3I6cG9pbnRlcn10Ym9keSB0cjpob3ZlcntiYWNrZ3JvdW5kOnJnYmEoMjU1LDI1NSwyNTUsLjAyNSl9Ci53aG8gYntkaXNwbGF5OmJsb2NrfS53aG8gc21hbGx7Y29sb3I6dmFyKC0tdDMpfQoudGFne2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo2cHg7cGFkZGluZzozcHggMTBweDtib3JkZXItcmFkaXVzOjk5cHg7Zm9udC1zaXplOjEycHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7bWFyZ2luOjJweCAwIDJweCA0cHg7Zm9udC13ZWlnaHQ6NjAwfQouc3R7ZGlzcGxheTppbmxpbmUtZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjdweDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEzcHh9Ci5zLW9ue2NvbG9yOnZhcigtLWEpfS5zLXdhaXR7Y29sb3I6dmFyKC0tYil9LnMtZXhwe2NvbG9yOnZhcigtLXIpfS5zLW9mZntjb2xvcjp2YXIoLS10Myl9LnMtc29vbntjb2xvcjp2YXIoLS15KX0KLm9ubGluZXt3aWR0aDo4cHg7aGVpZ2h0OjhweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZhcigtLWEpO2JveC1zaGFkb3c6MCAwIDAgNHB4IHJnYmEoMCwyMTQsMTQzLC4xOCk7ZGlzcGxheTppbmxpbmUtYmxvY2t9Ci5lbXB0eXtwYWRkaW5nOjQwcHg7dGV4dC1hbGlnbjpjZW50ZXI7Y29sb3I6dmFyKC0tdDIpfQovKiBkcmF3ZXIgKi8KLnNjcmlte3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7YmFja2dyb3VuZDpyZ2JhKDAsMCwwLC41NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMnB4KTt6LWluZGV4OjIwO29wYWNpdHk6MDtwb2ludGVyLWV2ZW50czpub25lO3RyYW5zaXRpb246LjJzfQouc2NyaW0ub3BlbntvcGFjaXR5OjE7cG9pbnRlci1ldmVudHM6YXV0b30KLmRyYXdlcntwb3NpdGlvbjpmaXhlZDt0b3A6MDtib3R0b206MDtsZWZ0OjA7d2lkdGg6bWluKDUyMHB4LDEwMCUpO2JhY2tncm91bmQ6dmFyKC0tcCk7Ym9yZGVyLXJpZ2h0OjFweCBzb2xpZCB2YXIoLS1saW5lKTt6LWluZGV4OjIxO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC0xMDAlKTt0cmFuc2l0aW9uOi4yNXMgY3ViaWMtYmV6aWVyKC4yLC44LC4yLDEpO2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW47Ym94LXNoYWRvdzp2YXIoLS1zaCl9Ci5kcmF3ZXIub3Blbnt0cmFuc2Zvcm06bm9uZX0KLmRoe3BhZGRpbmc6MjBweCAyMnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXJ9Ci5kYntwYWRkaW5nOjZweCAyMnB4IDIycHg7b3ZlcmZsb3c6YXV0bztmbGV4OjE7bWluLWhlaWdodDowfS5kZntwYWRkaW5nOjE2cHggMjJweDtib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1saW5lKTtkaXNwbGF5OmZsZXg7Z2FwOjEwcHg7ZmxleC13cmFwOndyYXB9Ci5zZWN7bWFyZ2luLXRvcDoyMHB4O3BhZGRpbmc6MTZweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTRweDtiYWNrZ3JvdW5kOnZhcigtLXAyKX0KLnNlYyBoM3ttYXJnaW46MCAwIDRweDtmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1hKTtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo4cHh9CmxhYmVse2Rpc3BsYXk6YmxvY2s7Y29sb3I6dmFyKC0tdDIpO2ZvbnQtc2l6ZToxMi41cHg7bWFyZ2luOjEycHggMCA1cHg7Zm9udC13ZWlnaHQ6NjAwfQppbnB1dCxzZWxlY3R7d2lkdGg6MTAwJTtiYWNrZ3JvdW5kOnZhcigtLWJnKTtjb2xvcjp2YXIoLS10KTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTBweDtwYWRkaW5nOjExcHggMTJweDtmb250LXNpemU6MTVweH0KaW5wdXQ6Zm9jdXMsc2VsZWN0OmZvY3Vze291dGxpbmU6MnB4IHNvbGlkIHZhcigtLWEpO2JvcmRlci1jb2xvcjp0cmFuc3BhcmVudH0KLmdyaWQye2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6MTBweH0ucXVpY2t7ZGlzcGxheTpmbGV4O2dhcDo2cHg7bWFyZ2luLXRvcDo4cHg7ZmxleC13cmFwOndyYXB9Ci54bHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO3BhZGRpbmc6OXB4IDEycHg7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEwcHg7bWFyZ2luLXRvcDo4cHg7YmFja2dyb3VuZDp2YXIoLS1iZyl9Ci5tc2d7bWluLWhlaWdodDoyMnB4O21hcmdpbi10b3A6MTBweDtmb250LXdlaWdodDo2MDB9Lm9re2NvbG9yOnZhcigtLWEpfS5iYWR7Y29sb3I6dmFyKC0tcil9Ci5zd2l0Y2h7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjttYXJnaW4tdG9wOjEycHh9Ci50Z3twb3NpdGlvbjpyZWxhdGl2ZTt3aWR0aDo0NnB4O2hlaWdodDoyNnB4O2JhY2tncm91bmQ6dmFyKC0tcDMpO2JvcmRlci1yYWRpdXM6OTlweDtjdXJzb3I6cG9pbnRlcjt0cmFuc2l0aW9uOi4ycztib3JkZXI6MH0KLnRnOjphZnRlcntjb250ZW50OiIiO3Bvc2l0aW9uOmFic29sdXRlO3RvcDozcHg7cmlnaHQ6M3B4O3dpZHRoOjIwcHg7aGVpZ2h0OjIwcHg7Ym9yZGVyLXJhZGl1czo1MCU7YmFja2dyb3VuZDojZmZmO3RyYW5zaXRpb246LjJzfQoudGcub257YmFja2dyb3VuZDp2YXIoLS1hKX0udGcub246OmFmdGVye3JpZ2h0OjIzcHh9Ci5sb2dpbnttYXgtd2lkdGg6NDIwcHg7bWFyZ2luOjEydmggYXV0bztwYWRkaW5nOjI4cHh9Ci50b2FzdHtwb3NpdGlvbjpmaXhlZDtib3R0b206MjJweDtsZWZ0OjUwJTt0cmFuc2Zvcm06dHJhbnNsYXRlWCgtNTAlKSB0cmFuc2xhdGVZKDMwcHgpO2JhY2tncm91bmQ6dmFyKC0tcDMpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoxMnB4IDE4cHg7Ym9yZGVyLXJhZGl1czoxMnB4O29wYWNpdHk6MDt0cmFuc2l0aW9uOi4yNXM7ei1pbmRleDo0MDtmb250LXdlaWdodDo2MDB9Ci50b2FzdC5zaG93e29wYWNpdHk6MTt0cmFuc2Zvcm06dHJhbnNsYXRlWCgtNTAlKX0KLmhlbHB7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoYXV0by1maXQsbWlubWF4KDI2MHB4LDFmcikpO2dhcDoxNHB4fQouaGVscCAuY2FyZHtwYWRkaW5nOjE4cHh9LmhlbHAgb2x7bWFyZ2luOjhweCAwIDA7cGFkZGluZy1pbmxpbmUtc3RhcnQ6MjBweDtjb2xvcjp2YXIoLS10Mil9Ci5waWxse2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MnB4IDhweDtib3JkZXItcmFkaXVzOjk5cHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7Y29sb3I6dmFyKC0tdDIpfQpAbWVkaWEgKG1heC13aWR0aDo4MjBweCl7LnNoZWxse2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnJ9YXNpZGV7cG9zaXRpb246c3RhdGljO2hlaWdodDphdXRvO2ZsZXgtZGlyZWN0aW9uOnJvdztvdmVyZmxvdy14OmF1dG87cGFkZGluZzoxMHB4O2JvcmRlcjowO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpfQogLmJyYW5ke3BhZGRpbmc6NnB4IDEwcHh9Lm5hdnt3aWR0aDphdXRvO3doaXRlLXNwYWNlOm5vd3JhcH0uc3BhY2Vye2Rpc3BsYXk6bm9uZX1tYWlue3BhZGRpbmc6MThweCAxNHB4fS5zZWFyY2h7bWluLXdpZHRoOjA7ZmxleDoxfQogLmhpZGUtbXtkaXNwbGF5Om5vbmV9dGgsdGR7cGFkZGluZzoxMHB4IDhweH19Ci5ub3dvbiwubm93b2Zme2Rpc3BsYXk6YmxvY2s7bWFyZ2luLXRvcDo0cHg7Zm9udC1zaXplOjEycHg7bGluZS1oZWlnaHQ6MS41O3doaXRlLXNwYWNlOm5vcm1hbH0ubm93b257Y29sb3I6dmFyKC0tYSl9Lm5vd29mZntjb2xvcjp2YXIoLS10Myl9LndoZXJle2Rpc3BsYXk6YmxvY2s7bWFyZ2luLXRvcDoycHh9LnZwbm9ue2NvbG9yOiMyZTlkNWI7Zm9udC13ZWlnaHQ6NjAwfQp0ci5ncnAgdGR7YmFja2dyb3VuZDp2YXIoLS1jYXJkMixyZ2JhKDI1NSwyNTUsMjU1LC4wNSkpO2ZvbnQtd2VpZ2h0OjcwMDtwYWRkaW5nOjEwcHggMTRweDtib3JkZXItdG9wOjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1LC4wOCl9PC9zdHlsZT48L2hlYWQ+PGJvZHk+Cgo8ZGl2IGlkPSJsb2dpbiIgY2xhc3M9ImNhcmQgbG9naW4gaGlkZSI+CiAgPGRpdiBjbGFzcz0iYnJhbmQiIHN0eWxlPSJwYWRkaW5nOjAgMCAxMHB4Ij5TQVVESTxiPi5UVjwvYj48L2Rpdj4KICA8aDIgaWQ9Imx0Ij7Yr9iu2YjZhCDZhNmI2K3YqSDYp9mE2KXYr9in2LHYqTwvaDI+PHAgaWQ9ImxoIiBjbGFzcz0ibXV0ZWQiPjwvcD4KICA8bGFiZWw+2YPZhNmF2Kkg2KfZhNiz2LE8L2xhYmVsPjxpbnB1dCBpZD0icHciIHR5cGU9InBhc3N3b3JkIiBhdXRvY29tcGxldGU9ImN1cnJlbnQtcGFzc3dvcmQiPgogIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6MTZweCI+PGJ1dHRvbiBpZD0iZ28iIGNsYXNzPSJidG4iIHN0eWxlPSJ3aWR0aDoxMDAlO2p1c3RpZnktY29udGVudDpjZW50ZXIiPtiv2K7ZiNmEPC9idXR0b24+PC9kaXY+PGRpdiBpZD0ibG0iIGNsYXNzPSJtc2cgYmFkIj48L2Rpdj4KPC9kaXY+Cgo8ZGl2IGlkPSJhcHAiIGNsYXNzPSJzaGVsbCBoaWRlIj4KICA8YXNpZGU+CiAgICA8ZGl2IGNsYXNzPSJicmFuZCI+U0FVREk8Yj4uVFY8L2I+PC9kaXY+CiAgICA8YnV0dG9uIGNsYXNzPSJuYXYgb24iIGRhdGEtdj0iZGFzaCI+PHNwYW4gY2xhc3M9ImljIj7il6c8L3NwYW4+INmE2YjYrdipINin2YTYqtit2YPZhTwvYnV0dG9uPgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IiBkYXRhLXY9ImRldnMiPjxzcGFuIGNsYXNzPSJpYyI+4pakPC9zcGFuPiDYp9mE2KPYrNmH2LLYqTwvYnV0dG9uPgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IiBkYXRhLXY9InByb21vIj48c3BhbiBjbGFzcz0iaWMiPvCfjp88L3NwYW4+IFByb21vIGNvZGVzPC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJuYXYiIGRhdGEtdj0icGF5Ij48c3BhbiBjbGFzcz0iaWMiPvCfkrM8L3NwYW4+INin2YTYr9mB2Lk8L2J1dHRvbj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgZGF0YS12PSJoZWxwIj48c3BhbiBjbGFzcz0iaWMiPj88L3NwYW4+INi32LHZitmC2Kkg2KfZhNin2LPYqtiu2K/Yp9mFPC9idXR0b24+CiAgICA8ZGl2IGNsYXNzPSJzcGFjZXIiPjwvZGl2PgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IiBpZD0ib3V0Ij48c3BhbiBjbGFzcz0iaWMiPuKOizwvc3Bhbj4g2K7YsdmI2Kw8L2J1dHRvbj4KICA8L2FzaWRlPgogIDxtYWluPgogICAgPGRpdiBjbGFzcz0idG9wIj4KICAgICAgPGRpdj48aDEgaWQ9InZ0Ij7ZhNmI2K3YqSDYp9mE2KrYrdmD2YU8L2gxPjxwIGNsYXNzPSJzdWIiIGlkPSJ2cyI+2YbYuNix2Kkg2LPYsdmK2LnYqSDYudmE2Ykg2YPZhCDYp9mE2KPYrNmH2LLYqTwvcD48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0idG9vbHMiPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgaWQ9InJlZnJlc2giPuKfsyDYqtit2K/ZitirPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0iYWRkIj7vvIsg2KzZh9in2LIg2KzYr9mK2K88L2J1dHRvbj48L2Rpdj4KICAgIDwvZGl2PgoKICAgIDxzZWN0aW9uIGlkPSJ2LWRhc2giPgogICAgICA8ZGl2IGNsYXNzPSJzdGF0cyIgaWQ9InN0YXRzIj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1oIj48aDI+2YrYrdiq2KfYrCDYp9mG2KrYqNin2YfZgzwvaDI+PHNwYW4gY2xhc3M9Im11dGVkIiBpZD0iYXR0bi1uIj48L3NwYW4+PC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0id3JhcCI+PHRhYmxlPjx0Ym9keSBpZD0iYXR0biI+PC90Ym9keT48L3RhYmxlPjwvZGl2PgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1oIj48aDI+2LXYrdipINin2YTYqti32KjZitmCPC9oMj48c3BhbiBjbGFzcz0ibXV0ZWQiIGlkPSJobC1uIj48L3NwYW4+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBpZD0iaGwtY2xyIj7Zhdiz2K08L2J1dHRvbj48L2Rpdj4KICAgICAgICA8cCBjbGFzcz0ibXV0ZWQiPtmD2YQg2YXYsdipINin2YTYqti32KjZitmCINio2YrYqtiz2YPZkdixINio2K7Yt9ijINij2Ygg2KfZhNi02KfYtNipINio2KrYudmE2YIg2LnZhNmJINij2Yog2KzZh9in2LLYjCDYqNmK2YjYtdmEINmH2YjZhiDZhNit2KfZhNmHINi02Ygg2LXYp9ixLjwvcD4KICAgICAgICA8ZGl2IGNsYXNzPSJ3cmFwIj48dGFibGU+PHRib2R5IGlkPSJobCI+PC90Ym9keT48L3RhYmxlPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBpZD0idi1kZXZzIiBjbGFzcz0iaGlkZSI+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtaCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJ0b29scyIgaWQ9ImNoaXBzIj48L2Rpdj4KICAgICAgICAgIDxpbnB1dCBjbGFzcz0ic2VhcmNoIiBpZD0icSIgcGxhY2Vob2xkZXI9Itio2K3Yqzog2YPZiNiv2Iwg2KfYs9mF2IwgcGxheWxpc3TigKYiPgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9IndyYXAiPjx0YWJsZT4KICAgICAgICAgIDx0aGVhZD48dHI+PHRoPtin2YTZg9mI2K88L3RoPjx0aD7Yp9mE2LLYqNmI2YY8L3RoPjx0aD5QbGF5bGlzdHM8L3RoPjx0aD7Yp9mE2K3Yp9mE2Kk8L3RoPjx0aCBjbGFzcz0iaGlkZS1tIj7Yotiu2LEg2LjZh9mI2LE8L3RoPjx0aCBjbGFzcz0iaGlkZS1tIj7ZitmG2KrZh9mKPC90aD48L3RyPjwvdGhlYWQ+CiAgICAgICAgICA8dGJvZHkgaWQ9InRiIj48L3Rib2R5PjwvdGFibGU+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgoKICAgIDxzZWN0aW9uIGlkPSJ2LXByb21vIiBjbGFzcz0iaGlkZSI+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtaCI+PGgyPtmD2YjYryDYrNiv2YrYrzwvaDI+PHNwYW4gY2xhc3M9Im11dGVkIiBpZD0icHJvbW8tbiI+PC9zcGFuPjwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9InBhZGRpbmc6MTRweCAxOHB4O2Rpc3BsYXk6ZmxleDtnYXA6MTBweDtmbGV4LXdyYXA6d3JhcDthbGlnbi1pdGVtczplbmQiPgogICAgICAgICAgPGRpdj48bGFiZWw+2YTZhdmK2YbYnyAo2YXZhNin2K3YuNipINil2YTZgyk8L2xhYmVsPjxpbnB1dCBpZD0icG5vdGUiIHBsYWNlaG9sZGVyPSLZhdir2YTYp9mLOiDYo9io2Ygg2KPYrdmF2K8iPjwvZGl2PgogICAgICAgICAgPGRpdj48bGFiZWw+2KfZhNi52K/YrzwvbGFiZWw+PHNlbGVjdCBpZD0icGNvdW50Ij48b3B0aW9uPjE8L29wdGlvbj48b3B0aW9uPjM8L29wdGlvbj48b3B0aW9uPjU8L29wdGlvbj48b3B0aW9uPjEwPC9vcHRpb24+PC9zZWxlY3Q+PC9kaXY+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJwZ2VuIj7vvIsg2KPYtdiv2LE8L2J1dHRvbj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJ3cmFwIj48dGFibGU+CiAgICAgICAgICA8dGhlYWQ+PHRyPjx0aD7Yp9mE2YPZiNivPC90aD48dGg+2YTZhdmK2YY8L3RoPjx0aD7Yp9mE2K3Yp9mE2Kk8L3RoPjx0aD48L3RoPjwvdHI+PC90aGVhZD4KICAgICAgICAgIDx0Ym9keSBpZD0icHRiIj48L3Rib2R5PjwvdGFibGU+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgoKICAgIDxzZWN0aW9uIGlkPSJ2LXBheSIgY2xhc3M9ImhpZGUiPgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPjxoMj7Yp9mE2K/Zgdi5INiv2KfYrtmEINin2YTYqti32KjZitmCPC9oMj48c3BhbiBjbGFzcz0ibXV0ZWQiIGlkPSJwYXktc3QiPjwvc3Bhbj48L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJwYWRkaW5nOjE0cHggMThweDttYXgtd2lkdGg6NjQwcHgiPgogICAgICAgICAgPHAgY2xhc3M9Im11dGVkIiBzdHlsZT0iZm9udC1zaXplOjEzLjVweDtsaW5lLWhlaWdodDoxLjgiPtin2YTZhNmKINmF2Kcg2LnZhtiv2YcgUHJvbW8gY29kZSDYqNmK2LTZiNmBINi52YTZiSDYtNin2LTYqSDYp9mE2KrZgdi52YrZhCDYstixIMKrQnV5IGFjY2Vzc8K7INmF2LkgUVIuINio2YrZgdiq2K0g2YXZhiDYqtmE2YHZiNmG2Ycg2LXZgdit2Kkg2YHZitmH2Kcg2YPZiNivINis2YfYp9iy2Ycg2YjYp9mE2LPYudixINmI2LLYsSA8Yj5QYXkgd2l0aCBWZW5tbzwvYj7YjCDZiNin2YTZhdio2YTYuiDZiNin2YTZhdmE2KfYrdi42KkgKNmD2YjYryDYp9mE2KzZh9in2LIpINmF2LnYqNmR2YrZitmGINmE2K3Yp9mE2YfZhS4g2YTZhdinINiq2YjYtdmE2YMg2KfZhNiv2YHYudipINi52YTZiSBWZW5tb9iMINin2YTZhdmE2KfYrdi42Kkg2YHZitmH2Kcg2YPZiNivINin2YTYrNmH2KfYsjog2YHYudmR2YTZhyDZhdmGIMKr2KfZhNij2KzZh9iy2KnCuyDYstmKINin2YTYudin2K/YqS48L3A+CiAgICAgICAgICA8bGFiZWw+2KfZhNiz2LnYsSDYp9mE2YTZiiDYqNmK2LjZh9ixINmE2YTYstio2YjZhiAo2LHZgtmFINio2KfZhNiv2YjZhNin2LEpPC9sYWJlbD48aW5wdXQgaWQ9InBheS1wcmljZSIgcGxhY2Vob2xkZXI9IjI1MCIgc3R5bGU9ImRpcmVjdGlvbjpsdHI7dGV4dC1hbGlnbjpsZWZ0Ij4KICAgICAgICAgIDxsYWJlbD7Yp9iz2YUg2KfZhNmF2LPYqtiu2K/ZhSDYudmE2YkgVmVubW8gKNio2K/ZiNmGIEApPC9sYWJlbD48aW5wdXQgaWQ9InBheS1saW5rIiBwbGFjZWhvbGRlcj0iU2FpZi1TYXVkaSIgc3R5bGU9ImRpcmVjdGlvbjpsdHI7dGV4dC1hbGlnbjpsZWZ0Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9InN3aXRjaCI+PHNwYW4+2KfZhNiv2YHYuSDYtNi62ZHYp9mEPC9zcGFuPjxidXR0b24gY2xhc3M9InRnIiBpZD0icGF5LW9uIiB0eXBlPSJidXR0b24iPjwvYnV0dG9uPjwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij48YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJwYXktc2F2ZSI+2K3Zgdi4PC9idXR0b24+IDxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9InBheS1tc2ciPjwvc3Bhbj48L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CgogICAgPHNlY3Rpb24gaWQ9InYtaGVscCIgY2xhc3M9ImhpZGUiPgogICAgICA8ZGl2IGNsYXNzPSJoZWxwIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj48aDI+2LLYqNmI2YYg2KzYr9mK2K88L2gyPjxvbD48bGk+2KfZhNiy2KjZiNmGINmK2YbYstmR2YQgU0FVREkuVFYg2YXZhiBEb3dubG9hZGVyINmI2YrZgdiq2K3Zhy48L2xpPjxsaT7YqNmK2LfZhNi5INi52YTZiSDYtNin2LTYqtmHINmD2YjYryDZhdmGIDgg2KPYsdmC2KfZhS48L2xpPjxsaT7Zh9mI2YY6IO+8iyDYrNmH2KfYsiDYrNiv2YrYryDihpAg2KfZg9iq2Kgg2KfZhNmD2YjYryDZiNin2YTYp9iz2YUg2YjYp9mE2YAgcGxheWxpc3Qg2YjYp9mE2YrZiNiy2LEuPC9saT48bGk+2KfZhNiy2KjZiNmGINmK2YPYqNizIFJlbG9hZCDigJQg2K7ZhNi1LjwvbGk+PC9vbD48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj48aDI+2KPZg9ir2LEg2YXZhiBwbGF5bGlzdDwvaDI+PG9sPjxsaT7Yp9mB2KrYrSDYp9mE2KzZh9in2LIg4oaQINmC2LPZhSDCq1BsYXlsaXN0cyDYpdi22KfZgdmK2KnCuy48L2xpPjxsaT7Yp9iu2KrYp9ixINin2YTZgCBwbGF5bGlzdCDZiNin2YPYqtioINin2YTZitmI2LLYsSDZiNin2YTYqNin2LPZiNmI2LHYryDihpAg2KPYttmBLjwvbGk+PGxpPtin2YTYstio2YjZhiDYqNmK2K7Yqtin2LEg2KjZitmG2YfZhSDZhdmGIMKrUGxheWxpc3Rzwrsg2KjYp9mE2KrYt9io2YrZgi48L2xpPjwvb2w+PC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+PGgyPtiq2KzYr9mK2K8g2YjYpdmK2YLYp9mBPC9oMj48b2w+PGxpPtin2YHYqtitINin2YTYrNmH2KfYsiDihpAg2KPYstix2KfYsSArMzAgLyArOTAgLyArMzY1INmK2YjZhS48L2xpPjxsaT7Cq9in2YTYrNmH2KfYsiDYtNi62ZHYp9mEwrsg2KrYt9mB2YrZhyDYqNmK2YjZgtmBINin2YTYrtiv2YXYqSDZgdmI2LHYp9mLINi52YbYryDYp9mE2LLYqNmI2YYuPC9saT48bGk+2KfZhNij2KzZh9iy2Kkg2KfZhNmE2Yog2KjYqtmG2KrZh9mKINiu2YTYp9mEIDcg2KPZitin2YUg2KjYqti32YTYuSDYqNin2YTYo9i12YHYsS48L2xpPjwvb2w+PC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+PGgyPtin2YTYo9mF2KfZhjwvaDI+PG9sPjxsaT7Yp9mE2YrZiNiy2LEg2YjYp9mE2KjYp9iz2YjZiNix2K8g2YXYrdmB2YjYuNmK2YYg2YXYtNmB2ZHYsdmK2YYuPC9saT48bGk+2KfZhNio2KfYs9mI2YjYsdivINmF2Kcg2KjZitix2KzYuSDZiti42YfYsSDZh9mI2YYg2KPYqNiv2KfZiyDigJQg2KfYqtix2YPZhyDZgdin2LbZiiDZhNmK2KjZgtmJINin2YTZgtiv2YrZhS48L2xpPjxsaT7Ysdin2KjYtyDYp9mE2KrYt9io2YrZgjogPHNwYW4gY2xhc3M9ImNvZGUiPnNhdWRpMS4xc2FpZnNhdWRpLndvcmtlcnMuZGV2L2Fwazwvc3Bhbj48L2xpPjwvb2w+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgogIDwvbWFpbj4KPC9kaXY+Cgo8ZGl2IGNsYXNzPSJzY3JpbSIgaWQ9InNjcmltIj48L2Rpdj4KPGRpdiBjbGFzcz0iZHJhd2VyIiBpZD0iZHJhd2VyIj4KICA8ZGl2IGNsYXNzPSJkaCI+PGRpdj48aDIgaWQ9ImR0Ij7YrNmH2KfYsiDYrNiv2YrYrzwvaDI+PGRpdiBjbGFzcz0ibXV0ZWQiIGlkPSJkc3ViIj48L2Rpdj48L2Rpdj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGlkPSJkeCI+4pyVPC9idXR0b24+PC9kaXY+CiAgPGRpdiBjbGFzcz0iZGIiPgogICAgPGRpdiBjbGFzcz0ic2VjIj4KICAgICAgPGgzPuKRoCDYp9mE2KzZh9in2LIg2YjYp9mE2LLYqNmI2YY8L2gzPgogICAgICA8bGFiZWw+2YPZiNivINin2YTYrNmH2KfYsiAoOCDYo9ix2YLYp9mFINmF2YYg2LTYp9i02Kkg2KfZhNiy2KjZiNmGKTwvbGFiZWw+PGlucHV0IGlkPSJjb2RlIiBpbnB1dG1vZGU9Im51bWVyaWMiIG1heGxlbmd0aD0iOSIgcGxhY2Vob2xkZXI9IjEyMzQgNTY3OCIgY2xhc3M9ImNvZGUiIHN0eWxlPSJ0ZXh0LWFsaWduOnJpZ2h0Ij4KICAgICAgPGxhYmVsPtin2LPZhSDYp9mE2LLYqNmI2YY8L2xhYmVsPjxpbnB1dCBpZD0ibmFtZSIgcGxhY2Vob2xkZXI9ItmF2KvZhNin2Ys6INij2KjZiCDYo9it2YXYryI+ICAgICAgIDxsYWJlbD7Yp9mE2KfYs9mFINi52YTZiSDYtNin2LTYqSDYp9mE2KrYsdit2YrYqCAoV2VsY29tZSDigKYpPC9sYWJlbD48aW5wdXQgaWQ9InduYW1lIiBwbGFjZWhvbGRlcj0i2YXYq9mE2KfZizogTGFpdGgiIG1heGxlbmd0aD0iMzAiPgogICAgICA8ZGl2IGNsYXNzPSJzd2l0Y2giPjxzcGFuPtin2YTYrNmH2KfYsiDYtNi62ZHYp9mEPC9zcGFuPjxidXR0b24gY2xhc3M9InRnIG9uIiBpZD0iYWN0IiB0eXBlPSJidXR0b24iPjwvYnV0dG9uPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzZWMiPgogICAgICA8aDM+4pGhINin2YTZgCBQbGF5bGlzdCDYp9mE2KPYs9in2LPZitipPC9oMz4KICAgICAgPGxhYmVsPlBsYXlsaXN0PC9sYWJlbD48c2VsZWN0IGlkPSJwbCI+PC9zZWxlY3Q+CiAgICAgIDxkaXYgY2xhc3M9ImdyaWQyIj4KICAgICAgICA8ZGl2PjxsYWJlbD7Yp9mE2YrZiNiy2LE8L2xhYmVsPjxpbnB1dCBpZD0idSIgYXV0b2NvbXBsZXRlPSJvZmYiPjwvZGl2PgogICAgICAgIDxkaXY+PGxhYmVsPtin2YTYqNin2LPZiNmI2LHYrzwvbGFiZWw+PGlucHV0IGlkPSJwIiB0eXBlPSJwYXNzd29yZCIgYXV0b2NvbXBsZXRlPSJuZXctcGFzc3dvcmQiPjwvZGl2PgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ibXV0ZWQiIGlkPSJsaGludCIgc3R5bGU9ImZvbnQtc2l6ZToxMi41cHg7bWFyZ2luLXRvcDo2cHgiPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzZWMiPgogICAgICA8aDM+4pGiINin2YTYp9i02KrYsdin2YM8L2gzPgogICAgICA8bGFiZWw+2YrZhtiq2YfZiiDYqNiq2KfYsdmK2K4gKNmB2KfYttmKID0g2KjYr9mI2YYg2KfZhtiq2YfYp9ihKTwvbGFiZWw+PGlucHV0IGlkPSJleCIgdHlwZT0iZGF0ZSI+CiAgICAgIDxkaXYgY2xhc3M9InF1aWNrIj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSIzMCI+KzMwINmK2YjZhTwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjkwIj4rOTAg2YrZiNmFPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWFkZD0iMTgwIj4rNiDYtNmH2YjYsTwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjM2NSI+K9iz2YbYqTwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjAiPtio2K/ZiNmGINin2YbYqtmH2KfYoTwvYnV0dG9uPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzZWMiIGlkPSJ4c2VjIj4KICAgICAgPGgzPuKRoyBQbGF5bGlzdHMg2KXYttin2YHZitipPC9oMz4KICAgICAgPGRpdiBpZD0ieGxpc3QiPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJncmlkMiIgc3R5bGU9Im1hcmdpbi10b3A6NnB4Ij48ZGl2PjxsYWJlbD5QbGF5bGlzdDwvbGFiZWw+PHNlbGVjdCBpZD0ieHBsIj48L3NlbGVjdD48L2Rpdj48ZGl2PjwvZGl2PgogICAgICAgIDxkaXY+PGxhYmVsPtin2YTZitmI2LLYsTwvbGFiZWw+PGlucHV0IGlkPSJ4dSIgYXV0b2NvbXBsZXRlPSJvZmYiPjwvZGl2PjxkaXY+PGxhYmVsPtin2YTYqNin2LPZiNmI2LHYrzwvbGFiZWw+PGlucHV0IGlkPSJ4cCIgdHlwZT0icGFzc3dvcmQiIGF1dG9jb21wbGV0ZT0ibmV3LXBhc3N3b3JkIj48L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0ibWFyZ2luLXRvcDoxMHB4Ij48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGlkPSJ4YWRkIj7vvIsg2KPYttmBIHBsYXlsaXN0PC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNlYyIgaWQ9InZzZWMiPgogICAgICA8aDM+4pGkIFZQTiDCtyBQcm90b24gKNmF2KzYp9mG2YopPC9oMz4KICAgICAgPGRpdiBjbGFzcz0ibXV0ZWQiIHN0eWxlPSJmb250LXNpemU6MTIuNXB4O2xpbmUtaGVpZ2h0OjEuNyI+2YTZg9mEINis2YfYp9iyINit2LPYp9ioIFByb3RvbiDZhdis2KfZhtmKINiu2KfYtSDZgdmK2Yc6IDxiPmFjY291bnQucHJvdG9udnBuLmNvbTwvYj4g4oaQIERvd25sb2FkcyDihpAgPGI+V2lyZUd1YXJkIGNvbmZpZ3VyYXRpb248L2I+IOKGkCBQbGF0Zm9ybTogQW5kcm9pZCDihpAg2LPZitix2YHYsSDZhdis2KfZhtmKIChGcmVlKSDihpAgQ3JlYXRlIOKGkCBEb3dubG9hZC4g2KfZgdiq2K0g2KfZhNmF2YTZgSAo4oCOLmNvbmYpINmI2KfZhNi12YIg2YPZhCDYp9mE2YTZiiDZgdmK2Ycg2YfZiNmGLiDYp9mE2KPYrNmH2LLYqSDYp9mE2YTZiiDZhdinINil2YTZh9inIFZQTiDZh9mI2YYg2YXYpyDYqNmK2LjZh9ix2YTZh9inINiu2YrYp9ixIFZQTiDYo9io2K/Yp9mLLjwvZGl2PgogICAgICA8ZGl2IGlkPSJ2c3RhdGUiIHN0eWxlPSJtYXJnaW4tdG9wOjhweDtmb250LXNpemU6MTNweCI+PC9kaXY+CiAgICAgIDx0ZXh0YXJlYSBpZD0idmNvbmYiIHJvd3M9IjciIHNwZWxsY2hlY2s9ImZhbHNlIiBwbGFjZWhvbGRlcj0iW0ludGVyZmFjZV0mIzEwO1ByaXZhdGVLZXkgPSDigKYmIzEwO0FkZHJlc3MgPSAxMC4yLjAuMi8zMiYjMTA7JiMxMDtbUGVlcl0mIzEwO1B1YmxpY0tleSA9IOKApiYjMTA7RW5kcG9pbnQgPSDigKY6NTE4MjAiIHN0eWxlPSJ3aWR0aDoxMDAlO21hcmdpbi10b3A6OHB4O2RpcmVjdGlvbjpsdHI7dGV4dC1hbGlnbjpsZWZ0O2ZvbnQtZmFtaWx5Om1vbm9zcGFjZTtmb250LXNpemU6MTJweCI+PC90ZXh0YXJlYT4KICAgICAgPGRpdiBzdHlsZT0ibWFyZ2luLXRvcDo4cHg7ZGlzcGxheTpmbGV4O2dhcDoxMHB4Ij4KICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gc20iIGlkPSJ2c2F2ZSI+2K3Zgdi4INin2YTZgCBWUE48L2J1dHRvbj4KICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGlkPSJ2ZGVsIj7YtNmK2YQg2KfZhNmAIFZQTjwvYnV0dG9uPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ibXNnIiBpZD0ic20iPjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImRmIj48YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJzYXZlIj7YrdmB2Lg8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIGlkPSJjYW5jZWwiPtil2YTYutin2KE8L2J1dHRvbj48c3BhbiBjbGFzcz0ic3BhY2VyIiBzdHlsZT0iZmxleDoxIj48L3NwYW4+PGJ1dHRvbiBjbGFzcz0iYnRuIHJlZCBoaWRlIiBpZD0iZGVsIj7Yrdiw2YEg2KfZhNis2YfYp9iyPC9idXR0b24+PC9kaXY+CjwvZGl2Pgo8ZGl2IGNsYXNzPSJ0b2FzdCIgaWQ9InRvYXN0Ij48L2Rpdj4KCjxzY3JpcHQ+CmNvbnN0ICQgPSAoaWQpID0+IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTsKY29uc3QgYXBpID0gKHAsIGIpID0+IGZldGNoKCcvYWRtaW4vYXBpLycgKyBwLCBiID8geyBtZXRob2Q6ICdQT1NUJywgaGVhZGVyczogeyAnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nIH0sIGJvZHk6IEpTT04uc3RyaW5naWZ5KGIpLCBjcmVkZW50aWFsczogJ3NhbWUtb3JpZ2luJyB9IDogeyBjcmVkZW50aWFsczogJ3NhbWUtb3JpZ2luJyB9KQogIC50aGVuKGFzeW5jIChyKSA9PiAoeyBvazogci5vaywgLi4uKGF3YWl0IHIuanNvbigpLmNhdGNoKCgpID0+ICh7fSkpKSB9KSk7CmNvbnN0IGVzYyA9IChzKSA9PiBTdHJpbmcocyA/PyAnJykucmVwbGFjZSgvWyY8PiInXS9nLCAoYykgPT4gKHsgJyYnOiAnJmFtcDsnLCAnPCc6ICcmbHQ7JywgJz4nOiAnJmd0OycsICciJzogJyZxdW90OycsICInIjogJyYjMzk7JyB9W2NdKSk7CmNvbnN0IERBWSA9IDg2NDAwMDAwOwpjb25zdCBhZ28gPSAodCkgPT4geyBpZiAoIXQpIHJldHVybiAn4oCUJzsgY29uc3QgbSA9IE1hdGgucm91bmQoKERhdGUubm93KCkgLSB0KSAvIDYwMDAwKTsgcmV0dXJuIG0gPCAxID8gJ9in2YTYotmGJyA6IG0gPCA2MCA/IGAke219INiv2YLZitmC2KlgIDogbSA8IDE0NDAgPyBgJHtNYXRoLnJvdW5kKG0gLyA2MCl9INiz2KfYudipYCA6IGAke01hdGgucm91bmQobSAvIDE0NDApfSDZitmI2YVgOyB9Owpjb25zdCBkYXkgPSAodCkgPT4gdCA/IG5ldyBEYXRlKHQpLnRvSVNPU3RyaW5nKCkuc2xpY2UoMCwgMTApIDogJyc7CmNvbnN0IHByZXR0eSA9IChjKSA9PiBjLnJlcGxhY2UoLyhcZHs0fSkoXGR7NH0pLywgJyQxICQyJyk7CmxldCBkZXZzID0gW10sIHBsYXlsaXN0cyA9IFtdLCBmaWx0ZXIgPSAnYWxsJywgZWRpdGluZyA9IG51bGw7CgpmdW5jdGlvbiB0b2FzdCh0KSB7IGNvbnN0IGUgPSAkKCd0b2FzdCcpOyBlLnRleHRDb250ZW50ID0gdDsgZS5jbGFzc0xpc3QuYWRkKCdzaG93Jyk7IGNsZWFyVGltZW91dChlLl90KTsgZS5fdCA9IHNldFRpbWVvdXQoKCkgPT4gZS5jbGFzc0xpc3QucmVtb3ZlKCdzaG93JyksIDI2MDApOyB9CgpmdW5jdGlvbiBzdGF0ZShkKSB7CiAgY29uc3Qgbm93ID0gRGF0ZS5ub3coKTsKICBpZiAoIWQuYWN0aXZlKSByZXR1cm4geyBrOiAnb2ZmJywgdDogJ9mF2YjZgtmI2YEnIH07CiAgaWYgKGQuZXhwaXJlcyAmJiBkLmV4cGlyZXMgPCBub3cpIHJldHVybiB7IGs6ICdleHAnLCB0OiAn2YXZhtiq2YfZiicgfTsKICBpZiAoIWQuaGFzX2xvZ2luIHx8ICFkLnBsYXlsaXN0KSByZXR1cm4geyBrOiAnd2FpdCcsIHQ6ICfYqNin2YbYqti42KfYsSDYp9mE2KrZgdi52YrZhCcgfTsKICBpZiAoZC5leHBpcmVzICYmIGQuZXhwaXJlcyAtIG5vdyA8IDcgKiBEQVkpIHJldHVybiB7IGs6ICdzb29uJywgdDogYNmK2YbYqtmH2Yog2K7ZhNin2YQgJHtNYXRoLm1heCgxLCBNYXRoLmNlaWwoKGQuZXhwaXJlcyAtIG5vdykgLyBEQVkpKX0g2YrZiNmFYCB9OwogIHJldHVybiB7IGs6ICdvbicsIHQ6ICfYtNi62ZHYp9mEJyB9Owp9CmNvbnN0IGlzT25saW5lID0gKGQpID0+IGQuc2VlbiAmJiBEYXRlLm5vdygpIC0gZC5zZWVuIDwgMjAgKiA2MDAwMDsKLy8gd2hhdCB0aGUgZGV2aWNlIGlzIHdhdGNoaW5nIG5vdyAodG9sZCBieSB0aGUgYXBwIGV2ZXJ5IDEwMCBzKSBvciB3YXRjaGVkIGxhc3QKY29uc3QgS0lORCA9IHsgbGl2ZTogJ/Cfk7onLCBtb3ZpZTogJ/CfjqwnLCBzZXJpZXM6ICfwn46eJywgcmVjb3JkaW5nOiAn4o+6JywgdmlkZW86ICfilrYnIH07CmNvbnN0IGlzV2F0Y2hpbmcgPSAoZCkgPT4gZC5ub3dfdCAmJiBEYXRlLm5vdygpIC0gZC5ub3dfdCA8IDQgKiA2MDAwMDsKLy8gd2hlcmUgdGhlIGRldmljZSBpcyBub3csIGZyb20gaXRzIGludGVybmV0OiBmbGFnICsgY291bnRyeSArIGNpdHksIGFuZCDwn5SSIHdoZW4gaXQgY29tZXMgdGhyb3VnaCBvdXIgVlBOCmNvbnN0IGZsYWcgPSAoYykgPT4gYyAmJiBjLmxlbmd0aCA9PT0gMiA/IFN0cmluZy5mcm9tQ29kZVBvaW50KC4uLlsuLi5jLnRvVXBwZXJDYXNlKCldLm1hcCgoeCkgPT4gMTI3Mzk3ICsgeC5jaGFyQ29kZUF0KDApKSkgOiAnJzsKZnVuY3Rpb24gd2hlcmUoZCkgewogIGlmICghZC5jb3VudHJ5KSByZXR1cm4gJyc7CiAgbGV0IG4gPSBkLmNvdW50cnk7IHRyeSB7IG4gPSBuZXcgSW50bC5EaXNwbGF5TmFtZXMoWydhciddLCB7IHR5cGU6ICdyZWdpb24nIH0pLm9mKGQuY291bnRyeSkgfHwgZC5jb3VudHJ5OyB9IGNhdGNoIChlKSB7fQogIGNvbnN0IHYgPSBkLm9uX3ZwbiA/ICcgPHNwYW4gY2xhc3M9InZwbm9uIj7wn5SSIFZQTiDYtNi62ZHYp9mEIChQcm90b24pPC9zcGFuPicgOiBkLmhhc192cG4gPyAnIDxzcGFuIGNsYXNzPSJtdXRlZCI+wrcgVlBOINmF2LfZgdmKPC9zcGFuPicgOiAnJzsKICByZXR1cm4gYDxzbWFsbCBjbGFzcz0id2hlcmUiPvCfk40gJHtmbGFnKGQuY291bnRyeSl9ICR7ZXNjKG4pfSR7ZC5jaXR5ID8gJyDCtyAnICsgZXNjKGQuY2l0eSkgOiAnJ30ke3Z9PC9zbWFsbD5gOwp9CmZ1bmN0aW9uIHdhdGNoaW5nKGQpIHsKICBpZiAoIWQubm93X3QgfHwgIWQubm93X3RpdGxlKSByZXR1cm4gJyc7CiAgY29uc3Qgd2hhdCA9IGAke0tJTkRbZC5ub3dfa2luZF0gfHwgJ+KWtid9ICR7ZXNjKGQubm93X3RpdGxlKX0ke2Qubm93X3BsYXlsaXN0ID8gJyA8c3BhbiBjbGFzcz0ibXV0ZWQiPsK3ICcgKyBlc2MoZC5ub3dfcGxheWxpc3QpICsgJzwvc3Bhbj4nIDogJyd9YDsKICByZXR1cm4gaXNXYXRjaGluZyhkKSA/IGA8c21hbGwgY2xhc3M9Im5vd29uIj48c3BhbiBjbGFzcz0ib25saW5lIj48L3NwYW4+2YrYtNin2YfYryDYp9mE2KLZhjogJHt3aGF0fTwvc21hbGw+YCA6IGA8c21hbGwgY2xhc3M9Im5vd29mZiI+2KLYrtixINmF2LTYp9mH2K/YqSAo2YLYqNmEICR7YWdvKGQubm93X3QpfSk6ICR7d2hhdH08L3NtYWxsPmA7Cn0KCmFzeW5jIGZ1bmN0aW9uIGluaXQoKSB7CiAgY29uc3QgcyA9IGF3YWl0IGFwaSgnc3RhdGUnKTsKICBwbGF5bGlzdHMgPSBzLnBsYXlsaXN0cyB8fCBbXTsKICBjb25zdCBvcHRzID0gcGxheWxpc3RzLm1hcCgocCkgPT4gYDxvcHRpb24gdmFsdWU9IiR7ZXNjKHApfSI+JHtlc2MocCl9PC9vcHRpb24+YCkuam9pbignJyk7CiAgJCgncGwnKS5pbm5lckhUTUwgPSBvcHRzOyAkKCd4cGwnKS5pbm5lckhUTUwgPSBvcHRzOwogIGlmIChzLnNpZ25lZCkgcmV0dXJuIHNob3coKTsKICAkKCdsb2dpbicpLmNsYXNzTGlzdC5yZW1vdmUoJ2hpZGUnKTsKICBpZiAocy5zZXR1cCkgeyAkKCdsdCcpLnRleHRDb250ZW50ID0gJ9ij2YjZhCDZhdix2Kk6INin2K7Yqtin2LEg2YPZhNmF2Kkg2LPYsSDZhNmE2KXYr9in2LHYqSc7ICQoJ2xoJykudGV4dENvbnRlbnQgPSAnOCDYo9it2LHZgSDYudmE2Ykg2KfZhNij2YLZhC4g2YfYp9mKINin2YTZg9mE2YXYqSDYqNiq2K/YrtmE2YMg2LnZhNmJINin2YTZhdmI2YLYuSDZhdmGINij2Yog2KzZh9in2LIuJzsgJCgncHcnKS5hdXRvY29tcGxldGUgPSAnbmV3LXBhc3N3b3JkJzsgfQogICQoJ3B3JykuZm9jdXMoKTsKfQokKCdnbycpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgnbG9naW4nLCB7IHBhc3N3b3JkOiAkKCdwdycpLnZhbHVlLCBzZXR1cDogbmV3IFVSTFNlYXJjaFBhcmFtcyhsb2NhdGlvbi5zZWFyY2gpLmdldCgnc2V0dXAnKSB8fCAnJyB9KTsKICBpZiAoci5vaykgeyAkKCdwdycpLnZhbHVlID0gJyc7IHNob3coKTsgfSBlbHNlICQoJ2xtJykudGV4dENvbnRlbnQgPSByLmVycm9yIHx8ICfYrti32KMnOwp9OwokKCdwdycpLm9ua2V5ZG93biA9IChlKSA9PiB7IGlmIChlLmtleSA9PT0gJ0VudGVyJykgJCgnZ28nKS5jbGljaygpOyB9OwokKCdvdXQnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4geyBhd2FpdCBhcGkoJ2xvZ291dCcsIHt9KTsgbG9jYXRpb24ucmVsb2FkKCk7IH07CgpmdW5jdGlvbiBzaG93KCkgeyAkKCdsb2dpbicpLmNsYXNzTGlzdC5hZGQoJ2hpZGUnKTsgJCgnYXBwJykuY2xhc3NMaXN0LnJlbW92ZSgnaGlkZScpOyBsb2FkKCk7IH0KCmNvbnN0IFZJRVdTID0geyBkYXNoOiBbJ9mE2YjYrdipINin2YTYqtit2YPZhScsICfZhti42LHYqSDYs9ix2YrYudipINi52YTZiSDZg9mEINin2YTYo9is2YfYstipJ10sIGRldnM6IFsn2KfZhNij2KzZh9iy2KknLCAn2YPZhCDYp9mE2LLYqNin2YrZhiDigJQg2KfYtti62Lcg2LnZhNmJINij2Yog2KzZh9in2LIg2YTYqti52K/ZitmE2YcnXSwgcHJvbW86IFsnUHJvbW8gY29kZXMnLCAn2YPZhCDZg9mI2K8g2KjZiti02KrYutmEINmF2LHYqSDZiNit2K/YqSDYudmE2Ykg2KzZh9in2LIg2YjYp9it2K8nXSwgcGF5OiBbJ9in2YTYr9mB2LknLCAn2KfZhNmE2Yog2KjYsdinINin2YTYr9in2KbYsdipINio2YrYr9mB2Lkg4oCUINmI2KfZhNmE2Yog2KzZiNmR2KfZh9inINio2YrYp9iu2K8gUHJvbW8gY29kZSddLCBoZWxwOiBbJ9i32LHZitmC2Kkg2KfZhNin2LPYqtiu2K/Yp9mFJywgJ9iu2LfZiNin2Kog2LPYsdmK2LnYqSddIH07CmZ1bmN0aW9uIHZpZXcodikgewogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy5uYXZbZGF0YS12XScpLmZvckVhY2goKG4pID0+IG4uY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCBuLmRhdGFzZXQudiA9PT0gdikpOwogIE9iamVjdC5rZXlzKFZJRVdTKS5mb3JFYWNoKChrKSA9PiAkKCd2LScgKyBrKS5jbGFzc0xpc3QudG9nZ2xlKCdoaWRlJywgayAhPT0gdikpOwogICQoJ3Z0JykudGV4dENvbnRlbnQgPSBWSUVXU1t2XVswXTsgJCgndnMnKS50ZXh0Q29udGVudCA9IFZJRVdTW3ZdWzFdOwogIGlmICh2ID09PSAncHJvbW8nKSBsb2FkUHJvbW9zKCk7CiAgaWYgKHYgPT09ICdwYXknKSBsb2FkUGF5KCk7Cn0KLy8gLS0tLS0tLS0tLSBwYXltZW50IC0tLS0tLS0tLS0KYXN5bmMgZnVuY3Rpb24gbG9hZFBheSgpIHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdwYXknKTsKICAkKCdwYXktcHJpY2UnKS52YWx1ZSA9IHIucHJpY2UgfHwgJyc7ICQoJ3BheS1saW5rJykudmFsdWUgPSByLmxpbmsgfHwgJyc7ICQoJ3BheS1vbicpLmNsYXNzTGlzdC50b2dnbGUoJ29uJywgISFyLm9uKTsKICAkKCdwYXktc3QnKS50ZXh0Q29udGVudCA9IChyLm9uID8gJ9i02LrZkdin2YQnIDogJ9mF2LfZgdmKJykgKyAoci5saW5rID8gJyDCtyBWZW5tbyBAJyArIHIubGluay5yZXBsYWNlKC9eQC8sICcnKSA6ICcnKTsKfQokKCdwYXktb24nKS5vbmNsaWNrID0gKCkgPT4gJCgncGF5LW9uJykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nKTsKJCgncGF5LXNhdmUnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3BheScsIHsgcHJpY2U6ICQoJ3BheS1wcmljZScpLnZhbHVlLnRyaW0oKSwgbGluazogJCgncGF5LWxpbmsnKS52YWx1ZS50cmltKCksIG9uOiAkKCdwYXktb24nKS5jbGFzc0xpc3QuY29udGFpbnMoJ29uJykgfSk7CiAgJCgncGF5LW1zZycpLnRleHRDb250ZW50ID0gci5vayA/ICfYp9mG2K3Zgdi4IOKckycgOiAoci5lcnJvciB8fCAn2K7Yt9ijJyk7IGxvYWRQYXkoKTsKfTsKLy8gLS0tLS0tLS0tLSBwcm9tbyBjb2Rlczogb25lIHVzZSwgb25lIGRldmljZSAtLS0tLS0tLS0tCmNvbnN0IHBjb2RlID0gKGMpID0+IGMucmVwbGFjZSgvKC57NH0pKC57NH0pLywgJyQxLSQyJyk7CmFzeW5jIGZ1bmN0aW9uIGxvYWRQcm9tb3MoKSB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgncHJvbW9zJyk7IGNvbnN0IGxpc3QgPSByLnByb21vcyB8fCBbXTsKICBjb25zdCBmcmVlID0gbGlzdC5maWx0ZXIoKHApID0+ICFwLnVzZWRfYnkpLmxlbmd0aDsKICAkKCdwcm9tby1uJykudGV4dENvbnRlbnQgPSBgJHtmcmVlfSDYrNin2YfYsiDCtyAke2xpc3QubGVuZ3RoIC0gZnJlZX0g2YXYs9iq2LnZhdmEYDsKICAkKCdwdGInKS5pbm5lckhUTUwgPSBsaXN0Lmxlbmd0aCA/IGxpc3QubWFwKChwKSA9PiB7CiAgICBjb25zdCBkID0gcC51c2VkX2J5ID8gZGV2cy5maW5kKCh4KSA9PiB4LmNvZGUgPT09IHAudXNlZF9ieSkgOiBudWxsOwogICAgY29uc3Qgc3QgPSBwLnVzZWRfYnkgPyBgPHNwYW4gY2xhc3M9InN0IHMtb2ZmIj7Zhdiz2KrYudmF2YQgwrcgJHtlc2MoZD8ubmFtZSB8fCBwcmV0dHkocC51c2VkX2J5KSl9IMK3INmC2KjZhCAke2FnbyhwLnVzZWRfYXQpfTwvc3Bhbj5gIDogJzxzcGFuIGNsYXNzPSJzdCBzLW9uIj7YrNin2YfYsjwvc3Bhbj4nOwogICAgcmV0dXJuIGA8dHI+PHRkPjxzcGFuIGNsYXNzPSJjb2RlIj4ke2VzYyhwY29kZShwLmNvZGUpKX08L3NwYW4+PC90ZD48dGQ+JHtlc2MocC5ub3RlIHx8ICcnKX08L3RkPjx0ZD4ke3N0fTwvdGQ+CiAgICAgIDx0ZCBzdHlsZT0idGV4dC1hbGlnbjpsZWZ0Ij4ke3AudXNlZF9ieSA/ICcnIDogYDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1jcD0iJHtlc2MocGNvZGUocC5jb2RlKSl9Ij7Zhtiz2K48L2J1dHRvbj4gYH08YnV0dG9uIGNsYXNzPSJidG4gcmVkIHNtIiBkYXRhLXBkPSIke2VzYyhwLmNvZGUpfSI+2K3YsNmBPC9idXR0b24+PC90ZD48L3RyPmA7CiAgfSkuam9pbignJykgOiAnPHRyPjx0ZCBjb2xzcGFuPSI0IiBjbGFzcz0iZW1wdHkiPtmF2Kcg2YHZiiDYo9mD2YjYp9ivIOKAlCDYo9i12K/YsSDYo9mI2YQg2YPZiNivINmF2YYg2YHZiNmCPC90ZD48L3RyPic7CiAgJCgncHRiJykucXVlcnlTZWxlY3RvckFsbCgnW2RhdGEtY3BdJykuZm9yRWFjaCgoYikgPT4gYi5vbmNsaWNrID0gKCkgPT4geyBuYXZpZ2F0b3IuY2xpcGJvYXJkPy53cml0ZVRleHQoYi5kYXRhc2V0LmNwKTsgdG9hc3QoJ9in2YbYqtiz2K46ICcgKyBiLmRhdGFzZXQuY3ApOyB9KTsKICAkKCdwdGInKS5xdWVyeVNlbGVjdG9yQWxsKCdbZGF0YS1wZF0nKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7IGlmICghY29uZmlybSgn2K3YsNmBINin2YTZg9mI2K/YnycpKSByZXR1cm47IGF3YWl0IGFwaSgncHJvbW9fZGVsZXRlJywgeyBjb2RlOiBiLmRhdGFzZXQucGQgfSk7IGxvYWRQcm9tb3MoKTsgfSk7Cn0KJCgncGdlbicpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgncHJvbW8nLCB7IG46ICskKCdwY291bnQnKS52YWx1ZSwgbm90ZTogJCgncG5vdGUnKS52YWx1ZS50cmltKCkgfSk7CiAgaWYgKHIub2spIHsgJCgncG5vdGUnKS52YWx1ZSA9ICcnOyB0b2FzdCgn2KrZhSDYpdi12K/Yp9ixICcgKyAoci5jb2RlcyB8fCBbXSkubGVuZ3RoICsgJyDZg9mI2K8nKTsgbG9hZFByb21vcygpOyB9IGVsc2UgdG9hc3Qoci5lcnJvciB8fCAn2K7Yt9ijJyk7Cn07CmRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy5uYXZbZGF0YS12XScpLmZvckVhY2goKG4pID0+IG4ub25jbGljayA9ICgpID0+IHZpZXcobi5kYXRhc2V0LnYpKTsKCmFzeW5jIGZ1bmN0aW9uIGxvYWQoKSB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgnZGV2aWNlcycpOwogIGlmIChyLm9rID09PSBmYWxzZSAmJiByLmVycm9yKSB7IGxvY2F0aW9uLnJlbG9hZCgpOyByZXR1cm47IH0KICBkZXZzID0gci5kZXZpY2VzIHx8IFtdOwogIHJlbmRlclN0YXRzKCk7IHJlbmRlclRhYmxlKCk7IHJlbmRlckF0dG4oKTsKICBsb2FkSGVhbHRoKCk7Cn0KYXN5bmMgZnVuY3Rpb24gbG9hZEhlYWx0aCgpIHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdoZWFsdGgnKTsKICBjb25zdCBoID0gci5oZWFsdGggfHwgW107CiAgJCgnaGwtbicpLnRleHRDb250ZW50ID0gaC5sZW5ndGggPyBgJHtoLmxlbmd0aH0g2KrZgtix2YrYsWAgOiAnJzsKICAkKCdobCcpLmlubmVySFRNTCA9IGgubGVuZ3RoID8gaC5tYXAoKHgpID0+IGA8dHI+PHRkPjxzcGFuIGNsYXNzPSJzdCAke3gua2luZCA9PT0gJ29mZi1haXInID8gJ3Mtb24nIDogeC5raW5kID09PSAnZnJlZXplJyA/ICdzLXNvb24nIDogJ3Mtb2ZmJ30iPiR7eC5raW5kID09PSAnb2ZmLWFpcicgPyAn2YLZhtin2Kkg2LPZiNiv2Kcg2LnZhtivINin2YTZhdiy2YjYrycgOiB4LmtpbmQgPT09ICdmcmVlemUnID8gJ9i52YTZkdmC2Kog2KfZhNi02KfYtNipJyA6ICfYqtiz2YPZkdixINio2K7Yt9ijJ308L3NwYW4+PC90ZD4KICAgIDx0ZD4ke2VzYyh4Lm5hbWUgfHwgcHJldHR5KHguY29kZSkpfTxicj48c21hbGwgY2xhc3M9Im11dGVkIj4ke2VzYyh4LnZlcil9IMK3INmC2KjZhCAke2Fnbyh4LnQpfTwvc21hbGw+PC90ZD4KICAgIDx0ZD48ZGV0YWlscz48c3VtbWFyeSBjbGFzcz0ibXV0ZWQiPtin2YTYqtmB2KfYtdmK2YQ8L3N1bW1hcnk+PHByZSBkaXI9Imx0ciIgc3R5bGU9IndoaXRlLXNwYWNlOnByZS13cmFwO2ZvbnQtc2l6ZToxMXB4O21heC1oZWlnaHQ6MjYwcHg7b3ZlcmZsb3c6YXV0byI+JHtlc2MoeC5pbmZvKX08L3ByZT48L2RldGFpbHM+PC90ZD48L3RyPmApLmpvaW4oJycpCiAgICA6ICc8dHI+PHRkIGNsYXNzPSJtdXRlZCI+4pyTINmI2YTYpyDYudi32YQg2LnZhNmJINij2Yog2KzZh9in2LI8L3RkPjwvdHI+JzsKfQokKCdobC1jbHInKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4geyBpZiAoIWNvbmZpcm0oJ9mF2LPYrSDZg9mEINin2YTYqtmC2KfYsdmK2LHYnycpKSByZXR1cm47IGF3YWl0IGFwaSgnaGVhbHRoL2NsZWFyJywge30pOyBsb2FkSGVhbHRoKCk7IH07CiQoJ3JlZnJlc2gnKS5vbmNsaWNrID0gKCkgPT4gbG9hZCgpLnRoZW4oKCkgPT4gdG9hc3QoJ9iq2YUg2KfZhNiq2K3Yr9mK2KsnKSk7CgpmdW5jdGlvbiBjb3VudHMoKSB7CiAgY29uc3QgYyA9IHsgYWxsOiBkZXZzLmxlbmd0aCwgb246IDAsIHdhaXQ6IDAsIHNvb246IDAsIGV4cDogMCwgb2ZmOiAwLCBvbmxpbmU6IDAsIHdhdGNoOiAwIH07CiAgZGV2cy5mb3JFYWNoKChkKSA9PiB7IGNbc3RhdGUoZCkua10rKzsgaWYgKGlzT25saW5lKGQpKSBjLm9ubGluZSsrOyBpZiAoaXNXYXRjaGluZyhkKSkgYy53YXRjaCsrOyB9KTsKICByZXR1cm4gYzsKfQpmdW5jdGlvbiByZW5kZXJTdGF0cygpIHsKICBjb25zdCBjID0gY291bnRzKCk7CiAgY29uc3QgUyA9IFtbJ2FsbCcsICfZg9mEINin2YTYo9is2YfYstipJywgYy5hbGwsICd2YXIoLS10MiknXSwgWydvbmxpbmUnLCAn2YXYqti12YQg2KfZhNii2YYnLCBjLm9ubGluZSwgJ3ZhcigtLWEpJ10sIFsnd2F0Y2gnLCAn2YrYtNin2YfYryDYp9mE2KLZhicsIGMud2F0Y2gsICd2YXIoLS1hKSddLCBbJ29uJywgJ9i02LrZkdin2YQnLCBjLm9uICsgYy5zb29uLCAndmFyKC0tYSknXSwKICAgIFsnd2FpdCcsICfYqNin2YbYqti42KfYsSDYp9mE2KrZgdi52YrZhCcsIGMud2FpdCwgJ3ZhcigtLWIpJ10sIFsnc29vbicsICfZitmG2KrZh9mKINiu2YTYp9mEIDcg2KPZitin2YUnLCBjLnNvb24sICd2YXIoLS15KSddLCBbJ2V4cCcsICfZhdmG2KrZh9mKJywgYy5leHAsICd2YXIoLS1yKSddLCBbJ29mZicsICfZhdmI2YLZiNmBJywgYy5vZmYsICd2YXIoLS10MyknXV07CiAgJCgnc3RhdHMnKS5pbm5lckhUTUwgPSBTLm1hcCgoW2ssIGwsIG4sIGNvbF0pID0+IGA8ZGl2IGNsYXNzPSJzdGF0IiBkYXRhLWY9IiR7a30iPjxkaXYgY2xhc3M9ImwiPjxzcGFuIGNsYXNzPSJkb3QiIHN0eWxlPSJiYWNrZ3JvdW5kOiR7Y29sfSI+PC9zcGFuPiR7bH08L2Rpdj48ZGl2IGNsYXNzPSJuIj4ke259PC9kaXY+PC9kaXY+YCkuam9pbignJyk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnN0YXQnKS5mb3JFYWNoKChzKSA9PiBzLm9uY2xpY2sgPSAoKSA9PiB7IGZpbHRlciA9IHMuZGF0YXNldC5mOyB2aWV3KCdkZXZzJyk7IHJlbmRlclRhYmxlKCk7IH0pOwogIGNvbnN0IEYgPSBbWydhbGwnLCAn2KfZhNmD2YQnXSwgWydvbmxpbmUnLCAn2YXYqti12YQg2KfZhNii2YYnXSwgWyd3YXRjaCcsICfZiti02KfZh9ivINin2YTYotmGJ10sIFsnb24nLCAn2LTYutmR2KfZhCddLCBbJ3dhaXQnLCAn2KjYp9mG2KrYuNin2LEg2KfZhNiq2YHYudmK2YQnXSwgWydzb29uJywgJ9mK2YbYqtmH2Yog2YLYsdmK2KjYp9mLJ10sIFsnZXhwJywgJ9mF2YbYqtmH2YonXSwgWydvZmYnLCAn2YXZiNmC2YjZgSddXTsKICAkKCdjaGlwcycpLmlubmVySFRNTCA9IEYubWFwKChbaywgbF0pID0+IGA8YnV0dG9uIGNsYXNzPSJjaGlwJHtmaWx0ZXIgPT09IGsgPyAnIG9uJyA6ICcnfSIgZGF0YS1mPSIke2t9Ij4ke2x9IDxzcGFuIGNsYXNzPSJwaWxsIj4ke2sgPT09ICdvbicgPyBjLm9uICsgYy5zb29uIDogY1trXX08L3NwYW4+PC9idXR0b24+YCkuam9pbignJyk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLmNoaXAnKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSAoKSA9PiB7IGZpbHRlciA9IGIuZGF0YXNldC5mOyByZW5kZXJTdGF0cygpOyByZW5kZXJUYWJsZSgpOyB9KTsKfQpmdW5jdGlvbiByb3coZCkgewogIGNvbnN0IHMgPSBzdGF0ZShkKTsKICBjb25zdCBwbHMgPSAoZC5wbGF5bGlzdCA/IGA8c3BhbiBjbGFzcz0idGFnIj4ke2VzYyhkLnBsYXlsaXN0KX08L3NwYW4+YCA6ICc8c3BhbiBjbGFzcz0ibXV0ZWQiPuKAlDwvc3Bhbj4nKSArIChkLmV4dHJhcyB8fCBbXSkubWFwKCh4KSA9PiBgPHNwYW4gY2xhc3M9InRhZyI+KyAke2VzYyh4KX08L3NwYW4+YCkuam9pbignJyk7CiAgcmV0dXJuIGA8dHIgZGF0YS1jPSIke2VzYyhkLmNvZGUpfSI+PHRkPjxzcGFuIGNsYXNzPSJjb2RlIj4ke3ByZXR0eShlc2MoZC5jb2RlKSl9PC9zcGFuPjwvdGQ+CiAgICA8dGQgY2xhc3M9IndobyI+PGI+JHtkLm5hbWUgPyBlc2MoZC5uYW1lKSA6ICc8c3BhbiBjbGFzcz0ibXV0ZWQiPtio2K/ZiNmGINin2LPZhTwvc3Bhbj4nfTwvYj48c21hbGw+JHtlc2MoZC5tb2RlbCB8fCAnJyl9PC9zbWFsbD4ke3doZXJlKGQpfSR7d2F0Y2hpbmcoZCl9PC90ZD4KICAgIDx0ZD4ke3Bsc30ke2QuaGFzX3ZwbiA/ICc8c3BhbiBjbGFzcz0idGFnIj7wn5uhIFZQTjwvc3Bhbj4nIDogJyd9JHtkLnByb21vID8gJzxzcGFuIGNsYXNzPSJ0YWciPicgKyAoZC5wcm9tby5zdGFydHNXaXRoKCdQQUlEJykgPyAn8J+SsyDYr9mB2LknIDogJ/Cfjp8gJyArIGVzYyhkLnByb21vLnJlcGxhY2UoLyguezR9KSguezR9KS8sICckMS0kMicpKSkgKyAnPC9zcGFuPicgOiAnJ308L3RkPjx0ZD48c3BhbiBjbGFzcz0ic3Qgcy0ke3Mua30iPiR7aXNPbmxpbmUoZCkgPyAnPHNwYW4gY2xhc3M9Im9ubGluZSI+PC9zcGFuPicgOiAnJ30ke3MudH08L3NwYW4+PC90ZD4KICAgIDx0ZCBjbGFzcz0iaGlkZS1tIG11dGVkIj4ke2FnbyhkLnNlZW4pfTwvdGQ+PHRkIGNsYXNzPSJoaWRlLW0gbXV0ZWQiPiR7ZGF5KGQuZXhwaXJlcykgfHwgJ+KAlCd9PC90ZD48L3RyPmA7Cn0KZnVuY3Rpb24gYmluZFJvd3ModGIpIHsgdGIucXVlcnlTZWxlY3RvckFsbCgndHJbZGF0YS1jXScpLmZvckVhY2goKHRyKSA9PiB0ci5vbmNsaWNrID0gKCkgPT4gb3BlbkRyYXdlcih0ci5kYXRhc2V0LmMpKTsgfQpmdW5jdGlvbiByZW5kZXJUYWJsZSgpIHsKICBjb25zdCBxID0gJCgncScpLnZhbHVlLnRyaW0oKS50b0xvd2VyQ2FzZSgpLnJlcGxhY2UoL1xzL2csICcnKTsKICBjb25zdCBsaXN0ID0gZGV2cy5maWx0ZXIoKGQpID0+IHsKICAgIGNvbnN0IGsgPSBzdGF0ZShkKS5rOwogICAgaWYgKGZpbHRlciA9PT0gJ3dhdGNoJyA/ICFpc1dhdGNoaW5nKGQpIDogZmlsdGVyID09PSAnb25saW5lJyA/ICFpc09ubGluZShkKSA6IGZpbHRlciA9PT0gJ29uJyA/ICEoayA9PT0gJ29uJyB8fCBrID09PSAnc29vbicpIDogZmlsdGVyICE9PSAnYWxsJyAmJiBrICE9PSBmaWx0ZXIpIHJldHVybiBmYWxzZTsKICAgIGlmICghcSkgcmV0dXJuIHRydWU7CiAgICByZXR1cm4gW2QuY29kZSwgZC5uYW1lLCBkLnBsYXlsaXN0LCBkLm1vZGVsLCBkLm5vd190aXRsZSwgLi4uKGQuZXh0cmFzIHx8IFtdKV0uc29tZSgodikgPT4gU3RyaW5nKHYgfHwgJycpLnRvTG93ZXJDYXNlKCkucmVwbGFjZSgvXHMvZywgJycpLmluY2x1ZGVzKHEpKTsKICB9KTsKICAvLyBkZXZpY2VzIHdpdGggdGhlIHNhbWUgY3VzdG9tZXIgbmFtZSBhcmUgc2hvd24gYXMgb25lIGdyb3VwOiB0aGV5IGFyZSB0aGUgb25lcyB0aGF0IHNoYXJlIGZhdm9yaXRlcyBhbmQgY29udGludWUgd2F0Y2hpbmcKICBjb25zdCBncnAgPSBuZXcgTWFwKCksIGxvb3NlID0gW107CiAgbGlzdC5mb3JFYWNoKChkKSA9PiB7IGNvbnN0IGsgPSBTdHJpbmcoZC5uYW1lIHx8ICcnKS50cmltKCkudG9Mb3dlckNhc2UoKTsgaWYgKCFrKSBsb29zZS5wdXNoKGQpOyBlbHNlIHsgaWYgKCFncnAuaGFzKGspKSBncnAuc2V0KGssIFtdKTsgZ3JwLmdldChrKS5wdXNoKGQpOyB9IH0pOwogIGNvbnN0IHBhcnRzID0gW107CiAgWy4uLmdycC5lbnRyaWVzKCldLnNvcnQoKGEsIGIpID0+IGFbMF0ubG9jYWxlQ29tcGFyZShiWzBdKSkuZm9yRWFjaCgoW2ssIGRzXSkgPT4gewogICAgaWYgKGRzLmxlbmd0aCA+IDEpIHBhcnRzLnB1c2goYDx0ciBjbGFzcz0iZ3JwIj48dGQgY29sc3Bhbj0iNiI+8J+RpSAke2VzYyhkc1swXS5uYW1lKX0gPHNtYWxsIGNsYXNzPSJtdXRlZCI+wrcgJHtkcy5sZW5ndGh9INij2KzZh9iy2Kkgwrcg2KfZhNmF2YHYttmE2Kkg2YjYpdmD2YXYp9mEINin2YTZhdi02KfZh9iv2Kkg2YXYqtiy2KfZhdmG2Kkg2KjZitmG2YfZhTwvc21hbGw+PC90ZD48L3RyPmAgKyBkcy5tYXAocm93KS5qb2luKCcnKSk7CiAgICBlbHNlIHBhcnRzLnB1c2gocm93KGRzWzBdKSk7CiAgfSk7CiAgaWYgKGxvb3NlLmxlbmd0aCkgcGFydHMucHVzaChgPHRyIGNsYXNzPSJncnAiPjx0ZCBjb2xzcGFuPSI2Ij7YqNiv2YjZhiDYp9iz2YUgPHNtYWxsIGNsYXNzPSJtdXRlZCI+wrcg2YXYpyDYqNiq2KrYstin2YXZhiAo2KfZg9iq2Kgg2KfYs9mFINin2YTYstio2YjZhiDZhNmE2KzZh9in2LIpPC9zbWFsbD48L3RkPjwvdHI+YCArIGxvb3NlLm1hcChyb3cpLmpvaW4oJycpKTsKICAkKCd0YicpLmlubmVySFRNTCA9IGxpc3QubGVuZ3RoID8gcGFydHMuam9pbignJykgOiBgPHRyPjx0ZCBjb2xzcGFuPSI2IiBjbGFzcz0iZW1wdHkiPtmF2Kcg2YHZiiDYo9is2YfYstipINmH2YjZhjwvdGQ+PC90cj5gOwogIGJpbmRSb3dzKCQoJ3RiJykpOwp9CiQoJ3EnKS5vbmlucHV0ID0gcmVuZGVyVGFibGU7CmZ1bmN0aW9uIHJlbmRlckF0dG4oKSB7CiAgY29uc3Qgb3JkZXIgPSB7IHdhaXQ6IDAsIHNvb246IDEsIGV4cDogMiB9OwogIGNvbnN0IGxpc3QgPSBkZXZzLmZpbHRlcigoZCkgPT4gc3RhdGUoZCkuayBpbiBvcmRlcikuc29ydCgoYSwgYikgPT4gb3JkZXJbc3RhdGUoYSkua10gLSBvcmRlcltzdGF0ZShiKS5rXSk7CiAgJCgnYXR0bi1uJykudGV4dENvbnRlbnQgPSBsaXN0Lmxlbmd0aCA/IGAke2xpc3QubGVuZ3RofSDYrNmH2KfYsmAgOiAnJzsKICAkKCdhdHRuJykuaW5uZXJIVE1MID0gbGlzdC5sZW5ndGggPyBsaXN0Lm1hcChyb3cpLmpvaW4oJycpIDogYDx0cj48dGQgY2xhc3M9ImVtcHR5Ij7Zg9mEINi02Yog2KrZhdin2YUg4pyTIOKAlCDZhdinINmB2Yog2KPYrNmH2LLYqSDYqNin2YbYqti42KfYsSDYo9mIINmF2YbYqtmH2YrYqTwvdGQ+PC90cj5gOwogIGJpbmRSb3dzKCQoJ2F0dG4nKSk7Cn0KCi8vIC0tLS0tLS0tLS0gZHJhd2VyIC0tLS0tLS0tLS0KZnVuY3Rpb24gb3BlbkRyYXdlcihjb2RlKSB7CiAgZWRpdGluZyA9IGNvZGUgPyBkZXZzLmZpbmQoKHgpID0+IHguY29kZSA9PT0gY29kZSkgOiBudWxsOwogIGNvbnN0IGQgPSBlZGl0aW5nIHx8IHt9OwogICQoJ2R0JykudGV4dENvbnRlbnQgPSBlZGl0aW5nID8gKGQubmFtZSB8fCAn2KzZh9in2LIgJyArIHByZXR0eShkLmNvZGUpKSA6ICfYrNmH2KfYsiDYrNiv2YrYryc7CiAgJCgnZHN1YicpLmlubmVySFRNTCA9IGVkaXRpbmcgPyBgPHNwYW4gY2xhc3M9ImNvZGUiPiR7cHJldHR5KGVzYyhkLmNvZGUpKX08L3NwYW4+IMK3ICR7ZXNjKGQubW9kZWwgfHwgJycpfSDCtyDYotiu2LEg2LjZh9mI2LEgJHthZ28oZC5zZWVuKX0ke3dhdGNoaW5nKGQpID8gJzxicj4nICsgd2F0Y2hpbmcoZCkgOiAnJ31gIDogJ9in2YPYqtioINin2YTZg9mI2K8g2KfZhNmE2Yog2LjYp9mH2LEg2LnZhNmJINi02KfYtNipINin2YTYstio2YjZhic7CiAgJCgnY29kZScpLnZhbHVlID0gZC5jb2RlID8gcHJldHR5KGQuY29kZSkgOiAnJzsgJCgnY29kZScpLmRpc2FibGVkID0gZmFsc2U7CiAgJCgnbmFtZScpLnZhbHVlID0gZC5uYW1lIHx8ICcnOyAkKCd3bmFtZScpLnZhbHVlID0gZC53ZWxjb21lIHx8ICcnOyAkKCdwbCcpLnZhbHVlID0gZC5wbGF5bGlzdCB8fCBwbGF5bGlzdHNbMF0gfHwgJyc7CiAgJCgndScpLnZhbHVlID0gJyc7ICQoJ3AnKS52YWx1ZSA9ICcnOyAkKCdleCcpLnZhbHVlID0gZGF5KGQuZXhwaXJlcyk7CiAgJCgnbGhpbnQnKS50ZXh0Q29udGVudCA9IGQuaGFzX2xvZ2luID8gJ9in2YTZitmI2LLYsSDZhdit2YHZiNi4INmI2YXYtNmB2ZHYsS4g2KfZg9iq2Kgg2YrZiNiy2LEg2YjYqNin2LPZiNmI2LHYryDYrNiv2KfYryDYqNizINil2LDYpyDYqNiv2YMg2KrYutmK2ZHYsdmH2YUuJyA6ICfYp9mD2KrYqCDYp9mE2YrZiNiy2LEg2YjYp9mE2KjYp9iz2YjZiNix2K8g2KrYqNi5INin2YTZgCBwbGF5bGlzdC4nOwogICQoJ2FjdCcpLmNsYXNzTGlzdC50b2dnbGUoJ29uJywgZWRpdGluZyA/ICEhZC5hY3RpdmUgOiB0cnVlKTsKICAkKCdkZWwnKS5jbGFzc0xpc3QudG9nZ2xlKCdoaWRlJywgIWVkaXRpbmcpOyAkKCd4c2VjJykuY2xhc3NMaXN0LnRvZ2dsZSgnaGlkZScsICFlZGl0aW5nKTsgJCgndnNlYycpLmNsYXNzTGlzdC50b2dnbGUoJ2hpZGUnLCAhZWRpdGluZyk7CiAgJCgndmNvbmYnKS52YWx1ZSA9ICcnOyB2ZHJhdyhkLmhhc192cG4pOwogIHJlbmRlckV4dHJhcygpOyAkKCdzbScpLnRleHRDb250ZW50ID0gJyc7CiAgJCgnc2NyaW0nKS5jbGFzc0xpc3QuYWRkKCdvcGVuJyk7ICQoJ2RyYXdlcicpLmNsYXNzTGlzdC5hZGQoJ29wZW4nKTsKICBzZXRUaW1lb3V0KCgpID0+IChlZGl0aW5nID8gJCgnbmFtZScpIDogJCgnY29kZScpKS5mb2N1cygpLCAyNTApOwp9CmZ1bmN0aW9uIGNsb3NlRHJhd2VyKCkgeyAkKCdzY3JpbScpLmNsYXNzTGlzdC5yZW1vdmUoJ29wZW4nKTsgJCgnZHJhd2VyJykuY2xhc3NMaXN0LnJlbW92ZSgnb3BlbicpOyBlZGl0aW5nID0gbnVsbDsgfQokKCdhZGQnKS5vbmNsaWNrID0gKCkgPT4gb3BlbkRyYXdlcihudWxsKTsKJCgnZHgnKS5vbmNsaWNrID0gJCgnY2FuY2VsJykub25jbGljayA9ICQoJ3NjcmltJykub25jbGljayA9IGNsb3NlRHJhd2VyOwpkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCdrZXlkb3duJywgKGUpID0+IHsgaWYgKGUua2V5ID09PSAnRXNjYXBlJykgY2xvc2VEcmF3ZXIoKTsgfSk7CiQoJ2FjdCcpLm9uY2xpY2sgPSAoKSA9PiAkKCdhY3QnKS5jbGFzc0xpc3QudG9nZ2xlKCdvbicpOwpkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCdbZGF0YS1hZGRdJykuZm9yRWFjaCgoYikgPT4gYi5vbmNsaWNrID0gKCkgPT4gewogIGNvbnN0IG4gPSArYi5kYXRhc2V0LmFkZDsKICBpZiAoIW4pIHsgJCgnZXgnKS52YWx1ZSA9ICcnOyByZXR1cm47IH0KICBjb25zdCBjdXIgPSAkKCdleCcpLnZhbHVlID8gRGF0ZS5wYXJzZSgkKCdleCcpLnZhbHVlKSA6IDA7CiAgJCgnZXgnKS52YWx1ZSA9IGRheShNYXRoLm1heChjdXIsIERhdGUubm93KCkpICsgbiAqIERBWSk7Cn0pOwpmdW5jdGlvbiByZW5kZXJFeHRyYXMoKSB7CiAgY29uc3QgeHMgPSBlZGl0aW5nPy5leHRyYXMgfHwgW107CiAgJCgneGxpc3QnKS5pbm5lckhUTUwgPSB4cy5sZW5ndGggPyB4cy5tYXAoKHgpID0+IGA8ZGl2IGNsYXNzPSJ4bCI+PHNwYW4gY2xhc3M9InRhZyI+JHtlc2MoeCl9PC9zcGFuPjxidXR0b24gY2xhc3M9ImJ0biByZWQgc20iIGRhdGEteD0iJHtlc2MoeCl9Ij7YtNmK2YQ8L2J1dHRvbj48L2Rpdj5gKS5qb2luKCcnKSA6ICc8ZGl2IGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxM3B4Ij7ZhdinINmB2YogcGxheWxpc3RzINil2LbYp9mB2YrYqS48L2Rpdj4nOwogICQoJ3hsaXN0JykucXVlcnlTZWxlY3RvckFsbCgnW2RhdGEteF0nKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgICBpZiAoIWNvbmZpcm0oYNi02YrZhCAke2IuZGF0YXNldC54fSDZhdmGINmH2LDYpyDYp9mE2KzZh9in2LLYn2ApKSByZXR1cm47CiAgICBhd2FpdCBhcGkoJ2V4dHJhJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUsIHBsYXlsaXN0OiBiLmRhdGFzZXQueCwgcmVtb3ZlOiB0cnVlIH0pOwogICAgYXdhaXQgcmVsb2FkRWRpdGluZygpOyB0b2FzdCgn2KfZhti02KfZhNiqJyk7CiAgfSk7Cn0KYXN5bmMgZnVuY3Rpb24gcmVsb2FkRWRpdGluZygpIHsgY29uc3QgYyA9IGVkaXRpbmc/LmNvZGU7IGF3YWl0IGxvYWQoKTsgaWYgKGMpIHsgZWRpdGluZyA9IGRldnMuZmluZCgoeCkgPT4geC5jb2RlID09PSBjKTsgcmVuZGVyRXh0cmFzKCk7IH0gfQokKCd4YWRkJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBpZiAoIWVkaXRpbmcpIHJldHVybjsKICBjb25zdCByID0gYXdhaXQgYXBpKCdleHRyYScsIHsgY29kZTogZWRpdGluZy5jb2RlLCBwbGF5bGlzdDogJCgneHBsJykudmFsdWUsIHVzZXI6ICQoJ3h1JykudmFsdWUsIHBhc3M6ICQoJ3hwJykudmFsdWUgfSk7CiAgaWYgKHIub2spIHsgJCgneHUnKS52YWx1ZSA9ICcnOyAkKCd4cCcpLnZhbHVlID0gJyc7IGF3YWl0IHJlbG9hZEVkaXRpbmcoKTsgdG9hc3QoJ9in2YbYttin2YHYqiDinJMg4oCUINiu2YTZiiDYp9mE2LLYqNmI2YYg2YrZg9io2LMgUmVsb2FkJyk7IH0KICBlbHNlICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKHIuZXJyb3IpfTwvc3Bhbj5gOwp9OwovLyBQcm90b24gb25seSAob3duZXIsIDExIE5vdiAyMDI2KTogcGFzdGUgdGhlIGRldmljZSdzIG93biBQcm90b24gV2lyZUd1YXJkIGZpbGUsIG9yIHRha2UgaXQgb2ZmCmNvbnN0IHZkcmF3ID0gKG9uKSA9PiB7CiAgJCgndnN0YXRlJykuaW5uZXJIVE1MID0gb24gPyAnPHNwYW4gY2xhc3M9Im9rIj7wn5uhINmH2LDYpyDYp9mE2KzZh9in2LIg2LnZhtiv2YcgVlBOIOKAlCDYqNmK2LjZh9ix2YTZhyDYstixIFZQTiBPTi9PRkY8L3NwYW4+JyA6ICc8c3BhbiBjbGFzcz0ibXV0ZWQiPtmF2Kcg2YHZiiBWUE4g2YTZh9iw2Kcg2KfZhNis2YfYp9iyICjZhdinINio2YrYuNmH2LHZhNmHINij2Yog2K7Zitin2LEgVlBOKTwvc3Bhbj4nOwogICQoJ3ZkZWwnKS5jbGFzc0xpc3QudG9nZ2xlKCdoaWRlJywgIW9uKTsKfTsKJCgndnNhdmUnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGlmICghZWRpdGluZykgcmV0dXJuOwogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3ZwbicsIHsgY29kZTogZWRpdGluZy5jb2RlLCBjb25mOiAkKCd2Y29uZicpLnZhbHVlIH0pOwogIGlmIChyLm9rKSB7ICQoJ3Zjb25mJykudmFsdWUgPSAnJzsgYXdhaXQgcmVsb2FkRWRpdGluZygpOyB2ZHJhdyhlZGl0aW5nLmhhc192cG4pOyB0b2FzdCgnVlBOINin2YbYrdmB2Lgg4oCUINiu2YTZiiDYp9mE2LLYqNmI2YYg2YrZg9io2LMgUmVsb2FkJyk7IH0KICBlbHNlICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKHIuZXJyb3IpfTwvc3Bhbj5gOwp9OwokKCd2ZGVsJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBpZiAoIWVkaXRpbmcgfHwgIWNvbmZpcm0oJ9i02YrZhCDYp9mE2YAgVlBOINmF2YYg2YfYsNinINin2YTYrNmH2KfYstifJykpIHJldHVybjsKICBhd2FpdCBhcGkoJ3ZwbicsIHsgY29kZTogZWRpdGluZy5jb2RlLCBjb25mOiAnJyB9KTsgYXdhaXQgcmVsb2FkRWRpdGluZygpOyB2ZHJhdyhlZGl0aW5nLmhhc192cG4pOyB0b2FzdCgn2KfZhti02KfZhCDigJQg2KjZitiu2KrZgdmKINiu2YrYp9ixINin2YTZgCBWUE4g2YXZhiDYp9mE2KzZh9in2LInKTsKfTsKJCgnc2F2ZScpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgY29uc3QgY29kZSA9ICQoJ2NvZGUnKS52YWx1ZS5yZXBsYWNlKC9cRC9nLCAnJyk7CiAgaWYgKGNvZGUubGVuZ3RoICE9PSA4KSB7ICQoJ3NtJykuaW5uZXJIVE1MID0gJzxzcGFuIGNsYXNzPSJiYWQiPtmD2YjYryDYp9mE2KzZh9in2LIgOCDYo9ix2YLYp9mFPC9zcGFuPic7IHJldHVybjsgfQogIC8vIGEgbmV3IGNvZGUgZm9yIHRoaXMgZGV2aWNlICh0aGUgYXBwIHdhcyBwdXQgYmFjayk6IGV2ZXJ5dGhpbmcgbW92ZXMgdG8gaXQgZmlyc3QKICBpZiAoZWRpdGluZyAmJiBjb2RlICE9PSBlZGl0aW5nLmNvZGUpIHsKICAgIGlmICghY29uZmlybShg2YbZgtmEICR7ZWRpdGluZy5uYW1lIHx8ICfYp9mE2KzZh9in2LInfSDZhdmGINin2YTZg9mI2K8gJHtwcmV0dHkoZWRpdGluZy5jb2RlKX0g2YTZhNmD2YjYryDYp9mE2KzYr9mK2K8gJHtwcmV0dHkoY29kZSl92J9gKSkgcmV0dXJuOwogICAgY29uc3QgbSA9IGF3YWl0IGFwaSgncmVjb2RlJywgeyBmcm9tOiBlZGl0aW5nLmNvZGUsIHRvOiBjb2RlIH0pOwogICAgaWYgKCFtLm9rKSB7ICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKG0uZXJyb3IpfTwvc3Bhbj5gOyByZXR1cm47IH0KICAgIGF3YWl0IGxvYWQoKTsgZWRpdGluZyA9IGRldnMuZmluZCgoeCkgPT4geC5jb2RlID09PSBjb2RlKSB8fCBlZGl0aW5nOwogIH0KICBjb25zdCBkID0gZGV2cy5maW5kKCh4KSA9PiB4LmNvZGUgPT09IGNvZGUpOwogIGlmICghZD8uaGFzX2xvZ2luICYmICghJCgndScpLnZhbHVlIHx8ICEkKCdwJykudmFsdWUpKSB7ICQoJ3NtJykuaW5uZXJIVE1MID0gJzxzcGFuIGNsYXNzPSJiYWQiPtin2YPYqtioINin2YTZitmI2LLYsSDZiNin2YTYqNin2LPZiNmI2LHYrzwvc3Bhbj4nOyByZXR1cm47IH0KICBjb25zdCByID0gYXdhaXQgYXBpKCdzYXZlJywgeyBjb2RlLCBuYW1lOiAkKCduYW1lJykudmFsdWUudHJpbSgpLCB3ZWxjb21lOiAkKCd3bmFtZScpLnZhbHVlLnRyaW0oKSwgcGxheWxpc3Q6ICQoJ3BsJykudmFsdWUsIHVzZXI6ICQoJ3UnKS52YWx1ZSwgcGFzczogJCgncCcpLnZhbHVlLCBleHBpcmVzOiAkKCdleCcpLnZhbHVlLCBhY3RpdmU6ICQoJ2FjdCcpLmNsYXNzTGlzdC5jb250YWlucygnb24nKSB9KTsKICBpZiAoIXIub2spIHsgJCgnc20nKS5pbm5lckhUTUwgPSBgPHNwYW4gY2xhc3M9ImJhZCI+JHtlc2Moci5lcnJvcil9PC9zcGFuPmA7IHJldHVybjsgfQogICQoJ3AnKS52YWx1ZSA9ICcnOyBjbG9zZURyYXdlcigpOyBhd2FpdCBsb2FkKCk7IHRvYXN0KCfYp9mG2K3Zgdi4IOKckyDigJQg2K7ZhNmKINin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQnKTsKfTsKJCgnZGVsJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBpZiAoIWVkaXRpbmcgfHwgIWNvbmZpcm0oYNit2LDZgSDYp9mE2KzZh9in2LIgJHtwcmV0dHkoZWRpdGluZy5jb2RlKX0g2YbZh9in2KbZitin2YvYn2ApKSByZXR1cm47CiAgYXdhaXQgYXBpKCdkZWxldGUnLCB7IGNvZGU6IGVkaXRpbmcuY29kZSB9KTsgY2xvc2VEcmF3ZXIoKTsgYXdhaXQgbG9hZCgpOyB0b2FzdCgn2KfZhtit2LDZgScpOwp9Owppbml0KCk7CnNldEludGVydmFsKCgpID0+IHsgaWYgKCEkKCdhcHAnKS5jbGFzc0xpc3QuY29udGFpbnMoJ2hpZGUnKSAmJiAhJCgnZHJhd2VyJykuY2xhc3NMaXN0LmNvbnRhaW5zKCdvcGVuJykpIGxvYWQoKTsgfSwgMzAwMDApOwo8L3NjcmlwdD48L2JvZHk+PC9odG1sPgo="), (c) => c.charCodeAt(0)));
