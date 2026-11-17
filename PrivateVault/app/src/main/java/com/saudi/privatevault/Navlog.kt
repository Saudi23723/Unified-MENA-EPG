package com.saudi.privatevault

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/**
 * The aeroplane's numbers, by the phase of flight: what it does in the climb, in the cruise and on
 * the way down. Taken from the POH (or the school's board) and typed in once; every leg of the log
 * is worked out from them, as ForeFlight's performance profiles and Jeppesen's do.
 */
class AircraftProfile(
    var name: String = "Default",
    var climbTas: Double = 65.0, var climbFpm: Double = 500.0, var climbGph: Double = 6.6,
    var cruiseTas: Double = 85.0, var cruiseGph: Double = 5.4,
    var descentTas: Double = 85.0, var descentFpm: Double = 500.0, var descentGph: Double = 5.4,
    var taxiGal: Double = 1.0,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("n", name).put("ct", climbTas).put("cr", climbFpm).put("cg", climbGph)
        .put("zt", cruiseTas).put("zg", cruiseGph)
        .put("dt", descentTas).put("dr", descentFpm).put("dg", descentGph).put("tx", taxiGal)

    companion object {
        fun fromJson(o: JSONObject) = AircraftProfile(
            o.optString("n", "Default"), o.optDouble("ct", 65.0), o.optDouble("cr", 500.0), o.optDouble("cg", 6.6),
            o.optDouble("zt", 85.0), o.optDouble("zg", 5.4),
            o.optDouble("dt", 85.0), o.optDouble("dr", 500.0), o.optDouble("dg", 5.4), o.optDouble("tx", 1.0),
        )

        /** The school's SportStar numbers, the ones already on the pattern card. */
        fun sportStar() = AircraftProfile("SportStar 5000 RPM", 65.0, 500.0, 6.6, 85.0, 5.4, 85.0, 500.0, 5.4, 1.0)

        fun all(ctx: Context): MutableList<AircraftProfile> {
            val s = VaultLock.prefs(ctx).getString("perf_profiles", "") ?: ""
            val out = ArrayList<AircraftProfile>()
            try {
                val a = JSONArray(s)
                for (i in 0 until a.length()) out.add(fromJson(a.getJSONObject(i)))
            } catch (e: Exception) { }
            if (out.isEmpty()) out.add(sportStar())
            return out
        }

        fun saveAll(ctx: Context, list: List<AircraftProfile>) = VaultLock.prefs(ctx).edit()
            .putString("perf_profiles", JSONArray().apply { for (p in list) put(p.toJson()) }.toString()).apply()

        /** The profile in use, by name; the first one when none was chosen. */
        fun current(ctx: Context): AircraftProfile {
            val list = all(ctx)
            val want = VaultLock.prefs(ctx).getString("perf_profile", "") ?: ""
            return list.firstOrNull { it.name == want } ?: list.first()
        }

        fun use(ctx: Context, name: String) = VaultLock.prefs(ctx).edit().putString("perf_profile", name).apply()
    }
}

/** Where in the flight a leg lies: climbing to the cruise, in the cruise, or coming down. */
enum class Phase { CLIMB, CRUISE, DESCENT }

/**
 * The navigation log as a navigator keeps it: the route broken at the top of the climb and the top
 * of the descent, each leg with its true course, the wind's correction, the magnetic heading to fly,
 * the ground speed, the time and the fuel — and, against the ground below it, the lowest safe altitude.
 */
object Navlog {

    class Row(
        val index: Int,
        val from: FlightPlan.Waypoint, val to: FlightPlan.Waypoint,
        val phase: Phase, val altFt: Int, val moraFt: Int?,
        val tc: Double, val wca: Double, val th: Double, val variation: Double, val mh: Double,
        val windDir: Int, val windKt: Int, val tas: Double, val gs: Double,
        val distNm: Double, val remainNm: Double,
        val minutes: Double, val cumMinutes: Double,
        val fuelGal: Double, val fuelLeftGal: Double,
        /** A leg the route does not hold as a point: the top of the climb or of the descent. */
        val virtual: Boolean,
    ) {
        var atoUtc: String? = null
    }

    class Result(
        val rows: List<Row>, val distNm: Double, val minutes: Double, val fuelGal: Double,
        val fuelLeftGal: Double, val reserveGal: Double, val reserveKept: Boolean,
        val tocNm: Double, val todNm: Double, val warnings: List<String>,
    )

