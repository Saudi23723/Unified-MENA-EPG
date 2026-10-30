package com.saudi.privatevault

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** A notebook written by hand: pages of strokes on a blank, lined, grid, dotted or scratchpad page. */
class NoteBook(val file: File) {
    enum class Style(val label: String) {
        SCRATCHPAD("✈️ Scratchpad (ATIS + clearance)"), LINED("📄 Lined"), BLANK("⬜ Blank"), GRID("▦ Grid"), DOTS("⠿ Dots"),
    }

    class Stroke(val tool: NotePad.Tool, val color: Int, val width: Float, val pts: FloatArray)

    var title = ""
    var topic: String? = null
    var style = Style.LINED
    var created = System.currentTimeMillis()
    val pages = ArrayList<ArrayList<Stroke>>()

    fun save() {
        val ps = JSONArray()
        for (p in pages) ps.put(JSONArray().apply {
            for (s in p) put(JSONObject().put("t", s.tool.name).put("c", s.color).put("w", s.width.toDouble())
                .put("p", JSONArray().apply { s.pts.forEach { put(Math.round(it * 10) / 10.0) } }))
        })
        file.parentFile?.mkdirs()
        file.writeText(JSONObject().put("title", title).put("topic", topic ?: "").put("style", style.name)
            .put("created", created).put("pages", ps).toString())
    }

    companion object {
        fun dir(ctx: Context) = File(ctx.filesDir, "notes").apply { mkdirs() }

        fun all(ctx: Context): List<NoteBook> =
            (dir(ctx).listFiles { f -> f.name.endsWith(".json") } ?: emptyArray()).mapNotNull { load(it) }.sortedByDescending { it.file.lastModified() }

        fun load(f: File): NoteBook? = try {
            val o = JSONObject(f.readText())
            NoteBook(f).apply {
                title = o.optString("title")
                topic = o.optString("topic").ifEmpty { null }
                style = try { Style.valueOf(o.optString("style")) } catch (e: Exception) { Style.LINED }
                created = o.optLong("created")
                val ps = o.optJSONArray("pages") ?: JSONArray()
                for (i in 0 until ps.length()) {
                    val arr = ps.getJSONArray(i)
                    pages.add(ArrayList((0 until arr.length()).map { k ->
                        val s = arr.getJSONObject(k)
                        val p = s.getJSONArray("p")
                        Stroke(try { NotePad.Tool.valueOf(s.getString("t")) } catch (e: Exception) { NotePad.Tool.PEN },
                            s.getInt("c"), s.getDouble("w").toFloat(), FloatArray(p.length()) { p.getDouble(it).toFloat() })
                    }))
                }
                if (pages.isEmpty()) pages.add(ArrayList())
            }
        } catch (e: Exception) {
            null
        }

        fun create(ctx: Context, style: Style, topic: String?): NoteBook {
            val stamp = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.US).format(java.util.Date())
            return NoteBook(File(dir(ctx), "${System.currentTimeMillis()}.json")).apply {
                this.style = style
                this.topic = topic
                title = listOfNotNull(topic, style.name.lowercase().replaceFirstChar { it.uppercase() }, stamp).joinToString(" · ")
                pages.add(ArrayList())
                save()
            }
        }
    }
}

/** The page: drawn in page units (1000 wide, A4 tall) and fitted to whatever size the window is. */
@SuppressLint("ViewConstructor")
class NoteCanvas(ctx: Context, val book: NoteBook) : View(ctx) {
    var page = 0
        set(v) { field = v; invalidate() }
    var tool = NotePad.Tool.PEN
    var color = Color.BLACK
    var onChange: () -> Unit = {}

