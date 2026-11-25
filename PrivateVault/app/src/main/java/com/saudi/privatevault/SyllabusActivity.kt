package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * The private pilot syllabus, lesson by lesson, in three stages: before the first solo, solo and
 * cross-country, and getting ready for the practical test. Each lesson says what it is for and which
 * area of the Private Pilot ACS it trains, opens the app's own material for it (the animated
 * maneuvers, the pre-solo exam, the nav log, the checkride preparation), and is ticked off with the
 * date and the pilot's own notes. The experience a Part 61 private pilot needs (14 CFR 61.109(a)) is
 * listed as its own checklist. The instructor's and the school's syllabus come first; this is a guide.
 */
class SyllabusActivity : BaseActivity() {
    override val alwaysDark = true

    private class Lesson(val id: String, val title: String, val goal: String, val acs: String, val link: String = "")

    private val stages = listOf(
        "Stage 1 · Up to the first solo" to listOf(
            Lesson("L1", "Introduction and the preflight", "The aeroplane, its documents, the preflight inspection, engine start, taxi, the controls in flight.", "I Preflight Preparation · II Preflight Procedures"),
            Lesson("L2", "The four fundamentals", "Straight and level, climbs, descents and turns, and their combinations, by attitude and power.", "V Performance Maneuvers", "man:"),
            Lesson("L3", "Slow flight and stalls", "Flight at low airspeed, recognising and recovering from power-off and power-on stalls.", "VII Slow Flight and Stalls", "man:"),
            Lesson("L4", "Ground reference maneuvers", "Rectangular course, S-turns and turns around a point: flying a track over the ground in wind.", "V Ground Reference Maneuvers", "man:"),
            Lesson("L5", "The traffic pattern, takeoffs and landings", "Pattern entry and departure, normal takeoffs and landings, the radio at towered and untowered fields.", "III Airport Operations · IV Takeoffs, Landings and Go-Arounds"),
            Lesson("L6", "Emergencies", "Engine failure in flight and after takeoff, emergency descent, systems failures, the checklists.", "IX Emergency Operations"),
            Lesson("L7", "Crosswinds and go-arounds", "Crosswind takeoffs and landings, the go-around, forward slips to a landing.", "IV Takeoffs, Landings and Go-Arounds", "man:"),
            Lesson("L8", "Pre-solo review and the pre-solo written exam", "Everything of Stage 1 to the standard, and the written exam the instructor gives before the first solo (14 CFR 61.87).", "61.87", "presolo:"),
            Lesson("L9", "First solo", "Three takeoffs and full-stop landings in the pattern, alone, with the instructor's endorsement.", "61.87"),
        ),
        "Stage 2 · Solo and cross-country" to listOf(
            Lesson("L10", "Short- and soft-field takeoffs and landings", "Performance takeoffs and landings, and the numbers for them from the POH.", "IV Takeoffs, Landings and Go-Arounds", "man:"),
            Lesson("L11", "Steep turns and the power-off 180", "Steep turns to the standard, and an accurate power-off approach.", "V Performance Maneuvers", "man:"),
            Lesson("L12", "Navigation and flight planning", "Pilotage and dead reckoning, the sectional, the nav log, weather and NOTAMs, the weight and balance.", "I Preflight Preparation · VI Navigation", "navlog:"),
            Lesson("L13", "Dual cross-country", "A cross-country with the instructor: diversion, lost procedures, flight following.", "VI Navigation"),
            Lesson("L14", "Night flying", "Night preparation, illusions, lighting; the night cross-country and the night takeoffs and landings.", "XI Night Operations"),
            Lesson("L15", "Flight by reference to instruments", "Basic attitude instrument flying, recovery from unusual attitudes, using the radios to get out of cloud.", "VIII Basic Instrument Maneuvers"),
            Lesson("L16", "Solo practice", "The maneuvers and the landings, alone, in the practice area.", "V · VII · IV"),
            Lesson("L17", "Solo cross-country", "A planned cross-country alone, with the instructor's endorsement for it.", "VI Navigation · 61.93"),
            Lesson("L18", "The long solo cross-country", "150 nm in all, full-stop landings at three points, one leg over 50 nm between take-off and landing.", "61.109(a)(5)(ii)"),
        ),
        "Stage 3 · The practical test" to listOf(
            Lesson("L19", "Every maneuver to the ACS", "Each task flown to the Private Pilot ACS tolerances.", "All areas of operation", "man:"),
            Lesson("L20", "The oral", "The knowledge part of the test, by ACS area, with flash cards.", "All areas of operation", "cr:"),
            Lesson("L21", "Mock checkride", "The whole practical test, flown as the examiner will fly it.", "All areas of operation"),
            Lesson("L22", "Practical test", "With the instructor's endorsements, the logbook and the knowledge test result.", "61.39 · 61.103 · 61.107 · 61.109"),
        ),
    )

    /** 14 CFR 61.109(a): what a private pilot (airplane single-engine) must have logged, at least. */
    private val requirements = listOf(
        "r1" to "40 hours of flight time in all",
        "r2" to "20 hours of training from an instructor",
        "r3" to "10 hours of solo flight",
        "r4" to "3 hours of dual cross-country",
        "r5" to "3 hours at night, with one cross-country of over 100 nm in all and 10 takeoffs and full-stop landings",
        "r6" to "3 hours of flight by reference to instruments",
        "r7" to "3 hours of practical-test preparation within the 2 calendar months before the test",
        "r8" to "5 hours of solo cross-country",
        "r9" to "One solo cross-country of 150 nm in all, full-stop landings at three points, one leg over 50 nm",
        "r10" to "3 solo takeoffs and full-stop landings at an airport with an operating control tower",
    )

