package com.saudi.privatevault

import android.content.Context
import android.graphics.RectF
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.io.MemoryUsageSetting
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionGoTo
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionURI
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.destination.PDDestination
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.destination.PDNamedDestination
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.destination.PDPageDestination
import com.tom_roush.pdfbox.pdmodel.interactive.documentnavigation.outline.PDOutlineNode
import java.io.Closeable
import java.io.File

/**
 * What PdfRenderer cannot see: the book's table of contents (bookmarks) and
 * the links on each page, such as a contents page whose lines jump to their
 * chapter. Not thread safe: use from one thread at a time.
 */
class PdfLinks private constructor(private val doc: PDDocument) : Closeable {

    class Chapter(val title: String, val level: Int, val page: Int)

    /** A tappable area in page points, top-left origin; [page] for jumps inside the book, else [uri]. */
    class Link(val area: RectF, val page: Int, val uri: String?)

    class PageLinks(val width: Float, val height: Float, val links: List<Link>)

    private val cache = HashMap<Int, PageLinks>()

    val chapters: List<Chapter> by lazy {
        val out = mutableListOf<Chapter>()
        try {
            doc.documentCatalog.documentOutline?.let { walk(it, 0, out) }
        } catch (e: Exception) {
            // A broken outline just means no contents list.
        }
        out
    }

    private fun walk(node: PDOutlineNode, level: Int, out: MutableList<Chapter>) {
        var item = node.firstChild
        var guard = 0
        while (item != null && guard++ < 10_000) {
            val page = try {
                item.findDestinationPage(doc)?.let { doc.pages.indexOf(it) } ?: -1
            } catch (e: Exception) {
                -1
            }
            out.add(Chapter(item.title?.trim().orEmpty(), level, page))
            if (level < 6) walk(item, level + 1, out)
            item = item.nextSibling
        }
    }

    fun linksOn(index: Int): PageLinks? = cache.getOrPut(index) {
        try {
            val page = doc.getPage(index)
            val box = page.cropBox
            val links = mutableListOf<Link>()
            if (page.rotation % 360 == 0) {
                for (a in page.annotations) {
                    if (a !is PDAnnotationLink) continue
                    val r = a.rectangle ?: continue
                    val action = a.action
                    val target = if (action is PDActionURI) -1 else pageOf(a.destination ?: (action as? PDActionGoTo)?.destination)
                    val uri = (action as? PDActionURI)?.uri
                    if (target < 0 && uri == null) continue
                    // PDF counts up from the bottom; the screen counts down from the top.
                    links.add(
                        Link(
                            RectF(
                                r.lowerLeftX - box.lowerLeftX, box.upperRightY - r.upperRightY,
                                r.upperRightX - box.lowerLeftX, box.upperRightY - r.lowerLeftY,
                            ),
                            target, uri,
                        )
                    )
                }
            }
            PageLinks(box.width, box.height, links)
        } catch (e: Exception) {
            PageLinks(1f, 1f, emptyList())
        }
    }

    private fun pageOf(dest: PDDestination?): Int {
        var d = dest
        if (d is PDNamedDestination) d = doc.documentCatalog.findNamedDestinationPage(d)
        return if (d is PDPageDestination) d.retrievePageNumber() else -1
    }

    override fun close() = doc.close()

    companion object {
        fun open(ctx: Context, file: File): PdfLinks? = try {
            PDFBoxResourceLoader.init(ctx.applicationContext)
            // Spill to a temp file rather than hold a large book in memory.
            PdfLinks(PDDocument.load(file, MemoryUsageSetting.setupTempFileOnly()))
        } catch (e: Throwable) {
            null
        }
    }
}
