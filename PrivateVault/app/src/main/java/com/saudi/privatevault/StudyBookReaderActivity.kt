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
        if (prefs.getBoolean(KEY_AUTO, true)) autoSort()
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

    // ---- the order the book puts itself in ----

    private val RE_UNIT_NO = Regex("""Unit\s*(\d+)""")
    private val RE_SUB_NO = Regex("""Subunit\s*(\d+)""")
    private val RE_HEAD_NO = Regex("""^(\d+)\.(\d+)""")

    /**
     * Where a page belongs in the book.
     *
     * A question bank is already a book with an order of its own — unit, then subunit, then the
     * number of the question — and that is the order it is meant to be studied in. A passage of
     * the book is numbered the same way, 3.10 being the tenth section of unit three, and it comes
     * before the questions on it. Anything the page does not say falls to the back, kept together
     * by subject and then by when it was taken.
     */
    private fun orderOf(p: JSONObject): IntArray {
        val head = p.optString("head")
        RE_HEAD_NO.find(head)?.let {
            return intArrayOf(it.groupValues[1].toInt(), it.groupValues[2].toInt(), 0)
        }
        val u = RE_UNIT_NO.find(p.optString("unit"))?.groupValues?.get(1)?.toIntOrNull() ?: 9999
        val sb = RE_SUB_NO.find(p.optString("sub"))?.groupValues?.get(1)?.toIntOrNull() ?: 9999
        val q = p.optString("n").toIntOrNull() ?: 9998
        return intArrayOf(u, sb, q)
    }

    /** The chapter a page sits under, for the contents. */
    private fun chapterOf(p: JSONObject): String {
        val head = p.optString("head")
        RE_HEAD_NO.find(head)?.let { return "Unit ${it.groupValues[1]}" }
        val u = p.optString("unit")
        if (u.isNotEmpty()) return u
        return p.optString("t", "GENERAL")
    }

    /** The book sorts itself into that order, keeping the page being read under the finger. */
    private fun autoSort() {
        val here = pages.optJSONObject(at)
        val list = (0 until pages.length()).mapNotNull { pages.optJSONObject(it) }
        val sorted = list.sortedWith(compareBy(
            { orderOf(it)[0] }, { orderOf(it)[1] }, { orderOf(it)[2] },
            { it.optString("t") }, { it.optLong("at") },
        ))
        val out = JSONArray()
        for (o in sorted) out.put(o)
        pages = out
        if (here != null) {
            val i = sorted.indexOfFirst { it === here }
            if (i >= 0) at = i
        }
    }

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
        placed.clear()
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
        head.addView(chip("PDF", 0xFF2D7FF9.toInt()) { exportPdf() },
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
    /** What this page is, said plainly at the top of it. */
    private fun kindBadge(col: LinearLayout, t: String, colour: Int) {
        col.addView(EfbUi.text(this, t, 10.5f, 0xFF0F141A.toInt(), bold = true).apply {
            letterSpacing = 0.16f
            background = EfbUi.cardBg(this@StudyBookReaderActivity, colour, 6)
            setPadding(dp(9), dp(3), dp(9), dp(4))
        }, LinearLayout.LayoutParams(-2, -2).apply { bottomMargin = dp(10) })
    }

    private fun qaTemplate(col: LinearLayout, p: org.json.JSONObject) {
        kindBadge(col, "QUESTION", 0xFF64D2FF.toInt())
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
                val letter = o.optString("l")
                // Right, wrong, or simply not said — the bank marks it, and the page says which.
                val right = if (o.has("ok")) o.optBoolean("ok") else letter.equals(ans, true)
                val judged = o.has("ok") || ans.isNotEmpty()
                val card = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    background = EfbUi.cardBg(this@StudyBookReaderActivity,
                        if (!judged) 0xFF161D25.toInt() else if (right) 0xFF13301F.toInt() else 0xFF2A161A.toInt(), 9)
                    setPadding(dp(11), dp(10), dp(11), dp(10))
                }
                val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
                line.addView(EfbUi.text(this, letter + if (!judged) "" else if (right) "  ✓" else "  ✗", 14f,
                    if (!judged) 0xFF8E9BA8.toInt() else if (right) 0xFF30D158.toInt() else 0xFFFF6B6B.toInt(), bold = true),
                    LinearLayout.LayoutParams(dp(42), -2))
                line.addView(EfbUi.text(this, o.optString("t"), 14.5f,
                    if (right && judged) 0xFFE8F5EC.toInt() else 0xFFC2CBD6.toInt(), bold = right && judged),
                    LinearLayout.LayoutParams(0, -2, 1f))
                card.addView(line)
                val reason = o.optString("why")
                if (reason.isNotEmpty()) {
                    card.addView(EfbUi.text(this, (if (right) "WHY IT IS RIGHT" else "WHY IT IS WRONG"), 9.5f,
                        if (right) 0xFF5BBF7A.toInt() else 0xFFC9757E.toInt(), bold = true).apply {
                        letterSpacing = 0.12f; setPadding(dp(42), dp(8), 0, dp(3))
                    })
                    card.addView(EfbUi.text(this, reason, 13f,
                        if (right) 0xFFB7D9C2.toInt() else 0xFFD9B7BC.toInt()).apply { setPadding(dp(42), 0, 0, 0) })
                }
                col.addView(card, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(7) })
            }
        }
        val why = p.optString("why")
        val carried = (0 until (ch?.length() ?: 0)).any { ch?.optJSONObject(it)?.optString("why")?.isNotEmpty() == true }
        if (why.isNotEmpty() && !carried) {
            label(col, "WHY" + (if (ans.isNotEmpty()) "  ·  ($ans) IS CORRECT" else ""), 0xFF30D158.toInt())
            col.addView(EfbUi.text(this, why, 14.5f, 0xFFB7D9C2.toInt()))
        }
    }

    /**
     * A passage of the book: its numbered heading, and the points under it kept as points rather
     * than run together into a wall of text.
     */
    private fun noteTemplate(col: LinearLayout, p: org.json.JSONObject) {
        kindBadge(col, "LESSON", 0xFFFFD60A.toInt())
        val head = p.optString("head")
        if (head.isNotEmpty()) col.addView(EfbUi.text(this, head, 16.5f, 0xFFFFD60A.toInt(), bold = true))

        // The points as the book sets them out: the marker in its own column, the words beside it,
        // and each level stepped in from the one above, so the shape of the lesson can be read.
        val plist = p.optJSONArray("plist")
        if (plist != null && plist.length() > 0) {
            for (i in 0 until plist.length()) {
                val o = plist.optJSONObject(i) ?: continue
                if (o.has("f")) {
                    // A figure where the page had it, between the words around it.
                    val k = o.optInt("f")
                    val figk = p.optJSONObject("figk")
                    figk?.keys()?.asSequence()?.firstOrNull { figk.optInt(it, -1) == k }?.let { nm ->
                        if (placed.add(nm)) figureView(col, nm)
                    }
                    continue
                }
                if (o.has("tb")) { o.optJSONArray("tb")?.let { tableView(col, it) }; continue }
                val d = o.optInt("d").coerceIn(0, 4)
                val m = o.optString("m")
                val t = o.optString("t")
                if (t.isBlank()) continue
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(dp(d * 15), dp(if (i == 0) 10 else 9), 0, 0)
                }
                if (m.isNotEmpty()) row.addView(
                    EfbUi.text(this, m, 13.5f, when (d) {
                        0 -> 0xFFFFD60A.toInt(); 1 -> 0xFF64D2FF.toInt(); else -> 0xFF8E9BA8.toInt()
                    }, bold = d == 0),
                    LinearLayout.LayoutParams(dp(if (d == 0) 24 else 26), -2))
                row.addView(EfbUi.text(this, t, if (d == 0) 15f else 14f,
                    if (d == 0) 0xFFFFFFFF.toInt() else 0xFFD3DAE2.toInt(), bold = d == 0),
                    LinearLayout.LayoutParams(0, -2, 1f))
                col.addView(row)
            }
            return
        }
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

    /**
     * A table from the page, set as a table: its rows and columns in words, sharp at any size,
     * numbers lined up on the right as the book prints them, and the rule under a figure kept.
     */
    private fun tableView(col: LinearLayout, rows: org.json.JSONArray) {
        if (rows.length() == 0) return
        // Columns with nothing in any row (the page's spacing cells) are left out.
        var cols = 0
        for (r in 0 until rows.length()) cols = maxOf(cols, rows.optJSONArray(r)?.length() ?: 0)
        val used = BooleanArray(cols); val numeric = BooleanArray(cols) { true }
        for (r in 0 until rows.length()) { val a = rows.optJSONArray(r) ?: continue
            for (c in 0 until a.length()) { val t = a.optJSONObject(c)?.optString("t").orEmpty()
                if (t.isNotEmpty()) { used[c] = true
                    if (r > 0 && !Regex("^[-−+?\$%.,()\\d\\s×x=]+\$").matches(t)) numeric[c] = false } } }
        val table = android.widget.TableLayout(this).apply { setPadding(dp(10), dp(8), dp(10), dp(8)) }
        for (r in 0 until rows.length()) { val a = rows.optJSONArray(r) ?: continue
            val tr = android.widget.TableRow(this)
            for (c in 0 until a.length()) { if (c >= cols || !used[c]) continue
                val cell = a.optJSONObject(c) ?: continue
                val head = r == 0 || cell.optInt("b") == 1
                val tv = EfbUi.text(this, cell.optString("t"), 14f,
                    if (r == 0) 0xFF64D2FF.toInt() else 0xFFE2E8EF.toInt(), bold = head).apply {
                    setPadding(dp(8), dp(3), dp(8), dp(3))
                    gravity = if (numeric[c] && c > 0) Gravity.END else Gravity.START
                    if (cell.optInt("u") == 1) paintFlags = paintFlags or android.graphics.Paint.UNDERLINE_TEXT_FLAG
                }
                tr.addView(tv)
            }
            table.addView(tr)
        }
        val box = android.widget.HorizontalScrollView(this).apply {
            addView(table)
            background = android.graphics.drawable.GradientDrawable().apply {
                setColor(0xFF161D25.toInt()); cornerRadius = dp(8).toFloat(); setStroke(dp(1), 0xFF2A3B4D.toInt()) }
        }
        col.addView(box, LinearLayout.LayoutParams(-1, -2).apply { setMargins(dp(24), dp(10), 0, dp(4)) })
    }

    /** Figures already set into the reading of the page being shown. */
    private val placed = HashSet<String>()

    /** One figure, inline, at the width of the page; a tap opens it to zoom. */
    private fun figureView(col: LinearLayout, name: String) {
        val f = java.io.File(java.io.File(filesDir, "studybook"), name)
        val bmp = (if (f.exists()) android.graphics.BitmapFactory.decodeFile(f.path) else null) ?: return
        col.addView(android.widget.ImageView(this).apply {
            setImageBitmap(bmp); adjustViewBounds = true
            scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
            background = EfbUi.cardBg(this@StudyBookReaderActivity, 0xFFFFFFFF.toInt(), 8)
            setPadding(dp(4), dp(4), dp(4), dp(4)); maxHeight = dp(420)
            setOnClickListener { zoomFigure(f) }
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10); bottomMargin = dp(4) })
    }

    /** The figure or table framed off the page, at the width of the book's page, on white. */
    private fun figure(col: LinearLayout, p: org.json.JSONObject) {
        val names = ArrayList<String>()
        p.optJSONArray("imgs")?.let { a -> for (i in 0 until a.length()) a.optString(i).takeIf { it.isNotEmpty() }?.let(names::add) }
        p.optString("img").takeIf { it.isNotEmpty() && it != "null" && !names.contains(it) }?.let(names::add)
        // Those already shown in their places in the reading are not shown again here.
        names.removeAll(placed)
        var first = true
        for (name in names) {
            val f = java.io.File(java.io.File(filesDir, "studybook"), name)
            if (!f.exists()) continue
            val bmp = android.graphics.BitmapFactory.decodeFile(f.path) ?: continue
            if (first) { label(col, if (names.size > 1) "FIGURES" else "FIGURE", 0xFFFF9F0A.toInt()); first = false }
            col.addView(android.widget.ImageView(this).apply {
                setImageBitmap(bmp)
                adjustViewBounds = true
                scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
                background = EfbUi.cardBg(this@StudyBookReaderActivity, 0xFFFFFFFF.toInt(), 8)
                setPadding(dp(4), dp(4), dp(4), dp(4))
                // A figure never swallows the page: tall ones are held to a readable height.
                maxHeight = dp(420)
                // A tap opens it on its own, full screen, to pinch and zoom into.
                setOnClickListener { zoomFigure(f) }
            }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        }
    }

    /** A figure full screen, on black, to pinch, zoom and pan; a tap on the ✕ or back closes it. */
    private fun zoomFigure(f: java.io.File) {
        val bmp = android.graphics.BitmapFactory.decodeFile(f.path) ?: return
        val dlg = android.app.Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val box = android.widget.FrameLayout(this).apply { setBackgroundColor(0xFF000000.toInt()) }
        box.addView(ZoomImageView(this).apply { setImageBitmap(bmp) }, android.widget.FrameLayout.LayoutParams(-1, -1))
        box.addView(android.widget.TextView(this).apply {
            text = "✕"; textSize = 22f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            background = EfbUi.cardBg(this@StudyBookReaderActivity, 0x99000000.toInt(), 24)
            setOnClickListener { dlg.dismiss() }
        }, android.widget.FrameLayout.LayoutParams(dp(48), dp(48), Gravity.TOP or Gravity.END).apply { setMargins(0, dp(28), dp(16), 0) })
        dlg.setContentView(box)
        dlg.show()
    }

    private var printWeb: android.webkit.WebView? = null

    /**
     * The whole book as a PDF: every page in the book's order, its unit and question, the choices with
     * the right one marked and why, the lesson points, the figures, and the pilot's own note — laid out
     * for paper and handed to the phone's printer, where "Save as PDF" keeps it.
     */
    private fun exportPdf() {
        save()
        fun e(x: String) = x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        val dir = java.io.File(filesDir, "studybook")
        val sb = StringBuilder()
        sb.append("<html><head><meta charset='utf-8'><style>body{font-family:sans-serif;font-size:11pt;color:#111;margin:18px}" +
            "h1{font-size:20pt;margin:0 0 4px}.pg{page-break-inside:avoid;border-top:1px solid #ccc;padding:10px 0}" +
            ".meta{color:#666;font-size:9pt}.q{font-weight:bold;margin:6px 0}.ch{margin:3px 0;padding:4px 8px;border-radius:6px;background:#f3f3f5}" +
            ".ok{background:#e3f4e8;font-weight:bold}.why{color:#2e6b40;font-size:10pt;margin-left:22px}.note{background:#fff7d6;padding:6px 8px;border-radius:6px;margin-top:6px}" +
            "img{max-width:100%;max-height:420px;display:block;margin:6px 0;border:1px solid #ddd}li{margin:2px 0}table.tb{border-collapse:collapse;margin:6px 0 6px 28px}table.tb td{padding:2px 10px}</style></head><body>")
        sb.append("<h1>Study book</h1><div class='meta'>${pages.length()} pages</div>")
        for (i in 0 until pages.length()) {
            val p = pages.optJSONObject(i) ?: continue
            val inlined = HashSet<String>()
            sb.append("<div class='pg'><div class='meta'>${e(listOf(p.optString("unit"), p.optString("sub"), p.optString("t")).filter { it.isNotEmpty() }.joinToString(" · "))}</div>")
            val head = p.optString("head")
            if (head.isNotEmpty()) sb.append("<div class='q'>${e(head)}</div>")
            if (p.optString("kind") == "qa") {
                val n = p.optString("n")
                sb.append("<div class='q'>${if (n.isNotEmpty()) "Q$n. " else ""}${e(p.optString("q"))}</div>")
                val ans = p.optString("ans")
                p.optJSONArray("ch")?.let { ch -> for (k in 0 until ch.length()) {
                    val o = ch.optJSONObject(k) ?: continue
                    val right = if (o.has("ok")) o.optBoolean("ok") else o.optString("l").equals(ans, true)
                    sb.append("<div class='ch${if (right) " ok" else ""}'>${e(o.optString("l"))}${if (right) " ✓" else ""} &nbsp; ${e(o.optString("t"))}</div>")
                    if (o.optString("why").isNotEmpty()) sb.append("<div class='why'>${if (right) "" else "✗ "}${e(o.optString("why"))}</div>")
                } }
                if (p.optString("why").isNotEmpty()) sb.append("<div class='why'>${e(p.optString("why"))}</div>")
            } else {
                val pl = p.optJSONArray("plist")
                if (pl != null && pl.length() > 0) {
                    sb.append("<ul>")
                    val fk = p.optJSONObject("figk")
                    for (k in 0 until pl.length()) pl.optJSONObject(k)?.let { o ->
                        if (o.has("f")) {
                            val nm = fk?.keys()?.asSequence()?.firstOrNull { fk.optInt(it, -1) == o.optInt("f") }
                            if (nm != null && java.io.File(dir, nm).exists()) { sb.append("</ul><img src='$nm'><ul>"); inlined.add(nm) }
                        } else if (o.has("tb")) {
                            sb.append("</ul><table class='tb'>")
                            val rs = o.optJSONArray("tb")
                            if (rs != null) for (r in 0 until rs.length()) { val a = rs.optJSONArray(r) ?: continue
                                sb.append("<tr>")
                                for (c in 0 until a.length()) { val cl = a.optJSONObject(c) ?: continue
                                    val st = (if (cl.optInt("u") == 1) "text-decoration:underline;" else "") + (if (r == 0 || cl.optInt("b") == 1) "font-weight:bold;" else "")
                                    sb.append("<td colspan='${cl.optInt("s", 1)}' style='$st'>${e(cl.optString("t"))}</td>") }
                                sb.append("</tr>") }
                            sb.append("</table><ul>")
                        } else sb.append("<li style='margin-left:${o.optInt("d") * 16}px'>${e(o.optString("m"))} ${e(o.optString("t"))}</li>")
                    }
                    sb.append("</ul>")
                } else p.optJSONArray("pts")?.let { a -> for (k in 0 until a.length()) sb.append("<p>${e(a.optString(k))}</p>") }
                    ?: sb.append("<p>${e(p.optString("q"))}</p>")
            }
            val names = ArrayList<String>()
            p.optJSONArray("imgs")?.let { a -> for (k in 0 until a.length()) a.optString(k).takeIf { it.isNotEmpty() }?.let(names::add) }
            p.optString("img").takeIf { it.isNotEmpty() && it != "null" && !names.contains(it) }?.let(names::add)
            for (nm in names) if (nm !in inlined && java.io.File(dir, nm).exists()) sb.append("<img src='$nm'>")
            if (p.optString("e").isNotBlank()) sb.append("<div class='note'><b>My note:</b> ${e(p.optString("e"))}</div>")
            sb.append("</div>")
        }
        sb.append("</body></html>")
        val web = android.webkit.WebView(this)
        web.settings.allowFileAccess = true
        web.webViewClient = object : android.webkit.WebViewClient() {
            override fun onPageFinished(v: android.webkit.WebView, url: String) {
                getSystemService(android.print.PrintManager::class.java).print("Study book",
                    v.createPrintDocumentAdapter("Study book"),
                    android.print.PrintAttributes.Builder().setMediaSize(android.print.PrintAttributes.MediaSize.ISO_A4).build())
            }
        }
        web.loadDataWithBaseURL("file://" + dir.absolutePath + "/", sb.toString(), "text/html", "utf-8", null)
        printWeb = web
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
        // The chapters in the order the book is in, so the contents read the way the pages do.
        val byChapter = LinkedHashMap<String, MutableList<Int>>()
        for (i in 0 until pages.length()) {
            val p = pages.optJSONObject(i) ?: continue
            byChapter.getOrPut(chapterOf(p)) { ArrayList() }.add(i)
        }
        for ((topic, list) in byChapter) {
            box.addView(EfbUi.text(this, "$topic   ·   ${list.size}", 12.5f, 0xFFFFD60A.toInt(), bold = true)
                .apply { setBackgroundColor(0xFF1A222B.toInt()); setPadding(dp(16), dp(8), dp(16), dp(8)) })
            for (i in list) {
                val p = pages.optJSONObject(i) ?: continue
                val mark = if ((p.optJSONArray("ink")?.length() ?: 0) > 0) "  ✎" else ""
                val figure = if (p.optString("img").let { it.isNotEmpty() && it != "null" } ||
                    (p.optJSONArray("imgs")?.length() ?: 0) > 0) "  🖼" else ""
                val sub = p.optString("sub").let { s2 -> RE_SUB_NO.find(s2)?.let { "§${it.groupValues[1]}  " } ?: "" }
                val kind = if (p.optString("kind") == "qa") "❓ " else "📖 "
                box.addView(EfbUi.text(this, "${i + 1}.  $kind$sub${p.optString("q").replace("\n", " ").take(60)}$mark$figure",
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
        val auto = prefs.getBoolean(KEY_AUTO, true)
        items.add((if (auto) "✓  Automatic order — unit, subunit, question" else "    Automatic order — unit, subunit, question") to {
            prefs.edit().putBoolean(KEY_AUTO, !auto).apply()
            if (!auto) { autoSort(); save(); paint(); Toast.makeText(this, "The book has put itself in order", Toast.LENGTH_SHORT).show() }
            else Toast.makeText(this, "Order is yours now — move pages as you like", Toast.LENGTH_SHORT).show()
        })
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
        // Moving a page by hand is the pilot saying the order is theirs, so the book stops sorting.
        if (prefs.getBoolean(KEY_AUTO, true)) {
            prefs.edit().putBoolean(KEY_AUTO, false).apply()
            Toast.makeText(this, "Automatic order off — the order is yours now", Toast.LENGTH_SHORT).show()
        }
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
        private const val KEY_AUTO = "study_book_auto"
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
