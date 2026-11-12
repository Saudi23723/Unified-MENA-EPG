package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * How far the aeroplane can glide from here with the engine out, as ForeFlight's glide advisor
 * draws it: not a circle but a shape, walked out along 48 bearings in half-mile steps, each step
 * losing the height the glide ratio says, stopping where the ground (with 300 ft to spare) comes up
 * to meet the airplane — so it reaches far over a valley and stops short at a ridge. Still air, best
 * glide (the SportStar's 59 KIAS); the ratio is set in the menu (10:1 by default). In flight only.
 */
class GlideRing(private val map: MapView, private val where: () -> GeoPoint?, private val altFt: () -> Double?) : Overlay() {
    var ratio = 10.0
    private val d = map.resources.displayMetrics.density
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 3f * d; color = 0xFF30D158.toInt(); strokeJoin = Paint.Join.ROUND }
    private val edgeHalo = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 6.5f * d; color = 0x99000000.toInt(); strokeJoin = Paint.Join.ROUND }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x2630D158 }
    private val tagBg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xE6143A1E.toInt() }
    private val tagTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); textSize = 12.5f * d; isFakeBoldText = true }
    private val pt = Point()
    private var shape: List<GeoPoint> = emptyList()
    private var builtAt: DoubleArray? = null
    private var reach = 0.0

    /** Nautical miles of still-air glide straight ahead over flat ground, or null on the ground. */
    fun rangeNm(): Double? {
        if (ratio <= 0) return null
        val g = where() ?: return null
        val alt = altFt() ?: return null
        val ground = Terrain.elevationFt(g.latitude, g.longitude) ?: return null
        val agl = alt - ground
        if (agl < 200) return null
        return agl * ratio / 6076.12
    }

    private fun build(g: GeoPoint, alt: Double) {
        val pts = ArrayList<GeoPoint>()
        var far = 0.0
        val ground0 = Terrain.elevationFt(g.latitude, g.longitude) ?: 0f
        val max = (alt - ground0) * ratio / 6076.12
        for (k in 0 until 48) {
            val brg = k * 7.5
            var dist = 0.0
            var last = GeoPoint(g.latitude, g.longitude)
            while (dist < max + 0.5) {
                val next = dist + 0.5
                val here = Nav.destination(g.latitude, g.longitude, brg, next)
                val h = alt - next * 6076.12 / ratio
                val ground = Terrain.elevationFt(here.latitude, here.longitude) ?: ground0
                if (h < ground + 300) break
                dist = next; last = GeoPoint(here.latitude, here.longitude)
            }
            pts.add(last); far = maxOf(far, dist)
        }
        shape = pts; reach = far
        builtAt = doubleArrayOf(g.latitude, g.longitude, alt)
    }

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        if (rangeNm() == null) return
        val g = where() ?: return
        val alt = altFt() ?: return
        val b = builtAt
        // Rebuilt when the airplane has moved a quarter mile or 100 ft.
        if (b == null || Nav.distanceNm(b[0], b[1], g.latitude, g.longitude) > 0.25 || Math.abs(b[2] - alt) > 100) build(g, alt)
        if (shape.size < 3) return
        val path = Path()
        for ((i, p) in shape.withIndex()) {
            mapView.projection.toPixels(p, pt)
            if (i == 0) path.moveTo(pt.x.toFloat(), pt.y.toFloat()) else path.lineTo(pt.x.toFloat(), pt.y.toFloat())
        }
        path.close()
        c.drawPath(path, fill)
        c.drawPath(path, edgeHalo)
        c.drawPath(path, edge)
        // The tag at the shape's northern edge, upright whatever the chart's turn.
        mapView.projection.toPixels(shape[0], pt)
        val s = "Glide %.1f nm · 59 KIAS · %.0f:1".format(reach, ratio)
        val w = tagTx.measureText(s)
        c.save(); c.rotate(-mapView.mapOrientation, pt.x.toFloat(), pt.y.toFloat())
        c.drawRoundRect(pt.x - w / 2 - 8 * d, pt.y - 26 * d, pt.x + w / 2 + 8 * d, pt.y - 6 * d, 6 * d, 6 * d, tagBg)
        c.drawText(s, pt.x - w / 2, pt.y - 11.5f * d, tagTx)
        c.restore()
    }
}