    private val undone = ArrayList<NoteBook.Stroke>()
    private var current: ArrayList<Float>? = null
    private val box = RectF()
    private var scale = 1f
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG)

    init { setLayerType(LAYER_TYPE_HARDWARE, null) }

    private val strokes get() = book.pages[page]

    override fun onDraw(c: Canvas) {
        c.drawColor(0xFF263238.toInt())
        scale = minOf(width / NotePad.W, height / NotePad.H)
        val w = NotePad.W * scale
        val h = NotePad.H * scale
        box.set((width - w) / 2, (height - h) / 2, (width + w) / 2, (height + h) / 2)
        c.save()
        c.translate(box.left, box.top)
        c.scale(scale, scale)
        bg.style = Paint.Style.FILL
        bg.color = Color.WHITE
        c.drawRect(0f, 0f, NotePad.W, NotePad.H, bg)
        NotePad.background(c, book.style, page, bg)
        // Highlighter under the ink, like real paper.
        for (s in strokes) if (s.tool == NotePad.Tool.HIGHLIGHTER) draw(c, s)
        for (s in strokes) if (s.tool != NotePad.Tool.HIGHLIGHTER) draw(c, s)
        current?.let { draw(c, NoteBook.Stroke(tool, color, tool.width, it.toFloatArray())) }
        c.restore()
    }

    private fun draw(c: Canvas, s: NoteBook.Stroke) {
        if (s.tool == NotePad.Tool.ERASER) return
        paint.color = s.color
        paint.alpha = s.tool.alpha
        paint.strokeWidth = s.width
        paint.strokeCap = if (s.tool == NotePad.Tool.HIGHLIGHTER) Paint.Cap.SQUARE else Paint.Cap.ROUND
        val p = s.pts
        if (p.size < 2) return
        if (p.size == 2) { c.drawPoint(p[0], p[1], paint); return }
        val path = Path().apply {
            moveTo(p[0], p[1])
            var i = 2
            while (i + 1 < p.size) {
                // Smooth: a curve through the midpoints.
                val mx = (p[i - 2] + p[i]) / 2
                val my = (p[i - 1] + p[i + 1]) / 2
                quadTo(p[i - 2], p[i - 1], mx, my)
                i += 2
            }
            lineTo(p[p.size - 2], p[p.size - 1])
        }
        c.drawPath(path, paint)
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        parent?.requestDisallowInterceptTouchEvent(true)
        val x = (e.x - box.left) / scale
        val y = (e.y - box.top) / scale
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (tool == NotePad.Tool.ERASER) erase(x, y) else current = arrayListOf(x, y)
            }
            MotionEvent.ACTION_MOVE -> {
                if (tool == NotePad.Tool.ERASER) erase(x, y)
                else current?.let { cur ->
                    for (h in 0 until e.historySize) { cur.add((e.getHistoricalX(h) - box.left) / scale); cur.add((e.getHistoricalY(h) - box.top) / scale) }
                    cur.add(x); cur.add(y)
                }
            }
            MotionEvent.ACTION_UP -> {
                current?.let {
                    strokes.add(NoteBook.Stroke(tool, if (tool == NotePad.Tool.HIGHLIGHTER && color == Color.BLACK) 0xFFFFEB3B.toInt() else color, tool.width, it.toFloatArray()))
                    undone.clear()
                    onChange()
                }
                current = null
            }
            MotionEvent.ACTION_CANCEL -> current = null
        }
        invalidate()
        return true
    }

    /** The eraser takes whole strokes it touches, as in most note apps. */
    private fun erase(x: Float, y: Float) {
        val r = 18f
        val hit = strokes.filter { s -> (0 until s.pts.size / 2).any { i -> Math.hypot((s.pts[2 * i] - x).toDouble(), (s.pts[2 * i + 1] - y).toDouble()) < r + s.width / 2 } }
        if (hit.isNotEmpty()) { strokes.removeAll(hit.toSet()); onChange() }
    }

    fun undo() { if (strokes.isNotEmpty()) { undone.add(strokes.removeAt(strokes.size - 1)); onChange(); invalidate() } }
    fun redo() { if (undone.isNotEmpty()) { strokes.add(undone.removeAt(undone.size - 1)); onChange(); invalidate() } }
    fun clearPage() { strokes.clear(); onChange(); invalidate() }
}

/**
 * The notepad: a small window on the right of the screen, over the map or
 * whatever is open, that grows to a full page with one tap and back. Pens:
 * pen, fine pen, pencil, marker, highlighter, and an eraser; colours; undo
 * and redo; pages to add and turn; and the notebook as a PDF in the vault.
 */
object NotePad {
    const val W = 1000f
    const val H = 1414f

    enum class Tool(val label: String, val width: Float, val alpha: Int) {
        PEN("🖊 Pen", 3.5f, 255), FINE("✒️ Fine", 1.8f, 255), PENCIL("✏️ Pencil", 2.4f, 150),
        MARKER("🖍 Marker", 9f, 255), HIGHLIGHTER("🖌 Highlighter", 26f, 90), ERASER("🧽 Eraser", 0f, 0),
    }

    private val COLORS = intArrayOf(Color.BLACK, 0xFF1565C0.toInt(), 0xFFD32F2F.toInt(), 0xFF2E7D32.toInt(), 0xFFF57C00.toInt(), 0xFF7B1FA2.toInt(), 0xFFFFEB3B.toInt())

    private var window: FrameLayout? = null

