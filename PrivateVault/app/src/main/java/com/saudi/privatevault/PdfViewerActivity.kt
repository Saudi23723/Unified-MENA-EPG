package com.saudi.privatevault

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import com.saudi.privatevault.databinding.ActivityPdfBinding
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class PdfViewerActivity : BaseActivity() {

    private lateinit var b: ActivityPdfBinding
    private var renderer: PdfRenderer? = null
    private var pageIndex = 0
    private var itemId = ""

    // PdfRenderer allows one page at a time, so every render goes through one thread.
    @OptIn(ExperimentalCoroutinesApi::class)
    private val pdfThread = Dispatchers.IO.limitedParallelism(1)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityPdfBinding.inflate(layoutInflater)
        setContentView(b.root)
        val item = VaultStore.item(intent.getStringExtra(Viewers.EXTRA_ID)) ?: return finish()
        itemId = item.id
        b.toolbar.title = item.name
        b.toolbar.setNavigationOnClickListener { finish() }
        b.toolbar.inflateMenu(R.menu.viewer_menu)
        b.toolbar.setOnMenuItemClickListener { Viewers.openWith(this, item); true }

        renderer = try {
            PdfRenderer(ParcelFileDescriptor.open(VaultStore.fileOf(item), ParcelFileDescriptor.MODE_READ_ONLY))
        } catch (e: Exception) {
            null
        }
        if (renderer == null || renderer!!.pageCount == 0) {
            // Protected or unusual PDFs: let another app try.
            Toast.makeText(this, R.string.open_failed, Toast.LENGTH_SHORT).show()
            Viewers.openWith(this, item)
            return finish()
        }
        // Reopening a document goes back to the page it was left on.
        pageIndex = savedInstanceState?.getInt("page")
            ?: VaultLock.prefs(this).getInt("pdf_$itemId", 0)
        b.prev.setOnClickListener { go(pageIndex - 1) }
        b.next.setOnClickListener { go(pageIndex + 1) }
        b.page.onSwipe = { dir -> go(pageIndex + dir) }
        b.page.post { show() }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putInt("page", pageIndex)
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
    }

    private fun go(i: Int) {
        val count = renderer?.pageCount ?: return
        if (i < 0 || i >= count) return
        pageIndex = i
        show()
    }

    private fun show() {
        val r = renderer ?: return
        val count = r.pageCount
        pageIndex = pageIndex.coerceIn(0, count - 1)
        val index = pageIndex
        b.pageNumber.text = getString(R.string.page_of, index + 1, count)
        b.prev.isEnabled = index > 0
        b.next.isEnabled = index < count - 1
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
            if (bmp != null && index == pageIndex) b.page.setImageBitmap(bmp)
        }
    }
}
