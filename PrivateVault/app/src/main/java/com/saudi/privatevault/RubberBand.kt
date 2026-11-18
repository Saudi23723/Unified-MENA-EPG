package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import android.view.MotionEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * Rubber-banding, as an EFB does it: press and hold the route line until a circle appears under the
 * finger, then — without lifting — drag the line where it should go, round the weather or the high
 * ground. The leg bends live as the finger moves. When the finger lifts, the map asks what to put
 * there: the point itself, or a field, a navaid or a fix near it.
 */
class RubberBandOverlay(
    private val map: MapView,
    private val plan: () -> FlightPlan,
    /** Called when the finger lifts, with the leg being bent and where it was dropped. */
    private val onDrop: (leg: Int, at: GeoPoint) -> Unit,
) : Overlay() {

    private val d = map.resources.displayMetrics.density
    private val band = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 4f * d; color = 0xFFE040FB.toInt(); strokeCap = Paint.Cap.ROUND
    }
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 3f * d; color = 0xFF2D8CFF.toInt()
    }
    private val ringFill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x442D8CFF }
    private val tagBg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xF01B1D22.toInt() }
    private val tagTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); textSize = 12f * d; isFakeBoldText = true }
    private val pa = Point(); private val pb = Point()

    /**
     * The Direct-To line, when one is being flown: where it starts and where it goes. A Direct-To
     * is a leg like any other and a pilot bends it round weather and high ground like any other,
     * so it is offered to the finger too, as leg 0.
     */
    var directLine: Pair<GeoPoint, GeoPoint>? = null

    /** The leg being bent, or -1; and where the finger is now. */
    private var leg = -1
    private var at: GeoPoint? = null
    private var armed = false

    val dragging get() = leg >= 0

    /** Which leg lies under a point on the screen, within about a fifth of an inch. */
    private fun legAt(x: Float, y: Float): Int {
        val p = plan()
        val pr = map.projection
        var best = -1
        var bestD = 24 * d
        directLine?.let { (s0, s1) ->
            val a = pr.toPixels(s0, null); val b = pr.toPixels(s1, null)
            val dx = (b.x - a.x).toFloat(); val dy = (b.y - a.y).toFloat()
            val len2 = dx * dx + dy * dy
            val u = if (len2 == 0f) 0f else (((x - a.x) * dx + (y - a.y) * dy) / len2).coerceIn(0f, 1f)
            val dist = Math.hypot((x - (a.x + u * dx)).toDouble(), (y - (a.y + u * dy)).toDouble()).toFloat()
            if (dist < bestD) { bestD = dist; best = 0 }
        }
        if (p.points.size < 2) return best
        for (i in 1 until p.points.size) {
            val a = pr.toPixels(GeoPoint(p.points[i - 1].lat, p.points[i - 1].lon), null)
            val b = pr.toPixels(GeoPoint(p.points[i].lat, p.points[i].lon), null)
            val dx = (b.x - a.x).toFloat(); val dy = (b.y - a.y).toFloat()
            val len2 = dx * dx + dy * dy
            val u = if (len2 == 0f) 0f else (((x - a.x) * dx + (y - a.y) * dy) / len2).coerceIn(0f, 1f)
            val dist = Math.hypot((x - (a.x + u * dx)).toDouble(), (y - (a.y + u * dy)).toDouble()).toFloat()
            if (dist < bestD) { bestD = dist; best = i }
        }
        return best
    }

    /** The map calls this when a long press lands; true when it has taken hold of a leg. */
    override fun onLongPress(e: MotionEvent, mv: MapView): Boolean {
        val i = legAt(e.x, e.y)
        if (i < 0) return false
        leg = i
        at = mv.projection.fromPixels(e.x.toInt(), e.y.toInt()) as GeoPoint
        armed = true
        mv.performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
        mv.invalidate()
        return true
    }

    /** Let go of the leg, whatever is happening. */
    fun release() { leg = -1; at = null; armed = false; map.invalidate() }

    override fun onTouchEvent(e: MotionEvent, mv: MapView): Boolean {
        if (leg < 0) return false
        // A second finger is a map gesture, never a bend: let the leg go and let the map have it.
        if (e.pointerCount > 1) { leg = -1; at = null; armed = false; mv.invalidate(); return false }
        when (e.actionMasked) {
            MotionEvent.ACTION_MOVE -> {
                at = mv.projection.fromPixels(e.x.toInt(), e.y.toInt()) as GeoPoint
                mv.invalidate()
                return true
            }
            MotionEvent.ACTION_UP -> {
                val where = at
                val which = leg
                leg = -1; at = null; armed = false
                mv.invalidate()
                if (where != null) onDrop(which, where)
                return true
            }
            MotionEvent.ACTION_CANCEL -> { leg = -1; at = null; armed = false; mv.invalidate(); return true }
        }
        return false
    }

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow || leg < 0) return
        val p = plan()
        val g = at ?: return
        val pr = mv.projection
        val ends: Pair<GeoPoint, GeoPoint> = if (leg == 0) (directLine ?: return)
            else {
                if (leg >= p.points.size) return
                GeoPoint(p.points[leg - 1].lat, p.points[leg - 1].lon) to GeoPoint(p.points[leg].lat, p.points[leg].lon)
            }
        pr.toPixels(ends.first, pa)
        pr.toPixels(ends.second, pb)
        val here = pr.toPixels(g, null)
        // The leg, bent through the finger.
        c.drawLine(pa.x.toFloat(), pa.y.toFloat(), here.x.toFloat(), here.y.toFloat(), band)
        c.drawLine(here.x.toFloat(), here.y.toFloat(), pb.x.toFloat(), pb.y.toFloat(), band)
        c.drawCircle(here.x.toFloat(), here.y.toFloat(), 17 * d, ringFill)
        c.drawCircle(here.x.toFloat(), here.y.toFloat(), 17 * d, ring)
        // How much longer the route has become by bending it here.
        val straight = Nav.distanceNm(ends.first.latitude, ends.first.longitude, ends.second.latitude, ends.second.longitude)
        val bent = Nav.distanceNm(ends.first.latitude, ends.first.longitude, g.latitude, g.longitude) +
            Nav.distanceNm(g.latitude, g.longitude, ends.second.latitude, ends.second.longitude)
        val s = "+%.1f nm".format((bent - straight).coerceAtLeast(0.0))
        val w = tagTx.measureText(s)
        c.save(); c.rotate(-mv.mapOrientation, here.x.toFloat(), here.y.toFloat())
        c.drawRoundRect(here.x - w / 2 - 8 * d, here.y - 44 * d, here.x + w / 2 + 8 * d, here.y - 22 * d, 6 * d, 6 * d, tagBg)
        c.drawText(s, here.x - w / 2, here.y - 28 * d, tagTx)
        c.restore()
    }
}
