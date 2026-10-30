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
    /** Runway designator → (threshold, far end). */
    var ends: Map<String, Pair<GeoPoint, GeoPoint>> = emptyMap()
    var runway: String? = null
    var right = false
    var tpaFt = 0

    private val d = map.resources.displayMetrics.density
    private val leg = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 11.5f * d; isFakeBoldText = true }
    private val pill = RectF()
    private val pt = Point()

    private fun xy(g: GeoPoint, out: Point = Point()): Point { map.projection.toPixels(g, out); return out }

    private fun dest(g: GeoPoint, brg: Double, nm: Double) = Nav.destination(g.latitude, g.longitude, (brg + 720) % 360, nm)

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow || mv.zoomLevelDouble < 11.5) return
        val (t, far) = ends[runway ?: return] ?: return
        val h = Nav.bearingTrue(t.latitude, t.longitude, far.latitude, far.longitude)
        val side = h + if (right) 90 else -90
        val o = 0.65    // downwind about 2/3 nm out: a light sport aircraft's pattern
        val ext = 0.6
        val up = dest(far, h, 0.5)
        val cross = dest(up, side, o)
        val abeam = dest(t, side, o)
        val baseTurn = dest(abeam, h + 180, ext)
        val finalTurn = dest(t, h + 180, ext)
        val downMid = GeoPoint((cross.latitude + abeam.latitude) / 2, (cross.longitude + abeam.longitude) / 2)
        val dw = h + 180
        val entryHdg = dw + if (right) 45 else -45
        val entry = dest(downMid, entryHdg + 180, 0.75)

        // The legs: one line, arrows on the way round.
        val path = Path()
        val pts = listOf(t, far, up, cross, abeam, baseTurn, finalTurn, t)
        for ((i, g) in pts.withIndex()) { val p = xy(g); if (i == 0) path.moveTo(p.x.toFloat(), p.y.toFloat()) else path.lineTo(p.x.toFloat(), p.y.toFloat()) }
        leg.pathEffect = null
        leg.color = 0x66000000; leg.strokeWidth = 7 * d; c.drawPath(path, leg)
        leg.color = 0xFF4DA3FF.toInt(); leg.strokeWidth = 3.5f * d; c.drawPath(path, leg)
        for (i in 1 until pts.size) arrow(c, pts[i - 1], pts[i])
        // The 45° entry, dashed.
        leg.color = 0xFFFFC107.toInt(); leg.strokeWidth = 2.5f * d
        leg.pathEffect = DashPathEffect(floatArrayOf(10 * d, 7 * d), 0f)
        val e1 = xy(entry); val e2 = xy(downMid)
        c.drawLine(e1.x.toFloat(), e1.y.toFloat(), e2.x.toFloat(), e2.y.toFloat(), leg)
        leg.pathEffect = null

        // What is done where (the school's whiteboard, SportStar).
        val tpa = if (tpaFt > 0) "%,d ft".format(tpaFt) else "TPA"
        callout(c, mid(t, far), "UPWIND", 0xFF4DA3FF.toInt())
        callout(c, cross, "CROSSWIND · within 300 ft of TPA (AC 90-66)", 0xFF4DA3FF.toInt())
        callout(c, dest(cross, dw, 0.15), "@TPA $tpa: pitch · power 4800 · 85 kt · trim", 0xFF34C759.toInt())
        callout(c, downMid, "DOWNWIND · before-landing checklist (BCGUMPS)", 0xFF4DA3FF.toInt())
        callout(c, abeam, "ABEAM NUMBERS: 3200 RPM · <70 kt · flaps 1 · descend", 0xFFFF9F0A.toInt())
        callout(c, mid(baseTurn, finalTurn), "BASE: flaps 2", 0xFFFF9F0A.toInt())
        callout(c, mid(finalTurn, t), "FINAL: 3° · 60–65 kt", 0xFFFF453A.toInt())
        callout(c, entry, "45° ENTRY", 0xFFFFC107.toInt())
        callout(c, dest(t, h + 180, 0.05), "RWY $runway · ${if (right) "RIGHT" else "LEFT"} TRAFFIC", 0xFFFFFFFF.toInt())
    }

    private fun mid(a: GeoPoint, b: GeoPoint) = GeoPoint((a.latitude + b.latitude) / 2, (a.longitude + b.longitude) / 2)

    private fun arrow(c: Canvas, a: GeoPoint, b: GeoPoint) {
        val p1 = xy(a); val p2 = xy(b)
        val mx = (p1.x + p2.x) / 2f; val my = (p1.y + p2.y) / 2f
        val ang = Math.atan2((p2.y - p1.y).toDouble(), (p2.x - p1.x).toDouble())
        val s = 9 * d
        val tri = Path().apply {
            moveTo((mx + s * Math.cos(ang)).toFloat(), (my + s * Math.sin(ang)).toFloat())
            lineTo((mx + s * Math.cos(ang + 2.5)).toFloat(), (my + s * Math.sin(ang + 2.5)).toFloat())
            lineTo((mx + s * Math.cos(ang - 2.5)).toFloat(), (my + s * Math.sin(ang - 2.5)).toFloat())
            close()
        }
        fill.color = 0xFFFFFFFF.toInt()
        c.drawPath(tri, fill)
    }

    /** A dark label with a coloured edge, kept upright whatever way the view is turned. */
    private fun callout(c: Canvas, g: GeoPoint, s: String, color: Int) {
        val p = xy(g, pt)
        val x = p.x.toFloat(); val y = p.y.toFloat()
        c.save()
        c.rotate(-map.mapOrientation, x, y)
        val w = text.measureText(s)
        pill.set(x - w / 2 - 7 * d, y - 12 * d, x + w / 2 + 7 * d, y + 6 * d)
        fill.color = 0xE60F1318.toInt()
        c.drawRoundRect(pill, 6 * d, 6 * d, fill)
        leg.color = color; leg.strokeWidth = 1.5f * d
        c.drawRoundRect(pill, 6 * d, 6 * d, leg)
        text.color = color
        c.drawText(s, x - w / 2, y, text)
        c.restore()
    }

    companion object {
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
