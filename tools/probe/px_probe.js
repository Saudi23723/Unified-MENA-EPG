// Temporary test worker (owner, 25 Nov 2026: "make sure Safari works"): checks from inside Cloudflare whether a
// worker can reach the playlist relays and where their video links lead. The provider itself is NOT contacted (a wrong login there can get an address blocked). Prints no logins, no host names:
// only status codes, the link's scheme (http/https) and port. Deleted again by the same workflow.
const RELAYS = ["strong", "dream4k", "argon", "hydra", "family4k", "aroma", "up1"];
export default {
  async fetch() {
    const out = {};
    for (const n of RELAYS) {
      const o = (out[n] = {});
      try {
        const r = await fetch(`https://${n}.1saifsaudi.workers.dev/live/test/test/1.m3u8`, { redirect: "manual" });
        o.relay = r.status;
        const loc = r.headers.get("location") || "";
        if (r.status >= 500 || !loc) o.body = (await r.text()).replace(/[^\w .:-]/g, " ").slice(0, 120);
        if (loc) {
          const u = new URL(loc);
          o.to = u.protocol.replace(":", "") + " port " + (u.port || (u.protocol === "https:" ? 443 : 80));
        }
      } catch (e) { o.relay = "error " + String(e).slice(0, 120); }
    }
    return new Response(JSON.stringify(out, null, 1), { headers: { "content-type": "application/json" } });
  },
};
