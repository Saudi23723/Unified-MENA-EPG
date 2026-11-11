package com.saudi1.tv

import android.content.Intent
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import coil.load
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** What Home turns into when nobody touches the remote: the playlist's newest and best rated movies and series,
 *  one at a time. OK opens the one on screen; any other key goes back to Home. */
class ShowcaseActivity : BaseActivity() {
    private var items: List<Triple<String, VodItem, Boolean>> = emptyList()
    private var i = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val d = resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val root = FrameLayout(this).apply {
            background = GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, intArrayOf(0xFF05070D.toInt(), 0xFF0B1020.toInt(), 0xFF151027.toInt()))
        }
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(90), dp(50), dp(90), dp(50)) }
        val poster = ImageView(this).apply { scaleType = ImageView.ScaleType.CENTER_CROP; clipToOutline = true
            background = GradientDrawable().apply { cornerRadius = dp(18).toFloat(); setColor(0xFF111827.toInt()) } }
        val ph = resources.displayMetrics.heightPixels - dp(120)
        row.addView(poster, LinearLayout.LayoutParams(ph * 2 / 3, ph))
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(56), 0, 0, 0) }
        val label = TextView(this).apply { textSize = 17f; letterSpacing = 0.18f; setTextColor(0xFF10B981.toInt()); setTypeface(typeface, Typeface.BOLD) }
        val title = TextView(this).apply { textSize = 44f; setTextColor(0xFFFFFFFF.toInt()); setTypeface(typeface, Typeface.BOLD); maxLines = 3 }
        val meta = TextView(this).apply { textSize = 22f; setTextColor(0xFFFFC83D.toInt()) }
        val hint = TextView(this).apply { textSize = 16f; setTextColor(0x99FFFFFF.toInt()); text = "OK  ·  open        ◀ ▶  ·  previous / next        any other key  ·  Home" }
        val brand = TextView(this).apply { text = "SAUDI.TV"; textSize = 15f; letterSpacing = 0.3f; setTextColor(0x80FFFFFF.toInt()); setTypeface(typeface, Typeface.BOLD) }
        col.addView(brand); col.addView(label, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(26) })
        col.addView(title, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        col.addView(meta, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(14) })
        col.addView(hint, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(40) })
        row.addView(col, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        root.addView(row)
        setContentView(root)
        show = {
            val (l, it, _) = items[i]
            label.text = l.uppercase()
            // provider prefixes ("AR-SUBS - ", "EN - ") are not part of the title
            title.text = Vod.shown(it.name).replace(Regex("\\s*[\\(\\[](19|20)\\d{2}[\\)\\]]\\s*$"), "")
            meta.text = listOfNotNull(it.rating.toDoubleOrNull()?.let { r -> "★ " + "%.1f".format(r) }, it.year.takeIf { y -> y.length == 4 }).joinToString("     ")
            row.animate().cancel(); row.alpha = 0f
            poster.load(it.poster) { size(600, 900); error(R.drawable.banner) }
            row.animate().alpha(1f).setDuration(500).start()
        }
        lifecycleScope.launch {
            val l = withContext(Dispatchers.IO) {
                val m = try { Vod.showcase(false) } catch (e: Exception) { emptyList() }
                val s = try { Vod.showcase(true) } catch (e: Exception) { emptyList() }
                // movies and series take turns
                val out = ArrayList<Triple<String, VodItem, Boolean>>()
                for (k in 0 until maxOf(m.size, s.size)) { m.getOrNull(k)?.let { out.add(Triple(it.first, it.second, false)) }; s.getOrNull(k)?.let { out.add(Triple(it.first, it.second, true)) } }
                // a different order every time: there is always something else to pick
                out.shuffle(); out
            }
            if (l.isEmpty()) { finish(); return@launch }
            items = l; i = 0; show()
            while (isActive) { delay(9000); if (!paused) { i = (i + 1) % items.size; show() } }
        }
    }

    private var show: () -> Unit = {}
    private var paused = false
    override fun onPause() { super.onPause(); paused = true }
    override fun onResume() { super.onResume(); paused = false }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (overlayOpen) return super.dispatchKeyEvent(e)
        if (e.action != KeyEvent.ACTION_DOWN) return true
        when (e.keyCode) {
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> items.getOrNull(i)?.let { (_, it, series) ->
                startActivity(Intent(this, VodDetailActivity::class.java).putExtra("series", series).putExtra("id", it.id)
                    .putExtra("name", it.name).putExtra("poster", it.poster).putExtra("ext", it.ext))
                finish()
            }
            KeyEvent.KEYCODE_DPAD_RIGHT -> if (items.isNotEmpty()) { i = (i + 1) % items.size; show() }
            KeyEvent.KEYCODE_DPAD_LEFT -> if (items.isNotEmpty()) { i = (i - 1 + items.size) % items.size; show() }
            else -> finish()
        }
        return true
    }
}
