package com.saudi.privatevault

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.drawable.BitmapDrawable
import org.osmdroid.tileprovider.MapTileProviderBasic
import org.osmdroid.tileprovider.ReusableBitmapDrawable
import org.osmdroid.tileprovider.modules.MapTileApproximater
import org.osmdroid.tileprovider.modules.MapTileFileStorageProviderBase
import org.osmdroid.tileprovider.modules.MapTileModuleProviderBase
import org.osmdroid.tileprovider.tilesource.ITileSource
import org.osmdroid.util.MapTileIndex
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Tiles for zoom levels finer than a chart was printed at, cut from the
 * finest tile there is and enlarged with smoothing, the way a scanned chart
 * is read up close, instead of osmdroid's blocky pixel doubling.
 */
class SmoothApproximater : MapTileApproximater() {

    private val sources = CopyOnWriteArrayList<MapTileModuleProviderBase>()
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG or Paint.DITHER_FLAG or Paint.ANTI_ALIAS_FLAG)

    override fun addProvider(pProvider: MapTileModuleProviderBase) {
        sources.add(pProvider)
        super.addProvider(pProvider)
    }

    // osmdroid's own loader calls this; here it is cut from the finest tile there is, with smoothing.
    override fun approximateTileFromLowerZoom(pMapTileIndex: Long): Bitmap? {
        val zoom = MapTileIndex.getZoom(pMapTileIndex)
        for (diff in 1..minOf(zoom, 10)) {
            for (p in sources) {
                val src = zoom - diff
                if (src < p.minimumZoomLevel || src > p.maximumZoomLevel) continue
                val srcTile = MapTileIndex.getTileIndex(src, MapTileIndex.getX(pMapTileIndex) shr diff, MapTileIndex.getY(pMapTileIndex) shr diff)
                val d = try { p.tileLoader.loadTileIfReachable(srcTile) } catch (e: Exception) { null } as? BitmapDrawable ?: continue
                crop(d, pMapTileIndex, diff)?.let { return it }
            }
        }
        return null
    }

    private fun crop(src: BitmapDrawable, index: Long, diff: Int): Bitmap? {
        val reusable = src as? ReusableBitmapDrawable
        reusable?.beginUsingDrawable()
        try {
            if (reusable != null && !reusable.isBitmapValid) return null
            val b = src.bitmap ?: return null
            val size = b.width
            val part = size.toFloat() / (1 shl diff)
            if (part < 1f) return null
            val sx = (MapTileIndex.getX(index) % (1 shl diff)) * part
            val sy = (MapTileIndex.getY(index) % (1 shl diff)) * part
            val out = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
            Canvas(out).drawBitmap(b, Rect(sx.toInt(), sy.toInt(), (sx + part).toInt().coerceAtLeast(sx.toInt() + 1), (sy + part).toInt().coerceAtLeast(sy.toInt() + 1)),
                Rect(0, 0, size, size), paint)
            return out
        } finally {
            reusable?.finishUsingDrawable()
        }
    }
}

/** osmdroid's usual tiles (cache, archives, internet), with the smooth enlarger. */
class SmoothTileProvider(ctx: Context, source: ITileSource) : MapTileProviderBasic(ctx, source) {
    override fun createApproximater(
        assetsProvider: MapTileFileStorageProviderBase,
        cacheProvider: MapTileFileStorageProviderBase,
        archiveProvider: MapTileFileStorageProviderBase,
    ): MapTileApproximater = SmoothApproximater().apply {
        addProvider(assetsProvider)
        addProvider(cacheProvider)
        addProvider(archiveProvider)
    }
}
