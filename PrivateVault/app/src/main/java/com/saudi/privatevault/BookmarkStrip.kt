package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs

/**
 * Coloured bookmark marks lined up with the page slider under them; a tap on
 * one goes to its page.
 */
class BookmarkStrip @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    var onPick: ((Int) -> Unit)? = null

    /** The slider's inset at each end, so marks sit over the right pages. */
    var trackInset = 0f

    private var pages = 0
    private var marks: List<Pair<Int, Int>> = emptyList()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val path = Path()
    private val d = resources.displayMetrics.density

    fun set(pageCount: Int, pageColors: List<Pair<Int, Int>>) {
        pages = pageCount
        marks = pageColors
        visibility = if (pageCount >= 2 && pageColors.isNotEmpty()) VISIBLE else GONE
        invalidate()
    }

    private fun xOf(page: Int): Float {
        val frac = page.toFloat() / (pages - 1).coerceAtLeast(1)
        val usable = width - 2 * trackInset
        // The slider runs right to left in an Arabic layout.
        return if (layoutDirection == LAYOUT_DIRECTION_RTL) width - trackInset - frac * usable else trackInset + frac * usable
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), (16 * d).toInt())
    }

    override fun onDraw(canvas: Canvas) {
        if (pages < 2) return
        val h = height.toFloat()
        for ((page, color) in marks) {
            val x = xOf(page)
            paint.color = color
            path.reset()
            path.moveTo(x - 5 * d, 1 * d)
            path.lineTo(x + 5 * d, 1 * d)
            path.lineTo(x + 5 * d, h - 5 * d)
            path.lineTo(x, h - 1 * d)
            path.lineTo(x - 5 * d, h - 5 * d)
            path.close()
            canvas.drawPath(path, paint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_UP) {
            val near = marks.minByOrNull { abs(xOf(it.first) - event.x) }
            if (near != null && abs(xOf(near.first) - event.x) < 24 * d) {
                onPick?.invoke(near.first)
                performClick()
            }
        }
        return true
    }

    override fun performClick(): Boolean = super.performClick()
}
