// Opens the real web player (/tv) in WebKit (Safari's engine) as an iPhone, plays live channels and checks that the
// picture really moves (currentTime grows). Prints no codes, no logins: channel names, states and HTTP codes only.
const { webkit, devices } = require("playwright");
const CODE = process.env.CODE, SITE = "https://saudi1.1saifsaudi.workers.dev";
(async () => {
  const b = await webkit.launch();
  const ctx = await b.newContext({ ...devices["iPhone 14"] });
  await ctx.addInitScript((c) => { try { localStorage.setItem("code", c); } catch (e) {} }, CODE);
  const page = await ctx.newPage();
  const px = {}; let pxN = 0;
  page.on("response", (r) => { if (r.url().includes("/api/px")) { pxN++; px[r.status()] = (px[r.status()] || 0) + 1; } });
  page.on("console", (m) => { if (m.type() === "error") console.log("console:", m.text().replace(/\/\/[^ ]*/g, "<link>").slice(0, 160)); });
  await page.goto(SITE + "/tv", { waitUntil: "domcontentloaded" });
  await page.waitForSelector('.card[data-c="live"]', { timeout: 45000 });
  console.log("home ok; native HLS:", await page.evaluate(() => document.createElement("video").canPlayType("application/vnd.apple.mpegurl") || "no"));
  await page.click('.card[data-c="live"]');
  await page.waitForSelector("#chans .row", { timeout: 45000 });
  const groups = await page.$$eval("#groups .chip", (a) => a.length);
  console.log("live list ok; groups", groups);
  let ok = 0;
  const tryGroups = [0, 3, 8].filter((g) => g < groups);
  for (const g of tryGroups) {
    if (g) { await page.click(`#groups .chip >> nth=${g}`); await page.waitForTimeout(3000); }
    const name = await page.$eval("#chans .row", (r) => r.innerText.replace(/\s+/g, " ").slice(0, 40)).catch(() => "?");
    await page.click("#chans .row >> nth=0");
    let last = -1, moving = 0, state = "";
    for (let i = 0; i < 20; i++) {
      await page.waitForTimeout(2000);
      state = await page.evaluate(() => { const v = document.getElementById("v"); const m = document.getElementById("msg"); return { t: v.currentTime, rs: v.readyState, paused: v.paused, err: v.error && v.error.code, msg: m && !m.classList.contains("hide") ? m.textContent : "", w: v.videoWidth }; });
      if (state.t > 0 && state.t > last) moving++; last = state.t;
      if (moving >= 3) break;
    }
    const good = moving >= 3;
    console.log(`${good ? "PLAYS" : "FAILS"}: ${name} | time ${state.t.toFixed(1)}s picture ${state.w}px ready ${state.rs} paused ${state.paused} err ${state.err} msg "${state.msg.replace(/\n/g, " ")}" | px calls ${pxN} ${JSON.stringify(px)}`);
    await page.screenshot({ path: `shot_${g}.png` });
    if (good) ok++;
    await page.goBack().catch(() => {}); await page.waitForTimeout(1500);
    if (!(await page.$("#chans .row"))) { await page.click('.card[data-c="live"]').catch(() => {}); await page.waitForSelector("#chans .row", { timeout: 30000 }).catch(() => {}); }
  }
  console.log(`RESULT ${ok}/${tryGroups.length} channels play`);
  await b.close();
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.log("TEST ERROR", String(e).slice(0, 300)); process.exit(2); });
