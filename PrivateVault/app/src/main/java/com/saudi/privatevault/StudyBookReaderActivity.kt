package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import org.json.JSONArray
import org.json.JSONObject

/**
 * The book itself: the pages kept from study, read one at a time the way a book is read.
 *
 * A page carries the question, the explanation written in the pilot's own words, and anything
 * drawn over it — a diagram sketched out, an arrow to the part that matters, a circle round the
 * figure to remember — in whatever colour it was drawn in. The ink belongs to the page and comes
 * back with it.
 *
 * The contents list every page by subject, as a book's contents do, and a page can be moved
 * forward or back so the book ends up in the order its owner wants to read it in.
 */
class StudyBookReaderActivity : BaseActivity() {
    override val alwaysDark = true

    private val prefs by lazy { VaultLock.prefs(this) }
    private lateinit var pages: JSONArray
    private var at = 0
    private lateinit var body: LinearLayout
    private var sketch: SketchView? = null
    private var drawing = false
    private var ink = 0xFFFF375F.toInt()
    private var nib = 3.5f
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = 0xFF0F141A.toInt()
        window.navigationBarColor = 0xFF0F141A.toInt()
        pages = try { JSONArray(prefs.getString(KEY, "[]")) } catch (e: Exception) { JSONArray() }
        if (pages.length() == 0) { finish(); return }
        at = intent.getIntExtra(EXTRA_AT, prefs.getInt(KEY_AT, 0)).coerceIn(0, pages.length() - 1)
        ink = prefs.getInt("study_ink", ink)
        nib = prefs.getFloat("study_nib", nib)
        body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF0F141A.toInt())
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        setContentView(body)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(body) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            body.setPadding(0, bars.top, 0, bars.bottom); ins
        }
        paint()
    }

    override fun onPause() { super.onPause(); save() }

    private fun save() {
        sketch?.commit()
        prefs.edit().putString(KEY, pages.toString()).putInt(KEY_AT, at)
            .putInt("study_ink", ink).putFloat("study_nib", nib).apply()
    }

    private fun page(): JSONObject = pages.optJSONObject(at) ?: JSONObject()

    private fun chip(label: String, colour: Int, go: () -> Unit) = TextView(this).apply {
        text = label; textSize = 12.5f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
        typeface = EfbUi.MEDIUM
        background = EfbUi.cardBg(this@StudyBookReaderActivity, colour, 9)
        setPadding(dp(11), dp(8), dp(11), dp(8))
        setOnClickListener { go() }
    }

    private fun go(to: Int) {
        save()
        at = to.coerceIn(0, pages.length() - 1)
        drawing = false
        paint()
    }

    private fun paint() {
        body.removeAllViews()
        val p = page()

        // ---- the head: where we are in the book, and the way through it ----
        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0xFF1B222C.toInt()); setPadding(dp(6), dp(7), dp(8), dp(7))
        }
        head.addView(chip("‹", 0xFF2A3B4D.toInt()) { if (at > 0) go(at - 1) else finish() },
            LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        val mid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER }
        mid.addView(EfbUi.text(this, p.optString("t", "GENERAL"), 13f, 0xFFFFD60A.toInt(), bold = true).apply { gravity = Gravity.CENTER })
        mid.addView(EfbUi.text(this, "page ${at + 1} of ${pages.length()}", 11f, 0xFFA9B6C3.toInt()).apply { gravity = Gravity.CENTER })
        head.addView(mid, LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(chip("📑", 0xFF8E5CF7.toInt()) { contents() },
            LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        head.addView(chip("›", 0xFF2A3B4D.toInt()) { if (at < pages.length() - 1) go(at + 1) })
        body.addView(head)

        // ---- the page: the words, and the ink over them ----
        val sheet = android.widget.FrameLayout(this)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(16), dp(16), dp(24)) }
        when (p.optString("kind")) {
            "qa" -> qaTemplate(col, p)
            else -> noteTemplate(col, p)
        }
        figure(col, p)
        myNote(col, p)
        val src = p.optString("u")
        if (src.isNotEmpty()) col.addView(EfbUi.text(this, src, 10.5f, 0xFF5D6873.toInt()).apply {
            maxLines = 2; setPadding(0, dp(16), 0, 0)
        })
        col.addView(View(this), LinearLayout.LayoutParams(-1, dp(360)))
        sheet.addView(ScrollView(this).apply { addView(col); isFillViewport = true },
            android.widget.FrameLayout.LayoutParams(-1, -1))
        val sk = SketchView(this).also { sketch = it }
        sk.load(p.optJSONArray("ink"))
        sk.live = drawing
        sheet.addView(sk, android.widget.FrameLayout.LayoutParams(-1, -1))
        body.addView(sheet, LinearLayout.LayoutParams(-1, 0, 1f))

        // ---- the pen tray, when the pen is out ----
        if (drawing) body.addView(tray())

        // ---- what can be done with this page ----
        val acts = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xFF161D25.toInt())
            setPadding(dp(8), dp(7), dp(8), dp(7))
        }
        acts.addView(chip(if (drawing) "✓ Done drawing" else "✎ Draw", if (drawing) 0xFF30D158.toInt() else 0xFF2D7FF9.toInt()) {
            sketch?.commit(); drawing = !drawing; paint()
        }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        acts.addView(chip("✏ Write", 0xFF2A3B4D.toInt()) { editPage() },
            LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        acts.addView(chip("⋯", 0xFF2A3B4D.toInt()) { more() })
        body.addView(acts)
    }

    /** A small label above a block, the way a printed book names its parts. */
    private fun label(col: LinearLayout, t: String, colour: Int) {
        col.addView(EfbUi.text(this, t, 10.5f, colour, bold = true).apply {
            letterSpacing = 0.14f; setPadding(0, dp(16), 0, dp(6))
        })
    }

    /**
     * A question as a question bank sets one out: where it comes from, the question, its lettered
     * choices with the right one marked, and why it is the right one. Never one block of prose.
     */
    private fun qaTemplate(col: LinearLayout, p: org.json.JSONObject) {
        val where = listOf(p.optString("unit"), p.optString("sub")).filter { it.isNotEmpty() }
        if (where.isNotEmpty()) col.addView(EfbUi.text(this, where.joinToString("  ·  "), 11f, 0xFF8E9BA8.toInt()))
        val tags = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(8), 0, 0) }
        for ((t, c) in listOf(p.optString("acs") to 0xFF8E5CF7.toInt(), p.optString("src") to 0xFF2D7FF9.toInt())) {
            if (t.isEmpty()) continue
            tags.addView(EfbUi.text(this, t, 11.5f, 0xFFFFFFFF.toInt(), bold = true).apply {
                background = EfbUi.cardBg(this@StudyBookReaderActivity, c, 7)
                setPadding(dp(9), dp(4), dp(9), dp(4))
            }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        }
        if (tags.childCount > 0) col.addView(tags)

        label(col, "QUESTION" + p.optString("n").let { if (it.isEmpty()) "" else "  $it" }, 0xFF64D2FF.toInt())
        col.addView(EfbUi.text(this, p.optString("q"), 16f, 0xFFFFFFFF.toInt(), bold = true))

        val ans = p.optString("ans")
        val ch = p.optJSONArray("ch")
        if (ch != null && ch.length() > 0) {
            label(col, "CHOICES", 0xFF8E9BA8.toInt())
            for (i in 0 until ch.length()) {
                val o = ch.optJSONObject(i) ?: continue
                val right = o.optString("l").equals(ans, true)
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    background = EfbUi.cardBg(this@StudyBookReaderActivity,
                        if (right) 0xFF13301F.toInt() else 0xFF161D25.toInt(), 9)
                    setPadding(dp(11), dp(10), dp(11), dp(10))
                }
                row.addView(EfbUi.text(this, o.optString("l") + if (right) " ✓" else "", 14f,
                    if (right) 0xFF30D158.toInt() else 0xFF8E9BA8.toInt(), bold = true),
                    LinearLayout.LayoutParams(dp(34), -2))
                row.addView(EfbUi.text(this, o.optString("t"), 14.5f,
                    if (right) 0xFFE8F5EC.toInt() else 0xFFC2CBD6.toInt(), bold = right),
                    LinearLayout.LayoutParams(0, -2, 1f))
                col.addView(row, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(7) })
            }
        }
        val why = p.optString("why")
        if (why.isNotEmpty()) {
            label(col, "WHY" + (if (ans.isNotEmpty()) "  ·  ($ans) IS CORRECT" else ""), 0xFF30D158.toInt())
            col.addView(EfbUi.text(this, why, 14.5f, 0xFFB7D9C2.toInt()))
        }
    }

    /**
     * A passage of the book: its numbered heading, and the points under it kept as points rather
     * than run together into a wall of text.
     */
    private fun noteTemplate(col: LinearLayout, p: org.json.JSONObject) {
        val head = p.optString("head")
        if (head.isNotEmpty()) col.addView(EfbUi.text(this, head, 16.5f, 0xFFFFD60A.toInt(), bold = true))
        val pts = p.optJSONArray("pts")
        if (pts != null && pts.length() > 0) {
            for (i in 0 until pts.length()) {
                col.addView(EfbUi.text(this, pts.optString(i), 14.5f, 0xFFE2E8EF.toInt()).apply {
                    setPadding(0, dp(if (i == 0 && head.isEmpty()) 0 else 10), 0, 0)
                })
            }
        } else {
            col.addView(EfbUi.text(this, p.optString("q"), 15f, 0xFFFFFFFF.toInt(), bold = head.isEmpty())
                .apply { setPadding(0, dp(if (head.isEmpty()) 0 else 10), 0, 0) })
        }
    }

    /** The figure or table framed off the page, at the width of the book's page, on white. */
    private fun figure(col: LinearLayout, p: org.json.JSONObject) {
        val img = p.optString("img")
        if (img.isEmpty() || img == "null") return
        val f = java.io.File(java.io.File(filesDir, "studybook"), img)
        if (!f.exists()) return
        android.graphics.BitmapFactory.decodeFile(f.path)?.let { bmp ->
            label(col, "FIGURE", 0xFFFF9F0A.toInt())
            col.addView(android.widget.ImageView(this).apply {
                setImageBitmap(bmp)
                adjustViewBounds = true
                scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
                background = EfbUi.cardBg(this@StudyBookReaderActivity, 0xFFFFFFFF.toInt(), 8)
                setPadding(dp(4), dp(4), dp(4), dp(4))
            }, LinearLayout.LayoutParams(-1, -2))
        }
    }

    /** What the pilot wrote for themselves, which is the part worth the book. */
    private fun myNote(col: LinearLayout, p: org.json.JSONObject) {
        val mineTx = p.optString("e")
        label(col, "MY NOTE", 0xFFA5D6A7.toInt())
        col.addView(EfbUi.text(this, if (mineTx.isBlank()) "— nothing written yet —" else mineTx,
            14.5f, if (mineTx.isBlank()) 0xFF6E7681.toInt() else 0xFFA5D6A7.toInt()))
    }

    /** The colours, the nib, and the ways to take ink back off the page. */
    private fun tray(): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0xFF121820.toInt()); setPadding(dp(8), dp(7), dp(8), dp(7))
        }
        for (c in COLOURS) {
            row.addView(View(this).apply {
                background = android.graphics.drawable.GradientDrawable().apply {
                    shape = android.graphics.drawable.GradientDrawable.OVAL
                    setColor(c)
                    if (c == ink) setStroke(dp(3), 0xFFFFFFFF.toInt()) else setStroke(dp(1), 0x44FFFFFF)
                }
                setOnClickListener { ink = c; sketch?.colour = c; paintTray(row) }
            }, LinearLayout.LayoutParams(dp(26), dp(26)).apply { marginEnd = dp(7) })
        }
        for ((label, w) in listOf("·" to 2f, "•" to 3.5f, "●" to 6f)) {
            row.addView(chip(label, if (nib == w) 0xFF2D7FF9.toInt() else 0xFF2A313B.toInt()) {
                nib = w; sketch?.nibDp = w; paint()
            }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(5) })
        }
        row.addView(View(this), LinearLayout.LayoutParams(0, dp(1), 1f))
        row.addView(chip("↶", 0xFF2A313B.toInt()) { sketch?.undo() },
            LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(5) })
        row.addView(chip("🧹", 0xFF3A2A2A.toInt()) {
            MaterialAlertDialogBuilder(this).setMessage("Take all the ink off this page?")
                .setPositiveButton(R.string.delete) { _, _ -> sketch?.clearAll() }
                .setNegativeButton(R.string.cancel, null).show()
        })
        return HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(row) }
    }

    private fun paintTray(row: LinearLayout) {
        for (i in COLOURS.indices) {
            (row.getChildAt(i).background as? android.graphics.drawable.GradientDrawable)?.apply {
                if (COLOURS[i] == ink) setStroke(dp(3), 0xFFFFFFFF.toInt()) else setStroke(dp(1), 0x44FFFFFF)
            }
        }
    }

    // ---- the contents ----

    /** Every page by subject, the way a book's contents are set out. */
    private fun contents() {
        save()
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(EfbUi.BG) }
        val dlg = MaterialAlertDialogBuilder(this).setView(ScrollView(this).apply { addView(box) }).create()
        box.addView(EfbUi.text(this, "CONTENTS  ·  ${pages.length()} pages", 12f, 0xFF8E9BA8.toInt(), bold = true)
            .apply { letterSpacing = 0.1f; setPadding(dp(16), dp(16), dp(16), dp(10)) })
        val byTopic = LinkedHashMap<String, MutableList<Int>>()
        for (i in 0 until pages.length()) {
            val t = pages.optJSONObject(i)?.optString("t", "GENERAL") ?: "GENERAL"
            byTopic.getOrPut(t) { ArrayList() }.add(i)
        }
        for ((topic, list) in byTopic.entries.sortedBy { it.key }) {
            box.addView(EfbUi.text(this, "$topic   ·   ${list.size}", 12.5f, 0xFFFFD60A.toInt(), bold = true)
                .apply { setBackgroundColor(0xFF1A222B.toInt()); setPadding(dp(16), dp(8), dp(16), dp(8)) })
            for (i in list) {
                val p = pages.optJSONObject(i) ?: continue
                val mark = if ((p.optJSONArray("ink")?.length() ?: 0) > 0) "  ✎" else ""
                box.addView(EfbUi.text(this, "${i + 1}.  ${p.optString("q").replace("\n", " ").take(70)}$mark",
                    13.5f, if (i == at) 0xFFFFFFFF.toInt() else 0xFFC2CBD6.toInt(), bold = i == at).apply {
                    setPadding(dp(20), dp(10), dp(16), dp(10))
                    setOnClickListener { dlg.dismiss(); go(i) }
                })
            }
        }
        dlg.show()
    }

    // ---- editing, ordering, removing ----

    private fun more() {
        save()
        val items = ArrayList<Pair<String, () -> Unit>>()
        items.add("↑  Move this page earlier" to { move(-1) })
        items.add("↓  Move this page later" to { move(1) })
        items.add("🏷  Change the subject" to { retopic() })
        Maneuvers.byId(StudyBookActivity.maneuverFor(page().optString("t")))?.let { m ->
            items.add("▶  ${m.title}" to { ManeuversActivity.open(this, m.id) })
        }
        items.add("📚  Library" to { startActivity(Intent(this, LibraryActivity::class.java)) })
        items.add("✕  Take this page out of the book" to {
            MaterialAlertDialogBuilder(this).setMessage("Take page ${at + 1} out of the book?")
                .setPositiveButton(R.string.delete) { _, _ ->
                    pages.remove(at)
                    prefs.edit().putString(KEY, pages.toString()).apply()
                    if (pages.length() == 0) finish() else go(at.coerceAtMost(pages.length() - 1))
                }
                .setNegativeButton(R.string.cancel, null).show()
        })
        MaterialAlertDialogBuilder(this).setTitle("Page ${at + 1}")
            .setItems(items.map { it.first }.toTypedArray()) { _, i -> items[i].second() }
            .setNegativeButton(R.string.cancel, null).show()
    }

    private fun move(by: Int) {
        val to = at + by
        if (to < 0 || to >= pages.length()) { Toast.makeText(this, "Already at the end", Toast.LENGTH_SHORT).show(); return }
        val a = pages.optJSONObject(at); val b2 = pages.optJSONObject(to)
        pages.put(at, b2); pages.put(to, a)
        at = to
        save(); paint()
        Toast.makeText(this, "Now page ${at + 1}", Toast.LENGTH_SHORT).show()
    }

    private fun retopic() {
        val all = TOPICS
        MaterialAlertDialogBuilder(this).setTitle("File this page under")
            .setItems(all) { _, i -> page().put("t", all[i]); save(); paint() }
            .setNegativeButton(R.string.cancel, null).show()
    }

    private fun editPage() {
        save()
        val p = page()
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), 0) }
        fun box(hint: String, ink2: Int, text: String) = EditText(this).apply {
            this.hint = hint; setText(text); textSize = 13.5f
            setTextColor(ink2); setHintTextColor(0xFF6E7681.toInt())
            background = EfbUi.cardBg(this@StudyBookReaderActivity, 0xFF1E242C.toInt(), 9)
            setPadding(dp(10), dp(9), dp(10), dp(9))
            gravity = Gravity.TOP or Gravity.START
            minLines = 3
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val q = box("The question", 0xFFFFFFFF.toInt(), p.optString("q"))
        val e = box("Your explanation", 0xFFA5D6A7.toInt(), p.optString("e"))
        col.addView(q); col.addView(e, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        MaterialAlertDialogBuilder(this).setView(ScrollView(this).apply { addView(col) })
            .setPositiveButton(R.string.ok) { _, _ ->
                p.put("q", q.text.toString().trim()).put("e", e.text.toString().trim())
                save(); paint()
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    // ---- the ink ----

    /**
     * The ink on a page. Strokes are kept as fractions of the page's width, so a page drawn on one
     * screen comes back the same shape on another. While the pen is away the layer takes no touch
     * at all, and the page scrolls and reads as if it were not there.
     */
    inner class SketchView(ctx: Context) : View(ctx) {
        var live = false
        var colour = ink
        var nibDp = nib
        private val strokes = ArrayList<Triple<Int, Float, ArrayList<Float>>>()
        private var current: ArrayList<Float>? = null
        private val brush = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
        }
        private val path = Path()

        fun load(a: JSONArray?) {
            strokes.clear()
            if (a == null) return
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
                val pts = ArrayList<Float>()
                o.optJSONArray("p")?.let { for (k in 0 until it.length()) pts.add(it.optDouble(k).toFloat()) }
                if (pts.size >= 4) strokes.add(Triple(o.optInt("c"), o.optDouble("w", 3.5).toFloat(), pts))
            }
        }

        fun commit() {
            val a = JSONArray()
            for ((c, w, pts) in strokes) {
                a.put(JSONObject().put("c", c).put("w", w.toDouble())
                    .put("p", JSONArray().apply { for (v in pts) put(v.toDouble()) }))
            }
            if (a.length() > 0) page().put("ink", a) else page().remove("ink")
        }

        fun undo() { if (strokes.isNotEmpty()) { strokes.removeAt(strokes.size - 1); commit(); invalidate() } }
        fun clearAll() { strokes.clear(); commit(); invalidate() }

        override fun onTouchEvent(e: MotionEvent): Boolean {
            if (!live) return false
            val w = pxWidth().toFloat()
            val x = e.x / w; val y = e.y / w
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    current = ArrayList<Float>().apply { add(x); add(y) }
                    strokes.add(Triple(colour, nibDp, current!!))
                    parent?.requestDisallowInterceptTouchEvent(true)
                }
                MotionEvent.ACTION_MOVE -> current?.apply { add(x); add(y) }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if ((current?.size ?: 0) < 4) strokes.removeAll { it.third === current }
                    current = null
                    commit()
                }
            }
            invalidate()
            return true
        }

        private fun pxWidth() = if (getWidth() > 0) getWidth() else resources.displayMetrics.widthPixels

        override fun onDraw(c: Canvas) {
            val w = pxWidth().toFloat()
            val d = resources.displayMetrics.density
            for ((col2, wid, pts) in strokes) {
                if (pts.size < 4) continue
                brush.color = col2
                brush.strokeWidth = wid * d
                path.reset()
                path.moveTo(pts[0] * w, pts[1] * w)
                var i = 2
                while (i + 1 < pts.size) { path.lineTo(pts[i] * w, pts[i + 1] * w); i += 2 }
                c.drawPath(path, brush)
            }
        }
    }

    companion object {
        private const val KEY = "study_book_pages"
        private const val KEY_AT = "study_book_at"
        const val EXTRA_AT = "at"

        val COLOURS = intArrayOf(
            0xFFFF375F.toInt(), 0xFFFF9F0A.toInt(), 0xFFFFD60A.toInt(), 0xFF30D158.toInt(),
            0xFF64D2FF.toInt(), 0xFF2D7FF9.toInt(), 0xFFBF5AF2.toInt(), 0xFFFFFFFF.toInt(),
        )

        val TOPICS = arrayOf(
            "STALLS", "CROSSWIND", "TAKEOFF & LANDING", "PATTERN & RADIO", "AIRSPACE", "WEATHER",
            "NAVIGATION", "WEIGHT & BALANCE", "PERFORMANCE", "SYSTEMS", "REGULATIONS",
            "EMERGENCIES", "AEROMEDICAL", "GENERAL",
        )

        fun open(ctx: Context, at: Int = -1) = ctx.startActivity(
            Intent(ctx, StudyBookReaderActivity::class.java).apply { if (at >= 0) putExtra(EXTRA_AT, at) })
    }
}
