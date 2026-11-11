package com.saudi.privatevault

import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Everything the Private Pilot knowledge test and checkride ask, gathered from the Library into
 * one study page: by the ACS's areas of operation, the rules and numbers to know cold with their
 * memory aids, each with the way to its source (the FARs in the app, the Jeppesen maneuvers, the
 * animated maneuvers), what to bring on the day, and flash cards to test yourself.
 */
class CheckrideActivity : BaseActivity() {

    private class Link(val label: String, val go: (CheckrideActivity) -> Unit)
    private class Topic(val title: String, val facts: List<Pair<String, String>>, val links: List<Link> = emptyList())
    private class Area(val code: String, val title: String, val topics: List<Topic>)

    private lateinit var col: LinearLayout
    private fun dp(v: Int) = EfbUi.dp(this, v)

    private fun far(part: String, label: String = "14 CFR $part") = Link("⚖️ $label") { RegsActivity.open(it, 14, part) }
    private fun book(no: Int) = Link("📘 Jeppesen maneuver $no") { JeppBookActivity.open(it, no) }
    private fun anim(id: String) = Link("▶ Animated: ${Maneuvers.byId(id)?.title ?: id}") { ManeuversActivity.open(it, id) }
    private val library = Link("📚 Library (PHAK, AFH, AIM, ACS)") { it.startActivity(Intent(it, LibraryActivity::class.java)) }

