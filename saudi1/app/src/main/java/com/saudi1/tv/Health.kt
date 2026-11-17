package com.saudi1.tv

import android.os.Handler
import android.os.Looper
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/** The app's own health report (owner, 13 Nov 2026: "make sure these errors never happen again").
 *  - the app stopped by an error: the error kept by App (last_error.txt) is sent the next time the app opens;
 *  - the screen froze (the app's main thread busy for 5 s or more, what Android calls "not responding"): what the
 *    app was doing at that moment is sent.
 *  Both land on the admin site (Dashboard › صحة التطبيق), so a problem on any TV is seen the same day, with its cause.
 *  It only watches and reports: nothing here touches the player, the screens or the keys. */
object Health {
    private var started = false

    fun start() {
        if (started) return
        started = true
        Thread({ try { sendCrash() } catch (e: Throwable) { } }, "health-send").apply { isDaemon = true }.start()
        watch()
    }

    /** a light thread: every 5 s it asks the main thread to tick; no tick in 5 s means the screen is frozen */
    private fun watch() {
        val main = Handler(Looper.getMainLooper())
        Thread({
            var told = false
            while (true) {
                try {
                    val tick = java.util.concurrent.atomic.AtomicBoolean(false)
                    main.post { tick.set(true) }
                    Thread.sleep(5000)
                    if (!tick.get()) {
                        if (!told) {
                            told = true   // one report for one freeze, not one every 5 s
                            val st = Looper.getMainLooper().thread.stackTrace.take(30).joinToString("\n") { "  at $it" }
                            send("freeze", "main thread busy for 5 s or more\n$st")
                        }
                    } else told = false
                } catch (e: Throwable) {
                    try { Thread.sleep(5000) } catch (x: Throwable) { }
                }
            }
        }, "health-watch").apply { isDaemon = true; priority = Thread.MIN_PRIORITY }.start()
    }

    /** the error that stopped the app last time, once */
    private fun sendCrash() {
        val f = java.io.File(App.app.filesDir, "last_error.txt")
        if (!f.isFile) return
        val at = f.lastModified()
        if (App.prefs.getLong("health_crash_sent", 0) >= at) return
        if (send("crash", f.readText().take(6000))) App.prefs.edit().putLong("health_crash_sent", at).apply()
    }

    private fun send(kind: String, info: String): Boolean = try {
        val body = JSONObject().put("code", Device.code).put("kind", kind).put("ver", BuildConfig.VERSION_NAME).put("info", info).toString()
        App.http.newCall(Request.Builder().url(Device.SITE + "/api/health")
            .post(body.toRequestBody("application/json".toMediaType())).build()).execute().use { it.isSuccessful }
    } catch (e: Throwable) { false }
}
