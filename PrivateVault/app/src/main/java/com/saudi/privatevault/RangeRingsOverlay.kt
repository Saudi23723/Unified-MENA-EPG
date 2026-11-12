package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import android.graphics.RectF
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * Range rings around the aircraft, as ForeFlight draws them: two or three circles at round
 * distances chosen for the zoom (2/5, 5/10, 10/20, 20/50 NM…), each with its distance on a tag.
 */
class RangeRingsOverlay(map: MapView, private val where: () -> GeoPoint?) : Overlay() {
    private val d = map.resources.displayMetrics.density
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xE6FFFFFF.toInt(); strokeWidth = 2.2f * d }
    private val shade = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0x66000000; strokeWidth = 4.5f * d }
    private val tagBg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xE61A1C20.toInt() }
    private val tagTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); textSize = 12.5f * d; isFakeBoldText = true; textAlign = Paint.Align.CENTER }
    private val c0 = Point(); private val c1 = Point()

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val p = where() ?: return
        val pr = mapView.projection
        pr.toPixels(p, c0)
        // Pixels per nautical mile here, from a point one mile north.
        val n = Nav.destination(p.latitude, p.longitude, 0.0, 1.0)
        pr.toPixels(GeoPoint(n.latitude, n.longitude), c1)
        val pxPerNm = Math.hypot((c1.x - c0.x).toDouble(), (c1.y - c0.y).toDouble())
        if (pxPerNm <= 0) return
        // Rings that fit the screen: the largest about 40 % of its shorter side.
        val span = minOf(mapView.width, mapView.height) * 0.42 / pxPerNm
        val steps = listOf(1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0)
        val outer = steps.lastOrNull { it <= span } ?: steps.first()
        val inner = steps.lastOrNull { it < outer * 0.6 }
        for (nm in listOfNotNull(inner, outer)) {
            val r = (nm * pxPerNm).toFloat()
            c.drawCircle(c0.x.toFloat(), c0.y.toFloat(), r, shade)
            c.drawCircle(c0.x.toFloat(), c0.y.toFloat(), r, ring)
            // The tag at the lower right of the ring, upright whatever the chart's turn.
            val a = Math.toRadians(135.0 - mapView.mapOrientation)
            val tx = c0.x + (r * Math.sin(a)).toFloat(); val ty = c0.y - (r * Math.cos(a)).toFloat()
            val s = (if (nm < 10) "%.0f" else "%.0f").format(nm) + "nm"
            val w = tagTx.measureText(s) / 2 + 7 * d
            c.save(); c.rotate(-mapView.mapOrientation, tx, ty)
            c.drawRoundRect(RectF(tx - w, ty - 11 * d, tx + w, ty + 9 * d), 5 * d, 5 * d, tagBg)
            c.drawText(s, tx, ty + 4 * d, tagTx)
            c.restore()
        }
    }
}
