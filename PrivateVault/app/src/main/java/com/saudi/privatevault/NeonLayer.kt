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
 * Neon over anything on the screen, written with a finger or a pen and gone by itself.
 *
 * It glows the way a neon sign does — a wide soft halo, a strong coloured tube and a white-hot
 * core — stays while it is being written and for a moment after, then fades and leaves the page
 * exactly as it was. Nothing is saved and nothing has to be rubbed out.
 */
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
class NeonLayer(ctx: Context) : View(ctx) {
    var color = 0xFFFF2D9B.toInt()
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
        // The stroke, in three passes, as a neon sign is built: halo, tube, white-hot core.
        // Each is drawn fainter the older that part of the stroke is, so the writing fades from
        // its own beginning rather than all at once.
        for (i in 1 until trail.size) {
            val a = trail[i - 1]; val b = trail[i]
            val f = 1f - (now - b.t).toFloat() / TAIL_MS
            if (f <= 0f) continue
            line.strokeWidth = 22 * d * f
            line.color = (color and 0x00FFFFFF) or ((0x4A * f).toInt() shl 24)
            c.drawLine(a.x, a.y, b.x, b.y, line)
            line.strokeWidth = 9 * d * f
            line.color = (color and 0x00FFFFFF) or ((0xE6 * f).toInt() shl 24)
            c.drawLine(a.x, a.y, b.x, b.y, line)
            line.strokeWidth = 3f * d * f
            line.color = 0x00FFFFFF or ((0xF0 * f).toInt() shl 24)
            c.drawLine(a.x, a.y, b.x, b.y, line)
        }
        // The tip, while the finger is down, so it is plain where the writing is going.
        if (down) {
            val r = 16 * d
            glow.shader = RadialGradient(lastX, lastY, r, intArrayOf(color, color and 0x00FFFFFF), floatArrayOf(0.2f, 1f), Shader.TileMode.CLAMP)
            glow.alpha = 255
            c.drawCircle(lastX, lastY, r, glow)
            core.alpha = 230
            c.drawCircle(lastX, lastY, 3f * d, core)
        }
        if (down || trail.isNotEmpty()) postInvalidateOnAnimation()
    }

    companion object {
        private const val TAG = "neon_layer"
        /** How long a stroke stays before it has faded away completely. */
        private const val TAIL_MS = 2600L

        /** Over the whole screen, with a small bar: the colour, and ✓ to put it away. */
        fun start(act: Activity) {
            val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
            content.findViewWithTag<View>(TAG)?.let { content.removeView(it); return }
            val dd = act.resources.displayMetrics.density
            fun dp(v: Int) = (v * dd).toInt()
            val box = FrameLayout(act).apply { tag = TAG; elevation = dp(30).toFloat() }
            val neon = NeonLayer(act)
            box.addView(neon, FrameLayout.LayoutParams(-1, -1))
            val bar = LinearLayout(act).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(12), dp(4), dp(6), dp(4)); layoutDirection = View.LAYOUT_DIRECTION_LTR
                background = GradientDrawable().apply { setColor(0xE6101214.toInt()); cornerRadius = dp(22).toFloat() }
            }
            bar.addView(TextView(act).apply { text = act.getString(R.string.neon_fade); textSize = 14f; setTextColor(0xFFFFFFFF.toInt()); typeface = EfbUi.MEDIUM; setPadding(0, 0, dp(8), 0) })
            val dots = ArrayList<View>()
            for (cl in intArrayOf(0xFFFF2D9B.toInt(), 0xFF39FF14.toInt(), 0xFF2E9BFF.toInt(), 0xFFFFD60A.toInt())) {
                val dot = View(act).apply {
                    background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(cl); setStroke(dp(2), if (cl == neon.color) 0xFFFFFFFF.toInt() else 0) }
                    setOnClickListener {
                        neon.color = cl
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
