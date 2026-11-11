package com.saudi.privatevault

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import android.graphics.drawable.GradientDrawable
import android.os.SystemClock
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

/**
 * A laser pointer, as a presenter's: a bright glowing dot that follows the finger or
 * the pen, a short tail that fades in half a second, and nothing left once lifted.
 */
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
class LaserLayer(ctx: Context) : View(ctx) {
    var color = 0xFFFF2D2D.toInt()
    private class P(val x: Float, val y: Float, val t: Long)
    private val trail = ArrayList<P>()
    private var down = false
    private var upAt = 0L
    private var lastX = 0f
    private var lastY = 0f
    private val d = ctx.resources.displayMetrics.density
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val glow = Paint(Paint.ANTI_ALIAS_FLAG)
    private val core = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt() }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        val now = SystemClock.uptimeMillis()
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> { down = true; trail.clear(); add(e.x, e.y, now) }
            MotionEvent.ACTION_MOVE -> {
                for (i in 0 until e.historySize) add(e.getHistoricalX(i), e.getHistoricalY(i), e.getHistoricalEventTime(i))
                add(e.x, e.y, now)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { down = false; upAt = now }
        }
        postInvalidateOnAnimation()
        return true
    }

    private fun add(x: Float, y: Float, t: Long) { trail.add(P(x, y, t)); lastX = x; lastY = y }

    override fun onDraw(c: Canvas) {
        val now = SystemClock.uptimeMillis()
        trail.removeAll { now - it.t > TAIL_MS }
        // The tail: thinner and fainter the older it is.
        for (i in 1 until trail.size) {
            val a = trail[i - 1]; val b = trail[i]
            val f = 1f - (now - b.t).toFloat() / TAIL_MS
            line.color = color; line.alpha = (200 * f).toInt().coerceIn(0, 255); line.strokeWidth = (2 + 6 * f) * d
            c.drawLine(a.x, a.y, b.x, b.y, line)
        }
        // The dot: full while touching, fading once lifted.
        val dotA = if (down) 1f else (1f - (now - upAt).toFloat() / FADE_MS).coerceIn(0f, 1f)
        if (dotA > 0f && (down || upAt > 0)) {
            val r = 22 * d
            glow.shader = RadialGradient(lastX, lastY, r, intArrayOf(color, color and 0x00FFFFFF), floatArrayOf(0.15f, 1f), Shader.TileMode.CLAMP)
            glow.alpha = (255 * dotA).toInt()
            c.drawCircle(lastX, lastY, r, glow)
            core.alpha = (255 * dotA).toInt()
            c.drawCircle(lastX, lastY, 4.5f * d, core)
        }
        if (down || trail.isNotEmpty() || dotA > 0f) postInvalidateOnAnimation()
    }

    companion object {
        private const val TAG = "laser_layer"
        private const val TAIL_MS = 450L
        private const val FADE_MS = 600L

        /** Over the whole screen, with a small bar: the colour, and ✓ to put it away. */
        fun start(act: Activity) {
            val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
            content.findViewWithTag<View>(TAG)?.let { content.removeView(it); return }
            val dd = act.resources.displayMetrics.density
            fun dp(v: Int) = (v * dd).toInt()
            val box = FrameLayout(act).apply { tag = TAG; elevation = dp(30).toFloat() }
            val laser = LaserLayer(act)
            box.addView(laser, FrameLayout.LayoutParams(-1, -1))
            val bar = LinearLayout(act).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(12), dp(4), dp(6), dp(4)); layoutDirection = View.LAYOUT_DIRECTION_LTR
                background = GradientDrawable().apply { setColor(0xE6101214.toInt()); cornerRadius = dp(22).toFloat() }
            }
            bar.addView(TextView(act).apply { text = act.getString(R.string.laser); textSize = 14f; setTextColor(0xFFFFFFFF.toInt()); typeface = EfbUi.MEDIUM; setPadding(0, 0, dp(8), 0) })
            val dots = ArrayList<View>()
            for (cl in intArrayOf(0xFFFF2D2D.toInt(), 0xFF39FF14.toInt(), 0xFF2E9BFF.toInt(), 0xFFFFD60A.toInt())) {
                val dot = View(act).apply {
                    background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(cl); setStroke(dp(2), if (cl == laser.color) 0xFFFFFFFF.toInt() else 0) }
                    setOnClickListener {
                        laser.color = cl
                        dots.forEach { v -> (v.background as GradientDrawable).setStroke(dp(2), 0) }
                        (background as GradientDrawable).setStroke(dp(2), 0xFFFFFFFF.toInt())
                    }
                }
                dots.add(dot)
                bar.addView(dot, LinearLayout.LayoutParams(dp(24), dp(24)).apply { marginStart = dp(5); marginEnd = dp(5) })
            }
            bar.addView(TextView(act).apply {
                text = "✓"; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()); setPadding(dp(12), dp(6), dp(10), dp(6))
                setOnClickListener { (box.parent as? ViewGroup)?.removeView(box) }
            })
            box.addView(bar, FrameLayout.LayoutParams(-2, -2, Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = dp(60) })
            content.addView(box, FrameLayout.LayoutParams(-1, -1))
        }
    }
}
