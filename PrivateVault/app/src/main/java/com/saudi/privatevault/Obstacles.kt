package com.saudi.privatevault

import android.content.Context
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Every tower, mast, stack and crane the FAA lists in the West, carried in the app itself.
 *
 * The Digital Obstacle File is 86 MB of text; this is the same thing packed down to under two —
 * each obstacle sixteen bytes: where it stands, how high its top is above the sea and above the
 * ground, and what kind of thing it is. It is read straight out of the file with no unpacking,
 * so a route can be swept for what stands near it in a few milliseconds, with no internet at all.
 */
object Obstacles {

    class Obstacle(val lat: Double, val lon: Double, val topFt: Int, val aglFt: Int, val kind: Int) {
        val name: String get() = when (kind) {
            1 -> "Tower"; 2 -> "Antenna"; 3 -> "Pole"; 4 -> "Stack"; 5 -> "Building"
            6 -> "Transmission line"; 7 -> "Wind turbine"; 8 -> "Crane"; 9 -> "Rig"; else -> "Obstacle"
        }
    }

    private var buf: ByteBuffer? = null
    private var count = 0
    private const val REC = 13      // two ints, two shorts, one byte

    private fun open(ctx: Context): ByteBuffer? {
        buf?.let { return it }
        return try {
            val bytes = ctx.assets.open("obstacles.bin").use { it.readBytes() }
            val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            if (b.int != 0x3153424F) return null          // "OBS1", little endian
            count = b.int
            buf = b
            b
        } catch (e: Throwable) { null }
    }

    private fun at(b: ByteBuffer, i: Int): Obstacle {
        val p = 8 + i * REC
        val lat = b.getInt(p) / 1e5
        val lon = b.getInt(p + 4) / 1e5
        val top = b.getShort(p + 8).toInt() and 0xFFFF
        val agl = b.getShort(p + 10).toInt() and 0xFFFF
        val k = b.get(p + 12).toInt() and 0xFF
        return Obstacle(lat, lon, top, agl, k)
    }

    /** Everything standing inside a box, highest first. Call off the main thread for a big box. */
    fun inBox(ctx: Context, south: Double, west: Double, north: Double, east: Double, limit: Int = 4000): List<Obstacle> {
        val b = open(ctx) ?: return emptyList()
        val out = ArrayList<Obstacle>()
        for (i in 0 until count) {
            val p = 8 + i * REC
            val lat = b.getInt(p) / 1e5
            if (lat < south || lat > north) continue
            val lon = b.getInt(p + 4) / 1e5
            if (lon < west || lon > east) continue
            out.add(at(b, i))
            if (out.size >= limit) break
        }
        return out
    }

    /**
     * What stands within [halfWidthNm] either side of a route, with how far along the route each one
     * lies — the corridor an EFB sweeps for the profile view. The list comes back in route order.
     */
    class Along(val obstacle: Obstacle, val alongNm: Double, val offsetNm: Double)

    fun alongRoute(ctx: Context, points: List<FlightPlan.Waypoint>, halfWidthNm: Double): List<Along> {
        if (points.size < 2) return emptyList()
        val b = open(ctx) ?: return emptyList()
        val pad = halfWidthNm / 60.0 + 0.05
        val south = points.minOf { it.lat } - pad; val north = points.maxOf { it.lat } + pad
        val west = points.minOf { it.lon } - pad * 1.4; val east = points.maxOf { it.lon } + pad * 1.4
        // Where each leg begins along the route, so an obstacle can be placed on the x axis.
        val legStart = DoubleArray(points.size)
        for (i in 1 until points.size)
            legStart[i] = legStart[i - 1] + Nav.distanceNm(points[i - 1].lat, points[i - 1].lon, points[i].lat, points[i].lon)
        val out = ArrayList<Along>()
        for (i in 0 until count) {
            val p = 8 + i * REC
            val lat = b.getInt(p) / 1e5
            if (lat < south || lat > north) continue
            val lon = b.getInt(p + 4) / 1e5
            if (lon < west || lon > east) continue
            // The nearest leg, and how far along it the obstacle falls.
            var bestOff = Double.MAX_VALUE
            var bestAlong = 0.0
            for (k in 1 until points.size) {
                val a = points[k - 1]; val c = points[k]
                val legNm = legStart[k] - legStart[k - 1]
                if (legNm < 1e-6) continue
                // Flat enough over a leg: project the point onto it in miles.
                val cosL = Math.cos(Math.toRadians((a.lat + c.lat) / 2))
                val ax = 0.0; val ay = 0.0
                val bx = (c.lon - a.lon) * 60 * cosL; val by = (c.lat - a.lat) * 60
                val px = (lon - a.lon) * 60 * cosL; val py = (lat - a.lat) * 60
                val len2 = bx * bx + by * by
                val u = if (len2 <= 0) 0.0 else (((px - ax) * bx + (py - ay) * by) / len2).coerceIn(0.0, 1.0)
                val dx = px - u * bx; val dy = py - u * by
                val off = Math.hypot(dx, dy)
                if (off < bestOff) { bestOff = off; bestAlong = legStart[k - 1] + u * legNm }
            }
            if (bestOff <= halfWidthNm) out.add(Along(at(b, i), bestAlong, bestOff))
        }
        return out.sortedBy { it.alongNm }
    }

    /** The highest thing standing within a corridor, or null when the corridor is clear. */
    fun highest(ctx: Context, points: List<FlightPlan.Waypoint>, halfWidthNm: Double): Along? =
        alongRoute(ctx, points, halfWidthNm).maxByOrNull { it.obstacle.topFt }
}
