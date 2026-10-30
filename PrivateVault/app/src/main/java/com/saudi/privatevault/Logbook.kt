package com.saudi.privatevault

import android.content.Context
import android.location.Location
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/** One flight in the pilot's logbook, with the columns the FAA rules count. */
class LogEntry(
    var id: String = UUID.randomUUID().toString(),
    var date: String = today(),
    var aircraft: String = "",
    var from: String = "",
    var to: String = "",
    var route: String = "",
    var total: Double = 0.0,
    var dual: Double = 0.0,
    var solo: Double = 0.0,
    var pic: Double = 0.0,
    var xc: Double = 0.0,
    var night: Double = 0.0,
    var instrument: Double = 0.0,
    var dayLdg: Int = 0,
    var nightLdg: Int = 0,
    var toweredLdg: Int = 0,
    /** The farthest point from the departure, straight line, for the 50 nm cross-country rule. */
    var farthestNm: Double = 0.0,
    /** The whole distance flown, for the 100 and 150 nm cross-countries. */
    var distanceNm: Double = 0.0,
    var remarks: String = "",
) {
    fun toJson(): JSONObject = JSONObject().put("id", id).put("date", date).put("ac", aircraft).put("from", from).put("to", to)
        .put("route", route).put("total", total).put("dual", dual).put("solo", solo).put("pic", pic).put("xc", xc)
        .put("night", night).put("inst", instrument).put("dl", dayLdg).put("nl", nightLdg).put("tl", toweredLdg)
        .put("far", farthestNm).put("dist", distanceNm).put("rem", remarks)

    fun dateMillis(): Long = try { FMT.parse(date)?.time ?: 0L } catch (e: Exception) { 0L }

    companion object {
        val FMT = SimpleDateFormat("yyyy-MM-dd", Locale.US)
        fun today(): String = FMT.format(Date())

        fun fromJson(o: JSONObject) = LogEntry(
            o.optString("id"), o.optString("date"), o.optString("ac"), o.optString("from"), o.optString("to"), o.optString("route"),
            o.optDouble("total", 0.0), o.optDouble("dual", 0.0), o.optDouble("solo", 0.0), o.optDouble("pic", 0.0), o.optDouble("xc", 0.0),
            o.optDouble("night", 0.0), o.optDouble("inst", 0.0), o.optInt("dl"), o.optInt("nl"), o.optInt("tl"),
            o.optDouble("far", 0.0), o.optDouble("dist", 0.0), o.optString("rem"),
        )
    }
}

object Logbook {
    private fun file(ctx: Context) = File(ctx.filesDir, "logbook.json")

    fun all(ctx: Context): MutableList<LogEntry> = try {
        val a = JSONArray(file(ctx).readText())
        (0 until a.length()).map { LogEntry.fromJson(a.getJSONObject(it)) }.sortedByDescending { it.date }.toMutableList()
    } catch (e: Exception) {
        mutableListOf()
    }

    fun save(ctx: Context, list: List<LogEntry>) {
        val tmp = File(file(ctx).path + ".tmp")
        tmp.writeText(JSONArray().apply { for (e in list) put(e.toJson()) }.toString())
        tmp.renameTo(file(ctx))
    }

    fun csv(list: List<LogEntry>): String = buildString {
        append("Date,Aircraft,From,To,Route,Total,Dual,Solo,PIC,XC,Night,Instrument,Day Ldg,Night Ldg,Towered Ldg,Distance nm,Remarks\n")
        for (e in list.sortedBy { it.date }) {
            append(listOf(e.date, e.aircraft, e.from, e.to, e.route, e.total, e.dual, e.solo, e.pic, e.xc, e.night, e.instrument,
                e.dayLdg, e.nightLdg, e.toweredLdg, "%.0f".format(e.distanceNm), e.remarks).joinToString(",") { "\"" + it.toString().replace("\"", "'") + "\"" })
            append('\n')
        }
    }
}

/**
 * Notices a flight from the GPS alone: the takeoff roll past 45 knots, each
 * landing below 30, and the end of the flight after five minutes standing
 * still; then offers it to the logbook with times, airports and distances.
 */
object FlightRecorder {
    private const val KEY = "flight_recorder"

    private class State(
        var started: Long = 0, var airborne: Boolean = false, var fast: Int = 0,
        var dep: String = "", var depLat: Double = 0.0, var depLon: Double = 0.0,
        var landings: Int = 0, var landedAt: Long = 0, var last: String = "", var airMs: Long = 0, var upAt: Long = 0,
        var dist: Double = 0.0, var far: Double = 0.0, var pLat: Double = 0.0, var pLon: Double = 0.0, var stops: String = "",
    ) {
        fun json() = JSONObject().put("s", started).put("a", airborne).put("f", fast).put("d", dep).put("dy", depLat).put("dx", depLon)
            .put("l", landings).put("la", landedAt).put("last", last).put("am", airMs).put("up", upAt).put("dist", dist).put("far", far)
            .put("py", pLat).put("px", pLon).put("stops", stops)
    }

