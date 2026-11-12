package com.saudi.privatevault

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.ZipInputStream

/**
 * The FAA's Coded Instrument Flight Procedures (CIFP, ARINC 424): the same coded database the
 * panel's GPS navigator flies, free from the FAA every 28 days. From it, every instrument approach
 * of the airports in the West: its transitions, every fix with its exact position, its role (IAF,
 * IF, FAF, step-down, missed-approach point), the leg's type, course and distance, the altitude
 * constraints, and the missed approach with its hold.
 *
 * The file (9 MB zipped, 53 MB of text) is read once per cycle on the phone and kept as one small
 * file per airport.
 */
object Cifp {
    class Leg(
        val fix: String, val lat: Double?, val lon: Double?, val role: String, val path: String,
        val course: Double?, val dist: Double?, val altDesc: Char, val alt1: Int?, val alt2: Int?, val turn: Char, val missed: Boolean,
    ) {
        /** The altitude constraint as charted: 3,500 (at), 3,500+ (at or above), 3,500- (at or below), between. */
        fun altText(): String {
            val a = alt1 ?: return ""
            val s = "%,d".format(a)
            return when (altDesc) {
                '+' -> "$s+"
                '-' -> "$s−"
                'B' -> alt2?.let { "%,d–$s".format(it) } ?: s
                'G', 'V' -> s
                else -> s
            }
        }
        fun roleText() = when (role) { "A" -> "IAF"; "I" -> "IF"; "F" -> "FAF"; "M" -> "MAP"; "S" -> "Step-down"; else -> "" }
    }

    class Procedure(val icao: String, val id: String, val name: String, val transitions: Map<String, List<Leg>>, val final: List<Leg>) {
        /** The final approach course: the leg into the missed-approach point. */
        fun finalCourse(): Double? = final.firstOrNull { it.role == "M" }?.course ?: final.lastOrNull { !it.missed && it.course != null }?.course
        fun legs(transition: String?): List<Leg> = (transition?.let { transitions[it] } ?: emptyList()).let { t ->
            // The transition ends at the fix where the final segment begins: no duplicate.
            if (t.isNotEmpty() && final.isNotEmpty() && t.last().fix == final.first().fix) t.dropLast(1) + final else t + final
        }
    }

    // The West: the Pacific to the Rockies (the charts the app carries).
    private const val S = 30.5; private const val N = 49.5; private const val W = -125.5; private const val E = -102.0

    private fun cycleStart(): java.time.LocalDate {
        // The AIRAC cycles run 28 days from a known start (29 Oct 2026).
        val anchor = java.time.LocalDate.of(2026, 10, 29)
        val today = java.time.LocalDate.now()
        val k = Math.floorDiv(java.time.temporal.ChronoUnit.DAYS.between(anchor, today), 28L)
        return anchor.plusDays(k * 28)
    }

    private fun dir(ctx: Context): File {
        val d = cycleStart()
        return File(ctx.filesDir, "cifp/%02d%02d%02d".format(d.year % 100, d.monthValue, d.dayOfMonth))
    }

    fun ready(ctx: Context) = File(dir(ctx), "done").exists()

