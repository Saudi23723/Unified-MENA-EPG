package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import org.json.JSONArray
import org.json.JSONObject
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * A VFR flight plan: the route, how the aircraft flies it (altitude, true
 * airspeed, fuel burn) and the wind at altitude; from these the nav log,
 * leg by leg, the way a student fills it by hand.
 */
class FlightPlan {

    class Waypoint(val id: String, val lat: Double, val lon: Double)

    class Leg(
        val from: Waypoint, val to: Waypoint, val tc: Double, val dist: Double, val wca: Double,
        val th: Double, val mh: Double, val gs: Double, val minutes: Double, val fuel: Double,
    )

    val points = ArrayList<Waypoint>()
    var altitude = 5500
    var tas = 100
    var gph = 5.0
    var windDir = 0
    var windKt = 0
    var fuelOnBoard = 24.0
    /** Going straight to one point from wherever the aircraft is. */
    var direct: Waypoint? = null
    /** The waypoint being flown to, along the route. */
    var active = 1

    fun legs(): List<Leg> = (1 until points.size).map { i -> leg(points[i - 1], points[i]) }

    fun leg(a: Waypoint, b: Waypoint): Leg {
        val tc = Nav.bearingTrue(a.lat, a.lon, b.lat, b.lon)
        val dist = Nav.distanceNm(a.lat, a.lon, b.lat, b.lon)
        // The wind triangle: the heading that holds the course, and the speed over the ground.
        val rel = Math.toRadians(windDir - tc)
        val s = (windKt * Math.sin(rel) / tas).coerceIn(-1.0, 1.0)
        val wca = Math.toDegrees(Math.asin(s))
        val gs = (tas * Math.cos(Math.asin(s)) - windKt * Math.cos(rel)).coerceAtLeast(1.0)
        val th = (tc + wca + 360) % 360
        val mh = Nav.magnetic(th, (a.lat + b.lat) / 2, (a.lon + b.lon) / 2)
        val minutes = dist / gs * 60
        return Leg(a, b, tc, dist, wca, th, mh, gs, minutes, minutes / 60 * gph)
    }

    /** The farthest any point of the route lies from the departure, for the cross-country rule (more than 50 nm). */
    fun farthestNm(): Double {
        val a = points.firstOrNull() ?: return 0.0
        return points.maxOfOrNull { Nav.distanceNm(a.lat, a.lon, it.lat, it.lon) } ?: 0.0
    }

    /** Where the aircraft is headed: the direct-to point, or the active waypoint of the route. */
    fun target(): Waypoint? = direct ?: points.getOrNull(active.coerceAtLeast(1)).takeIf { points.size > 1 }

    /** Moves to the next waypoint once the aircraft is close to the one it flies to. */
    fun sequence(lat: Double, lon: Double): Boolean {
        val t = target() ?: return false
        if (Nav.distanceNm(lat, lon, t.lat, t.lon) > 0.6) return false
        if (direct != null) {
            val i = points.indexOfFirst { it.id == t.id && it.lat == t.lat }
            direct = null
            if (i >= 0 && i + 1 < points.size) active = i + 1 else return true
            return true
        }
        if (active + 1 < points.size) {
            active++
            return true
        }
        return false
    }

    fun navLog(): String {
        val sb = StringBuilder()
        sb.append("ALT %,d ft · TAS %d kt · W %03d°/%d kt · %.1f gph\n\n".format(altitude, tas, windDir, windKt, gph))
        sb.append("%-11s %4s %4s %4s %4s %5s %4s %5s %5s\n".format("LEG", "TC", "WCA", "TH", "MH", "DIST", "GS", "ETE", "FUEL"))
        var dist = 0.0; var min = 0.0; var fuel = 0.0
        for (l in legs()) {
            dist += l.dist; min += l.minutes; fuel += l.fuel
            sb.append("%-11s %4s %+4d %4s %4s %5.1f %4d %5s %5.1f\n".format(
                "${l.from.id.take(5)}-${l.to.id.take(5)}", Nav.deg(l.tc), Math.round(l.wca).toInt(), Nav.deg(l.th), Nav.deg(l.mh),
                l.dist, Math.round(l.gs).toInt(), hm(l.minutes), l.fuel,
            ))
        }
        sb.append("\n%-11s %24s %5.1f %4s %5s %5.1f\n".format("TOTAL", "", dist, "", hm(min), fuel))
        val reserve = gph * 0.5
        val left = fuelOnBoard - fuel
        sb.append("\nFuel on board %.1f gal · after landing %.1f gal (%s)\n".format(fuelOnBoard, left, hm(left / gph * 60)))
        sb.append(if (left >= reserve) "✅ VFR day reserve 30 min (%.1f gal) kept\n".format(reserve)
            else "⚠️ Below the 30 min VFR day reserve (%.1f gal)\n".format(reserve))
        val far = farthestNm()
        if (points.size > 1) sb.append(if (far > 50) "✅ Cross-country: a point %.0f nm from the departure (61.109 > 50 nm)\n".format(far)
            else "Cross-country for 61.109 needs a landing more than 50 nm away (now %.0f nm)\n".format(far))
        return sb.toString()
    }

