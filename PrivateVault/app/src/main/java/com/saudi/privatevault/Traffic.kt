package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import org.json.JSONObject
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.util.concurrent.ConcurrentHashMap

/**
 * Traffic around the aircraft, from two sources: an ADS-B receiver such as
 * a Stratux on the phone's Wi-Fi (GDL 90 on UDP port 4000, works in flight
 * with no internet), or, when there is no receiver, the live feed of the
 * airplanes.live network over the internet.
 */
object Traffic {
    class Target(
        val id: String, var call: String, var lat: Double, var lon: Double, var altFt: Int?,
        var gsKt: Int, var track: Double, var type: String, var seen: Long, var fromReceiver: Boolean,
        var reg: String = "", var desc: String = "", var owner: String = "", var vsFpm: Int? = null, var squawk: String = "",
    )

    /** Airlines by their ICAO prefix, the ones met in the West. */
    private val AIRLINES = mapOf(
        "SWA" to "Southwest", "AAL" to "American", "DAL" to "Delta", "UAL" to "United", "ASA" to "Alaska", "JBU" to "JetBlue",
        "NKS" to "Spirit", "FFT" to "Frontier", "SKW" to "SkyWest", "AAY" to "Allegiant", "HAL" to "Hawaiian", "SCX" to "Sun Country",
        "MXY" to "Breeze", "JSX" to "JSX", "QXE" to "Horizon", "ENY" to "Envoy", "RPA" to "Republic", "ASH" to "Mesa", "GJS" to "GoJet",
        "FDX" to "FedEx", "UPS" to "UPS", "GTI" to "Atlas Air", "ABX" to "ABX Air", "VOI" to "Volaris", "VIV" to "Viva Aerobus",
        "AMX" to "Aeroméxico", "ACA" to "Air Canada", "WJA" to "WestJet", "BAW" to "British Airways", "DLH" to "Lufthansa",
        "KLM" to "KLM", "AFR" to "Air France", "VIR" to "Virgin Atlantic", "KAL" to "Korean Air", "EJA" to "NetJets", "LXJ" to "Flexjet",
        "XSR" to "Wheels Up", "CNS" to "Cobalt", "PGR" to "Pinnacle (charter)", "VAR" to "Vegas Air (charter)", "CMP" to "Copa",
        "EDV" to "Endeavor", "TCF" to "Shuttle America", "CPZ" to "Compass", "AWI" to "Air Wisconsin", "PDT" to "Piedmont",
    )

    fun airline(call: String): String? {
        val c = call.trim().uppercase()
        if (c.length < 4 || !c.substring(0, 3).all { it.isLetter() } || !c[3].isDigit()) return null
        return AIRLINES[c.substring(0, 3)] ?: c.substring(0, 3)
    }

    private val routes = ConcurrentHashMap<String, String>()

    /** A flight's route by its callsign (hexdb.io's callsign database, which can be out of date); null if unknown. */
    fun route(call: String): String? {
        val c = call.trim().uppercase()
        if (c.isEmpty()) return null
        routes[c]?.let { return it.ifEmpty { null } }
        val r = try { AviationData.get("https://hexdb.io/callsign-route?callsign=$c", 8000).trim() } catch (e: Exception) { "" }
        val ok = if (Regex("^[A-Z0-9]{3,4}(-[A-Z0-9]{3,4})+$").matches(r)) r.replace("-", " → ") else ""
        routes[c] = ok
        return ok.ifEmpty { null }
    }

    val targets = ConcurrentHashMap<String, Target>()
    @Volatile var receiverSeen = 0L
    private var socket: DatagramSocket? = null
    private var thread: Thread? = null

    fun prune() {
        val now = System.currentTimeMillis()
        targets.values.removeIf { now - it.seen > 60000 }
    }

    // ---- internet ----

    // Two free ADS-B networks fed by receivers on the ground; the one that answered last is asked first.
    // (airplanes.live now refuses apps without an agreement: it answers 403 with a JSON error.)
    private val SOURCES = listOf(
        "https://api.adsb.lol/v2/point/%.4f/%.4f/%d",
        "https://opendata.adsb.fi/api/v2/lat/%.4f/lon/%.4f/dist/%d",
    )
    @Volatile private var good = 0
    /** Which network the traffic came from last, for the map's label. */
    @Volatile var source = ""
    /** Why the last fetch brought nothing, for the message. */
    @Volatile var lastError = ""

