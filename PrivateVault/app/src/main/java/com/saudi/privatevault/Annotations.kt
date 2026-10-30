package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/** What the reader is doing on the page. */
enum class Tool { HAND, SELECT, PEN, HIGHLIGHT, ERASER, LINE, ARROW, RECT, OVAL, TEXT, TEXTMARK }

/**
 * One thing written on a page. Points are fractions of the page (0..1 of its
 * width and height) and [width] a fraction of the page width, so a mark stays
 * on the same words at any zoom, screen or render size.
 */
class Mark(
    val tool: Tool,
    var color: Int,
    var width: Float,
    val points: FloatArray,
    val text: String? = null,
    /** Highlights only: rounded ends instead of square ones. */
    var round: Boolean = false,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("t", tool.name)
        .put("c", color)
        .put("w", width.toDouble())
        .put("p", JSONArray().also { a -> points.forEach { a.put(it.toDouble()) } })
        .also { if (text != null) it.put("s", text) }
        .also { if (round) it.put("r", 1) }

    companion object {
        fun fromJson(o: JSONObject): Mark? = try {
            val p = o.getJSONArray("p")
            Mark(
                Tool.valueOf(o.getString("t")), o.getInt("c"), o.getDouble("w").toFloat(),
                FloatArray(p.length()) { p.getDouble(it).toFloat() }, o.optString("s").ifEmpty { null },
                o.optInt("r", 0) == 1,
            )
        } catch (e: Exception) {
            null
        }
    }
}

/** A page kept to come back to, in a named group (each group has its colour). */
class Bookmark(val page: Int, var title: String, var group: String)

/**
 * Every page's marks and the bookmarks of one document, kept in the app's
 * private storage. Each page and the bookmark list carry the time they last
 * changed, so copies from two devices merge page by page, newest wins.
 */
class DocumentMarks(private val file: File) {
    val pages = HashMap<Int, MutableList<Mark>>()
    val stamps = HashMap<Int, Long>()
    val bookmarks = ArrayList<Bookmark>()
    var bookmarksStamp = 0L

    fun on(page: Int): MutableList<Mark> = pages.getOrPut(page) { mutableListOf() }

    fun touch(page: Int) {
        stamps[page] = System.currentTimeMillis()
    }

    fun touchBookmarks() {
        bookmarksStamp = System.currentTimeMillis()
    }

    fun load(): DocumentMarks {
        try {
            read(JSONObject(file.readText()))
        } catch (e: Exception) {
            // Nothing written yet.
        }
        return this
    }

    private fun read(o: JSONObject) {
        val pg = o.optJSONObject("pages") ?: JSONObject()
        val ts = o.optJSONObject("t") ?: JSONObject()
        for (k in pg.keys()) {
            val a = pg.getJSONArray(k)
            val list = on(k.toInt())
            list.clear()
            list.addAll((0 until a.length()).mapNotNull { Mark.fromJson(a.getJSONObject(it)) })
            stamps[k.toInt()] = ts.optLong(k, 0L)
        }
        o.optJSONObject("bm")?.let { bm ->
            bookmarksStamp = bm.optLong("t", 0L)
            bookmarks.clear()
            val a = bm.optJSONArray("list") ?: JSONArray()
            for (i in 0 until a.length()) {
                val b = a.getJSONObject(i)
                bookmarks.add(Bookmark(b.getInt("p"), b.optString("n"), b.optString("g")))
            }
        }
    }

    fun toJson(): JSONObject {
        val pg = JSONObject()
        val ts = JSONObject()
        for ((page, marks) in pages) {
            val t = stamps[page] ?: 0L
            // An emptied page is kept (empty) so the emptying reaches other devices.
            if (marks.isEmpty() && t == 0L) continue
            pg.put(page.toString(), JSONArray(marks.map { it.toJson() }))
            ts.put(page.toString(), t)
        }
        val bm = JSONArray()
        for (b in bookmarks.sortedBy { it.page }) bm.put(JSONObject().put("p", b.page).put("n", b.title).put("g", b.group))
        return JSONObject().put("v", 2).put("pages", pg).put("t", ts)
            .put("bm", JSONObject().put("t", bookmarksStamp).put("list", bm))
    }

    /** A snapshot that can be written off the main thread. */
    fun snapshot(): String = toJson().toString()

