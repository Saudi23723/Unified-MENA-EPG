package com.saudi.privatevault

import android.content.Intent
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.graphics.RectF
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * An instrument approach drawn on the chart from the FAA's coded data, as the panel's GPS flies it:
 * the transition and the final in magenta, the missed approach dashed in cyan, each fix with its
 * name, its role (IAF, IF, FAF, MAP) and its altitude in a tag, and the hold as its racetrack.
 */
class ProcedureOverlay(map: MapView) : Overlay() {
    var proc: Cifp.Procedure? = null
    var transition: String? = null
    /** The aircraft: position, altitude (ft) and ground speed (kt), or null on the ground / without GPS. */
    var me: () -> Triple<GeoPoint, Double?, Double>? = { null }

    /** The first fix the aircraft flies to: the transition's start, or the final's first fix with vectors. */
    fun entry(): Cifp.Leg? = proc?.legs(transition)?.firstOrNull { !it.missed && it.lat != null && it.lon != null }

    /** The way from the aircraft to the approach: bearing, distance, time, and the height to lose for the entry fix's altitude. */
    private fun drawWayIn(c: Canvas, mv: MapView) {
        val m = me() ?: return
        val e = entry() ?: return
        val here = m.first
        val dist = Nav.distanceNm(here.latitude, here.longitude, e.lat!!, e.lon!!)
        if (dist < 0.3) return
        val pr = mv.projection
        pr.toPixels(here, p0); pr.toPixels(GeoPoint(e.lat, e.lon), p1)
        c.drawLine(p0.x.toFloat(), p0.y.toFloat(), p1.x.toFloat(), p1.y.toFloat(), toHalo)
        c.drawLine(p0.x.toFloat(), p0.y.toFloat(), p1.x.toFloat(), p1.y.toFloat(), toLine)
        val brg = Nav.magnetic(Nav.bearingTrue(here.latitude, here.longitude, e.lat, e.lon), here.latitude, here.longitude)
        val gs = m.third
        val ete = if (gs > 25) " · %d min".format(Math.round(dist / gs * 60)) else ""
        val l1 = "→ ${e.fix}${e.roleText().takeIf { it.isNotEmpty() && it != "Step-down" }?.let { " ($it)" } ?: ""} · ${Nav.deg(brg)}M · %.1f nm$ete".format(dist)
        // The height: what the entry fix asks against where the aircraft is, and the descent rate it takes.
        var l2 = ""
        val alt = m.second; val want = e.alt1
        if (alt != null && want != null) {
            val diff = alt - want
            l2 = when {
                diff > 150 && (e.altDesc == '+') -> "At or above %,d' — you are %,d' above".format(want, Math.round(diff))
                diff > 150 -> {
                    val fpm = if (gs > 25) diff / (dist / gs * 60) else Double.NaN
                    "Descend %,d' to %,d'".format(Math.round(diff), want) + (if (!fpm.isNaN()) " · %,d fpm".format(Math.round(fpm / 50) * 50) else "") +
                        (if (!fpm.isNaN() && fpm > 1000) " · start down now" else "")
                }
                diff < -150 && e.altDesc != '-' -> "Climb %,d' to %,d'".format(Math.round(-diff), want)
                else -> "On altitude for ${e.fix} (%,d')".format(want)
            }
        }
        val x = (p0.x + p1.x) / 2f; val y = (p0.y + p1.y) / 2f
        c.save(); c.rotate(-mv.mapOrientation, x, y)
        val w = maxOf(toTx.measureText(l1), if (l2.isEmpty()) 0f else toTx2.measureText(l2))
        val h = if (l2.isEmpty()) 22 * d else 38 * d
        c.drawRoundRect(RectF(x - w / 2 - 8 * d, y - h / 2, x + w / 2 + 8 * d, y + h / 2), 7 * d, 7 * d, toBg)
        c.drawText(l1, x - w / 2, y - h / 2 + 15.5f * d, toTx)
        if (l2.isNotEmpty()) c.drawText(l2, x - w / 2, y - h / 2 + 32 * d, toTx2)
        c.restore()
    }

