package com.saudi.privatevault

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.util.MapTileIndex
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Public US aviation data, straight from its source so it is always the
 * current edition: FAA charts (tiles the FAA re-publishes every 56-day
 * cycle), FAA airports, and aviationweather.gov observations and forecasts.
 */
object AviationData {

    /** A chart or base map, as tiles in the z/y/x order ArcGIS uses. */
    class Layer(val key: String, val label: Int, private val base: String, val maxZoom: Int) {
        fun source() = object : OnlineTileSourceBase(key, 3, maxZoom, 256, "", arrayOf(base)) {
            override fun getTileURLString(index: Long): String =
                "$base/tile/${MapTileIndex.getZoom(index)}/${MapTileIndex.getY(index)}/${MapTileIndex.getX(index)}"
        }
    }

    private const val FAA_TILES = "https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
    private const val ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services"

    val LAYERS = listOf(
        Layer("sectional", R.string.map_sectional, "$FAA_TILES/VFR_Sectional/MapServer", 12),
        Layer("tac", R.string.map_tac, "$FAA_TILES/VFR_Terminal/MapServer", 13),
        Layer("ifrlow", R.string.map_ifr_low, "$FAA_TILES/IFR_AreaLow/MapServer", 12),
        Layer("topo", R.string.map_topo, "$ESRI/World_Topo_Map/MapServer", 17),
        Layer("imagery", R.string.map_imagery, "$ESRI/World_Imagery/MapServer", 18),
    )

    /** A public-use airport. */
    class Airport(val ident: String, val icao: String, val name: String, val city: String, val elevation: Int, val lat: Double, val lon: Double)

    /** A weather report at a station, with its flight category (VFR, MVFR, IFR, LIFR). */
    class Metar(val station: String, val raw: String, val category: String, val time: Long, val json: JSONObject? = null)

    private const val AIRPORTS =
        "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/US_Airport/FeatureServer/0/query"


