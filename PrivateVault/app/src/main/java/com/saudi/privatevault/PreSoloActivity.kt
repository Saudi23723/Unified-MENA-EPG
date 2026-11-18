package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/**
 * The Pre-Solo Written Exam, the one a student sits before the first solo. Every question of the
 * AtheneAir (ASEL) paper is here as it is printed, in its three parts.
 *
 * Each question can be worked either way, which is the point of it: write the answer yourself in
 * the box, as you would on the paper — what you write is kept, so the exam can be put down and
 * picked up again — or open the answer and read it. Every answer carries where it comes from: the
 * regulation, the handbook, the AIM paragraph, or the page of the aircraft's own Operating
 * Instructions, so that the answer can be looked up and read in full rather than learnt by heart.
 * Where the source is a regulation in this app, a button opens it.
 *
 * Nothing about the aeroplane is invented here. Every figure is the Evektor SportStar MAX's own,
 * from its Aircraft Operating Instructions, with the section it is printed in.
 */
class PreSoloActivity : BaseActivity() {
    override val alwaysDark = true

    private class Q(val n: String, val q: String, val a: String, val src: String, val far: String? = null)
    private class Sect(val title: String, val qs: List<Q>)

    private lateinit var col: LinearLayout
    private val prefs by lazy { VaultLock.prefs(this) }
    private val shown = HashSet<String>()
    private var allOpen = false
    private var counter: TextView? = null
    private fun dp(v: Int) = EfbUi.dp(this, v)

