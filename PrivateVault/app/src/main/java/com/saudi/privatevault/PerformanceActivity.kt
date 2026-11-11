package com.saudi.privatevault

import android.os.Bundle
import android.widget.EditText
import android.widget.LinearLayout
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Takeoff and landing distances from the SportStar MAX POH (Doc. SSM2008AOIUS, section 5.2.3–5.2.4),
 * for each runway of a field with today's wind: the POH figures (1268 lbs, sea level ISA), its own
 * corrections for tailwind and slope, the demonstrated crosswind and tailwind limits, and the runway
 * it must fit on. The POH gives no altitude data; an estimate for density altitude is shown apart,
 * marked as a rule of thumb, never mixed with the POH numbers.
 */
class PerformanceActivity : BaseActivity() {
    private lateinit var col: LinearLayout
    private lateinit var out: LinearLayout
    private var apt: JSONObject? = null
    private fun dp(v: Int) = EfbUi.dp(this, v)

    // POH 5.2.3 / 5.2.4: (run, over 50 ft) in ft.
    private val TO_PAVED = 620.0 to 1440.0
    private val TO_GRASS = 720.0 to 1540.0
    private val LDG_PAVED = 590.0 to 1310.0
    private val LDG_GRASS = 520.0 to 1250.0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.perf_title))
        val card = EfbUi.card(this)
        col.addView(card)
        val home = VaultLock.prefs(this).getString("efb_home", "KBVU") ?: "KBVU"
        val ident = EfbUi.field(this, card, "Airport", home, number = false)
        val wdir = EfbUi.field(this, card, "Wind from (°M)", "")
        val wspd = EfbUi.field(this, card, "Wind speed (kt)", "")
        val temp = EfbUi.field(this, card, "Temperature (°C)", "")
        val alt = EfbUi.field(this, card, "Altimeter (inHg)", "")
        val elev = EfbUi.field(this, card, "Field elevation (ft)", "")
        val slope = EfbUi.field(this, card, "Runway slope (%, up for takeoff)", "0")
        card.addView(MaterialButton(this).apply {
            text = getString(R.string.perf_load); setOnClickListener { load(ident.text.toString().trim().uppercase(), wdir, wspd, temp, alt, elev) }
        })
        card.addView(MaterialButton(this).apply {
            text = getString(R.string.perf_calc); setOnClickListener {
                compute(wdir.d(), wspd.d(), temp.d(), alt.d(), elev.d(), slope.d() ?: 0.0)
            }
        })
        out = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(out)
        col.addView(EfbUi.text(this, getString(R.string.perf_note), 11.5f, EfbUi.DIM).apply { setPadding(dp(4), dp(14), dp(4), 0) })
        load(home, wdir, wspd, temp, alt, elev)
    }

    private fun EditText.d() = text.toString().replace(',', '.').trim().toDoubleOrNull()

    private fun load(ident: String, wdir: EditText, wspd: EditText, temp: EditText, alt: EditText, elev: EditText) {
        lifecycleScope.launch {
            val (m, a) = withContext(Dispatchers.IO) {
                (try { AviationData.metar(ident) } catch (e: Exception) { null }) to (try { AviationData.airportInfo(this@PerformanceActivity, ident) } catch (e: Exception) { null })
            }
            // Elevation in feet from the FAA airport list.
            val ap = withContext(Dispatchers.IO) { try { AviationData.airports(this@PerformanceActivity).firstOrNull { it.icao == ident || it.ident == ident || "K" + it.ident == ident } } catch (e: Exception) { null } }
            apt = a
            val j = m?.json
            val lat = ap?.lat ?: 35.95; val lon = ap?.lon ?: -114.86
            j?.opt("wdir")?.toString()?.toDoubleOrNull()?.let { wdir.setText("%.0f".format(Nav.magnetic(it, lat, lon))) }
            j?.opt("wspd")?.toString()?.toDoubleOrNull()?.let { wspd.setText("%.0f".format(it)) }
            j?.opt("temp")?.toString()?.toDoubleOrNull()?.let { temp.setText("%.0f".format(it)) }
            j?.opt("altim")?.toString()?.toDoubleOrNull()?.let { alt.setText("%.2f".format(if (it > 100) it / 33.8639 else it)) }
            ap?.let { elev.setText(it.elevation.toString()) }
            compute(wdir.d(), wspd.d(), temp.d(), alt.d(), elev.d(), 0.0)
        }
    }

    private fun compute(wdir: Double?, wspd: Double?, temp: Double?, altim: Double?, elev: Double?, slope: Double) {
        out.removeAllViews()
        val e = elev ?: 0.0
        val pa = e + (29.92 - (altim ?: 29.92)) * 1000
        val isa = 15 - 2 * pa / 1000
        val da = pa + 120 * ((temp ?: isa) - isa)
        out.addView(EfbUi.section(this, "Density altitude"))
        out.addView(EfbUi.ltr(EfbUi.text(this, "Pressure alt %,.0f ft · DA %,.0f ft".format(pa, da), 16f, if (da > 5000) EfbUi.WARN else EfbUi.TEXT, bold = true)))
        val rwys = apt?.optJSONArray("runways")
        if (rwys == null || rwys.length() == 0) { out.addView(EfbUi.text(this, getString(R.string.perf_no_rwy), 13f, EfbUi.DIM)); return }
        val rule = 1 + 0.10 * (da / 1000).coerceAtLeast(0.0)   // takeoff: about +10% per 1,000 ft DA
        val ruleL = 1 + 0.05 * (da / 1000).coerceAtLeast(0.0)  // landing: about +5% per 1,000 ft DA
        for (i in 0 until rwys.length()) {
            val r = rwys.optJSONObject(i) ?: continue
            val len = r.optString("dimension").substringBefore('x').trim().toDoubleOrNull()
            val grass = r.optString("surface").uppercase().let { it.startsWith("T") || it.startsWith("G") }
            for (end in r.optString("id").split('/')) {
                val n = end.takeWhile { it.isDigit() }.toIntOrNull() ?: continue
                val ang = Math.toRadians((wdir ?: 0.0) - n * 10.0)
                val head = (wspd ?: 0.0) * Math.cos(ang); val cross = Math.abs((wspd ?: 0.0) * Math.sin(ang))
                val tail = (-head).coerceAtLeast(0.0)
                val (tr, t50) = if (grass) TO_GRASS else TO_PAVED
                val (lr, l50) = if (grass) LDG_GRASS else LDG_PAVED
                // POH corrections: +4% per kt of tailwind (takeoff), +4.5% (landing); +8% of the run per 1% slope.
                val toRun = tr * (1 + 0.04 * tail) * (1 + 0.08 * slope.coerceAtLeast(0.0))
                val to50 = t50 * (1 + 0.04 * tail) + (toRun - tr * (1 + 0.04 * tail))
                val ldRun = lr * (1 + 0.045 * tail)
                val ld50 = l50 * (1 + 0.045 * tail)
                val c = EfbUi.card(this)
                c.addView(EfbUi.text(this, "RWY $end" + (len?.let { " · %,.0f ft".format(it) } ?: "") + if (grass) " · grass" else " · paved", 17f, EfbUi.ACCENT, bold = true))
                c.addView(EfbUi.ltr(EfbUi.text(this, (if (head >= 0) "Headwind %.0f kt" else "TAILWIND %.0f kt").format(Math.abs(head)) + " · crosswind %.0f kt".format(cross), 14f,
                    if (tail > 6 || cross > 16) EfbUi.BAD else EfbUi.TEXT)))
                val lines = StringBuilder()
                lines.append("POH (1268 lbs, sea level ISA, corrected for wind/slope):\n")
                lines.append("  Takeoff run %,.0f ft · over 50 ft %,.0f ft\n".format(toRun, to50))
                lines.append("  Landing over 50 ft %,.0f ft · braked run %,.0f ft\n".format(ld50, ldRun))
                lines.append("Estimate at DA %,.0f ft (rule of thumb, NOT POH):\n".format(da))
                lines.append("  Takeoff over 50 ft ≈ %,.0f ft · landing over 50 ft ≈ %,.0f ft".format(to50 * rule, ld50 * ruleL))
                c.addView(EfbUi.ltr(EfbUi.text(this, lines.toString(), 13f, EfbUi.TEXT, mono = true)))
                val warn = ArrayList<String>()
                if (tail > 6) warn.add("Tailwind above the 6 kt demonstrated (POH 5.3.6)")
                if (cross > 16) warn.add("Crosswind above the 16 kt demonstrated (POH 5.3.6)")
                if (len != null && to50 * rule > len) warn.add("Takeoff over 50 ft may not fit the runway")
                if (len != null && ld50 * ruleL > len) warn.add("Landing over 50 ft may not fit the runway")
                if (warn.isNotEmpty()) c.addView(EfbUi.text(this, "⚠ " + warn.joinToString("\n⚠ "), 13f, EfbUi.BAD, bold = true).apply { setPadding(0, dp(6), 0, 0) })
                out.addView(c, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
            }
        }
    }
}
