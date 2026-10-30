package com.saudi.privatevault

import java.util.Calendar

/**
 * The flight school's checkride checklists (pre-solo, private, instrument,
 * commercial): the endorsements each needs with their AC 61-65 numbers and
 * regulations, the paperwork for the test day, and the aeronautical
 * experience, measured from the logbook wherever the logbook can tell.
 */
object Checkride {

    /** An endorsement the checkride needs; [need] is Required, Optional or May be needed. */
    class End(val title: String, val ac: String, val far: String, val need: String, val validDays: Int = 0)

    /** A line of aeronautical experience: what it says, and how far the logbook has it (value, target); null when it can only be ticked. */
    class Exp(val title: String, val depth: Int = 0, val measure: ((List<LogEntry>) -> Pair<Double, Double>)? = null)

    class Ride(val key: String, val title: String, val ends: List<End>, val paperwork: List<String>, val experience: List<Exp>)

    private val TEST_DAY = listOf(
        "Required Endorsements in log book",
        "Written Test Endorsement",
        "Written Test Completed - scoresheet printed and available",
        "Written Test Deficiencies Logged and Endorsed",
        "IACRA signed",
        "Medical Verified Current",
        "Photo ID Current and Appropriate",
        "Airplane documents verified",
        "Airplane qualified (FAASTeam checklist)",
        "Cross Country Plan Completed",
        "Weight and Balance Completed",
        "Weather briefing attained",
        "View Limiting Device Available",
    )

    private fun inLastCalendarMonths(e: LogEntry, months: Int): Boolean {
        val c = Calendar.getInstance()
        c.add(Calendar.MONTH, -months)
        c.set(Calendar.DAY_OF_MONTH, 1)
        return e.dateMillis() >= c.timeInMillis
    }

    private fun hours(target: Double, f: (LogEntry) -> Double) = { l: List<LogEntry> -> l.sumOf(f) to target }
    private fun count(target: Double, f: (LogEntry) -> Int) = { l: List<LogEntry> -> l.sumOf(f).toDouble() to target }
    private fun any(f: (LogEntry) -> Boolean) = { l: List<LogEntry> -> (if (l.any(f)) 1.0 else 0.0) to 1.0 }

    val PRE_SOLO = listOf(
        "Pre-Solo Knowledge Test", "Corrected to 100%",
        "Proper flight preparation procedures", "Taxiing or surface operations", "Normal Takeoffs and landings",
        "Cross Wind Takeoffs and Landings", "Straight and level flight", "Turns in both directions", "Climbs and climbing turns",
        "Airport traffic patterns", "Traffic Pattern Entry", "Traffic Pattern Departure", "Collision avoidance", "Windshear avoidance",
        "Wake turbulence avoidance", "Straight Descents high and low drag", "Turning Descents high and low drag", "Cruise Flight",
        "Slow Flight", "Power-On Stall", "Power-Off Stall", "Emergency procedures", "Equipment malfunctions",
        "Ground reference maneuvers", "Approaches to a landing area with simulated engine malfunctions", "Slips to a landing", "Go-arounds",
    )

    val STUDENT = listOf(
        End("TSA-Endorsement Photocopy", "A.14", "", "3 Options"),
        End("Pre-solo Aeronautical Knowledge", "A.3", "61.87(b)", "Required"),
        End("Pre-solo Flight Training", "A.4", "61.87(c)(1)(2)", "Required"),
        End("Solo Flight (First 90 Days)", "A.6", "61.87(n)", "Required", 90),
        End("Pre-solo Flight Training at Night", "A.5", "61.87(o)", "Optional"),
        End("Solo Flight (Each additional 90 days)", "A.7", "61.87(p)", "May be needed", 90),
        End("Solo Cross Country Flight Training", "A.9", "61.93(c)(1)(2)", "Required"),
        End("Solo Cross Country Flight Review", "A.10", "61.93(c)(3)", "Required"),
        End("Solo Takeoffs and Landings (25 NM)", "A.8", "61.93(b)(1)", "Optional"),
        End("Repeated Solo Cross Country (Less than 50 NM)", "A.11", "61.93(b)(2)", "Optional"),
        End("Solo Flight in Class B Airspace", "A.12", "61.95(a)", "Optional"),
        End("Solo Flight to/from Class B Airport", "", "91.131(b)(1)", "Optional"),
    )

