package com.saudi.privatevault

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.drawable.GradientDrawable
import android.os.SystemClock
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Ink over any screen, with a floating tool palette as iPadOS has it: a dark rounded capsule that
 * can be dragged anywhere, holding the tools (hand, pen, marker, pencil, eraser, ruler, airplane
 * stamp, laser), the colour, undo, clear and done. The hand lets the screen underneath work; any
 * other tool writes on a clear sheet over it.
 */
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
class InkSheet(ctx: Context) : View(ctx) {
    enum class Tool { HAND, PEN, MARKER, PENCIL, ERASER, RULER, PLANE, NEON, LASER }

    private class Mark(val tool: Tool, val color: Int, val pts: ArrayList<Float>, var t: Long = 0L)

    var tool = Tool.PEN
    var color = 0xFFFF3B30.toInt()
    private val marks = ArrayList<Mark>()
    private val undone = ArrayList<Mark>()
    private var cur: Mark? = null
    private val d = ctx.resources.displayMetrics.density
    private val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val f = Paint(Paint.ANTI_ALIAS_FLAG)
    private val tx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 13f * ctx.resources.displayMetrics.density; isFakeBoldText = true }

    fun undo() { marks.removeLastOrNull()?.let { undone.add(it) }; invalidate() }
    fun clear() { marks.clear(); undone.clear(); invalidate() }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (tool == Tool.HAND) return false
        val x = e.x; val y = e.y
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                when (tool) {
                    Tool.ERASER -> erase(x, y)
                    Tool.PLANE -> { marks.add(Mark(Tool.PLANE, color, arrayListOf(x, y, 0f))); undone.clear() }
                    else -> { cur = Mark(tool, color, arrayListOf(x, y)).also { marks.add(it); undone.clear() } }
                }
            }
            MotionEvent.ACTION_MOVE -> {
                when (tool) {
                    Tool.ERASER -> erase(x, y)
                    // The airplane stamp turns toward the drag.
                    Tool.PLANE -> marks.lastOrNull()?.let { m -> m.pts[2] = Math.toDegrees(Math.atan2((x - m.pts[0]).toDouble(), -(y - m.pts[1]).toDouble())).toFloat() }
                    Tool.RULER -> cur?.let { m -> while (m.pts.size > 2) m.pts.removeAt(m.pts.size - 1); m.pts.add(x); m.pts.add(y) }
                    else -> cur?.pts?.apply { add(x); add(y) }
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                cur?.let { if (it.tool == Tool.LASER) it.t = SystemClock.uptimeMillis() }
                cur = null
            }
        }
        invalidate()
        return true
    }

    private fun erase(x: Float, y: Float) {
        val r = 18 * d
        val hit = marks.lastOrNull { m -> m.pts.indices.step(2).any { i -> i + 1 < m.pts.size && Math.hypot((m.pts[i] - x).toDouble(), (m.pts[i + 1] - y).toDouble()) < r } }
        if (hit != null) { marks.remove(hit); undone.add(hit) }
    }

    override fun onDraw(c: Canvas) {
        val now = SystemClock.uptimeMillis()
        var live = false
        val it = marks.iterator()
        while (it.hasNext()) {
            val m = it.next()
            // The laser stays bright two seconds after the finger lifts, then fades over two more.
            if (m.tool == Tool.LASER && m.t > 0 && now - m.t > 4000) { it.remove(); continue }
            when (m.tool) {
                Tool.PLANE -> plane(c, m.pts[0], m.pts[1], m.pts[2], m.color)
                else -> {
                    if (m.pts.size < 2) continue
                    val path = Path().apply {
                        moveTo(m.pts[0], m.pts[1])
                        if (m.pts.size == 2) lineTo(m.pts[0] + 0.1f, m.pts[1])
                        var i = 2
                        while (i + 1 < m.pts.size) { lineTo(m.pts[i], m.pts[i + 1]); i += 2 }
                    }
                    p.pathEffect = null
                    when (m.tool) {
                        Tool.MARKER -> { p.color = (m.color and 0x00FFFFFF) or 0x66000000; p.strokeWidth = 16 * d; p.strokeCap = Paint.Cap.SQUARE }
                        Tool.PENCIL -> { p.color = (m.color and 0x00FFFFFF) or 0xCC000000.toInt(); p.strokeWidth = 1.8f * d; p.strokeCap = Paint.Cap.ROUND }
                        Tool.LASER, Tool.NEON -> {
                            val fade = if (m.tool == Tool.NEON || m.t == 0L) 1f else (1f - (now - m.t - 2000) / 2000f).coerceIn(0f, 1f)
                            if (m.tool == Tool.LASER) live = true
                            p.strokeCap = Paint.Cap.ROUND
                            // Neon as a sign glows: a wide soft halo, a strong coloured tube, a white-hot core.
                            p.color = (m.color and 0x00FFFFFF) or ((0x50 * fade).toInt() shl 24); p.strokeWidth = 24 * d
                            c.drawPath(path, p)
                            p.color = (m.color and 0x00FFFFFF) or ((0xE6 * fade).toInt() shl 24); p.strokeWidth = 10 * d
                            c.drawPath(path, p)
                            p.color = 0x00FFFFFF or ((0xF0 * fade).toInt() shl 24); p.strokeWidth = 3.5f * d
                        }
                        Tool.RULER -> { p.color = m.color; p.strokeWidth = 3 * d; p.strokeCap = Paint.Cap.ROUND }
                        else -> { p.color = m.color; p.strokeWidth = 3.2f * d; p.strokeCap = Paint.Cap.ROUND }
                    }
                    c.drawPath(path, p)
                    if (m.tool == Tool.RULER && m.pts.size >= 4) {
                        // The straightedge's angle, as a bearing on the screen.
                        val ang = (Math.toDegrees(Math.atan2((m.pts[2] - m.pts[0]).toDouble(), -(m.pts[3] - m.pts[1]).toDouble())) + 360) % 360
                        val s = "%03.0f°".format(ang)
                        tx.color = m.color
                        c.drawText(s, (m.pts[0] + m.pts[2]) / 2 + 8 * d, (m.pts[1] + m.pts[3]) / 2 - 8 * d, tx)
                    }
                }
            }
        }
        if (live) postInvalidateOnAnimation()
    }

    private fun plane(c: Canvas, x: Float, y: Float, rot: Float, color: Int) {
        val s = 16 * d
        val path = Path().apply {
            moveTo(0f, -s); lineTo(s * 0.18f, -s * 0.2f); lineTo(s, s * 0.25f); lineTo(s, s * 0.45f); lineTo(s * 0.18f, s * 0.2f)
            lineTo(s * 0.15f, s * 0.7f); lineTo(s * 0.45f, s); lineTo(-s * 0.45f, s); lineTo(-s * 0.15f, s * 0.7f)
            lineTo(-s * 0.18f, s * 0.2f); lineTo(-s, s * 0.45f); lineTo(-s, s * 0.25f); lineTo(-s * 0.18f, -s * 0.2f); close()
        }
        c.save(); c.translate(x, y); c.rotate(rot)
        f.color = 0xFF000000.toInt(); f.style = Paint.Style.STROKE; f.strokeWidth = 2.5f * d; c.drawPath(path, f)
        f.style = Paint.Style.FILL; f.color = color; c.drawPath(path, f)
        c.restore()
    }

    companion object {
        private const val TAG = "ink_palette"

        fun isOpen(act: Activity) = act.findViewById<FrameLayout>(android.R.id.content)?.findViewWithTag<View>(TAG) != null

        /** Opens the palette over the screen (or closes it when open). */
        fun toggle(act: Activity) {
            val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
            content.findViewWithTag<View>(TAG)?.let { content.removeView(it); return }
            val dd = act.resources.displayMetrics.density
            fun dp(v: Int) = (v * dd).toInt()
            val prefs = VaultLock.prefs(act)
            val box = FrameLayout(act).apply { tag = TAG; elevation = dp(30).toFloat() }
            val ink = InkSheet(act).apply { color = prefs.getInt("ink_color", 0xFFFF3B30.toInt()) }
            box.addView(ink, FrameLayout.LayoutParams(-1, -1))

            // The capsule.
            val bar = LinearLayout(act).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(6), dp(5), dp(8), dp(5)); layoutDirection = View.LAYOUT_DIRECTION_LTR
                background = GradientDrawable().apply { setColor(0xF01C1C1E.toInt()); cornerRadius = dp(30).toFloat(); setStroke(dp(1), 0xFF3A3A3C.toInt()) }
                elevation = dp(14).toFloat()
            }
            val grip = TextView(act).apply { text = "⋮⋮"; textSize = 16f; setTextColor(0xFF8E8E93.toInt()); setPadding(dp(8), dp(6), dp(6), dp(6)) }
            bar.addView(grip)
            val toolViews = HashMap<Tool, TextView>()
            fun mark() = toolViews.forEach { (t, v) ->
                v.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(if (t == ink.tool) 0xFF0A84FF.toInt() else 0x00000000) }
            }
            fun btn(glyph: String, size: Float = 18f, onClick: (TextView) -> Unit) = TextView(act).apply {
                text = glyph; textSize = size; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt())
                setOnClickListener { onClick(this) }
            }
            for ((t, g) in listOf(Tool.HAND to "✋", Tool.PEN to "🖊", Tool.MARKER to "🖍", Tool.ERASER to "",
                Tool.RULER to "📏", Tool.PLANE to "✈️", Tool.NEON to "✨", Tool.LASER to "🔴")) {
                val v = btn(g, 18f) { ink.tool = t; mark() }
                if (t == Tool.ERASER) {
                    // A real eraser, drawn, not a delete key.
                    val dr = androidx.core.content.ContextCompat.getDrawable(act, R.drawable.ic_tool_eraser)?.mutate()?.apply { setTint(0xFFFFFFFF.toInt()); setBounds(0, 0, dp(22), dp(22)) }
                    v.setCompoundDrawables(dr, null, null, null)
                    v.setPadding(dp(10), 0, 0, 0)
                }
                toolViews[t] = v
                bar.addView(v, LinearLayout.LayoutParams(dp(42), dp(42)).apply { marginEnd = dp(2) })
            }
            mark()
            bar.addView(View(act).apply { setBackgroundColor(0xFF3A3A3C.toInt()) }, LinearLayout.LayoutParams(dp(1), dp(28)).apply { setMargins(dp(4), 0, dp(6), 0) })
            // The colour: a ringed dot; a tap opens the swatches under the bar.
            val swatch = View(act)
            fun paintSwatch() { swatch.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(ink.color); setStroke(dp(3), 0xFFFFFFFF.toInt()) } }
            paintSwatch()
            val colors = LinearLayout(act).apply {
                orientation = LinearLayout.HORIZONTAL; visibility = View.GONE; setPadding(dp(10), dp(8), dp(10), dp(8))
                background = GradientDrawable().apply { setColor(0xF01C1C1E.toInt()); cornerRadius = dp(24).toFloat() }
                elevation = dp(14).toFloat()
            }
            for (cl in intArrayOf(0xFFFFFFFF.toInt(), 0xFF000000.toInt(), 0xFFFF1744.toInt(), 0xFFFF9100.toInt(), 0xFFFFEA00.toInt(), 0xFF39FF14.toInt(),
                0xFF00E5FF.toInt(), 0xFF2979FF.toInt(), 0xFFD500F9.toInt(), 0xFFFF2BD6.toInt())) {
                colors.addView(View(act).apply {
                    background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(cl); setStroke(dp(1), 0xFF636366.toInt()) }
                    setOnClickListener { ink.color = cl; prefs.edit().putInt("ink_color", cl).apply(); paintSwatch(); colors.visibility = View.GONE }
                }, LinearLayout.LayoutParams(dp(30), dp(30)).apply { marginEnd = dp(8) })
            }
            swatch.setOnClickListener { colors.visibility = if (colors.visibility == View.VISIBLE) View.GONE else View.VISIBLE }
            bar.addView(swatch, LinearLayout.LayoutParams(dp(30), dp(30)).apply { marginEnd = dp(6) })
            bar.addView(btn("↶", 20f) { ink.undo() }, LinearLayout.LayoutParams(dp(38), dp(42)))
            bar.addView(btn("🗑", 17f) { ink.clear() }, LinearLayout.LayoutParams(dp(38), dp(42)))
            bar.addView(btn("📝", 17f) { if (NotePad.isOpen()) NotePad.close(act) else Notebooks.scratch(act) }, LinearLayout.LayoutParams(dp(38), dp(42)))
            bar.addView(btn("✓", 20f) { (box.parent as? ViewGroup)?.removeView(box) }, LinearLayout.LayoutParams(dp(38), dp(42)))

            val holder = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL }
            holder.addView(HorizontalScrollView(act).apply { isHorizontalScrollBarEnabled = false; addView(bar) })
            holder.addView(colors, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(6) })
            box.addView(holder, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply { bottomMargin = dp(150) })
            holder.translationX = prefs.getFloat("ink_x", 0f); holder.translationY = prefs.getFloat("ink_y", 0f)

            // Dragged by its grip, anywhere on the screen; the place is kept.
            var sx = 0f; var sy = 0f; var hx = 0f; var hy = 0f
            grip.setOnTouchListener { _, e ->
                when (e.actionMasked) {
                    MotionEvent.ACTION_DOWN -> { sx = e.rawX; sy = e.rawY; hx = holder.translationX; hy = holder.translationY }
                    MotionEvent.ACTION_MOVE -> { holder.translationX = hx + e.rawX - sx; holder.translationY = hy + e.rawY - sy }
                    MotionEvent.ACTION_UP -> prefs.edit().putFloat("ink_x", holder.translationX).putFloat("ink_y", holder.translationY).apply()
                }
                true
            }
            content.addView(box, FrameLayout.LayoutParams(-1, -1))
            holder.alpha = 0f; holder.scaleX = 0.92f; holder.scaleY = 0.92f
            holder.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(160).start()
        }
    }
}