    /**
     * Takes from another copy every page, and the bookmarks, that changed
     * there more recently. Returns the pages whose marks were replaced.
     */
    fun merge(other: JSONObject): Set<Int> {
        val incoming = DocumentMarks(file)
        incoming.read(other)
        val changed = HashSet<Int>()
        for ((page, marks) in incoming.pages) {
            if ((incoming.stamps[page] ?: 0L) > (stamps[page] ?: 0L)) {
                val list = on(page)
                list.clear()
                list.addAll(marks)
                stamps[page] = incoming.stamps[page] ?: 0L
                changed.add(page)
            }
        }
        if (incoming.bookmarksStamp > bookmarksStamp) {
            bookmarks.clear()
            bookmarks.addAll(incoming.bookmarks)
            bookmarksStamp = incoming.bookmarksStamp
            changed.add(-1)
        }
        return changed
    }

    fun write(text: String) {
        file.parentFile?.mkdirs()
        val tmp = File(file.path + ".tmp")
        tmp.writeText(text)
        if (!tmp.renameTo(file)) file.writeText(text)
    }

    fun count() = pages.values.sumOf { it.size }

    companion object {
        fun forItem(ctx: Context, itemId: String) =
            DocumentMarks(File(ctx.filesDir, "annotations/" + itemId.replace(Regex("[^A-Za-z0-9_-]"), "_") + ".json")).load()
    }
}

/** The bookmark groups, shared by all documents; each has a colour. */
object BookmarkGroups {
    class Group(val name: String, val color: Int)

    private val DEFAULTS = listOf(
        Group("عام", Color.parseColor("#E53935")),
        Group("مهم", Color.parseColor("#FB8C00")),
        Group("للمراجعة", Color.parseColor("#1E88E5")),
        Group("امتحان", Color.parseColor("#8E24AA")),
    )
    private val SPARE = intArrayOf(
        Color.parseColor("#43A047"), Color.parseColor("#00897B"), Color.parseColor("#6D4C41"),
        Color.parseColor("#F4511E"), Color.parseColor("#3949AB"), Color.parseColor("#C2185B"),
    )

    fun all(ctx: Context): List<Group> = try {
        val a = JSONArray(VaultLock.prefs(ctx).getString("bm_groups", null) ?: throw IllegalStateException())
        (0 until a.length()).map { a.getJSONObject(it).let { o -> Group(o.getString("n"), o.getInt("c")) } }
    } catch (e: Exception) {
        DEFAULTS
    }

    fun add(ctx: Context, name: String): Group {
        val list = all(ctx).toMutableList()
        list.firstOrNull { it.name == name }?.let { return it }
        val g = Group(name, SPARE[(list.size - DEFAULTS.size).coerceAtLeast(0) % SPARE.size])
        list.add(g)
        VaultLock.prefs(ctx).edit()
            .putString("bm_groups", JSONArray(list.map { JSONObject().put("n", it.name).put("c", it.color) }).toString())
            .apply()
        return g
    }

    fun color(ctx: Context, name: String): Int = all(ctx).firstOrNull { it.name == name }?.color ?: DEFAULTS[0].color
}

/** Draws marks onto a page that is [w] by [h] pixels. */
object MarkPainter {
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val path = Path()
    private val rect = RectF()

