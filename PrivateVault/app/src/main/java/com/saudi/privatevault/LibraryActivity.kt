package com.saudi.privatevault

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/**
 * The pilot's library from the FAA itself: the AIM, the FARs (Parts 1, 61,
 * 91 and NTSB 830), the Private Pilot ACS and the handbooks. A PDF is found
 * on the FAA's own page each time (its address changes with each edition),
 * downloaded once into «📚 References», and read with the pens and Gemini.
 * The FARs open as the official eCFR, always current.
 */
class LibraryActivity : BaseActivity() {

    private lateinit var col: LinearLayout
    private fun dp(v: Int) = EfbUi.dp(this, v)

    /** A book: its file name, the FAA page that links it, and how its link is named there. */
    private class Book(val icon: String, val title: String, val sub: String, val file: String?, val page: String, val pattern: String?)

    private val books = listOf(
        Book("📘", "AIM · Aeronautical Information Manual", "Procedures, ATC, weather, airspace (FAA, current)", "AIM · Aeronautical Information Manual.pdf",
            "https://www.faa.gov/air_traffic/publications/", "aim[^\"'<>]*basic[^\"'<>]*\\.pdf|aim_[^\"'<>]*\\.pdf"),
        Book("📗", "Pilot/Controller Glossary", "Every ATC word and phrase", "Pilot Controller Glossary.pdf",
            "https://www.faa.gov/air_traffic/publications/", "pcg[^\"'<>]*\\.pdf"),
        Book("⚖️", "14 CFR Part 61", "Certification: pilots and instructors (eCFR, current)", null, "https://www.ecfr.gov/current/title-14/part-61", null),
        Book("⚖️", "14 CFR Part 91", "General operating and flight rules (eCFR, current)", null, "https://www.ecfr.gov/current/title-14/part-91", null),
        Book("⚖️", "14 CFR Part 1", "Definitions and abbreviations (eCFR, current)", null, "https://www.ecfr.gov/current/title-14/part-1", null),
        Book("⚖️", "49 CFR Part 830 · NTSB", "Accident and incident reporting (eCFR, current)", null, "https://www.ecfr.gov/current/title-49/part-830", null),
        Book("🎓", "Private Pilot ACS (Airplane)", "What the checkride tests, task by task", "Private Pilot ACS Airplane.pdf",
            "https://www.faa.gov/training_testing/testing/acs", "private[^\"'<>]*airplane[^\"'<>]*acs[^\"'<>]*\\.pdf|private_airplane[^\"'<>]*\\.pdf"),
        Book("📕", "Pilot's Handbook of Aeronautical Knowledge", "FAA-H-8083-25", "PHAK FAA-H-8083-25.pdf",
            "https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/phak", "faa-h-8083-25[a-z]?\\.pdf"),
        Book("📙", "Airplane Flying Handbook", "FAA-H-8083-3", "Airplane Flying Handbook FAA-H-8083-3.pdf",
            "https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/airplane_handbook", "faa-h-8083-3[a-z]?\\.pdf"),
        Book("🌤", "Aviation Weather Handbook", "FAA-H-8083-28", "Aviation Weather Handbook FAA-H-8083-28.pdf",
            "https://www.faa.gov/regulations_policies/handbooks_manuals/aviation", "faa-h-8083-28[a-z]?\\.pdf"),
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.lib_title))
        col.addView(EfbUi.text(this, getString(R.string.lib_intro), 13f, EfbUi.DIM).apply { setPadding(dp(4), dp(4), dp(4), dp(10)) })
        val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@LibraryActivity, EfbUi.CARD, 16).apply { setStroke(0, 0) } }
        for ((i, b) in books.withIndex()) {
            if (i > 0) card.addView(android.view.View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(56) })
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(14), dp(12), dp(12), dp(12)) }
            row.addView(EfbUi.text(this, b.icon, 20f), LinearLayout.LayoutParams(dp(34), -2))
            val t = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(8), 0, 0, 0) }
            t.addView(EfbUi.ltr(EfbUi.text(this, b.title, 15.5f, EfbUi.TEXT, bold = true)))
            val sub = EfbUi.ltr(EfbUi.text(this, b.sub + if (b.file != null && held(b) != null) "  ·  ✓ " + getString(R.string.lib_saved) else "", 12.5f, EfbUi.DIM))
            t.addView(sub)
            row.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
            row.setOnClickListener { open(b, sub) }
            card.addView(row)
        }
        col.addView(card)
        EfbUi.stagger(col)
    }

    private fun refs(): String =
        (VaultStore.childFolders(null).firstOrNull { it.name == EfbCheckActivity.REFERENCES } ?: VaultStore.addFolder(EfbCheckActivity.REFERENCES, null)).id

    private fun held(b: Book) = VaultStore.itemsIn(refs()).firstOrNull { it.name == b.file }

    private fun read(item: VaultItem) = startActivity(Intent(this, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))

    private fun open(b: Book, sub: TextView) {
        if (b.file == null) { WebActivity.open(this, b.title, b.page); return }
        held(b)?.let { read(it); return }
        sub.text = getString(R.string.lib_finding)
        lifecycleScope.launch {
            val item = withContext(Dispatchers.IO) {
                try {
                    val link = find(b) ?: return@withContext null
                    val target = VaultStore.downloadTarget(b.file)
                    val c = URL(link).openConnection() as HttpURLConnection
                    c.connectTimeout = 20000; c.readTimeout = 120000
                    c.setRequestProperty("User-Agent", UA)
                    try {
                        if (c.responseCode != 200) return@withContext null
                        val total = c.contentLengthLong
                        c.inputStream.use { inp ->
                            target.outputStream().use { out ->
                                val buf = ByteArray(256 * 1024); var done = 0L; var last = -1
                                while (true) {
                                    val n = inp.read(buf); if (n < 0) break
                                    out.write(buf, 0, n); done += n
                                    val pct = if (total > 0) (done * 100 / total).toInt() else (done / (1024 * 1024)).toInt()
                                    if (pct != last) { last = pct; runOnUiThread { sub.text = if (total > 0) "⬇ $pct%" else "⬇ $pct MB" } }
                                }
                            }
                        }
                    } finally { c.disconnect() }
                    if (target.length() < 20000) { target.delete(); null } else VaultStore.adopt(target, b.file, "application/pdf", refs())
                } catch (e: Exception) { null }
            }
            if (item != null) { sub.text = b.sub + "  ·  ✓ " + getString(R.string.lib_saved); read(item) }
            else {
                // The FAA moved it: its page, to tap the PDF there.
                sub.text = b.sub
                Toast.makeText(this@LibraryActivity, R.string.lib_page, Toast.LENGTH_LONG).show()
                try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(b.page))) } catch (e: Exception) {}
            }
        }
    }

    /** The book's PDF link on its FAA page today. */
    private fun find(b: Book): String? {
        val c = URL(b.page).openConnection() as HttpURLConnection
        c.connectTimeout = 20000; c.readTimeout = 30000
        c.setRequestProperty("User-Agent", UA)
        val html = try { c.inputStream.bufferedReader().readText() } finally { c.disconnect() }
        val hrefs = Regex("href=[\"']([^\"']+)[\"']", RegexOption.IGNORE_CASE).findAll(html).map { it.groupValues[1] }.toList()
        val re = Regex(b.pattern ?: return null, RegexOption.IGNORE_CASE)
        val hit = hrefs.firstOrNull { re.containsMatchIn(it.substringAfterLast('/')) } ?: hrefs.firstOrNull { re.containsMatchIn(it) } ?: return null
        return URL(URL(b.page), hit).toString()
    }

    companion object {
        private const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
    }
}
