package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.MotionEvent
import android.widget.FrameLayout

/**
 * The frame a figure is taken through. It sits over the page and does nothing at all until it is
 * armed; then it dims the page, takes the drag of a finger as the corners of a box, and hands back
 * that rectangle so the picture under it can be cut out. One box, then it steps aside again.
 */
class ClipFrame(ctx: Context) : FrameLayout(ctx) {

    private var armed = false
    private var onBox: ((Int, Int, Int, Int) -> Unit)? = null
    private var x0 = 0f; private var y0 = 0f; private var x1 = 0f; private var y1 = 0f
    private var drawing = false
    private val d = resources.displayMetrics.density

    private val shade = Paint().apply { color = 0x66000000 }
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 2.5f * d; color = 0xFFFF9F0A.toInt()
    }
    private val corner = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 5f * d; color = 0xFFFF9F0A.toInt(); strokeCap = Paint.Cap.ROUND
    }
    private val hint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFFFFFFFF.toInt(); textSize = 14f * d; isFakeBoldText = true; textAlign = Paint.Align.CENTER
    }
    private val hintBg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xE6000000.toInt() }

    init { setWillNotDraw(false) }

    /** Wait for one box, then give it back and stand down. */
    fun arm(onBox: (left: Int, top: Int, width: Int, height: Int) -> Unit) {
        this.onBox = onBox
        armed = true
        drawing = false
        invalidate()
    }

    fun disarm() { armed = false; drawing = false; onBox = null; invalidate() }

    override fun onInterceptTouchEvent(e: MotionEvent): Boolean = armed

    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (!armed) return false
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> { x0 = e.x; y0 = e.y; x1 = e.x; y1 = e.y; drawing = true }
            MotionEvent.ACTION_MOVE -> { x1 = e.x; y1 = e.y }
            MotionEvent.ACTION_UP -> {
                x1 = e.x; y1 = e.y
                val l = Math.min(x0, x1).toInt(); val t = Math.min(y0, y1).toInt()
                val w = Math.abs(x1 - x0).toInt(); val h = Math.abs(y1 - y0).toInt()
                val give = onBox
                disarm()
                give?.invoke(l, t, w, h)
                return true
            }
            MotionEvent.ACTION_CANCEL -> { disarm(); return true }
        }
        invalidate()
        return true
    }

    override fun onDraw(c: Canvas) {
        if (!armed) return
        val w = width.toFloat(); val h = height.toFloat()
        if (drawing) {
            // Everything but the framed part is dimmed, so what will be cut out is the bright part.
            val r = RectF(Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1))
            c.drawRect(0f, 0f, w, r.top, shade)
            c.drawRect(0f, r.bottom, w, h, shade)
            c.drawRect(0f, r.top, r.left, r.bottom, shade)
            c.drawRect(r.right, r.top, w, r.bottom, shade)
            c.drawRect(r, edge)
            // The corners, so the box reads as a frame and not as a stray line.
            val k = 18 * d
            for (q in listOf(
                Quad(r.left, r.top, 1f, 1f), Quad(r.right, r.top, -1f, 1f),
                Quad(r.left, r.bottom, 1f, -1f), Quad(r.right, r.bottom, -1f, -1f))) {
                c.drawLine(q.x, q.y, q.x + k * q.sx, q.y, corner)
                c.drawLine(q.x, q.y, q.x, q.y + k * q.sy, corner)
            }
            val s = "%d × %d".format(Math.abs(x1 - x0).toInt(), Math.abs(y1 - y0).toInt())
            val tw = hint.measureText(s)
            val by = if (r.top > 46 * d) r.top - 12 * d else r.bottom + 32 * d
            c.drawRoundRect(r.centerX() - tw / 2 - 10 * d, by - 20 * d, r.centerX() + tw / 2 + 10 * d, by + 6 * d,
                8 * d, 8 * d, hintBg)
            c.drawText(s, r.centerX(), by, hint)
        } else {
            c.drawRect(0f, 0f, w, h, shade)
            val s = "Drag a box over the figure or the table"
            val tw = hint.measureText(s)
            val cx = w / 2f
            val by = 54 * d
            c.drawRoundRect(cx - tw / 2 - 14 * d, by - 24 * d, cx + tw / 2 + 14 * d, by + 8 * d, 10 * d, 10 * d, hintBg)
            c.drawText(s, cx, by, hint)
        }
    }

    private class Quad(val x: Float, val y: Float, val sx: Float, val sy: Float)
}
