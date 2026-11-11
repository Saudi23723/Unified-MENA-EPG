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
        // A heading with no page of its own (a part title) opens where its first section does.
        for (i in out.indices) if (out[i].page < 0) {
            val next = (i + 1 until out.size).firstOrNull { out[it].page >= 0 && out[it].level > out[i].level }
            if (next != null) out[i] = Chapter(out[i].title, out[i].level, out[next].page)
        }
        // The same line twice (some books repeat the outline) shown once; empty titles dropped.
        val seen = HashSet<String>()
        out.filter { it.title.isNotBlank() && seen.add("${it.level}|${it.title}|${it.page}") }
    }

    private fun walk(node: PDOutlineNode, level: Int, out: MutableList<Chapter>) {
        var item = node.firstChild
        var guard = 0
        while (item != null && guard++ < 10_000) {
            // The page: a direct destination, a named one, or a "go to" action; whichever the book used.
            var page = try { item.findDestinationPage(doc)?.let { doc.pages.indexOf(it) } ?: -1 } catch (e: Exception) { -1 }
            if (page < 0) page = try { pageOf(item.destination ?: (item.action as? PDActionGoTo)?.destination) } catch (e: Exception) { -1 }
            if (page >= doc.numberOfPages) page = -1
            val title = (item.title ?: "").replace(Regex("\\s+"), " ").trim()
            out.add(Chapter(title, level, page))
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
        if (d !is PDPageDestination) return -1
        // A destination given as a page object, or (in some books) as a bare page number.
        val n = d.retrievePageNumber()
        return if (n >= 0) n else d.pageNumber.takeIf { it in 0 until doc.numberOfPages } ?: -1
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

    /**
     * A chart that prints its latitude and longitude along its border (FAA airport diagrams do):
     * where each coordinate falls on the page, so the aircraft can be drawn on it. As page fractions:
     * x = ax·lon + bx, y = ay·lat + by. Null when the page has no such scale.
     */
    class Geo(val ax: Double, val bx: Double, val ay: Double, val by: Double) {
        fun at(lat: Double, lon: Double) = floatArrayOf((ax * lon + bx).toFloat(), (ay * lat + by).toFloat())
    }

    private val COORD = Regex("(\\d{2,3})\\s*[°º˚]\\s*(\\d{1,2}(?:\\.\\d+)?)\\s*['′’]?\\s*([NSEW])")

    fun georef(index: Int): Geo? = try {
        val page = doc.getPage(index)
        val w = page.cropBox.width.toDouble(); val h = page.cropBox.height.toDouble()
        val s = ChunkStripper().apply { startPage = index + 1; endPage = index + 1; sortByPosition = true }
        s.getText(doc)
        val lats = ArrayList<Pair<Double, Double>>()   // latitude, y fraction
        val lons = ArrayList<Pair<Double, Double>>()   // longitude, x fraction
        for ((text, pos) in s.chunks) {
            if (pos.isEmpty()) continue
            for (m in COORD.findAll(text)) {
                val v = m.groupValues[1].toDouble() + m.groupValues[2].toDouble() / 60.0
                // The label's middle, from the glyphs that make it up.
                val glyphs = pos.subList(minOf(m.range.first, pos.size - 1), minOf(m.range.last + 1, pos.size))
                if (glyphs.isEmpty()) continue
                val cx = glyphs.map { it.x + it.width / 2.0 }.average() / w
                val cy = glyphs.map { it.y - it.height / 2.0 }.average() / h
                when (m.groupValues[3]) {
                    "N" -> lats.add(v to cy); "S" -> lats.add(-v to cy)
                    "E" -> lons.add(v to cx); "W" -> lons.add(-v to cx)
                }
            }
        }
        fun fit(pts: List<Pair<Double, Double>>): Pair<Double, Double>? {
            if (pts.map { it.first }.distinct().size < 2) return null
            val mx = pts.map { it.first }.average(); val my = pts.map { it.second }.average()
            val sxx = pts.sumOf { (it.first - mx) * (it.first - mx) }
            if (sxx == 0.0) return null
            val a = pts.sumOf { (it.first - mx) * (it.second - my) } / sxx
            val b = my - a * mx
            // Every label must sit on the line: a scale, not stray numbers in the notes.
            if (pts.any { Math.abs(a * it.first + b - it.second) > 0.04 }) return null
            return a to b
        }
        val x = fit(lons); val y = fit(lats)
        // North up, east to the right.
        if (x == null || y == null || x.first <= 0 || y.first >= 0) byFixes(index, s.chunks, w, h) else Geo(x.first, x.second, y.first, y.second)
    } catch (e: Exception) { null }

    private val NOT_FIX = setOf("RWY", "MAP", "MDA", "TDZE", "APP", "CRS", "ILS", "LOC", "GPS", "RNAV", "VOR", "DME", "NDB", "MSA",
        "ATIS", "TWR", "GND", "CLNC", "DEL", "UNICOM", "CTAF", "ASOS", "AWOS", "NOTE", "ELEV", "FAF", "IAF", "IF", "MAP", "HAT", "HAA",
        "TCH", "GS", "VGSI", "PAPI", "VASI", "REIL", "MIRL", "HIRL", "MALSR", "ODALS", "LNAV", "VNAV", "LPV", "MIN", "MAX", "NM", "FT",
        "AND", "THE", "FOR", "NOT", "ALL", "CAT", "NA", "AIRPORT", "CIRCLING", "STRAIGHT", "TERPS", "WAAS", "CHAN", "APCH", "SEE",
        "LIMITS", "ALTERNATE", "TAKEOFF", "AMDT", "ORIG", "PROC", "FAA", "SW", "NE", "NW", "SE", "MSL", "AGL", "KIAS", "KNOTS", "CLIMB",
        "DIRECT", "HOLD", "LEFT", "RIGHT", "TURN", "THEN", "VIA", "FROM", "TO", "MISSED", "APPROACH", "CONTINUE", "INOP", "DIST", "SIM")

    /**
     * An approach chart has no latitude and longitude printed, but its plan view names its fixes
     * and navaids where they are. Their real positions (aviationweather.gov) against where their
     * names sit on the page give the chart's scale; pairs of fixes vote (a RANSAC fit) so a name
     * met in the notes or the profile cannot spoil it. Labels sit beside their symbols, so it is
     * good to a fraction of a mile — enough to see the airplane on the plan view, not to navigate.
     */
    private fun byFixes(index: Int, chunks: List<Pair<String, List<TextPosition>>>, w: Double, h: Double): Geo? {
        // Only an instrument approach chart: its briefing strip says so.
        val all = chunks.joinToString(" ") { it.first }
        if (!("TDZE" in all || "APP CRS" in all || "MISSED APCH" in all || "MISSED APPROACH" in all)) return null
        val word = Regex("\\b[A-Z]{3,5}\\b")
        val found = HashMap<String, MutableList<DoubleArray>>()
        for ((text, pos) in chunks) {
            if (pos.isEmpty()) continue
            for (m in word.findAll(text)) {
                val id = m.value
                if (id in NOT_FIX) continue
                val glyphs = pos.subList(minOf(m.range.first, pos.size - 1), minOf(m.range.last + 1, pos.size))
                if (glyphs.isEmpty()) continue
                val cx = glyphs.map { it.x + it.width / 2.0 }.average() / w
                val cy = glyphs.map { it.y - it.height / 2.0 }.average() / h
                // The plan view: between the briefing strip and the profile.
                if (cy < 0.14 || cy > 0.68) continue
                found.getOrPut(id) { ArrayList() }.add(doubleArrayOf(cx, cy))
            }
        }
        if (found.size < 3) return null
        val ids = found.keys.take(45)
        val where = HashMap<String, DoubleArray>()
        fun fetch(kind: String, list: List<String>) {
            if (list.isEmpty()) return
            try {
                val arr = org.json.JSONArray(AviationData.get("https://aviationweather.gov/api/data/$kind?ids=${list.joinToString(",")}&format=json", 12000))
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: continue
                    val id = (o.optString("id").ifEmpty { o.optString("ident") }).uppercase()
                    val lat = o.optDouble("lat", o.optDouble("latitude", Double.NaN))
                    val lon = o.optDouble("lon", o.optDouble("longitude", Double.NaN))
                    if (id.isNotEmpty() && !lat.isNaN() && !lon.isNaN() && id !in where) where[id] = doubleArrayOf(lat, lon)
                }
            } catch (e: Exception) { }
        }
        fetch("fix", ids.filter { it.length == 5 })
        fetch("navaid", ids.filter { it.length <= 4 })
        // Keep what lies together: a three-letter name can belong to a navaid on another continent.
        if (where.size < 3) return null
        val mLat = where.values.map { it[0] }.sorted()[where.size / 2]
        val mLon = where.values.map { it[1] }.sorted()[where.size / 2]
        class P(val lat: Double, val lon: Double, val x: Double, val y: Double)
        val pts = ArrayList<P>()
        for ((id, ll) in where) {
            if (Math.abs(ll[0] - mLat) > 1.0 || Math.abs(ll[1] - mLon) > 1.3) continue
            for (xy in found[id] ?: continue) pts += P(ll[0], ll[1], xy[0], xy[1])
        }
        if (pts.size < 3) return null
        val cosLat = Math.cos(Math.toRadians(mLat))
        var best: List<P> = emptyList()
        for (i in pts.indices) for (j in i + 1 until pts.size) {
            val a = pts[i]; val b = pts[j]
            if (Math.abs(a.lon - b.lon) < 0.02 || Math.abs(a.lat - b.lat) < 0.02) continue
            val ax = (a.x - b.x) / (a.lon - b.lon); val ay = (a.y - b.y) / (a.lat - b.lat)
            if (ax <= 0 || ay >= 0) continue
            // One scale both ways on the page (points per nautical mile).
            val sx = ax * w / (60 * cosLat); val sy = -ay * h / 60
            if (sx / sy !in 0.8..1.25) continue
            val bx = a.x - ax * a.lon; val by = a.y - ay * a.lat
            val inl = pts.filter { Math.abs(ax * it.lon + bx - it.x) < 0.02 && Math.abs(ay * it.lat + by - it.y) < 0.02 }
            if (inl.size > best.size) best = inl
        }
        if (best.map { "${it.lat},${it.lon}" }.distinct().size < 3) return null
        fun ls(u: List<Double>, v: List<Double>): Pair<Double, Double> {
            val mu = u.average(); val mv = v.average()
            val a = u.indices.sumOf { (u[it] - mu) * (v[it] - mv) } / u.indices.sumOf { (u[it] - mu) * (u[it] - mu) }
            return a to (mv - a * mu)
        }
        val (ax, bx) = ls(best.map { it.lon }, best.map { it.x })
        val (ay, by) = ls(best.map { it.lat }, best.map { it.y })
        return if (ax > 0 && ay < 0) Geo(ax, bx, ay, by) else null
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
