package com.saudi1.tv

import android.app.Activity
import android.app.Dialog
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView

/** The first opening: a welcome, then a short tour of the remote (also in Settings → How to use). */
object Intro {
    private class Page(val icon: String, val title: String, val lines: List<String>)

    val seen get() = App.prefs.getBoolean("intro_done", false)

    fun show(a: Activity) {
        val d = a.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val who = Device.name.trim().substringBefore(' ').takeIf { it.length in 2..20 }
        val pages = listOf(
            Page("", if (who != null) "Welcome, $who" else "Welcome", listOf("Every match. Every movie. Every moment.", "Live sport, cinema and series from around the world — one remote away.")),
            Page("📺", "Live TV", listOf("OK  ·  full screen, and the channel list again", "▲ ▼  ·  next / previous channel", "◀  ·  the groups", "Hold OK  ·  ★ add to Favorites", "MENU (or hold OK in full screen)  ·  Search, Night mode, Multiview, Record, Last channels, TV Guide")),
            Page("🎬", "Movies and Series", listOf("They open on Continue watching — your place is always kept", "Hold OK on a poster  ·  ★ Favorites", "▲ on the first row  ·  sort: latest, A – Z, top rated", "While watching: MENU  ·  picture, audio, subtitles, speed, sleep timer")),
            Page("🪟", "Multiview", listOf("Two or four channels at the same time", "OK  ·  choose the channel of a screen", "Hold OK  ·  big → same size → small", "MENU  ·  full screen, another playlist, fill the screen")),
            Page("⏰", "TV Guide and Sports today", listOf("OK on a programme that is on  ·  watch it", "OK on a coming programme or match  ·  a reminder", "A minute before it starts the TV counts 10 seconds and changes the channel")),
            Page("⚙️", "Settings", listOf("Night mode: dimming, eye comfort, and by the clock", "Backup and Restore of your favorites and your place", "PIN lock for groups", "Check for update")),
        )
        val dlg = Dialog(a, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val box = LinearLayout(a).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(0xFF07131A.toInt(), 0xFF0B1020.toInt(), 0xFF1A0F2A.toInt()))
            setPadding(dp(80), dp(40), dp(80), dp(40))
        }
        val brand = TextView(a).apply { text = "SAUDI.TV"; textSize = 20f; letterSpacing = 0.3f; setTextColor(0xFF10B981.toInt()); setTypeface(typeface, Typeface.BOLD); gravity = Gravity.CENTER }
        val icon = TextView(a).apply { textSize = 46f; gravity = Gravity.CENTER }
        val title = TextView(a).apply { textSize = 44f; setTextColor(0xFFFFFFFF.toInt()); setTypeface(typeface, Typeface.BOLD); gravity = Gravity.CENTER }
        val body = TextView(a).apply { textSize = 20f; setTextColor(0xD9FFFFFF.toInt()); gravity = Gravity.CENTER; setLineSpacing(dp(8).toFloat(), 1f) }
        val dots = TextView(a).apply { textSize = 16f; setTextColor(0x99FFFFFF.toInt()); gravity = Gravity.CENTER }
        fun button(t: String) = TextView(a).apply {
            text = t; textSize = 19f; gravity = Gravity.CENTER; isFocusable = true; isClickable = true; setTypeface(typeface, Typeface.BOLD)
            setBackgroundResource(R.drawable.tile_bg); setTextColor(a.getColorStateList(R.color.on_focus))
            setPadding(dp(34), dp(13), dp(34), dp(13))
        }
        val next = button("Next  ▶"); val skip = button("Skip")
        val row = LinearLayout(a).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        row.addView(skip); row.addView(View(a), LinearLayout.LayoutParams(dp(18), 1)); row.addView(next)
        fun wrap() = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        box.addView(brand, wrap()); box.addView(icon, wrap().apply { topMargin = dp(18) }); box.addView(title, wrap().apply { topMargin = dp(6) })
        box.addView(body, wrap().apply { topMargin = dp(18) }); box.addView(row, wrap().apply { topMargin = dp(34) }); box.addView(dots, wrap().apply { topMargin = dp(22) })
        var i = 0
        fun done() { App.prefs.edit().putBoolean("intro_done", true).apply(); dlg.dismiss() }
        fun draw() {
            val p = pages[i]
            icon.text = p.icon; icon.visibility = if (p.icon.isEmpty()) View.GONE else View.VISIBLE
            title.text = p.title; title.textSize = if (i == 0) 54f else 40f
            body.text = p.lines.joinToString("\n"); body.textSize = if (i == 0) 23f else 19f
            next.text = when (i) { 0 -> "Show me around  ▶"; pages.size - 1 -> "Start watching"; else -> "Next  ▶" }
            skip.text = if (i == 0) "Skip" else "◀  Back"
            dots.text = pages.indices.joinToString("  ") { if (it == i) "●" else "○" }
        }
        next.setOnClickListener { if (i == pages.size - 1) done() else { i++; draw() } }
        skip.setOnClickListener { if (i == 0) done() else { i--; draw() } }
        dlg.setContentView(box)
        dlg.setOnCancelListener { App.prefs.edit().putBoolean("intro_done", true).apply() }
        draw()
        dlg.show()
        next.requestFocus()
    }
}