    fun toJson(): JSONObject = JSONObject()
        .put("pts", JSONArray().apply { for (p in points) put(JSONArray().put(p.id).put(p.lat).put(p.lon)) })
        .put("alt", altitude).put("tas", tas).put("gph", gph).put("wd", windDir).put("ws", windKt).put("fob", fuelOnBoard)

    fun save(ctx: Context) = VaultLock.prefs(ctx).edit().putString("flight_plan", toJson().toString()).apply()

    companion object {
        fun hm(minutes: Double): String {
            val m = Math.round(minutes).toInt().coerceAtLeast(0)
            return "%d:%02d".format(m / 60, m % 60)
        }

        fun load(ctx: Context): FlightPlan = FlightPlan().apply {
            val o = try { JSONObject(VaultLock.prefs(ctx).getString("flight_plan", "{}")!!) } catch (e: Exception) { JSONObject() }
            o.optJSONArray("pts")?.let { a ->
                for (i in 0 until a.length()) a.optJSONArray(i)?.let { points.add(Waypoint(it.getString(0), it.getDouble(1), it.getDouble(2))) }
            }
            altitude = o.optInt("alt", 5500)
            tas = o.optInt("tas", VaultLock.prefs(ctx).getFloat("cruise_kt", 100f).toInt())
            gph = o.optDouble("gph", 5.0)
            windDir = o.optInt("wd", 0)
            windKt = o.optInt("ws", 0)
            fuelOnBoard = o.optDouble("fob", 24.0)
        }
    }
}

/** The route in magenta, as on a moving map, its waypoints, and the line to a direct-to point. */
class RouteOverlay(map: MapView, private val plan: () -> FlightPlan, private val aircraft: () -> GeoPoint?) : Overlay() {

    private val d = map.resources.displayMetrics.density
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFFE040FB.toInt()
        strokeWidth = 5 * d
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val past = Paint(line).apply { color = 0x99E040FB.toInt(); strokeWidth = 3.5f * d }
    private val outline = Paint(line).apply { color = 0xFFFFFFFF.toInt(); strokeWidth = 8 * d }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt() }
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFAA00FF.toInt(); style = Paint.Style.STROKE; strokeWidth = 3 * d }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 12 * d; isFakeBoldText = true; color = 0xFF4A148C.toInt() }
    private val halo = Paint(text).apply { style = Paint.Style.STROKE; strokeWidth = 3.5f * d; color = 0xF0FFFFFF.toInt() }
    private val pt = Point()
    private val pt2 = Point()

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val p = plan()
        val pr = mapView.projection
        if (p.points.size > 1) {
            for (i in 1 until p.points.size) {
                val a = p.points[i - 1]; val b = p.points[i]
                pr.toPixels(GeoPoint(a.lat, a.lon), pt)
                pr.toPixels(GeoPoint(b.lat, b.lon), pt2)
                val done = p.direct == null && i < p.active
                c.drawLine(pt.x.toFloat(), pt.y.toFloat(), pt2.x.toFloat(), pt2.y.toFloat(), outline)
                c.drawLine(pt.x.toFloat(), pt.y.toFloat(), pt2.x.toFloat(), pt2.y.toFloat(), if (done) past else line)
            }
        }
        p.direct?.let { t ->
            val from = aircraft() ?: return@let
            pr.toPixels(from, pt)
            pr.toPixels(GeoPoint(t.lat, t.lon), pt2)
            c.drawLine(pt.x.toFloat(), pt.y.toFloat(), pt2.x.toFloat(), pt2.y.toFloat(), outline)
            c.drawLine(pt.x.toFloat(), pt.y.toFloat(), pt2.x.toFloat(), pt2.y.toFloat(), line)
        }
        val target = p.target()
        val shown = p.points + listOfNotNull(p.direct)
        for (w in shown) {
            pr.toPixels(GeoPoint(w.lat, w.lon), pt)
            c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), 6 * d, dot)
            c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), 6 * d, ring)
            if (w === target) c.drawCircle(pt.x.toFloat(), pt.y.toFloat(), 11 * d, ring)
            c.save()
            c.rotate(-mapView.mapOrientation, pt.x.toFloat(), pt.y.toFloat())
            c.drawText(w.id, pt.x + 10 * d, pt.y - 8 * d, halo)
            c.drawText(w.id, pt.x + 10 * d, pt.y - 8 * d, text)
            c.restore()
        }
    }
}

