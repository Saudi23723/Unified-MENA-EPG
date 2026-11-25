package com.saudi.privatevault

import org.osmdroid.util.GeoPoint

/**
 * When a route would strike the ground, where to take it instead.
 *
 * A profile says that the route runs into a ridge at fifty-five miles. This answers the next
 * question a pilot asks: if I want to stay down here, where do I go round it?
 *
 * It looks at the leg that would be struck and tries a turning point on either side of it, at a
 * spread of distances out from the line and a spread of places along it, and sweeps each
 * candidate's two new legs through the same corridor of ground and the same obstacle list the
 * profile uses. What it offers is the SHORTEST detour that clears everything by the margin, not
 * the lowest ground — the lowest ground is usually a long way round — and a candidate that would
 * pass through prohibited or restricted airspace at the planned height is thrown out before it is
 * ever shown. If nothing clears, it says so and offers the next legal VFR height to climb to.
 *
 * It only suggests. Nothing changes until the pilot accepts it.
 */
object TerrainRouter {

    class Bypass(
        val legIndex: Int,
        val lat: Double, val lon: Double,
        val addedNm: Double,
        val maxGroundFt: Int,
        val side: String,
        /** The room it keeps over the highest ground: a thousand feet if it can, five hundred if that is the best there is. */
        val marginFt: Int,
    )

    /**
     * @param climbFt    the next legal VFR height that clears the ground by a thousand feet
     * @param climbMinFt the next legal VFR height that clears it by five hundred, when that is a lower one
     */
    class Answer(val bypass: Bypass?, val climbFt: Int?, val climbMinFt: Int?, val worstGroundFt: Int)

    private const val MARGIN_FT = 1000
    private const val MARGIN_MIN_FT = 500

    /** The highest ground in the corridor either side of a leg, swept every mile. */
    private fun worstOnLeg(a: GeoPoint, b: GeoPoint, half: Double, ground: (Double, Double) -> Float): Float {
        val len = Nav.distanceNm(a.latitude, a.longitude, b.latitude, b.longitude)
        val crs = Nav.bearingTrue(a.latitude, a.longitude, b.latitude, b.longitude)
        var worst = 0f
        var s = 0.0
        while (true) {
            val g = Nav.destination(a.latitude, a.longitude, crs, Math.min(s, len))
            for (k in -2..2) {
                val off = if (half <= 0.1) 0.0 else half * k / 2.0
                val p = if (off == 0.0) g else Nav.destination(g.latitude, g.longitude, crs + 90.0, off)
                val h = ground(p.latitude, p.longitude)
                if (h > worst) worst = h
            }
            if (s >= len) break
            s += 1.0
        }
        return worst
    }

    private fun throughForbidden(a: GeoPoint, b: GeoPoint, altFt: Int, areas: List<Airspace.Area>): Boolean {
        val len = Nav.distanceNm(a.latitude, a.longitude, b.latitude, b.longitude)
        val crs = Nav.bearingTrue(a.latitude, a.longitude, b.latitude, b.longitude)
        var s = 0.0
        while (s <= len) {
            val g = Nav.destination(a.latitude, a.longitude, crs, s)
            for (ar in areas) {
                val k = ar.kind.uppercase()
                if ((k == "R" || k == "P") && ar.contains(g.latitude, g.longitude) && ar.spans(altFt.toDouble())) return true
            }
            s += 1.0
        }
        return false
    }

    /**
     * The next legal VFR height at least a margin above the ground: odd thousands and five
     * hundred going east (magnetic course 0 to 179), even thousands and five hundred going west.
     */
    fun climbTo(maxGroundFt: Float, magneticCourse: Double, minimum: Int, margin: Int = MARGIN_FT): Int {
        val need = maxOf(maxGroundFt + margin, minimum.toFloat())
        val east = magneticCourse % 360 < 180
        var alt = if (east) 3500 else 4500
        while (alt < need) alt += 2000
        return alt
    }

