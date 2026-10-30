package com.saudi.privatevault

import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.button.MaterialButton

/**
 * Checklists, one item at a time: a tap ticks the item and lights the next,
 * each section shows how far it has gone, and the text is the pilot's to
 * edit so it matches the aircraft's own POH.
 */
class ChecklistActivity : BaseActivity() {

    private lateinit var col: LinearLayout
    private val prefs get() = VaultLock.prefs(this)
    private var aircraft = "SportStar"
    private val done = HashSet<String>()
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        aircraft = prefs.getString("ck_aircraft", "SportStar")!!
        col = EfbUi.screen(this, getString(R.string.ck_title)) { bar ->
            bar.menu.add(R.string.ck_reset).setOnMenuItemClickListener { done.clear(); build(); true }
            bar.menu.add(R.string.ck_edit).setOnMenuItemClickListener { edit(); true }
            bar.menu.add(R.string.ck_restore).setOnMenuItemClickListener { prefs.edit().remove("ck_$aircraft").apply(); done.clear(); build(); true }
        }
        build()
    }

    private fun text(): String = prefs.getString("ck_$aircraft", null) ?: if (aircraft == "C172") C172 else SPORTSTAR

    private fun build() {
        col.removeAllViews()
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(4), 0, dp(4)) }
        for (a in listOf("SportStar", "C172")) {
            chips.addView(EfbUi.text(this, a, 15f, EfbUi.TEXT, bold = true).apply {
                background = EfbUi.cardBg(this@ChecklistActivity, if (a == aircraft) 0xFF00838F.toInt() else EfbUi.CARD, 20)
                setPadding(dp(16), dp(8), dp(16), dp(8))
                EfbUi.pressable(this) {
                    aircraft = a
                    prefs.edit().putString("ck_aircraft", a).apply()
                    done.clear()
                    build()
                }
            }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) })
        }
        col.addView(chips)
        col.addView(EfbUi.text(this, getString(R.string.ck_note), 11f, EfbUi.DIM).apply { setPadding(dp(2), dp(4), dp(2), dp(4)) })
        var card: LinearLayout? = null
        var section = ""
        var progress: TextView? = null
        val rows = ArrayList<Triple<String, View, String>>()   // key, row, section
        val counters = HashMap<String, TextView?>()
        for (raw in text().lines()) {
            val line = raw.trim()
            if (line.isEmpty()) continue
            if (line.startsWith("#")) {
                section = line.trimStart('#').trim()
                card = EfbUi.card(this)
                val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                head.addView(EfbUi.text(this, section, 17f, if (section.contains("EMERGENCY", true)) EfbUi.BAD else EfbUi.ACCENT, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
                progress = EfbUi.text(this, "", 13f, EfbUi.DIM, mono = true)
                head.addView(progress)
                counters[section] = progress
                card.addView(head)
                col.addView(card)
                continue
            }
            val c = card ?: EfbUi.card(this).also { card = it; col.addView(it) }
            val key = "$section|$line"
            val (item, action) = line.split(Regex("\\s*(\\.{2,}|—|-{2,}|\\|)\\s*"), 2).let { it[0] to it.getOrElse(1) { "" } }
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(4), dp(9), dp(4), dp(9))
                layoutDirection = View.LAYOUT_DIRECTION_LTR
            }
            val mark = EfbUi.text(this, "○", 20f, EfbUi.DIM)
            row.addView(mark, LinearLayout.LayoutParams(dp(32), -2))
            row.addView(EfbUi.text(this, item, 15f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, action, 15f, EfbUi.WARN, bold = true).apply { gravity = Gravity.END })
            c.addView(row)
            val sec = section
            val p = progress
            rows.add(Triple(key, row, sec))
            row.setOnClickListener {
                if (!done.add(key)) done.remove(key)
                paint(rows, p, sec)
                row.animate().scaleX(0.97f).scaleY(0.97f).setDuration(70).withEndAction { row.animate().scaleX(1f).scaleY(1f).setDuration(120).start() }.start()
            }
            row.tag = mark
        }
        for (s in rows.map { it.third }.distinct()) paint(rows, counters[s], s)
        EfbUi.stagger(col)
    }

    /** Ticked items dim and strike through; the first unticked one in each section is lit. */
    private fun paint(rows: List<Triple<String, View, String>>, progress: TextView?, section: String) {
        val inSection = rows.filter { it.third == section }
        var next = true
        for ((key, row, _) in inSection) {
            val ticked = key in done
            val mark = row.tag as TextView
            mark.text = if (ticked) "✓" else "○"
            mark.setTextColor(if (ticked) EfbUi.GOOD else EfbUi.DIM)
            row.alpha = if (ticked) 0.45f else 1f
            val lit = !ticked && next
            if (!ticked) next = false
            row.background = if (lit) EfbUi.cardBg(this, 0xFF1E3358.toInt(), 10) else null
        }
        val n = inSection.count { it.first in done }
        progress?.text = "$n/${inSection.size}"
        progress?.setTextColor(if (n == inSection.size) EfbUi.GOOD else EfbUi.DIM)
    }

    private fun edit() {
        col.removeAllViews()
        col.addView(EfbUi.text(this, getString(R.string.ck_edit_help), 13f, EfbUi.DIM))
        val e = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            setText(text())
            setTextColor(EfbUi.TEXT)
            typeface = android.graphics.Typeface.MONOSPACE
            textSize = 13f
            gravity = Gravity.TOP
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            textDirection = View.TEXT_DIRECTION_LTR
        }
        col.addView(e, LinearLayout.LayoutParams(-1, -2))
        col.addView(MaterialButton(this).apply {
            text = getString(R.string.log_save)
            setOnClickListener {
                prefs.edit().putString("ck_$aircraft", e.text.toString()).apply()
                done.clear()
                build()
            }
        })
    }

    companion object {
        private val SPORTSTAR = """
# PREFLIGHT
Documents (ARROW) .. On board
Fuel quantity .. Checked visually
Fuel sump .. Drained, no water
Oil (Rotax 912) .. Burped, level checked
Coolant .. Level checked
Propeller & spinner .. No nicks, secure
Control surfaces .. Free, hinges secure
Tires & brakes .. Condition, pressure
Pitot cover / tie-downs .. Removed
Canopy .. Clean, latches work
# BEFORE START
Seats & harnesses .. Adjusted, fastened
Brakes .. Set
Fuel valve .. ON
Circuit breakers .. In
Avionics .. OFF
# ENGINE START
Choke .. As required (cold)
Throttle .. Idle
Master switch .. ON
Beacon .. ON
Ignition A & B .. ON
Propeller area .. CLEAR
Starter .. Engage
Oil pressure .. Rising within 10 s
Choke .. OFF
Avionics .. ON, ATIS
# BEFORE TAKEOFF
Brakes .. Set
Oil temperature .. In range for runup
Throttle .. 4000 RPM
Ignition check .. Drop within POH limits
Carb heat / instruments .. Checked
Throttle .. Idle, smooth
Flight controls .. Free and correct
Trim .. Set for takeoff
Flaps .. Takeoff position
Canopy .. Closed and locked
Transponder .. ALT
Lights .. ON
# TAKEOFF
Throttle .. Full
Engine instruments .. Green
Rotate .. At POH speed
Climb .. Vy, flaps up at safe altitude
# CRUISE
Power .. Set
Engine instruments .. Monitor
Fuel .. Check and log
# BEFORE LANDING
Fuel valve .. ON
Seat belts .. Tight
Landing light .. ON
Flaps .. As required
Approach speed .. Per POH
# AFTER LANDING
Flaps .. Up
Transponder .. Standby
Lights .. As required
# SHUTDOWN
Throttle .. Idle, cool down
Avionics .. OFF
Ignition .. OFF
Master .. OFF
Fuel valve .. OFF
Hobbs / tach .. Recorded
# EMERGENCY · ENGINE FAILURE IN FLIGHT
Airspeed .. Best glide
Landing site .. Choose
Fuel valve .. ON
Ignition .. Both
Choke / throttle .. Check
Mayday .. 121.5, squawk 7700
Rescue system .. As needed
""".trimIndent()

        private val C172 = """
# PREFLIGHT
Documents (ARROW) .. On board
Fuel quantity .. Checked visually
Fuel sumps (all) .. Drained, no water
Oil .. 5-8 qt
Propeller & spinner .. No nicks, secure
Control surfaces .. Free and correct
Tires & brakes .. Condition
Pitot cover / tie-downs / chocks .. Removed
Stall warning / vents .. Checked
# BEFORE START
Seats & belts .. Adjusted, fastened
Brakes .. Test and set
Circuit breakers .. Check in
Avionics .. OFF
Fuel selector .. BOTH
Fuel shutoff valve .. ON (push full in)
# ENGINE START
Throttle .. Open 1/4 inch
Mixture .. IDLE CUTOFF (fuel injected) / RICH
Master switch .. ON
Beacon .. ON
Auxiliary fuel pump .. ON 3-5 s, OFF
Propeller area .. CLEAR
Ignition .. START
Mixture .. Advance smoothly to RICH
Oil pressure .. Green within 30 s
Avionics .. ON
# BEFORE TAKEOFF
Parking brake .. Set
Flight controls .. Free and correct
Flight instruments .. Set
Fuel quantity .. Check
Mixture .. RICH (below 3000 ft)
Fuel selector .. BOTH
Elevator trim .. Takeoff
Throttle .. 1800 RPM
Magnetos .. Drop max 150, diff max 50
Vacuum / ammeter / engine gauges .. Green
Throttle .. 1000 RPM or less
Doors & windows .. Closed and locked
Transponder .. ALT
Lights .. ON
# TAKEOFF
Wing flaps .. 0-10°
Throttle .. Full
Mixture .. RICH (lean for max RPM above 3000 ft)
Rotate .. 55 KIAS
Climb .. 74 KIAS (Vy)
# CRUISE
Power .. 2100-2700 RPM
Mixture .. Lean
Fuel .. Monitor
# BEFORE LANDING
Seats & belts .. Secure
Fuel selector .. BOTH
Mixture .. RICH
Landing light .. ON
Flaps .. As required (below 110 KIAS for 10°)
Final approach .. 65-75 KIAS flaps up / 60-70 flaps 30°
# AFTER LANDING
Flaps .. UP
Transponder .. Standby
# SHUTDOWN
Parking brake .. Set
Throttle .. Idle
Avionics .. OFF
Mixture .. IDLE CUTOFF
Magnetos .. OFF
Master .. OFF
Hobbs / tach .. Recorded
# EMERGENCY · ENGINE FAILURE IN FLIGHT
Airspeed .. 68 KIAS
Landing site .. Choose
Fuel selector .. BOTH
Fuel pump .. ON
Mixture .. RICH
Fuel shutoff valve .. ON
Magnetos .. BOTH (or START if prop stopped)
Mayday .. 121.5, squawk 7700
""".trimIndent()
    }
}