    private val d = map.resources.displayMetrics.density
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 4.5f * d; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val halo = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 8f * d; color = 0x99000000.toInt(); strokeCap = Paint.Cap.ROUND }
    private val fixFill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fixEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.6f * d; color = 0xFF000000.toInt() }
    private val tagBg = Paint(Paint.ANTI_ALIAS_FLAG)
    private val tagTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 12f * d; isFakeBoldText = true; color = 0xFFFFFFFF.toInt() }
    private val nameTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 12.5f * d; isFakeBoldText = true; color = 0xFF111111.toInt() }
    private val nameHalo = Paint(nameTx).apply { style = Paint.Style.STROKE; strokeWidth = 3.5f * d; color = 0xEEFFFFFF.toInt() }
    private val p0 = Point(); private val p1 = Point()
    private val toLine = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 3f * d; color = 0xFFFFFFFF.toInt(); strokeCap = Paint.Cap.ROUND
        pathEffect = DashPathEffect(floatArrayOf(12 * d, 8 * d), 0f) }
    private val toHalo = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 6f * d; color = 0xAA000000.toInt(); strokeCap = Paint.Cap.ROUND }
    private val toBg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xEE1B1D22.toInt() }
    private val toTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 12.5f * d; isFakeBoldText = true; color = 0xFFFFFFFF.toInt() }
    private val toTx2 = Paint(toTx).apply { isFakeBoldText = false; textSize = 11.5f * d; color = 0xFFFFD60A.toInt() }

    private fun toTrue(magCourse: Double, lat: Double, lon: Double): Double {
        val m = Nav.magnetic(magCourse, lat, lon)
        return (magCourse + (magCourse - m) + 720) % 360
    }

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow) return
        val p = proc ?: return
        drawWayIn(c, mv)
        val legs = p.legs(transition)
        val pr = mv.projection
        var last: DoubleArray? = null
        val fixes = ArrayList<Pair<Cifp.Leg, DoubleArray>>()
        for (leg in legs) {
            val pos = if (leg.lat != null && leg.lon != null) doubleArrayOf(leg.lat, leg.lon) else null
            line.color = if (leg.missed) 0xFF00C8FF.toInt() else 0xFFFF2D9B.toInt()
            line.pathEffect = if (leg.missed) DashPathEffect(floatArrayOf(10 * d, 7 * d), 0f) else null
            val target = pos ?: run {
                // A climb or a heading leg (CA, VA, VI…): drawn two miles along its course.
                val from = last ?: return@run null
                val crs = leg.course ?: return@run null
                val g = Nav.destination(from[0], from[1], toTrue(crs, from[0], from[1]), 2.0)
                doubleArrayOf(g.latitude, g.longitude)
            }
            val from = last
            if (from != null && target != null && leg.path != "IF") {
                pr.toPixels(GeoPoint(from[0], from[1]), p0); pr.toPixels(GeoPoint(target[0], target[1]), p1)
                c.drawLine(p0.x.toFloat(), p0.y.toFloat(), p1.x.toFloat(), p1.y.toFloat(), halo)
                c.drawLine(p0.x.toFloat(), p0.y.toFloat(), p1.x.toFloat(), p1.y.toFloat(), line)
            }
            // A hold at the fix: its racetrack, inbound on the leg's course, standard 4 NM legs.
            if (pos != null && leg.path.startsWith("H") && leg.course != null) racetrack(c, mv, pos, toTrue(leg.course, pos[0], pos[1]), leg.turn != 'L', leg.missed)
            if (pos != null) fixes.add(leg to pos)
            if (target != null) last = target
        }
        line.pathEffect = null
        // The fixes on top, once each, with their tags upright whatever the chart's turn.
        val seen = HashSet<String>()
        for ((leg, pos) in fixes) {
            if (!seen.add(leg.fix)) continue
            pr.toPixels(GeoPoint(pos[0], pos[1]), p0)
            val x = p0.x.toFloat(); val y = p0.y.toFloat()
            fixFill.color = when (leg.role) { "F" -> 0xFFFFD60A.toInt(); "M" -> 0xFFFF453A.toInt(); "A" -> 0xFF34C759.toInt(); else -> 0xFFFFFFFF.toInt() }
            val s = 7 * d
            val dia = Path().apply { moveTo(x, y - s); lineTo(x + s, y); lineTo(x, y + s); lineTo(x - s, y); close() }
            c.drawPath(dia, fixFill); c.drawPath(dia, fixEdge)
            c.save(); c.rotate(-mv.mapOrientation, x, y)
            val name = leg.fix + (leg.roleText().takeIf { it.isNotEmpty() && it != "Step-down" }?.let { " ($it)" } ?: "")
            c.drawText(name, x + 11 * d, y - 4 * d, nameHalo); c.drawText(name, x + 11 * d, y - 4 * d, nameTx)
            val alt = leg.altText()
            if (alt.isNotEmpty()) {
                val t = "$alt'"
                val w = tagTx.measureText(t)
                val r = RectF(x + 10 * d, y + 2 * d, x + 18 * d + w, y + 20 * d)
                tagBg.color = if (leg.missed) 0xF0006E8C.toInt() else 0xF0E8590C.toInt()
                c.drawRoundRect(r, 4 * d, 4 * d, tagBg)
                c.drawText(t, r.left + 4 * d, r.bottom - 5 * d, tagTx)
            }
            c.restore()
        }
    }

    private fun racetrack(c: Canvas, mv: MapView, fix: DoubleArray, inbound: Double, right: Boolean, missed: Boolean) {
        val pr = mv.projection
        val out = (inbound + 180) % 360
        val side = (inbound + if (right) 90 else -90 + 360) % 360
        val a = fix
        val b = Nav.destination(a[0], a[1], out, 4.0).let { doubleArrayOf(it.latitude, it.longitude) }
        val cc = Nav.destination(b[0], b[1], side, 2.0).let { doubleArrayOf(it.latitude, it.longitude) }
        val dd = Nav.destination(a[0], a[1], side, 2.0).let { doubleArrayOf(it.latitude, it.longitude) }
        val pts = listOf(a, b, cc, dd).map { pr.toPixels(GeoPoint(it[0], it[1]), null) }
        line.color = if (missed) 0xFF00C8FF.toInt() else 0xFFFF2D9B.toInt()
        line.pathEffect = if (missed) DashPathEffect(floatArrayOf(10 * d, 7 * d), 0f) else null
        val path = Path().apply {
            moveTo(pts[0].x.toFloat(), pts[0].y.toFloat()); lineTo(pts[1].x.toFloat(), pts[1].y.toFloat())
            quadTo(((pts[1].x + pts[2].x) / 2f) + (pts[1].x - pts[0].x) * 0.35f, ((pts[1].y + pts[2].y) / 2f) + (pts[1].y - pts[0].y) * 0.35f, pts[2].x.toFloat(), pts[2].y.toFloat())
            lineTo(pts[3].x.toFloat(), pts[3].y.toFloat())
            quadTo(((pts[3].x + pts[0].x) / 2f) - (pts[1].x - pts[0].x) * 0.35f, ((pts[3].y + pts[0].y) / 2f) - (pts[1].y - pts[0].y) * 0.35f, pts[0].x.toFloat(), pts[0].y.toFloat())
        }
        c.drawPath(path, line)
        line.pathEffect = null
    }
}

