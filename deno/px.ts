// SAUDI.TV web player route on Deno Deploy (owner, 25 Nov 2026: "Deno, do it"). The same job as /api/px on the
// Cloudflare worker, for the providers that turn Cloudflare away but take an ordinary server (up1): Safari on an
// https page cannot play the providers' http video, so the video comes through here over https.
// Only working SAUDI.TV devices may use it (checked with the saudi1 worker, remembered 10 minutes).
const SITE = "https://saudi1.1saifsaudi.workers.dev";
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "Content-Length,Content-Range,Accept-Ranges", "Cache-Control": "no-store" };
const ok = new Map<string, number>();

async function allowed(code: string): Promise<boolean> {
  const t = ok.get(code);
  if (t && Date.now() - t < 600_000) return true;
  try {
    const r = await fetch(`${SITE}/api/ok?code=${code}`);
    if (r.status === 200) { ok.set(code, Date.now()); return true; }
  } catch { /* the check failed: no */ }
  return false;
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  if (req.method === "OPTIONS") return new Response(null, { headers: { ...CORS, "Access-Control-Allow-Headers": "Range" } });
  if (url.pathname !== "/px") return new Response("SAUDI.TV", { headers: CORS });
  const code = (url.searchParams.get("code") || "").replace(/\D/g, "");
  if (code.length !== 8 || !(await allowed(code))) return new Response("not allowed", { status: 403, headers: CORS });
  let t: URL;
  try { t = new URL(url.searchParams.get("u") || ""); } catch { return new Response("bad link", { status: 400, headers: CORS }); }
  if (!/^https?:$/.test(t.protocol) || /^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.)/.test(t.hostname)) return new Response("bad link", { status: 400, headers: CORS });
  const h: Record<string, string> = { "User-Agent": "Lavf/60.3.100" };
  const rg = req.headers.get("Range"); if (rg) h.Range = rg;
  let r: Response, at = t.toString();
  try {
    r = await fetch(at, { headers: h, redirect: "manual" });
    for (let hop = 0; hop < 6 && r.status >= 300 && r.status < 400 && r.headers.get("location"); hop++) {
      at = new URL(r.headers.get("location")!, at).toString();
      r = await fetch(at, { headers: h, redirect: "manual" });
    }
  } catch { return new Response("provider unreachable", { status: 502, headers: CORS }); }
  if (url.searchParams.get("dbg") === "1") return new Response(String(r.status), { headers: CORS });
  const ct = r.headers.get("content-type") || "";
  const path = new URL(at).pathname.toLowerCase();
  if (r.ok && !/\.(ts|m4s|aac|mp4|mkv|avi|mp3)$/.test(path) && (/mpegurl/i.test(ct) || /\.m3u8$/.test(path))) {
    const via = (u: string) => `${url.origin}/px?code=${code}&u=${encodeURIComponent(new URL(u, at).toString())}`;
    const body = (await r.text()).split(/\r?\n/).map((ln) => {
      if (!ln.trim()) return ln;
      if (ln[0] === "#") return ln.replace(/URI="([^"]+)"/g, (_m, u) => `URI="${via(u)}"`);
      return via(ln.trim());
    }).join("\n");
    return new Response(body, { headers: { ...CORS, "Content-Type": "application/vnd.apple.mpegurl" } });
  }
  const out = new Headers(CORS);
  for (const k of ["content-type", "content-length", "content-range", "accept-ranges"]) { const v = r.headers.get(k); if (v) out.set(k, v); }
  return new Response(r.body, { status: r.status, headers: out });
});