    /** Downloads and reads this cycle's CIFP (call off the main thread); [progress] gets 0..100. */
    fun ensure(ctx: Context, progress: (Int) -> Unit = {}): Boolean {
        val out = dir(ctx)
        if (File(out, "done").exists()) return true
        out.mkdirs()
        // Earlier cycles away.
        out.parentFile?.listFiles()?.filter { it != out }?.forEach { it.deleteRecursively() }
        val start = cycleStart()
        val names = listOf(start, start.minusDays(28)).map { "CIFP_%02d%02d%02d.zip".format(it.year % 100, it.monthValue, it.dayOfMonth) }
        for (n in names) {
            try {
                val c = URL("https://aeronav.faa.gov/Upload_313-d/cifp/$n").openConnection() as HttpURLConnection
                c.connectTimeout = 20000; c.readTimeout = 60000
                c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) PilotCompanion")
                if (c.responseCode != 200) { c.disconnect(); continue }
                val total = c.contentLengthLong
                val counted = object : java.io.FilterInputStream(c.inputStream) {
                    var read = 0L
                    override fun read(b: ByteArray, off: Int, len: Int): Int {
                        val k = super.read(b, off, len)
                        if (k > 0) { read += k; if (total > 0) progress((read * 100 / total).toInt()) }
                        return k
                    }
                }
                ZipInputStream(counted).use { z ->
                    var e = z.nextEntry
                    while (e != null && e.name != "FAACIFP18") e = z.nextEntry
                    if (e != null) parse(z.bufferedReader(Charsets.ISO_8859_1), out)
                }
                c.disconnect()
                if (out.listFiles()?.any { it.name.endsWith(".json") } == true) {
                    File(out, "done").writeText(n)
                    return true
                }
            } catch (e: Exception) { }
        }
        return false
    }

    private val LATLON = Regex("([NS])(\\d{2})(\\d{2})(\\d{4})([EW])(\\d{3})(\\d{2})(\\d{4})")

    private fun latlon(line: String): DoubleArray? {
        val m = LATLON.find(line, 30) ?: return null
        val g = m.groupValues
        val lat = (g[2].toInt() + g[3].toInt() / 60.0 + g[4].toInt() / 360000.0) * if (g[1] == "S") -1 else 1
        val lon = (g[6].toInt() + g[7].toInt() / 60.0 + g[8].toInt() / 360000.0) * if (g[5] == "W") -1 else 1
        return doubleArrayOf(lat, lon)
    }

    private fun col(l: String, from: Int, to: Int) = if (l.length >= to) l.substring(from - 1, to) else ""

    /** One pass: navaids and enroute waypoints first (they come first in the file), then airport by airport. */
    private fun parse(r: java.io.BufferedReader, out: File) {
        val global = HashMap<String, DoubleArray>()      // ident|region → position (EA, D, DB)
        var apt = ""
        val local = HashMap<String, DoubleArray>()       // terminal waypoints, runways, terminal NDBs
        val legs = ArrayList<String>()
        var ref: DoubleArray? = null
        var name = ""

        fun flush() {
            if (apt.isEmpty() || legs.isEmpty()) return
            val p = ref ?: return
            if (p[0] !in S..N || p[1] !in W..E) return
            write(out, apt, name, p, local, global, legs)
        }

        while (true) {
            val l = r.readLine() ?: break
            if (l.length < 40 || !l.startsWith("SUSA")) continue
            val sec = l[4]
            if (sec == 'D') {            // VHF (D ) and NDB (DB) navaids
                val id = col(l, 14, 17).trim(); val reg = col(l, 20, 21)
                latlon(l)?.let { global["$id|$reg"] = it }
                continue
            }
            if (sec == 'E' && l[5] == 'A') {
                val id = col(l, 14, 18).trim(); val reg = col(l, 20, 21)
                latlon(l)?.let { global["$id|$reg"] = it }
                continue
            }
            if (sec != 'P') continue
            val a = col(l, 7, 10).trim()
            if (a != apt) { flush(); apt = a; local.clear(); legs.clear(); ref = null; name = "" }
            when (l[12]) {
                'A' -> { ref = latlon(l); name = col(l, 94, 123).trim() }
                'C', 'N' -> { if (l[38 - 1 + 0] == '0' || true) latlon(l)?.let { local[col(l, 14, 18).trim()] = it } }
                'G' -> latlon(l)?.let { local[col(l, 14, 18).trim()] = it }
                'F' -> if (l[38] == '0' || l[38] == '1') legs.add(l)   // primary records (continuation 0/1) only
            }
        }
        flush()
    }

    private fun write(out: File, apt: String, name: String, ref: DoubleArray, local: Map<String, DoubleArray>, global: Map<String, DoubleArray>, lines: List<String>) {
        val procs = LinkedHashMap<String, JSONObject>()
        for (l in lines) {
            val id = col(l, 14, 19).trim()
            val route = l[19]
            val trans = col(l, 21, 25).trim()
            val fix = col(l, 30, 34).trim()
            val reg = col(l, 35, 36)
            val section = col(l, 37, 38)
            val desc = col(l, 40, 43)
            val path = col(l, 48, 49)
            val course = col(l, 71, 74).trim().toIntOrNull()?.let { it / 10.0 }
            val dist = col(l, 75, 78).trim().toIntOrNull()?.let { it / 10.0 }
            val altDesc = col(l, 83, 83).firstOrNull() ?: ' '
            val alt1 = col(l, 85, 89).trim().let { if (it.startsWith("FL")) it.drop(2).toIntOrNull()?.times(100) else it.toIntOrNull() }
            val alt2 = col(l, 90, 94).trim().let { if (it.startsWith("FL")) it.drop(2).toIntOrNull()?.times(100) else it.toIntOrNull() }
            val pos = if (fix.isEmpty()) null else when (section) {
                "PC", "PG", "PN", "PI" -> local[fix] ?: global["$fix|$reg"]
                else -> global["$fix|$reg"] ?: local[fix]
            }
            val role = when (desc.getOrNull(3)) { 'A' -> "A"; 'I' -> "I"; 'F' -> "F"; 'M' -> "M"; else -> if (desc.getOrNull(2) == 'S') "S" else "" }
            val p = procs.getOrPut(id) { JSONObject().put("id", id).put("t", JSONObject()) }
            // Final approach routes carry no transition name; approach transitions do (route type A).
            val key = if (route == 'A') trans else ""
            val arr = p.getJSONObject("t").optJSONArray(key) ?: JSONArray().also { p.getJSONObject("t").put(key, it) }
            arr.put(JSONArray().apply {
                put(fix); put(pos?.get(0) ?: JSONObject.NULL); put(pos?.get(1) ?: JSONObject.NULL); put(role); put(path)
                put(course ?: JSONObject.NULL); put(dist ?: JSONObject.NULL); put(altDesc.toString()); put(alt1 ?: JSONObject.NULL); put(alt2 ?: JSONObject.NULL)
                put(col(l, 44, 44))
            })
        }
        val o = JSONObject().put("icao", apt).put("name", name).put("lat", ref[0]).put("lon", ref[1])
        o.put("p", JSONArray(procs.values.toList()))
        val rw = JSONObject()
        for ((k, v) in local) if (k.startsWith("RW")) rw.put(k, JSONArray().put(v[0]).put(v[1]))
        o.put("rw", rw)
        File(out, "$apt.json").writeText(o.toString())
    }

    /** Every fix and runway threshold the airport's procedures use, by name: for placing its plates. */
    fun fixesFor(ctx: Context, icao: String): Map<String, DoubleArray> {
        val code = icao.uppercase().let { if (it.length == 3) "K$it" else it }
        val out = HashMap<String, DoubleArray>()
        try {
            val o = JSONObject(File(dir(ctx), "$code.json").readText())
            val ps = o.getJSONArray("p")
            for (i in 0 until ps.length()) {
                val t = ps.getJSONObject(i).getJSONObject("t")
                for (k in t.keys()) {
                    val a = t.getJSONArray(k)
                    for (j in 0 until a.length()) {
                        val x = a.getJSONArray(j)
                        val lat = x.opt(1)?.toString()?.toDoubleOrNull(); val lon = x.opt(2)?.toString()?.toDoubleOrNull()
                        if (lat != null && lon != null && x.optString(0).isNotEmpty()) out[x.optString(0)] = doubleArrayOf(lat, lon)
                    }
                }
            }
            val rw = o.getJSONObject("rw")
            for (k in rw.keys()) rw.getJSONArray(k).let { out[k] = doubleArrayOf(it.getDouble(0), it.getDouble(1)) }
        } catch (e: Exception) { }
        return out
    }

    /** A procedure's readable name from its code: R27 → RNAV (GPS) RWY 27, I12L → ILS RWY 12L, R08-Y → RNAV (GPS) Y RWY 08, RNV-B → RNAV (GPS)-B… */
    fun nameOf(id: String): String {
        // Circling procedures by their letter: RNV-B, VOR-C, VDM-A, NDB-A.
        Regex("^(RNV|VOR|VDM|NDB|LOC|LDA|GPS|TCN)-([A-Z])$").find(id)?.let { m ->
            val k = when (m.groupValues[1]) { "RNV" -> "RNAV (GPS)"; "VDM" -> "VOR/DME"; "TCN" -> "TACAN"; else -> m.groupValues[1] }
            return "$k-${m.groupValues[2]}"
        }
        val kind = when (id.firstOrNull()) {
            'R' -> "RNAV (GPS)"; 'H' -> "RNAV (RNP)"; 'I' -> "ILS"; 'L' -> "LOC"; 'B' -> "LOC/BC"; 'V' -> "VOR"; 'D' -> "VOR/DME"
            'N' -> "NDB"; 'Q' -> "NDB/DME"; 'S' -> "VOR"; 'P' -> "GPS"; 'X' -> "LDA"; 'U' -> "SDF"; 'G' -> "IGS"; 'J' -> "GLS"; else -> id.take(1)
        }
        // R08-Y: the runway padded to its letter.
        val rest = id.drop(1).let { r -> if (r.matches(Regex("^\\d{2}-[A-Z]$"))) r.replace("-", "") else r }
        if (rest.startsWith("-")) return "$kind-${rest.drop(1)}"          // circling: VOR-A, RNAV (GPS)-B
        val m = Regex("^(\\d{2}[LRC]?)([A-Z]?)$").find(rest)
        return if (m != null) "$kind${m.groupValues[2].takeIf { it.isNotEmpty() }?.let { " $it" } ?: ""} RWY ${m.groupValues[1]}" else "$kind $rest"
    }

    /** The approaches of an airport, read from this cycle's file; null when the data is not on the phone. */
    fun approaches(ctx: Context, icao: String): List<Procedure>? {
        val f = File(dir(ctx), "${icao.uppercase()}.json")
        if (!ready(ctx)) return null
        if (!f.exists()) return emptyList()
        val o = try { JSONObject(f.readText()) } catch (e: Exception) { return emptyList() }
        val out = ArrayList<Procedure>()
        val ps = o.optJSONArray("p") ?: return emptyList()
        for (i in 0 until ps.length()) {
            val p = ps.getJSONObject(i)
            val t = p.getJSONObject("t")
            fun legs(a: JSONArray): List<Leg> {
                val list = ArrayList<Leg>()
                var missed = false
                for (k in 0 until a.length()) {
                    val x = a.getJSONArray(k)
                    val role = x.optString(3)
                    val leg = Leg(x.optString(0), x.opt(1).takeIf { it != JSONObject.NULL }?.toString()?.toDoubleOrNull(),
                        x.opt(2).takeIf { it != JSONObject.NULL }?.toString()?.toDoubleOrNull(), role, x.optString(4),
                        x.opt(5).takeIf { it != JSONObject.NULL }?.toString()?.toDoubleOrNull(), x.opt(6).takeIf { it != JSONObject.NULL }?.toString()?.toDoubleOrNull(),
                        x.optString(7).firstOrNull() ?: ' ', x.opt(8).takeIf { it != JSONObject.NULL }?.toString()?.toIntOrNull(),
                        x.opt(9).takeIf { it != JSONObject.NULL }?.toString()?.toIntOrNull(), x.optString(10).firstOrNull() ?: ' ', missed)
                    list.add(leg)
                    // Everything after the missed-approach point is the missed approach.
                    if (role == "M") missed = true
                }
                return list
            }
            val trans = LinkedHashMap<String, List<Leg>>()
            var fin: List<Leg> = emptyList()
            for (k in t.keys()) { val l = legs(t.getJSONArray(k)); if (k.isEmpty()) fin = l else trans[k] = l }
            val id = p.getString("id")
            out.add(Procedure(icao.uppercase(), id, nameOf(id), trans, fin))
        }
        return out.sortedBy { it.name }
    }

    /** A runway threshold (RW27 → lat, lon). */
    fun runway(ctx: Context, icao: String, rw: String): DoubleArray? = try {
        JSONObject(File(dir(ctx), "${icao.uppercase()}.json").readText()).getJSONObject("rw").optJSONArray(rw)?.let { doubleArrayOf(it.getDouble(0), it.getDouble(1)) }
    } catch (e: Exception) { null }
}
