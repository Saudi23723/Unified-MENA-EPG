package com.saudi.privatevault

import android.content.Context
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.multipdf.PDFMergerUtility
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * The Chart Supplement as one book. The FAA publishes it only as hundreds of separate page files,
 * one or two pages each, by region — so this fetches a region's pages, in order, and binds them into
 * a single PDF in the vault, read like any other book: searched, marked, and kept offline.
 */
object ChartSupplementBook {

    /** The nine volumes the FAA divides the country into. */
    val REGIONS = listOf(
        "SW" to "Southwest  ·  NV AZ CA UT",
        "NW" to "Northwest  ·  WA OR ID MT WY",
        "SC" to "South Central  ·  TX OK NM CO KS",
        "NC" to "North Central  ·  ND SD NE MN IA MO",
        "EC" to "East Central  ·  IL IN OH MI KY WV",
        "SE" to "Southeast  ·  FL GA AL MS TN NC SC",
        "NE" to "Northeast  ·  NY PA NJ NEW ENGLAND",
        "AK" to "Alaska",
        "PAC" to "Pacific  ·  HI and the islands",
    )

    private const val BASE = "https://aeronav.faa.gov/afd"

    private fun listing(edition: String): String {
        val c = URL("$BASE/$edition/").openConnection() as HttpURLConnection
        c.connectTimeout = 25000; c.readTimeout = 40000
        c.setRequestProperty("User-Agent", "PilotCompanion/1.0")
        try {
            if (c.responseCode != 200) return ""
            return c.inputStream.bufferedReader().readText()
        } finally { c.disconnect() }
    }

    /** The region's numbered pages for this edition, in the order they are printed. */
    fun pages(edition: String, region: String): List<String> {
        val html = try { listing(edition) } catch (e: Exception) { return emptyList() }
        val re = Regex("${region}_(\\d+)_${edition}\\.pdf", RegexOption.IGNORE_CASE)
        return re.findAll(html).map { it.value to (it.groupValues[1].toIntOrNull() ?: 0) }
            .distinctBy { it.first.lowercase() }.sortedBy { it.second }.map { it.first }.toList()
    }

    private fun fetch(url: String, to: File): Boolean {
        if (to.length() > 1000) return true
        for (attempt in 0 until 3) {
            try {
                val c = URL(url).openConnection() as HttpURLConnection
                c.connectTimeout = 20000; c.readTimeout = 40000
                c.setRequestProperty("User-Agent", "PilotCompanion/1.0")
                try {
                    if (c.responseCode != 200) return false
                    to.parentFile?.mkdirs()
                    val tmp = File(to.path + ".part")
                    c.inputStream.use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
                    if (tmp.length() < 1000) { tmp.delete(); return false }
                    tmp.renameTo(to)
                    return true
                } finally { c.disconnect() }
            } catch (e: Exception) {
                Thread.sleep(400L * (attempt + 1))
            }
        }
        return false
    }

    /**
     * Builds the book, reporting as it goes: (pages done, pages in all, what it is doing). Returns
     * the vault item, or null when the FAA's listing could not be read. Call off the main thread.
     */
    fun build(ctx: Context, region: String, progress: (Int, Int, String) -> Unit): VaultItem? {
        val ed = OfflinePack.csEdition()
        progress(0, 0, "Asking the FAA what is in this edition…")
        val names = pages(ed, region)
        if (names.isEmpty()) return null
        val dir = File(ctx.filesDir, "supplement/book/$ed/$region")
        dir.mkdirs()
        val got = ArrayList<File>()
        for ((i, n) in names.withIndex()) {
            val f = File(dir, n)
            if (fetch("$BASE/$ed/$n", f)) got.add(f)
            progress(i + 1, names.size, "Page ${i + 1} of ${names.size}")
        }
        if (got.size < names.size / 2) return null
        progress(names.size, names.size, "Binding ${got.size} pages into one book…")
        val name = "Chart Supplement · $region · $ed.pdf"
        val folderId = (VaultStore.childFolders(null).firstOrNull { it.name == SupplementShelf.FOLDER }
            ?: VaultStore.addFolder(SupplementShelf.FOLDER, null)).id
        VaultStore.itemsIn(folderId).firstOrNull { it.name == name && VaultStore.fileOf(it).length() > 0 }?.let { return it }
        val target = VaultStore.downloadTarget(name)
        try {
            PDFBoxResourceLoader.init(ctx.applicationContext)
            PDFMergerUtility().apply {
                for (p in got) addSource(p)
                destinationFileName = target.absolutePath
                mergeDocuments(null)
            }
        } catch (e: Throwable) {
            target.delete()
            return null
        }
        // Older editions of the same region make way for this one.
        for (old in VaultStore.itemsIn(folderId).filter { it.name.startsWith("Chart Supplement · $region · ") && it.name != name }) VaultStore.deleteItem(old)
        File(ctx.filesDir, "supplement/book/$ed/$region").deleteRecursively()
        return VaultStore.adopt(target, name, "application/pdf", folderId)
    }
}