    /** Aircraft within [radiusNm] from the ADS-B networks (call off the main thread). */
    fun fetch(lat: Double, lon: Double, radiusNm: Int = 40) {
        if (System.currentTimeMillis() - receiverSeen < 15000) return
        try {
            var text: String? = null
            for (k in SOURCES.indices) {
                val i = (good + k) % SOURCES.size
                // The host by hand: the address template holds "%", which java.net.URI refuses
                // (that exception, swallowed, is what kept the traffic away).
                val host = SOURCES[i].substringAfter("://").substringBefore('/')
                text = try { AviationData.get(SOURCES[i].format(java.util.Locale.US, lat, lon, radiusNm), 8000) } catch (e: Exception) { lastError = "$host: ${e.message ?: e.javaClass.simpleName}"; null }
                // Only a real answer: an error message is JSON too.
                if (text != null && text.trimStart().startsWith("{") && ("\"ac\"" in text || "\"aircraft\"" in text)) { good = i; source = host; break }
                text = null
            }
            val j = JSONObject(text ?: return)
            lastError = ""
            val ac = j.optJSONArray("ac") ?: j.optJSONArray("aircraft") ?: return
            val now = System.currentTimeMillis()
            for (i in 0 until ac.length()) {
                val o = ac.optJSONObject(i) ?: continue
                val hex = o.optString("hex")
                if (hex.isEmpty()) continue
                val la = o.optDouble("lat", Double.NaN); val lo = o.optDouble("lon", Double.NaN)
                if (la.isNaN() || lo.isNaN()) continue
                val alt = o.opt("alt_baro")?.toString()?.let { if (it == "ground") 0 else it.toDoubleOrNull()?.toInt() }
                fun s(k: String) = o.optString(k).trim().takeIf { it != "null" } ?: ""
                val vs = (o.opt("baro_rate") ?: o.opt("geom_rate"))?.toString()?.toDoubleOrNull()?.toInt()
                targets[hex] = Target(hex, s("flight").ifEmpty { s("r") }, la, lo, alt,
                    o.optDouble("gs", 0.0).toInt(), o.optDouble("track", 0.0), s("t"), now, false,
                    reg = s("r"), desc = s("desc"), owner = s("ownOp"), vsFpm = vs, squawk = s("squawk"))
            }
        } catch (e: Exception) {
            lastError = e.javaClass.simpleName + (e.message?.let { ": $it" } ?: "")
        }
    }

    // ---- ADS-B receiver (GDL 90) ----

    fun startReceiver() {
        if (thread != null) return
        thread = Thread {
            try {
                val s = DatagramSocket(null).apply { reuseAddress = true; bind(java.net.InetSocketAddress(4000)) }
                socket = s
                val buf = ByteArray(4096)
                while (!Thread.currentThread().isInterrupted) {
                    val p = DatagramPacket(buf, buf.size)
                    s.receive(p)
                    frames(buf, p.length)
                }
            } catch (e: Exception) {
            }
        }.apply { isDaemon = true; start() }
    }

    fun stopReceiver() {
        thread?.interrupt()
        socket?.close()
        socket = null
        thread = null
    }

    private fun frames(b: ByteArray, n: Int) {
        var i = 0
        while (i < n) {
            if (b[i] != 0x7E.toByte()) { i++; continue }
            var j = i + 1
            val msg = ArrayList<Byte>()
            while (j < n && b[j] != 0x7E.toByte()) {
                if (b[j] == 0x7D.toByte() && j + 1 < n) { msg.add((b[j + 1].toInt() xor 0x20).toByte()); j += 2 } else { msg.add(b[j]); j++ }
            }
            if (msg.size > 3) message(msg.subList(0, msg.size - 2).toByteArray())
            i = j
        }
    }

    private fun u(b: ByteArray, i: Int) = b[i].toInt() and 0xFF

