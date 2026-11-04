package com.saudi.privatevault

import android.app.Activity
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * The route as a floating card over the map, as an EFB shows a flight plan: from and
 * to with the totals (distance, time, fuel), each leg with its magnetic heading,
 * distance, time and fuel (the active one lit), the fuel left and the reserve, and the
 * route's actions. Drag it by its head; fold it to its head; it follows every change.
 */
class RoutePanel(
    private val act: Activity,
    private val host: FrameLayout,
    private val plan: () -> FlightPlan,
    private val actions: List<Pair<String, () -> Unit>>,
) {
    private val d = act.resources.displayMetrics.density
    private fun dp(v: Int) = (v * d).toInt()
    private val white = 0xFFFFFFFF.toInt()
    private val grey = 0xFF8E8E93.toInt()
    private val magenta = 0xFFE040FB.toInt()
    private var card: LinearLayout? = null
    private var shown = ""
    private var folded = VaultLock.prefs(act).getBoolean("route_folded", false)
    var topOffset = 0

    private fun tv(s: CharSequence, size: Float, color: Int = white, bold: Boolean = false, mono: Boolean = false) = TextView(act).apply {
        text = s; textSize = size; setTextColor(color)
        typeface = when { mono && bold -> Typeface.create(Typeface.MONOSPACE, Typeface.BOLD); mono -> Typeface.MONOSPACE; bold -> EfbUi.MEDIUM; else -> Typeface.DEFAULT }
        layoutDirection = View.LAYOUT_DIRECTION_LTR; textDirection = View.TEXT_DIRECTION_LTR
    }

    /** Drawn again only when the route, its active leg or its settings change. */
    fun refresh(force: Boolean = false) {
        val p = plan()
        val key = p.points.joinToString(",") { it.id } + "|${p.active}|${p.direct?.id}|${p.altitude}|${p.tas}|${p.windDir}|${p.windKt}|${p.gph}|${p.fuelOnBoard}|$folded"
        if (!force && key == shown && card != null) return
        shown = key
        val old = card
        val keepX = old?.translationX ?: 0f
        val keepY = old?.translationY ?: 0f
        old?.let { host.removeView(it) }
        card = null
        if (p.points.size < 2) return
        build(p, keepX, keepY)
    }

    private fun build(p: FlightPlan, x: Float, y: Float) {
        val legs = p.legs()
        val dist = legs.sumOf { it.dist }; val min = legs.sumOf { it.minutes }; val fuel = legs.sumOf { it.fuel }
        val c = LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable().apply { cornerRadius = dp(18).toFloat(); setColor(0xF0121418.toInt()); setStroke(dp(1), 0xFF30353C.toInt()) }
            elevation = dp(14).toFloat()
            setPadding(dp(14), dp(10), dp(10), dp(12))
            isClickable = true
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            translationX = x; translationY = y
        }
        // Head: the route, the totals, fold and close.
        val head = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val names = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
        names.addView(tv("${p.points.first().id}  →  ${p.points.last().id}", 17f, white, bold = true))
        names.addView(tv("%.1f nm  ·  %s  ·  %.1f gal  ·  %,d ft".format(dist, FlightPlan.hm(min), fuel, p.altitude), 12.5f, grey))
        head.addView(names, LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(tv(if (folded) "⌄" else "⌃", 22f).apply {
            setPadding(dp(12), 0, dp(10), dp(2))
            setOnClickListener { folded = !folded; VaultLock.prefs(act).edit().putBoolean("route_folded", folded).apply(); refresh(true) }
        })
        c.addView(head)
        var dx = 0f; var dy = 0f
        head.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { dx = c.translationX - e.rawX; dy = c.translationY - e.rawY }
                MotionEvent.ACTION_MOVE -> { c.translationX = e.rawX + dx; c.translationY = e.rawY + dy }
            }
            false
        }

        if (!folded) {
            c.addView(View(act).apply { setBackgroundColor(0xFF2C2C2E.toInt()) }, LinearLayout.LayoutParams(-1, 1).apply { setMargins(0, dp(8), 0, dp(6)) })
            // The legs, as a table.
            val table = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
            fun row(cells: List<String>, color: Int, bold: Boolean, lit: Boolean) {
                val r = LinearLayout(act).apply {
                    orientation = LinearLayout.HORIZONTAL; setPadding(dp(6), dp(5), dp(6), dp(5))
                    if (lit) background = GradientDrawable().apply { cornerRadius = dp(8).toFloat(); setColor(0x33E040FB) }
                }
                val w = intArrayOf(96, 52, 56, 52, 48)
                for ((i, s) in cells.withIndex()) r.addView(tv(s, 13f, if (i == 0 && lit) magenta else color, bold, mono = i > 0).apply {
                    gravity = if (i == 0) Gravity.START else Gravity.END; maxLines = 1
                }, LinearLayout.LayoutParams(dp(w[i]), -2))
                table.addView(r)
            }
            row(listOf("LEG", "MH", "NM", "ETE", "GAL"), grey, true, false)
            val activeTo = p.target()
            for ((i, l) in legs.withIndex()) {
                val lit = p.direct == null && i + 1 == p.active
                row(listOf("${l.from.id.take(5)}›${l.to.id.take(5)}", Nav.deg(l.mh), "%.1f".format(l.dist), FlightPlan.hm(l.minutes), "%.1f".format(l.fuel)), white, false, lit)
            }
            if (p.direct != null && activeTo != null) row(listOf("D→ ${activeTo.id}", "", "", "", ""), magenta, true, true)
            c.addView(ScrollView(act).apply { addView(HorizontalScrollView(act).apply { isHorizontalScrollBarEnabled = false; addView(table) }) },
                LinearLayout.LayoutParams(-2, -2).apply { height = if (legs.size > 6) dp(220) else -2 })

            // Fuel left and the VFR day reserve (91.151: 30 minutes).
            val left = p.fuelOnBoard - fuel
            val reserve = p.gph * 0.5
            val ok = left >= reserve
            c.addView(tv((if (ok) "✓ " else "⚠ ") + act.getString(R.string.route_fuel_left, left, FlightPlan.hm(left / p.gph * 60)), 12.5f,
                if (ok) 0xFF30D158.toInt() else 0xFFFF9F0A.toInt(), bold = true).apply { setPadding(dp(6), dp(8), 0, dp(4)) })
            c.addView(tv(act.getString(R.string.route_settings, p.tas, p.windDir, p.windKt, p.gph), 11.5f, grey).apply { setPadding(dp(6), 0, 0, dp(8)) })

            // The route's actions, as chips.
            val chips = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }
            for ((label, go) in actions) chips.addView(tv(label, 13f, white, bold = true).apply {
                background = GradientDrawable().apply { cornerRadius = dp(14).toFloat(); setColor(0xFF1C1F24.toInt()); setStroke(dp(1), 0xFF3A3F47.toInt()) }
                setPadding(dp(12), dp(7), dp(12), dp(7))
                setOnClickListener { go() }
            }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
            c.addView(HorizontalScrollView(act).apply { isHorizontalScrollBarEnabled = false; addView(chips) })
        }
        val maxW = minOf((act.resources.displayMetrics.widthPixels * 0.92).toInt(), dp(380))
        host.addView(c, FrameLayout.LayoutParams(maxW, -2, Gravity.TOP or Gravity.START).apply { leftMargin = dp(10); topMargin = topOffset + dp(8) })
        card = c
    }

    fun hide() { card?.let { host.removeView(it) }; card = null; shown = "" }
}
