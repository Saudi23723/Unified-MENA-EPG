package com.saudi.privatevault

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/** A screen that can write neon that stays on its own page (the book reader, the map). */
interface NeonHost {
    fun neonPen()
    /** Neon that fades, on the page itself; by default over the whole screen. */
    fun neonFade() = NeonLayer.start(this as Activity, fade = true)
}

/**
 * A small round button on every screen: a floating note, and neon on the
 * screen in two kinds, one that fades after four seconds and one that stays.
 * Drag it anywhere; it remembers where.
 */
object QuickTools {
    private const val TAG = "quick_tools"

    fun enabled(ctx: Context) = VaultLock.prefs(ctx).getBoolean(TAG, true)
    fun setEnabled(ctx: Context, on: Boolean) = VaultLock.prefs(ctx).edit().putBoolean(TAG, on).apply()

    @SuppressLint("ClickableViewAccessibility")
    fun attach(act: Activity) {
        val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
        content.findViewWithTag<View>(TAG)?.let { content.removeView(it) }
        if (!enabled(act)) return
        val d = act.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val prefs = VaultLock.prefs(act)
        // A solid blue disc with a thin white ring and a drawn pencil, as an EFB's.
        val b = android.widget.ImageView(act).apply {
            tag = TAG
            setImageResource(R.drawable.ic_fab_pencil)
            scaleType = android.widget.ImageView.ScaleType.CENTER_INSIDE
            setPadding(dp(13), dp(13), dp(13), dp(13))
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(0xFF2FA4FF.toInt(), 0xFF1178D6.toInt())).apply {
                shape = GradientDrawable.OVAL; setStroke(dp(2), 0xE6FFFFFF.toInt())
            }
            elevation = dp(10).toFloat()
        }
        content.addView(b, FrameLayout.LayoutParams(dp(56), dp(56), Gravity.END or Gravity.BOTTOM).apply { marginEnd = dp(14); bottomMargin = dp(150) })
        b.translationX = prefs.getFloat("qt_x", 0f)
        b.translationY = prefs.getFloat("qt_y", 0f)
        var sx = 0f; var sy = 0f; var tx = 0f; var ty = 0f; var moved = false
        b.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { sx = e.rawX; sy = e.rawY; tx = v.translationX; ty = v.translationY; moved = false }
                MotionEvent.ACTION_MOVE -> {
                    if (Math.hypot((e.rawX - sx).toDouble(), (e.rawY - sy).toDouble()) > dp(8)) moved = true
                    if (moved) {
                        val p = v.parent as View
                        v.translationX = (tx + e.rawX - sx).coerceIn(-(p.width - v.width - dp(20)).toFloat(), dp(10).toFloat())
                        v.translationY = (ty + e.rawY - sy).coerceIn(-(p.height - v.height - dp(170)).toFloat(), dp(140).toFloat())
                    }
                }
                MotionEvent.ACTION_UP -> {
                    if (moved) prefs.edit().putFloat("qt_x", v.translationX).putFloat("qt_y", v.translationY).apply()
                    else menu(act, v)
                }
            }
            true
        }
    }

    /** The button's panel: dark and rounded beside it, a row per tool, as an EFB's tool pop-up. */
    private fun menu(act: Activity, anchor: View) {
        val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
        content.findViewWithTag<View>("qt_panel")?.let { content.removeView(it); return }
        val d = act.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        // A see-through sheet over the screen: a tap outside closes the panel.
        val shade = FrameLayout(act).apply { tag = "qt_panel"; elevation = dp(28).toFloat(); isClickable = true }
        shade.setOnClickListener { content.removeView(shade) }
        val panel = LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable().apply { cornerRadius = dp(18).toFloat(); setColor(0xF2161618.toInt()); setStroke(dp(1), 0xFF2C2C2E.toInt()) }
            setPadding(dp(8), dp(8), dp(8), dp(8))
            elevation = dp(16).toFloat()
            isClickable = true
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        fun row(iconRes: Int?, glyph: String?, tint: Int, title: Int, sub: Int?, go: () -> Unit) {
            val r = LinearLayout(act).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(8), dp(8), dp(14), dp(8))
                background = android.graphics.drawable.RippleDrawable(android.content.res.ColorStateList.valueOf(0x22FFFFFF), null,
                    GradientDrawable().apply { cornerRadius = dp(12).toFloat(); setColor(0xFFFFFFFF.toInt()) })
                setOnClickListener { content.removeView(shade); go() }
            }
            val icon: View = if (iconRes != null) android.widget.ImageView(act).apply {
                setImageResource(iconRes); setColorFilter(0xFFFFFFFF.toInt()); setPadding(dp(9), dp(9), dp(9), dp(9))
            } else TextView(act).apply { text = glyph; textSize = 17f; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt()) }
            icon.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(tint) }
            r.addView(icon, LinearLayout.LayoutParams(dp(38), dp(38)))
            val texts = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, 0, 0) }
            texts.addView(TextView(act).apply { text = act.getString(title); textSize = 15f; setTextColor(0xFFFFFFFF.toInt()); typeface = EfbUi.MEDIUM })
            sub?.let { texts.addView(TextView(act).apply { text = act.getString(it); textSize = 12f; setTextColor(0xFF8E8E93.toInt()) }) }
            r.addView(texts)
            panel.addView(r, LinearLayout.LayoutParams(-1, -2))
        }
        row(R.drawable.ic_fab_pencil, null, 0xFF2E9BFF.toInt(), R.string.qt_note_t, R.string.qt_note_s) {
            if (NotePad.isOpen()) NotePad.close(act) else Notebooks.choose(act, null)
        }
        row(null, "◉", 0xFFFF2D2D.toInt(), R.string.qt_laser_t, R.string.qt_laser_s) { LaserLayer.start(act) }
        row(null, "✎", 0xFF30D158.toInt(), R.string.qt_neon_stay_t, R.string.qt_neon_stay_s) {
            if (act is NeonHost) act.neonPen() else NeonLayer.start(act, fade = false)
        }
        panel.addView(View(act).apply { setBackgroundColor(0xFF2C2C2E.toInt()) }, LinearLayout.LayoutParams(-1, 1).apply { setMargins(dp(10), dp(4), dp(10), dp(4)) })
        row(R.drawable.ic_close, null, 0xFF48484A.toInt(), R.string.qt_hide_t, null) {
            setEnabled(act, false)
            attach(act)
            Toast.makeText(act, R.string.qt_hidden, Toast.LENGTH_LONG).show()
        }
        // Above the button, at the screen's edge.
        val loc = IntArray(2); anchor.getLocationInWindow(loc)
        val cLoc = IntArray(2); content.getLocationInWindow(cLoc)
        val bottom = content.height - (loc[1] - cLoc[1]) + dp(8)
        shade.addView(panel, FrameLayout.LayoutParams(dp(290), -2, Gravity.END or Gravity.BOTTOM).apply { marginEnd = dp(14); bottomMargin = bottom.coerceAtLeast(dp(16)) })
        content.addView(shade, FrameLayout.LayoutParams(-1, -1))
        panel.alpha = 0f; panel.translationY = dp(12).toFloat()
        panel.animate().alpha(1f).translationY(0f).setDuration(160).start()
    }
}

