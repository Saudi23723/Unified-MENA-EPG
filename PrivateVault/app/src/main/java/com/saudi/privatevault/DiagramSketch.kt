package com.saudi.privatevault

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PointF
import android.view.MotionEvent
import android.view.View

/**
 * Drawing over a paused airport view, to explain a taxi route, a pattern or
 * a runway: pen, highlighter, straight line, arrow, ruler (the real distance
 * on the ground), circle, box, an airplane placed and turned with a drag, and
 * an eraser. Nothing is kept: it is gone when the view plays again.
 */
@SuppressLint("ViewConstructor")
class DiagramSketch(ctx: Context, private val plane: Bitmap, private val metres: (PointF, PointF) -> Double?) : View(ctx) {
    enum class Tool(val label: String) {
        PEN("🖊"), HIGHLIGHT("🖌"), LINE("📏 Line"), ARROW("➜"), RULER("📐 Ruler"), CIRCLE("◯"), BOX("▭"), PLANE("✈"), ERASER("🧽"),
    }

    private class Mark(val tool: Tool, val color: Int, val pts: ArrayList<PointF>)

    var tool = Tool.PEN
    var color = 0xFFFFEB3B.toInt()
    private val marks = ArrayList<Mark>()
    private var current: Mark? = null
    private val d = ctx.resources.displayMetrics.density
    private val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 15 * d; isFakeBoldText = true; color = Color.WHITE }
    private val labelBg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xCC000000.toInt() }

    override fun onDraw(c: Canvas) {
        for (m in marks) draw(c, m)
        current?.let { draw(c, it) }
    }

    private fun draw(c: Canvas, m: Mark) {
        val a = m.pts.first()
        val b = m.pts.last()
        p.style = Paint.Style.STROKE
        p.color = m.color
        p.alpha = 255
        p.strokeWidth = 4 * d
        p.pathEffect = null
        when (m.tool) {
            Tool.PEN, Tool.HIGHLIGHT -> {
                if (m.tool == Tool.HIGHLIGHT) { p.strokeWidth = 18 * d; p.alpha = 110 }
                val path = Path().apply { moveTo(a.x, a.y); for (q in m.pts) lineTo(q.x, q.y) }
                c.drawPath(path, p)
            }
            Tool.LINE -> c.drawLine(a.x, a.y, b.x, b.y, p)
            Tool.ARROW -> {
                c.drawLine(a.x, a.y, b.x, b.y, p)
                val ang = Math.atan2((b.y - a.y).toDouble(), (b.x - a.x).toDouble())
                val len = 18 * d
                for (s in listOf(-0.45, 0.45)) c.drawLine(b.x, b.y, (b.x - len * Math.cos(ang + s)).toFloat(), (b.y - len * Math.sin(ang + s)).toFloat(), p)
            }
            Tool.RULER -> {
                p.pathEffect = android.graphics.DashPathEffect(floatArrayOf(14 * d, 8 * d), 0f)
                c.drawLine(a.x, a.y, b.x, b.y, p)
                p.pathEffect = null
                p.style = Paint.Style.FILL
                c.drawCircle(a.x, a.y, 5 * d, p); c.drawCircle(b.x, b.y, 5 * d, p)
                metres(a, b)?.let { m2 ->
                    val t = "%,d ft · %,d m".format(Math.round(m2 * 3.28084), Math.round(m2))
                    val x = (a.x + b.x) / 2
                    val y = (a.y + b.y) / 2 - 10 * d
                    val w = label.measureText(t)
                    c.drawRoundRect(x - w / 2 - 8 * d, y - 18 * d, x + w / 2 + 8 * d, y + 7 * d, 8 * d, 8 * d, labelBg)
                    c.drawText(t, x - w / 2, y, label)
                }
            }
            Tool.CIRCLE -> c.drawCircle(a.x, a.y, Math.hypot((b.x - a.x).toDouble(), (b.y - a.y).toDouble()).toFloat(), p)
            Tool.BOX -> c.drawRect(minOf(a.x, b.x), minOf(a.y, b.y), maxOf(a.x, b.x), maxOf(a.y, b.y), p)
            Tool.PLANE -> {
                // Placed where touched, nose toward the drag.
                val deg = if (Math.hypot((b.x - a.x).toDouble(), (b.y - a.y).toDouble()) > 8 * d)
                    Math.toDegrees(Math.atan2((b.x - a.x).toDouble(), -(b.y - a.y).toDouble())).toFloat() else 0f
                c.save()
                c.rotate(deg, a.x, a.y)
                val s = 1.6f
                c.scale(s, s, a.x, a.y)
                c.drawBitmap(plane, a.x - plane.width / 2f, a.y - plane.height / 2f, null)
                c.restore()
            }
            Tool.ERASER -> {}
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        val pt = PointF(e.x, e.y)
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> if (tool == Tool.ERASER) erase(pt) else current = Mark(tool, color, arrayListOf(pt))
            MotionEvent.ACTION_MOVE -> if (tool == Tool.ERASER) erase(pt) else current?.let {
                if (tool == Tool.PEN || tool == Tool.HIGHLIGHT) it.pts.add(pt)
                else { if (it.pts.size > 1) it.pts[1] = pt else it.pts.add(pt) }
            }
            MotionEvent.ACTION_UP -> { current?.let { marks.add(it) }; current = null }
            MotionEvent.ACTION_CANCEL -> current = null
        }
        invalidate()
        return true
    }

    private fun erase(pt: PointF) {
        val r = 22 * d
        marks.removeAll { m ->
            if (m.pts.size == 1 || m.tool == Tool.PEN || m.tool == Tool.HIGHLIGHT || m.tool == Tool.PLANE) m.pts.any { Math.hypot((it.x - pt.x).toDouble(), (it.y - pt.y).toDouble()) < r }
            else {
                // Near any point of the straight line between the ends.
                val a = m.pts.first(); val b = m.pts.last()
                (0..20).any { i -> val f = i / 20f; Math.hypot((a.x + (b.x - a.x) * f - pt.x).toDouble(), (a.y + (b.y - a.y) * f - pt.y).toDouble()) < r }
            }
        }
    }

    fun undo() { if (marks.isNotEmpty()) { marks.removeAt(marks.size - 1); invalidate() } }
    fun clear() { marks.clear(); invalidate() }
}
