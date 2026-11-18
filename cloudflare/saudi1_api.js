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
const PAGE = new TextDecoder().decode(Uint8Array.from(atob("PCFkb2N0eXBlIGh0bWw+PGh0bWwgbGFuZz0iYXIiIGRpcj0icnRsIj48aGVhZD48bWV0YSBjaGFyc2V0PSJ1dGYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEiPgo8dGl0bGU+U0FVREkuVFYgwrcg2YTZiNit2Kkg2KfZhNil2K/Yp9ix2Kk8L3RpdGxlPgo8c3R5bGU+Cjpyb290ey0tYmc6IzA5MGMxMjstLXA6IzEyMTcyMjstLXAyOiMxOTIwMmU7LS1wMzojMjIyYjNkOy0tbGluZTojMjMyYzNlOy0tdDojZjJmNGY4Oy0tdDI6IzlhYTNiNTstLXQzOiM2Yjc0ODg7LS1hOiMwMGQ2OGY7LS1hMjojMDBiMzc3Oy0tcjojZmY0ZDVlOy0teTojZmZiMDIwOy0tYjojNGRhM2ZmOy0tc2g6MCAxMHB4IDMwcHggcmdiYSgwLDAsMCwuMzUpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveH1odG1sLGJvZHl7aGVpZ2h0OjEwMCV9CmJvZHl7bWFyZ2luOjA7YmFja2dyb3VuZDpyYWRpYWwtZ3JhZGllbnQoMTIwMHB4IDYwMHB4IGF0IDEwMCUgLTEwJSwjMGYyYTIwIDAsdHJhbnNwYXJlbnQgNjAlKSx2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdCk7Zm9udDoxNXB4LzEuNTUgc3lzdGVtLXVpLC1hcHBsZS1zeXN0ZW0sIlNlZ29lIFVJIixUYWhvbWEsc2Fucy1zZXJpZn0KYXtjb2xvcjppbmhlcml0fS5oaWRle2Rpc3BsYXk6bm9uZSFpbXBvcnRhbnR9Lm11dGVke2NvbG9yOnZhcigtLXQyKX0uY29kZXtmb250LWZhbWlseTp1aS1tb25vc3BhY2UsTWVubG8sbW9ub3NwYWNlO2xldHRlci1zcGFjaW5nOjEuNXB4O2RpcmVjdGlvbjpsdHI7ZGlzcGxheTppbmxpbmUtYmxvY2s7d2hpdGUtc3BhY2U6bm93cmFwfQouc2hlbGx7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyNDBweCAxZnI7bWluLWhlaWdodDoxMDB2aH0KYXNpZGV7YmFja2dyb3VuZDpyZ2JhKDE4LDIzLDM0LC44NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMTBweCk7Ym9yZGVyLWxlZnQ6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6MjJweCAxNHB4O3Bvc2l0aW9uOnN0aWNreTt0b3A6MDtoZWlnaHQ6MTAwdmg7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4fQouYnJhbmR7Zm9udC1zaXplOjI0cHg7Zm9udC13ZWlnaHQ6ODAwO2xldHRlci1zcGFjaW5nOi41cHg7cGFkZGluZzo0cHggMTBweCAxOHB4O2RpcmVjdGlvbjpsdHI7dGV4dC1hbGlnbjpyaWdodH0uYnJhbmQgYntjb2xvcjp2YXIoLS1hKX0KLm5hdntkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4O3BhZGRpbmc6MTFweCAxMnB4O2JvcmRlci1yYWRpdXM6MTJweDtjb2xvcjp2YXIoLS10Mik7Y3Vyc29yOnBvaW50ZXI7Zm9udC13ZWlnaHQ6NjAwO2JvcmRlcjowO2JhY2tncm91bmQ6bm9uZTt3aWR0aDoxMDAlO3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjE1cHh9Ci5uYXY6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCl9Lm5hdi5vbntiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx0cmFuc3BhcmVudCxyZ2JhKDAsMjE0LDE0MywuMTYpKTtjb2xvcjp2YXIoLS10KTtib3gtc2hhZG93Omluc2V0IC0zcHggMCAwIHZhcigtLWEpfQoubmF2IC5pY3t3aWR0aDoyMnB4O3RleHQtYWxpZ246Y2VudGVyfS5zcGFjZXJ7ZmxleDoxfQptYWlue3BhZGRpbmc6MjZweCAzMHB4IDYwcHg7bWF4LXdpZHRoOjEyNDBweDt3aWR0aDoxMDAlfQoudG9we2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjE0cHg7bWFyZ2luLWJvdHRvbToyMnB4O2ZsZXgtd3JhcDp3cmFwfQpoMXttYXJnaW46MDtmb250LXNpemU6MjZweH1oMnttYXJnaW46MCAwIDRweDtmb250LXNpemU6MThweH0uc3Vie2NvbG9yOnZhcigtLXQyKTttYXJnaW46MnB4IDAgMH0KLmJ0bntiYWNrZ3JvdW5kOnZhcigtLWEpO2NvbG9yOiMwMzE0MGM7Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czoxMXB4O3BhZGRpbmc6MTFweCAxOHB4O2ZvbnQtd2VpZ2h0OjgwMDtmb250LXNpemU6MTQuNXB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo4cHg7dHJhbnNpdGlvbjouMTVzfQouYnRuOmhvdmVye2JhY2tncm91bmQ6dmFyKC0tYTIpfS5idG4uZ2hvc3R7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKX0uYnRuLmdob3N0OmhvdmVye2JhY2tncm91bmQ6dmFyKC0tcDMpfQouYnRuLnJlZHtiYWNrZ3JvdW5kOnJnYmEoMjU1LDc3LDk0LC4xNCk7Y29sb3I6dmFyKC0tcik7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDI1NSw3Nyw5NCwuMzUpfS5idG4uc217cGFkZGluZzo3cHggMTJweDtmb250LXNpemU6MTNweDtib3JkZXItcmFkaXVzOjlweH0KLnN0YXRze2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KGF1dG8tZml0LG1pbm1heCgxMzhweCwxZnIpKTtnYXA6MTRweDttYXJnaW4tYm90dG9tOjIycHh9Ci5zdGF0e2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDE4MGRlZyx2YXIoLS1wMiksdmFyKC0tcCkpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNnB4O3BhZGRpbmc6MTZweCAxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpO2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246LjE1c30KLnN0YXQ6aG92ZXJ7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoLTJweCk7Ym9yZGVyLWNvbG9yOiMyZjNhNTJ9Ci5zdGF0IC5ue2ZvbnQtc2l6ZTozMHB4O2ZvbnQtd2VpZ2h0OjgwMDttYXJnaW4tdG9wOjRweH0uc3RhdCAubHtjb2xvcjp2YXIoLS10Mik7Zm9udC1zaXplOjEzcHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6N3B4fQouZG90e3dpZHRoOjlweDtoZWlnaHQ6OXB4O2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrfQouY2FyZHtiYWNrZ3JvdW5kOnZhcigtLXApO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpfQouY2FyZC1oe2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjEycHg7cGFkZGluZzoxNnB4IDE4cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7ZmxleC13cmFwOndyYXB9Ci50b29sc3tkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5zZWFyY2h7YmFja2dyb3VuZDp2YXIoLS1wMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjExcHg7cGFkZGluZzo5cHggMTJweDtjb2xvcjp2YXIoLS10KTttaW4td2lkdGg6MjQwcHg7Zm9udC1zaXplOjE0cHh9Ci5jaGlwe2JhY2tncm91bmQ6dmFyKC0tcDIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Y29sb3I6dmFyKC0tdDIpO2JvcmRlci1yYWRpdXM6OTlweDtwYWRkaW5nOjZweCAxM3B4O2ZvbnQtc2l6ZToxM3B4O2N1cnNvcjpwb2ludGVyO2ZvbnQtd2VpZ2h0OjYwMH0KLmNoaXAub257YmFja2dyb3VuZDpyZ2JhKDAsMjE0LDE0MywuMTQpO2JvcmRlci1jb2xvcjpyZ2JhKDAsMjE0LDE0MywuNSk7Y29sb3I6dmFyKC0tYSl9Ci53cmFwe292ZXJmbG93LXg6YXV0b310YWJsZXt3aWR0aDoxMDAlO2JvcmRlci1jb2xsYXBzZTpjb2xsYXBzZX0KdGgsdGR7dGV4dC1hbGlnbjpyaWdodDtwYWRkaW5nOjEycHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1saW5lKTtmb250LXNpemU6MTRweDt2ZXJ0aWNhbC1hbGlnbjptaWRkbGV9CnRoe2NvbG9yOnZhcigtLXQzKTtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHh9CnRib2R5IHRye3RyYW5zaXRpb246LjEycztjdXJzb3I6cG9pbnRlcn10Ym9keSB0cjpob3ZlcntiYWNrZ3JvdW5kOnJnYmEoMjU1LDI1NSwyNTUsLjAyNSl9Ci53aG8gYntkaXNwbGF5OmJsb2NrfS53aG8gc21hbGx7Y29sb3I6dmFyKC0tdDMpfQoudGFne2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo2cHg7cGFkZGluZzozcHggMTBweDtib3JkZXItcmFkaXVzOjk5cHg7Zm9udC1zaXplOjEycHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7bWFyZ2luOjJweCAwIDJweCA0cHg7Zm9udC13ZWlnaHQ6NjAwfQouc3R7ZGlzcGxheTppbmxpbmUtZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjdweDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEzcHh9Ci5zLW9ue2NvbG9yOnZhcigtLWEpfS5zLXdhaXR7Y29sb3I6dmFyKC0tYil9LnMtZXhwe2NvbG9yOnZhcigtLXIpfS5zLW9mZntjb2xvcjp2YXIoLS10Myl9LnMtc29vbntjb2xvcjp2YXIoLS15KX0KLm9ubGluZXt3aWR0aDo4cHg7aGVpZ2h0OjhweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZhcigtLWEpO2JveC1zaGFkb3c6MCAwIDAgNHB4IHJnYmEoMCwyMTQsMTQzLC4xOCk7ZGlzcGxheTppbmxpbmUtYmxvY2t9Ci5lbXB0eXtwYWRkaW5nOjQwcHg7dGV4dC1hbGlnbjpjZW50ZXI7Y29sb3I6dmFyKC0tdDIpfQovKiBkcmF3ZXIgKi8KLnNjcmlte3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7YmFja2dyb3VuZDpyZ2JhKDAsMCwwLC41NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMnB4KTt6LWluZGV4OjIwO29wYWNpdHk6MDtwb2ludGVyLWV2ZW50czpub25lO3RyYW5zaXRpb246LjJzfQouc2NyaW0ub3BlbntvcGFjaXR5OjE7cG9pbnRlci1ldmVudHM6YXV0b30KLmRyYXdlcntwb3NpdGlvbjpmaXhlZDt0b3A6MDtib3R0b206MDtsZWZ0OjA7d2lkdGg6bWluKDUyMHB4LDEwMCUpO2JhY2tncm91bmQ6dmFyKC0tcCk7Ym9yZGVyLXJpZ2h0OjFweCBzb2xpZCB2YXIoLS1saW5lKTt6LWluZGV4OjIxO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC0xMDAlKTt0cmFuc2l0aW9uOi4yNXMgY3ViaWMtYmV6aWVyKC4yLC44LC4yLDEpO2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW47Ym94LXNoYWRvdzp2YXIoLS1zaCl9Ci5kcmF3ZXIub3Blbnt0cmFuc2Zvcm06bm9uZX0KLmRoe3BhZGRpbmc6MjBweCAyMnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXJ9Ci5kYntwYWRkaW5nOjZweCAyMnB4IDIycHg7b3ZlcmZsb3c6YXV0bztmbGV4OjF9LmRme3BhZGRpbmc6MTZweCAyMnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2Rpc3BsYXk6ZmxleDtnYXA6MTBweDtmbGV4LXdyYXA6d3JhcH0KLnNlY3ttYXJnaW4tdG9wOjIwcHg7cGFkZGluZzoxNnB4O2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNHB4O2JhY2tncm91bmQ6dmFyKC0tcDIpfQouc2VjIGgze21hcmdpbjowIDAgNHB4O2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLWEpO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweH0KbGFiZWx7ZGlzcGxheTpibG9jaztjb2xvcjp2YXIoLS10Mik7Zm9udC1zaXplOjEyLjVweDttYXJnaW46MTJweCAwIDVweDtmb250LXdlaWdodDo2MDB9CmlucHV0LHNlbGVjdHt3aWR0aDoxMDAlO2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXQpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxMHB4O3BhZGRpbmc6MTFweCAxMnB4O2ZvbnQtc2l6ZToxNXB4fQppbnB1dDpmb2N1cyxzZWxlY3Q6Zm9jdXN7b3V0bGluZToycHggc29saWQgdmFyKC0tYSk7Ym9yZGVyLWNvbG9yOnRyYW5zcGFyZW50fQouZ3JpZDJ7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDoxMHB4fS5xdWlja3tkaXNwbGF5OmZsZXg7Z2FwOjZweDttYXJnaW4tdG9wOjhweDtmbGV4LXdyYXA6d3JhcH0KLnhse2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47cGFkZGluZzo5cHggMTJweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTBweDttYXJnaW4tdG9wOjhweDtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLm1zZ3ttaW4taGVpZ2h0OjIycHg7bWFyZ2luLXRvcDoxMHB4O2ZvbnQtd2VpZ2h0OjYwMH0ub2t7Y29sb3I6dmFyKC0tYSl9LmJhZHtjb2xvcjp2YXIoLS1yKX0KLnN3aXRjaHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO21hcmdpbi10b3A6MTJweH0KLnRne3Bvc2l0aW9uOnJlbGF0aXZlO3dpZHRoOjQ2cHg7aGVpZ2h0OjI2cHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7Ym9yZGVyLXJhZGl1czo5OXB4O2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246LjJzO2JvcmRlcjowfQoudGc6OmFmdGVye2NvbnRlbnQ6IiI7cG9zaXRpb246YWJzb2x1dGU7dG9wOjNweDtyaWdodDozcHg7d2lkdGg6MjBweDtoZWlnaHQ6MjBweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOiNmZmY7dHJhbnNpdGlvbjouMnN9Ci50Zy5vbntiYWNrZ3JvdW5kOnZhcigtLWEpfS50Zy5vbjo6YWZ0ZXJ7cmlnaHQ6MjNweH0KLmxvZ2lue21heC13aWR0aDo0MjBweDttYXJnaW46MTJ2aCBhdXRvO3BhZGRpbmc6MjhweH0KLnRvYXN0e3Bvc2l0aW9uOmZpeGVkO2JvdHRvbToyMnB4O2xlZnQ6NTAlO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC01MCUpIHRyYW5zbGF0ZVkoMzBweCk7YmFja2dyb3VuZDp2YXIoLS1wMyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtwYWRkaW5nOjEycHggMThweDtib3JkZXItcmFkaXVzOjEycHg7b3BhY2l0eTowO3RyYW5zaXRpb246LjI1czt6LWluZGV4OjQwO2ZvbnQtd2VpZ2h0OjYwMH0KLnRvYXN0LnNob3d7b3BhY2l0eToxO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC01MCUpfQouaGVscHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdChhdXRvLWZpdCxtaW5tYXgoMjYwcHgsMWZyKSk7Z2FwOjE0cHh9Ci5oZWxwIC5jYXJke3BhZGRpbmc6MThweH0uaGVscCBvbHttYXJnaW46OHB4IDAgMDtwYWRkaW5nLWlubGluZS1zdGFydDoyMHB4O2NvbG9yOnZhcigtLXQyKX0KLnBpbGx7Zm9udC1zaXplOjExcHg7cGFkZGluZzoycHggOHB4O2JvcmRlci1yYWRpdXM6OTlweDtiYWNrZ3JvdW5kOnZhcigtLXAzKTtjb2xvcjp2YXIoLS10Mil9CkBtZWRpYSAobWF4LXdpZHRoOjgyMHB4KXsuc2hlbGx7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmcn1hc2lkZXtwb3NpdGlvbjpzdGF0aWM7aGVpZ2h0OmF1dG87ZmxleC1kaXJlY3Rpb246cm93O292ZXJmbG93LXg6YXV0bztwYWRkaW5nOjEwcHg7Ym9yZGVyOjA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSl9CiAuYnJhbmR7cGFkZGluZzo2cHggMTBweH0ubmF2e3dpZHRoOmF1dG87d2hpdGUtc3BhY2U6bm93cmFwfS5zcGFjZXJ7ZGlzcGxheTpub25lfW1haW57cGFkZGluZzoxOHB4IDE0cHh9LnNlYXJjaHttaW4td2lkdGg6MDtmbGV4OjF9CiAuaGlkZS1te2Rpc3BsYXk6bm9uZX10aCx0ZHtwYWRkaW5nOjEwcHggOHB4fX0KLm5vd29uLC5ub3dvZmZ7ZGlzcGxheTpibG9jazttYXJnaW4tdG9wOjRweDtmb250LXNpemU6MTJweDtsaW5lLWhlaWdodDoxLjU7d2hpdGUtc3BhY2U6bm9ybWFsfS5ub3dvbntjb2xvcjp2YXIoLS1hKX0ubm93b2Zme2NvbG9yOnZhcigtLXQzKX0ud2hlcmV7ZGlzcGxheTpibG9jazttYXJnaW4tdG9wOjJweH0udnBub257Y29sb3I6IzJlOWQ1Yjtmb250LXdlaWdodDo2MDB9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PgoKPGRpdiBpZD0ibG9naW4iIGNsYXNzPSJjYXJkIGxvZ2luIGhpZGUiPgogIDxkaXYgY2xhc3M9ImJyYW5kIiBzdHlsZT0icGFkZGluZzowIDAgMTBweCI+U0FVREk8Yj4uVFY8L2I+PC9kaXY+CiAgPGgyIGlkPSJsdCI+2K/YrtmI2YQg2YTZiNit2Kkg2KfZhNil2K/Yp9ix2Kk8L2gyPjxwIGlkPSJsaCIgY2xhc3M9Im11dGVkIj48L3A+CiAgPGxhYmVsPtmD2YTZhdipINin2YTYs9ixPC9sYWJlbD48aW5wdXQgaWQ9InB3IiB0eXBlPSJwYXNzd29yZCIgYXV0b2NvbXBsZXRlPSJjdXJyZW50LXBhc3N3b3JkIj4KICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxidXR0b24gaWQ9ImdvIiBjbGFzcz0iYnRuIiBzdHlsZT0id2lkdGg6MTAwJTtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyIj7Yr9iu2YjZhDwvYnV0dG9uPjwvZGl2PjxkaXYgaWQ9ImxtIiBjbGFzcz0ibXNnIGJhZCI+PC9kaXY+CjwvZGl2PgoKPGRpdiBpZD0iYXBwIiBjbGFzcz0ic2hlbGwgaGlkZSI+CiAgPGFzaWRlPgogICAgPGRpdiBjbGFzcz0iYnJhbmQiPlNBVURJPGI+LlRWPC9iPjwvZGl2PgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IG9uIiBkYXRhLXY9ImRhc2giPjxzcGFuIGNsYXNzPSJpYyI+4penPC9zcGFuPiDZhNmI2K3YqSDYp9mE2KrYrdmD2YU8L2J1dHRvbj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgZGF0YS12PSJkZXZzIj48c3BhbiBjbGFzcz0iaWMiPuKWpDwvc3Bhbj4g2KfZhNij2KzZh9iy2Kk8L2J1dHRvbj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgZGF0YS12PSJwcm9tbyI+PHNwYW4gY2xhc3M9ImljIj7wn46fPC9zcGFuPiBQcm9tbyBjb2RlczwvYnV0dG9uPgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IiBkYXRhLXY9InBheSI+PHNwYW4gY2xhc3M9ImljIj7wn5KzPC9zcGFuPiDYp9mE2K/Zgdi5PC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJuYXYiIGRhdGEtdj0iaGVscCI+PHNwYW4gY2xhc3M9ImljIj4/PC9zcGFuPiDYt9ix2YrZgtipINin2YTYp9iz2KrYrtiv2KfZhTwvYnV0dG9uPgogICAgPGRpdiBjbGFzcz0ic3BhY2VyIj48L2Rpdj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgaWQ9Im91dCI+PHNwYW4gY2xhc3M9ImljIj7ijos8L3NwYW4+INiu2LHZiNisPC9idXR0b24+CiAgPC9hc2lkZT4KICA8bWFpbj4KICAgIDxkaXYgY2xhc3M9InRvcCI+CiAgICAgIDxkaXY+PGgxIGlkPSJ2dCI+2YTZiNit2Kkg2KfZhNiq2K3Zg9mFPC9oMT48cCBjbGFzcz0ic3ViIiBpZD0idnMiPtmG2LjYsdipINiz2LHZiti52Kkg2LnZhNmJINmD2YQg2KfZhNij2KzZh9iy2Kk8L3A+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InRvb2xzIj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGlkPSJyZWZyZXNoIj7in7Mg2KrYrdiv2YrYqzwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biIgaWQ9ImFkZCI+77yLINis2YfYp9iyINis2K/ZitivPC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KCiAgICA8c2VjdGlvbiBpZD0idi1kYXNoIj4KICAgICAgPGRpdiBjbGFzcz0ic3RhdHMiIGlkPSJzdGF0cyI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtaCI+PGgyPtmK2K3Yqtin2Kwg2KfZhtiq2KjYp9mH2YM8L2gyPjxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9ImF0dG4tbiI+PC9zcGFuPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9IndyYXAiPjx0YWJsZT48dGJvZHkgaWQ9ImF0dG4iPjwvdGJvZHk+PC90YWJsZT48L2Rpdj4KICAgICAgPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtaCI+PGgyPti12K3YqSDYp9mE2KrYt9io2YrZgjwvaDI+PHNwYW4gY2xhc3M9Im11dGVkIiBpZD0iaGwtbiI+PC9zcGFuPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgaWQ9ImhsLWNsciI+2YXYs9itPC9idXR0b24+PC9kaXY+CiAgICAgICAgPHAgY2xhc3M9Im11dGVkIj7Zg9mEINmF2LHYqSDYp9mE2KrYt9io2YrZgiDYqNmK2KrYs9mD2ZHYsSDYqNiu2LfYoyDYo9mIINin2YTYtNin2LTYqSDYqNiq2LnZhNmCINi52YTZiSDYo9mKINis2YfYp9iy2Iwg2KjZitmI2LXZhCDZh9mI2YYg2YTYrdin2YTZhyDYtNmIINi12KfYsS48L3A+CiAgICAgICAgPGRpdiBjbGFzcz0id3JhcCI+PHRhYmxlPjx0Ym9keSBpZD0iaGwiPjwvdGJvZHk+PC90YWJsZT48L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CgogICAgPHNlY3Rpb24gaWQ9InYtZGV2cyIgY2xhc3M9ImhpZGUiPgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPgogICAgICAgICAgPGRpdiBjbGFzcz0idG9vbHMiIGlkPSJjaGlwcyI+PC9kaXY+CiAgICAgICAgICA8aW5wdXQgY2xhc3M9InNlYXJjaCIgaWQ9InEiIHBsYWNlaG9sZGVyPSLYqNit2Ks6INmD2YjYr9iMINin2LPZhdiMIHBsYXlsaXN04oCmIj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJ3cmFwIj48dGFibGU+CiAgICAgICAgICA8dGhlYWQ+PHRyPjx0aD7Yp9mE2YPZiNivPC90aD48dGg+2KfZhNiy2KjZiNmGPC90aD48dGg+UGxheWxpc3RzPC90aD48dGg+2KfZhNit2KfZhNipPC90aD48dGggY2xhc3M9ImhpZGUtbSI+2KLYrtixINi42YfZiNixPC90aD48dGggY2xhc3M9ImhpZGUtbSI+2YrZhtiq2YfZijwvdGg+PC90cj48L3RoZWFkPgogICAgICAgICAgPHRib2R5IGlkPSJ0YiI+PC90Ym9keT48L3RhYmxlPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBpZD0idi1wcm9tbyIgY2xhc3M9ImhpZGUiPgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPjxoMj7Zg9mI2K8g2KzYr9mK2K88L2gyPjxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9InByb21vLW4iPjwvc3Bhbj48L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJwYWRkaW5nOjE0cHggMThweDtkaXNwbGF5OmZsZXg7Z2FwOjEwcHg7ZmxleC13cmFwOndyYXA7YWxpZ24taXRlbXM6ZW5kIj4KICAgICAgICAgIDxkaXY+PGxhYmVsPtmE2YXZitmG2J8gKNmF2YTYp9it2LjYqSDYpdmE2YMpPC9sYWJlbD48aW5wdXQgaWQ9InBub3RlIiBwbGFjZWhvbGRlcj0i2YXYq9mE2KfZizog2KPYqNmIINij2K3ZhdivIj48L2Rpdj4KICAgICAgICAgIDxkaXY+PGxhYmVsPtin2YTYudiv2K88L2xhYmVsPjxzZWxlY3QgaWQ9InBjb3VudCI+PG9wdGlvbj4xPC9vcHRpb24+PG9wdGlvbj4zPC9vcHRpb24+PG9wdGlvbj41PC9vcHRpb24+PG9wdGlvbj4xMDwvb3B0aW9uPjwvc2VsZWN0PjwvZGl2PgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0icGdlbiI+77yLINij2LXYr9ixPC9idXR0b24+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0id3JhcCI+PHRhYmxlPgogICAgICAgICAgPHRoZWFkPjx0cj48dGg+2KfZhNmD2YjYrzwvdGg+PHRoPtmE2YXZitmGPC90aD48dGg+2KfZhNit2KfZhNipPC90aD48dGg+PC90aD48L3RyPjwvdGhlYWQ+CiAgICAgICAgICA8dGJvZHkgaWQ9InB0YiI+PC90Ym9keT48L3RhYmxlPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBpZD0idi1wYXkiIGNsYXNzPSJoaWRlIj4KICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1oIj48aDI+2KfZhNiv2YHYuSDYr9in2K7ZhCDYp9mE2KrYt9io2YrZgjwvaDI+PHNwYW4gY2xhc3M9Im11dGVkIiBpZD0icGF5LXN0Ij48L3NwYW4+PC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0icGFkZGluZzoxNHB4IDE4cHg7bWF4LXdpZHRoOjY0MHB4Ij4KICAgICAgICAgIDxwIGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxMy41cHg7bGluZS1oZWlnaHQ6MS44Ij7Yp9mE2YTZiiDZhdinINi52YbYr9mHIFByb21vIGNvZGUg2KjZiti02YjZgSDYudmE2Ykg2LTYp9i02Kkg2KfZhNiq2YHYudmK2YQg2LLYsSDCq0J1eSBhY2Nlc3PCuyDZhdi5IFFSLiDYqNmK2YHYqtitINmF2YYg2KrZhNmB2YjZhtmHINi12YHYrdipINmB2YrZh9inINmD2YjYryDYrNmH2KfYstmHINmI2KfZhNiz2LnYsSDZiNiy2LEgPGI+UGF5IHdpdGggVmVubW88L2I+2Iwg2YjYp9mE2YXYqNmE2Log2YjYp9mE2YXZhNin2K3YuNipICjZg9mI2K8g2KfZhNis2YfYp9iyKSDZhdi52KjZkdmK2YrZhiDZhNit2KfZhNmH2YUuINmE2YXYpyDYqtmI2LXZhNmDINin2YTYr9mB2LnYqSDYudmE2YkgVmVubW/YjCDYp9mE2YXZhNin2K3YuNipINmB2YrZh9inINmD2YjYryDYp9mE2KzZh9in2LI6INmB2LnZkdmE2Ycg2YXZhiDCq9in2YTYo9is2YfYstipwrsg2LLZiiDYp9mE2LnYp9iv2KkuPC9wPgogICAgICAgICAgPGxhYmVsPtin2YTYs9i52LEg2KfZhNmE2Yog2KjZiti42YfYsSDZhNmE2LLYqNmI2YYgKNix2YLZhSDYqNin2YTYr9mI2YTYp9ixKTwvbGFiZWw+PGlucHV0IGlkPSJwYXktcHJpY2UiIHBsYWNlaG9sZGVyPSIyNTAiIHN0eWxlPSJkaXJlY3Rpb246bHRyO3RleHQtYWxpZ246bGVmdCI+CiAgICAgICAgICA8bGFiZWw+2KfYs9mFINin2YTZhdiz2KrYrtiv2YUg2LnZhNmJIFZlbm1vICjYqNiv2YjZhiBAKTwvbGFiZWw+PGlucHV0IGlkPSJwYXktbGluayIgcGxhY2Vob2xkZXI9IlNhaWYtU2F1ZGkiIHN0eWxlPSJkaXJlY3Rpb246bHRyO3RleHQtYWxpZ246bGVmdCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzd2l0Y2giPjxzcGFuPtin2YTYr9mB2Lkg2LTYutmR2KfZhDwvc3Bhbj48YnV0dG9uIGNsYXNzPSJ0ZyIgaWQ9InBheS1vbiIgdHlwZT0iYnV0dG9uIj48L2J1dHRvbj48L2Rpdj4KICAgICAgICAgIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+PGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0icGF5LXNhdmUiPtit2YHYuDwvYnV0dG9uPiA8c3BhbiBjbGFzcz0ibXV0ZWQiIGlkPSJwYXktbXNnIj48L3NwYW4+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgoKICAgIDxzZWN0aW9uIGlkPSJ2LWhlbHAiIGNsYXNzPSJoaWRlIj4KICAgICAgPGRpdiBjbGFzcz0iaGVscCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+PGgyPtiy2KjZiNmGINis2K/ZitivPC9oMj48b2w+PGxpPtin2YTYstio2YjZhiDZitmG2LLZkdmEIFNBVURJLlRWINmF2YYgRG93bmxvYWRlciDZiNmK2YHYqtit2YcuPC9saT48bGk+2KjZiti32YTYuSDYudmE2Ykg2LTYp9i02KrZhyDZg9mI2K8g2YXZhiA4INij2LHZgtin2YUuPC9saT48bGk+2YfZiNmGOiDvvIsg2KzZh9in2LIg2KzYr9mK2K8g4oaQINin2YPYqtioINin2YTZg9mI2K8g2YjYp9mE2KfYs9mFINmI2KfZhNmAIHBsYXlsaXN0INmI2KfZhNmK2YjYstixLjwvbGk+PGxpPtin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQg4oCUINiu2YTYtS48L2xpPjwvb2w+PC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+PGgyPtij2YPYq9ixINmF2YYgcGxheWxpc3Q8L2gyPjxvbD48bGk+2KfZgdiq2K0g2KfZhNis2YfYp9iyIOKGkCDZgtiz2YUgwqtQbGF5bGlzdHMg2KXYttin2YHZitipwrsuPC9saT48bGk+2KfYrtiq2KfYsSDYp9mE2YAgcGxheWxpc3Qg2YjYp9mD2KrYqCDYp9mE2YrZiNiy2LEg2YjYp9mE2KjYp9iz2YjZiNix2K8g4oaQINij2LbZgS48L2xpPjxsaT7Yp9mE2LLYqNmI2YYg2KjZitiu2KrYp9ixINio2YrZhtmH2YUg2YXZhiDCq1BsYXlsaXN0c8K7INio2KfZhNiq2LfYqNmK2YIuPC9saT48L29sPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxoMj7Yqtis2K/ZitivINmI2KXZitmC2KfZgTwvaDI+PG9sPjxsaT7Yp9mB2KrYrSDYp9mE2KzZh9in2LIg4oaQINij2LLYsdin2LEgKzMwIC8gKzkwIC8gKzM2NSDZitmI2YUuPC9saT48bGk+wqvYp9mE2KzZh9in2LIg2LTYutmR2KfZhMK7INiq2LfZgdmK2Ycg2KjZitmI2YLZgSDYp9mE2K7Yr9mF2Kkg2YHZiNix2KfZiyDYudmG2K8g2KfZhNiy2KjZiNmGLjwvbGk+PGxpPtin2YTYo9is2YfYstipINin2YTZhNmKINio2KrZhtiq2YfZiiDYrtmE2KfZhCA3INij2YrYp9mFINio2KrYt9mE2Lkg2KjYp9mE2KPYtdmB2LEuPC9saT48L29sPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxoMj7Yp9mE2KPZhdin2YY8L2gyPjxvbD48bGk+2KfZhNmK2YjYstixINmI2KfZhNio2KfYs9mI2YjYsdivINmF2K3ZgdmI2LjZitmGINmF2LTZgdmR2LHZitmGLjwvbGk+PGxpPtin2YTYqNin2LPZiNmI2LHYryDZhdinINio2YrYsdis2Lkg2YrYuNmH2LEg2YfZiNmGINij2KjYr9in2Ysg4oCUINin2KrYsdmD2Ycg2YHYp9i22Yog2YTZitio2YLZiSDYp9mE2YLYr9mK2YUuPC9saT48bGk+2LHYp9io2Lcg2KfZhNiq2LfYqNmK2YI6IDxzcGFuIGNsYXNzPSJjb2RlIj5zYXVkaTEuMXNhaWZzYXVkaS53b3JrZXJzLmRldi9hcGs8L3NwYW4+PC9saT48L29sPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KICA8L21haW4+CjwvZGl2PgoKPGRpdiBjbGFzcz0ic2NyaW0iIGlkPSJzY3JpbSI+PC9kaXY+CjxkaXYgY2xhc3M9ImRyYXdlciIgaWQ9ImRyYXdlciI+CiAgPGRpdiBjbGFzcz0iZGgiPjxkaXY+PGgyIGlkPSJkdCI+2KzZh9in2LIg2KzYr9mK2K88L2gyPjxkaXYgY2xhc3M9Im11dGVkIiBpZD0iZHN1YiI+PC9kaXY+PC9kaXY+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBpZD0iZHgiPuKclTwvYnV0dG9uPjwvZGl2PgogIDxkaXYgY2xhc3M9ImRiIj4KICAgIDxkaXYgY2xhc3M9InNlYyI+CiAgICAgIDxoMz7ikaAg2KfZhNis2YfYp9iyINmI2KfZhNiy2KjZiNmGPC9oMz4KICAgICAgPGxhYmVsPtmD2YjYryDYp9mE2KzZh9in2LIgKDgg2KPYsdmC2KfZhSDZhdmGINi02KfYtNipINin2YTYstio2YjZhik8L2xhYmVsPjxpbnB1dCBpZD0iY29kZSIgaW5wdXRtb2RlPSJudW1lcmljIiBtYXhsZW5ndGg9IjkiIHBsYWNlaG9sZGVyPSIxMjM0IDU2NzgiIGNsYXNzPSJjb2RlIiBzdHlsZT0idGV4dC1hbGlnbjpyaWdodCI+CiAgICAgIDxsYWJlbD7Yp9iz2YUg2KfZhNiy2KjZiNmGPC9sYWJlbD48aW5wdXQgaWQ9Im5hbWUiIHBsYWNlaG9sZGVyPSLZhdir2YTYp9mLOiDYo9io2Ygg2KPYrdmF2K8iPiAgICAgICA8bGFiZWw+2KfZhNin2LPZhSDYudmE2Ykg2LTYp9i02Kkg2KfZhNiq2LHYrdmK2KggKFdlbGNvbWUg4oCmKTwvbGFiZWw+PGlucHV0IGlkPSJ3bmFtZSIgcGxhY2Vob2xkZXI9ItmF2KvZhNin2Ys6IExhaXRoIiBtYXhsZW5ndGg9IjMwIj4KICAgICAgPGRpdiBjbGFzcz0ic3dpdGNoIj48c3Bhbj7Yp9mE2KzZh9in2LIg2LTYutmR2KfZhDwvc3Bhbj48YnV0dG9uIGNsYXNzPSJ0ZyBvbiIgaWQ9ImFjdCIgdHlwZT0iYnV0dG9uIj48L2J1dHRvbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2VjIj4KICAgICAgPGgzPuKRoSDYp9mE2YAgUGxheWxpc3Qg2KfZhNij2LPYp9iz2YrYqTwvaDM+CiAgICAgIDxsYWJlbD5QbGF5bGlzdDwvbGFiZWw+PHNlbGVjdCBpZD0icGwiPjwvc2VsZWN0PgogICAgICA8ZGl2IGNsYXNzPSJncmlkMiI+CiAgICAgICAgPGRpdj48bGFiZWw+2KfZhNmK2YjYstixPC9sYWJlbD48aW5wdXQgaWQ9InUiIGF1dG9jb21wbGV0ZT0ib2ZmIj48L2Rpdj4KICAgICAgICA8ZGl2PjxsYWJlbD7Yp9mE2KjYp9iz2YjZiNix2K88L2xhYmVsPjxpbnB1dCBpZD0icCIgdHlwZT0icGFzc3dvcmQiIGF1dG9jb21wbGV0ZT0ibmV3LXBhc3N3b3JkIj48L2Rpdj4KICAgICAgPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9Im11dGVkIiBpZD0ibGhpbnQiIHN0eWxlPSJmb250LXNpemU6MTIuNXB4O21hcmdpbi10b3A6NnB4Ij48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2VjIj4KICAgICAgPGgzPuKRoiDYp9mE2KfYtNiq2LHYp9mDPC9oMz4KICAgICAgPGxhYmVsPtmK2YbYqtmH2Yog2KjYqtin2LHZitiuICjZgdin2LbZiiA9INio2K/ZiNmGINin2YbYqtmH2KfYoSk8L2xhYmVsPjxpbnB1dCBpZD0iZXgiIHR5cGU9ImRhdGUiPgogICAgICA8ZGl2IGNsYXNzPSJxdWljayI+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWFkZD0iMzAiPiszMCDZitmI2YU8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSI5MCI+KzkwINmK2YjZhTwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjE4MCI+KzYg2LTZh9mI2LE8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSIzNjUiPivYs9mG2Kk8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSIwIj7YqNiv2YjZhiDYp9mG2KrZh9in2KE8L2J1dHRvbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2VjIiBpZD0ieHNlYyI+CiAgICAgIDxoMz7ikaMgUGxheWxpc3RzINil2LbYp9mB2YrYqTwvaDM+CiAgICAgIDxkaXYgaWQ9InhsaXN0Ij48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iZ3JpZDIiIHN0eWxlPSJtYXJnaW4tdG9wOjZweCI+PGRpdj48bGFiZWw+UGxheWxpc3Q8L2xhYmVsPjxzZWxlY3QgaWQ9InhwbCI+PC9zZWxlY3Q+PC9kaXY+PGRpdj48L2Rpdj4KICAgICAgICA8ZGl2PjxsYWJlbD7Yp9mE2YrZiNiy2LE8L2xhYmVsPjxpbnB1dCBpZD0ieHUiIGF1dG9jb21wbGV0ZT0ib2ZmIj48L2Rpdj48ZGl2PjxsYWJlbD7Yp9mE2KjYp9iz2YjZiNix2K88L2xhYmVsPjxpbnB1dCBpZD0ieHAiIHR5cGU9InBhc3N3b3JkIiBhdXRvY29tcGxldGU9Im5ldy1wYXNzd29yZCI+PC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6MTBweCI+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBpZD0ieGFkZCI+77yLINij2LbZgSBwbGF5bGlzdDwvYnV0dG9uPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzZWMiIGlkPSJ2c2VjIj4KICAgICAgPGgzPuKRpCBWUE4gwrcgUHJvdG9uICjZhdis2KfZhtmKKTwvaDM+CiAgICAgIDxkaXYgY2xhc3M9Im11dGVkIiBzdHlsZT0iZm9udC1zaXplOjEyLjVweDtsaW5lLWhlaWdodDoxLjciPtmE2YPZhCDYrNmH2KfYsiDYrdiz2KfYqCBQcm90b24g2YXYrNin2YbZiiDYrtin2LUg2YHZitmHOiA8Yj5hY2NvdW50LnByb3RvbnZwbi5jb208L2I+IOKGkCBEb3dubG9hZHMg4oaQIDxiPldpcmVHdWFyZCBjb25maWd1cmF0aW9uPC9iPiDihpAgUGxhdGZvcm06IEFuZHJvaWQg4oaQINiz2YrYsdmB2LEg2YXYrNin2YbZiiAoRnJlZSkg4oaQIENyZWF0ZSDihpAgRG93bmxvYWQuINin2YHYqtitINin2YTZhdmE2YEgKOKAji5jb25mKSDZiNin2YTYtdmCINmD2YQg2KfZhNmE2Yog2YHZitmHINmH2YjZhi4g2KfZhNij2KzZh9iy2Kkg2KfZhNmE2Yog2YXYpyDYpdmE2YfYpyBWUE4g2YfZiNmGINmF2Kcg2KjZiti42YfYsdmE2YfYpyDYrtmK2KfYsSBWUE4g2KPYqNiv2KfZiy48L2Rpdj4KICAgICAgPGRpdiBpZD0idnN0YXRlIiBzdHlsZT0ibWFyZ2luLXRvcDo4cHg7Zm9udC1zaXplOjEzcHgiPjwvZGl2PgogICAgICA8dGV4dGFyZWEgaWQ9InZjb25mIiByb3dzPSI3IiBzcGVsbGNoZWNrPSJmYWxzZSIgcGxhY2Vob2xkZXI9IltJbnRlcmZhY2VdJiMxMDtQcml2YXRlS2V5ID0g4oCmJiMxMDtBZGRyZXNzID0gMTAuMi4wLjIvMzImIzEwOyYjMTA7W1BlZXJdJiMxMDtQdWJsaWNLZXkgPSDigKYmIzEwO0VuZHBvaW50ID0g4oCmOjUxODIwIiBzdHlsZT0id2lkdGg6MTAwJTttYXJnaW4tdG9wOjhweDtkaXJlY3Rpb246bHRyO3RleHQtYWxpZ246bGVmdDtmb250LWZhbWlseTptb25vc3BhY2U7Zm9udC1zaXplOjEycHgiPjwvdGV4dGFyZWE+CiAgICAgIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6OHB4O2Rpc3BsYXk6ZmxleDtnYXA6MTBweCI+CiAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIHNtIiBpZD0idnNhdmUiPtit2YHYuCDYp9mE2YAgVlBOPC9idXR0b24+CiAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBpZD0idmRlbCI+2LTZitmEINin2YTZgCBWUE48L2J1dHRvbj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ibXNnIiBpZD0ic20iPjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImRmIj48YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJzYXZlIj7YrdmB2Lg8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIGlkPSJjYW5jZWwiPtil2YTYutin2KE8L2J1dHRvbj48c3BhbiBjbGFzcz0ic3BhY2VyIiBzdHlsZT0iZmxleDoxIj48L3NwYW4+PGJ1dHRvbiBjbGFzcz0iYnRuIHJlZCBoaWRlIiBpZD0iZGVsIj7Yrdiw2YEg2KfZhNis2YfYp9iyPC9idXR0b24+PC9kaXY+CjwvZGl2Pgo8ZGl2IGNsYXNzPSJ0b2FzdCIgaWQ9InRvYXN0Ij48L2Rpdj4KCjxzY3JpcHQ+CmNvbnN0ICQgPSAoaWQpID0+IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTsKY29uc3QgYXBpID0gKHAsIGIpID0+IGZldGNoKCcvYWRtaW4vYXBpLycgKyBwLCBiID8geyBtZXRob2Q6ICdQT1NUJywgaGVhZGVyczogeyAnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nIH0sIGJvZHk6IEpTT04uc3RyaW5naWZ5KGIpLCBjcmVkZW50aWFsczogJ3NhbWUtb3JpZ2luJyB9IDogeyBjcmVkZW50aWFsczogJ3NhbWUtb3JpZ2luJyB9KQogIC50aGVuKGFzeW5jIChyKSA9PiAoeyBvazogci5vaywgLi4uKGF3YWl0IHIuanNvbigpLmNhdGNoKCgpID0+ICh7fSkpKSB9KSk7CmNvbnN0IGVzYyA9IChzKSA9PiBTdHJpbmcocyA/PyAnJykucmVwbGFjZSgvWyY8PiInXS9nLCAoYykgPT4gKHsgJyYnOiAnJmFtcDsnLCAnPCc6ICcmbHQ7JywgJz4nOiAnJmd0OycsICciJzogJyZxdW90OycsICInIjogJyYjMzk7JyB9W2NdKSk7CmNvbnN0IERBWSA9IDg2NDAwMDAwOwpjb25zdCBhZ28gPSAodCkgPT4geyBpZiAoIXQpIHJldHVybiAn4oCUJzsgY29uc3QgbSA9IE1hdGgucm91bmQoKERhdGUubm93KCkgLSB0KSAvIDYwMDAwKTsgcmV0dXJuIG0gPCAxID8gJ9in2YTYotmGJyA6IG0gPCA2MCA/IGAke219INiv2YLZitmC2KlgIDogbSA8IDE0NDAgPyBgJHtNYXRoLnJvdW5kKG0gLyA2MCl9INiz2KfYudipYCA6IGAke01hdGgucm91bmQobSAvIDE0NDApfSDZitmI2YVgOyB9Owpjb25zdCBkYXkgPSAodCkgPT4gdCA/IG5ldyBEYXRlKHQpLnRvSVNPU3RyaW5nKCkuc2xpY2UoMCwgMTApIDogJyc7CmNvbnN0IHByZXR0eSA9IChjKSA9PiBjLnJlcGxhY2UoLyhcZHs0fSkoXGR7NH0pLywgJyQxICQyJyk7CmxldCBkZXZzID0gW10sIHBsYXlsaXN0cyA9IFtdLCBmaWx0ZXIgPSAnYWxsJywgZWRpdGluZyA9IG51bGw7CgpmdW5jdGlvbiB0b2FzdCh0KSB7IGNvbnN0IGUgPSAkKCd0b2FzdCcpOyBlLnRleHRDb250ZW50ID0gdDsgZS5jbGFzc0xpc3QuYWRkKCdzaG93Jyk7IGNsZWFyVGltZW91dChlLl90KTsgZS5fdCA9IHNldFRpbWVvdXQoKCkgPT4gZS5jbGFzc0xpc3QucmVtb3ZlKCdzaG93JyksIDI2MDApOyB9CgpmdW5jdGlvbiBzdGF0ZShkKSB7CiAgY29uc3Qgbm93ID0gRGF0ZS5ub3coKTsKICBpZiAoIWQuYWN0aXZlKSByZXR1cm4geyBrOiAnb2ZmJywgdDogJ9mF2YjZgtmI2YEnIH07CiAgaWYgKGQuZXhwaXJlcyAmJiBkLmV4cGlyZXMgPCBub3cpIHJldHVybiB7IGs6ICdleHAnLCB0OiAn2YXZhtiq2YfZiicgfTsKICBpZiAoIWQuaGFzX2xvZ2luIHx8ICFkLnBsYXlsaXN0KSByZXR1cm4geyBrOiAnd2FpdCcsIHQ6ICfYqNin2YbYqti42KfYsSDYp9mE2KrZgdi52YrZhCcgfTsKICBpZiAoZC5leHBpcmVzICYmIGQuZXhwaXJlcyAtIG5vdyA8IDcgKiBEQVkpIHJldHVybiB7IGs6ICdzb29uJywgdDogYNmK2YbYqtmH2Yog2K7ZhNin2YQgJHtNYXRoLm1heCgxLCBNYXRoLmNlaWwoKGQuZXhwaXJlcyAtIG5vdykgLyBEQVkpKX0g2YrZiNmFYCB9OwogIHJldHVybiB7IGs6ICdvbicsIHQ6ICfYtNi62ZHYp9mEJyB9Owp9CmNvbnN0IGlzT25saW5lID0gKGQpID0+IGQuc2VlbiAmJiBEYXRlLm5vdygpIC0gZC5zZWVuIDwgMjAgKiA2MDAwMDsKLy8gd2hhdCB0aGUgZGV2aWNlIGlzIHdhdGNoaW5nIG5vdyAodG9sZCBieSB0aGUgYXBwIGV2ZXJ5IDEwMCBzKSBvciB3YXRjaGVkIGxhc3QKY29uc3QgS0lORCA9IHsgbGl2ZTogJ/Cfk7onLCBtb3ZpZTogJ/CfjqwnLCBzZXJpZXM6ICfwn46eJywgcmVjb3JkaW5nOiAn4o+6JywgdmlkZW86ICfilrYnIH07CmNvbnN0IGlzV2F0Y2hpbmcgPSAoZCkgPT4gZC5ub3dfdCAmJiBEYXRlLm5vdygpIC0gZC5ub3dfdCA8IDQgKiA2MDAwMDsKLy8gd2hlcmUgdGhlIGRldmljZSBpcyBub3csIGZyb20gaXRzIGludGVybmV0OiBmbGFnICsgY291bnRyeSArIGNpdHksIGFuZCDwn5SSIHdoZW4gaXQgY29tZXMgdGhyb3VnaCBvdXIgVlBOCmNvbnN0IGZsYWcgPSAoYykgPT4gYyAmJiBjLmxlbmd0aCA9PT0gMiA/IFN0cmluZy5mcm9tQ29kZVBvaW50KC4uLlsuLi5jLnRvVXBwZXJDYXNlKCldLm1hcCgoeCkgPT4gMTI3Mzk3ICsgeC5jaGFyQ29kZUF0KDApKSkgOiAnJzsKZnVuY3Rpb24gd2hlcmUoZCkgewogIGlmICghZC5jb3VudHJ5KSByZXR1cm4gJyc7CiAgbGV0IG4gPSBkLmNvdW50cnk7IHRyeSB7IG4gPSBuZXcgSW50bC5EaXNwbGF5TmFtZXMoWydhciddLCB7IHR5cGU6ICdyZWdpb24nIH0pLm9mKGQuY291bnRyeSkgfHwgZC5jb3VudHJ5OyB9IGNhdGNoIChlKSB7fQogIGNvbnN0IHYgPSBkLm9uX3ZwbiA/ICcgPHNwYW4gY2xhc3M9InZwbm9uIj7wn5SSIFZQTiDYtNi62ZHYp9mEIChQcm90b24pPC9zcGFuPicgOiBkLmhhc192cG4gPyAnIDxzcGFuIGNsYXNzPSJtdXRlZCI+wrcgVlBOINmF2LfZgdmKPC9zcGFuPicgOiAnJzsKICByZXR1cm4gYDxzbWFsbCBjbGFzcz0id2hlcmUiPvCfk40gJHtmbGFnKGQuY291bnRyeSl9ICR7ZXNjKG4pfSR7ZC5jaXR5ID8gJyDCtyAnICsgZXNjKGQuY2l0eSkgOiAnJ30ke3Z9PC9zbWFsbD5gOwp9CmZ1bmN0aW9uIHdhdGNoaW5nKGQpIHsKICBpZiAoIWQubm93X3QgfHwgIWQubm93X3RpdGxlKSByZXR1cm4gJyc7CiAgY29uc3Qgd2hhdCA9IGAke0tJTkRbZC5ub3dfa2luZF0gfHwgJ+KWtid9ICR7ZXNjKGQubm93X3RpdGxlKX0ke2Qubm93X3BsYXlsaXN0ID8gJyA8c3BhbiBjbGFzcz0ibXV0ZWQiPsK3ICcgKyBlc2MoZC5ub3dfcGxheWxpc3QpICsgJzwvc3Bhbj4nIDogJyd9YDsKICByZXR1cm4gaXNXYXRjaGluZyhkKSA/IGA8c21hbGwgY2xhc3M9Im5vd29uIj48c3BhbiBjbGFzcz0ib25saW5lIj48L3NwYW4+2YrYtNin2YfYryDYp9mE2KLZhjogJHt3aGF0fTwvc21hbGw+YCA6IGA8c21hbGwgY2xhc3M9Im5vd29mZiI+2KLYrtixINmF2LTYp9mH2K/YqSAo2YLYqNmEICR7YWdvKGQubm93X3QpfSk6ICR7d2hhdH08L3NtYWxsPmA7Cn0KCmFzeW5jIGZ1bmN0aW9uIGluaXQoKSB7CiAgY29uc3QgcyA9IGF3YWl0IGFwaSgnc3RhdGUnKTsKICBwbGF5bGlzdHMgPSBzLnBsYXlsaXN0cyB8fCBbXTsKICBjb25zdCBvcHRzID0gcGxheWxpc3RzLm1hcCgocCkgPT4gYDxvcHRpb24gdmFsdWU9IiR7ZXNjKHApfSI+JHtlc2MocCl9PC9vcHRpb24+YCkuam9pbignJyk7CiAgJCgncGwnKS5pbm5lckhUTUwgPSBvcHRzOyAkKCd4cGwnKS5pbm5lckhUTUwgPSBvcHRzOwogIGlmIChzLnNpZ25lZCkgcmV0dXJuIHNob3coKTsKICAkKCdsb2dpbicpLmNsYXNzTGlzdC5yZW1vdmUoJ2hpZGUnKTsKICBpZiAocy5zZXR1cCkgeyAkKCdsdCcpLnRleHRDb250ZW50ID0gJ9ij2YjZhCDZhdix2Kk6INin2K7Yqtin2LEg2YPZhNmF2Kkg2LPYsSDZhNmE2KXYr9in2LHYqSc7ICQoJ2xoJykudGV4dENvbnRlbnQgPSAnOCDYo9it2LHZgSDYudmE2Ykg2KfZhNij2YLZhC4g2YfYp9mKINin2YTZg9mE2YXYqSDYqNiq2K/YrtmE2YMg2LnZhNmJINin2YTZhdmI2YLYuSDZhdmGINij2Yog2KzZh9in2LIuJzsgJCgncHcnKS5hdXRvY29tcGxldGUgPSAnbmV3LXBhc3N3b3JkJzsgfQogICQoJ3B3JykuZm9jdXMoKTsKfQokKCdnbycpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgnbG9naW4nLCB7IHBhc3N3b3JkOiAkKCdwdycpLnZhbHVlLCBzZXR1cDogbmV3IFVSTFNlYXJjaFBhcmFtcyhsb2NhdGlvbi5zZWFyY2gpLmdldCgnc2V0dXAnKSB8fCAnJyB9KTsKICBpZiAoci5vaykgeyAkKCdwdycpLnZhbHVlID0gJyc7IHNob3coKTsgfSBlbHNlICQoJ2xtJykudGV4dENvbnRlbnQgPSByLmVycm9yIHx8ICfYrti32KMnOwp9OwokKCdwdycpLm9ua2V5ZG93biA9IChlKSA9PiB7IGlmIChlLmtleSA9PT0gJ0VudGVyJykgJCgnZ28nKS5jbGljaygpOyB9OwokKCdvdXQnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4geyBhd2FpdCBhcGkoJ2xvZ291dCcsIHt9KTsgbG9jYXRpb24ucmVsb2FkKCk7IH07CgpmdW5jdGlvbiBzaG93KCkgeyAkKCdsb2dpbicpLmNsYXNzTGlzdC5hZGQoJ2hpZGUnKTsgJCgnYXBwJykuY2xhc3NMaXN0LnJlbW92ZSgnaGlkZScpOyBsb2FkKCk7IH0KCmNvbnN0IFZJRVdTID0geyBkYXNoOiBbJ9mE2YjYrdipINin2YTYqtit2YPZhScsICfZhti42LHYqSDYs9ix2YrYudipINi52YTZiSDZg9mEINin2YTYo9is2YfYstipJ10sIGRldnM6IFsn2KfZhNij2KzZh9iy2KknLCAn2YPZhCDYp9mE2LLYqNin2YrZhiDigJQg2KfYtti62Lcg2LnZhNmJINij2Yog2KzZh9in2LIg2YTYqti52K/ZitmE2YcnXSwgcHJvbW86IFsnUHJvbW8gY29kZXMnLCAn2YPZhCDZg9mI2K8g2KjZiti02KrYutmEINmF2LHYqSDZiNit2K/YqSDYudmE2Ykg2KzZh9in2LIg2YjYp9it2K8nXSwgcGF5OiBbJ9in2YTYr9mB2LknLCAn2KfZhNmE2Yog2KjYsdinINin2YTYr9in2KbYsdipINio2YrYr9mB2Lkg4oCUINmI2KfZhNmE2Yog2KzZiNmR2KfZh9inINio2YrYp9iu2K8gUHJvbW8gY29kZSddLCBoZWxwOiBbJ9i32LHZitmC2Kkg2KfZhNin2LPYqtiu2K/Yp9mFJywgJ9iu2LfZiNin2Kog2LPYsdmK2LnYqSddIH07CmZ1bmN0aW9uIHZpZXcodikgewogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy5uYXZbZGF0YS12XScpLmZvckVhY2goKG4pID0+IG4uY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCBuLmRhdGFzZXQudiA9PT0gdikpOwogIE9iamVjdC5rZXlzKFZJRVdTKS5mb3JFYWNoKChrKSA9PiAkKCd2LScgKyBrKS5jbGFzc0xpc3QudG9nZ2xlKCdoaWRlJywgayAhPT0gdikpOwogICQoJ3Z0JykudGV4dENvbnRlbnQgPSBWSUVXU1t2XVswXTsgJCgndnMnKS50ZXh0Q29udGVudCA9IFZJRVdTW3ZdWzFdOwogIGlmICh2ID09PSAncHJvbW8nKSBsb2FkUHJvbW9zKCk7CiAgaWYgKHYgPT09ICdwYXknKSBsb2FkUGF5KCk7Cn0KLy8gLS0tLS0tLS0tLSBwYXltZW50IC0tLS0tLS0tLS0KYXN5bmMgZnVuY3Rpb24gbG9hZFBheSgpIHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdwYXknKTsKICAkKCdwYXktcHJpY2UnKS52YWx1ZSA9IHIucHJpY2UgfHwgJyc7ICQoJ3BheS1saW5rJykudmFsdWUgPSByLmxpbmsgfHwgJyc7ICQoJ3BheS1vbicpLmNsYXNzTGlzdC50b2dnbGUoJ29uJywgISFyLm9uKTsKICAkKCdwYXktc3QnKS50ZXh0Q29udGVudCA9IChyLm9uID8gJ9i02LrZkdin2YQnIDogJ9mF2LfZgdmKJykgKyAoci5saW5rID8gJyDCtyBWZW5tbyBAJyArIHIubGluay5yZXBsYWNlKC9eQC8sICcnKSA6ICcnKTsKfQokKCdwYXktb24nKS5vbmNsaWNrID0gKCkgPT4gJCgncGF5LW9uJykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nKTsKJCgncGF5LXNhdmUnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3BheScsIHsgcHJpY2U6ICQoJ3BheS1wcmljZScpLnZhbHVlLnRyaW0oKSwgbGluazogJCgncGF5LWxpbmsnKS52YWx1ZS50cmltKCksIG9uOiAkKCdwYXktb24nKS5jbGFzc0xpc3QuY29udGFpbnMoJ29uJykgfSk7CiAgJCgncGF5LW1zZycpLnRleHRDb250ZW50ID0gci5vayA/ICfYp9mG2K3Zgdi4IOKckycgOiAoci5lcnJvciB8fCAn2K7Yt9ijJyk7IGxvYWRQYXkoKTsKfTsKLy8gLS0tLS0tLS0tLSBwcm9tbyBjb2Rlczogb25lIHVzZSwgb25lIGRldmljZSAtLS0tLS0tLS0tCmNvbnN0IHBjb2RlID0gKGMpID0+IGMucmVwbGFjZSgvKC57NH0pKC57NH0pLywgJyQxLSQyJyk7CmFzeW5jIGZ1bmN0aW9uIGxvYWRQcm9tb3MoKSB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgncHJvbW9zJyk7IGNvbnN0IGxpc3QgPSByLnByb21vcyB8fCBbXTsKICBjb25zdCBmcmVlID0gbGlzdC5maWx0ZXIoKHApID0+ICFwLnVzZWRfYnkpLmxlbmd0aDsKICAkKCdwcm9tby1uJykudGV4dENvbnRlbnQgPSBgJHtmcmVlfSDYrNin2YfYsiDCtyAke2xpc3QubGVuZ3RoIC0gZnJlZX0g2YXYs9iq2LnZhdmEYDsKICAkKCdwdGInKS5pbm5lckhUTUwgPSBsaXN0Lmxlbmd0aCA/IGxpc3QubWFwKChwKSA9PiB7CiAgICBjb25zdCBkID0gcC51c2VkX2J5ID8gZGV2cy5maW5kKCh4KSA9PiB4LmNvZGUgPT09IHAudXNlZF9ieSkgOiBudWxsOwogICAgY29uc3Qgc3QgPSBwLnVzZWRfYnkgPyBgPHNwYW4gY2xhc3M9InN0IHMtb2ZmIj7Zhdiz2KrYudmF2YQgwrcgJHtlc2MoZD8ubmFtZSB8fCBwcmV0dHkocC51c2VkX2J5KSl9IMK3INmC2KjZhCAke2FnbyhwLnVzZWRfYXQpfTwvc3Bhbj5gIDogJzxzcGFuIGNsYXNzPSJzdCBzLW9uIj7YrNin2YfYsjwvc3Bhbj4nOwogICAgcmV0dXJuIGA8dHI+PHRkPjxzcGFuIGNsYXNzPSJjb2RlIj4ke2VzYyhwY29kZShwLmNvZGUpKX08L3NwYW4+PC90ZD48dGQ+JHtlc2MocC5ub3RlIHx8ICcnKX08L3RkPjx0ZD4ke3N0fTwvdGQ+CiAgICAgIDx0ZCBzdHlsZT0idGV4dC1hbGlnbjpsZWZ0Ij4ke3AudXNlZF9ieSA/ICcnIDogYDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1jcD0iJHtlc2MocGNvZGUocC5jb2RlKSl9Ij7Zhtiz2K48L2J1dHRvbj4gYH08YnV0dG9uIGNsYXNzPSJidG4gcmVkIHNtIiBkYXRhLXBkPSIke2VzYyhwLmNvZGUpfSI+2K3YsNmBPC9idXR0b24+PC90ZD48L3RyPmA7CiAgfSkuam9pbignJykgOiAnPHRyPjx0ZCBjb2xzcGFuPSI0IiBjbGFzcz0iZW1wdHkiPtmF2Kcg2YHZiiDYo9mD2YjYp9ivIOKAlCDYo9i12K/YsSDYo9mI2YQg2YPZiNivINmF2YYg2YHZiNmCPC90ZD48L3RyPic7CiAgJCgncHRiJykucXVlcnlTZWxlY3RvckFsbCgnW2RhdGEtY3BdJykuZm9yRWFjaCgoYikgPT4gYi5vbmNsaWNrID0gKCkgPT4geyBuYXZpZ2F0b3IuY2xpcGJvYXJkPy53cml0ZVRleHQoYi5kYXRhc2V0LmNwKTsgdG9hc3QoJ9in2YbYqtiz2K46ICcgKyBiLmRhdGFzZXQuY3ApOyB9KTsKICAkKCdwdGInKS5xdWVyeVNlbGVjdG9yQWxsKCdbZGF0YS1wZF0nKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7IGlmICghY29uZmlybSgn2K3YsNmBINin2YTZg9mI2K/YnycpKSByZXR1cm47IGF3YWl0IGFwaSgncHJvbW9fZGVsZXRlJywgeyBjb2RlOiBiLmRhdGFzZXQucGQgfSk7IGxvYWRQcm9tb3MoKTsgfSk7Cn0KJCgncGdlbicpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgncHJvbW8nLCB7IG46ICskKCdwY291bnQnKS52YWx1ZSwgbm90ZTogJCgncG5vdGUnKS52YWx1ZS50cmltKCkgfSk7CiAgaWYgKHIub2spIHsgJCgncG5vdGUnKS52YWx1ZSA9ICcnOyB0b2FzdCgn2KrZhSDYpdi12K/Yp9ixICcgKyAoci5jb2RlcyB8fCBbXSkubGVuZ3RoICsgJyDZg9mI2K8nKTsgbG9hZFByb21vcygpOyB9IGVsc2UgdG9hc3Qoci5lcnJvciB8fCAn2K7Yt9ijJyk7Cn07CmRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy5uYXZbZGF0YS12XScpLmZvckVhY2goKG4pID0+IG4ub25jbGljayA9ICgpID0+IHZpZXcobi5kYXRhc2V0LnYpKTsKCmFzeW5jIGZ1bmN0aW9uIGxvYWQoKSB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgnZGV2aWNlcycpOwogIGlmIChyLm9rID09PSBmYWxzZSAmJiByLmVycm9yKSB7IGxvY2F0aW9uLnJlbG9hZCgpOyByZXR1cm47IH0KICBkZXZzID0gci5kZXZpY2VzIHx8IFtdOwogIHJlbmRlclN0YXRzKCk7IHJlbmRlclRhYmxlKCk7IHJlbmRlckF0dG4oKTsKICBsb2FkSGVhbHRoKCk7Cn0KYXN5bmMgZnVuY3Rpb24gbG9hZEhlYWx0aCgpIHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdoZWFsdGgnKTsKICBjb25zdCBoID0gci5oZWFsdGggfHwgW107CiAgJCgnaGwtbicpLnRleHRDb250ZW50ID0gaC5sZW5ndGggPyBgJHtoLmxlbmd0aH0g2KrZgtix2YrYsWAgOiAnJzsKICAkKCdobCcpLmlubmVySFRNTCA9IGgubGVuZ3RoID8gaC5tYXAoKHgpID0+IGA8dHI+PHRkPjxzcGFuIGNsYXNzPSJzdCAke3gua2luZCA9PT0gJ2ZyZWV6ZScgPyAncy1zb29uJyA6ICdzLW9mZid9Ij4ke3gua2luZCA9PT0gJ2ZyZWV6ZScgPyAn2LnZhNmR2YLYqiDYp9mE2LTYp9i02KknIDogJ9iq2LPZg9mR2LEg2KjYrti32KMnfTwvc3Bhbj48L3RkPgogICAgPHRkPiR7ZXNjKHgubmFtZSB8fCBwcmV0dHkoeC5jb2RlKSl9PGJyPjxzbWFsbCBjbGFzcz0ibXV0ZWQiPiR7ZXNjKHgudmVyKX0gwrcg2YLYqNmEICR7YWdvKHgudCl9PC9zbWFsbD48L3RkPgogICAgPHRkPjxkZXRhaWxzPjxzdW1tYXJ5IGNsYXNzPSJtdXRlZCI+2KfZhNiq2YHYp9i12YrZhDwvc3VtbWFyeT48cHJlIGRpcj0ibHRyIiBzdHlsZT0id2hpdGUtc3BhY2U6cHJlLXdyYXA7Zm9udC1zaXplOjExcHg7bWF4LWhlaWdodDoyNjBweDtvdmVyZmxvdzphdXRvIj4ke2VzYyh4LmluZm8pfTwvcHJlPjwvZGV0YWlscz48L3RkPjwvdHI+YCkuam9pbignJykKICAgIDogJzx0cj48dGQgY2xhc3M9Im11dGVkIj7inJMg2YjZhNinINi52LfZhCDYudmE2Ykg2KPZiiDYrNmH2KfYsjwvdGQ+PC90cj4nOwp9CiQoJ2hsLWNscicpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7IGlmICghY29uZmlybSgn2YXYs9itINmD2YQg2KfZhNiq2YLYp9ix2YrYsdifJykpIHJldHVybjsgYXdhaXQgYXBpKCdoZWFsdGgvY2xlYXInLCB7fSk7IGxvYWRIZWFsdGgoKTsgfTsKJCgncmVmcmVzaCcpLm9uY2xpY2sgPSAoKSA9PiBsb2FkKCkudGhlbigoKSA9PiB0b2FzdCgn2KrZhSDYp9mE2KrYrdiv2YrYqycpKTsKCmZ1bmN0aW9uIGNvdW50cygpIHsKICBjb25zdCBjID0geyBhbGw6IGRldnMubGVuZ3RoLCBvbjogMCwgd2FpdDogMCwgc29vbjogMCwgZXhwOiAwLCBvZmY6IDAsIG9ubGluZTogMCwgd2F0Y2g6IDAgfTsKICBkZXZzLmZvckVhY2goKGQpID0+IHsgY1tzdGF0ZShkKS5rXSsrOyBpZiAoaXNPbmxpbmUoZCkpIGMub25saW5lKys7IGlmIChpc1dhdGNoaW5nKGQpKSBjLndhdGNoKys7IH0pOwogIHJldHVybiBjOwp9CmZ1bmN0aW9uIHJlbmRlclN0YXRzKCkgewogIGNvbnN0IGMgPSBjb3VudHMoKTsKICBjb25zdCBTID0gW1snYWxsJywgJ9mD2YQg2KfZhNij2KzZh9iy2KknLCBjLmFsbCwgJ3ZhcigtLXQyKSddLCBbJ29ubGluZScsICfZhdiq2LXZhCDYp9mE2KLZhicsIGMub25saW5lLCAndmFyKC0tYSknXSwgWyd3YXRjaCcsICfZiti02KfZh9ivINin2YTYotmGJywgYy53YXRjaCwgJ3ZhcigtLWEpJ10sIFsnb24nLCAn2LTYutmR2KfZhCcsIGMub24gKyBjLnNvb24sICd2YXIoLS1hKSddLAogICAgWyd3YWl0JywgJ9io2KfZhtiq2LjYp9ixINin2YTYqtmB2LnZitmEJywgYy53YWl0LCAndmFyKC0tYiknXSwgWydzb29uJywgJ9mK2YbYqtmH2Yog2K7ZhNin2YQgNyDYo9mK2KfZhScsIGMuc29vbiwgJ3ZhcigtLXkpJ10sIFsnZXhwJywgJ9mF2YbYqtmH2YonLCBjLmV4cCwgJ3ZhcigtLXIpJ10sIFsnb2ZmJywgJ9mF2YjZgtmI2YEnLCBjLm9mZiwgJ3ZhcigtLXQzKSddXTsKICAkKCdzdGF0cycpLmlubmVySFRNTCA9IFMubWFwKChbaywgbCwgbiwgY29sXSkgPT4gYDxkaXYgY2xhc3M9InN0YXQiIGRhdGEtZj0iJHtrfSI+PGRpdiBjbGFzcz0ibCI+PHNwYW4gY2xhc3M9ImRvdCIgc3R5bGU9ImJhY2tncm91bmQ6JHtjb2x9Ij48L3NwYW4+JHtsfTwvZGl2PjxkaXYgY2xhc3M9Im4iPiR7bn08L2Rpdj48L2Rpdj5gKS5qb2luKCcnKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuc3RhdCcpLmZvckVhY2goKHMpID0+IHMub25jbGljayA9ICgpID0+IHsgZmlsdGVyID0gcy5kYXRhc2V0LmY7IHZpZXcoJ2RldnMnKTsgcmVuZGVyVGFibGUoKTsgfSk7CiAgY29uc3QgRiA9IFtbJ2FsbCcsICfYp9mE2YPZhCddLCBbJ29ubGluZScsICfZhdiq2LXZhCDYp9mE2KLZhiddLCBbJ3dhdGNoJywgJ9mK2LTYp9mH2K8g2KfZhNii2YYnXSwgWydvbicsICfYtNi62ZHYp9mEJ10sIFsnd2FpdCcsICfYqNin2YbYqti42KfYsSDYp9mE2KrZgdi52YrZhCddLCBbJ3Nvb24nLCAn2YrZhtiq2YfZiiDZgtix2YrYqNin2YsnXSwgWydleHAnLCAn2YXZhtiq2YfZiiddLCBbJ29mZicsICfZhdmI2YLZiNmBJ11dOwogICQoJ2NoaXBzJykuaW5uZXJIVE1MID0gRi5tYXAoKFtrLCBsXSkgPT4gYDxidXR0b24gY2xhc3M9ImNoaXAke2ZpbHRlciA9PT0gayA/ICcgb24nIDogJyd9IiBkYXRhLWY9IiR7a30iPiR7bH0gPHNwYW4gY2xhc3M9InBpbGwiPiR7ayA9PT0gJ29uJyA/IGMub24gKyBjLnNvb24gOiBjW2tdfTwvc3Bhbj48L2J1dHRvbj5gKS5qb2luKCcnKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuY2hpcCcpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9ICgpID0+IHsgZmlsdGVyID0gYi5kYXRhc2V0LmY7IHJlbmRlclN0YXRzKCk7IHJlbmRlclRhYmxlKCk7IH0pOwp9CmZ1bmN0aW9uIHJvdyhkKSB7CiAgY29uc3QgcyA9IHN0YXRlKGQpOwogIGNvbnN0IHBscyA9IChkLnBsYXlsaXN0ID8gYDxzcGFuIGNsYXNzPSJ0YWciPiR7ZXNjKGQucGxheWxpc3QpfTwvc3Bhbj5gIDogJzxzcGFuIGNsYXNzPSJtdXRlZCI+4oCUPC9zcGFuPicpICsgKGQuZXh0cmFzIHx8IFtdKS5tYXAoKHgpID0+IGA8c3BhbiBjbGFzcz0idGFnIj4rICR7ZXNjKHgpfTwvc3Bhbj5gKS5qb2luKCcnKTsKICByZXR1cm4gYDx0ciBkYXRhLWM9IiR7ZXNjKGQuY29kZSl9Ij48dGQ+PHNwYW4gY2xhc3M9ImNvZGUiPiR7cHJldHR5KGVzYyhkLmNvZGUpKX08L3NwYW4+PC90ZD4KICAgIDx0ZCBjbGFzcz0id2hvIj48Yj4ke2QubmFtZSA/IGVzYyhkLm5hbWUpIDogJzxzcGFuIGNsYXNzPSJtdXRlZCI+2KjYr9mI2YYg2KfYs9mFPC9zcGFuPid9PC9iPjxzbWFsbD4ke2VzYyhkLm1vZGVsIHx8ICcnKX08L3NtYWxsPiR7d2hlcmUoZCl9JHt3YXRjaGluZyhkKX08L3RkPgogICAgPHRkPiR7cGxzfSR7ZC5oYXNfdnBuID8gJzxzcGFuIGNsYXNzPSJ0YWciPvCfm6EgVlBOPC9zcGFuPicgOiAnJ30ke2QucHJvbW8gPyAnPHNwYW4gY2xhc3M9InRhZyI+JyArIChkLnByb21vLnN0YXJ0c1dpdGgoJ1BBSUQnKSA/ICfwn5KzINiv2YHYuScgOiAn8J+OnyAnICsgZXNjKGQucHJvbW8ucmVwbGFjZSgvKC57NH0pKC57NH0pLywgJyQxLSQyJykpKSArICc8L3NwYW4+JyA6ICcnfTwvdGQ+PHRkPjxzcGFuIGNsYXNzPSJzdCBzLSR7cy5rfSI+JHtpc09ubGluZShkKSA/ICc8c3BhbiBjbGFzcz0ib25saW5lIj48L3NwYW4+JyA6ICcnfSR7cy50fTwvc3Bhbj48L3RkPgogICAgPHRkIGNsYXNzPSJoaWRlLW0gbXV0ZWQiPiR7YWdvKGQuc2Vlbil9PC90ZD48dGQgY2xhc3M9ImhpZGUtbSBtdXRlZCI+JHtkYXkoZC5leHBpcmVzKSB8fCAn4oCUJ308L3RkPjwvdHI+YDsKfQpmdW5jdGlvbiBiaW5kUm93cyh0YikgeyB0Yi5xdWVyeVNlbGVjdG9yQWxsKCd0cltkYXRhLWNdJykuZm9yRWFjaCgodHIpID0+IHRyLm9uY2xpY2sgPSAoKSA9PiBvcGVuRHJhd2VyKHRyLmRhdGFzZXQuYykpOyB9CmZ1bmN0aW9uIHJlbmRlclRhYmxlKCkgewogIGNvbnN0IHEgPSAkKCdxJykudmFsdWUudHJpbSgpLnRvTG93ZXJDYXNlKCkucmVwbGFjZSgvXHMvZywgJycpOwogIGNvbnN0IGxpc3QgPSBkZXZzLmZpbHRlcigoZCkgPT4gewogICAgY29uc3QgayA9IHN0YXRlKGQpLms7CiAgICBpZiAoZmlsdGVyID09PSAnd2F0Y2gnID8gIWlzV2F0Y2hpbmcoZCkgOiBmaWx0ZXIgPT09ICdvbmxpbmUnID8gIWlzT25saW5lKGQpIDogZmlsdGVyID09PSAnb24nID8gIShrID09PSAnb24nIHx8IGsgPT09ICdzb29uJykgOiBmaWx0ZXIgIT09ICdhbGwnICYmIGsgIT09IGZpbHRlcikgcmV0dXJuIGZhbHNlOwogICAgaWYgKCFxKSByZXR1cm4gdHJ1ZTsKICAgIHJldHVybiBbZC5jb2RlLCBkLm5hbWUsIGQucGxheWxpc3QsIGQubW9kZWwsIGQubm93X3RpdGxlLCAuLi4oZC5leHRyYXMgfHwgW10pXS5zb21lKCh2KSA9PiBTdHJpbmcodiB8fCAnJykudG9Mb3dlckNhc2UoKS5yZXBsYWNlKC9ccy9nLCAnJykuaW5jbHVkZXMocSkpOwogIH0pOwogICQoJ3RiJykuaW5uZXJIVE1MID0gbGlzdC5sZW5ndGggPyBsaXN0Lm1hcChyb3cpLmpvaW4oJycpIDogYDx0cj48dGQgY29sc3Bhbj0iNiIgY2xhc3M9ImVtcHR5Ij7ZhdinINmB2Yog2KPYrNmH2LLYqSDZh9mI2YY8L3RkPjwvdHI+YDsKICBiaW5kUm93cygkKCd0YicpKTsKfQokKCdxJykub25pbnB1dCA9IHJlbmRlclRhYmxlOwpmdW5jdGlvbiByZW5kZXJBdHRuKCkgewogIGNvbnN0IG9yZGVyID0geyB3YWl0OiAwLCBzb29uOiAxLCBleHA6IDIgfTsKICBjb25zdCBsaXN0ID0gZGV2cy5maWx0ZXIoKGQpID0+IHN0YXRlKGQpLmsgaW4gb3JkZXIpLnNvcnQoKGEsIGIpID0+IG9yZGVyW3N0YXRlKGEpLmtdIC0gb3JkZXJbc3RhdGUoYikua10pOwogICQoJ2F0dG4tbicpLnRleHRDb250ZW50ID0gbGlzdC5sZW5ndGggPyBgJHtsaXN0Lmxlbmd0aH0g2KzZh9in2LJgIDogJyc7CiAgJCgnYXR0bicpLmlubmVySFRNTCA9IGxpc3QubGVuZ3RoID8gbGlzdC5tYXAocm93KS5qb2luKCcnKSA6IGA8dHI+PHRkIGNsYXNzPSJlbXB0eSI+2YPZhCDYtNmKINiq2YXYp9mFIOKckyDigJQg2YXYpyDZgdmKINij2KzZh9iy2Kkg2KjYp9mG2KrYuNin2LEg2KPZiCDZhdmG2KrZh9mK2Kk8L3RkPjwvdHI+YDsKICBiaW5kUm93cygkKCdhdHRuJykpOwp9CgovLyAtLS0tLS0tLS0tIGRyYXdlciAtLS0tLS0tLS0tCmZ1bmN0aW9uIG9wZW5EcmF3ZXIoY29kZSkgewogIGVkaXRpbmcgPSBjb2RlID8gZGV2cy5maW5kKCh4KSA9PiB4LmNvZGUgPT09IGNvZGUpIDogbnVsbDsKICBjb25zdCBkID0gZWRpdGluZyB8fCB7fTsKICAkKCdkdCcpLnRleHRDb250ZW50ID0gZWRpdGluZyA/IChkLm5hbWUgfHwgJ9is2YfYp9iyICcgKyBwcmV0dHkoZC5jb2RlKSkgOiAn2KzZh9in2LIg2KzYr9mK2K8nOwogICQoJ2RzdWInKS5pbm5lckhUTUwgPSBlZGl0aW5nID8gYDxzcGFuIGNsYXNzPSJjb2RlIj4ke3ByZXR0eShlc2MoZC5jb2RlKSl9PC9zcGFuPiDCtyAke2VzYyhkLm1vZGVsIHx8ICcnKX0gwrcg2KLYrtixINi42YfZiNixICR7YWdvKGQuc2Vlbil9JHt3YXRjaGluZyhkKSA/ICc8YnI+JyArIHdhdGNoaW5nKGQpIDogJyd9YCA6ICfYp9mD2KrYqCDYp9mE2YPZiNivINin2YTZhNmKINi42KfZh9ixINi52YTZiSDYtNin2LTYqSDYp9mE2LLYqNmI2YYnOwogICQoJ2NvZGUnKS52YWx1ZSA9IGQuY29kZSA/IHByZXR0eShkLmNvZGUpIDogJyc7ICQoJ2NvZGUnKS5kaXNhYmxlZCA9ICEhZWRpdGluZzsKICAkKCduYW1lJykudmFsdWUgPSBkLm5hbWUgfHwgJyc7ICQoJ3duYW1lJykudmFsdWUgPSBkLndlbGNvbWUgfHwgJyc7ICQoJ3BsJykudmFsdWUgPSBkLnBsYXlsaXN0IHx8IHBsYXlsaXN0c1swXSB8fCAnJzsKICAkKCd1JykudmFsdWUgPSAnJzsgJCgncCcpLnZhbHVlID0gJyc7ICQoJ2V4JykudmFsdWUgPSBkYXkoZC5leHBpcmVzKTsKICAkKCdsaGludCcpLnRleHRDb250ZW50ID0gZC5oYXNfbG9naW4gPyAn2KfZhNmK2YjYstixINmF2K3ZgdmI2Lgg2YjZhdi02YHZkdixLiDYp9mD2KrYqCDZitmI2LLYsSDZiNio2KfYs9mI2YjYsdivINis2K/Yp9ivINio2LMg2KXYsNinINio2K/ZgyDYqti62YrZkdix2YfZhS4nIDogJ9in2YPYqtioINin2YTZitmI2LLYsSDZiNin2YTYqNin2LPZiNmI2LHYryDYqtio2Lkg2KfZhNmAIHBsYXlsaXN0Lic7CiAgJCgnYWN0JykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCBlZGl0aW5nID8gISFkLmFjdGl2ZSA6IHRydWUpOwogICQoJ2RlbCcpLmNsYXNzTGlzdC50b2dnbGUoJ2hpZGUnLCAhZWRpdGluZyk7ICQoJ3hzZWMnKS5jbGFzc0xpc3QudG9nZ2xlKCdoaWRlJywgIWVkaXRpbmcpOyAkKCd2c2VjJykuY2xhc3NMaXN0LnRvZ2dsZSgnaGlkZScsICFlZGl0aW5nKTsKICAkKCd2Y29uZicpLnZhbHVlID0gJyc7IHZkcmF3KGQuaGFzX3Zwbik7CiAgcmVuZGVyRXh0cmFzKCk7ICQoJ3NtJykudGV4dENvbnRlbnQgPSAnJzsKICAkKCdzY3JpbScpLmNsYXNzTGlzdC5hZGQoJ29wZW4nKTsgJCgnZHJhd2VyJykuY2xhc3NMaXN0LmFkZCgnb3BlbicpOwogIHNldFRpbWVvdXQoKCkgPT4gKGVkaXRpbmcgPyAkKCduYW1lJykgOiAkKCdjb2RlJykpLmZvY3VzKCksIDI1MCk7Cn0KZnVuY3Rpb24gY2xvc2VEcmF3ZXIoKSB7ICQoJ3NjcmltJykuY2xhc3NMaXN0LnJlbW92ZSgnb3BlbicpOyAkKCdkcmF3ZXInKS5jbGFzc0xpc3QucmVtb3ZlKCdvcGVuJyk7IGVkaXRpbmcgPSBudWxsOyB9CiQoJ2FkZCcpLm9uY2xpY2sgPSAoKSA9PiBvcGVuRHJhd2VyKG51bGwpOwokKCdkeCcpLm9uY2xpY2sgPSAkKCdjYW5jZWwnKS5vbmNsaWNrID0gJCgnc2NyaW0nKS5vbmNsaWNrID0gY2xvc2VEcmF3ZXI7CmRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoJ2tleWRvd24nLCAoZSkgPT4geyBpZiAoZS5rZXkgPT09ICdFc2NhcGUnKSBjbG9zZURyYXdlcigpOyB9KTsKJCgnYWN0Jykub25jbGljayA9ICgpID0+ICQoJ2FjdCcpLmNsYXNzTGlzdC50b2dnbGUoJ29uJyk7CmRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJ1tkYXRhLWFkZF0nKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSAoKSA9PiB7CiAgY29uc3QgbiA9ICtiLmRhdGFzZXQuYWRkOwogIGlmICghbikgeyAkKCdleCcpLnZhbHVlID0gJyc7IHJldHVybjsgfQogIGNvbnN0IGN1ciA9ICQoJ2V4JykudmFsdWUgPyBEYXRlLnBhcnNlKCQoJ2V4JykudmFsdWUpIDogMDsKICAkKCdleCcpLnZhbHVlID0gZGF5KE1hdGgubWF4KGN1ciwgRGF0ZS5ub3coKSkgKyBuICogREFZKTsKfSk7CmZ1bmN0aW9uIHJlbmRlckV4dHJhcygpIHsKICBjb25zdCB4cyA9IGVkaXRpbmc/LmV4dHJhcyB8fCBbXTsKICAkKCd4bGlzdCcpLmlubmVySFRNTCA9IHhzLmxlbmd0aCA/IHhzLm1hcCgoeCkgPT4gYDxkaXYgY2xhc3M9InhsIj48c3BhbiBjbGFzcz0idGFnIj4ke2VzYyh4KX08L3NwYW4+PGJ1dHRvbiBjbGFzcz0iYnRuIHJlZCBzbSIgZGF0YS14PSIke2VzYyh4KX0iPti02YrZhDwvYnV0dG9uPjwvZGl2PmApLmpvaW4oJycpIDogJzxkaXYgY2xhc3M9Im11dGVkIiBzdHlsZT0iZm9udC1zaXplOjEzcHgiPtmF2Kcg2YHZiiBwbGF5bGlzdHMg2KXYttin2YHZitipLjwvZGl2Pic7CiAgJCgneGxpc3QnKS5xdWVyeVNlbGVjdG9yQWxsKCdbZGF0YS14XScpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9IGFzeW5jICgpID0+IHsKICAgIGlmICghY29uZmlybShg2LTZitmEICR7Yi5kYXRhc2V0Lnh9INmF2YYg2YfYsNinINin2YTYrNmH2KfYstifYCkpIHJldHVybjsKICAgIGF3YWl0IGFwaSgnZXh0cmEnLCB7IGNvZGU6IGVkaXRpbmcuY29kZSwgcGxheWxpc3Q6IGIuZGF0YXNldC54LCByZW1vdmU6IHRydWUgfSk7CiAgICBhd2FpdCByZWxvYWRFZGl0aW5nKCk7IHRvYXN0KCfYp9mG2LTYp9mE2KonKTsKICB9KTsKfQphc3luYyBmdW5jdGlvbiByZWxvYWRFZGl0aW5nKCkgeyBjb25zdCBjID0gZWRpdGluZz8uY29kZTsgYXdhaXQgbG9hZCgpOyBpZiAoYykgeyBlZGl0aW5nID0gZGV2cy5maW5kKCh4KSA9PiB4LmNvZGUgPT09IGMpOyByZW5kZXJFeHRyYXMoKTsgfSB9CiQoJ3hhZGQnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGlmICghZWRpdGluZykgcmV0dXJuOwogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ2V4dHJhJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUsIHBsYXlsaXN0OiAkKCd4cGwnKS52YWx1ZSwgdXNlcjogJCgneHUnKS52YWx1ZSwgcGFzczogJCgneHAnKS52YWx1ZSB9KTsKICBpZiAoci5vaykgeyAkKCd4dScpLnZhbHVlID0gJyc7ICQoJ3hwJykudmFsdWUgPSAnJzsgYXdhaXQgcmVsb2FkRWRpdGluZygpOyB0b2FzdCgn2KfZhti22KfZgdiqIOKckyDigJQg2K7ZhNmKINin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQnKTsgfQogIGVsc2UgJCgnc20nKS5pbm5lckhUTUwgPSBgPHNwYW4gY2xhc3M9ImJhZCI+JHtlc2Moci5lcnJvcil9PC9zcGFuPmA7Cn07Ci8vIFByb3RvbiBvbmx5IChvd25lciwgMTEgTm92IDIwMjYpOiBwYXN0ZSB0aGUgZGV2aWNlJ3Mgb3duIFByb3RvbiBXaXJlR3VhcmQgZmlsZSwgb3IgdGFrZSBpdCBvZmYKY29uc3QgdmRyYXcgPSAob24pID0+IHsKICAkKCd2c3RhdGUnKS5pbm5lckhUTUwgPSBvbiA/ICc8c3BhbiBjbGFzcz0ib2siPvCfm6Eg2YfYsNinINin2YTYrNmH2KfYsiDYudmG2K/ZhyBWUE4g4oCUINio2YrYuNmH2LHZhNmHINiy2LEgVlBOIE9OL09GRjwvc3Bhbj4nIDogJzxzcGFuIGNsYXNzPSJtdXRlZCI+2YXYpyDZgdmKIFZQTiDZhNmH2LDYpyDYp9mE2KzZh9in2LIgKNmF2Kcg2KjZiti42YfYsdmE2Ycg2KPZiiDYrtmK2KfYsSBWUE4pPC9zcGFuPic7CiAgJCgndmRlbCcpLmNsYXNzTGlzdC50b2dnbGUoJ2hpZGUnLCAhb24pOwp9OwokKCd2c2F2ZScpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nKSByZXR1cm47CiAgY29uc3QgciA9IGF3YWl0IGFwaSgndnBuJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUsIGNvbmY6ICQoJ3Zjb25mJykudmFsdWUgfSk7CiAgaWYgKHIub2spIHsgJCgndmNvbmYnKS52YWx1ZSA9ICcnOyBhd2FpdCByZWxvYWRFZGl0aW5nKCk7IHZkcmF3KGVkaXRpbmcuaGFzX3Zwbik7IHRvYXN0KCdWUE4g2KfZhtit2YHYuCDigJQg2K7ZhNmKINin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQnKTsgfQogIGVsc2UgJCgnc20nKS5pbm5lckhUTUwgPSBgPHNwYW4gY2xhc3M9ImJhZCI+JHtlc2Moci5lcnJvcil9PC9zcGFuPmA7Cn07CiQoJ3ZkZWwnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGlmICghZWRpdGluZyB8fCAhY29uZmlybSgn2LTZitmEINin2YTZgCBWUE4g2YXZhiDZh9iw2Kcg2KfZhNis2YfYp9iy2J8nKSkgcmV0dXJuOwogIGF3YWl0IGFwaSgndnBuJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUsIGNvbmY6ICcnIH0pOyBhd2FpdCByZWxvYWRFZGl0aW5nKCk7IHZkcmF3KGVkaXRpbmcuaGFzX3Zwbik7IHRvYXN0KCfYp9mG2LTYp9mEIOKAlCDYqNmK2K7YqtmB2Yog2K7Zitin2LEg2KfZhNmAIFZQTiDZhdmGINin2YTYrNmH2KfYsicpOwp9OwokKCdzYXZlJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBjb25zdCBjb2RlID0gJCgnY29kZScpLnZhbHVlLnJlcGxhY2UoL1xEL2csICcnKTsKICBpZiAoY29kZS5sZW5ndGggIT09IDgpIHsgJCgnc20nKS5pbm5lckhUTUwgPSAnPHNwYW4gY2xhc3M9ImJhZCI+2YPZiNivINin2YTYrNmH2KfYsiA4INij2LHZgtin2YU8L3NwYW4+JzsgcmV0dXJuOyB9CiAgY29uc3QgZCA9IGRldnMuZmluZCgoeCkgPT4geC5jb2RlID09PSBjb2RlKTsKICBpZiAoIWQ/Lmhhc19sb2dpbiAmJiAoISQoJ3UnKS52YWx1ZSB8fCAhJCgncCcpLnZhbHVlKSkgeyAkKCdzbScpLmlubmVySFRNTCA9ICc8c3BhbiBjbGFzcz0iYmFkIj7Yp9mD2KrYqCDYp9mE2YrZiNiy2LEg2YjYp9mE2KjYp9iz2YjZiNix2K88L3NwYW4+JzsgcmV0dXJuOyB9CiAgY29uc3QgciA9IGF3YWl0IGFwaSgnc2F2ZScsIHsgY29kZSwgbmFtZTogJCgnbmFtZScpLnZhbHVlLnRyaW0oKSwgd2VsY29tZTogJCgnd25hbWUnKS52YWx1ZS50cmltKCksIHBsYXlsaXN0OiAkKCdwbCcpLnZhbHVlLCB1c2VyOiAkKCd1JykudmFsdWUsIHBhc3M6ICQoJ3AnKS52YWx1ZSwgZXhwaXJlczogJCgnZXgnKS52YWx1ZSwgYWN0aXZlOiAkKCdhY3QnKS5jbGFzc0xpc3QuY29udGFpbnMoJ29uJykgfSk7CiAgaWYgKCFyLm9rKSB7ICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKHIuZXJyb3IpfTwvc3Bhbj5gOyByZXR1cm47IH0KICAkKCdwJykudmFsdWUgPSAnJzsgY2xvc2VEcmF3ZXIoKTsgYXdhaXQgbG9hZCgpOyB0b2FzdCgn2KfZhtit2YHYuCDinJMg4oCUINiu2YTZiiDYp9mE2LLYqNmI2YYg2YrZg9io2LMgUmVsb2FkJyk7Cn07CiQoJ2RlbCcpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nIHx8ICFjb25maXJtKGDYrdiw2YEg2KfZhNis2YfYp9iyICR7cHJldHR5KGVkaXRpbmcuY29kZSl9INmG2YfYp9im2YrYp9mL2J9gKSkgcmV0dXJuOwogIGF3YWl0IGFwaSgnZGVsZXRlJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUgfSk7IGNsb3NlRHJhd2VyKCk7IGF3YWl0IGxvYWQoKTsgdG9hc3QoJ9in2YbYrdiw2YEnKTsKfTsKaW5pdCgpOwpzZXRJbnRlcnZhbCgoKSA9PiB7IGlmICghJCgnYXBwJykuY2xhc3NMaXN0LmNvbnRhaW5zKCdoaWRlJykgJiYgISQoJ2RyYXdlcicpLmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpKSBsb2FkKCk7IH0sIDMwMDAwKTsKPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"), (c) => c.charCodeAt(0)));
