package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import org.json.JSONArray
import org.json.JSONObject
import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.util.GeoPoint
import org.osmdroid.util.MapTileIndex
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import java.io.File
import java.net.URLEncoder

/**
 * More of the FAA's own data for the chart: military training routes, VFR
 * waypoints, navaids, obstacles and runways. The FAA's services are looked up
 * by name on the phone (their list is kept for 28 days), so a renamed
 * service is still found, and a missing one leaves its layer empty.
 */
object FaaData {
    private const val BASE = "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
    private const val WEST = "-125.5,31.0,-102.0,49.5"

    /** What a layer found, for the pilot to read if it stays empty. */
    val status = HashMap<String, String>()

    private fun dir(ctx: Context) = File(ctx.filesDir, "aviation/faa").apply { mkdirs() }

    private fun services(ctx: Context): List<String> {
        val f = File(dir(ctx), "services.json")
        val fresh = f.exists() && System.currentTimeMillis() - f.lastModified() < 28L * 86400000
        if (!fresh) try {
            val j = JSONObject(AviationData.get("$BASE?f=json", 30000))
            f.writeText(j.toString())
        } catch (e: Exception) {
        }
        return try {
            val a = JSONObject(f.readText()).getJSONArray("services")
            (0 until a.length()).map { a.getJSONObject(it).optString("name") }
        } catch (e: Exception) {
            emptyList()
        }
    }

    /** The first FAA service whose name has any of the words (and none of the others). */
    private fun find(ctx: Context, words: List<String>, not: List<String> = emptyList()): String? {
        val all = services(ctx)
        for (w in words) all.firstOrNull { n -> n.contains(w, true) && not.none { n.contains(it, true) } }?.let { return it }
        return null
    }

    private fun fields(name: String): List<String> = try {
        val a = JSONObject(AviationData.get("$BASE/$name/FeatureServer/0?f=json", 30000)).optJSONArray("fields") ?: JSONArray()
        (0 until a.length()).map { a.getJSONObject(it).optString("name") }
    } catch (e: Exception) {
        emptyList()
    }

    private fun query(name: String, box: String, where: String = "1=1", pages: Int = 5, simplify: Boolean = false): JSONArray {
        val all = JSONArray()
        var offset = 0
        repeat(pages) {
            val url = "$BASE/$name/FeatureServer/0/query?where=" + URLEncoder.encode(where, "UTF-8") +
                "&geometry=$box&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects" +
                "&outFields=*&returnGeometry=true&outSR=4326&geometryPrecision=5&f=json&resultOffset=$offset&resultRecordCount=1000" +
                (if (simplify) "&maxAllowableOffset=0.003" else "")
            val j = JSONObject(AviationData.get(url, 60000))
            if (j.has("error")) throw java.io.IOException(j.optJSONObject("error")?.optString("message"))
            val f = j.optJSONArray("features") ?: return all
            for (i in 0 until f.length()) all.put(f.get(i))
            if (!j.optBoolean("exceededTransferLimit") || f.length() == 0) return all
            offset += f.length()
        }
        return all
    }

    private fun s(a: JSONObject, vararg keys: String): String {
        for (k in keys) for (name in a.keys()) if (name.equals(k, true)) {
            val v = a.optString(name); if (v.isNotEmpty() && v != "null") return v.trim()
        }
        return ""
    }

    /** A number from the first field whose name has one of the words. */
    private fun n(a: JSONObject, vararg words: String): Double? {
        for (w in words) for (name in a.keys()) if (name.contains(w, true)) a.optString(name).toDoubleOrNull()?.let { return it }
        return null
    }

    /** Kept whole on the phone for 28 days; fetched again when older. */
    private fun cached(ctx: Context, key: String, fetch: () -> JSONArray?): JSONArray {
        val f = File(dir(ctx), "$key.json")
        val fresh = f.exists() && System.currentTimeMillis() - f.lastModified() < 28L * 86400000
        if (!fresh) try { fetch()?.let { if (it.length() > 0) f.writeText(it.toString()) } } catch (e: Throwable) { status[key] = e.message ?: "" }
        // Too big to be right (a filter the FAA did not take): not read, so it cannot fill the memory.
        if (f.length() > 12L * 1024 * 1024) { f.delete(); return JSONArray() }
        return try { JSONArray(f.readText()) } catch (e: Throwable) { JSONArray() }
    }

