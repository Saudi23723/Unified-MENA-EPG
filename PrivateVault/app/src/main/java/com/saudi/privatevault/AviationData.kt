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
    class Metar(val station: String, val raw: String, val category: String, val time: Long)

    private const val AIRPORTS =
        "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/US_Airport/FeatureServer/0/query"

    // The states a Nevada and California pilot crosses most.
    private val STATES = listOf("NV", "CA", "AZ", "UT", "OR", "ID", "NM", "CO", "WY")

    private fun get(url: String, timeout: Int = 20000): String {
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

    /** Public airports of the western states, kept on the phone for 28 days (and used offline). */
    fun airports(ctx: Context, refresh: Boolean = false): List<Airport> {
        val file = File(ctx.filesDir, "aviation/airports.json")
        val fresh = file.exists() && System.currentTimeMillis() - file.lastModified() < 28L * 86400000
        if (!refresh && fresh) parseAirports(file.readText())?.let { return it }
        return try {
            val all = JSONArray()
            for (state in STATES) {
                var offset = 0
                while (true) {
                    val where = URLEncoder.encode("STATE='$state' AND TYPE_CODE='AD' AND PRIVATEUSE=0", "UTF-8")
                    val json = JSONObject(get(
                        "$AIRPORTS?where=$where&outFields=IDENT,ICAO_ID,NAME,ELEVATION,SERVCITY,STATE" +
                            "&returnGeometry=true&outSR=4326&f=json&resultOffset=$offset&resultRecordCount=1000",
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
            if (file.exists()) parseAirports(file.readText()) ?: emptyList() else emptyList()
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
            Metar(o.optString("icaoId"), o.optString("rawOb"), o.optString("fltCat"), o.optLong("obsTime"))
        }
    } catch (e: Exception) {
        emptyList()
    }

    fun metar(station: String): Metar? = try {
        val a = JSONArray(get("https://aviationweather.gov/api/data/metar?ids=$station&format=json"))
        if (a.length() == 0) null else a.getJSONObject(0).let { Metar(it.optString("icaoId"), it.optString("rawOb"), it.optString("fltCat"), it.optLong("obsTime")) }
    } catch (e: Exception) {
        null
    }

    fun taf(station: String): String? = try {
        val a = JSONArray(get("https://aviationweather.gov/api/data/taf?ids=$station&format=json"))
        if (a.length() == 0) null else a.getJSONObject(0).optString("rawTAF")
    } catch (e: Exception) {
        null
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

    fun deg(d: Double) = "%03d°".format(Math.round(d).toInt() % 360)
}
