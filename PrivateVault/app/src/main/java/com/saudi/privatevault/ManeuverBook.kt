package com.saudi.privatevault


/** The maneuvers of the pilot's Jeppesen Private Pilot Maneuvers, and which of the app's animations each one has. */
object ManeuverBook {
    /** The book's maneuvers by number and title, with their pages in the file (1-based, inclusive). */
    class Entry(val no: Int, val title: String, val chapter: String, val pages: IntRange)

    val ENTRIES = listOf(
        Entry(1, "Preflight Inspection", "Ground Operations", 9..14),
        Entry(2, "Engine Starting", "Ground Operations", 15..18),
        Entry(3, "Taxiing", "Ground Operations", 19..22),
        Entry(4, "Before Takeoff Check", "Ground Operations", 23..27),
        Entry(5, "Postflight Procedures", "Ground Operations", 28..31),
        Entry(6, "Straight-and-Level Flight", "Basic Maneuvers", 36..37),
        Entry(7, "Climbs", "Basic Maneuvers", 38..39),
        Entry(8, "Descents", "Basic Maneuvers", 40..41),
        Entry(9, "Turns", "Basic Maneuvers", 42..46),
        Entry(10, "Normal Takeoff and Climb", "Airport Operations", 50..53),
        Entry(11, "Crosswind Takeoff and Climb", "Airport Operations", 54..55),
        Entry(12, "Traffic Patterns", "Airport Operations", 56..61),
        Entry(13, "Normal Approach and Landing", "Airport Operations", 62..67),
        Entry(14, "Forward Slip to a Landing", "Airport Operations", 68..69),
        Entry(15, "Go-Around", "Airport Operations", 70..71),
        Entry(16, "Crosswind Approach and Landing", "Airport Operations", 72..73),
        Entry(17, "Systems and Equipment Malfunctions", "Emergency Operations", 78..81),
        Entry(18, "Emergency Descent", "Emergency Operations", 82..83),
        Entry(19, "Emergency Approach and Landing", "Emergency Operations", 84..89),
        Entry(20, "Slow Flight", "Flight Maneuvers", 93..94),
        Entry(21, "Power-Off Stalls", "Flight Maneuvers", 95..98),
        Entry(22, "Power-On Stalls", "Flight Maneuvers", 99..102),
        Entry(23, "Demonstrated Stalls and Spin Awareness", "Flight Maneuvers", 103..108),
        Entry(24, "Steep Turns", "Flight Maneuvers", 109..110),
        Entry(25, "Rectangular Course", "Ground Reference Maneuvers", 114..115),
        Entry(26, "S-Turns", "Ground Reference Maneuvers", 116..117),
        Entry(27, "Turns Around a Point", "Ground Reference Maneuvers", 118..119),
        Entry(28, "Short-Field Takeoff and Maximum Performance Climb", "Performance Takeoffs and Landings", 123..124),
        Entry(29, "Short-Field Approach and Landing", "Performance Takeoffs and Landings", 125..127),
        Entry(30, "Soft-Field Takeoff and Climb", "Performance Takeoffs and Landings", 128..129),
        Entry(31, "Soft-Field Approach and Landing", "Performance Takeoffs and Landings", 130..131),
        Entry(32, "Basic Instrument Maneuvers", "Special Flight Operations", 135..145),
        Entry(33, "Night Operations", "Special Flight Operations", 146..152),
    )

    /** The book's maneuver for each of the app's animated ones. */
    val FOR = mapOf(
        "pattern" to 12, "normal_to" to 10, "xwind_to" to 11, "short_to" to 28, "soft_to" to 30,
        "normal_ldg" to 13, "xwind_ldg" to 16, "short_ldg" to 29, "soft_ldg" to 31, "slip" to 14,
        "go_around" to 15, "steep" to 24, "rect" to 25, "sturns" to 26, "tap" to 27, "slow" to 20,
        "stall_off" to 21, "stall_on" to 22, "emer" to 19,
    )

    fun entry(no: Int?) = ENTRIES.firstOrNull { it.no == no }
}
