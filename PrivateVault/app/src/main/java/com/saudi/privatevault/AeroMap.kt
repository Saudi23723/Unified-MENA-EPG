package com.saudi.privatevault

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.graphics.RectF
import android.graphics.Typeface
import android.util.LruCache
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors

/**
 * The VFR sectional, drawn rather than photographed.
 *
 * The printed sectional comes as a picture of a paper sheet: it has the printer's white margin down
 * the middle where two sheets meet, it goes soft when it is enlarged, it runs out where the sheet
 * runs out, and its lettering lies on its side when the map is turned. This one is made from the
 * data instead, so it is as sharp at the last zoom as at the first, has no seams and no edges,
 * keeps every name upright, and draws with no connection once the ground is on the phone.
 *
 * What a sectional is made of is all here:
 *  - the ground tinted by height, pale green low and through yellow and tan to brown high, lit from
 *    the north-west, with contour lines at the interval the scale allows and the lakes in blue;
 *  - the graticule every thirty minutes with its minute ticks, and in every quadrangle the maximum
 *    elevation figure — thousands large, hundreds small — worked out from the ground and the
 *    obstacles in it;
 *  - airspace as the charts colour it: Class B and D in blue, C in magenta, a dashed edge where a
 *    class reaches the surface, a shaded inner band where Class E begins, restricted and military
 *    areas banded, every area with its ceiling over its floor;
 *  - the radio beacons with their compass roses turned to magnetic north, their names, frequencies
 *    and identifiers;
 *  - the airports, towered ones in blue and the others in magenta, named and with their elevation,
 *    drawn as their own runways once close enough to land on them;
 *  - the towers and masts with their heights above the sea and above the ground.
 *
 * Everything heavy — shading a tile, tracing its contours, working out a figure — is done off the
 * screen's thread and drawn when it is ready, so the map moves as fast as it is pushed.
 */
class AeroMap(private val ctx: Context, private val map: MapView) : Overlay() {

    private val d = ctx.resources.displayMetrics.density

    // ---- what is drawn ----
    var airports: List<AviationData.Airport> = emptyList()
    var airspace: List<Airspace.Area> = emptyList()
    /** Runway ends by airport ident, so a field can be drawn as the runways it really has. */
    var runways: Map<String, Map<String, Pair<GeoPoint, GeoPoint>>> = emptyMap()

    /**
     * Drawn on its own, or laid over a printed chart. Over a chart the ground shading is left off —
     * the chart has its own — but the towers, the airspace and the upright names are still drawn.
     */
    var showTerrain = true
    var showAirspace = true
    var showObstacles = true
    var showFields = true
    var showContours = true
    var showGrid = true
    var showMef = true
    var showNavaids = true

    /** Where the shading, the contours and the figures are worked out, away from the screen's thread. */
    private val work = Executors.newSingleThreadExecutor { r ->
        Thread(r, "aero-build").apply { isDaemon = true; priority = Thread.NORM_PRIORITY - 1 }
    }
    /**
     * The maximum elevation figures get a worker of their own: they may have to wait for ground
     * tiles to download, and that wait must never hold up the shading of tiles already at hand.
     */
    private val slowWork = Executors.newSingleThreadExecutor { r ->
        Thread(r, "aero-mef").apply { isDaemon = true; priority = Thread.MIN_PRIORITY }
    }
    private val busy = ConcurrentHashMap.newKeySet<String>()

    private val ink = 0xFF1B2A4A.toInt()
    private val blue = 0xFF2A62C4.toInt()
    private val magenta = 0xFFA02F96.toInt()

    // ================================================================ the ground

    private val shaded = LruCache<String, Bitmap>(64)

    /** The sectional's tint ladder: feet, and the colour of the ground at that height. */
    private val stopsFt = floatArrayOf(0f, 1000f, 2000f, 3000f, 4000f, 5000f, 6000f, 7000f, 8000f, 9000f, 10000f, 12000f, 14000f)
    // Taken from a real sectional's tints: pale green low down, cream through the middle heights,
    // then a pinkish tan to grey at the top. Saturated colours here made it look nothing like the chart.
    private val stopsRgb = intArrayOf(
        0xC7DDB9, 0xCBD8BE, 0xDDE4C6, 0xF1EBD3, 0xF7EDD7, 0xF5E6CD, 0xEEDCC4,
        0xE6D3BF, 0xDECAC0, 0xD7CBC5, 0xD2C6C2, 0xCDC2C0, 0xC9BEC0,
    )

    private fun tint(ft: Float): Int {
        if (ft <= stopsFt[0]) return stopsRgb[0]
        for (i in 1 until stopsFt.size) {
            if (ft <= stopsFt[i]) {
                val k = (ft - stopsFt[i - 1]) / (stopsFt[i] - stopsFt[i - 1])
                val a = stopsRgb[i - 1]; val b = stopsRgb[i]
                val r = (((a shr 16) and 0xFF) + (((b shr 16) and 0xFF) - ((a shr 16) and 0xFF)) * k).toInt()
                val g = (((a shr 8) and 0xFF) + (((b shr 8) and 0xFF) - ((a shr 8) and 0xFF)) * k).toInt()
                val bl = ((a and 0xFF) + ((b and 0xFF) - (a and 0xFF)) * k).toInt()
                return (r shl 16) or (g shl 8) or bl
            }
        }
        return stopsRgb[stopsRgb.size - 1]
    }