    /** The ground's highest point within about 4 nm of a line, rounded up with 1,000 ft to spare. */
    fun mora(aLat: Double, aLon: Double, bLat: Double, bLon: Double): Int? {
        val d = Nav.distanceNm(aLat, aLon, bLat, bLon)
        val steps = (d / 2.0).toInt().coerceIn(1, 24)
        var high = -1.0
        var any = false
        val brg = Nav.bearingTrue(aLat, aLon, bLat, bLon)
        for (k in 0..steps) {
            val f = k.toDouble() / steps
            val lat = aLat + (bLat - aLat) * f
            val lon = aLon + (bLon - aLon) * f
            // On the line, and 4 nm either side of it: the corridor a navigator clears.
            for (off in listOf(0.0, 4.0, -4.0)) {
                val p = if (off == 0.0) doubleArrayOf(lat, lon) else
                    Nav.destination(lat, lon, (brg + if (off > 0) 90.0 else 270.0) % 360, abs(off)).let { doubleArrayOf(it.latitude, it.longitude) }
                val e = Terrain.elevationFt(p[0], p[1]) ?: continue
                any = true
                if (e > high) high = e.toDouble()
            }
        }
        if (!any) return null
        return (Math.ceil((high + 1000) / 100.0) * 100).toInt()
    }

    /**
     * The whole log. The climb and the descent are cut into the route where they really end, so the
     * leg that holds the top of the climb becomes two: one climbing, one in the cruise.
     */
    fun build(
        points: List<FlightPlan.Waypoint>, cruiseAltFt: Int, profile: AircraftProfile,
        windFor: (index: Int) -> Pair<Int, Int>, fuelOnBoard: Double, reserveMin: Int,
        depElevFt: Double?, destElevFt: Double?, withMora: Boolean,
    ): Result {
        val warn = ArrayList<String>()
        if (points.size < 2) return Result(emptyList(), 0.0, 0.0, 0.0, fuelOnBoard, 0.0, true, 0.0, 0.0, warn)

        val depElev = depElevFt ?: Terrain.elevationFt(points.first().lat, points.first().lon)?.toDouble() ?: 0.0
        val destElev = destElevFt ?: Terrain.elevationFt(points.last().lat, points.last().lon)?.toDouble() ?: 0.0

        // How far the climb and the descent reach, in still air at the profile's speeds.
        val climbMin = max(0.0, (cruiseAltFt - depElev) / max(100.0, profile.climbFpm))
        val tocNm = profile.climbTas * climbMin / 60.0
        val descMin = max(0.0, (cruiseAltFt - (destElev + 1000.0)) / max(100.0, profile.descentFpm))
        val todNm = profile.descentTas * descMin / 60.0

        // The route's own points, with the distance of each from the start.
        val legDist = ArrayList<Double>()
        var total = 0.0
        for (i in 0 until points.size - 1) {
            val d = Nav.distanceNm(points[i].lat, points[i].lon, points[i + 1].lat, points[i + 1].lon)
            legDist.add(d); total += d
        }
        if (tocNm + todNm > total && total > 0) warn.add("The route is shorter than the climb and the descent together: the cruise never happens.")

        // Cut points: the top of the climb and the top of the descent, placed along the line.
        class Cut(val at: Double, val id: String)
        val cuts = ArrayList<Cut>()
        if (tocNm > 0.2 && tocNm < total - 0.2) cuts.add(Cut(tocNm, "TOC"))
        if (todNm > 0.2 && total - todNm > 0.2 && total - todNm > tocNm + 0.2) cuts.add(Cut(total - todNm, "TOD"))

        // Walk the route, breaking a leg where a cut falls inside it.
        class Seg(val a: FlightPlan.Waypoint, val b: FlightPlan.Waypoint, val srcLeg: Int, val startAt: Double, val virtual: Boolean)
        val segs = ArrayList<Seg>()
        var walked = 0.0
        for (i in 0 until points.size - 1) {
            var a = points[i]
            val b = points[i + 1]
            val legLen = legDist[i]
            val inside = cuts.filter { it.at > walked + 0.05 && it.at < walked + legLen - 0.05 }.sortedBy { it.at }
            var fromAt = walked
            for (c in inside) {
                val along = c.at - walked
                val brg = Nav.bearingTrue(a.lat, a.lon, b.lat, b.lon)
                val g = Nav.destination(a.lat, a.lon, brg, along - (fromAt - walked))
                val cut = FlightPlan.Waypoint(c.id, g.latitude, g.longitude)
                segs.add(Seg(a, cut, i, fromAt, true))
                a = cut; fromAt = c.at
            }
            segs.add(Seg(a, b, i, fromAt, false))
            walked += legLen
        }

        val rows = ArrayList<Row>()
        var cum = 0.0
        var cumMin = 0.0
        var fuel = (fuelOnBoard - profile.taxiGal).coerceAtLeast(0.0)
        var runDist = 0.0
        for ((n, s) in segs.withIndex()) {
            val d = Nav.distanceNm(s.a.lat, s.a.lon, s.b.lat, s.b.lon)
            val mid = runDist + d / 2
            val phase = when {
                mid <= tocNm + 0.01 && tocNm > 0.05 -> Phase.CLIMB
                mid >= total - todNm - 0.01 && todNm > 0.05 -> Phase.DESCENT
                else -> Phase.CRUISE
            }
            val tas = when (phase) { Phase.CLIMB -> profile.climbTas; Phase.DESCENT -> profile.descentTas; else -> profile.cruiseTas }
            val gph = when (phase) { Phase.CLIMB -> profile.climbGph; Phase.DESCENT -> profile.descentGph; else -> profile.cruiseGph }
            val alt = when (phase) {
                Phase.CLIMB -> ((depElev + cruiseAltFt) / 2).toInt()
                Phase.DESCENT -> ((destElev + 1000 + cruiseAltFt) / 2).toInt()
                else -> cruiseAltFt
            }
            val (wd, wk) = windFor(s.srcLeg)
            val tc = Nav.bearingTrue(s.a.lat, s.a.lon, s.b.lat, s.b.lon)
            // The wind triangle: the angle to hold the line, and what is left over the ground.
            val rel = Math.toRadians(wd - tc)
            val sinW = ((wk * sin(rel)) / max(20.0, tas)).coerceIn(-1.0, 1.0)
            val wca = Math.toDegrees(asin(sinW))
            val th = (tc + wca + 360) % 360
            val mLat = (s.a.lat + s.b.lat) / 2; val mLon = (s.a.lon + s.b.lon) / 2
            val variation = Nav.variation(mLat, mLon)
            val mh = Nav.magnetic(th, mLat, mLon)
            val gs = max(20.0, tas * cos(Math.toRadians(wca)) - wk * cos(rel))
            val min = d / gs * 60
            val burn = min / 60 * gph
            cum += d; cumMin += min; fuel -= burn; runDist += d
            val moraFt = if (withMora) mora(s.a.lat, s.a.lon, s.b.lat, s.b.lon) else null
            rows.add(Row(n, s.a, s.b, phase, alt, moraFt, tc, wca, th, variation, mh, wd, wk, tas, gs,
                d, (total - cum).coerceAtLeast(0.0), min, cumMin, burn, fuel, s.virtual))
        }
        val reserve = when { rows.isEmpty() -> 0.0; else -> profile.cruiseGph * reserveMin / 60.0 }
        val left = fuel
        val burned = fuelOnBoard - left
        for (r in rows) if (r.moraFt != null && r.altFt < r.moraFt) warn.add("${r.from.id} → ${r.to.id}: ${"%,d".format(r.altFt)}' is below the ${"%,d".format(r.moraFt)}' lowest safe altitude.")
        if (left < reserve) warn.add("Only %.1f gal would be left: less than the %d minute reserve (%.1f gal).".format(left, reserveMin, reserve))
        return Result(rows, total, cumMin, burned, left, reserve, left >= reserve - 1e-9, tocNm, todNm, warn)
    }

