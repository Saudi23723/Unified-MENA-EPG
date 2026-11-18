package com.saudi.privatevault

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.util.LruCache
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * The aeronautical map, drawn rather than photographed.
 *
 * Every other chart in this app is a picture of a printed sheet: it has the printer's white margin
 * down the middle where two sheets meet, it runs out where the sheet runs out, and its lettering
 * lies over on its side when the map is turned. This one is made from the data instead — the ground
 * from elevation figures, the airspace from its published boundaries, the fields and the beacons
 * from their own records — so it is sharp at any size, it has no seams and no edges, its names
 * always stand upright, and it draws with no connection at all once the ground data is on the phone.
 *
 * It is laid out the way the commercial charts lay theirs out: the ground shaded by height with the
 * light falling from the north-west, controlled airspace in blue and magenta by class, restricted
 * ground hatched, fields drawn as their own runways once you are close enough to land on them, and
 * everything thinning out as you zoom away so the picture never becomes a thicket.
 */
class AeroMap(private val ctx: Context, private val map: MapView) : Overlay() {

    private val d = ctx.resources.displayMetrics.density

    // ---- what is drawn ----
    var airports: List<AviationData.Airport> = emptyList()
    var airspace: List<Airspace.Area> = emptyList()
    /** Runway ends by airport ident, so a field can be drawn as the runways it really has. */
    var runways: Map<String, Map<String, Pair<GeoPoint, GeoPoint>>> = emptyMap()
    var showTerrain = true
    var showAirspace = true
    var showObstacles = true

    // ---- the ground ----

    /** A shaded picture of one elevation tile, kept so it is only ever built once. */
    private val shaded = object : LruCache<String, Bitmap>(64) {
        override fun entryRemoved(evicted: Boolean, key: String, old: Bitmap, new: Bitmap?) {
            if (evicted && !old.isRecycled) old.recycle()
        }
    }

    /**
     * The colour of the ground at a height, as a chart tints it: dark green where it is low, through
     * olive and tan, to bare rock and snow high up.
     */
    private fun tint(ft: Float): Int = when {
        ft <= 0f -> 0xFF0B1A2A.toInt()          // sea
        ft < 500 -> 0xFF14261B.toInt()
        ft < 1500 -> 0xFF1B3122.toInt()
        ft < 3000 -> 0xFF28382239.toInt() or 0xFF000000.toInt()
        ft < 4500 -> 0xFF3A3A24.toInt()
        ft < 6000 -> 0xFF4A3C27.toInt()
        ft < 8000 -> 0xFF5A422B.toInt()
        ft < 10000 -> 0xFF6B4D33.toInt()
        ft < 12000 -> 0xFF7E6148.toInt()
        else -> 0xFF9A8B7A.toInt()
    }

    /** Builds the shaded picture of a tile: its colours by height, lit from the north-west. */
    private fun shade(t: Terrain.Tile): Bitmap {
        val n = 256
        val px = IntArray(n * n)
        // How far apart two samples are on the ground, so a slope means the same thing everywhere.
        val latTop = Terrain.latOf(t.y.toDouble(), t.z)
        val latBot = Terrain.latOf((t.y + 1).toDouble(), t.z)
        val metresPerSample = Math.abs(latTop - latBot) * 111_320.0 / n
        for (y in 0 until n) {
            for (x in 0 until n) {
                val h = t.ft[y * n + x]
                var col = tint(h)
                // The slope across and down, from the neighbours either side.
                val xl = t.ft[y * n + (x - 1).coerceAtLeast(0)]
                val xr = t.ft[y * n + (x + 1).coerceAtMost(n - 1)]
                val yu = t.ft[(y - 1).coerceAtLeast(0) * n + x]
                val yd = t.ft[(y + 1).coerceAtMost(n - 1) * n + x]
                val dzdx = (xr - xl) * 0.3048 / (2 * metresPerSample)
                val dzdy = (yd - yu) * 0.3048 / (2 * metresPerSample)
                // Light from the north-west, well above the horizon.
                val nx = -dzdx; val ny = -dzdy; val nz = 1.0
                val len = Math.sqrt(nx * nx + ny * ny + nz * nz)
                val lx = -0.5; val ly = -0.5; val lz = 0.707
                val lam = ((nx * lx + ny * ly + nz * lz) / len).coerceIn(0.0, 1.0)
                val k = (0.55 + 0.75 * lam).coerceIn(0.35, 1.45)
                val r = (((col shr 16) and 0xFF) * k).toInt().coerceIn(0, 255)
                val g = (((col shr 8) and 0xFF) * k).toInt().coerceIn(0, 255)
                val b = ((col and 0xFF) * k).toInt().coerceIn(0, 255)
                col = (0xFF shl 24) or (r shl 16) or (g shl 8) or b
                px[y * n + x] = col
            }
        }
        return Bitmap.createBitmap(px, n, n, Bitmap.Config.ARGB_8888)
    }

    private val tileMatrix = Matrix()
    private val src = FloatArray(8)
    private val dst = FloatArray(8)
    private val pa = Point(); private val pb = Point(); private val pc = Point(); private val pd = Point()

    private fun drawGround(c: Canvas, mv: MapView) {
        val z = Terrain.Z
        val bb = mv.boundingBox
        val x0 = Terrain.tileX(bb.lonWest, z); val x1 = Terrain.tileX(bb.lonEast, z)
        val y0 = Terrain.tileY(bb.latNorth, z); val y1 = Terrain.tileY(bb.latSouth, z)
        // Far out there would be hundreds of tiles: the ground is only shaded where it can be seen.
        if ((x1 - x0 + 1).toLong() * (y1 - y0 + 1) > 90) return
        val pr = mv.projection
        for (ty in y0..y1) for (tx in x0..x1) {
            val key = "$z/$tx/$ty"
            var bmp = shaded.get(key)
            if (bmp == null) {
                val t = Terrain.tile(tx, ty, z) ?: continue      // asks for it, draws it next time
                bmp = shade(t)
                shaded.put(key, bmp)
            }
            if (bmp.isRecycled) continue
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
        }
    }

