package com.saudi1.tv

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import okhttp3.Call
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

/** Movies / episodes saved on the phone or tablet to watch without internet.
 *  One at a time (one connection to the provider), continues where it stopped. */
class DlItem(val key: String, val title: String, val poster: String, val url: String, val file: String, var size: Long, var done: Boolean)

object Downloads {
    @Volatile var active: String? = null
    @Volatile var progress = 0     // 0..1000 of the active one

    private fun read(): MutableList<DlItem> = try {
        val a = JSONArray(App.prefs.getString("downloads", "[]"))
        (0 until a.length()).map { a.getJSONObject(it) }.map {
            DlItem(it.getString("k"), it.optString("t"), it.optString("p"), it.optString("u"), it.optString("f"), it.optLong("s"), it.optBoolean("d"))
        }.toMutableList()
    } catch (e: Exception) { mutableListOf() }

    @Synchronized private fun write(l: List<DlItem>) {
        val a = JSONArray()
        l.forEach { a.put(JSONObject().put("k", it.key).put("t", it.title).put("p", it.poster).put("u", it.url).put("f", it.file).put("s", it.size).put("d", it.done)) }
        App.prefs.edit().putString("downloads", a.toString()).apply()
    }

    fun all(): List<DlItem> = read()
    fun get(key: String) = read().firstOrNull { it.key == key }
    fun localFile(key: String): File? = get(key)?.takeIf { it.done }?.let { File(it.file) }?.takeIf { it.exists() }

    fun dir(ctx: Context): File =
        (ctx.getExternalFilesDir(android.os.Environment.DIRECTORY_MOVIES) ?: File(ctx.filesDir, "dl")).resolve("downloads").also { it.mkdirs() }

    fun add(ctx: Context, key: String, title: String, poster: String, url: String) {
        val l = read()
        if (l.any { it.key == key }) return
        val ext = url.substringAfterLast('.', "mp4").take(5)
        val f = File(dir(ctx), key + "." + ext)
        l.add(DlItem(key, title, poster, url, f.absolutePath, 0, false))
        write(l)
        start(ctx)
    }

    fun remove(ctx: Context, key: String) {
        val l = read()
        l.firstOrNull { it.key == key }?.let { File(it.file).delete(); File(it.file + ".part").delete() }
        write(l.filterNot { it.key == key })
        if (active == key) ctx.startService(Intent(ctx, DownloadService::class.java).setAction("skip"))
    }

    fun update(key: String, size: Long, done: Boolean) {
        val l = read(); l.firstOrNull { it.key == key }?.let { it.size = size; it.done = done }; write(l)
    }

    fun next(): DlItem? = read().firstOrNull { !it.done }

    fun start(ctx: Context) {
        val i = Intent(ctx, DownloadService::class.java)
        if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
    }
}

class DownloadService : Service() {
    @Volatile private var call: Call? = null
    @Volatile private var running = false
    override fun onBind(i: Intent?): IBinder? = null

    private fun note(text: String, pct: Int): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(NotificationChannel("dl", "Downloads", NotificationManager.IMPORTANCE_LOW))
        return (if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, "dl") else Notification.Builder(this))
            .setSmallIcon(android.R.drawable.stat_sys_download).setContentTitle("SAUDI.TV · Downloading").setContentText(text)
            .setProgress(100, pct, pct < 0).setOngoing(true).build()
    }

    override fun onStartCommand(i: Intent?, flags: Int, startId: Int): Int {
        if (i?.action == "skip") { call?.cancel(); return START_NOT_STICKY }
        val n = note("Starting…", -1)
        if (Build.VERSION.SDK_INT >= 29) startForeground(8, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC) else startForeground(8, n)
        if (running) return START_NOT_STICKY
        running = true
        Thread {
            val nm = getSystemService(NotificationManager::class.java)
            val client = App.http.newBuilder().readTimeout(60, java.util.concurrent.TimeUnit.SECONDS).build()
            var fails = 0
            while (true) {
                val it = Downloads.next() ?: break
                Downloads.active = it.key; Downloads.progress = 0
                val part = File(it.file + ".part")
                try {
                    val have = if (part.exists()) part.length() else 0L
                    val req = Request.Builder().url(it.url).apply { if (have > 0) header("Range", "bytes=$have-") }.build()
                    val c = client.newCall(req); call = c
                    c.execute().use { r ->
                        if (!r.isSuccessful) throw java.io.IOException("HTTP ${r.code}")
                        val resumed = r.code == 206
                        val total = (r.body!!.contentLength().takeIf { l -> l > 0 } ?: 0L) + (if (resumed) have else 0L)
                        FileOutputStream(part, resumed).use { out ->
                            val ins = r.body!!.byteStream(); val buf = ByteArray(128 * 1024)
                            var got = if (resumed) have else 0L; var last = 0L
                            while (true) {
                                val k = ins.read(buf); if (k < 0) break
                                out.write(buf, 0, k); got += k
                                if (System.currentTimeMillis() - last > 1500) {
                                    last = System.currentTimeMillis()
                                    val pct = if (total > 0) (got * 100 / total).toInt() else -1
                                    Downloads.progress = if (total > 0) (got * 1000 / total).toInt() else 0
                                    nm.notify(8, note(it.title + if (pct >= 0) "  ·  $pct %" else "", pct))
                                }
                            }
                            Downloads.update(it.key, got, false)
                        }
                    }
                    if (Downloads.get(it.key) != null) { part.renameTo(File(it.file)); Downloads.update(it.key, File(it.file).length(), true) }
                    fails = 0
                } catch (e: Exception) {
                    if (Downloads.get(it.key) == null) continue          // removed by the viewer
                    if (++fails >= 3) break                               // no internet: stop, continues next time
                    Thread.sleep(5000)
                }
            }
            Downloads.active = null; running = false
            stopForeground(true); stopSelf()
        }.start()
        return START_NOT_STICKY
    }

    override fun onDestroy() { call?.cancel(); super.onDestroy() }
}
