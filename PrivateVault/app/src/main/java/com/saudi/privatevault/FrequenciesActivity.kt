package com.saudi.privatevault

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Frequencies, the way an EFB lays them out: a COM radio card (active and
 * standby, swapped with one tap, any frequency tapped below goes to standby),
 * the airport's frequencies in the order they are called, the nearest weather
 * broadcasts, towers, Center and FSS from where the aircraft is, those of each
 * airport of the route, and the standard frequencies and codes.
 */
class FrequenciesActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_IDENT = "ident"
        const val EXTRA_LAT = "lat"
        const val EXTRA_LON = "lon"
        const val EXTRA_ROUTE = "route"

        fun open(ctx: Context, ident: String?, lat: Double? = null, lon: Double? = null, route: List<String> = emptyList()) =
            ctx.startActivity(Intent(ctx, FrequenciesActivity::class.java).apply {
                ident?.let { putExtra(EXTRA_IDENT, it) }
                lat?.let { putExtra(EXTRA_LAT, it) }
                lon?.let { putExtra(EXTRA_LON, it) }
                if (route.isNotEmpty()) putExtra(EXTRA_ROUTE, route.toTypedArray())
            })
    }

    private lateinit var col: LinearLayout
    private lateinit var active: TextView
    private lateinit var standby: TextView
    private val prefs by lazy { VaultLock.prefs(this) }
    private var airports: List<AviationData.Airport> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.freq_title)) { bar ->
            bar.menu.add(0, 1, 0, R.string.map_find).setIcon(R.drawable.ic_search).apply {
                icon?.setTint(EfbUi.TEXT)
                setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_ALWAYS)
            }
            bar.setOnMenuItemClickListener {
                AirportSearch.show(this, airports, null) { a -> open(this, a.icao.ifEmpty { a.ident }) }
                true
            }
        }
        radio()
        lifecycleScope.launch {
            airports = withContext(Dispatchers.IO) { AviationData.airports(this@FrequenciesActivity) }
            build()
        }
    }

    private fun dp(v: Int) = EfbUi.dp(this, v)

    private fun find(id: String) = airports.firstOrNull { it.icao == id || it.ident == id }

    /** COM1: active and standby, kept between flights. */
    private fun radio() {
        val card = EfbUi.card(this).apply { background = EfbUi.cardBg(this@FrequenciesActivity, EfbUi.pick(0xFF0B1A2E.toInt(), 0xFFEAF2FF.toInt())) }
        card.addView(EfbUi.text(this, "COM 1", 12f, EfbUi.DIM, bold = true))
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
        fun cell(label: String, color: Int): TextView {
            val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL }
            box.addView(EfbUi.text(this, label, 11f, EfbUi.DIM))
            val v = EfbUi.text(this, "", 28f, color, bold = true, mono = true)
            box.addView(v)
            row.addView(box, LinearLayout.LayoutParams(0, -2, 1f))
            return v
        }
        active = cell("ACTIVE", EfbUi.GOOD)
        val swap = EfbUi.text(this, "⇄", 30f, EfbUi.ACCENT, bold = true).apply { setPadding(dp(14), dp(4), dp(14), dp(4)) }
        row.addView(swap)
        standby = cell("STBY", EfbUi.ACCENT)
        card.addView(row)
        card.addView(EfbUi.text(this, getString(R.string.freq_hint), 12f, EfbUi.DIM).apply { setPadding(0, dp(6), 0, 0) })
        EfbUi.pressable(swap) {
            val a = prefs.getString("com_active", "122.7")!!
            val s = prefs.getString("com_stby", "121.5")!!
            prefs.edit().putString("com_active", s).putString("com_stby", a).apply()
            showRadio()
        }
        col.addView(card)
        showRadio()
    }

    private fun showRadio() {
        active.text = prefs.getString("com_active", "122.7")
        standby.text = prefs.getString("com_stby", "121.5")
    }

    private fun tune(mhz: String, what: String) {
        prefs.edit().putString("com_stby", mhz).apply()
        showRadio()
        (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("freq", mhz))
        Toast.makeText(this, getString(R.string.freq_stby, mhz, what), Toast.LENGTH_SHORT).show()
    }

    private fun section(title: String) = col.addView(EfbUi.text(this, title, 17f, EfbUi.ACCENT, bold = true).apply {
        setPadding(dp(2), dp(20), 0, dp(2))
    })

    /** A frequency line: what it is on the left, the number on the right; a tap puts it on standby. */
    private fun line(parent: LinearLayout, label: String, sub: String, mhz: String, tuneName: String) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            setPadding(0, dp(7), 0, dp(7))
        }
        val left = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        left.addView(EfbUi.ltr(EfbUi.text(this, label, 15f, bold = true)))
        if (sub.isNotEmpty()) left.addView(EfbUi.ltr(EfbUi.text(this, sub, 12f, EfbUi.DIM)))
        row.addView(left, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(EfbUi.ltr(EfbUi.text(this, mhz, 20f, EfbUi.ACCENT, bold = true, mono = true)))
        EfbUi.pressable(row) { tune(mhz, tuneName) }
        parent.addView(row)
    }

    private fun build() {
        val ident = intent.getStringExtra(EXTRA_IDENT)
        val lat = intent.getDoubleExtra(EXTRA_LAT, Double.NaN)
        val lon = intent.getDoubleExtra(EXTRA_LON, Double.NaN)
        val route = intent.getStringArrayExtra(EXTRA_ROUTE)?.toList().orEmpty()
        ident?.let { find(it) }?.let { airport(it) }
        if (!lat.isNaN()) nearest(lat, lon)
        if (route.isNotEmpty()) route(route)
        if (ident == null && lat.isNaN() && route.isEmpty()) {
            val home = prefs.getString("efb_home", "KBVU")!!
            find(home)?.let { airport(it); nearest(it.lat, it.lon) }
        }
        standard()
        col.addView(EfbUi.text(this, getString(R.string.freq_source), 11f, EfbUi.DIM).apply { setPadding(dp(2), dp(18), dp(2), 0) })
        EfbUi.stagger(col, 1)
    }

    /** One airport, grouped in the order they are used: weather, clearance, ground, tower or CTAF, departure. */
    private fun airport(a: AviationData.Airport) {
        val id = a.icao.ifEmpty { a.ident }
        section("$id · ${a.name}")
        val card = EfbUi.card(this)
        col.addView(card)
        val wait = EfbUi.text(this, getString(R.string.map_loading_wx), 13f, EfbUi.DIM)
        card.addView(wait)
        lifecycleScope.launch {
            val apt = withContext(Dispatchers.IO) { AviationData.airportInfo(this@FrequenciesActivity, id) }
            val list = Frequencies.forAirport(this@FrequenciesActivity, a, apt)
            card.removeView(wait)
            if (list.isEmpty()) {
                card.addView(EfbUi.text(this@FrequenciesActivity, getString(R.string.freq_none), 14f, EfbUi.DIM))
                return@launch
            }
            val towered = apt?.optString("tower") == "T" || list.any { it.kind == Frequencies.Kind.TWR }
            for (f in list) {
                val sub = listOfNotNull(
                    f.name.takeIf { it.isNotEmpty() && !it.equals(f.kind.label, true) },
                    if (f.official) "FAA" else null,
                ).joinToString(" · ")
                line(card, f.kind.label, sub, Frequencies.mhz(f.mhz), "$id ${f.kind.label}")
            }
            if (towered && list.any { it.kind == Frequencies.Kind.CTAF })
                card.addView(EfbUi.text(this@FrequenciesActivity, getString(R.string.freq_part_time), 12f, EfbUi.WARN).apply { setPadding(0, dp(6), 0, 0) })
        }
    }

    /** From where the aircraft is: the nearest weather broadcasts, towers and CTAFs, Center and FSS. */
    private fun nearest(lat: Double, lon: Double) {
        val near = airports.sortedBy { Nav.distanceNm(lat, lon, it.lat, it.lon) }.take(40)
        class Hit(val a: AviationData.Airport, val f: Frequencies.Freq, val nm: Double, val brg: Double)
        val hits = near.flatMap { a ->
            val nm = Nav.distanceNm(lat, lon, a.lat, a.lon)
            val brg = Nav.magnetic(Nav.bearingTrue(lat, lon, a.lat, a.lon), lat, lon)
            Frequencies.shipped(this, a).map { Hit(a, it, nm, brg) }
        }
        fun group(title: String, kinds: Set<Frequencies.Kind>, max: Int, byName: Boolean = false) {
            var list = hits.filter { it.f.kind in kinds }
            // Center and FSS: each sector or outlet once, from the nearest field that lists it.
            if (byName) list = list.distinctBy { Math.round(it.f.mhz * 1000) }
            list = list.take(max)
            if (list.isEmpty()) return
            section(title)
            val card = EfbUi.card(this)
            col.addView(card)
            for (h in list) {
                val id = h.a.icao.ifEmpty { h.a.ident }
                val label = if (byName) h.f.name.ifEmpty { h.f.kind.label } else "$id  ${h.f.kind.label}"
                val sub = (if (byName) "via $id · " else "") + "${Nav.deg(h.brg)}M  %.0f nm".format(h.nm)
                line(card, label, sub, Frequencies.mhz(h.f.mhz), "$id ${h.f.kind.label}")
            }
        }
        group(getString(R.string.freq_near_wx), setOf(Frequencies.Kind.ATIS, Frequencies.Kind.WX), 6)
        group(getString(R.string.freq_near_twr), setOf(Frequencies.Kind.TWR, Frequencies.Kind.CTAF), 8)
        group(getString(R.string.freq_near_app), setOf(Frequencies.Kind.APP), 4, byName = true)
        group(getString(R.string.freq_near_ctr), setOf(Frequencies.Kind.CENTER), 4, byName = true)
        group(getString(R.string.freq_near_fss), setOf(Frequencies.Kind.FSS), 4, byName = true)
    }

    /** Each airport of the route, with what is called there. */
    private fun route(ids: List<String>) {
        val list = ids.mapNotNull { find(it) }.distinct()
        if (list.isEmpty()) return
        section(getString(R.string.freq_route))
        val key = setOf(Frequencies.Kind.ATIS, Frequencies.Kind.WX, Frequencies.Kind.CLR, Frequencies.Kind.GND, Frequencies.Kind.TWR, Frequencies.Kind.CTAF)
        for (a in list) {
            val id = a.icao.ifEmpty { a.ident }
            val card = EfbUi.card(this)
            card.addView(EfbUi.ltr(EfbUi.text(this, "$id · ${a.name}", 15f, EfbUi.TEXT, bold = true)))
            val fs = Frequencies.shipped(this, a).filter { it.kind in key }.sortedBy { it.kind.ordinal }
            if (fs.isEmpty()) card.addView(EfbUi.text(this, getString(R.string.freq_none), 13f, EfbUi.DIM))
            for (f in fs) line(card, f.kind.label, "", Frequencies.mhz(f.mhz), "$id ${f.kind.label}")
            EfbUi.pressable(card) { open(this, id) }
            col.addView(card)
        }
    }

    private fun standard() {
        section(getString(R.string.freq_std))
        val card = EfbUi.card(this)
        for ((m, what) in Frequencies.STANDARD) line(card, what, "", m, what)
        card.addView(EfbUi.text(this, "Squawk", 13f, EfbUi.DIM, bold = true).apply { setPadding(0, dp(10), 0, dp(2)) })
        for ((code, what) in Frequencies.SQUAWKS) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR; setPadding(0, dp(4), 0, dp(4)) }
            row.addView(EfbUi.text(this, what, 15f), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, code, 20f, if (code == "1200") EfbUi.TEXT else EfbUi.BAD, bold = true, mono = true))
            card.addView(row)
        }
        val call = EfbUi.ltr(EfbUi.text(this, "📞 Flight Service (Leidos)  ${Frequencies.FSS_PHONE}", 15f, EfbUi.ACCENT, bold = true)).apply { setPadding(0, dp(12), 0, dp(4)) }
        EfbUi.pressable(call) {
            try { startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + Frequencies.FSS_PHONE.replace("-", "")))) } catch (e: Exception) {}
        }
        card.addView(call)
        col.addView(card)
    }
}