    class Line(val name: String, val pts: DoubleArray, val note: String)
    class Spot(val ident: String, val name: String, val lat: Double, val lon: Double, val kind: String, val extra: String)

    private fun lines(features: JSONArray, label: (JSONObject) -> String, note: (JSONObject) -> String = { "" }): List<Line> {
        val out = ArrayList<Line>()
        for (i in 0 until features.length()) {
            val o = features.optJSONObject(i) ?: continue
            val a = o.optJSONObject("attributes") ?: JSONObject()
            val g = o.optJSONObject("geometry") ?: continue
            val parts = g.optJSONArray("paths") ?: g.optJSONArray("rings") ?: continue
            for (k in 0 until parts.length()) {
                val ring = parts.getJSONArray(k)
                out.add(Line(label(a), DoubleArray(ring.length() * 2).also { d ->
                    for (m in 0 until ring.length()) { val p = ring.getJSONArray(m); d[2 * m] = p.getDouble(1); d[2 * m + 1] = p.getDouble(0) }
                }, note(a)))
            }
        }
        return out
    }

    private fun spots(features: JSONArray, make: (JSONObject, Double, Double) -> Spot?): List<Spot> {
        val out = ArrayList<Spot>()
        for (i in 0 until features.length()) {
            val o = features.optJSONObject(i) ?: continue
            val g = o.optJSONObject("geometry") ?: continue
            val x = g.optDouble("x"); val y = g.optDouble("y")
            if (x.isNaN() || y.isNaN()) continue
            make(o.optJSONObject("attributes") ?: JSONObject(), y, x)?.let { out.add(it) }
        }
        return out
    }

    @Volatile var mtrs: List<Line> = emptyList()
    @Volatile var waypoints: List<Spot> = emptyList()
    @Volatile var navaids: List<Spot> = emptyList()
    @Volatile var obstacles: List<Spot> = emptyList()
    @Volatile var runways: List<Line> = emptyList()

    /** Military training routes of the West (IR, VR, SR), with their altitudes. */
    fun loadMtrs(ctx: Context) {
        val name = find(ctx, listOf("MTR", "Military_Training", "MilitaryTraining"))
        if (name == null) { status["mtr"] = "FAA service not found"; return }
        mtrs = lines(cached(ctx, "mtr") { query(name, WEST, pages = 4, simplify = true) }, { a ->
            listOf(s(a, "TYPE_CODE", "ROUTE_TYPE"), s(a, "IDENT", "NAME", "ROUTE_ID", "ROUTE_NAME")).filter { it.isNotEmpty() }.joinToString("").ifEmpty { "MTR" }
        }, { a -> listOf(s(a, "LOWER_VAL", "MIN_ALT", "LOWALT"), s(a, "UPPER_VAL", "MAX_ALT", "HIGHALT")).filter { it.isNotEmpty() }.joinToString(" – ") })
    }

    /** VFR waypoints (their names start with VP) and VFR reporting points. */
    fun loadWaypoints(ctx: Context) {
        val name = find(ctx, listOf("Designated_Point", "DesignatedPoint", "Designated", "Waypoint"))
        if (name == null) { status["wp"] = "FAA service not found"; return }
        val arr = cached(ctx, "waypoints") {
            val f = fields(name)
            val id = f.firstOrNull { it.equals("IDENT", true) } ?: f.firstOrNull { it.contains("IDENT", true) } ?: f.firstOrNull { it.equals("NAME", true) }
            // Only the VFR waypoints; never every fix of the West.
            if (id != null) query(name, WEST, "$id LIKE 'VP%'", pages = 2) else null
        }
        waypoints = spots(arr) { a, y, x ->
            val ident = s(a, "IDENT", "NAME", "IDENT_TXT")
            val all = a.toString()
            if (!ident.startsWith("VP") && !all.contains("VFR", true) && !all.contains("REP-PT", true)) null
            else Spot(ident, s(a, "NAME", "REMARKS", "DESCRIPTION").takeIf { it != ident } ?: "", y, x, "VFR", "")
        }
    }

