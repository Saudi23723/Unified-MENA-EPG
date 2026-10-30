package com.saudi.privatevault

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors

/**
 * Ground elevation anywhere, from the open terrain tiles of the AWS
 * Terrain Tiles dataset (SRTM and others), each pixel an elevation in
 * metres coded in its colour. Tiles are kept on the phone once fetched,
 * so terrain awareness keeps working in the air without signal.
 */
object Terrain {
    const val Z = 10   // about 150 m a pixel at these latitudes
    private const val URL_BASE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"

    /** A tile's elevations in feet, 256 x 256. */
    class Tile(val z: Int, val x: Int, val y: Int, val ft: FloatArray)

    private lateinit var dir: File
    private val memory = LruCache<String, Tile>(48)
    private val pending = ConcurrentHashMap.newKeySet<String>()
    private val pool = Executors.newFixedThreadPool(3)
    /** Called on a background thread when a tile arrives. */
    var onTile: (() -> Unit)? = null

    fun init(ctx: Context) {
        if (!::dir.isInitialized) dir = File(ctx.filesDir, "terrain").apply { mkdirs() }
    }

    fun tileX(lon: Double, z: Int) = Math.floor((lon + 180) / 360 * (1 shl z)).toInt()
    fun tileY(lat: Double, z: Int): Int {
        val r = Math.toRadians(lat)
        return Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * (1 shl z)).toInt()
    }
    fun lonOf(x: Double, z: Int) = x / (1 shl z) * 360 - 180
    fun latOf(y: Double, z: Int): Double = Math.toDegrees(Math.atan(Math.sinh(Math.PI * (1 - 2 * y / (1 shl z)))))

    /** The tile if it is at hand; otherwise it is fetched in the background and null is returned. */
    fun tile(x: Int, y: Int, z: Int = Z): Tile? {
        val key = "$z/$x/$y"
        memory.get(key)?.let { return it }
        if (!::dir.isInitialized) return null
        if (pending.add(key)) pool.execute {
            try {
                load(x, y, z)?.let { memory.put(key, it); onTile?.invoke() }
            } finally {
                pending.remove(key)
            }
        }
        return null
    }

    /** The same, waiting for it (for background work only). */
    fun tileNow(x: Int, y: Int, z: Int = Z): Tile? {
        val key = "$z/$x/$y"
        memory.get(key)?.let { return it }
        return load(x, y, z)?.also { memory.put(key, it) }
    }

    private fun load(x: Int, y: Int, z: Int): Tile? {
        val f = File(dir, "$z/$x/$y.png")
        if (f.length() == 0L) {
            try {
                val c = URL("$URL_BASE/$z/$x/$y.png").openConnection() as HttpURLConnection
                c.connectTimeout = 15000
                c.readTimeout = 30000
                try {
                    if (c.responseCode != 200) return null
                    f.parentFile?.mkdirs()
                    val tmp = File(f.path + ".part")
                    c.inputStream.use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
                    tmp.renameTo(f)
                } finally {
                    c.disconnect()
                }
            } catch (e: Exception) {
                return null
            }
        }
        val bmp = BitmapFactory.decodeFile(f.path, BitmapFactory.Options().apply {
            inPreferredConfig = Bitmap.Config.ARGB_8888
            inPremultiplied = false
        }) ?: return null
        val px = IntArray(bmp.width * bmp.height)
        bmp.getPixels(px, 0, bmp.width, 0, 0, bmp.width, bmp.height)
        bmp.recycle()
        val ft = FloatArray(px.size)
        for (i in px.indices) {
            val p = px[i]
            val m = ((p shr 16) and 0xFF) * 256.0 + ((p shr 8) and 0xFF) + (p and 0xFF) / 256.0 - 32768
            ft[i] = (m * 3.28084).toFloat().coerceAtLeast(0f)
        }
        return Tile(z, x, y, ft)
    }

    /** Ground elevation in feet, or null while its tile is not at hand. */
    fun elevationFt(lat: Double, lon: Double, wait: Boolean = false): Float? {
        val n = 1 shl Z
        val fx = (lon + 180) / 360 * n
        val r = Math.toRadians(lat)
        val fy = (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n
        val x = Math.floor(fx).toInt(); val y = Math.floor(fy).toInt()
        val t = (if (wait) tileNow(x, y) else tile(x, y)) ?: return null
        val px = ((fx - x) * 256).toInt().coerceIn(0, 255)
        val py = ((fy - y) * 256).toInt().coerceIn(0, 255)
        return t.ft[py * 256 + px]
    }

    /** Fetches every tile a box needs, for use before a flight (background thread). */
    fun prefetch(south: Double, west: Double, north: Double, east: Double): Int {
        var n = 0
        for (x in tileX(west, Z)..tileX(east, Z)) for (y in tileY(north, Z)..tileY(south, Z)) if (tileNow(x, y) != null) n++
        return n
    }
}
