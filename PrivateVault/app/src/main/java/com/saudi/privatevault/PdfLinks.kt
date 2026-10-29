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
import com.tom_roush.pdfbox.text.PDFTextStripper
import com.tom_roush.pdfbox.text.TextPosition
import org.json.JSONArray
import org.json.JSONObject
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

    // ---- printed contents ----
    //
    // Many books print their contents ("Lift ....... 5-3") without making the
    // lines links. Each page's footer says which printed number it carries,
    // so "5-3" in the contents is the page whose footer reads 5-3.

    /** A printed page number on a contents page, in page points with a top-left origin. */
    class LabelBox(val area: RectF, val label: String)

    class Printed(val labels: List<String?>, val toc: List<Pair<String, String>>, val boxes: Map<Int, List<LabelBox>>) {
        private val firstPage = HashMap<String, Int>().also { m ->
            labels.forEachIndexed { i, l -> if (l != null && l !in m) m[l] = i }
        }

        fun pageOf(label: String): Int = firstPage[label] ?: -1

        /** The contents in book order, only lines whose page was found. */
        val chapters: List<Chapter> by lazy {
            val seen = HashSet<Pair<String, Int>>()
            toc.mapNotNull { (title, label) ->
                val p = pageOf(label)
                if (p < 0 || !seen.add(title to p)) null else Chapter("$title  ($label)", 0, p)
            }.sortedBy { it.page }
        }

        /** The contents line nearest to a tap: same line, the number to its right, not across columns. */
        fun hit(page: Int, x: Float, y: Float, pageWidth: Float): Int {
            var best: LabelBox? = null
            var bestScore = Float.MAX_VALUE
            for (b in boxes[page].orEmpty()) {
                if (b.area.right < x - 8) continue
                val dx = maxOf(0f, b.area.left - x)
                if (dx > pageWidth * 0.55f) continue
                val dy = kotlin.math.abs(b.area.centerY() - y)
                if (dy > 11f) continue
                val score = dy * 4 + dx / 50
                if (score < bestScore) {
                    bestScore = score
                    best = b
                }
            }
            return best?.let { pageOf(it.label) } ?: -1
        }

        fun toJson(): String {
            val bx = JSONObject()
            for ((p, list) in boxes) {
                bx.put(p.toString(), JSONArray(list.map { JSONArray(listOf(it.area.left, it.area.top, it.area.right, it.area.bottom, it.label)) }))
            }
            return JSONObject()
                .put("labels", JSONArray(labels.map { it ?: JSONObject.NULL }))
                .put("toc", JSONArray(toc.map { JSONArray(listOf(it.first, it.second)) }))
                .put("boxes", bx)
                .toString()
        }

        companion object {
            fun fromJson(s: String): Printed {
                val o = JSONObject(s)
                val la = o.getJSONArray("labels")
                val labels = (0 until la.length()).map { if (la.isNull(it)) null else la.getString(it) }
                val ta = o.getJSONArray("toc")
                val toc = (0 until ta.length()).map { ta.getJSONArray(it).let { e -> e.getString(0) to e.getString(1) } }
                val bo = o.getJSONObject("boxes")
                val boxes = HashMap<Int, List<LabelBox>>()
                for (k in bo.keys()) {
                    val arr = bo.getJSONArray(k)
                    boxes[k.toInt()] = (0 until arr.length()).map { i ->
                        val e = arr.getJSONArray(i)
                        LabelBox(
                            RectF(e.getDouble(0).toFloat(), e.getDouble(1).toFloat(), e.getDouble(2).toFloat(), e.getDouble(3).toFloat()),
                            e.getString(4),
                        )
                    }
                }
                return Printed(labels, toc, boxes)
            }
        }
    }

    private class ChunkStripper : PDFTextStripper() {
        val chunks = ArrayList<Pair<String, List<TextPosition>>>()

        override fun writeString(text: String, textPositions: MutableList<TextPosition>) {
            chunks.add(text to ArrayList(textPositions))
            super.writeString(text, textPositions)
        }
    }

    private var stripper: ChunkStripper? = null
    private val readLabels = ArrayList<String?>()
    private val readToc = ArrayList<Pair<String, String>>()
    private val readBoxes = HashMap<Int, List<LabelBox>>()

    val pageCount: Int get() = doc.numberOfPages

    /** Reads one page's printed number (and, near the front, its contents lines). Call for 0, 1, 2… in order. */
    fun readPage(i: Int) {
        val s = stripper ?: ChunkStripper().also { stripper = it }
        s.chunks.clear()
        s.startPage = i + 1
        s.endPage = i + 1
        val text = try {
            s.getText(doc)
        } catch (e: Exception) {
            ""
        }
        val label = LABEL_LINE.findAll(text).lastOrNull()?.groupValues?.get(1)?.lowercase()
        readLabels.add(label)
        // Contents pages sit near the front of a book.
        if (i >= 40) return
        val entries = TOC_LINE.findAll(text).map { m ->
            m.groupValues[1].trim(' ', '.', '\t') to m.groupValues[2].lowercase()
        }.filter { it.first.length >= 2 }.toList()
        if (entries.isEmpty()) return
        readToc.addAll(entries)
        val boxes = ArrayList<LabelBox>()
        for ((chunk, positions) in s.chunks) {
            val m = LABEL_END.find(chunk) ?: continue
            val lab = m.groupValues[1].lowercase()
            val alone = chunk.trim().equals(lab, ignoreCase = true)
            if ((!alone && !chunk.contains("..")) || lab == label || positions.isEmpty()) continue
            val tail = positions.subList(maxOf(0, positions.size - lab.length), positions.size)
            val r = RectF(Float.MAX_VALUE, Float.MAX_VALUE, -Float.MAX_VALUE, -Float.MAX_VALUE)
            for (p in tail) {
                r.left = minOf(r.left, p.xDirAdj)
                r.right = maxOf(r.right, p.xDirAdj + p.widthDirAdj)
                r.top = minOf(r.top, p.yDirAdj - p.heightDir)
                r.bottom = maxOf(r.bottom, p.yDirAdj)
            }
            boxes.add(LabelBox(r, lab))
        }
        if (boxes.isNotEmpty()) readBoxes[i] = boxes
    }

    fun printed() = Printed(ArrayList(readLabels), ArrayList(readToc), HashMap(readBoxes))

    // ---- the letters on a page, for selecting text ----

    /** One letter, as fractions of the page with a top-left origin. */
    class CharBox(val ch: String, val left: Float, val top: Float, val right: Float, val bottom: Float)

    private class LetterStripper : PDFTextStripper() {
        val letters = ArrayList<TextPosition>()

        override fun writeString(text: String, textPositions: MutableList<TextPosition>) {
            letters.addAll(textPositions)
            super.writeString(text, textPositions)
        }
    }

    private val letterCache = HashMap<Int, List<CharBox>>()

    /** The page's text, for the study assistant. */
    fun textOf(index: Int): String = try {
        val s = PDFTextStripper()
        s.startPage = index + 1
        s.endPage = index + 1
        s.getText(doc).trim()
    } catch (e: Exception) {
        ""
    }

    /** The page's letters in reading order (the order the book stores them, so columns stay apart). */
    fun lettersOn(index: Int): List<CharBox> = letterCache.getOrPut(index) {
        try {
            val page = doc.getPage(index)
            if (page.rotation % 360 != 0) return@getOrPut emptyList()
            val box = page.cropBox
            val s = LetterStripper()
            s.startPage = index + 1
            s.endPage = index + 1
            s.getText(doc)
            s.letters.mapNotNull { p ->
                val ch = p.unicode ?: return@mapNotNull null
                if (ch.isBlank()) return@mapNotNull null
                // Letters report their height above the baseline; a little more makes a full line band.
                val h = maxOf(p.heightDir, p.fontSizeInPt * 0.7f)
                val left = p.xDirAdj
                val right = p.xDirAdj + p.widthDirAdj
                val bottom = p.yDirAdj + h * 0.28f
                val top = p.yDirAdj - h * 1.05f
                CharBox(ch, left / box.width, top / box.height, right / box.width, bottom / box.height)
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    override fun close() = doc.close()

    companion object {
        private const val LABEL = "(?:\\d{1,2}-\\d{1,3}|[ivxlcdm]{1,7})"
        private val LABEL_LINE = Regex("^\\s*($LABEL)\\s*$", setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE))
        private val TOC_LINE = Regex("([^\\n.][^\\n]*?)[ \\t]*\\n?[ \\t]*\\.{3,}[ \\t]*\\n?[ \\t]*($LABEL)(?=\\s|$)", RegexOption.IGNORE_CASE)
        private val LABEL_END = Regex("($LABEL)\\s*$", RegexOption.IGNORE_CASE)

        fun open(ctx: Context, file: File): PdfLinks? = try {
            PDFBoxResourceLoader.init(ctx.applicationContext)
            // Spill to a temp file rather than hold a large book in memory.
            PdfLinks(PDDocument.load(file, MemoryUsageSetting.setupTempFileOnly()))
        } catch (e: Throwable) {
            null
        }
    }
}
