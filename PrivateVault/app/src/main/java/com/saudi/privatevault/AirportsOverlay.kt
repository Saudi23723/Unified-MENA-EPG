package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import android.view.MotionEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import kotlin.math.hypot

/**
 * Airports on the map, each ringed in its weather's flight-category colour
 * (VFR green, MVFR blue, IFR red, LIFR magenta) when it reports a METAR.
 * Identifiers show once zoomed in; a tap opens the airport.
 */
class AirportsOverlay(private val map: MapView) : Overlay() {

    var airports: List<AviationData.Airport> = emptyList()
    var weather: Map<String, AviationData.Metar> = emptyMap()
    var onPick: ((AviationData.Airport) -> Unit)? = null

    private val d = map.resources.displayMetrics.density
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 11 * d
        isFakeBoldText = true
        color = 0xFF1A237E.toInt()
    }
    private val halo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 11 * d
        isFakeBoldText = true
        style = Paint.Style.STROKE
        strokeWidth = 3 * d
        color = 0xEEFFFFFF.toInt()
    }
    private val pt = Point()

    fun station(a: AviationData.Airport) = a.icao.ifEmpty { if (a.ident.length == 3) "K" + a.ident else a.ident }

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val zoom = mapView.zoomLevelDouble
        if (zoom < 7) return
        val box = mapView.boundingBox
        val showNames = zoom >= 9
        for (a in airports) {
            if (a.lat < box.latSouth || a.lat > box.latNorth || a.lon < box.lonWest || a.lon > box.lonEast) continue
            mapView.projection.toPixels(GeoPoint(a.lat, a.lon), pt)
            val m = weather[station(a)]
            val r = (if (zoom >= 10) 7 else 5) * d
            if (m != null) {
                fill.color = AviationData.categoryColor(m.category)
                c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), r, fill)
                ring.color = 0xFFFFFFFF.toInt()
                ring.strokeWidth = 2 * d
                c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), r, ring)
            } else {
                ring.color = 0xFF3949AB.toInt()
                ring.strokeWidth = 2.5f * d
                c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), r * 0.8f, ring)
            }
            if (showNames) {
                val x = pt.x + r + 3 * d
                val y = pt.y + 4 * d
                c.drawText(a.ident, x, y, halo)
                c.drawText(a.ident, x, y, text)
            }
        }
    }

    override fun onSingleTapConfirmed(e: MotionEvent, mapView: MapView): Boolean {
        if (mapView.zoomLevelDouble < 7) return false
        var best: AviationData.Airport? = null
        var bestD = 22 * d
        for (a in airports) {
            mapView.projection.toPixels(GeoPoint(a.lat, a.lon), pt)
            val dd = hypot(pt.x - e.x, pt.y - e.y)
            if (dd < bestD) {
                bestD = dd
                best = a
            }
        }
        best ?: return false
        onPick?.invoke(best)
        return true
    }
}
