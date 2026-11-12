package com.saudi.privatevault

import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomsheet.BottomSheetDialog
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * A long press on the map, as an EFB answers it: the point and the airport
 * nearest it, the actions (Direct-To, add to the route, the airport), and
 * its weather in tabs: the METAR in a table, the TAF period by period, and
 * the winds aloft at every level.
 */
class PointSheet(
    private val act: AppCompatActivity,
    private val lat: Double,
    private val lon: Double,
    private val apt: AviationData.Airport?,
    private val from: Pair<Double, Double>?,
    private val onDirect: () -> Unit,
    private val onAdd: () -> Unit,
    private val onAirport: (() -> Unit)?,
    /** The pressed point itself, and the airports around it, for the Location / Airspace / Nearby sections. */
    private val press: Pair<Double, Double>? = null,
    private val nearby: List<AviationData.Airport> = emptyList(),
    private val onNearby: ((AviationData.Airport) -> Unit)? = null,
) {
    private val d = act.resources.displayMetrics.density
    private fun dp(v: Int) = (v * d).toInt()
    private val dialog = BottomSheetDialog(act)
    private val ink = EfbUi.TEXT
    private val dim = EfbUi.DIM
    private val accent = EfbUi.ACCENT

    private fun tv(s: CharSequence, size: Float = 14f, color: Int = ink, bold: Boolean = false, mono: Boolean = false) = TextView(act).apply {
        text = s; textSize = size; setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        if (mono) typeface = Typeface.MONOSPACE
        layoutDirection = View.LAYOUT_DIRECTION_LTR; textDirection = View.TEXT_DIRECTION_LTR
    }

    private fun pill(s: String, color: Int) = tv(s, 12.5f, 0xFFFFFFFF.toInt(), bold = true).apply {
        setPadding(dp(10), dp(3), dp(10), dp(3))
        background = GradientDrawable().apply { cornerRadius = dp(10).toFloat(); setColor(color) }
    }

    /** A table row: the name on the left, the value on the right. */
    private fun row(parent: LinearLayout, k: String, v: CharSequence, vColor: Int = ink) {
        val r = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR; setPadding(0, dp(7), 0, dp(7)) }
        r.addView(tv(k, 14f, dim, bold = true), LinearLayout.LayoutParams(dp(120), -2))
        r.addView(tv(v, 15f, vColor, bold = true).apply { gravity = Gravity.END }, LinearLayout.LayoutParams(0, -2, 1f))
        if (parent.childCount > 0) parent.addView(View(act).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
        parent.addView(r)
    }

    fun show() {
        val body = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(18), dp(12), dp(18), dp(24)); setBackgroundColor(EfbUi.BG) }
        val station = apt?.icao?.ifEmpty { apt.ident } ?: ""

        // Header: the airport (or the point), and where it is from here.
        val head = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
        head.addView(tv(if (apt != null) station else "%.4f°, %.4f°".format(lat, lon), 22f, ink, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
        val badge = pill("…", 0xFF607D8B.toInt())
        if (apt != null) head.addView(badge)
        body.addView(head)
        val sub = StringBuilder()
        if (apt != null) sub.append(apt.name).append(" · Elev ").append("%,d".format(apt.elevation)).append(" ft")
        from?.let { (y, x) ->
            val brg = Nav.magnetic(Nav.bearingTrue(y, x, lat, lon), y, x)
            if (sub.isNotEmpty()) sub.append('\n')
            sub.append("${Nav.deg(brg)}M · %.1f nm from you".format(Nav.distanceNm(y, x, lat, lon)))
        }
        if (sub.isNotEmpty()) body.addView(tv(sub, 13f, dim).apply { setPadding(0, dp(2), 0, dp(10)) })

        // Actions, big and in one row.
        val actions = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
        fun action(icon: String, label: Int, onClick: () -> Unit) = actions.addView(LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            background = EfbUi.cardBg(act, EfbUi.CARD, 12).apply { setStroke(0, 0) }
            setPadding(dp(6), dp(10), dp(6), dp(10))
            addView(tv(icon, 20f, accent).apply { gravity = Gravity.CENTER })
            addView(tv(act.getString(label), 11.5f, ink, bold = true).apply { gravity = Gravity.CENTER; maxLines = 1 })
            setOnClickListener { dialog.dismiss(); onClick() }
        }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        action("➜", R.string.apt_direct, onDirect)
        action("＋", R.string.apt_add_route, onAdd)
        onAirport?.let { action("✈", R.string.apt_tab_info, it) }
        body.addView(actions)
        pointInfo(body)

        if (apt == null) {
            dialog.setContentView(android.widget.ScrollView(act).apply { addView(body) })
            dialog.behavior.peekHeight = (act.resources.displayMetrics.heightPixels * 0.62).toInt()
            dialog.show(); return
        }

        // Weather tabs.
        val pages = listOf("METAR", "TAF", "WINDS ALOFT").map { it to LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(6), 0, 0) } }
        val tabs = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR; setPadding(0, dp(14), 0, dp(4)) }
        val tabViews = ArrayList<TextView>()
        fun select(k: Int) {
            pages.forEachIndexed { i, (_, v) -> v.visibility = if (i == k) View.VISIBLE else View.GONE }
            tabViews.forEachIndexed { i, t ->
                t.setTextColor(if (i == k) accent else dim)
                (t.tag as? View)?.setBackgroundColor(if (i == k) accent else 0)
            }
        }
        pages.forEachIndexed { i, (label, _) ->
            val cell = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
            val t = tv(label, 13f, dim, bold = true).apply { gravity = Gravity.CENTER; setPadding(0, dp(8), 0, dp(8)); letterSpacing = 0.05f }
            val line = View(act)
            t.tag = line
            cell.addView(t)
            cell.addView(line, LinearLayout.LayoutParams(-1, dp(3)))
            cell.setOnClickListener { select(i) }
            t.setOnClickListener { select(i) }
            tabViews.add(t)
            tabs.addView(cell, LinearLayout.LayoutParams(0, -2, 1f))
        }
        body.addView(tabs)
        for ((_, v) in pages) {
            v.addView(tv(act.getString(R.string.map_loading_wx), 13f, dim))
            body.addView(v)
        }
        select(0)
        dialog.setContentView(android.widget.ScrollView(act).apply { addView(body) })
        dialog.behavior.peekHeight = (act.resources.displayMetrics.heightPixels * 0.62).toInt()
        dialog.show()

        act.lifecycleScope.launch {
            val (m, taf, fb) = withContext(Dispatchers.IO) {
                Triple(AviationData.metar(station), AviationData.taf(station), try { AviationData.windsAloft(6) } catch (e: Exception) { "" })
            }
            m?.category?.takeIf { it.isNotEmpty() }?.let { badge.text = it; (badge.background as GradientDrawable).setColor(AviationData.categoryColor(it)) }
                ?: run { badge.visibility = View.GONE }
            metarPage(pages[0].second, m)
            tafPage(pages[1].second, taf)
            windsPage(pages[2].second, fb)
        }
    }

    private fun section(parent: LinearLayout, title: String) = parent.addView(tv(title, 12f, dim, bold = true).apply {
        letterSpacing = 0.08f; setPadding(dp(2), dp(16), 0, dp(6))
    })

    /**
     * As ForeFlight's map sidebar has it: where the point is (latitude/longitude in degrees and
     * minutes, the ground's elevation), every airspace over it with its floor and ceiling, and the
     * airports around it with distance and bearing.
     */
    private fun pointInfo(body: LinearLayout) {
        val (pl, po) = press ?: (lat to lon)
        fun dm(v: Double, pos: Char, neg: Char): String {
            val a = Math.abs(v); val deg = a.toInt(); val min = (a - deg) * 60
            return "%d°%05.2f'%c".format(deg, min, if (v >= 0) pos else neg)
        }
        section(body, "LOCATION")
        val loc = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(act); setPadding(dp(14), dp(4), dp(14), dp(4)); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        row(loc, "Position", "${dm(pl, 'N', 'S')}  ${dm(po, 'E', 'W')}")
        val elevRow = tv("…", 15f, ink, bold = true)
        val er = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(10), 0, dp(10)) }
        er.addView(tv("Ground", 14f, dim, bold = true), LinearLayout.LayoutParams(dp(120), -2))
        er.addView(elevRow.apply { gravity = Gravity.END }, LinearLayout.LayoutParams(0, -2, 1f))
        loc.addView(View(act).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
        loc.addView(er)
        body.addView(loc)

        section(body, "AIRSPACE")
        val asp = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(act); setPadding(dp(14), dp(6), dp(14), dp(6)); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        asp.addView(tv("…", 13f, dim))
        body.addView(asp)

        if (nearby.isNotEmpty()) {
            section(body, "NEARBY")
            val nb = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(act); setPadding(dp(14), dp(2), dp(14), dp(2)); layoutDirection = View.LAYOUT_DIRECTION_LTR }
            for ((i, a) in nearby.withIndex()) {
                if (i > 0) nb.addView(View(act).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
                val r = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(10), 0, dp(10)) }
                r.addView(tv("◉", 15f, accent), LinearLayout.LayoutParams(dp(26), -2))
                val t = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
                t.addView(tv(a.icao.ifEmpty { a.ident }, 15f, ink, bold = true))
                val brg = Nav.magnetic(Nav.bearingTrue(pl, po, a.lat, a.lon), pl, po)
                t.addView(tv("${a.name} · %.1f nm ${Nav.deg(brg)}M".format(Nav.distanceNm(pl, po, a.lat, a.lon)), 12.5f, dim))
                r.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
                r.addView(tv("›", 20f, dim))
                if (onNearby != null) r.setOnClickListener { dialog.dismiss(); onNearby.invoke(a) }
                nb.addView(r)
            }
            body.addView(nb)
        }

        act.lifecycleScope.launch {
            val (elev, list) = withContext(Dispatchers.IO) {
                val e = try { Terrain.elevationFt(pl, po, wait = true) } catch (e: Exception) { null }
                val areas = try { Airspace.areas.ifEmpty { Airspace.load(act) } } catch (e: Throwable) { emptyList() }
                e to areas.filter { it.contains(pl, po) }
            }
            elevRow.text = elev?.let { "%,d ft MSL".format(it.toInt()) } ?: "—"
            asp.removeAllViews()
            if (list.isEmpty()) asp.addView(tv("Class E/G (no B, C, D or special-use airspace here)", 13.5f, dim).apply { setPadding(0, dp(8), 0, dp(8)) })
            for ((i, a) in list.sortedBy { it.lowFt ?: 0 }.withIndex()) {
                if (i > 0) asp.addView(View(act).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
                val r = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(9), 0, dp(9)) }
                r.addView(View(act).apply { setBackgroundColor(Airspace.color(a.kind)) }, LinearLayout.LayoutParams(dp(5), dp(34)).apply { marginEnd = dp(10) })
                val t = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
                t.addView(tv(a.name.ifEmpty { Airspace.spoken(a.kind) }, 15f, ink, bold = true))
                t.addView(tv("${Airspace.spoken(a.kind)} · ${a.low.ifEmpty { "?" }} – ${a.high.ifEmpty { "?" }}" + if (a.note.isNotBlank()) " · ${a.note.take(60)}" else "", 12.5f, dim))
                r.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
                asp.addView(r)
            }
        }
    }

    private fun num(o: JSONObject?, key: String): Double? = o?.opt(key)?.toString()?.replace("+", "")?.toDoubleOrNull()

    private fun metarPage(p: LinearLayout, m: AviationData.Metar?) {
        p.removeAllViews()
        if (m == null) { p.addView(tv(act.getString(R.string.pt_no_metar), 14f, dim)); return }
        val j = m.json
        val wdir = j?.opt("wdir")?.toString()
        val wspd = num(j, "wspd")?.toInt()
        val gust = num(j, "wgst")?.toInt()
        if (wspd != null) row(p, "Wind", if (wspd == 0) "Calm" else "${if (wdir == "VRB") "VRB" else "%03d°".format(wdir?.toDoubleOrNull()?.toInt() ?: 0)} @ $wspd kt" + (gust?.let { "  G$it" } ?: ""))
        var ceil: Int? = null
        val layers = ArrayList<String>()
        j?.optJSONArray("clouds")?.let { c ->
            for (i in 0 until c.length()) {
                val o = c.optJSONObject(i) ?: continue
                val cover = o.optString("cover"); val base = o.optInt("base", -1)
                layers.add(if (base >= 0) "$cover %,d".format(base) else cover)
                if (cover in setOf("BKN", "OVC", "OVX", "VV") && base >= 0 && (ceil == null || base < ceil!!)) ceil = base
            }
        }
        row(p, "Ceiling", ceil?.let { "%,d ft".format(it) } ?: "None")
        j?.opt("visib")?.toString()?.let { row(p, "Visibility", "$it sm") }
        num(j, "altim")?.let { a -> row(p, "Altimeter", "%.2f inHg".format(if (a > 100) a * 0.02953 else a)) }
        j?.optString("wxString")?.takeIf { it.isNotEmpty() && it != "null" }?.let { row(p, "Weather", it) }
        if (layers.isNotEmpty()) row(p, "Clouds", layers.joinToString("\n"))
        val t = num(j, "temp"); val dew = num(j, "dewp")
        if (t != null) {
            row(p, "Temp / Dew", "%.0f°C / %s".format(t, dew?.let { "%.0f°C".format(it) } ?: "—"))
            val altim = num(j, "altim")?.let { if (it > 100) it * 0.02953 else it }
            if (altim != null && apt != null) {
                val elev = apt.elevation.toDouble()
                val da = elev + (29.92 - altim) * 1000 + 120 * (t - (15 - 2 * elev / 1000))
                row(p, "Density alt", "%,d ft".format(Math.round(da).toInt()), if (da > elev + 2000) EfbUi.WARN else ink)
            }
        }
        val age = (System.currentTimeMillis() / 1000 - m.time) / 60
        p.addView(tv(m.raw, 12.5f, dim, mono = true).apply { setPadding(0, dp(12), 0, 0); setTextIsSelectable(true) })
        if (m.time > 0) p.addView(tv(act.getString(R.string.pt_age, age), 12f, dim).apply { setPadding(0, dp(4), 0, 0) })
    }

    /** The TAF in its periods: each FM, BECMG, TEMPO and PROB on a line of its own. */
    private fun tafPage(p: LinearLayout, taf: String?) {
        p.removeAllViews()
        if (taf.isNullOrBlank()) { p.addView(tv(act.getString(R.string.pt_no_taf), 14f, dim)); return }
        val parts = taf.replace(Regex("\\s+"), " ").trim().split(Regex("(?=\\b(FM\\d{6}|BECMG|TEMPO|PROB\\d{2}))"))
        for ((i, part) in parts.withIndex()) {
            val s = part.trim()
            if (s.isEmpty()) continue
            val head = when {
                i == 0 -> "Initial"
                s.startsWith("FM") -> s.substring(2, 8).let { "From ${it.substring(0, 2)}th ${it.substring(2, 4)}:${it.substring(4, 6)}Z" }
                s.startsWith("TEMPO") -> "Temporarily"
                s.startsWith("BECMG") -> "Becoming"
                s.startsWith("PROB") -> "Probability ${s.substring(4, 6)}%"
                else -> ""
            }
            val card = LinearLayout(act).apply {
                orientation = LinearLayout.VERTICAL
                background = EfbUi.cardBg(act, EfbUi.CARD, 10).apply { setStroke(0, 0) }
                setPadding(dp(12), dp(8), dp(12), dp(8))
            }
            card.addView(tv(head, 13f, accent, bold = true))
            card.addView(tv(s, 13.5f, ink, mono = true).apply { setTextIsSelectable(true) })
            p.addView(card, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) })
        }
    }

    private fun windsPage(p: LinearLayout, fb: String) {
        p.removeAllViews()
        val levels = intArrayOf(3000, 6000, 9000, 12000, 18000, 24000, 30000, 34000, 39000)
        val near = AviationData.fbStations().minByOrNull { (_, v) -> Nav.distanceNm(lat, lon, v.first, v.second) }
        var any = false
        for (alt in levels) {
            val w = AviationData.windAt(fb, lat, lon, alt, near?.key) ?: continue
            // Below the field, a forecast level means nothing.
            if (apt != null && alt < apt.elevation + 1500) continue
            any = true
            val temp = w.third?.let { t ->
                val isa = 15 - 2 * alt / 1000
                "  %+d°C (ISA%+d)".format(t, t - isa)
            } ?: ""
            row(p, "%,d ft".format(alt), if (w.second == 0) "Light & var$temp" else "%03d° @ %d kt%s".format(w.first, w.second, temp))
        }
        if (!any) { p.addView(tv(act.getString(R.string.pt_no_winds), 14f, dim)); return }
        near?.let { (k, v) -> p.addView(tv(act.getString(R.string.pt_winds_from, k, Nav.distanceNm(lat, lon, v.first, v.second)), 12f, dim).apply { setPadding(0, dp(8), 0, 0) }) }
    }
}