    /** Ruling and boxes, in page units. */
    fun background(c: Canvas, style: NoteBook.Style, page: Int, p: Paint) {
        p.style = Paint.Style.STROKE
        var top = 70f
        val m = 60f
        if (style == NoteBook.Style.SCRATCHPAD && page == 0) {
            val ink = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF37474F.toInt(); textSize = 22f; isFakeBoldText = true }
            val small = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF78909C.toInt(); textSize = 15f }
            p.color = 0xFF90A4AE.toInt(); p.strokeWidth = 1.6f
            c.drawText("ATIS / AWOS", m, top, ink)
            top += 14
            val atis = listOf("Info", "Time Z", "Wind", "Visibility", "Sky", "Temp / Dew", "Altimeter", "Runway", "Remarks / NOTAMs")
            for ((i, t) in atis.withIndex()) {
                val x = if (i % 2 == 0) m else W / 2 + 10
                val y = top + (i / 2) * 74f
                val w = if (i == atis.size - 1) W - 2 * m else W / 2 - m - 10
                c.drawRect(x, y, x + w, y + 64, p)
                c.drawText(t, x + 6, y + 18, small)
            }
            top += ((atis.size + 1) / 2) * 74f + 40
            c.drawText("CLEARANCE  (C R A F T)", m, top, ink)
            top += 14
            for (t in listOf("C · Clearance limit", "R · Route", "A · Altitude", "F · Frequency", "T · Transponder")) {
                c.drawRect(m, top, W - m, top + 64, p)
                c.drawText(t, m + 6, top + 18, small)
                top += 74
            }
            top += 10
        }
        when (style) {
            NoteBook.Style.BLANK -> {}
            NoteBook.Style.GRID -> {
                p.color = 0xFFDDE4EA.toInt(); p.strokeWidth = 1f
                var x = m; while (x <= W - m) { c.drawLine(x, top, x, H - m, p); x += 32 }
                var y = top; while (y <= H - m) { c.drawLine(m, y, W - m, y, p); y += 32 }
            }
            NoteBook.Style.DOTS -> {
                p.style = Paint.Style.FILL; p.color = 0xFFB0BEC5.toInt()
                var y = top; while (y <= H - m) { var x = m; while (x <= W - m) { c.drawCircle(x, y, 2.2f, p); x += 32 }; y += 32 }
            }
            else -> {
                p.color = 0xFFB0BEC5.toInt(); p.strokeWidth = 1.3f
                var y = top + 48; while (y <= H - m) { c.drawLine(m, y, W - m, y, p); y += 48 }
            }
        }
    }

    /** Opens a notebook: small on the right (big = false) or as a full page. */
    @SuppressLint("ClickableViewAccessibility", "SetTextI18n")
    fun show(act: Activity, book: NoteBook, big: Boolean) {
        close(act)
        val content = act.findViewById<FrameLayout>(android.R.id.content)
        val d = act.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val sw = act.resources.displayMetrics.widthPixels
        val sh = act.resources.displayMetrics.heightPixels
        val smallW = minOf((sw * 0.42).toInt(), dp(380)).coerceAtLeast(dp(220))
        val smallH = (smallW * 1.6).toInt().coerceAtMost((sh * 0.7).toInt())

        val frame = FrameLayout(act).apply {
            elevation = dp(16).toFloat()
            background = GradientDrawable().apply { setColor(0xFF101826.toInt()); cornerRadius = dp(14).toFloat(); setStroke(dp(1), EfbUi.ACCENT) }
            clipToOutline = true
            isClickable = true
        }
        val col = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
        frame.addView(col, FrameLayout.LayoutParams(-1, -1))
        val canvas = NoteCanvas(act, book)
        var dirty = false
        canvas.onChange = { dirty = true }

        // Title bar: drag to move the small window; ⤢ grows or shrinks it; ✕ closes and saves.
        val head = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(8), dp(2), dp(2), dp(2)) }
        val title = TextView(act).apply { text = book.title; setTextColor(EfbUi.TEXT); textSize = 12f; maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END }
        head.addView(title, LinearLayout.LayoutParams(0, -2, 1f))
        fun chip(t: String, size: Float = 15f, onClick: (TextView) -> Unit) = TextView(act).apply {
            text = t; textSize = size; setTextColor(EfbUi.TEXT); gravity = Gravity.CENTER
            setPadding(dp(9), dp(7), dp(9), dp(7))
            setOnClickListener { onClick(this) }
        }
        val pageLabel = TextView(act).apply { setTextColor(EfbUi.DIM); textSize = 12f; setPadding(dp(4), 0, dp(4), 0) }
        fun showPage() { pageLabel.text = "${canvas.page + 1}/${book.pages.size}" }
        showPage()
        var isBig = big
        lateinit var grow: TextView
        fun place() {
            frame.layoutParams = if (isBig) FrameLayout.LayoutParams(-1, -1)
            else FrameLayout.LayoutParams(smallW, smallH, Gravity.END or Gravity.CENTER_VERTICAL).apply { marginEnd = dp(8) }
            frame.translationX = 0f; frame.translationY = 0f
            grow.text = if (isBig) "⤡" else "⤢"
        }
        head.addView(chip("‹") { if (canvas.page > 0) { canvas.page--; showPage() } })
        head.addView(pageLabel)
        head.addView(chip("›") { if (canvas.page < book.pages.size - 1) { canvas.page++; showPage() } })
        head.addView(chip("＋") {
            book.pages.add(canvas.page + 1, ArrayList()); canvas.page++; showPage(); dirty = true
        })
        grow = chip("⤢", 17f) { isBig = !isBig; place() }
        head.addView(grow)
        head.addView(chip("✕", 16f) { close(act) })
        var dx = 0f; var dy = 0f
        head.setOnTouchListener { _, e ->
            if (isBig) return@setOnTouchListener false
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { dx = frame.translationX - e.rawX; dy = frame.translationY - e.rawY }
                MotionEvent.ACTION_MOVE -> { frame.translationX = e.rawX + dx; frame.translationY = e.rawY + dy }
            }
            true
        }
        col.addView(head)

        // Pens, colours, undo / redo, clear, PDF.
        val tools = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(4), 0, dp(4), dp(2)) }
        val toolChips = ArrayList<Pair<Tool, TextView>>()
        fun mark() = toolChips.forEach { (t, v) -> v.background = if (t == canvas.tool) GradientDrawable().apply { setColor(0xFF1E3A5F.toInt()); cornerRadius = dp(8).toFloat() } else null }
        for (t in Tool.values()) {
            val v = chip(t.label, 12f) { canvas.tool = t; mark() }
            toolChips.add(t to v); tools.addView(v)
        }
        mark()
        val dots = ArrayList<View>()
        for (c in COLORS) {
            val dot = View(act).apply {
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(c); setStroke(dp(2), if (c == canvas.color) EfbUi.ACCENT else 0xFF455A64.toInt()) }
                setOnClickListener {
                    canvas.color = c
                    if (canvas.tool == Tool.ERASER) { canvas.tool = Tool.PEN; mark() }
                    dots.forEachIndexed { i, v -> (v.background as GradientDrawable).setStroke(dp(2), if (COLORS[i] == c) EfbUi.ACCENT else 0xFF455A64.toInt()) }
                }
            }
            dots.add(dot)
            tools.addView(dot, LinearLayout.LayoutParams(dp(24), dp(24)).apply { marginStart = dp(5); marginEnd = dp(5) })
        }
        tools.addView(chip("↶") { canvas.undo() })
        tools.addView(chip("↷") { canvas.redo() })
        tools.addView(chip("🗑 Page", 12f) {
            com.google.android.material.dialog.MaterialAlertDialogBuilder(act)
                .setMessage(R.string.notes_clear_page)
                .setPositiveButton(R.string.notes_clear) { _, _ ->
                    if (book.pages.size > 1 && book.pages[canvas.page].isEmpty()) { book.pages.removeAt(canvas.page); canvas.page = canvas.page.coerceAtMost(book.pages.size - 1); showPage() }
                    else canvas.clearPage()
                    dirty = true
                }
                .setNegativeButton(R.string.cancel, null).show()
        })
        tools.addView(chip("📄 PDF", 12f) { book.save(); Notebooks.exportPdf(act, book) })
        col.addView(HorizontalScrollView(act).apply { isHorizontalScrollBarEnabled = false; addView(tools) })
        col.addView(canvas, LinearLayout.LayoutParams(-1, 0, 1f))

        frame.tag = Runnable { if (dirty) book.save() }
        content.addView(frame)
        place()
        frame.alpha = 0f; frame.scaleX = 0.92f; frame.scaleY = 0.92f
        frame.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(200).start()
        window = frame
        // Saved every few seconds while open, so nothing is lost if the app is closed.
        val saver = object : Runnable {
            override fun run() {
                if (window !== frame) return
                if (dirty) { book.save(); dirty = false }
                frame.postDelayed(this, 4000)
            }
        }
        frame.postDelayed(saver, 4000)
    }

    fun isOpen() = window?.isAttachedToWindow == true

    fun close(act: Activity) {
        val w = window ?: return
        window = null
        (w.tag as? Runnable)?.run()
        (w.parent as? ViewGroup)?.removeView(w)
    }
}