    val RIDES = listOf(
        Ride("private", "Private Pilot", STUDENT + listOf(
            End("Aeronautical Knowledge Test", "A.32", "61.35(a)(1), 61.103(d), 61.105", "Required (A.32 or A.82)"),
            End("Review of a Home Study Curriculum", "A.82", "61.35(a)(1)", "Required (A.32 or A.82)"),
            End("Review of Deficiencies On Knowledge Test", "A.2", "61.39(a)(6)(iii)", "Required"),
            End("Prerequisites for Practical Test", "A.1", "61.39(a)(6)(i)(ii)", "Required"),
            End("Flight Proficiency/ Practical Test", "A.33", "61.103(f), 61.107(b), 61.109", "Required"),
            End("Retesting After Failure", "A.73", "61.49", "May be needed"),
        ), TEST_DAY.take(4) + listOf(
            "Ground Instruction Logged (61.105 Aeronautical Knowledge & 61.107 Flight Proficiency)",
        ) + TEST_DAY.drop(4), listOf(
            Exp("20 hours Flight Instruction Logged (61.107 & 61.109)", 0, hours(20.0) { it.dual }),
            Exp("3 Hours XC Flight Training 61.109(a)(1)", 1, hours(3.0) { minOf(it.dual, it.xc) }),
            Exp("3 Hours night training 61.109(a)(2)", 1, hours(3.0) { minOf(it.dual, it.night) }),
            Exp("100 nm XC 61.109(a)(2)(i)", 2, any { it.night > 0 && it.dual > 0 && it.distanceNm > 100 }),
            Exp("10 T/O & Landings 61.109(a)(2)(ii)", 2, count(10.0) { it.nightLdg }),
            Exp("3 Hours Instrument Training 61.109(a)(3)", 1, hours(3.0) { minOf(it.dual, it.instrument + it.actual) }),
            Exp("3 Hours in the preceding 2 calendar months 61.109(a)(4)", 1, { l -> l.filter { inLastCalendarMonths(it, 2) }.sumOf { it.dual } to 3.0 }),
            Exp("10 Hours solo flight 61.109(a)(5)", 1, hours(10.0) { it.solo }),
            Exp("5 hours XC solo 61.109(a)(5)(i)", 2, hours(5.0) { minOf(it.solo, it.xc) }),
            Exp("150 nm XC solo 61.109(a)(5)(ii)", 2, any { it.solo > 0 && it.distanceNm >= 150 && it.farthestNm > 50 }),
            Exp("3 T/O and Landing to full stop at towered airport 61.109(a)(5)(iii)", 2, { l -> l.filter { it.solo > 0 }.sumOf { it.toweredLdg }.toDouble() to 3.0 }),
            Exp("40 hours total 61.109(a)", 0, hours(40.0) { it.total }),
        )),
        Ride("instrument", "Instrument Rating", listOf(
            End("Aeronautical Knowledge Test", "A.38 or A.82", "61.35(a)(1), 61.65(a)(b)", "Required (A.38 or A.82)"),
            End("Review of a Home Study Curriculum", "A.82", "61.35(a)(1)", "Required (A.38 or A.82)"),
            End("Review of Deficiencies On Knowledge Test", "A.39", "61.39(a)(6)(iii)", "Required"),
            End("Prerequisites for Practical Test", "A.39", "61.39(a)(6)(i)(ii)", "Required"),
            End("Flight Proficiency/ Practical Test", "A.40", "61.123(e), 61.127(b), 61.129", "Required"),
            End("Retesting After Failure", "A.73", "61.49", "May be needed"),
            End("Completion of an Instrument Proficiency Check (IPC)", "A.67", "61.57(d)", "Required after lapse of currency"),
        ), TEST_DAY.take(4) + listOf(
            "Ground Instruction Logged (61.65(b))", "Flight Proficiency logged (61.65(c))", "Aeronautical Experience logged (61.65(d))",
        ) + TEST_DAY.drop(4), listOf(
            Exp("50 hours XC (PIC) 61.65(d)(1)", 0, hours(50.0) { minOf(it.xc, it.pic) }),
            Exp("40 Hours Instrument 61.65(d)(2)", 0, hours(40.0) { it.actual + it.instrument + minOf(it.groundTrainer, 10.0) }),
            Exp("Up to 10 can be approved ATD", 1, hours(10.0) { it.groundTrainer }),
            Exp("At least 15 with CFII", 1, hours(15.0) { minOf(it.dual, it.actual + it.instrument) }),
            Exp("Three hours within 2 calendar months of practical test 61.65(d)(2)(i)", 1,
                { l -> l.filter { inLastCalendarMonths(it, 2) }.sumOf { minOf(it.dual, it.actual + it.instrument) } to 3.0 }),
            Exp("Long XC Flight 61.65(d)(2)(ii): 250 nm, airways or ATC routing, approach at each airport, 3 kinds of approaches, IFR filed", 0,
                any { it.distanceNm >= 250 && it.approaches >= 3 && (it.actual + it.instrument) > 0 }),
        )),
        Ride("commercial", "Commercial Pilot", listOf(
            End("Aeronautical Knowledge Test", "A.34 or A.82", "61.35(a)(1), 61.123(c), 61.125", "Required (A.34 or A.82)"),
            End("Review of a Home Study Curriculum", "A.82", "61.35(a)(1)", "Required (A.34 or A.82)"),
            End("Review of Deficiencies On Knowledge Test", "A.2", "61.39(a)(6)(iii)", "Required"),
            End("Prerequisites for Practical Test", "A.1", "61.39(a)(6)(i)(ii)", "Required"),
            End("Flight Proficiency/ Practical Test", "A.35", "61.123(e), 61.127(b), 61.129", "Required"),
            End("Retesting After Failure", "A.73", "61.49", "May be needed"),
        ), TEST_DAY.take(4) + listOf(
            "Ground Instruction Logged 14 CFR 61.125 Aeronautical Knowledge", "Flight Proficiency Logged 14 CFR 61.127 Flight Proficiency",
            "Aeronautical Experience 14 CFR 61.129 Logged and annotated in logbook",
        ) + TEST_DAY.drop(4), listOf(
            Exp("100 Hours in powered aircraft, 50 in airplanes 61.129(a)(1)", 0, hours(100.0) { it.total }),
            Exp("100 hours PIC 61.129(a)(2)", 0, hours(100.0) { it.pic }),
            Exp("50 in airplanes 61.129(a)(2)(i)", 1, hours(50.0) { it.pic }),
            Exp("50 cross country, at least 10 in airplanes 61.129(a)(2)(ii)", 1, hours(50.0) { minOf(it.pic, it.xc) }),
            Exp("20 hours of training [61.127(b)(1)] 61.129(a)(3)", 0, hours(20.0) { it.dual }),
            Exp("10 hours inst. Training 61.129(a)(3)(i)", 1, hours(10.0) { minOf(it.dual, it.actual + it.instrument) }),
            Exp("10 hours complex, turbine powered, or TAA 61.129(a)(3)(ii)", 1),
            Exp("2 hour, daytime 100 nm XC 61.129(a)(3)(iii)", 1, any { it.dual >= 2 && it.night == 0.0 && it.farthestNm > 100 }),
            Exp("2 hour, nighttime 100 nm XC 61.129(a)(3)(iv)", 1, any { it.dual >= 2 && it.night >= 2 && it.farthestNm > 100 }),
            Exp("Three hours instruction within preceding 2 calendar months 61.129(a)(3)(v)", 1, { l -> l.filter { inLastCalendarMonths(it, 2) }.sumOf { it.dual } to 3.0 }),
            Exp("10 hours solo flight time -OR- PIC duties time 61.129(a)(4)", 0, hours(10.0) { it.solo }),
            Exp("300 nm XC (straight line 250 nm) 61.129(a)(4)(i)", 1, any { it.distanceNm >= 300 && it.farthestNm >= 250 }),
            Exp("5 hours night VFR with 10 takeoffs and 10 landings in traffic pattern at tower controlled airport 61.129(a)(4)(ii)", 1,
                { l -> minOf(l.sumOf { minOf(it.night, maxOf(it.solo, it.pic)) } / 5.0, l.filter { it.night > 0 }.sumOf { it.toweredLdg } / 10.0) to 1.0 }),
        )),
    )

    /** Endorsement templates for the logbook, from all the rides, without repeats. */
    val TEMPLATES: List<End> = (STUDENT + RIDES.flatMap { it.ends }).distinctBy { it.title + it.ac }
}
