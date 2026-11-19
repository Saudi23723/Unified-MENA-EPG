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
    /** Every figure and table found on the page and copied off it. */
    private val figures = ArrayList<String>()
    private var clipRow: LinearLayout? = null
    /** What was read off the page, in the shape the page had it in. */
    private var pending: JSONObject? = null
    private var pendRow: LinearLayout? = null
    private lateinit var question: EditText
    private lateinit var mine: EditText
    private val prefs by lazy { VaultLock.prefs(this) }
    private fun dp(v: Int) = EfbUi.dp(this, v)

    /** The phone's own back steps back through the page, and leaves once there is nowhere back to. */
    @Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }

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
        // ‹ leaves the study book. The bank opens an image viewer as another page in its own
        // history, so a back button that only steps back through that history can never get out
        // of it — which is what happened. Stepping back inside the page has its own button.
        head.addView(chip("‹", 0xFF2A3B4D.toInt()) { finish() },
            LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        head.addView(chip("↶", 0xFF2A3B4D.toInt()) { if (web.canGoBack()) web.goBack() else finish() },
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
        tools.addView(chip("📋  Capture page", 0xFF2D7FF9.toInt()) { capture() },
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
        clipper.arm { l, t, w, h -> takeClip(l, t, w, h) }
    }

    private fun takeClip(l: Int, t: Int, w: Int, h: Int) {
        if (w < 24 || h < 24) { Toast.makeText(this, "Too small — drag a bigger box", Toast.LENGTH_SHORT).show(); return }
        try {
            val full = pageShot() ?: run { Toast.makeText(this, "Could not take that picture", Toast.LENGTH_SHORT).show(); return }
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
            confirmClip(out)
        } catch (e: Throwable) {
            Toast.makeText(this, "Could not take that picture", Toast.LENGTH_SHORT).show()
        }
    }

    private fun dropFigures() {
        for (n in figures) java.io.File(java.io.File(filesDir, "studybook"), n).delete()
        figures.clear()
    }

    /** The cut shown at the size it really is, to keep or to take again. */
    private fun confirmClip(out: java.io.File) {
        val bmp = android.graphics.BitmapFactory.decodeFile(out.path)
        if (bmp == null) { out.delete(); Toast.makeText(this, "Could not take that picture", Toast.LENGTH_SHORT).show(); return }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(EfbUi.BG); setPadding(dp(14), dp(14), dp(14), dp(4))
        }
        box.addView(EfbUi.text(this, "%d × %d".format(bmp.width, bmp.height), 11.5f, 0xFF8E9BA8.toInt()))
        box.addView(android.widget.ImageView(this).apply {
            setImageBitmap(bmp)
            adjustViewBounds = true
            scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
            background = EfbUi.cardBg(this@StudyBookActivity, 0xFFFFFFFF.toInt(), 8)
            setPadding(dp(4), dp(4), dp(4), dp(4))
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        MaterialAlertDialogBuilder(this).setView(ScrollView(this).apply { addView(box) })
            .setPositiveButton("Keep it") { _, _ ->
                clipFile?.let { old -> java.io.File(java.io.File(filesDir, "studybook"), old).delete() }
                clipFile = out.name
                showClip()
            }
            .setNeutralButton("Try again") { _, _ -> out.delete(); startClip() }
            .setNegativeButton(R.string.cancel) { _, _ -> out.delete() }
            .show()
    }

    /** The picture waiting to go onto the page, with the way to drop it again. */
    private fun showClip() {
        clipRow?.let { (it.parent as? android.view.ViewGroup)?.removeView(it) }
        clipRow = null
        val name = clipFile ?: return
        val f = java.io.File(java.io.File(filesDir, "studybook"), name)
        if (!f.exists()) { clipFile = null; return }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xFF1B222C.toInt()); setPadding(dp(8), dp(6), dp(8), dp(8))
        }
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(EfbUi.text(this, "🖼  figure for this page", 12.5f, 0xFFFFD60A.toInt(), bold = true),
            LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(chip("✕", 0xFF3A2A2A.toInt()) { f.delete(); clipFile = null; showClip() })
        row.addView(head)
        row.addView(android.widget.ImageView(this).apply {
            setImageBitmap(android.graphics.BitmapFactory.decodeFile(f.path))
            adjustViewBounds = true
            scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
            background = EfbUi.cardBg(this@StudyBookActivity, 0xFFFFFFFF.toInt(), 6)
            setPadding(dp(3), dp(3), dp(3), dp(3))
            maxHeight = dp(150)
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) })
        pad.addView(row, 0)
        clipRow = row
    }

    /**
     * The page read as it stands, with nothing to highlight first. Whatever is selected is used if
     * anything is; otherwise the whole page is taken, and either way it is read into its own shape
     * — a question with its choices and its answer, or a passage of the book — so the book can set
     * it out properly instead of keeping a block of prose.
     */
    private fun capture() {
        // The page is asked for two things at once: everything it says, and where every picture,
        // table, drawing and chart on it sits. Nothing has to be highlighted and no box has to be
        // dragged — a lesson page is taken whole, the words read into their shape and every figure
        // on it copied off it as it stands.
        val js = """(function(){
            // Tables are NOT skipped. This bank lays the question, its choices and the answer's
            // explanation inside tables, so walking past every table threw away the very thing
            // being captured and left only the numbers down the side of the page.
            var SKIP = {script:1,style:1,button:1,input:1,select:1,textarea:1,noscript:1,svg:1};
            var JUNK = {'Back':1,'Forward':1,'Contents':1,'Print':1,'Done':1,'Hide':1,'Next':1,'Previous':1,
                        'Grade':1,'Discard':1,'Pause':1,'Calculator':1,'Question Properties':1,'Image Viewer':1,
                        'Session Tools':1,'Tools':1,'Session':1,'Mark For Review':1,'How Can We Help?':1,
                        'Main Page':1,'Personal Classroom':1,'Logout':1,'Question Filters':1,'Unanswered':1,
                        'Marked':1,'Incorrect':1,'No filters enabled':1,'Study Session':1,'Questions:':1,
                        'Correct First Try':1,'Currently Correct':1,'Contact Gleim':1,'Opens in new window':1,
                        'Skip to Main Content':1,'eBook':1,'Private Pilot':1,'Study Unit':1,'Subunit':1,
                        'ACS Code:':1,'Question':1,'Study Session':1,'Image Viewer':1,
                        'Privacy Policy':1,'Employment':1,'Terms and Conditions of Service':1};
            var out = [];
            var pts = [];
            // Only what the page actually shows: a bank's page carries directions, skip links,
            // spacers and an index of every question in it, none of it ever on the screen.
            function shown(el){
                if (!el.getClientRects || el.getClientRects().length === 0) return false;
                if (el.getAttribute && el.getAttribute('aria-hidden') === 'true') return false;
                var st = window.getComputedStyle ? window.getComputedStyle(el) : null;
                if (!st) return true;
                if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
                return true;
            }
            // A point keeps three things: how deep it sits, its marker, and its words. The depth
            // is what the book needs to set it out as a book does — the marker alone, flattened to
            // the left margin, reads as a jumble of letters and numbers with no shape to it.
            function push(t, depth, marker){
                t = (t || '').replace(/\s+/g, ' ').replace(/\s*\|\s*/g, ' ').trim();
                if (!t || JUNK[t]) return;
                if (/^(Copyright|Terms and Conditions|Phone:|Fax:|Elapsed Time|Average Time|©)/.test(t)) return;
                if (/^\(?\d{3}\)?[ -]?\d{3}-\d{4}$/.test(t)) return;
                if (/^Source(\s+\d+)+$/.test(t)) return;
                if (/^\d+\s*\(\d+\.\d+\.\d+\)$/.test(t)) return;
                if (t.length < 2) return;
                pts.push({ d: depth || 0, m: marker || '', t: t });
                out.push((marker ? marker + ' ' : '') + t);
            }
            // A list keeps its shape: 1. then a. then i., each one step in, as the book prints it.
            function mark(depth, n){
                if (depth === 0) return n + '.';
                if (depth === 1) return String.fromCharCode(96 + ((n - 1) % 26) + 1) + '.';
                var r = ['i','ii','iii','iv','v','vi','vii','viii','ix','x'];
                return (r[n - 1] || n) + '.';
            }

            function list(el, depth){
                var ordered = el.tagName.toLowerCase() === 'ol';
                // A long list whose items are bare numbers is the index of the bank's questions
                // running down the side of the page, not anything the lesson says.
                var kids = 0, bare = 0;
                for (var q = 0; q < el.children.length; q++){
                    var li0 = el.children[q];
                    if (li0.tagName.toLowerCase() !== 'li') continue;
                    kids++;
                    var t0 = (li0.innerText || '').trim();
                    if (t0.length <= 6 && /^[\d.\s()]*$/.test(t0)) bare++;
                }
                if (kids >= 12 && bare * 2 >= kids) return;
                var n = 1;
                for (var i = 0; i < el.children.length; i++){
                    var li = el.children[i];
                    if (li.tagName.toLowerCase() !== 'li' || !shown(li)) continue;
                    var own = '';
                    for (var k = 0; k < li.childNodes.length; k++){
                        var c = li.childNodes[k];
                        if (c.nodeType === 3) own += c.textContent + ' ';
                        else if (c.nodeType === 1){
                            var ct = c.tagName.toLowerCase();
                            if (ct === 'ol' || ct === 'ul' || ct === 'table' || SKIP[ct]) continue;
                            if (!shown(c)) continue;
                            own += (c.innerText || '') + ' ';
                        }
                    }
                    push(own, depth, ordered ? mark(depth, n++) : '•');
                    for (var k = 0; k < li.children.length; k++){
                        var c = li.children[k];
                        var ct = c.tagName.toLowerCase();
                        if ((ct === 'ol' || ct === 'ul') && shown(c)) list(c, depth + 1);
                    }
                }
            }
            function dataTable(t){
                if (t.querySelector('table,input,button,select,textarea,iframe,form')) return false;
                var rows = t.rows ? t.rows.length : 0;
                if (rows < 3) return false;
                // A grid, not a box of prose: three columns across as well as three rows down, and short
                // entries in them. The box a question and its choices sit in is two columns of paragraphs,
                // and it belongs in the words, not in the pictures.
                var cols = 0, cells = t.querySelectorAll('td,th'), total = 0;
                for (var i = 0; i < rows; i++) if (t.rows[i].cells.length > cols) cols = t.rows[i].cells.length;
                if (cols < 3 || cells.length < 9) return false;
                for (var i = 0; i < cells.length; i++) total += (cells[i].innerText || '').length;
                if (total / cells.length > 90) return false;
                var im = t.querySelectorAll('img');
                for (var i = 0; i < im.length; i++){
                    var ir = im[i].getBoundingClientRect();
                    if (ir.width > 120 || ir.height > 90) return false;
                }
                return true;
            }
            function walk(el){
                var tag = el.tagName ? el.tagName.toLowerCase() : '';
                if (SKIP[tag]) return;
                // A table of data is kept as a picture, so its text is not written out as well.
                if (tag === 'table' && dataTable(el)) return;
                if (!shown(el)) return;
                if (out.length > 500) return;
                // The list of every question in the bank sits beside the lesson. On the screen each
                // entry reads "5 (3.7.69)", but the text behind it reads "Question" and then
                // "Source 3 7 69" with no brackets at all — so looking for the bracketed form alone
                // let the whole index through. Either form, half a dozen times over in one box,
                // means that box is the index and not the lesson.
                if (el.children && el.children.length > 0){
                    var it = el.innerText || '';
                    if (it.length < 20000 &&
                        (((it.match(/\(\d+\.\d+\.\d+\)/g) || []).length >= 6) ||
                         ((it.match(/Source\s+\d+\s+\d+\s+\d+/g) || []).length >= 4) ||
                         ((it.match(/\bQuestion\b/g) || []).length >= 8))) return;
                }
                if (tag === 'ol' || tag === 'ul'){ list(el, 0); return; }
                if (!el.children || el.children.length === 0){ push(el.innerText || el.textContent, 0, ''); return; }
                for (var k = 0; k < el.childNodes.length; k++){
                    var c = el.childNodes[k];
                    if (c.nodeType === 3) push(c.textContent, 0, '');
                    else if (c.nodeType === 1) walk(c);
                }
            }
            var sel = window.getSelection().toString();
            if (sel && sel.trim().length > 20) out.push(sel);
            else if (document.body) walk(document.body);

            // A table of data is a figure. A table used to lay the page out is not: this bank is
            // built out of those, and one of them wraps the toolbar and the top of the lesson —
            // which is the picture that kept coming back instead of the diagram.
            function dataTable(t){
                if (t.querySelector('table,input,button,select,textarea,iframe,form')) return false;
                var rows = t.rows ? t.rows.length : 0;
                if (rows < 3) return false;
                // A grid, not a box of prose: three columns across as well as three rows down, and short
                // entries in them. The box a question and its choices sit in is two columns of paragraphs,
                // and it belongs in the words, not in the pictures.
                var cols = 0, cells = t.querySelectorAll('td,th'), total = 0;
                for (var i = 0; i < rows; i++) if (t.rows[i].cells.length > cols) cols = t.rows[i].cells.length;
                if (cols < 3 || cells.length < 9) return false;
                for (var i = 0; i < cells.length; i++) total += (cells[i].innerText || '').length;
                if (total / cells.length > 90) return false;
                var im = t.querySelectorAll('img');
                for (var i = 0; i < im.length; i++){
                    var ir = im[i].getBoundingClientRect();
                    if (ir.width > 120 || ir.height > 90) return false;
                }
                return true;
            }
            var vw = window.innerWidth || 1, vh = window.innerHeight || 1;
            var sy = window.pageYOffset || document.documentElement.scrollTop || 0;
            var res = { text: out.join('\n').slice(0, 20000), pts: pts.slice(0, 400), vw: vw, vh: vh,
                        scrollY: sy, docH: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
                        figs: [] };
            var els = document.querySelectorAll('img,table,svg,canvas');
            for (var i = 0; i < els.length; i++){
                var e = els[i];
                if (!shown(e)) continue;
                var r = e.getBoundingClientRect();
                if (r.width < 90 || r.height < 60) continue;
                if (e.tagName.toLowerCase() === 'table' && !dataTable(e)) continue;
                // Where it sits on the whole page, not just on the screen, so it can be scrolled to.
                res.figs.push({ x: r.left / vw, y: (r.top + sy), w: r.width / vw, h: r.height, ch: r.height / vh });
                if (res.figs.length >= 10) break;
            }
            return JSON.stringify(res);
        })()"""
        web.evaluateJavascript(js) { raw ->
            val o = try { JSONObject(unJs(raw)) } catch (e: Exception) { null }
            val text = o?.optString("text").orEmpty()
            if (text.isBlank()) {
                Toast.makeText(this, "Nothing on this page to read", Toast.LENGTH_SHORT).show()
                return@evaluateJavascript
            }
            // The page's own Copy / Share bar is left standing by a selection; put it away.
            web.evaluateJavascript("window.getSelection().removeAllRanges();", null)
            web.clearFocus()
            // A fresh capture starts with nothing of the last one still attached to it: without
            // this, taking one page and then another without keeping the first gave the second
            // page the first page's figures as well.
            dropFigures()
            val parsed = StudyParse.parse(text)
            // A lesson keeps the shape the page had it in, each point with its depth and marker.
            if (parsed.optString("kind") != "qa") o?.optJSONArray("pts")?.let { parsed.put("plist", it) }
            pending = parsed
            question.setText(if (parsed.optString("kind") == "qa") parsed.optString("q")
                else parsed.optString("head").ifEmpty { parsed.optString("q") })
            showPending()
            grabFigures(o) { n ->
                showPending()
                Toast.makeText(this, StudyParse.describe(parsed) +
                    (if (n > 0) " · $n figure" + (if (n > 1) "s" else "") else ""),
                    Toast.LENGTH_LONG).show()
            }
        }
    }

    /**
     * A picture of the page as it is on the screen.
     *
     * A WebView draws itself on the graphics card, and a view drawn that way hands back an empty
     * canvas when it is asked to draw into one — which is why figures came back as blank grey
     * boxes. Asked to draw itself in software for the moment it takes, it hands back what is
     * really there.
     */
    private fun pageShot(): android.graphics.Bitmap? = try {
        val was = web.layerType
        web.setLayerType(android.view.View.LAYER_TYPE_SOFTWARE, null)
        val bmp = android.graphics.Bitmap.createBitmap(
            web.width.coerceAtLeast(1), web.height.coerceAtLeast(1), android.graphics.Bitmap.Config.ARGB_8888)
        web.draw(android.graphics.Canvas(bmp))
        web.setLayerType(was, null)
        bmp
    } catch (e: Throwable) { null }

    /** The JavaScript that finds the figures and brings one of them, by number, into reach. */
    private fun figureJs(i: Int) = """(function(idx){
        function shown(el){
            if (!el.getClientRects || el.getClientRects().length === 0) return false;
            if (el.getAttribute && el.getAttribute('aria-hidden') === 'true') return false;
            var st = window.getComputedStyle ? window.getComputedStyle(el) : null;
            if (!st) return true;
            return !(st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0');
        }
        function dataTable(t){
            if (t.querySelector('table,input,button,select,textarea,iframe,form')) return false;
            var rows = t.rows ? t.rows.length : 0;
            if (rows < 3) return false;
            // A grid, not a box of prose: three columns across as well as three rows down, and short
            // entries in them. The box a question and its choices sit in is two columns of paragraphs,
            // and it belongs in the words, not in the pictures.
            var cols = 0, cells = t.querySelectorAll('td,th'), total = 0;
            for (var i = 0; i < rows; i++) if (t.rows[i].cells.length > cols) cols = t.rows[i].cells.length;
            if (cols < 3 || cells.length < 9) return false;
            for (var i = 0; i < cells.length; i++) total += (cells[i].innerText || '').length;
            if (total / cells.length > 90) return false;
            var im = t.querySelectorAll('img');
            for (var i = 0; i < im.length; i++){
                var ir = im[i].getBoundingClientRect();
                if (ir.width > 120 || ir.height > 90) return false;
            }
            return true;
        }
        var all = document.querySelectorAll('img,table,svg,canvas');
        var list = [];
        for (var k = 0; k < all.length; k++){
            var e = all[k];
            if (!shown(e)) continue;
            var r = e.getBoundingClientRect();
            var tg = e.tagName.toLowerCase();
            // A figure beside a question can be a small thumbnail; a table has to be a real one.
            if (tg === 'img' || tg === 'svg' || tg === 'canvas'){ if (r.width < 60 || r.height < 45) continue; }
            else if (r.width < 120 || r.height < 70) continue;
            if (tg === 'table' && !dataTable(e)) continue;
            list.push(e);
            if (list.length >= 10) break;
        }
        if (idx >= list.length) return JSON.stringify({ n: list.length, done: true });
        var e = list[idx];
        // Brings it into view through whatever scrolls it — the window, or a box inside the page
        // with a scrollbar of its own, which is how this bank lays its lessons out.
        // Straight there, not gliding: a page that scrolls smoothly would still be moving when it
        // was measured, and the rectangle would point at whatever was passing.
        try { e.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' }); }
        catch (x) { try { e.scrollIntoView(); } catch (y) {} }
        // A picture can be copied exactly, pixel for pixel, with no cutting out at all.
        var data = '';
        if (e.tagName.toLowerCase() === 'img'){
            try {
                var c = document.createElement('canvas');
                c.width = e.naturalWidth || e.width; c.height = e.naturalHeight || e.height;
                if (c.width > 8 && c.height > 8){
                    c.getContext('2d').drawImage(e, 0, 0, c.width, c.height);
                    data = c.toDataURL('image/png');
                }
            } catch (x) { data = ''; }
        }
        var r2 = e.getBoundingClientRect();
        var vw = window.innerWidth || 1, vh = window.innerHeight || 1;
        return JSON.stringify({ n: list.length, x: r2.left / vw, y: r2.top / vh,
                                w: r2.width / vw, h: r2.height / vh, data: data });
    })($i)"""

    /**
     * Every figure on the page, copied off it one at a time.
     *
     * A picture is copied exactly — the page draws it into a canvas of its own and hands back the
     * pixels, so there is no cutting out and nothing to line up. A table has no such trick, so the
     * page brings it into view through whatever scrolls it, says where it is on the screen now,
     * and that rectangle is cut from a drawing of the screen. Asking the page to scroll is what
     * makes this work at all: the lesson sits in a box with a scrollbar of its own, and scrolling
     * the window outside it moves nothing, which is why the figures came back blank.
     */
    private fun grabFigures(o: JSONObject?, done: (Int) -> Unit) {
        val dir = java.io.File(filesDir, "studybook")
        dir.mkdirs()
        var made = 0
        fun step(i: Int) {
            if (i >= 10) { done(made); return }
            web.evaluateJavascript(figureJs(i)) { raw ->
                val r = try { JSONObject(unJs(raw)) } catch (e: Exception) { null }
                if (r == null || r.optBoolean("done")) { done(made); return@evaluateJavascript }
                val data = r.optString("data")
                if (data.startsWith("data:image")) {
                    try {
                        val bytes = android.util.Base64.decode(data.substringAfter("base64,"), android.util.Base64.DEFAULT)
                        val out = java.io.File(dir, "fig_" + System.currentTimeMillis() + "_" + i + ".png")
                        out.writeBytes(bytes)
                        figures.add(out.name)
                        made++
                    } catch (e: Throwable) { }
                    step(i + 1)
                    return@evaluateJavascript
                }
                web.postDelayed({
                    try {
                        val full = pageShot() ?: run { step(i + 1); return@postDelayed }
                        val x = (r.optDouble("x") * full.width).toInt().coerceIn(0, full.width - 1)
                        val y = (r.optDouble("y") * full.height).toInt().coerceIn(0, full.height - 1)
                        val w = (r.optDouble("w") * full.width).toInt().coerceAtMost(full.width - x)
                        val h = (r.optDouble("h") * full.height).toInt().coerceAtMost(full.height - y)
                        if (w >= 60 && h >= 40) {
                            val cut = android.graphics.Bitmap.createBitmap(full, x, y, w, h)
                            val out = java.io.File(dir, "fig_" + System.currentTimeMillis() + "_" + i + ".png")
                            out.outputStream().use { cut.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
                            cut.recycle()
                            figures.add(out.name)
                            made++
                        }
                        full.recycle()
                    } catch (e: Throwable) { }
                    step(i + 1)
                }, 260)
            }
        }
        step(0)
    }





    /** The JavaScript string the WebView hands back, as plain text. */
    private fun unJs(raw: String?): String {
        var t = (raw ?: "").trim()
        if (t == "null") return ""
        if (t.startsWith("\"") && t.endsWith("\"") && t.length >= 2) t = t.substring(1, t.length - 1)
        return t.replace("\\u003C", "<").replace("\\n", "\n").replace("\\r", "")
            .replace("\\t", " ").replace("\\\"", "\"").replace("\\\\", "\\").trim()
    }

    /** What was read, named, so it can be checked before it is kept. */
    private fun showPending() {
        pendRow?.let { (it.parent as? android.view.ViewGroup)?.removeView(it) }
        pendRow = null
        val o = pending ?: return
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xFF14301F.toInt()); setPadding(dp(10), dp(7), dp(8), dp(8))
        }
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        top.addView(EfbUi.text(this, (if (o.optString("kind") == "qa") "✅  " else "📄  ") + StudyParse.describe(o) +
            (if (figures.isNotEmpty()) "  ·  ${figures.size} figure" + (if (figures.size > 1) "s" else "") else ""),
            12.5f, 0xFF7BE495.toInt(), bold = true), LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(chip("✕", 0xFF3A2A2A.toInt()) { pending = null; dropFigures(); showPending() })
        row.addView(top)
        // The figures found, side by side, so it is plain what was copied off the page.
        if (figures.isNotEmpty()) {
            val strip = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            for (name in figures) {
                val f = java.io.File(java.io.File(filesDir, "studybook"), name)
                if (!f.exists()) continue
                strip.addView(android.widget.ImageView(this).apply {
                    setImageBitmap(android.graphics.BitmapFactory.decodeFile(f.path))
                    adjustViewBounds = true
                    scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
                    background = EfbUi.cardBg(this@StudyBookActivity, 0xFFFFFFFF.toInt(), 5)
                    setPadding(dp(2), dp(2), dp(2), dp(2))
                }, LinearLayout.LayoutParams(-2, dp(74)).apply { marginEnd = dp(6) })
            }
            row.addView(android.widget.HorizontalScrollView(this).apply {
                isHorizontalScrollBarEnabled = false; addView(strip)
            }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(7) })
        }
        pad.addView(row, 0)
        pendRow = row
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
        val o = pending
        if (q.isEmpty() && clipFile == null && o == null && figures.isEmpty()) {
            Toast.makeText(this, "Nothing for a page yet — press Capture, or take a figure", Toast.LENGTH_SHORT).show(); return
        }
        // The page keeps the shape it was read in, with the pilot's own wording of the question if
        // they changed it, their explanation, and the figure if one was framed.
        val page = o ?: JSONObject().put("kind", "note")
        page.put("q", q.ifEmpty { page.optString("q").ifEmpty { "(a figure)" } })
            .put("e", mine.text.toString().trim())
            .put("img", clipFile ?: JSONObject.NULL)
            .put("imgs", JSONArray().apply { for (n in figures) put(n) })
            .put("u", prefs.getString("study_last_url", "") ?: "")
            .put("at", System.currentTimeMillis())
        val topic = topicOf(q + " " + page.optString("why") + " " + page.optString("acs") + " " + mine.text.toString())
        page.put("t", topic)
        val pages = load()
        pages.put(page)
        prefs.edit().putString(KEY, pages.toString()).apply()
        question.setText(""); mine.setText("")
        clipFile = null; showClip()
        pending = null; figures.clear(); showPending()
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