    /**
     * Builds the picture of one elevation tile: its colours by height, lit from the north-west, and
     * its lakes. The elevation data flattens a lake to one exact height, so a stretch that is level
     * to within half a foot across seven samples each way is water — which finds Lake Mead and
     * Lake Mohave and leaves a dry lake bed, which is never quite level, alone.
     */
    private fun shade(t: Terrain.Tile): Bitmap {
        val n = 256
        val f = t.ft
        val water = BooleanArray(n * n)
        var any = false
        for (y in 0 until n) for (x in 0 until n) {
            val h = f[y * n + x]
            if (h <= 5f) { water[y * n + x] = true; any = true; continue }
            var lo = h; var hi = h
            var level = true
            var yy = y - 3
            while (yy <= y + 3 && level) {
                val row = yy.coerceIn(0, n - 1) * n
                var xx = x - 3
                while (xx <= x + 3) {
                    val v = f[row + xx.coerceIn(0, n - 1)]
                    if (v < lo) lo = v
                    if (v > hi) hi = v
                    xx++
                }
                if (hi - lo >= 0.5f) level = false
                yy++
            }
            if (level) { water[y * n + x] = true; any = true }
        }
        // Grow the water back out by the three samples the test ate, onto ground at the same height.
        val lake = water.copyOf()
        if (any) {
            for (y in 0 until n) for (x in 0 until n) {
                val i = y * n + x
                if (water[i]) continue
                val h = f[i]
                var near = false
                var yy = y - 3
                while (yy <= y + 3 && !near) {
                    val row = yy.coerceIn(0, n - 1) * n
                    var xx = x - 3
                    while (xx <= x + 3) {
                        val j = row + xx.coerceIn(0, n - 1)
                        if (water[j] && Math.abs(f[j] - h) <= 3f) { near = true; break }
                        xx++
                    }
                    yy++
                }
                if (near) lake[i] = true
            }
        }
        val px = IntArray(n * n)
        val latTop = Terrain.latOf(t.y.toDouble(), t.z)
        val latBot = Terrain.latOf((t.y + 1).toDouble(), t.z)
        val metresPerSample = Math.abs(latTop - latBot) * 111_320.0 / n
        for (y in 0 until n) for (x in 0 until n) {
            val i = y * n + x
            if (lake[i]) {
                // The shore is a darker blue line, so a lake has an edge and not just a colour.
                val shore = (x > 0 && !lake[i - 1]) || (x < n - 1 && !lake[i + 1]) ||
                    (y > 0 && !lake[i - n]) || (y < n - 1 && !lake[i + n])
                px[i] = if (shore) 0xFF5C96C8.toInt() else 0xFFA8CDE6.toInt()
                continue
            }
            val h = f[i]
            val xl = f[y * n + (x - 1).coerceAtLeast(0)]
            val xr = f[y * n + (x + 1).coerceAtMost(n - 1)]
            val yu = f[(y - 1).coerceAtLeast(0) * n + x]
            val yd = f[(y + 1).coerceAtMost(n - 1) * n + x]
            val dzdx = (xr - xl) * 0.3048 / (2 * metresPerSample)
            val dzdy = (yd - yu) * 0.3048 / (2 * metresPerSample)
            val nx = -dzdx; val ny = -dzdy
            val len = Math.sqrt(nx * nx + ny * ny + 1.0)
            val lam = ((nx * -0.5 + ny * -0.5 + 0.707) / len).coerceIn(0.0, 1.0)
            val k = (0.80 + 0.36 * lam).coerceIn(0.78, 1.10)
            val c = tint(h)
            val r = (((c shr 16) and 0xFF) * k).toInt().coerceIn(0, 255)
            val g = (((c shr 8) and 0xFF) * k).toInt().coerceIn(0, 255)
            val b = ((c and 0xFF) * k).toInt().coerceIn(0, 255)
            px[i] = (0xFF shl 24) or (r shl 16) or (g shl 8) or b
        }
        return Bitmap.createBitmap(px, n, n, Bitmap.Config.ARGB_8888)
    }

    /** A flat list of line segments, four numbers each, that grows as it is filled. */
    private class Segs {
        var a = FloatArray(2048)
        var n = 0
        fun add(x1: Float, y1: Float, x2: Float, y2: Float) {
            if (n + 4 > a.size) a = a.copyOf(a.size * 2)
            a[n++] = x1; a[n++] = y1; a[n++] = x2; a[n++] = y2
        }
        fun done(): FloatArray = a.copyOf(n)
    }

    private class Contours(val minor: FloatArray, val index: FloatArray)

    private val contourCache = LruCache<String, Contours>(96)

    private fun frac(p: Float, q: Float, level: Float): Float =
        if (q == p) 0.5f else ((level - p) / (q - p)).coerceIn(0f, 1f)

