package com.saudi.privatevault

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.location.Location
import android.os.SystemClock
import android.view.MotionEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * The aircraft on the chart. Between GPS fixes it is moved along its track
 * at its ground speed, so it glides instead of jumping once a second. Ahead
 * of it a track vector marks where it will be in one, two and three minutes;
 * behind it the breadcrumb trail of the flight.
 */
class OwnshipOverlay(map: MapView, private val plane: Bitmap) : Overlay() {

    var fix: Location? = null
        private set
    private var fixAt = 0L
    /** A finger moved the map: the map stops following the aircraft. */
    var onUserPan: (() -> Unit)? = null

    private val trail = ArrayList<GeoPoint>()
    private val d = map.resources.displayMetrics.density
    private val vector = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF00E5FF.toInt()
        strokeWidth = 3 * d
        style = Paint.Style.STROKE
    }
    private val vectorHalo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xCC000000.toInt()
        strokeWidth = 6 * d
        style = Paint.Style.STROKE
    }
    private val crumbs = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xCC1565C0.toInt()
        strokeWidth = 2.5f * d
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(6 * d, 4 * d), 0f)
    }
    private val bmpPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val accuracy = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x221E88E5 }
    private val pt = Point()
    private val pt2 = Point()

    fun update(l: Location) {
        fix = l
        fixAt = SystemClock.elapsedRealtime()
        val g = GeoPoint(l.latitude, l.longitude)
        val last = trail.lastOrNull()
        if (last == null || Nav.distanceNm(last.latitude, last.longitude, g.latitude, g.longitude) > 0.02) {
            trail.add(g)
            if (trail.size > 4000) trail.subList(0, 1000).clear()
        }
    }

    fun clearTrail() = trail.clear()

    /** Knots, or 0 when standing still. */
    fun speedKt(): Double = fix?.takeIf { it.hasSpeed() }?.let { it.speed * 1.943844 } ?: 0.0

    /** Where the aircraft is now, carried forward from the last fix at its ground speed and track. */
    fun position(): GeoPoint? {
        val l = fix ?: return null
        val kt = speedKt()
        if (kt < 3 || !l.hasBearing()) return GeoPoint(l.latitude, l.longitude)
        val ageS = ((SystemClock.elapsedRealtime() - fixAt) / 1000.0).coerceAtMost(3.0)
        return Nav.destination(l.latitude, l.longitude, l.bearing.toDouble(), kt * ageS / 3600.0)
    }

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val l = fix ?: return
        val pr = mapView.projection
        if (trail.size > 1) {
            val path = Path()
            for ((i, g) in trail.withIndex()) {
                pr.toPixels(g, pt)
                if (i == 0) path.moveTo(pt.x.toFloat(), pt.y.toFloat()) else path.lineTo(pt.x.toFloat(), pt.y.toFloat())
            }
            position()?.let { pr.toPixels(it, pt); path.lineTo(pt.x.toFloat(), pt.y.toFloat()) }
            c.drawPath(path, crumbs)
        }
        val here = position() ?: return
        pr.toPixels(here, pt)
        if (l.hasAccuracy() && l.accuracy > 30) {
            c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), pr.metersToPixels(l.accuracy), accuracy)
        }
        val kt = speedKt()
        if (kt > 20 && l.hasBearing()) {
            // One, two and three minutes ahead along the track.
            val ahead = Nav.destination(here.latitude, here.longitude, l.bearing.toDouble(), kt * 3 / 60.0)
            pr.toPixels(ahead, pt2)
            c.drawLine(pt.x.toFloat(), pt.y.toFloat(), pt2.x.toFloat(), pt2.y.toFloat(), vectorHalo)
            c.drawLine(pt.x.toFloat(), pt.y.toFloat(), pt2.x.toFloat(), pt2.y.toFloat(), vector)
            for (m in 1..3) {
                val tick = Nav.destination(here.latitude, here.longitude, l.bearing.toDouble(), kt * m / 60.0)
                pr.toPixels(tick, pt2)
                c.drawCircle(pt2.x.toFloat(), pt2.y.toFloat(), 3.5f * d, vectorHalo)
                c.drawCircle(pt2.x.toFloat(), pt2.y.toFloat(), 2.5f * d, vector)
            }
        }
        c.save()
        c.rotate(if (l.hasBearing() && kt > 3) l.bearing else 0f, pt.x.toFloat(), pt.y.toFloat())
        c.drawBitmap(plane, pt.x - plane.width / 2f, pt.y - plane.height / 2f, bmpPaint)
        c.restore()
    }

    override fun onScroll(pEvent1: MotionEvent?, pEvent2: MotionEvent?, pDistanceX: Float, pDistanceY: Float, pMapView: MapView?): Boolean {
        onUserPan?.invoke()
        return false
    }
}