    /** VORs, VORTACs, VOR-DMEs and NDBs, with their frequencies. */
    fun loadNavaids(ctx: Context) {
        val name = find(ctx, listOf("NAVAID", "Navaid"), listOf("ILS"))
        if (name == null) { status["nav"] = "FAA service not found"; return }
        navaids = spots(cached(ctx, "navaids") { query(name, WEST, pages = 3) }) { a, y, x ->
            val kind = s(a, "CLASS_TXT", "TYPE_CODE", "NAV_TYPE", "CLASS", "TYPE").uppercase()
            if (kind.contains("TACAN") && !kind.contains("VOR")) return@spots null
            val freq = s(a, "FREQUENCY", "FREQ", "CHANNEL")
            Spot(s(a, "IDENT", "IDENT_TXT"), s(a, "NAME", "NAME_TXT"), y, x, kind.ifEmpty { "VOR" }, freq)
        }
    }

    private val obstacleCells = java.util.concurrent.ConcurrentHashMap<String, List<Spot>>()

    /** Obstacles around a point (a half-degree cell each side), 200 ft or more above the ground. */
    fun loadObstacles(ctx: Context, lat: Double, lon: Double) {
        val name = find(ctx, listOf("Obstacle", "DOF"))
        if (name == null) { status["obst"] = "FAA service not found"; return }
        val out = ArrayList<Spot>()
        for (dy in -1..1) for (dx in -1..1) {
            val cy = Math.floor(lat * 2) / 2 + dy * 0.5
            val cx = Math.floor(lon * 2) / 2 + dx * 0.5
            val key = "obst_%.1f_%.1f".format(java.util.Locale.US, cy, cx)
            val list = obstacleCells.getOrPut(key) {
                spots(cached(ctx, key) { query(name, "%.2f,%.2f,%.2f,%.2f".format(java.util.Locale.US, cx, cy, cx + 0.5, cy + 0.5), pages = 3) }) { a, y, x ->
                    val agl = n(a, "AGL") ?: return@spots null
                    if (agl < 200) return@spots null
                    val msl = n(a, "AMSL", "MSL") ?: 0.0
                    val lit = s(a, "LIGHTING", "LIGHT", "LGT")
                    Spot(s(a, "TYPE_CODE", "OBSTACLE_TYPE", "TYPE"), "", y, x, "%d".format(Math.round(msl)), "%d".format(Math.round(agl)) + if (lit.isNotEmpty() && !lit.startsWith("N", true) && !lit.startsWith("U", true)) " ✱" else "")
                }
            }
            out.addAll(list)
        }
        obstacles = out
    }

    /** Runways in view, for their extended centerlines. */
    fun loadRunways(ctx: Context, lat: Double, lon: Double) {
        val name = find(ctx, listOf("Runway"), listOf("Helipad", "Light"))
        if (name == null) { status["rwy"] = "FAA service not found"; return }
        val out = ArrayList<Line>()
        for (dy in -1..1) for (dx in -1..1) {
            val cy = Math.floor(lat) + dy
            val cx = Math.floor(lon) + dx
            val key = "rwy_%.0f_%.0f".format(java.util.Locale.US, cy, cx)
            out.addAll(lines(cached(ctx, key) { query(name, "%.2f,%.2f,%.2f,%.2f".format(java.util.Locale.US, cx, cy, cx + 1, cy + 1), pages = 2) }, { a ->
                s(a, "DESIGNATOR", "RWY_ID", "RUNWAY_ID", "NAME")
            }))
        }
        runways = out
    }
}

