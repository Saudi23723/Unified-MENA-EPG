package com.saudi.privatevault

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.util.Log
import android.widget.TextView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.io.File

/**
 * When the app stops by itself, why it stopped is written down; the next
 * time it opens, it is shown once, to copy or screenshot and send.
 */
object CrashReport {
    private fun file(ctx: Context) = File(ctx.filesDir, "last_crash.txt")

    fun install(ctx: Context) {
        val app = ctx.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            try {
                val v = try { app.packageManager.getPackageInfo(app.packageName, 0).versionName } catch (x: Exception) { "?" }
                file(app).writeText("SSEFB $v · ${java.util.Date()}\nthread: ${t.name}\n\n${Log.getStackTraceString(e)}")
            } catch (x: Throwable) {
            }
            previous?.uncaughtException(t, e)
        }
    }

    fun showIfAny(act: Activity) {
        val f = file(act)
        if (!f.exists()) return
        val text = try { f.readText() } catch (e: Exception) { "" }
        f.delete()
        if (text.isBlank()) return
        val short = text.lines().take(40).joinToString("\n")
        MaterialAlertDialogBuilder(act)
            .setTitle(R.string.crash_title)
            .setView(android.widget.ScrollView(act).apply {
                addView(TextView(act).apply {
                    this.text = short
                    textSize = 11f
                    typeface = android.graphics.Typeface.MONOSPACE
                    setTextIsSelectable(true)
                    setPadding(40, 20, 40, 20)
                })
            })
            .setPositiveButton(R.string.crash_copy) { _, _ ->
                (act.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("crash", text))
            }
            .setNegativeButton(android.R.string.ok, null)
            .show()
    }
}
