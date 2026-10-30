package com.saudi.privatevault

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Shader
import android.view.View

/**
 * The route seen from the side: the ground under every half mile of it,
 * the planned altitude, the highest terrain and how far above it the plan
 * stays, each waypoint, and the aircraft when flying.
 */
@SuppressLint("ViewConstructor")
class ProfileView(ctx: Context, private val plan: FlightPlan) : View(ctx) {

    class Sample(val nm: Double, val ft: Float)

    var samples: List<Sample> = emptyList()
    var marks: List<Pair<Double, String>> = emptyList()
    var aircraftNm: Double? = null
    var aircraftFt: Double? = null

    private val d = ctx.resources.displayMetrics.density
    private val ground = Paint(Paint.ANTI_ALIAS_FLAG)
    private val groundEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF8D6E63.toInt(); style = Paint.Style.STROKE; strokeWidth = 1.5f * d }
    private val planLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFE040FB.toInt(); strokeWidth = 3 * d }
    private val grid = Paint().apply { color = 0x33FFFFFF; strokeWidth = d }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.DIM; textSize = 10 * d }
    private val strong = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.TEXT; textSize = 12 * d; isFakeBoldText = true }
    private val danger = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFE53935.toInt(); strokeWidth = 1.5f * d; pathEffect = DashPathEffect(floatArrayOf(6 * d, 4 * d), 0f) }
    private val plane = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.ACCENT }

    init { setBackgroundColor(0xFF0B1220.toInt()) }

    /** Reads the ground along the route; call off the main thread. */
    fun sample() {
        val out = ArrayList<Sample>()
        val m = ArrayList<Pair<Double, String>>()
        var at = 0.0
        for (i in 0 until plan.points.size) {
            val w = plan.points[i]
            m.add(at to w.id)
            if (i == plan.points.size - 1) break
            val n = plan.points[i + 1]
            val len = Nav.distanceNm(w.lat, w.lon, n.lat, n.lon)
            val crs = Nav.bearingTrue(w.lat, w.lon, n.lat, n.lon)
            var s = 0.0
            while (s < len) {
                val g = Nav.destination(w.lat, w.lon, crs, s)
                out.add(Sample(at + s, Terrain.elevationFt(g.latitude, g.longitude, wait = true) ?: 0f))
                s += 0.5
            }
            at += len
        }
        plan.points.lastOrNull()?.let { out.add(Sample(at, Terrain.elevationFt(it.lat, it.lon, wait = true) ?: 0f)) }
        samples = out
        marks = m
        post { invalidate() }
    }

    override fun onDraw(c: Canvas) {
        if (samples.size < 2) {
            c.drawText(context.getString(R.string.profile_loading), 16 * d, height / 2f, strong)
            return
        }
        val total = samples.last().nm.coerceAtLeast(0.1)
        val top = maxOf(samples.maxOf { it.ft }.toDouble(), plan.altitude.toDouble(), aircraftFt ?: 0.0) + 1500
        val l = 40 * d; val r = width - 10 * d; val t = 24 * d; val b = height - 22 * d
        fun sx(nm: Double) = (l + nm / total * (r - l)).toFloat()
        fun sy(ft: Double) = (b - ft / top * (b - t)).toFloat()
        var g = 0.0
        while (g <= top) {
            c.drawLine(l, sy(g), r, sy(g), grid)
            c.drawText("%,d".format(g.toInt()), 2 * d, sy(g) + 4 * d, label)
            g += if (top > 12000) 4000.0 else 2000.0
        }
        val path = Path().apply {
            moveTo(sx(0.0), b)
            for (s in samples) lineTo(sx(s.nm), sy(s.ft.toDouble()))
            lineTo(sx(total), b)
            close()
        }
        ground.shader = LinearGradient(0f, t, 0f, b, 0xFF8D6E63.toInt(), 0xFF3E2723.toInt(), Shader.TileMode.CLAMP)
        c.drawPath(path, ground)
        c.drawPath(path, groundEdge)
        c.drawLine(sx(0.0), sy(plan.altitude.toDouble()), sx(total), sy(plan.altitude.toDouble()), planLine)
        val high = samples.maxByOrNull { it.ft }!!
        val clearance = plan.altitude - high.ft
        c.drawLine(sx(high.nm), sy(high.ft.toDouble()), sx(high.nm), sy(plan.altitude.toDouble()), danger)
        strong.color = if (clearance < 1000) 0xFFE53935.toInt() else if (clearance < 2000) 0xFFFDD835.toInt() else EfbUi.GOOD
        c.drawText("▲ %,d ft · %+,d ft".format(high.ft.toInt(), clearance.toInt()), (sx(high.nm) - 40 * d).coerceIn(l, r - 140 * d), 16 * d, strong)
        strong.color = EfbUi.TEXT
        for ((nm, id) in marks) {
            c.drawLine(sx(nm), t, sx(nm), b, grid)
            c.drawText(id, sx(nm) - 12 * d, height - 6 * d, label)
        }
        val an = aircraftNm; val af = aircraftFt
        if (an != null && af != null && an in 0.0..total) {
            c.drawCircle(sx(an), sy(af), 6 * d, plane)
        }
    }
}
