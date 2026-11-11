package com.saudi1.tv

import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.app.Activity
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.animation.DecelerateInterpolator
import android.view.animation.PathInterpolator
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/** The welcome every time the app opens (owner, 11 Nov 2026: "welcome him in a beautiful, professional way, every time").
 *  In the spirit of Apple TV / Netflix / Disney+: a dark stage with a slow breathing glow, the wordmark settling in,
 *  then the viewer's own name, the time of day and what was on last. About three seconds; any button goes straight in.
 *  The name is the one the owner gives the device on the admin site ("Laith Chromecast" → Laith). */
object Welcome {
    private val ease = PathInterpolator(0.2f, 0f, 0f, 1f)

    fun show(a: Activity, onDone: () -> Unit) {
        val root = a.window.decorView as? ViewGroup ?: run { onDone(); return }
        val d = a.resources.displayMetrics.density
        fun dp(v: Float) = (v * d).toInt()
        val w = a.resources.displayMetrics.widthPixels.toFloat()

        val stage = FrameLayout(a).apply {
            setBackgroundColor(0xFF04060B.toInt()); isFocusable = true; isFocusableInTouchMode = true; isClickable = true
        }
        // two soft glows, green and blue, breathing slowly behind the words
        fun glow(c: Int, size: Float, gx: Int, gy: Int) = View(a).apply {
            background = GradientDrawable().apply {
                gradientType = GradientDrawable.RADIAL_GRADIENT; gradientRadius = size / 2
                colors = intArrayOf(c, c and 0x00FFFFFF)
            }
            alpha = 0f
            stage.addView(this, FrameLayout.LayoutParams(size.toInt(), size.toInt(), Gravity.NO_GRAVITY).apply { leftMargin = gx; topMargin = gy })
        }
        val g1 = glow(0x6610B981, w * 0.75f, (-w * 0.12f).toInt(), (-w * 0.18f).toInt())
        val g2 = glow(0x553B82F6, w * 0.65f, (w * 0.45f).toInt(), (w * 0.05f).toInt())

        val col = LinearLayout(a).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL }
        stage.addView(col, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER))

        val logo = TextView(a).apply {
            text = SpannableString("SAUDI.TV").apply { setSpan(ForegroundColorSpan(0xFF10B981.toInt()), 5, 8, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE) }
            textSize = 30f; setTextColor(0xFFFFFFFF.toInt()); typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
            letterSpacing = 0.6f; alpha = 0f; gravity = Gravity.CENTER
        }
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        val part = when (hour) { in 5..11 -> "GOOD MORNING"; in 12..16 -> "GOOD AFTERNOON"; in 17..21 -> "GOOD EVENING"; else -> "GOOD NIGHT" }
        val tag = TextView(a).apply {
            text = part; textSize = 15f; letterSpacing = 0.45f; setTextColor(0x99FFFFFF.toInt()); alpha = 0f; gravity = Gravity.CENTER
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        }
        val who = Device.name.trim().substringBefore(' ').takeIf { it.length in 2..20 && !it.all { c -> c.isDigit() } }
        val first = !App.prefs.getBoolean("welcomed", false)
        val head = if (who == null) (if (first) "Welcome" else "Welcome back") else (if (first) "Welcome, " else "Welcome back, ") + who
        val name = TextView(a).apply {
            text = SpannableString(head).apply { if (who != null) setSpan(ForegroundColorSpan(0xFF34D399.toInt()), head.length - who.length, head.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE) }
            textSize = 56f; setTextColor(0xFFFFFFFF.toInt()); typeface = Typeface.create("sans-serif-light", Typeface.NORMAL)
            alpha = 0f; translationY = dp(28f).toFloat(); gravity = Gravity.CENTER
        }
        val now = Date()
        val last = Api.byId[Prefs.lastChannel]?.takeIf { it.id > 0 && it.group != Api.DASH }?.name
        val info = TextView(a).apply {
            text = SimpleDateFormat("EEEE d MMMM  ·  h:mm a", Locale.ENGLISH).format(now) + (if (last != null) "\nPick up where you left off  ·  $last" else "")
            textSize = 17f; setTextColor(0xB3FFFFFF.toInt()); alpha = 0f; gravity = Gravity.CENTER; setLineSpacing(dp(6f).toFloat(), 1f)
        }
        col.addView(logo)
        col.addView(tag, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(46f) })
        col.addView(name, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(10f) })
        col.addView(info, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(22f) })

        // a fine line along the bottom fills while the welcome is on
        val bar = View(a).apply { setBackgroundColor(0xFF10B981.toInt()); pivotX = 0f; scaleX = 0f; alpha = 0.9f }
        stage.addView(bar, FrameLayout.LayoutParams(-1, dp(3f), Gravity.BOTTOM))
        val hint = TextView(a).apply { text = "Press any button to start"; textSize = 13f; letterSpacing = 0.1f; setTextColor(0x55FFFFFF); alpha = 0f }
        stage.addView(hint, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply { bottomMargin = dp(26f) })

        root.addView(stage, ViewGroup.LayoutParams(-1, -1))
        stage.requestFocus()

        var gone = false
        val anims = ArrayList<android.animation.Animator>()
        fun finish() {
            if (gone) return; gone = true
            anims.forEach { it.cancel() }
            App.prefs.edit().putBoolean("welcomed", true).apply()
            stage.animate().alpha(0f).scaleX(1.04f).scaleY(1.04f).setDuration(450).setInterpolator(ease)
                .withEndAction { root.removeView(stage) }.start()
            onDone()
        }
        stage.setOnKeyListener { _, k, e -> if (e.action == KeyEvent.ACTION_UP && k != KeyEvent.KEYCODE_UNKNOWN) finish(); true }
        stage.setOnClickListener { finish() }

        // the timeline
        g1.animate().alpha(1f).setDuration(1400).setInterpolator(DecelerateInterpolator()).start()
        g2.animate().alpha(1f).setDuration(1400).setStartDelay(250).setInterpolator(DecelerateInterpolator()).start()
        listOf(g1, g2).forEachIndexed { i, g ->
            anims += ObjectAnimator.ofFloat(g, View.SCALE_X, 1f, 1.12f).apply { duration = 3400L + i * 600; repeatMode = ValueAnimator.REVERSE; repeatCount = ValueAnimator.INFINITE; start() }
            anims += ObjectAnimator.ofFloat(g, View.SCALE_Y, 1f, 1.12f).apply { duration = 3400L + i * 600; repeatMode = ValueAnimator.REVERSE; repeatCount = ValueAnimator.INFINITE; start() }
        }
        logo.animate().alpha(1f).setDuration(900).setInterpolator(ease).start()
        anims += ObjectAnimator.ofFloat(logo, "letterSpacing", 0.6f, 0.12f).apply { duration = 1300; interpolator = ease; start() }
        tag.animate().alpha(1f).setStartDelay(650).setDuration(700).setInterpolator(ease).start()
        name.animate().alpha(1f).translationY(0f).setStartDelay(850).setDuration(900).setInterpolator(ease).start()
        info.animate().alpha(1f).setStartDelay(1300).setDuration(800).setInterpolator(ease).start()
        hint.animate().alpha(1f).setStartDelay(1600).setDuration(600).start()
        anims += ObjectAnimator.ofFloat(bar, View.SCALE_X, 0f, 1f).apply { duration = 3300; interpolator = android.view.animation.LinearInterpolator(); start() }
        stage.postDelayed({ finish() }, 3400)
    }
}
