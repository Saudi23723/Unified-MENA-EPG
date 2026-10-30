package com.saudi.privatevault

import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Study with Gemini as the instructor: radio calls (Gemini plays the tower,
 * ground, approach or the traffic on the CTAF, with the real local
 * frequencies, grades each call and says it aloud) and weather (live METARs
 * and TAFs to decode, lessons, go/no-go decisions).
 */
class TrainerActivity : BaseActivity() {

    private lateinit var col: LinearLayout
    private fun dp(v: Int) = EfbUi.dp(this, v)

    private class Lesson(val icon: String, val title: String, val sub: String, val scenario: String)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.tr_title))
        col.addView(EfbUi.text(this, getString(R.string.tr_intro), 13f, EfbUi.DIM).apply { setPadding(dp(4), dp(4), dp(4), dp(4)) })

        group(getString(R.string.tr_radio), listOf(
            Lesson("🛫", "KBVU · CTAF departure", "Self-announce: taxi, takeoff, departing the pattern", "Departure from KBVU (non-towered): start-up, listen to AWOS, taxi, run-up, takeoff and departing the pattern, all self-announced on the CTAF, with other traffic in the pattern calling too."),
            Lesson("🛬", "KBVU · CTAF arrival & pattern", "10 nm out, 45° entry, downwind, base, final", "Arrival back to KBVU from 10 nm south-east at 5,500 ft: AWOS, the 10-mile call, 45° entry to downwind, downwind, base, final, clear of the runway, with traffic in the pattern."),
            Lesson("🗼", "KVGT · North Las Vegas tower (Class D)", "ATIS, ground, taxi, takeoff clearance", "Departure from North Las Vegas KVGT (Class D, towered): ATIS, ground for taxi (readback of the runway and hold short), tower for takeoff, departure instructions."),
            Lesson("🗼", "KHND · Henderson tower (Class D)", "Inbound from Boulder City to land", "Inbound to Henderson Executive KHND (Class D) from Boulder City at 4,500 ft: ATIS, first call to tower with position and intentions, pattern entry instructions, landing clearance, taxi."),
            Lesson("📡", "Las Vegas Approach · flight following", "VFR flight following KBVU → Kingman", "After departing KBVU, request VFR flight following to Kingman KIGM from Las Vegas Approach: first contact, the request, squawk and altimeter readback, traffic advisories, frequency change, terminating."),
            Lesson("🛑", "Class B · transition request", "Ask for and hear 'cleared into Class Bravo'", "Near the Las Vegas Class B: request a transition, and know that you need the words 'cleared into the Class Bravo airspace'. Include being told to remain outside, and a clearance with altitude and heading restrictions to read back."),
            Lesson("🆘", "Emergency · engine failure", "MAYDAY on 121.5 or Approach, squawk 7700", "Engine failure over the desert at 6,500 ft between KBVU and KIGM: the MAYDAY call (three times, callsign, position, nature, intentions, souls on board, fuel), squawk 7700, and the controller's help."),
            Lesson("🔦", "Lost comms & light gun signals", "What to do, and each signal on the ground and in the air", "Quiz on radio failure in VFR: squawk 7600, and the tower light gun signals (steady green, flashing green, steady red, flashing red, flashing white, alternating red/green) on the ground and in the air."),
            Lesson("🔤", "Phraseology drill", "Numbers, altitudes, frequencies, phonetics", "Quick drill on radio phraseology: phonetic alphabet, how to say numbers, altitudes, headings, frequencies and squawks, callsign abbreviation, 'roger', 'wilco', 'affirmative', 'unable', 'say again'. Give one item at a time."),
        ), radio = true)

        group(getString(R.string.tr_weather), listOf(
            Lesson("📟", "METAR decoding · live", "Real METARs around Las Vegas, one by one", "LIVE_METAR"),
            Lesson("🔮", "TAF decoding · live", "The Las Vegas TAF, period by period", "LIVE_TAF"),
            Lesson("✅", "Go / no-go · today", "Today's weather KBVU → Kingman: would you go?", "LIVE_GONOGO"),
            Lesson("☁️", "Clouds, fog & visibility", "Types, how fog forms, VFR minimums (91.155)", "Clouds, fog and visibility: cloud types and what they mean for a VFR pilot, how each kind of fog forms, and the VFR weather minimums of 14 CFR 91.155 by airspace class."),
            Lesson("🌀", "Air masses & fronts", "Cold, warm, stationary, occluded", "Air masses and fronts: what each front brings (clouds, winds, turbulence, visibility) and how to see one coming on the charts."),
            Lesson("⛈", "Thunderstorms & microbursts", "Stages, hazards, how far to stay away", "Thunderstorms: the three stages, hazards (hail, microbursts, lightning, turbulence), why to stay 20 nm away, and the monsoon season around Las Vegas."),
            Lesson("🌡", "Density altitude · Las Vegas summer", "What heat does to a SportStar's takeoff and climb", "Density altitude: how it is found, what it does to engine power, the propeller and the wing, and a hot summer day at KBVU (elevation 2,201 ft) in a SportStar MAX."),
            Lesson("🌬", "Wind, shear & mountain waves", "Spring Mountains, gusts, crosswind limits", "Wind: shear, gusts, mountain waves and rotors near the Spring Mountains and the River Mountains, and the SportStar's 16 kt demonstrated crosswind."),
            Lesson("🗺", "Weather charts & reports", "GFA, prog charts, AIRMET/SIGMET, PIREP, winds aloft", "Weather products a VFR pilot uses: the Graphical Forecasts for Aviation, prog charts, AIRMETs (Sierra, Tango, Zulu), SIGMETs, convective SIGMETs, PIREPs and the winds and temperatures aloft (FB)."),
            Lesson("📉", "Pressure & altimeter", "High to low, look out below; standard pressure", "Pressure and the altimeter: setting it, 'high to low, look out below', temperature errors, pressure altitude and standard atmosphere."),
        ), radio = false)
        EfbUi.stagger(col)
    }

    private fun group(title: String, items: List<Lesson>, radio: Boolean) {
        col.addView(EfbUi.text(this, title.uppercase(), 12f, EfbUi.DIM, bold = true).apply { letterSpacing = 0.08f; setPadding(dp(6), dp(20), dp(6), dp(6)) })
        val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@TrainerActivity, EfbUi.CARD, 16).apply { setStroke(0, 0) } }
        for ((i, l) in items.withIndex()) {
            if (i > 0) card.addView(android.view.View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(56) })
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(14), dp(11), dp(12), dp(11)) }
            row.addView(EfbUi.text(this, l.icon, 20f), LinearLayout.LayoutParams(dp(34), -2))
            val t = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(8), 0, 0, 0) }
            t.addView(EfbUi.ltr(EfbUi.text(this, l.title, 15.5f, EfbUi.TEXT, bold = true)))
            t.addView(EfbUi.ltr(EfbUi.text(this, l.sub, 12.5f, EfbUi.DIM)))
            row.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
            row.setOnClickListener { start(l, radio) }
            card.addView(row)
        }
        col.addView(card)
    }

    private fun lang() = if (Gemini.english(this)) "Write all feedback in English."
        else "Write the feedback and explanations in Arabic (Levantine-friendly), keeping aviation terms in English; radio calls always in English."

    /** The real local frequencies, from the app's frequency list. */
    private fun freqs(): String {
        val out = StringBuilder()
        for ((ident, icao) in listOf("BVU" to "KBVU", "VGT" to "KVGT", "HND" to "KHND", "LAS" to "KLAS")) {
            val a = AviationData.Airport(ident, icao, icao, "", 0, 0.0, 0.0)
            val fs = Frequencies.shipped(this, a)
            if (fs.isNotEmpty()) out.append("$icao: " + fs.joinToString(", ") { "${it.kind.label} ${Frequencies.mhz(it.mhz)}" } + "\n")
        }
        return out.toString()
    }

    private fun start(l: Lesson, radio: Boolean) {
        lifecycleScope.launch {
            val f = withContext(Dispatchers.IO) { freqs() }
            if (radio) {
                val system = """
You are a realistic FAA air traffic controller, and at the same time a radio-communication instructor, training a student pilot.
The pilot flies an Evektor SportStar MAX, callsign "Sportstar N19EV" ("Sportstar one niner echo victor"), based at Boulder City Municipal, KBVU (non-towered, CTAF). Elevation 2,201 ft.
Local frequencies (from the FAA/OurAirports lists; say so if one may have changed):
$f
Scenario: ${l.scenario}

How every turn goes:
1. If the pilot just made a radio call, grade it in two or three short lines: what was right, what was missing or wrong (who you are calling, who you are, where you are, what you want; readbacks of runway, hold short, altitude, heading, squawk, altimeter; correct phraseology per AIM chapter 4 and the Pilot/Controller Glossary). Then show the ideal call on a line starting with "IDEAL:".
2. Then answer exactly as heard on the radio, on its own line starting with the station in capitals and a colon: "TOWER:", "GROUND:", "APPROACH:", "ATIS:", "AWOS:", or "TRAFFIC:" for another aircraft on the CTAF.
3. End with a line starting "YOUR TURN:" saying what the pilot should do or say next, without the exact words unless they ask for a hint.
Start by setting the scene (where the aircraft is, altitude, weather, which frequency the pilot is on) and ask for the first call. Keep each answer short, as on a real frequency.
${lang()}
""".trimIndent()
                AiChatActivity.openTrainer(this@TrainerActivity, "🎧 ${l.title}", system, getString(R.string.tr_radio_hello),
                    listOf(getString(R.string.tr_c_hint) to "Give me a hint for my next call.", getString(R.string.tr_c_ideal) to "Show me the ideal call now and explain each part.",
                        getString(R.string.tr_c_again) to "Start the scenario again with different traffic and weather.", getString(R.string.tr_c_score) to "Give me my score for the calls so far, out of 10, with what to practise."),
                    radio = true, start = "Start the scenario.")
            } else {
                val live = withContext(Dispatchers.IO) { liveData(l.scenario) }
                val scenario = when (l.scenario) {
                    "LIVE_METAR" -> "Decode real current METARs, one at a time. Give the raw METAR, ask the student to decode it (wind, visibility, weather, clouds, temperature/dew point, altimeter, remarks) and say the flight category and whether VFR is possible; then correct and explain. Real METARs now:\n$live"
                    "LIVE_TAF" -> "Decode the real current TAF period by period: ask the student what each group means (FM, TEMPO, PROB30, BECMG, wind, visibility, clouds), correct and explain. Real TAF now:\n$live"
                    "LIVE_GONOGO" -> "A go/no-go decision for a VFR flight today from KBVU to Kingman KIGM in a SportStar MAX (16 kt demonstrated crosswind, VFR only). Using the real current data below, ask the student for their decision and the reasons (ceilings, visibility, winds and crosswind on each runway, gusts, density altitude, trends in the TAF), then give the instructor's view with the PAVE and IMSAFE checklists. Real data now:\n$live"
                    else -> l.scenario
                }
                val system = """
You are a patient CFI teaching aviation weather to a student pilot training for the Private Pilot certificate (Private Pilot ACS, area I.C Weather Information), flying a SportStar MAX from Boulder City KBVU near Las Vegas.
Topic: $scenario
Teach interactively: a short explanation, then a question for the student; correct their answer, explain why, and go on. Use real examples from around Las Vegas. Refer to the FAA Aviation Weather Handbook (FAA-H-8083-28), the PHAK and the AIM chapter 7 where useful. Use short bullet points and bold for key terms.
${lang()}
""".trimIndent()
                AiChatActivity.openTrainer(this@TrainerActivity, "🌤 ${l.title}", system, getString(R.string.tr_wx_hello),
                    listOf(getString(R.string.tr_c_next) to "Next one.", getString(R.string.tr_c_explain) to "Explain that again more simply.",
                        getString(R.string.tr_c_quiz) to "Quiz me with 5 questions on this, one at a time.", getString(R.string.tr_c_checkride) to "What would the examiner ask me about this on the checkride?"),
                    radio = false, start = "Begin.")
            }
        }
    }

    /** Real METARs and TAFs for the live lessons. */
    private fun liveData(kind: String): String = try {
        when (kind) {
            "LIVE_METAR" -> AviationData.get("https://aviationweather.gov/api/data/metar?ids=KBVU,KLAS,KHND,KVGT,KIGM,KPHX,KLAX,KSLC,KRNO,KFLG&format=raw").trim()
            "LIVE_TAF" -> AviationData.get("https://aviationweather.gov/api/data/taf?ids=KLAS&format=raw").trim()
            "LIVE_GONOGO" -> AviationData.get("https://aviationweather.gov/api/data/metar?ids=KBVU,KIGM,KLAS&format=raw").trim() + "\n\n" +
                AviationData.get("https://aviationweather.gov/api/data/taf?ids=KLAS,KIGM&format=raw").trim()
            else -> ""
        }
    } catch (e: Exception) {
        "(No live data now: use typical real examples from the Las Vegas area and say so.)"
    }
}
