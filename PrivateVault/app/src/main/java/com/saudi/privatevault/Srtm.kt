package com.saudi.privatevault

import android.content.Context
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.zip.GZIPInputStream

/**
 * The ground at thirty metres, for the tiles a route needs.
 *
 * The map's own ground data is a hundred and fifty metres to the pixel, which is right for
 * drawing a chart and for a glance at a profile, and a ridge a kilometre wide can still slip
 * between its samples. The Shuttle Radar data is five times finer: each one-degree tile is 3,601
 * samples a side, 26 MB, and is fetched once and kept. A tile that is on the phone is used in
 * place of the coarser ground wherever it covers; one that is not is simply not used, so nothing
 * ever depends on it being there.
 *
 * Tiles are memory-mapped rather than read: a corridor sweep asks for thousands of heights, and
 * the operating system's own paging answers each from the file without copying any of it.
 */
object Srtm {
    private const val SAMPLES = 3601
    private const val BASE = "https://s3.amazonaws.com/elevation-tiles-prod/skadi"

    private var dir: File? = null
    private val maps = ConcurrentHashMap<String, ByteBuffer>()
    private val missing = ConcurrentHashMap<String, Long>()

    fun init(ctx: Context) {
        if (dir == null) dir = File(ctx.filesDir, "srtm").apply { mkdirs() }
    }

    /** "N36W115" for the tile whose south-west corner is 36°N 115°W. */
    fun name(latFloor: Int, lonFloor: Int): String =
        String.format(Locale.US, "%s%02d%s%03d", if (latFloor >= 0) "N" else "S", Math.abs(latFloor),
            if (lonFloor >= 0) "E" else "W", Math.abs(lonFloor))

    private fun file(latFloor: Int, lonFloor: Int) = dir?.let { File(it, name(latFloor, lonFloor) + ".hgt") }

    fun have(latFloor: Int, lonFloor: Int): Boolean =
        file(latFloor, lonFloor)?.let { it.length() == SAMPLES.toLong() * SAMPLES * 2 } == true

    private fun buffer(latFloor: Int, lonFloor: Int): ByteBuffer? {
        val key = name(latFloor, lonFloor)
        maps[key]?.let { return it }
        // Do not hit the file system again and again for a tile that is not there.
        missing[key]?.let { if (System.currentTimeMillis() - it < 20_000L) return null }
        val f = file(latFloor, lonFloor)
        if (f == null || !have(latFloor, lonFloor)) { missing[key] = System.currentTimeMillis(); return null }
        return try {
            java.io.RandomAccessFile(f, "r").use { raf ->
                raf.channel.map(FileChannel.MapMode.READ_ONLY, 0, raf.length())
            }.also { maps[key] = it }
        } catch (e: Throwable) { missing[key] = System.currentTimeMillis(); null }
    }

    private fun sample(b: ByteBuffer, row: Int, col: Int): Int {
        val v = b.getShort((row * SAMPLES + col) * 2).toInt()      // big-endian, as the file is
        return if (v == -32768) Int.MIN_VALUE else v
    }

    /** Ground height in feet at a point, from the downloaded tile, or null when there is none. */
    fun elevationFt(lat: Double, lon: Double): Float? {
        val la = Math.floor(lat).toInt(); val lo = Math.floor(lon).toInt()
        val b = buffer(la, lo) ?: return null
        val rowF = (1.0 - (lat - la)) * (SAMPLES - 1)
        val colF = (lon - lo) * (SAMPLES - 1)
        val r0 = Math.floor(rowF).toInt().coerceIn(0, SAMPLES - 2)
        val c0 = Math.floor(colF).toInt().coerceIn(0, SAMPLES - 2)
        val h00 = sample(b, r0, c0); val h01 = sample(b, r0, c0 + 1)
        val h10 = sample(b, r0 + 1, c0); val h11 = sample(b, r0 + 1, c0 + 1)
        // A void in the data is not a pit: say so, and let the coarser ground answer.
        if (h00 == Int.MIN_VALUE || h01 == Int.MIN_VALUE || h10 == Int.MIN_VALUE || h11 == Int.MIN_VALUE) return null
        val dr = rowF - r0; val dc = colF - c0
        val top = h00 * (1 - dc) + h01 * dc
        val bottom = h10 * (1 - dc) + h11 * dc
        return ((top * (1 - dr) + bottom * dr) * 3.28084).toFloat().coerceAtLeast(0f)
    }

