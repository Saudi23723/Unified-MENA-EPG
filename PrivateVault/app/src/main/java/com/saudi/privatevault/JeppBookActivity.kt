package com.saudi.privatevault

import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.Editable
import android.text.SpannableString
import android.text.Spanned
import android.text.TextWatcher
import android.text.style.StyleSpan
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject

/**
 * The pilot's Jeppesen Private Pilot Maneuvers as a book of the app's own: a contents page by
 * chapter, each maneuver set as text with its headings, numbered steps, inset notes and figures,
 * a search across the whole book, adjustable type, and the place you stopped remembered.
 */
class JeppBookActivity : BaseActivity() {
    companion object {
        const val EXTRA_NO = "no"
        private var book: JSONObject? = null

        fun load(ctx: Context): JSONObject = book ?: JSONObject(ctx.assets.open("jepp/book.json").bufferedReader().use { it.readText() }).also { book = it }

        fun open(a: Activity, no: Int? = null) =
            a.startActivity(Intent(a, JeppBookActivity::class.java).apply { if (no != null) putExtra(EXTRA_NO, no) })

        /** Every maneuver with its chapter, in the book's order. */
        fun maneuvers(ctx: Context): List<Pair<JSONObject, JSONObject>> {
            val out = ArrayList<Pair<JSONObject, JSONObject>>()
            val chs = load(ctx).getJSONArray("chapters")
            for (i in 0 until chs.length()) {
                val c = chs.getJSONObject(i); val ms = c.getJSONArray("maneuvers")
                for (k in 0 until ms.length()) out += c to ms.getJSONObject(k)
            }
            return out
        }
    }

    private lateinit var col: LinearLayout
    private fun dp(v: Int) = EfbUi.dp(this, v)
    private val prefs get() = VaultLock.prefs(this)
    private var scale: Float
        get() = prefs.getFloat("jepp_scale", 1f)
        set(v) { prefs.edit().putFloat("jepp_scale", v.coerceIn(0.8f, 1.5f)).apply() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val no = intent.getIntExtra(EXTRA_NO, -1)
        when {
            no == 0 -> preface()
            no > 0 -> maneuver(no)
            else -> contents()
        }
    }

    override fun onResume() {
        super.onResume()
        if (intent.getIntExtra(EXTRA_NO, -1) < 0 && ::col.isInitialized) { col.removeAllViews(); fillContents() }
    }

    // ---------------------------------------------------------------- contents

    private fun contents() {
        col = EfbUi.screen(this, "Private Pilot Maneuvers")
        col.layoutDirection = View.LAYOUT_DIRECTION_LTR
        fillContents()
        EfbUi.stagger(col)
    }

