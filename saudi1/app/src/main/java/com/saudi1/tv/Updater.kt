package com.saudi1.tv

import android.content.Intent
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
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

    /** download the newest app and hand it to Android's installer */
    fun install(a: AppCompatActivity, build: Int) {
        a.lifecycleScope.launch {
            val toast = { s: String -> android.widget.Toast.makeText(a, s, android.widget.Toast.LENGTH_LONG).show() }
            toast("Downloading version 1.0.$build…")
            val f = File(a.cacheDir, "update.apk")
            val ok = withContext(Dispatchers.IO) {
                try {
                    App.http.newCall(Request.Builder().url(BASE + "SAUDI1.apk").build()).execute()
                        .use { r -> if (!r.isSuccessful) false else { f.outputStream().use { o -> r.body!!.byteStream().copyTo(o) }; true } }
                } catch (e: Exception) { false }
            }
            if (!ok) { toast("Download failed"); return@launch }
            val uri = FileProvider.getUriForFile(a, "${a.packageName}.files", f)
            a.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
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
