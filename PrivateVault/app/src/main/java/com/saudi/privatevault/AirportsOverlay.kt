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

    /** What each airport carries, as an EFB offers it: nothing more, its weather (station model), or the winds aloft. */
    enum class Data { NONE, WEATHER, WINDS }
    var data = Data.NONE
    /** The FB winds text and the altitude to show them at. */
    var winds: String = ""
    var windsAlt = 6000
    private val barb = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; color = 0xFF0D1B2A.toInt() }
    private val small = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10.5f * map.resources.displayMetrics.density; isFakeBoldText = true }
    private val smallHalo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 10.5f * map.resources.displayMetrics.density; isFakeBoldText = true
        style = Paint.Style.STROKE; strokeWidth = 3 * map.resources.displayMetrics.density; color = 0xEEFFFFFF.toInt()
    }

    /** A wind barb from the station, pointing where the wind comes from: a pennant per 50 kt, a line per 10, half per 5. */
    private fun drawBarb(c: Canvas, x: Float, y: Float, fromDeg: Int, kt: Int, color: Int) {
        if (kt < 3) { barb.color = color; barb.strokeWidth = 1.6f * d; c.drawCircle(x, y, 9 * d, barb); return }
        val a = Math.toRadians(fromDeg.toDouble())
        val len = 26 * d
        val ex = x + (Math.sin(a) * len).toFloat(); val ey = y - (Math.cos(a) * len).toFloat()
        barb.color = color; barb.strokeWidth = 2 * d
        c.drawLine(x, y, ex, ey, barb)
        // Feathers on the end, square to the shaft, on its clockwise side.
        val px = (Math.cos(a) * 9 * d).toFloat(); val py = (Math.sin(a) * 9 * d).toFloat()
        val ux = ((x - ex) / len); val uy = ((y - ey) / len)
        var left = ((kt + 2) / 5) * 5
        var at = 0f
        while (left >= 50) {
            val bx = ex + ux * at; val by = ey + uy * at
            val path = android.graphics.Path().apply { moveTo(bx, by); lineTo(bx + px, by + py); lineTo(bx + ux * 6 * d, by + uy * 6 * d); close() }
            barb.style = Paint.Style.FILL; c.drawPath(path, barb); barb.style = Paint.Style.STROKE
            left -= 50; at += 7 * d
        }
        while (left >= 10) { val bx = ex + ux * at; val by = ey + uy * at; c.drawLine(bx, by, bx + px, by + py, barb); left -= 10; at += 4.5f * d }
        if (left >= 5) { if (at == 0f) at = 4.5f * d; val bx = ex + ux * at; val by = ey + uy * at; c.drawLine(bx, by, bx + px / 2, by + py / 2, barb) }
    }

    private fun label(c: Canvas, s: String, x: Float, y: Float, color: Int) {
        c.drawText(s, x, y, smallHalo); small.color = color; c.drawText(s, x, y, small)
    }

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
            val px = pt.x.toFloat(); val py = pt.y.toFloat()
            if (data == Data.WEATHER && m != null && zoom >= 8) {
                // Station model: temperature and dew point on the left, altimeter on the right, the wind barb.
                val j = m.json
                j?.opt("wdir")?.toString()?.toDoubleOrNull()?.let { wd -> drawBarb(c, px, py, wd.toInt(), j.optInt("wspd", 0), AviationData.categoryColor(m.category)) }
                j?.opt("temp")?.toString()?.toDoubleOrNull()?.let { label(c, "%.0f°".format(it), px - 30 * d, py - 4 * d, 0xFFC62828.toInt()) }
                j?.opt("dewp")?.toString()?.toDoubleOrNull()?.let { label(c, "%.0f°".format(it), px - 30 * d, py + 12 * d, 0xFF2E7D32.toInt()) }
                j?.opt("altim")?.toString()?.toDoubleOrNull()?.let { a -> label(c, "%.2f".format(if (a > 100) a * 0.02953 else a), px + r + 4 * d, py - 4 * d, 0xFF1A237E.toInt()) }
                j?.opt("visib")?.toString()?.let { label(c, it.replace("+", ""), px - 30 * d, py + 28 * d, 0xFF424242.toInt()) }
            }
            if (data == Data.WINDS && winds.isNotEmpty() && zoom >= 7 && a.icao.isNotEmpty() && a.ident.length == 3) {
                AviationData.windAt(winds, a.lat, a.lon, windsAlt)?.let { (wd, kt, t) ->
                    drawBarb(c, px, py, wd, kt, 0xFF1565C0.toInt())
                    label(c, "$kt" + (t?.let { " ${it}°" } ?: ""), px + r + 4 * d, py + 14 * d, 0xFF1565C0.toInt())
                }
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