/** Choosing an approach and reading it: the procedure advisor. */
object ProcedureUi {
    /** A procedure chosen away from the map, to show when the map comes back. */
    var pending: Pair<Cifp.Procedure, String?>? = null
    /** Where the aircraft is (the map sets it), to tell the nearest transition. */
    var here: () -> GeoPoint? = { null }

    fun choose(act: AppCompatActivity, icao: String, onShow: (Cifp.Procedure, String?) -> Unit, onAdd: ((Cifp.Procedure, String?) -> Unit)?) {
        val code = icao.uppercase().let { if (it.length == 3) "K$it" else it }
        val status = TextView(act).apply { setPadding(60, 40, 60, 20); textSize = 15f; text = "Loading the FAA's coded procedures…" }
        val wait = MaterialAlertDialogBuilder(act).setTitle("✈ Approaches · $code").setView(status).setCancelable(true).create()
        act.lifecycleScope.launch {
            var list = withContext(Dispatchers.IO) { Cifp.approaches(act, code) }
            if (list == null) {
                wait.show()
                val ok = withContext(Dispatchers.IO) { Cifp.ensure(act) { pct -> act.runOnUiThread { status.text = "Downloading the FAA CIFP (this cycle, once): $pct %" } } }
                if (ok) { status.text = "Reading…"; list = withContext(Dispatchers.IO) { Cifp.approaches(act, code) } }
                wait.dismiss()
            }
            if (list == null) { Toast.makeText(act, "Could not get the FAA procedures (internet needed once per cycle).", Toast.LENGTH_LONG).show(); return@launch }
            if (list.isEmpty()) { Toast.makeText(act, "$code has no published instrument approach.", Toast.LENGTH_LONG).show(); return@launch }
            MaterialAlertDialogBuilder(act).setTitle("✈ Approaches · $code")
                .setItems(list.map { it.name }.toTypedArray()) { _, i -> transition(act, list[i], onShow, onAdd) }
                .setNegativeButton(R.string.cancel, null).show()
        }
    }