    private fun fillContents() {
        val b = load(this)
        // The cover, as a card.
        val cover = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(0xFF0B3D91.toInt(), 0xFF1565C0.toInt(), 0xFF4FA3E0.toInt())).apply { cornerRadius = dp(14).toFloat() }
            setPadding(dp(20), dp(20), dp(20), dp(20))
        }
        cover.addView(EfbUi.text(this, "JEPPESEN  ·  GUIDED FLIGHT DISCOVERY", 11f, 0xCCFFFFFF.toInt(), bold = true).apply { letterSpacing = 0.08f })
        cover.addView(EfbUi.text(this, "Private Pilot\nManeuvers", 28f, 0xFFFFFFFF.toInt(), bold = true).apply { setPadding(0, dp(8), 0, dp(6)); setLineSpacing(0f, 0.95f) })
        val all = maneuvers(this)
        val read = all.count { prefs.getBoolean("jepp_read_" + it.second.getInt("no"), false) }
        cover.addView(EfbUi.text(this, "${b.getJSONArray("chapters").length()} chapters · ${all.size} maneuvers · $read read", 13f, 0xDDFFFFFF.toInt()))
        val last = prefs.getInt("jepp_last", 0)
        if (last > 0) all.firstOrNull { it.second.getInt("no") == last }?.let { (_, m) ->
            val go = TextView(this).apply {
                text = "▶  Continue · ${m.getInt("no")}. ${m.getString("title")}"; textSize = 14f; typeface = EfbUi.MEDIUM
                setTextColor(0xFF0B3D91.toInt()); setPadding(dp(14), dp(9), dp(14), dp(9))
                background = GradientDrawable().apply { cornerRadius = dp(20).toFloat(); setColor(0xFFFFFFFF.toInt()) }
            }
            EfbUi.pressable(go) { open(this, last) }
            cover.addView(go, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(14) })
        }
        col.addView(cover, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) })

        // Search the whole book.
        val search = EditText(this).apply {
            hint = "🔍  Search the book"; textSize = 15f; setSingleLine()
            setTextColor(EfbUi.TEXT); setHintTextColor(EfbUi.DIM)
            background = EfbUi.cardBg(this@JeppBookActivity); setPadding(dp(14), dp(11), dp(14), dp(11))
        }
        col.addView(search, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        val results = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(results)
        val toc = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(toc)
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val q = s.toString().trim()
                results.removeAllViews()
                toc.visibility = if (q.length >= 3) View.GONE else View.VISIBLE
                if (q.length >= 3) find(q, results)
            }
        })

        // Preface, then the chapters.
        toc.addView(EfbUi.section(this, "Front matter"))
        val front = groupCard()
        front.addView(row("📄", "Preface", "How the book is built", false) { open(this, 0) })
        toc.addView(front)
        val chs = b.getJSONArray("chapters")
        for (i in 0 until chs.length()) {
            val c = chs.getJSONObject(i)
            toc.addView(EfbUi.section(this, "Chapter ${c.getInt("n")} · ${c.getString("title")}"))
            val intro = c.getJSONArray("intro")
            if (intro.length() > 0) {
                val t = EfbUi.text(this, intro.getJSONObject(0).getString("x"), 13f, EfbUi.DIM).apply {
                    maxLines = 3; ellipsize = android.text.TextUtils.TruncateAt.END; setPadding(dp(16), 0, dp(16), dp(8))
                    setOnClickListener { maxLines = if (maxLines == 3) 40 else 3 }
                }
                toc.addView(t)
            }
            val card = groupCard()
            val ms = c.getJSONArray("maneuvers")
            for (k in 0 until ms.length()) {
                val m = ms.getJSONObject(k); val n = m.getInt("no")
                if (k > 0) card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(60) })
                val hasAnim = ManeuverBook.FOR.containsValue(n)
                card.addView(row("$n", m.getString("title"), "Maneuver $n" + if (hasAnim) "  ·  ▶ animated" else "", prefs.getBoolean("jepp_read_$n", false)) { open(this, n) })
            }
            toc.addView(card)
        }
    }

    private fun groupCard() = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@JeppBookActivity) }

    private fun row(badge: String, title: String, sub: String, done: Boolean, click: () -> Unit): View {
        val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(12), dp(11), dp(12), dp(11)) }
        r.addView(TextView(this).apply {
            text = badge; textSize = 13f; typeface = EfbUi.MEDIUM; gravity = Gravity.CENTER
            setTextColor(if (done) 0xFFFFFFFF.toInt() else EfbUi.ACCENT)
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; if (done) setColor(EfbUi.GOOD) else setStroke(dp(1), EfbUi.ACCENT) }
        }, LinearLayout.LayoutParams(dp(34), dp(34)))
        val t = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), 0, dp(6), 0) }
        t.addView(EfbUi.text(this, title, 15.5f, EfbUi.TEXT, bold = true))
        t.addView(EfbUi.text(this, sub, 12f, EfbUi.DIM))
        r.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
        r.addView(EfbUi.text(this, "›", 22f, EfbUi.DIM))
        r.setBackgroundResource(R.drawable.item_focus_bg)
        r.setOnClickListener { click() }
        return r
    }

    private fun find(q: String, into: LinearLayout) {
        val ql = q.lowercase()
        var hits = 0
        val card = groupCard()
        for ((c, m) in maneuvers(this)) {
            val bl = m.getJSONArray("blocks")
            for (i in 0 until bl.length()) {
                val o = bl.getJSONObject(i)
                if (o.getString("t") == "f") continue
                val x = o.getString("x"); val at = x.lowercase().indexOf(ql)
                if (at < 0) continue
                val from = maxOf(0, at - 50); val to = minOf(x.length, at + q.length + 70)
                val snip = (if (from > 0) "…" else "") + x.substring(from, to) + if (to < x.length) "…" else ""
                val sp = SpannableString(snip)
                val s0 = snip.lowercase().indexOf(ql)
                if (s0 >= 0) sp.setSpan(StyleSpan(Typeface.BOLD), s0, s0 + q.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                if (hits > 0) card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
                val r = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(10), dp(14), dp(10)) }
                r.addView(EfbUi.text(this, "${m.getInt("no")} · ${m.getString("title")}", 12f, EfbUi.ACCENT, bold = true))
                r.addView(EfbUi.text(this, sp, 14f, EfbUi.TEXT))
                r.setBackgroundResource(R.drawable.item_focus_bg)
                val n = m.getInt("no")
                r.setOnClickListener { startActivity(Intent(this, JeppBookActivity::class.java).putExtra(EXTRA_NO, n).putExtra("q", q)) }
                card.addView(r)
                if (++hits >= 60) break
            }
            if (hits >= 60) break
        }
        into.addView(EfbUi.section(this, if (hits == 0) "No results" else "$hits results"))
        if (hits > 0) into.addView(card)
    }

    // ---------------------------------------------------------------- reading

    private fun preface() {
        col = EfbUi.screen(this, "Preface") { bar -> sizeMenu(bar) }
        col.layoutDirection = View.LAYOUT_DIRECTION_LTR
        render(load(this).getJSONArray("preface"), null)
    }

    private fun maneuver(no: Int) {
        val all = maneuvers(this)
        val i = all.indexOfFirst { it.second.getInt("no") == no }
        if (i < 0) { finish(); return }
        val (c, m) = all[i]
        prefs.edit().putInt("jepp_last", no).apply()
        col = EfbUi.screen(this, "Maneuver $no") { bar -> sizeMenu(bar) }
        col.layoutDirection = View.LAYOUT_DIRECTION_LTR

        col.addView(EfbUi.text(this, "CHAPTER ${c.getInt("n")} · ${c.getString("title").uppercase()}", 11.5f, EfbUi.ACCENT, bold = true).apply {
            letterSpacing = 0.07f; setPadding(dp(2), dp(16), dp(2), 0)
        })
        col.addView(EfbUi.text(this, "$no — ${m.getString("title")}", 26f * scale, EfbUi.TEXT, bold = true).apply { setPadding(dp(2), dp(6), dp(2), dp(4)) })

        // The animation, when the app has one for it.
        ManeuverBook.FOR.entries.firstOrNull { it.value == no }?.key?.let { id ->
            Maneuvers.byId(id)?.let { mm ->
                val f = FrameLayout(this).apply { background = EfbUi.cardBg(this@JeppBookActivity, 0xFF0E1712.toInt(), 14); clipToOutline = true }
                f.addView(ManeuverAnimationView(this).apply { anim = mm.anim() }, FrameLayout.LayoutParams(-1, -1))
                col.addView(f, LinearLayout.LayoutParams(-1, dp(220)).apply { topMargin = dp(12) })
                val go = TextView(this).apply {
                    text = "Speeds, ACS standards and errors for the SportStar  ›"; textSize = 13.5f; typeface = EfbUi.MEDIUM
                    setTextColor(EfbUi.ACCENT); setPadding(dp(2), dp(8), dp(2), dp(4))
                }
                EfbUi.pressable(go) { ManeuversActivity.open(this, id) }
                col.addView(go)
            }
        }

        render(m.getJSONArray("blocks"), intent.getStringExtra("q"))

        // Read, and the neighbours.
        val key = "jepp_read_$no"
        val mark = com.google.android.material.button.MaterialButton(this).apply {
            fun label() { text = if (prefs.getBoolean(key, false)) "✓  Read — tap to clear" else "Mark as read" }
            label()
            setOnClickListener { prefs.edit().putBoolean(key, !prefs.getBoolean(key, false)).apply(); label() }
        }
        col.addView(mark, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(22) })
        val nav = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(8), 0, 0) }
        fun navCard(head: String, title: String, to: Int, lp: LinearLayout.LayoutParams) {
            val v = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@JeppBookActivity); setPadding(dp(14), dp(10), dp(14), dp(12))
                addView(EfbUi.text(this@JeppBookActivity, head, 11.5f, EfbUi.ACCENT, bold = true))
                addView(EfbUi.text(this@JeppBookActivity, title, 13.5f, EfbUi.TEXT).apply { maxLines = 2 })
            }
            EfbUi.pressable(v) { finish(); open(this, to) }
            nav.addView(v, lp)
        }
        all.getOrNull(i - 1)?.let { (_, p) -> navCard("‹  Previous", "${p.getInt("no")}. ${p.getString("title")}", p.getInt("no"), LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) }) }
            ?: nav.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        all.getOrNull(i + 1)?.let { (_, n) -> navCard("Next  ›", "${n.getInt("no")}. ${n.getString("title")}", n.getInt("no"), LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(6) }) }
            ?: nav.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        col.addView(nav)
        col.addView(EfbUi.text(this, "From your copy of Jeppesen's Private Pilot Maneuvers, set as text by the app (OCR) — a figure or a word may read wrong; the printed book is the reference.", 11f, EfbUi.DIM).apply { setPadding(dp(4), dp(16), dp(4), 0) })
    }

    private fun sizeMenu(bar: com.google.android.material.appbar.MaterialToolbar) {
        bar.menu.add("A−").setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_ALWAYS)
        bar.menu.add("A+").setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_ALWAYS)
        bar.setOnMenuItemClickListener { item ->
            scale += if (item.title == "A+") 0.1f else -0.1f
            recreate(); true
        }
    }

    /** The blocks of a section: headings, paragraphs, numbered steps, notes and figures. */
    private fun render(blocks: JSONArray, highlight: String?) {
        var step = 0
        var firstHit: View? = null
        for (i in 0 until blocks.length()) {
            val o = blocks.getJSONObject(i)
            val x = o.getString("x")
            val v: View = when (o.getString("t")) {
                "h" -> { step = 0; EfbUi.text(this, x, 17.5f * scale, EfbUi.ACCENT, bold = true).apply { setPadding(dp(2), dp(22), dp(2), dp(2)) } }
                "s" -> {
                    step++
                    val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; background = EfbUi.cardBg(this@JeppBookActivity); setPadding(dp(14), dp(13), dp(14), dp(13)) }
                    r.addView(TextView(this).apply {
                        text = "$step"; textSize = 13f; typeface = EfbUi.MEDIUM; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt())
                        background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(EfbUi.ACCENT) }
                    }, LinearLayout.LayoutParams(dp(26), dp(26)))
                    r.addView(bodyText(lead(x), 15.5f, highlight).apply { setPadding(dp(12), 0, 0, 0) }, LinearLayout.LayoutParams(0, -2, 1f))
                    r.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) }
                    r
                }
                "n" -> {
                    val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) } }
                    r.addView(View(this).apply { setBackgroundColor(EfbUi.ACCENT) }, LinearLayout.LayoutParams(dp(3), -1))
                    r.addView(bodyText(x, 14f, highlight, EfbUi.DIM).apply { setPadding(dp(12), dp(4), dp(4), dp(4)) }, LinearLayout.LayoutParams(0, -2, 1f))
                    r
                }
                "f" -> figure(x, o.optDouble("r", 0.6).toFloat())
                "a" -> LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(EfbUi.section(this@JeppBookActivity, "ACS · Airman Certification Standards"))
                    addView(figure(x, o.optDouble("r", 1.0).toFloat()))
                }
                else -> bodyText(x, 16f, highlight).apply { setPadding(dp(2), dp(10), dp(2), 0) }
            }
            col.addView(v)
            if (firstHit == null && highlight != null && x.contains(highlight, true)) firstHit = v
        }
        firstHit?.let { hit -> col.post { (col.parent as? android.widget.ScrollView)?.smoothScrollTo(0, maxOf(0, hit.top - dp(60))) } }
    }

    /** The opening sentence of a step in bold, as the book sets it. */
    private fun lead(x: String): CharSequence {
        val end = x.indexOf(". ")
        if (end !in 8..80) return x
        return SpannableString(x).apply { setSpan(StyleSpan(Typeface.BOLD), 0, end + 1, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE) }
    }

    private fun bodyText(x: CharSequence, size: Float, highlight: String?, color: Int = EfbUi.TEXT): TextView {
        val s = SpannableString(x)
        if (highlight != null && highlight.isNotEmpty()) {
            var at = x.toString().indexOf(highlight, ignoreCase = true)
            while (at >= 0) {
                s.setSpan(android.text.style.BackgroundColorSpan(0x66FFD60A), at, at + highlight.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                at = x.toString().indexOf(highlight, at + highlight.length, ignoreCase = true)
            }
        }
        return EfbUi.text(this, s, size * scale, color).apply { setLineSpacing(0f, 1.28f) }
    }

    private fun figure(name: String, ratio: Float): View {
        val img = ImageView(this).apply {
            scaleType = ImageView.ScaleType.FIT_CENTER; adjustViewBounds = true
            background = EfbUi.cardBg(this@JeppBookActivity, 0xFFFFFFFF.toInt(), 12); clipToOutline = true
        }
        val w = resources.displayMetrics.widthPixels - dp(28)
        img.layoutParams = LinearLayout.LayoutParams(-1, (w * ratio).toInt()).apply { topMargin = dp(14) }
        Thread {
            val bm = try { assets.open("jepp/$name").use { BitmapFactory.decodeStream(it) } } catch (e: Exception) { null }
            runOnUiThread { if (bm != null) img.setImageBitmap(bm) }
        }.start()
        img.setOnClickListener { zoom(name) }
        return img
    }

    /** A figure alone, full screen, to pinch and pan. */
    private fun zoom(name: String) {
        val d = Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val f = FrameLayout(this).apply { setBackgroundColor(0xFF000000.toInt()) }
        val z = ZoomImageView(this)
        f.addView(z, FrameLayout.LayoutParams(-1, -1))
        f.addView(TextView(this).apply {
            text = "✕"; textSize = 20f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0x99000000.toInt()) }
            setOnClickListener { d.dismiss() }
        }, FrameLayout.LayoutParams(dp(42), dp(42), Gravity.TOP or Gravity.END).apply { setMargins(dp(12), dp(40), dp(14), 0) })
        d.setContentView(f); d.show()
        Thread {
            val bm = try { assets.open("jepp/$name").use { BitmapFactory.decodeStream(it) } } catch (e: Exception) { null }
            runOnUiThread { if (bm != null) { z.setImageBitmap(bm); z.fit() } }
        }.start()
    }
}
