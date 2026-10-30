package com.saudi.privatevault

import android.app.Activity
import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import com.google.android.material.appbar.MaterialToolbar

/** The look of the flight bag: a dark cockpit palette, cards, and gentle motion. */
object EfbUi {
    // A modern EFB's palette, night (the default, kind to the eyes in the cockpit) or day.
    @JvmStatic var light = false
    val BG get() = if (light) 0xFFF4F6F9.toInt() else 0xFF0F1318.toInt()
    val CARD get() = if (light) 0xFFFFFFFF.toInt() else 0xFF1A2029.toInt()
    val CARD_LINE get() = if (light) 0xFFE2E6EC.toInt() else 0xFF29313D.toInt()
    val ACCENT get() = if (light) 0xFF1A6FE0.toInt() else 0xFF4DA3FF.toInt()
    val TEXT get() = if (light) 0xFF111827.toInt() else 0xFFF1F4F8.toInt()
    val DIM get() = if (light) 0xFF5B6573.toInt() else 0xFF8D97A8.toInt()
    val GOOD get() = if (light) 0xFF1E9E4A.toInt() else 0xFF34C759.toInt()
    val WARN get() = if (light) 0xFFB86E00.toInt() else 0xFFFFB020.toInt()
    val BAD get() = if (light) 0xFFD93025.toInt() else 0xFFFF453A.toInt()

    /** A colour chosen for night or day. */
    fun pick(night: Int, day: Int) = if (light) day else night

    /** Follows the look in force (set from the app's Dark / Light / Auto choice). */
    fun sync(ctx: Context) {
        light = (ctx.resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK) !=
            android.content.res.Configuration.UI_MODE_NIGHT_YES
    }

    /** Dark, light, or as the phone: applied to every screen. */
    fun applyTheme(ctx: Context) {
        androidx.appcompat.app.AppCompatDelegate.setDefaultNightMode(when (VaultLock.prefs(ctx).getString("theme_mode", "dark")) {
            "light" -> androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_NO
            "auto" -> androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
            else -> androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_YES
        })
    }

    fun chooseTheme(act: Activity) {
        val modes = arrayOf("dark", "light", "auto")
        val now = modes.indexOf(VaultLock.prefs(act).getString("theme_mode", "dark")).coerceAtLeast(0)
        com.google.android.material.dialog.MaterialAlertDialogBuilder(act)
            .setTitle(R.string.theme_title)
            .setSingleChoiceItems(arrayOf(act.getString(R.string.theme_dark), act.getString(R.string.theme_light), act.getString(R.string.theme_auto)), now) { d, i ->
                d.dismiss()
                VaultLock.prefs(act).edit().putString("theme_mode", modes[i]).apply()
                applyTheme(act)
            }
            .show()
    }

    fun dp(ctx: Context, v: Int) = (v * ctx.resources.displayMetrics.density).toInt()