    /**
     * The best ground there is at a point: the thirty-metre tile where it is on the phone, else the
     * map's own ground. Call off the main thread, as the coarser ground may have to be fetched.
     */
    fun best(lat: Double, lon: Double): Float =
        elevationFt(lat, lon) ?: Terrain.elevationFt(lat, lon, wait = true) ?: 0f

    /** The tiles a route and its corridor touch, as (south, west) pairs. */
    fun tilesFor(points: List<FlightPlan.Waypoint>, halfCorridorNm: Double): List<Pair<Int, Int>> {
        if (points.isEmpty()) return emptyList()
        val pad = halfCorridorNm / 60.0 + 0.02
        val s = points.minOf { it.lat } - pad; val n = points.maxOf { it.lat } + pad
        val w = points.minOf { it.lon } - pad * 1.3; val e = points.maxOf { it.lon } + pad * 1.3
        val out = ArrayList<Pair<Int, Int>>()
        for (la in Math.floor(s).toInt()..Math.floor(n).toInt()) for (lo in Math.floor(w).toInt()..Math.floor(e).toInt()) out.add(la to lo)
        // A bounding box is generous on a diagonal route: keep only the tiles a leg really crosses.
        return out.filter { (la, lo) -> crosses(points, la, lo, pad) }
    }

    private fun crosses(points: List<FlightPlan.Waypoint>, la: Int, lo: Int, pad: Double): Boolean {
        if (points.size == 1) return points[0].lat >= la - pad && points[0].lat < la + 1 + pad && points[0].lon >= lo - pad && points[0].lon < lo + 1 + pad
        for (i in 1 until points.size) {
            val a = points[i - 1]; val b = points[i]
            val len = Nav.distanceNm(a.lat, a.lon, b.lat, b.lon)
            var s = 0.0
            while (s <= len) {
                val g = Nav.destination(a.lat, a.lon, Nav.bearingTrue(a.lat, a.lon, b.lat, b.lon), s)
                if (g.latitude >= la - pad && g.latitude < la + 1 + pad && g.longitude >= lo - pad && g.longitude < lo + 1 + pad) return true
                s += 2.0
            }
        }
        return false
    }

    /** What is still to fetch for a route, as tiles and as the megabytes that means. */
    fun missingFor(points: List<FlightPlan.Waypoint>, halfCorridorNm: Double): List<Pair<Int, Int>> =
        tilesFor(points, halfCorridorNm).filter { (la, lo) -> !have(la, lo) }

    const val MB_PER_TILE = 11    // compressed on the wire; 26 MB once kept

    /** Fetches one tile and keeps it; false when the service has none (the sea has no tile). Background thread. */
    fun download(la: Int, lo: Int, progress: (Int) -> Unit = {}): Boolean {
        val f = file(la, lo) ?: return false
        if (have(la, lo)) return true
        val url = "$BASE/${name(la, lo).substring(0, 3)}/${name(la, lo)}.hgt.gz"
        return try {
            val c = URL(url).openConnection() as HttpURLConnection
            c.connectTimeout = 20000; c.readTimeout = 60000
            try {
                if (c.responseCode != 200) return false
                val tmp = File(f.path + ".part")
                val total = c.contentLength.toLong().coerceAtLeast(1L)
                var read = 0L
                // Unpacked as it arrives, so the compressed file is never written out as well.
                val counting = object : java.io.FilterInputStream(c.inputStream) {
                    override fun read(b: ByteArray, off: Int, len: Int): Int {
                        val n = super.read(b, off, len)
                        if (n > 0) { read += n; progress((read * 100 / total).toInt().coerceAtMost(99)) }
                        return n
                    }
                }
                GZIPInputStream(counting, 64 * 1024).use { gz -> tmp.outputStream().use { o -> gz.copyTo(o, 64 * 1024) } }
                if (tmp.length() != SAMPLES.toLong() * SAMPLES * 2) { tmp.delete(); return false }
                tmp.renameTo(f)
                missing.remove(name(la, lo))
                progress(100)
                true
            } finally { c.disconnect() }
        } catch (e: Throwable) { false }
    }
}
