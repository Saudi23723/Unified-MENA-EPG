package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.concurrent.thread

/**
 * The air above the route, sliced the way a briefer draws it: distance along the bottom, height up
 * the side, the ground as a grey mass, and at each station and each two thousand feet the wind as a
 * number in knots coloured by what it does to the flight (green helps, red hinders, by how much of
 * it is along the track), with the freezing level drawn through it and the planned height as a
 * pink line. The wind is the same forecast the nav log uses.
 */
class WindSectionActivity : BaseActivity() {
    override val alwaysDark = true

    private class Cell(val dir: Int, val kt: Int, val temp: Int?)

    private lateinit var plan: FlightPlan
    private lateinit var chart: Chart
    private lateinit var note: TextView
    private val levels = listOf(3000, 5000, 7000, 9000, 11000, 13000, 15000, 17000)
    private val stations = 8

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = EfbUi.BG
        window.navigationBarColor = EfbUi.BG
        plan = FlightPlan.load(this)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(EfbUi.BG) }
        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0xFF121820.toInt()); setPadding(EfbUi.dp(this@WindSectionActivity, 6), EfbUi.dp(this@WindSectionActivity, 8), EfbUi.dp(this@WindSectionActivity, 14), EfbUi.dp(this@WindSectionActivity, 8))
        }
        head.addView(TextView(this).apply {
            text = "✕"; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(EfbUi.dp(this@WindSectionActivity, 42), EfbUi.dp(this@WindSectionActivity, 40)); setOnClickListener { finish() }
        })
        head.addView(EfbUi.text(this, "WIND CROSS-SECTION", 13f, EfbUi.TEXT, bold = true).apply { letterSpacing = 0.1f })
        root.addView(head)
        chart = Chart(this)
        root.addView(chart, LinearLayout.LayoutParams(-1, 0, 1f))
        note = EfbUi.text(this, "Reading the winds…", 12f, EfbUi.DIM).apply { setPadding(EfbUi.dp(this@WindSectionActivity, 12), EfbUi.dp(this@WindSectionActivity, 6), EfbUi.dp(this@WindSectionActivity, 12), EfbUi.dp(this@WindSectionActivity, 10)) }
        root.addView(note)
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            root.setPadding(0, bars.top, 0, bars.bottom); ins
        }
        if (plan.points.size < 2) { note.text = "No route yet. Put one in the flight plan first."; return }
        load()
    }

    private fun load() {
        val pts = plan.points.toList()
        val legs = (1 until pts.size).map { Nav.distanceNm(pts[it - 1].lat, pts[it - 1].lon, pts[it].lat, pts[it].lon) }
        val total = legs.sum()
        chart.total = total
        chart.altitude = plan.altitude
        val app = applicationContext
        thread {
            // Where each station is, and what the ground does along the way.
            val where = ArrayList<Triple<Double, Double, Double>>()   // distance, lat, lon
            val course = ArrayList<Double>()
            for (i in 0 until stations) {
                val d = total * i / (stations - 1)
                var run = 0.0
                var k = 0
                while (k < legs.size - 1 && d > run + legs[k]) { run += legs[k]; k++ }
                val a = pts[k]; val b2 = pts[k + 1]
                val crs = Nav.bearingTrue(a.lat, a.lon, b2.lat, b2.lon)
                val g = Nav.destination(a.lat, a.lon, crs, (d - run).coerceIn(0.0, legs[k]))
                where.add(Triple(d, g.latitude, g.longitude)); course.add(crs)
            }
            chart.stationNm = where.map { it.first }
            chart.courses = course
            try { Terrain.prefetch(pts.minOf { it.lat } - 0.3, pts.minOf { it.lon } - 0.3, pts.maxOf { it.lat } + 0.3, pts.maxOf { it.lon } + 0.3) } catch (e: Throwable) { }
            chart.ground = (0..120).map { i ->
                val d = total * i / 120.0
                var run = 0.0; var k = 0
                while (k < legs.size - 1 && d > run + legs[k]) { run += legs[k]; k++ }
                val crs = Nav.bearingTrue(pts[k].lat, pts[k].lon, pts[k + 1].lat, pts[k + 1].lon)
                val g = Nav.destination(pts[k].lat, pts[k].lon, crs, (d - run).coerceIn(0.0, legs[k]))
                Srtm.best(g.latitude, g.longitude)
            }
            chart.postInvalidate()
            val cells = Array(stations) { arrayOfNulls<Cell>(levels.size) }
            chart.cells = cells
            for (s in 0 until stations) {
                for ((li, alt) in levels.withIndex()) {
                    val w = try { Winds.at(app, where[s].second, where[s].third, alt) } catch (e: Throwable) { null }
                    if (w != null) cells[s][li] = Cell(w.dirTrue, w.kt, w.tempC)
                }
                chart.postInvalidate()
                runOnUiThread { note.text = "Reading the winds… ${s + 1} of $stations stations" }
            }
            runOnUiThread {
                val got = cells.sumOf { row -> row.count { it != null } }
                note.text = if (got == 0) "No wind forecast could be read. Connect once and open this again."
                else "Green helps, red hinders, in knots along the track. Blue line: freezing level. Pink: your planned ${"%,d".format(plan.altitude)} ft. Open-Meteo model winds, not an official briefing."
            }
        }
    }

    private inner class Chart(c: Context) : View(c) {
        var total = 1.0
        var altitude = 5500
        var ground: List<Float> = emptyList()
        var cells: Array<Array<Cell?>> = emptyArray()
        var stationNm: List<Double> = emptyList()
        var courses: List<Double> = emptyList()
        private val d = resources.displayMetrics.density
        private val p = Paint(Paint.ANTI_ALIAS_FLAG)

        override fun onDraw(cv: Canvas) {
            val w = width.toFloat(); val h = height.toFloat()
            val l = 44 * d; val r = w - 10 * d; val t = 10 * d; val bt = h - 28 * d
            val top = 18000f
            fun x(nm: Double) = l + (r - l) * (nm / total).toFloat()
            fun y(ft: Float) = bt - (bt - t) * (ft / top)
            p.style = Paint.Style.FILL; p.color = 0xFF0C1624.toInt(); cv.drawRect(l, t, r, bt, p)
            // Height lines every two thousand feet.
            p.textSize = 10f * d
            for (ft in 0..18000 step 2000) {
                p.color = 0x22FFFFFF; p.strokeWidth = 1f; cv.drawLine(l, y(ft.toFloat()), r, y(ft.toFloat()), p)
                p.color = 0xFF8FA3BC.toInt(); p.textAlign = Paint.Align.RIGHT
                cv.drawText(if (ft == 0) "0" else "${ft / 1000}k", l - 4 * d, y(ft.toFloat()) + 4 * d, p)
            }
            // Distance along the bottom.
            p.textAlign = Paint.Align.CENTER
            for (i in stationNm.indices) {
                p.color = 0xFF8FA3BC.toInt()
                cv.drawText("%.0f".format(stationNm[i]), x(stationNm[i]), h - 10 * d, p)
            }
            p.textAlign = Paint.Align.RIGHT
            p.color = 0xFF8FA3BC.toInt(); cv.drawText("nm", l - 4 * d, h - 10 * d, p)
            p.textAlign = Paint.Align.LEFT
            // The wind numbers.
            for (s in cells.indices) {
                val crs = courses.getOrNull(s) ?: continue
                for (li in levels.indices) {
                    val c = cells[s][li] ?: continue
                    // Component along the track: positive is a tailwind.
                    val tail = -c.kt * Math.cos(Math.toRadians(c.dir - crs))
                    p.color = when {
                        tail > 4 -> 0xFF30D158.toInt(); tail < -4 -> 0xFFFF6B5E.toInt(); else -> 0xFFD0D8E4.toInt()
                    }
                    p.textAlign = Paint.Align.CENTER; p.isFakeBoldText = true; p.textSize = 11f * d
                    cv.drawText("%03d".format(c.dir) + "°", x(stationNm[s]), y(levels[li].toFloat()) - 2 * d, p)
                    p.isFakeBoldText = false; p.textSize = 10.5f * d
                    cv.drawText((if (tail >= 0) "+" else "−") + Math.abs(tail).toInt() + " kt", x(stationNm[s]), y(levels[li].toFloat()) + 11 * d, p)
                }
            }
            // The freezing level, found between the levels where the temperature crosses zero.
            val zero = Path(); var started = false
            for (s in cells.indices) {
                val row = cells[s]
                var fl: Float? = null
                for (li in 0 until levels.size - 1) {
                    val a = row[li]?.temp ?: continue; val b = row[li + 1]?.temp ?: continue
                    if (a > 0 && b <= 0) { fl = levels[li] + (levels[li + 1] - levels[li]) * (a.toFloat() / (a - b)); break }
                }
                if (fl != null) {
                    if (!started) { zero.moveTo(x(stationNm[s]), y(fl)); started = true } else zero.lineTo(x(stationNm[s]), y(fl))
                }
            }
            if (started) {
                p.style = Paint.Style.STROKE; p.strokeWidth = 2.5f * d; p.color = 0xFF4FC3FF.toInt(); cv.drawPath(zero, p)
                p.style = Paint.Style.FILL
            }
            // The ground.
            if (ground.size > 1) {
                val g = Path(); g.moveTo(l, bt)
                for (i in ground.indices) g.lineTo(l + (r - l) * i / (ground.size - 1), y(ground[i]))
                g.lineTo(r, bt); g.close()
                p.style = Paint.Style.FILL; p.color = 0xFF5B5148.toInt(); cv.drawPath(g, p)
            }
            // The planned height.
            p.style = Paint.Style.STROKE; p.strokeWidth = 2.5f * d; p.color = 0xFFFF4DA6.toInt()
            cv.drawLine(l, y(altitude.toFloat()), r, y(altitude.toFloat()), p)
            p.style = Paint.Style.FILL
        }
    }

    companion object {
        fun open(ctx: Context) = ctx.startActivity(Intent(ctx, WindSectionActivity::class.java))
    }
}