/** The weight and balance of an aircraft: its empty weight, its loading stations and its CG envelope. */
class Aircraft(
    var name: String,
    var emptyWeight: Double, var emptyArm: Double, var maxWeight: Double,
    val stations: MutableList<Station>,
    /** The envelope as (CG arm, weight) corners, in order around it. */
    var envelope: MutableList<Pair<Double, Double>>,
    var example: Boolean = false,
) {
    class Station(val name: String, var arm: Double, var max: Double, val fuel: Boolean = false, var load: Double = 0.0)

    class Result(val weight: Double, val cg: Double, val inside: Boolean)

    fun compute(fuelBurnGal: Double = 0.0): Pair<Result, Result> {
        var w = emptyWeight; var m = emptyWeight * emptyArm
        var fuelArm = 0.0
        for (s in stations) {
            val lb = if (s.fuel) s.load * 6.0 else s.load
            w += lb; m += lb * s.arm
            if (s.fuel) fuelArm = s.arm
        }
        val takeoff = Result(w, m / w, inside(m / w, w) && w <= maxWeight + 0.01)
        val burn = fuelBurnGal.coerceAtMost(stations.filter { it.fuel }.sumOf { it.load }) * 6.0
        val lw = w - burn; val lm = m - burn * fuelArm
        return takeoff to Result(lw, lm / lw, inside(lm / lw, lw) && lw <= maxWeight + 0.01)
    }

    fun inside(cg: Double, w: Double): Boolean {
        var inside = false
        var j = envelope.size - 1
        for (i in envelope.indices) {
            val (xi, yi) = envelope[i]; val (xj, yj) = envelope[j]
            if ((yi > w) != (yj > w) && cg < (xj - xi) * (w - yi) / (yj - yi) + xi) inside = !inside
            j = i
        }
        return inside
    }

    fun toJson(): JSONObject = JSONObject().put("n", name).put("ew", emptyWeight).put("ea", emptyArm).put("mw", maxWeight).put("ex", example)
        .put("st", JSONArray().apply { for (s in stations) put(JSONObject().put("n", s.name).put("a", s.arm).put("m", s.max).put("f", s.fuel).put("l", s.load)) })
        .put("env", JSONArray().apply { for ((x, y) in envelope) put(JSONArray().put(x).put(y)) })

    companion object {
        fun fromJson(o: JSONObject) = Aircraft(
            o.getString("n"), o.getDouble("ew"), o.getDouble("ea"), o.getDouble("mw"),
            o.getJSONArray("st").let { a -> (0 until a.length()).map { i -> a.getJSONObject(i).let {
                Station(it.getString("n"), it.getDouble("a"), it.getDouble("m"), it.optBoolean("f"), it.optDouble("l", 0.0))
            } }.toMutableList() },
            o.getJSONArray("env").let { a -> (0 until a.length()).map { i -> a.getJSONArray(i).let { it.getDouble(0) to it.getDouble(1) } }.toMutableList() },
            o.optBoolean("ex"),
        )

        /** Cessna 172S, normal category (POH section 6); the empty weight and arm are typical: use the aircraft's own sheet. */
        fun c172() = Aircraft(
            "Cessna 172S", 1663.0, 41.0, 2550.0,
            mutableListOf(
                Station("Pilot + front passenger (lb)", 37.0, 400.0, load = 170.0),
                Station("Rear passengers (lb)", 73.0, 400.0),
                Station("Fuel (gal)", 48.0, 53.0, fuel = true, load = 40.0),
                Station("Baggage A (lb)", 95.0, 120.0),
                Station("Baggage B (lb)", 123.0, 50.0),
            ),
            mutableListOf(35.0 to 1500.0, 35.0 to 1950.0, 39.5 to 2550.0, 47.3 to 2550.0, 47.3 to 1500.0),
            example = true,
        )

        /** Evektor SportStar: only a starting point. Every number must come from the aircraft's own weight and balance sheet. */
        fun sportStar() = Aircraft(
            "Evektor SportStar", 780.0, 12.0, 1320.0,
            mutableListOf(
                Station("Pilot + passenger (lb)", 22.0, 440.0, load = 170.0),
                Station("Fuel (gal)", 8.0, 30.0, fuel = true, load = 20.0),
                Station("Baggage (lb)", 48.0, 55.0),
            ),
            mutableListOf(9.5 to 900.0, 9.5 to 1320.0, 15.0 to 1320.0, 15.0 to 900.0),
            example = true,
        )

        fun all(ctx: Context): MutableList<Aircraft> {
            val text = VaultLock.prefs(ctx).getString("wb_aircraft", null)
            return try {
                val a = JSONArray(text!!)
                (0 until a.length()).map { fromJson(a.getJSONObject(it)) }.toMutableList()
            } catch (e: Exception) {
                mutableListOf(sportStar(), c172())
            }
        }

        fun saveAll(ctx: Context, list: List<Aircraft>) =
            VaultLock.prefs(ctx).edit().putString("wb_aircraft", JSONArray().apply { for (a in list) put(a.toJson()) }.toString()).apply()
    }
}
