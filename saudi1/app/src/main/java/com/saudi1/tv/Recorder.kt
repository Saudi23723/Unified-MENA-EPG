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
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Records a live channel to a file on the device (phones / tablets, or a USB stick on the TV) until the
 *  chosen time. Uses one more connection to the provider while it records. */
class RecordService : Service() {
    private var call: Call? = null
    private var thread: Thread? = null

    override fun onBind(i: Intent?): IBinder? = null

    override fun onStartCommand(i: Intent?, flags: Int, startId: Int): Int {
        if (i?.action == "stop") { call?.cancel(); stopSelf(); return START_NOT_STICKY }
        val url = i?.getStringExtra("url") ?: return START_NOT_STICKY
        val title = i.getStringExtra("title") ?: "Recording"
        val until = i.getLongExtra("until", System.currentTimeMillis() + 3600_000)
        val nm = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(NotificationChannel("rec", "Recording", NotificationManager.IMPORTANCE_LOW))
        val n = (if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, "rec") else Notification.Builder(this))
            .setSmallIcon(android.R.drawable.presence_video_online).setContentTitle("⏺ Recording").setContentText(title).setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(7, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC) else startForeground(7, n)
        val f = File(Recordings.dir(this), SimpleDateFormat("yyyy-MM-dd HH.mm", Locale.ENGLISH).format(Date()) + " · " + title.replace(Regex("[\\\\/:*?\"<>|]"), " ") + ".ts")
        Recorder.current = f.name
        // the recording goes on with the screen off / the TV in standby: the device and its Wi-Fi are kept awake
        val wake = try { (getSystemService(Context.POWER_SERVICE) as android.os.PowerManager).newWakeLock(android.os.PowerManager.PARTIAL_WAKE_LOCK, "saudi1:rec").apply { acquire(until - System.currentTimeMillis() + 60_000) } } catch (e: Exception) { null }
        val wifi = try { (applicationContext.getSystemService(Context.WIFI_SERVICE) as android.net.wifi.WifiManager).createWifiLock(android.net.wifi.WifiManager.WIFI_MODE_FULL_HIGH_PERF, "saudi1:rec").apply { acquire() } } catch (e: Exception) { null }
        thread = Thread {
            try {
                val c = App.http.newBuilder().readTimeout(30, java.util.concurrent.TimeUnit.SECONDS).build().newCall(Request.Builder().url(url).build())
                call = c
                c.execute().use { r ->
                    val ins = r.body!!.byteStream()
                    f.outputStream().use { out ->
                        val buf = ByteArray(64 * 1024)
                        while (System.currentTimeMillis() < until) {
                            val k = ins.read(buf); if (k < 0) break
                            out.write(buf, 0, k)
                        }
                    }
                }
            } catch (_: Exception) { } finally {
                try { if (wake?.isHeld == true) wake.release() } catch (_: Exception) { }
                try { if (wifi?.isHeld == true) wifi.release() } catch (_: Exception) { }
                Recorder.current = null
                stopSelf()
            }
        }.also { it.start() }
        return START_NOT_STICKY
    }

    override fun onDestroy() { call?.cancel(); Recorder.current = null; super.onDestroy() }
}

object Recorder {
    @Volatile var current: String? = null
    fun start(ctx: Context, c: Channel, until: Long) {
        val i = Intent(ctx, RecordService::class.java).putExtra("url", Api.streamUrl(c)).putExtra("title", c.name).putExtra("until", until)
        if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
    }
    fun stop(ctx: Context) = ctx.startService(Intent(ctx, RecordService::class.java).setAction("stop"))
}

object Recordings {
    /** a USB stick when one is plugged in, else the device's own storage */
    fun dir(ctx: Context): File {
        val ext = ctx.getExternalFilesDirs(android.os.Environment.DIRECTORY_MOVIES).filterNotNull()
        val usb = ext.drop(1).firstOrNull { it.canWrite() }
        return (usb ?: ext.firstOrNull() ?: File(ctx.filesDir, "rec")).also { it.mkdirs() }
    }
    fun all(ctx: Context): List<File> =
        ctx.getExternalFilesDirs(android.os.Environment.DIRECTORY_MOVIES).filterNotNull().flatMap { it.listFiles()?.toList() ?: emptyList() }
            .filter { it.name.endsWith(".ts") }.sortedByDescending { it.lastModified() }
    fun free(ctx: Context): Long = dir(ctx).usableSpace
}
