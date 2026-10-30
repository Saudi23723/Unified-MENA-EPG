package com.saudi.privatevault

import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView

/** The flight computer: each card answers as soon as its numbers are typed. */
class E6bActivity : BaseActivity() {

    private val prefs get() = VaultLock.prefs(this)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val col = EfbUi.screen(this, getString(R.string.e6b_title))

        calc(col, "e6b_wind", "🧭 Wind triangle", listOf("True course °", "TAS kt", "Wind from °", "Wind kt")) { v ->
            val (tc, tas, wd, ws) = v
            if (tc == null || tas == null || wd == null || ws == null || tas <= 0) return@calc null
            val rel = Math.toRadians(wd - tc)
            val s = ws * Math.sin(rel) / tas
            if (Math.abs(s) > 1) return@calc "Wind stronger than TAS"
            val wca = Math.toDegrees(Math.asin(s))
            val gs = tas * Math.cos(Math.asin(s)) - ws * Math.cos(rel)
            "WCA %+.0f°   TH %s\nGS %.0f kt".format(wca, Nav.deg((tc + wca + 360) % 360), gs)
        }
        calc(col, "e6b_xw", "🛬 Crosswind", listOf("Runway (e.g. 27)", "Wind from ° (magnetic)", "Wind kt", "Gust kt")) { v ->
            val (rw, wd, ws, g) = v
            if (rw == null || wd == null || ws == null) return@calc null
            val a = Math.toRadians(wd - rw * 10)
            val head = ws * Math.cos(a)
            val cross = ws * Math.sin(a)
            "%s %.0f kt   Crosswind %.0f kt from the %s".format(if (head >= 0) "Headwind" else "TAILWIND", Math.abs(head), Math.abs(cross), if (cross >= 0) "right" else "left") +
                (g?.let { "\nGust crosswind %.0f kt".format(Math.abs(it * Math.sin(a))) } ?: "")
        }
        calc(col, "e6b_da", "⛰ Density altitude", listOf("Field elevation ft", "Altimeter inHg", "OAT °C")) { v ->
            val (el, alt, t) = v
            if (el == null || alt == null || t == null) return@calc null
            val pa = el + (29.92 - alt) * 1000
            val isa = 15 - 2 * pa / 1000
            val da = pa + 120 * (t - isa)
            "Pressure altitude %,.0f ft\nDensity altitude %,.0f ft%s".format(pa, da, if (da > el + 2000) "  ⚠️ long takeoff roll, slow climb" else "")
        }
        calc(col, "e6b_tas", "💨 True airspeed", listOf("CAS kt", "Pressure altitude ft", "OAT °C")) { v ->
            val (cas, pa, t) = v
            if (cas == null || pa == null || t == null) return@calc null
            val p = Math.pow(1 - 6.8756e-6 * pa, 5.2559)
            val sigma = p / ((t + 273.15) / 288.15)
            "TAS %.0f kt".format(cas / Math.sqrt(sigma))
        }
        calc(col, "e6b_tsd", "⏱ Time · speed · distance", listOf("Distance nm", "Ground speed kt")) { v ->
            val (d, gs) = v
            if (d == null || gs == null || gs <= 0) return@calc null
            "Time ${FlightPlan.hm(d / gs * 60)}  (%.1f h)".format(d / gs)
        }
        calc(col, "e6b_fuel", "⛽ Fuel", listOf("Burn gal/h", "Flight time min", "Fuel on board gal")) { v ->
            val (gph, min, fob) = v
            if (gph == null || gph <= 0) return@calc null
            val need = min?.let { gph * it / 60 }
            listOfNotNull(
                need?.let { "Fuel needed %.1f gal (+ 30 min reserve %.1f = %.1f)".format(it, gph / 2, it + gph / 2) },
                fob?.let { "Endurance ${FlightPlan.hm(it / gph * 60)}" },
            ).joinToString("\n").ifEmpty { null }
        }
        calc(col, "e6b_tod", "📉 Top of descent", listOf("Altitude to lose ft", "Descent rate fpm", "Ground speed kt")) { v ->
            val (alt, fpm, gs) = v
            if (alt == null || fpm == null || gs == null || fpm <= 0) return@calc null
            val min = alt / fpm
            "Start down %.1f nm out, %s before\n(3° path ≈ %.0f fpm at this speed)".format(gs * min / 60, FlightPlan.hm(min), gs * 5.3)
        }
        calc(col, "e6b_cloud", "☁️ Cloud base", listOf("Temperature °C", "Dew point °C")) { v ->
            val (t, d) = v
            if (t == null || d == null) return@calc null
            "Cumulus base ≈ %,.0f ft AGL · spread %.0f°".format((t - d) / 2.5 * 1000, t - d)
        }
        calc(col, "e6b_conv", "🔁 Conversions", listOf("Value")) { v ->
            val x = v[0] ?: return@calc null
            "°C→°F %.1f   °F→°C %.1f\nkg→lb %.1f   lb→kg %.1f\nL→gal %.2f   gal→L %.1f\nnm→sm %.1f   nm→km %.1f\nhPa→inHg %.2f   inHg→hPa %.0f\nAvgas %.1f lb (gal×6)".format(
                x * 9 / 5 + 32, (x - 32) * 5 / 9, x * 2.20462, x / 2.20462, x / 3.78541, x * 3.78541,
                x * 1.15078, x * 1.852, x * 0.02953, x / 0.02953, x * 6)
        }
        EfbUi.stagger(col)
    }

    private fun calc(col: LinearLayout, key: String, title: String, labels: List<String>, compute: (List<Double?>) -> String?) {
        val card = EfbUi.card(this)
        card.addView(EfbUi.text(this, title, 16f, EfbUi.ACCENT, bold = true))
        val values = MutableList<Double?>(labels.size) { null }
        val out: TextView = EfbUi.ltr(EfbUi.text(this, "", 16f, EfbUi.TEXT, bold = true, mono = true)).apply { setPadding(0, EfbUi.dp(this@E6bActivity, 8), 0, 0) }
        fun update() {
            val r = try { compute(values) } catch (e: Exception) { null }
            val was = out.text.toString()
            out.text = r ?: ""
            if (r != null && r != was) { out.alpha = 0.3f; out.animate().alpha(1f).setDuration(200).start() }
        }
        for ((i, l) in labels.withIndex()) {
            val saved = prefs.getString("$key$i", "") ?: ""
            values[i] = saved.toDoubleOrNull()
            EfbUi.field(this, card, l, saved) { s ->
                values[i] = s.toDoubleOrNull()
                prefs.edit().putString("$key$i", s).apply()
                update()
            }
        }
        card.addView(out)
        update()
        col.addView(card)
    }
}
