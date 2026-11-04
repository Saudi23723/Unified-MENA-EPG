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
      return json({ status: "active", server: lists[0].server, user: l.user, pass: l.pass, name: d.name || "", expires: d.expires || 0, playlists: lists });
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
        return json({ devices: (r.results || []).map((d) => ({ ...d, extras: by[d.code] || [] })) });
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

const PAGE = `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SAUDI.TV · لوحة الإدارة</title>
<style>
:root{--bg:#090c12;--p:#121722;--p2:#19202e;--p3:#222b3d;--line:#232c3e;--t:#f2f4f8;--t2:#9aa3b5;--t3:#6b7488;--a:#00d68f;--a2:#00b377;--r:#ff4d5e;--y:#ffb020;--b:#4da3ff;--sh:0 10px 30px rgba(0,0,0,.35)}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:radial-gradient(1200px 600px at 100% -10%,#0f2a20 0,transparent 60%),var(--bg);color:var(--t);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif}
a{color:inherit}.hide{display:none!important}.muted{color:var(--t2)}.code{font-family:ui-monospace,Menlo,monospace;letter-spacing:1.5px;direction:ltr;display:inline-block;white-space:nowrap}
.shell{display:grid;grid-template-columns:240px 1fr;min-height:100vh}
aside{background:rgba(18,23,34,.85);backdrop-filter:blur(10px);border-left:1px solid var(--line);padding:22px 14px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:6px}
.brand{font-size:24px;font-weight:800;letter-spacing:.5px;padding:4px 10px 18px;direction:ltr;text-align:right}.brand b{color:var(--a)}
.nav{display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:12px;color:var(--t2);cursor:pointer;font-weight:600;border:0;background:none;width:100%;text-align:right;font-size:15px}
.nav:hover{background:var(--p2);color:var(--t)}.nav.on{background:linear-gradient(90deg,transparent,rgba(0,214,143,.16));color:var(--t);box-shadow:inset -3px 0 0 var(--a)}
.nav .ic{width:22px;text-align:center}.spacer{flex:1}
main{padding:26px 30px 60px;max-width:1240px;width:100%}
.top{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:22px;flex-wrap:wrap}
h1{margin:0;font-size:26px}h2{margin:0 0 4px;font-size:18px}.sub{color:var(--t2);margin:2px 0 0}
.btn{background:var(--a);color:#03140c;border:0;border-radius:11px;padding:11px 18px;font-weight:800;font-size:14.5px;cursor:pointer;display:inline-flex;align-items:center;gap:8px;transition:.15s}
.btn:hover{background:var(--a2)}.btn.ghost{background:var(--p2);color:var(--t);border:1px solid var(--line)}.btn.ghost:hover{background:var(--p3)}
.btn.red{background:rgba(255,77,94,.14);color:var(--r);border:1px solid rgba(255,77,94,.35)}.btn.sm{padding:7px 12px;font-size:13px;border-radius:9px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(138px,1fr));gap:14px;margin-bottom:22px}
.stat{background:linear-gradient(180deg,var(--p2),var(--p));border:1px solid var(--line);border-radius:16px;padding:16px 18px;box-shadow:var(--sh);cursor:pointer;transition:.15s}
.stat:hover{transform:translateY(-2px);border-color:#2f3a52}
.stat .n{font-size:30px;font-weight:800;margin-top:4px}.stat .l{color:var(--t2);font-size:13px;display:flex;align-items:center;gap:7px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.card{background:var(--p);border:1px solid var(--line);border-radius:18px;box-shadow:var(--sh)}
.card-h{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.search{background:var(--p2);border:1px solid var(--line);border-radius:11px;padding:9px 12px;color:var(--t);min-width:240px;font-size:14px}
.chip{background:var(--p2);border:1px solid var(--line);color:var(--t2);border-radius:99px;padding:6px 13px;font-size:13px;cursor:pointer;font-weight:600}
.chip.on{background:rgba(0,214,143,.14);border-color:rgba(0,214,143,.5);color:var(--a)}
.wrap{overflow-x:auto}table{width:100%;border-collapse:collapse}
th,td{text-align:right;padding:12px 14px;border-bottom:1px solid var(--line);font-size:14px;vertical-align:middle}
th{color:var(--t3);font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
tbody tr{transition:.12s;cursor:pointer}tbody tr:hover{background:rgba(255,255,255,.025)}
.who b{display:block}.who small{color:var(--t3)}
.tag{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:99px;font-size:12px;background:var(--p3);margin:2px 0 2px 4px;font-weight:600}
.st{display:inline-flex;align-items:center;gap:7px;font-weight:700;font-size:13px}
.s-on{color:var(--a)}.s-wait{color:var(--b)}.s-exp{color:var(--r)}.s-off{color:var(--t3)}.s-soon{color:var(--y)}
.online{width:8px;height:8px;border-radius:50%;background:var(--a);box-shadow:0 0 0 4px rgba(0,214,143,.18);display:inline-block}
.empty{padding:40px;text-align:center;color:var(--t2)}
/* drawer */
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.55);backdrop-filter:blur(2px);z-index:20;opacity:0;pointer-events:none;transition:.2s}
.scrim.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;bottom:0;left:0;width:min(520px,100%);background:var(--p);border-right:1px solid var(--line);z-index:21;transform:translateX(-100%);transition:.25s cubic-bezier(.2,.8,.2,1);display:flex;flex-direction:column;box-shadow:var(--sh)}
.drawer.open{transform:none}
.dh{padding:20px 22px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}
.db{padding:6px 22px 22px;overflow:auto;flex:1}.df{padding:16px 22px;border-top:1px solid var(--line);display:flex;gap:10px;flex-wrap:wrap}
.sec{margin-top:20px;padding:16px;border:1px solid var(--line);border-radius:14px;background:var(--p2)}
.sec h3{margin:0 0 4px;font-size:14px;color:var(--a);display:flex;align-items:center;gap:8px}
label{display:block;color:var(--t2);font-size:12.5px;margin:12px 0 5px;font-weight:600}
input,select{width:100%;background:var(--bg);color:var(--t);border:1px solid var(--line);border-radius:10px;padding:11px 12px;font-size:15px}
input:focus,select:focus{outline:2px solid var(--a);border-color:transparent}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}.quick{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.xl{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;border:1px solid var(--line);border-radius:10px;margin-top:8px;background:var(--bg)}
.msg{min-height:22px;margin-top:10px;font-weight:600}.ok{color:var(--a)}.bad{color:var(--r)}
.switch{display:flex;align-items:center;justify-content:space-between;margin-top:12px}
.tg{position:relative;width:46px;height:26px;background:var(--p3);border-radius:99px;cursor:pointer;transition:.2s;border:0}
.tg::after{content:"";position:absolute;top:3px;right:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:.2s}
.tg.on{background:var(--a)}.tg.on::after{right:23px}
.login{max-width:420px;margin:12vh auto;padding:28px}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(30px);background:var(--p3);border:1px solid var(--line);padding:12px 18px;border-radius:12px;opacity:0;transition:.25s;z-index:40;font-weight:600}
.toast.show{opacity:1;transform:translateX(-50%)}
.help{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
.help .card{padding:18px}.help ol{margin:8px 0 0;padding-inline-start:20px;color:var(--t2)}
.pill{font-size:11px;padding:2px 8px;border-radius:99px;background:var(--p3);color:var(--t2)}
@media (max-width:820px){.shell{grid-template-columns:1fr}aside{position:static;height:auto;flex-direction:row;overflow-x:auto;padding:10px;border:0;border-bottom:1px solid var(--line)}
 .brand{padding:6px 10px}.nav{width:auto;white-space:nowrap}.spacer{display:none}main{padding:18px 14px}.search{min-width:0;flex:1}
 .hide-m{display:none}th,td{padding:10px 8px}}
</style></head><body>

<div id="login" class="card login hide">
  <div class="brand" style="padding:0 0 10px">SAUDI<b>.TV</b></div>
  <h2 id="lt">دخول لوحة الإدارة</h2><p id="lh" class="muted"></p>
  <label>كلمة السر</label><input id="pw" type="password" autocomplete="current-password">
  <div style="margin-top:16px"><button id="go" class="btn" style="width:100%;justify-content:center">دخول</button></div><div id="lm" class="msg bad"></div>
</div>

<div id="app" class="shell hide">
  <aside>
    <div class="brand">SAUDI<b>.TV</b></div>
    <button class="nav on" data-v="dash"><span class="ic">◧</span> لوحة التحكم</button>
    <button class="nav" data-v="devs"><span class="ic">▤</span> الأجهزة</button>
    <button class="nav" data-v="help"><span class="ic">?</span> طريقة الاستخدام</button>
    <div class="spacer"></div>
    <button class="nav" id="out"><span class="ic">⎋</span> خروج</button>
  </aside>
  <main>
    <div class="top">
      <div><h1 id="vt">لوحة التحكم</h1><p class="sub" id="vs">نظرة سريعة على كل الأجهزة</p></div>
      <div class="tools"><button class="btn ghost sm" id="refresh">⟳ تحديث</button><button class="btn" id="add">＋ جهاز جديد</button></div>
    </div>

    <section id="v-dash">
      <div class="stats" id="stats"></div>
      <div class="card">
        <div class="card-h"><h2>يحتاج انتباهك</h2><span class="muted" id="attn-n"></span></div>
        <div class="wrap"><table><tbody id="attn"></tbody></table></div>
      </div>
    </section>

    <section id="v-devs" class="hide">
      <div class="card">
        <div class="card-h">
          <div class="tools" id="chips"></div>
          <input class="search" id="q" placeholder="بحث: كود، اسم، playlist…">
        </div>
        <div class="wrap"><table>
          <thead><tr><th>الكود</th><th>الزبون</th><th>Playlists</th><th>الحالة</th><th class="hide-m">آخر ظهور</th><th class="hide-m">ينتهي</th></tr></thead>
          <tbody id="tb"></tbody></table></div>
      </div>
    </section>

    <section id="v-help" class="hide">
      <div class="help">
        <div class="card"><h2>زبون جديد</h2><ol><li>الزبون ينزّل SAUDI.TV من Downloader ويفتحه.</li><li>بيطلع على شاشته كود من 8 أرقام.</li><li>هون: ＋ جهاز جديد ← اكتب الكود والاسم والـ playlist واليوزر.</li><li>الزبون يكبس Reload — خلص.</li></ol></div>
        <div class="card"><h2>أكثر من playlist</h2><ol><li>افتح الجهاز ← قسم «Playlists إضافية».</li><li>اختار الـ playlist واكتب اليوزر والباسوورد ← أضف.</li><li>الزبون بيختار بينهم من «Playlists» بالتطبيق.</li></ol></div>
        <div class="card"><h2>تجديد وإيقاف</h2><ol><li>افتح الجهاز ← أزرار +30 / +90 / +365 يوم.</li><li>«الجهاز شغّال» تطفيه بيوقف الخدمة فوراً عند الزبون.</li><li>الأجهزة اللي بتنتهي خلال 7 أيام بتطلع بالأصفر.</li></ol></div>
        <div class="card"><h2>الأمان</h2><ol><li>اليوزر والباسوورد محفوظين مشفّرين.</li><li>الباسوورد ما بيرجع يظهر هون أبداً — اتركه فاضي ليبقى القديم.</li><li>رابط التطبيق: <span class="code">saudi1.1saifsaudi.workers.dev/apk</span></li></ol></div>
      </div>
    </section>
  </main>
</div>

<div class="scrim" id="scrim"></div>
<div class="drawer" id="drawer">
  <div class="dh"><div><h2 id="dt">جهاز جديد</h2><div class="muted" id="dsub"></div></div><button class="btn ghost sm" id="dx">✕</button></div>
  <div class="db">
    <div class="sec">
      <h3>① الجهاز والزبون</h3>
      <label>كود الجهاز (8 أرقام من شاشة الزبون)</label><input id="code" inputmode="numeric" maxlength="9" placeholder="1234 5678" class="code" style="text-align:right">
      <label>اسم الزبون</label><input id="name" placeholder="مثلاً: أبو أحمد">
      <div class="switch"><span>الجهاز شغّال</span><button class="tg on" id="act" type="button"></button></div>
    </div>
    <div class="sec">
      <h3>② الـ Playlist الأساسية</h3>
      <label>Playlist</label><select id="pl"></select>
      <div class="grid2">
        <div><label>اليوزر</label><input id="u" autocomplete="off"></div>
        <div><label>الباسوورد</label><input id="p" type="password" autocomplete="new-password"></div>
      </div>
      <div class="muted" id="lhint" style="font-size:12.5px;margin-top:6px"></div>
    </div>
    <div class="sec">
      <h3>③ الاشتراك</h3>
      <label>ينتهي بتاريخ (فاضي = بدون انتهاء)</label><input id="ex" type="date">
      <div class="quick"><button class="btn ghost sm" data-add="30">+30 يوم</button><button class="btn ghost sm" data-add="90">+90 يوم</button><button class="btn ghost sm" data-add="180">+6 شهور</button><button class="btn ghost sm" data-add="365">+سنة</button><button class="btn ghost sm" data-add="0">بدون انتهاء</button></div>
    </div>
    <div class="sec" id="xsec">
      <h3>④ Playlists إضافية</h3>
      <div id="xlist"></div>
      <div class="grid2" style="margin-top:6px"><div><label>Playlist</label><select id="xpl"></select></div><div></div>
        <div><label>اليوزر</label><input id="xu" autocomplete="off"></div><div><label>الباسوورد</label><input id="xp" type="password" autocomplete="new-password"></div></div>
      <div style="margin-top:10px"><button class="btn ghost sm" id="xadd">＋ أضف playlist</button></div>
    </div>
    <div class="msg" id="sm"></div>
  </div>
  <div class="df"><button class="btn" id="save">حفظ</button><button class="btn ghost" id="cancel">إلغاء</button><span class="spacer" style="flex:1"></span><button class="btn red hide" id="del">حذف الجهاز</button></div>
</div>
<div class="toast" id="toast"></div>

<script>
const $ = (id) => document.getElementById(id);
const api = (p, b) => fetch('/admin/api/' + p, b ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b), credentials: 'same-origin' } : { credentials: 'same-origin' })
  .then(async (r) => ({ ok: r.ok, ...(await r.json().catch(() => ({}))) }));
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const DAY = 86400000;
const ago = (t) => { if (!t) return '—'; const m = Math.round((Date.now() - t) / 60000); return m < 1 ? 'الآن' : m < 60 ? \`\${m} دقيقة\` : m < 1440 ? \`\${Math.round(m / 60)} ساعة\` : \`\${Math.round(m / 1440)} يوم\`; };
const day = (t) => t ? new Date(t).toISOString().slice(0, 10) : '';
const pretty = (c) => c.replace(/(\\d{4})(\\d{4})/, '$1 $2');
let devs = [], playlists = [], filter = 'all', editing = null;

function toast(t) { const e = $('toast'); e.textContent = t; e.classList.add('show'); clearTimeout(e._t); e._t = setTimeout(() => e.classList.remove('show'), 2600); }

function state(d) {
  const now = Date.now();
  if (!d.active) return { k: 'off', t: 'موقوف' };
  if (d.expires && d.expires < now) return { k: 'exp', t: 'منتهي' };
  if (!d.has_login || !d.playlist) return { k: 'wait', t: 'بانتظار التفعيل' };
  if (d.expires && d.expires - now < 7 * DAY) return { k: 'soon', t: \`ينتهي خلال \${Math.max(1, Math.ceil((d.expires - now) / DAY))} يوم\` };
  return { k: 'on', t: 'شغّال' };
}
const isOnline = (d) => d.seen && Date.now() - d.seen < 20 * 60000;

async function init() {
  const s = await api('state');
  playlists = s.playlists || [];
  const opts = playlists.map((p) => \`<option value="\${esc(p)}">\${esc(p)}</option>\`).join('');
  $('pl').innerHTML = opts; $('xpl').innerHTML = opts;
  if (s.signed) return show();
  $('login').classList.remove('hide');
  if (s.setup) { $('lt').textContent = 'أول مرة: اختار كلمة سر للإدارة'; $('lh').textContent = '8 أحرف على الأقل. هاي الكلمة بتدخلك على الموقع من أي جهاز.'; $('pw').autocomplete = 'new-password'; }
  $('pw').focus();
}
$('go').onclick = async () => {
  const r = await api('login', { password: $('pw').value, setup: new URLSearchParams(location.search).get('setup') || '' });
  if (r.ok) { $('pw').value = ''; show(); } else $('lm').textContent = r.error || 'خطأ';
};
$('pw').onkeydown = (e) => { if (e.key === 'Enter') $('go').click(); };
$('out').onclick = async () => { await api('logout', {}); location.reload(); };

function show() { $('login').classList.add('hide'); $('app').classList.remove('hide'); load(); }

const VIEWS = { dash: ['لوحة التحكم', 'نظرة سريعة على كل الأجهزة'], devs: ['الأجهزة', 'كل الزباين — اضغط على أي جهاز لتعديله'], help: ['طريقة الاستخدام', 'خطوات سريعة'] };
function view(v) {
  document.querySelectorAll('.nav[data-v]').forEach((n) => n.classList.toggle('on', n.dataset.v === v));
  Object.keys(VIEWS).forEach((k) => $('v-' + k).classList.toggle('hide', k !== v));
  $('vt').textContent = VIEWS[v][0]; $('vs').textContent = VIEWS[v][1];
}
document.querySelectorAll('.nav[data-v]').forEach((n) => n.onclick = () => view(n.dataset.v));

async function load() {
  const r = await api('devices');
  if (r.ok === false && r.error) { location.reload(); return; }
  devs = r.devices || [];
  renderStats(); renderTable(); renderAttn();
}
$('refresh').onclick = () => load().then(() => toast('تم التحديث'));

function counts() {
  const c = { all: devs.length, on: 0, wait: 0, soon: 0, exp: 0, off: 0, online: 0 };
  devs.forEach((d) => { c[state(d).k]++; if (isOnline(d)) c.online++; });
  return c;
}
function renderStats() {
  const c = counts();
  const S = [['all', 'كل الأجهزة', c.all, 'var(--t2)'], ['online', 'متصل الآن', c.online, 'var(--a)'], ['on', 'شغّال', c.on + c.soon, 'var(--a)'],
    ['wait', 'بانتظار التفعيل', c.wait, 'var(--b)'], ['soon', 'ينتهي خلال 7 أيام', c.soon, 'var(--y)'], ['exp', 'منتهي', c.exp, 'var(--r)'], ['off', 'موقوف', c.off, 'var(--t3)']];
  $('stats').innerHTML = S.map(([k, l, n, col]) => \`<div class="stat" data-f="\${k}"><div class="l"><span class="dot" style="background:\${col}"></span>\${l}</div><div class="n">\${n}</div></div>\`).join('');
  document.querySelectorAll('.stat').forEach((s) => s.onclick = () => { filter = s.dataset.f; view('devs'); renderTable(); });
  const F = [['all', 'الكل'], ['online', 'متصل الآن'], ['on', 'شغّال'], ['wait', 'بانتظار التفعيل'], ['soon', 'ينتهي قريباً'], ['exp', 'منتهي'], ['off', 'موقوف']];
  $('chips').innerHTML = F.map(([k, l]) => \`<button class="chip\${filter === k ? ' on' : ''}" data-f="\${k}">\${l} <span class="pill">\${k === 'on' ? c.on + c.soon : c[k]}</span></button>\`).join('');
  document.querySelectorAll('.chip').forEach((b) => b.onclick = () => { filter = b.dataset.f; renderStats(); renderTable(); });
}
function row(d) {
  const s = state(d);
  const pls = (d.playlist ? \`<span class="tag">\${esc(d.playlist)}</span>\` : '<span class="muted">—</span>') + (d.extras || []).map((x) => \`<span class="tag">+ \${esc(x)}</span>\`).join('');
  return \`<tr data-c="\${esc(d.code)}"><td><span class="code">\${pretty(esc(d.code))}</span></td>
    <td class="who"><b>\${d.name ? esc(d.name) : '<span class="muted">بدون اسم</span>'}</b><small>\${esc(d.model || '')}</small></td>
    <td>\${pls}</td><td><span class="st s-\${s.k}">\${isOnline(d) ? '<span class="online"></span>' : ''}\${s.t}</span></td>
    <td class="hide-m muted">\${ago(d.seen)}</td><td class="hide-m muted">\${day(d.expires) || '—'}</td></tr>\`;
}
function bindRows(tb) { tb.querySelectorAll('tr[data-c]').forEach((tr) => tr.onclick = () => openDrawer(tr.dataset.c)); }
function renderTable() {
  const q = $('q').value.trim().toLowerCase().replace(/\\s/g, '');
  const list = devs.filter((d) => {
    const k = state(d).k;
    if (filter === 'online' ? !isOnline(d) : filter === 'on' ? !(k === 'on' || k === 'soon') : filter !== 'all' && k !== filter) return false;
    if (!q) return true;
    return [d.code, d.name, d.playlist, d.model, ...(d.extras || [])].some((v) => String(v || '').toLowerCase().replace(/\\s/g, '').includes(q));
  });
  $('tb').innerHTML = list.length ? list.map(row).join('') : \`<tr><td colspan="6" class="empty">ما في أجهزة هون</td></tr>\`;
  bindRows($('tb'));
}
$('q').oninput = renderTable;
function renderAttn() {
  const order = { wait: 0, soon: 1, exp: 2 };
  const list = devs.filter((d) => state(d).k in order).sort((a, b) => order[state(a).k] - order[state(b).k]);
  $('attn-n').textContent = list.length ? \`\${list.length} جهاز\` : '';
  $('attn').innerHTML = list.length ? list.map(row).join('') : \`<tr><td class="empty">كل شي تمام ✓ — ما في أجهزة بانتظار أو منتهية</td></tr>\`;
  bindRows($('attn'));
}

// ---------- drawer ----------
function openDrawer(code) {
  editing = code ? devs.find((x) => x.code === code) : null;
  const d = editing || {};
  $('dt').textContent = editing ? (d.name || 'جهاز ' + pretty(d.code)) : 'جهاز جديد';
  $('dsub').innerHTML = editing ? \`<span class="code">\${pretty(esc(d.code))}</span> · \${esc(d.model || '')} · آخر ظهور \${ago(d.seen)}\` : 'اكتب الكود اللي ظاهر على شاشة الزبون';
  $('code').value = d.code ? pretty(d.code) : ''; $('code').disabled = !!editing;
  $('name').value = d.name || ''; $('pl').value = d.playlist || playlists[0] || '';
  $('u').value = ''; $('p').value = ''; $('ex').value = day(d.expires);
  $('lhint').textContent = d.has_login ? 'اليوزر محفوظ ومشفّر. اكتب يوزر وباسوورد جداد بس إذا بدك تغيّرهم.' : 'اكتب اليوزر والباسوورد تبع الـ playlist.';
  $('act').classList.toggle('on', editing ? !!d.active : true);
  $('del').classList.toggle('hide', !editing); $('xsec').classList.toggle('hide', !editing);
  renderExtras(); $('sm').textContent = '';
  $('scrim').classList.add('open'); $('drawer').classList.add('open');
  setTimeout(() => (editing ? $('name') : $('code')).focus(), 250);
}
function closeDrawer() { $('scrim').classList.remove('open'); $('drawer').classList.remove('open'); editing = null; }
$('add').onclick = () => openDrawer(null);
$('dx').onclick = $('cancel').onclick = $('scrim').onclick = closeDrawer;
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
$('act').onclick = () => $('act').classList.toggle('on');
document.querySelectorAll('[data-add]').forEach((b) => b.onclick = () => {
  const n = +b.dataset.add;
  if (!n) { $('ex').value = ''; return; }
  const cur = $('ex').value ? Date.parse($('ex').value) : 0;
  $('ex').value = day(Math.max(cur, Date.now()) + n * DAY);
});
function renderExtras() {
  const xs = editing?.extras || [];
  $('xlist').innerHTML = xs.length ? xs.map((x) => \`<div class="xl"><span class="tag">\${esc(x)}</span><button class="btn red sm" data-x="\${esc(x)}">شيل</button></div>\`).join('') : '<div class="muted" style="font-size:13px">ما في playlists إضافية.</div>';
  $('xlist').querySelectorAll('[data-x]').forEach((b) => b.onclick = async () => {
    if (!confirm(\`شيل \${b.dataset.x} من هذا الجهاز؟\`)) return;
    await api('extra', { code: editing.code, playlist: b.dataset.x, remove: true });
    await reloadEditing(); toast('انشالت');
  });
}
async function reloadEditing() { const c = editing?.code; await load(); if (c) { editing = devs.find((x) => x.code === c); renderExtras(); } }
$('xadd').onclick = async () => {
  if (!editing) return;
  const r = await api('extra', { code: editing.code, playlist: $('xpl').value, user: $('xu').value, pass: $('xp').value });
  if (r.ok) { $('xu').value = ''; $('xp').value = ''; await reloadEditing(); toast('انضافت ✓ — خلي الزبون يكبس Reload'); }
  else $('sm').innerHTML = \`<span class="bad">\${esc(r.error)}</span>\`;
};
$('save').onclick = async () => {
  const code = $('code').value.replace(/\\D/g, '');
  if (code.length !== 8) { $('sm').innerHTML = '<span class="bad">كود الجهاز 8 أرقام</span>'; return; }
  const d = devs.find((x) => x.code === code);
  if (!d?.has_login && (!$('u').value || !$('p').value)) { $('sm').innerHTML = '<span class="bad">اكتب اليوزر والباسوورد</span>'; return; }
  const r = await api('save', { code, name: $('name').value.trim(), playlist: $('pl').value, user: $('u').value, pass: $('p').value, expires: $('ex').value, active: $('act').classList.contains('on') });
  if (!r.ok) { $('sm').innerHTML = \`<span class="bad">\${esc(r.error)}</span>\`; return; }
  $('p').value = ''; closeDrawer(); await load(); toast('انحفظ ✓ — خلي الزبون يكبس Reload');
};
$('del').onclick = async () => {
  if (!editing || !confirm(\`حذف الجهاز \${pretty(editing.code)} نهائياً؟\`)) return;
  await api('delete', { code: editing.code }); closeDrawer(); await load(); toast('انحذف');
};
init();
setInterval(() => { if (!$('app').classList.contains('hide') && !$('drawer').classList.contains('open')) load(); }, 60000);
</script></body></html>
`;
