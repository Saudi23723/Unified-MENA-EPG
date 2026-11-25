package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The weather for the whole route, read the way a briefer gives it: what the flight looks like at a
 * glance, then the warnings that touch the line, the fields along it with their reports and
 * forecasts, the winds at the planned level, and what the pilot reports say. Not an official
 * briefing — that is 1800wxbrief.com — but everything needed to decide before calling for one.
 */
class BriefingActivity : BaseActivity() {
    override val alwaysDark = true

    private lateinit var plan: FlightPlan
    private lateinit var body: LinearLayout
    private var airports: List<AviationData.Airport> = emptyList()

    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = EfbUi.BG
        window.navigationBarColor = EfbUi.BG
        plan = FlightPlan.load(this)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(EfbUi.BG) }
        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0xFF121820.toInt()); setPadding(dp(6), dp(8), dp(14), dp(8))
        }
        head.addView(TextView(this).apply {
            text = "✕"; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(dp(42), dp(40)); setOnClickListener { finish() }
        })
        head.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(EfbUi.text(this@BriefingActivity, "WEATHER BRIEFING", 11f, EfbUi.DIM, bold = true).apply { letterSpacing = 0.14f })
            addView(EfbUi.text(this@BriefingActivity, plan.points.joinToString(" → ") { it.id }.ifEmpty { "no route" }, 16f, EfbUi.TEXT, bold = true).apply { maxLines = 1 })
        }, LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(TextView(this).apply {
            text = "⟳"; textSize = 20f; setTextColor(EfbUi.ACCENT); gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(dp(44), dp(40)); setOnClickListener { load() }
        })
        root.addView(head)
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(6), dp(12), dp(26)) }
        root.addView(ScrollView(this).apply { addView(body) }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            root.setPadding(0, bars.top, 0, bars.bottom); ins
        }
        load()
    }

    private fun card(): LinearLayout = EfbUi.card(this).also { body.addView(it) }
    private fun head(t: String) = body.addView(EfbUi.text(this, t.uppercase(), 12f, EfbUi.DIM, bold = true)
        .apply { letterSpacing = 0.07f; setPadding(dp(4), dp(18), dp(4), dp(6)) })

    /** The fields to brief: every point of the route that is an airport, plus any field within 10 nm of the line. */
    private fun along(): List<AviationData.Airport> {
        val out = LinkedHashMap<String, AviationData.Airport>()
        for (p in plan.points) airports.firstOrNull { it.icao == p.id || it.ident == p.id }?.let { out[it.ident] = it }
        if (plan.points.size >= 2) for (i in 1 until plan.points.size) {
            val a = plan.points[i - 1]; val b = plan.points[i]
            val d = Nav.distanceNm(a.lat, a.lon, b.lat, b.lon)
            val steps = (d / 15).toInt().coerceIn(1, 20)
            for (k in 0..steps) {
                val f = k.toDouble() / steps
                val lat = a.lat + (b.lat - a.lat) * f; val lon = a.lon + (b.lon - a.lon) * f
                airports.filter { Nav.distanceNm(lat, lon, it.lat, it.lon) < 10 }
                    .sortedBy { Nav.distanceNm(lat, lon, it.lat, it.lon) }.take(2)
                    .forEach { out.putIfAbsent(it.ident, it) }
            }
        }
        return out.values.take(14)
    }

    private fun load() {
        body.removeAllViews()
        if (plan.points.size < 2) {
            body.addView(EfbUi.text(this, "No route yet. Put one in the flight plan first, then come back.", 15f, EfbUi.TEXT)
                .apply { setPadding(dp(6), dp(24), dp(6), 0) })
            return
        }
        body.addView(EfbUi.text(this, "Reading the weather…", 15f, EfbUi.DIM).apply { setPadding(dp(6), dp(20), dp(6), 0) })
        lifecycleScope.launch {
            if (airports.isEmpty()) airports = withContext(Dispatchers.IO) { try { AviationData.airports(this@BriefingActivity) } catch (e: Exception) { emptyList() } }
            val fields = along()
            val lats = plan.points.map { it.lat }; val lons = plan.points.map { it.lon }
            val data = withContext(Dispatchers.IO) {
                val metars = try { AviationData.metars(lats.min() - 1, lons.min() - 1, lats.max() + 1, lons.max() + 1) } catch (e: Exception) { emptyList() }
                val tafs = HashMap<String, String>()
                for (f in fields.take(8)) {
                    val st = f.icao.ifEmpty { if (f.ident.length == 3) "K" + f.ident else f.ident }
                    try { AviationData.taf(st)?.let { tafs[st] = it } } catch (e: Exception) { }
                }
                val areas = try { AviationData.airspaceWeather() } catch (e: Exception) { emptyList() }
                val tfrs = try { AviationData.tfrs() } catch (e: Exception) { emptyList() }
                val pireps = try { AviationData.pireps(lats.min() - 1.5, lons.min() - 1.5, lats.max() + 1.5, lons.max() + 1.5) } catch (e: Exception) { emptyList() }
                plan.points.let { p -> Winds.forecast(this@BriefingActivity, p.sumOf { it.lat } / p.size, p.sumOf { it.lon } / p.size, plan.altitude) }
                val fb = try { AviationData.windsAloft(6) } catch (e: Exception) { "" }
                Triple(metars, tafs, listOf(areas, tfrs, pireps, listOf(fb)))
            }
            @Suppress("UNCHECKED_CAST")
            val metars = data.first
            val tafs = data.second
            @Suppress("UNCHECKED_CAST")
            val areas = data.third[0] as List<AviationData.Area>
            @Suppress("UNCHECKED_CAST")
            val tfrs = data.third[1] as List<AviationData.Area>
            @Suppress("UNCHECKED_CAST")
            val pireps = data.third[2] as List<AviationData.Pirep>
            val fb = (data.third[3].firstOrNull() as? String).orEmpty()
            body.removeAllViews()
            summary(fields, metars, areas, tfrs)
            hazards(areas, tfrs)
            minimumsCard(fields, metars)
            // Worst first: a field that breaks a limit or is IFR leads, a quiet one comes last.
            val ranked = fields.sortedByDescending { f -> severity(metars.firstOrNull { it.station == stationOf(f) }) }
            conditions(ranked, metars, tafs)
            winds(fb)
            pilotReports(pireps)
            footer()
        }
    }

    /** Anything whose shape crosses the route line, walked a mile at a time. */
    private fun onRoute(list: List<AviationData.Area>): List<AviationData.Area> {
        val hit = LinkedHashSet<AviationData.Area>()
        for (i in 1 until plan.points.size) {
            val a = plan.points[i - 1]; val b = plan.points[i]
            val steps = (Nav.distanceNm(a.lat, a.lon, b.lat, b.lon)).toInt().coerceIn(1, 220)
            for (k in 0..steps) {
                val f = k.toDouble() / steps
                val lat = a.lat + (b.lat - a.lat) * f; val lon = a.lon + (b.lon - a.lon) * f
                list.filter { it.contains(lat, lon) }.forEach { hit.add(it) }
            }
        }
        return hit.toList()
    }

    private fun summary(fields: List<AviationData.Airport>, metars: List<AviationData.Metar>,
                        areas: List<AviationData.Area>, tfrs: List<AviationData.Area>) {
        val onLine = onRoute(areas)
        val tfrOn = onRoute(tfrs)
        val cats = fields.mapNotNull { f -> metars.firstOrNull { it.station == f.icao.ifEmpty { "K" + f.ident } }?.category }
        val worst = when {
            cats.contains("LIFR") -> "LIFR"; cats.contains("IFR") -> "IFR"
            cats.contains("MVFR") -> "MVFR"; cats.isNotEmpty() -> "VFR"; else -> "—"
        }
        val bad = worst == "IFR" || worst == "LIFR"
        val c = card()
        c.addView(EfbUi.text(this, if (bad || tfrOn.isNotEmpty()) "⚠  Look carefully" else if (worst == "MVFR" || onLine.isNotEmpty()) "Worth a careful read" else "✓  Looks flyable",
            22f, if (bad || tfrOn.isNotEmpty()) 0xFFFF453A.toInt() else if (worst == "MVFR" || onLine.isNotEmpty()) 0xFFFFB020.toInt() else 0xFF30D158.toInt(), bold = true))
        c.addView(EfbUi.text(this, listOf(
            "Worst field on the route: $worst",
            if (tfrOn.isEmpty()) "No TFR on the line" else "${tfrOn.size} TFR on the line",
            if (onLine.isEmpty()) "No SIGMET or AIRMET on the line" else "${onLine.size} SIGMET/AIRMET on the line",
            "%,d ft planned · %.0f nm".format(plan.altitude, plan.summary().dist),
        ).joinToString("\n"), 13.5f, EfbUi.TEXT).apply { setLineSpacing(0f, 1.25f); setPadding(0, dp(8), 0, 0) })
        c.addView(EfbUi.text(this, "This is not an official briefing. Get one, and the NOTAMs, before you fly.", 11f, EfbUi.DIM)
            .apply { setPadding(0, dp(10), 0, 0) })
    }

    private fun stationOf(f: AviationData.Airport) = f.icao.ifEmpty { if (f.ident.length == 3) "K" + f.ident else f.ident }

    // ---- the pilot's own limits ----
    private val lim get() = getSharedPreferences("minimums", Context.MODE_PRIVATE)
    private fun minCeiling() = lim.getInt("ceiling", 3000)
    private fun minVis() = lim.getFloat("vis", 5f)
    private fun maxWind() = lim.getInt("wind", 20)
    private fun maxGust() = lim.getInt("gust", 25)
    private fun num(f: Float) = if (f == Math.floor(f.toDouble()).toFloat()) f.toInt().toString() else f.toString()

    /** Which of the pilot's limits a report breaks, in words. */
    private fun breaches(m: AviationData.Metar?): List<String> {
        val j = m?.json ?: return emptyList()
        val out = ArrayList<String>()
        var ceil = Int.MAX_VALUE
        j.optJSONArray("clouds")?.let { a ->
            for (i in 0 until a.length()) {
                val c = a.optJSONObject(i) ?: continue
                val cover = c.optString("cover")
                val base = c.opt("base")?.toString()?.toIntOrNull() ?: continue
                if ((cover == "BKN" || cover == "OVC" || cover == "OVX") && base < ceil) ceil = base
            }
        }
        if (ceil < minCeiling()) out.add("ceiling %,d ft is under your %,d".format(ceil, minCeiling()))
        val vis = j.opt("visib")?.toString()?.replace("+", "")?.toFloatOrNull()
        if (vis != null && vis < minVis()) out.add("visibility " + num(vis) + " sm is under your " + num(minVis()))
        val w = j.opt("wspd")?.toString()?.toIntOrNull()
        if (w != null && w > maxWind()) out.add("wind " + w + " kt is over your " + maxWind())
        val g = j.opt("wgst")?.toString()?.toIntOrNull()
        if (g != null && g > maxGust()) out.add("gusts " + g + " kt are over your " + maxGust())
        return out
    }

    private fun severity(m: AviationData.Metar?): Int {
        if (m == null) return 1
        val cat = when (m.category) { "LIFR" -> 40; "IFR" -> 30; "MVFR" -> 15; else -> 0 }
        return cat + breaches(m).size * 10
    }

    private fun minimumsCard(fields: List<AviationData.Airport>, metars: List<AviationData.Metar>) {
        head("Your minimums")
        val c = card()
        c.addView(EfbUi.text(this, "Ceiling at least %,d ft · visibility at least %s sm · wind up to %d kt · gusts up to %d kt".format(
            minCeiling(), num(minVis()), maxWind(), maxGust()), 13.5f, EfbUi.TEXT))
        var any = false
        for (f in fields) {
            val br = breaches(metars.firstOrNull { it.station == stationOf(f) })
            if (br.isNotEmpty()) {
                any = true
                c.addView(EfbUi.text(this, "✗ " + stationOf(f) + ": " + br.joinToString("; "), 13.5f, 0xFFFF453A.toInt(), bold = true).apply { setPadding(0, dp(6), 0, 0) })
            }
        }
        if (!any) c.addView(EfbUi.text(this, "✓ No field on the route breaks them in the latest reports.", 13.5f, 0xFF30D158.toInt()).apply { setPadding(0, dp(6), 0, 0) })
        c.addView(EfbUi.text(this, "Edit your limits", 13.5f, 0xFF4FA3FF.toInt(), bold = true).apply {
            setPadding(0, dp(10), 0, 0)
            setOnClickListener { editLimits() }
        })
    }

    private fun editLimits() {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(8), dp(20), 0) }
        fun field(label: String, value: String): android.widget.EditText {
            box.addView(TextView(this).apply { text = label; textSize = 12f })
            return android.widget.EditText(this).apply {
                setText(value); inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
                box.addView(this)
            }
        }
        val c = field("Lowest ceiling (ft)", minCeiling().toString())
        val v = field("Lowest visibility (sm)", num(minVis()))
        val w = field("Highest wind (kt)", maxWind().toString())
        val g = field("Highest gusts (kt)", maxGust().toString())
        android.app.AlertDialog.Builder(this).setTitle("Your minimums").setView(box)
            .setPositiveButton("Save") { _, _ ->
                lim.edit().putInt("ceiling", c.text.toString().toIntOrNull() ?: 3000).putFloat("vis", v.text.toString().toFloatOrNull() ?: 5f)
                    .putInt("wind", w.text.toString().toIntOrNull() ?: 20).putInt("gust", g.text.toString().toIntOrNull() ?: 25).apply()
                load()
            }.setNegativeButton("Cancel", null).show()
    }

    private fun hazards(areas: List<AviationData.Area>, tfrs: List<AviationData.Area>) {
        val onLine = onRoute(tfrs) + onRoute(areas)
        head("Adverse conditions on the route")
        if (onLine.isEmpty()) { card().addView(EfbUi.text(this, "Nothing reported over the line.", 14f, 0xFF30D158.toInt())); return }
        for (a in onLine) {
            val c = card()
            c.addView(EfbUi.ltr(EfbUi.text(this, a.text.trim(), 13f, EfbUi.TEXT, mono = true)).apply { setLineSpacing(0f, 1.2f) })
            (c.background as? android.graphics.drawable.GradientDrawable)?.setStroke(dp(1), AviationData.hazardColor(a.text))
        }
    }

    private fun conditions(fields: List<AviationData.Airport>, metars: List<AviationData.Metar>, tafs: Map<String, String>) {
        head("Fields along the way")
        if (fields.isEmpty()) { card().addView(EfbUi.text(this, "No field found near the line.", 14f, EfbUi.DIM)); return }
        for (f in fields) {
            val st = f.icao.ifEmpty { if (f.ident.length == 3) "K" + f.ident else f.ident }
            val m = metars.firstOrNull { it.station == st }
            val c = card()
            val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
            top.addView(EfbUi.text(this, st, 17f, EfbUi.TEXT, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
            top.addView(EfbUi.text(this, m?.category ?: "no report", 13f,
                m?.let { AviationData.categoryColor(it.category) } ?: EfbUi.DIM, bold = true).apply {
                background = EfbUi.cardBg(this@BriefingActivity, 0xFF0F1A2E.toInt(), 8); setPadding(dp(9), dp(3), dp(9), dp(3))
            })
            c.addView(top)
            c.addView(EfbUi.text(this, f.name, 12f, EfbUi.DIM))
            m?.let { c.addView(EfbUi.ltr(EfbUi.text(this, it.raw, 12.5f, EfbUi.TEXT, mono = true)).apply { setPadding(0, dp(8), 0, 0); setLineSpacing(0f, 1.2f) }) }
            tafs[st]?.let { c.addView(EfbUi.ltr(EfbUi.text(this, it, 12f, 0xFF9AD5A0.toInt(), mono = true)).apply { setPadding(0, dp(8), 0, 0); setLineSpacing(0f, 1.2f) }) }
            // Air that is close to saturated: fog, and the carburettor's own trouble.
            val j = m?.json
            val t = j?.opt("temp")?.toString()?.toDoubleOrNull()
            val dpC = j?.opt("dewp")?.toString()?.toDoubleOrNull()
            if (t != null && dpC != null) {
                val spread = t - dpC
                c.addView(EfbUi.text(this, "Temp %.0f° · dew point %.0f° · spread %.0f°".format(t, dpC, spread) +
                    if (spread <= 3) "  — mist or fog is close" else "", 12f,
                    if (spread <= 3) 0xFFFFB020.toInt() else EfbUi.DIM).apply { setPadding(0, dp(6), 0, 0) })
            }
        }
    }

    private fun winds(fb: String) {
        head("Winds aloft at ${"%,d".format(plan.altitude)} ft")
        val c = card()
        if (fb.isBlank()) { c.addView(EfbUi.text(this, "No forecast available right now.", 14f, EfbUi.DIM)); return }
        var any = false
        for (i in 1 until plan.points.size) {
            val a = plan.points[i - 1]; val b = plan.points[i]
            val w = Winds.triple(this, (a.lat + b.lat) / 2, (a.lon + b.lon) / 2, plan.altitude)
                ?: AviationData.windAt(fb, (a.lat + b.lat) / 2, (a.lon + b.lon) / 2, plan.altitude) ?: continue
            any = true
            val tc = Nav.bearingTrue(a.lat, a.lon, b.lat, b.lon)
            val rel = Math.toRadians(w.first - tc)
            val head = -Math.cos(rel) * w.second
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR; setPadding(0, dp(4), 0, dp(4)) }
            row.addView(EfbUi.text(this, "${a.id} → ${b.id}", 14f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, "%03d/%d".format(w.first, w.second) + (w.third?.let { "  %+d°C".format(it) } ?: ""), 13.5f, EfbUi.ACCENT, mono = true))
            row.addView(EfbUi.text(this, (if (head >= 0) "  ↑%.0f" else "  ↓%.0f").format(Math.abs(head)), 13.5f,
                if (head >= 0) 0xFF30D158.toInt() else 0xFFFF9F0A.toInt(), bold = true, mono = true))
            c.addView(row)
        }
        if (!any) c.addView(EfbUi.text(this, "No station near enough to the route.", 14f, EfbUi.DIM))
        else c.addView(EfbUi.text(this, "↑ tailwind component · ↓ headwind component", 11f, EfbUi.DIM).apply { setPadding(0, dp(8), 0, 0) })
    }

    private fun pilotReports(pireps: List<AviationData.Pirep>) {
        if (pireps.isEmpty()) return
        head("What pilots are reporting")
        val c = card()
        for (p in pireps.take(12)) c.addView(EfbUi.ltr(EfbUi.text(this, p.raw.trim(), 12f, EfbUi.TEXT, mono = true))
            .apply { setPadding(0, dp(4), 0, dp(4)); setLineSpacing(0f, 1.15f) })
    }

    private fun footer() {
        val b = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(18), 0, 0) }
        fun btn(t: String, go: () -> Unit) = b.addView(TextView(this).apply {
            text = t; textSize = 14.5f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            typeface = EfbUi.MEDIUM
            background = EfbUi.cardBg(this@BriefingActivity, 0xFF1F6FEB.toInt(), 12)
            setPadding(dp(10), dp(14), dp(10), dp(14))
            setOnClickListener { go() }
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        btn("📄  Official briefing and NOTAMs (1800wxbrief.com)") {
            try { startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse("https://www.1800wxbrief.com/"))) }
            catch (e: Exception) { Toast.makeText(this, "No browser", Toast.LENGTH_SHORT).show() }
        }
        btn("🌬  Wind cross-section along the route") { WindSectionActivity.open(this) }
        body.addView(b)
    }

    companion object {
        fun open(ctx: Context) = ctx.startActivity(Intent(ctx, BriefingActivity::class.java))
    }
}
