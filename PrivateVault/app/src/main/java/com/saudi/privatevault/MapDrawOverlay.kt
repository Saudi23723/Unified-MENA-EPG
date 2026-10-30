package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.graphics.RectF
import android.view.MotionEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * Drawing on the flight map: pen, line, arrow, circle, rectangle, text and a
 * ruler, all fixed to latitude and longitude so they stay on the chart as it
 * moves, zooms and turns. Lines and arrows carry their distance and magnetic
 * course; circles their radius. Line widths are in screen dp.
 *
 * Marks reuse [Mark]: points are latitude, longitude pairs; a circle is its
 * centre and a point on its edge.
 */
class MapDrawOverlay(private val map: MapView) : Overlay() {

    enum class MapTool { PAN, SELECT, PEN, LINE, ARROW, CIRCLE, RECT, TEXT, RULER, ERASER }

    var tool = MapTool.PAN
    var color = 0xFFD32F2F.toInt()
    var widthDp = 3f
    var penStyle = 0
    var showMeasures = true
    var cruiseKt = 100.0

    /** Airports to snap line, arrow and ruler ends to. */
    var snapTo: List<AviationData.Airport> = emptyList()

    val marks = mutableListOf<Mark>()
    var onEdit: ((AnnotatedPageView.Edit) -> Unit)? = null
    var onTextAt: ((GeoPoint) -> Unit)? = null

    /** The ruler's reading while measuring, for the bar under the map. */
    var onMeasure: ((String?) -> Unit)? = null

    var selected: Mark? = null
        set(value) {
            field = value
            map.invalidate()
        }

    private var current: Mark? = null
    private var pts = ArrayList<Float>()
    private var ruler: FloatArray? = null
    private var moving = false
    private var lastLat = 0.0
    private var lastLon = 0.0
    private var before: FloatArray? = null
    private var cancelled = false

