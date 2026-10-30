package com.saudi.privatevault

import android.content.Intent
import android.net.Uri
import android.view.View
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * An airport's page: its weather decoded (wind on each runway, density
 * altitude), its runways and frequencies, its charts and procedures for the
 * current cycle, and the Chart Supplement.
 */
class AirportSheet(
    private val act: AppCompatActivity,
    private val a: AviationData.Airport,
    private val station: String,
    private val from: org.osmdroid.util.GeoPoint?,
    private val onDirect: () -> Unit,
    private val onAddToRoute: () -> Unit,
) {
    private val d = act.resources.displayMetrics.density
    private fun dp(v: Int) = (v * d).toInt()

    private val body = LinearLayout(act).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(18), dp(14), dp(18), dp(28))
    }
    private val wx = text("${act.getString(R.string.map_loading_wx)}")
    private val info = text("")
    private val dialog = BottomSheetDialog(act)

    private fun text(s: String, size: Float = 14f, bold: Boolean = false, mono: Boolean = false) = TextView(act).apply {
        text = s
        textSize = size
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        if (mono) typeface = android.graphics.Typeface.MONOSPACE
        layoutDirection = View.LAYOUT_DIRECTION_LTR
        textDirection = View.TEXT_DIRECTION_LTR
        setTextIsSelectable(true)
        setPadding(0, dp(4), 0, dp(4))
    }

    fun show() {
        val title = "${a.icao.ifEmpty { a.ident }}${if (a.icao.isNotEmpty() && a.icao != a.ident) " (${a.ident})" else ""}"
        body.addView(text(title, 22f, bold = true))
        var sub = "${a.name}\n${a.city.lowercase().split(' ').joinToString(" ") { it.replaceFirstChar { c -> c.uppercase() } }} · Elev ${"%,d".format(a.elevation)} ft"
        from?.let {
            val dist = Nav.distanceNm(it.latitude, it.longitude, a.lat, a.lon)
            val brg = Nav.magnetic(Nav.bearingTrue(it.latitude, it.longitude, a.lat, a.lon), it.latitude, it.longitude)
            sub += "\n${Nav.deg(brg)}M · %.1f nm".format(dist)
        }
        body.addView(text(sub))
        val buttons = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }
        fun button(label: Int, onClick: () -> Unit) = buttons.addView(MaterialButton(act, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
            text = act.getString(label)
            isAllCaps = false
            setOnClickListener { onClick() }
        }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) })
        button(R.string.efb_diagram) { AirportDiagramActivity.open(act, a) }
        button(if (Favorites.has(act, a.ident)) R.string.fav_remove else R.string.fav_add) {
            val now = Favorites.toggle(act, a.ident)
            Toast.makeText(act, if (now) R.string.fav_added else R.string.fav_removed, Toast.LENGTH_SHORT).show()
        }
        button(R.string.apt_notams) { open("https://www.notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do?reportType=Raw&retrieveLocId=${a.icao.ifEmpty { a.ident }}&actionType=notamRetrievalbyICAOs") }
        button(R.string.apt_direct) { dialog.dismiss(); onDirect() }
        button(R.string.apt_add_route) { dialog.dismiss(); onAddToRoute() }
        button(R.string.apt_plates) { plates() }
        button(R.string.apt_supplement) { supplement() }
        body.addView(HorizontalScrollView(act).apply {
            isHorizontalScrollBarEnabled = false
            addView(buttons)
        })
        body.addView(header(R.string.apt_weather))
        body.addView(wx)
        body.addView(header(R.string.apt_runways))
        body.addView(info)
        body.addView(header(R.string.apt_sun))
        body.addView(text(sunText(), mono = true))
        dialog.setContentView(android.widget.ScrollView(act).apply { addView(body) })
        dialog.behavior.peekHeight = (act.resources.displayMetrics.heightPixels * 0.55).toInt()
        dialog.show()
        load()
    }

    /** Today's sun at the field, with the times that decide night logging (61.51) and night passenger currency (61.57(b)). */
    private fun sunText(): String {
        val t = Sun.times(a.lat, a.lon)
        return "Sunrise ${t["sunrise"]}   Sunset ${t["sunset"]}\n" +
            "Civil twilight ${t["dawn"]} – ${t["dusk"]}\n" +
            "Night (log night time): after ${t["dusk"]}, before ${t["dawn"]}\n" +
            "Night landings for 61.57(b): ${t["pax_night_from"]} – ${t["pax_night_to"]}\n" +
            "(phone time zone)"
    }

    private fun header(res: Int) = text(act.getString(res), 16f, bold = true).apply {
        setPadding(0, dp(14), 0, dp(2))
        setTextColor(0xFF1565C0.toInt())
        layoutDirection = View.LAYOUT_DIRECTION_INHERIT
        textDirection = View.TEXT_DIRECTION_INHERIT
    }

    private fun open(url: String) {
        try {
            act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (e: Exception) {
        }
    }

    private fun load() {
        act.lifecycleScope.launch {
            val (metar, taf, apt) = withContext(Dispatchers.IO) {
                Triple(AviationData.metar(station), AviationData.taf(station), AviationData.airportInfo(act, station))
            }
            wx.text = weather(metar, taf, apt)
            info.text = runways(apt, metar)
            metar?.category?.takeIf { it.isNotEmpty() }?.let { wx.setTextColor(AviationData.categoryColor(it)) }
        }
    }

    private fun num(o: JSONObject?, key: String): Double? = o?.opt(key)?.toString()?.replace("+", "")?.toDoubleOrNull()

    private fun weather(m: AviationData.Metar?, taf: String?, apt: JSONObject?): String {
        if (m == null) return act.getString(R.string.map_no_metar) + (taf?.let { "\n\nTAF\n$it" } ?: "")
        val j = m.json
        val sb = StringBuilder()
        sb.append(m.category.ifEmpty { "—" })
        val age = (System.currentTimeMillis() / 1000 - m.time) / 60
        if (m.time > 0) sb.append(" · ${age} min ago")
        sb.append('\n')
        val wdir = j?.opt("wdir")?.toString()
        val wspd = num(j, "wspd")?.toInt()
        val gust = num(j, "wgst")?.toInt()
        if (wspd != null) sb.append("Wind ${if (wspd == 0) "calm" else "${wdir?.let { if (it == "VRB") "VRB" else "%03d°".format(it.toDoubleOrNull()?.toInt() ?: 0) }} $wspd${gust?.let { "G$it" } ?: ""} kt"}\n")
        j?.opt("visib")?.toString()?.let { sb.append("Visibility $it sm\n") }
        j?.optJSONArray("clouds")?.let { c ->
            val layers = (0 until c.length()).mapNotNull { i -> c.optJSONObject(i)?.let { "${it.optString("cover")} ${it.optString("base").takeIf { b -> b != "null" } ?: ""}".trim() } }
            if (layers.isNotEmpty()) sb.append("Clouds ${layers.joinToString(", ")}\n")
        }
        j?.optString("wxString")?.takeIf { it.isNotEmpty() && it != "null" }?.let { sb.append("Weather $it\n") }
        val t = num(j, "temp"); val dew = num(j, "dewp")
        if (t != null) sb.append("Temp %.0f°C / dew %s\n".format(t, dew?.let { "%.0f°C".format(it) } ?: "—"))
        val altim = num(j, "altim")?.let { if (it > 100) it * 0.02953 else it }
        if (altim != null) {
            sb.append("Altimeter %.2f inHg\n".format(altim))
            if (t != null) {
                // Pressure altitude, then 120 ft per degree warmer than standard.
                val elev = a.elevation.toDouble()
                val pa = elev + (29.92 - altim) * 1000
                val da = pa + 120 * (t - (15 - 2 * elev / 1000))
                sb.append("Density altitude %,d ft%s\n".format(Math.round(da).toInt(), if (da > elev + 2000) "  ⚠️" else ""))
            }
        }
        sb.append("\nMETAR\n${m.raw}")
        taf?.let { sb.append("\n\nTAF\n$it") }
        return sb.toString()
    }

    /** Each runway end with its headwind and crosswind in the current wind. */
    private fun runways(apt: JSONObject?, m: AviationData.Metar?): String {
        val sb = StringBuilder()
        val rwys = apt?.optJSONArray("runways") ?: JSONArray()
        val j = m?.json
        val wdirTrue = j?.opt("wdir")?.toString()?.toDoubleOrNull()
        val wspd = num(j, "wspd") ?: 0.0
        val gust = num(j, "wgst")
        val variation = Nav.variation(a.lat, a.lon)
        var best: Pair<String, Double>? = null
        for (i in 0 until rwys.length()) {
            val r = rwys.optJSONObject(i) ?: continue
            val id = r.optString("id")
            sb.append("RWY $id  ${r.optString("dimension").replace("x", "×")} ft  ${surface(r.optString("surface"))}\n")
            if (wdirTrue == null || wspd <= 0) continue
            for (end in id.split('/')) {
                val num = end.takeWhile { it.isDigit() }.toIntOrNull() ?: continue
                val angle = Math.toRadians(wdirTrue - variation - num * 10.0)
                val head = wspd * Math.cos(angle)
                val cross = wspd * Math.sin(angle)
                val g = gust?.let { " (gust X %.0f)".format(Math.abs(it * Math.sin(angle))) } ?: ""
                sb.append("   %-4s %s %2.0f kt  X %2.0f kt %s%s\n".format(
                    end, if (head >= 0) "↑head" else "↓TAIL", Math.abs(head), Math.abs(cross), if (cross >= 0) "R" else "L", g,
                ))
                if (best == null || head > best.second) best = end to head
            }
        }
        best?.let { sb.append("\n✈ Best into the wind: RWY ${it.first}\n") }
        val freqs = apt?.opt("freqs")
        val list = when (freqs) {
            is JSONArray -> (0 until freqs.length()).mapNotNull { i -> freqs.optJSONObject(i)?.let { "${it.optString("type")}  ${it.optString("freq")}" } }
            is String -> freqs.split(';').filter { it.isNotBlank() }.map { it.replace(',', ' ').trim() }
            else -> emptyList()
        }
        if (list.isNotEmpty()) sb.append("\n${act.getString(R.string.apt_freqs)}\n").append(list.joinToString("\n"))
        apt?.optString("tower")?.takeIf { it.isNotEmpty() && it != "null" }?.let { sb.append("\nTower: ${if (it == "T") "yes" else it}") }
        if (sb.isEmpty()) sb.append("—")
        return sb.toString().trim()
    }

    private fun surface(s: String) = when (s.uppercase()) {
        "A" -> "asphalt"
        "C" -> "concrete"
        "G" -> "grass"
        "T" -> "turf"
        "D" -> "dirt"
        else -> s.lowercase()
    }

    // ---- charts and procedures ----

    /** The FAA Chart Supplement pages, from the phone when packed; the web as a last resort. */
    private fun supplement() {
        act.lifecycleScope.launch {
            val pages = withContext(Dispatchers.IO) { OfflinePack.supplement(act, a.ident, a.icao) }
            if (pages.isEmpty()) {
                open("https://www.airnav.com/airport/${a.icao.ifEmpty { a.ident }}")
                return@launch
            }
            fun show(i: Int) {
                val f = pages[i]
                val item = VaultItem("cs:" + f.name, "${a.ident} Chart Supplement ${i + 1}", f.absolutePath, "application/pdf", f.length(), f.lastModified(), null)
                VaultStore.viewOnly(item)
                act.startActivity(Intent(act, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
            }
            if (pages.size == 1) show(0) else MaterialAlertDialogBuilder(act)
                .setTitle("${a.ident} · Chart Supplement")
                .setItems(pages.indices.map { "Page ${it + 1}" }.toTypedArray()) { _, i -> show(i) }
                .show()
        }
    }

    private fun plates() {
        val wait = Toast.makeText(act, R.string.apt_plates_loading, Toast.LENGTH_LONG)
        wait.show()
        act.lifecycleScope.launch {
            val res = withContext(Dispatchers.IO) { AviationData.plates(act, a.ident) }
            wait.cancel()
            if (res == null) {
                Toast.makeText(act, R.string.apt_plates_fail, Toast.LENGTH_LONG).show()
                return@launch
            }
            val (cycle, list) = res
            if (list.isEmpty()) {
                Toast.makeText(act, R.string.apt_no_plates, Toast.LENGTH_LONG).show()
                return@launch
            }
            val order = listOf("APD", "IAP", "DP", "ODP", "STAR", "MIN", "HOT", "LAH")
            val sorted = list.sortedBy { order.indexOf(it.code).let { i -> if (i < 0) 99 else i } }
            MaterialAlertDialogBuilder(act)
                .setTitle("${a.ident} · cycle $cycle")
                .setItems(sorted.map { "${it.code}  ${it.name}" }.toTypedArray()) { _, i -> openPlate(cycle, sorted[i]) }
                .show()
        }
    }

    private fun openPlate(cycle: String, p: AviationData.Plate) {
        act.lifecycleScope.launch {
            val f: File? = withContext(Dispatchers.IO) { AviationData.platePdf(act, cycle, p.pdf) }
            if (f == null) {
                Toast.makeText(act, R.string.apt_plates_fail, Toast.LENGTH_LONG).show()
                return@launch
            }
            // Opened in the reader, so the pen and notes work on plates too.
            val item = VaultItem("plate:" + p.pdf, "${a.ident} ${p.name}", f.absolutePath, "application/pdf", f.length(), f.lastModified(), null)
            VaultStore.viewOnly(item)
            act.startActivity(Intent(act, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
        }
    }
}
