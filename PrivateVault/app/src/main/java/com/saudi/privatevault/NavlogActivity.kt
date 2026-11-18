package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The navigation log, laid out the way a pilot briefs one: a summary strip across the top, then a
 * line for every leg — where it goes, how high and how low it may safely be flown, the heading to
 * hold, the wind, the ground speed, the time and the fuel. The climb and the descent are their own
 * lines. A tap on a line flies it, goes direct to its end, takes it out, or stamps the time overhead.
 */
class NavlogActivity : BaseActivity() {
    override val alwaysDark = true

    private lateinit var plan: FlightPlan
    private lateinit var profile: AircraftProfile
    private lateinit var root: LinearLayout
    private lateinit var body: LinearLayout
    private var result: Navlog.Result? = null
    private var airports: List<AviationData.Airport> = emptyList()
    private val atos = HashMap<String, String>()
    /** What the pilot writes in as the flight goes: the actual ground speed, times and fuel. */
    private val actual = HashMap<String, String>()
    private var mora = true
    /** The points this log is built from — the route, or the single Direct-To leg. */
    private var pts: List<FlightPlan.Waypoint> = emptyList()
    private val prefs by lazy { VaultLock.prefs(this) }
    // What the GPS says, while the log is open: where we are, how fast, and which fix is next.
    private var fix: android.location.Location? = null
    private var live: TextView? = null
    private var nearest = Double.MAX_VALUE
    private var activeLeg = 0

    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = 0xFF0F141A.toInt()
        window.navigationBarColor = 0xFF0F141A.toInt()
        plan = FlightPlan.load(this)
        profile = AircraftProfile.current(this)
        mora = VaultLock.prefs(this).getBoolean("nav_mora", true)
        loadActuals()
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF0F141A.toInt()); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val scroll = ScrollView(this).apply { addView(body); isFillViewport = true }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            root.setPadding(0, bars.top, 0, bars.bottom)
            ins
        }
        lifecycleScope.launch {
            airports = withContext(Dispatchers.IO) { try { AviationData.airports(this@NavlogActivity) } catch (e: Exception) { emptyList() } }
            rebuild()
        }
        rebuild()
    }

    private fun elevOf(w: FlightPlan.Waypoint): Double? =
        airports.firstOrNull { it.icao == w.id || it.ident == w.id }?.elevation?.toDouble()

    private fun compute(): Navlog.Result = Navlog.build(
        pts, plan.altitude, profile,
        { i -> plan.legWinds[i]?.let { it.first to it.second } ?: (plan.windDir to plan.windKt) },
        plan.fuelOnBoard, plan.reserveMin,
        pts.firstOrNull()?.let { elevOf(it) }, pts.lastOrNull()?.let { elevOf(it) }, mora,
    )

    /**
     * The points the log is built from. Normally the route the pilot typed. But when they have
     * gone Direct-To without a route entered, Direct-To *is* the flight: the log is then the one
     * leg from where the aeroplane stands to that point, which is what the pilot asked for and
     * what every other electronic flight bag shows them.
     */
    private fun logPoints(): List<FlightPlan.Waypoint> {
        if (plan.points.size >= 2) return plan.points
        val to = plan.direct ?: return plan.points
        val from = plan.points.firstOrNull() ?: directStart() ?: return plan.points
        if (Nav.distanceNm(from.lat, from.lon, to.lat, to.lon) < 0.3) return plan.points
        return listOf(from, to)
    }

    /**
     * Where a Direct-To leg is measured from. The map writes this down the moment Direct-To is
     * pressed — the aeroplane if the GPS has it, else the middle of the chart that was on screen —
     * so the log has a starting point even where the phone will not give one now. Failing that,
     * the live fix, the last position the map saw, or whatever the phone still remembers.
     */
    private fun directStart(): FlightPlan.Waypoint? {
        val id = prefs.getString("dct_from_id", null)
        val lat = prefs.getFloat("dct_from_lat", 0f).toDouble()
        val lon = prefs.getFloat("dct_from_lon", 0f).toDouble()
        if (id != null && (lat != 0.0 || lon != 0.0)) return FlightPlan.Waypoint(id, lat, lon)
        here()?.let { return FlightPlan.Waypoint("PPOS", it.latitude, it.longitude) }
        val la = prefs.getFloat("last_lat", 0f).toDouble()
        val lo = prefs.getFloat("last_lon", 0f).toDouble()
        if (la != 0.0 || lo != 0.0) return FlightPlan.Waypoint("PPOS", la, lo)
        return null
    }

    /** Where the aeroplane is: the live fix if the log has one, else the last the phone remembers. */
    @android.annotation.SuppressLint("MissingPermission")
    private fun here(): android.location.Location? {
        fix?.let { return it }
        if (androidx.core.content.ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION)
            != android.content.pm.PackageManager.PERMISSION_GRANTED) return null
        val m = getSystemService(android.location.LocationManager::class.java) ?: return null
        return listOf(
            android.location.LocationManager.GPS_PROVIDER,
            android.location.LocationManager.NETWORK_PROVIDER,
            android.location.LocationManager.PASSIVE_PROVIDER,
        ).mapNotNull { p -> try { m.getLastKnownLocation(p) } catch (e: Exception) { null } }
            .maxByOrNull { it.time }
    }

    private fun rebuild() {
        pts = logPoints()
        val r = compute()
        result = r
        for (row in r.rows) atos[key(row)]?.let { row.atoUtc = it }
        body.removeAllViews()
        body.addView(header())
        if (pts.size < 2) {
            val why = if (plan.direct != null)
                "Going direct to ${plan.direct!!.id}, but the log needs a point to measure the leg from and nothing has given one yet \u2014 no GPS fix, and the map has not been opened since. Open the map once, or type a route with ${plan.direct!!.id} on the end of it."
            else "No route yet. Open the map, tap Edit on the flight plan and type one — for example KBVU KHND KVGT. Or go Direct-To a point and the log will show that leg."
            body.addView(EfbUi.text(this, why, 15f, EfbUi.TEXT)
                .apply { setPadding(dp(20), dp(30), dp(20), dp(20)) })
            body.addView(actionRow())
            return
        }
        body.addView(flightSummary(r))
        wbLine(r)?.let { body.addView(it) }
        live = EfbUi.text(this, "", 13f, 0xFF64D2FF.toInt(), bold = true).apply {
            setPadding(dp(14), dp(8), dp(14), dp(4)); visibility = View.GONE
        }
        body.addView(live)
        paintLive()
        val table = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        table.addView(columns())
        table.addView(departureRow())
        for (row in r.rows) {
            table.addView(View(this).apply { setBackgroundColor(0x14FFFFFF) }, LinearLayout.LayoutParams(-1, 1))
            table.addView(rowView(row, r))
        }
        table.addView(totalRow(r))
        body.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(table) })
        body.addView(EfbUi.text(this, "a tap on a line opens the leg · a tap under ACT stamps the time overhead · hold ACT or GS to type the real figure in", 10.5f, 0xFF6E7681.toInt())
            .apply { setPadding(dp(14), dp(6), dp(14), dp(2)) })
        windsBlock()?.let { body.addView(it) }
        body.addView(summaryBoxes(r))
        body.addView(airportDetails(r))
        if (r.warnings.isNotEmpty()) {
            val warn = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(6)) }
            for (w in r.warnings) warn.addView(EfbUi.text(this, "⚠  $w", 12.5f, 0xFFFFB020.toInt()).apply { setPadding(0, dp(3), 0, dp(3)) })
            body.addView(warn)
        }
        body.addView(EfbUi.text(this, "Winds are the forecast you loaded; the performance figures are the profile you typed. " +
            "Lowest safe altitudes are worked out from the terrain within 4 nm of the line and are not the charted MEA or MOCA.",
            10.5f, 0xFF6E7681.toInt()).apply { setPadding(dp(14), dp(10), dp(14), dp(4)) })
        body.addView(actionRow())
    }

    private fun key(r: Navlog.Row) = "${r.from.id}>${r.to.id}#${r.index}"

    /** The figures written in while flying are kept with the plan, so they survive the screen closing. */
    private fun saveActuals() {
        val o = org.json.JSONObject()
        for ((k, v) in atos) o.put("a|$k", v)
        for ((k, v) in actual) o.put("v|$k", v)
        VaultLock.prefs(this).edit().putString("navlog_actuals", o.toString()).apply()
    }

    private fun loadActuals() {
        atos.clear(); actual.clear()
        try {
            val o = org.json.JSONObject(VaultLock.prefs(this).getString("navlog_actuals", "{}")!!)
            for (k in o.keys()) {
                if (k.startsWith("a|")) atos[k.drop(2)] = o.getString(k)
                else if (k.startsWith("v|")) actual[k.drop(2)] = o.getString(k)
            }
        } catch (e: Exception) { }
    }

    /** One figure typed in by hand, against one leg of the log. */
    private fun typeIn(r: Navlog.Row, what: String, title: String) {
        val k = if (what == "ato") key(r) else "${key(r)}|$what"
        val input = EditText(this).apply {
            setText(if (what == "ato") atos[k] ?: "" else actual[k] ?: "")
            setSingleLine(); setPadding(dp(20), dp(12), dp(20), dp(12))
        }
        MaterialAlertDialogBuilder(this)
            .setTitle("$title · ${r.from.id} → ${r.to.id}")
            .setView(input)
            .setPositiveButton(R.string.ok) { _, _ ->
                val v = input.text.toString().trim()
                if (what == "ato") { if (v.isEmpty()) atos.remove(k) else atos[k] = v }
                else { if (v.isEmpty()) actual.remove(k) else actual[k] = v }
                saveActuals(); rebuild()
            }
            .setNeutralButton("Clear") { _, _ ->
                if (what == "ato") atos.remove(k) else actual.remove(k)
                saveActuals(); rebuild()
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    /**
     * The aeroplane's weight and where its balance sits, at take-off and again on landing with the
     * log's own fuel burn taken out — the two numbers a loaded aeroplane is flown by.
     */
    private fun wbLine(r: Navlog.Result): View? {
        val list = Aircraft.all(this)
        if (list.isEmpty()) return null
        val ac = list.getOrNull(VaultLock.prefs(this).getInt("wb_current", 0).coerceIn(0, list.size - 1)) ?: return null
        val (to, ld) = try { ac.compute(r.fuelGal) } catch (e: Exception) { return null }
        if (to.weight <= 0 || to.weight.isNaN()) return null
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xFF121820.toInt())
            setPadding(dp(14), dp(8), dp(14), dp(8))
        }
        fun cellOf(label: String, w: Double, cg: Double, ok: Boolean) = row.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(EfbUi.text(this@NavlogActivity, label, 9.5f, 0xFF8FA3B8.toInt(), bold = true).apply { letterSpacing = 0.1f })
            addView(EfbUi.text(this@NavlogActivity, "%,.0f lb · CG %.1f".format(w, cg), 14f,
                if (ok) 0xFF30D158.toInt() else 0xFFFF453A.toInt(), bold = true))
        }, LinearLayout.LayoutParams(0, -2, 1f))
        cellOf("TAKE-OFF", to.weight, to.cg, to.inside)
        cellOf("ON LANDING", ld.weight, ld.cg, ld.inside)
        row.addView(TextView(this).apply {
            text = "✎"; textSize = 16f; setTextColor(EfbUi.ACCENT); gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(dp(40), -2)
            setOnClickListener {
                startActivity(Intent(this@NavlogActivity, WeightBalanceActivity::class.java)
                    .putExtra(WeightBalanceActivity.EXTRA_BURN, r.fuelGal))
            }
        })
        return row
    }

    /** The live line: how far to the next fix, the speed over the ground now, and when we land. */
    private fun paintLive() {
        val v = live ?: return
        val l = fix
        val r = result
        if (l == null || r == null || r.rows.isEmpty()) { v.visibility = View.GONE; return }
        val leg = r.rows.getOrNull(activeLeg) ?: r.rows.last()
        val d = Nav.distanceNm(l.latitude, l.longitude, leg.to.lat, leg.to.lon)
        val gs = if (l.hasSpeed()) l.speed * 1.943844 else 0.0
        val brg = Nav.magnetic(Nav.bearingTrue(l.latitude, l.longitude, leg.to.lat, leg.to.lon), l.latitude, l.longitude)
        val rest = r.rows.drop(activeLeg + 1).sumOf { it.distNm } + d
        val mins = if (gs > 25) rest / gs * 60 else Double.NaN
        v.visibility = View.VISIBLE
        v.text = "▸ ${leg.to.id}  ${Nav.deg(brg)}M  %.1f nm".format(d) +
            (if (gs > 1) "   ·   %d kt".format(Math.round(gs).toInt()) else "") +
            (if (!mins.isNaN()) "   ·   lands ${plan.clock(mins)}" else "")
    }

    /** Overhead the fix: the time is stamped and the log moves on by itself, as a GPS does. */
    private fun onFix(l: android.location.Location) {
        fix = l
        val r = result ?: return
        val leg = r.rows.getOrNull(activeLeg) ?: return
        val d = Nav.distanceNm(l.latitude, l.longitude, leg.to.lat, leg.to.lon)
        val passed = d <= 0.5 || (nearest <= 1.5 && d > nearest + 0.15)
        nearest = minOf(nearest, d)
        if (passed) {
            atos.getOrPut(key(leg)) { Navlog.utcNow() }
            nearest = Double.MAX_VALUE
            if (activeLeg + 1 < r.rows.size) activeLeg++
            rebuild()
        } else paintLive()
    }

    private val gps = android.location.LocationListener { l -> onFix(l) }

    @android.annotation.SuppressLint("MissingPermission")
    private fun startGps() {
        if (androidx.core.content.ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION)
            != android.content.pm.PackageManager.PERMISSION_GRANTED) return
        val m = getSystemService(android.location.LocationManager::class.java) ?: return
        try {
            m.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)
                ?.takeIf { System.currentTimeMillis() - it.time < 120000 }?.let { fix = it; paintLive() }
            m.requestLocationUpdates(android.location.LocationManager.GPS_PROVIDER, 1000L, 0f, gps, mainLooper)
        } catch (e: Exception) { }
    }

    private fun stopGps() {
        try { getSystemService(android.location.LocationManager::class.java)?.removeUpdates(gps) } catch (e: Exception) { }
    }

    private fun header(): View {
        val h = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0xFF1A222D.toInt()); setPadding(dp(8), dp(8), dp(12), dp(8))
        }
        h.addView(TextView(this).apply {
            text = "✕"; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            setOnClickListener { finish() }
            layoutParams = LinearLayout.LayoutParams(dp(42), dp(40))
        })
        h.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(EfbUi.text(this@NavlogActivity, "NAVLOG", 11f, 0xFF8FA3B8.toInt(), bold = true).apply { letterSpacing = 0.14f })
            addView(EfbUi.text(this@NavlogActivity, pts.joinToString(" · ") { it.id }.ifEmpty { "no route" }, 16f, 0xFFFFFFFF.toInt(), bold = true).apply { maxLines = 1 })
        }, LinearLayout.LayoutParams(0, -2, 1f))
        h.addView(chip("${"%,d".format(plan.altitude)}'  ▾", 0xFF0077CC.toInt()) { altitudeAdvisor() })
        return h
    }

    private fun chip(t: String, color: Int, go: () -> Unit) = TextView(this).apply {
        text = t; textSize = 13f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
        typeface = EfbUi.MEDIUM
        background = EfbUi.cardBg(this@NavlogActivity, color, 8)
        setPadding(dp(12), dp(8), dp(12), dp(8))
        setOnClickListener { go() }
    }

    private fun metric(label: String, value: String, color: Int = 0xFFFFFFFF.toInt()) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        addView(EfbUi.text(this@NavlogActivity, label, 9.5f, 0xFF8FA3B8.toInt(), bold = true).apply { letterSpacing = 0.1f })
        addView(EfbUi.text(this@NavlogActivity, value, 16f, color, bold = true))
    }

    /** The head of the log: who is flying what, where, when, and on how much fuel. */
    private fun flightSummary(r: Navlog.Result): View {
        val wrap = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF141B24.toInt()) }
        val dep = pts.firstOrNull()?.id ?: ""
        val dest = pts.lastOrNull()?.id ?: ""
        val tail = Aircraft.all(this).getOrNull(VaultLock.prefs(this).getInt("wb_current", 0))?.name ?: ""
        val today = java.text.SimpleDateFormat("MMM d, yyyy", java.util.Locale.US).format(java.util.Date())
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(dp(14), dp(10), dp(14), dp(4)) }
        top.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(EfbUi.text(this@NavlogActivity, "$dep — $dest ($today)" + (if (tail.isNotEmpty()) " in $tail" else "") + "  VFR",
                13.5f, 0xFFFFFFFF.toInt(), bold = true).apply { maxLines = 2 })
            addView(EfbUi.text(this@NavlogActivity, "${profile.name} @ ${"%,d".format(plan.altitude)}'", 11.5f, 0xFF8FA3B8.toInt()))
        }, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.END
            addView(EfbUi.text(this@NavlogActivity, "Created " + java.text.SimpleDateFormat("HHmm'Z'", java.util.Locale.US)
                .apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }.format(java.util.Date()), 10f, 0xFF6E7681.toInt()))
            addView(EfbUi.text(this@NavlogActivity, if (plan.legWinds.isEmpty()) "Winds — none loaded" else "Winds loaded", 10f,
                if (plan.legWinds.isEmpty()) 0xFFFFB020.toInt() else 0xFF6E7681.toInt()))
        })
        wrap.addView(top)
        wrap.addView(summary(r))
        // The route itself, written out.
        wrap.addView(EfbUi.text(this, "Route", 9.5f, 0xFF8FA3B8.toInt(), bold = true).apply { letterSpacing = 0.09f; setPadding(dp(14), dp(6), dp(14), 0) })
        wrap.addView(EfbUi.ltr(EfbUi.text(this, pts.joinToString(" ") { it.id }, 12.5f, 0xFFD6DCE4.toInt(), mono = true))
            .apply { setPadding(dp(14), 0, dp(14), dp(10)) })
        return wrap
    }

    private fun summary(r: Navlog.Result): View {
        val s = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xFF141B24.toInt())
            setPadding(dp(14), dp(10), dp(14), dp(10))
        }
        fun add(v: View) = s.addView(v, LinearLayout.LayoutParams(0, -2, 1f))
        val comp = if (r.distNm > 0) r.rows.sumOf { x ->
            -Math.cos(Math.toRadians(x.windDir - x.tc)) * x.windKt * x.distNm
        } / r.distNm else 0.0
        add(metric("ETE", Navlog.hm(r.minutes)))
        add(metric("DISTANCE", "%.0f nm".format(r.distNm)))
        add(metric("AVG WIND", "%d kt %s".format(Math.abs(Math.round(comp).toInt()), if (comp >= 0) "tail" else "head"),
            if (comp >= 0) 0xFF30D158.toInt() else 0xFFFF9F0A.toInt()))
        add(metric("ETD", plan.etdMin?.let { "%02d:%02d".format(it / 60, it % 60) } ?: "now"))
        add(metric("ETA", plan.clock(r.minutes), 0xFF64D2FF.toInt()))
        add(metric("FLIGHT FUEL", "%.1f g".format(r.fuelGal), if (r.reserveKept) 0xFFFFFFFF.toInt() else 0xFFFF453A.toInt()))
        add(metric("TAXI FUEL", "%.1f g".format(profile.taxiGal)))
        return android.widget.HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(s) }
    }

    private fun cell(t: String, w: Int, color: Int = 0xFFE6EAF0.toInt(), bold: Boolean = false, size: Float = 12f,
                     mono: Boolean = true, align: Int = Gravity.CENTER): TextView =
        TextView(this).apply {
            text = t; textSize = size; setTextColor(color); gravity = align
            if (mono) typeface = android.graphics.Typeface.MONOSPACE
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(dp(2), 0, dp(2), 0)
            layoutParams = LinearLayout.LayoutParams(dp(w), -2)
        }

    // The columns of a navigation log, in the order and the grouping a printed one uses.
    private val W_WPT = 104; private val W_AWY = 54; private val W_HDG = 44; private val W_CRS = 44
    private val W_ALT = 52; private val W_CMP = 40; private val W_WIND = 62; private val W_ISA = 40
    private val W_TAS = 38; private val W_GS = 38; private val W_DL = 42; private val W_DR = 42
    private val W_TL = 42; private val W_TR = 42; private val W_ETE = 48; private val W_ACT = 48

    /** Two lines of heading: the group above, the column itself below, as the paper form prints it. */
    private fun columns(): View {
        val wrap = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF25303F.toInt()) }
        fun line(cells: List<Pair<String, Int>>, size: Float, color: Int) = wrap.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(8), dp(3), dp(8), dp(3))
            for ((t, w) in cells) addView(cell(t, w, color, bold = true, size = size, mono = false))
        })
        line(listOf("" to W_WPT, "" to W_AWY, "MAG" to (W_HDG + W_CRS), "" to W_ALT, "WIND" to (W_CMP + W_WIND + W_ISA),
            "SPD KT" to (W_TAS + W_GS), "DIST NM" to (W_DL + W_DR), "TIME" to (W_TL + W_TR + W_ETE + W_ACT)), 9f, 0xFF7C8B9C.toInt())
        line(listOf("WAYPOINT" to W_WPT, "AIRWAY" to W_AWY, "HDG" to W_HDG, "CRS" to W_CRS, "ALT" to W_ALT,
            "CMP" to W_CMP, "DIR/SPD" to W_WIND, "ISA" to W_ISA, "TAS" to W_TAS, "GS" to W_GS,
            "LEG" to W_DL, "REM" to W_DR, "LEG" to W_TL, "REM" to W_TR, "ETE" to W_ETE, "ACT" to W_ACT), 9.5f, 0xFFB0BEC5.toInt())
        return wrap
    }

    private fun badge(p: Phase): TextView {
        val (t, c) = when (p) {
            Phase.CLIMB -> "CLB" to 0xFF0277BD.toInt()
            Phase.CRUISE -> "CRZ" to 0xFF2E7D32.toInt()
            Phase.DESCENT -> "DSC" to 0xFFEF6C00.toInt()
        }
        return TextView(this).apply {
            text = t; textSize = 9f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            typeface = EfbUi.MEDIUM
            background = EfbUi.cardBg(this@NavlogActivity, c, 3)
            setPadding(dp(4), 0, dp(4), 0)
        }
    }

    /** The first line of the log: the departure, with nothing yet flown. */
    private fun departureRow(): View {
        val p = pts.firstOrNull() ?: return View(this)
        val line = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(7), dp(8), dp(7)); setBackgroundColor(0xFF18202B.toInt())
        }
        line.addView(cell(p.id, W_WPT, 0xFFFFFFFF.toInt(), bold = true, size = 13f, align = Gravity.START))
        for (w in listOf(W_AWY, W_HDG, W_CRS, W_ALT, W_CMP, W_WIND, W_ISA, W_TAS, W_GS, W_DL)) line.addView(cell("—", w, 0xFF55606D.toInt()))
        line.addView(cell("%.1f".format(result?.distNm ?: 0.0), W_DR, 0xFF8FA3B8.toInt()))
        line.addView(cell("—", W_TL, 0xFF55606D.toInt()))
        line.addView(cell(Navlog.hm(result?.minutes ?: 0.0), W_TR, 0xFF8FA3B8.toInt()))
        line.addView(cell("-", W_ETE, 0xFF55606D.toInt()))
        line.addView(cell("", W_ACT))
        return line
    }

    /** One line: the leg into a waypoint, and everything true of it on arrival. */
    private fun rowView(r: Navlog.Row, all: Navlog.Result): View {
        val alert = r.moraFt != null && r.altFt < r.moraFt
        val line = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(6), dp(8), dp(6))
            setBackgroundColor(if (alert) 0xFF3B1818.toInt() else if (r.index % 2 == 0) 0xFF141B24.toInt() else 0xFF18202B.toInt())
            isClickable = true
            setOnClickListener { legMenu(r) }
        }
        // The waypoint, its phase badge, and the lowest safe altitude under it.
        line.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(dp(W_WPT), -2)
            addView(LinearLayout(this@NavlogActivity).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                addView(badge(r.phase))
                addView(EfbUi.text(this@NavlogActivity, if (r.virtual) "-${r.to.id}-" else r.to.id, 13f,
                    if (r.virtual) 0xFFFFD60A.toInt() else 0xFFFFFFFF.toInt(), bold = true).apply {
                    setPadding(dp(4), 0, 0, 0); maxLines = 1
                })
            })
            r.moraFt?.let { addView(EfbUi.text(this@NavlogActivity, "MORA %,d".format(it), 9f,
                if (alert) 0xFFFF453A.toInt() else 0xFF6E7681.toInt())) }
        })
        line.addView(cell("DCT", W_AWY, 0xFF8FA3B8.toInt(), size = 10.5f))
        line.addView(cell("%03d".format(Math.round(r.mh).toInt() % 360), W_HDG, 0xFF4FC3F7.toInt(), bold = true, size = 13f))
        line.addView(cell("%03d".format(Math.round(r.tc).toInt() % 360), W_CRS, 0xFF8FA3B8.toInt(), size = 11f))
        line.addView(cell("%,d".format(r.altFt), W_ALT, if (alert) 0xFFFF453A.toInt() else 0xFFE6EAF0.toInt(), bold = alert))
        // The wind as a component along the leg: a head or a tail, and how many knots of it.
        val rel = Math.toRadians(r.windDir - r.tc)
        val comp = -Math.cos(rel) * r.windKt
        line.addView(cell((if (comp >= 0) "T" else "H") + "%d".format(Math.abs(Math.round(comp).toInt())), W_CMP,
            if (comp >= 0) 0xFF30D158.toInt() else 0xFFFF9F0A.toInt(), bold = true, size = 11f))
        line.addView(cell("%03d/%d".format(r.windDir, r.windKt), W_WIND,
            if (plan.legWinds.containsKey(r.index)) 0xFFD6DCE4.toInt() else 0xFF8FA3B8.toInt(), size = 11f))
        // How far the air is from a standard day at this height: what the book's figures assume.
        val isa = plan.legWinds[r.index]?.third?.let { it - Math.round(15 - 2.0 * r.altFt / 1000).toInt() }
        line.addView(cell(isa?.let { "%+d".format(it) } ?: "—", W_ISA, 0xFF8FA3B8.toInt(), size = 11f))
        line.addView(cell("%d".format(Math.round(r.tas).toInt()), W_TAS, 0xFF8FA3B8.toInt(), size = 11f))
        val gsAct = actual["${key(r)}|gs"]
        line.addView(cell(gsAct ?: "%d".format(Math.round(r.gs).toInt()), W_GS,
            if (gsAct != null) 0xFF69F0AE.toInt() else if (r.gs < r.tas - 5) 0xFFFF9F0A.toInt() else 0xFFE6EAF0.toInt(),
            bold = true).apply { setOnLongClickListener { typeIn(r, "gs", "Ground speed flown"); true } })
        line.addView(cell("%.1f".format(r.distNm), W_DL))
        line.addView(cell("%.1f".format(r.remainNm), W_DR, 0xFF8FA3B8.toInt(), size = 11f))
        line.addView(cell(Navlog.hm(r.minutes), W_TL))
        line.addView(cell(Navlog.hm(all.minutes - r.cumMinutes), W_TR, 0xFF8FA3B8.toInt(), size = 11f))
        line.addView(cell(Navlog.hm(r.cumMinutes), W_ETE, 0xFF64D2FF.toInt()))
        line.addView(TextView(this).apply {
            text = r.atoUtc ?: "·"
            textSize = 11f; typeface = android.graphics.Typeface.MONOSPACE; gravity = Gravity.CENTER
            setTextColor(if (r.atoUtc != null) 0xFF69F0AE.toInt() else 0xFF55606D.toInt())
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(dp(2), dp(5), dp(2), dp(5))
            layoutParams = LinearLayout.LayoutParams(dp(W_ACT), -2)
            setOnClickListener {
                if (r.atoUtc == null) atos[key(r)] = Navlog.utcNow() else atos.remove(key(r))
                saveActuals(); rebuild()
            }
            setOnLongClickListener { typeIn(r, "ato", "Time over (ATO)"); true }
        })
        return line
    }

    /** The totals line that closes the table. */
    private fun totalRow(r: Navlog.Result): View = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
        setBackgroundColor(0xFF14202C.toInt()); setPadding(dp(8), dp(8), dp(8), dp(8))
        addView(cell("TOTAL", W_WPT, 0xFFFFFFFF.toInt(), bold = true, size = 12.5f, mono = false, align = Gravity.START))
        for (w in listOf(W_AWY, W_HDG, W_CRS, W_ALT, W_CMP, W_WIND, W_ISA, W_TAS, W_GS)) addView(cell("", w))
        addView(cell("%.1f".format(r.distNm), W_DL, 0xFFFFFFFF.toInt(), bold = true))
        addView(cell("", W_DR))
        addView(cell(Navlog.hm(r.minutes), W_TL, 0xFFFFFFFF.toInt(), bold = true))
        addView(cell("", W_TR))
        addView(cell(Navlog.hm(r.minutes), W_ETE, 0xFF64D2FF.toInt(), bold = true))
        addView(cell("", W_ACT))
    }

    /** The same route flown at every level, so the wind at each can be compared at a glance. */
    private fun windsBlock(): View? {
        val mid = pts.let { p -> p.sumOf { it.lat } / p.size to p.sumOf { it.lon } / p.size }
        val levels = listOf(3000, 6000, 9000, 12000)
        val found = levels.mapNotNull { a -> Winds.at(this, mid.first, mid.second, a)?.let { a to it } }
        if (found.isEmpty()) return null
        val wrap = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        wrap.addView(EfbUi.text(this, "WINDS ALOFT", 11f, 0xFF8FA3B8.toInt(), bold = true)
            .apply { letterSpacing = 0.09f; setPadding(dp(14), dp(16), dp(14), dp(6)) })
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xFF141B24.toInt())
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        val tc = Nav.bearingTrue(pts.first().lat, pts.first().lon, pts.last().lat, pts.last().lon)
        for ((alt, w) in found) {
            val rel = Math.toRadians(w.dirTrue - tc)
            val comp = -Math.cos(rel) * w.kt
            card.addView(LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
                addView(EfbUi.text(this@NavlogActivity, "%,d FT".format(alt), 10f, 0xFF8FA3B8.toInt(), bold = true))
                addView(EfbUi.text(this@NavlogActivity, "%03d/%d".format(w.dirTrue, w.kt), 13f, 0xFFE6EAF0.toInt(), bold = true, mono = true))
                addView(EfbUi.text(this@NavlogActivity, (if (comp >= 0) "tail " else "head ") + "%d kt".format(Math.abs(Math.round(comp).toInt())), 10.5f,
                    if (comp >= 0) 0xFF30D158.toInt() else 0xFFFF9F0A.toInt()))
                w.tempC?.let { addView(EfbUi.text(this@NavlogActivity, "%+d°C".format(it), 10f, 0xFF6E7681.toInt())) }
            }, LinearLayout.LayoutParams(0, -2, 1f))
        }
        wrap.addView(card)
        return wrap
    }

    /**
     * The fields at either end of the flight, as the printed log sets them out: when the aeroplane
     * is due, the weather and tower frequencies, the ground and clearance, the field's elevation,
     * and its longest runway.
     */
    private fun airportDetails(r: Navlog.Result): View {
        val wrap = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        wrap.addView(EfbUi.text(this, "AIRPORT DETAILS", 11f, 0xFF8FA3B8.toInt(), bold = true)
            .apply { letterSpacing = 0.09f; setPadding(dp(14), dp(18), dp(14), dp(6)) })
        val table = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF141B24.toInt()) }
        val w = listOf(52, 72, 60, 68, 74, 60, 60, 56, 86)
        fun row(cells: List<String>, header: Boolean) = table.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(8), dp(7), dp(8), dp(7))
            if (header) setBackgroundColor(0xFF25303F.toInt())
            for ((i, c) in cells.withIndex()) addView(cell(c, w[i],
                if (header) 0xFFB0BEC5.toInt() else 0xFFE6EAF0.toInt(), bold = header,
                size = if (header) 9.5f else 11.5f, mono = !header))
        })
        row(listOf("", "AIRPORT", "ETA", "WX", "TWR/CTAF", "CLR", "GND", "ELEV", "LONGEST"), true)
        for ((which, pt) in listOf("DEP" to pts.firstOrNull(), "DEST" to pts.lastOrNull())) {
            val p = pt ?: continue
            val a = airports.firstOrNull { it.icao == p.id || it.ident == p.id }
            val station = a?.let { it.icao.ifEmpty { if (it.ident.length == 3) "K" + it.ident else it.ident } } ?: p.id
            val fs = a?.let { apt -> try { Frequencies.forAirport(this, apt, null) } catch (e: Exception) { emptyList() } }.orEmpty()
            fun freq(vararg keys: String) = fs.firstOrNull { fr -> keys.any { fr.kind.label.contains(it, true) } }?.let { Frequencies.mhz(it.mhz) } ?: "—"
            val longest = try { Cifp.runwayEnds(this, station).values.mapNotNull { it.lengthFt }.maxOrNull() } catch (e: Exception) { null }
            row(listOf(
                which, p.id,
                if (which == "DEP") (plan.etdMin?.let { "%02d:%02d".format(it / 60, it % 60) } ?: "—") else plan.clock(r.minutes),
                freq("ATIS", "AWOS", "ASOS"), freq("Tower", "CTAF", "UNICOM"), freq("Clearance", "Delivery"), freq("Ground"),
                a?.let { "%,d".format(it.elevation) } ?: "—",
                longest?.let { "%,d".format(it) } ?: "—",
            ), false)
            table.addView(View(this).apply { setBackgroundColor(0x14FFFFFF) }, LinearLayout.LayoutParams(-1, 1))
        }
        wrap.addView(android.widget.HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(table) })
        return wrap
    }

    /** The two boxes a log is signed off with: who flew it, and the times written in after. */
    private fun summaryBoxes(r: Navlog.Result): View {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(dp(8), dp(14), dp(8), 0) }
        fun boxOf(title: String, lines: List<Pair<String, String>>) = row.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = EfbUi.cardBg(this@NavlogActivity, 0xFF141B24.toInt(), 10)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            addView(EfbUi.text(this@NavlogActivity, title, 10.5f, 0xFF8FA3B8.toInt(), bold = true).apply { letterSpacing = 0.09f })
            for ((k, v) in lines) addView(LinearLayout(this@NavlogActivity).apply {
                orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(5), 0, 0)
                addView(EfbUi.text(this@NavlogActivity, k, 12f, 0xFF8FA3B8.toInt()), LinearLayout.LayoutParams(0, -2, 1f))
                addView(EfbUi.text(this@NavlogActivity, v, 12.5f, 0xFFE6EAF0.toInt(), bold = true, mono = true))
            })
        }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(8) })
        val tail = Aircraft.all(this).getOrNull(VaultLock.prefs(this).getInt("wb_current", 0))?.name ?: "—"
        boxOf("SUMMARY & TIMES", listOf(
            "PIC" to (VaultLock.prefs(this).getString("pilot_name", "") ?: "").ifEmpty { "—" },
            "Souls on board" to (VaultLock.prefs(this).getString("icao_pob", "2") ?: "2"),
            "Tail" to tail,
            "Profile" to "${profile.name} @ ${"%,d".format(plan.altitude)}'",
            "Distance" to "%.0f nm".format(r.distNm),
            "ETD" to (plan.etdMin?.let { "%02d:%02d".format(it / 60, it % 60) } ?: "now"),
            "ETE" to Navlog.hm(r.minutes),
            "ETA" to plan.clock(r.minutes),
        ))
        boxOf("NOTES", listOf(
            "Out" to "____", "In" to "____", "Block time" to "____",
            "Off" to "____", "On" to "____", "Flight time" to "____",
            "Start" to "____", "Stop" to "____", "Hobbs time" to "____",
            "Fuel used" to "____", "Signature" to "____",
        ))
        return row
    }

    /** What can be done with one leg: fly it, go straight to its end, take it out, give it its own wind. */
    private fun legMenu(r: Navlog.Row) {
        val real = !r.virtual
        val items = ArrayList<Pair<String, () -> Unit>>()
        items.add("\u279C  Fly this leg (make ${r.to.id} the active waypoint)" to { flyLeg(r) })
        items.add("\u2197  Direct to ${r.to.id}" to {
            plan.direct = FlightPlan.Waypoint(r.to.id, r.to.lat, r.to.lon); plan.save(this); toast("Direct ${r.to.id}"); rebuild()
        })
        items.add("\uD83C\uDF2C  Wind on this leg" to { legWind(r) })
        if (real) items.add("\uFF0B  Insert a point after ${r.from.id}" to { insertAfter(r) })
        if (real && plan.points.size > 2) items.add("\u2715  Remove ${r.to.id} from the route" to { removePoint(r) })
        MaterialAlertDialogBuilder(this)
            .setTitle("${r.from.id} \u2192 ${r.to.id}")
            .setItems(items.map { it.first }.toTypedArray()) { _, i -> items[i].second() }
            .setNegativeButton(R.string.cancel, null).show()
    }

    private fun flyLeg(r: Navlog.Row) {
        val i = plan.points.indexOfFirst { it.id == r.to.id && it.lat == r.to.lat }
        if (i > 0) { plan.active = i; plan.direct = null; plan.save(this); toast("Flying ${r.from.id} → ${r.to.id}") }
        else { plan.direct = FlightPlan.Waypoint(r.to.id, r.to.lat, r.to.lon); plan.save(this); toast("Direct ${r.to.id}") }
        rebuild()
    }

    private fun removePoint(r: Navlog.Row) {
        val i = plan.points.indexOfFirst { it.id == r.to.id && it.lat == r.to.lat }
        if (i < 0) return
        plan.points.removeAt(i)
        plan.legWinds.clear()
        plan.active = plan.active.coerceIn(1, maxOf(1, plan.points.size - 1))
        plan.save(this); rebuild()
    }

    private fun legWind(r: Navlog.Row) {
        val cur = plan.legWinds[r.index]
        val input = EditText(this).apply {
            setText(cur?.let { "%03d/%d".format(it.first, it.second) } ?: "")
            hint = "240/15"; setSingleLine(); setPadding(dp(20), dp(12), dp(20), dp(12))
        }
        MaterialAlertDialogBuilder(this)
            .setTitle("Wind · ${r.from.id} → ${r.to.id}")
            .setMessage("The forecast wind on this leg at %,d ft: direction it blows from, and knots.".format(plan.altitude))
            .setView(input)
            .setPositiveButton(R.string.ok) { _, _ ->
                val n = input.text.toString().split('/', ' ', '@').mapNotNull { it.trim().toIntOrNull() }
                if (n.size >= 2) plan.legWinds[r.index] = Triple(n[0] % 361, n[1], cur?.third) else plan.legWinds.remove(r.index)
                plan.save(this); rebuild()
            }
            .setNeutralButton("Use the plan's wind") { _, _ -> plan.legWinds.remove(r.index); plan.save(this); rebuild() }
            .setNegativeButton(R.string.cancel, null).show()
    }

    /**
     * A point put into the route after this one: an airport or fix by name, a latitude and longitude,
     * or a bearing and distance from a place — KBVU009017 is 17 nm out on the 009 radial of KBVU.
     */
    private fun insertAfter(r: Navlog.Row) {
        val input = EditText(this).apply {
            hint = "KHND, 35.9/-114.8, or KBVU009017"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            setSingleLine(); setPadding(dp(20), dp(12), dp(20), dp(12))
        }
        MaterialAlertDialogBuilder(this)
            .setTitle("Insert after ${r.from.id}")
            .setMessage("An airport or fix, a latitude/longitude, or a place with a bearing and distance: KBVU009017 is 17 nm out on the 009 radial from KBVU.")
            .setView(input)
            .setPositiveButton("Insert") { _, _ ->
                val w = resolve(input.text.toString())
                if (w == null) { toast("Not found: ${input.text}"); return@setPositiveButton }
                val i = plan.points.indexOfFirst { it.id == r.from.id && it.lat == r.from.lat }
                if (i < 0) plan.points.add(w) else plan.points.add(i + 1, w)
                plan.legWinds.clear()
                plan.save(this); rebuild()
            }.setNegativeButton(R.string.cancel, null).show()
    }

    /** A typed place: a name, a latitude and longitude, or a radial and distance from a named place. */
    fun resolve(token: String): FlightPlan.Waypoint? {
        val t = token.trim().uppercase()
        if (t.isEmpty()) return null
        Regex("^(-?\\d+(?:\\.\\d+)?)[,/](-?\\d+(?:\\.\\d+)?)$").find(t)?.let { m ->
            return FlightPlan.Waypoint("WP", m.groupValues[1].toDouble(), m.groupValues[2].toDouble())
        }
        // A place, three digits of magnetic bearing, then the distance: KBVU009017.
        Regex("^([A-Z0-9]{3,5})(\\d{3})(\\d{2,3})$").find(t)?.let { m ->
            base(m.groupValues[1])?.let { b ->
                val mag = m.groupValues[2].toDouble()
                val nm = m.groupValues[3].toDouble()
                // Magnetic as the chart gives it, turned back to true for the walk over the ground.
                val tru = (mag + Nav.variation(b.lat, b.lon) + 360) % 360
                val g = Nav.destination(b.lat, b.lon, tru, nm)
                return FlightPlan.Waypoint("${m.groupValues[1]}${m.groupValues[2]}${m.groupValues[3]}", g.latitude, g.longitude)
            }
        }
        return base(t)
    }

    private fun base(id: String): FlightPlan.Waypoint? {
        val a = airports.firstOrNull { it.icao == id || it.ident == id }
            ?: airports.firstOrNull { id.length == 4 && id.startsWith("K") && it.ident == id.substring(1) }
        if (a != null) return FlightPlan.Waypoint(a.icao.ifEmpty { a.ident }, a.lat, a.lon)
        // A fix the route already holds, or one the nearest airport's coded procedures name.
        plan.points.firstOrNull { it.id == id }?.let { return it }
        for (p in plan.points) {
            val near = airports.minByOrNull { Nav.distanceNm(p.lat, p.lon, it.lat, it.lon) } ?: continue
            Cifp.fixesFor(this, near.icao.ifEmpty { near.ident })[id]?.let { return FlightPlan.Waypoint(id, it[0], it[1]) }
        }
        return null
    }

    private fun actionRow(): View {
        val wrap = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(10), dp(8), dp(10), dp(16)) }
        fun line(): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }.also { wrap.addView(it, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) }) }
        fun btn(parent: LinearLayout, t: String, color: Int, go: () -> Unit) = parent.addView(TextView(this).apply {
            text = t; textSize = 13.5f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            typeface = EfbUi.MEDIUM
            background = EfbUi.cardBg(this@NavlogActivity, color, 10)
            setPadding(dp(6), dp(12), dp(6), dp(12))
        }.also { it.setOnClickListener { _ -> go() } }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        val l1 = line()
        btn(l1, "🌬 Winds aloft", 0xFF0A84FF.toInt()) { winds() }
        btn(l1, "✈ Aircraft", 0xFF48484A.toInt()) { profileEditor() }
        btn(l1, "📈 Altitudes", 0xFF5E5CE6.toInt()) { altitudeAdvisor() }
        val l2 = line()
        btn(l2, "⛰ MORA " + (if (mora) "on" else "off"), if (mora) 0xFF2E7D32.toInt() else 0xFF48484A.toInt()) {
            mora = !mora; VaultLock.prefs(this).edit().putBoolean("nav_mora", mora).apply(); rebuild()
        }
        btn(l2, "🖨 PDF", 0xFF48484A.toInt()) { printLog() }
        btn(l2, "📄 VFR Log", 0xFF8E6CC4.toInt()) { vfrNavLog() }
        btn(l2, "📋 ICAO", 0xFF48484A.toInt()) { icao() }
        btn(l2, "↗ Share", 0xFF48484A.toInt()) { share() }
        return wrap
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_SHORT).show()

    private fun winds() {
        if (pts.size < 2) return
        toast("Getting the forecast winds…")
        lifecycleScope.launch {
            val got = withContext(Dispatchers.IO) {
                var n = 0
                val found = HashMap<Int, Triple<Int, Int, Int?>>()
                for (i in 1 until pts.size) {
                    val a = pts[i - 1]; val b = pts[i]
                    val lat = (a.lat + b.lat) / 2; val lon = (a.lon + b.lon) / 2
                    val w = Winds.triple(this@NavlogActivity, lat, lon, plan.altitude, whenAt(i))
                        ?: AviationData.windAt(fbText(), lat, lon, plan.altitude)
                    if (w != null) { found[i - 1] = w; n++ }
                }
                found
            }
            if (got.isEmpty()) { toast("No wind forecast could be read — type one on a leg instead."); return@launch }
            plan.legWinds.clear(); plan.legWinds.putAll(got)
            plan.save(this@NavlogActivity)
            toast("Winds in: ${got.size} legs")
            rebuild()
        }
    }

    /** When the aeroplane is expected over a leg, so the wind read is the wind it will meet. */
    private fun whenAt(leg: Int): Long {
        val base = plan.etdMin?.let { m ->
            val c = java.util.Calendar.getInstance()
            c.set(java.util.Calendar.HOUR_OF_DAY, m / 60); c.set(java.util.Calendar.MINUTE, m % 60)
            c.set(java.util.Calendar.SECOND, 0); c.timeInMillis
        } ?: System.currentTimeMillis()
        val mins = result?.rows?.take(leg)?.sumOf { it.minutes } ?: 0.0
        return base + (mins * 60000).toLong()
    }

    private var fbCache: String? = null
    private fun fbText(): String = fbCache ?: (try { AviationData.windsAloft(6) } catch (e: Exception) { "" }).also { fbCache = it }

    /** Every legal cruising altitude flown on paper, so the quickest and the leanest show themselves. */
    private fun altitudeAdvisor() {
        if (pts.size < 2) return
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(8), dp(8), dp(8), 0) }
        box.addView(EfbUi.text(this, "Reading the winds aloft…", 14f, EfbUi.DIM).apply { setPadding(dp(12), dp(10), dp(12), dp(10)) })
        val dlg = MaterialAlertDialogBuilder(this).setTitle("📈 Cruising altitude")
            .setView(ScrollView(this).apply { addView(box) })
            .setNegativeButton(R.string.cancel, null).create()
        dlg.show()
        lifecycleScope.launch {
            val mid = pts.let { p -> p.sumOf { it.lat } / p.size to p.sumOf { it.lon } / p.size }
            val text = withContext(Dispatchers.IO) {
                Winds.forecast(this@NavlogActivity, mid.first, mid.second, plan.altitude)
                try { AviationData.windsAloft(6) } catch (e: Exception) { "" }
            }
            val opts = withContext(Dispatchers.Default) {
                Navlog.altitudes(pts, profile, plan.fuelOnBoard, plan.reserveMin, false,
                    { alt -> Winds.at(this@NavlogActivity, mid.first, mid.second, alt)?.let { it.dirTrue to it.kt }
                        ?: (if (text.isBlank()) null else AviationData.windAt(text, mid.first, mid.second, alt)?.let { it.first to it.second }) },
                    pts.firstOrNull()?.let { elevOf(it) }, pts.lastOrNull()?.let { elevOf(it) })
            }
            box.removeAllViews()
            if (opts.isEmpty()) { box.addView(EfbUi.text(this@NavlogActivity, "Nothing to compare.", 14f, EfbUi.DIM)); return@launch }
            if (opts.all { it.wind == "000/0" }) box.addView(EfbUi.text(this@NavlogActivity, "No forecast wind could be read: still air at every level.", 11.5f, 0xFFFFB020.toInt()).apply { setPadding(dp(10), 0, dp(10), dp(6)) })
            for (o in opts) {
                box.addView(LinearLayout(this@NavlogActivity).apply {
                    orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                    setBackgroundResource(R.drawable.item_focus_bg)
                    addView(EfbUi.text(this@NavlogActivity, "%,d'".format(o.altFt), 16f,
                        if (o.altFt == plan.altitude) 0xFF0A84FF.toInt() else 0xFFFFFFFF.toInt(), bold = true), LinearLayout.LayoutParams(dp(74), -2))
                    addView(LinearLayout(this@NavlogActivity).apply {
                        orientation = LinearLayout.VERTICAL
                        addView(EfbUi.text(this@NavlogActivity, "${Navlog.hm(o.minutes)}  ·  %.1f gal  ·  %d kt".format(o.fuelGal, o.avgGs), 13.5f, 0xFFE6EAF0.toInt()))
                        addView(EfbUi.text(this@NavlogActivity, "wind ${o.wind}" +
                            (if (o.fastest) "   ⚡ quickest" else "") + (if (o.leanest) "   ⛽ least fuel" else ""), 11.5f,
                            if (o.fastest || o.leanest) 0xFF30D158.toInt() else 0xFF8FA3B8.toInt()))
                    }, LinearLayout.LayoutParams(0, -2, 1f))
                    setOnClickListener {
                        plan.altitude = o.altFt; plan.save(this@NavlogActivity); dlg.dismiss()
                        winds(); rebuild()
                    }
                })
            }
        }
    }

    /** The aeroplane's own numbers: climb, cruise and descent, saved and used by every log. */
    private fun profileEditor() {
        val list = AircraftProfile.all(this)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(6), dp(20), 0) }
        fun f(label: String, v: String): EditText {
            box.addView(EfbUi.text(this, label, 12f, EfbUi.DIM).apply { setPadding(0, dp(8), 0, 0) })
            return EditText(this).apply {
                setText(v); setSingleLine()
                inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
                box.addView(this)
            }
        }
        val nameF = EditText(this).apply {
            setText(profile.name); setSingleLine()
            box.addView(EfbUi.text(this@NavlogActivity, "Name", 12f, EfbUi.DIM))
            box.addView(this)
        }
        val ct = f("Climb TAS (kt)", EfbUi.num(profile.climbTas))
        val cr = f("Climb rate (fpm)", EfbUi.num(profile.climbFpm))
        val cg = f("Climb fuel (gph)", EfbUi.num(profile.climbGph))
        val zt = f("Cruise TAS (kt)", EfbUi.num(profile.cruiseTas))
        val zg = f("Cruise fuel (gph)", EfbUi.num(profile.cruiseGph))
        val dt = f("Descent TAS (kt)", EfbUi.num(profile.descentTas))
        val dr = f("Descent rate (fpm)", EfbUi.num(profile.descentFpm))
        val dg = f("Descent fuel (gph)", EfbUi.num(profile.descentGph))
        val tx = f("Taxi fuel (gal)", EfbUi.num(profile.taxiGal))
        box.addView(EfbUi.text(this, "From your POH or the school's board. The log's climb, cruise and descent all come from these.", 11f, EfbUi.DIM)
            .apply { setPadding(0, dp(10), 0, 0) })
        MaterialAlertDialogBuilder(this).setTitle("✈ Aircraft performance")
            .setView(ScrollView(this).apply { addView(box) })
            .setPositiveButton(R.string.ok) { _, _ ->
                fun d(e: EditText, v: Double) = e.text.toString().toDoubleOrNull() ?: v
                profile.name = nameF.text.toString().trim().ifEmpty { profile.name }
                profile.climbTas = d(ct, profile.climbTas); profile.climbFpm = d(cr, profile.climbFpm); profile.climbGph = d(cg, profile.climbGph)
                profile.cruiseTas = d(zt, profile.cruiseTas); profile.cruiseGph = d(zg, profile.cruiseGph)
                profile.descentTas = d(dt, profile.descentTas); profile.descentFpm = d(dr, profile.descentFpm); profile.descentGph = d(dg, profile.descentGph)
                profile.taxiGal = d(tx, profile.taxiGal)
                val others = list.filter { it.name != profile.name }
                AircraftProfile.saveAll(this, others + profile)
                AircraftProfile.use(this, profile.name)
                // The cruise speed is the one the rest of the app plans with.
                plan.tas = profile.cruiseTas.toInt(); plan.gph = profile.cruiseGph; plan.save(this)
                rebuild()
            }.setNegativeButton(R.string.cancel, null).show()
    }

    private fun text(): String {
        val r = result ?: return ""
        val sb = StringBuilder()
        sb.append(pts.joinToString(" ") { it.id }).append("\n")
        sb.append("%,d ft · %s · %.1f gph cruise · %.1f gal on board\n\n".format(plan.altitude, profile.name, profile.cruiseGph, plan.fuelOnBoard))
        sb.append("%-14s %4s %6s %6s %6s %6s %6s %6s\n".format("LEG", "PH", "MH", "GS", "DIST", "ETE", "ETO", "LEFT"))
        for (x in r.rows) sb.append("%-14s %4s %6s %6d %6.1f %6s %6s %6.1f\n".format(
            "${x.from.id.take(6)}-${x.to.id.take(6)}",
            when (x.phase) { Phase.CLIMB -> "CLB"; Phase.CRUISE -> "CRZ"; else -> "DSC" },
            "%03d".format(Math.round(x.mh).toInt() % 360), Math.round(x.gs).toInt(), x.distNm,
            Navlog.hm(x.minutes), plan.clock(x.cumMinutes), x.fuelLeftGal))
        sb.append("\nTOTAL %.1f nm · %s · %.1f gal burnt · %.1f left\n".format(r.distNm, Navlog.hm(r.minutes), r.fuelGal, r.fuelLeftGal))
        for (w in r.warnings) sb.append("⚠ ").append(w).append("\n")
        return sb.toString()
    }

    /**
     * The flight plan as the ICAO form asks for it, box by box, ready to read out or to type into
     * Leidos. The aircraft's own boxes come from the aeroplane you keep in weight and balance.
     */
    private fun icao() {
        val r = result ?: return
        val p = VaultLock.prefs(this)
        val tail = Aircraft.all(this).getOrNull(p.getInt("wb_current", 0))?.name ?: ""
        val dep = plan.points.firstOrNull()?.id ?: ""
        val dest = plan.points.lastOrNull()?.id ?: ""
        val route = plan.points.drop(1).dropLast(1).joinToString(" ") { it.id }.ifEmpty { "DCT" }
        val etd = plan.etdMin?.let { "%02d%02d".format(it / 60, it % 60) } ?: "----"
        val endur = if (plan.gph > 0) Navlog.hm(plan.fuelOnBoard / plan.gph * 60).replace(":", "") else "----"
        val text = """
            ICAO FLIGHT PLAN

            7  Aircraft identification      ${p.getString("icao_call", tail).orEmpty()}
            8  Flight rules / Type          V / G
            9  Number / Type / Wake         1 / ${p.getString("icao_type", "EVSS").orEmpty()} / L
            10 Equipment / Surveillance     ${p.getString("icao_equip", "SG").orEmpty()} / ${p.getString("icao_surv", "C").orEmpty()}
            13 Departure / Time             $dep $etd
            15 Speed / Level / Route        N${"%04d".format(plan.tas)} A${"%03d".format(plan.altitude / 100)} $route
            16 Destination / EET / Alt      $dest ${Navlog.hm(r.minutes).replace(":", "")}
            18 Other information            DOF/ PBN/ 
            19 Endurance / Persons          E/$endur  P/${p.getString("icao_pob", "2").orEmpty()}
               Emergency                    R/UV  S/ 
               Colour / Pilot               A/${p.getString("icao_colour", "WHITE").orEmpty()}  C/${p.getString("pilot_name", "").orEmpty()}

            Distance ${"%.0f".format(r.distNm)} nm · fuel ${"%.1f".format(r.fuelGal)} gal · reserve ${plan.reserveMin} min
            Check every box before filing. VFR flight plans are filed with Leidos (1800wxbrief.com).
        """.trimIndent()
        val box = ScrollView(this).apply {
            addView(EfbUi.ltr(EfbUi.text(this@NavlogActivity, text, 12.5f, EfbUi.TEXT, mono = true)).apply {
                setPadding(dp(16), dp(10), dp(16), dp(10)); setTextIsSelectable(true)
            })
        }
        MaterialAlertDialogBuilder(this).setTitle("📋 ICAO flight plan").setView(box)
            .setPositiveButton("Share") { _, _ ->
                startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text)
                }, null))
            }.setNegativeButton(R.string.cancel, null).show()
    }

    private fun share() = startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text())
    }, null))

    private var printWeb: android.webkit.WebView? = null

    /** Sends a page to the printer, where it can be kept as a PDF. */
    private fun printHtml(title: String, html: String) {
        val web = android.webkit.WebView(this)
        web.webViewClient = object : android.webkit.WebViewClient() {
            override fun onPageFinished(v: android.webkit.WebView, url: String) {
                getSystemService(android.print.PrintManager::class.java).print(title,
                    v.createPrintDocumentAdapter(title),
                    android.print.PrintAttributes.Builder()
                        .setMediaSize(android.print.PrintAttributes.MediaSize.NA_LETTER.asLandscape()).build())
            }
        }
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
        printWeb = web
    }

    /**
     * The flight on the printed VFR navigation log — the ruled sheet pilots have carried on a
     * kneeboard for fifty years. Every column the form has is here, in its order: the check points
     * down the left, the beacon and its frequency, the course and the height, the wind and the
     * temperature, the speeds, the whole chain from true course through the wind correction and the
     * variation and the deviation to the compass heading, the distances, the ground speed, the times
     * and the fuel. What can be worked out is printed in; what is written while flying — the actual
     * ground speed, the time over, the fuel remaining — is left ruled and empty for a pencil.
     */
    private fun vfrNavLog() {
        val r = result ?: return
        val dep = plan.points.firstOrNull()?.id ?: ""
        val dest = plan.points.lastOrNull()?.id ?: ""
        val tail = Aircraft.all(this).getOrNull(VaultLock.prefs(this).getInt("wb_current", 0))?.name ?: ""
        fun e(x: String) = x.replace("&", "&amp;").replace("<", "&lt;")
        val rows = StringBuilder()
        // The departure line first, then a line for every point the flight crosses.
        rows.append("<tr><td class='fix'>${e(dep)}</td>" + "<td></td>".repeat(4) +
            "<td colspan='2'></td>" + "<td></td>".repeat(13) + "<td class='w'></td><td class='w'></td></tr>")
        for (x in r.rows) {
            val variation = Nav.variation((x.from.lat + x.to.lat) / 2, (x.from.lon + x.to.lon) / 2)
            val varTxt = "%.0f°%s".format(Math.abs(variation), if (variation >= 0) "W" else "E")
            rows.append("<tr>")
            rows.append("<td class='fix'>${e(x.to.id)}</td>")        // Check point
            rows.append("<td></td><td></td>")                         // VOR ident, freq
            rows.append("<td>DCT</td>")                               // Course (route)
            rows.append("<td>${"%,d".format(x.altFt)}</td>")          // Altitude
            rows.append("<td>${"%03d/%d".format(x.windDir, x.windKt)}</td>")
            rows.append("<td>${plan.legWinds[x.index]?.third?.let { "%+d".format(it) } ?: ""}</td>")
            rows.append("<td>${plan.tas}</td>")                       // CAS (planned)
            rows.append("<td>${Math.round(x.tas).toInt()}</td>")       // TAS
            rows.append("<td>${"%03d".format(Math.round(x.tc).toInt() % 360)}</td>")
            rows.append("<td>${"%+d".format(Math.round(x.wca).toInt())}</td>")
            rows.append("<td>${"%03d".format(Math.round(x.th).toInt() % 360)}</td>")
            rows.append("<td>$varTxt</td>")
            rows.append("<td class='mh'>${"%03d".format(Math.round(x.mh).toInt() % 360)}</td>")
            rows.append("<td></td>")                                   // Deviation, from the card
            rows.append("<td></td>")                                   // Compass heading
            rows.append("<td>${"%.1f".format(x.distNm)}</td>")
            rows.append("<td>${"%.1f".format(x.remainNm)}</td>")
            rows.append("<td>${Math.round(x.gs).toInt()}</td>")        // GS estimated
            rows.append("<td class='w'>${actual["${key(x)}|gs"] ?: ""}</td>")   // GS actual
            rows.append("<td>${Navlog.hm(x.minutes)}</td>")            // ETE
            rows.append("<td>${plan.clock(x.cumMinutes)}</td>")        // ETA
            rows.append("<td class='w'></td><td class='w'>${x.atoUtc ?: ""}</td>")   // ATE, ATA
            rows.append("<td>${"%.1f".format(x.fuelLeftGal)}</td>")    // Fuel remaining
            rows.append("</tr>")
        }
        // A few blank lines, as the printed form leaves them.
        repeat(3) { rows.append("<tr>" + "<td></td>".repeat(25) + "</tr>") }

        fun block(which: String, id: String): String = """
            <table class='sub'>
              <tr><th colspan='2'>$which &nbsp; ${e(id)}</th></tr>
              <tr><td>ATIS code</td><td class='w'></td></tr>
              <tr><td>Wind</td><td class='w'></td></tr>
              <tr><td>Ceiling &amp; visibility</td><td class='w'></td></tr>
              <tr><td>Altimeter</td><td class='w'></td></tr>
              <tr><td>Time check</td><td class='w'></td></tr>
              <tr><td>Approach</td><td class='w'></td></tr>
              <tr><td>Runway</td><td class='w'></td></tr>
            </table>"""

        fun freqs(which: String, id: String): String {
            val a = airports.firstOrNull { it.icao == id || it.ident == id }
            val list = a?.let { try { Frequencies.forAirport(this, it, null) } catch (x: Exception) { emptyList() } }.orEmpty()
            fun f(vararg keys: String) = list.firstOrNull { fr -> keys.any { fr.kind.label.contains(it, true) } }?.let { Frequencies.mhz(it.mhz) } ?: ""
            return """
              <table class='sub'>
                <tr><th colspan='2'>$which frequencies &nbsp; ${e(id)}</th></tr>
                <tr><td>ATIS</td><td>${f("ATIS", "AWOS", "ASOS")}</td></tr>
                <tr><td>Ground</td><td>${f("Ground")}</td></tr>
                <tr><td>Tower</td><td>${f("Tower")}</td></tr>
                <tr><td>Departure</td><td>${f("Departure", "Approach")}</td></tr>
                <tr><td>CTAF</td><td>${f("CTAF", "UNICOM")}</td></tr>
                <tr><td>FSS</td><td>${f("FSS", "Radio")}</td></tr>
              </table>"""
        }

        val html = """<html><head><meta charset="utf-8"><style>
          @page { margin: 8mm; }
          body { font-family: Helvetica, Arial, sans-serif; color:#000; margin:0 }
          h1 { font-size:15px; margin:0 0 2px 0; letter-spacing:1px }
          .top { display:flex; justify-content:space-between; align-items:flex-end; border-bottom:2px solid #000; padding-bottom:3px; margin-bottom:5px }
          .meta { font-size:10px }
          table.log { border-collapse:collapse; width:100%; font-size:8.5px; table-layout:fixed }
          table.log th, table.log td { border:0.6px solid #555; padding:2px 1px; text-align:center; height:15px; overflow:hidden }
          table.log thead th { background:#d9d9d9; font-size:7px; line-height:1.05; font-weight:bold }
          table.log td.fix { text-align:left; font-weight:bold; font-size:9px }
          table.log td.mh { font-weight:bold; background:#f0f0f0 }
          table.log td.w { background:#fbfbe8 }
          .row2 { display:flex; gap:6px; margin-top:6px }
          table.sub { border-collapse:collapse; font-size:8.5px; flex:1 }
          table.sub th { background:#d9d9d9; border:0.6px solid #555; padding:2px; font-size:8px }
          table.sub td { border:0.6px solid #555; padding:2px 4px; height:13px }
          table.sub td.w { background:#fbfbe8; width:52% }
          .foot { margin-top:5px; font-size:8px; color:#444 }
        </style></head><body>
        <div class="top">
          <div><h1>VFR NAVIGATION LOG</h1>
            <div class="meta"><b>${e(dep)} &rarr; ${e(dest)}</b> &nbsp; ${e(tail)} &nbsp;
            ${profile.name} &nbsp; ${"%,d".format(plan.altitude)} ft &nbsp;
            ${"%.1f".format(plan.gph)} gph &nbsp; ${"%.1f".format(plan.fuelOnBoard)} gal on board</div></div>
          <div class="meta">Aircraft ${e(tail)} &nbsp;&nbsp; Date ____________ &nbsp;&nbsp; Page 1</div>
        </div>
        <table class="log">
          <thead><tr>
            <th style="width:7%">CHECK POINTS<br>(FIXES)</th>
            <th style="width:3.4%">VOR<br>IDENT</th><th style="width:3.6%">FREQ</th>
            <th style="width:4%">COURSE<br>(ROUTE)</th><th style="width:4%">ALTITUDE</th>
            <th style="width:4.4%">WIND<br>DIR/VEL</th><th style="width:3%">TEMP</th>
            <th style="width:3%">CAS</th><th style="width:3%">TAS</th>
            <th style="width:3%">TC</th><th style="width:3.4%">WCA<br>-L +R</th><th style="width:3%">TH</th>
            <th style="width:3.6%">VAR<br>E- +W</th><th style="width:3.2%">MH</th>
            <th style="width:3.2%">DEV<br>&plusmn;</th><th style="width:3.2%">CH</th>
            <th style="width:3.4%">DIST<br>LEG</th><th style="width:3.4%">REM</th>
            <th style="width:3.4%">GS<br>EST</th><th style="width:3.4%">ACT</th>
            <th style="width:3.6%">ETE</th><th style="width:3.6%">ETA</th>
            <th style="width:3.6%">ATE</th><th style="width:3.6%">ATA</th>
            <th style="width:4%">FUEL<br>REM</th>
          </tr></thead>
          <tbody>$rows</tbody>
        </table>
        <div class="row2">
          ${block("Departure", dep)}
          ${block("Destination", dest)}
          ${freqs("Departure", dep)}
          ${freqs("Destination", dest)}
          <table class='sub'>
            <tr><th colspan='2'>Times &amp; fuel</th></tr>
            <tr><td>Block out</td><td class='w'></td></tr>
            <tr><td>Time off</td><td class='w'></td></tr>
            <tr><td>Time on</td><td class='w'></td></tr>
            <tr><td>Block in</td><td class='w'></td></tr>
            <tr><td>Log time</td><td class='w'></td></tr>
            <tr><td>Fuel used</td><td class='w'></td></tr>
          </table>
        </div>
        <div class="foot">Total ${"%.0f".format(r.distNm)} nm &middot; ${Navlog.hm(r.minutes)} &middot;
          ${"%.1f".format(r.fuelGal)} gal burnt &middot; ${"%.1f".format(r.fuelLeftGal)} gal on landing &middot;
          reserve ${plan.reserveMin} min (${"%.1f".format(r.reserveGal)} gal) ${if (r.reserveKept) "kept" else "NOT kept"}.
          Shaded boxes are filled in as the flight is flown. For planning; verify with an official briefing.</div>
        </body></html>"""
        printHtml("VFR Nav Log $dep-$dest", html)
    }

    private fun printLog() {
        val r = result ?: return
        val title = (plan.points.firstOrNull()?.id ?: "") + " → " + (plan.points.lastOrNull()?.id ?: "")
        val rows = StringBuilder()
        for (x in r.rows) {
            val alert = x.moraFt != null && x.altFt < x.moraFt
            rows.append("<tr${if (alert) " class='bad'" else ""}><td><b>${x.from.id}</b> → <b>${x.to.id}</b></td>" +
                "<td>${when (x.phase) { Phase.CLIMB -> "CLB"; Phase.CRUISE -> "CRZ"; else -> "DSC" }}</td>" +
                "<td>${"%,d".format(x.altFt)}</td><td>${x.moraFt?.let { "%,d".format(it) } ?: "—"}</td>" +
                "<td>${"%03d".format(Math.round(x.tc).toInt() % 360)}</td><td>${"%+d".format(Math.round(x.wca).toInt())}</td>" +
                "<td><b>${"%03d".format(Math.round(x.mh).toInt() % 360)}</b></td>" +
                "<td>${"%03d/%d".format(x.windDir, x.windKt)}</td><td>${Math.round(x.tas).toInt()}</td><td>${Math.round(x.gs).toInt()}</td>" +
                "<td>${"%.1f".format(x.distNm)}</td><td>${"%.1f".format(x.remainNm)}</td>" +
                "<td>${Navlog.hm(x.minutes)}</td><td>${plan.clock(x.cumMinutes)}</td><td></td>" +
                "<td>${"%.1f".format(x.fuelGal)}</td><td>${"%.1f".format(x.fuelLeftGal)}</td></tr>")
        }
        val html = """<html><head><meta charset="utf-8"><style>
            body{font-family:sans-serif;margin:16px;color:#111}h1{font-size:19px;margin:0}
            .sub{color:#555;margin:4px 0 12px;font-size:12px}
            table{border-collapse:collapse;width:100%;font-size:11px}th,td{border:1px solid #999;padding:4px;text-align:center}
            th{background:#1b2a3a;color:#fff}td:first-child{text-align:left}
            tr.bad td{background:#ffe3e3}.tot td{font-weight:bold;background:#eef}
            .box{display:inline-block;border:1px solid #999;padding:6px 10px;margin:10px 8px 0 0;min-width:120px;font-size:12px}
            </style></head><body>
            <h1>NAVLOG · $title</h1>
            <div class="sub">${plan.points.joinToString(" ") { it.id }} · ${"%,d".format(plan.altitude)} ft · ${profile.name} ·
            ${"%.1f".format(plan.fuelOnBoard)} gal on board${plan.etdMin?.let { " · off %02d:%02d".format(it / 60, it % 60) } ?: ""}</div>
            <table><tr><th>Leg</th><th>Ph</th><th>Alt</th><th>MORA</th><th>TC</th><th>WCA</th><th>MH</th><th>Wind</th><th>TAS</th><th>GS</th>
            <th>Dist</th><th>Rem</th><th>ETE</th><th>ETO</th><th>ATO</th><th>Fuel</th><th>Left</th></tr>
            $rows
            <tr class="tot"><td>TOTAL</td><td colspan="9"></td><td>${"%.1f".format(r.distNm)}</td><td></td>
            <td>${Navlog.hm(r.minutes)}</td><td>${plan.clock(r.minutes)}</td><td></td><td>${"%.1f".format(r.fuelGal)}</td><td>${"%.1f".format(r.fuelLeftGal)}</td></tr></table>
            <div class="box">Reserve ${plan.reserveMin} min<br><b>${"%.1f".format(r.reserveGal)} gal · ${if (r.reserveKept) "kept ✓" else "NOT kept ⚠"}</b></div>
            <div class="box">Top of climb<br><b>${"%.1f".format(r.tocNm)} nm out</b></div>
            <div class="box">Top of descent<br><b>${"%.1f".format(r.todNm)} nm to run</b></div>
            <div class="box">ATIS<br><br></div><div class="box">Clearance / squawk<br><br></div>
            <p style="color:#777;font-size:10px">For planning. Verify with an official briefing; lowest safe altitudes here are from terrain data, not charted MEAs.</p>
            </body></html>"""
        val web = android.webkit.WebView(this)
        web.webViewClient = object : android.webkit.WebViewClient() {
            override fun onPageFinished(v: android.webkit.WebView, url: String) {
                getSystemService(android.print.PrintManager::class.java).print("NavLog $title",
                    v.createPrintDocumentAdapter("NavLog $title"),
                    android.print.PrintAttributes.Builder().setMediaSize(android.print.PrintAttributes.MediaSize.NA_LETTER.asLandscape()).build())
            }
        }
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
        printWeb = web
    }

    override fun onResume() {
        super.onResume()
        plan = FlightPlan.load(this)
        profile = AircraftProfile.current(this)
        rebuild()
        startGps()
    }

    override fun onPause() {
        super.onPause()
        stopGps()
    }

    companion object {
        fun open(ctx: Context) = ctx.startActivity(Intent(ctx, NavlogActivity::class.java))
    }
}
