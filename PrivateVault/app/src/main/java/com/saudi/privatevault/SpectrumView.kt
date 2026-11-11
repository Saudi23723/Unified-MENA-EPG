package com.saudi.privatevault

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View

/**
 * The spectrum, as in Samsung Notes: every hue left to right, white at the top to full colour,
 * then dark at the bottom. A touch picks the colour under the finger.
 */
class SpectrumView(ctx: Context) : View(ctx) {
    var onPick: ((Int) -> Unit)? = null
    private var bmp: Bitmap? = null
    private var px = -1f
    private var py = -1f
    private val d = ctx.resources.displayMetrics.density
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 3 * d; color = Color.WHITE }
    private val ringDark = Paint(ring).apply { color = 0x88000000.toInt(); strokeWidth = 5 * d }
    private val clip = android.graphics.Path()

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        setMeasuredDimension(width, (width * 0.55f).toInt())
    }

    override fun onSizeChanged(w: Int, h: Int, ow: Int, oh: Int) {
        if (w <= 0 || h <= 0) return
        val sw = (w / 2).coerceAtLeast(1); val sh = (h / 2).coerceAtLeast(1)
        val b = Bitmap.createBitmap(sw, sh, Bitmap.Config.ARGB_8888)
        val hsv = FloatArray(3)
        for (y in 0 until sh) for (x in 0 until sw) b.setPixel(x, y, at(x.toFloat() / sw, y.toFloat() / sh, hsv))
        bmp = b
        clip.reset(); clip.addRoundRect(RectF(0f, 0f, w.toFloat(), h.toFloat()), 12 * d, 12 * d, android.graphics.Path.Direction.CW)
    }

    /** Hue across; down the first half white to full, the second half full to near black. */
    private fun at(fx: Float, fy: Float, hsv: FloatArray): Int {
        hsv[0] = fx * 360f
        if (fy < 0.5f) { hsv[1] = fy * 2f; hsv[2] = 1f } else { hsv[1] = 1f; hsv[2] = 1f - (fy - 0.5f) * 1.8f }
        return Color.HSVToColor(hsv)
    }

    override fun onDraw(c: Canvas) {
        val b = bmp ?: return
        c.save(); c.clipPath(clip)
        c.drawBitmap(b, null, RectF(0f, 0f, width.toFloat(), height.toFloat()), Paint(Paint.FILTER_BITMAP_FLAG))
        c.restore()
        if (px >= 0) { c.drawCircle(px, py, 11 * d, ringDark); c.drawCircle(px, py, 11 * d, ring) }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        parent?.requestDisallowInterceptTouchEvent(true)
        px = e.x.coerceIn(0f, width - 1f); py = e.y.coerceIn(0f, height - 1f)
        onPick?.invoke(at(px / width, py / height, FloatArray(3)))
        invalidate()
        return true
    }
}
