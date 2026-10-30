package com.saudi.privatevault

import android.app.Activity
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/** The app in Arabic (as it started) or fully in English, whatever the phone's own language. */
object Lang {
    /** Arabic until the pilot picks otherwise. */
    fun init(ctx: android.content.Context) {
        val p = ctx.getSharedPreferences("lang", 0)
        if (!p.getBoolean("set", false)) {
            p.edit().putBoolean("set", true).apply()
            AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags("ar"))
        }
    }

    fun choose(act: Activity) {
        val now = AppCompatDelegate.getApplicationLocales().toLanguageTags()
        val tags = arrayOf("ar", "en")
        MaterialAlertDialogBuilder(act)
            .setTitle("🌐 اللغة · Language")
            .setSingleChoiceItems(arrayOf("العربية", "English"), if (now.startsWith("en")) 1 else 0) { d, i ->
                d.dismiss()
                AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tags[i]))
            }
            .show()
    }
}