    fun get(url: String, timeout: Int = 20000): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = timeout
        c.readTimeout = timeout
        c.setRequestProperty("User-Agent", "Khazanti-EFB/1.0")
        try {
            if (c.responseCode != 200) throw java.io.IOException("HTTP ${c.responseCode}")
            return c.inputStream.bufferedReader().readText()
        } finally {
            c.disconnect()
        }
    }

    /** Every public-use airport in the US, kept on the phone for 28 days (and used offline). */
    fun airports(ctx: Context, refresh: Boolean = false): List<Airport> {
        val file = File(ctx.filesDir, "aviation/airports_us.json")
        val west = File(ctx.filesDir, "aviation/airports.json")
        val fresh = file.exists() && System.currentTimeMillis() - file.lastModified() < 28L * 86400000
        if (!refresh && fresh) parseAirports(file.readText())?.let { return it }
        return try {
            val all = JSONArray()
            run {
                var offset = 0
                while (true) {
                    val where = URLEncoder.encode("TYPE_CODE='AD' AND PRIVATEUSE=0", "UTF-8")
                    val json = JSONObject(get(
                        "$AIRPORTS?where=$where&outFields=IDENT,ICAO_ID,NAME,ELEVATION,SERVCITY,STATE" +
                            "&returnGeometry=true&outSR=4326&f=json&orderByFields=OBJECTID&resultOffset=$offset&resultRecordCount=2000",
                    ))
                    val features = json.optJSONArray("features") ?: JSONArray()
                    for (i in 0 until features.length()) {
                        val f = features.getJSONObject(i)
                        val a = f.getJSONObject("attributes")
                        val g = f.optJSONObject("geometry") ?: continue
                        all.put(JSONObject()
                            .put("id", a.optString("IDENT")).put("icao", a.optString("ICAO_ID").takeIf { it != "null" } ?: "")
                            .put("n", a.optString("NAME")).put("c", a.optString("SERVCITY"))
                            .put("e", a.optDouble("ELEVATION", 0.0).toInt())
                            .put("y", g.getDouble("y")).put("x", g.getDouble("x")))
                    }
                    if (!json.optBoolean("exceededTransferLimit") || features.length() == 0) break
                    offset += features.length()
                }
            }
            if (all.length() > 0) {
                file.parentFile?.mkdirs()
                file.writeText(all.toString())
            }
            parseAirports(all.toString()) ?: emptyList()
        } catch (e: Exception) {
            listOf(file, west).firstNotNullOfOrNull { f -> if (f.exists()) parseAirports(f.readText()) else null } ?: emptyList()
        }
    }

    private fun parseAirports(text: String): List<Airport>? = try {
        val a = JSONArray(text)
        (0 until a.length()).map { i ->
            val o = a.getJSONObject(i)
            Airport(o.getString("id"), o.optString("icao"), o.optString("n"), o.optString("c"), o.optInt("e"), o.getDouble("y"), o.getDouble("x"))
        }.takeIf { it.isNotEmpty() }
    } catch (e: Exception) {
        null
    }

    /** Latest METARs in a box (south, west, north, east). */
    fun metars(south: Double, west: Double, north: Double, east: Double): List<Metar> = try {
        val a = JSONArray(get("https://aviationweather.gov/api/data/metar?bbox=$south,$west,$north,$east&format=json"))
        (0 until a.length()).map { i ->
            val o = a.getJSONObject(i)
            Metar(o.optString("icaoId"), o.optString("rawOb"), o.optString("fltCat"), o.optLong("obsTime"), o)
        }
    } catch (e: Exception) {
        emptyList()
    }

    fun metar(station: String): Metar? = try {
        val a = JSONArray(get("https://aviationweather.gov/api/data/metar?ids=$station&format=json"))
        if (a.length() == 0) null else a.getJSONObject(0).let { Metar(it.optString("icaoId"), it.optString("rawOb"), it.optString("fltCat"), it.optLong("obsTime"), it) }
    } catch (e: Exception) {
        null
    }

    fun taf(station: String): String? = try {
        val a = JSONArray(get("https://aviationweather.gov/api/data/taf?ids=$station&format=json"))
        if (a.length() == 0) null else a.getJSONObject(0).optString("rawTAF")
    } catch (e: Exception) {
        null
    }

    // ---- weather and airspace drawn over the chart ----

    /** NEXRAD composite reflectivity (Iowa Environmental Mesonet), a fresh set every 5 minutes. */
    fun radarSource(): OnlineTileSourceBase {
        val bucket = System.currentTimeMillis() / 300000
        val base = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913"
        return object : OnlineTileSourceBase("radar$bucket", 3, 11, 256, ".png", arrayOf(base)) {
            override fun getTileURLString(index: Long): String =
                "$base/${MapTileIndex.getZoom(index)}/${MapTileIndex.getX(index)}/${MapTileIndex.getY(index)}.png"
        }
    }

    /** An area on the chart: a SIGMET, an AIRMET, or a TFR, as lat,lon pairs. */
    class Area(val kind: String, val label: String, val text: String, val color: Int, val pts: DoubleArray) {
        fun contains(lat: Double, lon: Double): Boolean {
            var inside = false
            var j = pts.size - 2
            var i = 0
            while (i < pts.size) {
                val yi = pts[i]; val xi = pts[i + 1]; val yj = pts[j]; val xj = pts[j + 1]
                if ((yi > lat) != (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside
                j = i
                i += 2
            }
            return inside
        }
    }

    /** A pilot report: where, what, and how bad. */
    class Pirep(val lat: Double, val lon: Double, val raw: String, val kind: Char, val urgent: Boolean)

    // The western states and a margin around them.
    private fun inWest(pts: DoubleArray): Boolean {
        var i = 0
        while (i < pts.size) {
            if (pts[i] in 28.0..52.0 && pts[i + 1] in -128.0..-100.0) return true
            i += 2
        }
        return false
    }

    private fun coords(o: JSONObject): DoubleArray? {
        val a = o.optJSONArray("coords") ?: return null
        val out = DoubleArray(a.length() * 2)
        for (i in 0 until a.length()) {
            val p = a.optJSONObject(i) ?: return null
            out[2 * i] = p.optString("lat").toDoubleOrNull() ?: return null
            out[2 * i + 1] = p.optString("lon").toDoubleOrNull() ?: return null
        }
        return out.takeIf { it.size >= 6 }
    }

    fun hazardColor(h: String): Int = when {
        h.startsWith("CONVECTIVE") -> 0xFFE53935.toInt()
        h.startsWith("IFR") -> 0xFF7B1FA2.toInt()
        h.startsWith("MT") -> 0xFF8D6E63.toInt()
        h.startsWith("TURB") -> 0xFFFF8F00.toInt()
        h.startsWith("ICE") -> 0xFF0288D1.toInt()
        h.startsWith("ASH") -> 0xFF424242.toInt()
        else -> 0xFF00897B.toInt()
    }

    private fun alt(v: String) = v.toIntOrNull()?.let { if (it == 0) "SFC" else "%,d".format(it) } ?: v

    /** SIGMETs, convective SIGMETs and the current G-AIRMETs over the West. */
    fun airspaceWeather(): List<Area> {
        val out = ArrayList<Area>()
        try {
            val a = JSONArray(get("https://aviationweather.gov/api/data/airsigmet?format=json"))
            for (i in 0 until a.length()) {
                val o = a.getJSONObject(i)
                val pts = coords(o) ?: continue
                if (!inWest(pts)) continue
                val type = o.optString("airSigmetType").ifEmpty { "SIGMET" }
                val hazard = o.optString("hazard")
                val lo = o.optString("altitudeLow1"); val hi = o.optString("altitudeHi1")
                out.add(Area(type, "$type $hazard", "$type · $hazard · ${alt(lo)}–${alt(hi)} ft\n\n${o.optString("rawAirSigmet")}",
                    if (type == "SIGMET") 0xFFD50000.toInt() else hazardColor(hazard), pts))
            }
        } catch (e: Exception) {
        }
        try {
            val a = JSONArray(get("https://aviationweather.gov/api/data/gairmet?format=json"))
            for (i in 0 until a.length()) {
                val o = a.getJSONObject(i)
                if (o.optString("forecastHour", "0").toIntOrNull()?.let { it != 0 } == true) continue
                val hazard = o.optString("hazard")
                if (hazard == "FZLVL" || hazard == "M_FZLVL") continue
                val pts = coords(o) ?: continue
                if (!inWest(pts)) continue
                val due = o.optString("dueTo").takeIf { it.isNotEmpty() && it != "null" }
                val levels = listOf(o.optString("base"), o.optString("top")).filter { it.isNotEmpty() && it != "null" }
                out.add(Area("AIRMET", hazard.replace('_', ' '),
                    "G-AIRMET ${o.optString("product")} · ${hazard.replace('_', ' ')}" +
                        (if (levels.size == 2) " · ${alt(levels[0])}–${alt(levels[1])} ft" else "") +
                        (due?.let { "\n$it" } ?: "") + "\n${o.optString("validTime")}",
                    hazardColor(hazard), pts))
            }
        } catch (e: Exception) {
        }
        return out
    }

    /** Temporary flight restrictions from the FAA, over the West. */
    fun tfrs(): List<Area> = try {
        val json = JSONObject(get(
            "https://tfr.faa.gov/geoserver/TFR/ows?service=WFS&version=1.1.0&request=GetFeature" +
                "&typeName=TFR:V_TFR_LOC&maxFeatures=800&outputFormat=application/json&srsname=EPSG:4326", 30000,
        ))
        val f = json.optJSONArray("features") ?: JSONArray()
        val out = ArrayList<Area>()
        for (i in 0 until f.length()) {
            val o = f.getJSONObject(i)
            val props = o.optJSONObject("properties") ?: JSONObject()
            val g = o.optJSONObject("geometry") ?: continue
            val rings = ArrayList<JSONArray>()
            val c = g.optJSONArray("coordinates") ?: continue
            when (g.optString("type")) {
                "Polygon" -> c.optJSONArray(0)?.let { rings.add(it) }
                "MultiPolygon" -> for (k in 0 until c.length()) c.optJSONArray(k)?.optJSONArray(0)?.let { rings.add(it) }
            }
            for (ring in rings) {
                val pts = DoubleArray(ring.length() * 2)
                for (k in 0 until ring.length()) {
                    val p = ring.getJSONArray(k)
                    val a0 = p.getDouble(0); val a1 = p.getDouble(1)
                    // Longitudes in the US are negative; whichever order the server used.
                    if (a0 < 0) { pts[2 * k] = a1; pts[2 * k + 1] = a0 } else { pts[2 * k] = a0; pts[2 * k + 1] = a1 }
                }
                if (pts.size < 6 || !inWest(pts)) continue
                val title = props.optString("TITLE").ifEmpty { props.optString("title") }
                val key = props.optString("NOTAM_KEY").ifEmpty { props.optString("notam_key") }
                val legal = props.optString("LEGAL").ifEmpty { props.optString("legal") }
                out.add(Area("TFR", "TFR", "TFR $key\n$legal\n$title", 0xFFD50000.toInt(), pts))
            }
        }
        out
    } catch (e: Exception) {
        emptyList()
    }

    fun pireps(south: Double, west: Double, north: Double, east: Double): List<Pirep> = try {
        val a = JSONArray(get("https://aviationweather.gov/api/data/pirep?bbox=$south,$west,$north,$east&age=3&format=json"))
        (0 until a.length()).mapNotNull { i ->
            val o = a.getJSONObject(i)
            val lat = o.optString("lat").toDoubleOrNull() ?: return@mapNotNull null
            val lon = o.optString("lon").toDoubleOrNull() ?: return@mapNotNull null
            val raw = o.optString("rawOb")
            val kind = when {
                o.optString("tbInt1").let { it.isNotEmpty() && it != "null" && it != "NEG" } || raw.contains("/TB") -> 'T'
                o.optString("icgInt1").let { it.isNotEmpty() && it != "null" && it != "NEG" } || raw.contains("/IC") -> 'I'
                else -> 'P'
            }
            Pirep(lat, lon, raw, kind, o.optString("pirepType").startsWith("Urgent") || raw.contains(" UUA "))
        }
    } catch (e: Exception) {
        emptyList()
    }

    // ---- airports in depth ----

    /** Runways and frequencies of an airport, as aviationweather.gov publishes them. */
    fun airportInfo(ctx: Context, station: String): JSONObject? {
        // Kept on the phone, so an airport opened once (or packed for a flight) works without signal.
        val file = File(ctx.filesDir, "aviation/info/${station.replace(Regex("[^A-Z0-9]"), "")}.json")
        return try {
            JSONArray(get("https://aviationweather.gov/api/data/airport?ids=$station&format=json")).optJSONObject(0)?.also {
                file.parentFile?.mkdirs()
                file.writeText(it.toString())
            }
        } catch (e: Exception) {
            null
        } ?: try { JSONObject(file.readText()) } catch (e: Exception) { null }
    }

    /** The last hours of METARs at a station, newest first. */
    fun metarHistory(station: String, hours: Int = 6): String = try {
        get("https://aviationweather.gov/api/data/metar?ids=$station&hours=$hours&format=raw").trim()
    } catch (e: Exception) {
        ""
    }

    /** NOTAMs for an airport from the FAA NOTAM Search, kept on the phone for reading without signal. */
    fun notams(ctx: Context, ident: String): Pair<List<String>, Long>? {
        val file = File(ctx.filesDir, "aviation/notams/${ident.replace(Regex("[^A-Z0-9]"), "")}.json")
        // The FAA's official NOTAM API, with the pilot's own free key from api.faa.gov.
        val prefs = VaultLock.prefs(ctx)
        val id = prefs.getString("faa_client_id", "") ?: ""
        val secret = prefs.getString("faa_client_secret", "") ?: ""
        if (id.isNotEmpty() && secret.isNotEmpty()) try {
            val c = URL("https://external-api.faa.gov/notamapi/v1/notams?icaoLocation=$ident&pageSize=100").openConnection() as HttpURLConnection
            c.connectTimeout = 20000
            c.readTimeout = 30000
            c.setRequestProperty("client_id", id)
            c.setRequestProperty("client_secret", secret)
            try {
                if (c.responseCode == 200) {
                    val items = JSONObject(c.inputStream.bufferedReader().readText()).optJSONArray("items") ?: JSONArray()
                    val list = JSONArray()
                    for (i in 0 until items.length()) {
                        val n = items.getJSONObject(i).optJSONObject("properties")?.optJSONObject("coreNOTAMData")?.optJSONObject("notam") ?: continue
                        list.put(JSONObject().put("icaoMessage", "${n.optString("number")}  ${n.optString("text")}".trim()))
                    }
                    file.parentFile?.mkdirs()
                    file.writeText(JSONObject().put("notamList", list).toString())
                }
            } finally {
                c.disconnect()
            }
        } catch (e: Exception) {
        }
        if (id.isEmpty()) try {
            // As the FAA's own page asks it: a session from the page first, then the search with the page's headers.
            if (java.net.CookieHandler.getDefault() == null) java.net.CookieHandler.setDefault(java.net.CookieManager())
            (URL("https://notams.aim.faa.gov/notamSearch/nsapp.html").openConnection() as HttpURLConnection).apply {
                connectTimeout = 15000; readTimeout = 15000
                setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")
                try { inputStream.use { it.readBytes() } } catch (e: Exception) {} finally { disconnect() }
            }
            val c = URL("https://notams.aim.faa.gov/notamSearch/search").openConnection() as HttpURLConnection
            c.setRequestProperty("Referer", "https://notams.aim.faa.gov/notamSearch/nsapp.html")
            c.setRequestProperty("Origin", "https://notams.aim.faa.gov")
            c.setRequestProperty("X-Requested-With", "XMLHttpRequest")
            c.setRequestProperty("Accept", "application/json, text/plain, */*")
            c.connectTimeout = 20000
            c.readTimeout = 30000
            c.requestMethod = "POST"
            c.doOutput = true
            c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")
            c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            c.outputStream.use { it.write("searchType=0&designatorsForLocation=$ident&notamsOnly=false&offset=0".toByteArray()) }
            try {
                if (c.responseCode == 200) {
                    val text = c.inputStream.bufferedReader().readText()
                    val list = JSONObject(text).optJSONArray("notamList")
                    if (list != null) {
                        file.parentFile?.mkdirs()
                        file.writeText(text)
                    }
                }
            } finally {
                c.disconnect()
            }
        } catch (e: Exception) {
        }
        return notamsSaved(ctx, ident)
    }

    /** The NOTAMs last saved for an airport, and when. */
    fun notamsSaved(ctx: Context, ident: String): Pair<List<String>, Long>? {
        val file = File(ctx.filesDir, "aviation/notams/${ident.replace(Regex("[^A-Z0-9]"), "")}.json")
        return try {
            val list = JSONObject(file.readText()).getJSONArray("notamList")
            (0 until list.length()).map { i ->
                val n = list.getJSONObject(i)
                n.optString("icaoMessage").ifEmpty { n.optString("traditionalMessageFrom4thWord") }.ifEmpty { n.optString("traditionalMessage") }
                    // The FAA sends some with HTML line breaks and bold labels.
                    .replace(Regex("(?i)<br\\s*/?>"), "\n").replace(Regex("<[^>]+>"), "")
                    .replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").trim()
            }.filter { it.isNotEmpty() } to file.lastModified()
        } catch (e: Exception) {
            null
        }
    }

    /** The raw winds and temperatures aloft (FB) for the western regions. */
    fun windsAloft(hours: Int = 6): String = listOf("sfo", "slc").joinToString("\n\n") { region ->
        try {
            get("https://aviationweather.gov/api/data/windtemp?region=$region&level=low&fcst=%02d".format(hours))
        } catch (e: Exception) {
            ""
        }
    }.trim()

    // Winds-aloft stations of the West, for picking the one nearest a route.
    private val FB_STATIONS = mapOf(
        "LAS" to (36.08 to -115.16), "PRC" to (34.70 to -112.48), "BAM" to (40.57 to -116.92), "RNO" to (39.50 to -119.77),
        "ELY" to (39.30 to -114.84), "TPH" to (38.06 to -117.09), "BIH" to (37.37 to -118.36), "FAT" to (36.78 to -119.72),
        "LAX" to (33.94 to -118.41), "SAN" to (32.73 to -117.19), "BLH" to (33.62 to -114.72), "SFO" to (37.62 to -122.37),
        "SAC" to (38.51 to -121.49), "PHX" to (33.43 to -112.01), "SLC" to (40.79 to -111.97), "RBL" to (40.15 to -122.25),
        "FOT" to (40.67 to -124.24), "ONT" to (34.06 to -117.60), "AST" to (46.16 to -123.88), "MLF" to (38.36 to -113.01),
        "DRK" to (34.70 to -112.48), "EED" to (34.77 to -114.47), "INW" to (35.02 to -110.72), "TUS" to (32.12 to -110.94),
    )

    /** Wind (degrees true, knots) and temperature at an altitude from the FB text, at the station nearest a point. */
    fun fbStations(): Map<String, Pair<Double, Double>> = FB_STATIONS

    fun windAt(text: String, lat: Double, lon: Double, altFt: Int, station: String? = null): Triple<Int, Int, Int?>? {
        var header: List<Pair<Int, Int>>? = null
        val rows = HashMap<String, String>()
        for (line in text.lines()) {
            if (line.startsWith("FT ")) {
                header = Regex("\\d{4,5}").findAll(line).map { it.value.toInt() to it.range.last }.toList()
            } else if (header != null && Regex("^[A-Z0-9]{3} ").containsMatchIn(line)) {
                rows[line.substring(0, 3)] = line
            }
        }
        val cols = header ?: return null
        val station = station?.takeIf { it in rows } ?: rows.keys.filter { it in FB_STATIONS }.minByOrNull { k ->
            FB_STATIONS[k]!!.let { (y, x) -> Nav.distanceNm(lat, lon, y, x) }
        } ?: return null
        val row = rows[station]!!
        val levels = ArrayList<Triple<Int, Double, Double>>()   // altitude, wind east, wind north (blowing from)
        val temps = HashMap<Int, Int>()
        for (m in Regex("\\S+").findAll(row).drop(1)) {
            val col = cols.minByOrNull { Math.abs(it.second - m.range.last) } ?: continue
            if (Math.abs(col.second - m.range.last) > 3) continue
            val v = m.value
            if (v.length < 4) continue
            var dir = v.substring(0, 2).toIntOrNull() ?: continue
            var spd = v.substring(2, 4).toIntOrNull() ?: continue
            if (dir == 99) { dir = 0; spd = 0 } else {
                if (dir > 36) { dir -= 50; spd += 100 }
                dir *= 10
            }
            if (v.length > 4) {
                val t = v.substring(4).replace("+", "").toIntOrNull()
                if (t != null) temps[col.first] = if (col.first >= 24000 && !v.substring(4).startsWith("+")) -Math.abs(t) else t
            }
            val r = Math.toRadians(dir.toDouble())
            levels.add(Triple(col.first, spd * Math.sin(r), spd * Math.cos(r)))
        }
        if (levels.isEmpty()) return null
        levels.sortBy { it.first }
        val lo = levels.lastOrNull { it.first <= altFt } ?: levels.first()
        val hi = levels.firstOrNull { it.first >= altFt } ?: levels.last()
        val f = if (hi.first == lo.first) 0.0 else (altFt - lo.first).toDouble() / (hi.first - lo.first)
        val e = lo.second + (hi.second - lo.second) * f
        val n = lo.third + (hi.third - lo.third) * f
        val dir = ((Math.toDegrees(Math.atan2(e, n)) + 360) % 360).toInt()
        val spd = Math.round(Math.hypot(e, n)).toInt()
        val temp = temps[lo.first]?.let { t0 -> temps[hi.first]?.let { t1 -> Math.round(t0 + (t1 - t0) * f).toInt() } ?: t0 }
        return Triple(if (spd == 0) 0 else (if (dir == 0) 360 else dir), spd, temp)
    }

    // ---- terminal procedures (d-TPP) ----

    /** The current 28-day AIRAC cycle, as the FAA names it (e.g. 2511). */
    fun airacCycle(epochDay: Long = java.time.LocalDate.now().toEpochDay()): String {
        var start = java.time.LocalDate.of(2025, 1, 23).toEpochDay()
        while (start + 28 <= epochDay) start += 28
        while (start > epochDay) start -= 28
        val year = java.time.LocalDate.ofEpochDay(start).year
        var first = start
        while (java.time.LocalDate.ofEpochDay(first - 28).year == year) first -= 28
        return "%02d%02d".format(year % 100, (start - first) / 28 + 1)
    }

    /** A chart of an airport: its kind (APD, IAP, DP, STAR, MIN…), its name and its PDF. */
    class Plate(val code: String, val name: String, val pdf: String)

    /** The procedures of one airport, from the FAA's index of the cycle, kept on the phone for the cycle. */
    fun plates(ctx: Context, ident: String): Pair<String, List<Plate>>? {
        val cycle = airacCycle()
        val file = File(ctx.filesDir, "aviation/tpp.json")
        var index = try { JSONObject(file.readText()) } catch (e: Exception) { null }
        if (index?.optString("cycle") != cycle || !index.optBoolean("us")) {
            index = tppIndex(cycle) ?: index ?: return null
            file.parentFile?.mkdirs()
            file.writeText(index.toString())
        }
        val list = index.optJSONObject("a")?.optJSONArray(ident) ?: return index.optString("cycle") to emptyList()
        return index.optString("cycle") to (0 until list.length()).map { i ->
            val p = list.getJSONArray(i)
            Plate(p.getString(0), p.getString(1), p.getString(2))
        }
    }

    private fun tppIndex(cycle: String): JSONObject? = try {
        val c = URL("https://aeronav.faa.gov/d-tpp/$cycle/xml_data/d-tpp_Metafile.xml").openConnection() as HttpURLConnection
        c.connectTimeout = 30000
        c.readTimeout = 60000
        c.setRequestProperty("User-Agent", "Khazanti-EFB/1.0")
        val airports = JSONObject()
        try {
            if (c.responseCode != 200) throw java.io.IOException("HTTP ${c.responseCode}")
            val x = android.util.Xml.newPullParser()
            x.setInput(c.inputStream.buffered(), null)
            var state = ""
            var apt: JSONArray? = null
            var tag = ""
            val rec = HashMap<String, String>()
            while (true) {
                when (x.next()) {
                    org.xmlpull.v1.XmlPullParser.END_DOCUMENT -> break
                    org.xmlpull.v1.XmlPullParser.START_TAG -> {
                        tag = x.name
                        when (x.name) {
                            "state_code" -> state = x.getAttributeValue(null, "ID") ?: ""
                            "airport_name" -> apt = if (state.isNotEmpty()) JSONArray().also { a ->
                                val id = x.getAttributeValue(null, "apt_ident") ?: ""
                                airports.put(id, a)
                                x.getAttributeValue(null, "icao_ident")?.takeIf { it.isNotEmpty() && it != id }?.let { airports.put(it, a) }
                            } else null
                            "record" -> rec.clear()
                        }
                    }
                    org.xmlpull.v1.XmlPullParser.TEXT -> if (apt != null && tag in setOf("chart_code", "chart_name", "pdf_name", "useraction")) {
                        rec[tag] = (rec[tag] ?: "") + x.text.trim()
                    }
                    org.xmlpull.v1.XmlPullParser.END_TAG -> {
                        if (x.name == "record" && apt != null && rec["useraction"] != "D") {
                            val pdf = rec["pdf_name"] ?: ""
                            if (pdf.endsWith(".PDF", true)) apt.put(JSONArray().put(rec["chart_code"] ?: "").put(rec["chart_name"] ?: "").put(pdf))
                        }
                        if (x.name == "airport_name") apt = null
                        tag = ""
                    }
                }
            }
        } finally {
            c.disconnect()
        }
        if (airports.length() == 0) null else JSONObject().put("cycle", cycle).put("us", true).put("a", airports)
    } catch (e: Exception) {
        null
    }

    /** Downloads one chart of the cycle, once. */
    fun platePdf(ctx: Context, cycle: String, pdf: String): File? {
        val f = File(ctx.filesDir, "plates/$cycle/$pdf")
        if (f.length() > 0) return f
        return try {
            val c = URL("https://aeronav.faa.gov/d-tpp/$cycle/$pdf").openConnection() as HttpURLConnection
            c.connectTimeout = 20000
            c.readTimeout = 60000
            c.setRequestProperty("User-Agent", "Khazanti-EFB/1.0")
            try {
                if (c.responseCode != 200) return null
                f.parentFile?.mkdirs()
                val tmp = File(f.path + ".part")
                c.inputStream.use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
                tmp.renameTo(f)
                f
            } finally {
                c.disconnect()
            }
        } catch (e: Exception) {
            null
        }
    }

    /** The colour charts use for each flight category. */
    fun categoryColor(cat: String): Int = when (cat) {
        "VFR" -> 0xFF2E7D32.toInt()
        "MVFR" -> 0xFF1565C0.toInt()
        "IFR" -> 0xFFC62828.toInt()
        "LIFR" -> 0xFFAD1457.toInt()
        else -> 0xFF757575.toInt()
    }
}

/** Great-circle navigation helpers, in nautical miles and degrees true. */
object Nav {
    private const val R_NM = 3440.065

    fun distanceNm(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val p1 = Math.toRadians(lat1)
        val p2 = Math.toRadians(lat2)
        val dp = p2 - p1
        val dl = Math.toRadians(lon2 - lon1)
        val a = Math.sin(dp / 2) * Math.sin(dp / 2) + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) * Math.sin(dl / 2)
        return 2 * R_NM * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
    }

    fun bearingTrue(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val p1 = Math.toRadians(lat1)
        val p2 = Math.toRadians(lat2)
        val dl = Math.toRadians(lon2 - lon1)
        val y = Math.sin(dl) * Math.cos(p2)
        val x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)
        return (Math.toDegrees(Math.atan2(y, x)) + 360) % 360
    }

    /** Magnetic variation (east positive) from the phone's World Magnetic Model. */
    fun variation(lat: Double, lon: Double): Double =
        android.hardware.GeomagneticField(lat.toFloat(), lon.toFloat(), 0f, System.currentTimeMillis()).declination.toDouble()

    fun magnetic(trueCourse: Double, lat: Double, lon: Double) = (trueCourse - variation(lat, lon) + 360) % 360

    /** The point a distance along a true course from a start. */
    fun destination(lat: Double, lon: Double, courseTrue: Double, nm: Double): org.osmdroid.util.GeoPoint {
        val dr = nm / R_NM
        val p1 = Math.toRadians(lat)
        val l1 = Math.toRadians(lon)
        val c = Math.toRadians(courseTrue)
        val p2 = Math.asin(Math.sin(p1) * Math.cos(dr) + Math.cos(p1) * Math.sin(dr) * Math.cos(c))
        val l2 = l1 + Math.atan2(Math.sin(c) * Math.sin(dr) * Math.cos(p1), Math.cos(dr) - Math.sin(p1) * Math.sin(p2))
        return org.osmdroid.util.GeoPoint(Math.toDegrees(p2), (Math.toDegrees(l2) + 540) % 360 - 180)
    }

    fun deg(d: Double) = "%03d°".format(Math.round(d).toInt() % 360)
}

