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
    private var aircraft = "SportStar MAX"
    private val done = HashSet<String>()
    private var emergency: View? = null
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The school's checklist, once, the first time it is there; then whichever the pilot picks.
        if (!prefs.getBoolean("ck_athene_shown", false)) prefs.edit().putBoolean("ck_athene_shown", true).putString("ck_aircraft", ATHENE).apply()
        aircraft = prefs.getString("ck_aircraft", ATHENE)!!.let { if (it == "SportStar") "SportStar MAX" else it }
        col = EfbUi.screen(this, getString(R.string.ck_title)) { bar ->
            bar.menu.add(R.string.ck_reset).setOnMenuItemClickListener { done.clear(); build(); true }
            bar.menu.add(R.string.ck_edit).setOnMenuItemClickListener { edit(); true }
            bar.menu.add(R.string.ck_restore).setOnMenuItemClickListener { prefs.edit().remove("ck_$aircraft").apply(); done.clear(); build(); true }
        }
        build()
        if (intent.getBooleanExtra("emergency", false)) col.postDelayed({ emergency?.let { v -> (col.parent as? android.widget.ScrollView)?.scrollTo(0, v.top) } }, 600)
    }

    private fun text(): String = prefs.getString("ck_$aircraft", null) ?: when (aircraft) {
        "C172" -> C172
        ATHENE -> ATHENEAIR
        else -> SPORTSTAR
    }

    private fun build() {
        col.removeAllViews()
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(4), 0, dp(4)) }
        for (a in listOf(ATHENE, "SportStar MAX", "C172")) {
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
        chips.addView(EfbUi.text(this, "🆘 EMERGENCY", 15f, 0xFFFFFFFF.toInt(), bold = true).apply {
            background = EfbUi.cardBg(this@ChecklistActivity, 0xFFC62828.toInt(), 20)
            setPadding(dp(16), dp(8), dp(16), dp(8))
            EfbUi.pressable(this) { emergency?.let { v -> (col.parent as? android.widget.ScrollView)?.smoothScrollTo(0, v.top) } }
        })
        col.addView(android.widget.HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(chips) })
        col.addView(EfbUi.text(this, getString(R.string.ck_note), 11f, EfbUi.DIM).apply { setPadding(dp(2), dp(4), dp(2), dp(4)) })
        var card: LinearLayout? = null
        var section = ""
        var progress: TextView? = null
        val rows = ArrayList<Triple<String, View, String>>()   // key, row, section
        val counters = HashMap<String, TextView?>()
        emergency = null
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
                if (emergency == null && section.contains("EMERGENCY", true)) emergency = card
                if (section.startsWith("📋")) card.background = EfbUi.cardBg(this, 0xFF0F2236.toInt())
                continue
            }
            val c = card ?: EfbUi.card(this).also { card = it; col.addView(it) }
            // Warnings, cautions and notes as printed, not ticked.
            if (line.startsWith("!")) {
                val t = line.drop(1).trim()
                c.addView(EfbUi.text(this, t, 13f, if (t.startsWith("WARNING")) EfbUi.BAD else EfbUi.WARN, bold = true).apply {
                    setPadding(dp(10), dp(8), dp(10), dp(8))
                    background = EfbUi.cardBg(this@ChecklistActivity, 0xFF2A1A12.toInt(), 10)
                    layoutDirection = View.LAYOUT_DIRECTION_LTR
                    textDirection = View.TEXT_DIRECTION_LTR
                }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6); bottomMargin = dp(6) })
                continue
            }
            val reference = section.startsWith("📋")
            val key = "$section|$line"
            val (item, action) = line.split(Regex("\\s*(\\.{2,}|—|-{2,}|\\|)\\s*"), 2).let { it[0] to it.getOrElse(1) { "" } }
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(4), dp(9), dp(4), dp(9))
                layoutDirection = View.LAYOUT_DIRECTION_LTR
            }
            val mark = EfbUi.text(this, if (reference) "•" else "○", 20f, if (reference) EfbUi.ACCENT else EfbUi.DIM)
            row.addView(mark, LinearLayout.LayoutParams(dp(32), -2))
            row.addView(EfbUi.text(this, item, 15f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, action, 15f, EfbUi.WARN, bold = true).apply { gravity = Gravity.END })
            c.addView(row)
            if (reference) continue
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
        /** Evektor SportStar MAX, from its Aircraft Operating Instructions (SSM2008AOIUS), with the AOI page of each part. */
        const val ATHENE = "AtheneAir EVSS"

        private val SPORTSTAR = """
# 📋 SPEEDS · AOI 2-3, 2-4, 3-3, 4-3
VS0 · stall, flaps 50°, max weight .. 37 KIAS
VS1 · stall, flaps 0°, max weight .. 38 KIAS
VX · flaps 15° / flaps 0° .. 54 / 56 KIAS
VY · flaps 15° / flaps 0° .. 57 / 65 KIAS
Climb to 50 ft (flaps 15°) .. 57 KIAS
Rotation / lift-off airspeed .. 57 KIAS
Approach, normal landing (flaps 50°) .. 60 KIAS
Balked landing, flaps 15° .. 56 KIAS
Best glide (flaps 0°) .. 59 KIAS
Glide, flaps 15° .. 55 KIAS
Precautionary / emergency landing (flaps 50°) .. 55 KIAS
VFE · max flap extended .. 70 KIAS
VA · manoeuvring .. 90 KIAS
VNO · max structural cruising .. 115 KIAS
VNE · never exceed .. 146 KIAS
Max demonstrated crosswind (AOI 5-14) .. 16 kts
Max demonstrated tail wind .. 6 kts
Max demonstrated wind .. 24 kts
# 📋 LIMITS · AOI 2-5 TO 2-10
Engine .. ROTAX 912 ULS
RPM max take-off (max 5 min) .. 5800
RPM max continuous .. 5500
RPM idle .. 1400
Oil temp max / optimum .. 266 °F / 190-230 °F
Oil pressure min / optimum / max .. 12 / 29-73 / 102 PSI
Coolant temp max .. 248 °F
Fuel pressure min .. 2.2 PSI
Ignition check at 4000 RPM: max drop .. 300 RPM
Max difference L / R .. 120 RPM
Max take-off / landing weight .. 1320 lbs
Max baggage .. 55 lbs
Min crew weight .. 121 lbs
Operating C.G. range .. 20 to 34 %MAC
Load factors .. +4.0 / -2.0
Fuel: total / usable .. 31.7 / 31.2 US gal
Oil volume min / max .. 0.53 / 0.79 US gal
Approved manoeuvres .. bank up to 60°, no spins
! WARNING: AEROBATICS AS WELL AS INTENTIONAL SPINS ARE PROHIBITED! NOT AUTHORIZED FOR FLIGHT INTO KNOWN OR FORECAST POSSIBLE ICING CONDITIONS. NOT AUTHORIZED FOR FLIGHT WITHIN 25 MILES OF KNOWN LIGHTNING OR THUNDERSTORMS.
# PRE-FLIGHT CHECK · AOI 4-4 TO 4-7
! WARNING: CHECK BEFORE PRE-FLIGHT CHECK THAT IGNITION IS SWITCHED OFF!
1. Left landing gear leg: attachment and condition .. check
1. Left gear: wheel, tire condition and inflation .. check
1. Left gear: wheel covers, ground cable (if installed) .. check
2. Left wing: surface, leading edge, landing light (if installed) .. check
2. Left wing: Pitot tube condition .. check
2. Left wing: drain fuel tank (AOI 8-6) .. drain
2. Left wing: fuel tank cap .. closed
3. Left wing tip: surface, attachment, fuel tank vent cleanness .. check
3. Left wing tip: position lights / beacon (if installed) .. check
4. Left aileron: surface, trim tab (if installed), attachment, free movement .. check
5. Left wing flap: surface, attachment .. check
6. Rear fuselage: surface, antennas (if installed) .. check
7. Tail units: tail skid, surface .. check
7. Tail units: rudder and elevator attachment, freedom of movement .. check
7. Tail units: trim tab and elevator trim tab control .. check
8. Rear fuselage: surface .. check
9. Right wing flap (see 5.) .. check
10. Right aileron (see 4., except the trim tab) .. check
11. Right wing tip (see 3.) .. check
12. Right wing (see 2., except landing light) .. check
12. Alternate pitot tube (IFR) / AOA probe (if installed) .. check
13. Right landing gear leg (see 1.) .. check
14. Front fuselage right: tip-up canopy attachment and condition .. check
14. Nose gear leg, nose wheel, nose wheel control rods .. check
14. External power socket (if installed) .. check
15. Engine, first flight of day (upper cowling off): engine bed, attachment, exhaust, cowlings .. check
15. Fuel and electrical system, visual .. check
15. Coolant in expansion tank (max. 2/3) .. check
15. Every flight: air intakes cleanness .. check
15. Oil level (between marks on dip stick) .. check
15. Coolant in overflow bottle (approx. 0.42 pints) .. check
15. Upper cowling .. properly closed
16. Propeller: attachment, blades, hub and spinner .. check
17. Front fuselage left: tip-up canopy attachment and condition .. check
18. Cockpit: Master switch .. switched on
18. Canopy OPEN/CLOSE indication light (or EFIS message) .. function check
18. All switches .. OFF
18. Instrument equipment .. check condition
18. Safety belts condition and attachment .. check
18. Loose objects in the cockpit .. check
18. Rudder pedals (if adjustable): same position, secured .. check
18. AOI and other required documents .. complete and valid
# BEFORE ENGINE STARTING · AOI 4-8
Pre-flight check, weight and C.G. .. done
External power source (if socket installed) .. connect as necessary
Safety harnesses .. check, fasten
Control stick .. free
Rudder pedals .. free
Wing flaps .. function check
Trim tab .. function check
PARKING BRAKE handle (if installed) .. release brakes
Brakes .. function check
AVIONICS SWITCH .. check OFF
Ignition .. check OFF
Canopy .. close
# ENGINE STARTING · AOI 4-8 TO 4-10
Master switch .. ON
Fuel gauge indicators .. check fuel qty.
FUEL SELECTOR (pull safety button) .. LEFT
Electric fuel pump (if installed) .. ON
THROTTLE lever .. idle
Choke .. as necessary
Space in the propeller area .. free
BEACON (if installed) .. ON as necessary
Brakes .. apply
Ignition .. START, then BOTH
! CAUTION: ACTIVATE STARTER FOR 10 SEC. AS A MAXIMUM, THEN LET IT COOL DOWN FOR 2 MINUTES.
THROTTLE lever .. approx. 2500 RPM
Oil pressure .. rising within 10 s
GEN, AUX GEN (if inst.) switches .. ON
Engine instruments .. check
Choke .. as necessary
Engine warm-up: 2000 RPM approx. 2 min, then 2500 RPM .. until oil 122 °F
FUEL SELECTOR: verify feeding approx. 1 minute .. RIGHT
FUEL SELECTOR .. LEFT
External power source (if used) .. disconnect
AVIONICS SWITCH .. ON
Radiostation / avionics .. ON
Other electrical equipment .. ON as necessary
# BEFORE TAXIING · TAXIING · AOI 4-10
Transponder (if installed) .. SBY
Outside lights (if installed) .. as necessary
THROTTLE lever .. as necessary
Brakes .. check by depressing
Rudder pedals .. function check
# BEFORE TAKE-OFF · AOI 4-11, 4-12
Brakes .. brake
Ignition check at 4000 RPM: L, BOTH, R, BOTH .. max drop 300, diff 120
Engine instruments .. check
Control stick .. free
Wing flaps .. Take-off pos. (15°)
Elevator trim .. NEUTRAL
Aileron trim (if installed) .. NEUTRAL
Fuel gauge indicator .. check fuel quantity
FUEL SELECTOR .. check LEFT
CARB. PREHEATER (if installed) .. check function, then OFF
Engine instruments .. check
Flight instruments .. check
Radiostation / avionics .. check, set
Ignition .. check BOTH
Choke .. close
Master switch .. check ON
Safety harnesses .. tighten up
Canopy .. closed
Transponder (if installed) .. ON or ALT
! WARNING: TAKE-OFF IS PROHIBITED IF ENGINE RUNNING IS IRREGULAR, IF CHOKE IS OPEN, OR IF ENGINE INSTRUMENTS ARE NOT WITHIN THE REQUIRED RANGE.
# TAKE-OFF · CLIMB · AOI 4-12
THROTTLE lever .. max. take-off power
Take-off run: lighten the nose wheel smoothly .. until lift-off
Airspeed .. 57 KIAS
Brakes .. stop main wheel rotation
At 150 ft: flaps .. retracted (0°)
Trim .. as necessary
Climb: THROTTLE lever .. max. continuous power
Airspeed .. VY 65 KIAS or VX 56 KIAS
Engine instruments .. check
Electric fuel pump (if installed) .. OFF
# CRUISE · DESCENT · AOI 4-13, 4-14
THROTTLE lever .. as necessary, max. 5500 RPM
Engine instruments .. check
Fuel quantity (level flight, wait approx. 2 min) .. check
Tanks: switch alternately; not RIGHT if left tank full .. as needed
CARB. PREHEATER (if installed) .. as necessary
Descent: increased idle, watch engine temperatures .. as necessary
# BEFORE LANDING · FINAL · AOI 4-14, 4-15
Fuel quantity .. check
FUEL SELECTOR .. LEFT
Engine instruments .. check
Brakes .. check by depressing pedals
Safety harnesses .. tighten up
Free area of landing .. check
CARB. PREHEATER (if installed) .. ON
Approaching speed .. 60 KIAS
Flaps .. Take-off pos. (15°)
Trim .. as necessary
Parking brake (if installed) .. check lever down
Electric fuel pump (if installed) .. ON
Final: flaps .. landing pos. (30° or 50°)
Maintain airspeed .. 60 KIAS
CARB. PREHEATER (if installed) .. OFF
Landing: THROTTLE lever .. idle
Touch-down on main wheels; brakes after nose wheel .. as necessary
# BALKED LANDING · AOI 4-15
THROTTLE lever .. max. take-off power
Flaps .. take-off pos. (15°)
Airspeed .. 56 KIAS
At 150 ft: flaps .. retracted (0°)
Trim .. as necessary
THROTTLE lever .. max. continuous power
Instruments .. check
Climb at airspeed .. 65 KIAS
# AFTER LANDING · SHUT-OFF · PARKING · AOI 4-16, 4-17
Flaps .. retracted (0°)
Trim .. NEUTRAL
Outside lights (if installed) .. OFF
Transponder (if installed) .. OFF
Electric fuel pump (if installed) .. OFF
THROTTLE lever .. idle
Engine instruments .. check
AVIONICS SWITCH .. OFF
Radiostation / avionics .. OFF
Other electrical equipment .. OFF
Ignition .. OFF
BEACON (if installed) .. OFF
Master switch .. OFF
FUEL SELECTOR (safety button) .. OFF
PARKING BRAKE (if installed) or chocks .. as necessary
Canopy .. close, lock as necessary
# EMERGENCY · ENGINE FAILURE AT TAKE-OFF RUN · AOI 3-3
THROTTLE lever .. idle
Brakes .. as necessary
FUEL SELECTOR .. OFF
Ignition .. OFF
Master switch .. OFF
# EMERGENCY · ENGINE FAILURE AT TAKE-OFF · AOI 3-3, 3-4
Gliding speed: flaps 15° / flaps 0° .. min. 55 / 59 KIAS
Below 150 ft .. land straight ahead
150 - 400 ft .. straight ahead or turn up to 90°
Above 250 ft .. you can try to start engine
Above 400 ft .. turn up to 180° possible
THROTTLE lever .. idle
Flaps .. as needed
FUEL SELECTOR .. OFF
Ignition .. OFF
ATC .. report
Master switch .. OFF
After touch down .. brake as needed
# EMERGENCY · ENGINE FAILURE IN FLIGHT · AOI 3-4
Gliding speed .. 59 KIAS
Altitude .. decide: restart (3.4) or emergency landing (3.8.1)
# EMERGENCY · ENGINE STARTING IN FLIGHT · AOI 3-4, 3-5
! NOTE: If the engine is shut down, altitude loss during engine starting can reach up to 1000 ft.
Gliding speed .. 59 KIAS
Altitude .. check
Master switch .. ON
Electrical fuel pump (if installed) .. ON
Unnecessary electrical equipment .. switch off
FUEL SELECTOR .. LEFT (or RIGHT if left is empty)
Choke .. as needed
THROTTLE lever .. idle (choke open) or increased idle
Propeller rotating: Ignition .. BOTH
Propeller not rotating: Ignition .. START
No start: increase gliding speed up to .. 108 KIAS
Ignition .. BOTH
Unsuccessful .. emergency landing 3.8.1
# EMERGENCY · FIRE ON THE GROUND · AOI 3-5
FUEL SELECTOR .. OFF
Brakes .. brake
THROTTLE lever .. full
HOT AIR knob (if installed) .. push
After engine stops: Ignition .. OFF
Master switch .. OFF
Airplane .. leave
Manual extinguisher (if available) .. use
# EMERGENCY · FIRE DURING TAKE-OFF · AOI 3-5, 3-6
FUEL SELECTOR .. OFF
THROTTLE lever .. full
Airspeed .. 65 KIAS
HOT AIR knob (if installed) .. push
COLD AIR knob (if installed) .. push
After engine stops: gliding speed .. 55 KIAS
Ignition .. OFF
Master switch .. OFF
Land .. land
Airplane .. leave
Manual extinguisher (if available) .. use
# EMERGENCY · FIRE IN FLIGHT · AOI 3-6, 3-7
FUEL SELECTOR .. OFF
THROTTLE lever .. full
HOT AIR knob (if installed) .. push
COLD AIR knob (if installed) .. push
Gliding speed .. 59 KIAS
Ignition .. OFF
ATC .. report if possible
Master switch .. OFF
! NOTE: For extinguishing the engine fire, you can perform slip if altitude and time allow.
! WARNING: AFTER EXTINGUISHING THE ENGINE FIRE START ENGINE ONLY IF IT IS NECESSARY TO SAFE LANDING. FIRE COULD RESTORE AGAIN.
If restarting: all switches OFF, Master ON, only necessary equipment .. as needed
Emergency landing .. per 3.8.1
Airplane .. leave
Manual extinguisher (if available) .. use as needed
# EMERGENCY · FIRE IN THE COCKPIT · AOI 3-7
Fire source .. identify
Master switch (if electrical fire) .. OFF
Manual extinguisher .. use
After extinguishing: aerate cockpit, open eye-ball vents .. as needed
Safety landing .. per 3.8.2
! WARNING: NEVER AGAIN SWITCH THE DEFECTIVE SYSTEM. If an electrical circuit was the source, switch off its circuit breaker and Master switch back ON.
# EMERGENCY · LANDING, ENGINE NOT OPERATING · AOI 3-8
Airspeed .. 59 KIAS
Landing area .. choose, determine wind direction
Safety harness .. tighten up
Flaps .. landing position (50°)
Airspeed .. 60 KIAS
Radiostation .. notify ATC (if possible)
FUEL SELECTOR .. OFF
Ignition .. OFF
Master switch .. OFF before touch down
# EMERGENCY · SAFETY LANDING, ENGINE OPERATING · AOI 3-8
Area for landing: pass over at 59 KIAS, flaps 15° .. choose, wind direction
Radiostation .. notify ATC (if possible)
Safety harness .. tighten up
Flaps .. landing position (50°)
Airspeed .. 60 KIAS
Landing .. carry out
# EMERGENCY · BURST TIRE · DAMAGED GEAR · AOI 3-9
Burst tire: keep that wheel off the ground with ailerons (nose wheel: elevator) .. as long as possible
At running: hold direction with foot control and brakes .. as needed
Nose gear damage: touch down at lowest speed, keep on main wheels .. as long as possible
Main gear damage: touch down at lowest speed, keep direction .. if possible
# EMERGENCY · UNINTENTIONAL SPIN · AOI 3-9, 3-10
THROTTLE lever .. idle
Control stick: ailerons .. neutral
Pedals .. full rudder against rotation
Control stick .. push forward, hold until rotation stops
Pedals, immediately after rotation stops .. neutral
Control stick .. recover the diving
! CAUTION: ALTITUDE LOSS PER ONE TURN AND RECOVERING FROM THE SPIN IS 500 UP TO 1000 FT.
# EMERGENCY · VIBRATION · CARBURETTOR ICING · AOI 3-10
Vibration: engine RPM .. set where vibrations are lowest
Land at nearest airport or safety landing 3.8.2 .. as needed
Carb icing: CARB. PREHEATER (if installed) .. ON
THROTTLE lever .. idle, then cruising power again
Power not recovered .. land at nearest airport or precautionary landing 3.8.2
# EMERGENCY · CANOPY OPENING IN FLIGHT · AOI 3-11
Grasp shaking control stick(s) .. hold
THROTTLE: reduce airspeed to approx. .. 65 KIAS
Pull opened canopy down by its frame and keep holding .. hold
! WARNING: PRIORITY IS TO MAINTAIN AIRPLANE CONTROLLABILITY! ATTEMPTS TO CLOSE THE CANOPY ARE SECONDARY!
Try to close the canopy (possible in dual flight) .. if able
Safety landing .. per 3.8.2
After landing: check canopy, lock system and horizontal tail .. inspect
""".trimIndent()

        /** The school's own checklist: AtheneAir EVSS Operating Checklist, Revision 1.3, 06/2026 (N19EV, N79EV, N19MX), as printed. */
        private val ATHENEAIR = """
# 📋 SPEEDS · AtheneAir EVSS Operating Checklist Rev 1.3, 06/2026
Aircraft .. N19EV / N79EV / N19MX
VR .. 50 KIAS
VX .. 56 KIAS
VY .. 65 KIAS
VA .. 90 KIAS
VG (best glide) .. 55 KIAS (Flaps 15) / 59 KIAS (Flaps 0)
Approach .. 65 – 70 KIAS
Final .. 60 – 65 KIAS
Short Final .. 60 KIAS
VFE .. 70 KIAS
VS0 .. 37 KIAS
VS1 .. 38 KIAS
VNO .. 115 KIAS
VNE .. 146 KIAS
! For Training use only, reference POH in real Emergency/Abnormal Operations
! ATTENTION! FUEL: MOGAS & 100LL. ENGINE OIL: Do NOT Overfill (1 Ounce at a Time)
# PREFLIGHT COCKPIT
Airplane documents .. CHECK
Interior for FOD .. CHECK
Circuit Breakers .. CHECK
Master Switch .. ON
Battery Voltage .. CHECK
Fuel Quantity .. CHECK
External Lights .. ON
Flaps .. LOWERED
Stall Warning .. CHECK
External Lights .. CHECK
Flaps .. CHECK
External Lights .. OFF
Flaps .. RETRACTED
Seatbelt .. REMOVED
Master .. OFF
# PREFLIGHT EXTERIOR · NOSE
Canopy Attachment .. CHECK
Nose Gear, Control Rods .. CHECK
Tire Inflation/Condition .. CHECK
1st Flight of the Day .. REMOVE COWLING
Engine & Coolant Levels .. INSPECT
Oil Level .. CHECK
! BURP IF NECESSARY
Air Intake / Radiator .. CHECK
Prop/Spinner .. CHECK FOR DAMAGE
Exhaust .. CHECK
# PREFLIGHT EXTERIOR · RIGHT WING
Wing Leading Edge .. CHECK
Vortex Generators .. CHECK
Wing Surface Condition .. CHECK
Wingtip / Fuel Vent .. CHECK
Wing Tie Down .. REMOVE
Aileron / Hinge / Pushrod .. CHECK
Main Gear / Brake Lines .. CHECK
Tire Inflation and Condition .. CHECK
Fuel Sump .. CHECK
Fuel Cap .. CHECK FUEL LEVEL / LOCK
# PREFLIGHT EXTERIOR · EMPENNAGE
Antennae .. CHECK
Vertical Stabilizer .. CHECK
RH. Horizontal Stabilizer .. CHECK
Elevator Movement .. CHECK
Elevator Trim Tab .. CHECK
Elevator Pushrod .. CHECK
Surface and Tail Skid .. CHECK
Tail Tie Down .. REMOVE
Rudder Movement .. CHECK
L.H Horizontal Stabilizer .. CHECK
# PREFLIGHT EXTERIOR · LEFT WING
Main Gear / Brake Lines .. CHECK
Fuel Sump .. CHECK
Tire Inflation and Condition .. CHECK
Aileron / Hinge / Pushrod .. CHECK
Wingtip / Fuel Vent .. CHECK
Wing Tie Down .. REMOVE
Pitot Static Tube .. CHECK CLEAR
Wing Leading Edge .. CHECK
Vortex Generators .. CHECK
Wing Surface Condition .. CHECK
Fuel Cap .. CHECK FUEL LEVEL / LOCK
# BEFORE ENGINE STARTING
Passenger Briefing .. SAFETY
Pilot Briefing .. COMPLETE
Circuit Breakers .. IN
Control Stick .. Free & Correct
Rudder Pedals .. Adjusted
Parking Brake .. As Necessary
All Switches .. OFF
Ignition .. OFF
# ENGINE STARTING
Master Switch .. ON Wait for Dynon
Hobbs .. Check & Dispatch
Fuel Gauge Indicator .. Check Fuel Quantity
Fuel Selector .. Lowest Tank
Electric Fuel Pump .. ON Check Fuel Pressure
Throttle .. Idle / 1 Turn if Warm
Choke .. As Necessary
Beacon .. On
Brakes .. Apply
Propeller Area .. Clear
Ignition .. Start
! Starter: Max 10 sec / 2 min cooldown
# AFTER START
Engine Warmup .. 2000RPM
Oil Pressure .. Check in Green
Engine Instruments .. Check
GEN, AUX GEN .. ON
Avionics Switch .. ON
Electric Fuel Pump .. OFF Check Fuel Pressure
# BEFORE TAXI
Transponder .. ON & ALT, Correct Code
Lights .. ON as Necessary
Weather .. ATIS/AWOS/ASOS
Flight Instruments .. SET
Radio/Avionics/GPS .. CHECK / SET
# TAXI
Taxi Clearance/Briefing .. COMPLETE
Parking Brake .. RELEASED
Brakes .. CHECK
# RUNUP
Fuel Pump .. ON Check Fuel Pressure
Fuel Selector .. Change Tank
Oil Temp .. At Least 122°F
Brakes .. HOLD
Throttle (ignition check) .. 4000RPM
Ignition Check .. Left/Both/Right/Both
! DO NOT EXCEED 300RPM DROP OR 120RPM DIFFERENCE
Carb Heat .. On/Check Drop/Off
Throttle .. 2000 RPM
Trim .. Set
Flight Instruments .. Check
Ignition .. Both
Choke .. Closed
# BEFORE TAKEOFF
Fuel Pump .. ON
Lights .. ON
Trim .. SET
Canopy .. Closed "Green Light"
Flaps .. 15° Degrees
! REVIEW EMERGENCY PROCEDURES
# AFTER TAKEOFF
Throttle .. Max Take-off Power
Airspeed .. 65 KIAS
Flaps .. UP / 0° (Above 150ft AGL)
Lights .. ON
# CLIMB
Throttle .. Max Continuous Power
! Above 1000 Ft AGL:
Fuel Pump .. OFF Check Fuel Pressure
Landing Light .. OFF
Engine Instruments .. Check in Green
Flaps .. Verify UP (0°)
Traffic Avoidance .. SCAN
# CRUISE
Throttle .. Max 5400 RPM
Engine Instruments .. CHECK
Fuel Quantity .. CHECK
Trim .. SET
Carb Preheat .. As Necessary
Traffic Avoidance .. SCAN
# DESCENT
Throttle .. As Necessary
Airspeed .. As Necessary
Trim .. As Necessary
Engine Instruments .. Check in Green
Carb Preheat .. As Necessary
Weather .. ATIS, AWOS, ASOS
# BEFORE LANDING
Fuel Pump .. ON
Fuel Selector .. Fullest Tank
Landing Light .. ON
Carb Preheat .. As Necessary
Seatbelts .. On
# AFTER LANDING
Fuel Pump .. OFF
Lights .. As Necessary
Trim .. Neutral
Flaps .. UP (0°)
# SHUTDOWN
All Electrical Switches .. OFF
Dynon MFD .. Engine Page
Ignition .. OFF
Hobbs/Tach .. Recorded
Master Switch .. OFF
Flight Circle .. Check-In
All Air Vents .. CLOSED
Control Stick .. SECURE
Canopy .. LOCKED
Canopy Cover .. SECURED
# 📋 EMERGENCY · ENGINE FAILURE BRIEF
ON Runway .. Throttle idle, apply the brakes smoothly, and bring aircraft to a stop
After Rotation w/Runway Remaining .. 55 KIAS · Land: Runway · Checklist if time permits · Declare emergency 121.5 / NRST freq
After Rotation No Runway .. 59 KIAS · Land: no more than 30° on each side · Checklist if time permits · Declare emergency 121.5 / NRST freq
After Rotation Above 1000 ft AGL .. 59 KIAS · Land: return to runway · Checklist if time permits · Declare emergency 121.5 or NRST freq
# EMERGENCY · ENGINE FAILURE IN FLIGHT
Airspeed .. 59 KIAS
Best Place to Land .. Locate
Checklist .. Troubleshoot Below
Declare Emergency .. Squawk 7700 & 121.5
# EMERGENCY · ENGINE FAILURE · TROUBLESHOOT
Fuel Pump .. ON
Fuel Selector .. Switch Tanks
Air .. Carb Heat ON
! If power is not restored, secure aircraft & land
# EMERGENCY · ENGINE FAILURE · SECURE
Fuel Pump .. OFF
Fuel Selector .. OFF
Air .. Carb Heat OFF
Spark Ignition .. OFF
Master Switch .. OFF (close to land)
# EMERGENCY LANDING
Airspeed .. 59 KIAS
Best Place to Land .. Locate
Safety Harness .. Tight
Flaps .. As Required (50° Recommended)
Declare Emergency .. Squawk 7700 & 121.5
Fuel Selector .. OFF
Ignition .. OFF
Master Switch .. OFF (Close to Land)
# EMERGENCY · ENGINE FIRE DURING START
Start .. Crank
Fuel Selector .. OFF
Throttle .. Full
Fuel Pump .. Off
Aircraft .. Evacuate
# EMERGENCY · ENGINE FIRE IN FLIGHT
Fuel Pump .. OFF
Fuel Selector .. OFF
Cabin Air .. OFF
Throttle .. Full
Ignition .. OFF
Airspeed .. 110 KIAS
ATC .. Distress
Emergency Landing .. Execute
Master Switch .. OFF
Airplane .. Evacuate
# EMERGENCY · ELECTRICAL FIRE
Fire Source .. Identify
Unnecessary Electrical Equipment .. OFF
Fire Extinguisher .. If Necessary
Circuit Breakers .. CHECK
Vents .. OPEN
Master Switch .. OFF
! Land as soon as Practical
# EMERGENCY · ENGINE OVERHEATING (IN CLIMB)
Airspeed .. >75 KIAS
Power .. Reduce if Possible
! Step Climb if Necessary
! If Temps in RED:
Land .. As soon as Practical
Aircraft .. Secure
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
