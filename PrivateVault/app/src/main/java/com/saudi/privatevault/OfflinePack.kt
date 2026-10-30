package com.saudi.privatevault

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.util.Locale

/**
 * Everything a flight needs once the phone has no signal: each airport's
 * plates, Chart Supplement pages, runways and frequencies, and its 3D
 * diagram, fetched together before departure.
 */
object OfflinePack {

    /** The 56-day Chart Supplement edition in force, as the FAA writes it (e.g. 30OCT2025). */
    fun csEdition(day: LocalDate = LocalDate.now()): String {
        var start = LocalDate.of(2025, 1, 23)
        while (!start.plusDays(56).isAfter(day)) start = start.plusDays(56)
        while (start.isAfter(day)) start = start.minusDays(56)
        return "%02d%s%d".format(start.dayOfMonth, start.month.name.take(3), start.year).uppercase(Locale.US)
    }

    private fun get(url: String, timeout: Int = 30000): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = timeout
        c.readTimeout = 90000
        c.setRequestProperty("User-Agent", "SSEFB/1.0")
        return c
    }

    /** The Chart Supplement's index of the edition: airport → its PDF pages; kept on the phone. */
    private fun csIndex(ctx: Context): JSONObject? {
        val ed = csEdition()
        val file = File(ctx.filesDir, "aviation/cs.json")
        val cached = try { JSONObject(file.readText()) } catch (e: Exception) { null }
        if (cached?.optString("ed") == ed) return cached
        val out = JSONObject()
        try {
            val c = get("https://aeronav.faa.gov/afd/$ed/afd_$ed.xml")
            try {
                if (c.responseCode == 200) {
                    val x = android.util.Xml.newPullParser()
                    x.setInput(c.inputStream.buffered(), null)
                    var tag = ""
                    var apt = ""
                    var pages = JSONArray()
                    while (true) {
                        when (x.next()) {
                            org.xmlpull.v1.XmlPullParser.END_DOCUMENT -> break
                            org.xmlpull.v1.XmlPullParser.START_TAG -> {
                                tag = x.name
                                if (x.name == "airport") { apt = ""; pages = JSONArray() }
                            }
                            org.xmlpull.v1.XmlPullParser.TEXT -> {
                                val t = x.text.trim()
                                if (t.isNotEmpty()) when (tag) {
                                    "aptid" -> apt = t
                                    "pdf" -> pages.put(t)
                                }
                            }
                            org.xmlpull.v1.XmlPullParser.END_TAG -> {
                                if (x.name == "airport" && apt.isNotEmpty() && pages.length() > 0) out.put(apt, pages)
                                tag = ""
                            }
                        }
                    }
                }
            } finally {
                c.disconnect()
            }
        } catch (e: Exception) {
        }
        if (out.length() == 0) return cached
        val index = JSONObject().put("ed", ed).put("a", out)
        file.parentFile?.mkdirs()
        file.writeText(index.toString())
        return index
    }

    private fun download(url: String, f: File): File? {
        if (f.length() > 0) return f
        return try {
            val c = get(url)
            try {
                if (c.responseCode != 200) return null
                f.parentFile?.mkdirs()
                val tmp = File(f.path + ".part")
                c.inputStream.use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
                tmp.renameTo(f)
                f
            } finally {
                c.disconnect()
            }
        } catch (e: Exception) {
            null
        }
    }

    /** The Chart Supplement pages of an airport as one PDF list, downloaded once per edition. */
    fun supplement(ctx: Context, ident: String): List<File> {
        val index = csIndex(ctx) ?: return emptyList()
        val ed = index.optString("ed")
        val pages = index.optJSONObject("a")?.optJSONArray(ident) ?: return emptyList()
        return (0 until pages.length()).mapNotNull { i ->
            val name = pages.getString(i)
            download("https://aeronav.faa.gov/afd/$ed/$name", File(ctx.filesDir, "supplement/$ed/$name"))
        }
    }

    /** Fetches all of one airport; reports what it managed. */
    fun airport(ctx: Context, a: AviationData.Airport, step: (String) -> Unit): Int {
        var n = 0
        val id = a.icao.ifEmpty { a.ident }
        step("$id · info")
        AviationData.airportInfo(ctx, id)?.let { n++ }
        step("$id · 3D")
        AirportDiagramActivity.fetch(ctx, a.ident, a.lat, a.lon, refresh = false)?.let { n++ }
        step("$id · Chart Supplement")
        n += supplement(ctx, a.ident).size
        val plates = AviationData.plates(ctx, a.ident)
        if (plates != null) {
            for ((i, p) in plates.second.withIndex()) {
                step("$id · plates ${i + 1}/${plates.second.size}")
                if (AviationData.platePdf(ctx, plates.first, p.pdf) != null) n++
            }
        }
        return n
    }
}
