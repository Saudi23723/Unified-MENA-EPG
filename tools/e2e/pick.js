// Throw-away worker for the web player test (owner, 25 Nov 2026: "check it works yourself"): gives the test ONE
// working device code (the owner's own devices first), only to a caller that knows the run's one-time key.
// Nothing else is read; the workflow deletes this worker straight after.
export default {
  async fetch(req, env) {
    if (req.headers.get("x-key") !== env.KEY) return new Response("no", { status: 403 });
    const now = Date.now();
    const q = "SELECT code FROM devices WHERE active=1 AND login IS NOT NULL AND login<>'' AND playlist IS NOT NULL AND (expires IS NULL OR expires=0 OR expires>?) ";
    let r = await env.DB.prepare(q + "AND (lower(coalesce(grp,''))='saif' OR lower(coalesce(name,'')) LIKE 'saif%') ORDER BY seen DESC LIMIT 1").bind(now).first();
    if (!r) r = await env.DB.prepare(q + "ORDER BY seen DESC LIMIT 1").bind(now).first();
    return new Response(r ? r.code : "", { status: r ? 200 : 404 });
  },
};