    private val areas by lazy { listOf(
        Area("I", "Preflight preparation", listOf(
            Topic("Pilot qualifications", listOf(
                "Aeronautical experience (61.109)" to "40 h total: 20 h dual — 3 h cross-country, 3 h night (one XC over 100 NM total, 10 night takeoffs and full-stop landings), 3 h by instruments, 3 h test prep within 2 calendar months — and 10 h solo: 5 h solo XC, one 150 NM total with full-stop landings at 3 points and one leg over 50 NM, 3 takeoffs and landings at a towered field",
                "Passenger currency (61.57)" to "3 takeoffs and landings in the preceding 90 days, same category and class; at night: 3 to a full stop, from 1 h after sunset to 1 h before sunrise",
                "Flight review (61.56)" to "Every 24 calendar months: at least 1 h of ground and 1 h of flight",
                "Medical (61.23)" to "Third class: 60 calendar months under age 40, 24 calendar months from 40 — or BasicMed (Part 68)",
                "Carry (61.3)" to "Pilot certificate, medical (or BasicMed papers), government photo ID",
                "Privileges (61.113)" to "No pay; you may share the operating expenses (fuel, oil, airport fees, rental) with passengers, paying at least your equal share",
                "Change of address (61.60)" to "Tell the FAA within 30 days",
            ), listOf(far("61"), far("68", "14 CFR 68 · BasicMed"))),
            Topic("Airworthiness", listOf(
                "Documents on board — ARROW" to "Airworthiness certificate · Registration (valid 7 years) · Radio station licence (international flights) · Operating limitations (POH/AFM, placards) · Weight and balance",
                "Inspections — AV1ATE" to "Annual (12 calendar months) · VOR check (30 days, IFR) · 100-hour (for hire or instruction) · Altimeter/static (24 calendar months, IFR) · Transponder (24 calendar months) · ELT (12 calendar months; battery after 1 h of use or half its life)",
                "Day VFR equipment (91.205) — A TOMATO FLAMES" to "Airspeed · Tachometer · Oil pressure · Manifold pressure · Altimeter · Temperature (liquid-cooled) · Oil temperature · Fuel gauges · Landing-gear position · Anticollision lights · Magnetic compass · ELT · Safety belts",
                "Night VFR adds — FLAPS" to "Fuses · Landing light (for hire) · Anticollision lights · Position lights · Source of electricity",
                "Something inoperative (91.213, no MEL)" to "Not required by 91.205, the equipment list/KOEL, an AD or the type certificate → remove or deactivate it, placard INOPERATIVE, and decide it is no hazard",
                "Airworthiness Directives (Part 39)" to "Mandatory; compliance is recorded in the maintenance records",
                "Preventive maintenance" to "What a pilot may do: Part 43 Appendix A (oil change, tyres, lights…), and sign for it",
            ), listOf(far("91", "14 CFR 91 · 91.205, 91.213"), far("43"), far("39"))),
            Topic("Weather information", listOf(
                "Flight categories" to "VFR: ceiling above 3,000 ft and visibility over 5 SM · MVFR: 1,000–3,000 ft and/or 3–5 SM · IFR: 500 to under 1,000 ft and/or 1 to under 3 SM · LIFR: below 500 ft and/or under 1 SM",
                "AIRMETs" to "Sierra: IFR and mountain obscuration · Tango: moderate turbulence, surface winds 30 kt+, low-level wind shear · Zulu: moderate icing and freezing levels",
                "SIGMET" to "Severe icing, severe or extreme turbulence, dust or sand storms, volcanic ash — for every aircraft",
                "Convective SIGMET" to "Thunderstorms: lines, embedded, areas of 40 % coverage or more, tornadoes, hail ¾\" or more, surface winds 50 kt+",
                "Standard lapse rates" to "Temperature 2 °C per 1,000 ft · pressure about 1 inHg per 1,000 ft",
                "Thunderstorm" to "Needs moisture, unstable air and lifting; cumulus → mature (rain starts) → dissipating. Avoid by 20 NM.",
                "Fog" to "Radiation (calm clear nights), advection (moist air over cold ground or water), upslope, steam, precipitation-induced",
            ), listOf(library)),
            Topic("Cross-country & regulations to know", listOf(
                "Preflight action (91.103) — NWKRAFT" to "NOTAMs · Weather · Known ATC delays · Runway lengths · Alternatives · Fuel · Takeoff and landing distances",
                "Fuel (91.151)" to "Day VFR: to the first point of landing + 30 min · Night: + 45 min",
                "VFR cruising altitudes (91.159)" to "Above 3,000 ft AGL: magnetic course 0–179° odd thousands + 500 · 180–359° even thousands + 500",
                "Minimum safe altitudes (91.119)" to "Anywhere: high enough for an emergency landing · Congested area: 1,000 ft above the highest obstacle within 2,000 ft · Elsewhere: 500 ft from any person, vessel, vehicle or structure",
                "Right of way (91.113)" to "Distress first · balloon > glider > airship > airplane/rotorcraft · converging: the one on the right · head-on: both turn right · overtaking: pass on the right · landing: the lower one",
                "Alcohol (91.17)" to "8 hours bottle to throttle, under 0.04 %, not under the influence",
                "Oxygen (91.211)" to "Crew: above 12,500 to 14,000 ft MSL after 30 min, and all the time above 14,000 · Passengers: provided above 15,000",
                "Lights (91.209)" to "Position lights sunset to sunrise",
                "Night for logging (Part 1)" to "End of evening civil twilight to the beginning of morning civil twilight",
                "Accidents (NTSB 830)" to "Notify immediately; written report within 10 days (incidents on request)",
            ), listOf(far("91"), Link("⚖️ 49 CFR 830 · NTSB") { RegsActivity.open(it, 49, "830") })),
            Topic("National airspace", listOf(
                "VFR weather minimums (91.155)" to "Class B: 3 SM, clear of clouds · Class C, D: 3 SM, 500 below, 1,000 above, 2,000 horizontal · Class E below 10,000 MSL: same 3 SM 152 · At/above 10,000 MSL: 5 SM, 1,000 below, 1,000 above, 1 SM horizontal",
                "Class G" to "At or below 1,200 AGL: day 1 SM clear of clouds, night 3 SM 152 · Above 1,200 AGL below 10,000 MSL: day 1 SM 152, night 3 SM 152",
                "Surface areas (91.155(c),(d))" to "Ceiling at least 1,000 ft and 3 SM visibility to enter or take off; Special VFR: 1 SM and clear of clouds (at night only with an instrument rating and an IFR airplane)",
                "Class B" to "Clearance (\"cleared into the Bravo\"), two-way radio, Mode C and ADS-B Out; 30 NM Mode C veil",
                "Class C" to "Two-way radio established before entering, Mode C and ADS-B Out; usually 5 NM from the surface and a 10 NM shelf from 1,200 ft, to 4,000 ft AGL",
                "Class D" to "Two-way radio established before entering; surface to about 2,500 ft AGL",
                "Speeds (91.117)" to "250 KIAS below 10,000 MSL · 200 KIAS within 4 NM of a C or D airport below 2,500 AGL, and under the Class B shelf",
                "ADS-B Out (91.225)" to "Class A, B, C; within the 30 NM veil; above 10,000 MSL (not below 2,500 AGL); above Class B or C up to 10,000 ft",
                "Special use" to "Prohibited: no entry · Restricted: with permission · MOA: VFR allowed, be careful · Warning, Alert, MTRs, TFRs (check NOTAMs)",
                "Squawks" to "1200 VFR · 7500 hijack · 7600 lost radio · 7700 emergency",
            ), listOf(far("91", "14 CFR 91 · 91.155, 91.117, 91.225"), far("71"), far("73"))),
            Topic("Performance & limitations", listOf(
                "SportStar MAX speeds (POH)" to "VS 38, VS0 37 KIAS · Vx 56 (54 with flaps 15°) · Vy 65 · VA 90 · VFE 70 · VNO 115 · VNE 146 · best glide 59 · final 60",
                "Weights" to "Maximum takeoff weight 1,320 lb (600 kg)",
                "Distances (POH, paved)" to "Takeoff run 620 ft, over 50 ft 1,440 ft · Landing over 50 ft 1,310 ft, run 590 ft · tailwind +4 % (takeoff) / +4.5 % (landing) per kt",
                "Wind limits" to "Demonstrated crosswind 16 kt · tailwind 6 kt",
                "Density altitude" to "Higher, hotter, more humid → longer takeoff, worse climb; pressure altitude corrected for non-standard temperature",
                "Weight and balance" to "Moment = weight × arm · CG = total moment ÷ total weight · aft CG: less stable, harder stall recovery",
            ), listOf(Link("🛫 Performance calculator") { it.startActivity(Intent(it, PerformanceActivity::class.java)) },
                Link("⚖️ Weight & balance") { it.startActivity(Intent(it, WeightBalanceActivity::class.java)) })),
            Topic("Human factors", listOf(
                "Fit to fly — IMSAFE" to "Illness · Medication · Stress · Alcohol · Fatigue · Emotion (or Eating)",
                "Risk — PAVE" to "Pilot · Aircraft · enVironment · External pressures",
                "Decide — DECIDE" to "Detect · Estimate · Choose · Identify · Do · Evaluate",
                "Hazardous attitudes" to "Anti-authority → \"Follow the rules\" · Impulsivity → \"Not so fast, think first\" · Invulnerability → \"It could happen to me\" · Macho → \"Taking chances is foolish\" · Resignation → \"I'm not helpless\"",
                "Hypoxia" to "Hypoxic (altitude) · Hypemic (blood: CO, anaemia) · Stagnant (circulation, g) · Histotoxic (alcohol, drugs)",
                "Hyperventilation" to "Too much breathing out CO2: tingling, dizziness — slow the breathing, talk aloud",
                "Spatial disorientation" to "The inner ear lies without a horizon (the leans, graveyard spiral): trust the instruments",
                "Carbon monoxide" to "Headache, drowsiness: heat off, fresh air, land",
            )),
        )),
        Area("II–III", "Preflight procedures & airport operations", listOf(
            Topic("Airport operations", listOf(
                "Light gun — in flight" to "Steady green: cleared to land · Flashing green: return for landing · Steady red: give way, keep circling · Flashing red: airport unsafe, do not land · Alternating red/green: extreme caution",
                "Light gun — on the ground" to "Steady green: cleared for takeoff · Flashing green: cleared to taxi · Steady red: stop · Flashing red: taxi clear of the runway · Flashing white: return to the start",
                "Traffic pattern" to "Left turns unless marked; enter 45° to downwind at pattern altitude (usually 1,000 ft AGL); depart straight out or 45° after reaching pattern altitude",
                "Runway markings" to "Hold-short: two solid and two dashed yellow lines, stop on the solid side · Displaced threshold: taxi and take off on it, do not land before the bar · Chevrons: blast pad, no use",
                "Wake turbulence" to "Land beyond a heavy's touchdown point; take off before its rotation point; wait 2–3 min",
                "Collision avoidance" to "Scan in 10° sectors, a second each; clearing turns before maneuvers",
            ), listOf(anim("pattern"), book(12))),
        )),
        Area("IV", "Takeoffs, landings & go-arounds", listOf(
            Topic("Maneuvers and standards", listOf(
                "Normal / crosswind" to "Climb Vy +10/−5 kt · land within 400 ft beyond the point, no drift, centerline",
                "Short field" to "Vx +10/−5 to clear the obstacle · approach 1.3 VS0 +5/−0 · land within 200 ft beyond the point",
                "Soft field" to "Weight off the nosewheel, stay in ground effect · touch down at the slowest speed",
                "Forward slip" to "Land within 400 ft beyond the point, recover before the flare",
                "Go-around" to "Full power, pitch, flaps 15°, climb, clean up; decide early",
            ), listOf(anim("normal_to"), anim("short_ldg"), anim("soft_to"), anim("slip"), anim("go_around"), book(13), book(29))),
        )),
        Area("V", "Performance & ground reference maneuvers", listOf(
            Topic("Standards", listOf(
                "Steep turns" to "45° ±5° bank · altitude ±100 ft · airspeed ±10 kt · roll out ±10° · at or below VA",
                "Ground reference" to "600–1,000 ft AGL · altitude ±100 ft · airspeed ±10 kt · steepest bank downwind (highest groundspeed)",
            ), listOf(anim("steep"), anim("rect"), anim("sturns"), anim("tap"), book(24), book(25))),
        )),
        Area("VI", "Navigation", listOf(
            Topic("Navigation", listOf(
                "Pilotage & dead reckoning" to "Landmarks against the chart, and heading, speed and time from the wind triangle",
                "Lost — the 5 Cs" to "Climb · Communicate · Confess · Comply · Conserve (fuel)",
                "Diversion" to "Turn toward the new destination first, estimate course, time and fuel, then refine; tell ATC/FSS",
                "VOR" to "Tune, identify (Morse), set the course; TO/FROM tells which side of the station; check within 30 days for IFR (±4° VOT)",
            ), listOf(library)),
        )),
        Area("VII", "Slow flight & stalls", listOf(
            Topic("Standards", listOf(
                "Slow flight" to "Altitude ±100 ft · heading ±10° · airspeed +10/−0 · bank ±10° · no stall warning",
                "Stalls" to "Recognize the cues, recover promptly by reducing the angle of attack; heading ±10°, bank 20° ±5° in turns",
                "Spin awareness" to "PARE: Power idle · Ailerons neutral · Rudder opposite · Elevator forward",
            ), listOf(anim("slow"), anim("stall_off"), anim("stall_on"), book(20), book(23))),
        )),
        Area("VIII", "Basic instrument maneuvers", listOf(
            Topic("Instruments", listOf(
                "Scan" to "Attitude indicator at the centre; radial scan to the others",
                "Unusual attitudes" to "Nose low: power off, level the wings, raise the nose · Nose high: power on, lower the nose, level the wings",
                "Gyros" to "Attitude and heading by vacuum (or electric); turn coordinator electric · pitot-static: airspeed, altimeter, VSI",
                "Compass errors" to "Variation, deviation · ANDS (accelerate north, decelerate south) · UNOS (undershoot north, overshoot south)",
            ), listOf(book(32))),
        )),
        Area("IX", "Emergency operations", listOf(
            Topic("Emergencies", listOf(
                "Engine failure — ABCD" to "Airspeed 59 KIAS best glide · Best field · Checklist (restart) · Declare (121.5, 7700)",
                "Fire in flight (POH)" to "Fuel selector off, full throttle, heat/air off, glide 59 KIAS, ignition off, master off, land",
                "Systems" to "Alternator failure: shed load, land; carburettor ice: carb heat, expect a little roughness",
                "Emergency descent" to "Idle, bank 30–45°, highest safe speed (below VNE/VA in turbulence)",
            ), listOf(anim("emer"), book(19), book(17), book(18))),
        )),
        Area("XI–XII", "Night & postflight", listOf(
            Topic("Night", listOf(
                "Vision" to "Rods for night, off-centre viewing, 30 min to adapt, avoid bright light; oxygen helps above 5,000 ft",
                "Illusions" to "Black hole approach (feels high, flies low) · featureless terrain · autokinesis (a fixed light seems to move)",
                "Airport lighting" to "Runway edge white (yellow in the last 2,000 ft on instrument runways) · taxiway edge blue · threshold green · PAPI: 2 white 2 red on path",
            ), listOf(book(33))),
        )),
    ) }

