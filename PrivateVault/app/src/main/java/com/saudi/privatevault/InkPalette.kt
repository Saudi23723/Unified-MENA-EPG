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
 * stamp, fading neon), the colour, undo, clear and done. The hand lets the screen underneath work; any
 * other tool writes on a clear sheet over it.
 */
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
class InkSheet(ctx: Context) : View(ctx) {
    enum class Tool { HAND, PEN, MARKER, PENCIL, ERASER, RULER, PLANE, NEON, NEON_FADE }

    private class Mark(val tool: Tool, val color: Int, val pts: ArrayList<Float>, var t: Long = 0L, val w: Float = 1f)

    var tool = Tool.PEN
    var color = 0xFFFF3B30.toInt()
    /** The pen's size: small, medium, large (a factor on every tool's width). */
    var size = 1f
    /** True while the ruler is sitting on a clean angle, so the tap is felt once, not continuously. */
    private var wasLevel = false
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
                    Tool.PLANE -> { marks.add(Mark(Tool.PLANE, color, arrayListOf(x, y, 0f), w = size)); undone.clear() }
                    else -> { cur = Mark(tool, color, arrayListOf(x, y), w = size).also { marks.add(it); undone.clear() } }
                }
            }
            MotionEvent.ACTION_MOVE -> {
                when (tool) {
                    Tool.ERASER -> erase(x, y)
                    // The airplane stamp turns toward the drag.
                    Tool.PLANE -> marks.lastOrNull()?.let { m -> m.pts[2] = Math.toDegrees(Math.atan2((x - m.pts[0]).toDouble(), -(y - m.pts[1]).toDouble())).toFloat() }
                    Tool.RULER -> cur?.let { m ->
                        while (m.pts.size > 2) m.pts.removeAt(m.pts.size - 1)
                        // Within a couple of degrees of level, upright, or a clean 45: the line
                        // clicks onto it and the tablet taps your hand, so a straight line is straight.
                        val dx = x - m.pts[0]; val dy = y - m.pts[1]
                        val len = Math.hypot(dx.toDouble(), dy.toDouble())
                        var nx = x; var ny = y
                        var snapped = false
                        if (len > 12 * d) {
                            val ang = Math.toDegrees(Math.atan2(dy.toDouble(), dx.toDouble()))
                            val step = Math.round(ang / 45.0) * 45.0
                            if (Math.abs(((ang - step + 540) % 360) - 180) < 2.5) {
                                nx = (m.pts[0] + len * Math.cos(Math.toRadians(step))).toFloat()
                                ny = (m.pts[1] + len * Math.sin(Math.toRadians(step))).toFloat()
                                snapped = true
                            }
                        }
                        if (snapped != wasLevel) {
                            wasLevel = snapped
                            if (snapped) try {
                                performHapticFeedback(android.view.HapticFeedbackConstants.KEYBOARD_TAP,
                                    android.view.HapticFeedbackConstants.FLAG_IGNORE_GLOBAL_SETTING)
                            } catch (e: Exception) { }
                        }
                        m.pts.add(nx); m.pts.add(ny)
                    }
                    else -> cur?.pts?.apply { add(x); add(y) }
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                cur?.let { if (it.tool == Tool.NEON_FADE) it.t = SystemClock.uptimeMillis() }
                cur = null
                wasLevel = false
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
            // Fading neon stays bright two seconds after the finger lifts, then fades over two more.
            if (m.tool == Tool.NEON_FADE && m.t > 0 && now - m.t > 4000) { it.remove(); continue }
            when (m.tool) {
                Tool.PLANE -> plane(c, m.pts[0], m.pts[1], m.pts[2], m.color, m.w)
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
                        Tool.MARKER -> { p.color = (m.color and 0x00FFFFFF) or 0x66000000; p.strokeWidth = 16 * d * m.w; p.strokeCap = Paint.Cap.SQUARE }
                        Tool.PENCIL -> { p.color = (m.color and 0x00FFFFFF) or 0xCC000000.toInt(); p.strokeWidth = 1.8f * d * m.w; p.strokeCap = Paint.Cap.ROUND }
                        Tool.NEON_FADE, Tool.NEON -> {
                            val fade = if (m.tool == Tool.NEON || m.t == 0L) 1f else (1f - (now - m.t - 2000) / 2000f).coerceIn(0f, 1f)
                            if (m.tool == Tool.NEON_FADE) live = true
                            p.strokeCap = Paint.Cap.ROUND
                            // Neon as a sign glows: a wide soft halo, a strong coloured tube, a white-hot core.
                            p.color = (m.color and 0x00FFFFFF) or ((0x50 * fade).toInt() shl 24); p.strokeWidth = 24 * d * m.w
                            c.drawPath(path, p)
                            p.color = (m.color and 0x00FFFFFF) or ((0xE6 * fade).toInt() shl 24); p.strokeWidth = 10 * d * m.w
                            c.drawPath(path, p)
                            p.color = 0x00FFFFFF or ((0xF0 * fade).toInt() shl 24); p.strokeWidth = 3.5f * d * m.w
                        }
                        Tool.RULER -> { p.color = m.color; p.strokeWidth = 3 * d * m.w; p.strokeCap = Paint.Cap.ROUND }
                        else -> { p.color = m.color; p.strokeWidth = 3.2f * d * m.w; p.strokeCap = Paint.Cap.ROUND }
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

    private fun plane(c: Canvas, x: Float, y: Float, rot: Float, color: Int, w: Float = 1f) {
        val s = 16 * d * w
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

            // The capsule: a dark glass bar with line icons, the tool in use on a blue disc, as a
            // modern drawing app has it; the colour, the size, undo, clear, notes and done at its end.
            val bar = LinearLayout(act).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(6), dp(6), dp(8), dp(6)); layoutDirection = View.LAYOUT_DIRECTION_LTR
                background = GradientDrawable().apply { setColor(0xEB202226.toInt()); cornerRadius = dp(28).toFloat(); setStroke(dp(1), 0x26FFFFFF) }
                elevation = dp(16).toFloat()
            }
            // The handle to drag it by: a short pill, not a symbol.
            val grip = FrameLayout(act).apply {
                addView(View(act).apply { background = GradientDrawable().apply { setColor(0x66FFFFFF); cornerRadius = dp(2).toFloat() } },
                    FrameLayout.LayoutParams(dp(4), dp(20), Gravity.CENTER))
            }
            bar.addView(grip, LinearLayout.LayoutParams(dp(22), dp(40)))
            val toolViews = HashMap<Tool, android.widget.ImageView>()
            fun mark() = toolViews.forEach { (t, v) ->
                val on = t == ink.tool
                v.background = if (on) GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0xFF2D8CFF.toInt()) } else null
                v.setColorFilter(if (on) 0xFFFFFFFF.toInt() else 0xD9FFFFFF.toInt())
            }
            fun icon(res: Int, onClick: () -> Unit) = android.widget.ImageView(act).apply {
                setImageResource(res); setColorFilter(0xD9FFFFFF.toInt())
                scaleType = android.widget.ImageView.ScaleType.CENTER_INSIDE
                setPadding(dp(9), dp(9), dp(9), dp(9))
                setOnClickListener { onClick() }
            }
            for ((t, res) in listOf(Tool.HAND to R.drawable.ic_tool_hand, Tool.PEN to R.drawable.ic_tool_pen, Tool.MARKER to R.drawable.ic_tool_highlight,
                Tool.ERASER to R.drawable.ic_tool_eraser, Tool.RULER to R.drawable.ic_ruler, Tool.PLANE to R.drawable.ic_tool_plane,
                Tool.NEON to R.drawable.ic_tool_neon, Tool.NEON_FADE to R.drawable.ic_tool_neon_fade)) {
                val v = icon(res) { ink.tool = t; mark() }
                v.contentDescription = t.name.lowercase()
                toolViews[t] = v
                bar.addView(v, LinearLayout.LayoutParams(dp(40), dp(40)).apply { marginEnd = dp(3) })
            }
            mark()
            bar.addView(View(act).apply { setBackgroundColor(0x33FFFFFF) }, LinearLayout.LayoutParams(dp(1), dp(26)).apply { setMargins(dp(5), 0, dp(8), 0) })
            // The colour: a ringed dot; a tap opens the swatches under the bar.
            val swatch = View(act)
            fun paintSwatch() { swatch.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(ink.color); setStroke(dp(2), 0xFFFFFFFF.toInt()) } }
            paintSwatch()
            val colors = LinearLayout(act).apply {
                orientation = LinearLayout.HORIZONTAL; visibility = View.GONE; setPadding(dp(10), dp(8), dp(10), dp(8))
                background = GradientDrawable().apply { setColor(0xEB202226.toInt()); cornerRadius = dp(24).toFloat(); setStroke(dp(1), 0x26FFFFFF) }
                elevation = dp(16).toFloat()
            }
            for (cl in intArrayOf(0xFFFFFFFF.toInt(), 0xFF000000.toInt(), 0xFFFF1744.toInt(), 0xFFFF9100.toInt(), 0xFFFFEA00.toInt(), 0xFF39FF14.toInt(),
                0xFF00E5FF.toInt(), 0xFF2979FF.toInt(), 0xFFD500F9.toInt(), 0xFFFF2BD6.toInt())) {
                colors.addView(View(act).apply {
                    background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(cl); setStroke(dp(1), 0xFF636366.toInt()) }
                    setOnClickListener { ink.color = cl; prefs.edit().putInt("ink_color", cl).apply(); paintSwatch(); colors.visibility = View.GONE }
                }, LinearLayout.LayoutParams(dp(30), dp(30)).apply { marginEnd = dp(8) })
            }
            swatch.setOnClickListener { colors.visibility = if (colors.visibility == View.VISIBLE) View.GONE else View.VISIBLE }
            bar.addView(swatch, LinearLayout.LayoutParams(dp(26), dp(26)).apply { marginEnd = dp(8) })
            // The size: a dot that grows with it.
            val sizes = floatArrayOf(0.45f, 1f, 1.8f)
            ink.size = sizes[prefs.getInt("ink_size", 1).coerceIn(0, 2)]
            val sizeBtn = FrameLayout(act)
            val sizeDot = View(act)
            sizeBtn.addView(sizeDot)
            fun paintSize() {
                val i = sizes.indexOfFirst { it == ink.size }.coerceAtLeast(0)
                val px = dp(6 + i * 5)
                sizeDot.layoutParams = FrameLayout.LayoutParams(px, px, Gravity.CENTER)
                sizeDot.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0xFFFFFFFF.toInt()) }
                sizeBtn.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0x22FFFFFF) }
            }
            paintSize()
            sizeBtn.setOnClickListener {
                val i = (sizes.indexOfFirst { it == ink.size } + 1) % sizes.size
                ink.size = sizes[i]; prefs.edit().putInt("ink_size", i).apply(); paintSize()
            }
            bar.addView(sizeBtn, LinearLayout.LayoutParams(dp(32), dp(32)).apply { marginEnd = dp(6) })
            bar.addView(icon(R.drawable.ic_undo) { ink.undo() }, LinearLayout.LayoutParams(dp(38), dp(40)))
            bar.addView(icon(R.drawable.ic_delete) { ink.clear() }, LinearLayout.LayoutParams(dp(38), dp(40)))
            bar.addView(icon(R.drawable.ic_tool_note) { if (NotePad.isOpen()) NotePad.close(act) else Notebooks.scratch(act) }, LinearLayout.LayoutParams(dp(38), dp(40)))
            bar.addView(icon(R.drawable.ic_check) { (box.parent as? ViewGroup)?.removeView(box) }.apply {
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0x332D8CFF) }
            }, LinearLayout.LayoutParams(dp(38), dp(38)).apply { marginStart = dp(2) })

            val holder = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL }
            holder.addView(HorizontalScrollView(act).apply { isHorizontalScrollBarEnabled = false; addView(bar) })
            holder.addView(colors, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(6) })
            box.addView(holder, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply { bottomMargin = dp(150) })
            // Dragged by its handle anywhere on the screen; the place is kept, but never off the screen:
            // a bar dragged out of sight earlier would open where nobody could see it.
            fun clampIn() {
                if (box.width == 0 || holder.width == 0) return
                val baseX = (box.width - holder.width) / 2f
                val baseY = box.height - dp(150) - holder.height.toFloat()
                val minX = -baseX + dp(4); val maxX = baseX - dp(4)
                val minY = -baseY + dp(40); val maxY = dp(140).toFloat()
                holder.translationX = holder.translationX.coerceIn(minOf(minX, 0f), maxOf(maxX, 0f))
                holder.translationY = holder.translationY.coerceIn(minOf(minY, 0f), maxY)
            }
            holder.translationX = prefs.getFloat("ink_x", 0f); holder.translationY = prefs.getFloat("ink_y", 0f)
            holder.post { clampIn() }
            var sx = 0f; var sy = 0f; var hx = 0f; var hy = 0f
            grip.setOnTouchListener { v, e ->
                when (e.actionMasked) {
                    MotionEvent.ACTION_DOWN -> { sx = e.rawX; sy = e.rawY; hx = holder.translationX; hy = holder.translationY; v.parent?.requestDisallowInterceptTouchEvent(true) }
                    MotionEvent.ACTION_MOVE -> { holder.translationX = hx + e.rawX - sx; holder.translationY = hy + e.rawY - sy }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { clampIn(); prefs.edit().putFloat("ink_x", holder.translationX).putFloat("ink_y", holder.translationY).apply() }
                }
                true
            }
            content.addView(box, FrameLayout.LayoutParams(-1, -1))
            holder.alpha = 0f; holder.scaleX = 0.92f; holder.scaleY = 0.92f
            holder.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(160).start()
        }
    }
}
