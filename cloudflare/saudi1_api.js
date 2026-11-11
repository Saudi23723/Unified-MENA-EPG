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
    // our own VPN's device files (owner, 11 Nov 2026): the admin page gives one to a device and takes it back
    db.prepare("CREATE TABLE IF NOT EXISTS vpnpool (n INTEGER PRIMARY KEY, conf TEXT, used_by TEXT)"),
    db.prepare("CREATE TABLE IF NOT EXISTS place (code TEXT PRIMARY KEY, t INTEGER, country TEXT, city TEXT, vpn INTEGER)"),
    db.prepare("CREATE TABLE IF NOT EXISTS backup (code TEXT PRIMARY KEY, t INTEGER, data TEXT)"),
    // promo codes (owner, 9 Nov 2026): made on the admin page, each opens ONE device ONCE
    // the name on the welcome screen (owner, 11 Nov 2026): typed by the owner for each device
    db.prepare("CREATE TABLE IF NOT EXISTS welcome (code TEXT PRIMARY KEY, name TEXT)"),
    db.prepare("CREATE TABLE IF NOT EXISTS promo (code TEXT PRIMARY KEY, created INTEGER, note TEXT, used_by TEXT, used_at INTEGER)"),
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
  const ip = req.headers.get("CF-Connecting-IP") || "", cf = req.cf || {};
  try {
    await env.DB.prepare("INSERT OR REPLACE INTO place (code, t, country, city, vpn) VALUES (?,?,?,?,?)")
      .bind(code, Date.now(), String(cf.country || ""), String(cf.city || "").slice(0, 60), ip === VPN_IP ? 1 : 0).run();
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
        // (none when the device comes through our VPN: that is Phoenix, not where the device is)
        tz: req.headers.get("CF-Connecting-IP") === VPN_IP ? "" : ((req.cf && req.cf.timezone) || "") });
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
      // our VPN's files: paste the whole Cloud Shell output (===== deviceN ===== blocks) once
      if (p === "/admin/api/vpnpool") {
        if (req.method === "POST") {
          const b = await req.json();
          const parts = String(b.confs || "").split(/=+\s*device(\d+)\s*=+/i);
          let n = 0;
          for (let i = 1; i + 1 < parts.length; i += 2) {
            const conf = parts[i + 1].replace(/\n\S+@cloudshell[^\n]*/g, "").trim();
            if (!/\[Interface\]/i.test(conf) || !/PrivateKey\s*=/i.test(conf)) continue;
            await env.DB.prepare("INSERT INTO vpnpool (n, conf, used_by) VALUES (?,?,NULL) ON CONFLICT(n) DO UPDATE SET conf=excluded.conf")
              .bind(Number(parts[i]), await seal(env, { conf })).run();
            n++;
          }
          if (!n) return json({ error: "ما لقيت ملفات device" }, 400);
        }
        const r = await env.DB.prepare("SELECT n, used_by FROM vpnpool ORDER BY n").all();
        const l = r.results || [];
        return json({ ok: true, total: l.length, free: l.filter((x) => !x.used_by).length });
      }
      // give a device one of our VPN files (or keep the one it has)
      if (p === "/admin/api/vpn_on" && req.method === "POST") {
        const code = String((await req.json()).code || "").replace(/\D/g, "");
        let f = await env.DB.prepare("SELECT n, conf FROM vpnpool WHERE used_by=?").bind(code).first();
        if (!f) f = await env.DB.prepare("SELECT n, conf FROM vpnpool WHERE used_by IS NULL ORDER BY n LIMIT 1").first();
        if (!f) return json({ error: "كل ملفات الـ VPN مستخدمة — شيل الـ VPN من جهاز ثاني أو زيد ملفات" }, 400);
        await env.DB.batch([
          env.DB.prepare("UPDATE vpnpool SET used_by=? WHERE n=?").bind(code, f.n),
          env.DB.prepare("INSERT OR REPLACE INTO vpn (code, conf) VALUES (?,?)").bind(code, f.conf),
        ]);
        return json({ ok: true, n: f.n });
      }
      if (p === "/admin/api/vpn" && req.method === "POST") {
        const b = await req.json();
        const code = String(b.code || "").replace(/\D/g, "");
        const conf = String(b.conf || "").trim();
        await env.DB.prepare("UPDATE vpnpool SET used_by=NULL WHERE used_by=?").bind(code).run();
        if (!conf) { await env.DB.prepare("DELETE FROM vpn WHERE code=?").bind(code).run(); return json({ ok: true }); }
        if (!/\[Interface\]/i.test(conf) || !/\[Peer\]/i.test(conf) || !/PrivateKey\s*=/i.test(conf)) return json({ error: "هذا مش ملف WireGuard (.conf)" }, 400);
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
        await env.DB.prepare("UPDATE vpnpool SET used_by=NULL WHERE used_by=?").bind(String(code)).run();
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
const VPN_IP = "137.131.29.53";
const PAGE = new TextDecoder().decode(Uint8Array.from(atob("PCFkb2N0eXBlIGh0bWw+PGh0bWwgbGFuZz0iYXIiIGRpcj0icnRsIj48aGVhZD48bWV0YSBjaGFyc2V0PSJ1dGYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEiPgo8dGl0bGU+U0FVREkuVFYgwrcg2YTZiNit2Kkg2KfZhNil2K/Yp9ix2Kk8L3RpdGxlPgo8c3R5bGU+Cjpyb290ey0tYmc6IzA5MGMxMjstLXA6IzEyMTcyMjstLXAyOiMxOTIwMmU7LS1wMzojMjIyYjNkOy0tbGluZTojMjMyYzNlOy0tdDojZjJmNGY4Oy0tdDI6IzlhYTNiNTstLXQzOiM2Yjc0ODg7LS1hOiMwMGQ2OGY7LS1hMjojMDBiMzc3Oy0tcjojZmY0ZDVlOy0teTojZmZiMDIwOy0tYjojNGRhM2ZmOy0tc2g6MCAxMHB4IDMwcHggcmdiYSgwLDAsMCwuMzUpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveH1odG1sLGJvZHl7aGVpZ2h0OjEwMCV9CmJvZHl7bWFyZ2luOjA7YmFja2dyb3VuZDpyYWRpYWwtZ3JhZGllbnQoMTIwMHB4IDYwMHB4IGF0IDEwMCUgLTEwJSwjMGYyYTIwIDAsdHJhbnNwYXJlbnQgNjAlKSx2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdCk7Zm9udDoxNXB4LzEuNTUgc3lzdGVtLXVpLC1hcHBsZS1zeXN0ZW0sIlNlZ29lIFVJIixUYWhvbWEsc2Fucy1zZXJpZn0KYXtjb2xvcjppbmhlcml0fS5oaWRle2Rpc3BsYXk6bm9uZSFpbXBvcnRhbnR9Lm11dGVke2NvbG9yOnZhcigtLXQyKX0uY29kZXtmb250LWZhbWlseTp1aS1tb25vc3BhY2UsTWVubG8sbW9ub3NwYWNlO2xldHRlci1zcGFjaW5nOjEuNXB4O2RpcmVjdGlvbjpsdHI7ZGlzcGxheTppbmxpbmUtYmxvY2s7d2hpdGUtc3BhY2U6bm93cmFwfQouc2hlbGx7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyNDBweCAxZnI7bWluLWhlaWdodDoxMDB2aH0KYXNpZGV7YmFja2dyb3VuZDpyZ2JhKDE4LDIzLDM0LC44NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMTBweCk7Ym9yZGVyLWxlZnQ6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6MjJweCAxNHB4O3Bvc2l0aW9uOnN0aWNreTt0b3A6MDtoZWlnaHQ6MTAwdmg7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4fQouYnJhbmR7Zm9udC1zaXplOjI0cHg7Zm9udC13ZWlnaHQ6ODAwO2xldHRlci1zcGFjaW5nOi41cHg7cGFkZGluZzo0cHggMTBweCAxOHB4O2RpcmVjdGlvbjpsdHI7dGV4dC1hbGlnbjpyaWdodH0uYnJhbmQgYntjb2xvcjp2YXIoLS1hKX0KLm5hdntkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4O3BhZGRpbmc6MTFweCAxMnB4O2JvcmRlci1yYWRpdXM6MTJweDtjb2xvcjp2YXIoLS10Mik7Y3Vyc29yOnBvaW50ZXI7Zm9udC13ZWlnaHQ6NjAwO2JvcmRlcjowO2JhY2tncm91bmQ6bm9uZTt3aWR0aDoxMDAlO3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjE1cHh9Ci5uYXY6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCl9Lm5hdi5vbntiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx0cmFuc3BhcmVudCxyZ2JhKDAsMjE0LDE0MywuMTYpKTtjb2xvcjp2YXIoLS10KTtib3gtc2hhZG93Omluc2V0IC0zcHggMCAwIHZhcigtLWEpfQoubmF2IC5pY3t3aWR0aDoyMnB4O3RleHQtYWxpZ246Y2VudGVyfS5zcGFjZXJ7ZmxleDoxfQptYWlue3BhZGRpbmc6MjZweCAzMHB4IDYwcHg7bWF4LXdpZHRoOjEyNDBweDt3aWR0aDoxMDAlfQoudG9we2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjE0cHg7bWFyZ2luLWJvdHRvbToyMnB4O2ZsZXgtd3JhcDp3cmFwfQpoMXttYXJnaW46MDtmb250LXNpemU6MjZweH1oMnttYXJnaW46MCAwIDRweDtmb250LXNpemU6MThweH0uc3Vie2NvbG9yOnZhcigtLXQyKTttYXJnaW46MnB4IDAgMH0KLmJ0bntiYWNrZ3JvdW5kOnZhcigtLWEpO2NvbG9yOiMwMzE0MGM7Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czoxMXB4O3BhZGRpbmc6MTFweCAxOHB4O2ZvbnQtd2VpZ2h0OjgwMDtmb250LXNpemU6MTQuNXB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo4cHg7dHJhbnNpdGlvbjouMTVzfQouYnRuOmhvdmVye2JhY2tncm91bmQ6dmFyKC0tYTIpfS5idG4uZ2hvc3R7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKX0uYnRuLmdob3N0OmhvdmVye2JhY2tncm91bmQ6dmFyKC0tcDMpfQouYnRuLnJlZHtiYWNrZ3JvdW5kOnJnYmEoMjU1LDc3LDk0LC4xNCk7Y29sb3I6dmFyKC0tcik7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDI1NSw3Nyw5NCwuMzUpfS5idG4uc217cGFkZGluZzo3cHggMTJweDtmb250LXNpemU6MTNweDtib3JkZXItcmFkaXVzOjlweH0KLnN0YXRze2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KGF1dG8tZml0LG1pbm1heCgxMzhweCwxZnIpKTtnYXA6MTRweDttYXJnaW4tYm90dG9tOjIycHh9Ci5zdGF0e2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDE4MGRlZyx2YXIoLS1wMiksdmFyKC0tcCkpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNnB4O3BhZGRpbmc6MTZweCAxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpO2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246LjE1c30KLnN0YXQ6aG92ZXJ7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoLTJweCk7Ym9yZGVyLWNvbG9yOiMyZjNhNTJ9Ci5zdGF0IC5ue2ZvbnQtc2l6ZTozMHB4O2ZvbnQtd2VpZ2h0OjgwMDttYXJnaW4tdG9wOjRweH0uc3RhdCAubHtjb2xvcjp2YXIoLS10Mik7Zm9udC1zaXplOjEzcHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6N3B4fQouZG90e3dpZHRoOjlweDtoZWlnaHQ6OXB4O2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrfQouY2FyZHtiYWNrZ3JvdW5kOnZhcigtLXApO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpfQouY2FyZC1oe2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjEycHg7cGFkZGluZzoxNnB4IDE4cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7ZmxleC13cmFwOndyYXB9Ci50b29sc3tkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5zZWFyY2h7YmFja2dyb3VuZDp2YXIoLS1wMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjExcHg7cGFkZGluZzo5cHggMTJweDtjb2xvcjp2YXIoLS10KTttaW4td2lkdGg6MjQwcHg7Zm9udC1zaXplOjE0cHh9Ci5jaGlwe2JhY2tncm91bmQ6dmFyKC0tcDIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Y29sb3I6dmFyKC0tdDIpO2JvcmRlci1yYWRpdXM6OTlweDtwYWRkaW5nOjZweCAxM3B4O2ZvbnQtc2l6ZToxM3B4O2N1cnNvcjpwb2ludGVyO2ZvbnQtd2VpZ2h0OjYwMH0KLmNoaXAub257YmFja2dyb3VuZDpyZ2JhKDAsMjE0LDE0MywuMTQpO2JvcmRlci1jb2xvcjpyZ2JhKDAsMjE0LDE0MywuNSk7Y29sb3I6dmFyKC0tYSl9Ci53cmFwe292ZXJmbG93LXg6YXV0b310YWJsZXt3aWR0aDoxMDAlO2JvcmRlci1jb2xsYXBzZTpjb2xsYXBzZX0KdGgsdGR7dGV4dC1hbGlnbjpyaWdodDtwYWRkaW5nOjEycHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1saW5lKTtmb250LXNpemU6MTRweDt2ZXJ0aWNhbC1hbGlnbjptaWRkbGV9CnRoe2NvbG9yOnZhcigtLXQzKTtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHh9CnRib2R5IHRye3RyYW5zaXRpb246LjEycztjdXJzb3I6cG9pbnRlcn10Ym9keSB0cjpob3ZlcntiYWNrZ3JvdW5kOnJnYmEoMjU1LDI1NSwyNTUsLjAyNSl9Ci53aG8gYntkaXNwbGF5OmJsb2NrfS53aG8gc21hbGx7Y29sb3I6dmFyKC0tdDMpfQoudGFne2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo2cHg7cGFkZGluZzozcHggMTBweDtib3JkZXItcmFkaXVzOjk5cHg7Zm9udC1zaXplOjEycHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7bWFyZ2luOjJweCAwIDJweCA0cHg7Zm9udC13ZWlnaHQ6NjAwfQouc3R7ZGlzcGxheTppbmxpbmUtZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjdweDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEzcHh9Ci5zLW9ue2NvbG9yOnZhcigtLWEpfS5zLXdhaXR7Y29sb3I6dmFyKC0tYil9LnMtZXhwe2NvbG9yOnZhcigtLXIpfS5zLW9mZntjb2xvcjp2YXIoLS10Myl9LnMtc29vbntjb2xvcjp2YXIoLS15KX0KLm9ubGluZXt3aWR0aDo4cHg7aGVpZ2h0OjhweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZhcigtLWEpO2JveC1zaGFkb3c6MCAwIDAgNHB4IHJnYmEoMCwyMTQsMTQzLC4xOCk7ZGlzcGxheTppbmxpbmUtYmxvY2t9Ci5lbXB0eXtwYWRkaW5nOjQwcHg7dGV4dC1hbGlnbjpjZW50ZXI7Y29sb3I6dmFyKC0tdDIpfQovKiBkcmF3ZXIgKi8KLnNjcmlte3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7YmFja2dyb3VuZDpyZ2JhKDAsMCwwLC41NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMnB4KTt6LWluZGV4OjIwO29wYWNpdHk6MDtwb2ludGVyLWV2ZW50czpub25lO3RyYW5zaXRpb246LjJzfQouc2NyaW0ub3BlbntvcGFjaXR5OjE7cG9pbnRlci1ldmVudHM6YXV0b30KLmRyYXdlcntwb3NpdGlvbjpmaXhlZDt0b3A6MDtib3R0b206MDtsZWZ0OjA7d2lkdGg6bWluKDUyMHB4LDEwMCUpO2JhY2tncm91bmQ6dmFyKC0tcCk7Ym9yZGVyLXJpZ2h0OjFweCBzb2xpZCB2YXIoLS1saW5lKTt6LWluZGV4OjIxO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC0xMDAlKTt0cmFuc2l0aW9uOi4yNXMgY3ViaWMtYmV6aWVyKC4yLC44LC4yLDEpO2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW47Ym94LXNoYWRvdzp2YXIoLS1zaCl9Ci5kcmF3ZXIub3Blbnt0cmFuc2Zvcm06bm9uZX0KLmRoe3BhZGRpbmc6MjBweCAyMnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXJ9Ci5kYntwYWRkaW5nOjZweCAyMnB4IDIycHg7b3ZlcmZsb3c6YXV0bztmbGV4OjF9LmRme3BhZGRpbmc6MTZweCAyMnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2Rpc3BsYXk6ZmxleDtnYXA6MTBweDtmbGV4LXdyYXA6d3JhcH0KLnNlY3ttYXJnaW4tdG9wOjIwcHg7cGFkZGluZzoxNnB4O2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNHB4O2JhY2tncm91bmQ6dmFyKC0tcDIpfQouc2VjIGgze21hcmdpbjowIDAgNHB4O2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLWEpO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweH0KbGFiZWx7ZGlzcGxheTpibG9jaztjb2xvcjp2YXIoLS10Mik7Zm9udC1zaXplOjEyLjVweDttYXJnaW46MTJweCAwIDVweDtmb250LXdlaWdodDo2MDB9CmlucHV0LHNlbGVjdHt3aWR0aDoxMDAlO2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXQpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxMHB4O3BhZGRpbmc6MTFweCAxMnB4O2ZvbnQtc2l6ZToxNXB4fQppbnB1dDpmb2N1cyxzZWxlY3Q6Zm9jdXN7b3V0bGluZToycHggc29saWQgdmFyKC0tYSk7Ym9yZGVyLWNvbG9yOnRyYW5zcGFyZW50fQouZ3JpZDJ7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDoxMHB4fS5xdWlja3tkaXNwbGF5OmZsZXg7Z2FwOjZweDttYXJnaW4tdG9wOjhweDtmbGV4LXdyYXA6d3JhcH0KLnhse2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47cGFkZGluZzo5cHggMTJweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTBweDttYXJnaW4tdG9wOjhweDtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLm1zZ3ttaW4taGVpZ2h0OjIycHg7bWFyZ2luLXRvcDoxMHB4O2ZvbnQtd2VpZ2h0OjYwMH0ub2t7Y29sb3I6dmFyKC0tYSl9LmJhZHtjb2xvcjp2YXIoLS1yKX0KLnN3aXRjaHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO21hcmdpbi10b3A6MTJweH0KLnRne3Bvc2l0aW9uOnJlbGF0aXZlO3dpZHRoOjQ2cHg7aGVpZ2h0OjI2cHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7Ym9yZGVyLXJhZGl1czo5OXB4O2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246LjJzO2JvcmRlcjowfQoudGc6OmFmdGVye2NvbnRlbnQ6IiI7cG9zaXRpb246YWJzb2x1dGU7dG9wOjNweDtyaWdodDozcHg7d2lkdGg6MjBweDtoZWlnaHQ6MjBweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOiNmZmY7dHJhbnNpdGlvbjouMnN9Ci50Zy5vbntiYWNrZ3JvdW5kOnZhcigtLWEpfS50Zy5vbjo6YWZ0ZXJ7cmlnaHQ6MjNweH0KLmxvZ2lue21heC13aWR0aDo0MjBweDttYXJnaW46MTJ2aCBhdXRvO3BhZGRpbmc6MjhweH0KLnRvYXN0e3Bvc2l0aW9uOmZpeGVkO2JvdHRvbToyMnB4O2xlZnQ6NTAlO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC01MCUpIHRyYW5zbGF0ZVkoMzBweCk7YmFja2dyb3VuZDp2YXIoLS1wMyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtwYWRkaW5nOjEycHggMThweDtib3JkZXItcmFkaXVzOjEycHg7b3BhY2l0eTowO3RyYW5zaXRpb246LjI1czt6LWluZGV4OjQwO2ZvbnQtd2VpZ2h0OjYwMH0KLnRvYXN0LnNob3d7b3BhY2l0eToxO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC01MCUpfQouaGVscHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdChhdXRvLWZpdCxtaW5tYXgoMjYwcHgsMWZyKSk7Z2FwOjE0cHh9Ci5oZWxwIC5jYXJke3BhZGRpbmc6MThweH0uaGVscCBvbHttYXJnaW46OHB4IDAgMDtwYWRkaW5nLWlubGluZS1zdGFydDoyMHB4O2NvbG9yOnZhcigtLXQyKX0KLnBpbGx7Zm9udC1zaXplOjExcHg7cGFkZGluZzoycHggOHB4O2JvcmRlci1yYWRpdXM6OTlweDtiYWNrZ3JvdW5kOnZhcigtLXAzKTtjb2xvcjp2YXIoLS10Mil9CkBtZWRpYSAobWF4LXdpZHRoOjgyMHB4KXsuc2hlbGx7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmcn1hc2lkZXtwb3NpdGlvbjpzdGF0aWM7aGVpZ2h0OmF1dG87ZmxleC1kaXJlY3Rpb246cm93O292ZXJmbG93LXg6YXV0bztwYWRkaW5nOjEwcHg7Ym9yZGVyOjA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSl9CiAuYnJhbmR7cGFkZGluZzo2cHggMTBweH0ubmF2e3dpZHRoOmF1dG87d2hpdGUtc3BhY2U6bm93cmFwfS5zcGFjZXJ7ZGlzcGxheTpub25lfW1haW57cGFkZGluZzoxOHB4IDE0cHh9LnNlYXJjaHttaW4td2lkdGg6MDtmbGV4OjF9CiAuaGlkZS1te2Rpc3BsYXk6bm9uZX10aCx0ZHtwYWRkaW5nOjEwcHggOHB4fX0KLm5vd29uLC5ub3dvZmZ7ZGlzcGxheTpibG9jazttYXJnaW4tdG9wOjRweDtmb250LXNpemU6MTJweDtsaW5lLWhlaWdodDoxLjU7d2hpdGUtc3BhY2U6bm9ybWFsfS5ub3dvbntjb2xvcjp2YXIoLS1hKX0ubm93b2Zme2NvbG9yOnZhcigtLXQzKX0ud2hlcmV7ZGlzcGxheTpibG9jazttYXJnaW4tdG9wOjJweH0udnBub257Y29sb3I6IzJlOWQ1Yjtmb250LXdlaWdodDo2MDB9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PgoKPGRpdiBpZD0ibG9naW4iIGNsYXNzPSJjYXJkIGxvZ2luIGhpZGUiPgogIDxkaXYgY2xhc3M9ImJyYW5kIiBzdHlsZT0icGFkZGluZzowIDAgMTBweCI+U0FVREk8Yj4uVFY8L2I+PC9kaXY+CiAgPGgyIGlkPSJsdCI+2K/YrtmI2YQg2YTZiNit2Kkg2KfZhNil2K/Yp9ix2Kk8L2gyPjxwIGlkPSJsaCIgY2xhc3M9Im11dGVkIj48L3A+CiAgPGxhYmVsPtmD2YTZhdipINin2YTYs9ixPC9sYWJlbD48aW5wdXQgaWQ9InB3IiB0eXBlPSJwYXNzd29yZCIgYXV0b2NvbXBsZXRlPSJjdXJyZW50LXBhc3N3b3JkIj4KICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxidXR0b24gaWQ9ImdvIiBjbGFzcz0iYnRuIiBzdHlsZT0id2lkdGg6MTAwJTtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyIj7Yr9iu2YjZhDwvYnV0dG9uPjwvZGl2PjxkaXYgaWQ9ImxtIiBjbGFzcz0ibXNnIGJhZCI+PC9kaXY+CjwvZGl2PgoKPGRpdiBpZD0iYXBwIiBjbGFzcz0ic2hlbGwgaGlkZSI+CiAgPGFzaWRlPgogICAgPGRpdiBjbGFzcz0iYnJhbmQiPlNBVURJPGI+LlRWPC9iPjwvZGl2PgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IG9uIiBkYXRhLXY9ImRhc2giPjxzcGFuIGNsYXNzPSJpYyI+4penPC9zcGFuPiDZhNmI2K3YqSDYp9mE2KrYrdmD2YU8L2J1dHRvbj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgZGF0YS12PSJkZXZzIj48c3BhbiBjbGFzcz0iaWMiPuKWpDwvc3Bhbj4g2KfZhNij2KzZh9iy2Kk8L2J1dHRvbj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgZGF0YS12PSJwcm9tbyI+PHNwYW4gY2xhc3M9ImljIj7wn46fPC9zcGFuPiBQcm9tbyBjb2RlczwvYnV0dG9uPgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IiBkYXRhLXY9InBheSI+PHNwYW4gY2xhc3M9ImljIj7wn5KzPC9zcGFuPiDYp9mE2K/Zgdi5PC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJuYXYiIGRhdGEtdj0iaGVscCI+PHNwYW4gY2xhc3M9ImljIj4/PC9zcGFuPiDYt9ix2YrZgtipINin2YTYp9iz2KrYrtiv2KfZhTwvYnV0dG9uPgogICAgPGRpdiBjbGFzcz0ic3BhY2VyIj48L2Rpdj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgaWQ9Im91dCI+PHNwYW4gY2xhc3M9ImljIj7ijos8L3NwYW4+INiu2LHZiNisPC9idXR0b24+CiAgPC9hc2lkZT4KICA8bWFpbj4KICAgIDxkaXYgY2xhc3M9InRvcCI+CiAgICAgIDxkaXY+PGgxIGlkPSJ2dCI+2YTZiNit2Kkg2KfZhNiq2K3Zg9mFPC9oMT48cCBjbGFzcz0ic3ViIiBpZD0idnMiPtmG2LjYsdipINiz2LHZiti52Kkg2LnZhNmJINmD2YQg2KfZhNij2KzZh9iy2Kk8L3A+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InRvb2xzIj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGlkPSJyZWZyZXNoIj7in7Mg2KrYrdiv2YrYqzwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biIgaWQ9ImFkZCI+77yLINis2YfYp9iyINis2K/ZitivPC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KCiAgICA8c2VjdGlvbiBpZD0idi1kYXNoIj4KICAgICAgPGRpdiBjbGFzcz0ic3RhdHMiIGlkPSJzdGF0cyI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtaCI+PGgyPtmK2K3Yqtin2Kwg2KfZhtiq2KjYp9mH2YM8L2gyPjxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9ImF0dG4tbiI+PC9zcGFuPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9IndyYXAiPjx0YWJsZT48dGJvZHkgaWQ9ImF0dG4iPjwvdGJvZHk+PC90YWJsZT48L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CgogICAgPHNlY3Rpb24gaWQ9InYtZGV2cyIgY2xhc3M9ImhpZGUiPgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPgogICAgICAgICAgPGRpdiBjbGFzcz0idG9vbHMiIGlkPSJjaGlwcyI+PC9kaXY+CiAgICAgICAgICA8aW5wdXQgY2xhc3M9InNlYXJjaCIgaWQ9InEiIHBsYWNlaG9sZGVyPSLYqNit2Ks6INmD2YjYr9iMINin2LPZhdiMIHBsYXlsaXN04oCmIj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJ3cmFwIj48dGFibGU+CiAgICAgICAgICA8dGhlYWQ+PHRyPjx0aD7Yp9mE2YPZiNivPC90aD48dGg+2KfZhNiy2KjZiNmGPC90aD48dGg+UGxheWxpc3RzPC90aD48dGg+2KfZhNit2KfZhNipPC90aD48dGggY2xhc3M9ImhpZGUtbSI+2KLYrtixINi42YfZiNixPC90aD48dGggY2xhc3M9ImhpZGUtbSI+2YrZhtiq2YfZijwvdGg+PC90cj48L3RoZWFkPgogICAgICAgICAgPHRib2R5IGlkPSJ0YiI+PC90Ym9keT48L3RhYmxlPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBpZD0idi1wcm9tbyIgY2xhc3M9ImhpZGUiPgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPjxoMj7Zg9mI2K8g2KzYr9mK2K88L2gyPjxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9InByb21vLW4iPjwvc3Bhbj48L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJwYWRkaW5nOjE0cHggMThweDtkaXNwbGF5OmZsZXg7Z2FwOjEwcHg7ZmxleC13cmFwOndyYXA7YWxpZ24taXRlbXM6ZW5kIj4KICAgICAgICAgIDxkaXY+PGxhYmVsPtmE2YXZitmG2J8gKNmF2YTYp9it2LjYqSDYpdmE2YMpPC9sYWJlbD48aW5wdXQgaWQ9InBub3RlIiBwbGFjZWhvbGRlcj0i2YXYq9mE2KfZizog2KPYqNmIINij2K3ZhdivIj48L2Rpdj4KICAgICAgICAgIDxkaXY+PGxhYmVsPtin2YTYudiv2K88L2xhYmVsPjxzZWxlY3QgaWQ9InBjb3VudCI+PG9wdGlvbj4xPC9vcHRpb24+PG9wdGlvbj4zPC9vcHRpb24+PG9wdGlvbj41PC9vcHRpb24+PG9wdGlvbj4xMDwvb3B0aW9uPjwvc2VsZWN0PjwvZGl2PgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0icGdlbiI+77yLINij2LXYr9ixPC9idXR0b24+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0id3JhcCI+PHRhYmxlPgogICAgICAgICAgPHRoZWFkPjx0cj48dGg+2KfZhNmD2YjYrzwvdGg+PHRoPtmE2YXZitmGPC90aD48dGg+2KfZhNit2KfZhNipPC90aD48dGg+PC90aD48L3RyPjwvdGhlYWQ+CiAgICAgICAgICA8dGJvZHkgaWQ9InB0YiI+PC90Ym9keT48L3RhYmxlPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBpZD0idi1wYXkiIGNsYXNzPSJoaWRlIj4KICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1oIj48aDI+2KfZhNiv2YHYuSDYr9in2K7ZhCDYp9mE2KrYt9io2YrZgjwvaDI+PHNwYW4gY2xhc3M9Im11dGVkIiBpZD0icGF5LXN0Ij48L3NwYW4+PC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0icGFkZGluZzoxNHB4IDE4cHg7bWF4LXdpZHRoOjY0MHB4Ij4KICAgICAgICAgIDxwIGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxMy41cHg7bGluZS1oZWlnaHQ6MS44Ij7Yp9mE2YTZiiDZhdinINi52YbYr9mHIFByb21vIGNvZGUg2KjZiti02YjZgSDYudmE2Ykg2LTYp9i02Kkg2KfZhNiq2YHYudmK2YQg2LLYsSDCq0J1eSBhY2Nlc3PCuyDZhdi5IFFSLiDYqNmK2YHYqtitINmF2YYg2KrZhNmB2YjZhtmHINi12YHYrdipINmB2YrZh9inINmD2YjYryDYrNmH2KfYstmHINmI2KfZhNiz2LnYsSDZiNiy2LEgPGI+UGF5IHdpdGggVmVubW88L2I+2Iwg2YjYp9mE2YXYqNmE2Log2YjYp9mE2YXZhNin2K3YuNipICjZg9mI2K8g2KfZhNis2YfYp9iyKSDZhdi52KjZkdmK2YrZhiDZhNit2KfZhNmH2YUuINmE2YXYpyDYqtmI2LXZhNmDINin2YTYr9mB2LnYqSDYudmE2YkgVmVubW/YjCDYp9mE2YXZhNin2K3YuNipINmB2YrZh9inINmD2YjYryDYp9mE2KzZh9in2LI6INmB2LnZkdmE2Ycg2YXZhiDCq9in2YTYo9is2YfYstipwrsg2LLZiiDYp9mE2LnYp9iv2KkuPC9wPgogICAgICAgICAgPGxhYmVsPtin2YTYs9i52LEg2KfZhNmE2Yog2KjZiti42YfYsSDZhNmE2LLYqNmI2YYgKNix2YLZhSDYqNin2YTYr9mI2YTYp9ixKTwvbGFiZWw+PGlucHV0IGlkPSJwYXktcHJpY2UiIHBsYWNlaG9sZGVyPSIyNTAiIHN0eWxlPSJkaXJlY3Rpb246bHRyO3RleHQtYWxpZ246bGVmdCI+CiAgICAgICAgICA8bGFiZWw+2KfYs9mFINin2YTZhdiz2KrYrtiv2YUg2LnZhNmJIFZlbm1vICjYqNiv2YjZhiBAKTwvbGFiZWw+PGlucHV0IGlkPSJwYXktbGluayIgcGxhY2Vob2xkZXI9IlNhaWYtU2F1ZGkiIHN0eWxlPSJkaXJlY3Rpb246bHRyO3RleHQtYWxpZ246bGVmdCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzd2l0Y2giPjxzcGFuPtin2YTYr9mB2Lkg2LTYutmR2KfZhDwvc3Bhbj48YnV0dG9uIGNsYXNzPSJ0ZyIgaWQ9InBheS1vbiIgdHlwZT0iYnV0dG9uIj48L2J1dHRvbj48L2Rpdj4KICAgICAgICAgIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+PGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0icGF5LXNhdmUiPtit2YHYuDwvYnV0dG9uPiA8c3BhbiBjbGFzcz0ibXV0ZWQiIGlkPSJwYXktbXNnIj48L3NwYW4+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgoKICAgIDxzZWN0aW9uIGlkPSJ2LWhlbHAiIGNsYXNzPSJoaWRlIj4KICAgICAgPGRpdiBjbGFzcz0iaGVscCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+PGgyPtiy2KjZiNmGINis2K/ZitivPC9oMj48b2w+PGxpPtin2YTYstio2YjZhiDZitmG2LLZkdmEIFNBVURJLlRWINmF2YYgRG93bmxvYWRlciDZiNmK2YHYqtit2YcuPC9saT48bGk+2KjZiti32YTYuSDYudmE2Ykg2LTYp9i02KrZhyDZg9mI2K8g2YXZhiA4INij2LHZgtin2YUuPC9saT48bGk+2YfZiNmGOiDvvIsg2KzZh9in2LIg2KzYr9mK2K8g4oaQINin2YPYqtioINin2YTZg9mI2K8g2YjYp9mE2KfYs9mFINmI2KfZhNmAIHBsYXlsaXN0INmI2KfZhNmK2YjYstixLjwvbGk+PGxpPtin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQg4oCUINiu2YTYtS48L2xpPjwvb2w+PC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+PGgyPtij2YPYq9ixINmF2YYgcGxheWxpc3Q8L2gyPjxvbD48bGk+2KfZgdiq2K0g2KfZhNis2YfYp9iyIOKGkCDZgtiz2YUgwqtQbGF5bGlzdHMg2KXYttin2YHZitipwrsuPC9saT48bGk+2KfYrtiq2KfYsSDYp9mE2YAgcGxheWxpc3Qg2YjYp9mD2KrYqCDYp9mE2YrZiNiy2LEg2YjYp9mE2KjYp9iz2YjZiNix2K8g4oaQINij2LbZgS48L2xpPjxsaT7Yp9mE2LLYqNmI2YYg2KjZitiu2KrYp9ixINio2YrZhtmH2YUg2YXZhiDCq1BsYXlsaXN0c8K7INio2KfZhNiq2LfYqNmK2YIuPC9saT48L29sPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxoMj7Yqtis2K/ZitivINmI2KXZitmC2KfZgTwvaDI+PG9sPjxsaT7Yp9mB2KrYrSDYp9mE2KzZh9in2LIg4oaQINij2LLYsdin2LEgKzMwIC8gKzkwIC8gKzM2NSDZitmI2YUuPC9saT48bGk+wqvYp9mE2KzZh9in2LIg2LTYutmR2KfZhMK7INiq2LfZgdmK2Ycg2KjZitmI2YLZgSDYp9mE2K7Yr9mF2Kkg2YHZiNix2KfZiyDYudmG2K8g2KfZhNiy2KjZiNmGLjwvbGk+PGxpPtin2YTYo9is2YfYstipINin2YTZhNmKINio2KrZhtiq2YfZiiDYrtmE2KfZhCA3INij2YrYp9mFINio2KrYt9mE2Lkg2KjYp9mE2KPYtdmB2LEuPC9saT48L29sPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxoMj7Yp9mE2KPZhdin2YY8L2gyPjxvbD48bGk+2KfZhNmK2YjYstixINmI2KfZhNio2KfYs9mI2YjYsdivINmF2K3ZgdmI2LjZitmGINmF2LTZgdmR2LHZitmGLjwvbGk+PGxpPtin2YTYqNin2LPZiNmI2LHYryDZhdinINio2YrYsdis2Lkg2YrYuNmH2LEg2YfZiNmGINij2KjYr9in2Ysg4oCUINin2KrYsdmD2Ycg2YHYp9i22Yog2YTZitio2YLZiSDYp9mE2YLYr9mK2YUuPC9saT48bGk+2LHYp9io2Lcg2KfZhNiq2LfYqNmK2YI6IDxzcGFuIGNsYXNzPSJjb2RlIj5zYXVkaTEuMXNhaWZzYXVkaS53b3JrZXJzLmRldi9hcGs8L3NwYW4+PC9saT48L29sPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KICA8L21haW4+CjwvZGl2PgoKPGRpdiBjbGFzcz0ic2NyaW0iIGlkPSJzY3JpbSI+PC9kaXY+CjxkaXYgY2xhc3M9ImRyYXdlciIgaWQ9ImRyYXdlciI+CiAgPGRpdiBjbGFzcz0iZGgiPjxkaXY+PGgyIGlkPSJkdCI+2KzZh9in2LIg2KzYr9mK2K88L2gyPjxkaXYgY2xhc3M9Im11dGVkIiBpZD0iZHN1YiI+PC9kaXY+PC9kaXY+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBpZD0iZHgiPuKclTwvYnV0dG9uPjwvZGl2PgogIDxkaXYgY2xhc3M9ImRiIj4KICAgIDxkaXYgY2xhc3M9InNlYyI+CiAgICAgIDxoMz7ikaAg2KfZhNis2YfYp9iyINmI2KfZhNiy2KjZiNmGPC9oMz4KICAgICAgPGxhYmVsPtmD2YjYryDYp9mE2KzZh9in2LIgKDgg2KPYsdmC2KfZhSDZhdmGINi02KfYtNipINin2YTYstio2YjZhik8L2xhYmVsPjxpbnB1dCBpZD0iY29kZSIgaW5wdXRtb2RlPSJudW1lcmljIiBtYXhsZW5ndGg9IjkiIHBsYWNlaG9sZGVyPSIxMjM0IDU2NzgiIGNsYXNzPSJjb2RlIiBzdHlsZT0idGV4dC1hbGlnbjpyaWdodCI+CiAgICAgIDxsYWJlbD7Yp9iz2YUg2KfZhNiy2KjZiNmGPC9sYWJlbD48aW5wdXQgaWQ9Im5hbWUiIHBsYWNlaG9sZGVyPSLZhdir2YTYp9mLOiDYo9io2Ygg2KPYrdmF2K8iPiAgICAgICA8bGFiZWw+2KfZhNin2LPZhSDYudmE2Ykg2LTYp9i02Kkg2KfZhNiq2LHYrdmK2KggKFdlbGNvbWUg4oCmKTwvbGFiZWw+PGlucHV0IGlkPSJ3bmFtZSIgcGxhY2Vob2xkZXI9ItmF2KvZhNin2Ys6IExhaXRoIiBtYXhsZW5ndGg9IjMwIj4KICAgICAgPGRpdiBjbGFzcz0ic3dpdGNoIj48c3Bhbj7Yp9mE2KzZh9in2LIg2LTYutmR2KfZhDwvc3Bhbj48YnV0dG9uIGNsYXNzPSJ0ZyBvbiIgaWQ9ImFjdCIgdHlwZT0iYnV0dG9uIj48L2J1dHRvbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2VjIj4KICAgICAgPGgzPuKRoSDYp9mE2YAgUGxheWxpc3Qg2KfZhNij2LPYp9iz2YrYqTwvaDM+CiAgICAgIDxsYWJlbD5QbGF5bGlzdDwvbGFiZWw+PHNlbGVjdCBpZD0icGwiPjwvc2VsZWN0PgogICAgICA8ZGl2IGNsYXNzPSJncmlkMiI+CiAgICAgICAgPGRpdj48bGFiZWw+2KfZhNmK2YjYstixPC9sYWJlbD48aW5wdXQgaWQ9InUiIGF1dG9jb21wbGV0ZT0ib2ZmIj48L2Rpdj4KICAgICAgICA8ZGl2PjxsYWJlbD7Yp9mE2KjYp9iz2YjZiNix2K88L2xhYmVsPjxpbnB1dCBpZD0icCIgdHlwZT0icGFzc3dvcmQiIGF1dG9jb21wbGV0ZT0ibmV3LXBhc3N3b3JkIj48L2Rpdj4KICAgICAgPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9Im11dGVkIiBpZD0ibGhpbnQiIHN0eWxlPSJmb250LXNpemU6MTIuNXB4O21hcmdpbi10b3A6NnB4Ij48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2VjIj4KICAgICAgPGgzPuKRoiDYp9mE2KfYtNiq2LHYp9mDPC9oMz4KICAgICAgPGxhYmVsPtmK2YbYqtmH2Yog2KjYqtin2LHZitiuICjZgdin2LbZiiA9INio2K/ZiNmGINin2YbYqtmH2KfYoSk8L2xhYmVsPjxpbnB1dCBpZD0iZXgiIHR5cGU9ImRhdGUiPgogICAgICA8ZGl2IGNsYXNzPSJxdWljayI+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWFkZD0iMzAiPiszMCDZitmI2YU8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSI5MCI+KzkwINmK2YjZhTwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjE4MCI+KzYg2LTZh9mI2LE8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSIzNjUiPivYs9mG2Kk8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSIwIj7YqNiv2YjZhiDYp9mG2KrZh9in2KE8L2J1dHRvbj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2VjIiBpZD0ieHNlYyI+CiAgICAgIDxoMz7ikaMgUGxheWxpc3RzINil2LbYp9mB2YrYqTwvaDM+CiAgICAgIDxkaXYgaWQ9InhsaXN0Ij48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iZ3JpZDIiIHN0eWxlPSJtYXJnaW4tdG9wOjZweCI+PGRpdj48bGFiZWw+UGxheWxpc3Q8L2xhYmVsPjxzZWxlY3QgaWQ9InhwbCI+PC9zZWxlY3Q+PC9kaXY+PGRpdj48L2Rpdj4KICAgICAgICA8ZGl2PjxsYWJlbD7Yp9mE2YrZiNiy2LE8L2xhYmVsPjxpbnB1dCBpZD0ieHUiIGF1dG9jb21wbGV0ZT0ib2ZmIj48L2Rpdj48ZGl2PjxsYWJlbD7Yp9mE2KjYp9iz2YjZiNix2K88L2xhYmVsPjxpbnB1dCBpZD0ieHAiIHR5cGU9InBhc3N3b3JkIiBhdXRvY29tcGxldGU9Im5ldy1wYXNzd29yZCI+PC9kaXY+PC9kaXY+CiAgICAgIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6MTBweCI+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBpZD0ieGFkZCI+77yLINij2LbZgSBwbGF5bGlzdDwvYnV0dG9uPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzZWMiIGlkPSJ2c2VjIj4KICAgICAgPGgzPuKRpCBWUE48L2gzPgogICAgICA8ZGl2IGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxMi41cHgiPlZQTiDYs9mK2LHZgdix2YbYpyDYp9mE2K7Yp9i1ICjYo9mF2LHZitmD2Kcgwrcg2YXYrNin2YbZiikuIDxzcGFuIGlkPSJ2cG9vbCI+PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjEwcHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTJweCI+CiAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIHNtIiBpZD0idnRvZ2dsZSIgc3R5bGU9Im1pbi13aWR0aDoxMjBweDtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyIj7igKY8L2J1dHRvbj4KICAgICAgICA8c3BhbiBpZD0idnN0YXRlIiBjbGFzcz0ibXV0ZWQiIHN0eWxlPSJmb250LXNpemU6MTNweCI+PC9zcGFuPgogICAgICA8L2Rpdj4KICAgICAgPHRleHRhcmVhIGlkPSJ2Y29uZiIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+PC90ZXh0YXJlYT48YnV0dG9uIGlkPSJ2c2F2ZSIgc3R5bGU9ImRpc3BsYXk6bm9uZSI+PC9idXR0b24+PGJ1dHRvbiBpZD0idm9uIiBzdHlsZT0iZGlzcGxheTpub25lIj48L2J1dHRvbj48YnV0dG9uIGlkPSJ2ZGVsIiBzdHlsZT0iZGlzcGxheTpub25lIj48L2J1dHRvbj4KICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJtc2ciIGlkPSJzbSI+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iZGYiPjxidXR0b24gY2xhc3M9ImJ0biIgaWQ9InNhdmUiPtit2YHYuDwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgaWQ9ImNhbmNlbCI+2KXZhNi62KfYoTwvYnV0dG9uPjxzcGFuIGNsYXNzPSJzcGFjZXIiIHN0eWxlPSJmbGV4OjEiPjwvc3Bhbj48YnV0dG9uIGNsYXNzPSJidG4gcmVkIGhpZGUiIGlkPSJkZWwiPtit2LDZgSDYp9mE2KzZh9in2LI8L2J1dHRvbj48L2Rpdj4KPC9kaXY+CjxkaXYgY2xhc3M9InRvYXN0IiBpZD0idG9hc3QiPjwvZGl2PgoKPHNjcmlwdD4KY29uc3QgJCA9IChpZCkgPT4gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpOwpjb25zdCBhcGkgPSAocCwgYikgPT4gZmV0Y2goJy9hZG1pbi9hcGkvJyArIHAsIGIgPyB7IG1ldGhvZDogJ1BPU1QnLCBoZWFkZXJzOiB7ICdDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbicgfSwgYm9keTogSlNPTi5zdHJpbmdpZnkoYiksIGNyZWRlbnRpYWxzOiAnc2FtZS1vcmlnaW4nIH0gOiB7IGNyZWRlbnRpYWxzOiAnc2FtZS1vcmlnaW4nIH0pCiAgLnRoZW4oYXN5bmMgKHIpID0+ICh7IG9rOiByLm9rLCAuLi4oYXdhaXQgci5qc29uKCkuY2F0Y2goKCkgPT4gKHt9KSkpIH0pKTsKY29uc3QgZXNjID0gKHMpID0+IFN0cmluZyhzID8/ICcnKS5yZXBsYWNlKC9bJjw+IiddL2csIChjKSA9PiAoeyAnJic6ICcmYW1wOycsICc8JzogJyZsdDsnLCAnPic6ICcmZ3Q7JywgJyInOiAnJnF1b3Q7JywgIiciOiAnJiMzOTsnIH1bY10pKTsKY29uc3QgREFZID0gODY0MDAwMDA7CmNvbnN0IGFnbyA9ICh0KSA9PiB7IGlmICghdCkgcmV0dXJuICfigJQnOyBjb25zdCBtID0gTWF0aC5yb3VuZCgoRGF0ZS5ub3coKSAtIHQpIC8gNjAwMDApOyByZXR1cm4gbSA8IDEgPyAn2KfZhNii2YYnIDogbSA8IDYwID8gYCR7bX0g2K/ZgtmK2YLYqWAgOiBtIDwgMTQ0MCA/IGAke01hdGgucm91bmQobSAvIDYwKX0g2LPYp9i52KlgIDogYCR7TWF0aC5yb3VuZChtIC8gMTQ0MCl9INmK2YjZhWA7IH07CmNvbnN0IGRheSA9ICh0KSA9PiB0ID8gbmV3IERhdGUodCkudG9JU09TdHJpbmcoKS5zbGljZSgwLCAxMCkgOiAnJzsKY29uc3QgcHJldHR5ID0gKGMpID0+IGMucmVwbGFjZSgvKFxkezR9KShcZHs0fSkvLCAnJDEgJDInKTsKbGV0IGRldnMgPSBbXSwgcGxheWxpc3RzID0gW10sIGZpbHRlciA9ICdhbGwnLCBlZGl0aW5nID0gbnVsbDsKCmZ1bmN0aW9uIHRvYXN0KHQpIHsgY29uc3QgZSA9ICQoJ3RvYXN0Jyk7IGUudGV4dENvbnRlbnQgPSB0OyBlLmNsYXNzTGlzdC5hZGQoJ3Nob3cnKTsgY2xlYXJUaW1lb3V0KGUuX3QpOyBlLl90ID0gc2V0VGltZW91dCgoKSA9PiBlLmNsYXNzTGlzdC5yZW1vdmUoJ3Nob3cnKSwgMjYwMCk7IH0KCmZ1bmN0aW9uIHN0YXRlKGQpIHsKICBjb25zdCBub3cgPSBEYXRlLm5vdygpOwogIGlmICghZC5hY3RpdmUpIHJldHVybiB7IGs6ICdvZmYnLCB0OiAn2YXZiNmC2YjZgScgfTsKICBpZiAoZC5leHBpcmVzICYmIGQuZXhwaXJlcyA8IG5vdykgcmV0dXJuIHsgazogJ2V4cCcsIHQ6ICfZhdmG2KrZh9mKJyB9OwogIGlmICghZC5oYXNfbG9naW4gfHwgIWQucGxheWxpc3QpIHJldHVybiB7IGs6ICd3YWl0JywgdDogJ9io2KfZhtiq2LjYp9ixINin2YTYqtmB2LnZitmEJyB9OwogIGlmIChkLmV4cGlyZXMgJiYgZC5leHBpcmVzIC0gbm93IDwgNyAqIERBWSkgcmV0dXJuIHsgazogJ3Nvb24nLCB0OiBg2YrZhtiq2YfZiiDYrtmE2KfZhCAke01hdGgubWF4KDEsIE1hdGguY2VpbCgoZC5leHBpcmVzIC0gbm93KSAvIERBWSkpfSDZitmI2YVgIH07CiAgcmV0dXJuIHsgazogJ29uJywgdDogJ9i02LrZkdin2YQnIH07Cn0KY29uc3QgaXNPbmxpbmUgPSAoZCkgPT4gZC5zZWVuICYmIERhdGUubm93KCkgLSBkLnNlZW4gPCAyMCAqIDYwMDAwOwovLyB3aGF0IHRoZSBkZXZpY2UgaXMgd2F0Y2hpbmcgbm93ICh0b2xkIGJ5IHRoZSBhcHAgZXZlcnkgMTAwIHMpIG9yIHdhdGNoZWQgbGFzdApjb25zdCBLSU5EID0geyBsaXZlOiAn8J+TuicsIG1vdmllOiAn8J+OrCcsIHNlcmllczogJ/Cfjp4nLCByZWNvcmRpbmc6ICfij7onLCB2aWRlbzogJ+KWticgfTsKY29uc3QgaXNXYXRjaGluZyA9IChkKSA9PiBkLm5vd190ICYmIERhdGUubm93KCkgLSBkLm5vd190IDwgNCAqIDYwMDAwOwovLyB3aGVyZSB0aGUgZGV2aWNlIGlzIG5vdywgZnJvbSBpdHMgaW50ZXJuZXQ6IGZsYWcgKyBjb3VudHJ5ICsgY2l0eSwgYW5kIPCflJIgd2hlbiBpdCBjb21lcyB0aHJvdWdoIG91ciBWUE4KY29uc3QgZmxhZyA9IChjKSA9PiBjICYmIGMubGVuZ3RoID09PSAyID8gU3RyaW5nLmZyb21Db2RlUG9pbnQoLi4uWy4uLmMudG9VcHBlckNhc2UoKV0ubWFwKCh4KSA9PiAxMjczOTcgKyB4LmNoYXJDb2RlQXQoMCkpKSA6ICcnOwpmdW5jdGlvbiB3aGVyZShkKSB7CiAgaWYgKCFkLmNvdW50cnkpIHJldHVybiAnJzsKICBsZXQgbiA9IGQuY291bnRyeTsgdHJ5IHsgbiA9IG5ldyBJbnRsLkRpc3BsYXlOYW1lcyhbJ2FyJ10sIHsgdHlwZTogJ3JlZ2lvbicgfSkub2YoZC5jb3VudHJ5KSB8fCBkLmNvdW50cnk7IH0gY2F0Y2ggKGUpIHt9CiAgY29uc3QgdiA9IGQub25fdnBuID8gJyA8c3BhbiBjbGFzcz0idnBub24iPvCflJIg2LnYqNixIFZQTiAo2KfZhNiz2YrYsdmB2LEg2YHZiiDYo9mF2LHZitmD2KcpPC9zcGFuPicgOiBkLmhhc192cG4gPyAnIDxzcGFuIGNsYXNzPSJtdXRlZCI+wrcgVlBOINmF2YLZgdmI2YQ8L3NwYW4+JyA6ICcnOwogIHJldHVybiBgPHNtYWxsIGNsYXNzPSJ3aGVyZSI+8J+TjSAke2ZsYWcoZC5jb3VudHJ5KX0gJHtlc2Mobil9JHtkLmNpdHkgPyAnIMK3ICcgKyBlc2MoZC5jaXR5KSA6ICcnfSR7dn08L3NtYWxsPmA7Cn0KZnVuY3Rpb24gd2F0Y2hpbmcoZCkgewogIGlmICghZC5ub3dfdCB8fCAhZC5ub3dfdGl0bGUpIHJldHVybiAnJzsKICBjb25zdCB3aGF0ID0gYCR7S0lORFtkLm5vd19raW5kXSB8fCAn4pa2J30gJHtlc2MoZC5ub3dfdGl0bGUpfSR7ZC5ub3dfcGxheWxpc3QgPyAnIDxzcGFuIGNsYXNzPSJtdXRlZCI+wrcgJyArIGVzYyhkLm5vd19wbGF5bGlzdCkgKyAnPC9zcGFuPicgOiAnJ31gOwogIHJldHVybiBpc1dhdGNoaW5nKGQpID8gYDxzbWFsbCBjbGFzcz0ibm93b24iPjxzcGFuIGNsYXNzPSJvbmxpbmUiPjwvc3Bhbj7Ziti02KfZh9ivINin2YTYotmGOiAke3doYXR9PC9zbWFsbD5gIDogYDxzbWFsbCBjbGFzcz0ibm93b2ZmIj7Yotiu2LEg2YXYtNin2YfYr9ipICjZgtio2YQgJHthZ28oZC5ub3dfdCl9KTogJHt3aGF0fTwvc21hbGw+YDsKfQoKYXN5bmMgZnVuY3Rpb24gaW5pdCgpIHsKICBjb25zdCBzID0gYXdhaXQgYXBpKCdzdGF0ZScpOwogIHBsYXlsaXN0cyA9IHMucGxheWxpc3RzIHx8IFtdOwogIGNvbnN0IG9wdHMgPSBwbGF5bGlzdHMubWFwKChwKSA9PiBgPG9wdGlvbiB2YWx1ZT0iJHtlc2MocCl9Ij4ke2VzYyhwKX08L29wdGlvbj5gKS5qb2luKCcnKTsKICAkKCdwbCcpLmlubmVySFRNTCA9IG9wdHM7ICQoJ3hwbCcpLmlubmVySFRNTCA9IG9wdHM7CiAgaWYgKHMuc2lnbmVkKSByZXR1cm4gc2hvdygpOwogICQoJ2xvZ2luJykuY2xhc3NMaXN0LnJlbW92ZSgnaGlkZScpOwogIGlmIChzLnNldHVwKSB7ICQoJ2x0JykudGV4dENvbnRlbnQgPSAn2KPZiNmEINmF2LHYqTog2KfYrtiq2KfYsSDZg9mE2YXYqSDYs9ixINmE2YTYpdiv2KfYsdipJzsgJCgnbGgnKS50ZXh0Q29udGVudCA9ICc4INij2K3YsdmBINi52YTZiSDYp9mE2KPZgtmELiDZh9in2Yog2KfZhNmD2YTZhdipINio2KrYr9iu2YTZgyDYudmE2Ykg2KfZhNmF2YjZgti5INmF2YYg2KPZiiDYrNmH2KfYsi4nOyAkKCdwdycpLmF1dG9jb21wbGV0ZSA9ICduZXctcGFzc3dvcmQnOyB9CiAgJCgncHcnKS5mb2N1cygpOwp9CiQoJ2dvJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdsb2dpbicsIHsgcGFzc3dvcmQ6ICQoJ3B3JykudmFsdWUsIHNldHVwOiBuZXcgVVJMU2VhcmNoUGFyYW1zKGxvY2F0aW9uLnNlYXJjaCkuZ2V0KCdzZXR1cCcpIHx8ICcnIH0pOwogIGlmIChyLm9rKSB7ICQoJ3B3JykudmFsdWUgPSAnJzsgc2hvdygpOyB9IGVsc2UgJCgnbG0nKS50ZXh0Q29udGVudCA9IHIuZXJyb3IgfHwgJ9iu2LfYoyc7Cn07CiQoJ3B3Jykub25rZXlkb3duID0gKGUpID0+IHsgaWYgKGUua2V5ID09PSAnRW50ZXInKSAkKCdnbycpLmNsaWNrKCk7IH07CiQoJ291dCcpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7IGF3YWl0IGFwaSgnbG9nb3V0Jywge30pOyBsb2NhdGlvbi5yZWxvYWQoKTsgfTsKCmZ1bmN0aW9uIHNob3coKSB7ICQoJ2xvZ2luJykuY2xhc3NMaXN0LmFkZCgnaGlkZScpOyAkKCdhcHAnKS5jbGFzc0xpc3QucmVtb3ZlKCdoaWRlJyk7IGxvYWQoKTsgfQoKY29uc3QgVklFV1MgPSB7IGRhc2g6IFsn2YTZiNit2Kkg2KfZhNiq2K3Zg9mFJywgJ9mG2LjYsdipINiz2LHZiti52Kkg2LnZhNmJINmD2YQg2KfZhNij2KzZh9iy2KknXSwgZGV2czogWyfYp9mE2KPYrNmH2LLYqScsICfZg9mEINin2YTYstio2KfZitmGIOKAlCDYp9i22LrYtyDYudmE2Ykg2KPZiiDYrNmH2KfYsiDZhNiq2LnYr9mK2YTZhyddLCBwcm9tbzogWydQcm9tbyBjb2RlcycsICfZg9mEINmD2YjYryDYqNmK2LTYqti62YQg2YXYsdipINmI2K3Yr9ipINi52YTZiSDYrNmH2KfYsiDZiNin2K3YryddLCBwYXk6IFsn2KfZhNiv2YHYuScsICfYp9mE2YTZiiDYqNix2Kcg2KfZhNiv2KfYptix2Kkg2KjZitiv2YHYuSDigJQg2YjYp9mE2YTZiiDYrNmI2ZHYp9mH2Kcg2KjZitin2K7YryBQcm9tbyBjb2RlJ10sIGhlbHA6IFsn2LfYsdmK2YLYqSDYp9mE2KfYs9iq2K7Yr9in2YUnLCAn2K7Yt9mI2KfYqiDYs9ix2YrYudipJ10gfTsKZnVuY3Rpb24gdmlldyh2KSB7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLm5hdltkYXRhLXZdJykuZm9yRWFjaCgobikgPT4gbi5jbGFzc0xpc3QudG9nZ2xlKCdvbicsIG4uZGF0YXNldC52ID09PSB2KSk7CiAgT2JqZWN0LmtleXMoVklFV1MpLmZvckVhY2goKGspID0+ICQoJ3YtJyArIGspLmNsYXNzTGlzdC50b2dnbGUoJ2hpZGUnLCBrICE9PSB2KSk7CiAgJCgndnQnKS50ZXh0Q29udGVudCA9IFZJRVdTW3ZdWzBdOyAkKCd2cycpLnRleHRDb250ZW50ID0gVklFV1Nbdl1bMV07CiAgaWYgKHYgPT09ICdwcm9tbycpIGxvYWRQcm9tb3MoKTsKICBpZiAodiA9PT0gJ3BheScpIGxvYWRQYXkoKTsKfQovLyAtLS0tLS0tLS0tIHBheW1lbnQgLS0tLS0tLS0tLQphc3luYyBmdW5jdGlvbiBsb2FkUGF5KCkgewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3BheScpOwogICQoJ3BheS1wcmljZScpLnZhbHVlID0gci5wcmljZSB8fCAnJzsgJCgncGF5LWxpbmsnKS52YWx1ZSA9IHIubGluayB8fCAnJzsgJCgncGF5LW9uJykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCAhIXIub24pOwogICQoJ3BheS1zdCcpLnRleHRDb250ZW50ID0gKHIub24gPyAn2LTYutmR2KfZhCcgOiAn2YXYt9mB2YonKSArIChyLmxpbmsgPyAnIMK3IFZlbm1vIEAnICsgci5saW5rLnJlcGxhY2UoL15ALywgJycpIDogJycpOwp9CiQoJ3BheS1vbicpLm9uY2xpY2sgPSAoKSA9PiAkKCdwYXktb24nKS5jbGFzc0xpc3QudG9nZ2xlKCdvbicpOwokKCdwYXktc2F2ZScpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgncGF5JywgeyBwcmljZTogJCgncGF5LXByaWNlJykudmFsdWUudHJpbSgpLCBsaW5rOiAkKCdwYXktbGluaycpLnZhbHVlLnRyaW0oKSwgb246ICQoJ3BheS1vbicpLmNsYXNzTGlzdC5jb250YWlucygnb24nKSB9KTsKICAkKCdwYXktbXNnJykudGV4dENvbnRlbnQgPSByLm9rID8gJ9in2YbYrdmB2Lgg4pyTJyA6IChyLmVycm9yIHx8ICfYrti32KMnKTsgbG9hZFBheSgpOwp9OwovLyAtLS0tLS0tLS0tIHByb21vIGNvZGVzOiBvbmUgdXNlLCBvbmUgZGV2aWNlIC0tLS0tLS0tLS0KY29uc3QgcGNvZGUgPSAoYykgPT4gYy5yZXBsYWNlKC8oLns0fSkoLns0fSkvLCAnJDEtJDInKTsKYXN5bmMgZnVuY3Rpb24gbG9hZFByb21vcygpIHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdwcm9tb3MnKTsgY29uc3QgbGlzdCA9IHIucHJvbW9zIHx8IFtdOwogIGNvbnN0IGZyZWUgPSBsaXN0LmZpbHRlcigocCkgPT4gIXAudXNlZF9ieSkubGVuZ3RoOwogICQoJ3Byb21vLW4nKS50ZXh0Q29udGVudCA9IGAke2ZyZWV9INis2KfZh9iyIMK3ICR7bGlzdC5sZW5ndGggLSBmcmVlfSDZhdiz2KrYudmF2YRgOwogICQoJ3B0YicpLmlubmVySFRNTCA9IGxpc3QubGVuZ3RoID8gbGlzdC5tYXAoKHApID0+IHsKICAgIGNvbnN0IGQgPSBwLnVzZWRfYnkgPyBkZXZzLmZpbmQoKHgpID0+IHguY29kZSA9PT0gcC51c2VkX2J5KSA6IG51bGw7CiAgICBjb25zdCBzdCA9IHAudXNlZF9ieSA/IGA8c3BhbiBjbGFzcz0ic3Qgcy1vZmYiPtmF2LPYqti52YXZhCDCtyAke2VzYyhkPy5uYW1lIHx8IHByZXR0eShwLnVzZWRfYnkpKX0gwrcg2YLYqNmEICR7YWdvKHAudXNlZF9hdCl9PC9zcGFuPmAgOiAnPHNwYW4gY2xhc3M9InN0IHMtb24iPtis2KfZh9iyPC9zcGFuPic7CiAgICByZXR1cm4gYDx0cj48dGQ+PHNwYW4gY2xhc3M9ImNvZGUiPiR7ZXNjKHBjb2RlKHAuY29kZSkpfTwvc3Bhbj48L3RkPjx0ZD4ke2VzYyhwLm5vdGUgfHwgJycpfTwvdGQ+PHRkPiR7c3R9PC90ZD4KICAgICAgPHRkIHN0eWxlPSJ0ZXh0LWFsaWduOmxlZnQiPiR7cC51c2VkX2J5ID8gJycgOiBgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWNwPSIke2VzYyhwY29kZShwLmNvZGUpKX0iPtmG2LPYrjwvYnV0dG9uPiBgfTxidXR0b24gY2xhc3M9ImJ0biByZWQgc20iIGRhdGEtcGQ9IiR7ZXNjKHAuY29kZSl9Ij7Yrdiw2YE8L2J1dHRvbj48L3RkPjwvdHI+YDsKICB9KS5qb2luKCcnKSA6ICc8dHI+PHRkIGNvbHNwYW49IjQiIGNsYXNzPSJlbXB0eSI+2YXYpyDZgdmKINij2YPZiNin2K8g4oCUINij2LXYr9ixINij2YjZhCDZg9mI2K8g2YXZhiDZgdmI2YI8L3RkPjwvdHI+JzsKICAkKCdwdGInKS5xdWVyeVNlbGVjdG9yQWxsKCdbZGF0YS1jcF0nKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSAoKSA9PiB7IG5hdmlnYXRvci5jbGlwYm9hcmQ/LndyaXRlVGV4dChiLmRhdGFzZXQuY3ApOyB0b2FzdCgn2KfZhtiq2LPYrjogJyArIGIuZGF0YXNldC5jcCk7IH0pOwogICQoJ3B0YicpLnF1ZXJ5U2VsZWN0b3JBbGwoJ1tkYXRhLXBkXScpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9IGFzeW5jICgpID0+IHsgaWYgKCFjb25maXJtKCfYrdiw2YEg2KfZhNmD2YjYr9ifJykpIHJldHVybjsgYXdhaXQgYXBpKCdwcm9tb19kZWxldGUnLCB7IGNvZGU6IGIuZGF0YXNldC5wZCB9KTsgbG9hZFByb21vcygpOyB9KTsKfQokKCdwZ2VuJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdwcm9tbycsIHsgbjogKyQoJ3Bjb3VudCcpLnZhbHVlLCBub3RlOiAkKCdwbm90ZScpLnZhbHVlLnRyaW0oKSB9KTsKICBpZiAoci5vaykgeyAkKCdwbm90ZScpLnZhbHVlID0gJyc7IHRvYXN0KCfYqtmFINil2LXYr9in2LEgJyArIChyLmNvZGVzIHx8IFtdKS5sZW5ndGggKyAnINmD2YjYrycpOyBsb2FkUHJvbW9zKCk7IH0gZWxzZSB0b2FzdChyLmVycm9yIHx8ICfYrti32KMnKTsKfTsKZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLm5hdltkYXRhLXZdJykuZm9yRWFjaCgobikgPT4gbi5vbmNsaWNrID0gKCkgPT4gdmlldyhuLmRhdGFzZXQudikpOwoKYXN5bmMgZnVuY3Rpb24gbG9hZCgpIHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdkZXZpY2VzJyk7CiAgaWYgKHIub2sgPT09IGZhbHNlICYmIHIuZXJyb3IpIHsgbG9jYXRpb24ucmVsb2FkKCk7IHJldHVybjsgfQogIGRldnMgPSByLmRldmljZXMgfHwgW107CiAgcmVuZGVyU3RhdHMoKTsgcmVuZGVyVGFibGUoKTsgcmVuZGVyQXR0bigpOwp9CiQoJ3JlZnJlc2gnKS5vbmNsaWNrID0gKCkgPT4gbG9hZCgpLnRoZW4oKCkgPT4gdG9hc3QoJ9iq2YUg2KfZhNiq2K3Yr9mK2KsnKSk7CgpmdW5jdGlvbiBjb3VudHMoKSB7CiAgY29uc3QgYyA9IHsgYWxsOiBkZXZzLmxlbmd0aCwgb246IDAsIHdhaXQ6IDAsIHNvb246IDAsIGV4cDogMCwgb2ZmOiAwLCBvbmxpbmU6IDAsIHdhdGNoOiAwIH07CiAgZGV2cy5mb3JFYWNoKChkKSA9PiB7IGNbc3RhdGUoZCkua10rKzsgaWYgKGlzT25saW5lKGQpKSBjLm9ubGluZSsrOyBpZiAoaXNXYXRjaGluZyhkKSkgYy53YXRjaCsrOyB9KTsKICByZXR1cm4gYzsKfQpmdW5jdGlvbiByZW5kZXJTdGF0cygpIHsKICBjb25zdCBjID0gY291bnRzKCk7CiAgY29uc3QgUyA9IFtbJ2FsbCcsICfZg9mEINin2YTYo9is2YfYstipJywgYy5hbGwsICd2YXIoLS10MiknXSwgWydvbmxpbmUnLCAn2YXYqti12YQg2KfZhNii2YYnLCBjLm9ubGluZSwgJ3ZhcigtLWEpJ10sIFsnd2F0Y2gnLCAn2YrYtNin2YfYryDYp9mE2KLZhicsIGMud2F0Y2gsICd2YXIoLS1hKSddLCBbJ29uJywgJ9i02LrZkdin2YQnLCBjLm9uICsgYy5zb29uLCAndmFyKC0tYSknXSwKICAgIFsnd2FpdCcsICfYqNin2YbYqti42KfYsSDYp9mE2KrZgdi52YrZhCcsIGMud2FpdCwgJ3ZhcigtLWIpJ10sIFsnc29vbicsICfZitmG2KrZh9mKINiu2YTYp9mEIDcg2KPZitin2YUnLCBjLnNvb24sICd2YXIoLS15KSddLCBbJ2V4cCcsICfZhdmG2KrZh9mKJywgYy5leHAsICd2YXIoLS1yKSddLCBbJ29mZicsICfZhdmI2YLZiNmBJywgYy5vZmYsICd2YXIoLS10MyknXV07CiAgJCgnc3RhdHMnKS5pbm5lckhUTUwgPSBTLm1hcCgoW2ssIGwsIG4sIGNvbF0pID0+IGA8ZGl2IGNsYXNzPSJzdGF0IiBkYXRhLWY9IiR7a30iPjxkaXYgY2xhc3M9ImwiPjxzcGFuIGNsYXNzPSJkb3QiIHN0eWxlPSJiYWNrZ3JvdW5kOiR7Y29sfSI+PC9zcGFuPiR7bH08L2Rpdj48ZGl2IGNsYXNzPSJuIj4ke259PC9kaXY+PC9kaXY+YCkuam9pbignJyk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnN0YXQnKS5mb3JFYWNoKChzKSA9PiBzLm9uY2xpY2sgPSAoKSA9PiB7IGZpbHRlciA9IHMuZGF0YXNldC5mOyB2aWV3KCdkZXZzJyk7IHJlbmRlclRhYmxlKCk7IH0pOwogIGNvbnN0IEYgPSBbWydhbGwnLCAn2KfZhNmD2YQnXSwgWydvbmxpbmUnLCAn2YXYqti12YQg2KfZhNii2YYnXSwgWyd3YXRjaCcsICfZiti02KfZh9ivINin2YTYotmGJ10sIFsnb24nLCAn2LTYutmR2KfZhCddLCBbJ3dhaXQnLCAn2KjYp9mG2KrYuNin2LEg2KfZhNiq2YHYudmK2YQnXSwgWydzb29uJywgJ9mK2YbYqtmH2Yog2YLYsdmK2KjYp9mLJ10sIFsnZXhwJywgJ9mF2YbYqtmH2YonXSwgWydvZmYnLCAn2YXZiNmC2YjZgSddXTsKICAkKCdjaGlwcycpLmlubmVySFRNTCA9IEYubWFwKChbaywgbF0pID0+IGA8YnV0dG9uIGNsYXNzPSJjaGlwJHtmaWx0ZXIgPT09IGsgPyAnIG9uJyA6ICcnfSIgZGF0YS1mPSIke2t9Ij4ke2x9IDxzcGFuIGNsYXNzPSJwaWxsIj4ke2sgPT09ICdvbicgPyBjLm9uICsgYy5zb29uIDogY1trXX08L3NwYW4+PC9idXR0b24+YCkuam9pbignJyk7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLmNoaXAnKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSAoKSA9PiB7IGZpbHRlciA9IGIuZGF0YXNldC5mOyByZW5kZXJTdGF0cygpOyByZW5kZXJUYWJsZSgpOyB9KTsKfQpmdW5jdGlvbiByb3coZCkgewogIGNvbnN0IHMgPSBzdGF0ZShkKTsKICBjb25zdCBwbHMgPSAoZC5wbGF5bGlzdCA/IGA8c3BhbiBjbGFzcz0idGFnIj4ke2VzYyhkLnBsYXlsaXN0KX08L3NwYW4+YCA6ICc8c3BhbiBjbGFzcz0ibXV0ZWQiPuKAlDwvc3Bhbj4nKSArIChkLmV4dHJhcyB8fCBbXSkubWFwKCh4KSA9PiBgPHNwYW4gY2xhc3M9InRhZyI+KyAke2VzYyh4KX08L3NwYW4+YCkuam9pbignJyk7CiAgcmV0dXJuIGA8dHIgZGF0YS1jPSIke2VzYyhkLmNvZGUpfSI+PHRkPjxzcGFuIGNsYXNzPSJjb2RlIj4ke3ByZXR0eShlc2MoZC5jb2RlKSl9PC9zcGFuPjwvdGQ+CiAgICA8dGQgY2xhc3M9IndobyI+PGI+JHtkLm5hbWUgPyBlc2MoZC5uYW1lKSA6ICc8c3BhbiBjbGFzcz0ibXV0ZWQiPtio2K/ZiNmGINin2LPZhTwvc3Bhbj4nfTwvYj48c21hbGw+JHtlc2MoZC5tb2RlbCB8fCAnJyl9PC9zbWFsbD4ke3doZXJlKGQpfSR7d2F0Y2hpbmcoZCl9PC90ZD4KICAgIDx0ZD4ke3Bsc30ke2QuaGFzX3ZwbiA/ICc8c3BhbiBjbGFzcz0idGFnIj7wn5uhIFZQTjwvc3Bhbj4nIDogJyd9JHtkLnByb21vID8gJzxzcGFuIGNsYXNzPSJ0YWciPicgKyAoZC5wcm9tby5zdGFydHNXaXRoKCdQQUlEJykgPyAn8J+SsyDYr9mB2LknIDogJ/Cfjp8gJyArIGVzYyhkLnByb21vLnJlcGxhY2UoLyguezR9KSguezR9KS8sICckMS0kMicpKSkgKyAnPC9zcGFuPicgOiAnJ308L3RkPjx0ZD48c3BhbiBjbGFzcz0ic3Qgcy0ke3Mua30iPiR7aXNPbmxpbmUoZCkgPyAnPHNwYW4gY2xhc3M9Im9ubGluZSI+PC9zcGFuPicgOiAnJ30ke3MudH08L3NwYW4+PC90ZD4KICAgIDx0ZCBjbGFzcz0iaGlkZS1tIG11dGVkIj4ke2FnbyhkLnNlZW4pfTwvdGQ+PHRkIGNsYXNzPSJoaWRlLW0gbXV0ZWQiPiR7ZGF5KGQuZXhwaXJlcykgfHwgJ+KAlCd9PC90ZD48L3RyPmA7Cn0KZnVuY3Rpb24gYmluZFJvd3ModGIpIHsgdGIucXVlcnlTZWxlY3RvckFsbCgndHJbZGF0YS1jXScpLmZvckVhY2goKHRyKSA9PiB0ci5vbmNsaWNrID0gKCkgPT4gb3BlbkRyYXdlcih0ci5kYXRhc2V0LmMpKTsgfQpmdW5jdGlvbiByZW5kZXJUYWJsZSgpIHsKICBjb25zdCBxID0gJCgncScpLnZhbHVlLnRyaW0oKS50b0xvd2VyQ2FzZSgpLnJlcGxhY2UoL1xzL2csICcnKTsKICBjb25zdCBsaXN0ID0gZGV2cy5maWx0ZXIoKGQpID0+IHsKICAgIGNvbnN0IGsgPSBzdGF0ZShkKS5rOwogICAgaWYgKGZpbHRlciA9PT0gJ3dhdGNoJyA/ICFpc1dhdGNoaW5nKGQpIDogZmlsdGVyID09PSAnb25saW5lJyA/ICFpc09ubGluZShkKSA6IGZpbHRlciA9PT0gJ29uJyA/ICEoayA9PT0gJ29uJyB8fCBrID09PSAnc29vbicpIDogZmlsdGVyICE9PSAnYWxsJyAmJiBrICE9PSBmaWx0ZXIpIHJldHVybiBmYWxzZTsKICAgIGlmICghcSkgcmV0dXJuIHRydWU7CiAgICByZXR1cm4gW2QuY29kZSwgZC5uYW1lLCBkLnBsYXlsaXN0LCBkLm1vZGVsLCBkLm5vd190aXRsZSwgLi4uKGQuZXh0cmFzIHx8IFtdKV0uc29tZSgodikgPT4gU3RyaW5nKHYgfHwgJycpLnRvTG93ZXJDYXNlKCkucmVwbGFjZSgvXHMvZywgJycpLmluY2x1ZGVzKHEpKTsKICB9KTsKICAkKCd0YicpLmlubmVySFRNTCA9IGxpc3QubGVuZ3RoID8gbGlzdC5tYXAocm93KS5qb2luKCcnKSA6IGA8dHI+PHRkIGNvbHNwYW49IjYiIGNsYXNzPSJlbXB0eSI+2YXYpyDZgdmKINij2KzZh9iy2Kkg2YfZiNmGPC90ZD48L3RyPmA7CiAgYmluZFJvd3MoJCgndGInKSk7Cn0KJCgncScpLm9uaW5wdXQgPSByZW5kZXJUYWJsZTsKZnVuY3Rpb24gcmVuZGVyQXR0bigpIHsKICBjb25zdCBvcmRlciA9IHsgd2FpdDogMCwgc29vbjogMSwgZXhwOiAyIH07CiAgY29uc3QgbGlzdCA9IGRldnMuZmlsdGVyKChkKSA9PiBzdGF0ZShkKS5rIGluIG9yZGVyKS5zb3J0KChhLCBiKSA9PiBvcmRlcltzdGF0ZShhKS5rXSAtIG9yZGVyW3N0YXRlKGIpLmtdKTsKICAkKCdhdHRuLW4nKS50ZXh0Q29udGVudCA9IGxpc3QubGVuZ3RoID8gYCR7bGlzdC5sZW5ndGh9INis2YfYp9iyYCA6ICcnOwogICQoJ2F0dG4nKS5pbm5lckhUTUwgPSBsaXN0Lmxlbmd0aCA/IGxpc3QubWFwKHJvdykuam9pbignJykgOiBgPHRyPjx0ZCBjbGFzcz0iZW1wdHkiPtmD2YQg2LTZiiDYqtmF2KfZhSDinJMg4oCUINmF2Kcg2YHZiiDYo9is2YfYstipINio2KfZhtiq2LjYp9ixINij2Ygg2YXZhtiq2YfZitipPC90ZD48L3RyPmA7CiAgYmluZFJvd3MoJCgnYXR0bicpKTsKfQoKLy8gLS0tLS0tLS0tLSBkcmF3ZXIgLS0tLS0tLS0tLQpmdW5jdGlvbiBvcGVuRHJhd2VyKGNvZGUpIHsKICBlZGl0aW5nID0gY29kZSA/IGRldnMuZmluZCgoeCkgPT4geC5jb2RlID09PSBjb2RlKSA6IG51bGw7CiAgY29uc3QgZCA9IGVkaXRpbmcgfHwge307CiAgJCgnZHQnKS50ZXh0Q29udGVudCA9IGVkaXRpbmcgPyAoZC5uYW1lIHx8ICfYrNmH2KfYsiAnICsgcHJldHR5KGQuY29kZSkpIDogJ9is2YfYp9iyINis2K/ZitivJzsKICAkKCdkc3ViJykuaW5uZXJIVE1MID0gZWRpdGluZyA/IGA8c3BhbiBjbGFzcz0iY29kZSI+JHtwcmV0dHkoZXNjKGQuY29kZSkpfTwvc3Bhbj4gwrcgJHtlc2MoZC5tb2RlbCB8fCAnJyl9IMK3INii2K7YsSDYuNmH2YjYsSAke2FnbyhkLnNlZW4pfSR7d2F0Y2hpbmcoZCkgPyAnPGJyPicgKyB3YXRjaGluZyhkKSA6ICcnfWAgOiAn2KfZg9iq2Kgg2KfZhNmD2YjYryDYp9mE2YTZiiDYuNin2YfYsSDYudmE2Ykg2LTYp9i02Kkg2KfZhNiy2KjZiNmGJzsKICAkKCdjb2RlJykudmFsdWUgPSBkLmNvZGUgPyBwcmV0dHkoZC5jb2RlKSA6ICcnOyAkKCdjb2RlJykuZGlzYWJsZWQgPSAhIWVkaXRpbmc7CiAgJCgnbmFtZScpLnZhbHVlID0gZC5uYW1lIHx8ICcnOyAkKCd3bmFtZScpLnZhbHVlID0gZC53ZWxjb21lIHx8ICcnOyAkKCdwbCcpLnZhbHVlID0gZC5wbGF5bGlzdCB8fCBwbGF5bGlzdHNbMF0gfHwgJyc7CiAgJCgndScpLnZhbHVlID0gJyc7ICQoJ3AnKS52YWx1ZSA9ICcnOyAkKCdleCcpLnZhbHVlID0gZGF5KGQuZXhwaXJlcyk7CiAgJCgnbGhpbnQnKS50ZXh0Q29udGVudCA9IGQuaGFzX2xvZ2luID8gJ9in2YTZitmI2LLYsSDZhdit2YHZiNi4INmI2YXYtNmB2ZHYsS4g2KfZg9iq2Kgg2YrZiNiy2LEg2YjYqNin2LPZiNmI2LHYryDYrNiv2KfYryDYqNizINil2LDYpyDYqNiv2YMg2KrYutmK2ZHYsdmH2YUuJyA6ICfYp9mD2KrYqCDYp9mE2YrZiNiy2LEg2YjYp9mE2KjYp9iz2YjZiNix2K8g2KrYqNi5INin2YTZgCBwbGF5bGlzdC4nOwogICQoJ2FjdCcpLmNsYXNzTGlzdC50b2dnbGUoJ29uJywgZWRpdGluZyA/ICEhZC5hY3RpdmUgOiB0cnVlKTsKICAkKCdkZWwnKS5jbGFzc0xpc3QudG9nZ2xlKCdoaWRlJywgIWVkaXRpbmcpOyAkKCd4c2VjJykuY2xhc3NMaXN0LnRvZ2dsZSgnaGlkZScsICFlZGl0aW5nKTsgJCgndnNlYycpLmNsYXNzTGlzdC50b2dnbGUoJ2hpZGUnLCAhZWRpdGluZyk7CiAgJCgndmNvbmYnKS52YWx1ZSA9ICcnOyB2cG9vbCgpOyB2ZHJhdyhkLmhhc192cG4pOwogIHJlbmRlckV4dHJhcygpOyAkKCdzbScpLnRleHRDb250ZW50ID0gJyc7CiAgJCgnc2NyaW0nKS5jbGFzc0xpc3QuYWRkKCdvcGVuJyk7ICQoJ2RyYXdlcicpLmNsYXNzTGlzdC5hZGQoJ29wZW4nKTsKICBzZXRUaW1lb3V0KCgpID0+IChlZGl0aW5nID8gJCgnbmFtZScpIDogJCgnY29kZScpKS5mb2N1cygpLCAyNTApOwp9CmZ1bmN0aW9uIGNsb3NlRHJhd2VyKCkgeyAkKCdzY3JpbScpLmNsYXNzTGlzdC5yZW1vdmUoJ29wZW4nKTsgJCgnZHJhd2VyJykuY2xhc3NMaXN0LnJlbW92ZSgnb3BlbicpOyBlZGl0aW5nID0gbnVsbDsgfQokKCdhZGQnKS5vbmNsaWNrID0gKCkgPT4gb3BlbkRyYXdlcihudWxsKTsKJCgnZHgnKS5vbmNsaWNrID0gJCgnY2FuY2VsJykub25jbGljayA9ICQoJ3NjcmltJykub25jbGljayA9IGNsb3NlRHJhd2VyOwpkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCdrZXlkb3duJywgKGUpID0+IHsgaWYgKGUua2V5ID09PSAnRXNjYXBlJykgY2xvc2VEcmF3ZXIoKTsgfSk7CiQoJ2FjdCcpLm9uY2xpY2sgPSAoKSA9PiAkKCdhY3QnKS5jbGFzc0xpc3QudG9nZ2xlKCdvbicpOwpkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCdbZGF0YS1hZGRdJykuZm9yRWFjaCgoYikgPT4gYi5vbmNsaWNrID0gKCkgPT4gewogIGNvbnN0IG4gPSArYi5kYXRhc2V0LmFkZDsKICBpZiAoIW4pIHsgJCgnZXgnKS52YWx1ZSA9ICcnOyByZXR1cm47IH0KICBjb25zdCBjdXIgPSAkKCdleCcpLnZhbHVlID8gRGF0ZS5wYXJzZSgkKCdleCcpLnZhbHVlKSA6IDA7CiAgJCgnZXgnKS52YWx1ZSA9IGRheShNYXRoLm1heChjdXIsIERhdGUubm93KCkpICsgbiAqIERBWSk7Cn0pOwpmdW5jdGlvbiByZW5kZXJFeHRyYXMoKSB7CiAgY29uc3QgeHMgPSBlZGl0aW5nPy5leHRyYXMgfHwgW107CiAgJCgneGxpc3QnKS5pbm5lckhUTUwgPSB4cy5sZW5ndGggPyB4cy5tYXAoKHgpID0+IGA8ZGl2IGNsYXNzPSJ4bCI+PHNwYW4gY2xhc3M9InRhZyI+JHtlc2MoeCl9PC9zcGFuPjxidXR0b24gY2xhc3M9ImJ0biByZWQgc20iIGRhdGEteD0iJHtlc2MoeCl9Ij7YtNmK2YQ8L2J1dHRvbj48L2Rpdj5gKS5qb2luKCcnKSA6ICc8ZGl2IGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxM3B4Ij7ZhdinINmB2YogcGxheWxpc3RzINil2LbYp9mB2YrYqS48L2Rpdj4nOwogICQoJ3hsaXN0JykucXVlcnlTZWxlY3RvckFsbCgnW2RhdGEteF0nKS5mb3JFYWNoKChiKSA9PiBiLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgICBpZiAoIWNvbmZpcm0oYNi02YrZhCAke2IuZGF0YXNldC54fSDZhdmGINmH2LDYpyDYp9mE2KzZh9in2LLYn2ApKSByZXR1cm47CiAgICBhd2FpdCBhcGkoJ2V4dHJhJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUsIHBsYXlsaXN0OiBiLmRhdGFzZXQueCwgcmVtb3ZlOiB0cnVlIH0pOwogICAgYXdhaXQgcmVsb2FkRWRpdGluZygpOyB0b2FzdCgn2KfZhti02KfZhNiqJyk7CiAgfSk7Cn0KYXN5bmMgZnVuY3Rpb24gcmVsb2FkRWRpdGluZygpIHsgY29uc3QgYyA9IGVkaXRpbmc/LmNvZGU7IGF3YWl0IGxvYWQoKTsgaWYgKGMpIHsgZWRpdGluZyA9IGRldnMuZmluZCgoeCkgPT4geC5jb2RlID09PSBjKTsgcmVuZGVyRXh0cmFzKCk7IH0gfQokKCd4YWRkJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBpZiAoIWVkaXRpbmcpIHJldHVybjsKICBjb25zdCByID0gYXdhaXQgYXBpKCdleHRyYScsIHsgY29kZTogZWRpdGluZy5jb2RlLCBwbGF5bGlzdDogJCgneHBsJykudmFsdWUsIHVzZXI6ICQoJ3h1JykudmFsdWUsIHBhc3M6ICQoJ3hwJykudmFsdWUgfSk7CiAgaWYgKHIub2spIHsgJCgneHUnKS52YWx1ZSA9ICcnOyAkKCd4cCcpLnZhbHVlID0gJyc7IGF3YWl0IHJlbG9hZEVkaXRpbmcoKTsgdG9hc3QoJ9in2YbYttin2YHYqiDinJMg4oCUINiu2YTZiiDYp9mE2LLYqNmI2YYg2YrZg9io2LMgUmVsb2FkJyk7IH0KICBlbHNlICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKHIuZXJyb3IpfTwvc3Bhbj5gOwp9OwovLyBvbmUgc3dpdGNoIChvd25lciwgMTEgTm92IDIwMjYpOiBncmVlbiBPTiA9IHRoaXMgZGV2aWNlIHVzZXMgb3VyIFZQTiwgZ3JleSBPRkYgPSBub3Q7IHRoZSBmaWxlcyBhcmUga2VwdCBieSB0aGUgc2l0ZQpjb25zdCB2ZHJhdyA9IChvbikgPT4gewogIGNvbnN0IGIgPSAkKCd2dG9nZ2xlJyk7IGIudGV4dENvbnRlbnQgPSBvbiA/ICdPTicgOiAnT0ZGJzsKICBiLnN0eWxlLmJhY2tncm91bmQgPSBvbiA/ICcjMTBCOTgxJyA6ICcjNEI1NTYzJzsgYi5zdHlsZS5jb2xvciA9IG9uID8gJyMwNDE0MEQnIDogJyNFNUU3RUInOwogICQoJ3ZzdGF0ZScpLnRleHRDb250ZW50ID0gb24gPyAn2LTYutmR2KfZhCDYudmE2Ykg2YfYsNinINin2YTYrNmH2KfYsicgOiAn2YXYt9mB2YonOwp9OwokKCd2dG9nZ2xlJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBpZiAoIWVkaXRpbmcpIHJldHVybjsKICBjb25zdCByID0gZWRpdGluZy5oYXNfdnBuID8gYXdhaXQgYXBpKCd2cG4nLCB7IGNvZGU6IGVkaXRpbmcuY29kZSwgY29uZjogJycgfSkgOiBhd2FpdCBhcGkoJ3Zwbl9vbicsIHsgY29kZTogZWRpdGluZy5jb2RlIH0pOwogIGlmIChyLm9rKSB7IGF3YWl0IHJlbG9hZEVkaXRpbmcoKTsgdnBvb2woKTsgdmRyYXcoZWRpdGluZy5oYXNfdnBuKTsgdG9hc3QoZWRpdGluZy5oYXNfdnBuID8gJ1ZQTiDYp9i02KrYutmEIOKAlCDYrtmE2Yog2KfZhNiy2KjZiNmGINmK2YPYqNizIFJlbG9hZCcgOiAnVlBOINin2YbYt9mB2YknKTsgfQogIGVsc2UgJCgnc20nKS5pbm5lckhUTUwgPSBgPHNwYW4gY2xhc3M9ImJhZCI+JHtlc2Moci5lcnJvcil9PC9zcGFuPmA7Cn07CmNvbnN0IHZwb29sID0gYXN5bmMgKCkgPT4geyB0cnkgeyBjb25zdCByID0gYXdhaXQgYXBpKCd2cG5wb29sJyk7IGlmIChyLm9rKSAkKCd2cG9vbCcpLnRleHRDb250ZW50ID0gYMK3INmF2KrYp9itICR7ci5mcmVlfSDZhdmGICR7ci50b3RhbH1gOyB9IGNhdGNoIChlKSB7fSB9OwokKCd2b24nKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGlmICghZWRpdGluZykgcmV0dXJuOwogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3Zwbl9vbicsIHsgY29kZTogZWRpdGluZy5jb2RlIH0pOwogIGlmIChyLm9rKSB7IGF3YWl0IHJlbG9hZEVkaXRpbmcoKTsgdnBvb2woKTsgJCgndnN0YXRlJykuaW5uZXJIVE1MID0gJzxzcGFuIGNsYXNzPSJvayI+4pyTINin2YTZgCBWUE4g2LTYutmR2KfZhCDZhNmH2LDYpyDYp9mE2KzZh9in2LIg4oCUINiu2YTZiiDYp9mE2LLYqNmI2YYg2YrZg9io2LMgUmVsb2FkPC9zcGFuPic7IHRvYXN0KCdWUE4g2KfYtNiq2LrZhCcpOyB9CiAgZWxzZSAkKCdzbScpLmlubmVySFRNTCA9IGA8c3BhbiBjbGFzcz0iYmFkIj4ke2VzYyhyLmVycm9yKX08L3NwYW4+YDsKfTsKJCgndnNhdmUnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGlmICghZWRpdGluZykgcmV0dXJuOwogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3ZwbicsIHsgY29kZTogZWRpdGluZy5jb2RlLCBjb25mOiAkKCd2Y29uZicpLnZhbHVlIH0pOwogIGlmIChyLm9rKSB7ICQoJ3Zjb25mJykudmFsdWUgPSAnJzsgYXdhaXQgcmVsb2FkRWRpdGluZygpOyAkKCd2c3RhdGUnKS5pbm5lckhUTUwgPSAnPHNwYW4gY2xhc3M9Im9rIj7inJMg2KfZhtit2YHYuCDigJQg2K7ZhNmKINin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQ8L3NwYW4+JzsgdG9hc3QoJ1ZQTiDYp9mG2K3Zgdi4Jyk7IH0KICBlbHNlICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKHIuZXJyb3IpfTwvc3Bhbj5gOwp9OwokKCd2ZGVsJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBpZiAoIWVkaXRpbmcgfHwgIWNvbmZpcm0oJ9i02YrZhCDYp9mE2YAgVlBOINmF2YYg2YfYsNinINin2YTYrNmH2KfYstifJykpIHJldHVybjsKICBhd2FpdCBhcGkoJ3ZwbicsIHsgY29kZTogZWRpdGluZy5jb2RlLCBjb25mOiAnJyB9KTsgYXdhaXQgcmVsb2FkRWRpdGluZygpOyB2cG9vbCgpOyAkKCd2c3RhdGUnKS5pbm5lckhUTUwgPSAnPHNwYW4gY2xhc3M9Im11dGVkIj7ZhdinINmB2YogVlBOPC9zcGFuPic7IHRvYXN0KCfYp9mG2LTYp9mEJyk7Cn07CiQoJ3NhdmUnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGNvbnN0IGNvZGUgPSAkKCdjb2RlJykudmFsdWUucmVwbGFjZSgvXEQvZywgJycpOwogIGlmIChjb2RlLmxlbmd0aCAhPT0gOCkgeyAkKCdzbScpLmlubmVySFRNTCA9ICc8c3BhbiBjbGFzcz0iYmFkIj7Zg9mI2K8g2KfZhNis2YfYp9iyIDgg2KPYsdmC2KfZhTwvc3Bhbj4nOyByZXR1cm47IH0KICBjb25zdCBkID0gZGV2cy5maW5kKCh4KSA9PiB4LmNvZGUgPT09IGNvZGUpOwogIGlmICghZD8uaGFzX2xvZ2luICYmICghJCgndScpLnZhbHVlIHx8ICEkKCdwJykudmFsdWUpKSB7ICQoJ3NtJykuaW5uZXJIVE1MID0gJzxzcGFuIGNsYXNzPSJiYWQiPtin2YPYqtioINin2YTZitmI2LLYsSDZiNin2YTYqNin2LPZiNmI2LHYrzwvc3Bhbj4nOyByZXR1cm47IH0KICBjb25zdCByID0gYXdhaXQgYXBpKCdzYXZlJywgeyBjb2RlLCBuYW1lOiAkKCduYW1lJykudmFsdWUudHJpbSgpLCB3ZWxjb21lOiAkKCd3bmFtZScpLnZhbHVlLnRyaW0oKSwgcGxheWxpc3Q6ICQoJ3BsJykudmFsdWUsIHVzZXI6ICQoJ3UnKS52YWx1ZSwgcGFzczogJCgncCcpLnZhbHVlLCBleHBpcmVzOiAkKCdleCcpLnZhbHVlLCBhY3RpdmU6ICQoJ2FjdCcpLmNsYXNzTGlzdC5jb250YWlucygnb24nKSB9KTsKICBpZiAoIXIub2spIHsgJCgnc20nKS5pbm5lckhUTUwgPSBgPHNwYW4gY2xhc3M9ImJhZCI+JHtlc2Moci5lcnJvcil9PC9zcGFuPmA7IHJldHVybjsgfQogICQoJ3AnKS52YWx1ZSA9ICcnOyBjbG9zZURyYXdlcigpOyBhd2FpdCBsb2FkKCk7IHRvYXN0KCfYp9mG2K3Zgdi4IOKckyDigJQg2K7ZhNmKINin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQnKTsKfTsKJCgnZGVsJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBpZiAoIWVkaXRpbmcgfHwgIWNvbmZpcm0oYNit2LDZgSDYp9mE2KzZh9in2LIgJHtwcmV0dHkoZWRpdGluZy5jb2RlKX0g2YbZh9in2KbZitin2YvYn2ApKSByZXR1cm47CiAgYXdhaXQgYXBpKCdkZWxldGUnLCB7IGNvZGU6IGVkaXRpbmcuY29kZSB9KTsgY2xvc2VEcmF3ZXIoKTsgYXdhaXQgbG9hZCgpOyB0b2FzdCgn2KfZhtit2LDZgScpOwp9Owppbml0KCk7CnNldEludGVydmFsKCgpID0+IHsgaWYgKCEkKCdhcHAnKS5jbGFzc0xpc3QuY29udGFpbnMoJ2hpZGUnKSAmJiAhJCgnZHJhd2VyJykuY2xhc3NMaXN0LmNvbnRhaW5zKCdvcGVuJykpIGxvYWQoKTsgfSwgMzAwMDApOwo8L3NjcmlwdD48L2JvZHk+PC9odG1sPgo="), (c) => c.charCodeAt(0)));
