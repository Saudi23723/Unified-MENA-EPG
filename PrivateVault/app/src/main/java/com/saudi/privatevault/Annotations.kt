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
enum class Tool { HAND, PEN, HIGHLIGHT, ERASER, LINE, ARROW, RECT, OVAL, TEXT }

/**
 * One thing written on a page. Points are fractions of the page (0..1 of its
 * width and height) and [width] a fraction of the page width, so a mark stays
 * on the same words at any zoom, screen or render size.
 */
class Mark(
    val tool: Tool,
    val color: Int,
    val width: Float,
    val points: FloatArray,
    val text: String? = null,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("t", tool.name)
        .put("c", color)
        .put("w", width.toDouble())
        .put("p", JSONArray().also { a -> points.forEach { a.put(it.toDouble()) } })
        .also { if (text != null) it.put("s", text) }

    companion object {
        fun fromJson(o: JSONObject): Mark? = try {
            val p = o.getJSONArray("p")
            Mark(
                Tool.valueOf(o.getString("t")), o.getInt("c"), o.getDouble("w").toFloat(),
                FloatArray(p.length()) { p.getDouble(it).toFloat() }, o.optString("s").ifEmpty { null },
            )
        } catch (e: Exception) {
            null
        }
    }
}

/** Every page's marks for one document, kept in the app's private storage. */
class DocumentMarks(private val file: File) {
    val pages = HashMap<Int, MutableList<Mark>>()

    fun on(page: Int): MutableList<Mark> = pages.getOrPut(page) { mutableListOf() }

    fun load(): DocumentMarks {
        try {
            val o = JSONObject(file.readText()).getJSONObject("pages")
            for (k in o.keys()) {
                val a = o.getJSONArray(k)
                on(k.toInt()).addAll((0 until a.length()).mapNotNull { Mark.fromJson(a.getJSONObject(it)) })
            }
        } catch (e: Exception) {
            // Nothing written yet.
        }
        return this
    }

    /** A snapshot that can be written off the main thread. */
    fun snapshot(): String {
        val o = JSONObject()
        for ((page, marks) in pages) if (marks.isNotEmpty()) o.put(page.toString(), JSONArray(marks.map { it.toJson() }))
        return JSONObject().put("v", 1).put("pages", o).toString()
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

/** Draws marks onto a page that is [w] by [h] pixels. */
object MarkPainter {
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG)
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
                stroke.strokeCap = if (m.tool == Tool.HIGHLIGHT) Paint.Cap.SQUARE else Paint.Cap.ROUND
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

    /** Colours offered for each kind of tool. */
    val INK = intArrayOf(
        Color.parseColor("#212121"), Color.parseColor("#1565C0"), Color.parseColor("#D32F2F"),
        Color.parseColor("#2E7D32"), Color.parseColor("#EF6C00"), Color.parseColor("#6A1B9A"),
    )
    val MARKER = intArrayOf(
        Color.parseColor("#FFEB3B"), Color.parseColor("#76FF03"), Color.parseColor("#FF4081"),
        Color.parseColor("#40C4FF"), Color.parseColor("#FFAB40"),
    )

    /** Thin, medium and thick, as fractions of the page width. */
    fun widths(tool: Tool): FloatArray = when (tool) {
        Tool.HIGHLIGHT -> floatArrayOf(0.016f, 0.024f, 0.034f)
        Tool.TEXT -> floatArrayOf(0.02f, 0.028f, 0.04f)
        else -> floatArrayOf(0.0022f, 0.0038f, 0.0065f)
    }
}
