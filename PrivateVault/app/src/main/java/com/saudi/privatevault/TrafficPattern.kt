package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.graphics.RectF
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * The traffic pattern of the runway in use, drawn on the airport view:
 * upwind, crosswind, downwind, base and final, the 45° entry, the side
 * (left or right traffic), and at each point what is done there in the
 * SportStar, as the school teaches it on its whiteboard (KBVU: TPA, power,
 * flaps, before-landing checklist). Pattern altitude is field elevation +
 * 1,000 ft (AC 90-66) unless set.
 */
class PatternOverlay(private val map: MapView) : Overlay() {
    /** One airport's runways for the patterns. */
    class Field(val ident: String, val name: String, val ends: Map<String, Pair<GeoPoint, GeoPoint>>, val tpaFt: Int, var active: String?)

    /** Every airport shown, by its identifier. */
    val fields = LinkedHashMap<String, Field>()
    /** The numbered steps (①…⑥) on the active pattern: the airport view, where there is room for them. */
    var steps = false
    /** Right traffic, per airport and runway. */
    var isRight: (String, String) -> Boolean = { _, _ -> false }

    // Kept for the airport view, which shows one airport.
    var ends: Map<String, Pair<GeoPoint, GeoPoint>>
        get() = fields.values.firstOrNull()?.ends ?: emptyMap()
        set(v) { fields.clear(); fields["_"] = Field("_", airport, v, tpaFt, runway) }
    var runway: String?
        get() = fields.values.firstOrNull()?.active
        set(v) { fields.values.firstOrNull()?.active = v }
    var right = false
    var tpaFt = 0
    var airport = ""

