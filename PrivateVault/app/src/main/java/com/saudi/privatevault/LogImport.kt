package com.saudi.privatevault

import java.text.SimpleDateFormat
import java.util.Locale

/**
 * Flights from another logbook's CSV export: ForeFlight, MyFlightbook, LogTen, CrewLounge, or any
 * sheet saved as CSV with a header row. Columns are found by their names, whichever app wrote them;
 * a flight already here (same day, route and time) is not added twice.
 */
object LogImport {
    private val COLS = mapOf(
        "date" to listOf("date", "flightdate", "flight_date"),
        "ac" to listOf("model", "aircrafttype", "typecode", "aircraftmodel", "make/model", "type"),
        "tail" to listOf("aircraftid", "tailnumber", "tail", "registration", "ident", "aircraft_id", "aircraftregistration"),
        "from" to listOf("from", "departure", "dep", "origin", "fromairport"),
        "to" to listOf("to", "arrival", "arr", "destination", "toairport"),
        "route" to listOf("route", "via"),
        "total" to listOf("totaltime", "totalflighttime", "total", "duration", "blocktime", "total_time"),
        "pic" to listOf("pic", "picTime", "pilotincommand"),
        "dual" to listOf("dualreceived", "dual", "dual_received", "dualrcvd"),
        "solo" to listOf("solo"),
        "xc" to listOf("crosscountry", "xcountry", "x-country", "xc", "cross_country"),
        "night" to listOf("night", "nighttime"),
        "act" to listOf("actualinstrument", "imc", "actual", "actualinst"),
        "inst" to listOf("simulatedinstrument", "siminstr", "hood", "simulated", "siminst"),
        "gt" to listOf("simulator", "groundtrainer", "ftd", "atd", "simulatortime"),
        "dl" to listOf("daylandingsfullstop", "fsdaylandings", "daylandings", "landingsday", "landings", "alllandings"),
        "nl" to listOf("nightlandingsfullstop", "fsnightlandings", "nightlandings", "landingsnight"),
        "app" to listOf("approaches", "instrumentapproaches", "approach"),
        "hold" to listOf("holds", "holding"),
        "cfi" to listOf("instructorname", "cfiname", "instructor", "cfi"),
        "rem" to listOf("pilotcomments", "comments", "remarks", "notes", "comment"),
        "out" to listOf("timeout", "out", "offblock", "blockout"),
        "in" to listOf("timein", "in", "onblock", "blockin"),
    )

    private fun norm(s: String) = s.lowercase(Locale.US).replace(Regex("[^a-z0-9/_-]"), "").replace("_", "")

    /** One CSV line into its cells, quotes honoured. */
    private fun cells(line: String, sep: Char): List<String> {
        val out = ArrayList<String>(); val b = StringBuilder(); var q = false; var i = 0
        while (i < line.length) {
            val c = line[i]
            when {
                q && c == '"' && i + 1 < line.length && line[i + 1] == '"' -> { b.append('"'); i++ }
                c == '"' -> q = !q
                c == sep && !q -> { out.add(b.toString().trim()); b.clear() }
                else -> b.append(c)
            }
            i++
        }
        out.add(b.toString().trim())
        return out
    }

    private val DATES = listOf("yyyy-MM-dd", "MM/dd/yyyy", "M/d/yyyy", "dd/MM/yyyy", "yyyy/MM/dd", "dd-MMM-yyyy", "MMM d, yyyy", "dd.MM.yyyy", "M/d/yy")

    private fun date(s: String): String? {
        val t = s.trim().substringBefore('T').substringBefore(' ').ifEmpty { return null }
        for (f in DATES) try {
            val p = SimpleDateFormat(f, Locale.US).apply { isLenient = false }
            val d = p.parse(t) ?: continue
            return LogEntry.FMT.format(d)
        } catch (e: Exception) {}
        return null
    }

    /** Hours from "1.6", "1,6" or "1:36". */
    private fun hours(s: String): Double {
        val t = s.trim()
        if (t.contains(':')) { val p = t.split(':'); return ((p[0].toIntOrNull() ?: 0) + (p.getOrNull(1)?.toIntOrNull() ?: 0) / 60.0).let { Math.round(it * 10) / 10.0 } }
        return t.replace(',', '.').toDoubleOrNull() ?: 0.0
    }

    /** The flights read, and how many were already in the logbook. */
    fun parse(text: String, have: List<LogEntry>): Pair<List<LogEntry>, Int> {
        val lines = text.replace("\r", "").split('\n')
        // The header: the first line naming a date and a total time (ForeFlight puts an aircraft table first).
        var hi = -1; var sep = ','
        for ((i, l) in lines.withIndex()) {
            val s = if (l.count { it == ';' } > l.count { it == ',' }) ';' else if (l.contains('\t')) '\t' else ','
            val names = cells(l, s).map { norm(it) }
            if (names.any { it in COLS["date"]!! } && names.any { n -> COLS["total"]!!.any { norm(it) == n } }) { hi = i; sep = s; break }
        }
        if (hi < 0) return emptyList<LogEntry>() to 0
        val head = cells(lines[hi], sep).map { norm(it) }
        val at = HashMap<String, Int>()
        for ((k, names) in COLS) {
            val idx = names.map { norm(it) }.firstNotNullOfOrNull { n -> head.indexOf(n).takeIf { it >= 0 } }
            if (idx != null) at[k] = idx
        }
        val seen = have.map { "${it.date}|${it.from}|${it.to}|${EfbUi.num(it.total)}" }.toHashSet()
        val out = ArrayList<LogEntry>(); var dup = 0
        for (l in lines.drop(hi + 1)) {
            if (l.isBlank()) continue
            val c = cells(l, sep)
            fun v(k: String) = at[k]?.let { c.getOrNull(it) }.orEmpty()
            val d = date(v("date")) ?: continue
            val total = hours(v("total"))
            if (total <= 0.0 && hours(v("gt")) <= 0.0) continue
            val e = LogEntry(date = d, aircraft = v("ac"), tail = v("tail").uppercase(), from = v("from").uppercase(), to = v("to").uppercase(),
                route = v("route").uppercase(), total = total, pic = hours(v("pic")), dual = hours(v("dual")), solo = hours(v("solo")),
                xc = hours(v("xc")), night = hours(v("night")), actual = hours(v("act")), instrument = hours(v("inst")), groundTrainer = hours(v("gt")),
                dayLdg = v("dl").toDoubleOrNull()?.toInt() ?: 0, nightLdg = v("nl").toDoubleOrNull()?.toInt() ?: 0,
                approaches = v("app").toDoubleOrNull()?.toInt() ?: 0, holds = v("hold").toDoubleOrNull()?.toInt() ?: 0,
                instructor = v("cfi"), remarks = v("rem"), timeOut = v("out"), timeIn = v("in"))
            if (!seen.add("${e.date}|${e.from}|${e.to}|${EfbUi.num(e.total)}")) { dup++; continue }
            out.add(e)
        }
        return out to dup
    }
}
