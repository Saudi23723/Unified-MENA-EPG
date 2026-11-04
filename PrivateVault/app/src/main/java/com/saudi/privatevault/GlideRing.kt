package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Point
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * How far the aeroplane could glide from here with the engine out: the
 * height above the ground below times the glide ratio the pilot enters
 * from the POH (nothing is drawn without one), still air, as a ring round
 * the aircraft. A planning aid only: wind, turns and the terrain on the
 * way all shorten it.
 */
class GlideRing(private val map: MapView, private val where: () -> GeoPoint?, private val altFt: () -> Double?) : Overlay() {
    var ratio = 0.0
    private val d = map.resources.displayMetrics.density
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 2.5f * d; color = 0xCC30D158.toInt()
        pathEffect = DashPathEffect(floatArrayOf(14 * d, 8 * d), 0f)
    }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x1430D158 }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF30D158.toInt(); textSize = 12 * d; isFakeBoldText = true }
    private val halo = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xDD000000.toInt(); textSize = 12 * d; isFakeBoldText = true; style = Paint.Style.STROKE; strokeWidth = 3 * d }
    private val a = Point()
    private val b = Point()

    /** Nautical miles of still-air glide from here, or null. */
    fun rangeNm(): Double? {
        if (ratio <= 0) return null
        val g = where() ?: return null
        val alt = altFt() ?: return null
        val ground = Terrain.elevationFt(g.latitude, g.longitude) ?: return null
        val agl = alt - ground
        if (agl < 100) return null
        return agl * ratio / 6076.12
    }

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val nm = rangeNm() ?: return
        val g = where() ?: return
        mapView.projection.toPixels(g, a)
        mapView.projection.toPixels(Nav.destination(g.latitude, g.longitude, 90.0, nm), b)
        val r = Math.hypot((b.x - a.x).toDouble(), (b.y - a.y).toDouble()).toFloat()
        if (r < 6 * d) return
        c.drawCircle(a.x.toFloat(), a.y.toFloat(), r, fill)
        c.drawCircle(a.x.toFloat(), a.y.toFloat(), r, ring)
        val s = "GLIDE %.1f nm".format(nm)
        c.drawText(s, a.x - text.measureText(s) / 2, a.y - r - 6 * d, halo)
        c.drawText(s, a.x - text.measureText(s) / 2, a.y - r - 6 * d, text)
    }
}
