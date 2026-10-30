package com.saudi.privatevault

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Radio frequencies of US airports: the FAA's own list for an airport
 * (aviationweather.gov, kept with the airport's info for offline use), and,
 * for every airport at once and with no signal, the OurAirports list shipped
 * in the app (assets/frequencies_us.json), which also gives the Center and
 * FSS frequencies heard near each field.
 */
object Frequencies {
    enum class Kind(val label: String) {
        ATIS("ATIS"), WX("AWOS / ASOS"), CLR("Clearance"), GND("Ground"), TWR("Tower"), CTAF("CTAF"),
        UNICOM("UNICOM"), APP("Approach / Departure"), CENTER("Center"), FSS("FSS / Radio"), OTHER("Other"),
    }

    class Freq(val kind: Kind, val name: String, val mhz: Double, val official: Boolean)

    fun mhz(v: Double): String = "%.3f".format(java.util.Locale.US, v).trimEnd('0').let { if (it.endsWith('.')) it + "0" else it }

    fun kindOf(type: String, desc: String = ""): Kind {
        val t = type.uppercase()
        val d = desc.uppercase()
        return when {
            "ATIS" in t -> Kind.ATIS
            "AWOS" in t || "ASOS" in t || "AWOS" in d || "ASOS" in d -> Kind.WX
            t.startsWith("CD") || t.startsWith("CLD") || "CLNC" in d || "CLEARANCE" in d || "GCO" in t -> Kind.CLR
            t.startsWith("GND") || "GROUND" in d -> Kind.GND
            t.startsWith("LCL") || t.startsWith("TWR") || "TOWER" in d -> Kind.TWR
            "CTAF" in t -> Kind.CTAF
            t.startsWith("UNIC") -> if ("CTAF" in d) Kind.CTAF else Kind.UNICOM
            t.startsWith("APCH") || t.startsWith("APP") || t.startsWith("DEP") || t.startsWith("A/D") || t.startsWith("ARR") || "APP" in d || "DEP" in d -> Kind.APP
            t.startsWith("CNTR") || t.startsWith("CTR") || t.startsWith("ARTC") || "CENTER" in d || "CTR" in d -> Kind.CENTER
            t.startsWith("RDO") || t.startsWith("FSS") || t.startsWith("RCO") || "RADIO" in d || " RDO" in d -> Kind.FSS
            else -> Kind.OTHER
        }
    }

    private fun parseMhz(s: String): Double? = s.trim().toDoubleOrNull()?.takeIf { it in 108.0..137.0 }

    /** The FAA's list from an airport's aviationweather.gov record, whichever shape it comes in. */
    fun official(apt: JSONObject?): List<Freq> {
        val out = ArrayList<Freq>()
        when (val f = apt?.opt("freqs")) {
            is JSONArray -> for (i in 0 until f.length()) {
                val o = f.optJSONObject(i) ?: continue
                val m = parseMhz(o.optString("freq")) ?: continue
                val type = o.optString("type")
                out.add(Freq(kindOf(type), type, m, true))
            }
            is String -> for (part in f.split(';')) {
                val bits = part.split(',').map { it.trim() }
                val m = bits.firstNotNullOfOrNull { parseMhz(it) } ?: continue
                val type = bits.filter { parseMhz(it) == null }.joinToString(" ")
                out.add(Freq(kindOf(type), type, m, true))
            }
        }
        return out
    }

    @Volatile private var shipped: JSONObject? = null

    private fun shipped(ctx: Context): JSONObject = shipped ?: try {
        JSONObject(ctx.assets.open("frequencies_us.json").bufferedReader().readText()).getJSONObject("apt")
    } catch (e: Exception) {
        JSONObject()
    }.also { shipped = it }

    /** The shipped list of one airport, by its FAA identifier (BVU) or ICAO code (KBVU). */
    fun shipped(ctx: Context, a: AviationData.Airport): List<Freq> {
        val all = shipped(ctx)
        val arr = all.optJSONArray(a.ident) ?: all.optJSONArray(a.icao) ?: return emptyList()
        return (0 until arr.length()).mapNotNull { i ->
            val r = arr.optJSONArray(i) ?: return@mapNotNull null
            val type = r.optString(0)
            val desc = r.optString(1)
            Freq(kindOf(type, desc), desc.ifEmpty { type }, r.optDouble(2), false)
        }
    }

    /** One list for an airport: the FAA's first, then whatever only the shipped list has, in radio-call order. */
    fun merge(official: List<Freq>, shipped: List<Freq>): List<Freq> {
        val out = ArrayList(official)
        for (s in shipped) if (out.none { Math.abs(it.mhz - s.mhz) < 0.001 && (it.kind == s.kind || s.kind == Kind.OTHER || s.kind == Kind.UNICOM) }) out.add(s)
        return out.distinctBy { it.kind to Math.round(it.mhz * 1000) }.sortedWith(compareBy({ it.kind.ordinal }, { it.mhz }))
    }

    fun forAirport(ctx: Context, a: AviationData.Airport, apt: JSONObject?) = merge(official(apt), shipped(ctx, a))

    /** Standard frequencies and codes every VFR pilot in the US uses. */
    val STANDARD = listOf(
        "121.5" to "Emergency (Guard)",
        "122.75" to "Air-to-air (fixed wing)",
        "122.9" to "MULTICOM (no tower, no UNICOM)",
        "122.2" to "FSS (common)",
    )
    val SQUAWKS = listOf("1200" to "VFR", "7700" to "Emergency", "7600" to "Lost comms", "7500" to "Hijack")
    const val FSS_PHONE = "1-800-992-7433"
}