    fun draw(c: Canvas, m: Mark, w: Float, h: Float) {
        val p = m.points
        if (p.size < 2) return
        stroke.color = m.color
        stroke.strokeWidth = (m.width * w).coerceAtLeast(1f)
        when (m.tool) {
            Tool.PEN, Tool.HIGHLIGHT -> {
                // A highlighter is a broad, see-through, flat-ended band.
                stroke.strokeCap = if (m.tool == Tool.HIGHLIGHT && !m.round) Paint.Cap.SQUARE else Paint.Cap.ROUND
                if (m.tool == Tool.HIGHLIGHT) stroke.alpha = 0x70
                path.reset()
                path.moveTo(p[0] * w, p[1] * h)
                if (p.size == 2) {
                    path.lineTo(p[0] * w + 0.1f, p[1] * h)
                } else {
                    // Smooth the hand's line through the midpoints.
                    var i = 2
                    while (i < p.size) {
                        val px = p[i - 2] * w
                        val py = p[i - 1] * h
                        val cx = p[i] * w
                        val cy = p[i + 1] * h
                        path.quadTo(px, py, (px + cx) / 2f, (py + cy) / 2f)
                        i += 2
                    }
                    path.lineTo(p[p.size - 2] * w, p[p.size - 1] * h)
                }
                c.drawPath(path, stroke)
                stroke.strokeCap = Paint.Cap.ROUND
            }
            Tool.LINE, Tool.ARROW -> {
                if (p.size < 4) return
                val x0 = p[0] * w
                val y0 = p[1] * h
                val x1 = p[2] * w
                val y1 = p[3] * h
                c.drawLine(x0, y0, x1, y1, stroke)
                if (m.tool == Tool.ARROW) {
                    val a = atan2(y1 - y0, x1 - x0)
                    val len = maxOf(stroke.strokeWidth * 4f, w * 0.02f)
                    for (side in floatArrayOf(-0.5f, 0.5f)) {
                        val b = a + Math.PI.toFloat() + side
                        c.drawLine(x1, y1, x1 + len * cos(b), y1 + len * sin(b), stroke)
                    }
                }
            }
            Tool.RECT, Tool.OVAL -> {
                if (p.size < 4) return
                rect.set(minOf(p[0], p[2]) * w, minOf(p[1], p[3]) * h, maxOf(p[0], p[2]) * w, maxOf(p[1], p[3]) * h)
                if (m.tool == Tool.RECT) c.drawRect(rect, stroke) else c.drawOval(rect, stroke)
            }
            Tool.TEXTMARK -> {
                // Selected words: one band per line, exactly over the letters.
                fill.color = m.color
                fill.alpha = 0x66
                var i = 0
                while (i + 3 < p.size) {
                    if (m.round) {
                        val r = (p[i + 3] - p[i + 1]) * h * 0.45f
                        c.drawRoundRect(p[i] * w, p[i + 1] * h, p[i + 2] * w, p[i + 3] * h, r, r, fill)
                    } else {
                        c.drawRect(p[i] * w, p[i + 1] * h, p[i + 2] * w, p[i + 3] * h, fill)
                    }
                    i += 4
                }
            }
            Tool.TEXT -> {
                val s = m.text ?: return
                text.color = m.color
                text.textSize = (m.width * w).coerceAtLeast(8f)
                var y = p[1] * h
                for (line in s.split('\n')) {
                    c.drawText(line, p[0] * w, y, text)
                    y += text.textSize * 1.25f
                }
            }
            else -> {}
        }
    }

    /** Whether a point (page pixels) touches the mark, for the eraser. */
    fun hits(m: Mark, x: Float, y: Float, w: Float, h: Float, slack: Float): Boolean {
        val p = m.points
        val reach = slack + m.width * w / 2f
        fun near(ax: Float, ay: Float, bx: Float, by: Float): Boolean {
            val dx = bx - ax
            val dy = by - ay
            val len2 = dx * dx + dy * dy
            val t = if (len2 == 0f) 0f else (((x - ax) * dx + (y - ay) * dy) / len2).coerceIn(0f, 1f)
            return hypot(x - (ax + t * dx), y - (ay + t * dy)) <= reach
        }
        return when (m.tool) {
            Tool.PEN, Tool.HIGHLIGHT -> {
                if (p.size == 2) return hypot(x - p[0] * w, y - p[1] * h) <= reach
                var i = 2
                while (i < p.size) {
                    if (near(p[i - 2] * w, p[i - 1] * h, p[i] * w, p[i + 1] * h)) return true
                    i += 2
                }
                false
            }
            Tool.LINE, Tool.ARROW -> p.size >= 4 && near(p[0] * w, p[1] * h, p[2] * w, p[3] * h)
            Tool.RECT, Tool.OVAL -> {
                if (p.size < 4) return false
                val l = minOf(p[0], p[2]) * w
                val r = maxOf(p[0], p[2]) * w
                val t = minOf(p[1], p[3]) * h
                val b = maxOf(p[1], p[3]) * h
                if (m.tool == Tool.RECT) {
                    near(l, t, r, t) || near(r, t, r, b) || near(r, b, l, b) || near(l, b, l, t)
                } else {
                    val cx = (l + r) / 2f
                    val cy = (t + b) / 2f
                    val rx = (r - l) / 2f
                    val ry = (b - t) / 2f
                    (0 until 32).any { k ->
                        val a0 = k * Math.PI * 2 / 32
                        val a1 = (k + 1) * Math.PI * 2 / 32
                        near(
                            cx + rx * cos(a0).toFloat(), cy + ry * sin(a0).toFloat(),
                            cx + rx * cos(a1).toFloat(), cy + ry * sin(a1).toFloat(),
                        )
                    }
                }
            }
            Tool.TEXTMARK -> {
                var i = 0
                while (i + 3 < p.size) {
                    if (x >= p[i] * w - slack && x <= p[i + 2] * w + slack && y >= p[i + 1] * h - slack && y <= p[i + 3] * h + slack) return true
                    i += 4
                }
                false
            }
            Tool.TEXT -> {
                val s = m.text ?: return false
                text.textSize = (m.width * w).coerceAtLeast(8f)
                val lines = s.split('\n')
                val tw = lines.maxOf { text.measureText(it) }
                val th = text.textSize * 1.25f * lines.size
                val left = p[0] * w
                val top = p[1] * h - text.textSize
                x >= left - slack && x <= left + tw + slack && y >= top - slack && y <= top + th + slack
            }
            else -> false
        }
    }

