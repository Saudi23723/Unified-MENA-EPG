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
const PAGE = new TextDecoder().decode(Uint8Array.from(atob("PCFkb2N0eXBlIGh0bWw+PGh0bWwgbGFuZz0iYXIiIGRpcj0icnRsIj48aGVhZD48bWV0YSBjaGFyc2V0PSJ1dGYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEiPgo8dGl0bGU+U0FVREkuVFYgwrcg2YTZiNit2Kkg2KfZhNil2K/Yp9ix2Kk8L3RpdGxlPgo8c3R5bGU+Cjpyb290ey0tYmc6IzA5MGMxMjstLXA6IzEyMTcyMjstLXAyOiMxOTIwMmU7LS1wMzojMjIyYjNkOy0tbGluZTojMjMyYzNlOy0tdDojZjJmNGY4Oy0tdDI6IzlhYTNiNTstLXQzOiM2Yjc0ODg7LS1hOiMwMGQ2OGY7LS1hMjojMDBiMzc3Oy0tcjojZmY0ZDVlOy0teTojZmZiMDIwOy0tYjojNGRhM2ZmOy0tc2g6MCAxMHB4IDMwcHggcmdiYSgwLDAsMCwuMzUpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveH1odG1sLGJvZHl7aGVpZ2h0OjEwMCV9CmJvZHl7bWFyZ2luOjA7YmFja2dyb3VuZDpyYWRpYWwtZ3JhZGllbnQoMTIwMHB4IDYwMHB4IGF0IDEwMCUgLTEwJSwjMGYyYTIwIDAsdHJhbnNwYXJlbnQgNjAlKSx2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdCk7Zm9udDoxNXB4LzEuNTUgc3lzdGVtLXVpLC1hcHBsZS1zeXN0ZW0sIlNlZ29lIFVJIixUYWhvbWEsc2Fucy1zZXJpZn0KYXtjb2xvcjppbmhlcml0fS5oaWRle2Rpc3BsYXk6bm9uZSFpbXBvcnRhbnR9Lm11dGVke2NvbG9yOnZhcigtLXQyKX0uY29kZXtmb250LWZhbWlseTp1aS1tb25vc3BhY2UsTWVubG8sbW9ub3NwYWNlO2xldHRlci1zcGFjaW5nOjEuNXB4O2RpcmVjdGlvbjpsdHI7ZGlzcGxheTppbmxpbmUtYmxvY2s7d2hpdGUtc3BhY2U6bm93cmFwfQouc2hlbGx7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyNDBweCAxZnI7bWluLWhlaWdodDoxMDB2aH0KYXNpZGV7YmFja2dyb3VuZDpyZ2JhKDE4LDIzLDM0LC44NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMTBweCk7Ym9yZGVyLWxlZnQ6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6MjJweCAxNHB4O3Bvc2l0aW9uOnN0aWNreTt0b3A6MDtoZWlnaHQ6MTAwdmg7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4fQouYnJhbmR7Zm9udC1zaXplOjI0cHg7Zm9udC13ZWlnaHQ6ODAwO2xldHRlci1zcGFjaW5nOi41cHg7cGFkZGluZzo0cHggMTBweCAxOHB4O2RpcmVjdGlvbjpsdHI7dGV4dC1hbGlnbjpyaWdodH0uYnJhbmQgYntjb2xvcjp2YXIoLS1hKX0KLm5hdntkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4O3BhZGRpbmc6MTFweCAxMnB4O2JvcmRlci1yYWRpdXM6MTJweDtjb2xvcjp2YXIoLS10Mik7Y3Vyc29yOnBvaW50ZXI7Zm9udC13ZWlnaHQ6NjAwO2JvcmRlcjowO2JhY2tncm91bmQ6bm9uZTt3aWR0aDoxMDAlO3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjE1cHh9Ci5uYXY6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCl9Lm5hdi5vbntiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx0cmFuc3BhcmVudCxyZ2JhKDAsMjE0LDE0MywuMTYpKTtjb2xvcjp2YXIoLS10KTtib3gtc2hhZG93Omluc2V0IC0zcHggMCAwIHZhcigtLWEpfQoubmF2IC5pY3t3aWR0aDoyMnB4O3RleHQtYWxpZ246Y2VudGVyfS5zcGFjZXJ7ZmxleDoxfQptYWlue3BhZGRpbmc6MjZweCAzMHB4IDYwcHg7bWF4LXdpZHRoOjEyNDBweDt3aWR0aDoxMDAlfQoudG9we2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjE0cHg7bWFyZ2luLWJvdHRvbToyMnB4O2ZsZXgtd3JhcDp3cmFwfQpoMXttYXJnaW46MDtmb250LXNpemU6MjZweH1oMnttYXJnaW46MCAwIDRweDtmb250LXNpemU6MThweH0uc3Vie2NvbG9yOnZhcigtLXQyKTttYXJnaW46MnB4IDAgMH0KLmJ0bntiYWNrZ3JvdW5kOnZhcigtLWEpO2NvbG9yOiMwMzE0MGM7Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czoxMXB4O3BhZGRpbmc6MTFweCAxOHB4O2ZvbnQtd2VpZ2h0OjgwMDtmb250LXNpemU6MTQuNXB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo4cHg7dHJhbnNpdGlvbjouMTVzfQouYnRuOmhvdmVye2JhY2tncm91bmQ6dmFyKC0tYTIpfS5idG4uZ2hvc3R7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKX0uYnRuLmdob3N0OmhvdmVye2JhY2tncm91bmQ6dmFyKC0tcDMpfQouYnRuLnJlZHtiYWNrZ3JvdW5kOnJnYmEoMjU1LDc3LDk0LC4xNCk7Y29sb3I6dmFyKC0tcik7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDI1NSw3Nyw5NCwuMzUpfS5idG4uc217cGFkZGluZzo3cHggMTJweDtmb250LXNpemU6MTNweDtib3JkZXItcmFkaXVzOjlweH0KLnN0YXRze2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KGF1dG8tZml0LG1pbm1heCgxMzhweCwxZnIpKTtnYXA6MTRweDttYXJnaW4tYm90dG9tOjIycHh9Ci5zdGF0e2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDE4MGRlZyx2YXIoLS1wMiksdmFyKC0tcCkpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNnB4O3BhZGRpbmc6MTZweCAxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpO2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246LjE1c30KLnN0YXQ6aG92ZXJ7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoLTJweCk7Ym9yZGVyLWNvbG9yOiMyZjNhNTJ9Ci5zdGF0IC5ue2ZvbnQtc2l6ZTozMHB4O2ZvbnQtd2VpZ2h0OjgwMDttYXJnaW4tdG9wOjRweH0uc3RhdCAubHtjb2xvcjp2YXIoLS10Mik7Zm9udC1zaXplOjEzcHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6N3B4fQouZG90e3dpZHRoOjlweDtoZWlnaHQ6OXB4O2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrfQouY2FyZHtiYWNrZ3JvdW5kOnZhcigtLXApO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpfQouY2FyZC1oe2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjEycHg7cGFkZGluZzoxNnB4IDE4cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7ZmxleC13cmFwOndyYXB9Ci50b29sc3tkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5zZWFyY2h7YmFja2dyb3VuZDp2YXIoLS1wMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjExcHg7cGFkZGluZzo5cHggMTJweDtjb2xvcjp2YXIoLS10KTttaW4td2lkdGg6MjQwcHg7Zm9udC1zaXplOjE0cHh9Ci5jaGlwe2JhY2tncm91bmQ6dmFyKC0tcDIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Y29sb3I6dmFyKC0tdDIpO2JvcmRlci1yYWRpdXM6OTlweDtwYWRkaW5nOjZweCAxM3B4O2ZvbnQtc2l6ZToxM3B4O2N1cnNvcjpwb2ludGVyO2ZvbnQtd2VpZ2h0OjYwMH0KLmNoaXAub257YmFja2dyb3VuZDpyZ2JhKDAsMjE0LDE0MywuMTQpO2JvcmRlci1jb2xvcjpyZ2JhKDAsMjE0LDE0MywuNSk7Y29sb3I6dmFyKC0tYSl9Ci53cmFwe292ZXJmbG93LXg6YXV0b310YWJsZXt3aWR0aDoxMDAlO2JvcmRlci1jb2xsYXBzZTpjb2xsYXBzZX0KdGgsdGR7dGV4dC1hbGlnbjpyaWdodDtwYWRkaW5nOjEycHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1saW5lKTtmb250LXNpemU6MTRweDt2ZXJ0aWNhbC1hbGlnbjptaWRkbGV9CnRoe2NvbG9yOnZhcigtLXQzKTtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHh9CnRib2R5IHRye3RyYW5zaXRpb246LjEycztjdXJzb3I6cG9pbnRlcn10Ym9keSB0cjpob3ZlcntiYWNrZ3JvdW5kOnJnYmEoMjU1LDI1NSwyNTUsLjAyNSl9Ci53aG8gYntkaXNwbGF5OmJsb2NrfS53aG8gc21hbGx7Y29sb3I6dmFyKC0tdDMpfQoudGFne2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo2cHg7cGFkZGluZzozcHggMTBweDtib3JkZXItcmFkaXVzOjk5cHg7Zm9udC1zaXplOjEycHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7bWFyZ2luOjJweCAwIDJweCA0cHg7Zm9udC13ZWlnaHQ6NjAwfQouc3R7ZGlzcGxheTppbmxpbmUtZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjdweDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEzcHh9Ci5zLW9ue2NvbG9yOnZhcigtLWEpfS5zLXdhaXR7Y29sb3I6dmFyKC0tYil9LnMtZXhwe2NvbG9yOnZhcigtLXIpfS5zLW9mZntjb2xvcjp2YXIoLS10Myl9LnMtc29vbntjb2xvcjp2YXIoLS15KX0KLm9ubGluZXt3aWR0aDo4cHg7aGVpZ2h0OjhweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZhcigtLWEpO2JveC1zaGFkb3c6MCAwIDAgNHB4IHJnYmEoMCwyMTQsMTQzLC4xOCk7ZGlzcGxheTppbmxpbmUtYmxvY2t9Ci5lbXB0eXtwYWRkaW5nOjQwcHg7dGV4dC1hbGlnbjpjZW50ZXI7Y29sb3I6dmFyKC0tdDIpfQovKiBkcmF3ZXIgKi8KLnNjcmlte3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7YmFja2dyb3VuZDpyZ2JhKDAsMCwwLC41NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMnB4KTt6LWluZGV4OjIwO29wYWNpdHk6MDtwb2ludGVyLWV2ZW50czpub25lO3RyYW5zaXRpb246LjJzfQouc2NyaW0ub3BlbntvcGFjaXR5OjE7cG9pbnRlci1ldmVudHM6YXV0b30KLmRyYXdlcntwb3NpdGlvbjpmaXhlZDt0b3A6MDtib3R0b206MDtsZWZ0OjA7d2lkdGg6bWluKDUyMHB4LDEwMCUpO2JhY2tncm91bmQ6dmFyKC0tcCk7Ym9yZGVyLXJpZ2h0OjFweCBzb2xpZCB2YXIoLS1saW5lKTt6LWluZGV4OjIxO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC0xMDAlKTt0cmFuc2l0aW9uOi4yNXMgY3ViaWMtYmV6aWVyKC4yLC44LC4yLDEpO2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW47Ym94LXNoYWRvdzp2YXIoLS1zaCl9Ci5kcmF3ZXIub3Blbnt0cmFuc2Zvcm06bm9uZX0KLmRoe3BhZGRpbmc6MjBweCAyMnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXJ9Ci5kYntwYWRkaW5nOjZweCAyMnB4IDIycHg7b3ZlcmZsb3c6YXV0bztmbGV4OjE7bWluLWhlaWdodDowfS5kZntwYWRkaW5nOjE2cHggMjJweDtib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1saW5lKTtkaXNwbGF5OmZsZXg7Z2FwOjEwcHg7ZmxleC13cmFwOndyYXB9Ci5zZWN7bWFyZ2luLXRvcDoyMHB4O3BhZGRpbmc6MTZweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTRweDtiYWNrZ3JvdW5kOnZhcigtLXAyKX0KLnNlYyBoM3ttYXJnaW46MCAwIDRweDtmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1hKTtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo4cHh9CmxhYmVse2Rpc3BsYXk6YmxvY2s7Y29sb3I6dmFyKC0tdDIpO2ZvbnQtc2l6ZToxMi41cHg7bWFyZ2luOjEycHggMCA1cHg7Zm9udC13ZWlnaHQ6NjAwfQppbnB1dCxzZWxlY3R7d2lkdGg6MTAwJTtiYWNrZ3JvdW5kOnZhcigtLWJnKTtjb2xvcjp2YXIoLS10KTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTBweDtwYWRkaW5nOjExcHggMTJweDtmb250LXNpemU6MTVweH0KaW5wdXQ6Zm9jdXMsc2VsZWN0OmZvY3Vze291dGxpbmU6MnB4IHNvbGlkIHZhcigtLWEpO2JvcmRlci1jb2xvcjp0cmFuc3BhcmVudH0KLmdyaWQye2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6MTBweH0ucXVpY2t7ZGlzcGxheTpmbGV4O2dhcDo2cHg7bWFyZ2luLXRvcDo4cHg7ZmxleC13cmFwOndyYXB9Ci54bHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO3BhZGRpbmc6OXB4IDEycHg7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEwcHg7bWFyZ2luLXRvcDo4cHg7YmFja2dyb3VuZDp2YXIoLS1iZyl9Ci5tc2d7bWluLWhlaWdodDoyMnB4O21hcmdpbi10b3A6MTBweDtmb250LXdlaWdodDo2MDB9Lm9re2NvbG9yOnZhcigtLWEpfS5iYWR7Y29sb3I6dmFyKC0tcil9Ci5zd2l0Y2h7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjttYXJnaW4tdG9wOjEycHh9Ci50Z3twb3NpdGlvbjpyZWxhdGl2ZTt3aWR0aDo0NnB4O2hlaWdodDoyNnB4O2JhY2tncm91bmQ6dmFyKC0tcDMpO2JvcmRlci1yYWRpdXM6OTlweDtjdXJzb3I6cG9pbnRlcjt0cmFuc2l0aW9uOi4ycztib3JkZXI6MH0KLnRnOjphZnRlcntjb250ZW50OiIiO3Bvc2l0aW9uOmFic29sdXRlO3RvcDozcHg7cmlnaHQ6M3B4O3dpZHRoOjIwcHg7aGVpZ2h0OjIwcHg7Ym9yZGVyLXJhZGl1czo1MCU7YmFja2dyb3VuZDojZmZmO3RyYW5zaXRpb246LjJzfQoudGcub257YmFja2dyb3VuZDp2YXIoLS1hKX0udGcub246OmFmdGVye3JpZ2h0OjIzcHh9Ci5sb2dpbnttYXgtd2lkdGg6NDIwcHg7bWFyZ2luOjEydmggYXV0bztwYWRkaW5nOjI4cHh9Ci50b2FzdHtwb3NpdGlvbjpmaXhlZDtib3R0b206MjJweDtsZWZ0OjUwJTt0cmFuc2Zvcm06dHJhbnNsYXRlWCgtNTAlKSB0cmFuc2xhdGVZKDMwcHgpO2JhY2tncm91bmQ6dmFyKC0tcDMpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoxMnB4IDE4cHg7Ym9yZGVyLXJhZGl1czoxMnB4O29wYWNpdHk6MDt0cmFuc2l0aW9uOi4yNXM7ei1pbmRleDo0MDtmb250LXdlaWdodDo2MDB9Ci50b2FzdC5zaG93e29wYWNpdHk6MTt0cmFuc2Zvcm06dHJhbnNsYXRlWCgtNTAlKX0KLmhlbHB7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoYXV0by1maXQsbWlubWF4KDI2MHB4LDFmcikpO2dhcDoxNHB4fQouaGVscCAuY2FyZHtwYWRkaW5nOjE4cHh9LmhlbHAgb2x7bWFyZ2luOjhweCAwIDA7cGFkZGluZy1pbmxpbmUtc3RhcnQ6MjBweDtjb2xvcjp2YXIoLS10Mil9Ci5waWxse2ZvbnQtc2l6ZToxMXB4O3BhZGRpbmc6MnB4IDhweDtib3JkZXItcmFkaXVzOjk5cHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7Y29sb3I6dmFyKC0tdDIpfQpAbWVkaWEgKG1heC13aWR0aDo4MjBweCl7LnNoZWxse2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnJ9YXNpZGV7cG9zaXRpb246c3RhdGljO2hlaWdodDphdXRvO2ZsZXgtZGlyZWN0aW9uOnJvdztvdmVyZmxvdy14OmF1dG87cGFkZGluZzoxMHB4O2JvcmRlcjowO2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpfQogLmJyYW5ke3BhZGRpbmc6NnB4IDEwcHh9Lm5hdnt3aWR0aDphdXRvO3doaXRlLXNwYWNlOm5vd3JhcH0uc3BhY2Vye2Rpc3BsYXk6bm9uZX1tYWlue3BhZGRpbmc6MThweCAxNHB4fS5zZWFyY2h7bWluLXdpZHRoOjA7ZmxleDoxfQogLmhpZGUtbXtkaXNwbGF5Om5vbmV9dGgsdGR7cGFkZGluZzoxMHB4IDhweH19Ci5ub3dvbiwubm93b2Zme2Rpc3BsYXk6YmxvY2s7bWFyZ2luLXRvcDo0cHg7Zm9udC1zaXplOjEycHg7bGluZS1oZWlnaHQ6MS41O3doaXRlLXNwYWNlOm5vcm1hbH0ubm93b257Y29sb3I6dmFyKC0tYSl9Lm5vd29mZntjb2xvcjp2YXIoLS10Myl9LndoZXJle2Rpc3BsYXk6YmxvY2s7bWFyZ2luLXRvcDoycHh9LnZwbm9ue2NvbG9yOiMyZTlkNWI7Zm9udC13ZWlnaHQ6NjAwfQo8L3N0eWxlPjwvaGVhZD48Ym9keT4KCjxkaXYgaWQ9ImxvZ2luIiBjbGFzcz0iY2FyZCBsb2dpbiBoaWRlIj4KICA8ZGl2IGNsYXNzPSJicmFuZCIgc3R5bGU9InBhZGRpbmc6MCAwIDEwcHgiPlNBVURJPGI+LlRWPC9iPjwvZGl2PgogIDxoMiBpZD0ibHQiPtiv2K7ZiNmEINmE2YjYrdipINin2YTYpdiv2KfYsdipPC9oMj48cCBpZD0ibGgiIGNsYXNzPSJtdXRlZCI+PC9wPgogIDxsYWJlbD7Zg9mE2YXYqSDYp9mE2LPYsTwvbGFiZWw+PGlucHV0IGlkPSJwdyIgdHlwZT0icGFzc3dvcmQiIGF1dG9jb21wbGV0ZT0iY3VycmVudC1wYXNzd29yZCI+CiAgPGRpdiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij48YnV0dG9uIGlkPSJnbyIgY2xhc3M9ImJ0biIgc3R5bGU9IndpZHRoOjEwMCU7anVzdGlmeS1jb250ZW50OmNlbnRlciI+2K/YrtmI2YQ8L2J1dHRvbj48L2Rpdj48ZGl2IGlkPSJsbSIgY2xhc3M9Im1zZyBiYWQiPjwvZGl2Pgo8L2Rpdj4KCjxkaXYgaWQ9ImFwcCIgY2xhc3M9InNoZWxsIGhpZGUiPgogIDxhc2lkZT4KICAgIDxkaXYgY2xhc3M9ImJyYW5kIj5TQVVESTxiPi5UVjwvYj48L2Rpdj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiBvbiIgZGF0YS12PSJkYXNoIj48c3BhbiBjbGFzcz0iaWMiPuKXpzwvc3Bhbj4g2YTZiNit2Kkg2KfZhNiq2K3Zg9mFPC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJuYXYiIGRhdGEtdj0iZGV2cyI+PHNwYW4gY2xhc3M9ImljIj7ilqQ8L3NwYW4+INin2YTYo9is2YfYstipPC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJuYXYiIGRhdGEtdj0icHJvbW8iPjxzcGFuIGNsYXNzPSJpYyI+8J+Onzwvc3Bhbj4gUHJvbW8gY29kZXM8L2J1dHRvbj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgZGF0YS12PSJwYXkiPjxzcGFuIGNsYXNzPSJpYyI+8J+Sszwvc3Bhbj4g2KfZhNiv2YHYuTwvYnV0dG9uPgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IiBkYXRhLXY9ImhlbHAiPjxzcGFuIGNsYXNzPSJpYyI+Pzwvc3Bhbj4g2LfYsdmK2YLYqSDYp9mE2KfYs9iq2K7Yr9in2YU8L2J1dHRvbj4KICAgIDxkaXYgY2xhc3M9InNwYWNlciI+PC9kaXY+CiAgICA8YnV0dG9uIGNsYXNzPSJuYXYiIGlkPSJvdXQiPjxzcGFuIGNsYXNzPSJpYyI+4o6LPC9zcGFuPiDYrtix2YjYrDwvYnV0dG9uPgogIDwvYXNpZGU+CiAgPG1haW4+CiAgICA8ZGl2IGNsYXNzPSJ0b3AiPgogICAgICA8ZGl2PjxoMSBpZD0idnQiPtmE2YjYrdipINin2YTYqtit2YPZhTwvaDE+PHAgY2xhc3M9InN1YiIgaWQ9InZzIj7Zhti42LHYqSDYs9ix2YrYudipINi52YTZiSDZg9mEINin2YTYo9is2YfYstipPC9wPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ0b29scyI+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBpZD0icmVmcmVzaCI+4p+zINiq2K3Yr9mK2Ks8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJhZGQiPu+8iyDYrNmH2KfYsiDYrNiv2YrYrzwvYnV0dG9uPjwvZGl2PgogICAgPC9kaXY+CgogICAgPHNlY3Rpb24gaWQ9InYtZGFzaCI+CiAgICAgIDxkaXYgY2xhc3M9InN0YXRzIiBpZD0ic3RhdHMiPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPjxoMj7Zitit2KrYp9isINin2YbYqtio2KfZh9mDPC9oMj48c3BhbiBjbGFzcz0ibXV0ZWQiIGlkPSJhdHRuLW4iPjwvc3Bhbj48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJ3cmFwIj48dGFibGU+PHRib2R5IGlkPSJhdHRuIj48L3Rib2R5PjwvdGFibGU+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPjxoMj7Ytdit2Kkg2KfZhNiq2LfYqNmK2YI8L2gyPjxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9ImhsLW4iPjwvc3Bhbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGlkPSJobC1jbHIiPtmF2LPYrTwvYnV0dG9uPjwvZGl2PgogICAgICAgIDxwIGNsYXNzPSJtdXRlZCI+2YPZhCDZhdix2Kkg2KfZhNiq2LfYqNmK2YIg2KjZitiq2LPZg9mR2LEg2KjYrti32KMg2KPZiCDYp9mE2LTYp9i02Kkg2KjYqti52YTZgiDYudmE2Ykg2KPZiiDYrNmH2KfYstiMINio2YrZiNi12YQg2YfZiNmGINmE2K3Yp9mE2Ycg2LTZiCDYtdin2LEuPC9wPgogICAgICAgIDxkaXYgY2xhc3M9IndyYXAiPjx0YWJsZT48dGJvZHkgaWQ9ImhsIj48L3Rib2R5PjwvdGFibGU+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgoKICAgIDxzZWN0aW9uIGlkPSJ2LWRldnMiIGNsYXNzPSJoaWRlIj4KICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1oIj4KICAgICAgICAgIDxkaXYgY2xhc3M9InRvb2xzIiBpZD0iY2hpcHMiPjwvZGl2PgogICAgICAgICAgPGlucHV0IGNsYXNzPSJzZWFyY2giIGlkPSJxIiBwbGFjZWhvbGRlcj0i2KjYrdirOiDZg9mI2K/YjCDYp9iz2YXYjCBwbGF5bGlzdOKApiI+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0id3JhcCI+PHRhYmxlPgogICAgICAgICAgPHRoZWFkPjx0cj48dGg+2KfZhNmD2YjYrzwvdGg+PHRoPtin2YTYstio2YjZhjwvdGg+PHRoPlBsYXlsaXN0czwvdGg+PHRoPtin2YTYrdin2YTYqTwvdGg+PHRoIGNsYXNzPSJoaWRlLW0iPtii2K7YsSDYuNmH2YjYsTwvdGg+PHRoIGNsYXNzPSJoaWRlLW0iPtmK2YbYqtmH2Yo8L3RoPjwvdHI+PC90aGVhZD4KICAgICAgICAgIDx0Ym9keSBpZD0idGIiPjwvdGJvZHk+PC90YWJsZT48L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CgogICAgPHNlY3Rpb24gaWQ9InYtcHJvbW8iIGNsYXNzPSJoaWRlIj4KICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1oIj48aDI+2YPZiNivINis2K/ZitivPC9oMj48c3BhbiBjbGFzcz0ibXV0ZWQiIGlkPSJwcm9tby1uIj48L3NwYW4+PC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0icGFkZGluZzoxNHB4IDE4cHg7ZGlzcGxheTpmbGV4O2dhcDoxMHB4O2ZsZXgtd3JhcDp3cmFwO2FsaWduLWl0ZW1zOmVuZCI+CiAgICAgICAgICA8ZGl2PjxsYWJlbD7ZhNmF2YrZhtifICjZhdmE2KfYrdi42Kkg2KXZhNmDKTwvbGFiZWw+PGlucHV0IGlkPSJwbm90ZSIgcGxhY2Vob2xkZXI9ItmF2KvZhNin2Ys6INij2KjZiCDYo9it2YXYryI+PC9kaXY+CiAgICAgICAgICA8ZGl2PjxsYWJlbD7Yp9mE2LnYr9ivPC9sYWJlbD48c2VsZWN0IGlkPSJwY291bnQiPjxvcHRpb24+MTwvb3B0aW9uPjxvcHRpb24+Mzwvb3B0aW9uPjxvcHRpb24+NTwvb3B0aW9uPjxvcHRpb24+MTA8L29wdGlvbj48L3NlbGVjdD48L2Rpdj4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biIgaWQ9InBnZW4iPu+8iyDYo9i12K/YsTwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9IndyYXAiPjx0YWJsZT4KICAgICAgICAgIDx0aGVhZD48dHI+PHRoPtin2YTZg9mI2K88L3RoPjx0aD7ZhNmF2YrZhjwvdGg+PHRoPtin2YTYrdin2YTYqTwvdGg+PHRoPjwvdGg+PC90cj48L3RoZWFkPgogICAgICAgICAgPHRib2R5IGlkPSJwdGIiPjwvdGJvZHk+PC90YWJsZT48L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CgogICAgPHNlY3Rpb24gaWQ9InYtcGF5IiBjbGFzcz0iaGlkZSI+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtaCI+PGgyPtin2YTYr9mB2Lkg2K/Yp9iu2YQg2KfZhNiq2LfYqNmK2YI8L2gyPjxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9InBheS1zdCI+PC9zcGFuPjwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9InBhZGRpbmc6MTRweCAxOHB4O21heC13aWR0aDo2NDBweCI+CiAgICAgICAgICA8cCBjbGFzcz0ibXV0ZWQiIHN0eWxlPSJmb250LXNpemU6MTMuNXB4O2xpbmUtaGVpZ2h0OjEuOCI+2KfZhNmE2Yog2YXYpyDYudmG2K/ZhyBQcm9tbyBjb2RlINio2YrYtNmI2YEg2LnZhNmJINi02KfYtNipINin2YTYqtmB2LnZitmEINiy2LEgwqtCdXkgYWNjZXNzwrsg2YXYuSBRUi4g2KjZitmB2KrYrSDZhdmGINiq2YTZgdmI2YbZhyDYtdmB2K3YqSDZgdmK2YfYpyDZg9mI2K8g2KzZh9in2LLZhyDZiNin2YTYs9i52LEg2YjYstixIDxiPlBheSB3aXRoIFZlbm1vPC9iPtiMINmI2KfZhNmF2KjZhNi6INmI2KfZhNmF2YTYp9it2LjYqSAo2YPZiNivINin2YTYrNmH2KfYsikg2YXYudio2ZHZitmK2YYg2YTYrdin2YTZh9mFLiDZhNmF2Kcg2KrZiNi12YTZgyDYp9mE2K/Zgdi52Kkg2LnZhNmJIFZlbm1v2Iwg2KfZhNmF2YTYp9it2LjYqSDZgdmK2YfYpyDZg9mI2K8g2KfZhNis2YfYp9iyOiDZgdi52ZHZhNmHINmF2YYgwqvYp9mE2KPYrNmH2LLYqcK7INiy2Yog2KfZhNi52KfYr9ipLjwvcD4KICAgICAgICAgIDxsYWJlbD7Yp9mE2LPYudixINin2YTZhNmKINio2YrYuNmH2LEg2YTZhNiy2KjZiNmGICjYsdmC2YUg2KjYp9mE2K/ZiNmE2KfYsSk8L2xhYmVsPjxpbnB1dCBpZD0icGF5LXByaWNlIiBwbGFjZWhvbGRlcj0iMjUwIiBzdHlsZT0iZGlyZWN0aW9uOmx0cjt0ZXh0LWFsaWduOmxlZnQiPgogICAgICAgICAgPGxhYmVsPtin2LPZhSDYp9mE2YXYs9iq2K7Yr9mFINi52YTZiSBWZW5tbyAo2KjYr9mI2YYgQCk8L2xhYmVsPjxpbnB1dCBpZD0icGF5LWxpbmsiIHBsYWNlaG9sZGVyPSJTYWlmLVNhdWRpIiBzdHlsZT0iZGlyZWN0aW9uOmx0cjt0ZXh0LWFsaWduOmxlZnQiPgogICAgICAgICAgPGRpdiBjbGFzcz0ic3dpdGNoIj48c3Bhbj7Yp9mE2K/Zgdi5INi02LrZkdin2YQ8L3NwYW4+PGJ1dHRvbiBjbGFzcz0idGciIGlkPSJwYXktb24iIHR5cGU9ImJ1dHRvbiI+PC9idXR0b24+PC9kaXY+CiAgICAgICAgICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjEycHgiPjxidXR0b24gY2xhc3M9ImJ0biIgaWQ9InBheS1zYXZlIj7YrdmB2Lg8L2J1dHRvbj4gPHNwYW4gY2xhc3M9Im11dGVkIiBpZD0icGF5LW1zZyI+PC9zcGFuPjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBpZD0idi1oZWxwIiBjbGFzcz0iaGlkZSI+CiAgICAgIDxkaXYgY2xhc3M9ImhlbHAiPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxoMj7Ystio2YjZhiDYrNiv2YrYrzwvaDI+PG9sPjxsaT7Yp9mE2LLYqNmI2YYg2YrZhtiy2ZHZhCBTQVVESS5UViDZhdmGIERvd25sb2FkZXIg2YjZitmB2KrYrdmHLjwvbGk+PGxpPtio2YrYt9mE2Lkg2LnZhNmJINi02KfYtNiq2Ycg2YPZiNivINmF2YYgOCDYo9ix2YLYp9mFLjwvbGk+PGxpPtmH2YjZhjog77yLINis2YfYp9iyINis2K/ZitivIOKGkCDYp9mD2KrYqCDYp9mE2YPZiNivINmI2KfZhNin2LPZhSDZiNin2YTZgCBwbGF5bGlzdCDZiNin2YTZitmI2LLYsS48L2xpPjxsaT7Yp9mE2LLYqNmI2YYg2YrZg9io2LMgUmVsb2FkIOKAlCDYrtmE2LUuPC9saT48L29sPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxoMj7Yo9mD2KvYsSDZhdmGIHBsYXlsaXN0PC9oMj48b2w+PGxpPtin2YHYqtitINin2YTYrNmH2KfYsiDihpAg2YLYs9mFIMKrUGxheWxpc3RzINil2LbYp9mB2YrYqcK7LjwvbGk+PGxpPtin2K7Yqtin2LEg2KfZhNmAIHBsYXlsaXN0INmI2KfZg9iq2Kgg2KfZhNmK2YjYstixINmI2KfZhNio2KfYs9mI2YjYsdivIOKGkCDYo9i22YEuPC9saT48bGk+2KfZhNiy2KjZiNmGINio2YrYrtiq2KfYsSDYqNmK2YbZh9mFINmF2YYgwqtQbGF5bGlzdHPCuyDYqNin2YTYqti32KjZitmCLjwvbGk+PC9vbD48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj48aDI+2KrYrNiv2YrYryDZiNil2YrZgtin2YE8L2gyPjxvbD48bGk+2KfZgdiq2K0g2KfZhNis2YfYp9iyIOKGkCDYo9iy2LHYp9ixICszMCAvICs5MCAvICszNjUg2YrZiNmFLjwvbGk+PGxpPsKr2KfZhNis2YfYp9iyINi02LrZkdin2YTCuyDYqti32YHZitmHINio2YrZiNmC2YEg2KfZhNiu2K/ZhdipINmB2YjYsdin2Ysg2LnZhtivINin2YTYstio2YjZhi48L2xpPjxsaT7Yp9mE2KPYrNmH2LLYqSDYp9mE2YTZiiDYqNiq2YbYqtmH2Yog2K7ZhNin2YQgNyDYo9mK2KfZhSDYqNiq2LfZhNi5INio2KfZhNij2LXZgdixLjwvbGk+PC9vbD48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj48aDI+2KfZhNij2YXYp9mGPC9oMj48b2w+PGxpPtin2YTZitmI2LLYsSDZiNin2YTYqNin2LPZiNmI2LHYryDZhdit2YHZiNi42YrZhiDZhdi02YHZkdix2YrZhi48L2xpPjxsaT7Yp9mE2KjYp9iz2YjZiNix2K8g2YXYpyDYqNmK2LHYrNi5INmK2LjZh9ixINmH2YjZhiDYo9io2K/Yp9mLIOKAlCDYp9iq2LHZg9mHINmB2KfYttmKINmE2YrYqNmC2Ykg2KfZhNmC2K/ZitmFLjwvbGk+PGxpPtix2KfYqNi3INin2YTYqti32KjZitmCOiA8c3BhbiBjbGFzcz0iY29kZSI+c2F1ZGkxLjFzYWlmc2F1ZGkud29ya2Vycy5kZXYvYXBrPC9zcGFuPjwvbGk+PC9vbD48L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CiAgPC9tYWluPgo8L2Rpdj4KCjxkaXYgY2xhc3M9InNjcmltIiBpZD0ic2NyaW0iPjwvZGl2Pgo8ZGl2IGNsYXNzPSJkcmF3ZXIiIGlkPSJkcmF3ZXIiPgogIDxkaXYgY2xhc3M9ImRoIj48ZGl2PjxoMiBpZD0iZHQiPtis2YfYp9iyINis2K/ZitivPC9oMj48ZGl2IGNsYXNzPSJtdXRlZCIgaWQ9ImRzdWIiPjwvZGl2PjwvZGl2PjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgaWQ9ImR4Ij7inJU8L2J1dHRvbj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJkYiI+CiAgICA8ZGl2IGNsYXNzPSJzZWMiPgogICAgICA8aDM+4pGgINin2YTYrNmH2KfYsiDZiNin2YTYstio2YjZhjwvaDM+CiAgICAgIDxsYWJlbD7Zg9mI2K8g2KfZhNis2YfYp9iyICg4INij2LHZgtin2YUg2YXZhiDYtNin2LTYqSDYp9mE2LLYqNmI2YYpPC9sYWJlbD48aW5wdXQgaWQ9ImNvZGUiIGlucHV0bW9kZT0ibnVtZXJpYyIgbWF4bGVuZ3RoPSI5IiBwbGFjZWhvbGRlcj0iMTIzNCA1Njc4IiBjbGFzcz0iY29kZSIgc3R5bGU9InRleHQtYWxpZ246cmlnaHQiPgogICAgICA8bGFiZWw+2KfYs9mFINin2YTYstio2YjZhjwvbGFiZWw+PGlucHV0IGlkPSJuYW1lIiBwbGFjZWhvbGRlcj0i2YXYq9mE2KfZizog2KPYqNmIINij2K3ZhdivIj4gICAgICAgPGxhYmVsPtin2YTYp9iz2YUg2LnZhNmJINi02KfYtNipINin2YTYqtix2K3ZitioIChXZWxjb21lIOKApik8L2xhYmVsPjxpbnB1dCBpZD0id25hbWUiIHBsYWNlaG9sZGVyPSLZhdir2YTYp9mLOiBMYWl0aCIgbWF4bGVuZ3RoPSIzMCI+CiAgICAgIDxkaXYgY2xhc3M9InN3aXRjaCI+PHNwYW4+2KfZhNis2YfYp9iyINi02LrZkdin2YQ8L3NwYW4+PGJ1dHRvbiBjbGFzcz0idGcgb24iIGlkPSJhY3QiIHR5cGU9ImJ1dHRvbiI+PC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNlYyI+CiAgICAgIDxoMz7ikaEg2KfZhNmAIFBsYXlsaXN0INin2YTYo9iz2KfYs9mK2Kk8L2gzPgogICAgICA8bGFiZWw+UGxheWxpc3Q8L2xhYmVsPjxzZWxlY3QgaWQ9InBsIj48L3NlbGVjdD4KICAgICAgPGRpdiBjbGFzcz0iZ3JpZDIiPgogICAgICAgIDxkaXY+PGxhYmVsPtin2YTZitmI2LLYsTwvbGFiZWw+PGlucHV0IGlkPSJ1IiBhdXRvY29tcGxldGU9Im9mZiI+PC9kaXY+CiAgICAgICAgPGRpdj48bGFiZWw+2KfZhNio2KfYs9mI2YjYsdivPC9sYWJlbD48aW5wdXQgaWQ9InAiIHR5cGU9InBhc3N3b3JkIiBhdXRvY29tcGxldGU9Im5ldy1wYXNzd29yZCI+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJtdXRlZCIgaWQ9ImxoaW50IiBzdHlsZT0iZm9udC1zaXplOjEyLjVweDttYXJnaW4tdG9wOjZweCI+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNlYyI+CiAgICAgIDxoMz7ikaIg2KfZhNin2LTYqtix2KfZgzwvaDM+CiAgICAgIDxsYWJlbD7ZitmG2KrZh9mKINio2KrYp9ix2YrYriAo2YHYp9i22YogPSDYqNiv2YjZhiDYp9mG2KrZh9in2KEpPC9sYWJlbD48aW5wdXQgaWQ9ImV4IiB0eXBlPSJkYXRlIj4KICAgICAgPGRpdiBjbGFzcz0icXVpY2siPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjMwIj4rMzAg2YrZiNmFPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWFkZD0iOTAiPis5MCDZitmI2YU8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSIxODAiPis2INi02YfZiNixPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWFkZD0iMzY1Ij4r2LPZhtipPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWFkZD0iMCI+2KjYr9mI2YYg2KfZhtiq2YfYp9ihPC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNlYyIgaWQ9InhzZWMiPgogICAgICA8aDM+4pGjIFBsYXlsaXN0cyDYpdi22KfZgdmK2Kk8L2gzPgogICAgICA8ZGl2IGlkPSJ4bGlzdCI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImdyaWQyIiBzdHlsZT0ibWFyZ2luLXRvcDo2cHgiPjxkaXY+PGxhYmVsPlBsYXlsaXN0PC9sYWJlbD48c2VsZWN0IGlkPSJ4cGwiPjwvc2VsZWN0PjwvZGl2PjxkaXY+PC9kaXY+CiAgICAgICAgPGRpdj48bGFiZWw+2KfZhNmK2YjYstixPC9sYWJlbD48aW5wdXQgaWQ9Inh1IiBhdXRvY29tcGxldGU9Im9mZiI+PC9kaXY+PGRpdj48bGFiZWw+2KfZhNio2KfYs9mI2YjYsdivPC9sYWJlbD48aW5wdXQgaWQ9InhwIiB0eXBlPSJwYXNzd29yZCIgYXV0b2NvbXBsZXRlPSJuZXctcGFzc3dvcmQiPjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgaWQ9InhhZGQiPu+8iyDYo9i22YEgcGxheWxpc3Q8L2J1dHRvbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2VjIiBpZD0idnNlYyI+CiAgICAgIDxoMz7ikaQgVlBOIMK3IFByb3RvbiAo2YXYrNin2YbZiik8L2gzPgogICAgICA8ZGl2IGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxMi41cHg7bGluZS1oZWlnaHQ6MS43Ij7ZhNmD2YQg2KzZh9in2LIg2K3Ys9in2KggUHJvdG9uINmF2KzYp9mG2Yog2K7Yp9i1INmB2YrZhzogPGI+YWNjb3VudC5wcm90b252cG4uY29tPC9iPiDihpAgRG93bmxvYWRzIOKGkCA8Yj5XaXJlR3VhcmQgY29uZmlndXJhdGlvbjwvYj4g4oaQIFBsYXRmb3JtOiBBbmRyb2lkIOKGkCDYs9mK2LHZgdixINmF2KzYp9mG2YogKEZyZWUpIOKGkCBDcmVhdGUg4oaQIERvd25sb2FkLiDYp9mB2KrYrSDYp9mE2YXZhNmBICjigI4uY29uZikg2YjYp9mE2LXZgiDZg9mEINin2YTZhNmKINmB2YrZhyDZh9mI2YYuINin2YTYo9is2YfYstipINin2YTZhNmKINmF2Kcg2KXZhNmH2KcgVlBOINmH2YjZhiDZhdinINio2YrYuNmH2LHZhNmH2Kcg2K7Zitin2LEgVlBOINij2KjYr9in2YsuPC9kaXY+CiAgICAgIDxkaXYgaWQ9InZzdGF0ZSIgc3R5bGU9Im1hcmdpbi10b3A6OHB4O2ZvbnQtc2l6ZToxM3B4Ij48L2Rpdj4KICAgICAgPHRleHRhcmVhIGlkPSJ2Y29uZiIgcm93cz0iNyIgc3BlbGxjaGVjaz0iZmFsc2UiIHBsYWNlaG9sZGVyPSJbSW50ZXJmYWNlXSYjMTA7UHJpdmF0ZUtleSA9IOKApiYjMTA7QWRkcmVzcyA9IDEwLjIuMC4yLzMyJiMxMDsmIzEwO1tQZWVyXSYjMTA7UHVibGljS2V5ID0g4oCmJiMxMDtFbmRwb2ludCA9IOKApjo1MTgyMCIgc3R5bGU9IndpZHRoOjEwMCU7bWFyZ2luLXRvcDo4cHg7ZGlyZWN0aW9uOmx0cjt0ZXh0LWFsaWduOmxlZnQ7Zm9udC1mYW1pbHk6bW9ub3NwYWNlO2ZvbnQtc2l6ZToxMnB4Ij48L3RleHRhcmVhPgogICAgICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjhweDtkaXNwbGF5OmZsZXg7Z2FwOjEwcHgiPgogICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBzbSIgaWQ9InZzYXZlIj7YrdmB2Lgg2KfZhNmAIFZQTjwvYnV0dG9uPgogICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgaWQ9InZkZWwiPti02YrZhCDYp9mE2YAgVlBOPC9idXR0b24+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJtc2ciIGlkPSJzbSI+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iZGYiPjxidXR0b24gY2xhc3M9ImJ0biIgaWQ9InNhdmUiPtit2YHYuDwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgaWQ9ImNhbmNlbCI+2KXZhNi62KfYoTwvYnV0dG9uPjxzcGFuIGNsYXNzPSJzcGFjZXIiIHN0eWxlPSJmbGV4OjEiPjwvc3Bhbj48YnV0dG9uIGNsYXNzPSJidG4gcmVkIGhpZGUiIGlkPSJkZWwiPtit2LDZgSDYp9mE2KzZh9in2LI8L2J1dHRvbj48L2Rpdj4KPC9kaXY+CjxkaXYgY2xhc3M9InRvYXN0IiBpZD0idG9hc3QiPjwvZGl2PgoKPHNjcmlwdD4KY29uc3QgJCA9IChpZCkgPT4gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpOwpjb25zdCBhcGkgPSAocCwgYikgPT4gZmV0Y2goJy9hZG1pbi9hcGkvJyArIHAsIGIgPyB7IG1ldGhvZDogJ1BPU1QnLCBoZWFkZXJzOiB7ICdDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbicgfSwgYm9keTogSlNPTi5zdHJpbmdpZnkoYiksIGNyZWRlbnRpYWxzOiAnc2FtZS1vcmlnaW4nIH0gOiB7IGNyZWRlbnRpYWxzOiAnc2FtZS1vcmlnaW4nIH0pCiAgLnRoZW4oYXN5bmMgKHIpID0+ICh7IG9rOiByLm9rLCAuLi4oYXdhaXQgci5qc29uKCkuY2F0Y2goKCkgPT4gKHt9KSkpIH0pKTsKY29uc3QgZXNjID0gKHMpID0+IFN0cmluZyhzID8/ICcnKS5yZXBsYWNlKC9bJjw+IiddL2csIChjKSA9PiAoeyAnJic6ICcmYW1wOycsICc8JzogJyZsdDsnLCAnPic6ICcmZ3Q7JywgJyInOiAnJnF1b3Q7JywgIiciOiAnJiMzOTsnIH1bY10pKTsKY29uc3QgREFZID0gODY0MDAwMDA7CmNvbnN0IGFnbyA9ICh0KSA9PiB7IGlmICghdCkgcmV0dXJuICfigJQnOyBjb25zdCBtID0gTWF0aC5yb3VuZCgoRGF0ZS5ub3coKSAtIHQpIC8gNjAwMDApOyByZXR1cm4gbSA8IDEgPyAn2KfZhNii2YYnIDogbSA8IDYwID8gYCR7bX0g2K/ZgtmK2YLYqWAgOiBtIDwgMTQ0MCA/IGAke01hdGgucm91bmQobSAvIDYwKX0g2LPYp9i52KlgIDogYCR7TWF0aC5yb3VuZChtIC8gMTQ0MCl9INmK2YjZhWA7IH07CmNvbnN0IGRheSA9ICh0KSA9PiB0ID8gbmV3IERhdGUodCkudG9JU09TdHJpbmcoKS5zbGljZSgwLCAxMCkgOiAnJzsKY29uc3QgcHJldHR5ID0gKGMpID0+IGMucmVwbGFjZSgvKFxkezR9KShcZHs0fSkvLCAnJDEgJDInKTsKbGV0IGRldnMgPSBbXSwgcGxheWxpc3RzID0gW10sIGZpbHRlciA9ICdhbGwnLCBlZGl0aW5nID0gbnVsbDsKCmZ1bmN0aW9uIHRvYXN0KHQpIHsgY29uc3QgZSA9ICQoJ3RvYXN0Jyk7IGUudGV4dENvbnRlbnQgPSB0OyBlLmNsYXNzTGlzdC5hZGQoJ3Nob3cnKTsgY2xlYXJUaW1lb3V0KGUuX3QpOyBlLl90ID0gc2V0VGltZW91dCgoKSA9PiBlLmNsYXNzTGlzdC5yZW1vdmUoJ3Nob3cnKSwgMjYwMCk7IH0KCmZ1bmN0aW9uIHN0YXRlKGQpIHsKICBjb25zdCBub3cgPSBEYXRlLm5vdygpOwogIGlmICghZC5hY3RpdmUpIHJldHVybiB7IGs6ICdvZmYnLCB0OiAn2YXZiNmC2YjZgScgfTsKICBpZiAoZC5leHBpcmVzICYmIGQuZXhwaXJlcyA8IG5vdykgcmV0dXJuIHsgazogJ2V4cCcsIHQ6ICfZhdmG2KrZh9mKJyB9OwogIGlmICghZC5oYXNfbG9naW4gfHwgIWQucGxheWxpc3QpIHJldHVybiB7IGs6ICd3YWl0JywgdDogJ9io2KfZhtiq2LjYp9ixINin2YTYqtmB2LnZitmEJyB9OwogIGlmIChkLmV4cGlyZXMgJiYgZC5leHBpcmVzIC0gbm93IDwgNyAqIERBWSkgcmV0dXJuIHsgazogJ3Nvb24nLCB0OiBg2YrZhtiq2YfZiiDYrtmE2KfZhCAke01hdGgubWF4KDEsIE1hdGguY2VpbCgoZC5leHBpcmVzIC0gbm93KSAvIERBWSkpfSDZitmI2YVgIH07CiAgcmV0dXJuIHsgazogJ29uJywgdDogJ9i02LrZkdin2YQnIH07Cn0KY29uc3QgaXNPbmxpbmUgPSAoZCkgPT4gZC5zZWVuICYmIERhdGUubm93KCkgLSBkLnNlZW4gPCAyMCAqIDYwMDAwOwovLyB3aGF0IHRoZSBkZXZpY2UgaXMgd2F0Y2hpbmcgbm93ICh0b2xkIGJ5IHRoZSBhcHAgZXZlcnkgMTAwIHMpIG9yIHdhdGNoZWQgbGFzdApjb25zdCBLSU5EID0geyBsaXZlOiAn8J+TuicsIG1vdmllOiAn8J+OrCcsIHNlcmllczogJ/Cfjp4nLCByZWNvcmRpbmc6ICfij7onLCB2aWRlbzogJ+KWticgfTsKY29uc3QgaXNXYXRjaGluZyA9IChkKSA9PiBkLm5vd190ICYmIERhdGUubm93KCkgLSBkLm5vd190IDwgNCAqIDYwMDAwOwovLyB3aGVyZSB0aGUgZGV2aWNlIGlzIG5vdywgZnJvbSBpdHMgaW50ZXJuZXQ6IGZsYWcgKyBjb3VudHJ5ICsgY2l0eSwgYW5kIPCflJIgd2hlbiBpdCBjb21lcyB0aHJvdWdoIG91ciBWUE4KY29uc3QgZmxhZyA9IChjKSA9PiBjICYmIGMubGVuZ3RoID09PSAyID8gU3RyaW5nLmZyb21Db2RlUG9pbnQoLi4uWy4uLmMudG9VcHBlckNhc2UoKV0ubWFwKCh4KSA9PiAxMjczOTcgKyB4LmNoYXJDb2RlQXQoMCkpKSA6ICcnOwpmdW5jdGlvbiB3aGVyZShkKSB7CiAgaWYgKCFkLmNvdW50cnkpIHJldHVybiAnJzsKICBsZXQgbiA9IGQuY291bnRyeTsgdHJ5IHsgbiA9IG5ldyBJbnRsLkRpc3BsYXlOYW1lcyhbJ2FyJ10sIHsgdHlwZTogJ3JlZ2lvbicgfSkub2YoZC5jb3VudHJ5KSB8fCBkLmNvdW50cnk7IH0gY2F0Y2ggKGUpIHt9CiAgY29uc3QgdiA9IGQub25fdnBuID8gJyA8c3BhbiBjbGFzcz0idnBub24iPvCflJIgVlBOINi02LrZkdin2YQgKFByb3Rvbik8L3NwYW4+JyA6IGQuaGFzX3ZwbiA/ICcgPHNwYW4gY2xhc3M9Im11dGVkIj7CtyBWUE4g2YXYt9mB2Yo8L3NwYW4+JyA6ICcnOwogIHJldHVybiBgPHNtYWxsIGNsYXNzPSJ3aGVyZSI+8J+TjSAke2ZsYWcoZC5jb3VudHJ5KX0gJHtlc2Mobil9JHtkLmNpdHkgPyAnIMK3ICcgKyBlc2MoZC5jaXR5KSA6ICcnfSR7dn08L3NtYWxsPmA7Cn0KZnVuY3Rpb24gd2F0Y2hpbmcoZCkgewogIGlmICghZC5ub3dfdCB8fCAhZC5ub3dfdGl0bGUpIHJldHVybiAnJzsKICBjb25zdCB3aGF0ID0gYCR7S0lORFtkLm5vd19raW5kXSB8fCAn4pa2J30gJHtlc2MoZC5ub3dfdGl0bGUpfSR7ZC5ub3dfcGxheWxpc3QgPyAnIDxzcGFuIGNsYXNzPSJtdXRlZCI+wrcgJyArIGVzYyhkLm5vd19wbGF5bGlzdCkgKyAnPC9zcGFuPicgOiAnJ31gOwogIHJldHVybiBpc1dhdGNoaW5nKGQpID8gYDxzbWFsbCBjbGFzcz0ibm93b24iPjxzcGFuIGNsYXNzPSJvbmxpbmUiPjwvc3Bhbj7Ziti02KfZh9ivINin2YTYotmGOiAke3doYXR9PC9zbWFsbD5gIDogYDxzbWFsbCBjbGFzcz0ibm93b2ZmIj7Yotiu2LEg2YXYtNin2YfYr9ipICjZgtio2YQgJHthZ28oZC5ub3dfdCl9KTogJHt3aGF0fTwvc21hbGw+YDsKfQoKYXN5bmMgZnVuY3Rpb24gaW5pdCgpIHsKICBjb25zdCBzID0gYXdhaXQgYXBpKCdzdGF0ZScpOwogIHBsYXlsaXN0cyA9IHMucGxheWxpc3RzIHx8IFtdOwogIGNvbnN0IG9wdHMgPSBwbGF5bGlzdHMubWFwKChwKSA9PiBgPG9wdGlvbiB2YWx1ZT0iJHtlc2MocCl9Ij4ke2VzYyhwKX08L29wdGlvbj5gKS5qb2luKCcnKTsKICAkKCdwbCcpLmlubmVySFRNTCA9IG9wdHM7ICQoJ3hwbCcpLmlubmVySFRNTCA9IG9wdHM7CiAgaWYgKHMuc2lnbmVkKSByZXR1cm4gc2hvdygpOwogICQoJ2xvZ2luJykuY2xhc3NMaXN0LnJlbW92ZSgnaGlkZScpOwogIGlmIChzLnNldHVwKSB7ICQoJ2x0JykudGV4dENvbnRlbnQgPSAn2KPZiNmEINmF2LHYqTog2KfYrtiq2KfYsSDZg9mE2YXYqSDYs9ixINmE2YTYpdiv2KfYsdipJzsgJCgnbGgnKS50ZXh0Q29udGVudCA9ICc4INij2K3YsdmBINi52YTZiSDYp9mE2KPZgtmELiDZh9in2Yog2KfZhNmD2YTZhdipINio2KrYr9iu2YTZgyDYudmE2Ykg2KfZhNmF2YjZgti5INmF2YYg2KPZiiDYrNmH2KfYsi4nOyAkKCdwdycpLmF1dG9jb21wbGV0ZSA9ICduZXctcGFzc3dvcmQnOyB9CiAgJCgncHcnKS5mb2N1cygpOwp9CiQoJ2dvJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdsb2dpbicsIHsgcGFzc3dvcmQ6ICQoJ3B3JykudmFsdWUsIHNldHVwOiBuZXcgVVJMU2VhcmNoUGFyYW1zKGxvY2F0aW9uLnNlYXJjaCkuZ2V0KCdzZXR1cCcpIHx8ICcnIH0pOwogIGlmIChyLm9rKSB7ICQoJ3B3JykudmFsdWUgPSAnJzsgc2hvdygpOyB9IGVsc2UgJCgnbG0nKS50ZXh0Q29udGVudCA9IHIuZXJyb3IgfHwgJ9iu2LfYoyc7Cn07CiQoJ3B3Jykub25rZXlkb3duID0gKGUpID0+IHsgaWYgKGUua2V5ID09PSAnRW50ZXInKSAkKCdnbycpLmNsaWNrKCk7IH07CiQoJ291dCcpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7IGF3YWl0IGFwaSgnbG9nb3V0Jywge30pOyBsb2NhdGlvbi5yZWxvYWQoKTsgfTsKCmZ1bmN0aW9uIHNob3coKSB7ICQoJ2xvZ2luJykuY2xhc3NMaXN0LmFkZCgnaGlkZScpOyAkKCdhcHAnKS5jbGFzc0xpc3QucmVtb3ZlKCdoaWRlJyk7IGxvYWQoKTsgfQoKY29uc3QgVklFV1MgPSB7IGRhc2g6IFsn2YTZiNit2Kkg2KfZhNiq2K3Zg9mFJywgJ9mG2LjYsdipINiz2LHZiti52Kkg2LnZhNmJINmD2YQg2KfZhNij2KzZh9iy2KknXSwgZGV2czogWyfYp9mE2KPYrNmH2LLYqScsICfZg9mEINin2YTYstio2KfZitmGIOKAlCDYp9i22LrYtyDYudmE2Ykg2KPZiiDYrNmH2KfYsiDZhNiq2LnYr9mK2YTZhyddLCBwcm9tbzogWydQcm9tbyBjb2RlcycsICfZg9mEINmD2YjYryDYqNmK2LTYqti62YQg2YXYsdipINmI2K3Yr9ipINi52YTZiSDYrNmH2KfYsiDZiNin2K3YryddLCBwYXk6IFsn2KfZhNiv2YHYuScsICfYp9mE2YTZiiDYqNix2Kcg2KfZhNiv2KfYptix2Kkg2KjZitiv2YHYuSDigJQg2YjYp9mE2YTZiiDYrNmI2ZHYp9mH2Kcg2KjZitin2K7YryBQcm9tbyBjb2RlJ10sIGhlbHA6IFsn2LfYsdmK2YLYqSDYp9mE2KfYs9iq2K7Yr9in2YUnLCAn2K7Yt9mI2KfYqiDYs9ix2YrYudipJ10gfTsKZnVuY3Rpb24gdmlldyh2KSB7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLm5hdltkYXRhLXZdJykuZm9yRWFjaCgobikgPT4gbi5jbGFzc0xpc3QudG9nZ2xlKCdvbicsIG4uZGF0YXNldC52ID09PSB2KSk7CiAgT2JqZWN0LmtleXMoVklFV1MpLmZvckVhY2goKGspID0+ICQoJ3YtJyArIGspLmNsYXNzTGlzdC50b2dnbGUoJ2hpZGUnLCBrICE9PSB2KSk7CiAgJCgndnQnKS50ZXh0Q29udGVudCA9IFZJRVdTW3ZdWzBdOyAkKCd2cycpLnRleHRDb250ZW50ID0gVklFV1Nbdl1bMV07CiAgaWYgKHYgPT09ICdwcm9tbycpIGxvYWRQcm9tb3MoKTsKICBpZiAodiA9PT0gJ3BheScpIGxvYWRQYXkoKTsKfQovLyAtLS0tLS0tLS0tIHBheW1lbnQgLS0tLS0tLS0tLQphc3luYyBmdW5jdGlvbiBsb2FkUGF5KCkgewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3BheScpOwogICQoJ3BheS1wcmljZScpLnZhbHVlID0gci5wcmljZSB8fCAnJzsgJCgncGF5LWxpbmsnKS52YWx1ZSA9IHIubGluayB8fCAnJzsgJCgncGF5LW9uJykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCAhIXIub24pOwogICQoJ3BheS1zdCcpLnRleHRDb250ZW50ID0gKHIub24gPyAn2LTYutmR2KfZhCcgOiAn2YXYt9mB2YonKSArIChyLmxpbmsgPyAnIMK3IFZlbm1vIEAnICsgci5saW5rLnJlcGxhY2UoL15ALywgJycpIDogJycpOwp9CiQoJ3BheS1vbicpLm9uY2xpY2sgPSAoKSA9PiAkKCdwYXktb24nKS5jbGFzc0xpc3QudG9nZ2xlKCdvbicpOwokKCdwYXktc2F2ZScpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgncGF5JywgeyBwcmljZTogJCgncGF5LXByaWNlJykudmFsdWUudHJpbSgpLCBsaW5rOiAkKCdwYXktbGluaycpLnZhbHVlLnRyaW0oKSwgb246ICQoJ3BheS1vbicpLmNsYXNzTGlzdC5jb250YWlucygnb24nKSB9KTsKICAkKCdwYXktbXNnJykudGV4dENvbnRlbnQgPSByLm9rID8gJ9in2YbYrdmB2Lgg4pyTJyA6IChyLmVycm9yIHx8ICfYrti32KMnKTsgbG9hZFBheSgpOwp9OwovLyAtLS0tLS0tLS0tIHByb21vIGNvZGVzOiBvbmUgdXNlLCBvbmUgZGV2aWNlIC0tLS0tLS0tLS0KY29uc3QgcGNvZGUgPSAoYykgPT4gYy5yZXBsYWNlKC8oLns0fSkoLns0fSkvLCAnJDEtJDInKTsKYXN5bmMgZnVuY3Rpb24gbG9hZFByb21vcygpIHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdwcm9tb3MnKTsgY29uc3QgbGlzdCA9IHIucHJvbW9zIHx8IFtdOwogIGNvbnN0IGZyZWUgPSBsaXN0LmZpbHRlcigocCkgPT4gIXAudXNlZF9ieSkubGVuZ3RoOwogICQoJ3Byb21vLW4nKS50ZXh0Q29udGVudCA9IGAke2ZyZWV9INis2KfZh9iyIMK3ICR7bGlzdC5sZW5ndGggLSBmcmVlfSDZhdiz2KrYudmF2YRgOwogICQoJ3B0YicpLmlubmVySFRNTCA9IGxpc3QubGVuZ3RoID8gbGlzdC5tYXAoKHApID0+IHsKICAgIGNvbnN0IGQgPSBwLnVzZWRfYnkgPyBkZXZzLmZpbmQoKHgpID0+IHguY29kZSA9PT0gcC51c2VkX2J5KSA6IG51bGw7CiAgICBjb25zdCBzdCA9IHAudXNlZF9ieSA/IGA8c3BhbiBjbGFzcz0ic3Qgcy1vZmYiPtmF2LPYqti52YXZhCDCtyAke2VzYyhkPy5uYW1lIHx8IHByZXR0eShwLnVzZWRfYnkpKX0gwrcg2YLYqNmEICR7YWdvKHAudXNlZF9hdCl9PC9zcGFuPmAgOiAnPHNwYW4gY2xhc3M9InN0IHMtb24iPtis2KfZh9iyPC9zcGFuPic7CiAgICByZXR1cm4gYDx0cj48dGQ+PHNwYW4gY2xhc3M9ImNvZGUiPiR7ZXNjKHBjb2RlKHAuY29kZSkpfTwvc3Bhbj48L3RkPjx0ZD4ke2VzYyhwLm5vdGUgfHwgJycpfTwvdGQ+PHRkPiR7c3R9PC90ZD4KICAgICAgPHRkIHN0eWxlPSJ0ZXh0LWFsaWduOmxlZnQiPiR7cC51c2VkX2J5ID8gJycgOiBgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWNwPSIke2VzYyhwY29kZShwLmNvZGUpKX0iPtmG2LPYrjwvYnV0dG9uPiBgfTxidXR0b24gY2xhc3M9ImJ0biByZWQgc20iIGRhdGEtcGQ9IiR7ZXNjKHAuY29kZSl9Ij7Yrdiw2YE8L2J1dHRvbj48L3RkPjwvdHI+YDsKICB9KS5qb2luKCcnKSA6ICc8dHI+PHRkIGNvbHNwYW49IjQiIGNsYXNzPSJlbXB0eSI+2YXYpyDZgdmKINij2YPZiNin2K8g4oCUINij2LXYr9ixINij2YjZhCDZg9mI2K8g2YXZhiDZgdmI2YI8L3RkPjwvdHI+JzsKICAkKCdwdGInKS5xdWVyeVNlbGVjdG9yQWxsKCdbZGF0YS1jcF0nKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSAoKSA9PiB7IG5hdmlnYXRvci5jbGlwYm9hcmQ/LndyaXRlVGV4dChiLmRhdGFzZXQuY3ApOyB0b2FzdCgn2KfZhtiq2LPYrjogJyArIGIuZGF0YXNldC5jcCk7IH0pOwogICQoJ3B0YicpLnF1ZXJ5U2VsZWN0b3JBbGwoJ1tkYXRhLXBkXScpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9IGFzeW5jICgpID0+IHsgaWYgKCFjb25maXJtKCfYrdiw2YEg2KfZhNmD2YjYr9ifJykpIHJldHVybjsgYXdhaXQgYXBpKCdwcm9tb19kZWxldGUnLCB7IGNvZGU6IGIuZGF0YXNldC5wZCB9KTsgbG9hZFByb21vcygpOyB9KTsKfQokKCdwZ2VuJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdwcm9tbycsIHsgbjogKyQoJ3Bjb3VudCcpLnZhbHVlLCBub3RlOiAkKCdwbm90ZScpLnZhbHVlLnRyaW0oKSB9KTsKICBpZiAoci5vaykgeyAkKCdwbm90ZScpLnZhbHVlID0gJyc7IHRvYXN0KCfYqtmFINil2LXYr9in2LEgJyArIChyLmNvZGVzIHx8IFtdKS5sZW5ndGggKyAnINmD2YjYrycpOyBsb2FkUHJvbW9zKCk7IH0gZWxzZSB0b2FzdChyLmVycm9yIHx8ICfYrti32KMnKTsKfTsKZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLm5hdltkYXRhLXZdJykuZm9yRWFjaCgobikgPT4gbi5vbmNsaWNrID0gKCkgPT4gdmlldyhuLmRhdGFzZXQudikpOwoKYXN5bmMgZnVuY3Rpb24gbG9hZCgpIHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdkZXZpY2VzJyk7CiAgaWYgKHIub2sgPT09IGZhbHNlICYmIHIuZXJyb3IpIHsgbG9jYXRpb24ucmVsb2FkKCk7IHJldHVybjsgfQogIGRldnMgPSByLmRldmljZXMgfHwgW107CiAgcmVuZGVyU3RhdHMoKTsgcmVuZGVyVGFibGUoKTsgcmVuZGVyQXR0bigpOwogIGxvYWRIZWFsdGgoKTsKfQphc3luYyBmdW5jdGlvbiBsb2FkSGVhbHRoKCkgewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ2hlYWx0aCcpOwogIGNvbnN0IGggPSByLmhlYWx0aCB8fCBbXTsKICAkKCdobC1uJykudGV4dENvbnRlbnQgPSBoLmxlbmd0aCA/IGAke2gubGVuZ3RofSDYqtmC2LHZitixYCA6ICcnOwogICQoJ2hsJykuaW5uZXJIVE1MID0gaC5sZW5ndGggPyBoLm1hcCgoeCkgPT4gYDx0cj48dGQ+PHNwYW4gY2xhc3M9InN0ICR7eC5raW5kID09PSAnb2ZmLWFpcicgPyAncy1vbicgOiB4LmtpbmQgPT09ICdmcmVlemUnID8gJ3Mtc29vbicgOiAncy1vZmYnfSI+JHt4LmtpbmQgPT09ICdvZmYtYWlyJyA/ICfZgtmG2KfYqSDYs9mI2K/YpyDYudmG2K8g2KfZhNmF2LLZiNivJyA6IHgua2luZCA9PT0gJ2ZyZWV6ZScgPyAn2LnZhNmR2YLYqiDYp9mE2LTYp9i02KknIDogJ9iq2LPZg9mR2LEg2KjYrti32KMnfTwvc3Bhbj48L3RkPgogICAgPHRkPiR7ZXNjKHgubmFtZSB8fCBwcmV0dHkoeC5jb2RlKSl9PGJyPjxzbWFsbCBjbGFzcz0ibXV0ZWQiPiR7ZXNjKHgudmVyKX0gwrcg2YLYqNmEICR7YWdvKHgudCl9PC9zbWFsbD48L3RkPgogICAgPHRkPjxkZXRhaWxzPjxzdW1tYXJ5IGNsYXNzPSJtdXRlZCI+2KfZhNiq2YHYp9i12YrZhDwvc3VtbWFyeT48cHJlIGRpcj0ibHRyIiBzdHlsZT0id2hpdGUtc3BhY2U6cHJlLXdyYXA7Zm9udC1zaXplOjExcHg7bWF4LWhlaWdodDoyNjBweDtvdmVyZmxvdzphdXRvIj4ke2VzYyh4LmluZm8pfTwvcHJlPjwvZGV0YWlscz48L3RkPjwvdHI+YCkuam9pbignJykKICAgIDogJzx0cj48dGQgY2xhc3M9Im11dGVkIj7inJMg2YjZhNinINi52LfZhCDYudmE2Ykg2KPZiiDYrNmH2KfYsjwvdGQ+PC90cj4nOwp9CiQoJ2hsLWNscicpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7IGlmICghY29uZmlybSgn2YXYs9itINmD2YQg2KfZhNiq2YLYp9ix2YrYsdifJykpIHJldHVybjsgYXdhaXQgYXBpKCdoZWFsdGgvY2xlYXInLCB7fSk7IGxvYWRIZWFsdGgoKTsgfTsKJCgncmVmcmVzaCcpLm9uY2xpY2sgPSAoKSA9PiBsb2FkKCkudGhlbigoKSA9PiB0b2FzdCgn2KrZhSDYp9mE2KrYrdiv2YrYqycpKTsKCmZ1bmN0aW9uIGNvdW50cygpIHsKICBjb25zdCBjID0geyBhbGw6IGRldnMubGVuZ3RoLCBvbjogMCwgd2FpdDogMCwgc29vbjogMCwgZXhwOiAwLCBvZmY6IDAsIG9ubGluZTogMCwgd2F0Y2g6IDAgfTsKICBkZXZzLmZvckVhY2goKGQpID0+IHsgY1tzdGF0ZShkKS5rXSsrOyBpZiAoaXNPbmxpbmUoZCkpIGMub25saW5lKys7IGlmIChpc1dhdGNoaW5nKGQpKSBjLndhdGNoKys7IH0pOwogIHJldHVybiBjOwp9CmZ1bmN0aW9uIHJlbmRlclN0YXRzKCkgewogIGNvbnN0IGMgPSBjb3VudHMoKTsKICBjb25zdCBTID0gW1snYWxsJywgJ9mD2YQg2KfZhNij2KzZh9iy2KknLCBjLmFsbCwgJ3ZhcigtLXQyKSddLCBbJ29ubGluZScsICfZhdiq2LXZhCDYp9mE2KLZhicsIGMub25saW5lLCAndmFyKC0tYSknXSwgWyd3YXRjaCcsICfZiti02KfZh9ivINin2YTYotmGJywgYy53YXRjaCwgJ3ZhcigtLWEpJ10sIFsnb24nLCAn2LTYutmR2KfZhCcsIGMub24gKyBjLnNvb24sICd2YXIoLS1hKSddLAogICAgWyd3YWl0JywgJ9io2KfZhtiq2LjYp9ixINin2YTYqtmB2LnZitmEJywgYy53YWl0LCAndmFyKC0tYiknXSwgWydzb29uJywgJ9mK2YbYqtmH2Yog2K7ZhNin2YQgNyDYo9mK2KfZhScsIGMuc29vbiwgJ3ZhcigtLXkpJ10sIFsnZXhwJywgJ9mF2YbYqtmH2YonLCBjLmV4cCwgJ3ZhcigtLXIpJ10sIFsnb2ZmJywgJ9mF2YjZgtmI2YEnLCBjLm9mZiwgJ3ZhcigtLXQzKSddXTsKICAkKCdzdGF0cycpLmlubmVySFRNTCA9IFMubWFwKChbaywgbCwgbiwgY29sXSkgPT4gYDxkaXYgY2xhc3M9InN0YXQiIGRhdGEtZj0iJHtrfSI+PGRpdiBjbGFzcz0ibCI+PHNwYW4gY2xhc3M9ImRvdCIgc3R5bGU9ImJhY2tncm91bmQ6JHtjb2x9Ij48L3NwYW4+JHtsfTwvZGl2PjxkaXYgY2xhc3M9Im4iPiR7bn08L2Rpdj48L2Rpdj5gKS5qb2luKCcnKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuc3RhdCcpLmZvckVhY2goKHMpID0+IHMub25jbGljayA9ICgpID0+IHsgZmlsdGVyID0gcy5kYXRhc2V0LmY7IHZpZXcoJ2RldnMnKTsgcmVuZGVyVGFibGUoKTsgfSk7CiAgY29uc3QgRiA9IFtbJ2FsbCcsICfYp9mE2YPZhCddLCBbJ29ubGluZScsICfZhdiq2LXZhCDYp9mE2KLZhiddLCBbJ3dhdGNoJywgJ9mK2LTYp9mH2K8g2KfZhNii2YYnXSwgWydvbicsICfYtNi62ZHYp9mEJ10sIFsnd2FpdCcsICfYqNin2YbYqti42KfYsSDYp9mE2KrZgdi52YrZhCddLCBbJ3Nvb24nLCAn2YrZhtiq2YfZiiDZgtix2YrYqNin2YsnXSwgWydleHAnLCAn2YXZhtiq2YfZiiddLCBbJ29mZicsICfZhdmI2YLZiNmBJ11dOwogICQoJ2NoaXBzJykuaW5uZXJIVE1MID0gRi5tYXAoKFtrLCBsXSkgPT4gYDxidXR0b24gY2xhc3M9ImNoaXAke2ZpbHRlciA9PT0gayA/ICcgb24nIDogJyd9IiBkYXRhLWY9IiR7a30iPiR7bH0gPHNwYW4gY2xhc3M9InBpbGwiPiR7ayA9PT0gJ29uJyA/IGMub24gKyBjLnNvb24gOiBjW2tdfTwvc3Bhbj48L2J1dHRvbj5gKS5qb2luKCcnKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuY2hpcCcpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9ICgpID0+IHsgZmlsdGVyID0gYi5kYXRhc2V0LmY7IHJlbmRlclN0YXRzKCk7IHJlbmRlclRhYmxlKCk7IH0pOwp9CmZ1bmN0aW9uIHJvdyhkKSB7CiAgY29uc3QgcyA9IHN0YXRlKGQpOwogIGNvbnN0IHBscyA9IChkLnBsYXlsaXN0ID8gYDxzcGFuIGNsYXNzPSJ0YWciPiR7ZXNjKGQucGxheWxpc3QpfTwvc3Bhbj5gIDogJzxzcGFuIGNsYXNzPSJtdXRlZCI+4oCUPC9zcGFuPicpICsgKGQuZXh0cmFzIHx8IFtdKS5tYXAoKHgpID0+IGA8c3BhbiBjbGFzcz0idGFnIj4rICR7ZXNjKHgpfTwvc3Bhbj5gKS5qb2luKCcnKTsKICByZXR1cm4gYDx0ciBkYXRhLWM9IiR7ZXNjKGQuY29kZSl9Ij48dGQ+PHNwYW4gY2xhc3M9ImNvZGUiPiR7cHJldHR5KGVzYyhkLmNvZGUpKX08L3NwYW4+PC90ZD4KICAgIDx0ZCBjbGFzcz0id2hvIj48Yj4ke2QubmFtZSA/IGVzYyhkLm5hbWUpIDogJzxzcGFuIGNsYXNzPSJtdXRlZCI+2KjYr9mI2YYg2KfYs9mFPC9zcGFuPid9PC9iPjxzbWFsbD4ke2VzYyhkLm1vZGVsIHx8ICcnKX08L3NtYWxsPiR7d2hlcmUoZCl9JHt3YXRjaGluZyhkKX08L3RkPgogICAgPHRkPiR7cGxzfSR7ZC5oYXNfdnBuID8gJzxzcGFuIGNsYXNzPSJ0YWciPvCfm6EgVlBOPC9zcGFuPicgOiAnJ30ke2QucHJvbW8gPyAnPHNwYW4gY2xhc3M9InRhZyI+JyArIChkLnByb21vLnN0YXJ0c1dpdGgoJ1BBSUQnKSA/ICfwn5KzINiv2YHYuScgOiAn8J+OnyAnICsgZXNjKGQucHJvbW8ucmVwbGFjZSgvKC57NH0pKC57NH0pLywgJyQxLSQyJykpKSArICc8L3NwYW4+JyA6ICcnfTwvdGQ+PHRkPjxzcGFuIGNsYXNzPSJzdCBzLSR7cy5rfSI+JHtpc09ubGluZShkKSA/ICc8c3BhbiBjbGFzcz0ib25saW5lIj48L3NwYW4+JyA6ICcnfSR7cy50fTwvc3Bhbj48L3RkPgogICAgPHRkIGNsYXNzPSJoaWRlLW0gbXV0ZWQiPiR7YWdvKGQuc2Vlbil9PC90ZD48dGQgY2xhc3M9ImhpZGUtbSBtdXRlZCI+JHtkYXkoZC5leHBpcmVzKSB8fCAn4oCUJ308L3RkPjwvdHI+YDsKfQpmdW5jdGlvbiBiaW5kUm93cyh0YikgeyB0Yi5xdWVyeVNlbGVjdG9yQWxsKCd0cltkYXRhLWNdJykuZm9yRWFjaCgodHIpID0+IHRyLm9uY2xpY2sgPSAoKSA9PiBvcGVuRHJhd2VyKHRyLmRhdGFzZXQuYykpOyB9CmZ1bmN0aW9uIHJlbmRlclRhYmxlKCkgewogIGNvbnN0IHEgPSAkKCdxJykudmFsdWUudHJpbSgpLnRvTG93ZXJDYXNlKCkucmVwbGFjZSgvXHMvZywgJycpOwogIGNvbnN0IGxpc3QgPSBkZXZzLmZpbHRlcigoZCkgPT4gewogICAgY29uc3QgayA9IHN0YXRlKGQpLms7CiAgICBpZiAoZmlsdGVyID09PSAnd2F0Y2gnID8gIWlzV2F0Y2hpbmcoZCkgOiBmaWx0ZXIgPT09ICdvbmxpbmUnID8gIWlzT25saW5lKGQpIDogZmlsdGVyID09PSAnb24nID8gIShrID09PSAnb24nIHx8IGsgPT09ICdzb29uJykgOiBmaWx0ZXIgIT09ICdhbGwnICYmIGsgIT09IGZpbHRlcikgcmV0dXJuIGZhbHNlOwogICAgaWYgKCFxKSByZXR1cm4gdHJ1ZTsKICAgIHJldHVybiBbZC5jb2RlLCBkLm5hbWUsIGQucGxheWxpc3QsIGQubW9kZWwsIGQubm93X3RpdGxlLCAuLi4oZC5leHRyYXMgfHwgW10pXS5zb21lKCh2KSA9PiBTdHJpbmcodiB8fCAnJykudG9Mb3dlckNhc2UoKS5yZXBsYWNlKC9ccy9nLCAnJykuaW5jbHVkZXMocSkpOwogIH0pOwogICQoJ3RiJykuaW5uZXJIVE1MID0gbGlzdC5sZW5ndGggPyBsaXN0Lm1hcChyb3cpLmpvaW4oJycpIDogYDx0cj48dGQgY29sc3Bhbj0iNiIgY2xhc3M9ImVtcHR5Ij7ZhdinINmB2Yog2KPYrNmH2LLYqSDZh9mI2YY8L3RkPjwvdHI+YDsKICBiaW5kUm93cygkKCd0YicpKTsKfQokKCdxJykub25pbnB1dCA9IHJlbmRlclRhYmxlOwpmdW5jdGlvbiByZW5kZXJBdHRuKCkgewogIGNvbnN0IG9yZGVyID0geyB3YWl0OiAwLCBzb29uOiAxLCBleHA6IDIgfTsKICBjb25zdCBsaXN0ID0gZGV2cy5maWx0ZXIoKGQpID0+IHN0YXRlKGQpLmsgaW4gb3JkZXIpLnNvcnQoKGEsIGIpID0+IG9yZGVyW3N0YXRlKGEpLmtdIC0gb3JkZXJbc3RhdGUoYikua10pOwogICQoJ2F0dG4tbicpLnRleHRDb250ZW50ID0gbGlzdC5sZW5ndGggPyBgJHtsaXN0Lmxlbmd0aH0g2KzZh9in2LJgIDogJyc7CiAgJCgnYXR0bicpLmlubmVySFRNTCA9IGxpc3QubGVuZ3RoID8gbGlzdC5tYXAocm93KS5qb2luKCcnKSA6IGA8dHI+PHRkIGNsYXNzPSJlbXB0eSI+2YPZhCDYtNmKINiq2YXYp9mFIOKckyDigJQg2YXYpyDZgdmKINij2KzZh9iy2Kkg2KjYp9mG2KrYuNin2LEg2KPZiCDZhdmG2KrZh9mK2Kk8L3RkPjwvdHI+YDsKICBiaW5kUm93cygkKCdhdHRuJykpOwp9CgovLyAtLS0tLS0tLS0tIGRyYXdlciAtLS0tLS0tLS0tCmZ1bmN0aW9uIG9wZW5EcmF3ZXIoY29kZSkgewogIGVkaXRpbmcgPSBjb2RlID8gZGV2cy5maW5kKCh4KSA9PiB4LmNvZGUgPT09IGNvZGUpIDogbnVsbDsKICBjb25zdCBkID0gZWRpdGluZyB8fCB7fTsKICAkKCdkdCcpLnRleHRDb250ZW50ID0gZWRpdGluZyA/IChkLm5hbWUgfHwgJ9is2YfYp9iyICcgKyBwcmV0dHkoZC5jb2RlKSkgOiAn2KzZh9in2LIg2KzYr9mK2K8nOwogICQoJ2RzdWInKS5pbm5lckhUTUwgPSBlZGl0aW5nID8gYDxzcGFuIGNsYXNzPSJjb2RlIj4ke3ByZXR0eShlc2MoZC5jb2RlKSl9PC9zcGFuPiDCtyAke2VzYyhkLm1vZGVsIHx8ICcnKX0gwrcg2KLYrtixINi42YfZiNixICR7YWdvKGQuc2Vlbil9JHt3YXRjaGluZyhkKSA/ICc8YnI+JyArIHdhdGNoaW5nKGQpIDogJyd9YCA6ICfYp9mD2KrYqCDYp9mE2YPZiNivINin2YTZhNmKINi42KfZh9ixINi52YTZiSDYtNin2LTYqSDYp9mE2LLYqNmI2YYnOwogICQoJ2NvZGUnKS52YWx1ZSA9IGQuY29kZSA/IHByZXR0eShkLmNvZGUpIDogJyc7ICQoJ2NvZGUnKS5kaXNhYmxlZCA9IGZhbHNlOwogICQoJ25hbWUnKS52YWx1ZSA9IGQubmFtZSB8fCAnJzsgJCgnd25hbWUnKS52YWx1ZSA9IGQud2VsY29tZSB8fCAnJzsgJCgncGwnKS52YWx1ZSA9IGQucGxheWxpc3QgfHwgcGxheWxpc3RzWzBdIHx8ICcnOwogICQoJ3UnKS52YWx1ZSA9ICcnOyAkKCdwJykudmFsdWUgPSAnJzsgJCgnZXgnKS52YWx1ZSA9IGRheShkLmV4cGlyZXMpOwogICQoJ2xoaW50JykudGV4dENvbnRlbnQgPSBkLmhhc19sb2dpbiA/ICfYp9mE2YrZiNiy2LEg2YXYrdmB2YjYuCDZiNmF2LTZgdmR2LEuINin2YPYqtioINmK2YjYstixINmI2KjYp9iz2YjZiNix2K8g2KzYr9in2K8g2KjYsyDYpdiw2Kcg2KjYr9mDINiq2LrZitmR2LHZh9mFLicgOiAn2KfZg9iq2Kgg2KfZhNmK2YjYstixINmI2KfZhNio2KfYs9mI2YjYsdivINiq2KjYuSDYp9mE2YAgcGxheWxpc3QuJzsKICAkKCdhY3QnKS5jbGFzc0xpc3QudG9nZ2xlKCdvbicsIGVkaXRpbmcgPyAhIWQuYWN0aXZlIDogdHJ1ZSk7CiAgJCgnZGVsJykuY2xhc3NMaXN0LnRvZ2dsZSgnaGlkZScsICFlZGl0aW5nKTsgJCgneHNlYycpLmNsYXNzTGlzdC50b2dnbGUoJ2hpZGUnLCAhZWRpdGluZyk7ICQoJ3ZzZWMnKS5jbGFzc0xpc3QudG9nZ2xlKCdoaWRlJywgIWVkaXRpbmcpOwogICQoJ3Zjb25mJykudmFsdWUgPSAnJzsgdmRyYXcoZC5oYXNfdnBuKTsKICByZW5kZXJFeHRyYXMoKTsgJCgnc20nKS50ZXh0Q29udGVudCA9ICcnOwogICQoJ3NjcmltJykuY2xhc3NMaXN0LmFkZCgnb3BlbicpOyAkKCdkcmF3ZXInKS5jbGFzc0xpc3QuYWRkKCdvcGVuJyk7CiAgc2V0VGltZW91dCgoKSA9PiAoZWRpdGluZyA/ICQoJ25hbWUnKSA6ICQoJ2NvZGUnKSkuZm9jdXMoKSwgMjUwKTsKfQpmdW5jdGlvbiBjbG9zZURyYXdlcigpIHsgJCgnc2NyaW0nKS5jbGFzc0xpc3QucmVtb3ZlKCdvcGVuJyk7ICQoJ2RyYXdlcicpLmNsYXNzTGlzdC5yZW1vdmUoJ29wZW4nKTsgZWRpdGluZyA9IG51bGw7IH0KJCgnYWRkJykub25jbGljayA9ICgpID0+IG9wZW5EcmF3ZXIobnVsbCk7CiQoJ2R4Jykub25jbGljayA9ICQoJ2NhbmNlbCcpLm9uY2xpY2sgPSAkKCdzY3JpbScpLm9uY2xpY2sgPSBjbG9zZURyYXdlcjsKZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigna2V5ZG93bicsIChlKSA9PiB7IGlmIChlLmtleSA9PT0gJ0VzY2FwZScpIGNsb3NlRHJhd2VyKCk7IH0pOwokKCdhY3QnKS5vbmNsaWNrID0gKCkgPT4gJCgnYWN0JykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nKTsKZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnW2RhdGEtYWRkXScpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9ICgpID0+IHsKICBjb25zdCBuID0gK2IuZGF0YXNldC5hZGQ7CiAgaWYgKCFuKSB7ICQoJ2V4JykudmFsdWUgPSAnJzsgcmV0dXJuOyB9CiAgY29uc3QgY3VyID0gJCgnZXgnKS52YWx1ZSA/IERhdGUucGFyc2UoJCgnZXgnKS52YWx1ZSkgOiAwOwogICQoJ2V4JykudmFsdWUgPSBkYXkoTWF0aC5tYXgoY3VyLCBEYXRlLm5vdygpKSArIG4gKiBEQVkpOwp9KTsKZnVuY3Rpb24gcmVuZGVyRXh0cmFzKCkgewogIGNvbnN0IHhzID0gZWRpdGluZz8uZXh0cmFzIHx8IFtdOwogICQoJ3hsaXN0JykuaW5uZXJIVE1MID0geHMubGVuZ3RoID8geHMubWFwKCh4KSA9PiBgPGRpdiBjbGFzcz0ieGwiPjxzcGFuIGNsYXNzPSJ0YWciPiR7ZXNjKHgpfTwvc3Bhbj48YnV0dG9uIGNsYXNzPSJidG4gcmVkIHNtIiBkYXRhLXg9IiR7ZXNjKHgpfSI+2LTZitmEPC9idXR0b24+PC9kaXY+YCkuam9pbignJykgOiAnPGRpdiBjbGFzcz0ibXV0ZWQiIHN0eWxlPSJmb250LXNpemU6MTNweCI+2YXYpyDZgdmKIHBsYXlsaXN0cyDYpdi22KfZgdmK2KkuPC9kaXY+JzsKICAkKCd4bGlzdCcpLnF1ZXJ5U2VsZWN0b3JBbGwoJ1tkYXRhLXhdJykuZm9yRWFjaCgoYikgPT4gYi5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogICAgaWYgKCFjb25maXJtKGDYtNmK2YQgJHtiLmRhdGFzZXQueH0g2YXZhiDZh9iw2Kcg2KfZhNis2YfYp9iy2J9gKSkgcmV0dXJuOwogICAgYXdhaXQgYXBpKCdleHRyYScsIHsgY29kZTogZWRpdGluZy5jb2RlLCBwbGF5bGlzdDogYi5kYXRhc2V0LngsIHJlbW92ZTogdHJ1ZSB9KTsKICAgIGF3YWl0IHJlbG9hZEVkaXRpbmcoKTsgdG9hc3QoJ9in2YbYtNin2YTYqicpOwogIH0pOwp9CmFzeW5jIGZ1bmN0aW9uIHJlbG9hZEVkaXRpbmcoKSB7IGNvbnN0IGMgPSBlZGl0aW5nPy5jb2RlOyBhd2FpdCBsb2FkKCk7IGlmIChjKSB7IGVkaXRpbmcgPSBkZXZzLmZpbmQoKHgpID0+IHguY29kZSA9PT0gYyk7IHJlbmRlckV4dHJhcygpOyB9IH0KJCgneGFkZCcpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nKSByZXR1cm47CiAgY29uc3QgciA9IGF3YWl0IGFwaSgnZXh0cmEnLCB7IGNvZGU6IGVkaXRpbmcuY29kZSwgcGxheWxpc3Q6ICQoJ3hwbCcpLnZhbHVlLCB1c2VyOiAkKCd4dScpLnZhbHVlLCBwYXNzOiAkKCd4cCcpLnZhbHVlIH0pOwogIGlmIChyLm9rKSB7ICQoJ3h1JykudmFsdWUgPSAnJzsgJCgneHAnKS52YWx1ZSA9ICcnOyBhd2FpdCByZWxvYWRFZGl0aW5nKCk7IHRvYXN0KCfYp9mG2LbYp9mB2Kog4pyTIOKAlCDYrtmE2Yog2KfZhNiy2KjZiNmGINmK2YPYqNizIFJlbG9hZCcpOyB9CiAgZWxzZSAkKCdzbScpLmlubmVySFRNTCA9IGA8c3BhbiBjbGFzcz0iYmFkIj4ke2VzYyhyLmVycm9yKX08L3NwYW4+YDsKfTsKLy8gUHJvdG9uIG9ubHkgKG93bmVyLCAxMSBOb3YgMjAyNik6IHBhc3RlIHRoZSBkZXZpY2UncyBvd24gUHJvdG9uIFdpcmVHdWFyZCBmaWxlLCBvciB0YWtlIGl0IG9mZgpjb25zdCB2ZHJhdyA9IChvbikgPT4gewogICQoJ3ZzdGF0ZScpLmlubmVySFRNTCA9IG9uID8gJzxzcGFuIGNsYXNzPSJvayI+8J+boSDZh9iw2Kcg2KfZhNis2YfYp9iyINi52YbYr9mHIFZQTiDigJQg2KjZiti42YfYsdmE2Ycg2LLYsSBWUE4gT04vT0ZGPC9zcGFuPicgOiAnPHNwYW4gY2xhc3M9Im11dGVkIj7ZhdinINmB2YogVlBOINmE2YfYsNinINin2YTYrNmH2KfYsiAo2YXYpyDYqNmK2LjZh9ix2YTZhyDYo9mKINiu2YrYp9ixIFZQTik8L3NwYW4+JzsKICAkKCd2ZGVsJykuY2xhc3NMaXN0LnRvZ2dsZSgnaGlkZScsICFvbik7Cn07CiQoJ3ZzYXZlJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBpZiAoIWVkaXRpbmcpIHJldHVybjsKICBjb25zdCByID0gYXdhaXQgYXBpKCd2cG4nLCB7IGNvZGU6IGVkaXRpbmcuY29kZSwgY29uZjogJCgndmNvbmYnKS52YWx1ZSB9KTsKICBpZiAoci5vaykgeyAkKCd2Y29uZicpLnZhbHVlID0gJyc7IGF3YWl0IHJlbG9hZEVkaXRpbmcoKTsgdmRyYXcoZWRpdGluZy5oYXNfdnBuKTsgdG9hc3QoJ1ZQTiDYp9mG2K3Zgdi4IOKAlCDYrtmE2Yog2KfZhNiy2KjZiNmGINmK2YPYqNizIFJlbG9hZCcpOyB9CiAgZWxzZSAkKCdzbScpLmlubmVySFRNTCA9IGA8c3BhbiBjbGFzcz0iYmFkIj4ke2VzYyhyLmVycm9yKX08L3NwYW4+YDsKfTsKJCgndmRlbCcpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nIHx8ICFjb25maXJtKCfYtNmK2YQg2KfZhNmAIFZQTiDZhdmGINmH2LDYpyDYp9mE2KzZh9in2LLYnycpKSByZXR1cm47CiAgYXdhaXQgYXBpKCd2cG4nLCB7IGNvZGU6IGVkaXRpbmcuY29kZSwgY29uZjogJycgfSk7IGF3YWl0IHJlbG9hZEVkaXRpbmcoKTsgdmRyYXcoZWRpdGluZy5oYXNfdnBuKTsgdG9hc3QoJ9in2YbYtNin2YQg4oCUINio2YrYrtiq2YHZiiDYrtmK2KfYsSDYp9mE2YAgVlBOINmF2YYg2KfZhNis2YfYp9iyJyk7Cn07CiQoJ3NhdmUnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGNvbnN0IGNvZGUgPSAkKCdjb2RlJykudmFsdWUucmVwbGFjZSgvXEQvZywgJycpOwogIGlmIChjb2RlLmxlbmd0aCAhPT0gOCkgeyAkKCdzbScpLmlubmVySFRNTCA9ICc8c3BhbiBjbGFzcz0iYmFkIj7Zg9mI2K8g2KfZhNis2YfYp9iyIDgg2KPYsdmC2KfZhTwvc3Bhbj4nOyByZXR1cm47IH0KICAvLyBhIG5ldyBjb2RlIGZvciB0aGlzIGRldmljZSAodGhlIGFwcCB3YXMgcHV0IGJhY2spOiBldmVyeXRoaW5nIG1vdmVzIHRvIGl0IGZpcnN0CiAgaWYgKGVkaXRpbmcgJiYgY29kZSAhPT0gZWRpdGluZy5jb2RlKSB7CiAgICBpZiAoIWNvbmZpcm0oYNmG2YLZhCAke2VkaXRpbmcubmFtZSB8fCAn2KfZhNis2YfYp9iyJ30g2YXZhiDYp9mE2YPZiNivICR7cHJldHR5KGVkaXRpbmcuY29kZSl9INmE2YTZg9mI2K8g2KfZhNis2K/ZitivICR7cHJldHR5KGNvZGUpfdifYCkpIHJldHVybjsKICAgIGNvbnN0IG0gPSBhd2FpdCBhcGkoJ3JlY29kZScsIHsgZnJvbTogZWRpdGluZy5jb2RlLCB0bzogY29kZSB9KTsKICAgIGlmICghbS5vaykgeyAkKCdzbScpLmlubmVySFRNTCA9IGA8c3BhbiBjbGFzcz0iYmFkIj4ke2VzYyhtLmVycm9yKX08L3NwYW4+YDsgcmV0dXJuOyB9CiAgICBhd2FpdCBsb2FkKCk7IGVkaXRpbmcgPSBkZXZzLmZpbmQoKHgpID0+IHguY29kZSA9PT0gY29kZSkgfHwgZWRpdGluZzsKICB9CiAgY29uc3QgZCA9IGRldnMuZmluZCgoeCkgPT4geC5jb2RlID09PSBjb2RlKTsKICBpZiAoIWQ/Lmhhc19sb2dpbiAmJiAoISQoJ3UnKS52YWx1ZSB8fCAhJCgncCcpLnZhbHVlKSkgeyAkKCdzbScpLmlubmVySFRNTCA9ICc8c3BhbiBjbGFzcz0iYmFkIj7Yp9mD2KrYqCDYp9mE2YrZiNiy2LEg2YjYp9mE2KjYp9iz2YjZiNix2K88L3NwYW4+JzsgcmV0dXJuOyB9CiAgY29uc3QgciA9IGF3YWl0IGFwaSgnc2F2ZScsIHsgY29kZSwgbmFtZTogJCgnbmFtZScpLnZhbHVlLnRyaW0oKSwgd2VsY29tZTogJCgnd25hbWUnKS52YWx1ZS50cmltKCksIHBsYXlsaXN0OiAkKCdwbCcpLnZhbHVlLCB1c2VyOiAkKCd1JykudmFsdWUsIHBhc3M6ICQoJ3AnKS52YWx1ZSwgZXhwaXJlczogJCgnZXgnKS52YWx1ZSwgYWN0aXZlOiAkKCdhY3QnKS5jbGFzc0xpc3QuY29udGFpbnMoJ29uJykgfSk7CiAgaWYgKCFyLm9rKSB7ICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKHIuZXJyb3IpfTwvc3Bhbj5gOyByZXR1cm47IH0KICAkKCdwJykudmFsdWUgPSAnJzsgY2xvc2VEcmF3ZXIoKTsgYXdhaXQgbG9hZCgpOyB0b2FzdCgn2KfZhtit2YHYuCDinJMg4oCUINiu2YTZiiDYp9mE2LLYqNmI2YYg2YrZg9io2LMgUmVsb2FkJyk7Cn07CiQoJ2RlbCcpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nIHx8ICFjb25maXJtKGDYrdiw2YEg2KfZhNis2YfYp9iyICR7cHJldHR5KGVkaXRpbmcuY29kZSl9INmG2YfYp9im2YrYp9mL2J9gKSkgcmV0dXJuOwogIGF3YWl0IGFwaSgnZGVsZXRlJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUgfSk7IGNsb3NlRHJhd2VyKCk7IGF3YWl0IGxvYWQoKTsgdG9hc3QoJ9in2YbYrdiw2YEnKTsKfTsKaW5pdCgpOwpzZXRJbnRlcnZhbCgoKSA9PiB7IGlmICghJCgnYXBwJykuY2xhc3NMaXN0LmNvbnRhaW5zKCdoaWRlJykgJiYgISQoJ2RyYXdlcicpLmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpKSBsb2FkKCk7IH0sIDMwMDAwKTsKPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"), (c) => c.charCodeAt(0)));
