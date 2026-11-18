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
    private val inside = Paint().apply { color = 0x22FF9F0A }
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
        c.drawRect(0f, 0f, width.toFloat(), height.toFloat(), shade)
        if (drawing) {
            val r = RectF(Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1))
            c.drawRect(r, inside)
            c.drawRect(r, edge)
        } else {
            val s = "Drag a box over the figure or the table"
            val w = hint.measureText(s)
            val cx = width / 2f
            c.drawRoundRect(cx - w / 2 - 14 * d, height / 2f - 22 * d, cx + w / 2 + 14 * d, height / 2f + 10 * d,
                10 * d, 10 * d, hintBg)
            c.drawText(s, cx, height / 2f, hint)
        }
    }
}
