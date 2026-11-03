package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.text.Html
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/**
 * An FAA handbook page inside the app: its chapters (and the full book)
 * as read from the FAA page today, each one downloaded once into
 * References and read in the app's PDF viewer; a page of handbooks
 * opens each one here the same way.
 */
class HandbookActivity : BaseActivity() {
    companion object {
        fun open(ctx: Context, name: String, page: String) =
            ctx.startActivity(Intent(ctx, HandbookActivity::class.java).putExtra("name", name).putExtra("page", page))
        private const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
    }

    private class Link(val url: String, val text: String, val note: String) { val pdf get() = url.substringBefore('?').endsWith(".pdf", true) }

    private lateinit var col: LinearLayout
    private lateinit var name: String
    private lateinit var page: String
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        name = intent.getStringExtra("name") ?: "FAA"
        page = intent.getStringExtra("page") ?: return finish()
        col = EfbUi.screen(this, name)
        col.addView(EfbUi.text(this, getString(R.string.lib_finding), 14f, EfbUi.DIM).apply { setPadding(dp(4), dp(12), dp(4), 0) })
        lifecycleScope.launch {
            val links = withContext(Dispatchers.IO) { try { links() } catch (e: Exception) { emptyList() } }
            col.removeAllViews()
            if (links.isEmpty()) failed() else show(links)
        }
    }

    private fun get(url: String): HttpURLConnection = (URL(url).openConnection() as HttpURLConnection).apply {
        connectTimeout = 20000; readTimeout = 60000; setRequestProperty("User-Agent", UA)
    }

    /** The PDFs on the page with their own words; on a page of handbooks, the handbooks. */
    private fun links(): List<Link> {
        val c = get(page)
        val html = try { c.inputStream.bufferedReader().readText() } finally { c.disconnect() }
        val main = html.substringAfter("<main", html)
        val here = URL(page)
        val all = Regex("<a\\s[^>]*href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>\\s*(\\(([^)]{1,40})\\))?", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL))
            .findAll(main).mapNotNull { m ->
                val text = Html.fromHtml(m.groupValues[2], Html.FROM_HTML_MODE_LEGACY).toString().replace(Regex("\\s+"), " ").trim()
                if (text.isEmpty()) null else Link(URL(here, m.groupValues[1].trim()).toString(), text, m.groupValues[4].trim())
            }.distinctBy { it.url }.toList()
        val pdfs = all.filter { it.pdf }
        // A handbook's page: its PDFs. A page of handbooks: the handbooks under it.
        val dir = here.path.trimEnd('/')
        val pages = all.filter { !it.pdf && URL(it.url).host.endsWith("faa.gov") && URL(it.url).path.trimEnd('/').let { p -> p.startsWith("$dir/") } }
        return if (pages.size > pdfs.size) pages + pdfs else pdfs
    }

    private fun failed() {
        col.addView(EfbUi.text(this, getString(R.string.hb_failed), 14f, EfbUi.WARN).apply { setPadding(dp(4), dp(12), dp(4), dp(12)) })
        col.addView(EfbUi.text(this, "🌐 " + getString(R.string.hb_browser), 14f, EfbUi.ACCENT, bold = true).apply {
            setPadding(dp(4), dp(8), dp(4), dp(8))
            // Still in the app: the FAA page in the app's own browser.
            setOnClickListener { WebActivity.open(this@HandbookActivity, name, page) }
        })
    }

    private fun show(links: List<Link>) {
        col.addView(EfbUi.text(this, getString(R.string.hb_intro), 13f, EfbUi.DIM).apply { setPadding(dp(4), dp(4), dp(4), dp(10)) })
        val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@HandbookActivity, EfbUi.CARD, 14).apply { setStroke(0, 0) } }
        col.addView(card)
        for ((i, l) in links.withIndex()) {
            if (i > 0) card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(50) })
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(14), dp(11), dp(12), dp(11)); layoutDirection = View.LAYOUT_DIRECTION_LTR }
            val held = if (l.pdf) held(l) else null
            row.addView(EfbUi.text(this, if (!l.pdf) "📚" else if (held != null) "📗" else "📄", 18f), LinearLayout.LayoutParams(dp(36), -2))
            val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            texts.addView(EfbUi.ltr(EfbUi.text(this, l.text, 14.5f, EfbUi.TEXT)))
            val sub = EfbUi.ltr(EfbUi.text(this, when {
                !l.pdf -> ""
                held != null -> "✓ " + getString(R.string.lib_saved)
                else -> l.note.ifEmpty { "PDF" }
            }, 12f, EfbUi.DIM))
            if (sub.text.isNotEmpty()) texts.addView(sub)
            row.addView(texts, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, "›", 20f, EfbUi.DIM))
            row.setOnClickListener { if (l.pdf) pdf(l, sub) else open(this, l.text, l.url) }
            card.addView(row)
        }
    }

    private fun refs(): String =
        (VaultStore.childFolders(null).firstOrNull { it.name == EfbCheckActivity.REFERENCES } ?: VaultStore.addFolder(EfbCheckActivity.REFERENCES, null)).id

    private fun fileName(l: Link): String {
        val t = if (l.text.contains(name, true)) l.text else "$name · ${l.text}"
        return t.replace(Regex("[\\\\/:*?\"<>|]"), " ").replace(Regex("\\s+"), " ").trim().take(120) + ".pdf"
    }

    private fun held(l: Link) = VaultStore.itemsIn(refs()).firstOrNull { it.name == fileName(l) }

    private fun read(item: VaultItem) = startActivity(Intent(this, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))

    private var busy = false

    private fun pdf(l: Link, sub: TextView) {
        held(l)?.let { read(it); return }
        if (busy) return
        busy = true
        val was = sub.text
        sub.text = "⬇ …"
        lifecycleScope.launch {
            val item = withContext(Dispatchers.IO) {
                val file = fileName(l)
                val target = VaultStore.downloadTarget(file)
                try {
                    val c = get(l.url)
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
                    if (target.length() < 20000) { target.delete(); null } else VaultStore.adopt(target, file, "application/pdf", refs())
                } catch (e: Exception) { target.delete(); null }
            }
            busy = false
            if (item != null) { sub.text = "✓ " + getString(R.string.lib_saved); read(item) }
            else { sub.text = was; android.widget.Toast.makeText(this@HandbookActivity, R.string.hb_failed, android.widget.Toast.LENGTH_LONG).show() }
        }
    }
}
