package com.saudi.privatevault

import android.content.Context
import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors

/**
 * The radio beacons — VOR, VORTAC, VOR/DME, TACAN, NDB — from the aviation weather service's own
 * navaid records: where each stands, its frequency, and the magnetic variation at it, which is
 * what turns a compass rose to point at magnetic north the way a chart draws it.
 *
 * They come a degree-square at a time, as the map is moved over them, and are kept on the phone,
 * so a chart that has been looked at once draws its beacons again with no connection.
 */
object Navaids {

    class Navaid(
        val id: String, val type: String, val name: String,
        val lat: Double, val lon: Double, val freq: Double, val magVar: Double,
    ) {
        val isVor get() = type.contains("VOR")
        val isNdb get() = type.contains("NDB")
        val isTacan get() = type == "TACAN"
    }

    private val cells = ConcurrentHashMap<String, List<Navaid>>()
    private val pending = ConcurrentHashMap.newKeySet<String>()
    private val pool = Executors.newFixedThreadPool(2)
    private var dir: File? = null

    /** Called on a background thread when a square of beacons arrives. */
    var onData: (() -> Unit)? = null

    fun init(ctx: Context) {
        if (dir == null) dir = File(ctx.filesDir, "aviation/navaids").apply { mkdirs() }
    }

    private fun key(lat: Int, lon: Int) = "$lat/$lon"

    /** Whatever is at hand inside a box; the squares it needs that are not are fetched for next time. */
    fun inView(south: Double, west: Double, north: Double, east: Double): List<Navaid> {
        val out = ArrayList<Navaid>()
        val la0 = Math.floor(south).toInt(); val la1 = Math.floor(north).toInt()
        val lo0 = Math.floor(west).toInt(); val lo1 = Math.floor(east).toInt()
        // A box wider than this is the whole country; beacons are not drawn from that high.
        if ((la1 - la0 + 1) * (lo1 - lo0 + 1) > 20) return out
        for (la in la0..la1) for (lo in lo0..lo1) {
            val k = key(la, lo)
            val list = cells[k]
            if (list != null) out.addAll(list.filter { it.lat in south..north && it.lon in west..east })
            else request(la, lo)
        }
        return out
    }

    private fun request(la: Int, lo: Int) {
        val k = key(la, lo)
        if (!pending.add(k)) return
        pool.execute {
            try {
                val f = dir?.let { File(it, "${la}_$lo.json") }
                var text: String? = null
                // A month is long enough for a beacon: they hardly ever move.
                if (f != null && f.length() > 0 && System.currentTimeMillis() - f.lastModified() < 30L * 86_400_000L) {
                    text = try { f.readText() } catch (e: Exception) { null }
                }
                if (text == null) {
                    text = fetch("https://aviationweather.gov/api/data/navaid?bbox=$la,$lo,${la + 1},${lo + 1}&format=json")
                    if (text != null && f != null) try { f.writeText(text) } catch (e: Exception) { }
                }
                if (text == null) {
                    // The old copy is better than nothing when there is no signal.
                    text = f?.takeIf { it.length() > 0 }?.let { try { it.readText() } catch (e: Exception) { null } }
                }
                if (text != null) {
                    cells[k] = parse(text)
                    onData?.invoke()
                }
            } finally {
                pending.remove(k)
            }
        }
    }

    private fun fetch(url: String): String? = try {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 12000; c.readTimeout = 20000
        try { if (c.responseCode != 200) null else c.inputStream.bufferedReader().readText() } finally { c.disconnect() }
    } catch (e: Exception) { null }

    private fun parse(text: String): List<Navaid> {
        val out = ArrayList<Navaid>()
        try {
            val a = JSONArray(text)
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
                val type = o.optString("type").uppercase()
                if (!(type.contains("VOR") || type.contains("NDB") || type == "TACAN")) continue
                // "15E" is a variation of fifteen degrees east; west counts the other way.
                val mv = o.optString("mag_dec")
                val num = mv.takeWhile { it.isDigit() || it == '.' }.toDoubleOrNull() ?: 0.0
                val magVar = if (mv.endsWith("W", true)) -num else num
                out.add(Navaid(o.optString("id"), type, o.optString("name"),
                    o.optDouble("lat"), o.optDouble("lon"), o.optDouble("freq", 0.0), magVar))
            }
        } catch (e: Exception) { }
        return out
    }
}