    private fun key(s: Int, q: Q) = "presolo_" + s + "_" + q.n

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = 0xFF0F141A.toInt()
        window.navigationBarColor = 0xFF0F141A.toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF0F141A.toInt())
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(10), dp(6), dp(10), dp(28)) }
        root.addView(head())
        root.addView(ScrollView(this).apply { addView(col); isFillViewport = true }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            root.setPadding(0, bars.top, 0, bars.bottom); ins
        }
        build()
    }

    private fun head(): View {
        val h = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0xFF1B222C.toInt()); setPadding(dp(6), dp(7), dp(8), dp(7))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        h.addView(btn("‹", 0xFF2A3B4D.toInt()) { finish() }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        val mid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER }
        mid.addView(EfbUi.text(this, "PRE-SOLO WRITTEN EXAM", 14.5f, 0xFFFFFFFF.toInt(), bold = true).apply { gravity = Gravity.CENTER })
        counter = EfbUi.text(this, "", 11f, 0xFFA9B6C3.toInt()).apply { gravity = Gravity.CENTER }
        mid.addView(counter)
        h.addView(mid, LinearLayout.LayoutParams(0, -2, 1f))
        h.addView(btn("Answers", 0xFF2D7FF9.toInt()) { allOpen = !allOpen; if (allOpen) openAll() else shown.clear(); build() })
        return h
    }

    private fun btn(label: String, colour: Int, go: () -> Unit) = TextView(this).apply {
        text = label; textSize = 13f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
        typeface = EfbUi.MEDIUM
        background = EfbUi.cardBg(this@PreSoloActivity, colour, 8)
        setPadding(dp(12), dp(8), dp(12), dp(8))
        setOnClickListener { go() }
    }

    private fun openAll() { for ((s, sec) in SECTIONS.withIndex()) for (q in sec.qs) shown.add(s.toString() + q.n) }

    private fun answered(): Int {
        var n = 0
        for ((s, sec) in SECTIONS.withIndex()) for (q in sec.qs) if (prefs.getString(key(s, q), "").orEmpty().isNotBlank()) n++
        return n
    }

    private fun total() = SECTIONS.sumOf { it.qs.size }

    private fun count() { counter?.text = "ASEL · " + ChecklistActivity.ATHENE + "  ·  written " + answered() + " / " + total() }

    private fun build() {
        col.removeAllViews()
        count()
        col.addView(EfbUi.text(this, "An open-book exam. Write the answer in the box the way you would on the paper — what you write is kept. " +
            "Or open the answer and read it, with where to find it in the books.", 12f, 0xFF93A0AD.toInt())
            .apply { setPadding(dp(6), dp(8), dp(6), dp(12)) })
        for ((s, sec) in SECTIONS.withIndex()) {
            col.addView(EfbUi.text(this, sec.title.uppercase(), 11.5f, 0xFF4DA3FF.toInt(), bold = true).apply {
                letterSpacing = 0.12f; setPadding(dp(6), dp(16), dp(6), dp(8))
            })
            for (q in sec.qs) col.addView(card(s, q), LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) })
        }
        col.addView(btn("Print the exam", 0xFF2A3B4D.toInt()) { printExam() }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(16) })
        col.addView(btn("Clear everything I wrote", 0xFF3A2A2A.toInt()) { askClear() }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
    }

    private fun card(s: Int, q: Q): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = EfbUi.cardBg(this@PreSoloActivity, 0xFF161D25.toInt(), 12)
            setPadding(dp(13), dp(12), dp(13), dp(12))
        }
        card.addView(EfbUi.text(this, q.n + ".  " + q.q, 14.5f, 0xFFE8EDF3.toInt(), bold = true))

        val box = EditText(this).apply {
            setText(prefs.getString(key(s, q), ""))
            textSize = 14f
            setTextColor(0xFFFFFFFF.toInt()); setHintTextColor(0xFF5D6873.toInt())
            hint = "Write your answer"
            setBackgroundColor(0x00000000)
            background = EfbUi.cardBg(this@PreSoloActivity, 0xFF0E141A.toInt(), 9)
            setPadding(dp(10), dp(9), dp(10), dp(9))
            minLines = 2
            gravity = Gravity.TOP or Gravity.START
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            addTextChangedListener(object : TextWatcher {
                override fun afterTextChanged(e: Editable?) {
                    prefs.edit().putString(key(s, q), e?.toString() ?: "").apply(); count()
                }
                override fun beforeTextChanged(c: CharSequence?, a: Int, b: Int, d: Int) {}
                override fun onTextChanged(c: CharSequence?, a: Int, b: Int, d: Int) {}
            })
        }
        card.addView(box, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(9) })

        val id = s.toString() + q.n
        val open = shown.contains(id)
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row.addView(btn(if (open) "Hide the answer" else "Show the answer", if (open) 0xFF2A3B4D.toInt() else 0xFF1E4D7B.toInt()) {
            if (open) shown.remove(id) else shown.add(id); build()
        })
        q.far?.let { part ->
            row.addView(btn("⚖️  14 CFR " + part, 0xFF2A3B4D.toInt()) {
                RegsActivity.open(this, 14, part)
            }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(6) })
        }
        card.addView(row, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(9) })

        if (open) {
            card.addView(View(this).apply { setBackgroundColor(0x1AFFFFFF) },
                LinearLayout.LayoutParams(-1, 1).apply { topMargin = dp(11) })
            card.addView(EfbUi.text(this, q.a, 14f, 0xFFB7F5C9.toInt()).apply { setPadding(0, dp(10), 0, 0) })
            card.addView(EfbUi.text(this, "📖  " + q.src, 11.5f, 0xFF8E9BA8.toInt()).apply { setPadding(0, dp(8), 0, 0) })
        }
        return card
    }

    private fun askClear() {
        MaterialAlertDialogBuilder(this)
            .setTitle("Clear everything I wrote")
            .setMessage("Every answer you have typed into this exam is removed. The exam itself stays.")
            .setPositiveButton("Clear") { _, _ ->
                val e = prefs.edit()
                for ((s, sec) in SECTIONS.withIndex()) for (q in sec.qs) e.remove(key(s, q))
                e.apply(); build()
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    private var printWeb: android.webkit.WebView? = null

    /** The exam as the instructor reviews it: the questions, what was written, and the answer with its source. */
    private fun printExam() {
        val sb = StringBuilder()
        for ((s, sec) in SECTIONS.withIndex()) {
            sb.append("<h2>").append(esc(sec.title)).append("</h2>")
            for (q in sec.qs) {
                val mine = prefs.getString(key(s, q), "").orEmpty()
                sb.append("<div class='q'><b>").append(esc(q.n)).append(". ").append(esc(q.q)).append("</b>")
                sb.append("<div class='mine'>").append(if (mine.isBlank()) "&nbsp;" else esc(mine)).append("</div>")
                sb.append("<div class='a'>").append(esc(q.a)).append("</div>")
                sb.append("<div class='s'>").append(esc(q.src)).append("</div></div>")
            }
        }
        val html = """<html><head><meta charset="utf-8"><style>
            body{font-family:sans-serif;margin:18px;color:#111;font-size:12px}
            h1{font-size:18px;margin:0}h2{font-size:13px;margin:18px 0 6px;color:#1b2a3a;border-bottom:1px solid #999;padding-bottom:3px}
            .sub{color:#555;margin:4px 0 10px;font-size:11px}
            .q{margin:0 0 11px;page-break-inside:avoid}
            .mine{border:1px solid #bbb;background:#fcfcfc;padding:6px 8px;margin:4px 0;min-height:22px;white-space:pre-wrap}
            .a{color:#14532d;margin:3px 0 2px}
            .s{color:#666;font-size:10px}
            </style></head><body>
            <h1>Pre-Solo Written Exam (ASEL)</h1>
            <div class="sub">${esc(ChecklistActivity.ATHENE)} &middot; student: ________________________ &middot; date: ____________ &middot;
            reviewed with instructor: ____________________</div>
            $sb
            </body></html>"""
        val web = android.webkit.WebView(this)
        web.webViewClient = object : android.webkit.WebViewClient() {
            override fun onPageFinished(v: android.webkit.WebView, url: String) {
                getSystemService(android.print.PrintManager::class.java).print("Pre-Solo Written Exam",
                    v.createPrintDocumentAdapter("Pre-Solo Written Exam"),
                    android.print.PrintAttributes.Builder()
                        .setMediaSize(android.print.PrintAttributes.MediaSize.NA_LETTER).build())
            }
        }
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
        printWeb = web
    }

    private fun esc(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    companion object {
        fun open(ctx: Context) = ctx.startActivity(Intent(ctx, PreSoloActivity::class.java))

        private val GENERAL = Sect("General questions", listOf(
            Q("1", "What personal documents and endorsements are you required having before you fly solo?",
                "On you: your student pilot certificate, a valid medical certificate (or, flying as a sport pilot, a current and valid US driver licence), and a government-issued photo ID.\n\n" +
                "In your logbook, from your instructor:\n" +
                "• the endorsement that you have passed this pre-solo written exam and that it was reviewed with you — 61.87(b);\n" +
                "• the endorsement that you have had the pre-solo flight training of 61.87(c) and (d) in this make and model, and are competent to fly it solo safely;\n" +
                "• a solo flight endorsement in your logbook for the make and model, repeated at least every 90 days — 61.87(n);\n" +
                "• for any solo cross-country, the further endorsements of 61.93.",
                "14 CFR 61.3, 61.87, 61.89 · the wording of each endorsement is in AC 61-65 (latest), Appendix A, items A.2 to A.6.", "61"),
            Q("2", "What are your limitations as a student pilot regarding carrying of passengers or cargo and flying for compensation or hire?",
                "A student pilot may not act as pilot in command of an aircraft:\n" +
                "• carrying a passenger;\n" +
                "• carrying property for compensation or hire;\n" +
                "• for compensation or hire;\n" +
                "• in furtherance of a business;\n" +
                "• on an international flight (with the stated exceptions);\n" +
                "• with a flight or surface visibility less than 3 statute miles by day, or 5 by night;\n" +
                "• when the flight cannot be made with visual reference to the surface;\n" +
                "• in an aircraft requiring more than one pilot;\n" +
                "• contrary to any limitation placed in the logbook by the instructor.",
                "14 CFR 61.89(a). Read the whole paragraph — it is short and it is the one the examiner quotes.", "61"),
            Q("3", "Who has the final authority and responsibility for the operation of the aircraft when you are flying solo?",
                "You do. Flying solo you are the pilot in command, and the pilot in command is directly responsible for, and is the final authority as to, the operation of that aircraft.",
                "14 CFR 91.3(a). The power to deviate in an in-flight emergency is 91.3(b).", "91"),
            Q("4", "What are your weather minimums?",
                "Two sets, and the stricter one wins.\n\n" +
                "The regulation: as a student you may not fly solo with flight or surface visibility less than 3 statute miles by day or 5 by night, and not when the flight cannot be made with visual reference to the surface — 61.89(a)(6) and (7). The airspace you are in sets its own minima as well (91.155): in Class D, 3 SM and 500 below, 1,000 above, 2,000 horizontal from cloud.\n\n" +
                "Your own: the limits your instructor wrote into your solo endorsement — a ceiling, a visibility, a surface and a crosswind figure. Write those in here from your own endorsement; they are usually tighter than the regulation and they are the ones you fly.",
                "14 CFR 61.89(a)(6)(7) and 91.155 · and your instructor's written solo limitations (AC 61-65, endorsement A.6).", "91"),
            Q("5", "Discuss what preflight action concerning the airport and aircraft performance is specified in the regulations for a local flight.",
                "Before beginning a flight the pilot in command must become familiar with all available information concerning that flight. For any flight, that includes the runway lengths at airports of intended use, and the take-off and landing distance data in the approved flight manual for the aeroplane — worked for the conditions of the day: the pressure altitude, the temperature, the weight, the wind and the runway surface.",
                "14 CFR 91.103, in particular 91.103(b). The distances themselves: SportStar MAX Aircraft Operating Instructions, Section 5, Performance.", "91"),
            Q("6", "What are the general requirements pertaining to the use of safety belts and shoulder harnesses?",
                "The pilot in command briefs each person on board on how to fasten and unfasten the safety belt and, if installed, the shoulder harness, and tells them when to fasten them. No one may take off or land, and no one may taxi, unless each person on board has a safety belt properly secured about them. The shoulder harness, where one is installed at that seat, is fastened for take-off and landing, unless the person cannot perform required duties with it on.\n\n" +
                "The flight crew keep their belts fastened while at their stations, and the shoulder harness during take-off and landing.",
                "14 CFR 91.107 (passengers and occupants) and 91.105 (flight crewmembers at their stations).", "91"),
            Q("7", "What is the minimum fuel reserve for day VFR flight and on what cruise speed is the fuel reserve based?",
                "By day, VFR, you may not begin a flight unless there is enough fuel to fly to the first point of intended landing and, assuming normal cruising speed, to fly after that for at least 30 minutes. By night it is 45 minutes.\n\n" +
                "The reserve is figured at normal cruising speed, that is at the cruise power setting and fuel flow published for the aeroplane — not at best endurance.",
                "14 CFR 91.151(a). The cruise figures: SportStar MAX Aircraft Operating Instructions, Section 5, Performance — cruise power, speed and consumption. Total fuel 31.7 US gal, usable 31.2 US gal (AOI Section 2, limits).", "91"),
            Q("8", "What aircraft certificates and documents must be on board when you are flying solo?",
                "ARROW:\n" +
                "• Airworthiness certificate — displayed where the occupants can see it;\n" +
                "• Registration certificate — current;\n" +
                "• Radio station licence — only for flight outside the United States;\n" +
                "• Operating limitations — the approved flight manual, here the Aircraft Operating Instructions, together with the placards and markings;\n" +
                "• Weight and balance data, current.\n\n" +
                "A light sport aircraft carries, as its operating limitations, the operating limitations document issued with its airworthiness certificate.",
                "14 CFR 91.203 (certificates to be carried) and 91.9 (flight manual, markings and placards).", "91"),
            Q("9", "Discuss the right-of-way rules regarding overtaking another aircraft, approaching head-on and another aircraft converging from the side.",
                "Overtaking: the aircraft being overtaken has the right of way. The aircraft overtaking — you — alters course to the right, and keeps out of the way, whether climbing, descending or level.\n\n" +
                "Head-on, or nearly so: each aircraft alters course to the right.\n\n" +
                "Converging from the side, at about the same altitude: the aircraft to the other's right has the right of way. Where they are of different categories, the less manoeuvrable has it — a balloon over a glider, a glider over an airship, an airship over an aeroplane or rotorcraft; an aircraft towing or refuelling has the right of way over all other engine-driven aircraft.\n\n" +
                "An aircraft in distress has the right of way over all other air traffic.",
                "14 CFR 91.113(b) to (f). Figures and the same rules in plain words: Pilot's Handbook of Aeronautical Knowledge, chapter on airport operations.", "91"),
            Q("10", "Who has the right-of-way when two aircraft are on final approach to land at the same time?",
                "The aircraft at the lower altitude has the right of way — but it may not use that to cut in front of another that is on final approach to land, or to overtake it.",
                "14 CFR 91.113(g).", "91"),
            Q("11", "At and around your home airport, where is an operating mode C transponder required?",
                "KVGT lies inside the Las Vegas Class B Mode C veil, so a transponder with altitude reporting is required in all airspace within 30 nautical miles of the Class B primary airport, from the surface up to 10,000 feet MSL — which covers the whole of KVGT and its pattern.\n\n" +
                "The rule in general: within and above all of a Class B or Class C surface area up to 10,000 feet MSL; within 30 NM of a Class B primary airport from the surface to 10,000 feet MSL; above the ceiling of Class B or C up to 10,000 feet MSL; at and above 10,000 feet MSL except at and below 2,500 feet AGL; and in Class A. ADS-B Out is required in the same airspace under 91.225.",
                "14 CFR 91.215(b) and 91.225. The veil is drawn on the Las Vegas sectional as a thin magenta circle; open the sectional in Maps and look at the 30 NM ring around KLAS.", "91"),
            Q("12", "Except when necessary for takeoffs and landings, what are the minimum safe altitudes when flying over congested and other than congested areas?",
                "Anywhere: an altitude which, if the engine fails, allows an emergency landing without undue hazard to persons or property on the surface.\n\n" +
                "Over a congested area of a city, town or settlement, or over an open-air assembly of persons: 1,000 feet above the highest obstacle within a horizontal radius of 2,000 feet of the aircraft.\n\n" +
                "Other than congested: 500 feet above the surface. Over open water or sparsely populated areas, no closer than 500 feet to any person, vessel, vehicle or structure.",
                "14 CFR 91.119(a), (b), (c).", "91"),
            Q("13", "If the altimeter setting is not available at an airport, what setting should you use before departing on a local flight?",
                "Set the altimeter so that it reads the field elevation of the departure airport. If neither a local setting nor the elevation is available, use an available altimeter setting from a station within 100 nautical miles.",
                "14 CFR 91.121(a)(1)(ii) and (iii).", "91"),
            Q("14", "When practicing steep turns, stalls and maneuvering during slow flight, the entry altitude must allow a recovery to be completed no lower than how many feet AGL?",
                "No lower than 1,500 feet above ground level. Pick an entry altitude that leaves that much below you after the recovery is finished.",
                "Private Pilot Airman Certification Standards — the risk-management and completion standards for slow flight, stalls and steep turns · Airplane Flying Handbook, the chapter on slow flight, stalls and spins.", null),
            Q("15", "When is a go-around appropriate?",
                "Whenever the approach or the landing is in doubt. Fly it early and fly it fully; the decision is never wrong.\n\n" +
                "• the approach is unstable — off speed, off centreline, high, low, or not configured;\n" +
                "• the runway is not clear, or will not be: traffic, a vehicle, an animal, a late-departing aircraft;\n" +
                "• ATC tells you to go around;\n" +
                "• wind shear, a gust or a bounce you are not comfortable with;\n" +
                "• a long float or a touchdown so far down the runway that the remaining length is in question;\n" +
                "• loss of visual reference, or anything at all that leaves you unsure.",
                "Airplane Flying Handbook, the go-around (rejected landing) section of the approaches and landings chapter.", null),
            Q("16", "What general steps should you follow after an engine failure in flight?",
                "In this order, from the aeroplane's own procedure:\n" +
                "1. Airspeed — 59 KIAS, the best glide speed, flaps up. Pitch for it first, before anything else.\n" +
                "2. Best place to land — locate it, and turn towards it. Wind, length, surface, obstacles, people.\n" +
                "3. Troubleshoot, if height allows — fuel pump ON, fuel selector switch tanks, carburettor heat ON.\n" +
                "4. Declare the emergency — squawk 7700 and call on 121.5 or the nearest frequency.\n" +
                "5. If the power does not come back — secure the aeroplane: fuel pump OFF, fuel selector OFF, carburettor heat OFF, ignition OFF, master switch OFF close to the ground — and land. Harness tight, flaps as required, 50 degrees recommended.",
                "SportStar MAX Aircraft Operating Instructions, Section 3, Emergency Procedures — the same list is the ENGINE FAILURE IN FLIGHT, TROUBLESHOOT, SECURE and EMERGENCY LANDING checklists in this app, under Checklist → Emergency.", null),
            Q("17", "Provide visibility and cloud clearance requirements for the following airspace. Class D · Class E below 10,000 MSL · Class G below 1,200 AGL during the day · Class G below 1,200 AGL at night.",
                "Class D: 3 statute miles flight visibility; 500 feet below, 1,000 feet above, 2,000 feet horizontal from cloud.\n\n" +
                "Class E below 10,000 feet MSL: 3 statute miles; 500 below, 1,000 above, 2,000 horizontal.\n\n" +
                "Class G at or below 1,200 feet AGL, day: 1 statute mile, and clear of clouds.\n\n" +
                "Class G at or below 1,200 feet AGL, night: 3 statute miles; 500 below, 1,000 above, 2,000 horizontal. (The night exception for a traffic pattern within half a mile of the runway does not change what a student may fly: 61.89 still requires 5 statute miles at night.)",
                "14 CFR 91.155, the table in paragraph (a). The same table is drawn in the Pilot's Handbook of Aeronautical Knowledge, airspace chapter.", "91"),
            Q("18", "IAW FARS, can a student pilot request a special VFR clearance in less than VFR conditions? Explain your answer.",
                "By day, a student pilot may ask for and accept a special VFR clearance — nothing in 91.157 bars it, and no instrument rating is needed by day. It must be requested from and granted by ATC, the visibility must be at least 1 statute mile, and the aircraft must remain clear of clouds.\n\n" +
                "But it does you very little good, because your own limits do not move: 61.89 forbids a student flying solo with flight or surface visibility less than 3 statute miles, and forbids flying when the flight cannot be made with visual reference to the surface. So in practice the answer is: yes you may request it, and no you may not use it to fly in less than 3 miles.\n\n" +
                "At night, special VFR needs an instrument rating and an instrument-equipped aircraft, so it is out of the question for a student.",
                "14 CFR 91.157 (special VFR weather minimums) read together with 14 CFR 61.89(a)(6) and (7).", "91"),
            Q("19", "During engine run-up, you cause rocks, debris and propeller blast to be directed toward another aircraft or person. Could this be considered careless or reckless operation of an aircraft? Why or why not?",
                "Yes. No person may operate an aircraft in a careless or reckless manner so as to endanger the life or property of another — and that is exactly what blowing stones and prop blast at another aeroplane or at a person on the ramp does. It is one of the most commonly cited uses of the rule.\n\n" +
                "Why: it endangers others, and it was avoidable. Point the aeroplane away from other aircraft, people, buildings and open hangars before the run-up, choose a run-up spot on a hard clean surface, and use the lowest power that does the job.",
                "14 CFR 91.13(a). Good operating practice: AIM 4-3-20 (taxiing, run-up) and the Pilot's Handbook chapter on airport operations.", "91"),
            Q("20", "What altitudes should you use when operating VFR in level cruising flight at more than 3000 feet AGL and what determines those altitudes?",
                "More than 3,000 feet above the surface, in level cruising flight, and below 18,000 feet MSL:\n" +
                "• magnetic course 0 through 179 degrees — any odd thousand foot MSL altitude plus 500 feet (3,500, 5,500, 7,500 …);\n" +
                "• magnetic course 180 through 359 degrees — any even thousand foot MSL altitude plus 500 feet (4,500, 6,500, 8,500 …).\n\n" +
                "What determines it is the magnetic COURSE — the track over the ground — not the heading you are holding to allow for the wind.",
                "14 CFR 91.159(a).", "91"),
            Q("21", "What is the emergency frequency?",
                "121.5 MHz, the VHF emergency frequency, guarded by ATC facilities, by many airliners and by flight service. With it, squawk 7700 on the transponder.\n\n" +
                "(243.0 MHz is the UHF military emergency frequency. 7600 is the squawk for lost communications, 7500 for unlawful interference.)",
                "AIM 6-3-1 and 6-2-2 · 14 CFR 91.183 and the Pilot/Controller Glossary.", null),
        ))

        private val AIRCRAFT = Sect("Aircraft questions", listOf(
            Q("1", "List the minimum equipment and instruments that must be working properly in your aircraft for day VFR flight.",
                "The regulation's list for day VFR, remembered as A TOMATO FLAMES:\n" +
                "Airspeed indicator · Tachometer for each engine · Oil pressure gauge · Manifold pressure gauge (altitude engine) · Altimeter · Temperature gauge for each liquid-cooled engine · Oil temperature gauge (air-cooled) · Fuel gauge for each tank · Landing gear position indicator (retractable) · Anticollision lights · Magnetic direction indicator · ELT · Seat belts and shoulder harnesses.\n\n" +
                "On top of that, for this aeroplane: whatever its own equipment list and its operating limitations document require, and anything an airworthiness directive requires. Anything not required and not working is removed or deactivated and placarded INOPERATIVE before flight (91.213(d)).",
                "14 CFR 91.205(b) · 91.213(d) for inoperative equipment · the aeroplane's equipment list, SportStar MAX Aircraft Operating Instructions, Section 6, and the operating limitations issued with its airworthiness certificate.", "91"),
            Q("2", "Fill in the V-speed definitions and the corresponding speed for your training airplane. Vso · Vs · Vx · Vy · Vfe · Va · Vno · Vne",
                "Vso — stall speed in the landing configuration, flaps 50 degrees, at maximum weight: 37 KIAS.\n" +
                "Vs (Vs1) — stall speed clean, flaps 0, at maximum weight: 38 KIAS.\n" +
                "Vx — best angle of climb, most height in the least distance: 54 KIAS with flaps 15, 56 KIAS with flaps 0.\n" +
                "Vy — best rate of climb, most height in the least time: 57 KIAS with flaps 15, 65 KIAS with flaps 0.\n" +
                "Vfe — maximum speed with flaps extended: 70 KIAS.\n" +
                "Va — manoeuvring speed, below which full deflection of one control will not overstress the aeroplane: 90 KIAS.\n" +
                "Vno — maximum structural cruising speed, the top of the green arc; above it only in smooth air: 115 KIAS.\n" +
                "Vne — never exceed, the red line: 146 KIAS.",
                "SportStar MAX Aircraft Operating Instructions, Section 2 (limitations, airspeed) and Sections 3, 4 and 5 — pages 2-3, 2-4, 3-3, 4-3. The same table is in this app under Checklist → Reference → SPEEDS. The definitions: Pilot's Handbook of Aeronautical Knowledge, flight instruments chapter.", null),
            Q("3", "What is the best glide speed for your training airplane? KIAS",
                "59 KIAS, flaps 0. With flaps 15 the glide speed is 55 KIAS, and the precautionary or emergency landing approach with flaps 50 is flown at 55 KIAS.",
                "SportStar MAX Aircraft Operating Instructions, Section 3 (emergency procedures, page 3-3) — also listed in this app under Checklist → Reference → SPEEDS.", null),
            Q("4", "Describe the changes in Va with changes in the gross weight of an aircraft.",
                "Manoeuvring speed falls as the weight falls, and rises as the weight rises. A lighter aeroplane is accelerated to its limit load factor by a smaller gust or a smaller control input, so it must be flown more slowly to be protected.\n\n" +
                "It varies with the square root of the weight ratio: Va at the new weight = Va at maximum weight multiplied by the square root of (new weight divided by maximum weight). For this aeroplane Va is 90 KIAS at the maximum take-off weight of 1,320 lb; at a lower weight it is lower, and must be worked out or read from the flight manual.",
                "Pilot's Handbook of Aeronautical Knowledge, the aerodynamics chapter, load factor and manoeuvring speed · the published figure: SportStar MAX Aircraft Operating Instructions, Section 2, airspeed limitations (page 2-3); maximum weight 1,320 lb, Section 2 (page 2-8).", null),
            Q("5", "Describe any limitations on flap use in your training airplane.",
                "• Flaps may not be extended, nor flown extended, above Vfe 70 KIAS.\n" +
                "• The settings are 0, 15 and 50 degrees; 15 is the take-off setting and 50 the full landing setting.\n" +
                "• Flaps 15 is used for the short-field take-off and the balked landing climb (56 KIAS); the normal approach with flaps 50 is flown at 60 KIAS.\n" +
                "• A go-around or balked landing is begun with the flaps retracted in stages, not all at once.\n" +
                "Read the exact wording and any further restriction in Section 2 of the Operating Instructions before you answer this one to your instructor.",
                "SportStar MAX Aircraft Operating Instructions, Section 2 (limitations, pages 2-3 to 2-10) and Section 4 (normal procedures, page 4-3). Vfe 70 KIAS and the approach speeds are in this app under Checklist → Reference → SPEEDS.", null),
            Q("6", "Under what circumstances should you use carburetor heat?",
                "When carburettor icing is likely or suspected, and as the engine's procedures call for it:\n" +
                "• at low power — a descent, a glide, a long approach, extended taxiing;\n" +
                "• in visible moisture, rain, or high humidity, at outside air temperatures that suit icing — it can form on a warm day, roughly between -7 and 21 degrees Celsius with enough moisture;\n" +
                "• at the first sign of it: a gradual loss of RPM with the throttle where you left it, and rough running;\n" +
                "• in the engine failure troubleshooting drill — fuel pump on, switch tanks, carburettor heat on.\n\n" +
                "Applied fully, not partially, and expect a small drop in RPM when it comes on — that drop is how you know it is working.",
                "SportStar MAX Aircraft Operating Instructions, Section 4 (normal procedures) and Section 7 (the ROTAX 912 ULS and its systems) · the theory and the icing-probability chart: Pilot's Handbook of Aeronautical Knowledge, aircraft systems chapter, induction icing.", null),
            Q("7", "Under what circumstances could a spin occur in your training aircraft?",
                "A spin needs two things at once: the wing stalled, and yaw. So it can happen whenever the aeroplane is stalled while uncoordinated — the ball out of the middle:\n" +
                "• a skidding turn from base to final, bottom rudder in to tighten the turn because the aeroplane has overshot the centreline, with the nose coming up;\n" +
                "• a stall with the wings not level, or with rudder held in;\n" +
                "• a cross-controlled stall, a departure stall at high power with the nose high and right rudder held in;\n" +
                "• a stall recovery flown with aileron instead of rudder;\n" +
                "• the pull-up out of a steep turn or a low pass, with back pressure and yaw together.\n\n" +
                "Note that intentional spins in this aeroplane are PROHIBITED, as are all aerobatics: approved manoeuvres are bank up to 60 degrees only.",
                "SportStar MAX Aircraft Operating Instructions, Section 2 — approved manoeuvres and the warning that aerobatics and intentional spins are prohibited (page 2-10) · the aerodynamics: Airplane Flying Handbook, the stalls and spins chapter.", null),
            Q("8", "Describe the spin recovery procedures for your training aircraft.",
                "Fly the Operating Instructions' own wording — Section 3, Emergency Procedures. The standard recovery, which it follows, is PARE:\n" +
                "• Power — throttle to idle;\n" +
                "• Ailerons — neutral;\n" +
                "• Rudder — full deflection OPPOSITE to the direction of rotation, and hold it;\n" +
                "• Elevator — control stick forward, briskly, to break the stall.\n" +
                "When the rotation stops, centralise the rudder at once, and recover from the resulting dive with smooth back pressure, watching the airspeed so as not to exceed Vne 146 KIAS and not to stall again.\n\n" +
                "Intentional spins are prohibited in this aeroplane, so this is a recovery from an unintentional one, and the best recovery is not entering: keep the ball in the middle.",
                "SportStar MAX Aircraft Operating Instructions, Section 3, Emergency Procedures — read the spin paragraph there and copy its exact wording · Airplane Flying Handbook, stalls and spins chapter, for PARE.", null),
            Q("9", "What is the stall speed of your training airplane in a 30 degree bank with flaps up?",
                "In a level 30 degree banked turn the load factor is 1.15 g, and stall speed rises with the square root of the load factor.\n\n" +
                "Vs1, flaps up, at maximum weight, is 38 KIAS. The square root of 1.15 is 1.07. 38 × 1.07 = about 41 KIAS.\n\n" +
                "Check it against the stall-speed table printed for this aeroplane — the flight manual gives stall speeds at bank angles, and that table is the figure to write down.",
                "Load factor and the square-root rule: Pilot's Handbook of Aeronautical Knowledge, aerodynamics chapter, load factor in turns · the stall speeds: SportStar MAX Aircraft Operating Instructions, Section 5, Performance — stall speed table, and Section 2 for Vs0 37 and Vs1 38 KIAS.", null),
        ))

        private val AIRPORT = Sect("Airport / airspace", listOf(
            Q("1", "What are the traffic patterns for each runway at your home airport? What is the MSL altitude for the traffic pattern?",
                "Read the runways, and which of them fly right traffic, from the Chart Supplement entry for KVGT — it is in this app under Airports → KVGT → Chart Supplement, and the airport diagram shows the runways themselves. Any runway with right-hand traffic is marked RP in the Chart Supplement remarks and by the segmented circle at the field. Everything not marked is left traffic.\n\n" +
                "The pattern altitude: a light aeroplane flies the pattern 1,000 feet above the airport elevation unless the Chart Supplement says otherwise. So take the field elevation from the Chart Supplement entry and add 1,000 feet, and that is the MSL figure to write in. KVGT is a towered Class D field, so at the end of it the tower's instruction is what you fly.",
                "AIM 4-3-3 (traffic patterns) and AIM 4-3-4 (visual indicators at an airport without a tower) · the airport's own figures: the Chart Supplement entry for KVGT, in this app under Airports · 14 CFR 91.126(b) for the direction of turns.", null),
            Q("2", "How do you enter and exit the traffic pattern at your airport. What radio communications are required?",
                "KVGT has an operating control tower, so it is Class D and you may not enter that airspace until two-way radio communication has been established with the tower — that is, until the controller answers you using your call sign without telling you to stand by or to remain clear.\n\n" +
                "Entering: listen to the ATIS first, then call the tower before you reach the Class D boundary, giving who you are, where you are, your altitude, that you have the ATIS, and what you want. Then fly the entry the tower gives you — report to a point, join a leg, make straight in. Do not join on your own plan.\n\n" +
                "Leaving: ask the tower for the departure you want, fly the runway heading to the pattern altitude unless told otherwise, and stay with the tower until it hands you off or tells you a frequency change is approved.",
                "14 CFR 91.129(c) (two-way radio communications in Class D) · AIM 4-3-2 (airports with an operating control tower) and AIM 4-3-3 · the frequencies: the Chart Supplement entry for KVGT, in this app under Airports.", "91"),
            Q("3", "Describe how you would approach and enter the traffic pattern at an uncontrolled airport.",
                "Listen out on the CTAF well before you arrive, and build a picture of who is there and which runway is in use. Check the wind — the wind sock, the AWOS, the other traffic.\n\n" +
                "Then either:\n" +
                "• join the downwind on a 45 degree entry, at midfield, at pattern altitude, having arrived at the field already at pattern altitude from outside the pattern; or\n" +
                "• if you arrive from the dead side, overfly the field at least 500 feet above the pattern altitude, go out beyond the upwind, descend on the far side, and join the 45 to downwind — descending into the pattern over the field is how aeroplanes meet each other.\n\n" +
                "Fly the pattern at the published altitude and make the standard left turns unless right traffic is published. Announce on the CTAF at each point.",
                "AIM 4-3-3 and the figures with it · Advisory Circular 90-66 (latest revision), non-towered airport flight operations · 14 CFR 91.126 and 91.127.", null),
            Q("4", "What radio calls are recommended as you approach and fly in the traffic pattern at an uncontrolled airport?",
                "On the CTAF, each beginning and ending with the name of the airport, so that everyone knows which field you mean:\n" +
                "• 10 miles out: airport name, call sign, position, altitude, intention;\n" +
                "• entering downwind, giving the runway;\n" +
                "• turning base;\n" +
                "• turning final, giving the runway and whether it is a full stop or a touch and go;\n" +
                "• clear of the active runway.\n" +
                "On the ground: before taxiing, and before taking the runway for departure; and departing, which direction you are leaving.",
                "AIM 4-1-9, self-announce procedures, and its table of recommended calls · Advisory Circular 90-66 (latest revision).", null),
            Q("5", "What are the typical dimensions of Class D airspace and what requirement(s) must be met prior to entry?",
                "Typically a circle of about 4 nautical miles radius around the airport, from the surface up to and including 2,500 feet above the airport elevation — the figure is rounded to the nearest 100 feet and published on the chart in a dashed blue segmented box. The shape is tailored to the field, with cut-outs and extensions for the instrument approaches.\n\n" +
                "To enter: the aircraft must have an operable two-way radio, and two-way radio communication must be established with the control tower before entering, and kept while in the airspace. Communication is established when the controller answers with your call sign. If the reply is your call sign followed by 'remain outside the Class D airspace' — or just 'standby' — you stay out.",
                "14 CFR 91.129(a) and (c) · AIM 3-2-5 (Class D airspace) · Pilot/Controller Glossary, two-way radio communications failure and the ATC phraseology.", "91"),
            Q("6", "How can you tell if a runway is closed?",
                "• A yellow X on the runway at each end — painted, or a lighted X placed there, or an X-shaped marker; that is the sign for a closed runway.\n" +
                "• The runway markings and the threshold markings obliterated, and the lights turned off or the approach lights off.\n" +
                "• A NOTAM — read before every flight; the closure appears there first.\n" +
                "• The ATIS, or the tower, or the CTAF.",
                "AIM 2-3-6 (runway closure markings) and AIM 2-1 for the lighted X · NOTAMs: AIM 5-1-3 and 14 CFR 91.103 (preflight action).", null),
            Q("7", "If you receive ATC instructions that you do not understand or feel may compromise safety, what should you do?",
                "Say so, straight away, on the radio. Ask the controller to say again, to speak slower, or to confirm — there is no cost to asking. If the instruction is one you cannot safely or legally fly, answer 'unable' and say what you can do instead, and ask for an alternative.\n\n" +
                "A clearance is not an order to do something unsafe: you are the pilot in command, and in an in-flight emergency you may deviate from any rule of Part 91 to the extent required to meet that emergency — and if you do, the controller is told, and the Administrator may ask for a written report.",
                "AIM 4-4-1 (ATC clearance, and the pilot's responsibility) and AIM 4-4-10 · 14 CFR 91.3(b) and (c) · 14 CFR 91.123 (compliance with ATC clearances and instructions).", "91"),
            Q("8", "Describe lost comms procedures at KVGT.",
                "KVGT is Class D with an operating tower, so the question is a radio failure arriving at or leaving a towered field.\n\n" +
                "First work the problem: check the volume, the squelch, the frequency, the headset plugs, the audio panel, the other radio, the circuit breaker. Squawk 7600.\n\n" +
                "Arriving: stay outside or clear of the Class D airspace until you have worked out the direction and flow of traffic, then join the pattern and look at the tower for light-gun signals. Acknowledge a signal by rocking your wings by day, or by flashing the landing light or the navigation lights at night. Then land as the signals tell you, and clear the runway.\n\n" +
                "Departing or in the pattern: if the radio fails after you are already in the Class D, keep flying the pattern, watch the tower for the light signals, and acknowledge them the same way. If you can receive but not transmit, tell the tower so and acknowledge its instructions by rocking the wings or by the landing light.\n\n" +
                "A telephone call to the tower afterwards is the courteous end of it.",
                "AIM 4-2-13 (communications failure) and AIM 4-3-13 (traffic control light signals, with the acknowledgement by rocking wings or flashing the landing light) · 14 CFR 91.125 (ATC light signals) and 91.129(d) · the tower telephone number: the Chart Supplement entry for KVGT.", "91"),
            Q("9", "What is the meaning of each of the following ATC light signals? Steady green · Flashing green · Steady red · Flashing red · White · Alternating red/green",
                "In flight:\n" +
                "• Steady green — cleared to land.\n" +
                "• Flashing green — return for landing (a steady green will follow at the proper time).\n" +
                "• Steady red — give way to other aircraft and continue circling.\n" +
                "• Flashing red — airport unsafe, do not land.\n" +
                "• Flashing white — no meaning in flight.\n" +
                "• Alternating red and green — exercise extreme caution.\n\n" +
                "On the ground:\n" +
                "• Steady green — cleared for take-off.\n" +
                "• Flashing green — cleared to taxi.\n" +
                "• Steady red — stop.\n" +
                "• Flashing red — taxi clear of the runway in use.\n" +
                "• Flashing white — return to the starting point on the airport.\n" +
                "• Alternating red and green — exercise extreme caution.",
                "AIM 4-3-13, the light-signal table · 14 CFR 91.125. The same table is in this app under Study → Checkride prep.", "91"),
            Q("10", "What aircraft equipment and student pilot authorizations are required for a student pilot to fly solo in Class B airspace?",
                "The equipment: a two-way radio capable of communicating with ATC on the appropriate frequencies, an operable transponder with Mode C altitude reporting, and ADS-B Out. (A VOR or TACAN receiver is required for IFR.) An ATC clearance to enter is required of everyone, and you must hear the words 'cleared into the Class B airspace'.\n\n" +
                "The authorisations: a student pilot needs ground and flight training from an authorised instructor on that specific Class B airspace, and a logbook endorsement from that instructor for that specific Class B airspace, given within the preceding 90 days.\n\n" +
                "And some Class B primary airports are closed to student pilots altogether — the list is in Part 91, Appendix D, Section 4; no student solo take-offs or landings there whatever the endorsement.",
                "14 CFR 61.95 (student pilot operations in Class B airspace) · 14 CFR 91.131 (operations in Class B) and 91.215, 91.225 · 14 CFR Part 91, Appendix D, Section 4 · AIM 3-2-3.", "61"),
            Q("11", "A magenta dashed line surrounds certain uncontrolled airports. What does this indicate and what is its significance to VFR pilots?",
                "It is a Class E surface area — controlled airspace that begins at the surface at an airport that has no operating control tower, put there so that instrument traffic is protected right down to the ground.\n\n" +
                "What it means to you: the airspace is controlled from the surface up, so the Class E weather minimums apply at the surface — 3 statute miles visibility and 500 below, 1,000 above, 2,000 horizontal from cloud. You do not need a clearance and you do not need to talk to anyone to fly VFR in it, but you cannot get in or out of that airport in weather below those minimums without a special VFR clearance. And instrument traffic may be breaking out of cloud there, so look out.",
                "AIM 3-2-6 (Class E airspace) · 14 CFR 91.155 for the minimums · the Aeronautical Chart User's Guide, the VFR chart legend — dashed magenta is Class E to the surface, a magenta vignette is Class E from 700 feet AGL.", "91"),
            Q("12", "On a sectional, what does a dashed blue line around an airport indicate?",
                "Class D airspace: an airport with an operating control tower. Inside the line a dashed blue box gives the ceiling in hundreds of feet MSL — for example [25] means the airspace goes up to and including 2,500 feet MSL.\n\n" +
                "Because the tower may only operate part of the day, the Chart Supplement is read for the hours; when the tower is closed the airspace normally reverts to Class E or Class G.",
                "AIM 3-2-5 (Class D) · the Aeronautical Chart User's Guide, VFR chart legend · the hours of operation: the Chart Supplement entry for the airport.", null),
            Q("13", "What are the minimum visibility and ceiling requirements for VFR flight in Class D airspace?",
                "Flight visibility 3 statute miles, with 500 feet below, 1,000 feet above and 2,000 feet horizontal cloud clearance.\n\n" +
                "And for taking off, landing or entering the traffic pattern at an airport in Class D: the ground visibility at that airport must be at least 3 statute miles (or, if none is reported, the flight visibility during landing or take-off must be at least 3 statute miles), and the ceiling must be at least 1,000 feet. Below that it is special VFR or nothing.",
                "14 CFR 91.155(a) table, and 91.155(c) and (d) · AIM 3-2-5.", "91"),
            Q("14", "Prior to taking the runway at an uncontrolled airport, it is recommended to maneuver the airplane as needed to view the final approach area to confirm that there is no other landing traffic. At an airport with a control tower is this still a recommended maneuver? Explain your answer.",
                "Yes. A clearance to take the runway is not a guarantee that the final approach is clear: the controller can be mistaken, another aeroplane can be on a straight-in without talking, and you are the one who will be in the way. Clearing the final approach path with your own eyes before you cross a hold line or line up costs two seconds and has prevented a great many runway incursions and collisions.\n\n" +
                "At a towered field it is done in addition to, never instead of, the clearance — you still hold until the tower clears you, and then you look.",
                "AIM 4-3-18 and AIM 4-3-20 (taxiing and crossing runways) · Advisory Circular 91-73 (latest revision), parts 91 and 135 single-pilot procedures during taxi operations · 14 CFR 91.3(a).", null),
            Q("15", "What is the standard direction of turn in the traffic pattern? Give an example of a visual display indicating a non-standard traffic pattern.",
                "Standard is left turns. Approaching to land at an airport without an operating control tower, each turn of the traffic pattern is made to the left unless the airport displays approved light signals or visual markings indicating that turns should be made to the right.\n\n" +
                "The visual display: the segmented circle at the field, with traffic pattern indicators — L-shaped extensions off the circle whose short leg shows the direction of the base-to-final turn. If the short legs point right, that runway is right traffic. The landing direction indicator (tetrahedron) and the wind sock sit in the middle. In print, right traffic is shown as 'RP' with the runway number in the Chart Supplement.",
                "14 CFR 91.126(b) and 91.127 · AIM 4-3-4 (visual indicators at airports without an operating control tower) and its figure of the segmented circle.", "91"),
            Q("16", "What is the purpose of CTAF?",
                "The Common Traffic Advisory Frequency is the one frequency on which all the traffic at an airport without an operating control tower talks, so that pilots can broadcast where they are and what they intend, and hear everyone else do the same. It is how separation is arranged when no one is arranging it for you.\n\n" +
                "It may be a UNICOM, a MULTICOM, an FSS frequency, or the tower frequency when the tower is closed. It is marked on the chart and in the Chart Supplement with a white C in a solid magenta circle.",
                "AIM 4-1-9 (traffic advisory practices at airports without operating control towers) · Pilot/Controller Glossary, CTAF · Advisory Circular 90-66 (latest revision).", null),
            Q("17", "You call KVGT Tower prior to entering the airspace and the controller tells you 'N79EV, Standby.' Are you now allowed to enter the airspace without any further instructions? Explain.",
                "No. Remain outside the Class D airspace.\n\n" +
                "Two-way radio communication is established when the controller answers with your call sign. But 'standby' means the controller has heard you and wants you to wait — it is an acknowledgement, not a response to your request, and it does not establish the communication that 91.129 requires for entry. The same is true of 'aircraft calling, standby'.\n\n" +
                "If the controller had said 'N79EV, remain outside the Class D airspace and standby', that is plainer still. Either way: hold outside, or orbit clear of the boundary, until you are answered properly and given an instruction.",
                "14 CFR 91.129(c)(1) · AIM 3-2-5 and AIM 4-3-2, which give this exact example · Pilot/Controller Glossary, 'standby'.", "91"),
            Q("18", "Define the following airport markings: a runway direction sign reading 27-33 with an arrow · the taxiway holding position marking · a sign reading B with an arrow · a sign reading 14-32 · a sign reading A",
                "• 27-33 with an arrow, black on yellow — a runway direction or runway exit sign. It points the way to runway 27-33 from where you are. A yellow background with black lettering always means 'this way to', never 'stop'.\n\n" +
                "• Four lines across the taxiway, two solid and two dashed — the runway holding position marking. The solid pair is always on the side you are approaching from: you hold short of the solid lines until cleared, and you may cross the dashed lines freely coming off the runway.\n\n" +
                "• B with an arrow, black on yellow — a taxiway direction sign: taxiway B lies in the direction of the arrow.\n\n" +
                "• 14-32, white on red — a mandatory instruction sign, the runway holding position sign. It stands at the hold line for runway 14-32. Do not pass it without a clearance.\n\n" +
                "• A on black with a yellow border and yellow letter — a taxiway location sign: you are on taxiway A now.\n\n" +
                "The whole family in one line: red with white letters tells you to stop, yellow with black letters tells you where to go, black with yellow letters tells you where you are.",
                "AIM 2-3-4 and 2-3-5 (runway holding position markings), 2-3-8 (mandatory instruction signs), 2-3-9 (location signs), 2-3-10 (direction signs) — all with colour figures · Advisory Circular 150/5340-18 for the signing standard · the Pilot's Handbook of Aeronautical Knowledge, airport operations chapter, reprints the same figures.", null),
        ))

        private val SECTIONS = listOf(GENERAL, AIRCRAFT, AIRPORT)
    }
}