    /** The mark's extent in page pixels, for selecting and moving it. */
    fun bounds(m: Mark, w: Float, h: Float): RectF {
        val p = m.points
        val r = RectF(Float.MAX_VALUE, Float.MAX_VALUE, -Float.MAX_VALUE, -Float.MAX_VALUE)
        if (m.tool == Tool.TEXT) {
            val s = m.text ?: ""
            text.textSize = (m.width * w).coerceAtLeast(8f)
            val lines = s.split('\n')
            val tw = lines.maxOf { text.measureText(it) }
            r.set(p[0] * w, p[1] * h - text.textSize, p[0] * w + tw, p[1] * h - text.textSize + text.textSize * 1.25f * lines.size)
            return r
        }
        var i = 0
        while (i + 1 < p.size) {
            r.union(p[i] * w, p[i + 1] * h)
            i += 2
        }
        val pad = m.width * w / 2f
        r.inset(-pad, -pad)
        return r
    }

    /** Colours offered for each kind of tool. */
    val INK = intArrayOf(
        // Greys
        Color.parseColor("#000000"), Color.parseColor("#424242"), Color.parseColor("#757575"),
        Color.parseColor("#BDBDBD"), Color.parseColor("#FFFFFF"), Color.parseColor("#795548"),
        // Reds and pinks
        Color.parseColor("#B71C1C"), Color.parseColor("#E53935"), Color.parseColor("#FF5252"),
        Color.parseColor("#C2185B"), Color.parseColor("#EC407A"), Color.parseColor("#F48FB1"),
        // Oranges and yellows
        Color.parseColor("#E65100"), Color.parseColor("#FB8C00"), Color.parseColor("#FFB300"),
        Color.parseColor("#FDD835"), Color.parseColor("#FFEE58"), Color.parseColor("#FF7043"),
        // Greens
        Color.parseColor("#1B5E20"), Color.parseColor("#43A047"), Color.parseColor("#7CB342"),
        Color.parseColor("#C0CA33"), Color.parseColor("#00897B"), Color.parseColor("#26A69A"),
        // Blues
        Color.parseColor("#0D47A1"), Color.parseColor("#1E88E5"), Color.parseColor("#42A5F5"),
        Color.parseColor("#00ACC1"), Color.parseColor("#26C6DA"), Color.parseColor("#3949AB"),
        // Purples
        Color.parseColor("#4A148C"), Color.parseColor("#8E24AA"), Color.parseColor("#AB47BC"),
        Color.parseColor("#5E35B1"), Color.parseColor("#7E57C2"), Color.parseColor("#B39DDB"),
    )
    val MARKER = intArrayOf(
        Color.parseColor("#FFEB3B"), Color.parseColor("#FFF176"), Color.parseColor("#FFD54F"),
        Color.parseColor("#FFAB40"), Color.parseColor("#FF8A65"), Color.parseColor("#FF8A80"),
        Color.parseColor("#FF4081"), Color.parseColor("#F48FB1"), Color.parseColor("#EA80FC"),
        Color.parseColor("#B388FF"), Color.parseColor("#82B1FF"), Color.parseColor("#40C4FF"),
        Color.parseColor("#84FFFF"), Color.parseColor("#64FFDA"), Color.parseColor("#69F0AE"),
        Color.parseColor("#76FF03"), Color.parseColor("#C6FF00"), Color.parseColor("#E0E0E0"),
    )

    /** Thin, medium and thick, as fractions of the page width. */
    /** The thinnest and thickest each kind of tool allows, as fractions of the page width. */
    fun sizeRange(tool: Tool): Pair<Float, Float> = when (tool) {
        Tool.HIGHLIGHT, Tool.TEXTMARK -> 0.005f to 0.06f
        Tool.TEXT -> 0.01f to 0.08f
        else -> 0.0006f to 0.016f
    }

    fun widths(tool: Tool): FloatArray = when (tool) {
        Tool.HIGHLIGHT -> floatArrayOf(0.016f, 0.024f, 0.034f)
        Tool.TEXT -> floatArrayOf(0.02f, 0.028f, 0.04f)
        else -> floatArrayOf(0.0022f, 0.0038f, 0.0065f)
    }
}
