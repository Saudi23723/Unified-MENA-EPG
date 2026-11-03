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
      return json({ status: "active", server: PLAYLISTS[d.playlist] || d.playlist, user: l.user, pass: l.pass, name: d.name || "", expires: d.expires || 0 });
    }

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
        return json({ devices: r.results });
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
<title>SAUDI.1 · الإدارة</title>
<style>
:root{--bg:#0b0e14;--p:#141923;--p2:#1b2130;--t:#f2f4f8;--t2:#9aa3b5;--a:#00d68f;--r:#ff4d5e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif}
header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid #222a3a}
h1{margin:0;font-size:22px;letter-spacing:.5px}h1 b{color:var(--a)}
main{max-width:1000px;margin:0 auto;padding:20px 16px}
.card{background:var(--p);border-radius:14px;padding:18px;margin-bottom:16px}
label{display:block;color:var(--t2);font-size:13px;margin:10px 0 4px}
input,select{width:100%;background:var(--p2);color:var(--t);border:1px solid #2a3245;border-radius:10px;padding:11px 12px;font-size:15px}
input:focus,select:focus{outline:2px solid var(--a);border-color:transparent}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
button{background:var(--a);color:#06110c;border:0;border-radius:10px;padding:11px 18px;font-weight:700;font-size:15px;cursor:pointer}
button.ghost{background:var(--p2);color:var(--t)}button.red{background:var(--r);color:#fff}
table{width:100%;border-collapse:collapse}th,td{text-align:right;padding:10px 8px;border-bottom:1px solid #222a3a;font-size:14px}
th{color:var(--t2);font-weight:600}.tag{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;background:var(--p2)}
.ok{color:var(--a)}.bad{color:var(--r)}.muted{color:var(--t2)}.hide{display:none}.code{font-family:ui-monospace,monospace;letter-spacing:1px}
.msg{margin-top:10px;min-height:20px}.wrap{overflow-x:auto}
</style></head><body>
<header><h1>SAUDI<b>.1</b> · الإدارة</h1><button id="out" class="ghost hide">خروج</button></header>
<main>
<div id="login" class="card hide">
  <h2 id="lt">دخول</h2><p id="lh" class="muted"></p>
  <label>كلمة السر</label><input id="pw" type="password" autocomplete="current-password">
  <div style="margin-top:14px"><button id="go">دخول</button></div><div id="lm" class="msg bad"></div>
</div>
<div id="app" class="hide">
  <div class="card">
    <h2 style="margin-top:0">إضافة / تعديل جهاز</h2>
    <p class="muted">كود الجهاز بيطلع على شاشة SAUDI.1 عند الزبون (8 أرقام). بعد الحفظ، الزبون بيكبس Reload.</p>
    <div class="row">
      <div><label>كود الجهاز</label><input id="code" inputmode="numeric" maxlength="9" placeholder="1234 5678" class="code"></div>
      <div><label>اسم الزبون</label><input id="name" placeholder="مثلاً: أبو أحمد"></div>
      <div><label>الـ Playlist</label><select id="pl"></select></div>
    </div>
    <div class="row">
      <div><label>اليوزر</label><input id="u" autocomplete="off"></div>
      <div><label>الباسوورد</label><input id="p" type="password" autocomplete="new-password" placeholder="اتركه فاضي لتبقى القديمة"></div>
      <div><label>ينتهي بتاريخ (اختياري)</label><input id="ex" type="date"></div>
    </div>
    <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap"><button id="save">حفظ</button><button id="clear" class="ghost">جديد</button></div>
    <div id="sm" class="msg"></div>
  </div>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center"><h2 style="margin:0">الأجهزة</h2><span id="cnt" class="muted"></span></div>
    <div class="wrap"><table><thead><tr><th>الكود</th><th>الزبون</th><th>Playlist</th><th>الحالة</th><th>آخر ظهور</th><th>ينتهي</th><th></th></tr></thead><tbody id="tb"></tbody></table></div>
  </div>
</div>
</main>
<script>
const $=id=>document.getElementById(id);
const api=(p,b)=>fetch('/admin/api/'+p,b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b),credentials:'same-origin'}:{credentials:'same-origin'}).then(async r=>({ok:r.ok,...(await r.json())}));
const ago=t=>{if(!t)return'—';const m=Math.round((Date.now()-t)/60000);return m<1?'الآن':m<60?m+' دقيقة':m<1440?Math.round(m/60)+' ساعة':Math.round(m/1440)+' يوم'};
const day=t=>t?new Date(t).toISOString().slice(0,10):'';
let devs=[];
async function init(){const s=await api('state');
 $('pl').innerHTML=s.playlists.map(p=>'<option value="'+p+'">'+p+'</option>').join('');
 if(s.signed){show();return}
 $('login').classList.remove('hide');
 if(s.setup){$('lt').textContent='أول مرة: اختار كلمة سر للإدارة';$('lh').textContent='8 أحرف على الأقل. هاي الكلمة بتدخلك على الموقع من أي جهاز.';$('pw').autocomplete='new-password'}
 $('pw').focus()}
$('go').onclick=async()=>{const r=await api('login',{password:$('pw').value,setup:new URLSearchParams(location.search).get('setup')||''});if(r.ok){$('pw').value='';show()}else $('lm').textContent=r.error};
$('pw').onkeydown=e=>{if(e.key==='Enter')$('go').click()};
$('out').onclick=async()=>{await api('logout',{});location.reload()};
async function show(){$('login').classList.add('hide');$('app').classList.remove('hide');$('out').classList.remove('hide');load()}
async function load(){const r=await api('devices');devs=r.devices||[];$('cnt').textContent=devs.length+' جهاز';
 $('tb').innerHTML=devs.map(d=>{const exp=d.expires&&d.expires<Date.now();
  const st=!d.active?'<span class="bad">موقوف</span>':exp?'<span class="bad">منتهي</span>':d.has_login&&d.playlist?'<span class="ok">شغّال</span>':'<span class="muted">بانتظار التفعيل</span>';
  return '<tr><td class="code">'+d.code.replace(/(\\d{4})(\\d{4})/,'$1 $2')+'</td><td>'+(d.name||'<span class=muted>—</span>')+'<div class=muted style="font-size:12px">'+(d.model||'')+'</div></td><td>'+(d.playlist?'<span class=tag>'+d.playlist+'</span>':'—')+'</td><td>'+st+'</td><td>'+ago(d.seen)+'</td><td>'+(day(d.expires)||'—')+'</td><td style="white-space:nowrap"><button class="ghost" onclick="edit(\\''+d.code+'\\')">تعديل</button> <button class="ghost" onclick="tog(\\''+d.code+'\\')">'+(d.active?'إيقاف':'تشغيل')+'</button> <button class="red" onclick="del(\\''+d.code+'\\')">حذف</button></td></tr>'}).join('')}
window.edit=c=>{const d=devs.find(x=>x.code===c);$('code').value=d.code;$('name').value=d.name||'';$('pl').value=d.playlist||'strong';$('u').value='';$('p').value='';$('ex').value=day(d.expires);$('sm').textContent=d.has_login?'اليوزر محفوظ. اكتب يوزر وباسوورد جداد بس إذا بدك تغيّرهم.':'';scrollTo(0,0)};
window.tog=async c=>{const d=devs.find(x=>x.code===c);await api('save',{code:c,name:d.name,playlist:d.playlist,expires:day(d.expires),active:!d.active});load()};
window.del=async c=>{if(confirm('حذف الجهاز '+c+'؟')){await api('delete',{code:c});load()}};
$('clear').onclick=()=>{['code','name','u','p','ex'].forEach(i=>$(i).value='');$('sm').textContent=''};
$('save').onclick=async()=>{const code=$('code').value.replace(/\\D/g,'');const d=devs.find(x=>x.code===code);
 if(!d?.has_login&&(!$('u').value||!$('p').value)){$('sm').innerHTML='<span class=bad>اكتب اليوزر والباسوورد</span>';return}
 const r=await api('save',{code,name:$('name').value,playlist:$('pl').value,user:$('u').value,pass:$('p').value,expires:$('ex').value,active:d?!!d.active:true});
 $('sm').innerHTML=r.ok?'<span class=ok>انحفظ ✓ — خلي الزبون يكبس Reload</span>':'<span class=bad>'+r.error+'</span>';if(r.ok){$('p').value='';load()}};
init();
</script></body></html>`;