    fun transition(act: AppCompatActivity, p: Cifp.Procedure, onShow: (Cifp.Procedure, String?) -> Unit, onAdd: ((Cifp.Procedure, String?) -> Unit)?) {
        val keys = p.transitions.keys.toList()
        if (keys.isEmpty()) { advisor(act, p, null, onShow, onAdd); return }
        // Each transition's start, with its distance from the aircraft, the nearest one marked.
        val h = here()
        val far = keys.map { k -> p.transitions[k]?.firstOrNull { it.lat != null }?.let { l -> h?.let { Nav.distanceNm(it.latitude, it.longitude, l.lat!!, l.lon!!) } } }
        val best = far.withIndex().filter { it.value != null }.minByOrNull { it.value!! }?.index
        val labels = keys.mapIndexed { i, k -> (if (i == best) "★ " else "") + k + (p.transitions[k]?.firstOrNull()?.let { if (it.role == "A") " (IAF)" else "" } ?: "") +
            (far[i]?.let { "  ·  %.0f nm".format(it) } ?: "") + (if (i == best) "  · nearest" else "") } + "Vectors to final"
        MaterialAlertDialogBuilder(act).setTitle("${p.name} · transition")
            .setItems(labels.toTypedArray()) { _, i -> advisor(act, p, keys.getOrNull(i), onShow, onAdd) }
            .setNegativeButton(R.string.cancel, null).show()
    }