    private var s: State? = null

    private fun state(ctx: Context): State {
        s?.let { return it }
        val o = try { JSONObject(VaultLock.prefs(ctx).getString(KEY, "{}")!!) } catch (e: Exception) { JSONObject() }
        return State(o.optLong("s"), o.optBoolean("a"), o.optInt("f"), o.optString("d"), o.optDouble("dy"), o.optDouble("dx"),
            o.optInt("l"), o.optLong("la"), o.optString("last"), o.optLong("am"), o.optLong("up"), o.optDouble("dist"), o.optDouble("far"),
            o.optDouble("py"), o.optDouble("px"), o.optString("stops")).also { s = it }
    }

    private fun store(ctx: Context, st: State) = VaultLock.prefs(ctx).edit().putString(KEY, st.json().toString()).apply()

    fun inProgress(ctx: Context) = state(ctx).started > 0

    fun summary(ctx: Context): String {
        val st = state(ctx)
        val air = st.airMs + if (st.airborne) System.currentTimeMillis() - st.upAt else 0
        return "${st.dep} → ${if (st.airborne) "✈" else st.last} · ${FlightPlan.hm(air / 60000.0)} · ${st.landings} ldg · %.0f nm".format(st.dist)
    }

    private fun nearest(lat: Double, lon: Double, airports: List<AviationData.Airport>): String {
        val a = airports.minByOrNull { Nav.distanceNm(lat, lon, it.lat, it.lon) }
        return if (a != null && Nav.distanceNm(lat, lon, a.lat, a.lon) < 3) a.icao.ifEmpty { a.ident } else "%.3f,%.3f".format(lat, lon)
    }

    /** Feeds one GPS fix; returns a finished flight when there is one. */
    fun onFix(ctx: Context, l: Location, airports: List<AviationData.Airport>): LogEntry? {
        if (!l.hasSpeed()) return null
        val st = state(ctx)
        val kt = l.speed * 1.943844
        val now = System.currentTimeMillis()
        var changed = false
        if (!st.airborne) {
            st.fast = if (kt > 45) st.fast + 1 else 0
            if (st.fast >= 3) {
                if (st.started == 0L) {
                    st.started = now
                    st.dep = nearest(l.latitude, l.longitude, airports)
                    st.depLat = l.latitude; st.depLon = l.longitude
                    st.pLat = l.latitude; st.pLon = l.longitude
                    st.stops = st.dep
                }
                st.airborne = true
                st.upAt = now
                changed = true
            } else if (st.started > 0 && kt < 3 && st.landedAt > 0 && now - st.landedAt > 5 * 60000) {
                val e = finish(st)
                s = State()
                store(ctx, s!!)
                return e
            }
        } else {
            st.dist += Nav.distanceNm(st.pLat, st.pLon, l.latitude, l.longitude)
            st.far = maxOf(st.far, Nav.distanceNm(st.depLat, st.depLon, l.latitude, l.longitude))
            st.pLat = l.latitude; st.pLon = l.longitude
            if (kt < 30) {
                st.airborne = false
                st.fast = 0
                st.landings++
                st.landedAt = now
                st.airMs += now - st.upAt
                st.last = nearest(l.latitude, l.longitude, airports)
                if (!st.stops.endsWith(st.last)) st.stops += " " + st.last
                changed = true
            }
        }
        if (changed || (st.started > 0 && (now / 1000) % 15 == 0L)) store(ctx, st)
        return null
    }

    /** Ends the flight being recorded now, if it has landed at least once. */
    fun finishNow(ctx: Context): LogEntry? {
        val st = state(ctx)
        if (st.started == 0L) return null
        if (st.airborne) { st.airMs += System.currentTimeMillis() - st.upAt; st.airborne = false }
        val e = finish(st)
        s = State()
        store(ctx, s!!)
        return e
    }

    private fun finish(st: State): LogEntry {
        // Logged time: airborne time plus a few minutes for taxi on each side.
        val hours = Math.round((st.airMs / 3600000.0 + 0.2) * 10) / 10.0
        return LogEntry(
            date = LogEntry.FMT.format(Date(st.started)), from = st.dep, to = st.last.ifEmpty { st.dep }, route = st.stops,
            total = hours, dayLdg = st.landings, farthestNm = Math.round(st.far * 10) / 10.0, distanceNm = Math.round(st.dist).toDouble(),
            xc = if (st.far > 50) hours else 0.0, remarks = "Recorded by GPS",
        )
    }
}
