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

/**
 * The plotter, as a pilot lays one on a paper chart: put two fingers on the map and hold them still
 * for a moment and a ruler springs up between them — the distance, the magnetic course each way, and
 * the time it would take at the speed being flown. Lift a finger and it is gone. Pinching to zoom
 * still works, because a pinch moves the fingers and this only wakes when they rest.
 */
class PlotterOverlay(
    private val map: MapView,
    private val groundSpeedKt: () -> Double,
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
    private val tick = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.6f * d; color = 0xCCFFFFFF.toInt() }

    private var on = false
    private var downAt = 0L
    private var startSpan = 0f
    private var startCx = 0f
    private var startCy = 0f
    private var ax = 0f; private var ay = 0f
    private var bx = 0f; private var by = 0f
    private val p0 = Point()

    /** How long the fingers must rest before the ruler appears, and how far they may drift. */
    private val holdMs = 260L
    private val slopPx get() = 16 * d

    private fun span(e: MotionEvent): Float =
        Math.hypot((e.getX(0) - e.getX(1)).toDouble(), (e.getY(0) - e.getY(1)).toDouble()).toFloat()

    override fun onTouchEvent(e: MotionEvent, mv: MapView): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_POINTER_DOWN -> if (e.pointerCount == 2) {
                downAt = System.currentTimeMillis()
                startSpan = span(e)
                startCx = (e.getX(0) + e.getX(1)) / 2; startCy = (e.getY(0) + e.getY(1)) / 2
            }
            MotionEvent.ACTION_MOVE -> {
                if (e.pointerCount != 2) { if (on) stop(mv); return false }
                val s = span(e)
                val cx = (e.getX(0) + e.getX(1)) / 2; val cy = (e.getY(0) + e.getY(1)) / 2
                if (!on) {
                    val moved = Math.abs(s - startSpan) > slopPx ||
                        Math.hypot((cx - startCx).toDouble(), (cy - startCy).toDouble()) > slopPx
                    // A pinch or a two-finger drag: leave it to the map.
                    if (moved) { downAt = 0L; return false }
                    if (downAt > 0L && System.currentTimeMillis() - downAt > holdMs) {
                        on = true
                        map.performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
                    } else return false
                }
                ax = e.getX(0); ay = e.getY(0); bx = e.getX(1); by = e.getY(1)
                mv.invalidate()
                return true
            }
            MotionEvent.ACTION_POINTER_UP, MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                downAt = 0L
                if (on) { stop(mv); return true }
            }
        }
        return false
    }

    private fun stop(mv: MapView) { on = false; mv.invalidate() }

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow || !on) return
        val pr = mv.projection
        val a = pr.fromPixels(ax.toInt(), ay.toInt()) as GeoPoint
        val b = pr.fromPixels(bx.toInt(), by.toInt()) as GeoPoint
        val nm = Nav.distanceNm(a.latitude, a.longitude, b.latitude, b.longitude)
        val outT = Nav.bearingTrue(a.latitude, a.longitude, b.latitude, b.longitude)
        val out = Nav.magnetic(outT, a.latitude, a.longitude)
        val back = (out + 180) % 360
        c.drawLine(ax, ay, bx, by, halo)
        c.drawLine(ax, ay, bx, by, line)
        // A tick every whole mile, so the eye can step the distance off as on a paper plotter.
        if (nm > 0.2) {
            val steps = Math.floor(nm).toInt().coerceAtMost(60)
            val ux = (bx - ax) / nm.toFloat(); val uy = (by - ay) / nm.toFloat()
            val px = -uy / Math.hypot(ux.toDouble(), uy.toDouble()).toFloat()
            val py = ux / Math.hypot(ux.toDouble(), uy.toDouble()).toFloat()
            for (k in 1..steps) {
                val x = ax + ux * k; val y = ay + uy * k
                val len = if (k % 10 == 0) 9 * d else if (k % 5 == 0) 6 * d else 3.5f * d
                c.drawLine(x - px * len, y - py * len, x + px * len, y + py * len, tick)
            }
        }
        for (p in listOf(ax to ay, bx to by)) {
            c.drawCircle(p.first, p.second, 7 * d, knob)
            c.drawCircle(p.first, p.second, 7 * d, knobEdge)
        }
        // The reading, upright whatever the chart's turn, beside the middle of the line.
        val mx = (ax + bx) / 2; val my = (ay + by) / 2
        val gs = groundSpeedKt()
        val l1 = "%.1f nm".format(nm)
        val l2 = "${Nav.deg(out)}M  ·  ${Nav.deg(back)}M back" + if (gs > 20) "  ·  %d min".format(Math.round(nm / gs * 60)) else ""
        c.save()
        c.rotate(-mv.mapOrientation, mx, my)
        val w = maxOf(big.measureText(l1), sub.measureText(l2))
        val r = RectF(mx - w / 2 - 10 * d, my - 44 * d, mx + w / 2 + 10 * d, my - 6 * d)
        c.drawRoundRect(r, 9 * d, 9 * d, bg)
        c.drawText(l1, mx - w / 2, my - 26 * d, big)
        c.drawText(l2, mx - w / 2, my - 11 * d, sub)
        c.restore()
    }
}