    /** As ForeFlight's procedure advisor: the approach, its final course, every fix with its altitude, the missed approach. */
    fun advisor(act: AppCompatActivity, p: Cifp.Procedure, trans: String?, onShow: (Cifp.Procedure, String?) -> Unit, onAdd: ((Cifp.Procedure, String?) -> Unit)?) {
        val d = act.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val dlg = BottomSheetDialog(act)
        val body = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(18), dp(14), dp(18), dp(26)); setBackgroundColor(EfbUi.BG); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        body.addView(EfbUi.text(act, "VERIFY WITH CHART", 10.5f, EfbUi.DIM, bold = true).apply { letterSpacing = 0.1f; gravity = Gravity.CENTER })
        body.addView(EfbUi.text(act, p.name, 22f, EfbUi.TEXT, bold = true).apply { gravity = Gravity.CENTER })
        body.addView(EfbUi.text(act, "${p.icao}" + (trans?.let { " · via $it" } ?: " · vectors to final"), 13f, EfbUi.DIM).apply { gravity = Gravity.CENTER })
        val legs = p.legs(trans)
        // The briefing strip: final course and the FAF's altitude.
        val strip = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; background = EfbUi.cardBg(act); setPadding(dp(8), dp(10), dp(8), dp(10)) }
        fun cell(k: String, v: String) = strip.addView(LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            addView(EfbUi.text(act, k, 11f, EfbUi.DIM, bold = true).apply { gravity = Gravity.CENTER })
            addView(EfbUi.text(act, v, 17f, EfbUi.TEXT, bold = true).apply { gravity = Gravity.CENTER })
        }, LinearLayout.LayoutParams(0, -2, 1f))
        val faf = legs.firstOrNull { it.role == "F" }
        val map0 = legs.firstOrNull { it.role == "M" }
        // The runway this approach serves, as the FAA codes it: its threshold elevation and crossing height.
        val rwy = Regex("(\\d{2}[LRC]?)").find(p.id.drop(1))?.groupValues?.get(1)?.trimStart('0')
        val end = rwy?.let { Cifp.runwayEnds(act, p.icao)[it] }
        // How far it is from each fix to the missed-approach point, along the path itself.
        val onPath = legs.filter { !it.missed && it.lat != null && it.lon != null }
        fun toGo(fix: String): Double? {
            val i = onPath.indexOfFirst { it.fix == fix }
            val m = onPath.indexOfFirst { it.role == "M" }
            if (i < 0 || m < 0 || i > m) return null
            var sum = 0.0
            for (k in i until m) sum += Nav.distanceNm(onPath[k].lat!!, onPath[k].lon!!, onPath[k + 1].lat!!, onPath[k + 1].lon!!)
            return sum
        }
        val finalNm = faf?.let { toGo(it.fix) }
        cell("Final", p.finalCourse()?.let { "%03.0f°".format(it) } ?: "—")
        cell("FAF", faf?.let { "${it.fix}\n${it.altText()}'" } ?: "—")
        cell("MAP", map0?.let { it.fix + (finalNm?.let { n -> "\n%.1f nm".format(n) } ?: "") } ?: "—")
        if (end?.elevFt != null) cell("RWY $rwy", "%,d'".format(end.elevFt) + (end.tchFt?.takeIf { it > 0 }?.let { "\nTCH $it'" } ?: ""))
        body.addView(strip, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })

        fun section(t: String) = body.addView(EfbUi.text(act, t, 12f, EfbUi.DIM, bold = true).apply { letterSpacing = 0.08f; setPadding(dp(2), dp(16), 0, dp(6)) })
        fun legsCard(list: List<Cifp.Leg>, missed: Boolean) {
            val card = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(act); setPadding(dp(12), dp(4), dp(12), dp(4)) }
            for ((i, l) in list.withIndex()) {
                if (i > 0) card.addView(View(act).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
                val r = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(9), 0, dp(9)) }
                val badge = TextView(act).apply {
                    text = l.roleText().ifEmpty { if (l.path.startsWith("H")) "HOLD" else l.path }
                    textSize = 10.5f; typeface = EfbUi.MEDIUM; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt())
                    background = EfbUi.cardBg(act, when (l.role) { "F" -> 0xFFB8860B.toInt(); "M" -> 0xFFD93025.toInt(); "A" -> 0xFF1E9E4A.toInt(); "I" -> 0xFF2D8CFF.toInt()
                        else -> if (missed) 0xFF006E8C.toInt() else 0xFF48484A.toInt() }, 6)
                }
                r.addView(badge, LinearLayout.LayoutParams(dp(62), dp(24)))
                val t = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, 0, 0) }
                t.addView(EfbUi.text(act, l.fix.ifEmpty { "climb on course" }, 15.5f, EfbUi.TEXT, bold = true))
                val sub = listOfNotNull(l.course?.let { "%03.0f°".format(it) }, l.dist?.let { "%.1f nm".format(it) },
                    if (l.path.startsWith("H")) (if (l.turn == 'L') "left turns" else "right turns") else null,
                    if (!missed) toGo(l.fix)?.takeIf { it > 0.05 }?.let { "%.1f nm to the MAP".format(it) } else null).joinToString("  ·  ")
                if (sub.isNotEmpty()) t.addView(EfbUi.text(act, sub, 12.5f, EfbUi.DIM))
                r.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
                val alt = l.altText()
                if (alt.isNotEmpty()) r.addView(EfbUi.text(act, "$alt'", 16f, if (missed) 0xFF00C8FF.toInt() else 0xFFFF9F0A.toInt(), bold = true))
                card.addView(r)
            }
            body.addView(card)
        }
        section("ROUTE")
        legsCard(legs.filter { !it.missed }, false)
        // The descent on the final segment: the gradient it asks and the rate that holds it.
        if (faf != null && finalNm != null && finalNm > 0.3) {
            val fafAlt = faf.alt1
            val bottom = end?.elevFt?.let { it + (end.tchFt?.takeIf { t -> t > 0 } ?: 50) }
            if (fafAlt != null && bottom != null && fafAlt > bottom) {
                section("DESCENT ON FINAL")
                val drop = (fafAlt - bottom).toDouble()
                val perNm = drop / finalNm
                val card = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(act); setPadding(dp(12), dp(10), dp(12), dp(10)) }
                card.addView(EfbUi.text(act, "%,d' at ${faf.fix} down to %,d' over the threshold in %.1f nm".format(fafAlt, bottom, finalNm), 14f, EfbUi.TEXT, bold = true))
                card.addView(EfbUi.text(act, "%,d ft per nm  ·  %.2f° path".format(Math.round(perNm).toInt(), Math.toDegrees(Math.atan(perNm / 6076.12))), 12.5f, 0xFFFF9F0A.toInt()))
                val tbl = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(8), 0, 0) }
                tbl.addView(LinearLayout(act).apply {
                    orientation = LinearLayout.HORIZONTAL
                    addView(EfbUi.text(act, "GS", 11f, EfbUi.DIM, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
                    addView(EfbUi.text(act, "RATE", 11f, EfbUi.DIM, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
                    addView(EfbUi.text(act, "FAF TO MAP", 11f, EfbUi.DIM, bold = true), LinearLayout.LayoutParams(0, -2, 1.3f))
                })
                for (gs in listOf(70, 80, 90, 100, 120)) {
                    val mins = finalNm / gs * 60
                    tbl.addView(LinearLayout(act).apply {
                        orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(3), 0, dp(3))
                        addView(EfbUi.text(act, "$gs kt", 13f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1f))
                        addView(EfbUi.text(act, "%,d fpm".format((Math.round(perNm * gs / 60 / 10) * 10).toInt()), 13f, 0xFF64D2FF.toInt(), bold = true), LinearLayout.LayoutParams(0, -2, 1f))
                        addView(EfbUi.text(act, "%d:%02d".format(mins.toInt(), Math.round((mins - mins.toInt()) * 60).toInt().coerceIn(0, 59)), 13f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1.3f))
                    })
                }
                card.addView(tbl)
                card.addView(EfbUi.text(act, "From the coded altitudes and the runway's own elevation: the chart's own rate table and minimums still rule.", 10.5f, EfbUi.DIM).apply { setPadding(0, dp(8), 0, 0) })
                body.addView(card)
            }
        }
        val ma = legs.filter { it.missed }
        if (ma.isNotEmpty()) {
            section("MISSED APPROACH")
            legsCard(ma, true)
        }
        // The actions.
        val acts = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(16), 0, 0) }
        fun action(label: String, color: Int, go: () -> Unit) = acts.addView(TextView(act).apply {
            text = label; textSize = 14f; typeface = EfbUi.MEDIUM; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt())
            setPadding(dp(6), dp(12), dp(6), dp(12)); background = EfbUi.cardBg(act, color, 10)
            setOnClickListener { dlg.dismiss(); go() }
        }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        action("🗺 Show on map", 0xFF2D8CFF.toInt()) { onShow(p, trans) }
        onAdd?.let { add -> action("＋ Add to route", 0xFF34C759.toInt()) { add(p, trans) } }
        action("📄 Plate", 0xFF48484A.toInt()) { plate(act, p) }
        body.addView(acts)
        body.addView(EfbUi.text(act, "From the FAA CIFP of this cycle — the coded data the GPS navigator flies. Minimums and notes: the plate.", 11f, EfbUi.DIM).apply { setPadding(dp(2), dp(12), dp(2), 0) })
        dlg.setContentView(android.widget.ScrollView(act).apply { addView(body) })
        dlg.behavior.peekHeight = (act.resources.displayMetrics.heightPixels * 0.7).toInt()
        dlg.show()
    }

    /** The FAA plate of the same approach, in the reader. */
    fun plate(act: AppCompatActivity, p: Cifp.Procedure) {
        val ident = p.icao.removePrefix("K").takeIf { p.icao.length == 4 && p.icao.startsWith("K") } ?: p.icao
        act.lifecycleScope.launch {
            val res = withContext(Dispatchers.IO) { AviationData.plates(act, ident) }
            val norm = { s: String -> s.uppercase().replace(" ", "").replace("RWY", "") }
            val pl = res?.second?.firstOrNull { it.code == "IAP" && norm(it.name) == norm(p.name) }
                ?: res?.second?.firstOrNull { it.code == "IAP" && norm(it.name).startsWith(norm(p.name)) }
            if (res == null || pl == null) { Toast.makeText(act, R.string.apt_plates_fail, Toast.LENGTH_LONG).show(); return@launch }
            val f = withContext(Dispatchers.IO) { AviationData.platePdf(act, res.first, pl.pdf) }
            if (f == null) { Toast.makeText(act, R.string.apt_plates_fail, Toast.LENGTH_LONG).show(); return@launch }
            val item = VaultItem("plate:" + pl.pdf, "${p.icao} ${pl.name}", f.absolutePath, "application/pdf", f.length(), f.lastModified(), null)
            VaultStore.viewOnly(item)
            act.startActivity(Intent(act, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
        }
    }
}
