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
    // A modern EFB's night palette: near-black ground, raised graphite cards, one clear blue.
    const val BG = 0xFF0F1318.toInt()
    const val CARD = 0xFF1A2029.toInt()
    const val CARD_LINE = 0xFF29313D.toInt()
    const val ACCENT = 0xFF4DA3FF.toInt()
    const val TEXT = 0xFFF1F4F8.toInt()
    const val DIM = 0xFF8D97A8.toInt()
    const val GOOD = 0xFF34C759.toInt()
    const val WARN = 0xFFFFB020.toInt()
    const val BAD = 0xFFFF453A.toInt()

    fun dp(ctx: Context, v: Int) = (v * ctx.resources.displayMetrics.density).toInt()

    /** A dark screen with a toolbar and a scrolling column; returns the column. */
    fun screen(act: Activity, title: String, menu: ((MaterialToolbar) -> Unit)? = null): LinearLayout {
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
