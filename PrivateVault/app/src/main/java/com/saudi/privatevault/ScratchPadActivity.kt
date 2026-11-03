package com.saudi.privatevault

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.SweepGradient
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * The scratch pad as an EFB has it: the whole screen to write on, dark, its
 * pages in tabs along the top (two blank pages, then ATIS, CRAFT and PIREP
 * forms), and one round pen button that opens a small panel: the pen, the
 * marker, the highlighter; three widths; a colour wheel; Clear and Invert
 * colours. Everything is kept as it is written.
 */
class ScratchPadActivity : BaseActivity() {
    override val alwaysDark = true

    private class Stroke(val kind: Int, var color: Int, val width: Float, val pts: FloatArray)

    private val tabs = listOf("Page 1", "Page 2", "Page 3", "ATIS", "CRAFT", "PIREP")
    private val pages = HashMap<Int, ArrayList<Stroke>>()
    // Each page's own undo and redo: what was added, or what Clear and the eraser took.
    private val undo = HashMap<Int, ArrayList<List<Stroke>>>()
    private val redo = HashMap<Int, ArrayList<List<Stroke>>>()
    private val undoneAdds = HashMap<Int, ArrayList<Boolean>>()

    private fun record(added: Boolean, strokes: List<Stroke>) {
        undo.getOrPut(tab) { ArrayList() }.add(strokes)
        undoneAdds.getOrPut(tab) { ArrayList() }.add(added)
        redo[tab]?.clear()
    }

    private fun undoLast() {
        val u = undo[tab]?.removeLastOrNull() ?: return
        val added = undoneAdds[tab]!!.removeAt(undoneAdds[tab]!!.size - 1)
        val list = pages.getOrPut(tab) { ArrayList() }
        if (added) list.removeAll(u.toSet()) else list.addAll(u)
        redo.getOrPut(tab) { ArrayList() }.add(u)
        redoKinds.getOrPut(tab) { ArrayList() }.add(added)
        save(); pad.invalidate()
    }

    private val redoKinds = HashMap<Int, ArrayList<Boolean>>()

    private fun redoLast() {
        val r = redo[tab]?.removeLastOrNull() ?: return
        val added = redoKinds[tab]!!.removeAt(redoKinds[tab]!!.size - 1)
        val list = pages.getOrPut(tab) { ArrayList() }
        if (added) list.addAll(r) else list.removeAll(r.toSet())
        undo.getOrPut(tab) { ArrayList() }.add(r)
        undoneAdds.getOrPut(tab) { ArrayList() }.add(added)
        save(); pad.invalidate()
    }
    private var tab = 0
    private var kind = 0 // 0 pen, 1 marker, 2 highlighter, 3 eraser
    private var widthIdx = 0
    private var color = 0xFF8FD3FF.toInt()
    private var light = false
    private lateinit var pad: Pad
    private lateinit var tabRow: LinearLayout
    private lateinit var root: FrameLayout
    private var panel: View? = null
    private val file get() = File(filesDir, "notes/scratchpad.json")
    private fun dp(v: Int) = EfbUi.dp(this, v)