    private lateinit var body: LinearLayout
    private fun dp(v: Int) = EfbUi.dp(this, v)
    private val prefs get() = VaultLock.prefs(this)

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = EfbUi.BG
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(EfbUi.BG) }
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setBackgroundColor(0xFF121820.toInt()); setPadding(dp(6), dp(8), dp(14), dp(8)) }
        head.addView(TextView(this).apply { text = "✕"; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(dp(42), dp(40)); setOnClickListener { finish() } })
        head.addView(EfbUi.text(this, "PRIVATE PILOT SYLLABUS", 13f, EfbUi.TEXT, bold = true).apply { letterSpacing = 0.1f })
        root.addView(head)
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(6), dp(12), dp(40)) }
        root.addView(ScrollView(this).apply { addView(body) }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            root.setPadding(0, bars.top, 0, bars.bottom); ins
        }
        fill()
    }

    private fun done(id: String) = prefs.getString("syl_$id", null)

    private fun fill() {
        body.removeAllViews()
        val all = stages.sumOf { it.second.size }
        val got = stages.sumOf { s -> s.second.count { done(it.id) != null } }
        body.addView(EfbUi.text(this, "$got of $all lessons done", 15f, EfbUi.TEXT, bold = true).apply { setPadding(dp(4), dp(12), 0, dp(4)) })
        body.addView(android.widget.ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = all; progress = got })
        body.addView(EfbUi.text(this, "Your instructor's and your school's syllabus come first; this follows the Private Pilot ACS and 14 CFR 61.", 11.5f, EfbUi.DIM).apply { setPadding(dp(4), dp(4), 0, 0) })
        for ((title, lessons) in stages) {
            body.addView(EfbUi.text(this, title.uppercase(), 12f, EfbUi.DIM, bold = true).apply { setPadding(dp(4), dp(18), 0, dp(6)) })
            for (l in lessons) {
                val c = EfbUi.card(this).also { body.addView(it, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) }) }
                val d = done(l.id)
                c.addView(EfbUi.text(this, (if (d != null) "✓ " else "○ ") + "${l.id} · ${l.title}", 15.5f, if (d != null) 0xFF30D158.toInt() else EfbUi.TEXT, bold = true))
                c.addView(EfbUi.text(this, l.goal, 13f, EfbUi.TEXT).apply { setPadding(0, dp(4), 0, 0) })
                c.addView(EfbUi.text(this, "ACS / FAR: ${l.acs}", 11.5f, EfbUi.DIM).apply { setPadding(0, dp(4), 0, 0) })
                prefs.getString("syl_${l.id}_note", null)?.takeIf { it.isNotBlank() }?.let { c.addView(EfbUi.text(this, "📝 $it", 12.5f, 0xFFFFC857.toInt()).apply { setPadding(0, dp(4), 0, 0) }) }
                d?.let { c.addView(EfbUi.text(this, "Done $it", 11.5f, 0xFF30D158.toInt())) }
                c.setOnClickListener { lessonMenu(l) }
            }
        }
        body.addView(EfbUi.text(this, "EXPERIENCE · 14 CFR 61.109(a)", 12f, EfbUi.DIM, bold = true).apply { setPadding(dp(4), dp(22), 0, dp(6)) })
        val rc = EfbUi.card(this).also { body.addView(it) }
        for ((k, t) in requirements) {
            val on = prefs.getBoolean("syl_$k", false)
            rc.addView(EfbUi.text(this, (if (on) "☑ " else "☐ ") + t, 13.5f, if (on) 0xFF30D158.toInt() else EfbUi.TEXT).apply {
                setPadding(0, dp(6), 0, dp(6))
                setOnClickListener { prefs.edit().putBoolean("syl_$k", !on).apply(); fill() }
            })
        }
    }

    private fun lessonMenu(l: Lesson) {
        val acts = ArrayList<Pair<String, () -> Unit>>()
        if (done(l.id) == null) acts.add("✓ Mark done today" to {
            prefs.edit().putString("syl_${l.id}", SimpleDateFormat("d MMM yyyy", Locale.US).format(Date())).apply(); fill()
        }) else acts.add("↺ Mark not done" to { prefs.edit().remove("syl_${l.id}").apply(); fill() })
        acts.add("📝 Notes" to { note(l) })
        when (l.link) {
            "man:" -> acts.add("🛩 Open the maneuvers" to { ManeuversActivity.open(this) })
            "presolo:" -> acts.add("📝 Pre-solo written exam" to { PreSoloActivity.open(this) })
            "navlog:" -> acts.add("📋 The nav log" to { startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_NAVLOG, true)) })
            "cr:" -> acts.add("🎓 Checkride preparation" to { startActivity(Intent(this, CheckrideActivity::class.java)) })
        }
        MaterialAlertDialogBuilder(this).setTitle("${l.id} · ${l.title}")
            .setItems(acts.map { it.first }.toTypedArray()) { _, i -> acts[i].second() }.show()
    }

    private fun note(l: Lesson) {
        val input = EditText(this).apply { setText(prefs.getString("syl_${l.id}_note", "")); minLines = 3 }
        MaterialAlertDialogBuilder(this).setTitle("Notes · ${l.id}").setView(input)
            .setPositiveButton("Save") { _, _ -> prefs.edit().putString("syl_${l.id}_note", input.text.toString()).apply(); fill() }
            .setNegativeButton("Cancel", null).show()
    }

    companion object {
        fun open(ctx: Context) = ctx.startActivity(Intent(ctx, SyllabusActivity::class.java))
    }
}