/** Clouds from the GOES weather satellites, infrared (day and night), Iowa Environmental Mesonet. */
object Satellite {
    fun source(): OnlineTileSourceBase {
        val bucket = System.currentTimeMillis() / 600000
        val base = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/goes-ir-4km-900913"
        return object : OnlineTileSourceBase("goesir$bucket", 3, 9, 256, ".png", arrayOf(base)) {
            override fun getTileURLString(index: Long): String =
                "$base/${MapTileIndex.getZoom(index)}/${MapTileIndex.getX(index)}/${MapTileIndex.getY(index)}.png"
        }
    }
}

/** User-drawn practice areas, kept on the phone. */
object PracticeAreas {
    class Area(val name: String, val pts: DoubleArray)

    fun load(ctx: Context): MutableList<Area> = try {
        val a = JSONArray(VaultLock.prefs(ctx).getString("practice_areas", "[]"))
        (0 until a.length()).map { i ->
            val o = a.getJSONObject(i)
            val p = o.getJSONArray("p")
            Area(o.getString("n"), DoubleArray(p.length()) { p.getDouble(it) })
        }.toMutableList()
    } catch (e: Exception) {
        mutableListOf()
    }

    fun save(ctx: Context, list: List<Area>) {
        val a = JSONArray()
        for (x in list) a.put(JSONObject().put("n", x.name).put("p", JSONArray().apply { x.pts.forEach { put(it) } }))
        VaultLock.prefs(ctx).edit().putString("practice_areas", a.toString()).apply()
    }
}

/**
 * Everything else drawn over the chart, each part switched on its own:
 * MTRs, Mode C veils, VFR waypoints, navaids, obstacles, winds at the
 * airports and aloft, ceiling and visibility, density altitude, range rings,
 * extended runway centerlines, practice areas, and night.
 */
class ExtrasOverlay(map: MapView, private val ownship: () -> GeoPoint?, private val altitudeFt: () -> Double?) : Overlay() {
    var mtr = false; var modeC = true; var waypoints = false; var navaids = false; var obstacles = false
    var sfcWind = false; var aloft = false; var ceilVis = false; var densityAlt = false
    var rings = false; var centerlines = false; var practice = true; var night = false

    var metars: () -> Collection<AviationData.Metar> = { emptyList() }
    var aloftText = ""
    var aloftFt = 6000
    var practiceAreas: List<PracticeAreas.Area> = emptyList()
    var drafting: List<Double>? = null

