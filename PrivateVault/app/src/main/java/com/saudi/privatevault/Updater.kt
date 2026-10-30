package com.saudi.privatevault

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.core.content.pm.PackageInfoCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * One-tap updates. Every CI build is published to the vault-builds-android
 * branch (latest.json + PrivateVault.apk); it is read through GitHub and,
 * where GitHub is unreachable, through the jsDelivr mirror of the same branch.
 */
object Updater {
    private val SOURCES = listOf(
        "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/vault-builds-android/",
        "https://cdn.jsdelivr.net/gh/Saudi23723/Unified-MENA-EPG@vault-builds-android/",
    )
    private const val CHECK_EVERY_MS = 6 * 60 * 60 * 1000L

    private class Latest(val code: Long, val name: String, val apkUrl: String)

    private var downloading = false

    /** On opening the app: at most every few hours, and silent when there is nothing new. */
    fun checkQuietly(a: AppCompatActivity) {
        val prefs = VaultLock.prefs(a)
        val now = System.currentTimeMillis()
        if (now - prefs.getLong("update_checked", 0) < CHECK_EVERY_MS) return
        prefs.edit().putLong("update_checked", now).apply()
        check(a, quiet = true)
    }

    fun check(a: AppCompatActivity, quiet: Boolean) {
        val mine = PackageInfoCompat.getLongVersionCode(a.packageManager.getPackageInfo(a.packageName, 0))
        val myName = a.packageManager.getPackageInfo(a.packageName, 0).versionName ?: ""
        a.lifecycleScope.launch {
            val latest = withContext(Dispatchers.IO) { fetchLatest() }
            when {
                latest == null -> if (!quiet) toast(a, a.getString(R.string.update_offline))
                latest.code <= mine -> if (!quiet) toast(a, a.getString(R.string.update_none, myName))
                else -> MaterialAlertDialogBuilder(a)
                    .setTitle(R.string.update_title)
                    .setMessage(a.getString(R.string.update_msg, latest.name, myName))
                    .setPositiveButton(R.string.update_now) { _, _ -> download(a, latest) }
                    .setNegativeButton(R.string.update_later, null)
                    .show()
            }
        }
    }

    /**
     * The newest build any source knows of: a mirror can lag behind for hours, so every source is
     * asked and the highest version wins; GitHub's API is asked too, as it is never cached for long.
     */
    private fun fetchLatest(): Latest? {
        val found = ArrayList<Latest>()
        for (base in SOURCES) {
            try {
                val json = JSONObject(read(base + "latest.json?t=" + System.currentTimeMillis()))
                found.add(Latest(json.getLong("versionCode"), json.optString("versionName"), base + json.getString("apk")))
            } catch (e: Exception) {
                // Try the next source.
            }
        }
        try {
            val api = JSONObject(read("https://api.github.com/repos/Saudi23723/Unified-MENA-EPG/contents/latest.json?ref=vault-builds-android"))
            val json = JSONObject(String(android.util.Base64.decode(api.getString("content"), android.util.Base64.DEFAULT)))
            found.add(Latest(json.getLong("versionCode"), json.optString("versionName"), SOURCES[0] + json.getString("apk")))
        } catch (e: Exception) {
        }
        return found.maxByOrNull { it.code }
    }

    private fun download(a: AppCompatActivity, latest: Latest) {
        if (downloading) return
        // Android asks once whether this app may install updates.
        if (!a.packageManager.canRequestPackageInstalls()) {
            toast(a, a.getString(R.string.update_allow))
            VaultLock.keepUnlockedOnce = true
            try {
                a.startActivity(
                    Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + a.packageName))
                )
            } catch (e: ActivityNotFoundException) {
                VaultLock.keepUnlockedOnce = false
            }
            return
        }
        downloading = true
        val dialog = MaterialAlertDialogBuilder(a)
            .setTitle(R.string.update_title)
            .setMessage(a.getString(R.string.update_downloading, 0))
            .setCancelable(false)
            .show()
        val dir = File(a.cacheDir, "update").apply { deleteRecursively(); mkdirs() }
        val apk = File(dir, "PrivateVault.apk")
        a.lifecycleScope.launch {
            val ok = withContext(Dispatchers.IO) {
                // The same file from whichever source answers.
                val urls = listOf(latest.apkUrl) + SOURCES.map { it + "PrivateVault.apk" }.filter { it != latest.apkUrl }
                urls.any { url ->
                    try {
                        save(url, apk) { pct -> a.runOnUiThread { dialog.setMessage(a.getString(R.string.update_downloading, pct)) } }
                        true
                    } catch (e: IOException) {
                        false
                    }
                }
            }
            dialog.dismiss()
            downloading = false
            if (!ok) {
                toast(a, a.getString(R.string.update_failed))
                return@launch
            }
            val uri = FileProvider.getUriForFile(a, a.packageName + ".files", apk)
            VaultLock.keepUnlockedOnce = true
            a.startActivity(
                Intent(Intent.ACTION_VIEW)
                    .setDataAndType(uri, "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }

    private fun open(url: String): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 8000
        conn.readTimeout = 30000
        conn.instanceFollowRedirects = true
        if (conn.responseCode != 200) {
            conn.disconnect()
            throw IOException("HTTP ${conn.responseCode}")
        }
        return conn
    }

    private fun read(url: String): String {
        val conn = open(url)
        try {
            return conn.inputStream.bufferedReader().readText()
        } finally {
            conn.disconnect()
        }
    }

    private fun save(url: String, target: File, progress: (Int) -> Unit) {
        val conn = open(url)
        try {
            val total = conn.contentLengthLong
            conn.inputStream.use { inp ->
                target.outputStream().use { out ->
                    val buf = ByteArray(256 * 1024)
                    var done = 0L
                    var last = -1
                    while (true) {
                        val n = inp.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        done += n
                        val pct = if (total > 0) (done * 100 / total).toInt() else 0
                        if (pct != last) {
                            last = pct
                            progress(pct)
                        }
                    }
                    if (total > 0 && done != total) throw IOException("cut short")
                }
            }
        } finally {
            conn.disconnect()
        }
    }

    private fun toast(a: AppCompatActivity, msg: String) = Toast.makeText(a, msg, Toast.LENGTH_LONG).show()
}