    /** A dark screen with a toolbar and a scrolling column; returns the column. */
    fun screen(act: Activity, title: String, menu: ((MaterialToolbar) -> Unit)? = null): LinearLayout {
        sync(act)
        androidx.core.view.WindowCompat.getInsetsController(act.window, act.window.decorView).apply {
            isAppearanceLightStatusBars = light
            isAppearanceLightNavigationBars = light
        }
        act.window.statusBarColor = BG
        act.window.navigationBarColor = BG
        val root = LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(BG)
        }
        val bar = MaterialToolbar(act).apply {
            this.title = title
            setTitleTextColor(TEXT)
            setBackgroundColor(BG)
            setNavigationIcon(R.drawable.ic_back)
            navigationIcon?.setTint(TEXT)
            setNavigationOnClickListener { act.finish() }
            overflowIcon?.setTint(TEXT)
        }
        menu?.invoke(bar)
        root.addView(bar)
        val col = LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(act, 14), dp(act, 6), dp(act, 14), dp(act, 32))
        }
        root.addView(ScrollView(act).apply {
            isFillViewport = true
            addView(col)
        }, LinearLayout.LayoutParams(-1, 0, 1f))
        act.setContentView(root)
        // Below the status bar and above the gesture bar.
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars() or androidx.core.view.WindowInsetsCompat.Type.ime())
            v.setPadding(0, bars.top, 0, bars.bottom)
            insets
        }
        return col
    }

    fun cardBg(ctx: Context, color: Int = CARD, radius: Int = 18) = GradientDrawable().apply {
        cornerRadius = dp(ctx, radius).toFloat()
        setColor(color)
        setStroke(dp(ctx, 1), CARD_LINE)
    }

    fun card(ctx: Context): LinearLayout = LinearLayout(ctx).apply {
        orientation = LinearLayout.VERTICAL
        background = cardBg(ctx)
        setPadding(dp(ctx, 16), dp(ctx, 14), dp(ctx, 16), dp(ctx, 14))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(ctx, 12) }
    }

    fun text(ctx: Context, s: CharSequence, size: Float = 15f, color: Int = TEXT, bold: Boolean = false, mono: Boolean = false) = TextView(ctx).apply {
        text = s
        textSize = size
        setTextColor(color)
        if (mono) typeface = Typeface.MONOSPACE
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

    fun ltr(v: TextView) = v.apply {
        layoutDirection = View.LAYOUT_DIRECTION_LTR
        textDirection = View.TEXT_DIRECTION_LTR
    }

    /** A labelled number field that reports each change. */
    fun field(ctx: Context, parent: LinearLayout, label: String, value: String, number: Boolean = true, onChange: (String) -> Unit = {}): EditText {
        val row = LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        row.addView(text(ctx, label, 14f, DIM), LinearLayout.LayoutParams(0, -2, 1f))
        val e = EditText(ctx).apply {
            inputType = if (number) InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED
                else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            setText(value)
            setTextColor(TEXT)
            setHintTextColor(DIM)
            gravity = Gravity.END
            textSize = 16f
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun afterTextChanged(s: Editable?) = onChange(s.toString())
            })
        }
        row.addView(e, LinearLayout.LayoutParams(dp(ctx, 140), -2))
        parent.addView(row)
        return e
    }

    /** A progress line: label, value of target, and a bar that fills when shown. */
    fun progress(ctx: Context, parent: LinearLayout, label: String, value: Double, target: Double, unit: String) {
        val done = value >= target - 1e-6
        val head = LinearLayout(ctx).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(text(ctx, (if (done) "✅ " else "") + label, 14f, if (done) GOOD else TEXT), LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(ltr(text(ctx, "%s / %s %s".format(num(value), num(target), unit), 13f, DIM, mono = true)))
        parent.addView(head, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(ctx, 10) })
        val bar = ProgressBar(ctx, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000
            progress = 0
            progressTintList = android.content.res.ColorStateList.valueOf(if (done) GOOD else ACCENT)
            progressBackgroundTintList = android.content.res.ColorStateList.valueOf(CARD_LINE)
        }
        parent.addView(bar, LinearLayout.LayoutParams(-1, dp(ctx, 8)).apply { topMargin = dp(ctx, 4) })
        val goal = ((value / target).coerceIn(0.0, 1.0) * 1000).toInt()
        android.animation.ObjectAnimator.ofInt(bar, "progress", 0, goal).apply {
            duration = 900
            startDelay = 150
            interpolator = DecelerateInterpolator()
            start()
        }
    }

    fun num(v: Double) = if (Math.abs(v - Math.round(v)) < 0.05) Math.round(v).toString() else "%.1f".format(v)

    /** Children rise and fade in one after another. */
    fun stagger(group: LinearLayout, from: Int = 0) {
        for (i in from until group.childCount) {
            val v = group.getChildAt(i)
            v.alpha = 0f
            v.translationY = dp(group.context, 26).toFloat()
            v.animate().alpha(1f).translationY(0f).setStartDelay(40L * (i - from)).setDuration(420)
                .setInterpolator(OvershootInterpolator(0.8f)).start()
        }
    }

    /** A small press: the view dips and springs back. */
    fun pressable(v: View, onClick: () -> Unit) {
        v.isClickable = true
        v.setOnClickListener {
            v.animate().scaleX(0.95f).scaleY(0.95f).setDuration(80).withEndAction {
                v.animate().scaleX(1f).scaleY(1f).setDuration(160).setInterpolator(OvershootInterpolator(2f)).start()
                onClick()
            }.start()
        }
    }
}
