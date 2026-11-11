package com.saudi.privatevault

import android.app.Activity
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.Gravity
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

/** The welcome as the app starts: the name over a dusk sky, then the app. Once per launch. */
object Splash {
    private var shown = false

    fun show(act: Activity) {
        if (shown) return
        shown = true
        val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
        val d = act.resources.displayMetrics.density
        val sky = FrameLayout(act).apply {
            background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(0xFF0B1A33.toInt(), 0xFF13284D.toInt(), 0xFF1F3F6E.toInt(), 0xFF2E4F7E.toInt()))
            isClickable = true
            elevation = 60 * d
        }
        val col = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER }
        val name = SpannableString("PILOT COMPANION").apply {
            setSpan(ForegroundColorSpan(0xFF4DA3FF.toInt()), 6, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        col.addView(TextView(act).apply {
            text = "✈"; textSize = 46f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
        })
        col.addView(TextView(act).apply {
            text = name; textSize = 32f; letterSpacing = 0.06f; gravity = Gravity.CENTER
            setTextColor(0xFFFFFFFF.toInt()); typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            setPadding(0, (8 * d).toInt(), 0, 0)
        })
        col.addView(TextView(act).apply {
            text = "Plan.  Fly.  Learn.  Log."; textSize = 18f; gravity = Gravity.CENTER
            setTextColor(0xFFE8EEF7.toInt()); setTypeface(typeface, Typeface.BOLD)
            setPadding(0, (6 * d).toInt(), 0, 0)
        })
        col.addView(TextView(act).apply {
            text = "Welcome"; textSize = 26f; gravity = Gravity.CENTER
            setTextColor(0xFFFFFFFF.toInt()); setTypeface(typeface, Typeface.BOLD)
            setPadding(0, (22 * d).toInt(), 0, 0)
        })
        sky.addView(col, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER))
        content.addView(sky, FrameLayout.LayoutParams(-1, -1))
        col.alpha = 0f; col.translationY = 24 * d
        col.animate().alpha(1f).translationY(0f).setDuration(450).start()
        sky.postDelayed({
            sky.animate().alpha(0f).setDuration(380).withEndAction { if (sky.parent === content && sky.isAttachedToWindow) content.removeView(sky) }.start()
        }, 1400)
    }
}