    private val d = map.resources.displayMetrics.density
    private val leg = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10.5f * d; isFakeBoldText = true; textAlign = Paint.Align.CENTER }
    private val pill = RectF()
    private val pt = Point()

    private fun xy(g: GeoPoint, out: Point = Point()): Point { map.projection.toPixels(g, out); return out }
    private fun dest(g: GeoPoint, brg: Double, nm: Double) = Nav.destination(g.latitude, g.longitude, (brg + 720) % 360, nm)
    private fun mid(a: GeoPoint, b: GeoPoint) = GeoPoint((a.latitude + b.latitude) / 2, (a.longitude + b.longitude) / 2)

    /** A pattern's corners: threshold, far end, upwind, crosswind turn, abeam the numbers, base turn, final turn, and the 45° entry. */
    private class Shape(val pts: List<GeoPoint>, val cross: GeoPoint, val tpaPoint: GeoPoint, val downMid: GeoPoint, val abeam: GeoPoint,
                        val base: GeoPoint, val fin: GeoPoint, val entry: GeoPoint)

    private fun shape(t: GeoPoint, far: GeoPoint, right: Boolean): Shape {
        val h = Nav.bearingTrue(t.latitude, t.longitude, far.latitude, far.longitude)
        val side = h + if (right) 90 else -90
        val o = 0.65    // downwind about 2/3 nm out, for a light aircraft
        val up = dest(far, h, 0.5)
        val cross = dest(up, side, o)
        val abeam = dest(t, side, o)
        val baseTurn = dest(abeam, h + 180, 0.6)
        val finalTurn = dest(t, h + 180, 0.6)
        val downMid = mid(cross, abeam)
        val dw = h + 180
        val entry = dest(downMid, dw + (if (right) 45 else -45) + 180, 0.75)
        return Shape(listOf(t, far, up, cross, abeam, baseTurn, finalTurn, t), mid(up, cross), dest(cross, dw, 0.15), downMid, abeam,
            mid(baseTurn, finalTurn), mid(finalTurn, t), entry)
    }

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow || mv.zoomLevelDouble < 11.5) return
        val bb = mv.boundingBox
        for (f in fields.values) {
            // The other runways first, quiet; the one in use over them.
            val order = f.ends.keys.sortedBy { if (it == f.active) 1 else 0 }
            for (r in order) {
                val (t, far) = f.ends[r] ?: continue
                if (t.latitude !in bb.latSouth - 0.05..bb.latNorth + 0.05 || t.longitude !in bb.lonWest - 0.06..bb.lonEast + 0.06) continue
                val rightTfc = if (f.ident == "_") (if (r == f.active) right else isRight(f.name, r)) else isRight(f.ident, r)
                val sh = shape(t, far, rightTfc)
                val path = Path()
                for ((i, g) in sh.pts.withIndex()) { val p = xy(g); if (i == 0) path.moveTo(p.x.toFloat(), p.y.toFloat()) else path.lineTo(p.x.toFloat(), p.y.toFloat()) }
                val on = r == f.active
                if (on) {
                    leg.pathEffect = null
                    leg.color = 0x55000000; leg.strokeWidth = 5 * d; c.drawPath(path, leg)
                    leg.color = 0xFF4DA3FF.toInt(); leg.strokeWidth = 2.5f * d; c.drawPath(path, leg)
                    for (i in 1 until sh.pts.size) arrow(c, sh.pts[i - 1], sh.pts[i])
                    leg.color = 0xCCFFC107.toInt(); leg.strokeWidth = 1.8f * d
                    leg.pathEffect = DashPathEffect(floatArrayOf(8 * d, 6 * d), 0f)
                    val e1 = xy(sh.entry); val e2 = xy(sh.downMid)
                    c.drawLine(e1.x.toFloat(), e1.y.toFloat(), e2.x.toFloat(), e2.y.toFloat(), leg)
                    leg.pathEffect = null
                } else {
                    leg.color = 0x99B0BEC5.toInt(); leg.strokeWidth = 1.3f * d
                    leg.pathEffect = DashPathEffect(floatArrayOf(6 * d, 5 * d), 0f)
                    c.drawPath(path, leg)
                    leg.pathEffect = null
                }
                tag(c, sh.downMid, "$r ${if (rightTfc) "R" else "L"}" + if (on && f.tpaFt > 0) " · TPA %,d".format(f.tpaFt) else "", on)
                if (on && steps) {
                    dot(c, sh.cross, "1"); dot(c, sh.tpaPoint, "2"); dot(c, dest(sh.downMid, Nav.bearingTrue(t.latitude, t.longitude, far.latitude, far.longitude), 0.12), "3")
                    dot(c, sh.abeam, "4"); dot(c, sh.base, "5"); dot(c, sh.fin, "6"); dot(c, sh.entry, "E")
                }
            }
        }
    }

    private fun arrow(c: Canvas, a: GeoPoint, b: GeoPoint) {
        val p1 = xy(a); val p2 = xy(b)
        val mx = (p1.x + p2.x) / 2f; val my = (p1.y + p2.y) / 2f
        val ang = Math.atan2((p2.y - p1.y).toDouble(), (p2.x - p1.x).toDouble())
        val s = 7 * d
        fill.color = 0xFFFFFFFF.toInt()
        c.drawPath(Path().apply {
            moveTo((mx + s * Math.cos(ang)).toFloat(), (my + s * Math.sin(ang)).toFloat())
            lineTo((mx + s * Math.cos(ang + 2.5)).toFloat(), (my + s * Math.sin(ang + 2.5)).toFloat())
            lineTo((mx + s * Math.cos(ang - 2.5)).toFloat(), (my + s * Math.sin(ang - 2.5)).toFloat())
            close()
        }, fill)
    }

    /** A small runway tag on the downwind: "27 L · TPA 3,200". */
    private fun tag(c: Canvas, g: GeoPoint, s: String, on: Boolean) {
        val p = xy(g, pt); val x = p.x.toFloat(); val y = p.y.toFloat()
        c.save(); c.rotate(-map.mapOrientation, x, y)
        val w = text.measureText(s) / 2 + 6 * d
        pill.set(x - w, y - 9 * d, x + w, y + 6 * d)
        fill.color = if (on) 0xF01A6FE0.toInt() else 0xCC263238.toInt()
        c.drawRoundRect(pill, 5 * d, 5 * d, fill)
        text.color = 0xFFFFFFFF.toInt()
        c.drawText(s, x, y + 2.5f * d, text)
        c.restore()
    }

    /** A numbered step on the pattern, explained under the view. */
    private fun dot(c: Canvas, g: GeoPoint, n: String) {
        val p = xy(g, pt); val x = p.x.toFloat(); val y = p.y.toFloat()
        c.save(); c.rotate(-map.mapOrientation, x, y)
        fill.color = if (n == "E") 0xFFFFC107.toInt() else 0xFFFF9F0A.toInt()
        c.drawCircle(x, y, 9 * d, fill)
        text.color = 0xFF111111.toInt()
        c.drawText(n, x, y + 3.5f * d, text)
        c.restore()
    }

    companion object {
        /** Runway ends from the airport's surveyed layout (the airport view's saved OSM data). */
        fun endsFrom(json: org.json.JSONObject?): Map<String, Pair<GeoPoint, GeoPoint>> {
            val el = json?.optJSONArray("elements") ?: return emptyMap()
            val byRef = LinkedHashMap<String, MutableList<GeoPoint>>()
            for (i in 0 until el.length()) {
                val o = el.optJSONObject(i) ?: continue
                val t = o.optJSONObject("tags") ?: continue
                if (t.optString("aeroway") != "runway") continue
                val ref = t.optString("ref")
                if (ref.isEmpty()) continue
                val g = o.optJSONArray("geometry") ?: continue
                val list = byRef.getOrPut(ref) { ArrayList() }
                for (k in 0 until g.length()) g.optJSONObject(k)?.let { list.add(GeoPoint(it.getDouble("lat"), it.getDouble("lon"))) }
            }
            val out = LinkedHashMap<String, Pair<GeoPoint, GeoPoint>>()
            for ((ref, pts) in byRef) {
                if (pts.size < 2) continue
                var a0 = pts.first(); var a1 = pts.last(); var best = -1.0
                for (i in pts.indices) for (j in i + 1 until pts.size) {
                    val dd = Nav.distanceNm(pts[i].latitude, pts[i].longitude, pts[j].latitude, pts[j].longitude)
                    if (dd > best) { best = dd; a0 = pts[i]; a1 = pts[j] }
                }
                val brg = Nav.magnetic(Nav.bearingTrue(a0.latitude, a0.longitude, a1.latitude, a1.longitude), a0.latitude, a0.longitude)
                val parts = ref.split('/').map { it.trim() }.filter { it.isNotEmpty() }
                fun gap(p: String) = p.takeWhile { it.isDigit() }.toIntOrNull()?.let { Math.abs(((it * 10 - brg + 540) % 360) - 180) } ?: 999.0
                val first = parts.minByOrNull { gap(it) } ?: continue
                out[first] = a0 to a1
                parts.firstOrNull { it != first }?.let { out[it] = a1 to a0 }
            }
            return out
        }

        /** The runway most into the wind (METAR, true degrees), else the calm-wind runway, else the first. */
        fun favored(ident: String, runways: Collection<String>, metar: org.json.JSONObject?, lat: Double, lon: Double): String? {
            val spd = metar?.opt("wspd")?.toString()?.toDoubleOrNull() ?: 0.0
            val dir = metar?.opt("wdir")?.toString()?.toDoubleOrNull()
            if (dir != null && spd >= 3) {
                val mag = Nav.magnetic(dir, lat, lon)
                runways.maxByOrNull { r -> r.takeWhile { it.isDigit() }.toIntOrNull()?.let { Math.cos(Math.toRadians(mag - it * 10.0)) } ?: -9.0 }?.let { return it }
            }
            return calmRunway(ident)?.takeIf { it in runways } ?: runways.firstOrNull()
        }

        fun tpa(elevFt: Int) = ((elevFt + 1000 + 50) / 100) * 100

        /** Right traffic is set per runway; the school's board gives KBVU 09 right and 27 left. */
        private val KNOWN = mapOf("BVU|09" to true, "BVU|27" to false)
        private val CALM = mapOf("BVU" to "27")

        fun key(ident: String) = ident.removePrefix("K").let { if (it.length == 3) it else ident }

        fun isRight(ctx: Context, ident: String, rwy: String): Boolean =
            VaultLock.prefs(ctx).getString("tp_${key(ident)}_$rwy", null)?.let { it == "R" } ?: (KNOWN["${key(ident)}|$rwy"] ?: false)

        fun setRight(ctx: Context, ident: String, rwy: String, right: Boolean) =
            VaultLock.prefs(ctx).edit().putString("tp_${key(ident)}_$rwy", if (right) "R" else "L").apply()

        fun calmRunway(ident: String) = CALM[key(ident)]
    }
}
