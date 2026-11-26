package com.saudi1.tv

import android.content.Intent
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.withResumed
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.File

/** Updates (owner, 25 Nov 2026: "tell the customer by itself when a new version is out"). Settings › Check for update
 *  as before, and the Home screen checks by itself (at most every 6 hours) and offers the new version:
 *  Update now / Later (Later = asked again the next day). */
object Updater {
    private const val BASE = "https://github.com/Saudi23723/Unified-MENA-EPG/releases/download/saudi1/"

    /** newest build number on the release; -1 = could not check */
    suspend fun newest(): Int = withContext(Dispatchers.IO) {
        try {
            App.http.newCall(Request.Builder().url(BASE + "version.txt?t=" + System.currentTimeMillis() / 60000).build()).execute()
                .use { it.body!!.string().trim().substringAfter("build ").toIntOrNull() ?: 0 }
        } catch (e: Exception) { -1 }
    }

    @Volatile private var busy = false

    /** download the newest app and hand it to Android's installer. One press is enough (owner, 26 Nov 2026: "it says
     *  Downloading and nothing happens, I have to press again"): the download shows its progress and keeps the screen,
     *  a second press while it runs does nothing, a version already downloaded is not downloaded again, and the
     *  installer opens as soon as the screen is in front (Android refuses it from behind). */
    fun install(a: AppCompatActivity, build: Int) {
        if (busy) return
        busy = true
        val f = File(a.cacheDir, "update_$build.apk")
        val bar = android.widget.ProgressBar(a, null, android.R.attr.progressBarStyleHorizontal).apply { max = 100; isIndeterminate = true }
        val msg = android.widget.TextView(a).apply { text = "Downloading…"; textSize = 16f }
        val box = android.widget.LinearLayout(a).apply {
            orientation = android.widget.LinearLayout.VERTICAL; val p = (24 * a.resources.displayMetrics.density).toInt()
            setPadding(p, p / 2, p, 0); addView(msg); addView(bar)
        }
        val dlg = AlertDialog.Builder(a).setTitle("Version 1.0.$build").setView(box).setCancelable(false).show()
        a.lifecycleScope.launch {
            try {
                val ok = withContext(Dispatchers.IO) {
                    val done = App.prefs.getLong("upd_len_$build", -1)
                    if (f.isFile && f.length() == done && done > 0) return@withContext true
                    a.cacheDir.listFiles()?.filter { it.name.startsWith("update") && it.name.endsWith(".apk") }?.forEach { it.delete() }
                    try {
                        App.http.newCall(Request.Builder().url(BASE + "SAUDI1.apk").build()).execute().use { r ->
                            if (!r.isSuccessful) return@use false
                            val body = r.body!!; val total = body.contentLength()
                            var got = 0L; var shown = -1
                            f.outputStream().use { o -> body.byteStream().use { i ->
                                val buf = ByteArray(64 * 1024)
                                while (true) {
                                    val n = i.read(buf); if (n < 0) break
                                    o.write(buf, 0, n); got += n
                                    val pc = if (total > 0) (got * 100 / total).toInt() else -1
                                    if (pc != shown) { shown = pc; withContext(Dispatchers.Main) {
                                        if (pc >= 0) { bar.isIndeterminate = false; bar.progress = pc; msg.text = "Downloading…  $pc%" }
                                        else msg.text = "Downloading…  ${got / 1048576} MB"
                                    } }
                                }
                            } }
                            if (total > 0 && got != total) false
                            else { App.prefs.edit().putLong("upd_len_$build", f.length()).apply(); true }
                        }
                    } catch (e: Exception) { false }
                }
                try { dlg.dismiss() } catch (e: Exception) { }
                if (!ok) { android.widget.Toast.makeText(a, "Download failed — check the internet and try again", android.widget.Toast.LENGTH_LONG).show(); return@launch }
                val uri = FileProvider.getUriForFile(a, "${a.packageName}.files", f)
                a.lifecycle.withResumed {
                    a.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
                }
            } finally { busy = false; try { dlg.dismiss() } catch (e: Exception) { } }
        }
    }

    /** Home screen: a quiet check; a newer version = a small question */
    fun offer(a: AppCompatActivity) {
        val p = App.prefs; val now = System.currentTimeMillis()
        if (now - p.getLong("upd_checked", 0) < 6 * 3600_000L) return
        a.lifecycleScope.launch {
            val n = newest()
            if (n < 0) return@launch
            p.edit().putLong("upd_checked", now).apply()
            if (n <= BuildConfig.VERSION_CODE) return@launch
            // "Later" for this version: asked again a day later
            if (p.getInt("upd_later", 0) == n && now - p.getLong("upd_later_at", 0) < 24 * 3600_000L) return@launch
            // only on Home in front, never over the welcome or another screen
            if (a.isFinishing || a.isDestroyed || !a.lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.RESUMED)) {
                p.edit().putLong("upd_checked", 0).apply(); return@launch }
            AlertDialog.Builder(a).setTitle("New version 1.0.$n")
                .setMessage("A new version of SAUDI.TV is ready.")
                // the download and the installer run from Settings, in front (from Home, Android blocked the
                // installer when Home had gone behind another screen: "Update now" did nothing, 26 Nov 2026)
                .setPositiveButton("Update now") { _, _ -> a.startActivity(Intent(a, SettingsActivity::class.java).putExtra("update_now", true)) }
                .setNegativeButton("Later") { _, _ -> p.edit().putInt("upd_later", n).putLong("upd_later_at", System.currentTimeMillis()).apply() }
                .show()
        }
    }
}
