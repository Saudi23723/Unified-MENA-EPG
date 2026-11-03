package com.saudi.privatevault

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import android.graphics.Rect
import android.graphics.RectF
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import kotlin.math.PI
import kotlin.math.atan
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.tan

/**
 * NEXRAD radar drawn smooth, as an EFB draws it: the radar is about a
 * kilometre a pixel, so past a few zoom levels its tiles are stretched
 * with filtering (and a soft edge) instead of shown as blocks.
 */
class RadarOverlay(private val map: MapView) : Overlay() {
    private val base = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913"
    private val cache = object : LinkedHashMap<String, Bitmap>(96, 0.75f, true) {
        override fun removeEldestEntry(e: MutableMap.MutableEntry<String, Bitmap>?) = size > 96
    }
    private val loading = HashSet<String>()
    private val pool = Executors.newFixedThreadPool(4)
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG).apply { alpha = 175 }
    private var bucket = System.currentTimeMillis() / 300000
    private val a = Point()
    private val b = Point()
    private val src = Rect()
    private val dst = RectF()

    /** New radar every five minutes. */
    fun refresh() {
        synchronized(cache) { cache.clear() }
        bucket = System.currentTimeMillis() / 300000
        map.postInvalidate()
    }

    private fun lon2x(lon: Double, z: Int) = ((lon + 180) / 360 * (1 shl z))
    private fun lat2y(lat: Double, z: Int): Double {
        val r = Math.toRadians(lat.coerceIn(-85.0, 85.0))
        return (1 - ln(tan(r) + 1 / Math.cos(r)) / PI) / 2 * (1 shl z)
    }
    private fun x2lon(x: Double, z: Int) = x / (1 shl z) * 360 - 180
    private fun y2lat(y: Double, z: Int): Double = Math.toDegrees(atan(Math.sinh(PI * (1 - 2 * y / (1 shl z)))))

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        if (System.currentTimeMillis() / 300000 != bucket) refresh()
        // The radar's own detail tops out near zoom 8; above that, the same tiles stretched smooth.
        val z = (floor(mapView.zoomLevelDouble).toInt() - 1).coerceIn(3, 8)
        val box = mapView.boundingBox
        val x0 = floor(lon2x(box.lonWest, z)).toInt(); val x1 = floor(lon2x(box.lonEast, z)).toInt()
        val y0 = floor(lat2y(box.latNorth, z)).toInt(); val y1 = floor(lat2y(box.latSouth, z)).toInt()
        val n = 1 shl z
        for (x in x0..x1) for (y in y0..y1) {
            if (y < 0 || y >= n) continue
            val xx = ((x % n) + n) % n
            val key = "$bucket/$z/$xx/$y"
            val bmp = synchronized(cache) { cache[key] }
            if (bmp == null) { fetch(key, z, xx, y); continue }
            mapView.projection.toPixels(GeoPoint(y2lat(y.toDouble(), z), x2lon(x.toDouble(), z)), a)
            mapView.projection.toPixels(GeoPoint(y2lat(y + 1.0, z), x2lon(x + 1.0, z)), b)
            src.set(0, 0, bmp.width, bmp.height)
            // A hair of overlap, so no seams show between stretched tiles.
            dst.set(a.x - 0.5f, a.y - 0.5f, b.x + 0.5f, b.y + 0.5f)
            c.drawBitmap(bmp, src, dst, paint)
        }
    }

    private fun fetch(key: String, z: Int, x: Int, y: Int) {
        synchronized(loading) { if (!loading.add(key)) return }
        pool.execute {
            try {
                val conn = URL("$base/$z/$x/$y.png?b=$bucket").openConnection() as HttpURLConnection
                conn.connectTimeout = 15000; conn.readTimeout = 20000
                conn.setRequestProperty("User-Agent", "PilotCompanion/1.0")
                val bmp = try { conn.inputStream.use { BitmapFactory.decodeStream(it) } } finally { conn.disconnect() }
                if (bmp != null) synchronized(cache) { cache[key] = bmp }
                map.postInvalidate()
            } catch (e: Exception) {
            } finally {
                synchronized(loading) { loading.remove(key) }
            }
        }
    }

    override fun onDetach(mapView: MapView?) {
        pool.shutdownNow()
        super.onDetach(mapView)
    }
}
