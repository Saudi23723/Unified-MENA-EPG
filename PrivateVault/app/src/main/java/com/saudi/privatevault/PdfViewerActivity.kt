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
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.Toast
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
    private var pageIndex = 0
    private var itemId = ""

    // Width in pixels of the bitmap now shown, to turn a tap into page points.
    private var shownWidth = 0
    private var shownIndex = -1

    // Pages left by following a link or the contents, so Back returns to them.
    private val history = ArrayList<Int>()

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
        b.toolbar.title = item.name
        b.toolbar.setNavigationOnClickListener { finish() }
        b.toolbar.inflateMenu(R.menu.reader_menu)
        b.toolbar.setOnMenuItemClickListener { mi ->
            when (mi.itemId) {
                R.id.v_read_mode -> ReadingMode.choose(this) { applyMode(it) }
                R.id.v_contents -> showContents()
                R.id.v_goto -> askPage()
                else -> Viewers.openWith(this, item)
            }
            true
        }
        applyMode(ReadingMode.current(this))
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

        val file = VaultStore.fileOf(item)
        lifecycleScope.launch {
            val l = withContext(linkThread) { PdfLinks.open(this@PdfViewerActivity, file)?.also { it.chapters } }
            if (l == null) return@launch
            if (isDestroyed) {
                CoroutineScope(linkThread).launch { l.close() }
                return@launch
            }
            links = l
            b.toolbar.menu.findItem(R.id.v_contents).isVisible = true
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
                b.page.setImageBitmap(bmp)
            }
        }
    }

    // ---- links and contents ----

    private fun tapped(x: Float, y: Float) {
        val l = links ?: return
        val index = shownIndex
        if (index != pageIndex || shownWidth <= 0) return
        val width = shownWidth
        lifecycleScope.launch {
            val pageLinks = withContext(linkThread) { l.linksOn(index) } ?: return@launch
            if (pageLinks.links.isEmpty()) return@launch
            val scale = width / pageLinks.width
            val px = x / scale
            val py = y / scale
            // A little slack around each link, as fingers are wider than the text.
            val slack = 6f
            val hit = pageLinks.links.firstOrNull {
                px >= it.area.left - slack && px <= it.area.right + slack &&
                    py >= it.area.top - slack && py <= it.area.bottom + slack
            } ?: return@launch
            if (hit.page >= 0) jump(hit.page) else hit.uri?.let { openUri(it) }
        }
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

    private fun showContents() {
        val chapters = links?.chapters.orEmpty().filter { it.page >= 0 }
        if (chapters.isEmpty()) {
            Toast.makeText(this, R.string.pdf_no_contents, Toast.LENGTH_LONG).show()
            return
        }
        val labels = chapters.map { c ->
            " ".repeat(c.level) + c.title + "  ·  " + getString(R.string.pdf_page_short, c.page + 1)
        }.toTypedArray()
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pdf_contents)
            .setItems(labels) { _, which -> jump(chapters[which].page) }
            .setNegativeButton(R.string.cancel, null)
            .show()
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
