# Channels that were tried and are not published

This is the record of what was checked and rejected, kept out of the
README so that file describes only what actually works. It is here so the
same dead ends are not walked a second time.

Every channel below was tried from its own site, with full browser
headers. Two ways to fail: the site never serves the page at all, or it
serves times whose timezone cannot be established — and an unanchorable
time is worse than no time, because it is silently wrong for everyone
outside whatever zone was guessed.

---

| Channel | What its own site does |
|---|---|
| العربية | **403 on every path including the home page** — a 180 KB block page, so the whole domain refuses datacenter traffic. Not a missing schedule: an unreachable site |
| الحدث | 403, same block as العربية |
| MBC (كل القنوات) | `mbc.net` loops redirects forever; every `/schedule`, `/api` and `/sitemap.xml` 404s. Its own platform **Shahid** does answer — `product/id` returns `success:true` — but walking sixty channel ids returns **zero titles**, every EPG path 400s or 500s, the reply always reports `country: USA` whatever country is asked for, and the web app's 385 KB data blob holds no channel at all. The API is reachable and empty from outside the region |
| STC TV · SSC | `stctv.com` 403 with a zero-byte body, `api.stctv.com` does not resolve, `sscsport.com` refuses TLS, `ssc.sa` does not resolve, `sscsports.com` is a parked domain for sale |
| العربي 1 & 2 | no schedule on `alaraby.com` or `alaraby2.com`, sitemaps included |
| الميادين | 403 on every path, its sitemap included |
| المملكة | 403 or 404 on every schedule path |
| التلفزيون الأردني | a 2.6 KB shell |
| قناة عمّان | the same 16 KB page for every URL |
| سما الأردن | no schedule page |
| سكاي نيوز عربية | 404 on schedule, programmes and sitemap |
| الشرق | 403, and an empty 202 on the business site |
| الغد | 403 |
| الحرة | 429 |
| MTV لبنان | the page loads and contains no times |
| المنار | 404 |
| OTV لبنان | 410 Gone |
| تلفزيون لبنان | a 3.4 KB shell |
| أبوظبي | 403 |
| دبي | 404, and awaan.ae carries no times |
| قطر · عُمان · البحرين · النيل · فلسطين · الأقصى | the hosts do not answer at all |
| الكويت | 404 |
| CBC مصر | a 114-byte page |
| CNBC عربية | a 3 KB page with no times |
| BBC عربي · DW · فرانس24 | 404 or 403 |
| OSN | 403 with a zero-byte body on every locale |
| DMC مصر | **serves 28 times and names no timezone** |
| LBCI | **serves 16 times and names no timezone** |
| elcinema.com | carries Jordan TV, Amman TV and Al Araby 2, but renders every row a flat **six hours behind Amman** — UTC−03:00, nobody's broadcast clock — and states no zone. The date box a browser shows is filled by JavaScript from the visitor's own device and never appears in the HTML the server sends. |
| epgshare01 | about five programmes per channel |

Al Jazeera's sibling channels were checked too: `aljazeera.net/schedule`
takes a `?channel=` parameter, but it is **ignored** — thirteen values
including a deliberate nonsense one all return the byte-identical
schedule. The page publishes the main channel and nothing else.

DMC and LBCI are the only two worth revisiting: they publish real
schedules and lack only a clock. If either ever states its timezone, or
turns out to name its own bulletins by the hour the way الجديد does, it
becomes publishable the same day.