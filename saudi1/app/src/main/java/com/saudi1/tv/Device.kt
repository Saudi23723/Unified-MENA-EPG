package com.saudi1.tv

import okhttp3.Request
import org.json.JSONObject

/** Activation through the owner's admin site: the TV shows its code, the owner adds the login there,
 *  Reload picks it up. A login typed by hand on the TV (Settings) is kept as it is. */
object Device {
    private const val API = "https://saudi1.1saifsaudi.workers.dev/api/device"

    val code: String
        get() {
            var c = App.prefs.getString("device_code", "") ?: ""
            if (c.length != 8) {
                val r = java.security.SecureRandom()
                c = (1..8).map { if (it == 1) 1 + r.nextInt(9) else r.nextInt(10) }.joinToString("")
                App.prefs.edit().putString("device_code", c).apply()
            }
            return c
        }

    val pretty get() = code.substring(0, 4) + " " + code.substring(4)

    var manual: Boolean
        get() = App.prefs.getBoolean("manual_login", false)
        set(v) = App.prefs.edit().putBoolean("manual_login", v).apply()

    var name: String
        get() = App.prefs.getString("customer", "") ?: ""
        private set(v) = App.prefs.edit().putString("customer", v).apply()

    var expires: Long
        get() = App.prefs.getLong("expires", 0)
        private set(v) = App.prefs.edit().putLong("expires", v).apply()

    /** "active" | "pending" | "stopped" | "expired" | "offline" */
    fun check(): String = try {
        val u = "$API?code=$code&model=" + java.net.URLEncoder.encode(android.os.Build.MODEL, "UTF-8")
        App.http.newCall(Request.Builder().url(u).build()).execute().use { r ->
            val o = JSONObject(r.body!!.string())
            val st = o.optString("status")
            if (st == "active") {
                val changed = Prefs.server != o.optString("server") || Prefs.user != o.optString("user") || Prefs.pass != o.optString("pass")
                Prefs.server = o.optString("server"); Prefs.user = o.optString("user"); Prefs.pass = o.optString("pass")
                name = o.optString("name"); expires = o.optLong("expires")
                manual = false
                if (changed) Api.groups = emptyList()
            } else if (!manual && (st == "stopped" || st == "expired")) {
                Prefs.pass = ""  // the owner stopped this device: no more channels until he turns it on again
                Api.groups = emptyList()
            }
            st
        }
    } catch (e: Exception) { "offline" }
}
