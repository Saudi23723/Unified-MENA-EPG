package com.saudi.privatevault

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * The FAA's own charts (GeoTIFF from aeronav.faa.gov, made into WebP tiles
 * each edition by the vfr-charts workflow) kept on the phone: drawn over the
 * chart service where they cover, with their edition shown. Fetched from the
 * linked cloud vault when it holds them, else from GitHub.
 */
object OfficialCharts {
    private const val GITHUB = "https://github.com/Saudi23723/Unified-MENA-EPG/releases/download/vfr-charts/"

    fun dir(ctx: Context) = File(ctx.filesDir, "charts").apply { mkdirs() }

    fun manifest(ctx: Context): JSONObject? = try { JSONObject(File(dir(ctx), "manifest.json").readText()) } catch (e: Exception) { null }

    /** The edition held, or null. */
    fun edition(ctx: Context): String? = manifest(ctx)?.optString("edition")?.takeIf { it.isNotEmpty() }

    fun current(ctx: Context) = edition(ctx) == ChartUpdates.cycleStart(56).toString()

    /** The official file for a chart layer ("sectional" or "tac"), when held. */
    fun fileFor(ctx: Context, layer: String): File? {
        val prefix = when (layer) { "sectional" -> "sec_"; "tac" -> "tac_"; else -> return null }
        val charts = manifest(ctx)?.optJSONArray("charts") ?: return null
        for (i in 0 until charts.length()) {
            val f = File(dir(ctx), charts.getJSONObject(i).optString("file"))
            if (f.name.startsWith(prefix) && f.length() > 0) return f
        }
        return null
    }

    private fun open(ctx: Context, name: String): HttpURLConnection? {
        // The linked cloud first (the phone may not reach GitHub), then GitHub.
        LaptopClient.vaultConnection(ctx, "charts/$name")?.let { c ->
            try { if (c.responseCode == 200) return c } catch (e: Exception) {}
            c.disconnect()
        }
        val c = URL(GITHUB + name).openConnection() as HttpURLConnection
        c.connectTimeout = 15000
        c.readTimeout = 120000
        c.instanceFollowRedirects = true
        return try { if (c.responseCode == 200) c else { c.disconnect(); null } } catch (e: Exception) { null }
    }

    /**
     * Brings the edition in force onto the phone; [progress] gets (chart title, percent).
     * Returns the edition held after, or null when nothing could be fetched. Off the main thread.
     */
    private val busy = java.util.concurrent.atomic.AtomicBoolean(false)

    fun update(ctx: Context, progress: (String, Int) -> Unit = { _, _ -> }): String? {
        if (!busy.compareAndSet(false, true)) return edition(ctx)
        try { return fetch(ctx, progress) } finally { busy.set(false) }
    }

    private fun fetch(ctx: Context, progress: (String, Int) -> Unit): String? {
        val m = open(ctx, "manifest.json")?.let { c -> try { JSONObject(c.inputStream.bufferedReader().readText()) } finally { c.disconnect() } }
            ?: return edition(ctx)
        val charts = m.optJSONArray("charts") ?: return edition(ctx)
        val same = m.optString("edition") == edition(ctx)
        for (i in 0 until charts.length()) {
            val ch = charts.getJSONObject(i)
            val file = File(dir(ctx), ch.optString("file"))
            if (same && file.length() == ch.optLong("size")) continue
            val c = open(ctx, file.name) ?: return edition(ctx)
            val part = File(file.path + ".part")
            try {
                val total = c.contentLengthLong.takeIf { it > 0 } ?: ch.optLong("size")
                c.inputStream.use { inp ->
                    part.outputStream().use { out ->
                        val buf = ByteArray(256 * 1024)
                        var done = 0L
                        var last = -1
                        while (true) {
                            val n = inp.read(buf)
                            if (n < 0) break
                            out.write(buf, 0, n)
                            done += n
                            val pct = if (total > 0) (done * 100 / total).toInt() else 0
                            if (pct != last) { last = pct; progress(ch.optString("title"), pct) }
                        }
                    }
                }
            } finally {
                c.disconnect()
            }
            if (ch.optLong("size") > 0 && part.length() != ch.optLong("size")) { part.delete(); return edition(ctx) }
            file.delete()
            part.renameTo(file)
        }
        File(dir(ctx), "manifest.json").writeText(m.toString())
        // Files of an older edition with other names go.
        val keep = (0 until charts.length()).map { charts.getJSONObject(it).optString("file") }.toSet() + "manifest.json"
        dir(ctx).listFiles()?.forEach { if (it.name !in keep) it.delete() }
        return m.optString("edition")
    }

    fun describe(ctx: Context): String {
        val m = manifest(ctx) ?: return "—"
        val charts = m.optJSONArray("charts")
        val names = (0 until (charts?.length() ?: 0)).joinToString(", ") { charts!!.getJSONObject(it).optString("title") }
        val mb = dir(ctx).listFiles()?.filter { it.name.endsWith(".mbtiles") }?.sumOf { it.length() }?.div(1024 * 1024) ?: 0
        return "$names · edition ${m.optString("edition")} → ${m.optString("expires")} · $mb MB"
    }
}