    private val bg get() = if (light) 0xFFF7F4EF.toInt() else 0xFF1C1712.toInt()
    private val bar get() = if (light) 0xFFE9E4DC.toInt() else 0xFF2A231C.toInt()
    private val fg get() = if (light) 0xFF2B2B2B.toInt() else 0xFFE8E2D8.toInt()
    private val dim get() = if (light) 0xFF8A8378.toInt() else 0xFF8C8072.toInt()
    private val blue = 0xFF2F9BFF.toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        load()
        build()
    }

    override fun onPause() { super.onPause(); save() }

    private fun build() {
        window.statusBarColor = bar; window.navigationBarColor = bg
        root = FrameLayout(this).apply { setBackgroundColor(bg) }
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(col, FrameLayout.LayoutParams(-1, -1))

        // Title bar.
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setBackgroundColor(bar); setPadding(dp(6), dp(8), dp(8), 0); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        top.addView(TextView(this).apply { text = "‹"; textSize = 28f; setTextColor(fg); setPadding(dp(12), 0, dp(14), dp(4)); setOnClickListener { finish() } })
        top.addView(TextView(this).apply { text = "Scratch Pad"; textSize = 21f; setTextColor(fg); setTypeface(typeface, android.graphics.Typeface.BOLD) }, LinearLayout.LayoutParams(0, -2, 1f))
        for ((t, go) in listOf("↶" to { undoLast() }, "↷" to { redoLast() })) top.addView(TextView(this).apply {
            text = t; textSize = 24f; setTextColor(fg); setPadding(dp(12), 0, dp(12), dp(4))
            setOnClickListener { go() }
        })
        top.addView(TextView(this).apply {
            text = "📒"; textSize = 19f; setPadding(dp(10), dp(4), dp(10), dp(4))
            setOnClickListener { Notebooks.choose(this@ScratchPadActivity, null, big = true) }
        })
        col.addView(top)

        // The pages, as tabs with a line under the one open.
        tabRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(bar); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        col.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; isFillViewport = true; setBackgroundColor(bar); addView(tabRow) })
        paintTabs()

        pad = Pad(this)
        col.addView(pad, LinearLayout.LayoutParams(-1, 0, 1f))

        // The pen button.
        val fab = android.widget.ImageView(this).apply {
            setImageResource(R.drawable.ic_fab_pencil); setPadding(dp(15), dp(15), dp(15), dp(15))
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(0xFF2FA4FF.toInt(), 0xFF1178D6.toInt())).apply { shape = GradientDrawable.OVAL; setStroke(dp(2), 0xE6FFFFFF.toInt()) }
            elevation = dp(8).toFloat()
            setOnClickListener { togglePanel() }
        }
        root.addView(fab, FrameLayout.LayoutParams(dp(60), dp(60), Gravity.BOTTOM or Gravity.END).apply { setMargins(0, 0, dp(22), dp(28)) })
        setContentView(root)
    }

    private fun paintTabs() {
        tabRow.removeAllViews()
        for ((i, t) in tabs.withIndex()) {
            val cell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setOnClickListener { tab = i; paintTabs(); pad.invalidate() } }
            cell.addView(TextView(this).apply {
                text = t; textSize = 14f; gravity = Gravity.CENTER; setTextColor(if (i == tab) fg else dim)
                setTypeface(typeface, if (i == tab) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL)
                setPadding(dp(18), dp(12), dp(18), dp(10))
            })
            cell.addView(View(this).apply { setBackgroundColor(if (i == tab) blue else 0) }, LinearLayout.LayoutParams(-1, dp(3)))
            tabRow.addView(cell, LinearLayout.LayoutParams(-2, -2, 1f))
        }
    }

    /** The small panel: tools, widths, the colour wheel, Clear, Invert colours. */
    private fun togglePanel() {
        panel?.let { root.removeView(it); panel = null; return }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR
            background = GradientDrawable().apply { cornerRadius = dp(14).toFloat(); setColor(if (light) 0xFFFFFFFF.toInt() else 0xFF3A322A.toInt()); setStroke(dp(1), 0x33FFFFFF) }
            elevation = dp(16).toFloat(); setPadding(dp(10), dp(10), dp(10), dp(10))
        }
        fun icon(t: String, on: Boolean, onClick: () -> Unit) = TextView(this).apply {
            text = t; textSize = 20f; gravity = Gravity.CENTER; setTextColor(if (on) blue else fg)
            background = if (on) GradientDrawable().apply { cornerRadius = dp(10).toFloat(); setColor(0x332F9BFF) } else null
            setPadding(dp(10), dp(8), dp(10), dp(8)); setOnClickListener { onClick(); togglePanel(); togglePanel() }
        }
        val tools = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        for ((i, t) in listOf("✒️", "🖍", "▬", "⌫").withIndex()) tools.addView(icon(t, kind == i) { kind = i })
        box.addView(tools)
        box.addView(View(this).apply { setBackgroundColor(0x33FFFFFF) }, LinearLayout.LayoutParams(dp(1), -1).apply { setMargins(dp(8), 0, dp(8), 0) })
        val widths = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER }
        for (i in 0..2) widths.addView(icon(listOf("∼", "〜", "≋")[i], widthIdx == i) { widthIdx = i })
        box.addView(widths)
        box.addView(View(this).apply { setBackgroundColor(0x33FFFFFF) }, LinearLayout.LayoutParams(dp(1), -1).apply { setMargins(dp(8), 0, dp(8), 0) })
        val right = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL }
        right.addView(Wheel(this), LinearLayout.LayoutParams(dp(130), dp(130)))
        right.addView(TextView(this).apply {
            text = "CLEAR"; textSize = 14f; setTextColor(blue); setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(dp(8), dp(10), dp(8), dp(4))
            setOnClickListener { pages[tab]?.let { if (it.isNotEmpty()) { record(false, ArrayList(it)); it.clear() } }; save(); pad.invalidate() }
        })
        right.addView(TextView(this).apply {
            text = "INVERT COLORS"; textSize = 14f; setTextColor(blue); setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(dp(8), dp(4), dp(8), dp(4))
            setOnClickListener { light = !light; save(); panel = null; build(); pad.invalidate() }
        })
        box.addView(right)
        panel = box
        root.addView(box, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.END).apply { setMargins(0, 0, dp(22), dp(100)) })
    }

    /** A ring of colours; the middle shows the one in use (white and black at its centre and edge). */
    @SuppressLint("ViewConstructor", "ClickableViewAccessibility")
    private inner class Wheel(ctx: Context) : View(ctx) {
        private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
        private val dot = Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(c: Canvas) {
            val cx = width / 2f; val cy = height / 2f; val r = minOf(cx, cy) - dp(10)
            ring.strokeWidth = dp(16).toFloat()
            ring.shader = SweepGradient(cx, cy, intArrayOf(Color.RED, Color.MAGENTA, Color.BLUE, Color.CYAN, Color.GREEN, Color.YELLOW, Color.RED), null)
            c.drawCircle(cx, cy, r, ring)
            dot.color = color; c.drawCircle(cx, cy, r * 0.42f, dot)
            dot.color = 0x66FFFFFF; dot.style = Paint.Style.STROKE; dot.strokeWidth = dp(2).toFloat(); c.drawCircle(cx, cy, r * 0.42f, dot); dot.style = Paint.Style.FILL
        }
        override fun onTouchEvent(e: MotionEvent): Boolean {
            val dx = e.x - width / 2f; val dy = e.y - height / 2f
            val dist = Math.hypot(dx.toDouble(), dy.toDouble())
            val r = minOf(width, height) / 2f - dp(10)
            color = if (dist < r * 0.5) (if (light) Color.BLACK else Color.WHITE) else {
                // The sweep runs clockwise from 3 o'clock: red, magenta, blue, cyan, green, yellow.
                var deg = Math.toDegrees(Math.atan2(dy.toDouble(), dx.toDouble())).toFloat()
                if (deg < 0) deg += 360f
                Color.HSVToColor(floatArrayOf((360f - deg) % 360f, 0.75f, 1f))
            }
            invalidate()
            if (e.actionMasked == MotionEvent.ACTION_UP) { panel?.let { root.removeView(it); panel = null } }
            return true
        }
    }

    private val widthsPx = floatArrayOf(2.4f, 4.5f, 8f)

    /** The page: dark, the form of its tab drawn in faint lines, the writing over it. */
    @SuppressLint("ViewConstructor", "ClickableViewAccessibility")
    private inner class Pad(ctx: Context) : View(ctx) {
        private val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
        private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
        private val label = Paint(Paint.ANTI_ALIAS_FLAG)
        private var cur: ArrayList<Float>? = null
        private var erased: ArrayList<Stroke>? = null
        private val d = resources.displayMetrics.density

        override fun onDraw(c: Canvas) {
            c.drawColor(bg)
            form(c)
            val list = pages[tab].orEmpty()
            for (s in list) if (s.kind == 2) stroke(c, s)
            for (s in list) if (s.kind != 2) stroke(c, s)
            cur?.let { stroke(c, Stroke(kind, color, widthsPx[widthIdx], it.toFloatArray())) }
        }

        private fun form(c: Canvas) {
            val fields = when (tabs[tab]) {
                "ATIS" -> listOf("INFO", "TIME Z", "WIND", "VIS", "SKY", "TEMP / DEW", "ALTIMETER", "RUNWAY", "NOTAMS / REMARKS")
                "CRAFT" -> listOf("C · CLEARANCE LIMIT", "R · ROUTE", "A · ALTITUDE", "F · FREQUENCY", "T · TRANSPONDER")
                "PIREP" -> listOf("UA / UUA", "OV · LOCATION", "TM · TIME", "FL · ALTITUDE", "TP · TYPE", "SK · SKY", "WX · WEATHER", "TA · TEMP", "WV · WIND", "TB · TURB", "IC · ICING", "RM · REMARKS")
                else -> return
            }
            line.color = if (light) 0x33000000 else 0x33FFFFFF; line.strokeWidth = d
            label.color = dim; label.textSize = 12 * d; label.isFakeBoldText = true; label.letterSpacing = 0.08f
            val two = fields.size > 6 && width > height
            val rows = if (two) (fields.size + 1) / 2 else fields.size
            val h = height.toFloat() / rows
            for ((i, f) in fields.withIndex()) {
                val colI = if (two) i % 2 else 0
                val row = if (two) i / 2 else i
                val x0 = if (colI == 0) 20 * d else width / 2f + 10 * d
                val x1 = if (two && colI == 0) width / 2f - 10 * d else width - 20 * d
                val y = row * h
                c.drawText(f, x0, y + 22 * d, label)
                c.drawLine(x0, y + h - 6 * d, x1, y + h - 6 * d, line)
            }
        }

        private fun stroke(c: Canvas, s: Stroke) {
            if (s.kind == 3 || s.pts.size < 2) return
            val w = s.width * d
            p.color = s.color
            p.alpha = when (s.kind) { 2 -> 90; else -> 255 }
            p.strokeWidth = when (s.kind) { 1 -> w * 2.2f; 2 -> w * 5f; else -> w }
            p.strokeCap = if (s.kind == 2) Paint.Cap.SQUARE else Paint.Cap.ROUND
            val pts = s.pts
            val path = Path().apply {
                moveTo(pts[0] * width, pts[1] * width)
                var i = 2
                while (i + 1 < pts.size) {
                    quadTo(pts[i - 2] * width, pts[i - 1] * width, (pts[i - 2] + pts[i]) / 2 * width, (pts[i - 1] + pts[i + 1]) / 2 * width); i += 2
                }
                lineTo(pts[pts.size - 2] * width, pts[pts.size - 1] * width)
            }
            c.drawPath(path, p)
        }

        override fun onTouchEvent(e: MotionEvent): Boolean {
            panel?.let { root.removeView(it); panel = null }
            val x = e.x / width; val y = e.y / width
            val list = pages.getOrPut(tab) { ArrayList() }
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> if (kind == 3) erase(list, x, y) else cur = arrayListOf(x, y)
                MotionEvent.ACTION_MOVE -> if (kind == 3) erase(list, x, y) else cur?.let { cu ->
                    for (h in 0 until e.historySize) { cu.add(e.getHistoricalX(h) / width); cu.add(e.getHistoricalY(h) / width) }
                    cu.add(x); cu.add(y)
                }
                MotionEvent.ACTION_UP -> {
                    cur?.let { val s = Stroke(kind, color, widthsPx[widthIdx], it.toFloatArray()); list.add(s); record(true, listOf(s)) }
                    erased?.let { if (it.isNotEmpty()) record(false, it) }
                    erased = null
                    save(); cur = null
                }
                MotionEvent.ACTION_CANCEL -> cur = null
            }
            invalidate()
            return true
        }

        private fun erase(list: ArrayList<Stroke>, x: Float, y: Float) {
            val r = 16 * d / width
            val hit = list.filter { s -> (0 until s.pts.size / 2).any { i -> Math.hypot((s.pts[2 * i] - x).toDouble(), (s.pts[2 * i + 1] - y).toDouble()) < r } }
            if (hit.isNotEmpty()) { list.removeAll(hit.toSet()); (erased ?: ArrayList<Stroke>().also { erased = it }).addAll(hit) }
        }
    }

    private fun load() {
        try {
            val o = JSONObject(file.readText())
            light = o.optBoolean("light")
            tab = o.optInt("tab").coerceIn(0, tabs.size - 1)
            color = o.optInt("color", color)
            val ps = o.getJSONObject("pages")
            for (k in ps.keys()) {
                val a = ps.getJSONArray(k)
                pages[k.toInt()] = ArrayList((0 until a.length()).map { i ->
                    val s = a.getJSONObject(i); val pa = s.getJSONArray("p")
                    Stroke(s.getInt("k"), s.getInt("c"), s.getDouble("w").toFloat(), FloatArray(pa.length()) { pa.getDouble(it).toFloat() })
                })
            }
        } catch (e: Exception) {
        }
    }

    private fun save() {
        val ps = JSONObject()
        for ((k, list) in pages) ps.put(k.toString(), JSONArray().apply {
            for (s in list) put(JSONObject().put("k", s.kind).put("c", s.color).put("w", s.width.toDouble())
                .put("p", JSONArray().apply { s.pts.forEach { put(Math.round(it * 100000) / 100000.0) } }))
        })
        file.parentFile?.mkdirs()
        file.writeText(JSONObject().put("light", light).put("tab", tab).put("color", color).put("pages", ps).toString())
    }
}
