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
            var postedAt = 0L; var logged = false; var sent = false
            val tick = java.util.concurrent.atomic.AtomicBoolean(true)
            while (true) {
                try {
                    val now = android.os.SystemClock.uptimeMillis()
                    if (tick.get()) {
                        // the main thread answered: post the next tick
                        tick.set(false); postedAt = now; logged = false; sent = false
                        main.post { tick.set(true) }
                    } else {
                        val busy = now - postedAt
                        val st by lazy { Looper.getMainLooper().thread.stackTrace.take(30).joinToString("\n") { "  at $it" } }
                        // a stall the viewer feels (1.5 s): written to the device's log, to find its cause
                        if (busy > 1500 && !logged) { logged = true; android.util.Log.w("SAUDI", "main thread busy ${busy} ms\n$st") }
                        // a frozen screen (5 s, Android's "not responding"): sent to the admin site
                        if (busy > 5000 && !sent) { sent = true; send("freeze", "main thread busy for 5 s or more\n$st") }
                    }
                    Thread.sleep(500)
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

    /** something the app found and handled by itself (an off-air channel...), sent in the background */
    fun report(kind: String, info: String) { Thread({ try { send(kind, info) } catch (e: Throwable) { } }, "health-report").apply { isDaemon = true }.start() }

    private fun send(kind: String, info: String): Boolean = try {
        val body = JSONObject().put("code", Device.code).put("kind", kind).put("ver", BuildConfig.VERSION_NAME).put("info", info).toString()
        App.http.newCall(Request.Builder().url(Device.SITE + "/api/health")
            .post(body.toRequestBody("application/json".toMediaType())).build()).execute().use { it.isSuccessful }
    } catch (e: Throwable) { false }
}
