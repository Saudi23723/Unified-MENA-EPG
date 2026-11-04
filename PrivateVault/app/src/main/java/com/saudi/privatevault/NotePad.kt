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
        SCRATCHPAD("✈️ Scratchpad (ATIS + clearance)"), ATIS("📻 ATIS"), CRAFT("🛫 CRAFT clearance"), PIREP("🌦 PIREP"), LINED("📄 Lined"), BLANK("⬜ Blank"), GRID("▦ Grid"), DOTS("⠿ Dots"),
    }

    class Stroke(val tool: NotePad.Tool, val color: Int, val width: Float, val pts: FloatArray, val pen: Int = 0)

    var title = ""
    var topic: String? = null
    var style = Style.LINED
    var created = System.currentTimeMillis()
    val pages = ArrayList<ArrayList<Stroke>>()

    fun save() {
        val ps = JSONArray()
        for (p in pages) ps.put(JSONArray().apply {
            for (s in p) put(JSONObject().put("t", s.tool.name).put("c", s.color).put("w", s.width.toDouble()).put("y", s.pen)
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
                            s.getInt("c"), s.getDouble("w").toFloat(), FloatArray(p.length()) { p.getDouble(it).toFloat() }, s.optInt("y", 0))
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
    var pen = 0
    var onChange: () -> Unit = {}
    /** Black paper and white ink, as a phone's note pop-up. */
    var dark = false
    private val invert = Paint().apply {
        colorFilter = android.graphics.ColorMatrixColorFilter(android.graphics.ColorMatrix(floatArrayOf(
            -1f, 0f, 0f, 0f, 255f, 0f, -1f, 0f, 0f, 255f, 0f, 0f, -1f, 0f, 255f, 0f, 0f, 0f, 1f, 0f,
        )))
    }
    /** On black paper, ink written black shows white. */
    private fun ink(c: Int) = if (dark && Color.red(c) + Color.green(c) + Color.blue(c) < 90) Color.WHITE else c

    private val undone = ArrayList<NoteBook.Stroke>()
    private var current: ArrayList<Float>? = null
    private val box = RectF()
    private var scale = 1f
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG)

    init { setLayerType(LAYER_TYPE_HARDWARE, null) }

    private val strokes get() = book.pages[page]

    override fun onDraw(c: Canvas) {
        c.drawColor(if (dark) 0xFF000000.toInt() else 0xFF263238.toInt())
        // A note pop-up fills its window width; a page scrolls of its own height.
        scale = if (dark) width / NotePad.W else minOf(width / NotePad.W, height / NotePad.H)
        val w = NotePad.W * scale
        val h = NotePad.H * scale
        if (dark) box.set(0f, 0f, w, h) else box.set((width - w) / 2, (height - h) / 2, (width + w) / 2, (height + h) / 2)
        c.save()
        c.translate(box.left, box.top)
        c.scale(scale, scale)
        bg.style = Paint.Style.FILL
        bg.color = Color.WHITE
        // The ruling drawn on white, then turned to black paper with grey lines.
        if (dark) c.saveLayer(0f, 0f, NotePad.W, NotePad.H, invert)
        c.drawRect(0f, 0f, NotePad.W, NotePad.H, bg)
        NotePad.background(c, book.style, page, bg)
        if (dark) c.restore()
        // Highlighter under the ink, like real paper.
        for (s in strokes) if (s.tool == NotePad.Tool.HIGHLIGHTER) draw(c, s)
        for (s in strokes) if (s.tool != NotePad.Tool.HIGHLIGHTER) draw(c, s)
        current?.let { draw(c, NoteBook.Stroke(tool, color, tool.width, it.toFloatArray(), pen)) }
        c.restore()
    }

    private fun draw(c: Canvas, s: NoteBook.Stroke) {
        if (s.tool == NotePad.Tool.ERASER) return
        if (s.tool == NotePad.Tool.FINE || s.tool == NotePad.Tool.PENCIL || s.tool == NotePad.Tool.MARKER) {
            val k = when (s.tool) { NotePad.Tool.FINE -> PenStyle.FINE; NotePad.Tool.PENCIL -> PenStyle.PENCIL; else -> PenStyle.MARKER }
            PenInk.draw(c, k, ink(s.color), NotePad.Tool.PEN.width, s.pts); return
        }
        if (s.tool == NotePad.Tool.PEN) { PenInk.draw(c, PenInk.style(s.pen), ink(s.color), s.width, s.pts); return }
        paint.color = ink(s.color)
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
                    strokes.add(NoteBook.Stroke(tool, if (tool == NotePad.Tool.HIGHLIGHTER && color == Color.BLACK) 0xFFFFEB3B.toInt() else color, tool.width, it.toFloatArray(), pen))
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
        // One template a page, as an EFB's scratch pads: the boxes, each with its name.
        fun boxes(title: String, names: List<String>, two: Boolean) {
            val ink = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF37474F.toInt(); textSize = 24f; isFakeBoldText = true }
            val small = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF78909C.toInt(); textSize = 16f }
            p.color = 0xFF90A4AE.toInt(); p.strokeWidth = 1.6f
            c.drawText(title, m, top, ink)
            top += 16
            val rowH = ((H - m - top) / (if (two) (names.size + 1) / 2 else names.size)).coerceIn(70f, 150f)
            for ((i, t) in names.withIndex()) {
                val x = if (two && i % 2 == 1) W / 2 + 8 else m
                val y = top + (if (two) i / 2 else i) * rowH
                val w = if (two) W / 2 - m - 8 else W - 2 * m
                c.drawRect(x, y, x + w, y + rowH - 10, p)
                c.drawText(t, x + 8, y + 22, small)
            }
            top = H
        }
        when (style) {
            NoteBook.Style.ATIS -> if (page == 0) boxes("ATIS / AWOS", listOf("Airport", "Information", "Time Z", "Wind", "Visibility", "Weather", "Sky", "Temp / Dew", "Altimeter", "Runway / Approach", "NOTAMs", "Remarks"), true)
            NoteBook.Style.CRAFT -> if (page == 0) boxes("CLEARANCE", listOf("C · Clearance limit", "R · Route", "A · Altitude (initial / expect)", "F · Departure frequency", "T · Transponder code"), false)
            NoteBook.Style.PIREP -> if (page == 0) boxes("PIREP  ·  UA / UUA", listOf("OV · Location", "TM · Time Z", "FL · Altitude", "TP · Aircraft type", "SK · Sky cover", "WX · Weather / visibility", "TA · Temperature", "WV · Wind", "TB · Turbulence", "IC · Icing", "RM · Remarks"), true)
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
        val white = 0xFFFFFFFF.toInt()
        val grey = 0xFF8E8E93.toInt()
        val blue = 0xFF2E9BFF.toInt()

        // A black pop-up window with rounded corners and a soft shadow, as a phone's floating note.
        val frame = FrameLayout(act).apply {
            elevation = dp(24).toFloat()
            background = GradientDrawable().apply { setColor(0xFF000000.toInt()); cornerRadius = dp(22).toFloat(); setStroke(dp(1), 0xFF2C2C2E.toInt()) }
            clipToOutline = true
            isClickable = true
        }
        val col = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
        frame.addView(col, FrameLayout.LayoutParams(-1, -1))
        val canvas = NoteCanvas(act, book).apply { dark = true; color = Color.WHITE }
        var dirty = false
        canvas.onChange = { dirty = true }

        fun icon(res: Int, tint: Int = white, onClick: (android.widget.ImageView) -> Unit) = android.widget.ImageView(act).apply {
            setImageResource(res); setColorFilter(tint); setPadding(dp(9), dp(9), dp(9), dp(9))
            background = android.graphics.drawable.RippleDrawable(android.content.res.ColorStateList.valueOf(0x33FFFFFF), null,
                GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(white) })
            setOnClickListener { onClick(this) }
        }
        fun glyph(t: String, size: Float = 18f, onClick: (TextView) -> Unit) = TextView(act).apply {
            text = t; textSize = size; setTextColor(white); gravity = Gravity.CENTER
            setPadding(dp(10), dp(6), dp(10), dp(6)); setOnClickListener { onClick(this) }
        }

        // The handle: a small pill to drag the window by.
        col.addView(View(act).apply { background = GradientDrawable().apply { setColor(0xFF3A3A3C.toInt()); cornerRadius = dp(3).toFloat() } },
            LinearLayout.LayoutParams(dp(40), dp(5)).apply { gravity = Gravity.CENTER_HORIZONTAL; topMargin = dp(8) })

        // The title, the page, and minimise / size / close.
        val head = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(14), dp(2), dp(6), 0) }
        head.addView(TextView(act).apply {
            text = book.title; setTextColor(white); textSize = 15f; maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END
            typeface = EfbUi.MEDIUM
        }, LinearLayout.LayoutParams(0, -2, 1f))
        val pageLabel = TextView(act).apply { setTextColor(grey); textSize = 12f; setPadding(dp(6), 0, dp(6), 0) }
        fun showPage() { pageLabel.text = "${canvas.page + 1} / ${book.pages.size}" }
        showPage()
        var isBig = big
        lateinit var grow: TextView
        val smallW = minOf((sw * 0.46).toInt(), dp(400)).coerceAtLeast(dp(260))
        val smallH = (smallW * 1.25).toInt().coerceAtMost((sh * 0.62).toInt())
        val bigW = minOf((sw * 0.86).toInt(), dp(720))
        val bigH = (sh * 0.8).toInt()
        fun place() {
            frame.layoutParams = FrameLayout.LayoutParams(if (isBig) bigW else smallW, if (isBig) bigH else smallH, Gravity.END or Gravity.CENTER_VERTICAL).apply { marginEnd = dp(12) }
            frame.translationX = 0f; frame.translationY = 0f
            grow.text = if (isBig) "⤡" else "⤢"
        }
        head.addView(pageLabel)
        head.addView(glyph("–", 22f) { minimise(act, frame, book) })
        grow = glyph("⤢", 18f) { isBig = !isBig; place() }
        head.addView(grow)
        head.addView(icon(R.drawable.ic_close) { close(act) }, LinearLayout.LayoutParams(dp(38), dp(38)))
        var dx = 0f; var dy = 0f
        val drag = View.OnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { dx = frame.translationX - e.rawX; dy = frame.translationY - e.rawY }
                MotionEvent.ACTION_MOVE -> { frame.translationX = e.rawX + dx; frame.translationY = e.rawY + dy }
            }
            true
        }
        head.setOnTouchListener(drag)
        col.getChildAt(0).setOnTouchListener(drag)
        col.addView(head)

        col.addView(canvas, LinearLayout.LayoutParams(-1, 0, 1f))

        // The tools along the bottom, on a dark strip: pens, colours, undo / redo, pages.
        val tools = LinearLayout(act).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(6), dp(4), dp(6), dp(6)); setBackgroundColor(0xFF1C1C1E.toInt())
        }
        val toolViews = ArrayList<Pair<Tool, android.widget.ImageView>>()
        fun mark() = toolViews.forEach { (t, v) ->
            v.setColorFilter(if (t == canvas.tool || (t == Tool.PEN && canvas.tool != Tool.HIGHLIGHTER && canvas.tool != Tool.ERASER)) blue else white)
        }
        for ((t, res) in listOf(Tool.PEN to R.drawable.ic_tool_pen, Tool.HIGHLIGHTER to R.drawable.ic_tool_highlight, Tool.ERASER to R.drawable.ic_tool_eraser)) {
            val v = icon(res) {
                if (t == Tool.PEN && canvas.tool == Tool.PEN) PenInk.choose(act, canvas.pen) { i -> canvas.pen = i }
                canvas.tool = t; mark()
            }
            if (t == Tool.PEN) v.setOnLongClickListener { PenInk.choose(act, canvas.pen) { i -> canvas.pen = i; canvas.tool = Tool.PEN; mark() }; true }
            toolViews.add(t to v)
            tools.addView(v, LinearLayout.LayoutParams(dp(40), dp(40)))
        }
        mark()
        tools.addView(View(act).apply { setBackgroundColor(0xFF3A3A3C.toInt()) }, LinearLayout.LayoutParams(dp(1), dp(22)).apply { setMargins(dp(4), 0, dp(6), 0) })
        val inks = intArrayOf(Color.WHITE, 0xFFFFD60A.toInt(), 0xFF64D2FF.toInt(), 0xFF30D158.toInt(), 0xFFFF375F.toInt(), 0xFFBF5AF2.toInt())
        val dots = ArrayList<View>()
        fun ring() = dots.forEachIndexed { i, v -> (v.background as GradientDrawable).setStroke(dp(2), if (inks[i] == canvas.color) blue else 0x00000000) }
        for (cl in inks) {
            val dot = View(act).apply {
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(cl) }
                setOnClickListener {
                    canvas.color = cl
                    if (canvas.tool == Tool.ERASER) { canvas.tool = Tool.PEN; mark() }
                    ring()
                }
            }
            dots.add(dot)
            tools.addView(dot, LinearLayout.LayoutParams(dp(22), dp(22)).apply { marginStart = dp(4); marginEnd = dp(4) })
        }
        ring()
        tools.addView(View(act), LinearLayout.LayoutParams(0, 1, 1f))
        tools.addView(icon(R.drawable.ic_undo) { canvas.undo() }, LinearLayout.LayoutParams(dp(38), dp(38)))
        tools.addView(icon(R.drawable.ic_redo) { canvas.redo() }, LinearLayout.LayoutParams(dp(38), dp(38)))
        tools.addView(glyph("‹", 20f) { if (canvas.page > 0) { canvas.page--; showPage() } })
        tools.addView(glyph("›", 20f) { if (canvas.page < book.pages.size - 1) { canvas.page++; showPage() } })
        tools.addView(glyph("＋", 16f) { book.pages.add(canvas.page + 1, ArrayList()); canvas.page++; showPage(); dirty = true })
        tools.addView(glyph("⋯", 18f) { v ->
            val m = android.widget.PopupMenu(act, v)
            m.menu.add(0, 1, 0, act.getString(R.string.notes_clear))
            m.menu.add(0, 2, 1, "PDF")
            m.setOnMenuItemClickListener {
                if (it.itemId == 1) com.google.android.material.dialog.MaterialAlertDialogBuilder(act)
                    .setMessage(R.string.notes_clear_page)
                    .setPositiveButton(R.string.notes_clear) { _, _ ->
                        if (book.pages.size > 1 && book.pages[canvas.page].isEmpty()) { book.pages.removeAt(canvas.page); canvas.page = canvas.page.coerceAtMost(book.pages.size - 1); showPage() }
                        else canvas.clearPage()
                        dirty = true
                    }.setNegativeButton(R.string.cancel, null).show()
                else { book.save(); Notebooks.exportPdf(act, book) }
                true
            }
            m.show()
        })
        col.addView(HorizontalScrollView(act).apply { isHorizontalScrollBarEnabled = false; isFillViewport = true; setBackgroundColor(0xFF1C1C1E.toInt()); addView(tools) })

        // The corner grip: any size between small and nearly the whole screen.
        val grip = View(act).apply {
            background = GradientDrawable().apply { setColor(0x553A3A3C); cornerRadius = dp(4).toFloat() }
        }
        var gx = 0f; var gy = 0f; var gw = 0; var gh = 0
        grip.setOnTouchListener { _, e ->
            val lp = frame.layoutParams as FrameLayout.LayoutParams
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { gx = e.rawX; gy = e.rawY; gw = frame.width; gh = frame.height }
                MotionEvent.ACTION_MOVE -> {
                    lp.width = (gw - (e.rawX - gx)).toInt().coerceIn(dp(240), (sw * 0.94).toInt())
                    lp.height = (gh + (e.rawY - gy)).toInt().coerceIn(dp(260), (sh * 0.9).toInt())
                    frame.layoutParams = lp
                }
            }
            true
        }
        frame.addView(grip, FrameLayout.LayoutParams(dp(18), dp(18), Gravity.BOTTOM or Gravity.START).apply { setMargins(dp(4), 0, 0, dp(52)) })

        frame.tag = Runnable { if (dirty) book.save() }
        content.addView(frame)
        place()
        frame.alpha = 0f; frame.scaleX = 0.94f; frame.scaleY = 0.94f
        frame.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(180).start()
        window = frame
        val saver = object : Runnable {
            override fun run() {
                if (window !== frame) return
                if (dirty) { book.save(); dirty = false }
                frame.postDelayed(this, 4000)
            }
        }
        frame.postDelayed(saver, 4000)
    }

    /** Folded to a round bubble at the screen's edge, as a phone's floating note; a tap opens it again. */
    private fun minimise(act: Activity, frame: View, book: NoteBook) {
        (frame.tag as? Runnable)?.run()
        val content = act.findViewById<FrameLayout>(android.R.id.content)
        val d = act.resources.displayMetrics.density
        frame.visibility = View.GONE
        val bubble = android.widget.ImageView(act).apply {
            setImageResource(R.drawable.ic_fab_pencil)
            setPadding((14 * d).toInt(), (14 * d).toInt(), (14 * d).toInt(), (14 * d).toInt())
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0xFF000000.toInt()); setStroke((2 * d).toInt(), 0xFF2E9BFF.toInt()) }
            elevation = 20 * d
        }
        content.addView(bubble, FrameLayout.LayoutParams((54 * d).toInt(), (54 * d).toInt(), Gravity.END or Gravity.CENTER_VERTICAL).apply { marginEnd = (10 * d).toInt() })
        var sx = 0f; var sy = 0f; var ty = 0f; var moved = false
        bubble.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { sx = e.rawX; sy = e.rawY; ty = v.translationY; moved = false }
                MotionEvent.ACTION_MOVE -> { if (Math.abs(e.rawY - sy) > 10 * d) moved = true; if (moved) v.translationY = ty + e.rawY - sy }
                MotionEvent.ACTION_UP -> if (!moved) { content.removeView(bubble); frame.visibility = View.VISIBLE }
            }
            true
        }
        // Closing the note elsewhere takes the bubble too.
        frame.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(v: View) {}
            override fun onViewDetachedFromWindow(v: View) { content.removeView(bubble) }
        })
    }

    fun isOpen() = window?.isAttachedToWindow == true

    fun close(act: Activity) {
        val w = window ?: return
        window = null
        (w.tag as? Runnable)?.run()
        (w.parent as? ViewGroup)?.removeView(w)
    }
}
