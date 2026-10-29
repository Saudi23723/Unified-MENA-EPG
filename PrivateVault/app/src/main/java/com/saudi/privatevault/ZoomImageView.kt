package com.saudi.privatevault

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.graphics.RectF
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import androidx.appcompat.widget.AppCompatImageView
import kotlin.math.abs

/** Image view with pinch zoom, drag, double-tap zoom, and swipe when not zoomed. */
class ZoomImageView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : AppCompatImageView(context, attrs) {

    /** -1 for a swipe towards the previous item, +1 towards the next one. */
    var onSwipe: ((Int) -> Unit)? = null
    var onTap: (() -> Unit)? = null

    private val m = Matrix()
    private val values = FloatArray(9)
    private var minScale = 1f

    // Where the current touch began, and whether it turned into a pinch.
    private var downX = 0f
    private var downY = 0f
    private var pinched = false

    private val scaleDetector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            pinched = true
            val cur = currentScale()
            val target = (cur * detector.scaleFactor).coerceIn(minScale, minScale * 8f)
            val f = target / cur
            m.postScale(f, f, detector.focusX, detector.focusY)
            apply()
            return true
        }
    })

    private val gestures = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDown(e: MotionEvent) = true

        override fun onScroll(e1: MotionEvent?, e2: MotionEvent, distanceX: Float, distanceY: Float): Boolean {
            if (!isZoomed()) return false
            m.postTranslate(-distanceX, -distanceY)
            apply()
            return true
        }

        override fun onDoubleTap(e: MotionEvent): Boolean {
            if (isZoomed()) {
                fit()
            } else {
                m.postScale(2.5f, 2.5f, e.x, e.y)
                apply()
            }
            return true
        }

        override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
            onTap?.invoke()
            return true
        }
    })

    init {
        scaleType = ScaleType.MATRIX
    }

    /**
     * Like turning a page: dragging up or to the left goes forward, down or
     * to the right goes back. Pages follow the document, not the RTL screen.
     */
    private fun swipe(dx: Float, dy: Float) {
        val horizontal = abs(dx) > abs(dy)
        val far = if (horizontal) abs(dx) > width / 8f else abs(dy) > height / 10f
        if (!far) return
        val forward = if (horizontal) dx < 0 else dy < 0
        onSwipe?.invoke(if (forward) 1 else -1)
    }

    override fun setImageBitmap(bm: Bitmap?) {
        super.setImageBitmap(bm)
        fit()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        fit()
    }

    fun fit() {
        val d = drawable ?: return
        if (width == 0 || height == 0 || d.intrinsicWidth <= 0 || d.intrinsicHeight <= 0) return
        val dw = d.intrinsicWidth.toFloat()
        val dh = d.intrinsicHeight.toFloat()
        val s = minOf(width / dw, height / dh)
        m.reset()
        m.postScale(s, s)
        m.postTranslate((width - dw * s) / 2f, (height - dh * s) / 2f)
        minScale = s
        imageMatrix = m
    }

    private fun currentScale(): Float {
        m.getValues(values)
        return values[Matrix.MSCALE_X]
    }

    private fun isZoomed() = currentScale() > minScale * 1.02f

    /** Keep the picture centred while smaller than the view, and its edges on screen when bigger. */
    private fun apply() {
        val d = drawable ?: return
        val r = RectF(0f, 0f, d.intrinsicWidth.toFloat(), d.intrinsicHeight.toFloat())
        m.mapRect(r)
        val dx = when {
            r.width() <= width -> (width - r.width()) / 2f - r.left
            r.left > 0 -> -r.left
            r.right < width -> width - r.right
            else -> 0f
        }
        val dy = when {
            r.height() <= height -> (height - r.height()) / 2f - r.top
            r.top > 0 -> -r.top
            r.bottom < height -> height - r.bottom
            else -> 0f
        }
        m.postTranslate(dx, dy)
        imageMatrix = m
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.x
                downY = event.y
                pinched = false
            }
            MotionEvent.ACTION_UP -> if (!pinched && !isZoomed()) swipe(event.x - downX, event.y - downY)
        }
        scaleDetector.onTouchEvent(event)
        gestures.onTouchEvent(event)
        parent?.requestDisallowInterceptTouchEvent(isZoomed())
        return true
    }
}