    /**
     * The contour lines of a tile at an interval, by marching squares over every second sample — the
     * line where the ground passes through a height, found cell by cell and joined end to end. Each
     * fifth thousand feet is an index contour, drawn heavier.
     */
    private fun contoursOf(t: Terrain.Tile, interval: Int): Contours {
        val n = 256
        val g = 129
        val grid = FloatArray(g * g)
        var lo = Float.MAX_VALUE; var hi = -1f
        for (j in 0 until g) for (i in 0 until g) {
            val v = t.ft[Math.min(j * 2, n - 1) * n + Math.min(i * 2, n - 1)]
            grid[j * g + i] = v
            if (v < lo) lo = v
            if (v > hi) hi = v
        }
        val minor = Segs(); val index = Segs()
        var level = (Math.floor(lo / interval.toDouble()).toInt() + 1) * interval
        while (level <= hi) {
            val L = level.toFloat()
            val into = if (level % 5000 == 0) index else minor
            for (j in 0 until g - 1) for (i in 0 until g - 1) {
                val a = grid[j * g + i]; val b = grid[j * g + i + 1]
                val c = grid[(j + 1) * g + i + 1]; val dd = grid[(j + 1) * g + i]
                var code = 0
                if (a >= L) code = code or 8
                if (b >= L) code = code or 4
                if (c >= L) code = code or 2
                if (dd >= L) code = code or 1
                if (code == 0 || code == 15) continue
                val tx = (i + frac(a, b, L)) * 2f; val ty = j * 2f
                val rx = (i + 1) * 2f; val ry = (j + frac(b, c, L)) * 2f
                val bx = (i + frac(dd, c, L)) * 2f; val by = (j + 1) * 2f
                val lx = i * 2f; val ly = (j + frac(a, dd, L)) * 2f
                when (code) {
                    1, 14 -> into.add(lx, ly, bx, by)
                    2, 13 -> into.add(bx, by, rx, ry)
                    3, 12 -> into.add(lx, ly, rx, ry)
                    4, 11 -> into.add(tx, ty, rx, ry)
                    5 -> { into.add(lx, ly, tx, ty); into.add(bx, by, rx, ry) }
                    6, 9 -> into.add(tx, ty, bx, by)
                    7, 8 -> into.add(lx, ly, tx, ty)
                    10 -> { into.add(lx, ly, bx, by); into.add(tx, ty, rx, ry) }
                }
            }
            level += interval
        }
        return Contours(minor.done(), index.done())
    }

    /** How far apart the contours are at this scale; none at all when they would only be a tangle. */
    private fun interval(zoom: Double): Int = when {
        zoom < 7.5 -> 0
        zoom < 9.5 -> 1000
        else -> 500
    }

