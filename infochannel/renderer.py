#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draws the info-channel screen.

The expensive work (background, cards, all the text) happens once per page
change; the clock is the only thing repainted every frame, by restoring a
saved patch of the background under it. That keeps a 24/7 stream at a few
percent of one CPU core, which is what makes this runnable on a Raspberry Pi
or a free-tier VM instead of a paid server.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFilter

from theme import Palette, Theme, channel_colour, covers, direction_for, font_for, prepare


def measure(draw, text: str, fnt) -> float:
    """Width of a string as it will actually be drawn (direction included)."""
    return draw.textlength(prepare(text, fnt), font=fnt, direction=direction_for(text))

AR_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]
AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

LIVE_PER_PAGE = 5
UPCOMING_PER_PAGE = 8
MAX_PAGES = 8


def fmt_duration(delta: timedelta) -> str:
    """`1س 32د` — mirrors how broadcast info screens count down."""
    total = max(0, int(delta.total_seconds()))
    hours, minutes = total // 3600, (total % 3600) // 60
    if hours >= 24:
        days = hours // 24
        return f"{days}ي {hours % 24}س"
    if hours:
        return f"{hours}س {minutes}د"
    if minutes:
        return f"{minutes}د"
    return ""


def fmt_countdown(delta: timedelta) -> str:
    """Prefixed countdown, degrading to `يبدأ الآن` under a minute so the
    board never reads `بعد الآن`."""
    text = fmt_duration(delta)
    return f"بعد {text}" if text else "يبدأ الآن"


def arabic_date(dt: datetime) -> str:
    return f"{dt.day} {AR_MONTHS[dt.month - 1]} {dt.year} · {AR_DAYS[dt.weekday()]}"


def channel_label(name: str) -> str:
    """Shorten a channel name so it fits a chip without wrapping."""
    text = (name or "").strip()
    text = text.replace("beIN SPORTS", "beIN").replace("beIN Sports", "beIN")
    text = text.replace("Tabii Spor", "Tabii").replace("ON Sport", "ON")
    return text[:22]


