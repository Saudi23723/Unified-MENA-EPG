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

    var active: String
        get() = App.prefs.getString("active_pl", "") ?: ""
        set(v) = App.prefs.edit().putString("active_pl", v).apply()

    /** the playlists this device may use (from the admin site): name, server, user, pass */
    fun playlists(): List<JSONObject> = try {
        val a = org.json.JSONArray(App.prefs.getString("playlists", "[]")); (0 until a.length()).map { a.getJSONObject(it) }
    } catch (e: Exception) { emptyList() }

    /** switch to another of this device's playlists */
    fun use(p: JSONObject) {
        active = p.optString("name")
        Prefs.server = p.optString("server"); Prefs.user = p.optString("user"); Prefs.pass = p.optString("pass")
        Api.groups = emptyList()
        java.io.File(App.app.filesDir, "live_categories.json").delete(); java.io.File(App.app.filesDir, "live_streams.json").delete()
        Vod.clear()
    }

    /** "active" | "pending" | "stopped" | "expired" | "offline" */
    fun check(): String = try {
        val u = "$API?code=$code&model=" + java.net.URLEncoder.encode(android.os.Build.MODEL, "UTF-8")
        App.http.newCall(Request.Builder().url(u).build()).execute().use { r ->
            val o = JSONObject(r.body!!.string())
            val st = o.optString("status")
            if (st == "active") {
                // the playlists the owner gave this device; the one picked on the Playlists screen stays picked
                val arr = o.optJSONArray("playlists")
                val lists = if (arr != null && arr.length() > 0) (0 until arr.length()).map { arr.getJSONObject(it) }
                    else listOf(JSONObject().put("name", "").put("server", o.optString("server")).put("user", o.optString("user")).put("pass", o.optString("pass")))
                App.prefs.edit().putString("playlists", org.json.JSONArray(lists).toString()).apply()
                val pick = lists.firstOrNull { it.optString("name") == active } ?: lists[0]
                val changed = Prefs.server != pick.optString("server") || Prefs.user != pick.optString("user") || Prefs.pass != pick.optString("pass")
                Prefs.server = pick.optString("server"); Prefs.user = pick.optString("user"); Prefs.pass = pick.optString("pass")
                active = pick.optString("name")
                name = o.optString("name"); expires = o.optLong("expires")
                // the VPN the owner put on the admin site (an empty one there keeps a file imported on the phone)
                o.optString("vpn").takeIf { it.isNotBlank() }?.let { if (it != Vpn.conf) { Vpn.conf = it; Vpn.wanted = true } }
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