    private val tileMatrix = Matrix()
    private val src = FloatArray(8)
    private val dst = FloatArray(8)
    private val pa = Point(); private val pb = Point(); private val pc = Point(); private val pd = Point()
    private val groundPaint = Paint(Paint.FILTER_BITMAP_FLAG).apply { isAntiAlias = true }
    private val minorLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0x8C78542F.toInt() }
    private val indexLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xCC78542F.toInt() }

    private fun drawGround(c: Canvas, mv: MapView) {
        val z = Terrain.Z
        val bb = mv.boundingBox
        val x0 = Terrain.tileX(bb.lonWest, z); val x1 = Terrain.tileX(bb.lonEast, z)
        val y0 = Terrain.tileY(bb.latNorth, z); val y1 = Terrain.tileY(bb.latSouth, z)
        // Far out there would be hundreds of tiles: the ground is only drawn where it can be seen.
        if ((x1 - x0 + 1).toLong() * (y1 - y0 + 1) > 90) return
        val pr = mv.projection
        val step = interval(mv.zoomLevelDouble)
        for (ty in y0..y1) for (tx in x0..x1) {
            val key = "$z/$tx/$ty"
            val bmp = shaded.get(key)
            if (bmp == null) { buildShade(tx, ty, z, key); continue }
            // The tile's four corners on the screen: a matrix, so a turned map still lands square.
            pr.toPixels(GeoPoint(Terrain.latOf(ty.toDouble(), z), Terrain.lonOf(tx.toDouble(), z)), pa)
            pr.toPixels(GeoPoint(Terrain.latOf(ty.toDouble(), z), Terrain.lonOf((tx + 1).toDouble(), z)), pb)
            pr.toPixels(GeoPoint(Terrain.latOf((ty + 1).toDouble(), z), Terrain.lonOf((tx + 1).toDouble(), z)), pc)
            pr.toPixels(GeoPoint(Terrain.latOf((ty + 1).toDouble(), z), Terrain.lonOf(tx.toDouble(), z)), pd)
            src[0] = 0f; src[1] = 0f; src[2] = 256f; src[3] = 0f
            src[4] = 256f; src[5] = 256f; src[6] = 0f; src[7] = 256f
            dst[0] = pa.x.toFloat(); dst[1] = pa.y.toFloat(); dst[2] = pb.x.toFloat(); dst[3] = pb.y.toFloat()
            dst[4] = pc.x.toFloat(); dst[5] = pc.y.toFloat(); dst[6] = pd.x.toFloat(); dst[7] = pd.y.toFloat()
            tileMatrix.reset()
            tileMatrix.setPolyToPoly(src, 0, dst, 0, 4)
            c.drawBitmap(bmp, tileMatrix, groundPaint)

            if (showContours && step > 0 && !light) {
                val ck = "$key/$step"
                val cs = contourCache.get(ck)
                if (cs == null) { buildContours(tx, ty, z, step, ck); continue }
                // Drawn in the tile's own 256-square space, so the line widths are put back by the
                // scale the matrix applies, and a hairline stays a hairline at every zoom.
                val s = tileMatrix.mapRadius(1f).coerceAtLeast(0.0001f)
                c.save()
                c.concat(tileMatrix)
                minorLine.strokeWidth = 0.7f * d / s
                indexLine.strokeWidth = 1.4f * d / s
                if (cs.minor.isNotEmpty()) c.drawLines(cs.minor, minorLine)
                if (cs.index.isNotEmpty()) c.drawLines(cs.index, indexLine)
                c.restore()
            }
        }
    }

    private fun buildShade(tx: Int, ty: Int, z: Int, key: String) {
        if (!busy.add("s$key")) return
        val t = Terrain.tile(tx, ty, z)
        if (t == null) { busy.remove("s$key"); return }          // asked for; it redraws when it lands
        work.execute {
            try { shaded.put(key, shade(t)); map.postInvalidate() } finally { busy.remove("s$key") }
        }
    }

    private fun buildContours(tx: Int, ty: Int, z: Int, step: Int, ck: String) {
        if (!busy.add("c$ck")) return
        val t = Terrain.tile(tx, ty, z)
        if (t == null) { busy.remove("c$ck"); return }
        work.execute {
            try { contourCache.put(ck, contoursOf(t, step)); map.postInvalidate() } finally { busy.remove("c$ck") }
        }
    }

    // ================================================================ graticule and maximum elevations

    private val gridLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0x8C3C4678.toInt() }
    private val gridText = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF37417A.toInt(); typeface = Typeface.DEFAULT_BOLD }
    private val halo = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xCCFFFFFF.toInt(); typeface = Typeface.DEFAULT_BOLD }

    private fun text(c: Canvas, s: String, x: Float, y: Float, p: Paint, haloW: Float = 2.6f) {
        halo.textSize = p.textSize; halo.strokeWidth = haloW * d
        c.drawText(s, x, y, halo)
        c.drawText(s, x, y, p)
    }

    private fun dm(v: Double, hemi: String): String {
        val a = Math.abs(v)
        val deg = a.toInt()
        val min = Math.round((a - deg) * 60.0).toInt()
        return "%d°%02d'%s".format(if (min == 60) deg + 1 else deg, if (min == 60) 0 else min, hemi)
    }

    /** Lines every thirty minutes, with a tick for every minute along them, as the sectional is ruled. */
    private fun drawGrid(c: Canvas, mv: MapView) {
        val zoom = mv.zoomLevelDouble
        if (!showGrid || zoom < 7.5 || zoom > 14) return
        val bb = mv.boundingBox
        val pr = mv.projection
        val p1 = Point(); val p2 = Point()
        gridLine.strokeWidth = 0.9f * d
        gridText.textSize = 10.5f * d
        val spanLat = bb.latNorth - bb.latSouth
        val spanLon = bb.lonEast - bb.lonWest
        var lat = Math.ceil(bb.latSouth * 2) / 2
        var guard = 0
        while (lat <= bb.latNorth && guard++ < 40) {
            pr.toPixels(GeoPoint(lat, bb.lonWest), p1); pr.toPixels(GeoPoint(lat, bb.lonEast), p2)
            c.drawLine(p1.x.toFloat(), p1.y.toFloat(), p2.x.toFloat(), p2.y.toFloat(), gridLine)
            if (zoom >= 9.5) ticksAlong(c, pr, lat, true, bb.lonWest, bb.lonEast)
            val ex = bb.lonWest + spanLon * 0.05
            pr.toPixels(GeoPoint(lat, ex), p1)
            c.save(); c.rotate(-mv.mapOrientation, p1.x.toFloat(), p1.y.toFloat())
            text(c, dm(lat, if (lat >= 0) "N" else "S"), p1.x + 3 * d, p1.y - 4 * d, gridText)
            c.restore()
            lat += 0.5
        }
        var lon = Math.ceil(bb.lonWest * 2) / 2
        guard = 0
        while (lon <= bb.lonEast && guard++ < 40) {
            pr.toPixels(GeoPoint(bb.latSouth, lon), p1); pr.toPixels(GeoPoint(bb.latNorth, lon), p2)
            c.drawLine(p1.x.toFloat(), p1.y.toFloat(), p2.x.toFloat(), p2.y.toFloat(), gridLine)
            if (zoom >= 9.5) ticksAlong(c, pr, lon, false, bb.latSouth, bb.latNorth)
            val ey = bb.latNorth - spanLat * 0.05
            pr.toPixels(GeoPoint(ey, lon), p1)
            c.save(); c.rotate(-mv.mapOrientation, p1.x.toFloat(), p1.y.toFloat())
            text(c, dm(lon, if (lon >= 0) "E" else "W"), p1.x + 4 * d, p1.y + 12 * d, gridText)
            c.restore()
            lon += 0.5
        }
    }

    private fun ticksAlong(c: Canvas, pr: org.osmdroid.views.Projection, fixed: Double, alongLon: Boolean, from: Double, to: Double) {
        val a = Point(); val b = Point(); val q = Point()
        val minutes = Math.ceil(from * 60).toInt()..Math.floor(to * 60).toInt()
        if (minutes.last - minutes.first > 90) return
        // Which way across the line is, on the screen: the line's own direction turned a quarter.
        if (alongLon) { pr.toPixels(GeoPoint(fixed, from), a); pr.toPixels(GeoPoint(fixed, to), b) }
        else { pr.toPixels(GeoPoint(from, fixed), a); pr.toPixels(GeoPoint(to, fixed), b) }
        val dx = (b.x - a.x).toFloat(); val dy = (b.y - a.y).toFloat()
        val len = Math.hypot(dx.toDouble(), dy.toDouble()).toFloat().coerceAtLeast(1f)
        val ux = -dy / len; val uy = dx / len
        for (m in minutes) {
            if (m % 30 == 0) continue
            if (alongLon) pr.toPixels(GeoPoint(fixed, m / 60.0), q) else pr.toPixels(GeoPoint(m / 60.0, fixed), q)
            val h = (if (m % 10 == 0) 6f else if (m % 5 == 0) 4.5f else 3f) * d
            c.drawLine(q.x - ux * h, q.y - uy * h, q.x + ux * h, q.y + uy * h, gridLine)
        }
    }

    private val mefCache = ConcurrentHashMap<String, Int>()
    private val mefFailedAt = ConcurrentHashMap<String, Long>()
    private val mefBig = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF2A4C8C.toInt(); typeface = Typeface.DEFAULT_BOLD }
    private val mefSmall = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF2A4C8C.toInt(); typeface = Typeface.DEFAULT_BOLD }

    private fun mercY(lat: Double): Double {
        val r = Math.toRadians(lat)
        return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2
    }

    /**
     * The maximum elevation figure of one thirty-minute quadrangle: the highest ground in it, and
     * the highest obstacle, each with a margin above it, rounded up to the next hundred feet. This
     * is worked out from the same ground and obstacle data the rest of the map uses; it follows the
     * method the charts describe, and where it differs from a printed figure the printed one rules.
     */
    private fun mefOf(latIdx: Int, lonIdx: Int): Int? {
        val south = latIdx / 2.0; val north = south + 0.5
        val west = lonIdx / 2.0; val east = west + 0.5
        val z = Terrain.Z
        val n = (1 shl z).toDouble()
        val tx0 = Terrain.tileX(west, z); val tx1 = Terrain.tileX(east - 1e-9, z)
        val ty0 = Terrain.tileY(north, z); val ty1 = Terrain.tileY(south + 1e-9, z)
        var top = 0f
        for (ty in ty0..ty1) for (tx in tx0..tx1) {
            val t = Terrain.tileNow(tx, ty, z) ?: return null
            val fx0 = ((west + 180) / 360 * n - tx) * 256; val fx1 = ((east + 180) / 360 * n - tx) * 256
            val fy0 = (mercY(north) * n - ty) * 256; val fy1 = (mercY(south) * n - ty) * 256
            val px0 = Math.floor(fx0).toInt().coerceIn(0, 255); val px1 = Math.ceil(fx1).toInt().coerceIn(0, 255)
            val py0 = Math.floor(fy0).toInt().coerceIn(0, 255); val py1 = Math.ceil(fy1).toInt().coerceIn(0, 255)
            for (y in py0..py1) for (x in px0..px1) {
                val h = t.ft[y * 256 + x]
                if (h > top) top = h
            }
        }
        var mef = top + 200f
        try {
            val high = Obstacles.inBox(ctx, south, west, north, east, 6000).maxOfOrNull { it.topFt } ?: 0
            if (high > 0) mef = Math.max(mef, high + 100f)
        } catch (e: Throwable) { }
        return (Math.ceil(mef / 100.0) * 100).toInt()
    }

    private fun drawMef(c: Canvas, mv: MapView) {
        val zoom = mv.zoomLevelDouble
        if (!showMef || zoom < 7.0 || zoom > 11.8) return
        val bb = mv.boundingBox
        val pr = mv.projection
        val p = Point()
        val la0 = Math.floor(bb.latSouth * 2).toInt(); val la1 = Math.floor(bb.latNorth * 2).toInt()
        val lo0 = Math.floor(bb.lonWest * 2).toInt(); val lo1 = Math.floor(bb.lonEast * 2).toInt()
        if ((la1 - la0 + 1) * (lo1 - lo0 + 1) > 80) return
        val big = ((15 + 4 * (zoom - 8)).coerceIn(15.0, 34.0) * d).toFloat()
        mefBig.textSize = big; mefSmall.textSize = big * 0.55f
        for (la in la0..la1) for (lo in lo0..lo1) {
            val key = "$la/$lo"
            val v = mefCache[key]
            if (v == null) {
                val failed = mefFailedAt[key]
                if ((failed == null || System.currentTimeMillis() - failed > 60_000L) && busy.add("m$key")) {
                    slowWork.execute {
                        try {
                            val r = mefOf(la, lo)
                            if (r != null) { mefCache[key] = r; map.postInvalidate() } else mefFailedAt[key] = System.currentTimeMillis()
                        } finally { busy.remove("m$key") }
                    }
                }
                continue
            }
            // The middle of the part of the quadrangle in view, so the figure is there to read.
            val cs = Math.max(la / 2.0, bb.latSouth); val cn = Math.min(la / 2.0 + 0.5, bb.latNorth)
            val cw = Math.max(lo / 2.0, bb.lonWest); val ce = Math.min(lo / 2.0 + 0.5, bb.lonEast)
            if (cn <= cs || ce <= cw) continue
            pr.toPixels(GeoPoint((cs + cn) / 2, (cw + ce) / 2), p)
            val th = (v / 1000).toString(); val hu = ((v % 1000) / 100).toString()
            val tw = mefBig.measureText(th)
            c.save(); c.rotate(-mv.mapOrientation, p.x.toFloat(), p.y.toFloat())
            mefBig.alpha = 215; mefSmall.alpha = 215
            text(c, th, p.x - tw / 2, p.y + big * 0.35f, mefBig, 3f)
            text(c, hu, p.x + tw / 2 + 1.5f * d, p.y + big * 0.35f, mefSmall, 2.4f)
            c.restore()
        }
    }

    // ================================================================ airspace

    private val asLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeJoin = Paint.Join.ROUND }
    private val asBand = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val asText = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10f * d; typeface = Typeface.DEFAULT_BOLD }

    /** The colour a class of airspace is drawn in, as the sectional colours them. */
    private fun airspaceColour(kind: String): Int = when (kind.uppercase()) {
        "B", "D" -> blue
        "C", "E", "MOA" -> magenta
        "R", "RESTRICTED", "P", "PROHIBITED", "W", "WARNING", "A", "ALERT" -> 0xFF2D5AAE.toInt()
        else -> 0xFF7F8B99.toInt()
    }

    private fun dashFor(a: Airspace.Area): DashPathEffect? = when (a.kind.uppercase()) {
        "D" -> DashPathEffect(floatArrayOf(7 * d, 4 * d), 0f)
        "E" -> if (a.lowFt == 0) DashPathEffect(floatArrayOf(5 * d, 4 * d), 0f) else null
        else -> null
    }

    private val labelled = ArrayList<RectF>()

    private fun drawAirspace(c: Canvas, mv: MapView) {
        val zoom = mv.zoomLevelDouble
        if (zoom < 6.5) return
        val bb = mv.boundingBox
        val pr = mv.projection
        val p = Point()
        for (a in airspace) {
            if (a.maxLat < bb.latSouth || a.minLat > bb.latNorth || a.maxLon < bb.lonWest || a.minLon > bb.lonEast) continue
            // Small strips of airspace only clutter the view from high up.
            val span = maxOf(a.maxLat - a.minLat, a.maxLon - a.minLon)
            if (zoom < 8.5 && span < 0.25) continue
            val kind = a.kind.uppercase()
            val colour = airspaceColour(kind)
            asLine.color = colour
            asLine.strokeWidth = when (kind) { "B" -> 3.4f; "C" -> 2.8f; "D" -> 2.2f; else -> 1.8f } * d
            asLine.pathEffect = dashFor(a)
            // Where Class E begins, and inside restricted and military ground, the chart shades an
            // inner band along the edge rather than filling the whole area.
            val banded = kind == "E" || kind == "MOA" || kind == "R" || kind == "P" || kind == "W" || kind == "A"
            asBand.color = (colour and 0x00FFFFFF) or 0x30000000
            asBand.strokeWidth = (if (kind == "E") 22f else 16f) * d
            for (ring in a.rings) {
                if (ring.size < 6) continue
                val path = Path()
                var i = 0
                while (i < ring.size) {
                    pr.toPixels(GeoPoint(ring[i], ring[i + 1]), p)
                    if (i == 0) path.moveTo(p.x.toFloat(), p.y.toFloat()) else path.lineTo(p.x.toFloat(), p.y.toFloat())
                    i += 2
                }
                path.close()
                if (banded) {
                    c.save()
                    c.clipPath(path)
                    c.drawPath(path, asBand)
                    c.restore()
                }
                c.drawPath(path, asLine)
            }
            // Its ceiling over its floor, in hundreds of feet as a chart prints them, upright
            // whatever the map's turn, and only where there is clear room.
            if (zoom >= 8.5 && a.lowFt != null) {
                pr.toPixels(GeoPoint((a.minLat + a.maxLat) / 2, (a.minLon + a.maxLon) / 2), p)
                val top = a.highFt?.let { "%d".format(it / 100) } ?: "—"
                val bot = if (a.lowFt == 0) "SFC" else "%d".format(a.lowFt!! / 100)
                val box = RectF(p.x - 20 * d, p.y - 14 * d, p.x + 20 * d, p.y + 16 * d)
                if (labelled.any { RectF.intersects(it, box) }) continue
                labelled.add(box)
                asText.color = colour
                c.save(); c.rotate(-mv.mapOrientation, p.x.toFloat(), p.y.toFloat())
                val w = asText.measureText(top)
                text(c, top, p.x - w / 2, p.y.toFloat(), asText, 2.2f)
                asLine.pathEffect = null
                asLine.strokeWidth = 1.2f * d
                c.drawLine(p.x - w / 2 - 2 * d, p.y + 2 * d, p.x + w / 2 + 2 * d, p.y + 2 * d, asLine)
                text(c, bot, p.x - asText.measureText(bot) / 2, p.y + 13 * d, asText, 2.2f)
                c.restore()
            }
        }
        asLine.pathEffect = null
    }

    // ================================================================ beacons

    private val navLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xFF2A62C4.toInt() }
    private val navFill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL; color = 0xFFFFFFFF.toInt() }
    private val navDot = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL; color = 0xFF2A62C4.toInt() }
    private val navName = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF2A62C4.toInt(); typeface = Typeface.DEFAULT_BOLD }

    private fun drawNavaids(c: Canvas, mv: MapView) {
        val zoom = mv.zoomLevelDouble
        if (!showNavaids || zoom < 7.5) return
        val bb = mv.boundingBox
        val list = Navaids.inView(bb.latSouth, bb.lonWest, bb.latNorth, bb.lonEast)
        val pr = mv.projection
        val p = Point()
        navName.textSize = 9.5f * d
        for (n in list) {
            pr.toPixels(GeoPoint(n.lat, n.lon), p)
            val x = p.x.toFloat(); val y = p.y.toFloat()
            var reach = 8f * d
            if (n.isVor) {
                // The compass rose, turned so its north is magnetic north.
                if (zoom >= 8.5) {
                    val rad = ((16 + 4 * (zoom - 8.5)).coerceIn(14.0, 42.0) * d).toFloat()
                    reach = rad
                    navLine.strokeWidth = 1.1f * d
                    c.drawCircle(x, y, rad, navLine)
                    for (deg in 0 until 360 step 10) {
                        val a = Math.toRadians(deg + n.magVar)
                        val inner = rad * (if (deg % 30 == 0) 0.78f else 0.89f)
                        val sx = Math.sin(a).toFloat(); val cy = Math.cos(a).toFloat()
                        c.drawLine(x + inner * sx, y - inner * cy, x + rad * sx, y - rad * cy, navLine)
                    }
                    // A mark at magnetic north, so the rose can be read.
                    val an = Math.toRadians(n.magVar)
                    c.drawLine(x, y, x + rad * 0.78f * Math.sin(an).toFloat(), y - rad * 0.78f * Math.cos(an).toFloat(), navLine)
                }
                val hex = Path()
                for (k in 0 until 6) {
                    val a = Math.toRadians(30.0 + 60.0 * k)
                    val hx = x + 5.5f * d * Math.cos(a).toFloat(); val hy = y + 5.5f * d * Math.sin(a).toFloat()
                    if (k == 0) hex.moveTo(hx, hy) else hex.lineTo(hx, hy)
                }
                hex.close()
                navLine.strokeWidth = 1.6f * d
                c.drawPath(hex, navFill); c.drawPath(hex, navLine)
                c.drawCircle(x, y, 1.6f * d, navDot)
            } else if (n.isNdb) {
                navLine.strokeWidth = 1.3f * d
                navLine.pathEffect = DashPathEffect(floatArrayOf(2 * d, 2 * d), 0f)
                c.drawCircle(x, y, 7f * d, navLine)
                navLine.pathEffect = null
                c.drawCircle(x, y, 1.8f * d, navDot)
            } else {
                // A TACAN: a hexagon on its own, with no rose.
                val hex = Path()
                for (k in 0 until 6) {
                    val a = Math.toRadians(30.0 + 60.0 * k)
                    val hx = x + 4.5f * d * Math.cos(a).toFloat(); val hy = y + 4.5f * d * Math.sin(a).toFloat()
                    if (k == 0) hex.moveTo(hx, hy) else hex.lineTo(hx, hy)
                }
                hex.close()
                navLine.strokeWidth = 1.4f * d
                c.drawPath(hex, navFill); c.drawPath(hex, navLine)
            }
            if (zoom >= 8.5) {
                val l1 = n.name.uppercase().take(16)
                val l2 = (if (n.freq >= 200) "%.0f".format(n.freq) else if (n.freq > 0) "%.1f".format(n.freq) else "") + "  " + n.id
                val w = Math.max(navName.measureText(l1), navName.measureText(l2))
                val box = RectF(x + reach * 0.55f, y + reach * 0.35f, x + reach * 0.55f + w, y + reach * 0.35f + 24 * d)
                if (labelled.any { RectF.intersects(it, box) }) continue
                labelled.add(box)
                c.save(); c.rotate(-mv.mapOrientation, x, y)
                text(c, l1, box.left, box.top + 9 * d, navName, 2.4f)
                text(c, l2, box.left, box.top + 20 * d, navName, 2.4f)
                c.restore()
            }
        }
    }

    // ================================================================ airports

    private val fieldFill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fieldEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.8f * d }
    private val rwyPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeCap = Paint.Cap.BUTT }
    private val nameTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10.5f * d; typeface = Typeface.DEFAULT_BOLD }
    private val subTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 9f * d; color = 0xFF3A4660.toInt() }

    private fun drawFields(c: Canvas, mv: MapView) {
        val zoom = mv.zoomLevelDouble
        val bb = mv.boundingBox
        val pr = mv.projection
        val p = Point()
        val centre = mv.mapCenter
        // Fewer fields the further out you are, nearest the middle first, so the picture stays clear.
        val limit = when { zoom >= 11 -> 220; zoom >= 9 -> 120; zoom >= 7.5 -> 60; zoom >= 6 -> 28; else -> 12 }
        val inView = airports.asSequence()
            .filter { it.lat in bb.latSouth..bb.latNorth && it.lon in bb.lonWest..bb.lonEast }
            .sortedBy { Nav.distanceNm(centre.latitude, centre.longitude, it.lat, it.lon) }
            .take(limit).toList()
        for (a in inView) {
            pr.toPixels(GeoPoint(a.lat, a.lon), p)
            val x = p.x.toFloat(); val y = p.y.toFloat()
            val ends = runways[a.ident]
            val towered = a.icao.isNotEmpty()
            val colour = if (towered) blue else magenta
            fieldFill.color = colour
            fieldEdge.color = colour
            if (zoom >= 11.5 && ends != null && ends.isNotEmpty()) {
                // Close in, the field is its own runways, drawn where they really lie.
                rwyPaint.color = 0xFF3A4660.toInt()
                rwyPaint.strokeWidth = (if (zoom >= 13) 5f else 3f) * d
                val seen = HashSet<String>()
                for ((id, pairEnds) in ends) {
                    val other = id.takeWhile { it.isDigit() }.toIntOrNull()?.let { ((it + 18 - 1) % 36 + 1).toString() }
                    if (other != null && !seen.add(listOf(id, other).sorted().joinToString("/"))) continue
                    val q1 = Point(); val q2 = Point()
                    pr.toPixels(pairEnds.first, q1); pr.toPixels(pairEnds.second, q2)
                    c.drawLine(q1.x.toFloat(), q1.y.toFloat(), q2.x.toFloat(), q2.y.toFloat(), rwyPaint)
                }
                c.drawCircle(x, y, 3f * d, fieldFill)
            } else {
                // A ring as a chart marks a field, blue where there is a tower and magenta where
                // there is not, with its dot in the middle.
                val r = if (zoom >= 9) 6f * d else 4.5f * d
                fieldEdge.style = Paint.Style.STROKE
                c.drawCircle(x, y, r, fieldEdge)
                fieldFill.style = Paint.Style.FILL
                c.drawCircle(x, y, r * 0.4f, fieldFill)
            }
            // Its name, upright however the map is turned, where there is room for it.
            if (zoom >= 8) {
                val id = a.icao.ifEmpty { a.ident }
                val big = zoom >= 9.5
                val l1 = if (big) a.name.uppercase().take(20).ifEmpty { id } else id
                nameTx.color = colour
                val nbox = RectF(x + 8 * d, y - 14 * d, x + 10 * d + nameTx.measureText(l1), y + 12 * d)
                if (labelled.any { RectF.intersects(it, nbox) }) continue
                labelled.add(nbox)
                c.save(); c.rotate(-mv.mapOrientation, x, y)
                text(c, l1, x + 9 * d, y - 4 * d, nameTx, 2.8f)
                if (zoom >= 10) text(c, "$id  %,d'".format(a.elevation), x + 9 * d, y + 7 * d, subTx, 2.4f)
                c.restore()
            }
        }
    }

    // ================================================================ towers

    private val obsPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 1.8f * d; color = 0xFF55486B.toInt() }
    private val obsTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 8.5f * d; color = 0xFF55486B.toInt() }

    private fun drawObstacles(c: Canvas, mv: MapView) {
        val zoom = mv.zoomLevelDouble
        if (!showObstacles || zoom < 10.5) return
        val bb = mv.boundingBox
        val list = try {
            Obstacles.inBox(ctx, bb.latSouth, bb.lonWest, bb.latNorth, bb.lonEast, 400)
        } catch (e: Throwable) { return }
        val pr = mv.projection
        val p = Point()
        for (o in list) {
            if (o.aglFt < 200 && zoom < 12) continue
            pr.toPixels(GeoPoint(o.lat, o.lon), p)
            val x = p.x.toFloat(); val y = p.y.toFloat()
            val h = (if (o.aglFt >= 1000) 11f else 8f) * d
            c.drawLine(x, y, x, y - h, obsPaint)
            c.drawCircle(x, y - h, 2.2f * d, obsPaint)
            c.drawLine(x - 3 * d, y, x + 3 * d, y, obsPaint)
            // Its height above the sea, and above the ground in brackets, as a chart prints it.
            if (zoom >= 12.2 && (o.aglFt >= 200 || zoom >= 13)) {
                val s = "%d (%d)".format(o.topFt, o.aglFt)
                val box = RectF(x + 4 * d, y - h - 9 * d, x + 6 * d + obsTx.measureText(s), y - h + 3 * d)
                if (labelled.any { RectF.intersects(it, box) }) continue
                labelled.add(box)
                c.save(); c.rotate(-mv.mapOrientation, x, y)
                text(c, s, x + 5 * d, y - h + 1 * d, obsTx, 2.2f)
                c.restore()
            }
        }
    }

    // ================================================================ the whole picture

    // While the chart is being dragged or zoomed the heavy detail (contour lines, the maximum
    // elevation figures, the tower labels) is left out, and put back a moment after it stops, so
    // the chart keeps up with the finger. A frame that is slow switches the lighter drawing on.
    private var lastView = DoubleArray(4)
    private var lastCost = 0L
    private var settle: Runnable? = null
    private var light = false

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow || !isEnabled) return
        val t0 = android.os.SystemClock.uptimeMillis()
        val ctr = mv.mapCenter
        val now = doubleArrayOf(ctr.latitude, ctr.longitude, mv.zoomLevelDouble, mv.mapOrientation.toDouble())
        val moving = now[0] != lastView[0] || now[1] != lastView[1] || now[2] != lastView[2] || now[3] != lastView[3]
        lastView = now
        light = moving && (lastCost > 24L || light)
        if (light) {
            settle?.let { mv.removeCallbacks(it) }
            settle = Runnable { light = false; lastCost = 0L; mv.postInvalidate() }.also { mv.postDelayed(it, 280L) }
        }
        try {
            labelled.clear()
            if (showTerrain) {
                drawGround(c, mv)
                if (!light) { drawGrid(c, mv); drawMef(c, mv) }
            }
            if (showAirspace) drawAirspace(c, mv)
            if (!light) { drawNavaids(c, mv); drawObstacles(c, mv) }
            if (showFields) drawFields(c, mv)
        } catch (e: Throwable) {
            // A map that cannot draw one thing still draws the rest.
        }
        lastCost = android.os.SystemClock.uptimeMillis() - t0
    }

    fun release() {
        shaded.evictAll()
        contourCache.evictAll()
    }
}