/** Neon written over the whole screen: fading four seconds after it is drawn, or staying until cleared. */
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
class NeonLayer(ctx: Context, var fade: Boolean) : View(ctx) {
    private class Stroke(val color: Int, val pts: ArrayList<Float>, var ended: Long = 0L)

    var color = 0xFF39FF14.toInt()
    private val strokes = ArrayList<Stroke>()
    private var current: Stroke? = null
    private val d = ctx.resources.displayMetrics.density
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val path = Path()

    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> { current = Stroke(color, arrayListOf(e.x, e.y)).also { strokes.add(it) } }
            MotionEvent.ACTION_MOVE -> current?.let { s ->
                for (i in 0 until e.historySize) { s.pts.add(e.getHistoricalX(i)); s.pts.add(e.getHistoricalY(i)) }
                s.pts.add(e.x); s.pts.add(e.y)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { current?.ended = System.currentTimeMillis(); current = null }
        }
        invalidate()
        return true
    }

    fun clear() { strokes.clear(); current = null; invalidate() }

    override fun onDraw(c: Canvas) {
        val now = System.currentTimeMillis()
        var live = false
        val it = strokes.iterator()
        while (it.hasNext()) {
            val s = it.next()
            // Full for three seconds after the finger lifts, gone by four and a half.
            var a = 1f
            if (fade && s.ended > 0) {
                val age = now - s.ended
                if (age > 4500) { it.remove(); continue }
                if (age > 3000) a = 1f - (age - 3000) / 1500f
                live = true
            }
            if (s === current && fade) live = true
            path.reset()
            path.moveTo(s.pts[0], s.pts[1])
            var i = 2
            while (i + 1 < s.pts.size) {
                val mx = (s.pts[i - 2] + s.pts[i]) / 2; val my = (s.pts[i - 1] + s.pts[i + 1]) / 2
                path.quadTo(s.pts[i - 2], s.pts[i - 1], mx, my)
                i += 2
            }
            path.lineTo(s.pts[s.pts.size - 2], s.pts[s.pts.size - 1])
            // A wide soft glow, a brighter band, and a white-hot core.
            paint.color = s.color; paint.alpha = (60 * a).toInt(); paint.strokeWidth = 16 * d; c.drawPath(path, paint)
            paint.alpha = (140 * a).toInt(); paint.strokeWidth = 8 * d; c.drawPath(path, paint)
            paint.color = 0xFFFFFFFF.toInt(); paint.alpha = (230 * a).toInt(); paint.strokeWidth = 2.6f * d; c.drawPath(path, paint)
        }
        if (live) postInvalidateOnAnimation()
    }

    companion object {
        private const val TAG = "neon_layer"

        fun start(act: Activity, fade: Boolean) {
            val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
            content.findViewWithTag<View>(TAG)?.let { content.removeView(it) }
            val d = act.resources.displayMetrics.density
            fun dp(v: Int) = (v * d).toInt()
            val box = FrameLayout(act).apply { tag = TAG; elevation = dp(30).toFloat() }
            val layer = NeonLayer(act, fade)
            box.addView(layer, FrameLayout.LayoutParams(-1, -1))
            // The bar: which neon, its colour, clear, done.
            val bar = LinearLayout(act).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(8), dp(4), dp(8), dp(4))
                background = GradientDrawable().apply { setColor(0xE6101826.toInt()); cornerRadius = dp(22).toFloat() }
                layoutDirection = View.LAYOUT_DIRECTION_LTR
            }
            fun chip(t: String, onClick: (TextView) -> Unit) = TextView(act).apply {
                text = t; textSize = 14f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
                setPadding(dp(10), dp(8), dp(10), dp(8)); setOnClickListener { onClick(this) }
            }
            lateinit var kind: TextView
            fun label() { kind.text = if (layer.fade) "✨ 4s" else "🖍 ∞" }
            kind = chip("") { layer.fade = !layer.fade; label(); layer.invalidate() }
            label()
            bar.addView(kind)
            val dots = ArrayList<View>()
            for (cl in intArrayOf(0xFF39FF14.toInt(), 0xFFFF2BD6.toInt(), 0xFF00E5FF.toInt(), 0xFFFFEA00.toInt(), 0xFFFF5252.toInt())) {
                val dot = View(act).apply {
                    background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(cl); setStroke(dp(2), if (cl == layer.color) 0xFFFFFFFF.toInt() else 0x00000000) }
                    setOnClickListener {
                        layer.color = cl
                        dots.forEach { v -> (v.background as GradientDrawable).setStroke(dp(2), 0x00000000) }
                        (background as GradientDrawable).setStroke(dp(2), 0xFFFFFFFF.toInt())
                    }
                }
                dots.add(dot)
                bar.addView(dot, LinearLayout.LayoutParams(dp(24), dp(24)).apply { marginStart = dp(5); marginEnd = dp(5) })
            }
            bar.addView(chip("🗑") { layer.clear() })
            bar.addView(chip("✓") { (box.parent as? ViewGroup)?.removeView(box) })
            box.addView(bar, FrameLayout.LayoutParams(-2, -2, Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = dp(60) })
            content.addView(box, FrameLayout.LayoutParams(-1, -1))
        }
    }
}