    private val CARDS = listOf(
        "How long is a third-class medical valid, under 40?" to "60 calendar months (24 if 40 or older)",
        "Passenger currency?" to "3 takeoffs and landings in the last 90 days (full stop for night)",
        "Flight review?" to "Every 24 calendar months: 1 h ground + 1 h flight",
        "Documents on board?" to "ARROW: Airworthiness, Registration, Radio licence (intl), Operating limitations, Weight & balance",
        "Inspections?" to "AV1ATE: Annual, VOR (IFR), 100-hour, Altimeter (IFR), Transponder, ELT",
        "Day VFR fuel reserve?" to "30 minutes (45 at night)",
        "Class C entry?" to "Two-way radio established before entering, Mode C, ADS-B Out",
        "Class B entry?" to "An ATC clearance into the Bravo",
        "Class E below 10,000 MSL minimums?" to "3 SM, 500 below, 1,000 above, 2,000 horizontal",
        "Class G day at or below 1,200 AGL?" to "1 SM, clear of clouds",
        "Special VFR?" to "1 SM, clear of clouds, with ATC clearance (night: instrument rating and airplane)",
        "Cruising altitude, magnetic course 090°, 5,500 or 6,500?" to "5,500 — odd + 500 for 0–179°",
        "Bottle to throttle?" to "8 hours, under 0.04 %",
        "Oxygen for the crew?" to "Above 12,500 after 30 min; always above 14,000",
        "Congested area minimum altitude?" to "1,000 ft above the highest obstacle within 2,000 ft",
        "Head-on, who turns?" to "Both turn right",
        "Steady red, in the air?" to "Give way to other aircraft and continue circling",
        "Flashing green, on the ground?" to "Cleared to taxi",
        "Flashing white?" to "Return to the starting point (ground only)",
        "Squawk lost radio?" to "7600",
        "Steep turn tolerances?" to "45° ±5°, altitude ±100 ft, airspeed ±10 kt, rollout ±10°",
        "Short-field touchdown tolerance?" to "Within 200 ft beyond the point",
        "SportStar best glide?" to "59 KIAS",
        "SportStar Vy and Vx?" to "Vy 65 KIAS, Vx 56 KIAS (54 with flaps 15°)",
        "SportStar demonstrated crosswind?" to "16 kt",
        "Four types of hypoxia?" to "Hypoxic, hypemic, stagnant, histotoxic",
        "Antidote for Macho?" to "\"Taking chances is foolish\"",
        "AIRMET Tango?" to "Turbulence, strong surface winds, low-level wind shear",
        "AIRMET Sierra?" to "IFR and mountain obscuration",
        "NWKRAFT?" to "NOTAMs, Weather, Known delays, Runway lengths, Alternatives, Fuel, Takeoff/landing distances",
        "Lost procedure?" to "5 Cs: Climb, Communicate, Confess, Comply, Conserve",
        "Spin recovery?" to "PARE: Power idle, Ailerons neutral, Rudder opposite, Elevator forward",
        "Compass turning errors?" to "UNOS — undershoot north, overshoot south",
        "Accident written report to the NTSB?" to "Within 10 days",
        "Knowledge test pass mark and validity?" to "70 %; valid 24 calendar months",
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.cr_title))
        col.layoutDirection = View.LAYOUT_DIRECTION_LTR

        val hero = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(0xFF3A1C71.toInt(), 0xFF5E3DB3.toInt(), 0xFF2D8CFF.toInt())).apply { cornerRadius = dp(14).toFloat() }
            setPadding(dp(20), dp(18), dp(20), dp(18))
        }
        hero.addView(EfbUi.text(this, "PRIVATE PILOT · AIRPLANE SINGLE-ENGINE LAND", 11f, 0xCCFFFFFF.toInt(), bold = true).apply { letterSpacing = 0.07f })
        hero.addView(EfbUi.text(this, "Checkride &\nKnowledge Test", 26f, 0xFFFFFFFF.toInt(), bold = true).apply { setPadding(0, dp(6), 0, dp(6)) })
        hero.addView(EfbUi.text(this, "Everything to know cold, by ACS area — with the way to every source in your Library.", 13.5f, 0xE6FFFFFF.toInt()))
        val go = TextView(this).apply {
            text = "🃏  Flash cards (${CARDS.size})"; textSize = 14f; typeface = EfbUi.MEDIUM; setTextColor(0xFF3A1C71.toInt())
            setPadding(dp(14), dp(9), dp(14), dp(9))
            background = GradientDrawable().apply { cornerRadius = dp(20).toFloat(); setColor(0xFFFFFFFF.toInt()) }
        }
        EfbUi.pressable(go) { cards() }
        hero.addView(go, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(14) })
        col.addView(hero, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) })

        // The knowledge test and the day of the practical test.
        section("The knowledge test")
        pairsCard(listOf(
            "Questions" to "60, multiple choice, 2.5 hours",
            "Pass" to "70 % — the report is valid 24 calendar months; missed areas are listed by ACS code for the examiner",
            "Needs" to "Endorsement (61.35), photo ID, the Testing Supplement figures (in the Library)",
        ))
        section("Bring to the checkride")
        pairsCard(listOf(
            "You" to "Government photo ID · student pilot certificate · medical (or BasicMed) · knowledge test report",
            "Logbook" to "Hours meeting 61.109 and the endorsements: 61.103, 61.107(b), 61.109, solo XC, and 61.39 (prep training in the 2 calendar months before the test)",
            "IACRA" to "Form 8710-1 completed and signed by your instructor",
            "Airplane" to "Airworthiness certificate, registration, POH, current W&B · maintenance logbooks showing the inspections and ADs",
            "Planning" to "The assigned cross-country: nav log, weather brief, W&B and performance worked out · current sectional and Chart Supplement · plotter and E6B (or the app)",
        ))

        for (a in areas) {
            section("Area ${a.code} · ${a.title}")
            for (t in a.topics) topicCard(t)
        }
        col.addView(EfbUi.text(this, getString(R.string.cr_note), 11f, EfbUi.DIM).apply { setPadding(dp(4), dp(18), dp(4), 0) })
        EfbUi.stagger(col)
    }

    private fun section(s: String) { col.addView(EfbUi.section(this, s)) }

    private fun pairsCard(rows: List<Pair<String, String>>) {
        val c = EfbUi.card(this).apply { (layoutParams as LinearLayout.LayoutParams).topMargin = 0 }
        rows.forEachIndexed { i, (k, v) ->
            if (i > 0) c.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { topMargin = dp(9); bottomMargin = dp(9) })
            c.addView(EfbUi.text(this, k, 12.5f, EfbUi.ACCENT, bold = true))
            c.addView(EfbUi.text(this, v, 14.5f, EfbUi.TEXT).apply { setLineSpacing(0f, 1.15f); setPadding(0, dp(2), 0, 0) })
        }
        col.addView(c)
    }

    private fun topicCard(t: Topic) {
        val c = EfbUi.card(this)
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(EfbUi.text(this, t.title, 16.5f, EfbUi.TEXT, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
        val arrow = EfbUi.text(this, "▾", 18f, EfbUi.DIM)
        head.addView(arrow)
        c.addView(head)
        val body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE }
        t.facts.forEach { (k, v) ->
            body.addView(EfbUi.text(this, k, 12.5f, EfbUi.ACCENT, bold = true).apply { setPadding(0, dp(12), 0, 0) })
            body.addView(EfbUi.text(this, v, 14.5f, EfbUi.TEXT).apply { setLineSpacing(0f, 1.15f); setPadding(0, dp(2), 0, 0) })
        }
        if (t.links.isNotEmpty()) {
            val links = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(12), 0, 0) }
            for (l in t.links) {
                val tv = TextView(this).apply {
                    text = l.label + "  ›"; textSize = 14f; typeface = EfbUi.MEDIUM; setTextColor(EfbUi.ACCENT)
                    setPadding(dp(12), dp(9), dp(12), dp(9))
                    background = GradientDrawable().apply { cornerRadius = dp(10).toFloat(); setStroke(dp(1), EfbUi.CARD_LINE) }
                }
                EfbUi.pressable(tv) { l.go(this) }
                links.addView(tv, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) })
            }
            body.addView(links)
        }
        c.addView(body)
        val key = "cr_open_" + t.title
        fun show(open: Boolean) { body.visibility = if (open) View.VISIBLE else View.GONE; arrow.text = if (open) "▴" else "▾" }
        show(VaultLock.prefs(this).getBoolean(key, false))
        head.setOnClickListener {
            val open = body.visibility != View.VISIBLE
            VaultLock.prefs(this).edit().putBoolean(key, open).apply()
            show(open)
        }
        col.addView(c)
    }

    /** Flash cards: a question, tap for the answer, then I knew it / again. Missed ones come back. */
    private fun cards() {
        val deck = ArrayDeque(CARDS.shuffled())
        var known = 0
        val d = com.google.android.material.bottomsheet.BottomSheetDialog(this)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(18), dp(20), dp(28)); setBackgroundColor(EfbUi.BG) }
        val count = EfbUi.text(this, "", 12f, EfbUi.DIM, bold = true)
        val q = EfbUi.text(this, "", 21f, EfbUi.TEXT, bold = true).apply { setPadding(0, dp(14), 0, dp(14)) }
        val a = EfbUi.text(this, "", 17f, EfbUi.GOOD).apply { visibility = View.INVISIBLE; setLineSpacing(0f, 1.15f) }
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(20), 0, 0) }
        val reveal = com.google.android.material.button.MaterialButton(this).apply { text = "Show answer" }
        val again = com.google.android.material.button.MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply { text = "Again" }
        val got = com.google.android.material.button.MaterialButton(this).apply { text = "I knew it ✓" }
        fun next() {
            val c = deck.firstOrNull()
            if (c == null) { q.text = "Done — $known of ${CARDS.size} known first time 🎉"; a.visibility = View.GONE; row.visibility = View.GONE; reveal.visibility = View.GONE; return }
            count.text = "${CARDS.size - deck.size + 1} / ${CARDS.size}  ·  ${deck.size} left"
            q.text = c.first; a.text = c.second; a.visibility = View.INVISIBLE
            reveal.visibility = View.VISIBLE; row.visibility = View.GONE
        }
        val missed = HashSet<String>()
        reveal.setOnClickListener { a.visibility = View.VISIBLE; reveal.visibility = View.GONE; row.visibility = View.VISIBLE }
        got.setOnClickListener { deck.removeFirstOrNull()?.let { if (it.first !in missed) known++ }; next() }
        again.setOnClickListener { deck.removeFirstOrNull()?.let { missed += it.first; deck.addLast(it) }; next() }
        row.addView(again, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(8) })
        row.addView(got, LinearLayout.LayoutParams(0, -2, 1f))
        box.addView(count); box.addView(q); box.addView(a); box.addView(reveal, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(20) }); box.addView(row)
        box.layoutDirection = View.LAYOUT_DIRECTION_LTR
        d.setContentView(box)
        next()
        d.show()
    }
}
