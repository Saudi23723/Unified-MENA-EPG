package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.view.MotionEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import kotlin.math.hypot

/**
 * SIGMETs, AIRMETs and TFRs as shaded areas, and pilot reports as small
 * marks. A tap lists everything under the finger, with its full text.
 */
class WeatherOverlay(map: MapView) : Overlay() {

    var areas: List<AviationData.Area> = emptyList()
    var tfrs: List<AviationData.Area> = emptyList()
    var pireps: List<AviationData.Pirep> = emptyList()
    var showAirmets = true
    var showTfrs = true
    var showPireps = true
    var onPick: ((List<String>) -> Unit)? = null

    private val d = map.resources.displayMetrics.density
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 11 * d
        isFakeBoldText = true
        textAlign = Paint.Align.CENTER
    }
    private val halo = Paint(label).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3 * d
        color = 0xEEFFFFFF.toInt()
    }
    private val dash = DashPathEffect(floatArrayOf(9 * d, 5 * d), 0f)
    private val pt = Point()

    private fun visible(): List<AviationData.Area> =
        (if (showAirmets) areas else emptyList()) + (if (showTfrs) tfrs else emptyList())

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val pr = mapView.projection
        val box = mapView.boundingBox
        for (a in visible()) {
            var minLat = 90.0; var maxLat = -90.0; var minLon = 180.0; var maxLon = -180.0
            var i = 0
            while (i < a.pts.size) {
                minLat = minOf(minLat, a.pts[i]); maxLat = maxOf(maxLat, a.pts[i])
                minLon = minOf(minLon, a.pts[i + 1]); maxLon = maxOf(maxLon, a.pts[i + 1])
                i += 2
            }
            if (maxLat < box.latSouth || minLat > box.latNorth || maxLon < box.lonWest || minLon > box.lonEast) continue
            val path = Path()
            var sx = 0f; var sy = 0f
            i = 0
            while (i < a.pts.size) {
                pr.toPixels(GeoPoint(a.pts[i], a.pts[i + 1]), pt)
                if (i == 0) path.moveTo(pt.x.toFloat(), pt.y.toFloat()) else path.lineTo(pt.x.toFloat(), pt.y.toFloat())
                sx += pt.x; sy += pt.y
                i += 2
            }
            path.close()
            val tfr = a.kind == "TFR"
            fill.color = (a.color and 0x00FFFFFF) or (if (tfr) 0x40000000 else 0x26000000)
            c.drawPath(path, fill)
            edge.color = a.color
            edge.strokeWidth = (if (tfr) 3f else 2f) * d
            edge.pathEffect = if (a.kind == "AIRMET") dash else null
            c.drawPath(path, edge)
            if (mapView.zoomLevelDouble >= 7) {
                val n = a.pts.size / 2
                label.color = a.color
                c.save()
                c.rotate(-mapView.mapOrientation, sx / n, sy / n)
                c.drawText(a.label, sx / n, sy / n, halo)
                c.drawText(a.label, sx / n, sy / n, label)
                c.restore()
            }
        }
        if (showPireps && mapView.zoomLevelDouble >= 6) {
            for (p in pireps) {
                if (p.lat < box.latSouth || p.lat > box.latNorth || p.lon < box.lonWest || p.lon > box.lonEast) continue
                pr.toPixels(GeoPoint(p.lat, p.lon), pt)
                val r = 6 * d
                val tri = Path().apply {
                    moveTo(pt.x.toFloat(), pt.y - r)
                    lineTo(pt.x + r, pt.y + r * 0.8f)
                    lineTo(pt.x - r, pt.y + r * 0.8f)
                    close()
                }
                fill.color = when (p.kind) {
                    'T' -> 0xFFFF8F00.toInt()
                    'I' -> 0xFF0288D1.toInt()
                    else -> 0xFF546E7A.toInt()
                }
                c.drawPath(tri, fill)
                edge.pathEffect = null
                edge.strokeWidth = (if (p.urgent) 2.5f else 1.5f) * d
                edge.color = if (p.urgent) 0xFFD50000.toInt() else 0xFFFFFFFF.toInt()
                c.drawPath(tri, edge)
            }
        }
    }

    override fun onSingleTapConfirmed(e: MotionEvent, mapView: MapView): Boolean {
        val g = mapView.projection.fromPixels(e.x.toInt(), e.y.toInt())
        val hits = ArrayList<String>()
        if (showPireps) {
            for (p in pireps) {
                mapView.projection.toPixels(GeoPoint(p.lat, p.lon), pt)
                if (hypot(pt.x - e.x, pt.y - e.y) < 18 * d) hits.add("PIREP\n" + p.raw)
            }
        }
        for (a in visible()) if (a.contains(g.latitude, g.longitude)) hits.add(a.text)
        if (hits.isEmpty()) return false
        onPick?.invoke(hits)
        return true
    }
}
