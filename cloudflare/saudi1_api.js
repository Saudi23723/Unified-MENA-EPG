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
      return json({ status: "active", server: lists[0].server, user: l.user, pass: l.pass, name: d.name || "", expires: d.expires || 0, playlists: lists, vpn });
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
        const nw = await env.DB.prepare("SELECT code, t, playlist, kind, title FROM now").all();
        const nb = {};
        for (const n of nw.results || []) nb[n.code] = n;
        return json({ devices: (r.results || []).map((d) => ({ ...d, extras: by[d.code] || [], has_vpn: hv.has(d.code), promo: pb[d.code] || "",
          now_t: nb[d.code]?.t || 0, now_playlist: nb[d.code]?.playlist || "", now_kind: nb[d.code]?.kind || "", now_title: nb[d.code]?.title || "",
          country: wb[d.code]?.country || "", city: wb[d.code]?.city || "", on_vpn: !!wb[d.code]?.vpn, place_t: wb[d.code]?.t || 0 })) });
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
const PAGE = new TextDecoder().decode(Uint8Array.from(atob("PCFkb2N0eXBlIGh0bWw+PGh0bWwgbGFuZz0iYXIiIGRpcj0icnRsIj48aGVhZD48bWV0YSBjaGFyc2V0PSJ1dGYtOCI+PG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEiPgo8dGl0bGU+U0FVREkuVFYgwrcg2YTZiNit2Kkg2KfZhNil2K/Yp9ix2Kk8L3RpdGxlPgo8c3R5bGU+Cjpyb290ey0tYmc6IzA5MGMxMjstLXA6IzEyMTcyMjstLXAyOiMxOTIwMmU7LS1wMzojMjIyYjNkOy0tbGluZTojMjMyYzNlOy0tdDojZjJmNGY4Oy0tdDI6IzlhYTNiNTstLXQzOiM2Yjc0ODg7LS1hOiMwMGQ2OGY7LS1hMjojMDBiMzc3Oy0tcjojZmY0ZDVlOy0teTojZmZiMDIwOy0tYjojNGRhM2ZmOy0tc2g6MCAxMHB4IDMwcHggcmdiYSgwLDAsMCwuMzUpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveH1odG1sLGJvZHl7aGVpZ2h0OjEwMCV9CmJvZHl7bWFyZ2luOjA7YmFja2dyb3VuZDpyYWRpYWwtZ3JhZGllbnQoMTIwMHB4IDYwMHB4IGF0IDEwMCUgLTEwJSwjMGYyYTIwIDAsdHJhbnNwYXJlbnQgNjAlKSx2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdCk7Zm9udDoxNXB4LzEuNTUgc3lzdGVtLXVpLC1hcHBsZS1zeXN0ZW0sIlNlZ29lIFVJIixUYWhvbWEsc2Fucy1zZXJpZn0KYXtjb2xvcjppbmhlcml0fS5oaWRle2Rpc3BsYXk6bm9uZSFpbXBvcnRhbnR9Lm11dGVke2NvbG9yOnZhcigtLXQyKX0uY29kZXtmb250LWZhbWlseTp1aS1tb25vc3BhY2UsTWVubG8sbW9ub3NwYWNlO2xldHRlci1zcGFjaW5nOjEuNXB4O2RpcmVjdGlvbjpsdHI7ZGlzcGxheTppbmxpbmUtYmxvY2s7d2hpdGUtc3BhY2U6bm93cmFwfQouc2hlbGx7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoyNDBweCAxZnI7bWluLWhlaWdodDoxMDB2aH0KYXNpZGV7YmFja2dyb3VuZDpyZ2JhKDE4LDIzLDM0LC44NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMTBweCk7Ym9yZGVyLWxlZnQ6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6MjJweCAxNHB4O3Bvc2l0aW9uOnN0aWNreTt0b3A6MDtoZWlnaHQ6MTAwdmg7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4fQouYnJhbmR7Zm9udC1zaXplOjI0cHg7Zm9udC13ZWlnaHQ6ODAwO2xldHRlci1zcGFjaW5nOi41cHg7cGFkZGluZzo0cHggMTBweCAxOHB4O2RpcmVjdGlvbjpsdHI7dGV4dC1hbGlnbjpyaWdodH0uYnJhbmQgYntjb2xvcjp2YXIoLS1hKX0KLm5hdntkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4O3BhZGRpbmc6MTFweCAxMnB4O2JvcmRlci1yYWRpdXM6MTJweDtjb2xvcjp2YXIoLS10Mik7Y3Vyc29yOnBvaW50ZXI7Zm9udC13ZWlnaHQ6NjAwO2JvcmRlcjowO2JhY2tncm91bmQ6bm9uZTt3aWR0aDoxMDAlO3RleHQtYWxpZ246cmlnaHQ7Zm9udC1zaXplOjE1cHh9Ci5uYXY6aG92ZXJ7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCl9Lm5hdi5vbntiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx0cmFuc3BhcmVudCxyZ2JhKDAsMjE0LDE0MywuMTYpKTtjb2xvcjp2YXIoLS10KTtib3gtc2hhZG93Omluc2V0IC0zcHggMCAwIHZhcigtLWEpfQoubmF2IC5pY3t3aWR0aDoyMnB4O3RleHQtYWxpZ246Y2VudGVyfS5zcGFjZXJ7ZmxleDoxfQptYWlue3BhZGRpbmc6MjZweCAzMHB4IDYwcHg7bWF4LXdpZHRoOjEyNDBweDt3aWR0aDoxMDAlfQoudG9we2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjE0cHg7bWFyZ2luLWJvdHRvbToyMnB4O2ZsZXgtd3JhcDp3cmFwfQpoMXttYXJnaW46MDtmb250LXNpemU6MjZweH1oMnttYXJnaW46MCAwIDRweDtmb250LXNpemU6MThweH0uc3Vie2NvbG9yOnZhcigtLXQyKTttYXJnaW46MnB4IDAgMH0KLmJ0bntiYWNrZ3JvdW5kOnZhcigtLWEpO2NvbG9yOiMwMzE0MGM7Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czoxMXB4O3BhZGRpbmc6MTFweCAxOHB4O2ZvbnQtd2VpZ2h0OjgwMDtmb250LXNpemU6MTQuNXB4O2N1cnNvcjpwb2ludGVyO2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo4cHg7dHJhbnNpdGlvbjouMTVzfQouYnRuOmhvdmVye2JhY2tncm91bmQ6dmFyKC0tYTIpfS5idG4uZ2hvc3R7YmFja2dyb3VuZDp2YXIoLS1wMik7Y29sb3I6dmFyKC0tdCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKX0uYnRuLmdob3N0OmhvdmVye2JhY2tncm91bmQ6dmFyKC0tcDMpfQouYnRuLnJlZHtiYWNrZ3JvdW5kOnJnYmEoMjU1LDc3LDk0LC4xNCk7Y29sb3I6dmFyKC0tcik7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDI1NSw3Nyw5NCwuMzUpfS5idG4uc217cGFkZGluZzo3cHggMTJweDtmb250LXNpemU6MTNweDtib3JkZXItcmFkaXVzOjlweH0KLnN0YXRze2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KGF1dG8tZml0LG1pbm1heCgxMzhweCwxZnIpKTtnYXA6MTRweDttYXJnaW4tYm90dG9tOjIycHh9Ci5zdGF0e2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDE4MGRlZyx2YXIoLS1wMiksdmFyKC0tcCkpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNnB4O3BhZGRpbmc6MTZweCAxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpO2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246LjE1c30KLnN0YXQ6aG92ZXJ7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoLTJweCk7Ym9yZGVyLWNvbG9yOiMyZjNhNTJ9Ci5zdGF0IC5ue2ZvbnQtc2l6ZTozMHB4O2ZvbnQtd2VpZ2h0OjgwMDttYXJnaW4tdG9wOjRweH0uc3RhdCAubHtjb2xvcjp2YXIoLS10Mik7Zm9udC1zaXplOjEzcHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6N3B4fQouZG90e3dpZHRoOjlweDtoZWlnaHQ6OXB4O2JvcmRlci1yYWRpdXM6NTAlO2Rpc3BsYXk6aW5saW5lLWJsb2NrfQouY2FyZHtiYWNrZ3JvdW5kOnZhcigtLXApO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxOHB4O2JveC1zaGFkb3c6dmFyKC0tc2gpfQouY2FyZC1oe2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjEycHg7cGFkZGluZzoxNnB4IDE4cHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7ZmxleC13cmFwOndyYXB9Ci50b29sc3tkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5zZWFyY2h7YmFja2dyb3VuZDp2YXIoLS1wMik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjExcHg7cGFkZGluZzo5cHggMTJweDtjb2xvcjp2YXIoLS10KTttaW4td2lkdGg6MjQwcHg7Zm9udC1zaXplOjE0cHh9Ci5jaGlwe2JhY2tncm91bmQ6dmFyKC0tcDIpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Y29sb3I6dmFyKC0tdDIpO2JvcmRlci1yYWRpdXM6OTlweDtwYWRkaW5nOjZweCAxM3B4O2ZvbnQtc2l6ZToxM3B4O2N1cnNvcjpwb2ludGVyO2ZvbnQtd2VpZ2h0OjYwMH0KLmNoaXAub257YmFja2dyb3VuZDpyZ2JhKDAsMjE0LDE0MywuMTQpO2JvcmRlci1jb2xvcjpyZ2JhKDAsMjE0LDE0MywuNSk7Y29sb3I6dmFyKC0tYSl9Ci53cmFwe292ZXJmbG93LXg6YXV0b310YWJsZXt3aWR0aDoxMDAlO2JvcmRlci1jb2xsYXBzZTpjb2xsYXBzZX0KdGgsdGR7dGV4dC1hbGlnbjpyaWdodDtwYWRkaW5nOjEycHggMTRweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1saW5lKTtmb250LXNpemU6MTRweDt2ZXJ0aWNhbC1hbGlnbjptaWRkbGV9CnRoe2NvbG9yOnZhcigtLXQzKTtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2xldHRlci1zcGFjaW5nOi41cHh9CnRib2R5IHRye3RyYW5zaXRpb246LjEycztjdXJzb3I6cG9pbnRlcn10Ym9keSB0cjpob3ZlcntiYWNrZ3JvdW5kOnJnYmEoMjU1LDI1NSwyNTUsLjAyNSl9Ci53aG8gYntkaXNwbGF5OmJsb2NrfS53aG8gc21hbGx7Y29sb3I6dmFyKC0tdDMpfQoudGFne2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo2cHg7cGFkZGluZzozcHggMTBweDtib3JkZXItcmFkaXVzOjk5cHg7Zm9udC1zaXplOjEycHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7bWFyZ2luOjJweCAwIDJweCA0cHg7Zm9udC13ZWlnaHQ6NjAwfQouc3R7ZGlzcGxheTppbmxpbmUtZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjdweDtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjEzcHh9Ci5zLW9ue2NvbG9yOnZhcigtLWEpfS5zLXdhaXR7Y29sb3I6dmFyKC0tYil9LnMtZXhwe2NvbG9yOnZhcigtLXIpfS5zLW9mZntjb2xvcjp2YXIoLS10Myl9LnMtc29vbntjb2xvcjp2YXIoLS15KX0KLm9ubGluZXt3aWR0aDo4cHg7aGVpZ2h0OjhweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZhcigtLWEpO2JveC1zaGFkb3c6MCAwIDAgNHB4IHJnYmEoMCwyMTQsMTQzLC4xOCk7ZGlzcGxheTppbmxpbmUtYmxvY2t9Ci5lbXB0eXtwYWRkaW5nOjQwcHg7dGV4dC1hbGlnbjpjZW50ZXI7Y29sb3I6dmFyKC0tdDIpfQovKiBkcmF3ZXIgKi8KLnNjcmlte3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7YmFja2dyb3VuZDpyZ2JhKDAsMCwwLC41NSk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoMnB4KTt6LWluZGV4OjIwO29wYWNpdHk6MDtwb2ludGVyLWV2ZW50czpub25lO3RyYW5zaXRpb246LjJzfQouc2NyaW0ub3BlbntvcGFjaXR5OjE7cG9pbnRlci1ldmVudHM6YXV0b30KLmRyYXdlcntwb3NpdGlvbjpmaXhlZDt0b3A6MDtib3R0b206MDtsZWZ0OjA7d2lkdGg6bWluKDUyMHB4LDEwMCUpO2JhY2tncm91bmQ6dmFyKC0tcCk7Ym9yZGVyLXJpZ2h0OjFweCBzb2xpZCB2YXIoLS1saW5lKTt6LWluZGV4OjIxO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC0xMDAlKTt0cmFuc2l0aW9uOi4yNXMgY3ViaWMtYmV6aWVyKC4yLC44LC4yLDEpO2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW47Ym94LXNoYWRvdzp2YXIoLS1zaCl9Ci5kcmF3ZXIub3Blbnt0cmFuc2Zvcm06bm9uZX0KLmRoe3BhZGRpbmc6MjBweCAyMnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXJ9Ci5kYntwYWRkaW5nOjZweCAyMnB4IDIycHg7b3ZlcmZsb3c6YXV0bztmbGV4OjF9LmRme3BhZGRpbmc6MTZweCAyMnB4O2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2Rpc3BsYXk6ZmxleDtnYXA6MTBweDtmbGV4LXdyYXA6d3JhcH0KLnNlY3ttYXJnaW4tdG9wOjIwcHg7cGFkZGluZzoxNnB4O2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNHB4O2JhY2tncm91bmQ6dmFyKC0tcDIpfQouc2VjIGgze21hcmdpbjowIDAgNHB4O2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLWEpO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweH0KbGFiZWx7ZGlzcGxheTpibG9jaztjb2xvcjp2YXIoLS10Mik7Zm9udC1zaXplOjEyLjVweDttYXJnaW46MTJweCAwIDVweDtmb250LXdlaWdodDo2MDB9CmlucHV0LHNlbGVjdHt3aWR0aDoxMDAlO2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXQpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxMHB4O3BhZGRpbmc6MTFweCAxMnB4O2ZvbnQtc2l6ZToxNXB4fQppbnB1dDpmb2N1cyxzZWxlY3Q6Zm9jdXN7b3V0bGluZToycHggc29saWQgdmFyKC0tYSk7Ym9yZGVyLWNvbG9yOnRyYW5zcGFyZW50fQouZ3JpZDJ7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDoxMHB4fS5xdWlja3tkaXNwbGF5OmZsZXg7Z2FwOjZweDttYXJnaW4tdG9wOjhweDtmbGV4LXdyYXA6d3JhcH0KLnhse2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47cGFkZGluZzo5cHggMTJweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTBweDttYXJnaW4tdG9wOjhweDtiYWNrZ3JvdW5kOnZhcigtLWJnKX0KLm1zZ3ttaW4taGVpZ2h0OjIycHg7bWFyZ2luLXRvcDoxMHB4O2ZvbnQtd2VpZ2h0OjYwMH0ub2t7Y29sb3I6dmFyKC0tYSl9LmJhZHtjb2xvcjp2YXIoLS1yKX0KLnN3aXRjaHtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO21hcmdpbi10b3A6MTJweH0KLnRne3Bvc2l0aW9uOnJlbGF0aXZlO3dpZHRoOjQ2cHg7aGVpZ2h0OjI2cHg7YmFja2dyb3VuZDp2YXIoLS1wMyk7Ym9yZGVyLXJhZGl1czo5OXB4O2N1cnNvcjpwb2ludGVyO3RyYW5zaXRpb246LjJzO2JvcmRlcjowfQoudGc6OmFmdGVye2NvbnRlbnQ6IiI7cG9zaXRpb246YWJzb2x1dGU7dG9wOjNweDtyaWdodDozcHg7d2lkdGg6MjBweDtoZWlnaHQ6MjBweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOiNmZmY7dHJhbnNpdGlvbjouMnN9Ci50Zy5vbntiYWNrZ3JvdW5kOnZhcigtLWEpfS50Zy5vbjo6YWZ0ZXJ7cmlnaHQ6MjNweH0KLmxvZ2lue21heC13aWR0aDo0MjBweDttYXJnaW46MTJ2aCBhdXRvO3BhZGRpbmc6MjhweH0KLnRvYXN0e3Bvc2l0aW9uOmZpeGVkO2JvdHRvbToyMnB4O2xlZnQ6NTAlO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC01MCUpIHRyYW5zbGF0ZVkoMzBweCk7YmFja2dyb3VuZDp2YXIoLS1wMyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtwYWRkaW5nOjEycHggMThweDtib3JkZXItcmFkaXVzOjEycHg7b3BhY2l0eTowO3RyYW5zaXRpb246LjI1czt6LWluZGV4OjQwO2ZvbnQtd2VpZ2h0OjYwMH0KLnRvYXN0LnNob3d7b3BhY2l0eToxO3RyYW5zZm9ybTp0cmFuc2xhdGVYKC01MCUpfQouaGVscHtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdChhdXRvLWZpdCxtaW5tYXgoMjYwcHgsMWZyKSk7Z2FwOjE0cHh9Ci5oZWxwIC5jYXJke3BhZGRpbmc6MThweH0uaGVscCBvbHttYXJnaW46OHB4IDAgMDtwYWRkaW5nLWlubGluZS1zdGFydDoyMHB4O2NvbG9yOnZhcigtLXQyKX0KLnBpbGx7Zm9udC1zaXplOjExcHg7cGFkZGluZzoycHggOHB4O2JvcmRlci1yYWRpdXM6OTlweDtiYWNrZ3JvdW5kOnZhcigtLXAzKTtjb2xvcjp2YXIoLS10Mil9CkBtZWRpYSAobWF4LXdpZHRoOjgyMHB4KXsuc2hlbGx7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmcn1hc2lkZXtwb3NpdGlvbjpzdGF0aWM7aGVpZ2h0OmF1dG87ZmxleC1kaXJlY3Rpb246cm93O292ZXJmbG93LXg6YXV0bztwYWRkaW5nOjEwcHg7Ym9yZGVyOjA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSl9CiAuYnJhbmR7cGFkZGluZzo2cHggMTBweH0ubmF2e3dpZHRoOmF1dG87d2hpdGUtc3BhY2U6bm93cmFwfS5zcGFjZXJ7ZGlzcGxheTpub25lfW1haW57cGFkZGluZzoxOHB4IDE0cHh9LnNlYXJjaHttaW4td2lkdGg6MDtmbGV4OjF9CiAuaGlkZS1te2Rpc3BsYXk6bm9uZX10aCx0ZHtwYWRkaW5nOjEwcHggOHB4fX0KLm5vd29uLC5ub3dvZmZ7ZGlzcGxheTpibG9jazttYXJnaW4tdG9wOjRweDtmb250LXNpemU6MTJweDtsaW5lLWhlaWdodDoxLjU7d2hpdGUtc3BhY2U6bm9ybWFsfS5ub3dvbntjb2xvcjp2YXIoLS1hKX0ubm93b2Zme2NvbG9yOnZhcigtLXQzKX0ud2hlcmV7ZGlzcGxheTpibG9jazttYXJnaW4tdG9wOjJweH0udnBub257Y29sb3I6IzJlOWQ1Yjtmb250LXdlaWdodDo2MDB9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PgoKPGRpdiBpZD0ibG9naW4iIGNsYXNzPSJjYXJkIGxvZ2luIGhpZGUiPgogIDxkaXYgY2xhc3M9ImJyYW5kIiBzdHlsZT0icGFkZGluZzowIDAgMTBweCI+U0FVREk8Yj4uVFY8L2I+PC9kaXY+CiAgPGgyIGlkPSJsdCI+2K/YrtmI2YQg2YTZiNit2Kkg2KfZhNil2K/Yp9ix2Kk8L2gyPjxwIGlkPSJsaCIgY2xhc3M9Im11dGVkIj48L3A+CiAgPGxhYmVsPtmD2YTZhdipINin2YTYs9ixPC9sYWJlbD48aW5wdXQgaWQ9InB3IiB0eXBlPSJwYXNzd29yZCIgYXV0b2NvbXBsZXRlPSJjdXJyZW50LXBhc3N3b3JkIj4KICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjE2cHgiPjxidXR0b24gaWQ9ImdvIiBjbGFzcz0iYnRuIiBzdHlsZT0id2lkdGg6MTAwJTtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyIj7Yr9iu2YjZhDwvYnV0dG9uPjwvZGl2PjxkaXYgaWQ9ImxtIiBjbGFzcz0ibXNnIGJhZCI+PC9kaXY+CjwvZGl2PgoKPGRpdiBpZD0iYXBwIiBjbGFzcz0ic2hlbGwgaGlkZSI+CiAgPGFzaWRlPgogICAgPGRpdiBjbGFzcz0iYnJhbmQiPlNBVURJPGI+LlRWPC9iPjwvZGl2PgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IG9uIiBkYXRhLXY9ImRhc2giPjxzcGFuIGNsYXNzPSJpYyI+4penPC9zcGFuPiDZhNmI2K3YqSDYp9mE2KrYrdmD2YU8L2J1dHRvbj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgZGF0YS12PSJkZXZzIj48c3BhbiBjbGFzcz0iaWMiPuKWpDwvc3Bhbj4g2KfZhNij2KzZh9iy2Kk8L2J1dHRvbj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgZGF0YS12PSJwcm9tbyI+PHNwYW4gY2xhc3M9ImljIj7wn46fPC9zcGFuPiBQcm9tbyBjb2RlczwvYnV0dG9uPgogICAgPGJ1dHRvbiBjbGFzcz0ibmF2IiBkYXRhLXY9InBheSI+PHNwYW4gY2xhc3M9ImljIj7wn5KzPC9zcGFuPiDYp9mE2K/Zgdi5PC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJuYXYiIGRhdGEtdj0iaGVscCI+PHNwYW4gY2xhc3M9ImljIj4/PC9zcGFuPiDYt9ix2YrZgtipINin2YTYp9iz2KrYrtiv2KfZhTwvYnV0dG9uPgogICAgPGRpdiBjbGFzcz0ic3BhY2VyIj48L2Rpdj4KICAgIDxidXR0b24gY2xhc3M9Im5hdiIgaWQ9Im91dCI+PHNwYW4gY2xhc3M9ImljIj7ijos8L3NwYW4+INiu2LHZiNisPC9idXR0b24+CiAgPC9hc2lkZT4KICA8bWFpbj4KICAgIDxkaXYgY2xhc3M9InRvcCI+CiAgICAgIDxkaXY+PGgxIGlkPSJ2dCI+2YTZiNit2Kkg2KfZhNiq2K3Zg9mFPC9oMT48cCBjbGFzcz0ic3ViIiBpZD0idnMiPtmG2LjYsdipINiz2LHZiti52Kkg2LnZhNmJINmD2YQg2KfZhNij2KzZh9iy2Kk8L3A+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InRvb2xzIj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGlkPSJyZWZyZXNoIj7in7Mg2KrYrdiv2YrYqzwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biIgaWQ9ImFkZCI+77yLINis2YfYp9iyINis2K/ZitivPC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KCiAgICA8c2VjdGlvbiBpZD0idi1kYXNoIj4KICAgICAgPGRpdiBjbGFzcz0ic3RhdHMiIGlkPSJzdGF0cyI+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtaCI+PGgyPtmK2K3Yqtin2Kwg2KfZhtiq2KjYp9mH2YM8L2gyPjxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9ImF0dG4tbiI+PC9zcGFuPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9IndyYXAiPjx0YWJsZT48dGJvZHkgaWQ9ImF0dG4iPjwvdGJvZHk+PC90YWJsZT48L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CgogICAgPHNlY3Rpb24gaWQ9InYtZGV2cyIgY2xhc3M9ImhpZGUiPgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPgogICAgICAgICAgPGRpdiBjbGFzcz0idG9vbHMiIGlkPSJjaGlwcyI+PC9kaXY+CiAgICAgICAgICA8aW5wdXQgY2xhc3M9InNlYXJjaCIgaWQ9InEiIHBsYWNlaG9sZGVyPSLYqNit2Ks6INmD2YjYr9iMINin2LPZhdiMIHBsYXlsaXN04oCmIj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJ3cmFwIj48dGFibGU+CiAgICAgICAgICA8dGhlYWQ+PHRyPjx0aD7Yp9mE2YPZiNivPC90aD48dGg+2KfZhNiy2KjZiNmGPC90aD48dGg+UGxheWxpc3RzPC90aD48dGg+2KfZhNit2KfZhNipPC90aD48dGggY2xhc3M9ImhpZGUtbSI+2KLYrtixINi42YfZiNixPC90aD48dGggY2xhc3M9ImhpZGUtbSI+2YrZhtiq2YfZijwvdGg+PC90cj48L3RoZWFkPgogICAgICAgICAgPHRib2R5IGlkPSJ0YiI+PC90Ym9keT48L3RhYmxlPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBpZD0idi1wcm9tbyIgY2xhc3M9ImhpZGUiPgogICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWgiPjxoMj7Zg9mI2K8g2KzYr9mK2K88L2gyPjxzcGFuIGNsYXNzPSJtdXRlZCIgaWQ9InByb21vLW4iPjwvc3Bhbj48L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJwYWRkaW5nOjE0cHggMThweDtkaXNwbGF5OmZsZXg7Z2FwOjEwcHg7ZmxleC13cmFwOndyYXA7YWxpZ24taXRlbXM6ZW5kIj4KICAgICAgICAgIDxkaXY+PGxhYmVsPtmE2YXZitmG2J8gKNmF2YTYp9it2LjYqSDYpdmE2YMpPC9sYWJlbD48aW5wdXQgaWQ9InBub3RlIiBwbGFjZWhvbGRlcj0i2YXYq9mE2KfZizog2KPYqNmIINij2K3ZhdivIj48L2Rpdj4KICAgICAgICAgIDxkaXY+PGxhYmVsPtin2YTYudiv2K88L2xhYmVsPjxzZWxlY3QgaWQ9InBjb3VudCI+PG9wdGlvbj4xPC9vcHRpb24+PG9wdGlvbj4zPC9vcHRpb24+PG9wdGlvbj41PC9vcHRpb24+PG9wdGlvbj4xMDwvb3B0aW9uPjwvc2VsZWN0PjwvZGl2PgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0icGdlbiI+77yLINij2LXYr9ixPC9idXR0b24+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0id3JhcCI+PHRhYmxlPgogICAgICAgICAgPHRoZWFkPjx0cj48dGg+2KfZhNmD2YjYrzwvdGg+PHRoPtmE2YXZitmGPC90aD48dGg+2KfZhNit2KfZhNipPC90aD48dGg+PC90aD48L3RyPjwvdGhlYWQ+CiAgICAgICAgICA8dGJvZHkgaWQ9InB0YiI+PC90Ym9keT48L3RhYmxlPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBpZD0idi1wYXkiIGNsYXNzPSJoaWRlIj4KICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1oIj48aDI+2KfZhNiv2YHYuSDYr9in2K7ZhCDYp9mE2KrYt9io2YrZgjwvaDI+PHNwYW4gY2xhc3M9Im11dGVkIiBpZD0icGF5LXN0Ij48L3NwYW4+PC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0icGFkZGluZzoxNHB4IDE4cHg7bWF4LXdpZHRoOjY0MHB4Ij4KICAgICAgICAgIDxwIGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxMy41cHg7bGluZS1oZWlnaHQ6MS44Ij7Yp9mE2YTZiiDZhdinINi52YbYr9mHIFByb21vIGNvZGUg2KjZiti02YjZgSDYudmE2Ykg2LTYp9i02Kkg2KfZhNiq2YHYudmK2YQg2LLYsSDCq0J1eSBhY2Nlc3PCuyDZhdi5IFFSLiDYqNmK2YHYqtitINmF2YYg2KrZhNmB2YjZhtmHINi12YHYrdipINmB2YrZh9inINmD2YjYryDYrNmH2KfYstmHINmI2KfZhNiz2LnYsSDZiNiy2LEgPGI+UGF5IHdpdGggVmVubW88L2I+2Iwg2YjYp9mE2YXYqNmE2Log2YjYp9mE2YXZhNin2K3YuNipICjZg9mI2K8g2KfZhNis2YfYp9iyKSDZhdi52KjZkdmK2YrZhiDZhNit2KfZhNmH2YUuINmE2YXYpyDYqtmI2LXZhNmDINin2YTYr9mB2LnYqSDYudmE2YkgVmVubW/YjCDYp9mE2YXZhNin2K3YuNipINmB2YrZh9inINmD2YjYryDYp9mE2KzZh9in2LI6INmB2LnZkdmE2Ycg2YXZhiDCq9in2YTYo9is2YfYstipwrsg2LLZiiDYp9mE2LnYp9iv2KkuPC9wPgogICAgICAgICAgPGxhYmVsPtin2YTYs9i52LEg2KfZhNmE2Yog2KjZiti42YfYsSDZhNmE2LLYqNmI2YYgKNix2YLZhSDYqNin2YTYr9mI2YTYp9ixKTwvbGFiZWw+PGlucHV0IGlkPSJwYXktcHJpY2UiIHBsYWNlaG9sZGVyPSIyNTAiIHN0eWxlPSJkaXJlY3Rpb246bHRyO3RleHQtYWxpZ246bGVmdCI+CiAgICAgICAgICA8bGFiZWw+2KfYs9mFINin2YTZhdiz2KrYrtiv2YUg2LnZhNmJIFZlbm1vICjYqNiv2YjZhiBAKTwvbGFiZWw+PGlucHV0IGlkPSJwYXktbGluayIgcGxhY2Vob2xkZXI9IlNhaWYtU2F1ZGkiIHN0eWxlPSJkaXJlY3Rpb246bHRyO3RleHQtYWxpZ246bGVmdCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzd2l0Y2giPjxzcGFuPtin2YTYr9mB2Lkg2LTYutmR2KfZhDwvc3Bhbj48YnV0dG9uIGNsYXNzPSJ0ZyIgaWQ9InBheS1vbiIgdHlwZT0iYnV0dG9uIj48L2J1dHRvbj48L2Rpdj4KICAgICAgICAgIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+PGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0icGF5LXNhdmUiPtit2YHYuDwvYnV0dG9uPiA8c3BhbiBjbGFzcz0ibXV0ZWQiIGlkPSJwYXktbXNnIj48L3NwYW4+PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgoKICAgIDxzZWN0aW9uIGlkPSJ2LWhlbHAiIGNsYXNzPSJoaWRlIj4KICAgICAgPGRpdiBjbGFzcz0iaGVscCI+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+PGgyPtiy2KjZiNmGINis2K/ZitivPC9oMj48b2w+PGxpPtin2YTYstio2YjZhiDZitmG2LLZkdmEIFNBVURJLlRWINmF2YYgRG93bmxvYWRlciDZiNmK2YHYqtit2YcuPC9saT48bGk+2KjZiti32YTYuSDYudmE2Ykg2LTYp9i02KrZhyDZg9mI2K8g2YXZhiA4INij2LHZgtin2YUuPC9saT48bGk+2YfZiNmGOiDvvIsg2KzZh9in2LIg2KzYr9mK2K8g4oaQINin2YPYqtioINin2YTZg9mI2K8g2YjYp9mE2KfYs9mFINmI2KfZhNmAIHBsYXlsaXN0INmI2KfZhNmK2YjYstixLjwvbGk+PGxpPtin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQg4oCUINiu2YTYtS48L2xpPjwvb2w+PC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+PGgyPtij2YPYq9ixINmF2YYgcGxheWxpc3Q8L2gyPjxvbD48bGk+2KfZgdiq2K0g2KfZhNis2YfYp9iyIOKGkCDZgtiz2YUgwqtQbGF5bGlzdHMg2KXYttin2YHZitipwrsuPC9saT48bGk+2KfYrtiq2KfYsSDYp9mE2YAgcGxheWxpc3Qg2YjYp9mD2KrYqCDYp9mE2YrZiNiy2LEg2YjYp9mE2KjYp9iz2YjZiNix2K8g4oaQINij2LbZgS48L2xpPjxsaT7Yp9mE2LLYqNmI2YYg2KjZitiu2KrYp9ixINio2YrZhtmH2YUg2YXZhiDCq1BsYXlsaXN0c8K7INio2KfZhNiq2LfYqNmK2YIuPC9saT48L29sPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxoMj7Yqtis2K/ZitivINmI2KXZitmC2KfZgTwvaDI+PG9sPjxsaT7Yp9mB2KrYrSDYp9mE2KzZh9in2LIg4oaQINij2LLYsdin2LEgKzMwIC8gKzkwIC8gKzM2NSDZitmI2YUuPC9saT48bGk+wqvYp9mE2KzZh9in2LIg2LTYutmR2KfZhMK7INiq2LfZgdmK2Ycg2KjZitmI2YLZgSDYp9mE2K7Yr9mF2Kkg2YHZiNix2KfZiyDYudmG2K8g2KfZhNiy2KjZiNmGLjwvbGk+PGxpPtin2YTYo9is2YfYstipINin2YTZhNmKINio2KrZhtiq2YfZiiDYrtmE2KfZhCA3INij2YrYp9mFINio2KrYt9mE2Lkg2KjYp9mE2KPYtdmB2LEuPC9saT48L29sPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxoMj7Yp9mE2KPZhdin2YY8L2gyPjxvbD48bGk+2KfZhNmK2YjYstixINmI2KfZhNio2KfYs9mI2YjYsdivINmF2K3ZgdmI2LjZitmGINmF2LTZgdmR2LHZitmGLjwvbGk+PGxpPtin2YTYqNin2LPZiNmI2LHYryDZhdinINio2YrYsdis2Lkg2YrYuNmH2LEg2YfZiNmGINij2KjYr9in2Ysg4oCUINin2KrYsdmD2Ycg2YHYp9i22Yog2YTZitio2YLZiSDYp9mE2YLYr9mK2YUuPC9saT48bGk+2LHYp9io2Lcg2KfZhNiq2LfYqNmK2YI6IDxzcGFuIGNsYXNzPSJjb2RlIj5zYXVkaTEuMXNhaWZzYXVkaS53b3JrZXJzLmRldi9hcGs8L3NwYW4+PC9saT48L29sPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KICA8L21haW4+CjwvZGl2PgoKPGRpdiBjbGFzcz0ic2NyaW0iIGlkPSJzY3JpbSI+PC9kaXY+CjxkaXYgY2xhc3M9ImRyYXdlciIgaWQ9ImRyYXdlciI+CiAgPGRpdiBjbGFzcz0iZGgiPjxkaXY+PGgyIGlkPSJkdCI+2KzZh9in2LIg2KzYr9mK2K88L2gyPjxkaXYgY2xhc3M9Im11dGVkIiBpZD0iZHN1YiI+PC9kaXY+PC9kaXY+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBpZD0iZHgiPuKclTwvYnV0dG9uPjwvZGl2PgogIDxkaXYgY2xhc3M9ImRiIj4KICAgIDxkaXYgY2xhc3M9InNlYyI+CiAgICAgIDxoMz7ikaAg2KfZhNis2YfYp9iyINmI2KfZhNiy2KjZiNmGPC9oMz4KICAgICAgPGxhYmVsPtmD2YjYryDYp9mE2KzZh9in2LIgKDgg2KPYsdmC2KfZhSDZhdmGINi02KfYtNipINin2YTYstio2YjZhik8L2xhYmVsPjxpbnB1dCBpZD0iY29kZSIgaW5wdXRtb2RlPSJudW1lcmljIiBtYXhsZW5ndGg9IjkiIHBsYWNlaG9sZGVyPSIxMjM0IDU2NzgiIGNsYXNzPSJjb2RlIiBzdHlsZT0idGV4dC1hbGlnbjpyaWdodCI+CiAgICAgIDxsYWJlbD7Yp9iz2YUg2KfZhNiy2KjZiNmGPC9sYWJlbD48aW5wdXQgaWQ9Im5hbWUiIHBsYWNlaG9sZGVyPSLZhdir2YTYp9mLOiDYo9io2Ygg2KPYrdmF2K8iPgogICAgICA8ZGl2IGNsYXNzPSJzd2l0Y2giPjxzcGFuPtin2YTYrNmH2KfYsiDYtNi62ZHYp9mEPC9zcGFuPjxidXR0b24gY2xhc3M9InRnIG9uIiBpZD0iYWN0IiB0eXBlPSJidXR0b24iPjwvYnV0dG9uPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzZWMiPgogICAgICA8aDM+4pGhINin2YTZgCBQbGF5bGlzdCDYp9mE2KPYs9in2LPZitipPC9oMz4KICAgICAgPGxhYmVsPlBsYXlsaXN0PC9sYWJlbD48c2VsZWN0IGlkPSJwbCI+PC9zZWxlY3Q+CiAgICAgIDxkaXYgY2xhc3M9ImdyaWQyIj4KICAgICAgICA8ZGl2PjxsYWJlbD7Yp9mE2YrZiNiy2LE8L2xhYmVsPjxpbnB1dCBpZD0idSIgYXV0b2NvbXBsZXRlPSJvZmYiPjwvZGl2PgogICAgICAgIDxkaXY+PGxhYmVsPtin2YTYqNin2LPZiNmI2LHYrzwvbGFiZWw+PGlucHV0IGlkPSJwIiB0eXBlPSJwYXNzd29yZCIgYXV0b2NvbXBsZXRlPSJuZXctcGFzc3dvcmQiPjwvZGl2PgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ibXV0ZWQiIGlkPSJsaGludCIgc3R5bGU9ImZvbnQtc2l6ZToxMi41cHg7bWFyZ2luLXRvcDo2cHgiPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzZWMiPgogICAgICA8aDM+4pGiINin2YTYp9i02KrYsdin2YM8L2gzPgogICAgICA8bGFiZWw+2YrZhtiq2YfZiiDYqNiq2KfYsdmK2K4gKNmB2KfYttmKID0g2KjYr9mI2YYg2KfZhtiq2YfYp9ihKTwvbGFiZWw+PGlucHV0IGlkPSJleCIgdHlwZT0iZGF0ZSI+CiAgICAgIDxkaXYgY2xhc3M9InF1aWNrIj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtYWRkPSIzMCI+KzMwINmK2YjZhTwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjkwIj4rOTAg2YrZiNmFPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IHNtIiBkYXRhLWFkZD0iMTgwIj4rNiDYtNmH2YjYsTwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjM2NSI+K9iz2YbYqTwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgZGF0YS1hZGQ9IjAiPtio2K/ZiNmGINin2YbYqtmH2KfYoTwvYnV0dG9uPjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzZWMiIGlkPSJ4c2VjIj4KICAgICAgPGgzPuKRoyBQbGF5bGlzdHMg2KXYttin2YHZitipPC9oMz4KICAgICAgPGRpdiBpZD0ieGxpc3QiPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJncmlkMiIgc3R5bGU9Im1hcmdpbi10b3A6NnB4Ij48ZGl2PjxsYWJlbD5QbGF5bGlzdDwvbGFiZWw+PHNlbGVjdCBpZD0ieHBsIj48L3NlbGVjdD48L2Rpdj48ZGl2PjwvZGl2PgogICAgICAgIDxkaXY+PGxhYmVsPtin2YTZitmI2LLYsTwvbGFiZWw+PGlucHV0IGlkPSJ4dSIgYXV0b2NvbXBsZXRlPSJvZmYiPjwvZGl2PjxkaXY+PGxhYmVsPtin2YTYqNin2LPZiNmI2LHYrzwvbGFiZWw+PGlucHV0IGlkPSJ4cCIgdHlwZT0icGFzc3dvcmQiIGF1dG9jb21wbGV0ZT0ibmV3LXBhc3N3b3JkIj48L2Rpdj48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0ibWFyZ2luLXRvcDoxMHB4Ij48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGlkPSJ4YWRkIj7vvIsg2KPYttmBIHBsYXlsaXN0PC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNlYyIgaWQ9InZzZWMiPgogICAgICA8aDM+4pGkIFZQTjwvaDM+CiAgICAgIDxkaXYgY2xhc3M9Im11dGVkIiBzdHlsZT0iZm9udC1zaXplOjEyLjVweCI+VlBOINiz2YrYsdmB2LHZhtinINin2YTYrtin2LUgKNij2YXYsdmK2YPYpyDCtyDZhdis2KfZhtmKKS4g2KfZhNmF2LTYqtix2YMg2YrYt9mE2Lkg2YPYo9mG2Ycg2YHZiiDYo9mF2LHZitmD2KcuIDxzcGFuIGlkPSJ2cG9vbCI+PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGlkPSJ2c3RhdGUiIHN0eWxlPSJtYXJnaW4tdG9wOjhweDtmb250LXdlaWdodDo2MDAiPjwvZGl2PgogICAgICA8ZGV0YWlscyBzdHlsZT0ibWFyZ2luLXRvcDo4cHgiPjxzdW1tYXJ5IGNsYXNzPSJtdXRlZCIgc3R5bGU9ImN1cnNvcjpwb2ludGVyO2ZvbnQtc2l6ZToxMi41cHgiPtmF2YTZgSDZhdmGINmF2LLZiNmR2K8g2KvYp9mG2YogKNin2K7YqtmK2KfYsdmKKTwvc3VtbWFyeT4KICAgICAgPHRleHRhcmVhIGlkPSJ2Y29uZiIgcm93cz0iNiIgcGxhY2Vob2xkZXI9IltJbnRlcmZhY2VdJiMxMDtQcml2YXRlS2V5ID0g4oCmJiMxMDtBZGRyZXNzID0g4oCmJiMxMDsmIzEwO1tQZWVyXSYjMTA7UHVibGljS2V5ID0g4oCmJiMxMDtFbmRwb2ludCA9IOKApiIgc3R5bGU9IndpZHRoOjEwMCU7bWFyZ2luLXRvcDo4cHg7YmFja2dyb3VuZDp2YXIoLS1iZyk7Y29sb3I6dmFyKC0tdCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzoxMHB4O2ZvbnQ6MTNweCB1aS1tb25vc3BhY2UsbW9ub3NwYWNlO2RpcmVjdGlvbjpsdHIiPjwvdGV4dGFyZWE+CiAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBzbSIgaWQ9InZzYXZlIiBzdHlsZT0ibWFyZ2luLXRvcDo2cHgiPtit2YHYuCDZh9iw2Kcg2KfZhNmF2YTZgTwvYnV0dG9uPjwvZGV0YWlscz4KICAgICAgPGRpdiBzdHlsZT0ibWFyZ2luLXRvcDoxMHB4O2Rpc3BsYXk6ZmxleDtnYXA6OHB4Ij48YnV0dG9uIGNsYXNzPSJidG4gc20iIGlkPSJ2b24iPvCfm6Eg2LTYutmR2YQgVlBOPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIHJlZCBzbSIgaWQ9InZkZWwiPti02YrZhCDYp9mE2YAgVlBOPC9idXR0b24+PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9Im1zZyIgaWQ9InNtIj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJkZiI+PGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0ic2F2ZSI+2K3Zgdi4PC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBpZD0iY2FuY2VsIj7YpdmE2LrYp9ihPC9idXR0b24+PHNwYW4gY2xhc3M9InNwYWNlciIgc3R5bGU9ImZsZXg6MSI+PC9zcGFuPjxidXR0b24gY2xhc3M9ImJ0biByZWQgaGlkZSIgaWQ9ImRlbCI+2K3YsNmBINin2YTYrNmH2KfYsjwvYnV0dG9uPjwvZGl2Pgo8L2Rpdj4KPGRpdiBjbGFzcz0idG9hc3QiIGlkPSJ0b2FzdCI+PC9kaXY+Cgo8c2NyaXB0Pgpjb25zdCAkID0gKGlkKSA9PiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7CmNvbnN0IGFwaSA9IChwLCBiKSA9PiBmZXRjaCgnL2FkbWluL2FwaS8nICsgcCwgYiA/IHsgbWV0aG9kOiAnUE9TVCcsIGhlYWRlcnM6IHsgJ0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJyB9LCBib2R5OiBKU09OLnN0cmluZ2lmeShiKSwgY3JlZGVudGlhbHM6ICdzYW1lLW9yaWdpbicgfSA6IHsgY3JlZGVudGlhbHM6ICdzYW1lLW9yaWdpbicgfSkKICAudGhlbihhc3luYyAocikgPT4gKHsgb2s6IHIub2ssIC4uLihhd2FpdCByLmpzb24oKS5jYXRjaCgoKSA9PiAoe30pKSkgfSkpOwpjb25zdCBlc2MgPSAocykgPT4gU3RyaW5nKHMgPz8gJycpLnJlcGxhY2UoL1smPD4iJ10vZywgKGMpID0+ICh7ICcmJzogJyZhbXA7JywgJzwnOiAnJmx0OycsICc+JzogJyZndDsnLCAnIic6ICcmcXVvdDsnLCAiJyI6ICcmIzM5OycgfVtjXSkpOwpjb25zdCBEQVkgPSA4NjQwMDAwMDsKY29uc3QgYWdvID0gKHQpID0+IHsgaWYgKCF0KSByZXR1cm4gJ+KAlCc7IGNvbnN0IG0gPSBNYXRoLnJvdW5kKChEYXRlLm5vdygpIC0gdCkgLyA2MDAwMCk7IHJldHVybiBtIDwgMSA/ICfYp9mE2KLZhicgOiBtIDwgNjAgPyBgJHttfSDYr9mC2YrZgtipYCA6IG0gPCAxNDQwID8gYCR7TWF0aC5yb3VuZChtIC8gNjApfSDYs9in2LnYqWAgOiBgJHtNYXRoLnJvdW5kKG0gLyAxNDQwKX0g2YrZiNmFYDsgfTsKY29uc3QgZGF5ID0gKHQpID0+IHQgPyBuZXcgRGF0ZSh0KS50b0lTT1N0cmluZygpLnNsaWNlKDAsIDEwKSA6ICcnOwpjb25zdCBwcmV0dHkgPSAoYykgPT4gYy5yZXBsYWNlKC8oXGR7NH0pKFxkezR9KS8sICckMSAkMicpOwpsZXQgZGV2cyA9IFtdLCBwbGF5bGlzdHMgPSBbXSwgZmlsdGVyID0gJ2FsbCcsIGVkaXRpbmcgPSBudWxsOwoKZnVuY3Rpb24gdG9hc3QodCkgeyBjb25zdCBlID0gJCgndG9hc3QnKTsgZS50ZXh0Q29udGVudCA9IHQ7IGUuY2xhc3NMaXN0LmFkZCgnc2hvdycpOyBjbGVhclRpbWVvdXQoZS5fdCk7IGUuX3QgPSBzZXRUaW1lb3V0KCgpID0+IGUuY2xhc3NMaXN0LnJlbW92ZSgnc2hvdycpLCAyNjAwKTsgfQoKZnVuY3Rpb24gc3RhdGUoZCkgewogIGNvbnN0IG5vdyA9IERhdGUubm93KCk7CiAgaWYgKCFkLmFjdGl2ZSkgcmV0dXJuIHsgazogJ29mZicsIHQ6ICfZhdmI2YLZiNmBJyB9OwogIGlmIChkLmV4cGlyZXMgJiYgZC5leHBpcmVzIDwgbm93KSByZXR1cm4geyBrOiAnZXhwJywgdDogJ9mF2YbYqtmH2YonIH07CiAgaWYgKCFkLmhhc19sb2dpbiB8fCAhZC5wbGF5bGlzdCkgcmV0dXJuIHsgazogJ3dhaXQnLCB0OiAn2KjYp9mG2KrYuNin2LEg2KfZhNiq2YHYudmK2YQnIH07CiAgaWYgKGQuZXhwaXJlcyAmJiBkLmV4cGlyZXMgLSBub3cgPCA3ICogREFZKSByZXR1cm4geyBrOiAnc29vbicsIHQ6IGDZitmG2KrZh9mKINiu2YTYp9mEICR7TWF0aC5tYXgoMSwgTWF0aC5jZWlsKChkLmV4cGlyZXMgLSBub3cpIC8gREFZKSl9INmK2YjZhWAgfTsKICByZXR1cm4geyBrOiAnb24nLCB0OiAn2LTYutmR2KfZhCcgfTsKfQpjb25zdCBpc09ubGluZSA9IChkKSA9PiBkLnNlZW4gJiYgRGF0ZS5ub3coKSAtIGQuc2VlbiA8IDIwICogNjAwMDA7Ci8vIHdoYXQgdGhlIGRldmljZSBpcyB3YXRjaGluZyBub3cgKHRvbGQgYnkgdGhlIGFwcCBldmVyeSAxMDAgcykgb3Igd2F0Y2hlZCBsYXN0CmNvbnN0IEtJTkQgPSB7IGxpdmU6ICfwn5O6JywgbW92aWU6ICfwn46sJywgc2VyaWVzOiAn8J+OnicsIHJlY29yZGluZzogJ+KPuicsIHZpZGVvOiAn4pa2JyB9Owpjb25zdCBpc1dhdGNoaW5nID0gKGQpID0+IGQubm93X3QgJiYgRGF0ZS5ub3coKSAtIGQubm93X3QgPCA0ICogNjAwMDA7Ci8vIHdoZXJlIHRoZSBkZXZpY2UgaXMgbm93LCBmcm9tIGl0cyBpbnRlcm5ldDogZmxhZyArIGNvdW50cnkgKyBjaXR5LCBhbmQg8J+UkiB3aGVuIGl0IGNvbWVzIHRocm91Z2ggb3VyIFZQTgpjb25zdCBmbGFnID0gKGMpID0+IGMgJiYgYy5sZW5ndGggPT09IDIgPyBTdHJpbmcuZnJvbUNvZGVQb2ludCguLi5bLi4uYy50b1VwcGVyQ2FzZSgpXS5tYXAoKHgpID0+IDEyNzM5NyArIHguY2hhckNvZGVBdCgwKSkpIDogJyc7CmZ1bmN0aW9uIHdoZXJlKGQpIHsKICBpZiAoIWQuY291bnRyeSkgcmV0dXJuICcnOwogIGxldCBuID0gZC5jb3VudHJ5OyB0cnkgeyBuID0gbmV3IEludGwuRGlzcGxheU5hbWVzKFsnYXInXSwgeyB0eXBlOiAncmVnaW9uJyB9KS5vZihkLmNvdW50cnkpIHx8IGQuY291bnRyeTsgfSBjYXRjaCAoZSkge30KICBjb25zdCB2ID0gZC5vbl92cG4gPyAnIDxzcGFuIGNsYXNzPSJ2cG5vbiI+8J+UkiDYudio2LEgVlBOICjYp9mE2LPZitix2YHYsSDZgdmKINij2YXYsdmK2YPYpyk8L3NwYW4+JyA6IGQuaGFzX3ZwbiA/ICcgPHNwYW4gY2xhc3M9Im11dGVkIj7CtyBWUE4g2YXZgtmB2YjZhDwvc3Bhbj4nIDogJyc7CiAgcmV0dXJuIGA8c21hbGwgY2xhc3M9IndoZXJlIj7wn5ONICR7ZmxhZyhkLmNvdW50cnkpfSAke2VzYyhuKX0ke2QuY2l0eSA/ICcgwrcgJyArIGVzYyhkLmNpdHkpIDogJyd9JHt2fTwvc21hbGw+YDsKfQpmdW5jdGlvbiB3YXRjaGluZyhkKSB7CiAgaWYgKCFkLm5vd190IHx8ICFkLm5vd190aXRsZSkgcmV0dXJuICcnOwogIGNvbnN0IHdoYXQgPSBgJHtLSU5EW2Qubm93X2tpbmRdIHx8ICfilrYnfSAke2VzYyhkLm5vd190aXRsZSl9JHtkLm5vd19wbGF5bGlzdCA/ICcgPHNwYW4gY2xhc3M9Im11dGVkIj7CtyAnICsgZXNjKGQubm93X3BsYXlsaXN0KSArICc8L3NwYW4+JyA6ICcnfWA7CiAgcmV0dXJuIGlzV2F0Y2hpbmcoZCkgPyBgPHNtYWxsIGNsYXNzPSJub3dvbiI+PHNwYW4gY2xhc3M9Im9ubGluZSI+PC9zcGFuPtmK2LTYp9mH2K8g2KfZhNii2YY6ICR7d2hhdH08L3NtYWxsPmAgOiBgPHNtYWxsIGNsYXNzPSJub3dvZmYiPtii2K7YsSDZhdi02KfZh9iv2KkgKNmC2KjZhCAke2FnbyhkLm5vd190KX0pOiAke3doYXR9PC9zbWFsbD5gOwp9Cgphc3luYyBmdW5jdGlvbiBpbml0KCkgewogIGNvbnN0IHMgPSBhd2FpdCBhcGkoJ3N0YXRlJyk7CiAgcGxheWxpc3RzID0gcy5wbGF5bGlzdHMgfHwgW107CiAgY29uc3Qgb3B0cyA9IHBsYXlsaXN0cy5tYXAoKHApID0+IGA8b3B0aW9uIHZhbHVlPSIke2VzYyhwKX0iPiR7ZXNjKHApfTwvb3B0aW9uPmApLmpvaW4oJycpOwogICQoJ3BsJykuaW5uZXJIVE1MID0gb3B0czsgJCgneHBsJykuaW5uZXJIVE1MID0gb3B0czsKICBpZiAocy5zaWduZWQpIHJldHVybiBzaG93KCk7CiAgJCgnbG9naW4nKS5jbGFzc0xpc3QucmVtb3ZlKCdoaWRlJyk7CiAgaWYgKHMuc2V0dXApIHsgJCgnbHQnKS50ZXh0Q29udGVudCA9ICfYo9mI2YQg2YXYsdipOiDYp9iu2KrYp9ixINmD2YTZhdipINiz2LEg2YTZhNil2K/Yp9ix2KknOyAkKCdsaCcpLnRleHRDb250ZW50ID0gJzgg2KPYrdix2YEg2LnZhNmJINin2YTYo9mC2YQuINmH2KfZiiDYp9mE2YPZhNmF2Kkg2KjYqtiv2K7ZhNmDINi52YTZiSDYp9mE2YXZiNmC2Lkg2YXZhiDYo9mKINis2YfYp9iyLic7ICQoJ3B3JykuYXV0b2NvbXBsZXRlID0gJ25ldy1wYXNzd29yZCc7IH0KICAkKCdwdycpLmZvY3VzKCk7Cn0KJCgnZ28nKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ2xvZ2luJywgeyBwYXNzd29yZDogJCgncHcnKS52YWx1ZSwgc2V0dXA6IG5ldyBVUkxTZWFyY2hQYXJhbXMobG9jYXRpb24uc2VhcmNoKS5nZXQoJ3NldHVwJykgfHwgJycgfSk7CiAgaWYgKHIub2spIHsgJCgncHcnKS52YWx1ZSA9ICcnOyBzaG93KCk7IH0gZWxzZSAkKCdsbScpLnRleHRDb250ZW50ID0gci5lcnJvciB8fCAn2K7Yt9ijJzsKfTsKJCgncHcnKS5vbmtleWRvd24gPSAoZSkgPT4geyBpZiAoZS5rZXkgPT09ICdFbnRlcicpICQoJ2dvJykuY2xpY2soKTsgfTsKJCgnb3V0Jykub25jbGljayA9IGFzeW5jICgpID0+IHsgYXdhaXQgYXBpKCdsb2dvdXQnLCB7fSk7IGxvY2F0aW9uLnJlbG9hZCgpOyB9OwoKZnVuY3Rpb24gc2hvdygpIHsgJCgnbG9naW4nKS5jbGFzc0xpc3QuYWRkKCdoaWRlJyk7ICQoJ2FwcCcpLmNsYXNzTGlzdC5yZW1vdmUoJ2hpZGUnKTsgbG9hZCgpOyB9Cgpjb25zdCBWSUVXUyA9IHsgZGFzaDogWyfZhNmI2K3YqSDYp9mE2KrYrdmD2YUnLCAn2YbYuNix2Kkg2LPYsdmK2LnYqSDYudmE2Ykg2YPZhCDYp9mE2KPYrNmH2LLYqSddLCBkZXZzOiBbJ9in2YTYo9is2YfYstipJywgJ9mD2YQg2KfZhNiy2KjYp9mK2YYg4oCUINin2LbYuti3INi52YTZiSDYo9mKINis2YfYp9iyINmE2KrYudiv2YrZhNmHJ10sIHByb21vOiBbJ1Byb21vIGNvZGVzJywgJ9mD2YQg2YPZiNivINio2YrYtNiq2LrZhCDZhdix2Kkg2YjYrdiv2Kkg2LnZhNmJINis2YfYp9iyINmI2KfYrdivJ10sIHBheTogWyfYp9mE2K/Zgdi5JywgJ9in2YTZhNmKINio2LHYpyDYp9mE2K/Yp9im2LHYqSDYqNmK2K/Zgdi5IOKAlCDZiNin2YTZhNmKINis2YjZkdin2YfYpyDYqNmK2KfYrtivIFByb21vIGNvZGUnXSwgaGVscDogWyfYt9ix2YrZgtipINin2YTYp9iz2KrYrtiv2KfZhScsICfYrti32YjYp9iqINiz2LHZiti52KknXSB9OwpmdW5jdGlvbiB2aWV3KHYpIHsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcubmF2W2RhdGEtdl0nKS5mb3JFYWNoKChuKSA9PiBuLmNsYXNzTGlzdC50b2dnbGUoJ29uJywgbi5kYXRhc2V0LnYgPT09IHYpKTsKICBPYmplY3Qua2V5cyhWSUVXUykuZm9yRWFjaCgoaykgPT4gJCgndi0nICsgaykuY2xhc3NMaXN0LnRvZ2dsZSgnaGlkZScsIGsgIT09IHYpKTsKICAkKCd2dCcpLnRleHRDb250ZW50ID0gVklFV1Nbdl1bMF07ICQoJ3ZzJykudGV4dENvbnRlbnQgPSBWSUVXU1t2XVsxXTsKICBpZiAodiA9PT0gJ3Byb21vJykgbG9hZFByb21vcygpOwogIGlmICh2ID09PSAncGF5JykgbG9hZFBheSgpOwp9Ci8vIC0tLS0tLS0tLS0gcGF5bWVudCAtLS0tLS0tLS0tCmFzeW5jIGZ1bmN0aW9uIGxvYWRQYXkoKSB7CiAgY29uc3QgciA9IGF3YWl0IGFwaSgncGF5Jyk7CiAgJCgncGF5LXByaWNlJykudmFsdWUgPSByLnByaWNlIHx8ICcnOyAkKCdwYXktbGluaycpLnZhbHVlID0gci5saW5rIHx8ICcnOyAkKCdwYXktb24nKS5jbGFzc0xpc3QudG9nZ2xlKCdvbicsICEhci5vbik7CiAgJCgncGF5LXN0JykudGV4dENvbnRlbnQgPSAoci5vbiA/ICfYtNi62ZHYp9mEJyA6ICfZhdi32YHZiicpICsgKHIubGluayA/ICcgwrcgVmVubW8gQCcgKyByLmxpbmsucmVwbGFjZSgvXkAvLCAnJykgOiAnJyk7Cn0KJCgncGF5LW9uJykub25jbGljayA9ICgpID0+ICQoJ3BheS1vbicpLmNsYXNzTGlzdC50b2dnbGUoJ29uJyk7CiQoJ3BheS1zYXZlJykub25jbGljayA9IGFzeW5jICgpID0+IHsKICBjb25zdCByID0gYXdhaXQgYXBpKCdwYXknLCB7IHByaWNlOiAkKCdwYXktcHJpY2UnKS52YWx1ZS50cmltKCksIGxpbms6ICQoJ3BheS1saW5rJykudmFsdWUudHJpbSgpLCBvbjogJCgncGF5LW9uJykuY2xhc3NMaXN0LmNvbnRhaW5zKCdvbicpIH0pOwogICQoJ3BheS1tc2cnKS50ZXh0Q29udGVudCA9IHIub2sgPyAn2KfZhtit2YHYuCDinJMnIDogKHIuZXJyb3IgfHwgJ9iu2LfYoycpOyBsb2FkUGF5KCk7Cn07Ci8vIC0tLS0tLS0tLS0gcHJvbW8gY29kZXM6IG9uZSB1c2UsIG9uZSBkZXZpY2UgLS0tLS0tLS0tLQpjb25zdCBwY29kZSA9IChjKSA9PiBjLnJlcGxhY2UoLyguezR9KSguezR9KS8sICckMS0kMicpOwphc3luYyBmdW5jdGlvbiBsb2FkUHJvbW9zKCkgewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3Byb21vcycpOyBjb25zdCBsaXN0ID0gci5wcm9tb3MgfHwgW107CiAgY29uc3QgZnJlZSA9IGxpc3QuZmlsdGVyKChwKSA9PiAhcC51c2VkX2J5KS5sZW5ndGg7CiAgJCgncHJvbW8tbicpLnRleHRDb250ZW50ID0gYCR7ZnJlZX0g2KzYp9mH2LIgwrcgJHtsaXN0Lmxlbmd0aCAtIGZyZWV9INmF2LPYqti52YXZhGA7CiAgJCgncHRiJykuaW5uZXJIVE1MID0gbGlzdC5sZW5ndGggPyBsaXN0Lm1hcCgocCkgPT4gewogICAgY29uc3QgZCA9IHAudXNlZF9ieSA/IGRldnMuZmluZCgoeCkgPT4geC5jb2RlID09PSBwLnVzZWRfYnkpIDogbnVsbDsKICAgIGNvbnN0IHN0ID0gcC51c2VkX2J5ID8gYDxzcGFuIGNsYXNzPSJzdCBzLW9mZiI+2YXYs9iq2LnZhdmEIMK3ICR7ZXNjKGQ/Lm5hbWUgfHwgcHJldHR5KHAudXNlZF9ieSkpfSDCtyDZgtio2YQgJHthZ28ocC51c2VkX2F0KX08L3NwYW4+YCA6ICc8c3BhbiBjbGFzcz0ic3Qgcy1vbiI+2KzYp9mH2LI8L3NwYW4+JzsKICAgIHJldHVybiBgPHRyPjx0ZD48c3BhbiBjbGFzcz0iY29kZSI+JHtlc2MocGNvZGUocC5jb2RlKSl9PC9zcGFuPjwvdGQ+PHRkPiR7ZXNjKHAubm90ZSB8fCAnJyl9PC90ZD48dGQ+JHtzdH08L3RkPgogICAgICA8dGQgc3R5bGU9InRleHQtYWxpZ246bGVmdCI+JHtwLnVzZWRfYnkgPyAnJyA6IGA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qgc20iIGRhdGEtY3A9IiR7ZXNjKHBjb2RlKHAuY29kZSkpfSI+2YbYs9iuPC9idXR0b24+IGB9PGJ1dHRvbiBjbGFzcz0iYnRuIHJlZCBzbSIgZGF0YS1wZD0iJHtlc2MocC5jb2RlKX0iPtit2LDZgTwvYnV0dG9uPjwvdGQ+PC90cj5gOwogIH0pLmpvaW4oJycpIDogJzx0cj48dGQgY29sc3Bhbj0iNCIgY2xhc3M9ImVtcHR5Ij7ZhdinINmB2Yog2KPZg9mI2KfYryDigJQg2KPYtdiv2LEg2KPZiNmEINmD2YjYryDZhdmGINmB2YjZgjwvdGQ+PC90cj4nOwogICQoJ3B0YicpLnF1ZXJ5U2VsZWN0b3JBbGwoJ1tkYXRhLWNwXScpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9ICgpID0+IHsgbmF2aWdhdG9yLmNsaXBib2FyZD8ud3JpdGVUZXh0KGIuZGF0YXNldC5jcCk7IHRvYXN0KCfYp9mG2KrYs9iuOiAnICsgYi5kYXRhc2V0LmNwKTsgfSk7CiAgJCgncHRiJykucXVlcnlTZWxlY3RvckFsbCgnW2RhdGEtcGRdJykuZm9yRWFjaCgoYikgPT4gYi5vbmNsaWNrID0gYXN5bmMgKCkgPT4geyBpZiAoIWNvbmZpcm0oJ9it2LDZgSDYp9mE2YPZiNiv2J8nKSkgcmV0dXJuOyBhd2FpdCBhcGkoJ3Byb21vX2RlbGV0ZScsIHsgY29kZTogYi5kYXRhc2V0LnBkIH0pOyBsb2FkUHJvbW9zKCk7IH0pOwp9CiQoJ3BnZW4nKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3Byb21vJywgeyBuOiArJCgncGNvdW50JykudmFsdWUsIG5vdGU6ICQoJ3Bub3RlJykudmFsdWUudHJpbSgpIH0pOwogIGlmIChyLm9rKSB7ICQoJ3Bub3RlJykudmFsdWUgPSAnJzsgdG9hc3QoJ9iq2YUg2KXYtdiv2KfYsSAnICsgKHIuY29kZXMgfHwgW10pLmxlbmd0aCArICcg2YPZiNivJyk7IGxvYWRQcm9tb3MoKTsgfSBlbHNlIHRvYXN0KHIuZXJyb3IgfHwgJ9iu2LfYoycpOwp9Owpkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcubmF2W2RhdGEtdl0nKS5mb3JFYWNoKChuKSA9PiBuLm9uY2xpY2sgPSAoKSA9PiB2aWV3KG4uZGF0YXNldC52KSk7Cgphc3luYyBmdW5jdGlvbiBsb2FkKCkgewogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ2RldmljZXMnKTsKICBpZiAoci5vayA9PT0gZmFsc2UgJiYgci5lcnJvcikgeyBsb2NhdGlvbi5yZWxvYWQoKTsgcmV0dXJuOyB9CiAgZGV2cyA9IHIuZGV2aWNlcyB8fCBbXTsKICByZW5kZXJTdGF0cygpOyByZW5kZXJUYWJsZSgpOyByZW5kZXJBdHRuKCk7Cn0KJCgncmVmcmVzaCcpLm9uY2xpY2sgPSAoKSA9PiBsb2FkKCkudGhlbigoKSA9PiB0b2FzdCgn2KrZhSDYp9mE2KrYrdiv2YrYqycpKTsKCmZ1bmN0aW9uIGNvdW50cygpIHsKICBjb25zdCBjID0geyBhbGw6IGRldnMubGVuZ3RoLCBvbjogMCwgd2FpdDogMCwgc29vbjogMCwgZXhwOiAwLCBvZmY6IDAsIG9ubGluZTogMCwgd2F0Y2g6IDAgfTsKICBkZXZzLmZvckVhY2goKGQpID0+IHsgY1tzdGF0ZShkKS5rXSsrOyBpZiAoaXNPbmxpbmUoZCkpIGMub25saW5lKys7IGlmIChpc1dhdGNoaW5nKGQpKSBjLndhdGNoKys7IH0pOwogIHJldHVybiBjOwp9CmZ1bmN0aW9uIHJlbmRlclN0YXRzKCkgewogIGNvbnN0IGMgPSBjb3VudHMoKTsKICBjb25zdCBTID0gW1snYWxsJywgJ9mD2YQg2KfZhNij2KzZh9iy2KknLCBjLmFsbCwgJ3ZhcigtLXQyKSddLCBbJ29ubGluZScsICfZhdiq2LXZhCDYp9mE2KLZhicsIGMub25saW5lLCAndmFyKC0tYSknXSwgWyd3YXRjaCcsICfZiti02KfZh9ivINin2YTYotmGJywgYy53YXRjaCwgJ3ZhcigtLWEpJ10sIFsnb24nLCAn2LTYutmR2KfZhCcsIGMub24gKyBjLnNvb24sICd2YXIoLS1hKSddLAogICAgWyd3YWl0JywgJ9io2KfZhtiq2LjYp9ixINin2YTYqtmB2LnZitmEJywgYy53YWl0LCAndmFyKC0tYiknXSwgWydzb29uJywgJ9mK2YbYqtmH2Yog2K7ZhNin2YQgNyDYo9mK2KfZhScsIGMuc29vbiwgJ3ZhcigtLXkpJ10sIFsnZXhwJywgJ9mF2YbYqtmH2YonLCBjLmV4cCwgJ3ZhcigtLXIpJ10sIFsnb2ZmJywgJ9mF2YjZgtmI2YEnLCBjLm9mZiwgJ3ZhcigtLXQzKSddXTsKICAkKCdzdGF0cycpLmlubmVySFRNTCA9IFMubWFwKChbaywgbCwgbiwgY29sXSkgPT4gYDxkaXYgY2xhc3M9InN0YXQiIGRhdGEtZj0iJHtrfSI+PGRpdiBjbGFzcz0ibCI+PHNwYW4gY2xhc3M9ImRvdCIgc3R5bGU9ImJhY2tncm91bmQ6JHtjb2x9Ij48L3NwYW4+JHtsfTwvZGl2PjxkaXYgY2xhc3M9Im4iPiR7bn08L2Rpdj48L2Rpdj5gKS5qb2luKCcnKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuc3RhdCcpLmZvckVhY2goKHMpID0+IHMub25jbGljayA9ICgpID0+IHsgZmlsdGVyID0gcy5kYXRhc2V0LmY7IHZpZXcoJ2RldnMnKTsgcmVuZGVyVGFibGUoKTsgfSk7CiAgY29uc3QgRiA9IFtbJ2FsbCcsICfYp9mE2YPZhCddLCBbJ29ubGluZScsICfZhdiq2LXZhCDYp9mE2KLZhiddLCBbJ3dhdGNoJywgJ9mK2LTYp9mH2K8g2KfZhNii2YYnXSwgWydvbicsICfYtNi62ZHYp9mEJ10sIFsnd2FpdCcsICfYqNin2YbYqti42KfYsSDYp9mE2KrZgdi52YrZhCddLCBbJ3Nvb24nLCAn2YrZhtiq2YfZiiDZgtix2YrYqNin2YsnXSwgWydleHAnLCAn2YXZhtiq2YfZiiddLCBbJ29mZicsICfZhdmI2YLZiNmBJ11dOwogICQoJ2NoaXBzJykuaW5uZXJIVE1MID0gRi5tYXAoKFtrLCBsXSkgPT4gYDxidXR0b24gY2xhc3M9ImNoaXAke2ZpbHRlciA9PT0gayA/ICcgb24nIDogJyd9IiBkYXRhLWY9IiR7a30iPiR7bH0gPHNwYW4gY2xhc3M9InBpbGwiPiR7ayA9PT0gJ29uJyA/IGMub24gKyBjLnNvb24gOiBjW2tdfTwvc3Bhbj48L2J1dHRvbj5gKS5qb2luKCcnKTsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuY2hpcCcpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9ICgpID0+IHsgZmlsdGVyID0gYi5kYXRhc2V0LmY7IHJlbmRlclN0YXRzKCk7IHJlbmRlclRhYmxlKCk7IH0pOwp9CmZ1bmN0aW9uIHJvdyhkKSB7CiAgY29uc3QgcyA9IHN0YXRlKGQpOwogIGNvbnN0IHBscyA9IChkLnBsYXlsaXN0ID8gYDxzcGFuIGNsYXNzPSJ0YWciPiR7ZXNjKGQucGxheWxpc3QpfTwvc3Bhbj5gIDogJzxzcGFuIGNsYXNzPSJtdXRlZCI+4oCUPC9zcGFuPicpICsgKGQuZXh0cmFzIHx8IFtdKS5tYXAoKHgpID0+IGA8c3BhbiBjbGFzcz0idGFnIj4rICR7ZXNjKHgpfTwvc3Bhbj5gKS5qb2luKCcnKTsKICByZXR1cm4gYDx0ciBkYXRhLWM9IiR7ZXNjKGQuY29kZSl9Ij48dGQ+PHNwYW4gY2xhc3M9ImNvZGUiPiR7cHJldHR5KGVzYyhkLmNvZGUpKX08L3NwYW4+PC90ZD4KICAgIDx0ZCBjbGFzcz0id2hvIj48Yj4ke2QubmFtZSA/IGVzYyhkLm5hbWUpIDogJzxzcGFuIGNsYXNzPSJtdXRlZCI+2KjYr9mI2YYg2KfYs9mFPC9zcGFuPid9PC9iPjxzbWFsbD4ke2VzYyhkLm1vZGVsIHx8ICcnKX08L3NtYWxsPiR7d2hlcmUoZCl9JHt3YXRjaGluZyhkKX08L3RkPgogICAgPHRkPiR7cGxzfSR7ZC5oYXNfdnBuID8gJzxzcGFuIGNsYXNzPSJ0YWciPvCfm6EgVlBOPC9zcGFuPicgOiAnJ30ke2QucHJvbW8gPyAnPHNwYW4gY2xhc3M9InRhZyI+JyArIChkLnByb21vLnN0YXJ0c1dpdGgoJ1BBSUQnKSA/ICfwn5KzINiv2YHYuScgOiAn8J+OnyAnICsgZXNjKGQucHJvbW8ucmVwbGFjZSgvKC57NH0pKC57NH0pLywgJyQxLSQyJykpKSArICc8L3NwYW4+JyA6ICcnfTwvdGQ+PHRkPjxzcGFuIGNsYXNzPSJzdCBzLSR7cy5rfSI+JHtpc09ubGluZShkKSA/ICc8c3BhbiBjbGFzcz0ib25saW5lIj48L3NwYW4+JyA6ICcnfSR7cy50fTwvc3Bhbj48L3RkPgogICAgPHRkIGNsYXNzPSJoaWRlLW0gbXV0ZWQiPiR7YWdvKGQuc2Vlbil9PC90ZD48dGQgY2xhc3M9ImhpZGUtbSBtdXRlZCI+JHtkYXkoZC5leHBpcmVzKSB8fCAn4oCUJ308L3RkPjwvdHI+YDsKfQpmdW5jdGlvbiBiaW5kUm93cyh0YikgeyB0Yi5xdWVyeVNlbGVjdG9yQWxsKCd0cltkYXRhLWNdJykuZm9yRWFjaCgodHIpID0+IHRyLm9uY2xpY2sgPSAoKSA9PiBvcGVuRHJhd2VyKHRyLmRhdGFzZXQuYykpOyB9CmZ1bmN0aW9uIHJlbmRlclRhYmxlKCkgewogIGNvbnN0IHEgPSAkKCdxJykudmFsdWUudHJpbSgpLnRvTG93ZXJDYXNlKCkucmVwbGFjZSgvXHMvZywgJycpOwogIGNvbnN0IGxpc3QgPSBkZXZzLmZpbHRlcigoZCkgPT4gewogICAgY29uc3QgayA9IHN0YXRlKGQpLms7CiAgICBpZiAoZmlsdGVyID09PSAnd2F0Y2gnID8gIWlzV2F0Y2hpbmcoZCkgOiBmaWx0ZXIgPT09ICdvbmxpbmUnID8gIWlzT25saW5lKGQpIDogZmlsdGVyID09PSAnb24nID8gIShrID09PSAnb24nIHx8IGsgPT09ICdzb29uJykgOiBmaWx0ZXIgIT09ICdhbGwnICYmIGsgIT09IGZpbHRlcikgcmV0dXJuIGZhbHNlOwogICAgaWYgKCFxKSByZXR1cm4gdHJ1ZTsKICAgIHJldHVybiBbZC5jb2RlLCBkLm5hbWUsIGQucGxheWxpc3QsIGQubW9kZWwsIGQubm93X3RpdGxlLCAuLi4oZC5leHRyYXMgfHwgW10pXS5zb21lKCh2KSA9PiBTdHJpbmcodiB8fCAnJykudG9Mb3dlckNhc2UoKS5yZXBsYWNlKC9ccy9nLCAnJykuaW5jbHVkZXMocSkpOwogIH0pOwogICQoJ3RiJykuaW5uZXJIVE1MID0gbGlzdC5sZW5ndGggPyBsaXN0Lm1hcChyb3cpLmpvaW4oJycpIDogYDx0cj48dGQgY29sc3Bhbj0iNiIgY2xhc3M9ImVtcHR5Ij7ZhdinINmB2Yog2KPYrNmH2LLYqSDZh9mI2YY8L3RkPjwvdHI+YDsKICBiaW5kUm93cygkKCd0YicpKTsKfQokKCdxJykub25pbnB1dCA9IHJlbmRlclRhYmxlOwpmdW5jdGlvbiByZW5kZXJBdHRuKCkgewogIGNvbnN0IG9yZGVyID0geyB3YWl0OiAwLCBzb29uOiAxLCBleHA6IDIgfTsKICBjb25zdCBsaXN0ID0gZGV2cy5maWx0ZXIoKGQpID0+IHN0YXRlKGQpLmsgaW4gb3JkZXIpLnNvcnQoKGEsIGIpID0+IG9yZGVyW3N0YXRlKGEpLmtdIC0gb3JkZXJbc3RhdGUoYikua10pOwogICQoJ2F0dG4tbicpLnRleHRDb250ZW50ID0gbGlzdC5sZW5ndGggPyBgJHtsaXN0Lmxlbmd0aH0g2KzZh9in2LJgIDogJyc7CiAgJCgnYXR0bicpLmlubmVySFRNTCA9IGxpc3QubGVuZ3RoID8gbGlzdC5tYXAocm93KS5qb2luKCcnKSA6IGA8dHI+PHRkIGNsYXNzPSJlbXB0eSI+2YPZhCDYtNmKINiq2YXYp9mFIOKckyDigJQg2YXYpyDZgdmKINij2KzZh9iy2Kkg2KjYp9mG2KrYuNin2LEg2KPZiCDZhdmG2KrZh9mK2Kk8L3RkPjwvdHI+YDsKICBiaW5kUm93cygkKCdhdHRuJykpOwp9CgovLyAtLS0tLS0tLS0tIGRyYXdlciAtLS0tLS0tLS0tCmZ1bmN0aW9uIG9wZW5EcmF3ZXIoY29kZSkgewogIGVkaXRpbmcgPSBjb2RlID8gZGV2cy5maW5kKCh4KSA9PiB4LmNvZGUgPT09IGNvZGUpIDogbnVsbDsKICBjb25zdCBkID0gZWRpdGluZyB8fCB7fTsKICAkKCdkdCcpLnRleHRDb250ZW50ID0gZWRpdGluZyA/IChkLm5hbWUgfHwgJ9is2YfYp9iyICcgKyBwcmV0dHkoZC5jb2RlKSkgOiAn2KzZh9in2LIg2KzYr9mK2K8nOwogICQoJ2RzdWInKS5pbm5lckhUTUwgPSBlZGl0aW5nID8gYDxzcGFuIGNsYXNzPSJjb2RlIj4ke3ByZXR0eShlc2MoZC5jb2RlKSl9PC9zcGFuPiDCtyAke2VzYyhkLm1vZGVsIHx8ICcnKX0gwrcg2KLYrtixINi42YfZiNixICR7YWdvKGQuc2Vlbil9JHt3YXRjaGluZyhkKSA/ICc8YnI+JyArIHdhdGNoaW5nKGQpIDogJyd9YCA6ICfYp9mD2KrYqCDYp9mE2YPZiNivINin2YTZhNmKINi42KfZh9ixINi52YTZiSDYtNin2LTYqSDYp9mE2LLYqNmI2YYnOwogICQoJ2NvZGUnKS52YWx1ZSA9IGQuY29kZSA/IHByZXR0eShkLmNvZGUpIDogJyc7ICQoJ2NvZGUnKS5kaXNhYmxlZCA9ICEhZWRpdGluZzsKICAkKCduYW1lJykudmFsdWUgPSBkLm5hbWUgfHwgJyc7ICQoJ3BsJykudmFsdWUgPSBkLnBsYXlsaXN0IHx8IHBsYXlsaXN0c1swXSB8fCAnJzsKICAkKCd1JykudmFsdWUgPSAnJzsgJCgncCcpLnZhbHVlID0gJyc7ICQoJ2V4JykudmFsdWUgPSBkYXkoZC5leHBpcmVzKTsKICAkKCdsaGludCcpLnRleHRDb250ZW50ID0gZC5oYXNfbG9naW4gPyAn2KfZhNmK2YjYstixINmF2K3ZgdmI2Lgg2YjZhdi02YHZkdixLiDYp9mD2KrYqCDZitmI2LLYsSDZiNio2KfYs9mI2YjYsdivINis2K/Yp9ivINio2LMg2KXYsNinINio2K/ZgyDYqti62YrZkdix2YfZhS4nIDogJ9in2YPYqtioINin2YTZitmI2LLYsSDZiNin2YTYqNin2LPZiNmI2LHYryDYqtio2Lkg2KfZhNmAIHBsYXlsaXN0Lic7CiAgJCgnYWN0JykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLCBlZGl0aW5nID8gISFkLmFjdGl2ZSA6IHRydWUpOwogICQoJ2RlbCcpLmNsYXNzTGlzdC50b2dnbGUoJ2hpZGUnLCAhZWRpdGluZyk7ICQoJ3hzZWMnKS5jbGFzc0xpc3QudG9nZ2xlKCdoaWRlJywgIWVkaXRpbmcpOyAkKCd2c2VjJykuY2xhc3NMaXN0LnRvZ2dsZSgnaGlkZScsICFlZGl0aW5nKTsKICAkKCd2Y29uZicpLnZhbHVlID0gJyc7IHZwb29sKCk7ICQoJ3ZzdGF0ZScpLmlubmVySFRNTCA9IGQuaGFzX3ZwbiA/ICc8c3BhbiBjbGFzcz0ib2siPuKckyDZgdmKIFZQTiDZhdit2YHZiNi4INmE2YfYsNinINin2YTYrNmH2KfYsiAo2YXYtNmB2ZHYsSk8L3NwYW4+JyA6ICc8c3BhbiBjbGFzcz0ibXV0ZWQiPtmF2Kcg2YHZiiBWUE48L3NwYW4+JzsKICByZW5kZXJFeHRyYXMoKTsgJCgnc20nKS50ZXh0Q29udGVudCA9ICcnOwogICQoJ3NjcmltJykuY2xhc3NMaXN0LmFkZCgnb3BlbicpOyAkKCdkcmF3ZXInKS5jbGFzc0xpc3QuYWRkKCdvcGVuJyk7CiAgc2V0VGltZW91dCgoKSA9PiAoZWRpdGluZyA/ICQoJ25hbWUnKSA6ICQoJ2NvZGUnKSkuZm9jdXMoKSwgMjUwKTsKfQpmdW5jdGlvbiBjbG9zZURyYXdlcigpIHsgJCgnc2NyaW0nKS5jbGFzc0xpc3QucmVtb3ZlKCdvcGVuJyk7ICQoJ2RyYXdlcicpLmNsYXNzTGlzdC5yZW1vdmUoJ29wZW4nKTsgZWRpdGluZyA9IG51bGw7IH0KJCgnYWRkJykub25jbGljayA9ICgpID0+IG9wZW5EcmF3ZXIobnVsbCk7CiQoJ2R4Jykub25jbGljayA9ICQoJ2NhbmNlbCcpLm9uY2xpY2sgPSAkKCdzY3JpbScpLm9uY2xpY2sgPSBjbG9zZURyYXdlcjsKZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigna2V5ZG93bicsIChlKSA9PiB7IGlmIChlLmtleSA9PT0gJ0VzY2FwZScpIGNsb3NlRHJhd2VyKCk7IH0pOwokKCdhY3QnKS5vbmNsaWNrID0gKCkgPT4gJCgnYWN0JykuY2xhc3NMaXN0LnRvZ2dsZSgnb24nKTsKZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnW2RhdGEtYWRkXScpLmZvckVhY2goKGIpID0+IGIub25jbGljayA9ICgpID0+IHsKICBjb25zdCBuID0gK2IuZGF0YXNldC5hZGQ7CiAgaWYgKCFuKSB7ICQoJ2V4JykudmFsdWUgPSAnJzsgcmV0dXJuOyB9CiAgY29uc3QgY3VyID0gJCgnZXgnKS52YWx1ZSA/IERhdGUucGFyc2UoJCgnZXgnKS52YWx1ZSkgOiAwOwogICQoJ2V4JykudmFsdWUgPSBkYXkoTWF0aC5tYXgoY3VyLCBEYXRlLm5vdygpKSArIG4gKiBEQVkpOwp9KTsKZnVuY3Rpb24gcmVuZGVyRXh0cmFzKCkgewogIGNvbnN0IHhzID0gZWRpdGluZz8uZXh0cmFzIHx8IFtdOwogICQoJ3hsaXN0JykuaW5uZXJIVE1MID0geHMubGVuZ3RoID8geHMubWFwKCh4KSA9PiBgPGRpdiBjbGFzcz0ieGwiPjxzcGFuIGNsYXNzPSJ0YWciPiR7ZXNjKHgpfTwvc3Bhbj48YnV0dG9uIGNsYXNzPSJidG4gcmVkIHNtIiBkYXRhLXg9IiR7ZXNjKHgpfSI+2LTZitmEPC9idXR0b24+PC9kaXY+YCkuam9pbignJykgOiAnPGRpdiBjbGFzcz0ibXV0ZWQiIHN0eWxlPSJmb250LXNpemU6MTNweCI+2YXYpyDZgdmKIHBsYXlsaXN0cyDYpdi22KfZgdmK2KkuPC9kaXY+JzsKICAkKCd4bGlzdCcpLnF1ZXJ5U2VsZWN0b3JBbGwoJ1tkYXRhLXhdJykuZm9yRWFjaCgoYikgPT4gYi5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogICAgaWYgKCFjb25maXJtKGDYtNmK2YQgJHtiLmRhdGFzZXQueH0g2YXZhiDZh9iw2Kcg2KfZhNis2YfYp9iy2J9gKSkgcmV0dXJuOwogICAgYXdhaXQgYXBpKCdleHRyYScsIHsgY29kZTogZWRpdGluZy5jb2RlLCBwbGF5bGlzdDogYi5kYXRhc2V0LngsIHJlbW92ZTogdHJ1ZSB9KTsKICAgIGF3YWl0IHJlbG9hZEVkaXRpbmcoKTsgdG9hc3QoJ9in2YbYtNin2YTYqicpOwogIH0pOwp9CmFzeW5jIGZ1bmN0aW9uIHJlbG9hZEVkaXRpbmcoKSB7IGNvbnN0IGMgPSBlZGl0aW5nPy5jb2RlOyBhd2FpdCBsb2FkKCk7IGlmIChjKSB7IGVkaXRpbmcgPSBkZXZzLmZpbmQoKHgpID0+IHguY29kZSA9PT0gYyk7IHJlbmRlckV4dHJhcygpOyB9IH0KJCgneGFkZCcpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nKSByZXR1cm47CiAgY29uc3QgciA9IGF3YWl0IGFwaSgnZXh0cmEnLCB7IGNvZGU6IGVkaXRpbmcuY29kZSwgcGxheWxpc3Q6ICQoJ3hwbCcpLnZhbHVlLCB1c2VyOiAkKCd4dScpLnZhbHVlLCBwYXNzOiAkKCd4cCcpLnZhbHVlIH0pOwogIGlmIChyLm9rKSB7ICQoJ3h1JykudmFsdWUgPSAnJzsgJCgneHAnKS52YWx1ZSA9ICcnOyBhd2FpdCByZWxvYWRFZGl0aW5nKCk7IHRvYXN0KCfYp9mG2LbYp9mB2Kog4pyTIOKAlCDYrtmE2Yog2KfZhNiy2KjZiNmGINmK2YPYqNizIFJlbG9hZCcpOyB9CiAgZWxzZSAkKCdzbScpLmlubmVySFRNTCA9IGA8c3BhbiBjbGFzcz0iYmFkIj4ke2VzYyhyLmVycm9yKX08L3NwYW4+YDsKfTsKY29uc3QgdnBvb2wgPSBhc3luYyAoKSA9PiB7IHRyeSB7IGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3ZwbnBvb2wnKTsgaWYgKHIub2spICQoJ3Zwb29sJykudGV4dENvbnRlbnQgPSBgwrcg2YXYqtin2K0gJHtyLmZyZWV9INmF2YYgJHtyLnRvdGFsfWA7IH0gY2F0Y2ggKGUpIHt9IH07CiQoJ3ZvbicpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nKSByZXR1cm47CiAgY29uc3QgciA9IGF3YWl0IGFwaSgndnBuX29uJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUgfSk7CiAgaWYgKHIub2spIHsgYXdhaXQgcmVsb2FkRWRpdGluZygpOyB2cG9vbCgpOyAkKCd2c3RhdGUnKS5pbm5lckhUTUwgPSAnPHNwYW4gY2xhc3M9Im9rIj7inJMg2KfZhNmAIFZQTiDYtNi62ZHYp9mEINmE2YfYsNinINin2YTYrNmH2KfYsiDigJQg2K7ZhNmKINin2YTYstio2YjZhiDZitmD2KjYsyBSZWxvYWQ8L3NwYW4+JzsgdG9hc3QoJ1ZQTiDYp9i02KrYutmEJyk7IH0KICBlbHNlICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKHIuZXJyb3IpfTwvc3Bhbj5gOwp9OwokKCd2c2F2ZScpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nKSByZXR1cm47CiAgY29uc3QgciA9IGF3YWl0IGFwaSgndnBuJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUsIGNvbmY6ICQoJ3Zjb25mJykudmFsdWUgfSk7CiAgaWYgKHIub2spIHsgJCgndmNvbmYnKS52YWx1ZSA9ICcnOyBhd2FpdCByZWxvYWRFZGl0aW5nKCk7ICQoJ3ZzdGF0ZScpLmlubmVySFRNTCA9ICc8c3BhbiBjbGFzcz0ib2siPuKckyDYp9mG2K3Zgdi4IOKAlCDYrtmE2Yog2KfZhNiy2KjZiNmGINmK2YPYqNizIFJlbG9hZDwvc3Bhbj4nOyB0b2FzdCgnVlBOINin2YbYrdmB2LgnKTsgfQogIGVsc2UgJCgnc20nKS5pbm5lckhUTUwgPSBgPHNwYW4gY2xhc3M9ImJhZCI+JHtlc2Moci5lcnJvcil9PC9zcGFuPmA7Cn07CiQoJ3ZkZWwnKS5vbmNsaWNrID0gYXN5bmMgKCkgPT4gewogIGlmICghZWRpdGluZyB8fCAhY29uZmlybSgn2LTZitmEINin2YTZgCBWUE4g2YXZhiDZh9iw2Kcg2KfZhNis2YfYp9iy2J8nKSkgcmV0dXJuOwogIGF3YWl0IGFwaSgndnBuJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUsIGNvbmY6ICcnIH0pOyBhd2FpdCByZWxvYWRFZGl0aW5nKCk7IHZwb29sKCk7ICQoJ3ZzdGF0ZScpLmlubmVySFRNTCA9ICc8c3BhbiBjbGFzcz0ibXV0ZWQiPtmF2Kcg2YHZiiBWUE48L3NwYW4+JzsgdG9hc3QoJ9in2YbYtNin2YQnKTsKfTsKJCgnc2F2ZScpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgY29uc3QgY29kZSA9ICQoJ2NvZGUnKS52YWx1ZS5yZXBsYWNlKC9cRC9nLCAnJyk7CiAgaWYgKGNvZGUubGVuZ3RoICE9PSA4KSB7ICQoJ3NtJykuaW5uZXJIVE1MID0gJzxzcGFuIGNsYXNzPSJiYWQiPtmD2YjYryDYp9mE2KzZh9in2LIgOCDYo9ix2YLYp9mFPC9zcGFuPic7IHJldHVybjsgfQogIGNvbnN0IGQgPSBkZXZzLmZpbmQoKHgpID0+IHguY29kZSA9PT0gY29kZSk7CiAgaWYgKCFkPy5oYXNfbG9naW4gJiYgKCEkKCd1JykudmFsdWUgfHwgISQoJ3AnKS52YWx1ZSkpIHsgJCgnc20nKS5pbm5lckhUTUwgPSAnPHNwYW4gY2xhc3M9ImJhZCI+2KfZg9iq2Kgg2KfZhNmK2YjYstixINmI2KfZhNio2KfYs9mI2YjYsdivPC9zcGFuPic7IHJldHVybjsgfQogIGNvbnN0IHIgPSBhd2FpdCBhcGkoJ3NhdmUnLCB7IGNvZGUsIG5hbWU6ICQoJ25hbWUnKS52YWx1ZS50cmltKCksIHBsYXlsaXN0OiAkKCdwbCcpLnZhbHVlLCB1c2VyOiAkKCd1JykudmFsdWUsIHBhc3M6ICQoJ3AnKS52YWx1ZSwgZXhwaXJlczogJCgnZXgnKS52YWx1ZSwgYWN0aXZlOiAkKCdhY3QnKS5jbGFzc0xpc3QuY29udGFpbnMoJ29uJykgfSk7CiAgaWYgKCFyLm9rKSB7ICQoJ3NtJykuaW5uZXJIVE1MID0gYDxzcGFuIGNsYXNzPSJiYWQiPiR7ZXNjKHIuZXJyb3IpfTwvc3Bhbj5gOyByZXR1cm47IH0KICAkKCdwJykudmFsdWUgPSAnJzsgY2xvc2VEcmF3ZXIoKTsgYXdhaXQgbG9hZCgpOyB0b2FzdCgn2KfZhtit2YHYuCDinJMg4oCUINiu2YTZiiDYp9mE2LLYqNmI2YYg2YrZg9io2LMgUmVsb2FkJyk7Cn07CiQoJ2RlbCcpLm9uY2xpY2sgPSBhc3luYyAoKSA9PiB7CiAgaWYgKCFlZGl0aW5nIHx8ICFjb25maXJtKGDYrdiw2YEg2KfZhNis2YfYp9iyICR7cHJldHR5KGVkaXRpbmcuY29kZSl9INmG2YfYp9im2YrYp9mL2J9gKSkgcmV0dXJuOwogIGF3YWl0IGFwaSgnZGVsZXRlJywgeyBjb2RlOiBlZGl0aW5nLmNvZGUgfSk7IGNsb3NlRHJhd2VyKCk7IGF3YWl0IGxvYWQoKTsgdG9hc3QoJ9in2YbYrdiw2YEnKTsKfTsKaW5pdCgpOwpzZXRJbnRlcnZhbCgoKSA9PiB7IGlmICghJCgnYXBwJykuY2xhc3NMaXN0LmNvbnRhaW5zKCdoaWRlJykgJiYgISQoJ2RyYXdlcicpLmNsYXNzTGlzdC5jb250YWlucygnb3BlbicpKSBsb2FkKCk7IH0sIDMwMDAwKTsKPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"), (c) => c.charCodeAt(0)));
