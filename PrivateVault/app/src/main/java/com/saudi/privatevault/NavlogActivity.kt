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
    private var mora = true

    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = 0xFF0F141A.toInt()
        window.navigationBarColor = 0xFF0F141A.toInt()
        plan = FlightPlan.load(this)
        profile = AircraftProfile.current(this)
        mora = VaultLock.prefs(this).getBoolean("nav_mora", true)
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
        plan.points, plan.altitude, profile,
        { i -> plan.legWinds[i]?.let { it.first to it.second } ?: (plan.windDir to plan.windKt) },
        plan.fuelOnBoard, plan.reserveMin,
        plan.points.firstOrNull()?.let { elevOf(it) }, plan.points.lastOrNull()?.let { elevOf(it) }, mora,
    )

    private fun rebuild() {
        val r = compute()
        result = r
        for (row in r.rows) atos[key(row)]?.let { row.atoUtc = it }
        body.removeAllViews()
        body.addView(header())
        if (plan.points.size < 2) {
            body.addView(EfbUi.text(this, "No route yet. Open the map, tap Edit on the flight plan and type one — for example KBVU KHND KVGT.", 15f, EfbUi.TEXT)
                .apply { setPadding(dp(20), dp(30), dp(20), dp(20)) })
            body.addView(actionRow())
            return
        }
        body.addView(summary(r))
        val table = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        table.addView(columns())
        for (row in r.rows) table.addView(rowView(row, r))
        body.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(table) })
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
            addView(EfbUi.text(this@NavlogActivity, plan.points.joinToString(" · ") { it.id }.ifEmpty { "no route" }, 16f, 0xFFFFFFFF.toInt(), bold = true).apply { maxLines = 1 })
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

    private fun summary(r: Navlog.Result): View {
        val s = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xFF141B24.toInt())
            setPadding(dp(14), dp(10), dp(14), dp(10))
        }
        fun add(v: View) = s.addView(v, LinearLayout.LayoutParams(0, -2, 1f))
        add(metric("DIST", "%.1f nm".format(r.distNm)))
        add(metric("ETE", Navlog.hm(r.minutes)))
        add(metric("BURN", "%.1f gal".format(r.fuelGal)))
        add(metric("ON LANDING", "%.1f gal".format(r.fuelLeftGal), if (r.reserveKept) 0xFF30D158.toInt() else 0xFFFF453A.toInt()))
        return s
    }

    private fun cell(t: String, w: Int, color: Int = 0xFFE6EAF0.toInt(), bold: Boolean = false, size: Float = 12.5f, mono: Boolean = true): TextView =
        TextView(this).apply {
            text = t; textSize = size; setTextColor(color); gravity = Gravity.START
            if (mono) typeface = android.graphics.Typeface.MONOSPACE
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(dp(3), 0, dp(3), 0)
            layoutParams = LinearLayout.LayoutParams(dp(w), -2)
        }

    private val cols = listOf("LEG" to 120, "ALT / MORA" to 92, "MH / TC" to 80, "WIND / GS" to 82,
        "DIST / REM" to 86, "ETE / ETO" to 84, "FUEL / LEFT" to 90, "ATO" to 64)

    private fun columns(): View {
        val h = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xFF25303F.toInt())
            setPadding(dp(10), dp(7), dp(10), dp(7))
        }
        for ((t, w) in cols) h.addView(cell(t, w, 0xFFB0BEC5.toInt(), bold = true, size = 10f, mono = false))
        return h
    }

    private fun badge(p: Phase): TextView {
        val (t, c) = when (p) {
            Phase.CLIMB -> "CLB" to 0xFF0277BD.toInt()
            Phase.CRUISE -> "CRZ" to 0xFF2E7D32.toInt()
            Phase.DESCENT -> "DSC" to 0xFFEF6C00.toInt()
        }
        return TextView(this).apply {
            text = t; textSize = 9.5f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            typeface = EfbUi.MEDIUM
            background = EfbUi.cardBg(this@NavlogActivity, c, 4)
            setPadding(dp(5), dp(1), dp(5), dp(1))
        }
    }

    private fun rowView(r: Navlog.Row, all: Navlog.Result): View {
        val alert = r.moraFt != null && r.altFt < r.moraFt
        val line = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(10), dp(8), dp(10), dp(8))
            setBackgroundColor(if (alert) 0xFF3B1818.toInt() else if (r.index % 2 == 0) 0xFF141B24.toInt() else 0xFF18202B.toInt())
        }
        // The leg and what part of the flight it is.
        line.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(EfbUi.text(this@NavlogActivity, "${r.from.id.take(6)} → ${r.to.id.take(6)}", 13.5f, 0xFFFFFFFF.toInt(), bold = true).apply { maxLines = 1 })
            addView(badge(r.phase), LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(2) })
            layoutParams = LinearLayout.LayoutParams(dp(cols[0].second), -2)
        })
        line.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(cell("%,d'".format(r.altFt), cols[1].second, 0xFFFFFFFF.toInt(), bold = true))
            addView(cell(r.moraFt?.let { "MORA %,d'".format(it) } ?: "MORA —", cols[1].second,
                if (alert) 0xFFFF453A.toInt() else 0xFF8FA3B8.toInt(), size = 10.5f))
        })
        line.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(cell("%03d°M".format(Math.round(r.mh).toInt() % 360), cols[2].second, 0xFF4FC3F7.toInt(), bold = true, size = 14f))
            addView(cell("%03d°T %+d".format(Math.round(r.tc).toInt() % 360, Math.round(r.wca).toInt()), cols[2].second, 0xFF8FA3B8.toInt(), size = 10.5f))
        })
        line.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(cell("%d kt".format(Math.round(r.gs).toInt()), cols[3].second,
                if (r.gs < r.tas - 5) 0xFFFF9F0A.toInt() else 0xFFE6EAF0.toInt(), bold = true))
            addView(cell("%03d/%d".format(r.windDir, r.windKt), cols[3].second,
                if (plan.legWinds.containsKey(r.index)) 0xFF30D158.toInt() else 0xFF8FA3B8.toInt(), size = 10.5f))
        })
        line.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(cell("%.1f".format(r.distNm), cols[4].second, 0xFFE6EAF0.toInt()))
            addView(cell("%.1f rem".format(r.remainNm), cols[4].second, 0xFF8FA3B8.toInt(), size = 10.5f))
        })
        line.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(cell(Navlog.hm(r.minutes), cols[5].second, 0xFFE6EAF0.toInt()))
            addView(cell(plan.clock(r.cumMinutes), cols[5].second, 0xFF64D2FF.toInt(), size = 10.5f))
        })
        line.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(cell("%.1f".format(r.fuelGal), cols[6].second, 0xFFE6EAF0.toInt()))
            addView(cell("%.1f left".format(r.fuelLeftGal), cols[6].second,
                if (r.fuelLeftGal < all.reserveGal) 0xFFFF453A.toInt() else 0xFF30D158.toInt(), size = 10.5f, bold = true))
        })
        line.addView(TextView(this).apply {
            text = r.atoUtc ?: "TAP"
            textSize = 11.5f; typeface = android.graphics.Typeface.MONOSPACE
            setTextColor(if (r.atoUtc != null) 0xFF69F0AE.toInt() else 0xFFFFB74D.toInt())
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(dp(3), dp(6), dp(3), dp(6))
            layoutParams = LinearLayout.LayoutParams(dp(cols[7].second), -2)
            setOnClickListener {
                if (r.atoUtc == null) { atos[key(r)] = Navlog.utcNow() } else atos.remove(key(r))
                rebuild()
            }
        })
        line.setOnClickListener { legMenu(r) }
        line.isClickable = true
        return line
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
        btn(l2, "↗ Share", 0xFF48484A.toInt()) { share() }
        return wrap
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_SHORT).show()

    private fun winds() {
        if (plan.points.size < 2) return
        toast("Getting the forecast winds…")
        lifecycleScope.launch {
            val text = withContext(Dispatchers.IO) { try { AviationData.windsAloft(6) } catch (e: Exception) { "" } }
            if (text.isBlank()) { toast("No winds-aloft forecast right now — type them on a leg instead."); return@launch }
            plan.legWinds.clear()
            for (i in 1 until plan.points.size) {
                val a = plan.points[i - 1]; val b = plan.points[i]
                AviationData.windAt(text, (a.lat + b.lat) / 2, (a.lon + b.lon) / 2, plan.altitude)?.let { plan.legWinds[i - 1] = it }
            }
            plan.save(this@NavlogActivity)
            toast("Winds in: ${plan.legWinds.size} legs")
            rebuild()
        }
    }

    /** Every legal cruising altitude flown on paper, so the quickest and the leanest show themselves. */
    private fun altitudeAdvisor() {
        if (plan.points.size < 2) return
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(8), dp(8), dp(8), 0) }
        box.addView(EfbUi.text(this, "Reading the winds aloft…", 14f, EfbUi.DIM).apply { setPadding(dp(12), dp(10), dp(12), dp(10)) })
        val dlg = MaterialAlertDialogBuilder(this).setTitle("📈 Cruising altitude")
            .setView(ScrollView(this).apply { addView(box) })
            .setNegativeButton(R.string.cancel, null).create()
        dlg.show()
        lifecycleScope.launch {
            val text = withContext(Dispatchers.IO) { try { AviationData.windsAloft(6) } catch (e: Exception) { "" } }
            val mid = plan.points.let { p -> p.sumOf { it.lat } / p.size to p.sumOf { it.lon } / p.size }
            val opts = withContext(Dispatchers.Default) {
                Navlog.altitudes(plan.points, profile, plan.fuelOnBoard, plan.reserveMin, false,
                    { alt -> if (text.isBlank()) null else AviationData.windAt(text, mid.first, mid.second, alt)?.let { it.first to it.second } },
                    plan.points.firstOrNull()?.let { elevOf(it) }, plan.points.lastOrNull()?.let { elevOf(it) })
            }
            box.removeAllViews()
            if (opts.isEmpty()) { box.addView(EfbUi.text(this@NavlogActivity, "Nothing to compare.", 14f, EfbUi.DIM)); return@launch }
            if (text.isBlank()) box.addView(EfbUi.text(this@NavlogActivity, "No forecast wind: still air at every level.", 11.5f, 0xFFFFB020.toInt()).apply { setPadding(dp(10), 0, dp(10), dp(6)) })
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
        sb.append(plan.points.joinToString(" ") { it.id }).append("\n")
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

    private fun share() = startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text())
    }, null))

    private var printWeb: android.webkit.WebView? = null

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
    }

    companion object {
        fun open(ctx: Context) = ctx.startActivity(Intent(ctx, NavlogActivity::class.java))
    }
}
