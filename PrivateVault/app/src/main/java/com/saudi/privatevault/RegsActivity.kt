package com.saudi.privatevault

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.xmlpull.v1.XmlPullParser
import java.io.File

/**
 * The FARs read in the app, not on a website: a Part from the official
 * eCFR (its API, the edition up to date today), kept on the phone, with its
 * contents by subpart and section, a search through the whole Part, each
 * section laid out paragraph by paragraph, and Gemini to explain it.
 */
class RegsActivity : BaseActivity() {
    companion object {
        const val EXTRA_TITLE = "title"
        const val EXTRA_PART = "part"

        fun open(ctx: Context, title: Int, part: String) =
            ctx.startActivity(Intent(ctx, RegsActivity::class.java).putExtra(EXTRA_TITLE, title).putExtra(EXTRA_PART, part))
    }

    class Section(val num: String, val head: String, val paras: List<String>, val subpart: String)
    class Doc(val head: String, val asOf: String, val sections: List<Section>)

    private lateinit var col: LinearLayout
    private var doc: Doc? = null
    private var inSection = false
    private var title = 14
    private var part = "61"
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = intent.getIntExtra(EXTRA_TITLE, 14)
        part = intent.getStringExtra(EXTRA_PART) ?: "61"
        col = EfbUi.screen(this, "$title CFR Part $part")
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (inSection) contents("") else finish()
            }
        })
        col.addView(EfbUi.text(this, getString(R.string.regs_loading), 14f, EfbUi.DIM).apply { setPadding(dp(4), dp(12), dp(4), 0) })
        lifecycleScope.launch {
            val d = withContext(Dispatchers.IO) { try { load() } catch (e: Exception) { null } }
            if (d == null || d.sections.isEmpty()) {
                col.removeAllViews()
                col.addView(EfbUi.text(this@RegsActivity, getString(R.string.regs_failed), 14f, EfbUi.WARN).apply { setPadding(dp(4), dp(12), dp(4), dp(12)) })
                return@launch
            }
            doc = d
            contents("")
        }
    }

    private fun cache() = File(filesDir, "regs/t$title-p$part.xml").apply { parentFile?.mkdirs() }

    /** The Part from the eCFR (refreshed after a week), or the copy on the phone. */
    private fun load(): Doc? {
        val f = cache()
        val fresh = f.exists() && System.currentTimeMillis() - f.lastModified() < 7L * 86400000
        if (!fresh) try {
            val titles = JSONObject(AviationData.get("https://www.ecfr.gov/api/versioner/v1/titles.json", 30000)).getJSONArray("titles")
            val asOf = (0 until titles.length()).map { titles.getJSONObject(it) }.first { it.optInt("number") == title }.optString("up_to_date_as_of")
            val xml = AviationData.get("https://www.ecfr.gov/api/versioner/v1/full/$asOf/title-$title.xml?part=$part", 60000)
            if (xml.contains("DIV8")) { f.writeText(xml); File(f.path + ".date").writeText(asOf) }
        } catch (e: Exception) {
        }
        if (!f.exists()) return null
        return parse(f, try { File(f.path + ".date").readText() } catch (e: Exception) { "" })
    }

    /** eCFR XML: DIV5 the part, DIV6 a subpart, DIV8 a section; HEAD its heading, P a paragraph. */
    private fun parse(f: File, asOf: String): Doc {
        val p = android.util.Xml.newPullParser()
        p.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, false)
        f.inputStream().use { input ->
            p.setInput(input, "UTF-8")
            var partHead = ""
            var subpart = ""
            val sections = ArrayList<Section>()
            var secNum: String? = null
            var secHead = ""
            var paras = ArrayList<String>()
            val text = StringBuilder()
            var collecting: String? = null   // "HEAD" or "P" while inside one
            var where = ""                   // the DIV the current HEAD belongs to
            var depth = 0
            var collectDepth = 0
            while (true) {
                when (p.next()) {
                    XmlPullParser.START_TAG -> {
                        depth++
                        val n = p.name
                        when {
                            n == "DIV5" -> where = "part"
                            n == "DIV6" -> where = "subpart"
                            n == "DIV8" -> { secNum = p.getAttributeValue(null, "N"); secHead = ""; paras = ArrayList(); where = "section" }
                            collecting == null && (n == "HEAD" || n == "P" || n == "FP" || n == "NOTE") -> { collecting = n; collectDepth = depth; text.setLength(0) }
                        }
                    }
                    XmlPullParser.TEXT -> if (collecting != null) text.append(p.text)
                    XmlPullParser.END_TAG -> {
                        val n = p.name
                        if (collecting != null && depth == collectDepth) {
                            val t = text.toString().replace(Regex("\\s+"), " ").trim()
                            if (collecting == "HEAD") when (where) {
                                "part" -> if (partHead.isEmpty()) partHead = t
                                "subpart" -> subpart = t
                                "section" -> secHead = t
                            } else if (secNum != null && t.isNotEmpty()) paras.add(t)
                            collecting = null
                        }
                        if (n == "DIV8" && secNum != null) {
                            sections.add(Section(secNum!!, secHead, paras, subpart))
                            secNum = null
                            where = "subpart"
                        }
                        depth--
                    }
                    XmlPullParser.END_DOCUMENT -> return Doc(partHead, asOf, sections)
                }
            }
        }
    }

    /** The contents by subpart, or the sections matching a search. */
    private fun contents(query: String) {
        inSection = false
        val d = doc ?: return
        col.removeAllViews()
        col.addView(EfbUi.text(this, d.head, 18f, EfbUi.TEXT, bold = true).apply { setPadding(dp(4), dp(6), dp(4), dp(2)) })
        col.addView(EfbUi.text(this, getString(R.string.regs_asof, d.asOf.ifEmpty { "—" }), 12f, EfbUi.DIM).apply { setPadding(dp(4), 0, dp(4), dp(10)) })
        val search = EditText(this).apply {
            hint = getString(R.string.regs_search); setText(query); setSingleLine()
            setTextColor(EfbUi.TEXT); setHintTextColor(EfbUi.DIM)
            background = EfbUi.cardBg(this@RegsActivity, EfbUi.CARD, 12).apply { setStroke(0, 0) }
            setPadding(dp(14), dp(11), dp(14), dp(11))
        }
        col.addView(search)
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(list)
        fun fill(q: String) {
            list.removeAllViews()
            val words = q.trim().lowercase()
            val hits = if (words.isEmpty()) d.sections else d.sections.filter { s ->
                (s.num + " " + s.head + " " + s.paras.joinToString(" ")).lowercase().contains(words)
            }
            var lastSub: String? = null
            var card: LinearLayout? = null
            for (s in hits.take(400)) {
                if (s.subpart != lastSub || card == null) {
                    lastSub = s.subpart
                    if (s.subpart.isNotEmpty()) list.addView(EfbUi.text(this, s.subpart.uppercase(), 11.5f, EfbUi.DIM, bold = true).apply { letterSpacing = 0.05f; setPadding(dp(6), dp(16), dp(6), dp(5)) })
                    card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@RegsActivity, EfbUi.CARD, 14).apply { setStroke(0, 0) } }
                    list.addView(card, LinearLayout.LayoutParams(-1, -2).apply { topMargin = if (s.subpart.isEmpty()) dp(10) else 0 })
                } else card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(14) })
                val row = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(10), dp(12), dp(10)); layoutDirection = View.LAYOUT_DIRECTION_LTR }
                row.addView(EfbUi.ltr(EfbUi.text(this, s.head.ifEmpty { "§ ${s.num}" }, 14.5f, EfbUi.TEXT)))
                if (words.isNotEmpty()) {
                    val body = s.paras.joinToString(" ")
                    val i = body.lowercase().indexOf(words)
                    if (i >= 0) row.addView(EfbUi.ltr(EfbUi.text(this, "…" + body.substring(maxOf(0, i - 40), minOf(body.length, i + 80)) + "…", 12f, EfbUi.DIM)))
                }
                row.setOnClickListener { section(s, q) }
                card!!.addView(row)
            }
            if (hits.isEmpty()) list.addView(EfbUi.text(this, getString(R.string.regs_none), 14f, EfbUi.DIM).apply { setPadding(dp(6), dp(14), dp(6), 0) })
        }
        fill(query)
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun afterTextChanged(s: Editable?) { fill(s.toString()) }
        })
    }

    /** One section, paragraph by paragraph, indented by its level: (a), (1), (i), (A). */
    private fun section(s: Section, back: String) {
        inSection = true
        col.removeAllViews()
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        top.addView(EfbUi.text(this, "‹ " + getString(R.string.regs_contents), 14f, EfbUi.ACCENT, bold = true).apply {
            setPadding(dp(4), dp(8), dp(12), dp(8)); setOnClickListener { contents(back) }
        }, LinearLayout.LayoutParams(0, -2, 1f))
        col.addView(top)
        col.addView(EfbUi.ltr(EfbUi.text(this, s.head, 19f, EfbUi.TEXT, bold = true)).apply { setPadding(dp(4), dp(6), dp(4), dp(10)) })
        val card = EfbUi.card(this)
        for (para in s.paras) {
            val level = when {
                Regex("^\\([a-z]{1,2}\\)").containsMatchIn(para) && !Regex("^\\((i|ii|iii|iv|v|vi|vii|viii|ix|x)\\)").containsMatchIn(para) -> 0
                Regex("^\\(\\d+\\)").containsMatchIn(para) -> 1
                Regex("^\\((i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)\\)").containsMatchIn(para) -> 2
                Regex("^\\([A-Z]\\)").containsMatchIn(para) -> 3
                else -> 0
            }
            card.addView(EfbUi.ltr(EfbUi.text(this, para, 15f, EfbUi.TEXT).apply {
                setLineSpacing(0f, 1.3f); setTextIsSelectable(true)
                setPadding(dp(4 + level * 16), dp(5), dp(2), dp(5))
            }))
        }
        col.addView(card)
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(12), 0, dp(4)) }
        fun action(label: String, go: () -> Unit) = actions.addView(EfbUi.text(this, label, 14f, EfbUi.ACCENT, bold = true).apply {
            gravity = Gravity.CENTER
            background = EfbUi.cardBg(this@RegsActivity, EfbUi.CARD, 12).apply { setStroke(0, 0) }
            setPadding(dp(10), dp(11), dp(10), dp(11))
            setOnClickListener { go() }
        }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        val text = s.head + "\n\n" + s.paras.joinToString("\n")
        action("✦ " + getString(R.string.regs_explain)) {
            AiChatActivity.open(this, null, text, "$title CFR ${s.head}", 0, getString(R.string.regs_explain_prompt))
        }
        action("⧉ " + getString(R.string.sel_copy)) {
            (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(s.num, text))
            Toast.makeText(this, R.string.sel_copied, Toast.LENGTH_SHORT).show()
        }
        col.addView(actions)
        (col.parent as? android.widget.ScrollView)?.scrollTo(0, 0)
    }
}
