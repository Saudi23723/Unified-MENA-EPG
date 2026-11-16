#!/usr/bin/env python3
"""Read Al Mamlaka's own weekly schedule with a real browser.

    xvfb-run -a python tools/fetch_mamlaka_schedule.py

almamlakatv.com answers a plain request with Cloudflare's browser check;
a real Chromium passes it. The page's week is parsed by
mamlaka_epg.parse_schedule_html and written to mamlaka_schedule.json only
when it is whole — five days or more, each with ten shows or more — so a
half-loaded page never replaces a good week. The channel's own logo is
saved beside the others the first time.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mamlaka_epg  # noqa: E402

PAGE = "https://www.almamlakatv.com/ourprograms/schedule"
LOGO_URL = "https://almamlakatv.com/css/frontcss/images/logo.png"
LOGO_FILE = os.path.join("logos", "al_mamlaka.png")


async def main() -> int:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            locale="ar-JO", timezone_id="Asia/Amman",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = await ctx.new_page()
        await page.goto(PAGE, timeout=90000)
        for _ in range(30):
            title = await page.title()
            if "Just a moment" not in title and "لحظة" not in title:
                break
            await page.wait_for_timeout(1500)
        await page.wait_for_timeout(2000)
        html = await page.content()
        if not os.path.exists(LOGO_FILE):
            r = await ctx.request.get(LOGO_URL)
            if r.ok and (r.headers.get("content-type") or "").startswith("image"):
                with open(LOGO_FILE, "wb") as handle:
                    handle.write(await r.body())
                print(f"logo saved: {LOGO_FILE}")
        await browser.close()

    week = mamlaka_epg.parse_schedule_html(html)
    full = [d for d, rows in week.items() if len(rows) >= 10]
    print(f"schedule: {len(week)} day(s), {len(full)} whole, "
          f"{sum(map(len, week.values()))} shows")
    if len(full) < 5:
        print("::warning::the schedule page did not come back whole — "
              "the last week is kept")
        return 0
    old = {}
    if os.path.exists(mamlaka_epg.GRID):
        with open(mamlaka_epg.GRID, encoding="utf-8") as handle:
            old = json.load(handle).get("week") or {}
    if week == old:
        print("schedule: unchanged")
        return 0
    with open(mamlaka_epg.GRID, "w", encoding="utf-8") as handle:
        json.dump({"source": PAGE, "clock": "+03:00",
                   "read": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                   "week": week}, handle, ensure_ascii=False, indent=1)
    print("schedule: updated")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