class Renderer:
    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        *,
        title: str = "MENA SPORTS INFO",
        subtitle: str = "دليل المباريات المباشر · يتحدث تلقائياً",
        tz=None,
    ) -> None:
        self.t = Theme(width, height)
        self.title = title
        self.subtitle = subtitle
        self.tz = tz

        self._bg = self._build_background()
        self._canvas: Image.Image | None = None
        self._clock_box: tuple[int, int, int, int] | None = None
        self._clock_patch: Image.Image | None = None
        self._page_key: tuple | None = None

    # -- background ----------------------------------------------------------
    def _build_background(self) -> Image.Image:
        t = self.t
        w, h = t.w, t.h
        base = Image.new("RGB", (w, h), Palette.bg_top)
        draw = ImageDraw.Draw(base)

        top, bottom = Palette.bg_top, Palette.bg_bottom
        for y in range(h):
            k = y / max(1, h - 1)
            draw.line(
                [(0, y), (w, y)],
                fill=tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)),
            )

        # Soft corner glow, blurred so it reads as light rather than a shape.
        glow = Image.new("RGB", (w, h), (0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        r = int(w * 0.42)
        gdraw.ellipse([-r // 3, -r // 2, r, r // 2], fill=Palette.glow)
        gdraw.ellipse([w - r, h - r // 2, w + r // 3, h + r // 2], fill=(70, 40, 130))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=max(24, int(w * 0.06))))
        base = Image.blend(base, Image.blend(base, glow, 0.35), 0.55)

        # Thin accent rule under the header.
        d = ImageDraw.Draw(base)
        y = t.header_h
        d.line([(t.pad, y), (w - t.pad, y)], fill=(38, 48, 76), width=max(1, t.px(1)))
        return base

    # -- small helpers -------------------------------------------------------
    @staticmethod
    def _text(draw, xy, text, fnt, fill, anchor="la") -> None:
        draw.text(xy, prepare(text, fnt), font=fnt, fill=fill, anchor=anchor,
                  direction=direction_for(text))

    @staticmethod
    def _fit(draw, text: str, fnt, max_w: int) -> str:
        """Truncate with an ellipsis so a long fixture never overruns a card.

        The ellipsis character is chosen per font: the Arabic faces have no
        U+2026, and silently dropping it would leave a title looking complete
        when it was actually cut."""
        if measure(draw, text, fnt) <= max_w:
            return text
        ell = "…" if covers(fnt, "…") else "..."
        out = text
        while out and measure(draw, out + ell, fnt) > max_w:
            out = out[:-1]
        return (out.rstrip() + ell) if out else ""

    def _chip(self, odraw, x, y, label, colour, fnt, text_ops) -> int:
        """Rounded channel badge. Returns its width."""
        t = self.t
        pad_x = t.px(8)
        tw = measure(odraw, label, fnt)
        h = t.px(22)
        w = int(tw) + pad_x * 2
        odraw.rounded_rectangle(
            [x, y, x + w, y + h], radius=t.px(6), fill=(*colour, 46), outline=(*colour, 150), width=1
        )
        text_ops.append(((x + w / 2, y + h / 2), label, fnt, colour, "mm"))
        return w

    # -- sections ------------------------------------------------------------
    def _section_header(self, odraw, x, y, w, title, en, count, colour, text_ops) -> int:
        t = self.t
        fnt = font_for(title, t.fs_section, bold=True)
        bar_w, bar_h = t.px(4), t.px(20)
        odraw.rounded_rectangle(
            [x, y + t.px(3), x + bar_w, y + t.px(3) + bar_h], radius=t.px(2), fill=(*colour, 255)
        )
        tx = x + bar_w + t.px(10)
        text_ops.append(((tx, y), title, fnt, Palette.text, "la"))
        tw = measure(odraw, title, fnt)

        small = font_for(en, t.fs_small, bold=False)
        text_ops.append(((tx + tw + t.px(10), y + t.px(9)), en, small, Palette.text_faint, "la"))

        if count:
            cf = font_for(str(count), t.fs_small, bold=True)
            label = str(count)
            cw = int(odraw.textlength(label, font=cf)) + t.px(14)
            cx = x + w - cw
            odraw.rounded_rectangle(
                [cx, y + t.px(2), cx + cw, y + t.px(2) + t.px(20)],
                radius=t.px(10), fill=(*colour, 40), outline=(*colour, 120), width=1,
            )
            text_ops.append(((cx + cw / 2, y + t.px(12)), label, cf, colour, "mm"))

        return y + t.px(34)

    def _live_card(self, odraw, x, y, w, ev, now, text_ops) -> int:
        t = self.t
        h = t.px(96)
        r = t.radius
        odraw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=Palette.card_live,
                                outline=(255, 71, 82, 60), width=1)
        # Accent spine on the left edge.
        odraw.rounded_rectangle([x, y + t.px(10), x + t.px(3), y + h - t.px(10)],
                                radius=t.px(2), fill=(*Palette.live, 230))

        ix = x + t.px(14)
        iw = w - t.px(28)

        # Row 1 — channel chip + LIVE badge.
        chip_f = font_for(ev.channel_name, t.fs_small, bold=True)
        colour = channel_colour(ev.channel_id, ev.channel_name)
        self._chip(odraw, ix, y + t.px(11), channel_label(ev.channel_name), colour, chip_f, text_ops)

        badge_f = font_for("LIVE", t.fs_small, bold=True)
        bw = int(odraw.textlength("LIVE", font=badge_f)) + t.px(26)
        bx = x + w - t.px(14) - bw
        odraw.rounded_rectangle([bx, y + t.px(11), bx + bw, y + t.px(11) + t.px(22)],
                                radius=t.px(11), fill=(*Palette.live, 220))
        dot_r = t.px(3)
        dcx, dcy = bx + t.px(11), y + t.px(11) + t.px(11)
        odraw.ellipse([dcx - dot_r, dcy - dot_r, dcx + dot_r, dcy + dot_r], fill=(255, 255, 255, 255))
        text_ops.append(((bx + t.px(17), dcy), "LIVE", badge_f, Palette.text, "lm"))

        # Row 2 — fixture.
        title_f = font_for(ev.title, t.fs_row, bold=True)
        text_ops.append(((ix, y + t.px(40)), self._fit(odraw, ev.title, title_f, iw),
                         title_f, Palette.text, "la"))

        # Row 3 — clock window + remaining time.
        meta_f = font_for("00:00", t.fs_small, bold=False)
        start_l = self._local(ev.start).strftime("%H:%M")
        stop_l = self._local(ev.stop).strftime("%H:%M")
        text_ops.append(((ix, y + t.px(69)), f"{start_l} — {stop_l}", meta_f, Palette.text_dim, "la"))
        left_f = font_for("متبقي", t.fs_small, bold=True)
        text_ops.append(((x + w - t.px(14), y + t.px(69)),
                         f"متبقي {fmt_duration(ev.stop - now)}", left_f, Palette.live_soft, "ra"))

        # Progress track.
        by = y + t.px(87)
        odraw.rounded_rectangle([ix, by, ix + iw, by + t.px(4)], radius=t.px(2), fill=Palette.track)
        p = ev.progress(now)
        if p > 0:
            odraw.rounded_rectangle([ix, by, ix + max(t.px(4), int(iw * p)), by + t.px(4)],
                                    radius=t.px(2), fill=(*Palette.live, 235))
        return h

    def _upcoming_row(self, odraw, x, y, w, ev, now, index, text_ops) -> int:
        t = self.t
        h = t.px(56)
        fill = Palette.card if index % 2 == 0 else Palette.card_alt
        odraw.rounded_rectangle([x, y, x + w, y + h], radius=t.px(9), fill=fill)

        local = self._local(ev.start)
        time_f = font_for("19:30", t.fs_time, bold=True)
        text_ops.append(((x + t.px(14), y + t.px(13)), local.strftime("%H:%M"),
                         time_f, Palette.next_soft, "la"))

        # A day marker only when the event is not today — keeps the column calm.
        if local.date() != self._local(now).date():
            day_f = font_for("غداً", t.fs_small, bold=False)
            label = "غداً" if (local.date() - self._local(now).date()).days == 1 else \
                local.strftime("%d/%m")
            text_ops.append(((x + t.px(14), y + t.px(38)), label, day_f, Palette.text_faint, "la"))

        tx = x + t.px(96)
        colour = channel_colour(ev.channel_id, ev.channel_name)
        chip_f = font_for(ev.channel_name, t.fs_small, bold=True)

        cd_f = font_for("بعد", t.fs_small, bold=True)
        cd = fmt_countdown(ev.start - now)
        cd_w = int(measure(odraw, cd, cd_f))
        avail = w - (tx - x) - t.px(16) - cd_w - t.px(12)

        title_f = font_for(ev.title, t.fs_row, bold=True)
        text_ops.append(((tx, y + t.px(7)), self._fit(odraw, ev.title, title_f, avail),
                         title_f, Palette.text, "la"))

        chip_w = self._chip(odraw, tx, y + t.px(32), channel_label(ev.channel_name),
                            colour, chip_f, text_ops)
        if ev.subtitle:
            sub_f = font_for(ev.subtitle, t.fs_small, bold=False)
            sx = tx + chip_w + t.px(8)
            text_ops.append(((sx, y + t.px(37)),
                             self._fit(odraw, ev.subtitle, sub_f, avail - chip_w - t.px(8)),
                             sub_f, Palette.text_faint, "la"))

        text_ops.append(((x + w - t.px(14), y + t.px(21)), cd, cd_f, Palette.next_, "ra"))
        return h

    def _empty(self, odraw, x, y, w, message, text_ops) -> None:
        t = self.t
        h = t.px(70)
        odraw.rounded_rectangle([x, y, x + w, y + h], radius=t.px(9), fill=Palette.card)
        fnt = font_for(message, t.fs_meta, bold=False)
        text_ops.append(((x + w / 2, y + h / 2), message, fnt, Palette.text_faint, "mm"))

    def _local(self, dt: datetime) -> datetime:
        return dt.astimezone(self.tz) if self.tz else dt.astimezone()

    # -- page assembly -------------------------------------------------------
    def _build_page(self, now: datetime, live: list, upcoming: list, page: int,
                    pages: int, updated: datetime | None) -> None:
        t = self.t
        base = self._bg.copy()
        overlay = Image.new("RGBA", (t.w, t.h), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        text_ops: list = []

        # --- header
        bar_h = t.px(38)
        odraw.rounded_rectangle([t.pad, t.px(26), t.pad + t.px(5), t.px(26) + bar_h],
                                radius=t.px(3), fill=(*Palette.accent, 255))
        brand_f = font_for(self.title, t.fs_brand, bold=True)
        text_ops.append(((t.pad + t.px(16), t.px(24)), self.title, brand_f, Palette.text, "la"))
        sub_f = font_for(self.subtitle, t.fs_small, bold=False)
        text_ops.append(((t.pad + t.px(17), t.px(56)), self.subtitle, sub_f, Palette.text_dim, "la"))

        # Clock area: reserve a fixed box so per-frame repaints stay cheap.
        clock_f = font_for("00:00:00", t.fs_clock, bold=True)
        cw = int(odraw.textlength("00:00:00", font=clock_f)) + t.px(6)
        cx1 = t.w - t.pad - cw
        self._clock_box = (cx1, t.px(18), t.w - t.pad, t.px(18) + t.fs_clock + t.px(8))

        date_f = font_for("date", t.fs_small, bold=False)
        text_ops.append(((t.w - t.pad, t.px(64)), arabic_date(self._local(now)),
                         date_f, Palette.text_dim, "ra"))

        # --- columns
        usable = t.w - t.pad * 2
        left_w = int(usable * 0.46)
        right_w = usable - left_w - t.gutter
        lx, rx = t.pad, t.pad + left_w + t.gutter
        top = t.header_h + t.px(20)

        y = self._section_header(odraw, lx, top, left_w, "على الهواء الآن",
                                 "LIVE NOW", len(live), Palette.live, text_ops)
        page_live = live[page * LIVE_PER_PAGE:(page + 1) * LIVE_PER_PAGE]
        if page_live:
            for ev in page_live:
                y += self._live_card(odraw, lx, y, left_w, ev, now, text_ops) + t.px(8)
        else:
            self._empty(odraw, lx, y, left_w,
                        "لا يوجد بث مباشر حالياً" if not live else "تابع الصفحة التالية",
                        text_ops)

        y = self._section_header(odraw, rx, top, right_w, "البث القادم",
                                 "UP NEXT", len(upcoming), Palette.next_, text_ops)
        page_next = upcoming[page * UPCOMING_PER_PAGE:(page + 1) * UPCOMING_PER_PAGE]
        if page_next:
            for i, ev in enumerate(page_next):
                y += self._upcoming_row(odraw, rx, y, right_w, ev, now, i, text_ops) + t.px(8)
        else:
            self._empty(odraw, rx, y, right_w, "لا توجد مباريات مجدولة", text_ops)

        # --- footer
        fy = t.h - t.footer_h
        odraw.line([(t.pad, fy), (t.w - t.pad, fy)], fill=(38, 48, 76, 255), width=max(1, t.px(1)))
        foot_f = font_for("updated", t.fs_small, bold=False)
        stamp = self._local(updated).strftime("%H:%M") if updated else "—"
        text_ops.append(((t.pad, fy + t.px(19)), f"آخر تحديث للبيانات: {stamp}",
                         foot_f, Palette.text_faint, "la"))
        text_ops.append(((t.w - t.pad, fy + t.px(19)), "Unified MENA EPG · مصادر رسمية",
                         foot_f, Palette.text_faint, "ra"))

        if pages > 1:
            dot_r, gap = t.px(4), t.px(14)
            total = pages * gap - (gap - dot_r * 2)
            sx = (t.w - total) // 2
            cy = fy + t.px(21)
            for i in range(pages):
                cxp = sx + i * gap + dot_r
                on = i == page
                odraw.ellipse([cxp - dot_r, cy - dot_r, cxp + dot_r, cy + dot_r],
                              fill=(*Palette.accent, 255) if on else (255, 255, 255, 60))

        canvas = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        for xy, text, fnt, fill, anchor in text_ops:
            self._text(draw, xy, text, fnt, fill, anchor)

        self._canvas = canvas
        self._clock_patch = canvas.crop(self._clock_box).copy()

    # -- public --------------------------------------------------------------
    def frame(self, now: datetime, live: list, upcoming: list, *,
              page: int = 0, pages: int = 1, updated: datetime | None = None) -> Image.Image:
        """Return the current frame. Rebuilds the page only when its contents
        change; otherwise just repaints the ticking clock."""
        key = (
            page, pages,
            tuple((e.channel_id, e.start) for e in live[page * LIVE_PER_PAGE:(page + 1) * LIVE_PER_PAGE]),
            tuple((e.channel_id, e.start) for e in upcoming[page * UPCOMING_PER_PAGE:(page + 1) * UPCOMING_PER_PAGE]),
            self._local(now).strftime("%Y%m%d%H%M"),  # minute-level meta refresh
        )
        if key != self._page_key or self._canvas is None:
            self._build_page(now, live, upcoming, page, pages, updated)
            self._page_key = key

        canvas = self._canvas
        assert canvas is not None and self._clock_patch is not None and self._clock_box is not None
        canvas.paste(self._clock_patch, self._clock_box[:2])

        draw = ImageDraw.Draw(canvas)
        t = self.t
        clock_f = font_for("00:00:00", t.fs_clock, bold=True)
        draw.text((t.w - t.pad, t.px(18)), self._local(now).strftime("%H:%M:%S"),
                  font=clock_f, fill=Palette.text, anchor="ra")
        return canvas

    @staticmethod
    def page_count(live: list, upcoming: list) -> int:
        pages = max(
            math.ceil(len(live) / LIVE_PER_PAGE) if live else 1,
            math.ceil(len(upcoming) / UPCOMING_PER_PAGE) if upcoming else 1,
        )
        return max(1, min(MAX_PAGES, pages))