    private fun message(m: ByteArray) {
        val id = u(m, 0)
        // Only real position reports count as a receiver: a stray packet on port 4000 must not
        // silence the internet feed.
        if ((id != 0x14 && id != 0x0A) || m.size < 28) return
        receiverSeen = System.currentTimeMillis()
        if (id == 0x0A) return   // ownship: the phone's own GPS already places the aircraft
        val addr = "%02x%02x%02x".format(u(m, 2), u(m, 3), u(m, 4))
        fun s24(i: Int): Double { var v = (u(m, i) shl 16) or (u(m, i + 1) shl 8) or u(m, i + 2); if (v and 0x800000 != 0) v -= 0x1000000; return v * 180.0 / 0x800000 }
        val lat = s24(5); val lon = s24(8)
        val altRaw = (u(m, 11) shl 4) or (u(m, 12) shr 4)
        val alt = if (altRaw == 0xFFF) null else altRaw * 25 - 1000
        val gs = (u(m, 14) shl 4) or (u(m, 15) shr 4)
        val track = u(m, 17) * 360.0 / 256
        val call = String(m, 19, 8).trim()
        targets[addr] = Target(addr, call, lat, lon, alt, if (gs == 0xFFF) 0 else gs, track, "", System.currentTimeMillis(), true)
    }
}

/** Traffic as arrowheads along their track, with relative altitude in hundreds of feet and a climb or descent arrow. */
class TrafficOverlay(map: MapView, private val ownAltFt: () -> Double?) : Overlay() {
    private val d = map.resources.displayMetrics.density
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.5f * d; color = 0xFF000000.toInt() }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 11 * d; isFakeBoldText = true }
    private val halo = Paint(text).apply { style = Paint.Style.STROKE; strokeWidth = 3 * d; color = 0xEE000000.toInt() }
    private val pt = Point()
    var near: (Traffic.Target) -> Boolean = { false }
    /** A tap on an aircraft: its card. */
    var onTap: ((Traffic.Target) -> Unit)? = null

    override fun onSingleTapConfirmed(e: android.view.MotionEvent, mapView: MapView): Boolean {
        val cb = onTap ?: return false
        // In ground terms, so a turned chart makes no difference: the tap and a finger's width around it.
        val g = mapView.projection.fromPixels(e.x.toInt(), e.y.toInt())
        val g2 = mapView.projection.fromPixels((e.x + 28 * d).toInt(), e.y.toInt())
        val r = Nav.distanceNm(g.latitude, g.longitude, g2.latitude, g2.longitude)
        val hit = Traffic.targets.values.map { t -> t to Nav.distanceNm(g.latitude, g.longitude, t.lat, t.lon) }
            .filter { it.second < r }.minByOrNull { it.second }?.first ?: return false
        cb(hit)
        return true
    }

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val box = mapView.boundingBox
        val own = ownAltFt()
        for (t in Traffic.targets.values) {
            if (t.lat < box.latSouth || t.lat > box.latNorth || t.lon < box.lonWest || t.lon > box.lonEast) continue
            mapView.projection.toPixels(GeoPoint(t.lat, t.lon), pt)
            val x = pt.x.toFloat(); val y = pt.y.toFloat()
            val close = near(t)
            fill.color = if (close) 0xFFFFD600.toInt() else 0xFF00E5FF.toInt()
            val r = 9 * d
            c.save()
            c.rotate(t.track.toFloat(), x, y)
            val p = Path().apply { moveTo(x, y - r); lineTo(x + r * 0.7f, y + r * 0.7f); lineTo(x, y + r * 0.3f); lineTo(x - r * 0.7f, y + r * 0.7f); close() }
            c.drawPath(p, fill)
            c.drawPath(p, edge)
            c.restore()
            val rel = if (own != null && t.altFt != null) "%+03d".format(Math.round((t.altFt!! - own) / 100.0).toInt()) else t.altFt?.let { "%03d".format(it / 100) } ?: ""
            text.color = fill.color
            c.save()
            c.rotate(-mapView.mapOrientation, x, y)
            for ((i, s) in listOf(rel, t.call).filter { it.isNotEmpty() }.withIndex()) {
                c.drawText(s, x + 12 * d, y - 2 * d + i * 12 * d, halo)
                c.drawText(s, x + 12 * d, y - 2 * d + i * 12 * d, text)
            }
            c.restore()
        }
    }
}
