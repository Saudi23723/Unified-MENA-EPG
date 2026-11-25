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

    // The flight's trail outlives the screen: going to notes, the radio or traffic and back keeps it.
    private val trail get() = TRAIL
    companion object { private val TRAIL = ArrayList<GeoPoint>() }
    /** How far the aircraft could glide, in nm; drawn as a ring when above zero. */
    var glideNm = 0.0
    private val glide = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xCC2E7D32.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * map.resources.displayMetrics.density
        pathEffect = DashPathEffect(floatArrayOf(14 * map.resources.displayMetrics.density, 8 * map.resources.displayMetrics.density), 0f)
    }
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
    // Where the aircraft has already been: green, as flown.
    private val crumbs = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF2BD96B.toInt()
        strokeWidth = 4f * d
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val crumbsHalo = Paint(crumbs).apply { color = 0xAA06210F.toInt(); strokeWidth = 7f * d }
    private val bmpPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val accuracy = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x221E88E5 }
    private val pt = Point()
    private val pt2 = Point()

    /** Degrees per second the track is turning, smoothed; positive is to the right. */
    var turnRate = 0.0
        private set
    private var prevBearing = Float.NaN
    private var prevAt = 0L

    fun update(l: Location) {
        val nowT = SystemClock.elapsedRealtime()
        if (l.hasBearing() && l.hasSpeed() && l.speed * 1.943844 > 30) {
            if (!prevBearing.isNaN() && nowT > prevAt && nowT - prevAt < 5000) {
                var dd = (l.bearing - prevBearing).toDouble()
                while (dd > 180) dd -= 360
                while (dd < -180) dd += 360
                val rate = (dd / ((nowT - prevAt) / 1000.0)).coerceIn(-6.0, 6.0)
                turnRate = turnRate * 0.7 + rate * 0.3
            }
            prevBearing = l.bearing; prevAt = nowT
        } else { turnRate = 0.0; prevBearing = Float.NaN }
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
            // Thousands of points would be worked out on every frame: about five hundred show the same line.
            val stepT = Math.max(1, trail.size / 500)
            var k = 0
            while (k < trail.size) {
                pr.toPixels(trail[k], pt)
                if (k == 0) path.moveTo(pt.x.toFloat(), pt.y.toFloat()) else path.lineTo(pt.x.toFloat(), pt.y.toFloat())
                k += stepT
            }
            position()?.let { pr.toPixels(it, pt); path.lineTo(pt.x.toFloat(), pt.y.toFloat()) }
            c.drawPath(path, crumbsHalo)
            c.drawPath(path, crumbs)
        }
        val here = position() ?: return
        pr.toPixels(here, pt)
        if (glideNm > 0.3) c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), pr.metersToPixels((glideNm * 1852).toFloat()), glide)
        if (l.hasAccuracy() && l.accuracy > 30) {
            c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), pr.metersToPixels(l.accuracy), accuracy)
        }
        val kt = speedKt()
        if (kt > 20 && l.hasBearing()) {
            // The track three minutes ahead: straight when wings are level, a curve when turning,
            // stepped every ten seconds with the turn rate measured from the last fixes.
            val curve = Path()
            curve.moveTo(pt.x.toFloat(), pt.y.toFloat())
            var cur = here
            var hdg = l.bearing.toDouble()
            val rate = if (Math.abs(turnRate) > 0.4) turnRate else 0.0
            val marks = ArrayList<GeoPoint>()
            for (sec in 10..180 step 10) {
                hdg += rate * 10
                cur = Nav.destination(cur.latitude, cur.longitude, hdg, kt * 10 / 3600.0)
                pr.toPixels(cur, pt2)
                curve.lineTo(pt2.x.toFloat(), pt2.y.toFloat())
                if (sec % 60 == 0) marks.add(cur)
            }
            c.drawPath(curve, vectorHalo)
            c.drawPath(curve, vector)
            for (m in marks) {
                pr.toPixels(m, pt2)
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
