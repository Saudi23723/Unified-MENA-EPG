package com.saudi.privatevault

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * The wind and the temperature at a height, anywhere on the route.
 *
 * The FAA's FB winds-aloft tables were retired with the NAM model in 2026, and the old call now
 * answers only with an error — which is why the plan's winds had stopped coming. This reads the same
 * thing from the global weather model instead: the wind at the standard pressure levels, taken at
 * the two levels either side of the planned altitude and blended between them. It is kept on the
 * phone for the day, so a flight planned on the ground still has its winds in the air.
 */
object Winds {

    /** The standard atmosphere's height for each pressure level the model publishes, in feet. */
    private val LEVELS = listOf(
        1000 to 364, 975 to 1000, 950 to 1640, 925 to 2500, 900 to 3240,
        850 to 4780, 800 to 6390, 700 to 9880, 600 to 13800, 500 to 18280,
        400 to 23570, 300 to 30070,
    )

    class At(val dirTrue: Int, val kt: Int, val tempC: Int?)

    private val memory = HashMap<String, JSONObject>()

    private fun key(lat: Double, lon: Double) = "%.1f_%.1f".format(lat, lon)

    private fun file(ctx: Context, lat: Double, lon: Double) = File(ctx.filesDir, "aviation/winds/${key(lat, lon)}.json")

    /** The two levels around an altitude, and how far between them it sits. */
    private fun bracket(altFt: Int): Triple<Int, Int, Double> {
        val below = LEVELS.lastOrNull { it.second <= altFt } ?: LEVELS.first()
        val above = LEVELS.firstOrNull { it.second >= altFt } ?: LEVELS.last()
        if (below.first == above.first) return Triple(below.first, above.first, 0.0)
        val f = (altFt - below.second).toDouble() / (above.second - below.second).coerceAtLeast(1)
        return Triple(below.first, above.first, f.coerceIn(0.0, 1.0))
    }

    /**
     * Fetches (or re-reads) the forecast around a point. Call off the main thread. The answer is
     * kept for six hours; an older one is still used when the fetch fails, so planning never stops.
     */
    fun forecast(ctx: Context, lat: Double, lon: Double): JSONObject? {
        val k = key(lat, lon)
        memory[k]?.let { if (System.currentTimeMillis() - it.optLong("got") < 6 * 3600_000L) return it }
        val f = file(ctx, lat, lon)
        val cached = try { JSONObject(f.readText()) } catch (e: Exception) { null }
        if (cached != null && System.currentTimeMillis() - cached.optLong("got") < 6 * 3600_000L) {
            memory[k] = cached; return cached
        }
        val levels = LEVELS.joinToString(",") { l ->
            "wind_speed_${l.first}hPa,wind_direction_${l.first}hPa,temperature_${l.first}hPa"
        }
        val url = "https://api.open-meteo.com/v1/forecast?latitude=%.3f&longitude=%.3f&hourly=$levels".format(lat, lon) +
            "&forecast_days=2&wind_speed_unit=kn&timeformat=unixtime&timezone=UTC"
        return try {
            val o = JSONObject(AviationData.get(url, 25000)).put("got", System.currentTimeMillis())
            f.parentFile?.mkdirs()
            f.writeText(o.toString())
            memory[k] = o
            o
        } catch (e: Exception) {
            cached?.also { memory[k] = it }
        }
    }

    private fun hourIndex(o: JSONObject, whenMs: Long): Int {
        val t = o.optJSONObject("hourly")?.optJSONArray("time") ?: return -1
        val want = whenMs / 1000
        var best = -1; var bestGap = Long.MAX_VALUE
        for (i in 0 until t.length()) {
            // The model answers in seconds since the epoch, or in text when asked that way.
            val v = t.opt(i)
            val sec = when (v) {
                is Number -> v.toLong()
                is String -> try { java.time.Instant.parse(if (v.endsWith("Z")) v else v + ":00Z").epochSecond } catch (e: Exception) { continue }
                else -> continue
            }
            val gap = Math.abs(sec - want)
            if (gap < bestGap) { bestGap = gap; best = i }
        }
        return best
    }

    private fun value(o: JSONObject, name: String, i: Int): Double? {
        val a = o.optJSONObject("hourly")?.optJSONArray(name) ?: return null
        if (i < 0 || i >= a.length() || a.isNull(i)) return null
        return a.optDouble(i).takeIf { !it.isNaN() }
    }

    /** The wind at a point and a height, at a time (now by default). Null when nothing could be read. */
    fun at(ctx: Context, lat: Double, lon: Double, altFt: Int, whenMs: Long = System.currentTimeMillis()): At? {
        val o = forecast(ctx, lat, lon) ?: return null
        val i = hourIndex(o, whenMs)
        if (i < 0) return null
        val (lo, hi, f) = bracket(altFt)
        fun read(level: Int): Triple<Double, Double, Double?>? {
            val d = value(o, "wind_direction_${level}hPa", i) ?: return null
            val s = value(o, "wind_speed_${level}hPa", i) ?: return null
            return Triple(d, s, value(o, "temperature_${level}hPa", i))
        }
        val a = read(lo) ?: read(hi) ?: return null
        val b = read(hi) ?: a
        // Directions are blended the short way round the compass, never through the long side.
        val turn = ((b.first - a.first + 540) % 360) - 180
        val dir = ((a.first + turn * f) % 360 + 360) % 360
        val kt = a.second + (b.second - a.second) * f
        val temp = if (a.third != null && b.third != null) a.third!! + (b.third!! - a.third!!) * f else a.third
        return At(Math.round(dir).toInt() % 360, Math.round(kt).toInt(), temp?.let { Math.round(it).toInt() })
    }

    /** The same, shaped the way the flight plan keeps a leg's wind: from, knots, temperature. */
    fun triple(ctx: Context, lat: Double, lon: Double, altFt: Int, whenMs: Long = System.currentTimeMillis()): Triple<Int, Int, Int?>? =
        at(ctx, lat, lon, altFt, whenMs)?.let { Triple(it.dirTrue, it.kt, it.tempC) }
}