    private val d = map.resources.displayMetrics.density
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 11 * d; isFakeBoldText = true }
    private val halo = Paint(text).apply { style = Paint.Style.STROKE; strokeWidth = 3 * d; color = 0xEEFFFFFF.toInt() }
    private val pt = Point()
    private val pt2 = Point()

    private fun label(c: Canvas, s: String, x: Float, y: Float, color: Int, align: Paint.Align = Paint.Align.LEFT) {
        text.textAlign = align; halo.textAlign = align
        c.drawText(s, x, y, halo)
        text.color = color
        c.drawText(s, x, y, text)
    }

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow) return
        try { paint(c, mv) } catch (e: Exception) { }
    }

    private fun paint(c: Canvas, mv: MapView) {
        val pr = mv.projection
        val bb = mv.boundingBox
        val z = mv.zoomLevelDouble
        fun inView(lat: Double, lon: Double, pad: Double = 0.3) = lat in bb.latSouth - pad..bb.latNorth + pad && lon in bb.lonWest - pad..bb.lonEast + pad
        fun xy(lat: Double, lon: Double): Point { pr.toPixels(GeoPoint(lat, lon), pt); return pt }

        if (night) drawNight(c, mv)

        if (ceilVis) for (m in metars()) {
            val j = m.json ?: continue
            val lat = j.optDouble("lat"); val lon = j.optDouble("lon")
            if (lat.isNaN() || !inView(lat, lon, 1.0)) continue
            val p = xy(lat, lon)
            val r = (pr.metersToPixels(25 * 1852f)).coerceAtLeast(12 * d)
            fill.color = (AviationData.categoryColor(m.category) and 0x00FFFFFF) or 0x30000000
            c.drawCircle(p.x.toFloat(), p.y.toFloat(), r, fill)
        }

        if (practice) {
            for (a in practiceAreas) polygon(c, mv, a.pts, 0xFF7E57C2.toInt(), a.name)
            drafting?.let { polygon(c, mv, it.toDoubleArray(), 0xFFFFAB00.toInt(), "…", closed = false) }
        }

        if (mtr && z >= 8) {
            line.color = 0xFF6D4C41.toInt(); line.strokeWidth = 2 * d; line.pathEffect = null
            for (l in FaaData.mtrs) {
                if (!(0 until l.pts.size / 2).any { inView(l.pts[2 * it], l.pts[2 * it + 1]) }) continue
                val path = Path()
                for (i in 0 until l.pts.size / 2) {
                    val p = xy(l.pts[2 * i], l.pts[2 * i + 1])
                    if (i == 0) path.moveTo(p.x.toFloat(), p.y.toFloat()) else path.lineTo(p.x.toFloat(), p.y.toFloat())
                }
                c.drawPath(path, line)
                val mid = l.pts.size / 4
                val p = xy(l.pts[2 * mid], l.pts[2 * mid + 1])
                if (z >= 9.5) label(c, l.name, p.x + 4 * d, p.y - 4 * d, 0xFF6D4C41.toInt())
            }
        }

        if (modeC && z >= 6 && z <= 11) {
            // 30 nm around each Class B primary airport (91.215): a transponder with altitude, and ADS-B Out.
            line.color = 0xFF2962FF.toInt(); line.strokeWidth = 1.6f * d
            line.pathEffect = DashPathEffect(floatArrayOf(12 * d, 8 * d), 0f)
            for ((name, ctr) in ModeC.centers) {
                if (!inView(ctr.first, ctr.second, 1.0)) continue
                val p = xy(ctr.first, ctr.second)
                val r = pr.metersToPixels(30 * 1852f)
                c.drawCircle(p.x.toFloat(), p.y.toFloat(), r, line)
                label(c, "MODE C 30 NM · $name", p.x.toFloat(), p.y - r - 4 * d, 0xFF2962FF.toInt(), Paint.Align.CENTER)
            }
            line.pathEffect = null
        }

        if (navaids && z >= 8) for (n in FaaData.navaids) {
            if (!inView(n.lat, n.lon)) continue
            val p = xy(n.lat, n.lon)
            val x = p.x.toFloat(); val y = p.y.toFloat()
            line.color = 0xFF0D47A1.toInt(); line.strokeWidth = 1.6f * d
            val r = 7 * d
            val hex = Path().apply { for (k in 0..6) { val a = Math.toRadians(60.0 * k); val px = x + r * Math.cos(a).toFloat(); val py = y + r * Math.sin(a).toFloat(); if (k == 0) moveTo(px, py) else lineTo(px, py) } }
            c.drawPath(hex, line)
            fill.color = 0xFF0D47A1.toInt(); c.drawCircle(x, y, 1.8f * d, fill)
            if (z >= 9.5) label(c, "${n.ident} ${n.extra}".trim(), x + 9 * d, y - 6 * d, 0xFF0D47A1.toInt())
        }

        if (waypoints && z >= 9) for (w in FaaData.waypoints) {
            if (!inView(w.lat, w.lon)) continue
            val p = xy(w.lat, w.lon)
            val x = p.x.toFloat(); val y = p.y.toFloat()
            fill.color = 0xFFAD1457.toInt()
            val flag = Path().apply { moveTo(x, y); lineTo(x, y - 12 * d); lineTo(x + 8 * d, y - 9 * d); lineTo(x, y - 6 * d); close() }
            c.drawPath(flag, fill)
            if (z >= 10.5) label(c, w.ident, x + 9 * d, y - 4 * d, 0xFFAD1457.toInt())
        }

        if (obstacles && z >= 9) {
            val alt = altitudeFt()
            for (o in FaaData.obstacles) {
                if (!inView(o.lat, o.lon, 0.05)) continue
                val p = xy(o.lat, o.lon)
                val msl = o.kind.toDoubleOrNull() ?: 0.0
                // Red within 500 ft of the aircraft's altitude or above it.
                val color = if (alt != null && msl >= alt - 500) 0xFFD50000.toInt() else 0xFF37474F.toInt()
                fill.color = color
                val x = p.x.toFloat(); val y = p.y.toFloat()
                c.drawPath(Path().apply { moveTo(x, y - 10 * d); lineTo(x - 5 * d, y); lineTo(x + 5 * d, y); close() }, fill)
                if (z >= 11) label(c, "${o.kind} (${o.extra})", x + 6 * d, y - 2 * d, color)
            }
        }

        if (centerlines && z >= 10) {
            line.color = 0xFF00838F.toInt(); line.strokeWidth = 1.4f * d
            line.pathEffect = DashPathEffect(floatArrayOf(10 * d, 6 * d), 0f)
            for (r in FaaData.runways) {
                val ends = Runways.ends(r.pts) ?: continue
                if (!inView(ends[0], ends[1], 0.2)) continue
                for (k in 0..1) {
                    val (aLat, aLon) = if (k == 0) ends[0] to ends[1] else ends[2] to ends[3]
                    val (bLat, bLon) = if (k == 0) ends[2] to ends[3] else ends[0] to ends[1]
                    // From each end, 5 nm out along the runway's line, with a tick each mile.
                    val len = Nav.distanceNm(aLat, aLon, bLat, bLon).coerceAtLeast(0.01)
                    val dLat = (aLat - bLat) / len; val dLon = (aLon - bLon) / len
                    val p0 = xy(aLat, aLon); val x0 = p0.x.toFloat(); val y0 = p0.y.toFloat()
                    pr.toPixels(GeoPoint(aLat + dLat * 5, aLon + dLon * 5), pt2)
                    c.drawLine(x0, y0, pt2.x.toFloat(), pt2.y.toFloat(), line)
                }
            }
            line.pathEffect = null
        }

        if (sfcWind && z >= 8.5) for (m in metars()) {
            val j = m.json ?: continue
            val lat = j.optDouble("lat"); val lon = j.optDouble("lon")
            if (lat.isNaN() || !inView(lat, lon)) continue
            val spd = j.optString("wspd").toIntOrNull() ?: continue
            val dir = j.optString("wdir").toIntOrNull()
            val p = xy(lat, lon)
            val gust = j.optString("wgst").toIntOrNull()
            barb(c, p.x.toFloat(), p.y.toFloat(), dir, spd, mv.mapOrientation, if (spd >= 16 || (gust ?: 0) >= 20) 0xFFD50000.toInt() else 0xFF263238.toInt())
            if (z >= 10.5) label(c, (if (dir == null) "VRB" else "%03d".format(dir)) + "/$spd" + (gust?.let { "G$it" } ?: ""),
                p.x.toFloat(), p.y + 16 * d, 0xFF263238.toInt(), Paint.Align.CENTER)
        }

        if (densityAlt && z >= 8.5) for (m in metars()) {
            val j = m.json ?: continue
            val lat = j.optDouble("lat"); val lon = j.optDouble("lon")
            if (lat.isNaN() || !inView(lat, lon)) continue
            val da = DensityAlt.of(j) ?: continue
            val p = xy(lat, lon)
            val color = when { da >= 8000 -> 0xFFD50000.toInt(); da >= 5000 -> 0xFFE65100.toInt(); else -> 0xFF2E7D32.toInt() }
            label(c, "DA %,d".format(da), p.x + 10 * d, p.y + 4 * d, color)
        }

        if (aloft && aloftText.isNotEmpty() && z >= 5) for ((st, pos) in AviationData.fbStations()) {
            if (!inView(pos.first, pos.second, 1.0)) continue
            val w = AviationData.windAt(aloftText, pos.first, pos.second, aloftFt, station = st) ?: continue
            val p = xy(pos.first, pos.second)
            barb(c, p.x.toFloat(), p.y.toFloat(), w.first, w.second, mv.mapOrientation, 0xFF1A237E.toInt())
            label(c, "%03d/%d%s".format(w.first, w.second, w.third?.let { " %+d°".format(it) } ?: ""), p.x.toFloat(), p.y + 16 * d, 0xFF1A237E.toInt(), Paint.Align.CENTER)
        }

        if (rings) ownship()?.let { me ->
            val p = xy(me.latitude, me.longitude)
            line.color = 0xCC00B8D4.toInt(); line.strokeWidth = 1.5f * d
            for (nm in intArrayOf(5, 10, 20)) {
                val r = pr.metersToPixels(nm * 1852f)
                c.drawCircle(p.x.toFloat(), p.y.toFloat(), r, line)
                label(c, "$nm", p.x.toFloat(), p.y - r - 3 * d, 0xFF00838F.toInt(), Paint.Align.CENTER)
            }
        }
    }

    private fun polygon(c: Canvas, mv: MapView, pts: DoubleArray, color: Int, name: String, closed: Boolean = true) {
        if (pts.size < 2) return
        val path = Path()
        var sx = 0f; var sy = 0f
        for (i in 0 until pts.size / 2) {
            mv.projection.toPixels(GeoPoint(pts[2 * i], pts[2 * i + 1]), pt)
            if (i == 0) path.moveTo(pt.x.toFloat(), pt.y.toFloat()) else path.lineTo(pt.x.toFloat(), pt.y.toFloat())
            sx += pt.x; sy += pt.y
            if (!closed) { fill.color = color; c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), 5 * d, fill) }
        }
        if (closed) path.close()
        fill.color = (color and 0x00FFFFFF) or 0x22000000
        if (closed) c.drawPath(path, fill)
        line.color = color; line.strokeWidth = 2.2f * d; line.pathEffect = null
        c.drawPath(path, line)
        val n = pts.size / 2
        label(c, name, sx / n, sy / n, color, Paint.Align.CENTER)
    }

    /** A wind barb: the staff points where the wind comes from; a half feather 5 kt, a feather 10, a flag 50. */
    private fun barb(c: Canvas, x: Float, y: Float, dirTrue: Int?, kt: Int, mapTurn: Float, color: Int) {
        line.color = color; line.strokeWidth = 1.8f * d; line.pathEffect = null
        fill.color = color
        if (kt < 3 || dirTrue == null) { c.drawCircle(x, y, 5 * d, line); return }
        c.save()
        c.rotate(dirTrue + mapTurn, x, y)
        val staff = 20 * d
        c.drawLine(x, y, x, y - staff, line)
        var left = (kt + 2) / 5 * 5
        var at = y - staff
        while (left >= 50) { c.drawPath(Path().apply { moveTo(x, at); lineTo(x + 10 * d, at + 3 * d); lineTo(x, at + 6 * d); close() }, fill); at += 8 * d; left -= 50 }
        while (left >= 10) { c.drawLine(x, at, x + 10 * d, at - 4 * d, line); at += 5 * d; left -= 10 }
        if (left >= 5) c.drawLine(x, at, x + 5 * d, at - 2 * d, line)
        c.restore()
    }

    /** Where it is night now: the side of the Earth away from the sun, shaded. */
    private fun drawNight(c: Canvas, mv: MapView) {
        val now = System.currentTimeMillis()
        val days = now / 86400000.0 - 10957.5   // since 2000-01-01 12:00 UTC
        val g = Math.toRadians((357.529 + 0.98560028 * days) % 360)
        val q = (280.459 + 0.98564736 * days) % 360
        val lam = Math.toRadians(q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g))
        val eps = Math.toRadians(23.439 - 0.00000036 * days)
        val decl = Math.asin(Math.sin(eps) * Math.sin(lam))
        val ra = Math.toDegrees(Math.atan2(Math.cos(eps) * Math.sin(lam), Math.cos(lam)))
        val gmst = (280.46061837 + 360.98564736629 * days) % 360
        val subLon = ((ra - gmst + 540) % 360) - 180
        val path = Path()
        val north = decl < 0
        var first = true
        var lon = -180.0
        while (lon <= 180.0) {
            val h = Math.toRadians(lon - subLon)
            val lat = Math.toDegrees(Math.atan(-Math.cos(h) / Math.tan(decl))).coerceIn(-84.0, 84.0)
            mv.projection.toPixels(GeoPoint(lat, lon), pt)
            if (first) { path.moveTo(pt.x.toFloat(), pt.y.toFloat()); first = false } else path.lineTo(pt.x.toFloat(), pt.y.toFloat())
            lon += 2.0
        }
        mv.projection.toPixels(GeoPoint(if (north) 84.0 else -84.0, 180.0), pt); path.lineTo(pt.x.toFloat(), pt.y.toFloat())
        mv.projection.toPixels(GeoPoint(if (north) 84.0 else -84.0, -180.0), pt); path.lineTo(pt.x.toFloat(), pt.y.toFloat())
        path.close()
        fill.color = 0x400D1B3E
        c.drawPath(path, fill)
    }
}

