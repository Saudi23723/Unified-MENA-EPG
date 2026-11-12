package com.saudi.privatevault

import android.content.Context
import org.osmdroid.util.GeoPoint

/**
 * One field's FAA airport diagram placed where it really lies (from the latitude and longitude
 * printed on it): the picture, its north-west and its south-east corners. Call off the main thread.
 */
object FaaDiagram {
    fun build(ctx: Context, ident: String): Triple<android.graphics.Bitmap, GeoPoint, GeoPoint>? = try {
        val res = AviationData.plates(ctx, ident)
        val apd = res?.second?.firstOrNull { it.code == "APD" }
        val f = apd?.let { AviationData.platePdf(ctx, res.first, it.pdf) }
        val geo = f?.let { PdfLinks.open(ctx, it)?.use { l -> l.georef(0) } }
        if (f == null || geo == null) null else {
            // The drawing: the page without its edges, title band and footer (the runways often run
            // past the last printed coordinate, so the grid alone would cut them).
            val x0 = 0.04; val x1 = 0.96
            val y0 = if (geo.turn == 0f) 0.085 else 0.05; val y1 = if (geo.turn == 0f) 0.925 else 0.95
            val pfd = android.os.ParcelFileDescriptor.open(f, android.os.ParcelFileDescriptor.MODE_READ_ONLY)
            var bmp = android.graphics.pdf.PdfRenderer(pfd).use { r ->
                r.openPage(0).use { pg ->
                    val pw = pg.width.toDouble(); val ph = pg.height.toDouble()
                    val cw = 1300
                    val s = cw / ((x1 - x0) * pw)
                    val ch = ((y1 - y0) * ph * s).toInt().coerceIn(200, 2600)
                    android.graphics.Bitmap.createBitmap(cw, ch, android.graphics.Bitmap.Config.ARGB_8888).also {
                        it.eraseColor(android.graphics.Color.WHITE)
                        val m = android.graphics.Matrix().apply {
                            postScale(s.toFloat(), s.toFloat())
                            postTranslate((-x0 * pw * s).toFloat(), (-y0 * ph * s).toFloat())
                        }
                        pg.render(it, null, m, android.graphics.pdf.PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    }
                }
            }
            val corners = listOf(geo.ground(x0, y0), geo.ground(x1, y0), geo.ground(x1, y1), geo.ground(x0, y1))
            val north = corners.maxOf { it[0] }; val south = corners.minOf { it[0] }
            val west = corners.minOf { it[1] }; val east = corners.maxOf { it[1] }
            val turn = -geo.turn
            if (turn != 0f) bmp = android.graphics.Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height,
                android.graphics.Matrix().apply { postRotate(turn) }, true)
            Triple(bmp, GeoPoint(north, west), GeoPoint(south, east))
        }
    } catch (e: Throwable) { null }
}
