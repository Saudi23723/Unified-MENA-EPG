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
import android.widget.TextView

/**
 * The flight plan bar across the top of the chart, laid out the way an EFB lays it out:
 *
 *  · on the left, the aeroplane, the performance profile it is flown on, and the cruising altitude,
 *    each its own box and each a tap away from being changed;
 *  · along the middle, the route as a row of chips — a tap on one opens that waypoint (go direct,
 *    put it in the route, take it out), a tap between two opens the leg (fly it, direct to its end,
 *    remove it);
 *  · on the right, the buttons that act on the whole plan;
 *  · underneath, the figures a pilot reads at a glance: distance, time, the clock time of arrival,
 *    fuel, the wind along the route, and how much longer the route is than the straight line.
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
    private val grey = 0xFF8E9299.toInt()
    private val blue = 0xFF2F80ED.toInt()
    private val panel = 0xF0151A21.toInt()
    private var card: LinearLayout? = null
    private var shown = ""
    private var folded = VaultLock.prefs(act).getBoolean("route_folded", false)
    var topOffset = 0

    /** What the bar can do beyond the plain actions; the map fills these in. */
    var onEdit: (() -> Unit)? = null
    var onNavlog: (() -> Unit)? = null
    var onProfile: (() -> Unit)? = null
    var onProcedure: (() -> Unit)? = null
    var onEtd: (() -> Unit)? = null
    var onAircraft: (() -> Unit)? = null
    var onAltitude: (() -> Unit)? = null
    var onWaypoint: ((Int) -> Unit)? = null
    var onLeg: ((Int) -> Unit)? = null

    /**
     * The colour a route element is drawn in, by what it is: fields one colour, airways another,
     * navaids another again, and anything the app could not place in red — so a bad entry shows
     * itself at a glance instead of failing quietly.
     */
    private fun chipColour(id: String, known: Boolean): Int = when {
        !known -> 0xFFE05A5A.toInt()                                  // not found
        Regex("^[A-Z]{1,2}\\d{1,3}[A-Z]?$").matches(id) -> 0xFFE0A354.toInt()   // airway, V6 / J121
        id.length == 3 && Regex("^[A-Z]{3}$").matches(id) -> 0xFF8E7CE0.toInt()   // navaid
        id.length >= 5 && Regex("^[A-Z]{5}$").matches(id) -> 0xFF6E8BE0.toInt()   // a named fix
        Regex("^[A-Z]?\\d{2,}").containsMatchIn(id) -> 0xFF5C8DBE.toInt()        // a point by its numbers
        else -> 0xFF4A90D9.toInt()                                    // an airport
    }

    private fun tv(s: CharSequence, size: Float, color: Int = white, bold: Boolean = false, mono: Boolean = false) = TextView(act).apply {
        text = s; textSize = size; setTextColor(color)
        typeface = when { mono && bold -> Typeface.create(Typeface.MONOSPACE, Typeface.BOLD); mono -> Typeface.MONOSPACE; bold -> EfbUi.MEDIUM; else -> Typeface.DEFAULT }
        layoutDirection = View.LAYOUT_DIRECTION_LTR; textDirection = View.TEXT_DIRECTION_LTR
    }

    private fun box(fill: Int, radius: Int = 7, stroke: Int = 0) = GradientDrawable().apply {
        cornerRadius = dp(radius).toFloat(); setColor(fill)
        if (stroke != 0) setStroke(dp(1), stroke)
    }

    fun refresh(force: Boolean = false) {
        val p = plan()
        val key = p.points.joinToString(",") { it.id } + "|${p.active}|${p.direct?.id}|${p.altitude}|${p.tas}|${p.windDir}|" +
            "${p.windKt}|${p.gph}|${p.fuelOnBoard}|${p.etdMin}|${p.legWinds.size}|$folded|${AircraftProfile.current(act).name}"
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

    /** One of the small stacked boxes on the left: a label over a value. */
    private fun stack(value: String, sub: String?, go: (() -> Unit)?): LinearLayout =
        LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            background = box(0xFF20262E.toInt())
            setPadding(dp(9), dp(5), dp(9), dp(5))
            addView(tv(value, 12.5f, white, bold = true).apply { gravity = Gravity.CENTER })
            if (sub != null) addView(tv(sub, 10f, grey).apply { gravity = Gravity.CENTER })
            go?.let { setOnClickListener { _ -> it() } }
        }

    /** A figure under the bar: its name small and grey above, its value below. */
    private fun figure(label: String, value: String, color: Int = white): LinearLayout =
        LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, dp(16), 0)
            addView(tv(label, 9f, grey, bold = true).apply { letterSpacing = 0.08f })
            addView(tv(value, 13.5f, color, bold = true))
        }

    private fun build(p: FlightPlan, x: Float, y: Float) {
        val profile = AircraftProfile.current(act)
        val res = Navlog.build(
            p.points, p.altitude, profile,
            { i -> p.legWinds[i]?.let { it.first to it.second } ?: (p.windDir to p.windKt) },
            p.fuelOnBoard, p.reserveMin, null, null, withMora = false,
        )
        val c = LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL
            background = box(panel, 14, 0xFF2B323C.toInt())
            elevation = dp(12).toFloat()
            setPadding(dp(8), dp(8), dp(8), dp(8))
            isClickable = true
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            translationX = x; translationY = y
        }

        // ---- the top line: aeroplane and altitude, the route chips, the plan's own buttons ----
        val top = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }
        val left = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
        val tail = Aircraft.all(act).getOrNull(VaultLock.prefs(act).getInt("wb_current", 0))?.name ?: "AIRCRAFT"
        left.addView(stack(tail.take(10), null) { onAircraft?.invoke() }, LinearLayout.LayoutParams(dp(92), -2))
        left.addView(stack(profile.name.take(12), "${Math.round(profile.cruiseTas)} kt · ${EfbUi.num(profile.cruiseGph)} gph") { onProfile?.invoke() },
            LinearLayout.LayoutParams(dp(92), -2).apply { topMargin = dp(4) })
        left.addView(stack("%,d'".format(p.altitude), null) { onAltitude?.invoke() },
            LinearLayout.LayoutParams(dp(92), -2).apply { topMargin = dp(4) })
        top.addView(left)

        val mid = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(8), 0, dp(8), 0) }
        // The route: a chip for every point, with the leg between two of them tappable in its own right.
        val chips = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val activeTo = p.target()
        for ((i, w) in p.points.withIndex()) {
            if (i > 0) chips.addView(TextView(act).apply {
                text = "›"; textSize = 15f; setTextColor(grey); gravity = Gravity.CENTER
                setPadding(dp(5), dp(3), dp(5), dp(3))
                setOnClickListener { onLeg?.invoke(i) }
            })
            val lit = activeTo != null && p.direct == null && w.id == activeTo.id && i == p.active
            val known = w.lat != 0.0 || w.lon != 0.0
            val colour = chipColour(w.id, known)
            chips.addView(tv(w.id, 13f, if (lit) white else 0xFF0E1419.toInt(), bold = true).apply {
                background = box(if (lit) white else colour, 13)
                if (lit) setTextColor(0xFF0E1419.toInt())
                setPadding(dp(11), dp(6), dp(11), dp(6))
                maxLines = 1
                setOnClickListener { onWaypoint?.invoke(i) }
            }, LinearLayout.LayoutParams(-2, -2))
        }
        p.direct?.let { dt ->
            chips.addView(tv("D→ ${dt.id}", 13f, white, bold = true).apply {
                background = box(0xFFE040FB.toInt(), 13); setPadding(dp(11), dp(6), dp(11), dp(6))
                setOnClickListener { plan().direct = null; plan().save(act); refresh(true) }
            }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(6) })
        }
        mid.addView(HorizontalScrollView(act).apply { isHorizontalScrollBarEnabled = false; addView(chips) })
        top.addView(mid, LinearLayout.LayoutParams(0, -2, 1f))

        val right = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
        fun sideBtn(label: String, go: () -> Unit) = right.addView(tv(label, 12f, white, bold = true).apply {
            gravity = Gravity.CENTER
            background = box(0xFF20262E.toInt())
            setPadding(dp(10), dp(6), dp(10), dp(6))
            setOnClickListener { go() }
        }, LinearLayout.LayoutParams(dp(86), -2).apply { topMargin = dp(4) })
        sideBtn("Procedure") { onProcedure?.invoke() }
        sideBtn("Routes (${p.points.size})") { onEdit?.invoke() }
        sideBtn(p.etdMin?.let { "ETD %02d:%02d".format(it / 60, it % 60) } ?: "ETD") { onEtd?.invoke() }
        top.addView(right)
        c.addView(top)

        // Turn the route round, or clear it: the two the route editor keeps beside the chips.
        val tools = LinearLayout(act).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.END
            setPadding(0, dp(5), dp(90), 0)
        }
        fun tool(label: String, go: () -> Unit) = tools.addView(tv(label, 12f, white, bold = true).apply {
            gravity = Gravity.CENTER
            background = box(0xFF20262E.toInt())
            setPadding(dp(14), dp(5), dp(14), dp(5))
            setOnClickListener { go() }
        }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(6) })
        tool("⇄") { actions.getOrNull(2)?.second?.invoke() }
        tool("Clear") { actions.getOrNull(5)?.second?.invoke() }
        c.addView(tools)

        if (!folded) {
            c.addView(View(act).apply { setBackgroundColor(0xFF2B323C.toInt()) },
                LinearLayout.LayoutParams(-1, 1).apply { setMargins(0, dp(8), 0, dp(7)) })

            // ---- the figures, and the three buttons that open the plan in full ----
            val row = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            val fig = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }
            fig.addView(figure("DIST", "%.0f nm".format(res.distNm)))
            fig.addView(figure("ETE", "%dh%02dm".format(res.minutes.toInt() / 60, res.minutes.toInt() % 60)))
            fig.addView(figure("ETA", p.clock(res.minutes), 0xFF64D2FF.toInt()))
            fig.addView(figure("FUEL", "%.1f g".format(res.fuelGal), if (res.reserveKept) white else 0xFFFF453A.toInt()))
            // The wind along the whole route: how much it helps or holds, on the average.
            val comp = res.rows.sumOf { r ->
                val rel = Math.toRadians(r.windDir - r.tc)
                -Math.cos(rel) * r.windKt * r.distNm
            } / res.distNm.coerceAtLeast(0.1)
            fig.addView(figure("WIND", "%d kt %s".format(Math.abs(Math.round(comp).toInt()), if (comp >= 0) "tail" else "head"),
                if (comp >= 0) 0xFF30D158.toInt() else 0xFFFF9F0A.toInt()))
            // How far the route goes beyond the straight line between its ends.
            val straight = Nav.distanceNm(p.points.first().lat, p.points.first().lon, p.points.last().lat, p.points.last().lon)
            fig.addView(figure("RTE CORR", "%.0f nm".format((res.distNm - straight).coerceAtLeast(0.0))))
            row.addView(HorizontalScrollView(act).apply { isHorizontalScrollBarEnabled = false; addView(fig) },
                LinearLayout.LayoutParams(0, -2, 1f))
            fun act3(label: String, go: () -> Unit) = row.addView(tv(label, 12.5f, white, bold = true).apply {
                gravity = Gravity.CENTER
                background = box(0xFF20262E.toInt())
                setPadding(dp(11), dp(8), dp(11), dp(8))
                setOnClickListener { go() }
            }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(5) })
            act3("Edit") { onEdit?.invoke() }
            act3("NavLog") { onNavlog?.invoke() }
            act3("Profile") { actions.getOrNull(3)?.second?.invoke() }
            c.addView(row)
            if (res.warnings.isNotEmpty()) c.addView(tv("⚠ " + res.warnings.first(), 11f, 0xFFFFB020.toInt())
                .apply { setPadding(dp(2), dp(6), 0, 0); maxLines = 2 })
        }

        // Folded to the chips alone; dragged anywhere by its left boxes.
        c.setOnLongClickListener {
            folded = !folded
            VaultLock.prefs(act).edit().putBoolean("route_folded", folded).apply()
            refresh(true); true
        }
        var dx = 0f; var dy = 0f
        left.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { dx = c.translationX - e.rawX; dy = c.translationY - e.rawY }
                MotionEvent.ACTION_MOVE -> { c.translationX = e.rawX + dx; c.translationY = e.rawY + dy }
            }
            false
        }
        val maxW = minOf((act.resources.displayMetrics.widthPixels * 0.97).toInt(), dp(760))
        host.addView(c, FrameLayout.LayoutParams(maxW, -2, Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = topOffset + dp(6) })
        card = c
    }

    fun hide() { card?.let { host.removeView(it) }; card = null; shown = "" }
}
