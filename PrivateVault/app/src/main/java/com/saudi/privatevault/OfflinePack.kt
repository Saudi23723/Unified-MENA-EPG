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
        // VFR charts and the Chart Supplement: every other AIRAC date, 56 days apart from 20 Feb 2025 (29 Oct 2026 is one).
        var start = LocalDate.of(2025, 2, 20)
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
        // The FAA has published the edition's XML index in more than one place over the years.
        for (url in listOf(
            "https://aeronav.faa.gov/afd/$ed/afd_$ed.xml",
            "https://aeronav.faa.gov/Upload_313-d/supplements/afd_$ed.xml",
            "https://aeronav.faa.gov/upload_313-d/supplements/afd_$ed.xml",
        )) {
            val out = parseIndex(url)
            if (out.length() > 0) {
                val index = JSONObject().put("ed", ed).put("a", out)
                file.parentFile?.mkdirs()
                file.writeText(index.toString())
                return index
            }
        }
        return cached
    }

    private fun parseIndex(url: String): JSONObject {
        val out = JSONObject()
        try {
            val c = get(url)
            try {
                if (c.responseCode != 200) return out
                val x = android.util.Xml.newPullParser()
                x.setInput(c.inputStream.buffered(), null)
                var tag = ""
                var ids = ArrayList<String>()
                var pages = JSONArray()
                while (true) {
                    when (x.next()) {
                        org.xmlpull.v1.XmlPullParser.END_DOCUMENT -> break
                        org.xmlpull.v1.XmlPullParser.START_TAG -> {
                            tag = x.name.lowercase(Locale.US)
                            if (tag == "airport") { ids = ArrayList(); pages = JSONArray() }
                        }
                        org.xmlpull.v1.XmlPullParser.TEXT -> {
                            val t = x.text.trim()
                            if (t.isNotEmpty()) when {
                                tag == "pdf" || t.endsWith(".pdf", true) -> pages.put(t)
                                tag.contains("id") -> ids.add(t.uppercase(Locale.US))
                            }
                        }
                        org.xmlpull.v1.XmlPullParser.END_TAG -> {
                            if (x.name.equals("airport", true) && pages.length() > 0) for (id in ids) out.put(id, pages)
                            tag = ""
                        }
                    }
                }
            } finally {
                c.disconnect()
            }
        } catch (e: Exception) {
        }
        return out
    }

    /** Chart Supplement page links found on a web page about the airport. */
    private fun scrape(url: String): List<String> = try {
        val c = get(url, 20000)
        try {
            if (c.responseCode != 200) emptyList() else {
                val html = c.inputStream.bufferedReader().readText()
                Regex("https?://aeronav\\.faa\\.gov/[^\"'\\s>]+?\\.pdf", RegexOption.IGNORE_CASE).findAll(html).map { it.value }
                    .filter { it.contains("/afd/", true) || it.contains("supplement", true) || Regex("_\\d+_\\d{2}[A-Z]{3}\\d{4}", RegexOption.IGNORE_CASE).containsMatchIn(it) }
                    .distinct().toList()
            }
        } finally {
            c.disconnect()
        }
    } catch (e: Exception) {
        emptyList()
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

    /** Which pages each airport's supplement is on, as saved on this phone: it answers without signal. */
    private fun saved(ctx: Context): JSONObject = try { JSONObject(File(ctx.filesDir, "supplement/saved.json").readText()) } catch (e: Exception) { JSONObject() }

    private fun remember(ctx: Context, ident: String, files: List<File>) {
        val o = saved(ctx)
        o.put(ident, JSONArray().apply { for (f in files) put(f.absolutePath) })
        File(ctx.filesDir, "supplement").mkdirs()
        File(ctx.filesDir, "supplement/saved.json").writeText(o.toString())
    }

    /** The Chart Supplement pages of an airport: from the phone when saved, else from the FAA (then saved). */
    fun supplement(ctx: Context, ident: String, icao: String = ""): List<File> {
        val ed = csEdition()
        val keys = listOf(ident.uppercase(Locale.US), icao.uppercase(Locale.US)).filter { it.isNotEmpty() }
        val mine = saved(ctx)
        val have = keys.firstNotNullOfOrNull { k -> mine.optJSONArray(k) }?.let { a -> (0 until a.length()).map { File(a.getString(it)) } }?.filter { it.length() > 0 }
        if (have != null && have.isNotEmpty() && have.all { it.parentFile?.name == ed }) return have
        var urls: List<String> = csIndex(ctx)?.optJSONObject("a")?.let { a ->
            keys.firstNotNullOfOrNull { k -> a.optJSONArray(k) }?.let { p -> (0 until p.length()).map { "https://aeronav.faa.gov/afd/$ed/" + p.getString(it) } }
        } ?: emptyList()
        if (urls.isEmpty()) urls = scrape("https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/dafd/search/results/?ident=${keys.first()}")
        if (urls.isEmpty()) urls = scrape("https://www.airnav.com/airport/${keys.last()}")
        val files = urls.mapNotNull { u -> download(u, File(ctx.filesDir, "supplement/$ed/" + u.substringAfterLast('/'))) }
        if (files.isNotEmpty()) {
            remember(ctx, keys.first(), files)
            return files
        }
        // No signal and no new edition: the last saved edition is better than nothing.
        return have ?: emptyList()
    }

    /** Fetches all of one airport; reports what it managed. */
    /** What a flight pack fetches for each airport. */
    class Parts(val info: Boolean = true, val diagram: Boolean = true, val supplement: Boolean = true, val plates: Boolean = true)

    fun airport(ctx: Context, a: AviationData.Airport, parts: Parts = Parts(), step: (String) -> Unit): Int {
        var n = 0
        val id = a.icao.ifEmpty { a.ident }
        if (parts.info) {
            step("$id · info")
            AviationData.airportInfo(ctx, id)?.let { n++ }
        }
        if (parts.diagram) {
            step("$id · diagram")
            AirportDiagramActivity.fetch(ctx, a.ident, a.lat, a.lon, refresh = false)?.let { n++ }
        }
        if (parts.supplement) {
            step("$id · Chart Supplement")
            val pages = supplement(ctx, a.ident, a.icao)
            n += pages.size
            // Kept in the vault's Chart Supplement folder too, where the pilot sees it.
            SupplementShelf.keep(ctx, a.ident, pages)
        }
        if (parts.plates) {
            val plates = AviationData.plates(ctx, a.ident)
            if (plates != null) {
                for ((i, p) in plates.second.withIndex()) {
                    step("$id · plates ${i + 1}/${plates.second.size}")
                    if (AviationData.platePdf(ctx, plates.first, p.pdf) != null) n++
                }
            }
        }
        return n
    }
}
