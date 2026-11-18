package com.saudi.privatevault

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import org.json.JSONArray
import org.json.JSONObject

/**
 * The study book: a place to read a question bank on the web and keep what matters from it.
 *
 * The page you were last on comes back when you return, signed in as you left it. Highlight a
 * question, press Capture, write your own explanation under it in your own words, and it becomes a
 * page of your book — filed by itself under the subject it is about.
 *
 * The book reads one page at a time, and where a page is about something the app can show you
 * flying — a stall, a steep turn, a short field landing — it offers the animated maneuver and the
 * handbook to go with it, so the explanation is never only words.
 */
class StudyBookActivity : BaseActivity() {
    override val alwaysDark = true

    private lateinit var web: WebView
    private lateinit var clipper: ClipFrame
    private lateinit var pad: LinearLayout
    /** The picture taken for the page being written, if one has been taken. */
    private var clipFile: String? = null
    private var clipRow: LinearLayout? = null
    private lateinit var question: EditText
    private lateinit var mine: EditText
    private val prefs by lazy { VaultLock.prefs(this) }
    private fun dp(v: Int) = EfbUi.dp(this, v)

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = 0xFF0F141A.toInt()
        window.navigationBarColor = 0xFF0F141A.toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF0F141A.toInt())
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }

        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0xFF1B222C.toInt()); setPadding(dp(6), dp(7), dp(8), dp(7))
        }
        head.addView(chip("‹", 0xFF2A3B4D.toInt()) { if (web.canGoBack()) web.goBack() else finish() },
            LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        head.addView(EfbUi.text(this, "STUDY BOOK", 14f, 0xFFFFFFFF.toInt(), bold = true).apply { gravity = Gravity.CENTER },
            LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(chip("🌐", 0xFF2A3B4D.toInt()) { askSite() },
            LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        head.addView(chip("📖 Book", 0xFF8E5CF7.toInt()) { readBook() })
        root.addView(head)

        clipper = ClipFrame(this)
        web = WebView(this)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            useWideViewPort = true
            loadWithOverviewMode = true
            setSupportZoom(true); builtInZoomControls = true; displayZoomControls = false
        }
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true)
        web.webViewClient = object : WebViewClient() {
            override fun onPageFinished(v: WebView?, url: String?) {
                if (!url.isNullOrEmpty()) prefs.edit().putString("study_last_url", url).apply()
            }
        }
        clipper.addView(web, android.widget.FrameLayout.LayoutParams(-1, -1))
        root.addView(clipper, LinearLayout.LayoutParams(-1, 0, 0.58f))

        val tools = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xFF161D25.toInt()); setPadding(dp(8), dp(7), dp(8), dp(7))
        }
        tools.addView(chip("📋  Text", 0xFF2D7FF9.toInt()) { capture() },
            LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        tools.addView(chip("📷  Figure", 0xFFFF9F0A.toInt()) { startClip() },
            LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        tools.addView(chip("➕  Add as a page", 0xFF30D158.toInt()) { addPage() },
            LinearLayout.LayoutParams(0, -2, 1f))
        root.addView(tools)

        pad = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF121820.toInt()); setPadding(dp(10), dp(8), dp(10), dp(10))
        }
        question = box("The question, as you highlighted it", 0xFFFFFFFF.toInt())
        mine = box("Your own explanation — why this answer, and what to remember", 0xFFA5D6A7.toInt())
        pad.addView(question, LinearLayout.LayoutParams(-1, 0, 1f))
        pad.addView(mine, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(7) })
        root.addView(pad, LinearLayout.LayoutParams(-1, 0, 0.42f))

        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            root.setPadding(0, bars.top, 0, bars.bottom); ins
        }
        web.loadUrl(prefs.getString("study_last_url", HOME) ?: HOME)
    }

    private fun chip(label: String, colour: Int, go: () -> Unit) = TextView(this).apply {
        text = label; textSize = 12.5f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
        typeface = EfbUi.MEDIUM
        background = EfbUi.cardBg(this@StudyBookActivity, colour, 9)
        setPadding(dp(11), dp(8), dp(11), dp(8))
        setOnClickListener { go() }
    }

    private fun box(hint: String, ink: Int) = EditText(this).apply {
        this.hint = hint
        textSize = 13.5f
        setTextColor(ink); setHintTextColor(0xFF6E7681.toInt())
        background = EfbUi.cardBg(this@StudyBookActivity, 0xFF1E242C.toInt(), 9)
        setPadding(dp(10), dp(9), dp(10), dp(9))
        gravity = Gravity.TOP or Gravity.START
        inputType = android.text.InputType.TYPE_CLASS_TEXT or
            android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
    }

    /**
     * A figure or a table cannot be highlighted: selecting text leaves the picture behind, and the
     * light-gun signal table, the airspace diagram and every chart excerpt are exactly the things
     * worth keeping. So they are taken as a picture instead — frame the part of the page that
     * matters by dragging a box over it, and that rectangle is cut out and kept with the note.
     */
    private fun startClip() {
        Toast.makeText(this, "Drag a box over the figure or the table", Toast.LENGTH_SHORT).show()
        clipper.arm { l, t, w, h -> takeClip(l, t, w, h) }
    }

    private fun takeClip(l: Int, t: Int, w: Int, h: Int) {
        if (w < 24 || h < 24) { Toast.makeText(this, "Too small — drag a bigger box", Toast.LENGTH_SHORT).show(); return }
        try {
            val full = android.graphics.Bitmap.createBitmap(
                web.width.coerceAtLeast(1), web.height.coerceAtLeast(1), android.graphics.Bitmap.Config.ARGB_8888)
            web.draw(android.graphics.Canvas(full))
            val x = l.coerceIn(0, full.width - 1)
            val y = t.coerceIn(0, full.height - 1)
            val cw = w.coerceAtMost(full.width - x)
            val ch = h.coerceAtMost(full.height - y)
            val cut = android.graphics.Bitmap.createBitmap(full, x, y, cw, ch)
            full.recycle()
            val dir = java.io.File(filesDir, "studybook")
            dir.mkdirs()
            val out = java.io.File(dir, "clip_" + System.currentTimeMillis() + ".png")
            out.outputStream().use { cut.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
            cut.recycle()
            clipFile = out.name
            showClip()
            Toast.makeText(this, "Figure kept — now press Add as a page", Toast.LENGTH_SHORT).show()
        } catch (e: Throwable) {
            Toast.makeText(this, "Could not take that picture", Toast.LENGTH_SHORT).show()
        }
    }

    /** The picture waiting to go onto the page, with the way to drop it again. */
    private fun showClip() {
        clipRow?.let { (it.parent as? android.view.ViewGroup)?.removeView(it) }
        clipRow = null
        val name = clipFile ?: return
        val f = java.io.File(java.io.File(filesDir, "studybook"), name)
        if (!f.exists()) { clipFile = null; return }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0xFF1B222C.toInt()); setPadding(dp(8), dp(6), dp(8), dp(6))
        }
        row.addView(android.widget.ImageView(this).apply {
            setImageBitmap(android.graphics.BitmapFactory.decodeFile(f.path))
            adjustViewBounds = true
            scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
        }, LinearLayout.LayoutParams(dp(90), dp(56)).apply { marginEnd = dp(10) })
        row.addView(EfbUi.text(this, "🖼  a figure is kept for this page", 12.5f, 0xFFFFD60A.toInt()),
            LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(chip("✕", 0xFF3A2A2A.toInt()) { f.delete(); clipFile = null; showClip() })
        pad.addView(row, 0)
        clipRow = row
    }

    /** Whatever is highlighted up in the page, brought down into the box. */
    private fun capture() {
        web.evaluateJavascript("(function(){return window.getSelection().toString();})()") { raw ->
            val text = (raw ?: "").trim().removeSurrounding("\"")
                .replace("\\n", "\n").replace("\\t", " ").replace("\\\"", "\"").trim()
            if (text.isEmpty()) {
                Toast.makeText(this, "Highlight the question up in the page first", Toast.LENGTH_SHORT).show()
            } else {
                question.setText(text)
                Toast.makeText(this, "Captured", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun askSite() {
        val e = EditText(this).apply {
            setText(prefs.getString("study_last_url", HOME)); setSingleLine()
            inputType = android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        MaterialAlertDialogBuilder(this).setTitle("Open a page").setView(e)
            .setPositiveButton(R.string.ok) { _, _ ->
                var u = e.text.toString().trim()
                if (u.isNotEmpty()) {
                    if (!u.startsWith("http")) u = "https://$u"
                    web.loadUrl(u)
                }
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    private fun addPage() {
        val q = question.text.toString().trim()
        if (q.isEmpty() && clipFile == null) {
            Toast.makeText(this, "Nothing for a page yet — capture some text or a figure", Toast.LENGTH_SHORT).show(); return
        }
        val topic = topicOf(q + " " + mine.text.toString())
        val pages = load()
        pages.put(JSONObject()
            .put("q", q.ifEmpty { "(a figure)" })
            .put("e", mine.text.toString().trim())
            .put("img", clipFile ?: JSONObject.NULL)
            .put("t", topic)
            .put("u", prefs.getString("study_last_url", "") ?: "")
            .put("at", System.currentTimeMillis()))
        prefs.edit().putString(KEY, pages.toString()).apply()
        question.setText(""); mine.setText("")
        clipFile = null; showClip()
        Toast.makeText(this, "Page ${pages.length()} · filed under $topic", Toast.LENGTH_SHORT).show()
    }

    private fun load(): JSONArray =
        try { JSONArray(prefs.getString(KEY, "[]")) } catch (e: Exception) { JSONArray() }

    // ---- the book ----

    private fun readBook() {
        if (load().length() == 0) {
            MaterialAlertDialogBuilder(this).setTitle("\ud83d\udcd6 The book is empty")
                .setMessage("Highlight a question in the page above, press Capture, write your explanation under it, " +
                    "and press Add as a page. Every page you add is kept in the book, filed by subject, and can be " +
                    "drawn on in colour and put in whatever order you want to read it in.")
                .setPositiveButton(R.string.ok, null).show()
            return
        }
        StudyBookReaderActivity.open(this)
    }

    companion object {
        private const val KEY = "study_book_pages"
        private const val KEY_AT = "study_book_at"
        private const val HOME = "https://www.gleim.com/aviation/"

        fun open(ctx: Context) = ctx.startActivity(Intent(ctx, StudyBookActivity::class.java))

        /** What a question is about, read off the words in it, so the book files itself. */
        fun topicOf(text: String): String {
            val t = text.lowercase()
            fun any(vararg w: String) = w.any { t.contains(it) }
            return when {
                any("stall", "spin", "slow flight", "angle of attack") -> "STALLS"
                any("crosswind", "wind correction", "slip", "gust") -> "CROSSWIND"
                any("takeoff", "take-off", "landing", "go-around", "go around", "flare", "short-field", "soft-field") -> "TAKEOFF & LANDING"
                any("traffic pattern", "downwind", "base leg", "ctaf", "unicom", "tower", "light signal") -> "PATTERN & RADIO"
                any("airspace", "class b", "class c", "class d", "class e", "class g", "tfr", "moa", "vfr minimum") -> "AIRSPACE"
                any("metar", "taf", "weather", "front", "fog", "icing", "thunderstorm", "turbulence", "airmet", "sigmet") -> "WEATHER"
                any("vor", "radial", "gps", "dme", "heading", "course", "navigation", "pilotage", "dead reckoning") -> "NAVIGATION"
                any("weight", "balance", "cg", "center of gravity", "moment", "arm", "load factor") -> "WEIGHT & BALANCE"
                any("density altitude", "performance", "takeoff distance", "climb rate", "koch") -> "PERFORMANCE"
                any("engine", "carburetor", "magneto", "oil", "fuel", "propeller", "alternator", "electrical") -> "SYSTEMS"
                any("61.", "91.", "far ", "regulation", "medical", "logbook", "currency", "endorsement") -> "REGULATIONS"
                any("emergency", "fire", "failure", "ditching", "forced landing", "121.5", "7700") -> "EMERGENCIES"
                any("hypoxia", "vertigo", "illusion", "aeromedical", "scuba", "carbon monoxide") -> "AEROMEDICAL"
                else -> "GENERAL"
            }
        }

        /** The animated maneuver that belongs with a subject, where there is one. */
        fun maneuverFor(topic: String): String? = when (topic) {
            "STALLS" -> "slow"
            "CROSSWIND" -> "xwind_ldg"
            "TAKEOFF & LANDING" -> "normal_ldg"
            "PATTERN & RADIO" -> "pattern"
            "EMERGENCIES" -> "emer"
            "PERFORMANCE" -> "short_to"
            else -> null
        }
    }
}
