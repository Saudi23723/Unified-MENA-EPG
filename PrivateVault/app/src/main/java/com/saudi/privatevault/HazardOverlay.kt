package com.saudi.privatevault

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import android.graphics.RectF
import android.util.LruCache
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * Terrain awareness: ground at or above the aircraft's altitude (less 100 ft)
 * in red, within 1000 ft below it in yellow, the rest left clear, the way a
 * hazard advisor shades a chart. In flight it follows the GPS altitude; on
 * the ground it shows the planned cruising altitude.
 */
class HazardOverlay(private val map: MapView) : Overlay() {

    /** The altitude to compare with, in feet MSL. */
    var altitudeFt = 5500.0
        set(v) {
            val bucket = Math.round(v / 100) * 100.0
            if (bucket != field) { field = bucket; map.postInvalidate() }
        }

    private val cache = LruCache<String, Bitmap>(40)
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG).apply { alpha = 150 }
    private val nw = Point()
    private val se = Point()
    private val rect = RectF()

    private fun colored(t: Terrain.Tile): Bitmap {
        val key = "${t.x}/${t.y}/${altitudeFt.toInt()}"
        cache.get(key)?.let { return it }
        val px = IntArray(256 * 256)
        val red = altitudeFt - 100
        val yellow = altitudeFt - 1000
        for (i in px.indices) {
            val e = t.ft[i]
            px[i] = when {
                e >= red -> 0xFFE53935.toInt()
                e >= yellow -> 0xFFFDD835.toInt()
                else -> 0
            }
        }
        val bmp = Bitmap.createBitmap(px, 256, 256, Bitmap.Config.ARGB_8888)
        cache.put(key, bmp)
        return bmp
    }

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow || mapView.zoomLevelDouble < 7) return
        val box = mapView.boundingBox
        val z = Terrain.Z
        val x0 = Terrain.tileX(box.lonWest, z); val x1 = Terrain.tileX(box.lonEast, z)
        val y0 = Terrain.tileY(box.latNorth, z); val y1 = Terrain.tileY(box.latSouth, z)
        if ((x1 - x0 + 1) * (y1 - y0 + 1) > 60) return
        val pr = mapView.projection
        for (x in x0..x1) for (y in y0..y1) {
            val t = Terrain.tile(x, y) ?: continue
            pr.toPixels(GeoPoint(Terrain.latOf(y.toDouble(), z), Terrain.lonOf(x.toDouble(), z)), nw)
            pr.toPixels(GeoPoint(Terrain.latOf(y + 1.0, z), Terrain.lonOf(x + 1.0, z)), se)
            rect.set(nw.x.toFloat(), nw.y.toFloat(), se.x.toFloat(), se.y.toFloat())
            c.drawBitmap(colored(t), null, rect, paint)
        }
    }
}