    private val groundPaint = Paint(Paint.FILTER_BITMAP_FLAG).apply { isAntiAlias = true }

    // ---- airspace ----

    private val asLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeJoin = Paint.Join.ROUND }
    private val asFill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val asText = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10f * d; isFakeBoldText = true }

    /** The colour a class of airspace is drawn in, as the commercial charts colour them. */
    private fun airspaceColour(kind: String): Int = when (kind.uppercase()) {
        "B" -> 0xFF3F8EDC.toInt()
        "C" -> 0xFFB85BA8.toInt()
        "D" -> 0xFF4FA3D1.toInt()
        "E" -> 0xFF8F6FA8.toInt()
        "R", "RESTRICTED", "P", "PROHIBITED", "W", "WARNING" -> 0xFFD1544F.toInt()
        "MOA", "A", "ALERT" -> 0xFFCE8A3C.toInt()
        else -> 0xFF7F8B99.toInt()
    }

    private fun dashFor(kind: String): android.graphics.DashPathEffect? = when (kind.uppercase()) {
        "D" -> android.graphics.DashPathEffect(floatArrayOf(7 * d, 4 * d), 0f)
        "E" -> android.graphics.DashPathEffect(floatArrayOf(3 * d, 5 * d), 0f)
        else -> null
    }

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
            val colour = airspaceColour(a.kind)
            asLine.color = colour
            asLine.strokeWidth = if (a.kind.uppercase() == "B") 3.2f * d else 2.2f * d
            asLine.pathEffect = dashFor(a.kind)
            asFill.color = (colour and 0x00FFFFFF) or 0x1A000000
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
                c.drawPath(path, asFill)
                c.drawPath(path, asLine)
            }
            // Its ceiling over its floor, as a chart prints them, upright whatever the map's turn.
            if (zoom >= 8.5 && a.lowFt != null) {
                pr.toPixels(GeoPoint((a.minLat + a.maxLat) / 2, (a.minLon + a.maxLon) / 2), p)
                val top = a.highFt?.let { "%d".format(it / 100) } ?: "—"
                val bot = if (a.lowFt == 0) "SFC" else "%d".format(a.lowFt!! / 100)
                asText.color = colour
                c.save(); c.rotate(-mv.mapOrientation, p.x.toFloat(), p.y.toFloat())
                val w = asText.measureText(top)
                c.drawText(top, p.x - w / 2, p.y.toFloat(), asText)
                c.drawLine(p.x - w / 2 - 2 * d, p.y + 2 * d, p.x + w / 2 + 2 * d, p.y + 2 * d, asLine)
                c.drawText(bot, p.x - asText.measureText(bot) / 2, p.y + 13 * d, asText)
                c.restore()
            }
        }
        asLine.pathEffect = null
    }

    // ---- fields ----

    private val fieldFill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fieldEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.8f * d }
    private val rwyPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeCap = Paint.Cap.BUTT }
    private val nameTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 11.5f * d; isFakeBoldText = true; color = 0xFFEDF2F7.toInt() }
    private val nameHalo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 11.5f * d; isFakeBoldText = true; style = Paint.Style.STROKE; strokeWidth = 3.2f * d; color = 0xC0000000.toInt()
    }
    private val subTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 9.5f * d; color = 0xFFB9C4CF.toInt() }
    private val subHalo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 9.5f * d; style = Paint.Style.STROKE; strokeWidth = 2.6f * d; color = 0xC0000000.toInt()
    }

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
            val hard = true
            fieldFill.color = if (a.icao.isNotEmpty()) 0xFF2F80ED.toInt() else 0xFFB85BA8.toInt()
            fieldEdge.color = fieldFill.color
            if (zoom >= 11.5 && ends != null && ends.isNotEmpty()) {
                // Close in, the field is its own runways, drawn where they really lie.
                rwyPaint.color = 0xFFE8EDF2.toInt()
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
                // A circle, as a chart marks a field; a ring for one with a tower.
                val r = if (zoom >= 9) 5.5f * d else 4f * d
                c.drawCircle(x, y, r, fieldEdge.apply { style = Paint.Style.STROKE })
                if (a.icao.isNotEmpty()) c.drawCircle(x, y, r * 0.45f, fieldFill.apply { style = Paint.Style.FILL })
            }
            // Its name, upright however the map is turned.
            if (zoom >= 8) {
                c.save(); c.rotate(-mv.mapOrientation, x, y)
                val id = a.icao.ifEmpty { a.ident }
                c.drawText(id, x + 8 * d, y - 4 * d, nameHalo)
                c.drawText(id, x + 8 * d, y - 4 * d, nameTx)
                if (zoom >= 10.5) {
                    val sub = "%,d'".format(a.elevation)
                    c.drawText(sub, x + 8 * d, y + 7 * d, subHalo)
                    c.drawText(sub, x + 8 * d, y + 7 * d, subTx)
                }
                c.restore()
            }
        }
    }

    // ---- towers ----

    private val obsPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 2f * d; color = 0xFFC9A227.toInt() }

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
        }
    }

    // ---- the whole picture ----

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow || !isEnabled) return
        try {
            if (showTerrain) drawGround(c, mv)
            if (showAirspace) drawAirspace(c, mv)
            drawObstacles(c, mv)
            drawFields(c, mv)
        } catch (e: Throwable) {
            // A map that cannot draw one thing still draws the rest.
        }
    }

    fun release() {
        shaded.evictAll()
    }
}