/** Density altitude from a METAR: pressure altitude from the altimeter, then the temperature's effect. */
object DensityAlt {
    fun of(j: JSONObject): Int? {
        val elevM = j.optString("elev").toDoubleOrNull() ?: return null
        val t = j.optString("temp").toDoubleOrNull() ?: return null
        var alt = j.optString("altim").toDoubleOrNull() ?: return null
        if (alt < 100) alt *= 33.8639   // inHg to hPa
        val elevFt = elevM * 3.28084
        val pa = elevFt + (1013.25 - alt) * 30.0
        val isa = 15 - 2 * pa / 1000
        return Math.round(pa + 120 * (t - isa)).toInt()
    }
}

/** The two ends of a runway from its outline: the middles of its two short sides (or a line's ends). */
object Runways {
    fun ends(pts: DoubleArray): DoubleArray? {
        val n = pts.size / 2
        if (n < 2) return null
        if (n <= 3) return doubleArrayOf(pts[0], pts[1], pts[2 * n - 2], pts[2 * n - 1])
        val m = if (pts[0] == pts[2 * n - 2] && pts[1] == pts[2 * n - 1]) n - 1 else n
        if (m < 4) return null
        // The shortest side and the side across from it.
        val sides = (0 until m).map { i -> val k = (i + 1) % m; i to Nav.distanceNm(pts[2 * i], pts[2 * i + 1], pts[2 * k], pts[2 * k + 1]) }
        val s1 = sides.minByOrNull { it.second }!!.first
        val s2 = (s1 + m / 2) % m
        fun mid(i: Int): Pair<Double, Double> { val k = (i + 1) % m; return (pts[2 * i] + pts[2 * k]) / 2 to (pts[2 * i + 1] + pts[2 * k + 1]) / 2 }
        val a = mid(s1); val b = mid(s2)
        return doubleArrayOf(a.first, a.second, b.first, b.second)
    }
}

/** Mode C veils: 30 nm around each Class B primary airport, found from the Class B airspace itself. */
object ModeC {
    @Volatile var centers: List<Pair<String, Pair<Double, Double>>> = emptyList()

    fun build(airports: List<AviationData.Airport>) {
        val groups = Airspace.areas.filter { it.kind == "B" }.groupBy { it.name.uppercase().replace(Regex("CLASS B.*|AREA [A-Z].*"), "").trim() }
        centers = groups.mapNotNull { (name, list) ->
            // The Class B's surface area sits on its primary airport.
            val sfc = list.filter { it.lowFt == 0 }.ifEmpty { list }
            val lat = (sfc.minOf { it.minLat } + sfc.maxOf { it.maxLat }) / 2
            val lon = (sfc.minOf { it.minLon } + sfc.maxOf { it.maxLon }) / 2
            val apt = airports.filter { it.icao.startsWith("K") }.minByOrNull { Nav.distanceNm(lat, lon, it.lat, it.lon) }
                ?.takeIf { Nav.distanceNm(lat, lon, it.lat, it.lon) < 10 }
            if (apt != null) apt.icao to (apt.lat to apt.lon) else if (name.isNotEmpty()) name to (lat to lon) else null
        }.distinctBy { it.first }
    }
}