    private val d = map.resources.displayMetrics.density
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 13 * d
        isFakeBoldText = true
    }
    private val halo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 13 * d
        isFakeBoldText = true
        style = Paint.Style.STROKE
        strokeWidth = 4 * d
        color = 0xEEFFFFFF.toInt()
    }
    private val dash = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 1.5f * d
        color = 0xFF1E88E5.toInt()
        pathEffect = android.graphics.DashPathEffect(floatArrayOf(6 * d, 5 * d), 0f)
    }
    private val path = Path()
    private val p0 = Point()
    private val p1 = Point()

    private fun px(lat: Float, lon: Float, out: Point): Point = map.projection.toPixels(GeoPoint(lat.toDouble(), lon.toDouble()), out)

    // ---- drawing ----

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        for (m in marks) drawMark(c, m)
        current?.let { drawMark(c, it) }
        ruler?.let { drawMark(c, Mark(Tool.LINE, 0xFF000000.toInt(), 2.5f, it, "ruler")) }
        selected?.let { drawSelection(c, it) }
    }

    private fun drawMark(c: Canvas, m: Mark) {
        val p = m.points
        if (p.size < 2) return
        stroke.color = m.color
        stroke.strokeWidth = m.width * d
        stroke.pathEffect = if (m.text == "ruler") android.graphics.DashPathEffect(floatArrayOf(10 * d, 6 * d), 0f) else null
        when (m.tool) {
            Tool.PEN -> {
                val xy = FloatArray(p.size)
                var i = 0
                while (i + 1 < p.size) {
                    px(p[i], p[i + 1], p1)
                    xy[i] = p1.x.toFloat(); xy[i + 1] = p1.y.toFloat()
                    i += 2
                }
                PenInk.draw(c, PenInk.style(m.pen), m.color, stroke.strokeWidth, xy)
            }
            Tool.LINE, Tool.ARROW -> {
                if (p.size < 4) return
                px(p[0], p[1], p0)
                px(p[2], p[3], p1)
                c.drawLine(p0.x.toFloat(), p0.y.toFloat(), p1.x.toFloat(), p1.y.toFloat(), stroke)
                if (m.tool == Tool.ARROW) {
                    stroke.pathEffect = null
                    val a = atan2((p1.y - p0.y).toFloat(), (p1.x - p0.x).toFloat())
                    val len = maxOf(stroke.strokeWidth * 4f, 14 * d)
                    for (side in floatArrayOf(-0.5f, 0.5f)) {
                        val b = a + Math.PI.toFloat() + side
                        c.drawLine(p1.x.toFloat(), p1.y.toFloat(), p1.x + len * cos(b), p1.y + len * sin(b), stroke)
                    }
                }
                if (showMeasures || m.text == "ruler") {
                    drawLabel(c, legText(p), (p0.x + p1.x) / 2f, (p0.y + p1.y) / 2f - 8 * d)
                }
            }
            Tool.OVAL -> { // a circle: centre and a point on its edge
                if (p.size < 4) return
                px(p[0], p[1], p0)
                px(p[2], p[3], p1)
                val r = hypot((p1.x - p0.x).toFloat(), (p1.y - p0.y).toFloat())
                c.drawCircle(p0.x.toFloat(), p0.y.toFloat(), r, stroke)
                if (showMeasures) {
                    val nm = Nav.distanceNm(p[0].toDouble(), p[1].toDouble(), p[2].toDouble(), p[3].toDouble())
                    drawLabel(c, "r %.1f NM".format(nm), p0.x.toFloat(), p0.y - r - 6 * d)
                }
            }
            Tool.RECT -> {
                if (p.size < 4) return
                px(p[0], p[1], p0)
                px(p[2], p[3], p1)
                c.drawRect(minOf(p0.x, p1.x).toFloat(), minOf(p0.y, p1.y).toFloat(), maxOf(p0.x, p1.x).toFloat(), maxOf(p0.y, p1.y).toFloat(), stroke)
            }
            Tool.TEXT -> {
                px(p[0], p[1], p0)
                label.color = m.color
                label.textSize = m.width * d
                halo.textSize = m.width * d
                var y = p0.y.toFloat()
                for (line in (m.text ?: "").split('\n')) {
                    c.drawText(line, p0.x.toFloat(), y, halo)
                    c.drawText(line, p0.x.toFloat(), y, label)
                    y += label.textSize * 1.25f
                }
                label.textSize = 13 * d
                halo.textSize = 13 * d
            }
            else -> {}
        }
        stroke.pathEffect = null
    }

    private fun drawLabel(c: Canvas, text: String, x: Float, y: Float) {
        val w = label.measureText(text)
        label.color = 0xFF111111.toInt()
        c.drawText(text, x - w / 2, y, halo)
        c.drawText(text, x - w / 2, y, label)
    }

    /** "24.6 NM · 213°M · 15 min" for a leg. */
    private fun legText(p: FloatArray): String {
        val nm = Nav.distanceNm(p[0].toDouble(), p[1].toDouble(), p[2].toDouble(), p[3].toDouble())
        val tc = Nav.bearingTrue(p[0].toDouble(), p[1].toDouble(), p[2].toDouble(), p[3].toDouble())
        val mc = Nav.magnetic(tc, p[0].toDouble(), p[1].toDouble())
        val min = nm / cruiseKt * 60
        return "%.1f NM · %sM · %d min".format(nm, Nav.deg(mc), Math.round(min))
    }

    fun rulerText(p: FloatArray): String {
        val nm = Nav.distanceNm(p[0].toDouble(), p[1].toDouble(), p[2].toDouble(), p[3].toDouble())
        val tc = Nav.bearingTrue(p[0].toDouble(), p[1].toDouble(), p[2].toDouble(), p[3].toDouble())
        val mc = Nav.magnetic(tc, p[0].toDouble(), p[1].toDouble())
        val min = nm / cruiseKt * 60
        return "📏 %.1f NM   TC %s   MC %s   ⏱ %d:%02d @ %d kt".format(
            nm, Nav.deg(tc), Nav.deg(mc), (min / 60).toInt(), (min % 60).toInt(), cruiseKt.toInt(),
        )
    }

    private fun bounds(m: Mark): RectF {
        val r = RectF(Float.MAX_VALUE, Float.MAX_VALUE, -Float.MAX_VALUE, -Float.MAX_VALUE)
        val p = m.points
        if (m.tool == Tool.OVAL && p.size >= 4) {
            px(p[0], p[1], p0)
            px(p[2], p[3], p1)
            val rad = hypot((p1.x - p0.x).toFloat(), (p1.y - p0.y).toFloat())
            return RectF(p0.x - rad, p0.y - rad, p0.x + rad, p0.y + rad)
        }
        if (m.tool == Tool.TEXT) {
            px(p[0], p[1], p0)
            label.textSize = m.width * d
            val lines = (m.text ?: "").split('\n')
            val w = lines.maxOf { label.measureText(it) }
            val rr = RectF(p0.x.toFloat(), p0.y - label.textSize, p0.x + w, p0.y - label.textSize + label.textSize * 1.25f * lines.size)
            label.textSize = 13 * d
            return rr
        }
        var i = 0
        while (i + 1 < p.size) {
            px(p[i], p[i + 1], p0)
            r.union(p0.x.toFloat(), p0.y.toFloat())
            i += 2
        }
        return r
    }

    private fun drawSelection(c: Canvas, m: Mark) {
        val r = bounds(m)
        r.inset(-8 * d, -8 * d)
        c.drawRect(r, dash)
    }

    // ---- touch ----

    private fun geo(e: MotionEvent): GeoPoint = map.projection.fromPixels(e.x.toInt(), e.y.toInt()) as GeoPoint

    /** The airport near a screen point (within 24 dp), for clean measurements. */
    private fun snap(e: MotionEvent, g: GeoPoint): GeoPoint {
        var best: AviationData.Airport? = null
        var bestD = 24 * d
        val pt = Point()
        for (a in snapTo) {
            map.projection.toPixels(GeoPoint(a.lat, a.lon), pt)
            val dd = hypot(pt.x - e.x, pt.y - e.y)
            if (dd < bestD) {
                bestD = dd
                best = a
            }
        }
        return best?.let { GeoPoint(it.lat, it.lon) } ?: g
    }

    private fun hitMark(e: MotionEvent): Mark? = marks.lastOrNull { m ->
        val r = bounds(m)
        r.inset(-14 * d, -14 * d)
        r.contains(e.x, e.y) && (m.tool != Tool.PEN || nearPen(m, e))
    }

    private fun nearPen(m: Mark, e: MotionEvent): Boolean {
        val p = m.points
        var i = 0
        while (i + 1 < p.size) {
            px(p[i], p[i + 1], p0)
            if (hypot(p0.x - e.x, p0.y - e.y) < 20 * d) return true
            i += 2
        }
        return false
    }

    override fun onTouchEvent(e: MotionEvent, mapView: MapView): Boolean {
        if (tool == MapTool.PAN) return false
        // Two fingers always move and zoom the map.
        if (e.pointerCount > 1) {
            if (current != null || ruler != null) {
                current = null
                cancelled = true
                map.invalidate()
            }
            return false
        }
        val g = geo(e)
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                cancelled = false
                when (tool) {
                    MapTool.SELECT -> {
                        selected = hitMark(e)
                        moving = selected != null
                        before = selected?.points?.copyOf()
                        lastLat = g.latitude
                        lastLon = g.longitude
                        if (!moving) return false
                    }
                    MapTool.ERASER -> erase(e)
                    MapTool.TEXT -> {}
                    MapTool.RULER -> {
                        val s = snap(e, g)
                        ruler = floatArrayOf(s.latitude.toFloat(), s.longitude.toFloat(), s.latitude.toFloat(), s.longitude.toFloat())
                    }
                    else -> {
                        val s = if (tool == MapTool.LINE || tool == MapTool.ARROW) snap(e, g) else g
                        pts = arrayListOf(s.latitude.toFloat(), s.longitude.toFloat())
                        if (tool != MapTool.PEN) pts.addAll(listOf(s.latitude.toFloat(), s.longitude.toFloat()))
                        current = build()
                    }
                }
            }
            MotionEvent.ACTION_MOVE -> {
                if (tool == MapTool.SELECT && !moving) return false
                if (cancelled) return true
                when (tool) {
                    MapTool.SELECT -> if (moving) {
                        val m = selected ?: return true
                        val dLat = (g.latitude - lastLat).toFloat()
                        val dLon = (g.longitude - lastLon).toFloat()
                        var i = 0
                        while (i + 1 < m.points.size) {
                            m.points[i] += dLat
                            m.points[i + 1] += dLon
                            i += 2
                        }
                        lastLat = g.latitude
                        lastLon = g.longitude
                    }
                    MapTool.ERASER -> erase(e)
                    MapTool.RULER -> ruler?.let { r ->
                        val s = snap(e, g)
                        r[2] = s.latitude.toFloat()
                        r[3] = s.longitude.toFloat()
                        onMeasure?.invoke(rulerText(r))
                    }
                    MapTool.PEN -> {
                        pts.add(g.latitude.toFloat())
                        pts.add(g.longitude.toFloat())
                        current = build()
                    }
                    MapTool.TEXT -> {}
                    else -> if (pts.size >= 4) {
                        val s = if (tool == MapTool.LINE || tool == MapTool.ARROW) snap(e, g) else g
                        pts[2] = s.latitude.toFloat()
                        pts[3] = s.longitude.toFloat()
                        current = build()
                        if (tool == MapTool.LINE || tool == MapTool.ARROW) onMeasure?.invoke(rulerText(current!!.points))
                    }
                }
            }
            MotionEvent.ACTION_UP -> {
                if (tool == MapTool.SELECT && !moving) return false
                if (!cancelled) when (tool) {
                    MapTool.SELECT -> {
                        val m = selected
                        val b = before
                        if (moving && m != null && b != null && !b.contentEquals(m.points)) {
                            onEdit?.invoke(AnnotatedPageView.Edit.Changed(m, b, m.points.copyOf(), m.color, m.color))
                        }
                        moving = false
                    }
                    MapTool.TEXT -> onTextAt?.invoke(g)
                    MapTool.RULER -> ruler?.let { onMeasure?.invoke(rulerText(it)) }
                    MapTool.ERASER -> {}
                    else -> {
                        val m = current
                        current = null
                        if (m != null && big(m)) {
                            marks.add(m)
                            onEdit?.invoke(AnnotatedPageView.Edit.Added(m))
                        }
                        onMeasure?.invoke(null)
                    }
                }
            }
        }
        map.invalidate()
        return true
    }

    private fun big(m: Mark): Boolean {
        if (m.tool == Tool.PEN) return m.points.size >= 4
        px(m.points[0], m.points[1], p0)
        px(m.points[2], m.points[3], p1)
        return hypot((p1.x - p0.x).toFloat(), (p1.y - p0.y).toFloat()) > 10 * d
    }

    private fun build(): Mark {
        val t = when (tool) {
            MapTool.PEN -> Tool.PEN
            MapTool.LINE -> Tool.LINE
            MapTool.ARROW -> Tool.ARROW
            MapTool.CIRCLE -> Tool.OVAL
            else -> Tool.RECT
        }
        return Mark(t, color, widthDp, pts.toFloatArray(), pen = if (t == Tool.PEN) penStyle else 0)
    }

    private fun erase(e: MotionEvent) {
        val hit = hitMark(e) ?: return
        val i = marks.indexOf(hit)
        marks.removeAt(i)
        if (selected === hit) selected = null
        onEdit?.invoke(AnnotatedPageView.Edit.Removed(listOf(i to hit)))
    }

    fun addText(at: GeoPoint, text: String) {
        val m = Mark(Tool.TEXT, color, 16f, floatArrayOf(at.latitude.toFloat(), at.longitude.toFloat()), text)
        marks.add(m)
        onEdit?.invoke(AnnotatedPageView.Edit.Added(m))
        map.invalidate()
    }

    /** Turns the last ruler reading into a kept line. */
    fun keepRuler() {
        val r = ruler ?: return
        val m = Mark(Tool.LINE, color, widthDp, r.copyOf())
        marks.add(m)
        onEdit?.invoke(AnnotatedPageView.Edit.Added(m))
        ruler = null
        map.invalidate()
    }

    fun clearRuler() {
        ruler = null
        onMeasure?.invoke(null)
        map.invalidate()
    }

    fun deleteSelected() {
        val m = selected ?: return
        val i = marks.indexOf(m)
        if (i < 0) return
        marks.removeAt(i)
        selected = null
        onEdit?.invoke(AnnotatedPageView.Edit.Removed(listOf(i to m)))
    }

    fun recolorSelected(c: Int) {
        val m = selected ?: return
        val old = m.color
        m.color = c
        onEdit?.invoke(AnnotatedPageView.Edit.Changed(m, m.points.copyOf(), m.points.copyOf(), old, c))
        map.invalidate()
    }
}
