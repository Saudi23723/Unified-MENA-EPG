package com.saudi1.tv

import android.app.Activity
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.LayerDrawable
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** The player's menus in TiviMate's style (owner, 17 Nov 2026: "like TiviMate, modern and professional"):
 *  a bar of icons along the bottom of the picture, and the choices in a panel on the right with round radio marks,
 *  the focused row white. Only views: nothing here touches the player. */
object TvUi {
    class Tile(val icon: String, val label: String, val value: String, val action: () -> Unit)

    // more sizes for different screens (owner, 25 Nov 2026), added at the end so saved choices keep their meaning
    val MODES = arrayOf("Normal", "Full", "Zoom", "Zoom · 2.35:1", "Reduced", "4:3", "16:9", "2.35:1",
        "Zoom 110%", "Zoom 125%", "18:9 · phones", "20:9 · phones", "21:9 · wide", "5:4", "Reduced · 75%")

    /** TiviMate's display modes on a PlayerView: the resize mode, then a scale of the picture's frame */
    fun applyMode(pv: androidx.media3.ui.PlayerView, vs: androidx.media3.common.VideoSize, m: Int) {
        val frame = pv.findViewById<View>(androidx.media3.ui.R.id.exo_content_frame) ?: return
        frame.scaleX = 1f; frame.scaleY = 1f
        pv.resizeMode = when (m) { 1 -> androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FILL; 2 -> androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM
            else -> androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FIT }
        val v = if (vs.width > 0 && vs.height > 0) vs.width * vs.pixelWidthHeightRatio / vs.height else 16f / 9f
        val sc = if (pv.width > 0 && pv.height > 0) pv.width.toFloat() / pv.height else 16f / 9f
        fun fit(a: Float) = if (a >= sc) 1f to sc / a else a / sc to 1f
        when (m) {
            3 -> { val z = (2.35f / v).coerceAtLeast(1f); frame.scaleX = z; frame.scaleY = z }
            4 -> { frame.scaleX = 0.85f; frame.scaleY = 0.85f }
            14 -> { frame.scaleX = 0.75f; frame.scaleY = 0.75f }
            8 -> { frame.scaleX = 1.10f; frame.scaleY = 1.10f }
            9 -> { frame.scaleX = 1.25f; frame.scaleY = 1.25f }
            5, 6, 7, 10, 11, 12, 13 -> {
                val a = when (m) { 5 -> 4f / 3f; 6 -> 16f / 9f; 10 -> 18f / 9f; 11 -> 20f / 9f; 12 -> 21f / 9f; 13 -> 5f / 4f; else -> 2.35f }
                val (wv, hv) = fit(v); val (wa, ha) = fit(a)
                frame.scaleX = wa / wv; frame.scaleY = ha / hv
            }
        }
    }

    /** the open menus of a screen, top last: Back closes the top one */
    class Stack(private val a: BaseActivity) {
        private val list = ArrayList<View>()
        val open get() = list.isNotEmpty()
        val top get() = list.lastOrNull()
        fun push(v: View) {
            (a.window.decorView as ViewGroup).addView(v, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            list.add(v); a.applyDim()
        }
        fun pop() {
            val v = list.removeLastOrNull() ?: return
            (a.window.decorView as ViewGroup).removeView(v)
            list.lastOrNull()?.let { it.post { it.findFocus() ?: it.requestFocus(View.FOCUS_DOWN) } }
        }
        fun close() { while (list.isNotEmpty()) pop() }
    }

    private fun dp(a: Activity, v: Float) = (v * a.resources.displayMetrics.density).toInt()
    private fun round(c: Int, r: Float) = GradientDrawable().apply { setColor(c); cornerRadius = r }

