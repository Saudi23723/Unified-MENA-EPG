package com.saudi.privatevault

import android.app.Activity
import android.content.Context
import android.view.View
import android.widget.FrameLayout
import java.util.Calendar

/**
 * Eye comfort: a warm amber veil that takes the blue out of the screen, and a dimming
 * over it, laid over every screen of the app (it lets every touch and key through).
 * On, off, or at night only (from 7 pm to 6 am).
 */
object EyeComfort {
    private const val TAG = "eye_comfort"
    val WARM = intArrayOf(0, 18, 32, 46)      // percent of the amber veil
    val DIM = intArrayOf(0, 25, 45, 65)       // percent of black over it

    private fun prefs(ctx: Context) = VaultLock.prefs(ctx)
    fun mode(ctx: Context) = prefs(ctx).getString("eye_mode", "off") ?: "off"
    fun warm(ctx: Context) = prefs(ctx).getInt("eye_warm", 2).coerceIn(0, 3)
    fun dim(ctx: Context) = prefs(ctx).getInt("eye_dim", 1).coerceIn(0, 3)

    fun set(ctx: Context, mode: String? = null, warm: Int? = null, dim: Int? = null) {
        prefs(ctx).edit().apply {
            mode?.let { putString("eye_mode", it) }
            warm?.let { putInt("eye_warm", it) }
            dim?.let { putInt("eye_dim", it) }
        }.apply()
    }

    private fun active(ctx: Context): Boolean = when (mode(ctx)) {
        "on" -> true
        "night" -> Calendar.getInstance().get(Calendar.HOUR_OF_DAY).let { it >= 19 || it < 6 }
        else -> false
    }

    /** Lays the veil over the screen, or takes it off, as the settings say now. */
    fun apply(act: Activity) {
        val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
        var v = content.findViewWithTag<View>(TAG)
        if (!active(act)) { v?.let { content.removeView(it) }; return }
        if (v == null) {
            v = View(act).apply {
                tag = TAG
                isClickable = false; isFocusable = false; importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                elevation = 1000f
            }
            content.addView(v, FrameLayout.LayoutParams(-1, -1))
        } else v.bringToFront()
        v.setBackgroundColor(color(warm(act), dim(act)))
    }

    /** The amber veil and the black, blended into one colour over the screen. */
    fun color(warmStep: Int, dimStep: Int): Int {
        val w = WARM[warmStep] / 100f
        val k = DIM[dimStep] / 100f
        // Amber (255, 147, 41) at w, then black at k on top: one colour and one alpha.
        val a = 1 - (1 - w) * (1 - k)
        if (a <= 0f) return 0
        val r = (255 * w * (1 - k) / a).toInt()
        val g = (147 * w * (1 - k) / a).toInt()
        val b = (41 * w * (1 - k) / a).toInt()
        return ((a * 255).toInt() shl 24) or (r shl 16) or (g shl 8) or b
    }

    /** The choices, as a TV-friendly dialog: mode, warmth, dimming; each change shows at once. */
    fun choose(act: Activity) {
        val modes = arrayOf("off", "on", "night")
        val modeNames = arrayOf(act.getString(R.string.eye_off), act.getString(R.string.eye_on), act.getString(R.string.eye_night))
        val levels = arrayOf(act.getString(R.string.eye_l0), act.getString(R.string.eye_l1), act.getString(R.string.eye_l2), act.getString(R.string.eye_l3))
        fun step(title: Int, now: Int, onPick: (Int) -> Unit) {
            com.google.android.material.dialog.MaterialAlertDialogBuilder(act)
                .setTitle(title)
                .setSingleChoiceItems(levels, now) { d, i -> onPick(i); apply(act); d.dismiss(); choose(act) }
                .setNegativeButton(android.R.string.ok, null)
                .show()
        }
        val items = arrayOf(
            act.getString(R.string.eye_mode) + ":  " + modeNames[modes.indexOf(mode(act)).coerceAtLeast(0)],
            act.getString(R.string.eye_warm) + ":  " + levels[warm(act)],
            act.getString(R.string.eye_dim) + ":  " + levels[dim(act)],
        )
        com.google.android.material.dialog.MaterialAlertDialogBuilder(act)
            .setTitle(R.string.eye_title)
            .setItems(items) { _, i ->
                when (i) {
                    0 -> com.google.android.material.dialog.MaterialAlertDialogBuilder(act).setTitle(R.string.eye_mode)
                        .setSingleChoiceItems(modeNames, modes.indexOf(mode(act)).coerceAtLeast(0)) { d, k -> set(act, mode = modes[k]); apply(act); d.dismiss(); choose(act) }
                        .show()
                    1 -> step(R.string.eye_warm, warm(act)) { set(act, warm = it) }
                    2 -> step(R.string.eye_dim, dim(act)) { set(act, dim = it) }
                }
            }
            .setNegativeButton(android.R.string.ok, null)
            .show()
    }
}
