package com.saudi.privatevault

import android.app.Activity
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/** How documents are shown: as they are, dark for night, or warm paper. */
enum class ReadingMode(val label: Int, val background: Int, val text: Int) {
    NORMAL(R.string.read_normal, Color.WHITE, Color.BLACK),

    // Not pure black and white: light-grey text on near-black is easier on the eyes.
    NIGHT(R.string.read_night, Color.rgb(18, 18, 18), Color.rgb(205, 205, 200)),
    WARM(R.string.read_warm, Color.rgb(244, 236, 216), Color.rgb(91, 70, 54));

    /** Turns a rendered white page into this mode's colours; null leaves it as is. */
    fun pageFilter(): ColorMatrixColorFilter? = when (this) {
        NORMAL -> null
        // Invert, then squeeze into the range between this mode's background and text.
        NIGHT -> {
            val bg = 18f
            val fg = 205f
            val k = (fg - bg) / 255f
            ColorMatrixColorFilter(
                ColorMatrix(
                    floatArrayOf(
                        -k, 0f, 0f, 0f, fg,
                        0f, -k, 0f, 0f, fg,
                        0f, 0f, -k, 0f, fg - 5f,
                        0f, 0f, 0f, 1f, 0f,
                    )
                )
            )
        }
        // Keep dark text dark and tint the white paper towards a warm cream.
        WARM -> ColorMatrixColorFilter(
            ColorMatrix(
                floatArrayOf(
                    0.957f, 0f, 0f, 0f, 0f,
                    0f, 0.925f, 0f, 0f, 0f,
                    0f, 0f, 0.847f, 0f, 0f,
                    0f, 0f, 0f, 1f, 0f,
                )
            )
        )
    }

    companion object {
        fun current(a: Activity): ReadingMode =
            entries.getOrElse(VaultLock.prefs(a).getInt("read_mode", 0)) { NORMAL }

        /** Lets the reader pick a mode and remembers it for every document. */
        fun choose(a: Activity, changed: (ReadingMode) -> Unit) {
            val labels = entries.map { a.getString(it.label) }.toTypedArray()
            MaterialAlertDialogBuilder(a)
                .setTitle(R.string.read_mode)
                .setSingleChoiceItems(labels, current(a).ordinal) { d, which ->
                    VaultLock.prefs(a).edit().putInt("read_mode", which).apply()
                    d.dismiss()
                    changed(entries[which])
                }
                .show()
        }
    }
}