    /** the bottom bar: the title, then the tiles; ◀ ▶ move, OK opens */
    fun bar(a: Activity, title: String, tiles: List<Tile>, start: Int = 0): View {
        val root = FrameLayout(a).apply { isClickable = true }
        val box = LinearLayout(a).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(0x00000000, 0xCC000000.toInt(), 0xF2000000.toInt()))
            setPadding(dp(a, 32f), dp(a, 70f), dp(a, 32f), dp(a, 36f))
        }
        box.addView(TextView(a).apply {
            text = title; textSize = 20f; setTextColor(0xFFFFFFFF.toInt()); typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END
        })
        val row = LinearLayout(a).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_HORIZONTAL }
        val views = ArrayList<View>()
        tiles.forEach { t ->
            val v = LinearLayout(a).apply {
                orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL
                isFocusable = true; isClickable = true; setPadding(dp(a, 4f), dp(a, 12f), dp(a, 4f), dp(a, 12f))
            }
            val ic = TextView(a).apply {
                text = t.icon; textSize = 26f; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt())
                typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0x26FFFFFF) }
            }
            v.addView(ic, LinearLayout.LayoutParams(dp(a, 58f), dp(a, 58f)))
            val lb = TextView(a).apply { text = t.label; textSize = 13f; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt()); maxLines = 1 }
            v.addView(lb, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(a, 8f) })
            val vl = TextView(a).apply { text = t.value; textSize = 12f; gravity = Gravity.CENTER; setTextColor(0x99FFFFFF.toInt()); maxLines = 1 }
            if (t.value.isNotEmpty()) v.addView(vl)
            v.setOnFocusChangeListener { _, f ->
                (ic.background as GradientDrawable).setColor(if (f) 0xFFFFFFFF.toInt() else 0x26FFFFFF)
                ic.setTextColor(if (f) 0xFF111111.toInt() else 0xFFFFFFFF.toInt())
                vl.setTextColor(if (f) 0xFFFFFFFF.toInt() else 0x99FFFFFF.toInt())
                v.animate().scaleX(if (f) 1.08f else 1f).scaleY(if (f) 1.08f else 1f).setDuration(120).start()
            }
            v.setOnClickListener { t.action() }
            val avail = a.resources.displayMetrics.widthPixels - dp(a, 64f)
            row.addView(v, LinearLayout.LayoutParams(minOf(dp(a, 132f), avail / tiles.size.coerceAtLeast(1)), -2))
            views += v
        }
        box.addView(row, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(a, 18f) })
        root.addView(box, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
        root.alpha = 0f; root.animate().alpha(1f).setDuration(160).start()
        root.post { views.getOrNull(start.coerceIn(0, (views.size - 1).coerceAtLeast(0)))?.requestFocus() }
        return root
    }

    private fun radio(a: Activity, on: Boolean, focused: Boolean): android.graphics.drawable.Drawable {
        val ring = GradientDrawable().apply {
            shape = GradientDrawable.OVAL; setColor(0)
            setStroke(dp(a, 2f), when { on -> 0xFF10B981.toInt(); focused -> 0xFF333333.toInt(); else -> 0xB3FFFFFF.toInt() })
        }
        if (!on) return ring
        val dot = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0xFF10B981.toInt()) }
        return LayerDrawable(arrayOf(ring, dot)).apply { val i = dp(a, 5f); setLayerInset(1, i, i, i, i) }
    }

    /** the panel on the right: a title, the choices with radio marks, and an optional on/off row at the bottom */
    fun side(a: Activity, title: String, items: List<String>, checked: Int, onPick: (Int) -> Unit,
             toggle: String? = null, toggleOn: Boolean = false, onToggle: (() -> Unit)? = null, lines: List<String> = emptyList()): View {
        val root = FrameLayout(a).apply { isClickable = true; setBackgroundColor(0x33000000) }
        val card = LinearLayout(a).apply {
            orientation = LinearLayout.VERTICAL
            background = round(0xF0222327.toInt(), dp(a, 22f).toFloat())
            setPadding(dp(a, 14f), dp(a, 26f), dp(a, 14f), dp(a, 18f))
        }
        card.addView(TextView(a).apply {
            text = title; textSize = 22f; setTextColor(0xFFFFFFFF.toInt()); typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
            setPadding(dp(a, 16f), 0, dp(a, 16f), dp(a, 14f)); maxLines = 2
        })
        lines.forEach { l ->
            card.addView(TextView(a).apply { text = l; textSize = 16f; setTextColor(0xCCFFFFFF.toInt()); setPadding(dp(a, 16f), dp(a, 4f), dp(a, 16f), dp(a, 4f)) })
        }
        val list = LinearLayout(a).apply { orientation = LinearLayout.VERTICAL }
        var first: View? = null
        fun row(text: String, on: Boolean, isToggle: Boolean, click: () -> Unit): View {
            val r = LinearLayout(a).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                isFocusable = true; isClickable = true; setPadding(dp(a, 16f), dp(a, 13f), dp(a, 16f), dp(a, 13f))
            }
            val mark = View(a)
            val tv = TextView(a).apply { this.text = text; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()); maxLines = 2 }
            if (isToggle) {
                tv.text = (if (on) "✓  " else "   ") + text
                r.addView(tv, LinearLayout.LayoutParams(0, -2, 1f))
            } else {
                mark.background = radio(a, on, false)
                r.addView(mark, LinearLayout.LayoutParams(dp(a, 22f), dp(a, 22f)))
                r.addView(tv, LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = dp(a, 18f) })
            }
            r.setOnFocusChangeListener { _, f ->
                r.background = if (f) round(0xFFFFFFFF.toInt(), dp(a, 12f).toFloat()) else null
                tv.setTextColor(if (f) 0xFF111111.toInt() else 0xFFFFFFFF.toInt())
                if (!isToggle) mark.background = radio(a, on, f)
            }
            r.setOnClickListener { click() }
            return r
        }
        items.forEachIndexed { i, s ->
            val r = row(s, i == checked, false) { onPick(i) }
            list.addView(r, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(a, 2f) })
            if (i == checked || first == null) first = r
        }
        if (toggle != null && onToggle != null) {
            list.addView(View(a).apply { setBackgroundColor(0x22FFFFFF) }, LinearLayout.LayoutParams(-1, dp(a, 1f)).apply { setMargins(dp(a, 16f), dp(a, 8f), dp(a, 16f), dp(a, 8f)) })
            val t = row(toggle, toggleOn, true) { onToggle() }
            list.addView(t, LinearLayout.LayoutParams(-1, -2))
            if (first == null) first = t
        }
        card.addView(ScrollView(a).apply { isVerticalScrollBarEnabled = false; addView(list) }, LinearLayout.LayoutParams(-1, -2))
        val w = (a.resources.displayMetrics.widthPixels * 0.32f).toInt().coerceAtLeast(dp(a, 360f))
        root.addView(card, FrameLayout.LayoutParams(w, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.END or Gravity.CENTER_VERTICAL).apply {
            setMargins(0, dp(a, 28f), dp(a, 28f), dp(a, 28f))
        })
        card.translationX = dp(a, 60f).toFloat(); card.alpha = 0f
        card.animate().translationX(0f).alpha(1f).setDuration(180).start()
        root.post { first?.requestFocus() }
        return root
    }
}
