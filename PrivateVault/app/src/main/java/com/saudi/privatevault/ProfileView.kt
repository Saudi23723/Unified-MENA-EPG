package com.saudi.privatevault

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.view.MotionEvent
import android.view.View

/**
 * The route seen from the side, as ForeFlight draws it: the ground under every half mile,
 * coloured yellow within 2,000 ft and red within 1,000 ft of the planned altitude, the airspace
 * the route passes through as boxes from floor to ceiling, each waypoint, the aircraft when
 * flying, and a cursor to drag along the route that reads the terrain and airspace under it.
 */
@SuppressLint("ViewConstructor")
class ProfileView(ctx: Context, private val plan: FlightPlan) : View(ctx) {

    class Sample(val nm: Double, val ft: Float, val lat: Double = 0.0, val lon: Double = 0.0)
    /** One airspace along the route: where it starts and ends (NM) and its limits. */
    class Run(val area: Airspace.Area, val from: Double, val to: Double)

    var samples: List<Sample> = emptyList()
    var marks: List<Pair<Double, String>> = emptyList()
    var runs: List<Run> = emptyList()
    var aircraftNm: Double? = null
    var aircraftFt: Double? = null
    private var cursor: Double? = null

    private val d = ctx.resources.displayMetrics.density
    private val ground = Paint(Paint.ANTI_ALIAS_FLAG)
    private val groundEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFB08968.toInt(); style = Paint.Style.STROKE; strokeWidth = 1.5f * d }
    private val planLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFF2D9B.toInt(); strokeWidth = 3 * d }
    private val grid = Paint().apply { color = 0x22FFFFFF; strokeWidth = d }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFB8BCC4.toInt(); textSize = 10 * d }
    private val strong = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); textSize = 12 * d; isFakeBoldText = true }
    private val danger = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFF453A.toInt(); strokeWidth = 1.5f * d; pathEffect = DashPathEffect(floatArrayOf(6 * d, 4 * d), 0f) }
    private val plane = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF2D8CFF.toInt() }
    private val box = Paint(Paint.ANTI_ALIAS_FLAG)
    private val boxEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.6f * d }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)

    /** Reads the ground and the airspace along the route; call off the main thread. */
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
                out.add(Sample(at + s, Terrain.elevationFt(g.latitude, g.longitude, wait = true) ?: 0f, g.latitude, g.longitude))
                s += 0.5
            }
            at += len
        }
        plan.points.lastOrNull()?.let { out.add(Sample(at, Terrain.elevationFt(it.lat, it.lon, wait = true) ?: 0f, it.lat, it.lon)) }
        samples = out
        marks = m
        post { invalidate() }
        // The airspace the route crosses, each as a run of samples inside it.
        val areas = try { Airspace.load(context) } catch (e: Throwable) { emptyList() }
        if (out.isNotEmpty() && areas.isNotEmpty()) {
            val s0 = out.minOf { it.lat } - 0.05; val n0 = out.maxOf { it.lat } + 0.05
            val w0 = out.minOf { it.lon } - 0.05; val e0 = out.maxOf { it.lon } + 0.05
            val near = areas.filter { it.maxLat >= s0 && it.minLat <= n0 && it.maxLon >= w0 && it.minLon <= e0 }
            val rs = ArrayList<Run>()
            for (a in near) {
                var start: Double? = null
                for ((k, s) in out.withIndex()) {
                    val inside = a.contains(s.lat, s.lon)
                    if (inside && start == null) start = s.nm
                    if ((!inside || k == out.size - 1) && start != null) { rs += Run(a, start, s.nm); start = null }
                }
            }
            runs = rs.sortedByDescending { (it.area.highFt ?: 18000) - (it.area.lowFt ?: 0) }
            post { invalidate() }
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (samples.size < 2) return false
        val l = 44 * d; val r = width - 10 * d
        val total = samples.last().nm.coerceAtLeast(0.1)
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                cursor = ((e.x - l) / (r - l) * total).coerceIn(0.0, total); invalidate()
            }
        }
        return true
    }

    override fun onDraw(c: Canvas) {
        val w = width.toFloat(); val h = height.toFloat()
        fill.shader = LinearGradient(0f, 0f, 0f, h, 0xFF0B2545.toInt(), 0xFF1B3B5F.toInt(), Shader.TileMode.CLAMP)
        c.drawRect(0f, 0f, w, h, fill); fill.shader = null
        if (samples.size < 2) {
            c.drawText(context.getString(R.string.profile_loading), 16 * d, h / 2f, strong)
            return
        }
        val total = samples.last().nm.coerceAtLeast(0.1)
        val alt = plan.altitude.toDouble()
        val top = maxOf(samples.maxOf { it.ft }.toDouble(), alt, aircraftFt ?: 0.0) + 2500
        val l = 44 * d; val r = w - 10 * d; val t = 26 * d; val b = h - 24 * d
        fun sx(nm: Double) = (l + nm / total * (r - l)).toFloat()
        fun sy(ft: Double) = (b - ft / top * (b - t)).toFloat()

        var g = 0.0
        val step = if (top > 14000) 4000.0 else if (top > 7000) 2000.0 else 1000.0
        while (g <= top) {
            c.drawLine(l, sy(g), r, sy(g), grid)
            c.drawText("%,d".format(g.toInt()), 3 * d, sy(g) + 4 * d, label)
            g += step
        }

        // Airspace boxes, behind the ground.
        for (run in runs) {
            val a = run.area
            val col = Airspace.color(a.kind)
            val x0 = sx(run.from); val x1 = maxOf(sx(run.to), x0 + 3 * d)
            val y0 = sy((a.highFt ?: top.toInt()).toDouble().coerceAtMost(top)); val y1 = sy((a.lowFt ?: 0).toDouble())
            box.color = (col and 0x00FFFFFF) or 0x30000000
            c.drawRect(x0, y0, x1, y1, box)
            boxEdge.color = col
            boxEdge.pathEffect = if (a.kind == "D" || a.kind == "MOA") DashPathEffect(floatArrayOf(5 * d, 4 * d), 0f) else null
            c.drawRect(x0, y0, x1, y1, boxEdge)
            if (x1 - x0 > 60 * d) {
                label.color = 0xFFFFFFFF.toInt()
                val name = (if (a.kind.length == 1) "${a.kind} · " else "${a.kind} · ") + a.name
                c.drawText(name.take(((x1 - x0) / (6 * d)).toInt().coerceAtLeast(4)), x0 + 4 * d, y0 + 12 * d, label)
                label.color = 0xFFB8BCC4.toInt()
                c.drawText(a.limits(), x0 + 4 * d, y0 + 24 * d, label)
            }
        }

        // The ground: brown, yellow within 2,000 ft of the plan, red within 1,000.
        val path = Path().apply {
            moveTo(sx(0.0), b)
            for (s in samples) lineTo(sx(s.nm), sy(s.ft.toDouble()))
            lineTo(sx(total), b); close()
        }
        ground.shader = LinearGradient(0f, t, 0f, b, 0xFF8D6E63.toInt(), 0xFF3E2723.toInt(), Shader.TileMode.CLAMP)
        c.drawPath(path, ground); ground.shader = null
        c.save(); c.clipRect(l, 0f, r, sy(alt - 2000)); ground.color = 0xFFFFC400.toInt(); c.drawPath(path, ground); c.restore()
        c.save(); c.clipRect(l, 0f, r, sy(alt - 1000)); ground.color = 0xFFFF3B30.toInt(); c.drawPath(path, ground); c.restore()
        c.drawPath(path, groundEdge)

        // The planned altitude, and the highest ground under it.
        c.drawLine(sx(0.0), sy(alt), sx(total), sy(alt), planLine)
        strong.color = 0xFFFF2D9B.toInt()
        c.drawText("%,d".format(alt.toInt()), r - 46 * d, sy(alt) - 6 * d, strong)
        val high = samples.maxByOrNull { it.ft }!!
        val clearance = alt - high.ft
        c.drawLine(sx(high.nm), sy(high.ft.toDouble()), sx(high.nm), sy(alt), danger)
        strong.color = if (clearance < 1000) 0xFFFF453A.toInt() else if (clearance < 2000) 0xFFFFD60A.toInt() else 0xFF34C759.toInt()
        c.drawText("▲ %,d ft · %+,d ft".format(high.ft.toInt(), clearance.toInt()), (sx(high.nm) - 40 * d).coerceIn(l, r - 140 * d), 16 * d, strong)
        strong.color = 0xFFFFFFFF.toInt()
        for ((nm, id) in marks) {
            c.drawLine(sx(nm), t, sx(nm), b, grid)
            c.drawText(id, (sx(nm) - 12 * d).coerceIn(0f, w - 40 * d), h - 7 * d, label)
        }
        val an = aircraftNm; val af = aircraftFt
        if (an != null && af != null && an in 0.0..total) {
            plane.color = 0x552D8CFF; c.drawCircle(sx(an), sy(af), 11 * d, plane)
            plane.color = 0xFF2D8CFF.toInt(); c.drawCircle(sx(an), sy(af), 6 * d, plane)
        }

        // The cursor and what lies under it.
        cursor?.let { cn ->
            val s = samples.minByOrNull { Math.abs(it.nm - cn) } ?: return@let
            val x = sx(s.nm)
            boxEdge.color = 0xFFFFFFFF.toInt(); boxEdge.pathEffect = null; boxEdge.strokeWidth = 1.2f * d
            c.drawLine(x, t, x, b, boxEdge); boxEdge.strokeWidth = 1.6f * d
            val inside = runs.filter { s.nm in it.from..it.to }.joinToString("  ") { "${it.area.kind} ${it.area.limits()}" }
            val lines = listOf("%.1f NM · ground %,d ft".format(s.nm, s.ft.toInt()), "clear %+,d ft".format((alt - s.ft).toInt())) + if (inside.isNotEmpty()) listOf(inside) else emptyList()
            val tw = lines.maxOf { strong.measureText(it) } + 16 * d
            val bx = if (x + tw + 8 * d < r) x + 8 * d else x - tw - 8 * d
            fill.color = 0xE6101216.toInt()
            c.drawRoundRect(RectF(bx, t, bx + tw, t + lines.size * 16 * d + 10 * d), 8 * d, 8 * d, fill)
            lines.forEachIndexed { i, s2 -> c.drawText(s2, bx + 8 * d, t + 18 * d + i * 16 * d, strong) }
        }
    }
}
