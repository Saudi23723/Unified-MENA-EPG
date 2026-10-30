package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

/**
 * Every part of a CFR title, from the eCFR's own structure: all of 14 CFR
 * (Aeronautics and Space), or the aviation chapters of 49 CFR (the NTSB and
 * the TSA), by chapter and subchapter, with a search; each part opens in
 * the app's FAR reader.
 */
class CfrBrowseActivity : BaseActivity() {
    companion object {
        fun open(ctx: Context, title: Int) = ctx.startActivity(Intent(ctx, CfrBrowseActivity::class.java).putExtra("title", title))
        // 49 CFR: the chapters a pilot meets (VIII NTSB, XII TSA).
        private val CHAPTERS_49 = setOf("VIII", "XII")
    }

    private class Part(val id: String, val name: String, val group: String)

    private lateinit var col: LinearLayout
    private var title = 14
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = intent.getIntExtra("title", 14)
        col = EfbUi.screen(this, if (title == 14) "14 CFR · Aeronautics and Space" else "49 CFR · NTSB & TSA")
        col.addView(EfbUi.text(this, getString(R.string.regs_loading), 14f, EfbUi.DIM).apply { setPadding(dp(4), dp(12), dp(4), 0) })
        lifecycleScope.launch {
            val parts = withContext(Dispatchers.IO) { try { load() } catch (e: Exception) { emptyList() } }
            col.removeAllViews()
            if (parts.isEmpty()) {
                col.addView(EfbUi.text(this@CfrBrowseActivity, getString(R.string.regs_failed), 14f, EfbUi.WARN).apply { setPadding(dp(4), dp(12), dp(4), 0) })
                return@launch
            }
            show(parts)
        }
    }

    private fun load(): List<Part> {
        val f = File(filesDir, "regs/structure-$title.json").apply { parentFile?.mkdirs() }
        if (!f.exists() || System.currentTimeMillis() - f.lastModified() > 7L * 86400000) try {
            val titles = JSONObject(AviationData.get("https://www.ecfr.gov/api/versioner/v1/titles.json", 30000)).getJSONArray("titles")
            val asOf = (0 until titles.length()).map { titles.getJSONObject(it) }.first { it.optInt("number") == title }.optString("up_to_date_as_of")
            f.writeText(AviationData.get("https://www.ecfr.gov/api/versioner/v1/structure/$asOf/title-$title.json", 90000))
        } catch (e: Exception) {
        }
        val root = JSONObject(f.readText())
        val out = ArrayList<Part>()
        fun walk(n: JSONObject, chapter: String, group: String) {
            val type = n.optString("type")
            if (n.optBoolean("reserved")) return
            val label = n.optString("label").ifEmpty { n.optString("label_description") }
            if (type == "part") {
                if (title == 49 && chapter !in CHAPTERS_49) return
                out.add(Part(n.optString("identifier"), n.optString("label_description").ifEmpty { label }, group))
                return
            }
            val kids = n.optJSONArray("children") ?: return
            val ch = if (type == "chapter") n.optString("identifier") else chapter
            val g = if (type == "chapter" || type == "subchapter") label else group
            for (i in 0 until kids.length()) walk(kids.getJSONObject(i), ch, g)
        }
        walk(root, "", "")
        return out
    }

    private fun show(parts: List<Part>) {
        val search = EditText(this).apply {
            hint = getString(R.string.cfr_search); setSingleLine()
            setTextColor(EfbUi.TEXT); setHintTextColor(EfbUi.DIM)
            background = EfbUi.cardBg(this@CfrBrowseActivity, EfbUi.CARD, 12).apply { setStroke(0, 0) }
            setPadding(dp(14), dp(11), dp(14), dp(11))
        }
        col.addView(search)
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(list)
        fun fill(q: String) {
            list.removeAllViews()
            val w = q.trim().lowercase()
            var group: String? = null
            var card: LinearLayout? = null
            for (p in parts.filter { w.isEmpty() || "part ${p.id} ${p.name} ${p.group}".lowercase().contains(w) }) {
                if (p.group != group || card == null) {
                    group = p.group
                    list.addView(EfbUi.ltr(EfbUi.text(this, p.group.uppercase(), 11.5f, EfbUi.DIM, bold = true)).apply { letterSpacing = 0.04f; setPadding(dp(6), dp(16), dp(6), dp(5)) })
                    card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@CfrBrowseActivity, EfbUi.CARD, 14).apply { setStroke(0, 0) } }
                    list.addView(card)
                } else card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(14) })
                val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(dp(14), dp(11), dp(12), dp(11)); layoutDirection = View.LAYOUT_DIRECTION_LTR }
                row.addView(EfbUi.text(this, "Part ${p.id}", 14.5f, EfbUi.ACCENT, bold = true, mono = true), LinearLayout.LayoutParams(dp(96), -2))
                row.addView(EfbUi.ltr(EfbUi.text(this, p.name, 14f, EfbUi.TEXT)), LinearLayout.LayoutParams(0, -2, 1f))
                row.setOnClickListener { RegsActivity.open(this, title, p.id) }
                card!!.addView(row)
            }
        }
        fill("")
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun afterTextChanged(s: Editable?) = fill(s.toString())
        })
    }
}