    /**
     * @param points   the route
     * @param strikeNm how far along it the first strike is
     * @param ground   the ground at a point, best available
     * @param areas    the airspace to keep clear of
     */
    fun suggest(
        points: List<FlightPlan.Waypoint>, altFt: Int, halfCorridorNm: Double, strikeNm: Double,
        worstGroundFt: Float, areas: List<Airspace.Area>, ground: (Double, Double) -> Float,
    ): Answer {
        // The leg the strike falls on, and how far along that leg.
        var run = 0.0
        var leg = 0
        var along = 0.0
        var legLen = 0.0
        for (i in 1 until points.size) {
            val len = Nav.distanceNm(points[i - 1].lat, points[i - 1].lon, points[i].lat, points[i].lon)
            if (strikeNm <= run + len || i == points.size - 1) { leg = i; along = (strikeNm - run).coerceIn(0.0, len); legLen = len; break }
            run += len
        }
        if (leg == 0 || legLen < 3.0) return Answer(null, null, null, worstGroundFt.toInt())
        val a = GeoPoint(points[leg - 1].lat, points[leg - 1].lon)
        val b = GeoPoint(points[leg].lat, points[leg].lon)
        val crs = Nav.bearingTrue(a.latitude, a.longitude, b.latitude, b.longitude)
        val direct = legLen
        val limit = altFt - MARGIN_FT
        val limitMin = altFt - MARGIN_MIN_FT

        // Have the ground the candidates will be swept through, so it is not fetched one tile at a
        // time in the middle of the search.
        try {
            val pad = 0.55
            Terrain.prefetch(Math.min(a.latitude, b.latitude) - pad, Math.min(a.longitude, b.longitude) - pad,
                Math.max(a.latitude, b.latitude) + pad, Math.max(a.longitude, b.longitude) + pad)
        } catch (e: Throwable) { }

        // Two tiers are kept as the search goes: the shortest detour that clears by a thousand feet,
        // and the shortest that clears by five hundred. The first is offered if there is one; the
        // second, marked as the lesser, when there is not — better a way round that keeps five
        // hundred feet than the word "none" when the pilot is looking at a ridge.
        var best: Bypass? = null
        var bestMin: Bypass? = null
        val ctx = appContext
        val fractions = listOf(-0.2, -0.1, 0.0, 0.1, 0.2).map { (along / legLen + it).coerceIn(0.12, 0.9) }.distinct()
        val offsets = listOf(3.0, 5.0, 8.0, 12.0, 16.0, 22.0, 30.0)
        for (f in fractions) {
            val pivot = Nav.destination(a.latitude, a.longitude, crs, legLen * f)
            for (side in intArrayOf(-1, 1)) for (off in offsets) {
                val w = Nav.destination(pivot.latitude, pivot.longitude, crs + 90.0 * side, off)
                val added = Nav.distanceNm(a.latitude, a.longitude, w.latitude, w.longitude) +
                    Nav.distanceNm(w.latitude, w.longitude, b.latitude, b.longitude) - direct
                // Nothing can beat a thousand-foot detour that is already shorter than this.
                if (best != null && added >= best.addedNm) continue
                if (best == null && bestMin != null && added >= bestMin.addedNm && added > bestMin.addedNm + 40.0) continue
                val worst1 = worstOnLeg(a, w, halfCorridorNm, ground)
                if (worst1 > limitMin) continue
                val worst2 = worstOnLeg(w, b, halfCorridorNm, ground)
                if (worst2 > limitMin) continue
                val worst = Math.max(worst1, worst2)
                val tier = if (worst <= limit) MARGIN_FT else MARGIN_MIN_FT
                if (tier == MARGIN_MIN_FT && bestMin != null && added >= bestMin.addedNm) continue
                if (throughForbidden(a, w, altFt, areas) || throughForbidden(w, b, altFt, areas)) continue
                // The towers on the two new legs, except close to the ends where the climb and the
                // descent take care of them.
                val tw: List<Obstacles.Along> = if (ctx == null) emptyList() else try {
                    Obstacles.alongRoute(ctx,
                        listOf(points[leg - 1], FlightPlan.Waypoint("W", w.latitude, w.longitude), points[leg]), halfCorridorNm)
                } catch (e: Throwable) { emptyList() }
                val total = Nav.distanceNm(a.latitude, a.longitude, w.latitude, w.longitude) +
                    Nav.distanceNm(w.latitude, w.longitude, b.latitude, b.longitude)
                val lim = if (tier == MARGIN_FT) limit else limitMin
                if (tw.any { it.obstacle.topFt > lim && it.alongNm > 3.0 && it.alongNm < total - 3.0 }) continue
                val cand = Bypass(leg - 1, w.latitude, w.longitude, added, worst.toInt(),
                    if (side < 0) "left of the course" else "right of the course", tier)
                if (tier == MARGIN_FT) best = cand else bestMin = cand
            }
        }
        val course = Nav.magnetic(crs, a.latitude, a.longitude)
        val climb = climbTo(worstGroundFt, course, 3500)
        val climbMin = climbTo(worstGroundFt, course, 3500, MARGIN_MIN_FT).takeIf { it < climb }
        return Answer(best ?: bestMin, climb, climbMin, worstGroundFt.toInt())
    }

    /** Set once by the map, so the obstacle list can be read from here. */
    var appContext: android.content.Context? = null
}
