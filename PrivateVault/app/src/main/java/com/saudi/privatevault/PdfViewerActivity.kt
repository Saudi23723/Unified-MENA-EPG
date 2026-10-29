package com.saudi.privatevault

import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.text.InputType
import android.graphics.drawable.GradientDrawable
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.Toast
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.activity.OnBackPressedCallback
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.slider.Slider
import com.saudi.privatevault.databinding.ActivityPdfBinding
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class PdfViewerActivity : BaseActivity() {

    private lateinit var b: ActivityPdfBinding
    private var renderer: PdfRenderer? = null
    private var links: PdfLinks? = null

    // The printed contents joined to page footers, once read (kept on disk per book).
    private var printed: PdfLinks.Printed? = null
    private var pageIndex = 0
    private var itemId = ""

    // Width in pixels of the bitmap now shown, to turn a tap into page points.
    private var shownWidth = 0
    private var shownIndex = -1

    // Pages left by following a link or the contents, so Back returns to them.
    private val history = ArrayList<Int>()

    // What is written on the pages, and each page's undo and redo.
    private lateinit var marks: DocumentMarks
    private val undo = HashMap<Int, ArrayDeque<AnnotatedPageView.Edit>>()
    private val redo = HashMap<Int, ArrayDeque<AnnotatedPageView.Edit>>()
    private var writing = false
    private var chromeShown = true
    private var penColor = MarkPainter.INK[0]
    private var markerColor = MarkPainter.MARKER[0]
    private val toolButtons = HashMap<Tool, ImageButton>()
    private var colorButton: ImageButton? = null
    private var sizeButton: ImageButton? = null
    private var undoButton: ImageButton? = null
    private var redoButton: ImageButton? = null

    // PdfRenderer allows one page at a time, so every render goes through one thread.
    @OptIn(ExperimentalCoroutinesApi::class)
    private val pdfThread = Dispatchers.IO.limitedParallelism(1)

    // The contents and links come from a second reader with its own thread.
    @OptIn(ExperimentalCoroutinesApi::class)
    private val linkThread = Dispatchers.IO.limitedParallelism(1)

    private val backToLink = object : OnBackPressedCallback(false) {
        override fun handleOnBackPressed() {
            val prev = history.removeAt(history.size - 1)
            isEnabled = history.isNotEmpty()
            go(prev)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityPdfBinding.inflate(layoutInflater)
        setContentView(b.root)
        val item = VaultStore.item(intent.getStringExtra(Viewers.EXTRA_ID)) ?: return finish()
        itemId = item.id
        // The page always fills the screen; the bars float over it and slide away.
        WindowCompat.setDecorFitsSystemWindows(window, false)
        ViewCompat.setOnApplyWindowInsetsListener(b.root) { _, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            b.topBar.setPadding(bars.left, bars.top, bars.right, 0)
            b.bottomBar.setPadding(bars.left, 0, bars.right, bars.bottom)
            insets
        }
        marks = DocumentMarks.forItem(this, itemId)
        loadBookmarks()
        setUpPen()
        b.page.onSelection = { _, text -> onTextSelected(text) }
        b.toolbar.title = item.name
        b.toolbar.setNavigationOnClickListener { finish() }
        b.toolbar.inflateMenu(R.menu.reader_menu)
        b.toolbar.setOnMenuItemClickListener { mi ->
            when (mi.itemId) {
                R.id.v_read_mode -> ReadingMode.choose(this) { applyMode(it) }
                R.id.v_contents -> showContents()
                R.id.v_goto -> askPage()
                R.id.v_write -> startWriting()
                R.id.v_bookmark -> toggleBookmark()
                R.id.v_finger -> {
                    b.page.fingerDraws = !b.page.fingerDraws
                    mi.isChecked = b.page.fingerDraws
                    VaultLock.prefs(this).edit().putBoolean("finger_draws", b.page.fingerDraws).apply()
                }
                else -> Viewers.openWith(this, item)
            }
            true
        }
        applyMode(ReadingMode.current(this))
        b.toolbar.menu.findItem(R.id.v_finger)?.isChecked = b.page.fingerDraws
        // Reading should not be cut off by the screen going dark.
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        renderer = try {
            PdfRenderer(ParcelFileDescriptor.open(VaultStore.fileOf(item), ParcelFileDescriptor.MODE_READ_ONLY))
        } catch (e: Exception) {
            null
        }
        val count = renderer?.pageCount ?: 0
        if (count == 0) {
            // Protected or unusual PDFs: let another app try.
            Toast.makeText(this, R.string.open_failed, Toast.LENGTH_SHORT).show()
            Viewers.openWith(this, item)
            return finish()
        }
        // Reopening a document goes back to the page it was left on.
        pageIndex = savedInstanceState?.getInt("page")
            ?: VaultLock.prefs(this).getInt("pdf_$itemId", 0)
        savedInstanceState?.getIntegerArrayList("history")?.let { history.addAll(it) }
        backToLink.isEnabled = history.isNotEmpty()
        onBackPressedDispatcher.addCallback(this, backToLink)

        b.prev.setOnClickListener { go(pageIndex - 1) }
        b.next.setOnClickListener { go(pageIndex + 1) }
        b.pageNumber.setOnClickListener { askPage() }
        b.page.onSwipe = { dir -> go(pageIndex + dir) }
        b.page.onTapAt = { x, y -> tapped(x, y) }
        b.toolbar.menu.findItem(R.id.v_goto).isVisible = true
        setUpSlider(count)
        b.page.post { show() }
        // A moment to see where things are, then the page alone.
        b.root.postDelayed({ if (!writing) setChrome(false) }, 2500)

        val file = VaultStore.fileOf(item)
        lifecycleScope.launch {
            val l = withContext(linkThread) { PdfLinks.open(this@PdfViewerActivity, file)?.also { it.chapters } }
            if (l == null) return@launch
            if (isDestroyed) {
                CoroutineScope(linkThread).launch { l.close() }
                return@launch
            }
            links = l
            if (shownIndex == pageIndex) loadLetters(pageIndex)
            readPrinted(l, file)
        }
    }

    private fun setUpSlider(count: Int) {
        val s = b.pageSlider
        if (count < 2) return
        s.valueFrom = 1f
        s.valueTo = count.toFloat()
        s.value = (pageIndex + 1).coerceIn(1, count).toFloat()
        s.setLabelFormatter { it.toInt().toString() }
        s.visibility = android.view.View.VISIBLE
        // While dragging only the number follows; the page is drawn on release.
        s.addOnChangeListener { _, value, fromUser ->
            if (fromUser) b.pageNumber.text = getString(R.string.page_of, value.toInt(), count)
        }
        s.addOnSliderTouchListener(object : Slider.OnSliderTouchListener {
            override fun onStartTrackingTouch(slider: Slider) {}
            override fun onStopTrackingTouch(slider: Slider) = jump(slider.value.toInt() - 1)
        })
    }

    private fun applyMode(mode: ReadingMode) {
        b.page.colorFilter = mode.pageFilter()
        b.page.setBackgroundColor(if (mode == ReadingMode.NORMAL) 0xFF9E9E9E.toInt() else mode.background)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putInt("page", pageIndex)
        outState.putIntegerArrayList("history", history)
    }

    override fun onPause() {
        super.onPause()
        if (itemId.isNotEmpty()) VaultLock.prefs(this).edit().putInt("pdf_$itemId", pageIndex).apply()
    }

    override fun onDestroy() {
        super.onDestroy()
        val r = renderer
        renderer = null
        // lifecycleScope is already cancelled here, so close on a scope of its own.
        if (r != null) CoroutineScope(pdfThread).launch { r.close() }
        val l = links
        links = null
        if (l != null) CoroutineScope(linkThread).launch { l.close() }
    }

    private fun go(i: Int) {
        val count = renderer?.pageCount ?: return
        if (i < 0 || i >= count) return
        pageIndex = i
        show()
    }

    /** A far move (contents, link, slider, typed number): Back returns to where it started. */
    private fun jump(i: Int) {
        val count = renderer?.pageCount ?: return
        if (i < 0 || i >= count || i == pageIndex) {
            show()
            return
        }
        history.add(pageIndex)
        if (history.size > 50) history.removeAt(0)
        backToLink.isEnabled = true
        go(i)
    }

    private fun show() {
        val r = renderer ?: return
        val count = r.pageCount
        pageIndex = pageIndex.coerceIn(0, count - 1)
        val index = pageIndex
        b.pageNumber.text = getString(R.string.page_of, index + 1, count)
        b.prev.isEnabled = index > 0
        b.next.isEnabled = index < count - 1
        if (count >= 2) b.pageSlider.value = (index + 1).toFloat()
        // Render at twice the screen width so text stays sharp when zoomed in.
        val width = (maxOf(b.page.width, resources.displayMetrics.widthPixels) * 2).coerceAtMost(3000)
        lifecycleScope.launch {
            val bmp = withContext(pdfThread) {
                try {
                    if (renderer == null) return@withContext null
                    val page = r.openPage(index)
                    try {
                        val h = (width.toFloat() * page.height / page.width).toInt().coerceIn(1, 6000)
                        Bitmap.createBitmap(width, h, Bitmap.Config.ARGB_8888).also {
                            it.eraseColor(Color.WHITE)
                            page.render(it, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        }
                    } finally {
                        page.close()
                    }
                } catch (e: Exception) {
                    null
                }
            }
            if (bmp != null && index == pageIndex) {
                shownWidth = bmp.width
                shownIndex = index
                b.page.marks = marks.on(index)
                b.page.setImageBitmap(bmp)
                refreshUndo()
                refreshBookmark()
                loadLetters(index)
            }
        }
    }

    // ---- links and contents ----

    private fun printedCache(): java.io.File =
        java.io.File(filesDir, "pdfindex/" + itemId.replace(Regex("[^A-Za-z0-9_-]"), "_") + ".json")

    /** Reads every page's printed number once, a page at a time so taps are not held up. */
    private suspend fun readPrinted(l: PdfLinks, file: java.io.File) {
        val cache = printedCache()
        val stamp = "${file.length()}:${file.lastModified()}"
        withContext(Dispatchers.IO) {
            try {
                val o = org.json.JSONObject(cache.readText())
                if (o.optString("stamp") == stamp) PdfLinks.Printed.fromJson(o.getString("index")) else null
            } catch (e: Exception) {
                null
            }
        }?.let {
            printed = it
            return
        }
        val n = withContext(linkThread) { l.pageCount }
        for (i in 0 until n) {
            if (links !== l) return
            withContext(linkThread) { l.readPage(i) }
            if (i % 10 == 0) b.toolbar.subtitle = getString(R.string.pdf_preparing, i + 1, n)
        }
        val p = withContext(linkThread) { l.printed() }
        printed = p
        b.toolbar.subtitle = null
        withContext(Dispatchers.IO) {
            try {
                cache.parentFile?.mkdirs()
                cache.writeText(org.json.JSONObject().put("stamp", stamp).put("index", p.toJson()).toString())
            } catch (e: Exception) {
                // Read again next time.
            }
        }
    }

    private fun tapped(x: Float, y: Float) {
        val l = links
        val index = shownIndex
        if (l == null || index != pageIndex || shownWidth <= 0) {
            toggleChrome()
            return
        }
        val width = shownWidth
        lifecycleScope.launch {
            val pageLinks = withContext(linkThread) { l.linksOn(index) } ?: return@launch
            val scale = width / pageLinks.width
            val px = x / scale
            val py = y / scale
            // A little slack around each link, as fingers are wider than the text.
            val slack = 6f
            val hit = pageLinks.links.firstOrNull {
                px >= it.area.left - slack && px <= it.area.right + slack &&
                    py >= it.area.top - slack && py <= it.area.bottom + slack
            }
            if (hit != null) {
                if (hit.page >= 0) jump(hit.page) else hit.uri?.let { openUri(it) }
                return@launch
            }
            // No real link: a line of the printed contents goes to the page with that number.
            val target = printed?.hit(index, px, py, pageLinks.width) ?: -1
            if (target >= 0) jump(target) else toggleChrome()
        }
    }

    // ---- reading full screen ----

    private fun toggleChrome() {
        if (!writing) setChrome(!chromeShown)
    }

    /** The bars and the phone's own bars come and go together; the page never moves. */
    private fun setChrome(shown: Boolean) {
        chromeShown = shown
        b.topBar.animate().translationY(if (shown) 0f else -b.topBar.height.toFloat()).setDuration(180).start()
        b.navBar.visibility = if (shown && !writing) View.VISIBLE else View.GONE
        val ctl = WindowCompat.getInsetsController(window, window.decorView)
        ctl.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        if (shown) ctl.show(WindowInsetsCompat.Type.systemBars()) else ctl.hide(WindowInsetsCompat.Type.systemBars())
    }

    // ---- writing on the page ----

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun setUpPen() {
        val p = b.page
        p.fingerDraws = VaultLock.prefs(this).getBoolean("finger_draws", true)
        p.onStylusSeen = {
            if (!VaultLock.prefs(this).contains("finger_draws")) {
                Toast.makeText(this, R.string.pen_stylus_found, Toast.LENGTH_LONG).show()
            } else {
                p.fingerDraws = VaultLock.prefs(this).getBoolean("finger_draws", false)
            }
            VaultLock.prefs(this).edit().putBoolean("finger_draws", p.fingerDraws).apply()
            b.toolbar.menu.findItem(R.id.v_finger)?.isChecked = p.fingerDraws
        }
        p.onEdit = { e ->
            undo.getOrPut(pageIndex) { ArrayDeque() }.addLast(e)
            redo[pageIndex]?.clear()
            saveMarks()
        }
        p.onTextAt = { x, y -> askText(x, y) }

        val bar = b.penTools
        fun button(icon: Int, label: Int, onClick: () -> Unit) = ImageButton(this).apply {
            setImageResource(icon)
            contentDescription = getString(label)
            tooltipText = getString(label)
            background = null
            setPadding(dp(10), dp(10), dp(10), dp(10))
            setOnClickListener { onClick() }
            bar.addView(this, LinearLayout.LayoutParams(dp(46), dp(46)).apply { setMargins(dp(2), 0, dp(2), 0) })
        }
        val tools = listOf(
            Triple(Tool.HAND, R.drawable.ic_tool_hand, R.string.pen_hand),
            Triple(Tool.PEN, R.drawable.ic_tool_pen, R.string.pen_pen),
            Triple(Tool.HIGHLIGHT, R.drawable.ic_tool_highlight, R.string.pen_highlight),
            Triple(Tool.ERASER, R.drawable.ic_tool_eraser, R.string.pen_eraser),
            Triple(Tool.LINE, R.drawable.ic_tool_line, R.string.pen_line),
            Triple(Tool.ARROW, R.drawable.ic_tool_arrow, R.string.pen_arrow),
            Triple(Tool.RECT, R.drawable.ic_tool_rect, R.string.pen_rect),
            Triple(Tool.OVAL, R.drawable.ic_tool_oval, R.string.pen_oval),
            Triple(Tool.TEXT, R.drawable.ic_tool_text, R.string.pen_text),
        )
        for ((tool, icon, label) in tools) toolButtons[tool] = button(icon, label) { pick(tool) }
        // A long press on the highlighter switches between a straight band and free hand.
        p.straightMarker = VaultLock.prefs(this).getBoolean("straight_marker", true)
        toolButtons[Tool.HIGHLIGHT]?.setOnLongClickListener {
            p.straightMarker = !p.straightMarker
            VaultLock.prefs(this).edit().putBoolean("straight_marker", p.straightMarker).apply()
            pick(Tool.HIGHLIGHT, quiet = true)
            Toast.makeText(this, if (p.straightMarker) R.string.pen_marker_straight else R.string.pen_marker_free, Toast.LENGTH_SHORT).show()
            true
        }
        bar.addView(View(this).apply { setBackgroundColor(0x33000000) }, LinearLayout.LayoutParams(dp(1), dp(28)).apply { setMargins(dp(6), 0, dp(6), 0) })
        colorButton = button(R.drawable.ic_tool_pen, R.string.pen_color) { chooseColor() }
        sizeButton = button(R.drawable.ic_tool_pen, R.string.pen_size) {
            p.widthLevel = (p.widthLevel + 1) % 3
            VaultLock.prefs(this).edit().putInt("pen_width", p.widthLevel).apply()
            paintSwatches()
        }
        undoButton = button(R.drawable.ic_undo, R.string.pen_undo) { undoLast() }
        redoButton = button(R.drawable.ic_redo, R.string.pen_redo) { redoLast() }
        button(R.drawable.ic_check, R.string.pen_done) { stopWriting() }
        p.widthLevel = VaultLock.prefs(this).getInt("pen_width", 1)
        penColor = VaultLock.prefs(this).getInt("pen_color", penColor)
        markerColor = VaultLock.prefs(this).getInt("marker_color", markerColor)
        pick(Tool.PEN, quiet = true)
        p.tool = Tool.HAND
    }

    private fun startWriting() {
        writing = true
        setChrome(false)
        b.penBar.visibility = View.VISIBLE
        pick(if (b.page.tool == Tool.HAND) Tool.PEN else b.page.tool)
    }

    private fun stopWriting() {
        writing = false
        b.page.tool = Tool.HAND
        b.penBar.visibility = View.GONE
        setChrome(true)
    }

    private fun pick(tool: Tool, quiet: Boolean = false) {
        val p = b.page
        p.tool = tool
        p.color = if (tool == Tool.HIGHLIGHT) markerColor else penColor
        for ((t, btn) in toolButtons) btn.background = if (t == tool) getDrawable(R.drawable.tool_selected_bg) else null
        paintSwatches()
        if (!quiet && tool == Tool.HAND) Toast.makeText(this, R.string.pen_hand_hint, Toast.LENGTH_SHORT).show()
    }

    /** The colour button shows the colour, the size button a dot of the line's thickness. */
    private fun paintSwatches() {
        val p = b.page
        colorButton?.setImageDrawable(GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(p.color)
            setStroke(dp(2), 0x33000000)
            setSize(dp(22), dp(22))
        })
        val d = intArrayOf(6, 11, 17)[p.widthLevel.coerceIn(0, 2)]
        sizeButton?.setImageDrawable(GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(0xFF616161.toInt())
            setSize(dp(d), dp(d))
        })
    }

    private fun chooseColor() {
        val p = b.page
        val marker = p.tool == Tool.HIGHLIGHT
        val colors = if (marker) MarkPainter.MARKER else MarkPainter.INK
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(16), dp(12), dp(16), dp(4))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        val dialog = MaterialAlertDialogBuilder(this).setTitle(R.string.pen_color).setView(row).show()
        for (c in colors) {
            row.addView(View(this).apply {
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    setColor(c)
                    setStroke(dp(if (c == p.color) 4 else 1), if (c == p.color) 0xFF424242.toInt() else 0x33000000)
                }
                setOnClickListener {
                    if (marker) markerColor = c else penColor = c
                    VaultLock.prefs(this@PdfViewerActivity).edit()
                        .putInt(if (marker) "marker_color" else "pen_color", c).apply()
                    p.color = c
                    paintSwatches()
                    dialog.dismiss()
                }
            }, LinearLayout.LayoutParams(dp(40), dp(40)).apply { setMargins(dp(6), dp(6), dp(6), dp(6)) })
        }
    }

    private fun askText(x: Float, y: Float) {
        val input = EditText(this).apply {
            hint = getString(R.string.pen_text_hint)
            minLines = 2
        }
        val box = FrameLayout(this).apply {
            setPadding(dp(20), dp(8), dp(20), 0)
            addView(input)
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pen_text)
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ ->
                val t = input.text.toString().trimEnd()
                if (t.isNotBlank()) b.page.addText(x, y, t)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
        input.requestFocus()
        dialog.window?.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE)
    }

    private fun undoLast() {
        val e = undo[pageIndex]?.removeLastOrNull() ?: return
        val list = marks.on(pageIndex)
        when (e) {
            is AnnotatedPageView.Edit.Added -> list.remove(e.mark)
            is AnnotatedPageView.Edit.Removed -> for ((i, m) in e.removed.asReversed()) list.add(i.coerceAtMost(list.size), m)
        }
        redo.getOrPut(pageIndex) { ArrayDeque() }.addLast(e)
        b.page.invalidate()
        saveMarks()
    }

    private fun redoLast() {
        val e = redo[pageIndex]?.removeLastOrNull() ?: return
        val list = marks.on(pageIndex)
        when (e) {
            is AnnotatedPageView.Edit.Added -> list.add(e.mark)
            is AnnotatedPageView.Edit.Removed -> for ((_, m) in e.removed) list.remove(m)
        }
        undo.getOrPut(pageIndex) { ArrayDeque() }.addLast(e)
        b.page.invalidate()
        saveMarks()
    }

    private fun refreshUndo() {
        undoButton?.alpha = if (undo[pageIndex].isNullOrEmpty()) 0.35f else 1f
        redoButton?.alpha = if (redo[pageIndex].isNullOrEmpty()) 0.35f else 1f
    }

    /** Written right away, so nothing is lost if the app is closed. */
    private fun saveMarks() {
        refreshUndo()
        val text = marks.snapshot()
        CoroutineScope(Dispatchers.IO).launch { marks.write(text) }
    }

    private fun openUri(uri: String) {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pdf_open_link)
            .setMessage(uri)
            .setPositiveButton(R.string.ok) { _, _ ->
                try {
                    VaultLock.keepUnlockedOnce = true
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(uri)))
                } catch (e: ActivityNotFoundException) {
                    VaultLock.keepUnlockedOnce = false
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** The page's letters, so a long press can select words (read in the background). */
    private fun loadLetters(index: Int) {
        b.page.letters = null
        val l = links ?: return
        lifecycleScope.launch {
            val ls = withContext(linkThread) { l.lettersOn(index) }
            if (index == pageIndex && shownIndex == index) b.page.letters = ls
        }
    }

    // ---- bookmarks ----

    private class Bookmark(val page: Int, var title: String)

    private val bookmarks = ArrayList<Bookmark>()

    private fun loadBookmarks() {
        bookmarks.clear()
        try {
            val a = org.json.JSONArray(VaultLock.prefs(this).getString("bm_$itemId", "[]"))
            for (k in 0 until a.length()) {
                val o = a.getJSONObject(k)
                bookmarks.add(Bookmark(o.getInt("p"), o.optString("t")))
            }
        } catch (e: Exception) {
            // None yet.
        }
    }

    private fun saveBookmarks() {
        val a = org.json.JSONArray()
        for (bm in bookmarks.sortedBy { it.page }) a.put(org.json.JSONObject().put("p", bm.page).put("t", bm.title))
        VaultLock.prefs(this).edit().putString("bm_$itemId", a.toString()).apply()
        refreshBookmark()
    }

    private fun refreshBookmark() {
        val on = bookmarks.any { it.page == pageIndex }
        b.page.bookmarked = on
        b.toolbar.menu.findItem(R.id.v_bookmark)?.setIcon(if (on) R.drawable.ic_bookmark_on else R.drawable.ic_bookmark)
    }

    /** One tap marks the page (named after its chapter when known); another removes it. */
    private fun toggleBookmark() {
        val existing = bookmarks.firstOrNull { it.page == pageIndex }
        if (existing != null) {
            bookmarks.remove(existing)
            Toast.makeText(this, R.string.bm_removed, Toast.LENGTH_SHORT).show()
        } else {
            val chapter = (links?.chapters.orEmpty().filter { it.page in 0..pageIndex } +
                printed?.chapters.orEmpty().filter { it.page in 0..pageIndex }).maxByOrNull { it.page }
            bookmarks.add(Bookmark(pageIndex, chapter?.title?.substringBefore("  (") ?: ""))
            Toast.makeText(this, getString(R.string.bm_added, pageIndex + 1), Toast.LENGTH_SHORT).show()
        }
        saveBookmarks()
    }

    private fun renameBookmark(bm: Bookmark) {
        val input = EditText(this).apply {
            setText(bm.title)
            setSingleLine()
            hint = getString(R.string.bm_name)
        }
        val box = FrameLayout(this).apply {
            setPadding(dp(20), dp(8), dp(20), 0)
            addView(input)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(getString(R.string.pdf_page_short, bm.page + 1))
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ ->
                bm.title = input.text.toString().trim()
                saveBookmarks()
            }
            .setNeutralButton(R.string.delete) { _, _ ->
                bookmarks.remove(bm)
                saveBookmarks()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    // ---- selected text ----

    private fun onTextSelected(text: String) {
        val items = arrayOf(getString(R.string.sel_highlight), getString(R.string.sel_copy))
        MaterialAlertDialogBuilder(this)
            .setTitle(text.replace('\n', ' ').take(80) + if (text.length > 80) "…" else "")
            .setItems(items) { _, which ->
                if (which == 0) {
                    b.page.highlightSelection(markerColor)
                } else {
                    val cm = getSystemService(android.content.ClipboardManager::class.java)
                    cm?.setPrimaryClip(android.content.ClipData.newPlainText("text", text))
                    Toast.makeText(this, R.string.sel_copied, Toast.LENGTH_SHORT).show()
                    b.page.clearSelection()
                }
            }
            .setOnCancelListener { b.page.clearSelection() }
            .setNegativeButton(R.string.cancel) { _, _ -> b.page.clearSelection() }
            .show()
    }

    /** Bookmarks, pages with notes, then the book's contents, in one list. */
    private fun showContents() {
        val chapters = links?.chapters.orEmpty().filter { it.page >= 0 }
            .ifEmpty { printed?.chapters.orEmpty() }
        val labels = ArrayList<CharSequence>()
        val actions = ArrayList<(() -> Unit)?>()
        fun header(text: String) {
            labels.add(android.text.SpannableString(text).apply {
                setSpan(android.text.style.StyleSpan(android.graphics.Typeface.BOLD), 0, text.length, 0)
            })
            actions.add(null)
        }
        if (bookmarks.isNotEmpty()) {
            header(getString(R.string.bm_header))
            for (bm in bookmarks.sortedBy { it.page }) {
                labels.add("🔖  " + getString(R.string.pdf_page_short, bm.page + 1) + if (bm.title.isNotEmpty()) "  ·  ${bm.title}" else "")
                actions.add { jump(bm.page) }
            }
        }
        val noted = marks.pages.filterValues { it.isNotEmpty() }.keys.sorted()
        if (noted.isNotEmpty()) {
            header(getString(R.string.notes_header))
            for (pg in noted) {
                labels.add("✏️  " + getString(R.string.pdf_page_short, pg + 1) + "  ·  " + getString(R.string.notes_count, marks.on(pg).size))
                actions.add { jump(pg) }
            }
        }
        if (chapters.isNotEmpty()) {
            header(getString(R.string.pdf_contents))
            for (c in chapters) {
                labels.add("\u2003".repeat(c.level) + c.title + "  ·  " + getString(R.string.pdf_page_short, c.page + 1))
                actions.add { jump(c.page) }
            }
        }
        if (labels.isEmpty()) {
            val msg = if (printed == null && links != null) R.string.pdf_preparing_wait else R.string.contents_empty
            Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
            return
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.contents_title)
            .setItems(labels.toTypedArray()) { _, which -> actions[which]?.invoke() }
            .setNegativeButton(R.string.cancel, null)
            .show()
        // A long press on a bookmark renames or removes it.
        val sorted = bookmarks.sortedBy { it.page }
        dialog.listView?.setOnItemLongClickListener { _, _, position, _ ->
            val bm = sorted.getOrNull(position - 1)
            if (bookmarks.isNotEmpty() && position in 1..sorted.size && bm != null) {
                dialog.dismiss()
                renameBookmark(bm)
                true
            } else false
        }
    }

    private fun askPage() {
        val count = renderer?.pageCount ?: return
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            hint = getString(R.string.pdf_goto_hint, count)
            setSingleLine()
        }
        val pad = (resources.displayMetrics.density * 20).toInt()
        val box = FrameLayout(this).apply {
            setPadding(pad, pad / 2, pad, 0)
            addView(input)
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pdf_goto)
            .setView(box)
            .setPositiveButton(R.string.pdf_go) { _, _ ->
                val n = input.text.toString().toIntOrNull() ?: return@setPositiveButton
                jump(n.coerceIn(1, count) - 1)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
        input.requestFocus()
        dialog.window?.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE)
    }
}
