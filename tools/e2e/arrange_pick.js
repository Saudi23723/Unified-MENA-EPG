// Throw-away worker (owner, 26 Nov 2026: "make the groups like I have them on Strong, for everyone"): reads the
// owner's own devices' backups and gives ONLY the group arrangement (order, hidden, shown, hidden channels, channel
// order, names) per playlist, to a caller that knows the run's one-time key. No logins, no codes. Deleted after.
export default {
  async fetch(req, env) {
    if (req.headers.get("x-key") !== env.KEY) return new Response("no", { status: 403 });
    const rows = (await env.DB.prepare(
      "SELECT b.t AS t, b.data AS data, d.name AS name, d.playlist AS pl FROM backup b JOIN devices d ON d.code=b.code " +
      "WHERE lower(coalesce(d.grp,''))='saif' OR lower(coalesce(d.name,'')) LIKE 'saif%' ORDER BY b.t DESC LIMIT 20").all()).results || [];
    const out = [];
    for (const r of rows) {
      let d = {}; try { d = JSON.parse(r.data); } catch (e) { continue; }
      const keep = {};
      for (const [k, v] of Object.entries(d)) if (/^(go|gh|gs|ch|co|gr)_[a-z0-9]+$/.test(k)) keep[k] = v.v;
      if (Object.keys(keep).length) out.push({ device: r.name || "", playlist: r.pl || "", saved: new Date(r.t).toISOString(), keys: keep });
    }
    if (!out.length) {
      // nothing found: counts only, to see why (no names, no codes)
      const c = async (q) => ((await env.DB.prepare(q).first()) || {}).n;
      return new Response(JSON.stringify({ found: 0,
        owner_devices: await c("SELECT count(*) n FROM devices WHERE lower(coalesce(grp,''))='saif' OR lower(coalesce(name,'')) LIKE 'saif%'"),
        owner_backups: await c("SELECT count(*) n FROM backup b JOIN devices d ON d.code=b.code WHERE lower(coalesce(d.grp,''))='saif' OR lower(coalesce(d.name,'')) LIKE 'saif%'"),
        backups_all: await c("SELECT count(*) n FROM backup"),
        backups_with_arrange: await c("SELECT count(*) n FROM backup WHERE data LIKE '%\"go_strong\"%' OR data LIKE '%\"gh_strong\"%' OR data LIKE '%\"gs_strong\"%'"),
        groups: (await env.DB.prepare("SELECT coalesce(grp,'') g, count(*) n FROM devices GROUP BY g ORDER BY n DESC LIMIT 12").all()).results }),
        { headers: { "content-type": "application/json" } });
    }
    return new Response(JSON.stringify(out), { headers: { "content-type": "application/json" } });
  },
};