/** Sunrise, sunset and civil twilight (the almanac method), for the day and night rules of logging and currency. */
object Sun {
    /** Minutes after midnight UTC of a sun event on a day, or null when it does not happen there that day. */
    fun utcMinutes(lat: Double, lon: Double, date: java.time.LocalDate, zenith: Double, rising: Boolean): Double? {
        val n = date.dayOfYear
        val lngHour = lon / 15
        val t = n + ((if (rising) 6.0 else 18.0) - lngHour) / 24
        val m = 0.9856 * t - 3.289
        var l = m + 1.916 * Math.sin(Math.toRadians(m)) + 0.020 * Math.sin(Math.toRadians(2 * m)) + 282.634
        l = (l % 360 + 360) % 360
        var ra = Math.toDegrees(Math.atan(0.91764 * Math.tan(Math.toRadians(l))))
        ra = (ra % 360 + 360) % 360
        ra += Math.floor(l / 90) * 90 - Math.floor(ra / 90) * 90
        ra /= 15
        val sinDec = 0.39782 * Math.sin(Math.toRadians(l))
        val cosDec = Math.cos(Math.asin(sinDec))
        val cosH = (Math.cos(Math.toRadians(zenith)) - sinDec * Math.sin(Math.toRadians(lat))) / (cosDec * Math.cos(Math.toRadians(lat)))
        if (cosH > 1 || cosH < -1) return null
        val h = (if (rising) 360 - Math.toDegrees(Math.acos(cosH)) else Math.toDegrees(Math.acos(cosH))) / 15
        val tt = h + ra - 0.06571 * t - 6.622
        return ((tt - lngHour) % 24 + 24) % 24 * 60
    }

    /** The day's sun times at a place, in the phone's own time zone. */
    fun times(lat: Double, lon: Double, date: java.time.LocalDate = java.time.LocalDate.now()): Map<String, String> {
        val zone = java.time.ZoneId.systemDefault()
        fun at(zenith: Double, rising: Boolean, shiftMin: Long = 0): String {
            val m = utcMinutes(lat, lon, date, zenith, rising) ?: return "—"
            val utc = date.atStartOfDay(java.time.ZoneOffset.UTC).plusSeconds((m * 60).toLong()).plusMinutes(shiftMin)
            var local = utc.withZoneSameInstant(zone)
            // The almanac can land on the neighbouring UTC day; keep the event on this local date.
            if (local.toLocalDate().isBefore(date)) local = local.plusDays(1) else if (local.toLocalDate().isAfter(date)) local = local.minusDays(1)
            return "%02d:%02d".format(local.hour, local.minute)
        }
        return linkedMapOf(
            "dawn" to at(96.0, true), "sunrise" to at(90.833, true), "sunset" to at(90.833, false), "dusk" to at(96.0, false),
            "pax_night_from" to at(90.833, false, 60), "pax_night_to" to at(90.833, true, -60),
        )
    }
}
