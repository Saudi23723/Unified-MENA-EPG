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
    private var deleteButton: ImageButton? = null
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
        pullNotes()
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
                R.id.v_bookmarks -> showBookmarks()
                R.id.v_ai -> askAssistant(null)
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
        b.bookmarkStrip.trackInset = b.pageSlider.trackSidePadding.toFloat()
        b.bookmarkStrip.onPick = { jump(it) }
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
        b.root.removeCallbacks(pushSoon)
        pushNotes()
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
            marks.touch(pageIndex)
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
            Triple(Tool.SELECT, R.drawable.ic_tool_select, R.string.pen_select),
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
        // A long press on the highlighter: straight or free hand, square or rounded ends.
        p.straightMarker = VaultLock.prefs(this).getBoolean("straight_marker", true)
        p.roundMarker = VaultLock.prefs(this).getBoolean("round_marker", false)
        // The pen: a long press, or a tap when it is already in hand, picks the kind of pen.
        p.penStyle = VaultLock.prefs(this).getInt("pen_style", 0)
        fun penKinds() = PenInk.choose(this, p.penStyle) { i ->
            p.penStyle = i
            VaultLock.prefs(this).edit().putInt("pen_style", i).apply()
            pick(Tool.PEN)
            Toast.makeText(this, PenStyle.values()[i].label, Toast.LENGTH_SHORT).show()
        }
        toolButtons[Tool.PEN]?.setOnClickListener { if (b.page.tool == Tool.PEN) penKinds() else pick(Tool.PEN) }
        toolButtons[Tool.PEN]?.setOnLongClickListener { penKinds(); true }
        toolButtons[Tool.HIGHLIGHT]?.setOnLongClickListener {
            markerOptions()
            true
        }
        bar.addView(View(this).apply { setBackgroundColor(0x33000000) }, LinearLayout.LayoutParams(dp(1), dp(28)).apply { setMargins(dp(6), 0, dp(6), 0) })
        colorButton = button(R.drawable.ic_tool_pen, R.string.pen_color) { chooseColor() }
        sizeButton = button(R.drawable.ic_tool_pen, R.string.pen_size) { chooseSize() }
        deleteButton = button(R.drawable.ic_delete, R.string.pen_delete) { b.page.deleteSelected() }
        deleteButton?.alpha = 0.35f
        p.onSelected = { m ->
            deleteButton?.alpha = if (m != null) 1f else 0.35f
            if (m != null && m.tool != Tool.TEXTMARK) paintSwatches(m.color)
            else paintSwatches()
        }
        undoButton = button(R.drawable.ic_undo, R.string.pen_undo) { undoLast() }
        redoButton = button(R.drawable.ic_redo, R.string.pen_redo) { redoLast() }
        button(R.drawable.ic_check, R.string.pen_done) { stopWriting() }
        p.textSize = VaultLock.prefs(this).getFloat("size_text", 0.028f)
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
        if (tool != Tool.SELECT && !(tool == Tool.LINE || tool == Tool.ARROW || tool == Tool.RECT || tool == Tool.OVAL)) p.selected = null
        p.color = if (tool == Tool.HIGHLIGHT) markerColor else penColor
        p.size = sizeFor(tool)
        for ((t, btn) in toolButtons) btn.background = if (t == tool) getDrawable(R.drawable.tool_selected_bg) else null
        paintSwatches()
        if (!quiet && tool == Tool.HAND) Toast.makeText(this, R.string.pen_hand_hint, Toast.LENGTH_SHORT).show()
    }

    /** The colour button shows the colour, the size button a dot of the line's thickness. */
    private fun paintSwatches(shown: Int? = null) {
        val p = b.page
        colorButton?.setImageDrawable(GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(shown ?: p.color)
            setStroke(dp(2), 0x33000000)
            setSize(dp(22), dp(22))
        })
        // The dot grows with the thickness, between thin and thick for the tool.
        val t = if (p.tool == Tool.TEXT) Tool.TEXT else p.tool
        val (lo, hi) = MarkPainter.sizeRange(t)
        val now = p.selected?.width?.takeIf { it > 0f } ?: if (t == Tool.TEXT) p.textSize else p.size
        val d = 4 + ((now - lo) / (hi - lo)).coerceIn(0f, 1f) * 16
        sizeButton?.setImageDrawable(GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(0xFF616161.toInt())
            setSize(dp(d.toInt()), dp(d.toInt()))
        })
    }

    // ---- sizes ----

    private fun sizeKey(tool: Tool) = when (tool) {
        Tool.HIGHLIGHT -> "size_marker"
        Tool.TEXT -> "size_text"
        else -> "size_pen"
    }

    private fun sizeFor(tool: Tool): Float =
        VaultLock.prefs(this).getFloat(sizeKey(tool), MarkPainter.widths(tool)[1])

    /** A slider from very thin to very thick, with a live preview; on a picked mark it resizes that mark. */
    private fun chooseSize() {
        val p = b.page
        val picked = p.selected?.takeIf { it.tool != Tool.TEXTMARK }
        val tool = picked?.tool ?: p.tool
        val (lo, hi) = MarkPainter.sizeRange(tool)
        val start = (picked?.width ?: if (tool == Tool.TEXT) p.textSize else p.size).coerceIn(lo, hi)
        // How wide the page is on screen right now, to show the line at its real size.
        val pagePx = b.page.width.toFloat().coerceAtLeast(1f)
        val preview = View(this)
        fun show(v: Float) {
            val px = (v * pagePx).coerceIn(1f, dp(60).toFloat())
            preview.background = GradientDrawable().apply {
                cornerRadius = px / 2
                setColor(picked?.color ?: p.color)
                alpha = if (tool == Tool.HIGHLIGHT) 0x90 else 0xFF
            }
            preview.layoutParams = LinearLayout.LayoutParams(dp(200), px.toInt().coerceAtLeast(1)).apply { gravity = android.view.Gravity.CENTER_HORIZONTAL }
        }
        val slider = com.google.android.material.slider.Slider(this).apply {
            valueFrom = 0f
            valueTo = 100f
            // An even feel across the range: thin sizes get as much of the slider as thick ones.
            value = (Math.log((start / lo).toDouble()) / Math.log((hi / lo).toDouble()) * 100).toFloat().coerceIn(0f, 100f)
            setLabelFormatter { "${it.toInt()}" }
        }
        fun valueOf(pos: Float) = (lo * Math.pow((hi / lo).toDouble(), pos / 100.0)).toFloat()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), 0)
            addView(FrameLayout(this@PdfViewerActivity).apply {
                minimumHeight = dp(70)
                addView(preview)
            }, LinearLayout.LayoutParams(-1, dp(70)))
            addView(slider)
        }
        show(start)
        (preview.layoutParams as LinearLayout.LayoutParams).let { lp ->
            preview.layoutParams = FrameLayout.LayoutParams(lp.width, lp.height, android.view.Gravity.CENTER)
        }
        slider.addOnChangeListener { _, pos, _ ->
            val v = valueOf(pos)
            show(v)
            preview.layoutParams = FrameLayout.LayoutParams(dp(200), (v * pagePx).coerceIn(1f, dp(60).toFloat()).toInt(), android.view.Gravity.CENTER)
            if (picked != null) p.resizeSelected(v, record = false)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pen_size)
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ ->
                val v = valueOf(slider.value)
                if (picked != null) {
                    p.resizeSelected(v, record = true)
                } else {
                    VaultLock.prefs(this).edit().putFloat(sizeKey(tool), v).apply()
                    if (tool == Tool.TEXT) p.textSize = v else p.size = v
                }
                paintSwatches()
            }
            .setNegativeButton(R.string.cancel) { _, _ ->
                if (picked != null) p.resizeSelected(start, record = false)
            }
            .show()
    }

    private fun markerOptions() {
        val p = b.page
        val labels = arrayOf(getString(R.string.pen_marker_straight_opt), getString(R.string.pen_marker_round_opt))
        val checked = booleanArrayOf(p.straightMarker, p.roundMarker)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pen_highlight)
            .setMultiChoiceItems(labels, checked) { _, which, on -> checked[which] = on }
            .setPositiveButton(R.string.ok) { _, _ ->
                p.straightMarker = checked[0]
                p.roundMarker = checked[1]
                VaultLock.prefs(this).edit().putBoolean("straight_marker", checked[0]).putBoolean("round_marker", checked[1]).apply()
                // A picked highlight takes the new ends too.
                p.selected?.takeIf { it.tool == Tool.HIGHLIGHT || it.tool == Tool.TEXTMARK }?.let { m ->
                    m.round = checked[1]
                    marks.touch(pageIndex)
                    saveMarks()
                    p.invalidate()
                }
                pick(Tool.HIGHLIGHT, quiet = true)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    // ---- colours ----

    private fun customColors(): List<Int> =
        VaultLock.prefs(this).getString("custom_colors", "")!!.split(',').mapNotNull { it.toIntOrNull() }

    private fun rememberColor(c: Int) {
        val list = (listOf(c) + customColors().filter { it != c }).take(12)
        VaultLock.prefs(this).edit().putString("custom_colors", list.joinToString(",")).apply()
    }

    private fun applyColor(c: Int, marker: Boolean, picked: Mark?) {
        val p = b.page
        if (picked != null) {
            p.recolorSelected(c)
            paintSwatches(c)
        } else {
            if (marker) markerColor = c else penColor = c
            VaultLock.prefs(this).edit().putInt(if (marker) "marker_color" else "pen_color", c).apply()
            p.color = c
            paintSwatches()
        }
    }

    /** Any colour: hue, saturation and brightness, with a preview. */
    private fun customColor(marker: Boolean, picked: Mark?, start: Int) {
        val hsv = FloatArray(3)
        android.graphics.Color.colorToHSV(start, hsv)
        val preview = View(this)
        fun paint() = preview.setBackgroundColor(android.graphics.Color.HSVToColor(hsv))
        fun slider(max: Float, value: Float, onChange: (Float) -> Unit) = com.google.android.material.slider.Slider(this).apply {
            valueFrom = 0f
            valueTo = max
            this.value = value.coerceIn(0f, max)
            addOnChangeListener { _, v, _ -> onChange(v); paint() }
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(12), dp(20), 0)
            addView(preview, LinearLayout.LayoutParams(-1, dp(56)))
            addView(slider(359f, hsv[0]) { hsv[0] = it })
            addView(slider(100f, hsv[1] * 100) { hsv[1] = it / 100f })
            addView(slider(100f, hsv[2] * 100) { hsv[2] = it / 100f })
        }
        paint()
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pen_custom_color)
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ ->
                val c = android.graphics.Color.HSVToColor(hsv)
                rememberColor(c)
                applyColor(c, marker, picked)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** A grid of colours; with a mark picked, it recolours that mark. */
    private fun chooseColor() {
        val p = b.page
        val picked = p.selected
        val marker = if (picked != null) picked.tool == Tool.HIGHLIGHT || picked.tool == Tool.TEXTMARK else p.tool == Tool.HIGHLIGHT
        val colors = (if (marker) MarkPainter.MARKER.toList() else MarkPainter.INK.toList()) + customColors()
        val current = picked?.color ?: p.color
        val grid = android.widget.GridLayout(this).apply {
            columnCount = 6
            setPadding(dp(14), dp(10), dp(14), dp(4))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        val scroll = android.widget.ScrollView(this).apply { addView(grid) }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pen_color)
            .setView(scroll)
            .setNeutralButton(R.string.pen_custom_color) { _, _ -> customColor(marker, picked, current) }
            .show()
        for (c in colors.distinct()) {
            grid.addView(View(this).apply {
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    setColor(c)
                    setStroke(dp(if (c == current) 4 else 1), if (c == current) 0xFF1E88E5.toInt() else 0x44000000)
                }
                setOnClickListener {
                    applyColor(c, marker, picked)
                    dialog.dismiss()
                }
            }, android.widget.GridLayout.LayoutParams().apply {
                width = dp(40)
                height = dp(40)
                setMargins(dp(5), dp(5), dp(5), dp(5))
            })
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
            is AnnotatedPageView.Edit.Changed -> {
                e.before.copyInto(e.mark.points)
                e.mark.color = e.colorBefore
                if (!e.widthBefore.isNaN()) e.mark.width = e.widthBefore
            }
        }
        b.page.selected = null
        redo.getOrPut(pageIndex) { ArrayDeque() }.addLast(e)
        marks.touch(pageIndex)
        b.page.invalidate()
        saveMarks()
    }

    private fun redoLast() {
        val e = redo[pageIndex]?.removeLastOrNull() ?: return
        val list = marks.on(pageIndex)
        when (e) {
            is AnnotatedPageView.Edit.Added -> list.add(e.mark)
            is AnnotatedPageView.Edit.Removed -> for ((_, m) in e.removed) list.remove(m)
            is AnnotatedPageView.Edit.Changed -> {
                e.after.copyInto(e.mark.points)
                e.mark.color = e.colorAfter
                if (!e.widthAfter.isNaN()) e.mark.width = e.widthAfter
            }
        }
        b.page.selected = null
        undo.getOrPut(pageIndex) { ArrayDeque() }.addLast(e)
        marks.touch(pageIndex)
        b.page.invalidate()
        saveMarks()
    }

    private fun refreshUndo() {
        undoButton?.alpha = if (undo[pageIndex].isNullOrEmpty()) 0.35f else 1f
        redoButton?.alpha = if (redo[pageIndex].isNullOrEmpty()) 0.35f else 1f
    }

    /** Written right away, so nothing is lost if the app is closed; shared a moment later. */
    private fun saveMarks() {
        refreshUndo()
        val text = marks.snapshot()
        CoroutineScope(Dispatchers.IO).launch { marks.write(text) }
        b.root.removeCallbacks(pushSoon)
        b.root.postDelayed(pushSoon, 2500)
    }

    // ---- sharing notes with the vault, so other devices see them ----

    /** How the vault knows this document: its own file, or a phone file that was sent to it. */
    private fun notesQuery(): String? {
        if (!LaptopClient.isLinked(this)) return null
        return if (itemId.startsWith("laptop:")) "item=" + Uri.encode(itemId.removePrefix("laptop:"))
        else "src=" + Uri.encode("phone:$itemId")
    }

    private val pushSoon = Runnable { pushNotes() }

    private fun pullNotes() {
        val q = notesQuery() ?: return
        lifecycleScope.launch {
            val remote = withContext(Dispatchers.IO) { LaptopClient.syncNotes(this@PdfViewerActivity, q, null) } ?: return@launch
            applyRemote(remote)
            // Anything only this device had goes up too.
            pushNotes()
        }
    }

    private fun pushNotes() {
        val q = notesQuery() ?: return
        val text = marks.snapshot()
        CoroutineScope(Dispatchers.IO).launch {
            val merged = LaptopClient.syncNotes(this@PdfViewerActivity, q, text) ?: return@launch
            runOnUiThread { if (!isDestroyed) applyRemote(merged) }
        }
    }

    /** Takes in the pages another device changed later, and shows them if on screen. */
    private fun applyRemote(remote: org.json.JSONObject) {
        val changed = marks.merge(remote)
        if (changed.isEmpty()) return
        for (p in changed) {
            undo.remove(p)
            redo.remove(p)
        }
        if (pageIndex in changed) b.page.invalidate()
        refreshBookmark()
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

    private val bookmarks get() = marks.bookmarks

    /** Bookmarks were kept apart before notes were synced; bring them into the document's file. */
    private fun loadBookmarks() {
        val old = VaultLock.prefs(this).getString("bm_$itemId", null) ?: return
        try {
            val a = org.json.JSONArray(old)
            for (k in 0 until a.length()) {
                val o = a.getJSONObject(k)
                if (bookmarks.none { it.page == o.getInt("p") }) {
                    bookmarks.add(Bookmark(o.getInt("p"), o.optString("t"), BookmarkGroups.all(this)[0].name))
                }
            }
            marks.touchBookmarks()
            saveMarks()
        } catch (e: Exception) {
            // Nothing usable.
        }
        VaultLock.prefs(this).edit().remove("bm_$itemId").apply()
    }

    private fun saveBookmarks() {
        marks.touchBookmarks()
        saveMarks()
        refreshBookmark()
    }

    private fun refreshBookmark() {
        val here = bookmarks.firstOrNull { it.page == pageIndex }
        b.page.bookmarked = here != null
        if (here != null) b.page.ribbonColor = BookmarkGroups.color(this, here.group)
        b.toolbar.menu.findItem(R.id.v_bookmark)?.setIcon(if (here != null) R.drawable.ic_bookmark_on else R.drawable.ic_bookmark)
        b.bookmarkStrip.set(
            renderer?.pageCount ?: 0,
            bookmarks.map { it.page to BookmarkGroups.color(this, it.group) },
        )
    }

    private fun chapterTitle(page: Int): String {
        val chapter = (links?.chapters.orEmpty().filter { it.page in 0..page } +
            printed?.chapters.orEmpty().filter { it.page in 0..page }).maxByOrNull { it.page }
        return chapter?.title?.substringBefore("  (") ?: ""
    }

    /** The bookmark button: a new page asks which group; a marked page offers its choices. */
    private fun toggleBookmark() {
        val existing = bookmarks.firstOrNull { it.page == pageIndex }
        if (existing != null) {
            editBookmark(existing)
            return
        }
        chooseGroup(getString(R.string.bm_add_to)) { group ->
            bookmarks.add(Bookmark(pageIndex, chapterTitle(pageIndex), group))
            saveBookmarks()
            Toast.makeText(this, getString(R.string.bm_added_group, pageIndex + 1, group), Toast.LENGTH_SHORT).show()
        }
    }

    private fun chooseGroup(title: String, done: (String) -> Unit) {
        val groups = BookmarkGroups.all(this)
        val labels = groups.map { g ->
            android.text.SpannableString("●  " + g.name).apply {
                setSpan(android.text.style.ForegroundColorSpan(g.color), 0, 1, 0)
            }
        } + listOf<CharSequence>(getString(R.string.bm_new_group))
        MaterialAlertDialogBuilder(this)
            .setTitle(title)
            .setItems(labels.toTypedArray()) { _, which ->
                if (which < groups.size) done(groups[which].name) else askText(getString(R.string.bm_new_group), "") { name ->
                    done(BookmarkGroups.add(this, name).name)
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun editBookmark(bm: Bookmark) {
        val items = arrayOf(getString(R.string.bm_rename), getString(R.string.bm_move_group), getString(R.string.bm_delete))
        MaterialAlertDialogBuilder(this)
            .setTitle(getString(R.string.pdf_page_short, bm.page + 1) + if (bm.title.isNotEmpty()) "  ·  ${bm.title}" else "")
            .setItems(items) { _, which ->
                when (which) {
                    0 -> askText(getString(R.string.bm_name), bm.title) { bm.title = it; saveBookmarks() }
                    1 -> chooseGroup(getString(R.string.bm_move_group)) { bm.group = it; saveBookmarks() }
                    else -> {
                        bookmarks.remove(bm)
                        saveBookmarks()
                        Toast.makeText(this, R.string.bm_removed, Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun askText(title: String, value: String, done: (String) -> Unit) {
        val input = EditText(this).apply {
            setText(value)
            setSingleLine()
            setSelection(text.length)
        }
        val box = FrameLayout(this).apply {
            setPadding(dp(20), dp(8), dp(20), 0)
            addView(input)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(title)
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ -> input.text.toString().trim().takeIf { it.isNotEmpty() }?.let(done) }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** The bookmarks on their own, by group, with page numbers. */
    private fun showBookmarks() {
        if (bookmarks.isEmpty()) {
            Toast.makeText(this, R.string.bm_none, Toast.LENGTH_LONG).show()
            return
        }
        val labels = ArrayList<CharSequence>()
        val targets = ArrayList<Bookmark?>()
        for (g in BookmarkGroups.all(this) + bookmarks.map { it.group }.distinct()
            .filter { n -> BookmarkGroups.all(this).none { it.name == n } }.map { BookmarkGroups.Group(it, BookmarkGroups.color(this, it)) }) {
            val inGroup = bookmarks.filter { it.group == g.name }.sortedBy { it.page }
            if (inGroup.isEmpty()) continue
            labels.add(android.text.SpannableString("●  " + g.name).apply {
                setSpan(android.text.style.ForegroundColorSpan(g.color), 0, 1, 0)
                setSpan(android.text.style.StyleSpan(android.graphics.Typeface.BOLD), 0, length, 0)
            })
            targets.add(null)
            for (bm in inGroup) {
                labels.add("      " + getString(R.string.pdf_page_short, bm.page + 1) + if (bm.title.isNotEmpty()) "  ·  ${bm.title}" else "")
                targets.add(bm)
            }
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.bm_list)
            .setItems(labels.toTypedArray()) { _, which -> targets[which]?.let { jump(it.page) } }
            .setNegativeButton(R.string.cancel, null)
            .show()
        dialog.listView?.setOnItemLongClickListener { _, _, position, _ ->
            val bm = targets.getOrNull(position) ?: return@setOnItemLongClickListener false
            dialog.dismiss()
            editBookmark(bm)
            true
        }
    }

    // ---- selected text ----

    private fun onTextSelected(text: String) {
        val items = arrayOf(getString(R.string.sel_highlight), getString(R.string.sel_copy),
            getString(R.string.ai_explain_sel), getString(R.string.ai_ask_sel))
        MaterialAlertDialogBuilder(this)
            .setTitle(text.replace('\n', ' ').take(80) + if (text.length > 80) "…" else "")
            .setItems(items) { _, which ->
                if (which == 2 || which == 3) {
                    b.page.clearSelection()
                    if (which == 2) askAssistant(text, getString(R.string.ai_p_explain_sel)) else askAssistant(text)
                } else if (which == 0) {
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

    // ---- the study assistant ----

    /** From the menu: about the whole page; from a selection: about the chosen words. */
    /** Gemini about this page: the page as a picture (figures and tables too), and any selected words. */
    private fun askAssistant(selected: String?, start: String? = null) {
        val bmp = (b.page.drawable as? android.graphics.drawable.BitmapDrawable)?.bitmap
        val jpeg = bmp?.let {
            // About 1000 px wide: the text stays readable to Gemini, and the picture is light to send.
            val w = minOf(1000, it.width)
            val small = if (it.width > w) Bitmap.createScaledBitmap(it, w, (it.height.toFloat() * w / it.width).toInt(), true) else it
            java.io.ByteArrayOutputStream().also { o -> small.compress(Bitmap.CompressFormat.JPEG, 72, o) }.toByteArray()
        }
        AiChatActivity.open(this, jpeg, selected, b.toolbar.title?.toString().orEmpty().removeSuffix(".pdf"), pageIndex + 1, start)
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
                labels.add(android.text.SpannableString("🔖  " + getString(R.string.pdf_page_short, bm.page + 1) +
                    "  ·  " + bm.group + if (bm.title.isNotEmpty()) "  ·  ${bm.title}" else ""))
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
                editBookmark(bm)
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