    class AltitudeOption(val altFt: Int, val minutes: Double, val fuelGal: Double, val avgGs: Int, val wind: String) {
        var fastest = false
        var leanest = false
    }

    /**
     * Every cruising altitude the rules allow for this direction, flown through on paper with the
     * forecast wind at each: the quickest and the one that burns least are marked.
     */
    fun altitudes(
        points: List<FlightPlan.Waypoint>, profile: AircraftProfile, fuelOnBoard: Double, reserveMin: Int,
        ifr: Boolean, windAt: (altFt: Int) -> Pair<Int, Int>?, depElevFt: Double?, destElevFt: Double?,
    ): List<AltitudeOption> {
        if (points.size < 2) return emptyList()
        val tc = Nav.bearingTrue(points.first().lat, points.first().lon, points.last().lat, points.last().lon)
        val mc = Nav.magnetic(tc, points.first().lat, points.first().lon)
        val east = mc < 180
        // 91.159 for VFR (odd or even thousands plus 500), 91.179 for IFR.
        val list = if (ifr) (if (east) listOf(3000, 5000, 7000, 9000, 11000) else listOf(4000, 6000, 8000, 10000, 12000))
        else (if (east) listOf(3500, 5500, 7500, 9500, 11500) else listOf(4500, 6500, 8500, 10500, 12500))
        val out = ArrayList<AltitudeOption>()
        for (alt in list) {
            val w = windAt(alt) ?: Pair(0, 0)
            val r = build(points, alt, profile, { w }, fuelOnBoard, reserveMin, depElevFt, destElevFt, withMora = false)
            if (r.rows.isEmpty()) continue
            val gs = if (r.minutes > 0) (r.distNm / r.minutes * 60).toInt() else 0
            out.add(AltitudeOption(alt, r.minutes, r.fuelGal, gs, "%03d/%d".format(w.first, w.second)))
        }
        out.minByOrNull { it.minutes }?.fastest = true
        out.minByOrNull { it.fuelGal }?.leanest = true
        return out
    }

    fun hm(minutes: Double): String {
        val m = Math.round(minutes).toInt().coerceAtLeast(0)
        return "%d:%02d".format(m / 60, m % 60)
    }

    fun utcNow(): String = java.text.SimpleDateFormat("HH:mm'Z'", java.util.Locale.US)
        .apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }.format(java.util.Date())
}
