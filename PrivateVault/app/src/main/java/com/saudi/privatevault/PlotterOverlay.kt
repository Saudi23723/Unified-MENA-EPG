package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import android.graphics.RectF
import android.view.MotionEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * The plotter, as a pilot lays one on a paper chart.
 *
 * Put two fingers on the chart and hold them still for a moment and a ruler springs up between
 * them. Slide the fingers to measure elsewhere. Then lift them: the ruler stays where it was put,
 * pinned to the ground rather than to the glass, so the chart can be dragged and zoomed under it
 * and the measurement still runs between the same two places.
 *
 * Unlocked, either end can be picked up and moved, and a tap on the ruler puts it away. Locked, it
 * is a line drawn on the chart: nothing moves it, nothing clears it, and every finger belongs to
 * the map again. That is the lock the pilot asks for when the plotter keeps getting in the way.
 *
 * The reading is the one an electronic flight bag gives for two points: the distance, in feet as
 * well when it is under three miles so a runway can be measured, the magnetic course out and back,
 * the time at the speed being flown, and what the leg costs in fuel.
 */
class PlotterOverlay(
    private val map: MapView,
    private val groundSpeedKt: () -> Double,
    private val cruiseKt: () -> Double = { 0.0 },
    private val gph: () -> Double = { 0.0 },
    private val onChange: () -> Unit = {},
) : Overlay() {

    private val d = map.resources.displayMetrics.density
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 2.5f * d; color = 0xFFFFD60A.toInt(); strokeCap = Paint.Cap.ROUND
    }
    private val halo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 6f * d; color = 0xAA000000.toInt(); strokeCap = Paint.Cap.ROUND
    }
    private val knob = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFD60A.toInt() }
    private val knobEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 2f * d; color = 0xFF000000.toInt() }
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xF21B1D22.toInt() }
    private val big = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); textSize = 15f * d; isFakeBoldText = true }
    private val sub = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFD60A.toInt(); textSize = 12f * d }
    private val dim = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFC8D0DA.toInt(); textSize = 12f * d }
    private val tick = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.6f * d; color = 0xCCFFFFFF.toInt() }

    /** The two ends, pinned to the ground. */
    private var a: GeoPoint? = null
    private var b: GeoPoint? = null

    /** Locked: the ruler is part of the chart and no finger touches it. */
    var locked = false
        set(v) { field = v; map.invalidate(); onChange() }

    val up: Boolean get() = a != null && b != null

    fun clear() { a = null; b = null; locked = false; map.invalidate(); onChange() }

    /** The reading as the bar above the chart shows it, or null when the ruler is down. */
    fun reading(): String? {
        val p = a ?: return null
        val q = b ?: return null
        return "%.1f nm".format(Nav.distanceNm(p.latitude, p.longitude, q.latitude, q.longitude))
    }

    private var measuring = false
    private var downAt = 0L
    private var startSpan = 0f
    private var startCx = 0f
    private var startCy = 0f
    /** 0 none, 1 the first end, 2 the second. */
    private var dragEnd = 0
    private val pa = Point()
    private val pb = Point()

    /** How long the fingers must rest before the ruler appears, and how far they may drift. */
    private val holdMs = 260L
    private val slopPx get() = 16 * d

    private fun span(e: MotionEvent): Float =
        Math.hypot((e.getX(0) - e.getX(1)).toDouble(), (e.getY(0) - e.getY(1)).toDouble()).toFloat()

    private fun near(x: Float, y: Float, p: Point) =
        Math.hypot((x - p.x).toDouble(), (y - p.y).toDouble()) < 26 * d

    private fun pin(mv: MapView) {
        val pr = mv.projection
        a?.let { pr.toPixels(it, pa) }
        b?.let { pr.toPixels(it, pb) }
    }

    override fun onTouchEvent(e: MotionEvent, mv: MapView): Boolean {
        if (locked) return false
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                // An end of a ruler already laid down can be picked up and carried.
                if (up) {
                    pin(mv)
                    dragEnd = if (near(e.x, e.y, pa)) 1 else if (near(e.x, e.y, pb)) 2 else 0
                    if (dragEnd != 0) return true
                }
            }
            MotionEvent.ACTION_POINTER_DOWN -> if (e.pointerCount == 2) {
                dragEnd = 0
                downAt = System.currentTimeMillis()
                startSpan = span(e)
                startCx = (e.getX(0) + e.getX(1)) / 2; startCy = (e.getY(0) + e.getY(1)) / 2
            }
            MotionEvent.ACTION_MOVE -> {
                if (dragEnd != 0 && e.pointerCount == 1) {
                    val g = mv.projection.fromPixels(e.x.toInt(), e.y.toInt()) as GeoPoint
                    if (dragEnd == 1) a = g else b = g
                    mv.invalidate(); onChange()
                    return true
                }
                if (e.pointerCount != 2) return false
                val s = span(e)
                val cx = (e.getX(0) + e.getX(1)) / 2; val cy = (e.getY(0) + e.getY(1)) / 2
                if (!measuring) {
                    val moved = Math.abs(s - startSpan) > slopPx ||
                        Math.hypot((cx - startCx).toDouble(), (cy - startCy).toDouble()) > slopPx
                    // A pinch or a two-finger drag: leave it to the map.
                    if (moved) { downAt = 0L; return false }
                    if (downAt > 0L && System.currentTimeMillis() - downAt > holdMs) {
                        measuring = true
                        map.performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
                    } else return false
                }
                val pr = mv.projection
                a = pr.fromPixels(e.getX(0).toInt(), e.getY(0).toInt()) as GeoPoint
                b = pr.fromPixels(e.getX(1).toInt(), e.getY(1).toInt()) as GeoPoint
                mv.invalidate(); onChange()
                return true
            }
            MotionEvent.ACTION_POINTER_UP, MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                downAt = 0L
                val was = measuring || dragEnd != 0
                // The ruler stays where it was put; the fingers are free to move the chart again.
                measuring = false
                dragEnd = 0
                if (was) { mv.invalidate(); onChange(); return true }
            }
        }
        return false
    }

    /** A tap on the ruler puts it away — unless it is locked, when nothing does. */
    override fun onSingleTapConfirmed(e: MotionEvent, mv: MapView): Boolean {
        if (locked || !up) return false
        pin(mv)
        if (near(e.x, e.y, pa) || near(e.x, e.y, pb) || distToLine(e.x, e.y) < 22 * d) { clear(); return true }
        return false
    }

    private fun distToLine(x: Float, y: Float): Float {
        val x1 = pa.x.toFloat(); val y1 = pa.y.toFloat(); val x2 = pb.x.toFloat(); val y2 = pb.y.toFloat()
        val dx = x2 - x1; val dy = y2 - y1
        val len = dx * dx + dy * dy
        if (len < 1f) return Math.hypot((x - x1).toDouble(), (y - y1).toDouble()).toFloat()
        val t = (((x - x1) * dx + (y - y1) * dy) / len).coerceIn(0f, 1f)
        return Math.hypot((x - (x1 + t * dx)).toDouble(), (y - (y1 + t * dy)).toDouble()).toFloat()
    }

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow) return
        val p = a ?: return
        val q = b ?: return
        pin(mv)
        val ax = pa.x.toFloat(); val ay = pa.y.toFloat()
        val bx = pb.x.toFloat(); val by = pb.y.toFloat()
        val nm = Nav.distanceNm(p.latitude, p.longitude, q.latitude, q.longitude)
        val outT = Nav.bearingTrue(p.latitude, p.longitude, q.latitude, q.longitude)
        val out = Nav.magnetic(outT, p.latitude, p.longitude)
        val back = Nav.magnetic(Nav.bearingTrue(q.latitude, q.longitude, p.latitude, p.longitude), q.latitude, q.longitude)
        if (locked) { line.color = 0xFF4DA3FF.toInt(); knob.color = 0xFF4DA3FF.toInt(); sub.color = 0xFF4DA3FF.toInt() }
        else { line.color = 0xFFFFD60A.toInt(); knob.color = 0xFFFFD60A.toInt(); sub.color = 0xFFFFD60A.toInt() }
        c.drawLine(ax, ay, bx, by, halo)
        c.drawLine(ax, ay, bx, by, line)
        // A tick every whole mile, so the eye can step the distance off as on a paper plotter.
        if (nm > 0.2) {
            val steps = Math.floor(nm).toInt().coerceAtMost(60)
            val ux = (bx - ax) / nm.toFloat(); val uy = (by - ay) / nm.toFloat()
            val h = Math.hypot(ux.toDouble(), uy.toDouble()).toFloat().coerceAtLeast(0.0001f)
            val px = -uy / h; val py = ux / h
            for (k in 1..steps) {
                val x = ax + ux * k; val y = ay + uy * k
                val len = if (k % 10 == 0) 9 * d else if (k % 5 == 0) 6 * d else 3.5f * d
                c.drawLine(x - px * len, y - py * len, x + px * len, y + py * len, tick)
            }
        }
        for (pt in listOf(ax to ay, bx to by)) {
            c.drawCircle(pt.first, pt.second, 7 * d, knob)
            c.drawCircle(pt.first, pt.second, 7 * d, knobEdge)
        }
        // The reading, upright whatever the chart's turn, beside the middle of the line.
        val mx = (ax + bx) / 2; val my = (ay + by) / 2
        val gs = groundSpeedKt()
        val speed = if (gs > 20) gs else cruiseKt()
        val l1 = if (nm < 3.0) "%.2f nm  ·  %,d ft".format(nm, Math.round(nm * 6076.12)) else "%.1f nm".format(nm)
        val l2 = "${Nav.deg(out)}M out  ·  ${Nav.deg(back)}M back"
        val burn = gph()
        val l3 = if (speed > 20) {
            val mins = nm / speed * 60
            "%s at %d kt".format(FlightPlan.hm(mins), Math.round(speed)) +
                (if (burn > 0) "  ·  %.1f gal".format(nm / speed * burn) else "") +
                (if (gs > 20) "" else "  (planned)")
        } else ""
        c.save()
        c.rotate(-mv.mapOrientation, mx, my)
        val w = maxOf(big.measureText(l1), maxOf(sub.measureText(l2), dim.measureText(l3)))
        val tall = if (l3.isEmpty()) 44 * d else 60 * d
        val r = RectF(mx - w / 2 - 10 * d, my - tall, mx + w / 2 + 10 * d, my - 6 * d)
        c.drawRoundRect(r, 9 * d, 9 * d, bg)
        c.drawText(l1, mx - w / 2, my - tall + 18 * d, big)
        c.drawText(l2, mx - w / 2, my - tall + 33 * d, sub)
        if (l3.isNotEmpty()) c.drawText(l3, mx - w / 2, my - tall + 49 * d, dim)
        c.restore()
    }
}
