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
 * The route seen from the side: the ground under every mile, coloured yellow within a thousand
 * feet of the planned altitude and red within a hundred, the airspace the route passes through as
 * boxes from floor to ceiling, the towers in the corridor, each waypoint, the top of climb and the
 * top of descent, the aircraft when flying, and the planned altitude as a pink line.
 *
 * Two fingers' worth of things can be done with one finger:
 *  - drag the pink line up or down and the altitude changes in steps of a hundred feet, the
 *    clearance and the first strike are worked out again as it moves, and the flight plan, and with
 *    it the nav log, follows;
 *  - drag anywhere else along the route and a cursor reads the ground, the clearance and the
 *    airspace under it.
 *
 * The ground is the highest in the whole corridor at each point, not the height under the line:
 * a ridge a few miles off to one side is as much a hazard as one on the track.
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

    /** The towers standing in the corridor, and how wide that corridor is either side of the line. */
    var obstacles: List<Obstacles.Along> = emptyList()
    var halfCorridorNm = 4.0
    /** The room below which a hazard turns amber, and below which it turns red. */
    var cautionFt = 1000
    var warnFt = 100
    /** What the sweep found: the least room there is, and the first thing that would be struck. */
    var clearanceFt: Int? = null
    var firstStrikeNm: Double? = null
    /** The highest ground in the corridor, and how far along it stands. */
    var highestFt: Float = 0f
    var highestNm: Double = 0.0

    /** Airspace that begins far above the planned height is left off, as it cannot matter. */
    var smartAirspace = true
    /** Told whenever the pink line is moved, and when the finger comes off it. */
    var onAltitude: ((Int) -> Unit)? = null
    var onAltitudeDone: (() -> Unit)? = null
    /** Where the ground comes from: the best there is, which is the thirty-metre tile where there is one. */
    var ground: (Double, Double) -> Float = { la, lo -> Srtm.best(la, lo) }

    private var dragAlt = false
    // The layout of the last draw, so a touch can be read against it.
    private var lastL = 0f; private var lastR = 0f; private var lastT = 0f; private var lastB = 0f
    private var lastTop = 1.0

    private val d = ctx.resources.displayMetrics.density
    private val groundPaint = Paint(Paint.ANTI_ALIAS_FLAG)
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
    private val tower = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 2f * d; strokeCap = Paint.Cap.ROUND }
    private val star = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFF453A.toInt() }
    private val headTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 11f * d; isFakeBoldText = true }
    private val sub = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 9.5f * d; color = 0xFF8FA3B8.toInt() }

    // ================================================================ sampling

    /** Reads the ground and the airspace along the route; call off the main thread. */
    fun sample() {
        val out = ArrayList<Sample>()
        val m = ArrayList<Pair<Double, String>>()
        var at = 0.0
        val half = halfCorridorNm
        // The highest ground across the corridor at a point on the line, seven samples abreast.
        fun worstAt(lat: Double, lon: Double, crs: Double): Float {
            var worst = ground(lat, lon)
            if (half > 0.1) for (k in -3..3) {
                if (k == 0) continue
                val p = Nav.destination(lat, lon, crs + 90.0, half * k / 3.0)
                val h = ground(p.latitude, p.longitude)
                if (h > worst) worst = h
            }
            return worst
        }
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
                out.add(Sample(at + s, worstAt(g.latitude, g.longitude, crs), g.latitude, g.longitude))
                s += 0.5
            }
            at += len
        }
        plan.points.lastOrNull()?.let {
            val crs = if (plan.points.size >= 2) Nav.bearingTrue(plan.points[plan.points.size - 2].lat, plan.points[plan.points.size - 2].lon, it.lat, it.lon) else 0.0
            out.add(Sample(at, worstAt(it.lat, it.lon, crs), it.lat, it.lon))
        }
        samples = out
        marks = m
        out.maxByOrNull { it.ft }?.let { highestFt = it.ft; highestNm = it.nm }
        analyse()
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

    // ================================================================ the planned flight

    /** Where the climb ends and the descent begins, in miles along the route, at the aircraft's own rates. */
    private fun phases(): Pair<Double, Double> {
        if (samples.size < 2) return 0.0 to 0.0
        val total = samples.last().nm
        val alt = plan.altitude.toDouble()
        val depFt = samples.first().ft.toDouble()
        val destFt = samples.last().ft.toDouble()
        val prof = AircraftProfile.current(context)
        val climbNm = ((alt - depFt) / Math.max(100.0, prof.climbFpm) / 60.0 * prof.climbTas).coerceAtLeast(0.0)
        val descNm = ((alt - destFt - 1000) / Math.max(100.0, prof.descentFpm) / 60.0 * prof.descentTas).coerceAtLeast(0.0)
        // A short route can be all climb and descent; the two never pass each other.
        val c = Math.min(climbNm, total * 0.5)
        val dn = Math.min(descNm, total - c)
        return c to (total - dn)
    }

    /** The planned height at a point along the route: the climb, the cruise, the descent. */
    fun plannedFt(nm: Double): Double {
        if (samples.size < 2) return plan.altitude.toDouble()
        val total = samples.last().nm.coerceAtLeast(0.1)
        val alt = plan.altitude.toDouble()
        val depFt = samples.first().ft.toDouble()
        val destFt = samples.last().ft.toDouble()
        val (toc, tod) = phases()
        return when {
            toc > 0.1 && nm < toc -> depFt + (alt - depFt) * (nm / toc)
            tod < total - 0.1 && nm > tod -> alt - (alt - destFt - 1000) * ((nm - tod) / (total - tod))
            else -> alt
        }.coerceAtLeast(0.0)
    }

    /**
     * Works out the least room there is over anything in the corridor — ground or tower — and
     * where the first strike would be, against the planned altitude as it stands. Called again each
     * time the pink line moves, so the figures follow the finger.
     */
    fun analyse() {
        if (samples.size < 2) return
        var room: Int? = null
        var strike: Double? = null
        for (o in obstacles) {
            val r = (plannedFt(o.alongNm) - o.obstacle.topFt).toInt()
            if (room == null || r < room!!) room = r
            if (r < 0 && (strike == null || o.alongNm < strike!!)) strike = o.alongNm
        }
        for (g in samples) {
            val r = (plannedFt(g.nm) - g.ft).toInt()
            if (room == null || r < room!!) room = r
            if (r < 0 && (strike == null || g.nm < strike!!)) strike = g.nm
        }
        clearanceFt = room
        firstStrikeNm = strike
    }

    // ================================================================ touch

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (samples.size < 2) return false
        val l = lastL; val r = lastR
        val total = samples.last().nm.coerceAtLeast(0.1)
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                val y = lastB - (plan.altitude / lastTop * (lastB - lastT)).toFloat()
                // Near the pink line, the finger takes the line; anywhere else it reads the route.
                dragAlt = Math.abs(e.y - y) <= 28 * d && e.x >= l
                if (!dragAlt) { cursor = ((e.x - l) / (r - l) * total).coerceIn(0.0, total) }
                invalidate()
            }
            MotionEvent.ACTION_MOVE -> {
                if (dragAlt) {
                    val raw = lastTop * (lastB - e.y) / (lastB - lastT)
                    val snapped = (Math.round(raw / 100.0) * 100).toInt().coerceIn(1500, 17500)
                    if (snapped != plan.altitude) {
                        plan.altitude = snapped
                        analyse()
                        onAltitude?.invoke(snapped)
                    }
                } else cursor = ((e.x - l) / (r - l) * total).coerceIn(0.0, total)
                invalidate()
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                if (dragAlt) { dragAlt = false; onAltitudeDone?.invoke() }
                invalidate()
            }
        }
        return true
    }

    // ================================================================ drawing

    /** The numbers laid in a row so that none can run into another, shrunk together if they must. */
    private fun headerRow(c: Canvas, y: Float, items: List<Pair<String, Int>>) {
        val left = 46 * d; val right = width - 10 * d
        headTx.textSize = 11f * d
        var widths = items.map { headTx.measureText(it.first) }
        val gap = 12 * d
        val need = widths.sum() + gap * (items.size - 1)
        val room = right - left
        if (need > room) {
            headTx.textSize = 11f * d * room / need
            widths = items.map { headTx.measureText(it.first) }
        }
        val free = (room - widths.sum()).coerceAtLeast(0f)
        // First at the left edge, last at the right edge, the rest spaced evenly between.
        var x = left
        val between = if (items.size > 1) free / (items.size - 1) else 0f
        for ((i, it) in items.withIndex()) {
            headTx.color = it.second
            c.drawText(it.first, x, y, headTx)
            x += widths[i] + between
        }
        headTx.textSize = 11f * d
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
        val gray = 0xFF8FA3B8.toInt()

        // Row one: the three figures, never on top of one another.
        val room = clearanceFt
        val col = when { room == null -> gray; room < warnFt -> 0xFFFF453A.toInt(); room < cautionFt -> 0xFFFFD60A.toInt(); else -> 0xFF4CD964.toInt() }
        val fs = firstStrikeNm
        headerRow(c, 14 * d, listOf(
            ("CLEARANCE " + (if (room == null) "—" else String.format("%+,d'", room))) to col,
            (if (fs != null) String.format("FIRST STRIKE %.0f nm", fs) else "NO STRIKE") to (if (fs != null) 0xFFFF453A.toInt() else gray),
            String.format("CORRIDOR %.0f nm", halfCorridorNm * 2) to gray,
        ))
        // Row two: the highest ground, on its own line, and what to do with the pink one.
        val clearance = alt - highestFt
        sub.color = if (clearance < cautionFt) 0xFFFF453A.toInt() else if (clearance < 2000) 0xFFFFD60A.toInt() else 0xFF34C759.toInt()
        c.drawText("▲ highest %,d ft at %.0f nm · %+,d ft".format(highestFt.toInt(), highestNm, clearance.toInt()), 46 * d, 29 * d, sub)
        sub.color = gray
        if (!dragAlt) {
            val hint = "drag the pink line ↕"
            c.drawText(hint, w - 10 * d - sub.measureText(hint), 29 * d, sub)
        }

        val top = maxOf(samples.maxOf { it.ft }.toDouble(), alt, aircraftFt ?: 0.0) + 2500
        val l = 44 * d; val r = w - 10 * d; val t = 40 * d; val b = h - 24 * d
        lastL = l; lastR = r; lastT = t; lastB = b; lastTop = top
        fun sx(nm: Double) = (l + nm / total * (r - l)).toFloat()
        fun sy(ft: Double) = (b - ft / top * (b - t)).toFloat()

        var g = 0.0
        val step = if (top > 14000) 4000.0 else if (top > 7000) 2000.0 else 1000.0
        while (g <= top) {
            c.drawLine(l, sy(g), r, sy(g), grid)
            c.drawText("%,d".format(g.toInt()), 3 * d, sy(g) + 4 * d, label)
            g += step
        }

        // The towers in the corridor: green with room over them, amber close, red where the
        // planned height would not clear them, and a star on anything that would be struck.
        for (o in obstacles) {
            if (o.alongNm > total) continue
            val x = sx(o.alongNm)
            val topY = sy(o.obstacle.topFt.toDouble().coerceAtMost(top))
            val baseY = sy((o.obstacle.topFt - o.obstacle.aglFt).toDouble().coerceAtLeast(0.0))
            val roomO = plannedFt(o.alongNm) - o.obstacle.topFt
            tower.color = when {
                roomO < warnFt -> 0xFFFF453A.toInt()
                roomO < cautionFt -> 0xFFFFD60A.toInt()
                else -> 0xFF4CD964.toInt()
            }
            c.drawLine(x, baseY, x, topY, tower)
            c.drawCircle(x, topY, 2.5f * d, tower)
            if (roomO < 0) {
                val p = Path()
                val rr = 6 * d
                for (k in 0 until 10) {
                    val ang = Math.toRadians(-90.0 + k * 36.0)
                    val rad = if (k % 2 == 0) rr else rr * 0.45f
                    p.let { if (k == 0) it.moveTo(x + (rad * Math.cos(ang)).toFloat(), topY + (rad * Math.sin(ang)).toFloat())
                            else it.lineTo(x + (rad * Math.cos(ang)).toFloat(), topY + (rad * Math.sin(ang)).toFloat()) }
                }
                p.close(); c.drawPath(p, star)
            }
        }

        // Airspace boxes, behind the ground. Airspace that begins far above the planned height is
        // left off; where the planned height is inside the limits, the box is drawn heavier.
        for (run in runs) {
            val a = run.area
            if (smartAirspace && (a.lowFt ?: 0) > alt + 3000) continue
            val colA = Airspace.color(a.kind)
            val conflict = alt >= (a.lowFt ?: 0) - 200 && alt <= (a.highFt ?: 99999) + 200
            val x0 = sx(run.from); val x1 = maxOf(sx(run.to), x0 + 3 * d)
            val y0 = sy((a.highFt ?: top.toInt()).toDouble().coerceAtMost(top)); val y1 = sy((a.lowFt ?: 0).toDouble())
            box.color = (colA and 0x00FFFFFF) or (if (conflict) 0x48000000 else 0x24000000)
            c.drawRect(x0, y0, x1, y1, box)
            boxEdge.color = colA
            boxEdge.strokeWidth = (if (conflict) 2.6f else 1.4f) * d
            boxEdge.pathEffect = if (a.kind == "D" || a.kind == "MOA") DashPathEffect(floatArrayOf(5 * d, 4 * d), 0f) else null
            c.drawRect(x0, y0, x1, y1, boxEdge)
            if (x1 - x0 > 60 * d) {
                label.color = 0xFFFFFFFF.toInt()
                val name = (if (conflict) "! " else "") + a.kind + " · " + a.name
                c.drawText(name.take(((x1 - x0) / (6 * d)).toInt().coerceAtLeast(4)), x0 + 4 * d, y0 + 12 * d, label)
                label.color = 0xFFB8BCC4.toInt()
                c.drawText(a.limits(), x0 + 4 * d, y0 + 24 * d, label)
            }
        }
        boxEdge.strokeWidth = 1.6f * d

        // The ground: brown, yellow within a thousand feet of the plan, red within a hundred.
        val path = Path().apply {
            moveTo(sx(0.0), b)
            for (s in samples) lineTo(sx(s.nm), sy(s.ft.toDouble()))
            lineTo(sx(total), b); close()
        }
        groundPaint.shader = LinearGradient(0f, t, 0f, b, 0xFF8D6E63.toInt(), 0xFF3E2723.toInt(), Shader.TileMode.CLAMP)
        c.drawPath(path, groundPaint); groundPaint.shader = null
        // The bands follow the climb and the descent, so the colours say where the strike really is.
        val bands = Path()
        val cl = samples
        for (pass in 0..1) {
            val limitFt = if (pass == 0) cautionFt else warnFt
            groundPaint.color = if (pass == 0) 0xFFFFC400.toInt() else 0xFFFF3B30.toInt()
            bands.reset()
            var open = false
            for (s in cl) {
                val hot = s.ft >= plannedFt(s.nm) - limitFt
                if (hot) {
                    if (!open) { bands.moveTo(sx(s.nm), b); open = true }
                    bands.lineTo(sx(s.nm), sy(s.ft.toDouble()))
                } else if (open) {
                    bands.lineTo(sx(s.nm), b); bands.close(); open = false
                }
            }
            if (open) { bands.lineTo(sx(total), b); bands.close() }
            // Only the part of the ground inside the band, so the colour sits on the ridge, not the valley.
            c.save()
            c.clipPath(path)
            c.drawPath(bands, groundPaint)
            c.restore()
        }
        c.drawPath(path, groundEdge)

        // The planned altitude, with the top of climb and the top of descent marked on it.
        val pl = Path()
        var first = true
        var nm = 0.0
        while (nm <= total) {
            val x = sx(nm); val y = sy(plannedFt(nm))
            if (first) { pl.moveTo(x, y); first = false } else pl.lineTo(x, y)
            nm += Math.max(0.5, total / 120.0)
        }
        pl.lineTo(sx(total), sy(plannedFt(total)))
        planLine.style = Paint.Style.STROKE
        planLine.strokeWidth = (if (dragAlt) 4.5f else 3f) * d
        c.drawPath(pl, planLine)
        val (toc, tod) = phases()
        sub.color = 0xFFFF80AB.toInt()
        if (toc > 0.5 && toc < total) { c.drawCircle(sx(toc), sy(alt), 3.5f * d, star.apply { color = 0xFFFF2D9B.toInt() }); c.drawText("TOC", sx(toc) - 9 * d, sy(alt) - 8 * d, sub) }
        if (tod < total - 0.5 && tod > 0) { c.drawCircle(sx(tod), sy(alt), 3.5f * d, star); c.drawText("TOD", sx(tod) - 9 * d, sy(alt) - 8 * d, sub) }
        star.color = 0xFFFF453A.toInt()
        sub.color = gray
        // Its handle: the pill the finger is meant to take hold of.
        val pillTx = "↕ %,d".format(alt.toInt())
        val pw = strong.measureText(pillTx) + 14 * d
        val py = (sy(alt) - 24 * d).coerceAtLeast(t)
        fill.color = if (dragAlt) 0xFFD81B60.toInt() else 0xCCAD1457.toInt()
        c.drawRoundRect(RectF(r - pw - 4 * d, py, r - 4 * d, py + 20 * d), 6 * d, 6 * d, fill)
        strong.color = 0xFFFFFFFF.toInt()
        c.drawText(pillTx, r - pw + 3 * d, py + 14 * d, strong)

        // The highest ground under the line, and the room over it.
        c.drawLine(sx(highestNm), sy(highestFt.toDouble()), sx(highestNm), sy(plannedFt(highestNm)), danger)
        for ((m2, id) in marks) {
            c.drawLine(sx(m2), t, sx(m2), b, grid)
            c.drawText(id, (sx(m2) - 12 * d).coerceIn(0f, w - 40 * d), h - 7 * d, label)
        }
        val an = aircraftNm; val af = aircraftFt
        if (an != null && af != null && an in 0.0..total) {
            plane.color = 0x552D8CFF; c.drawCircle(sx(an), sy(af), 11 * d, plane)
            plane.color = 0xFF2D8CFF.toInt(); c.drawCircle(sx(an), sy(af), 6 * d, plane)
        }

        // The cursor and what lies under it.
        cursor?.takeIf { !dragAlt }?.let { cn ->
            val s = samples.minByOrNull { Math.abs(it.nm - cn) } ?: return@let
            val x = sx(s.nm)
            boxEdge.color = 0xFFFFFFFF.toInt(); boxEdge.pathEffect = null; boxEdge.strokeWidth = 1.2f * d
            c.drawLine(x, t, x, b, boxEdge); boxEdge.strokeWidth = 1.6f * d
            val inside = runs.filter { s.nm in it.from..it.to }.joinToString("  ") { "${it.area.kind} ${it.area.limits()}" }
            val here = plannedFt(s.nm)
            val lines = listOf("%.1f NM · ground %,d ft".format(s.nm, s.ft.toInt()), "clear %+,d ft".format((here - s.ft).toInt())) + if (inside.isNotEmpty()) listOf(inside) else emptyList()
            val tw = lines.maxOf { strong.measureText(it) } + 16 * d
            val bx = if (x + tw + 8 * d < r) x + 8 * d else x - tw - 8 * d
            fill.color = 0xE6101216.toInt()
            c.drawRoundRect(RectF(bx, t, bx + tw, t + lines.size * 16 * d + 10 * d), 8 * d, 8 * d, fill)
            lines.forEachIndexed { i, s2 -> c.drawText(s2, bx + 8 * d, t + 18 * d + i * 16 * d, strong) }
        }
    }
}
