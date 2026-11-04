package com.saudi.privatevault

import android.content.Intent
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Pilot Companion on a television (Chromecast with Google TV, Android TV): a home of
 * large tiles moved between with the remote's arrows. The cloud and the laptop's
 * vault (videos stream, books open in the reader), the files on the TV itself, the
 * library, and the settings.
 */
class TvActivity : BaseActivity() {
    override val quickTools = false
    override val alwaysDark = true

    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this).apply {
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(0xFF07101F.toInt(), 0xFF0B1A33.toInt(), 0xFF15315A.toInt()))
        }
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(56), dp(40), dp(56), dp(32)) }
        root.addView(col, FrameLayout.LayoutParams(-1, -1))
        col.addView(TextView(this).apply {
            text = android.text.SpannableString("PILOT COMPANION").apply { setSpan(android.text.style.ForegroundColorSpan(0xFF8CC8FF.toInt()), 6, 15, 0) }
            textSize = 30f; letterSpacing = 0.12f; setTextColor(0xFFFFFFFF.toInt()); typeface = EfbUi.MEDIUM
        })
        col.addView(TextView(this).apply {
            text = getString(R.string.tv_sub); textSize = 16f; setTextColor(0xB3FFFFFF.toInt()); setPadding(0, dp(6), 0, dp(28))
        })
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        col.addView(row)
        val tiles = listOf(
            Tile(R.drawable.ic_laptop, R.string.tv_cloud, R.string.tv_cloud_sub, intArrayOf(0xFF4DB2FF.toInt(), 0xFF0A72E0.toInt())) { startActivity(Intent(this, LaptopActivity::class.java)) },
            Tile(R.drawable.ic_video, R.string.tv_device, R.string.tv_device_sub, intArrayOf(0xFFFF8A65.toInt(), 0xFFD84315.toInt())) { startActivity(Intent(this, MainActivity::class.java)) },
            Tile(R.drawable.ic_contents, R.string.tv_library, R.string.tv_library_sub, intArrayOf(0xFFA98BFF.toInt(), 0xFF6C47E0.toInt())) { startActivity(Intent(this, LibraryActivity::class.java)) },
            Tile(R.drawable.ic_more, R.string.set_title, R.string.tv_settings_sub, intArrayOf(0xFF8E9AAB.toInt(), 0xFF4A5566.toInt())) { startActivity(Intent(this, SettingsActivity::class.java)) },
        )
        var first: View? = null
        for ((i, t) in tiles.withIndex()) {
            val v = tile(t)
            row.addView(v, LinearLayout.LayoutParams(0, dp(230), 1f).apply { marginEnd = if (i < tiles.size - 1) dp(22) else 0 })
            if (first == null) first = v
        }
        col.addView(TextView(this).apply {
            text = getString(R.string.tv_hint); textSize = 14f; setTextColor(0x80FFFFFF.toInt()); setPadding(0, dp(30), 0, 0)
        })
        setContentView(root)
        first?.requestFocus()
    }

    private class Tile(val icon: Int, val title: Int, val sub: Int, val grad: IntArray, val go: () -> Unit)

    /** A tile that lifts and lights its edge when the remote's focus is on it. */
    private fun tile(t: Tile): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        isFocusable = true
        isClickable = true
        setPadding(dp(18), dp(18), dp(18), dp(18))
        val idle = GradientDrawable().apply { cornerRadius = dp(22).toFloat(); setColor(0xCC141A24.toInt()); setStroke(dp(2), 0x33FFFFFF) }
        val lit = GradientDrawable().apply { cornerRadius = dp(22).toFloat(); setColor(0xFF1C2433.toInt()); setStroke(dp(4), 0xFF8CC8FF.toInt()) }
        background = idle
        addView(android.widget.ImageView(context).apply {
            setImageResource(t.icon); setColorFilter(0xFFFFFFFF.toInt()); setPadding(dp(20), dp(20), dp(20), dp(20))
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, t.grad).apply { shape = GradientDrawable.OVAL }
        }, LinearLayout.LayoutParams(dp(84), dp(84)))
        addView(TextView(context).apply {
            text = getString(t.title).replace(Regex("^[^\\p{L}]+"), ""); textSize = 22f; setTextColor(0xFFFFFFFF.toInt())
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL); gravity = Gravity.CENTER; setPadding(0, dp(16), 0, dp(4))
        })
        addView(TextView(context).apply { text = getString(t.sub); textSize = 14f; setTextColor(0xB3FFFFFF.toInt()); gravity = Gravity.CENTER })
        setOnFocusChangeListener { v, has ->
            v.background = if (has) lit else idle
            v.animate().scaleX(if (has) 1.06f else 1f).scaleY(if (has) 1.06f else 1f).translationZ(if (has) dp(12).toFloat() else 0f).setDuration(150).start()
        }
        setOnClickListener { t.go() }
    }
}
